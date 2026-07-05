"""
================================================================================
COG: Auto Responder Module v1.0 — Synapse Discord Bot
================================================================================
File    : backend/cogs/auto_response/auto_response.py
Deskripsi : Auto-responder berbasis keyword dari Firestore
Fitur:
  • Multi-keyword support (array)
  • Case-sensitive / insensitive option
  • Regex support
  • Response types: text, embed, image
  • Channel filtering (include/exclude)
  • Cooldown per responder
  • Delete trigger message option
  • Mention user in response
================================================================================
"""

import re
import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

import discord
from discord.ext import commands, tasks
from discord import app_commands
from ..database.firebase_setup import db


class AutoResponderCog(commands.Cog, name="AutoResponder"):
    """Cog untuk auto-response berbasis keyword."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Cooldown cache: {guild_id: {responder_id:user_id: timestamp}}
        self._cooldown_cache: Dict[str, Dict[str, float]] = {}
        # Settings cache: {guild_id: {"data": settings_dict, "last_fetched": timestamp}}
        self._settings_cache: Dict[str, Dict[str, Any]] = {}
        # Trigger stats: {guild_id: {responder_id: count}}
        self._trigger_stats: Dict[str, Dict[str, int]] = {}
        
        self.cleanup_caches.start()
        self.batch_write_stats.start()
        print("[AUTO-RESPONSE] ✅ Cog loaded and cache tasks started.")

    def cog_unload(self):
        self.cleanup_caches.cancel()
        self.batch_write_stats.cancel()

    def cog_unload(self):
        self.cleanup_caches.cancel()

    @tasks.loop(minutes=30)
    async def cleanup_caches(self):
        """Bersihkan cache secara berkala."""
        now = time.time()
        
        # 1. Cleanup Settings Cache (TTL > 5 menit sudah dihandle di _get_guild_settings)
        # Tapi kita bersihkan entry yang sudah sangat lama
        for guild_id, entry in list(self._settings_cache.items()):
            if now - entry["last_fetched"] > 3600: # 1 jam
                del self._settings_cache[guild_id]

        # 2. Cleanup Cooldown Cache
        for guild_id, entries in list(self._cooldown_cache.items()):
            for key, timestamp in list(entries.items()):
                # Hapus jika sudah > 1 jam
                if now - timestamp > 3600:
                    del self._cooldown_cache[guild_id][key]
            
            # Jika empty, hapus guild_id
            if not self._cooldown_cache[guild_id]:
                del self._cooldown_cache[guild_id]
        print("[AUTO-RESPONSE] 🧹 Cache cleaned up.")

    @tasks.loop(minutes=5)
    async def batch_write_stats(self):
        """Batch write trigger stats ke Firestore setiap 5 menit (hemat quota)."""
        if not self._trigger_stats or db is None:
            return
        stats_copy = dict(self._trigger_stats)
        self._trigger_stats.clear()
        try:
            for guild_id, responders in stats_copy.items():
                doc_ref = db.collection("guild_settings").document(str(guild_id))
                def _blocking_write(gid=guild_id, rstats=responders):
                    doc = doc_ref.get()
                    if not doc.exists:
                        return
                    existing = doc.to_dict().get("auto_responders", {})
                    dirty = False
                    for rid, inc in rstats.items():
                        if rid in existing:
                            cur = existing[rid].get("trigger_count", 0)
                            existing[rid]["trigger_count"] = cur + inc
                            dirty = True
                    if dirty:
                        doc_ref.update({"auto_responders": existing})
                await asyncio.to_thread(_blocking_write)
        except Exception as e:
            print(f"[AUTO-RESPONSE] ⚠️ Batch stats write error: {e}")

    # ═══════════════════════════════════════════════════════════════════════
    # HELPER: Firestore Operations
    # ═══════════════════════════════════════════════════════════════════════
    async def _get_guild_settings(self, guild_id: str) -> dict:
        """Ambil settings auto-responder dengan caching."""
        now = time.time()
        
        # Cek Cache
        if guild_id in self._settings_cache:
            cached = self._settings_cache[guild_id]
            if now - cached["last_fetched"] < 300: # 5 menit TTL
                return cached["data"]

        # Fetch dari Firestore jika miss atau expired
        if db is None:
            return {"enabled": False, "responders": {}}

        try:
            doc_ref = db.collection("guild_settings").document(str(guild_id))
            doc = await asyncio.to_thread(doc_ref.get)

            if not doc.exists:
                settings = {"enabled": False, "responders": {}}
            else:
                data = doc.to_dict()
                settings = {
                    "enabled": data.get("auto_responders_enabled", False),
                    "responders": data.get("auto_responders", {})
                }
            
            # Update Cache
            self._settings_cache[guild_id] = {"data": settings, "last_fetched": now}
            return settings
            
        except Exception as e:
            print(f"[AUTO-RESPONSE] ⚠️ Error fetching settings: {e}")
            return {"enabled": False, "responders": {}}

    async def _save_responder(
        self,
        guild_id: str,
        responder_id: str,
        config: dict
    ) -> bool:
        """Simpan/update satu responder ke Firestore."""
        if db is None:
            return False

        try:
            doc_ref = db.collection("guild_settings").document(str(guild_id))

            # Ambil responders existing
            doc = await asyncio.to_thread(doc_ref.get)
            existing = doc.to_dict().get("auto_responders", {}) if doc.exists else {}

            # Update responder tertentu
            existing[responder_id] = config

            # Simpan dengan merge=True
            await asyncio.to_thread(
                doc_ref.set,
                {"auto_responders": existing, "auto_responders_enabled": True},
                merge=True
            )
            return True
        except Exception as e:
            print(f"[AUTO-RESPONSE] ⚠️ Error saving responder: {e}")
            return False

    async def _delete_responder(self, guild_id: str, responder_id: str) -> bool:
        """Hapus responder dari Firestore."""
        if db is None:
            return False

        try:
            doc_ref = db.collection("guild_settings").document(str(guild_id))
            doc = await asyncio.to_thread(doc_ref.get)

            if not doc.exists:
                return False

            existing = doc.to_dict().get("auto_responders", {})
            if responder_id in existing:
                del existing[responder_id]
                await asyncio.to_thread(
                    doc_ref.set,
                    {"auto_responders": existing},
                    merge=True
                )
            return True
        except Exception as e:
            print(f"[AUTO-RESPONSE] ⚠️ Error deleting responder: {e}")
            return False

    async def _list_responders(self, guild_id: str) -> List[dict]:
        """Ambil semua responders untuk guild."""
        settings = await self._get_guild_settings(guild_id)
        responders = settings.get("responders", {})

        result = []
        for responder_id, config in responders.items():
            result.append({
                "id": responder_id,
                **config
            })
        return result

    # ═══════════════════════════════════════════════════════════════════════
    # HELPER: Message Matching
    # ═══════════════════════════════════════════════════════════════════════
    def _match_keyword(
        self,
        message_content: str,
        keyword: str,
        case_sensitive: bool = False,
        regex_enabled: bool = False,
        match_whole_word: bool = False
    ) -> bool:
        """Cek apakah message cocok dengan keyword."""
        content = message_content
        kw = keyword

        if not case_sensitive:
            content = content.lower()
            kw = kw.lower()

        if regex_enabled:
            try:
                pattern = re.compile(kw)
                return bool(pattern.search(content))
            except re.error:
                # Invalid regex, fallback ke literal match
                return kw in content
        elif match_whole_word:
            # Use word boundaries
            pattern = r'\b' + re.escape(kw) + r'\b'
            return bool(re.search(pattern, content, re.IGNORECASE if not case_sensitive else 0))
        else:
            return kw in content

    def _check_channel_filter(
        self,
        channel_id: str,
        channel_ids: List[str],
    ) -> bool:
        """Cek apakah channel diizinkan. Kosong = semua channel."""
        if channel_ids:
            return str(channel_id) in channel_ids
        return True

    def _check_cooldown(
        self,
        guild_id: str,
        responder_id: str,
        cooldown_seconds: int,
        user_id: str = None,
    ) -> bool:
        """Cek apakah responder masih dalam cooldown (per-user). Returns True if allowed."""
        if cooldown_seconds <= 0:
            return True

        per_user_key = f"{responder_id}:{user_id}" if user_id else responder_id
        if guild_id not in self._cooldown_cache:
            self._cooldown_cache[guild_id] = {}

        last_triggered = self._cooldown_cache[guild_id].get(per_user_key, 0)
        now = time.time()

        if now - last_triggered < cooldown_seconds:
            return False

        # Update timestamp
        self._cooldown_cache[guild_id][per_user_key] = now
        return True

    # ═══════════════════════════════════════════════════════════════════════
    # HELPER: Variables
    # ═══════════════════════════════════════════════════════════════════════
    def _replace_variables(self, text: str, message: discord.Message) -> str:
        """Ganti {user}, {server}, {channel} dll dengan nilai asli."""
        replacements = {
            "{user}": message.author.mention,
            "{username}": message.author.name,
            "{nickname}": message.author.display_name,
            "{server}": message.guild.name,
            "{channel}": message.channel.mention,
            "{channel_name}": message.channel.name,
        }
        for var, val in replacements.items():
            text = text.replace(var, val)
        return text

    # ═══════════════════════════════════════════════════════════════════════
    # CORE: Process Auto-Response
    # ═══════════════════════════════════════════════════════════════════════
    async def _process_response(
        self,
        message: discord.Message,
        responder_id: str,
        config: dict
    ):
        """Eksekusi auto-response untuk satu responder."""
        # 1. Check cooldown per-user
        cooldown = config.get("cooldown_seconds", 10)
        if not self._check_cooldown(str(message.guild.id), responder_id, cooldown, str(message.author.id)):
            return

        # 2. Check channel filter
        channel_id = str(message.channel.id)
        channel_ids = config.get("channel_ids", [])

        if not self._check_channel_filter(channel_id, channel_ids):
            return

        # 3. Increment trigger stat
        gid = str(message.guild.id)
        if gid not in self._trigger_stats:
            self._trigger_stats[gid] = {}
        self._trigger_stats[gid][responder_id] = self._trigger_stats[gid].get(responder_id, 0) + 1

        # 4. Build response
        response_type = config.get("response_type", "text")
        response_content = config.get("response_content", "")
        mention_user = config.get("mention_user", False)
        delete_trigger = config.get("delete_trigger", False)

        # Replace variables
        response_content = self._replace_variables(response_content, message)

        # Delete trigger message if requested
        if delete_trigger:
            try:
                await message.delete()
            except discord.Forbidden:
                print(f"[AUTO-RESPONSE] ⚠️ Cannot delete message: no permission")
            except discord.NotFound:
                pass

        # Build content with mention prefix
        content = ""
        if mention_user:
            content = f"{message.author.mention} "
        content += response_content

        # Send response based on type
        if response_type == "text":
            await message.channel.send(content, suppress_embeds=True)

        elif response_type == "embed":
            embed_color_hex = config.get("embed_color", "#5865F2").lstrip("#")
            try:
                embed_color = discord.Color(int(embed_color_hex, 16))
            except:
                embed_color = discord.Color(0x5865F2)

            embed_title = self._replace_variables(config.get("embed_title", ""), message)
            embed_thumbnail = self._replace_variables(config.get("embed_thumbnail", ""), message)

            embed = discord.Embed(
                title=embed_title,
                description=response_content,
                color=embed_color
            )

            thumbnail_url = embed_thumbnail
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)

            await message.channel.send(content=content if mention_user else None, embed=embed)

        elif response_type == "image":
            image_url = config.get("response_image_url", "")
            if image_url:
                if image_url.startswith("data:"):
                    import base64
                    header, encoded = image_url.split(",", 1)
                    img_bytes = base64.b64decode(encoded)
                    await message.channel.send(
                        content=content,
                        files=[discord.File(img_bytes, filename="response.png")]
                    )
                else:
                    await message.channel.send(
                        content=content,
                        files=[discord.File(await self._download_image(image_url), filename="response.png")]
                    )
            else:
                await message.channel.send(content)

    async def _download_image(self, url: str) -> bytes:
        """Download image from URL."""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                return await resp.read()

    # ═══════════════════════════════════════════════════════════════════════
    # EVENT LISTENER: on_message
    # ═══════════════════════════════════════════════════════════════════════
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen untuk setiap pesan dan proses auto-response."""
        # Skip if message is from bot or system
        if message.author.bot or message.is_system():
            return

        # Skip if no guild
        if not message.guild:
            return

        guild_id = str(message.guild.id)

        # Get settings
        settings = await self._get_guild_settings(guild_id)

        # Skip if auto-responder disabled globally
        if not settings.get("enabled", False):
            return

        responders = settings.get("responders", {})
        message_content = message.content

        # Sort by order field (default 0) so first match is deterministic
        sorted_items = sorted(
            responders.items(),
            key=lambda item: item[1].get("order", 0) if isinstance(item[1], dict) else 0
        )

        # Check each responder
        for responder_id, config in sorted_items:
            if not isinstance(config, dict):
                continue
            # Skip if responder disabled
            if not config.get("enabled", True):
                continue

            # Get keywords (support array or single string)
            keywords = config.get("keyword", [])
            if isinstance(keywords, str):
                keywords = [keywords]

            # Check if any keyword matches
            case_sensitive = config.get("case_sensitive", False)
            regex_enabled = config.get("regex_enabled", False)
            match_whole_word = config.get("match_whole_word", False)

            for keyword in keywords:
                if self._match_keyword(message_content, keyword, case_sensitive, regex_enabled, match_whole_word):
                    # Found match! Process response
                    await self._process_response(message, responder_id, config)
                    break  # Only trigger first matching responder

    # ═══════════════════════════════════════════════════════════════════════
    # SLASH COMMANDS: Management
    # ═══════════════════════════════════════════════════════════════════════
    @commands.hybrid_command(name="ar-list", description="Lihat semua auto-responder di server ini")
    async def ar_list(self, ctx: commands.Context):
        """List semua auto-responder."""
        guild_id = str(ctx.guild.id)
        responders = await self._list_responders(guild_id)

        if not responders:
            await ctx.send(
                "📭 Belum ada auto-responder. Buat dengan `/ar-add`!",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📝 Auto-Responders",
            color=discord.Color.blue()
        )

        for i, ar in enumerate(responders, 1):
            keywords = ar.get("keyword", [])
            if isinstance(keywords, list):
                keywords_str = ", ".join(keywords[:3])
                if len(keywords) > 3:
                    keywords_str += f" +{len(keywords)-3}"
            else:
                keywords_str = str(keywords)

            status = "✅ Aktif" if ar.get("enabled", True) else "❌ Nonaktif"
            embed.add_field(
                name=f"{i}. {keywords_str}",
                value=f"Type: {ar.get('response_type', 'text')} | {status}",
                inline=False
            )

        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="ar-add", description="Tambah auto-responder baru")
    @app_commands.describe(
        keyword="Keyword yang memicu response",
        response="Response yang ingin dikirim",
        response_type="Tipe response (text/embed/image)",
        case_sensitive="Case sensitive?",
        cooldown="Cooldown dalam detik"
    )
    @app_commands.choices(response_type=[
        app_commands.Choice(name="Text", value="text"),
        app_commands.Choice(name="Embed", value="embed"),
        app_commands.Choice(name="Image", value="image"),
    ])
    async def ar_add(
        self,
        ctx: commands.Context,
        keyword: str,
        response: str,
        response_type: app_commands.Choice[str] = None,
        case_sensitive: bool = False,
        cooldown: int = 10
    ):
        """Tambah auto-responder baru."""
        # Check permissions
        if not ctx.author.guild_permissions.manage_messages:
            await ctx.send(
                "❌ Kamu butuh izin `Manage Messages` untuk membuat auto-responder.",
                ephemeral=True
            )
            return

        guild_id = str(ctx.guild.id)
        responder_id = f"ar_{int(time.time() * 1000)}"

        # Determine next order
        settings = await self._get_guild_settings(guild_id)
        existing = settings.get("responders", {})
        max_order = 0
        for cfg in existing.values():
            if isinstance(cfg, dict):
                max_order = max(max_order, cfg.get("order", 0))
        next_order = max_order + 1

        config = {
            "keyword": [keyword],
            "response_type": response_type.value if response_type else "text",
            "response_content": response,
            "case_sensitive": case_sensitive,
            "cooldown_seconds": cooldown,
            "enabled": True,
            "order": next_order,
            "created_at": datetime.now(timezone.utc)
        }

        success = await self._save_responder(guild_id, responder_id, config)

        if success:
            self._settings_cache.pop(guild_id, None) # Invalidate Cache
            await ctx.send(
                f"✅ Auto-responder dibuat!\n🔑 Keyword: `{keyword}`\n💬 Response: {response}",
                ephemeral=True
            )
        else:
            await ctx.send(
                "❌ Gagal membuat auto-responder. Pastikan Firebase terhubung.",
                ephemeral=True
            )

    @commands.hybrid_command(name="ar-remove", description="Hapus auto-responder")
    @app_commands.describe(keyword="Keyword yang mau dihapus")
    async def ar_remove(self, ctx: commands.Context, keyword: str):
        """Hapus auto-responder berdasarkan keyword."""
        if not ctx.author.guild_permissions.manage_messages:
            await ctx.send(
                "❌ Kamu butuh izin `Manage Messages`.",
                ephemeral=True
            )
            return

        guild_id = str(ctx.guild.id)
        settings = await self._get_guild_settings(guild_id)
        responders = settings.get("responders", {})

        # Find responder with this keyword
        found_id = None
        for responder_id, config in responders.items():
            keywords = config.get("keyword", [])
            if isinstance(keywords, str):
                keywords = [keywords]
            if keyword in keywords:
                found_id = responder_id
                break

        if found_id:
            await self._delete_responder(guild_id, found_id)
            self._settings_cache.pop(guild_id, None) # Invalidate Cache
            await ctx.send(
                f"✅ Auto-responder dengan keyword `{keyword}` dihapus!",
                ephemeral=True
            )
        else:
            await ctx.send(
                f"❌ Tidak ada auto-responder dengan keyword `{keyword}`.",
                ephemeral=True
            )

    @commands.hybrid_command(name="ar-edit", description="Edit auto-responder yang sudah ada")
    @app_commands.describe(
        keyword="Keyword yang mau diedit",
        new_keyword="Keyword baru (opsional)",
        response="Response baru (opsional)",
        response_type="Tipe response baru (opsional): text / embed / image",
        cooldown="Cooldown baru dalam detik (opsional)",
        case_sensitive="Case sensitive? (opsional: true/false)",
    )
    @app_commands.choices(response_type=[
        app_commands.Choice(name="Text", value="text"),
        app_commands.Choice(name="Embed", value="embed"),
        app_commands.Choice(name="Image", value="image"),
    ])
    async def ar_edit(
        self,
        ctx: commands.Context,
        keyword: str,
        new_keyword: str = None,
        response: str = None,
        response_type: app_commands.Choice[str] = None,
        cooldown: int = None,
        case_sensitive: bool = None,
    ):
        """Edit auto-responder yang sudah ada."""
        if not ctx.author.guild_permissions.manage_messages:
            await ctx.send("❌ Kamu butuh izin `Manage Messages`.", ephemeral=True)
            return

        guild_id = str(ctx.guild.id)
        settings = await self._get_guild_settings(guild_id)
        responders = settings.get("responders", {})

        found_id = None
        for rid, cfg in responders.items():
            kws = cfg.get("keyword", [])
            if isinstance(kws, str):
                kws = [kws]
            if keyword in kws:
                found_id = rid
                break

        if not found_id:
            await ctx.send(f"❌ Tidak ada auto-responder dengan keyword `{keyword}`.", ephemeral=True)
            return

        config = dict(responders[found_id])
        if new_keyword:
            config["keyword"] = [new_keyword]
        if response:
            config["response_content"] = response
        if response_type:
            config["response_type"] = response_type.value
        if cooldown is not None:
            config["cooldown_seconds"] = cooldown
        if case_sensitive is not None:
            config["case_sensitive"] = case_sensitive

        success = await self._save_responder(guild_id, found_id, config)
        if success:
            self._settings_cache.pop(guild_id, None)
            await ctx.send(f"✅ Auto-responder `{keyword}` berhasil diperbarui!", ephemeral=True)
        else:
            await ctx.send("❌ Gagal memperbarui auto-responder.", ephemeral=True)

    @commands.hybrid_command(name="ar-toggle", description="Aktifkan/nonaktifkan auto-responder")
    @app_commands.describe(keyword="Keyword yang mau diaktifkan/nonaktifkan", enable="Aktifkan?")
    async def ar_toggle(self, ctx: commands.Context, keyword: str, enable: bool):
        """Toggle auto-responder."""
        if not ctx.author.guild_permissions.manage_messages:
            await ctx.send(
                "❌ Kamu butuh izin `Manage Messages`.",
                ephemeral=True
            )
            return

        guild_id = str(ctx.guild.id)
        settings = await self._get_guild_settings(guild_id)
        responders = settings.get("responders", {})

        # Find responder
        found_id = None
        for responder_id, config in responders.items():
            keywords = config.get("keyword", [])
            if isinstance(keywords, str):
                keywords = [keywords]
            if keyword in keywords:
                found_id = responder_id
                break

        if found_id:
            config = responders[found_id]
            config["enabled"] = enable
            await self._save_responder(guild_id, found_id, config)
            self._settings_cache.pop(guild_id, None) # Invalidate Cache
            status = "diaktifkan" if enable else "dinonaktifkan"
            await ctx.send(
                f"✅ Auto-responder `{keyword}` {status}!",
                ephemeral=True
            )
        else:
            await ctx.send(
                f"❌ Tidak ada auto-responder dengan keyword `{keyword}`.",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoResponderCog(bot))
