# =============================================================================
# cogs/welcome.py — Hidden Hamlet Discord Bot v3.7.3
# Modul  : Welcome Announcement (Join Message) — Dual Style: Embed + Banner
# Author : zeeinz-ux
# Features: Embed style + Banner style (Pillow image generation), 
#           Join + Rejoin support, Anti-spam cooldown, Default background image
# FIX v3.7.3:
#   - Remove redundant on_guild_member_add listener
#   - Add asyncio.Lock per member to prevent race-condition double welcome
#   - Fix on_member_update: skip first-join (only handle screening & true rejoin)
#   - _download_image: add User-Agent header + longer timeout
# =============================================================================

import discord
from discord.ext import commands
import asyncio
import time
import io
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import aiohttp

# Import instance Firestore dari firebase_setup (sudah diinisiasi di main.py)
from backend.cogs.firebase_setup import db


class WelcomeCog(commands.Cog, name="Welcome"):
    """
    Cog untuk mengirim pesan sambutan otomatis saat member bergabung.

    Dua style tersedia:
    1. "embed"   → Discord embed biasa (thumbnail + background image)
    2. "banner"  → Generate image banner dengan Pillow (avatar + text overlay)

    Support: join pertama kali + rejoin (dengan anti-spam cooldown).
    Konfigurasi diambil real-time dari Firestore per guild_id.
    """

    # Default background image URL (Logo HH) — untuk embed style
    DEFAULT_BG_IMAGE = "https://raw.githubusercontent.com/zeeinz-ux/my-discord-bot/main/frontend/static/images/default-welcome-bg.png"

    # Default banner background untuk banner style
    DEFAULT_BANNER_BG = "https://raw.githubusercontent.com/zeeinz-ux/my-discord-bot/main/frontend/static/images/default-welcome-bg.png"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Anti-spam: track last welcome per member per guild (cooldown 30 detik)
        self._last_welcome = {}  # key: "guild_id:user_id" → timestamp
        self._cooldown_seconds = 30  # 30 detik

        # ← FIX v3.7.3: Lock per member untuk mencegah race condition double welcome
        self._welcome_locks = {}  # key: "guild_id:user_id" → asyncio.Lock()

        print("[WELCOME] ✅ WelcomeCog berhasil dimuat (v3.7.3 — Anti-double + Fix download).")

    # ─────────────────────────────────────────────────────────────────────────
    # LOCK HELPER (NEW v3.7.3)
    # ─────────────────────────────────────────────────────────────────────────
    def _get_lock(self, guild_id: str, user_id: str) -> asyncio.Lock:
        """Ambil atau buat asyncio.Lock untuk member tertentu."""
        key = f"{guild_id}:{user_id}"
        if key not in self._welcome_locks:
            self._welcome_locks[key] = asyncio.Lock()
        return self._welcome_locks[key]

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
          {count}  → Nomor member ke-berapa
        """
        return (
            text
            .replace("{user}", member.mention)
            .replace("{server}", member.guild.name)
            .replace("{count}", str(member.guild.member_count))
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

            print(f"[WELCOME] ✅ Config ditemukan untuk guild {guild_id}: enabled={welcome_cfg.get('enabled')}, channel_id={welcome_cfg.get('channel_id')}, style={welcome_cfg.get('style', 'embed')}")
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

        # ← FIX v3.7.3: Gunakan lock per member untuk mencegah race condition
        lock = self._get_lock(guild_id, user_id)
        async with lock:
            # Anti-spam check (di dalam lock agar tidak ada race)
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

            # 4. Tentukan style (embed atau banner)
            style = cfg.get("style", "embed")
            is_embed = cfg.get("is_embed", False)

            print(f"[WELCOME] 📝 Message text (raw): {raw_text}")
            print(f"[WELCOME] 📝 Message text (parsed): {parsed_text}")
            print(f"[WELCOME] 🎨 Style: {style}, is_embed: {is_embed}")

            # 5. Kirim pesan sesuai style
            try:
                if style == "banner":
                    print(f"[WELCOME] 📤 Mengirim BANNER ke #{channel.name}...")
                    await self._send_banner(channel, member, cfg, parsed_text)
                elif is_embed:
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
        - Kalau before.joined_at is None → after.joined_at ada: member baru join (TAPI
          skip ini karena sudah ditangani on_member_join untuk menghindari double)
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

        # ← FIX v3.7.3: HAPUS rejoin detection via joined_at
        #    Karena on_member_join sudah handle join pertama, dan joined_at berubah
        #    saat join pertama juga → menyebabkan double welcome!
        #    Jika ingin support rejoin, gunakan database tracking, bukan joined_at.

    # ─────────────────────────────────────────────────────────────────────────
    # REMOVED: on_guild_member_add (redundant dengan on_member_join)
    # ─────────────────────────────────────────────────────────────────────────
    # @commands.Cog.listener()
    # async def on_guild_member_add(self, member: discord.Member):
    #     """Alternative event listener (backup untuk on_member_join)."""
    #     print(f"[WELCOME] 📥 on_guild_member_add event: {member.name} added to {member.guild.name}")
    #     await self._send_welcome(member)

    # ─────────────────────────────────────────────────────────────────────────
    # HELPER: Download image dari URL ke bytes (async)
    # ← FIX v3.7.3: Add User-Agent header + longer timeout + better error handling
    # ─────────────────────────────────────────────────────────────────────────
    async def _download_image(self, url: str) -> bytes | None:
        """Download image dari URL, return bytes atau None jika gagal."""
        if not url:
            return None
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            }
            timeout = aiohttp.ClientTimeout(total=30, connect=10)

            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url, allow_redirects=True) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        print(f"[WELCOME] ✅ Downloaded image: {len(data)} bytes from {url}")
                        return data
                    else:
                        print(f"[WELCOME] ⚠️ Download image failed: HTTP {resp.status} for {url}")
                        return None
        except asyncio.TimeoutError:
            print(f"[WELCOME] ⚠️ Download image timeout: {url}")
            return None
        except Exception as e:
            print(f"[WELCOME] ⚠️ Download image error: {type(e).__name__}: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # HELPER: Generate banner image dengan Pillow
    # ─────────────────────────────────────────────────────────────────────────
    async def _generate_banner_image(
        self,
        member: discord.Member,
        cfg: dict
    ) -> discord.File | None:
        """
        Generate welcome banner image menggunakan Pillow.

        Layout Koya-style:
        - Background image (config atau default)
        - Avatar user di tengah (lingkaran, border putih)
        - Text overlay: "WELCOME" + username
        - Subtext kustom dari config

        Returns:
            discord.File yang siap di-attach, atau None jika gagal.
        """
        try:
            # 1. Download background image
            bg_url = cfg.get("banner_bg_url", "").strip()
            if not bg_url:
                bg_url = self.DEFAULT_BANNER_BG

            print(f"[WELCOME] 🖼️ Banner background URL: {bg_url}")

            bg_bytes = await self._download_image(bg_url)
            if bg_bytes:
                bg_img = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
                print(f"[WELCOME] ✅ Background loaded: {bg_img.size}")
            else:
                # Fallback: buat gradient background
                print(f"[WELCOME] ⚠️ Using fallback gradient background")
                bg_img = Image.new("RGBA", (1200, 500), (15, 15, 35, 255))
                draw = ImageDraw.Draw(bg_img)
                for y in range(500):
                    r = int(15 + (y / 500) * 30)
                    g = int(15 + (y / 500) * 20)
                    b = int(35 + (y / 500) * 40)
                    draw.line([(0, y), (1200, y)], fill=(r, g, b, 255))

            # Resize ke ukuran banner (1200x500)
            bg_img = bg_img.resize((1200, 500), Image.LANCZOS)

            # 2. Apply dark overlay untuk readability
            overlay = Image.new("RGBA", (1200, 500), (0, 0, 0, 120))
            bg_img = Image.alpha_composite(bg_img, overlay)

            # 3. Download avatar user
            avatar_url = str(member.display_avatar.url)
            avatar_bytes = await self._download_image(avatar_url)

            if avatar_bytes:
                avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            else:
                # Fallback avatar
                avatar_img = Image.new("RGBA", (256, 256), (88, 101, 242, 255))
                draw_av = ImageDraw.Draw(avatar_img)
                draw_av.ellipse([0, 0, 256, 256], fill=(88, 101, 242, 255))

            # 4. Create circular avatar with white border
            avatar_size = 200
            avatar_img = avatar_img.resize((avatar_size, avatar_size), Image.LANCZOS)

            # Create circular mask
            mask = Image.new("L", (avatar_size, avatar_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse([0, 0, avatar_size, avatar_size], fill=255)

            # Create avatar with ring
            ring_size = avatar_size + 20
            ring_img = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
            ring_draw = ImageDraw.Draw(ring_img)

            # Draw white ring
            ring_color = (255, 255, 255, 255)
            if cfg.get("banner_avatar_ring", True):
                ring_draw.ellipse([0, 0, ring_size, ring_size], fill=ring_color)

            # Paste avatar in center of ring
            avatar_pos = (10, 10)
            ring_img.paste(avatar_img, avatar_pos, mask)

            # 5. Paste avatar ke banner (center horizontally, slightly above center)
            avatar_x = (1200 - ring_size) // 2
            avatar_y = 120
            bg_img.paste(ring_img, (avatar_x, avatar_y), ring_img)

            # 6. Add text overlay
            draw = ImageDraw.Draw(bg_img)

            # Try to load fonts, fallback to default
            try:
                font_welcome = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
                font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 56)
                font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
            except:
                try:
                    font_welcome = ImageFont.truetype("arial.ttf", 72)
                    font_name = ImageFont.truetype("arial.ttf", 56)
                    font_sub = ImageFont.truetype("arial.ttf", 28)
                except:
                    font_welcome = ImageFont.load_default()
                    font_name = font_welcome
                    font_sub = font_welcome

            # Text colors
            font_color_hex = cfg.get("banner_font_color", "#FFFFFF").lstrip("#")
            try:
                font_color = tuple(int(font_color_hex[i:i+2], 16) for i in (0, 2, 4)) + (255,)
            except:
                font_color = (255, 255, 255, 255)

            shadow_color = (0, 0, 0, 180)

            # "WELCOME" text
            welcome_text = cfg.get("banner_text", "WELCOME").upper()

            # Calculate text positions
            def get_text_size(draw, text, font):
                bbox = draw.textbbox((0, 0), text, font=font)
                return bbox[2] - bbox[0], bbox[3] - bbox[1]

            w_w, h_w = get_text_size(draw, welcome_text, font_welcome)
            x_w = (1200 - w_w) // 2
            y_w = avatar_y + ring_size + 30

            # Draw shadow then text
            draw.text((x_w + 3, y_w + 3), welcome_text, font=font_welcome, fill=shadow_color)
            draw.text((x_w, y_w), welcome_text, font=font_welcome, fill=font_color)

            # Username text
            username = member.name.upper()
            w_n, h_n = get_text_size(draw, username, font_name)
            x_n = (1200 - w_n) // 2
            y_n = y_w + h_w + 10

            draw.text((x_n + 2, y_n + 2), username, font=font_name, fill=shadow_color)
            draw.text((x_n, y_n), username, font=font_name, fill=font_color)

            # Subtext (custom message)
            subtext = cfg.get("banner_subtext", f"Member ke-{member.guild.member_count} • {member.guild.name}")
            subtext = subtext.replace("{count}", str(member.guild.member_count)).replace("{server}", member.guild.name)
            w_s, h_s = get_text_size(draw, subtext, font_sub)
            x_s = (1200 - w_s) // 2
            y_s = y_n + h_n + 20

            draw.text((x_s + 1, y_s + 1), subtext, font=font_sub, fill=shadow_color)
            draw.text((x_s, y_s), subtext, font=font_sub, fill=(255, 255, 255, 200))

            # 7. Convert to bytes and create discord.File
            output = io.BytesIO()
            bg_img = bg_img.convert("RGB")
            bg_img.save(output, format="PNG", optimize=True)
            output.seek(0)

            file = discord.File(output, filename=f"welcome_{member.id}.png")
            print(f"[WELCOME] 🎨 Banner image generated for {member.name}")
            return file

        except Exception as e:
            print(f"[WELCOME] ❌ Error generating banner: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # HELPER: Kirim sebagai Banner Image (Koya-style)
    # ─────────────────────────────────────────────────────────────────────────
    async def _send_banner(
        self,
        channel: discord.TextChannel,
        member: discord.Member,
        cfg: dict,
        parsed_text: str
    ):
        """
        Kirim pesan sambutan dalam format banner image (Koya-style).

        - Generate image banner dengan Pillow
        - Upload sebagai file attachment ke Discord
        - Mention user di content
        """
        # Generate banner image
        banner_file = await self._generate_banner_image(member, cfg)

        if banner_file:
            # Send with image attachment + mention
            await channel.send(content=member.mention, file=banner_file)
            print(f"[WELCOME] 📤 Banner image sent to #{channel.name}")
        else:
            # Fallback ke embed kalau banner gagal generate
            print("[WELCOME] ⚠️ Banner generation failed, falling back to embed...")
            await self._send_embed(channel, member, cfg, parsed_text)

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
