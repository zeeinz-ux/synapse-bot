# =============================================================================
# cogs/welcome.py — Hidden Hamlet Discord Bot v3.6
# Modul  : Welcome Announcement (Join Message)
# Author : zeeinz-ux
# Features: Join + Rejoin support, Anti-spam cooldown, Default background image
# =============================================================================

import discord
from discord.ext import commands
import asyncio
import time

# Import instance Firestore dari firebase_setup (sudah diinisiasi di main.py)
from backend.cogs.firebase_setup import db


class WelcomeCog(commands.Cog, name="Welcome"):
    """
    Cog untuk mengirim pesan sambutan otomatis saat member bergabung.
    Support: join pertama kali + rejoin (dengan anti-spam cooldown).
    Konfigurasi diambil real-time dari Firestore per guild_id.
    """

    # Default background image URL (Logo HH)
    DEFAULT_BG_IMAGE = "https://raw.githubusercontent.com/zeeinz-ux/my-discord-bot/main/frontend/static/images/default-welcome-bg.png"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Anti-spam: track last welcome per member per guild (cooldown 5 menit)
        self._last_welcome = {}  # key: "guild_id:user_id" → timestamp
        self._cooldown_seconds = 300  # 5 menit
        print("[WELCOME] ✅ WelcomeCog berhasil dimuat.")

    # ─────────────────────────────────────────────────────────────────────────
    # ANTI-SPAM HELPER
    # ─────────────────────────────────────────────────────────────────────────
    def _can_send_welcome(self, guild_id: str, user_id: str) -> bool:
        """Cek apakah boleh kirim welcome (cooldown 5 menit per member per guild)."""
        key = f"{guild_id}:{user_id}"
        now = time.time()
        last = self._last_welcome.get(key, 0)
        if now - last < self._cooldown_seconds:
            print(f"[WELCOME] ⏱️ Cooldown aktif untuk user {user_id} di guild {guild_id} (tersisa {int(self._cooldown_seconds - (now - last))}s)")
            return False
        self._last_welcome[key] = now
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # PLACEHOLDER PARSER
    # ─────────────────────────────────────────────────────────────────────────
    def parse_placeholders(self, text: str, member: discord.Member) -> str:
        """
        Ganti placeholder kustom dalam teks dengan nilai asli.

        Placeholder yang didukung:
          {user}   → Mention langsung ke user (@Username)
          {server} → Nama server Discord
        """
        return (
            text
            .replace("{user}", member.mention)
            .replace("{server}", member.guild.name)
        )

    # ─────────────────────────────────────────────────────────────────────────
    # AMBIL KONFIGURASI DARI FIRESTORE (async-safe wrapper)
    # ─────────────────────────────────────────────────────────────────────────
    async def get_welcome_config(self, guild_id: str) -> dict | None:
        """
        Ambil konfigurasi welcome dari Firestore.
        Menggunakan asyncio.to_thread() agar operasi sync Firestore
        tidak memblokir event loop Discord.

        Returns:
            dict konfigurasi welcome, atau None jika tidak ada / tidak enabled.
        """
        # Guard: db belum tersedia (Firebase gagal init)
        if db is None:
            print("[WELCOME] ⚠️ Firebase db tidak tersedia, skip.")
            return None

        def _fetch():
            doc_ref = db.collection("guild_settings").document(guild_id)
            return doc_ref.get()

        try:
            doc = await asyncio.to_thread(_fetch)

            if not doc.exists:
                print(f"[WELCOME] ℹ️ Tidak ada config untuk guild {guild_id}")
                return None

            guild_data = doc.to_dict()
            welcome_cfg = guild_data.get("welcome", {})

            # Kembalikan None jika modul dinonaktifkan
            if not welcome_cfg.get("enabled", False):
                print(f"[WELCOME] ℹ️ Welcome disabled untuk guild {guild_id}")
                return None

            print(f"[WELCOME] ✅ Config ditemukan untuk guild {guild_id}: enabled={welcome_cfg.get('enabled')}, channel_id={welcome_cfg.get('channel_id')}")
            return welcome_cfg

        except Exception as e:
            print(f"[WELCOME] ❌ Gagal mengambil config dari Firestore: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # CORE: Kirim welcome message
    # ─────────────────────────────────────────────────────────────────────────
    async def _send_welcome(self, member: discord.Member):
        """Kirim welcome message untuk member (digunakan oleh on_member_join & fallback)."""
        guild_id = str(member.guild.id)
        user_id = str(member.id)

        # Anti-spam check
        if not self._can_send_welcome(guild_id, user_id):
            return

        print(f"[WELCOME] 🔥 Welcome triggered! Member: {member.name} (ID: {user_id}) di Guild: {member.guild.name} (ID: {guild_id})")

        # 1. Ambil konfigurasi dari Firestore
        cfg = await self.get_welcome_config(guild_id)
        if cfg is None:
            print(f"[WELCOME] ⚠️ Config None untuk guild {guild_id}, skip welcome.")
            return

        # 2. Validasi channel tujuan
        channel_id_str = cfg.get("channel_id", "")
        if not channel_id_str:
            print(f"[WELCOME] ⚠️ Guild {guild_id}: channel_id belum diset.")
            return

        print(f"[WELCOME] 📍 Channel target: {channel_id_str}")

        try:
            channel = member.guild.get_channel(int(channel_id_str))
        except (ValueError, TypeError) as e:
            print(f"[WELCOME] ❌ channel_id tidak valid: '{channel_id_str}' — Error: {e}")
            return

        if channel is None:
            print(f"[WELCOME] ❌ Channel {channel_id_str} tidak ditemukan di guild {guild_id}.")
            return

        print(f"[WELCOME] ✅ Channel ditemukan: #{channel.name} (ID: {channel.id})")

        # 3. Parse placeholder dalam teks pesan
        raw_text = cfg.get("message_text", "Selamat datang {user} di {server}! 🎉")
        parsed_text = self.parse_placeholders(raw_text, member)
        is_embed = cfg.get("is_embed", False)

        print(f"[WELCOME] 📝 Message text (raw): {raw_text}")
        print(f"[WELCOME] 📝 Message text (parsed): {parsed_text}")
        print(f"[WELCOME] 🎨 is_embed: {is_embed}")

        # 4. Kirim pesan (Embed atau plain text)
        try:
            if is_embed:
                print(f"[WELCOME] 📤 Mengirim EMBED ke #{channel.name}...")
                await self._send_embed(channel, member, cfg, parsed_text)
            else:
                print(f"[WELCOME] 📤 Mengirim PLAIN TEXT ke #{channel.name}...")
                await self._send_plain(channel, parsed_text)

            print(f"[WELCOME] 🎉 Sambutan BERHASIL terkirim → {member} di '{member.guild.name}'")

        except discord.Forbidden as e:
            print(f"[WELCOME] ❌ FORBIDDEN: Tidak ada izin kirim pesan di #{channel.name}. Error: {e}")
        except discord.HTTPException as e:
            print(f"[WELCOME] ❌ HTTPException saat kirim pesan: {e}")
        except Exception as e:
            print(f"[WELCOME] ❌ UNEXPECTED ERROR: {type(e).__name__}: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # EVENT LISTENER: on_member_join (join pertama kali)
    # ─────────────────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Terpicu saat member baru bergabung ke server (join pertama kali)."""
        print(f"[WELCOME] 📥 on_member_join event: {member.name} joined {member.guild.name}")
        await self._send_welcome(member)

    # ─────────────────────────────────────────────────────────────────────────
    # FALLBACK: on_member_update (catch rejoin & screening completion)
    # ─────────────────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """
        Fallback untuk member yang rejoin atau selesai membership screening.

        Logic:
        - Kalau before.pending=True → after.pending=False: member selesai screening
        - Kalau before.roles kosong → after.roles ada: member baru diberi role (rejoin)
        - Kalau before.joined_at is None → after.joined_at ada: member baru join
        """
        # Skip kalau bukan guild yang sama (shouldn't happen tapi safety)
        if before.guild.id != after.guild.id:
            return

        guild_id = str(after.guild.id)
        user_id = str(after.id)

        # Case 1: Membership screening selesai (pending → not pending)
        if before.pending and not after.pending:
            print(f"[WELCOME] 🔄 on_member_update (screening): {after.name} selesai screening di {after.guild.name}")
            await self._send_welcome(after)
            return

        # Case 2: Rejoin detection (joined_at berubah = baru join/rejoin)
        # Note: joined_at berubah saat member join, meskipun pernah join sebelumnya
        if before.joined_at != after.joined_at and after.joined_at is not None:
            print(f"[WELCOME] 🔄 on_member_update (rejoin): {after.name} joined_at updated di {after.guild.name}")
            await self._send_welcome(after)
            return

    # ─────────────────────────────────────────────────────────────────────────
    # FALLBACK: on_guild_member_add (alternative event, some cases catch this but not on_member_join)
    # ─────────────────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_guild_member_add(self, member: discord.Member):
        """Alternative event listener (backup untuk on_member_join)."""
        print(f"[WELCOME] 📥 on_guild_member_add event: {member.name} added to {member.guild.name}")
        await self._send_welcome(member)

    # ─────────────────────────────────────────────────────────────────────────
    # HELPER: Kirim sebagai discord.Embed
    # ─────────────────────────────────────────────────────────────────────────
    async def _send_embed(
        self,
        channel: discord.TextChannel,
        member: discord.Member,
        cfg: dict,
        parsed_text: str
    ):
        """
        Kirim pesan sambutan dalam format discord.Embed.

        ⚠️  PENTING: mention dikirim di field `content` (DI LUAR embed) agar
            Discord tetap mengirimkan push notification / ping ke user.
            Embed sendiri tidak men-trigger notifikasi.
        """
        # Parse warna hex → discord.Color
        color_hex = cfg.get("embed_color", "#5865F2").lstrip("#")
        try:
            embed_color = discord.Color(int(color_hex, 16))
            print(f"[WELCOME] 🎨 Embed color: #{color_hex} → {embed_color}")
        except (ValueError, TypeError) as e:
            print(f"[WELCOME] ⚠️ Warna hex tidak valid: '{color_hex}', fallback ke default. Error: {e}")
            embed_color = discord.Color(0x5865F2)  # Fallback: Discord Blurple

        # Parse judul (juga support placeholder)
        raw_title = cfg.get("embed_title", "👋 Selamat Datang!")
        embed_title = self.parse_placeholders(raw_title, member)

        embed = discord.Embed(
            title=embed_title,
            description=parsed_text,
            color=embed_color
        )

        # Thumbnail = foto profil member yang baru join
        embed.set_thumbnail(url=member.display_avatar.url)
        print(f"[WELCOME] 🖼️ Thumbnail: {member.display_avatar.url}")

        # Banner / bg_image — pakai config atau default
        bg_image_url = cfg.get("bg_image_url", "").strip()
        if not bg_image_url:
            # Kalau kosong, pakai default background image (Logo HH)
            bg_image_url = self.DEFAULT_BG_IMAGE
            print(f"[WELCOME] 🖼️ Using DEFAULT background image: {bg_image_url}")
        else:
            print(f"[WELCOME] 🖼️ Using CUSTOM background image: {bg_image_url}")

        embed.set_image(url=bg_image_url)

        # Footer informatif
        embed.set_footer(
            text=f"Member ke-{member.guild.member_count} • {member.guild.name}",
            icon_url=member.guild.icon.url if member.guild.icon else None
        )

        # Kirim: mention di content (ping), embed sebagai visual
        print(f"[WELCOME] 📤 Sending: content={member.mention}, embed title={embed_title}")
        await channel.send(content=member.mention, embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # HELPER: Kirim sebagai teks biasa
    # ─────────────────────────────────────────────────────────────────────────
    async def _send_plain(self, channel: discord.TextChannel, parsed_text: str):
        """
        Kirim pesan sambutan sebagai plain text.
        Mention sudah terembed di dalam parsed_text via placeholder {user}.
        """
        print(f"[WELCOME] 📤 Sending plain text: {parsed_text}")
        await channel.send(content=parsed_text)


# =============================================================================
# SETUP — dipanggil otomatis oleh bot.load_extension() di main.py
# =============================================================================
async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))
