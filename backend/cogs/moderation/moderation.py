import discord
from discord.ext import commands
import datetime
from datetime import timezone
import asyncio
import time
import aiohttp
from ...utils.spam_engine import SpamEngine
from ...utils.image_spam import ImageSpamDetector
from ...utils.spam_intelligence import SpamIntelligence
from ..database.firebase_setup import db

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.engine = SpamEngine()
        self.img_detector = ImageSpamDetector()
        self.intel: SpamIntelligence | None = None
        self._session: aiohttp.ClientSession | None = None
        self.report_channel_id = 1517948052537868449
        self._join_timestamps: dict[int, list[float]] = {}
        self._raid_mode: dict[int, bool] = {}
        self._raid_lock: dict[int, float] = {}

    async def cog_load(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

        self.intel = SpamIntelligence(self.bot)
        await self.intel.ensure_cache_loaded()

        # Load persisted spam hashes + OCR counters dari Firestore
        await self._load_spam_hashes()
        await self.img_detector.load_ocr_counters()

    async def cog_unload(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _load_spam_hashes(self):
        if db is None:
            return
        try:
            docs = await asyncio.to_thread(
                lambda: list(db.collection("spam_hashes").stream())
            )
            hashes: dict[int, float] = {}
            for doc in docs:
                data = doc.to_dict()
                h = data.get("hash")
                t = data.get("flagged_at", 0)
                if h is not None:
                    hashes[h] = t
            self.img_detector.load_hashes(hashes)
            print(f"[MODERATION] ✅ Loaded {len(hashes)} spam hashes from Firestore")
        except Exception as e:
            print(f"[MODERATION] ⚠️ Gagal load spam hashes: {e}")

    async def _save_spam_hash(self, img_hash: int):
        if db is None:
            return
        try:
            doc_ref = db.collection("spam_hashes").document(str(img_hash))
            await asyncio.to_thread(
                doc_ref.set,
                {"hash": img_hash, "flagged_at": time.time()},
                merge=True,
            )
        except Exception as e:
            print(f"[MODERATION] ⚠️ Gagal simpan spam hash: {e}")

    async def _cleanup_expired_hashes(self):
        if db is None:
            return
        expired = self.img_detector.get_expired_hashes()
        if expired:
            print(f"[MODERATION] 🧹 Cleaned {len(expired)} expired spam hashes from memory (Firestore keeps permanent)")

    async def _get_config(self, guild_id: str) -> dict:
        if db is None:
            return {}
        try:
            doc_ref = db.collection("guild_settings").document(guild_id)
            doc = await asyncio.to_thread(doc_ref.get)
            if doc.exists:
                return doc.to_dict().get("moderation_config", {})
        except Exception:
            pass
        return {}

    async def _get_action(self, guild_id: str, strikes: int) -> dict:
        cfg = await self._get_config(guild_id)
        key = f"strike_{strikes}"
        defaults = {
            1: {"action": "timeout", "duration_hours": 24},
            2: {"action": "kick"},
            3: {"action": "ban"},
        }
        return cfg.get(key, defaults.get(strikes, {"action": "ban"}))

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            await self.bot.process_commands(message)
            return

        if message.guild and message.author.guild_permissions.administrator:
            await self.bot.process_commands(message)
            return

        if not message.guild:
            return

        guild_id = str(message.guild.id)

        self.engine.track_message(message)
        cfg = await self._get_config(guild_id)
        if not cfg.get("enabled", True):
            await self.bot.process_commands(message)
            return

        custom_kw = cfg.get("custom_keywords", [])
        current_score = self.engine.get_risk_score(message, custom_keywords=custom_kw)
        account_age = 0
        if hasattr(message.author, "created_at"):
            account_age = (datetime.datetime.now(timezone.utc) - message.author.created_at).days

        # ── Known threat pre-check ──
        image_urls = self.img_detector.extract_image_urls(message) if cfg.get("filter_image", True) and self._session else []
        if self.intel and image_urls:
            data = await self.img_detector.download_image(image_urls[0][0], self._session)
            if data:
                pre_hash = ImageSpamDetector.compute_hash(data)
                if pre_hash is not None:
                    pre_result = await self.intel.analyze(
                        content=message.content or "",
                        img_hash=pre_hash,
                        heuristic_score=current_score,
                        account_age_days=account_age,
                        author_id=str(message.author.id),
                        guild_id=guild_id,
                        channel_id=str(message.channel.id),
                    )
                    if pre_result["signatureExists"] and pre_result["confidence"] >= 85:
                        await self.handle_spam(message, f"Filter Intel: {pre_result['explanation']}")
                        return

        # ── Ban pattern / evasion check (young accounts only) ──
        if account_age < 60 and self.intel and message.content:
            evasion = await self.intel.check_ban_pattern(message.content, account_age_days=account_age)
            if evasion:
                await self.handle_spam(message, f"Filter Evasi: Pola scam cocok dengan pengguna yang di-ban sebelumnya ({evasion['matchType']}, bannedUser={evasion['bannedUser']})")
                return

        # ── Heuristic trigger (score >= 5) → skip AI kalo akun <60hr / join <7hr / score >=10 ──
        if cfg.get("filter_heuristic", True) and current_score >= 5:
            # ── Skip AI condition ──
            join_age_days = 999
            if hasattr(message.author, "joined_at") and message.author.joined_at:
                join_age_days = (datetime.datetime.now(timezone.utc) - message.author.joined_at).days

            skip_ai = account_age < 60 or join_age_days < 7 or current_score >= 10

            if not skip_ai and cfg.get("filter_ai", True):
                ai_cog = self.bot.get_cog("AIChat")
                if ai_cog:
                    is_ai_spam = await ai_cog.analyze_spam(
                        message.content,
                        risk_score=current_score,
                        account_age_days=account_age,
                    )
                    if is_ai_spam:
                        await self.handle_spam(message, "Filter AI: Diverifikasi sebagai spam oleh AI")
                        return
                    # AI disagrees → masih flag tapi hukuman diturunkan (timeout aja)
                    await self.handle_spam_light(message, "Filter Dasar: Pesan mencurigakan (dilemahkan oleh AI)")
                    return
            await self.handle_spam(message, "Filter Dasar: Terdeteksi kata kunci/link mencurigakan")
            return

        # ── New account heuristic ──
        if cfg.get("filter_new_account", True) and self.engine.is_new_account(message) and len(message.content) > 30:
            await self.handle_spam(message, "Filter Keamanan: Akun baru mengirim pesan panjang")
            return

        # ── Borderline (score 1-4) → AI decides ──
        if cfg.get("filter_ai", True) and 0 < current_score < 5 and len(message.content) > 10:
            ai_cog = self.bot.get_cog("AIChat")
            if ai_cog:
                is_ai_spam = await ai_cog.analyze_spam(
                    message.content,
                    risk_score=current_score,
                    account_age_days=account_age,
                )
                if is_ai_spam:
                    await self.handle_spam(message, "Filter AI: Terdeteksi konten mencurigakan oleh LLM")
                    return

        # ── Image spam check ──
        if cfg.get("filter_image", True) and self._session:
            image_urls = self.img_detector.extract_image_urls(message)
            if image_urls and await self._check_image_spam(message, image_urls, current_score):
                return

        await self.bot.process_commands(message)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild_id = member.guild.id

        # Auto-recover raid mode setelah 10 menit gak ada aktivitas
        if self._raid_mode.get(guild_id, False) and time.time() - self._raid_lock.get(guild_id, 0) > 600:
            self._raid_mode[guild_id] = False
            print(f"[RAID] ✅ Raid mode auto-recovered for {member.guild.name}")

        cfg = await self._get_config(str(guild_id))
        if not cfg.get("raid_protection", False) or not cfg.get("enabled", True):
            return

        now = time.time()
        window = cfg.get("raid_window", 300)
        threshold = cfg.get("raid_threshold", 10)
        action = cfg.get("raid_action", "kick")

        self._join_timestamps.setdefault(guild_id, [])
        self._join_timestamps[guild_id] = [
            t for t in self._join_timestamps[guild_id] if now - t < window
        ]
        self._join_timestamps[guild_id].append(now)

        if len(self._join_timestamps[guild_id]) >= threshold:
            if self._raid_mode.get(guild_id, False):
                if action == "ban":
                    await member.ban(reason="Raid protection: mass-join")
                elif action == "timeout":
                    await member.timeout(datetime.timedelta(hours=1), reason="Raid protection")
                else:
                    await member.kick(reason="Raid protection: mass-join")
                return

            self._raid_mode[guild_id] = True
            self._raid_lock[guild_id] = now

            if action == "ban":
                await member.ban(reason="Raid protection: mass-join")
            elif action == "timeout":
                await member.timeout(datetime.timedelta(hours=1), reason="Raid protection")
            else:
                await member.kick(reason="Raid protection: mass-join")

            report_ch_id = cfg.get("report_channel", "") or str(self.report_channel_id)
            report_channel = self.bot.get_channel(int(report_ch_id)) if report_ch_id else None
            if report_channel:
                await report_channel.send(
                    f"🚨 **Raid Protection**\n"
                    f"Mass-join detected in **{member.guild.name}**\n"
                    f"Threshold: {threshold} joins in {window//60} menit\n"
                    f"Action: {action.upper()}"
                )
            print(f"[RAID] ⚠️ Raid detected in {member.guild.name} - {len(self._join_timestamps[guild_id])} joins in {window//60}min")

    async def _check_image_spam(self, message, image_urls: list[tuple[str, str]], heuristic_score: int = 0) -> bool:
        """Check images in message. Returns True if flagged as spam."""
        guild_id = str(message.guild.id)
        cfg = await self._get_config(guild_id)
        user_id = str(message.author.id)
        flagged = False

        account_age = 0
        if hasattr(message.author, "created_at"):
            account_age = (datetime.datetime.now(timezone.utc) - message.author.created_at).days
        join_age_days = 999
        if hasattr(message.author, "joined_at") and message.author.joined_at:
            join_age_days = (datetime.datetime.now(timezone.utc) - message.author.joined_at).days

        for url, mime in image_urls:
            # Layer 1: Rate limit
            if self.img_detector.track_image_sent(user_id):
                await self.handle_spam(message, "Filter Gambar: Mengirim gambar terlalu cepat")
                return True

            # Download image
            data = await self.img_detector.download_image(url, self._session)
            if data is None:
                continue

            # Compute hash
            img_hash = self.img_detector.compute_hash(data)
            if img_hash is None:
                continue

            # Layer 2a: Known spam hash
            if self.img_detector.is_known_spam_hash(img_hash):
                flagged = True
                break

            # Layer 2b: Duplicate image from same user
            dup_count = self.img_detector.count_duplicate(user_id, img_hash)
            if dup_count >= self.img_detector.dup_threshold:
                await self.handle_spam(message, "Filter Gambar: Mengirim gambar yang sama berulang kali")
                return True

            # Layer 3: Gemini Vision (only for suspicious users)
            is_suspicious = account_age < 60 or join_age_days < 7
            is_flooding = self.img_detector.is_sending_images_fast(user_id)

            if is_suspicious or is_flooding or dup_count >= 2:
                cached = self.img_detector.get_vision_cache(img_hash)
                if cached is not None:
                    if cached:
                        flagged = True
                        break
                elif self.img_detector.can_call_vision():
                    ai_cog = self.bot.get_cog("AIChat")
                    if ai_cog:
                        vision_result = await ai_cog.analyze_image_spam(data, mime)
                        self.img_detector.set_vision_cache(img_hash, vision_result)
                        if vision_result:
                            flagged = True
                            break

            # ── Layer 3b: OCR fallback kalo Gemini Vision gak bisa / skip ──
            if not flagged and await self.img_detector.can_ocr():
                ocr_text = await self.img_detector.ocr_text_via_api(data, self._session)
                if ocr_text and self.img_detector.is_ocr_spam(ocr_text):
                    print(f"[OCR] Spam detected in image: '{ocr_text[:100]}'")
                    flagged = True
                    break

        if flagged:
            self.img_detector.flag_as_spam(img_hash)
            await self._save_spam_hash(img_hash)

            vision_reason = "Filter Gambar: Gambar mengandung konten spam/judi/scam"
            if self.intel and data:
                intel_result = await self.intel.analyze(
                    content=message.content or "",
                    image_data=data,
                    mime_type=mime,
                    heuristic_score=heuristic_score,
                    account_age_days=account_age,
                    join_age_days=join_age_days,
                    author_id=str(message.author.id),
                    img_hash=img_hash,
                    guild_id=guild_id,
                    channel_id=str(message.channel.id),
                )
                if intel_result["shouldStoreSignature"]:
                    signature = await self.intel.build_signature(
                        img_hash=img_hash,
                        confidence=intel_result["confidence"],
                        category=intel_result["threatCategory"],
                        indicators=intel_result["detectedIndicators"],
                        guild_id=guild_id,
                        user_id=str(message.author.id),
                        channel_id=str(message.channel.id),
                        domains=intel_result.get("domains"),
                        wallet_addresses=intel_result.get("walletAddresses"),
                        logos=intel_result.get("logos"),
                    )
                    await self.intel.store_threat_signature(signature)

                if intel_result["recommendation"] in ("AUTO_BAN", "AUTO_DELETE", "AUTO_KICK"):
                    vision_reason = f"Filter Intel: {intel_result['explanation']}"

            await self.handle_spam(message, vision_reason)
            return True

        # Periodic cleanup (once every 50 checks)
        if getattr(self, "_cleanup_counter", 0) % 50 == 0:
            asyncio.create_task(self._cleanup_expired_hashes())
        self._cleanup_counter = getattr(self, "_cleanup_counter", 0) + 1

        return False

    async def handle_spam(self, message, reason):
        try:
            guild_id = str(message.guild.id)
            cfg = await self._get_config(guild_id)
            if not cfg.get("enabled", True):
                return

            await message.delete()

            account_age = 999
            if hasattr(message.author, "created_at"):
                account_age = (datetime.datetime.now(timezone.utc) - message.author.created_at).days

            reason_lower = reason.lower()
            is_ai_serious = any(k in reason_lower for k in [
                "gambar mengandung", "scam", "judi", "phishing", "berbahaya",
                "diverifikasi sebagai spam oleh ai", "konten mencurigakan oleh llm",
                "filter intel",
            ])

            was_punished = False

            if is_ai_serious:
                await message.author.ban(reason=f"BAN LANGSUNG (AI): {reason}")
                punishment_msg = "BAN LANGSUNG ⛔"
                strikes = "-"
                was_punished = True
            else:
                new_account_max_age = cfg.get("new_account_max_age", 60)
                new_account_action = cfg.get("new_account_action", "ban")

                if account_age < new_account_max_age:
                    na_action = new_account_action
                    if na_action == "ban":
                        await message.author.ban(reason=f"Auto-Ban (akun <{new_account_max_age}hr): {reason}")
                        punishment_msg = f"BAN (akun baru < {new_account_max_age} hari)"
                        was_punished = True
                    elif na_action == "kick":
                        await message.author.kick(reason=f"Auto-Kick (akun <{new_account_max_age}hr): {reason}")
                        punishment_msg = f"KICK (akun baru < {new_account_max_age} hari)"
                        was_punished = True
                    elif na_action == "timeout":
                        hours = cfg.get("new_account_timeout_hours", 1)
                        duration = datetime.timedelta(hours=hours)
                        await message.author.timeout(duration, reason=f"Spam (akun baru): {reason}")
                        punishment_msg = f"TIMEOUT {hours} jam (akun baru)"
                    else:
                        await message.author.ban(reason=f"Auto-Ban (akun <{new_account_max_age}hr): {reason}")
                        punishment_msg = f"BAN (akun baru < {new_account_max_age} hari)"
                    strikes = "-"
                else:
                    user_id = str(message.author.id)
                    strike_key = f"{guild_id}_{user_id}"
                    doc_ref = db.collection("strikes").document(strike_key)
                    doc = await asyncio.to_thread(doc_ref.get)
                    if doc.exists:
                        data = doc.to_dict()
                        if time.time() - data.get("last_strike", 0) > 86400:
                            strikes = 0
                        else:
                            strikes = data.get("count", 0)
                    else:
                        strikes = 0
                    strikes += 1
                    await asyncio.to_thread(doc_ref.set, {"count": strikes, "last_strike": time.time()})

                    action_cfg = await self._get_action(guild_id, min(strikes, 3))
                    action = action_cfg.get("action", "ban")

                    if action == "ban":
                        await message.author.ban(reason=f"Auto-Ban: {reason}")
                        punishment_msg = "BAN permanen"
                        was_punished = True
                    elif action == "kick":
                        await message.author.kick(reason=f"Auto-Kick: {reason}")
                        punishment_msg = "KICK"
                        was_punished = True
                    elif action == "timeout":
                        hours = action_cfg.get("duration_hours", 1)
                        duration = datetime.timedelta(hours=hours)
                        await message.author.timeout(duration, reason=f"Spam: {reason}")
                        punishment_msg = f"TIMEOUT {hours} jam"
                    else:
                        await message.author.ban(reason=f"Auto-Ban: {reason}")
                        punishment_msg = "BAN permanen"
                        was_punished = True

            if was_punished and hasattr(self, "spam_intel") and self.spam_intel:
                await self.spam_intel.store_ban_pattern(
                    content=message.content,
                    reason=reason,
                    guild_id=guild_id,
                    user_id=str(message.author.id),
                    user_name=str(message.author),
                )

            report_ch_id = cfg.get("report_channel", "") or str(self.report_channel_id)
            report_channel = self.bot.get_channel(int(report_ch_id))
            if report_channel:
                embed_color = discord.Color.dark_red() if is_ai_serious else discord.Color.red()
                embed = discord.Embed(
                    title="🚨 Laporan Spam Berbahaya" if is_ai_serious else "Laporan Spam",
                    color=embed_color,
                    description=f"User **{message.author.name}** ({message.author.id}) dihukum: **{punishment_msg}**"
                )
                embed.add_field(name="Alasan", value=reason, inline=False)
                embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                embed.add_field(name="Usia Akun", value=f"{account_age} hari", inline=True)
                embed.add_field(name="Peringatan Ke", value=str(strikes), inline=True)
                await report_channel.send(embed=embed)
                spoiler_lines = [f"||{message.content[:500]}||"]
                for a in message.attachments[:3]:
                    spoiler_lines.append(f"||{a.url}||")
                await report_channel.send("\n".join(spoiler_lines))

            try:
                if is_ai_serious:
                    dm_msg = (
                        f"⚠️ KAMU TELAH DI-BAN DARI SERVER {message.guild.name.upper()}!\n\n"
                        f"Alasan: {reason}\n\n"
                        f"🔴 Ini adalah hukuman OTOMATIS karena sistem AI kami mendeteksi kamu mengirim konten "
                        f"BERBAHAYA (scam/phishing/konten penipuan).\n"
                        f"🛡️ Server ini menggunakan sistem keamanan super ketat - TIDAK ada toleransi bagi pelaku spam berbahaya.\n"
                        f"❌ Banding TIDAK DITERIMA untuk pelanggaran ini."
                    )
                else:
                    dm_msg = (
                        f"Kamu telah di-{punishment_msg} dari server {message.guild.name} "
                        f"karena melanggar aturan. Ini adalah peringatan ke-{strikes}."
                    )
                await message.author.send(dm_msg)
            except discord.Forbidden:
                print(f"[MODERATION] Gagal kirim DM ke {message.author}, DM ditutup.")

            print(f"[MODERATION] {message.author} {punishment_msg}: {reason}")
        except Exception as e:
            print(f"[ERROR] Gagal moderasi: {e}")

    async def handle_spam_light(self, message, reason):
        """Hapus pesan + timeout singkat, tanpa strike. Buat false positive AI."""
        try:
            guild_id = str(message.guild.id)
            cfg = await self._get_config(guild_id)
            if not cfg.get("enabled", True):
                return

            await message.delete()
            duration = datetime.timedelta(minutes=10)
            await message.author.timeout(duration, reason=f"Spam Ringan: {reason}")

            report_ch_id = cfg.get("report_channel", "") or str(self.report_channel_id)
            report_channel = self.bot.get_channel(int(report_ch_id))
            if report_channel:
                embed = discord.Embed(
                    title="Laporan Spam Ringan (Diverifikasi AI)",
                    color=discord.Color.orange(),
                    description=f"User **{message.author.name}** ({message.author.id}) di-TIMEOUT 10 menit"
                )
                embed.add_field(name="Alasan", value=reason, inline=False)
                await report_channel.send(embed=embed)
                spoiler_lines = [f"||{message.content[:500]}||"]
                for a in message.attachments[:3]:
                    spoiler_lines.append(f"||{a.url}||")
                await report_channel.send("\n".join(spoiler_lines))

            print(f"[MODERATION] {message.author} Light timeout (10m): {reason}")
        except Exception as e:
            print(f"[ERROR] Gagal moderasi ringan: {e}")

    @commands.hybrid_command(name="purge", aliases=["clear"], description="Hapus pesan dalam jumlah banyak dari channel")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @discord.app_commands.describe(amount="Jumlah pesan yang mau dihapus (1-100)", member="Hapus hanya pesan dari member tertentu")
    async def purge(self, ctx: commands.Context, amount: int, member: discord.Member = None):
        if amount < 1 or amount > 100:
            embed = discord.Embed(description="Jumlah harus antara 1-100.", color=0xFF0000)
            await ctx.send(embed=embed, ephemeral=True)
            return

        def check(msg):
            return member is None or msg.author.id == member.id

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check, bulk=True)
        except discord.Forbidden:
            embed = discord.Embed(description="Bot gak punya izin Manage Messages.", color=0xFF0000)
            await ctx.send(embed=embed, ephemeral=True)
            return
        except Exception as e:
            embed = discord.Embed(description=f"Gagal purge: {e}", color=0xFF0000)
            await ctx.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            description=f"Berhasil hapus **{len(deleted)}** pesan{' dari ' + member.mention if member else ''}.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed, delete_after=5)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
