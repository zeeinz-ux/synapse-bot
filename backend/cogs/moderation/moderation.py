import discord
from discord.ext import commands
import datetime
from datetime import timezone
import asyncio
import time
import aiohttp
from ...utils.spam_engine import SpamEngine
from ...utils.image_spam import ImageSpamDetector
from ..database.firebase_setup import db

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.engine = SpamEngine()
        self.img_detector = ImageSpamDetector()
        self._session: aiohttp.ClientSession | None = None
        self.report_channel_id = 1517948052537868449

    async def cog_load(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

        # Load persisted spam hashes dari Firestore
        await self._load_spam_hashes()

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
        if not expired:
            return
        try:
            batch = db.batch()
            for h in expired:
                doc_ref = db.collection("spam_hashes").document(str(h))
                batch.delete(doc_ref)
            await asyncio.to_thread(batch.commit)
            print(f"[MODERATION] 🧹 Cleaned {len(expired)} expired spam hashes from Firestore")
        except Exception as e:
            print(f"[MODERATION] ⚠️ Gagal cleanup expired hashes: {e}")

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
            1: {"action": "timeout", "duration_hours": 1},
            2: {"action": "kick"},
            3: {"action": "ban"},
        }
        return cfg.get(key, defaults.get(strikes, {"action": "ban"}))

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.author.guild_permissions.administrator:
            await self.bot.process_commands(message)
            return

        guild_id = str(message.guild.id)

        self.engine.track_message(message)
        cfg = await self._get_config(guild_id)
        if not cfg.get("enabled", True):
            await self.bot.process_commands(message)
            return

        current_score = self.engine.get_risk_score(message)
        account_age = 0
        if hasattr(message.author, "created_at"):
            account_age = (datetime.datetime.now(timezone.utc) - message.author.created_at).days

        # ── Heuristic trigger (score >= 5) → AI verify before escalating ──
        if cfg.get("filter_heuristic", True) and current_score >= 5:
            if cfg.get("filter_ai", True):
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
            # AI gak available → pakai heuristic langsung
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
            if image_urls and await self._check_image_spam(message, image_urls):
                return

        await self.bot.process_commands(message)

    async def _check_image_spam(self, message, image_urls: list[tuple[str, str]]) -> bool:
        """Check images in message. Returns True if flagged as spam."""
        guild_id = str(message.guild.id)
        cfg = await self._get_config(guild_id)
        user_id = str(message.author.id)
        flagged = False

        for url, mime in image_urls:
            # Layer 1: Rate limit
            if self.img_detector.track_image_sent(user_id):
                await self.handle_spam_light(message, "Filter Gambar: Mengirim gambar terlalu cepat")
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
                await self.handle_spam_light(message, "Filter Gambar: Mengirim gambar yang sama berulang kali")
                return True

            # Layer 3: Gemini Vision (only for suspicious users)
            account_age = 0
            if hasattr(message.author, "created_at"):
                account_age = (datetime.datetime.now(timezone.utc) - message.author.created_at).days
            is_new = account_age < 7
            is_flooding = self.img_detector.is_sending_images_fast(user_id)

            if is_new or is_flooding or dup_count >= 2:
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

        if flagged:
            self.img_detector.flag_as_spam(img_hash)
            await self._save_spam_hash(img_hash)
            await self.handle_spam(message, "Filter Gambar: Gambar mengandung konten spam/judi/scam")
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

            punishment_msg = ""
            action_cfg = await self._get_action(guild_id, min(strikes, 3))
            action = action_cfg.get("action", "ban")

            if action == "ban":
                await message.author.ban(reason=f"Auto-Ban: {reason}")
                punishment_msg = "BAN permanen"
            elif action == "kick":
                await message.author.kick(reason=f"Auto-Kick: {reason}")
                punishment_msg = "KICK"
            elif action == "timeout":
                hours = action_cfg.get("duration_hours", 1)
                duration = datetime.timedelta(hours=hours)
                await message.author.timeout(duration, reason=f"Spam: {reason}")
                punishment_msg = f"TIMEOUT {hours} jam"
            else:
                await message.author.ban(reason=f"Auto-Ban: {reason}")
                punishment_msg = "BAN permanen"

            report_ch_id = cfg.get("report_channel", "") or str(self.report_channel_id)
            report_channel = self.bot.get_channel(int(report_ch_id))
            if report_channel:
                embed = discord.Embed(
                    title="Laporan Spam",
                    color=discord.Color.red(),
                    description=f"User **{message.author.name}** ({message.author.id}) dihukum: **{punishment_msg}**"
                )
                embed.add_field(name="Alasan", value=reason, inline=False)
                embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                embed.add_field(name="Peringatan Ke", value=strikes, inline=True)
                embed.add_field(name="Isi Pesan", value=f"||{message.content[:500]}||", inline=False)
                await report_channel.send(embed=embed)

            try:
                await message.author.send(f"Peringatan! Kamu telah di-{punishment_msg} dari server {message.guild.name} karena melakukan spam. Ini adalah peringatan ke-{strikes}.")
            except discord.Forbidden:
                print(f"[MODERATION] Gagal kirim DM ke {message.author}, DM ditutup.")

            print(f"[MODERATION] {message.author} Strike {strikes}: {reason}")
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
                embed.add_field(name="Isi Pesan", value=f"||{message.content[:500]}||", inline=False)
                await report_channel.send(embed=embed)

            print(f"[MODERATION] {message.author} Light timeout (10m): {reason}")
        except Exception as e:
            print(f"[ERROR] Gagal moderasi ringan: {e}")

async def setup(bot):
    await bot.add_cog(Moderation(bot))
