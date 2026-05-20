# =============================================================================
# cogs/welcome.py — Hidden Hamlet Discord Bot v3.5
# Modul  : Welcome Announcement (Join Message)
# Author : zeeinz-ux
# =============================================================================

import discord
from discord.ext import commands
import asyncio

# Import instance Firestore dari firebase_setup (sudah diinisiasi di main.py)
from cogs.firebase_setup import db


class WelcomeCog(commands.Cog, name="Welcome"):
    """
    Cog untuk mengirim pesan sambutan otomatis saat member baru bergabung.
    Konfigurasi diambil real-time dari Firestore per guild_id.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        print("[WELCOME] ✅ WelcomeCog berhasil dimuat.")

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
                return None

            guild_data = doc.to_dict()
            welcome_cfg = guild_data.get("welcome", {})

            # Kembalikan None jika modul dinonaktifkan
            if not welcome_cfg.get("enabled", False):
                return None

            return welcome_cfg

        except Exception as e:
            print(f"[WELCOME] ❌ Gagal mengambil config dari Firestore: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # EVENT LISTENER: on_member_join
    # ─────────────────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Terpicu otomatis saat member baru bergabung ke server.
        Mengirim pesan sambutan sesuai konfigurasi yang tersimpan di Firestore.
        """
        guild_id = str(member.guild.id)

        # 1. Ambil konfigurasi dari Firestore
        cfg = await self.get_welcome_config(guild_id)
        if cfg is None:
            return  # Modul tidak aktif atau belum dikonfigurasi

        # 2. Validasi channel tujuan
        channel_id_str = cfg.get("channel_id", "")
        if not channel_id_str:
            print(f"[WELCOME] ⚠️ Guild {guild_id}: channel_id belum diset.")
            return

        try:
            channel = member.guild.get_channel(int(channel_id_str))
        except (ValueError, TypeError):
            print(f"[WELCOME] ❌ channel_id tidak valid: '{channel_id_str}'")
            return

        if channel is None:
            print(f"[WELCOME] ❌ Channel {channel_id_str} tidak ditemukan di guild {guild_id}.")
            return

        # 3. Parse placeholder dalam teks pesan
        raw_text  = cfg.get("message_text", "Selamat datang {user} di {server}! 🎉")
        parsed_text = self.parse_placeholders(raw_text, member)
        is_embed    = cfg.get("is_embed", False)

        # 4. Kirim pesan (Embed atau plain text)
        try:
            if is_embed:
                await self._send_embed(channel, member, cfg, parsed_text)
            else:
                await self._send_plain(channel, parsed_text)

            print(f"[WELCOME] 🎉 Sambutan terkirim → {member} di '{member.guild.name}'")

        except discord.Forbidden:
            print(f"[WELCOME] ❌ Tidak ada izin kirim pesan di #{channel.name}.")
        except discord.HTTPException as e:
            print(f"[WELCOME] ❌ HTTPException saat kirim pesan: {e}")

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
        except (ValueError, TypeError):
            embed_color = discord.Color(0x5865F2)  # Fallback: Discord Blurple

        # Parse judul (juga support placeholder)
        raw_title   = cfg.get("embed_title", "👋 Selamat Datang!")
        embed_title = self.parse_placeholders(raw_title, member)

        embed = discord.Embed(
            title=embed_title,
            description=parsed_text,
            color=embed_color
        )

        # Thumbnail = foto profil member yang baru join
        embed.set_thumbnail(url=member.display_avatar.url)

        # Banner / bg_image opsional
        bg_image_url = cfg.get("bg_image_url", "").strip()
        if bg_image_url:
            embed.set_image(url=bg_image_url)

        # Footer informatif
        embed.set_footer(
            text=f"Member ke-{member.guild.member_count} • {member.guild.name}",
            icon_url=member.guild.icon.url if member.guild.icon else None
        )

        # Kirim: mention di content (ping), embed sebagai visual
        await channel.send(content=member.mention, embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # HELPER: Kirim sebagai teks biasa
    # ─────────────────────────────────────────────────────────────────────────
    async def _send_plain(self, channel: discord.TextChannel, parsed_text: str):
        """
        Kirim pesan sambutan sebagai plain text.
        Mention sudah terembed di dalam parsed_text via placeholder {user}.
        """
        await channel.send(content=parsed_text)


# =============================================================================
# SETUP — dipanggil otomatis oleh bot.load_extension() di main.py
# =============================================================================
async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))