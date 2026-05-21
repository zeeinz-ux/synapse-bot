# =============================================================================
# cogs/welcome.py — Hidden Hamlet Discord Bot v3.7.4 FINAL
# Modul  : Welcome Announcement (Join Message) — Dual Style: Embed + Banner
# Author : zeeinz-ux
# Features: Embed style + Banner style (Pillow image generation), 
#           Join + Rejoin support, Anti-spam cooldown, Default background image
# FIX v3.7.4:
#   - Remove on_guild_member_add (redundant, cause double welcome)
#   - Cooldown default 30s (configurable, change self._cooldown_seconds)
#   - asyncio.Lock per member prevents race-condition double welcome
#   - on_member_update: only handles screening completion
#   - _download_image: User-Agent + timeout + allow_redirects
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
        # Anti-spam: track last welcome per member per guild
        self._last_welcome = {}  # key: "guild_id:user_id" → timestamp
        self._cooldown_seconds = 30  # ← GANTI DI SINI: 0, 30, 60, 300, dll

        # Lock per member untuk mencegah race condition double welcome
        self._welcome_locks = {}  # key: "guild_id:user_id" → asyncio.Lock()

        print(f"[WELCOME] ✅ WelcomeCog dimuat (v3.7.4 — Cooldown: {self._cooldown_seconds}s)")

    # ─────────────────────────────────────────────────────────────────────────
    # LOCK HELPER
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
        """Cek apakah boleh kirim welcome (cooldown per member per guild)."""
        key = f"{guild_id}:{user_id}"
        now = time.time()
        last = self._last_welcome.get(key, 0)
        elapsed = now - last
        if elapsed < self._cooldown_seconds:
            print(f"[WELCOME] ⏱️ Cooldown: user {user_id} di guild {guild_id} (tunggu {int(self._cooldown_seconds - elapsed)}s lagi)")
            return False
        self._last_welcome[key] = now
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # PLACEHOLDER PARSER
    # ─────────────────────────────────────────────────────────────────────────
    def parse_placeholders(self, text: str, member: discord.Member) -> str:
        """Ganti placeholder kustom dengan nilai asli."""
        return (
            text
            .replace("{user}", member.mention)
            .replace("{server}", member.guild.name)
            .replace("{count}", str(member.guild.member_count))
        )

    # ─────────────────────────────────────────────────────────────────────────
    # AMBIL KONFIGURASI DARI FIRESTORE
    # ─────────────────────────────────────────────────────────────────────────
    async def get_welcome_config(self, guild_id: str) -> dict | None:
        """Ambil konfigurasi welcome dari Firestore."""
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

            if not welcome_cfg.get("enabled", False):
                return None

            return welcome_cfg

        except Exception as e:
            print(f"[WELCOME] ❌ Gagal ambil config Firestore: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # CORE: Kirim welcome message
    # ─────────────────────────────────────────────────────────────────────────
    async def _send_welcome(self, member: discord.Member):
        """Kirim welcome message untuk member."""
        guild_id = str(member.guild.id)
        user_id = str(member.id)

        # Gunakan lock per member untuk mencegah race condition
        lock = self._get_lock(guild_id, user_id)
        async with lock:
            # Anti-spam check (di dalam lock agar tidak ada race)
            if not self._can_send_welcome(guild_id, user_id):
                return

            print(f"[WELCOME] 🔥 Welcome triggered! {member.name} (ID: {user_id}) di {member.guild.name}")

            # 1. Ambil konfigurasi
            cfg = await self.get_welcome_config(guild_id)
            if cfg is None:
                print(f"[WELCOME] ⚠️ Config None untuk guild {guild_id}, skip.")
                return

            # 2. Validasi channel
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
                print(f"[WELCOME] ❌ Channel {channel_id_str} tidak ditemukan.")
                return

            # 3. Parse teks
            raw_text = cfg.get("message_text", "Selamat datang {user} di {server}! 🎉")
            parsed_text = self.parse_placeholders(raw_text, member)

            # 4. Tentukan style
            style = cfg.get("style", "embed")
            is_embed = cfg.get("is_embed", False)

            print(f"[WELCOME] 🎨 Style: {style}, is_embed: {is_embed}")

            # 5. Kirim sesuai style
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

                print(f"[WELCOME] 🎉 Sambutan BERHASIL → {member} di '{member.guild.name}'")

            except discord.Forbidden as e:
                print(f"[WELCOME] ❌ FORBIDDEN: #{channel.name}. Error: {e}")
            except discord.HTTPException as e:
                print(f"[WELCOME] ❌ HTTPException: {e}")
            except Exception as e:
                print(f"[WELCOME] ❌ UNEXPECTED: {type(e).__name__}: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # EVENT: on_member_join (fire untuk first join + rejoin)
    # ─────────────────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Terpicu saat member bergabung (first join atau rejoin)."""
        print(f"[WELCOME] 📥 on_member_join: {member.name} joined {member.guild.name}")
        await self._send_welcome(member)

    # ─────────────────────────────────────────────────────────────────────────
    # EVENT: on_member_update (hanya untuk membership screening)
    # ─────────────────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Fallback: member selesai membership screening (pending → not pending)."""
        if before.guild.id != after.guild.id:
            return

        # Hanya handle screening completion
        if before.pending and not after.pending:
            print(f"[WELCOME] 🔄 Screening complete: {after.name} di {after.guild.name}")
            await self._send_welcome(after)

    # ─────────────────────────────────────────────────────────────────────────
    # REMOVED: on_guild_member_add (redundant dengan on_member_join)
    #    Menghapus ini mencegah double welcome untuk member yang sama.
    # ─────────────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────────────
    # HELPER: Download image dari URL
    # ─────────────────────────────────────────────────────────────────────────
    async def _download_image(self, url: str) -> bytes | None:
        """Download image dari URL, return bytes atau None."""
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
                        print(f"[WELCOME] ✅ Downloaded: {len(data)} bytes from {url}")
                        return data
                    else:
                        print(f"[WELCOME] ⚠️ Download failed: HTTP {resp.status} for {url}")
                        return None
        except asyncio.TimeoutError:
            print(f"[WELCOME] ⚠️ Download timeout: {url}")
            return None
        except Exception as e:
            print(f"[WELCOME] ⚠️ Download error: {type(e).__name__}: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # HELPER: Generate banner image dengan Pillow
    # ─────────────────────────────────────────────────────────────────────────
    async def _generate_banner_image(self, member: discord.Member, cfg: dict) -> discord.File | None:
        """Generate welcome banner image Koya-style."""
        try:
            # 1. Background
            bg_url = cfg.get("banner_bg_url", "").strip()
            if not bg_url:
                bg_url = self.DEFAULT_BANNER_BG

            print(f"[WELCOME] 🖼️ Banner BG URL: {bg_url}")

            bg_bytes = await self._download_image(bg_url)
            if bg_bytes:
                bg_img = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
                print(f"[WELCOME] ✅ BG loaded: {bg_img.size}")
            else:
                print("[WELCOME] ⚠️ Fallback gradient")
                bg_img = Image.new("RGBA", (1200, 500), (15, 15, 35, 255))
                draw = ImageDraw.Draw(bg_img)
                for y in range(500):
                    r = int(15 + (y / 500) * 30)
                    g = int(15 + (y / 500) * 20)
                    b = int(35 + (y / 500) * 40)
                    draw.line([(0, y), (1200, y)], fill=(r, g, b, 255))

            bg_img = bg_img.resize((1200, 500), Image.LANCZOS)

            # 2. Dark overlay
            overlay = Image.new("RGBA", (1200, 500), (0, 0, 0, 120))
            bg_img = Image.alpha_composite(bg_img, overlay)

            # 3. Avatar
            avatar_url = str(member.display_avatar.url)
            avatar_bytes = await self._download_image(avatar_url)

            if avatar_bytes:
                avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            else:
                avatar_img = Image.new("RGBA", (256, 256), (88, 101, 242, 255))
                draw_av = ImageDraw.Draw(avatar_img)
                draw_av.ellipse([0, 0, 256, 256], fill=(88, 101, 242, 255))

            # 4. Circular avatar with ring
            avatar_size = 200
            avatar_img = avatar_img.resize((avatar_size, avatar_size), Image.LANCZOS)

            mask = Image.new("L", (avatar_size, avatar_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse([0, 0, avatar_size, avatar_size], fill=255)

            ring_size = avatar_size + 20
            ring_img = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
            ring_draw = ImageDraw.Draw(ring_img)

            if cfg.get("banner_avatar_ring", True):
                ring_draw.ellipse([0, 0, ring_size, ring_size], fill=(255, 255, 255, 255))

            ring_img.paste(avatar_img, (10, 10), mask)

            # 5. Paste ke banner
            avatar_x = (1200 - ring_size) // 2
            avatar_y = 120
            bg_img.paste(ring_img, (avatar_x, avatar_y), ring_img)

            # 6. Text
            draw = ImageDraw.Draw(bg_img)

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

            font_color_hex = cfg.get("banner_font_color", "#FFFFFF").lstrip("#")
            try:
                font_color = tuple(int(font_color_hex[i:i+2], 16) for i in (0, 2, 4)) + (255,)
            except:
                font_color = (255, 255, 255, 255)

            shadow_color = (0, 0, 0, 180)

            welcome_text = cfg.get("banner_text", "WELCOME").upper()

            def get_text_size(draw, text, font):
                bbox = draw.textbbox((0, 0), text, font=font)
                return bbox[2] - bbox[0], bbox[3] - bbox[1]

            w_w, h_w = get_text_size(draw, welcome_text, font_welcome)
            x_w = (1200 - w_w) // 2
            y_w = avatar_y + ring_size + 30

            draw.text((x_w + 3, y_w + 3), welcome_text, font=font_welcome, fill=shadow_color)
            draw.text((x_w, y_w), welcome_text, font=font_welcome, fill=font_color)

            username = member.name.upper()
            w_n, h_n = get_text_size(draw, username, font_name)
            x_n = (1200 - w_n) // 2
            y_n = y_w + h_w + 10

            draw.text((x_n + 2, y_n + 2), username, font=font_name, fill=shadow_color)
            draw.text((x_n, y_n), username, font=font_name, fill=font_color)

            subtext = cfg.get("banner_subtext", f"Member ke-{member.guild.member_count} • {member.guild.name}")
            subtext = subtext.replace("{count}", str(member.guild.member_count)).replace("{server}", member.guild.name)
            w_s, h_s = get_text_size(draw, subtext, font_sub)
            x_s = (1200 - w_s) // 2
            y_s = y_n + h_n + 20

            draw.text((x_s + 1, y_s + 1), subtext, font=font_sub, fill=shadow_color)
            draw.text((x_s, y_s), subtext, font=font_sub, fill=(255, 255, 255, 200))

            # 7. Export
            output = io.BytesIO()
            bg_img = bg_img.convert("RGB")
            bg_img.save(output, format="PNG", optimize=True)
            output.seek(0)

            file = discord.File(output, filename=f"welcome_{member.id}.png")
            print(f"[WELCOME] 🎨 Banner generated for {member.name}")
            return file

        except Exception as e:
            print(f"[WELCOME] ❌ Banner error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # HELPER: Kirim Banner
    # ─────────────────────────────────────────────────────────────────────────
    async def _send_banner(self, channel, member, cfg, parsed_text):
        """Kirim welcome dalam format banner image."""
        banner_file = await self._generate_banner_image(member, cfg)
        if banner_file:
            await channel.send(content=member.mention, file=banner_file)
            print(f"[WELCOME] 📤 Banner sent to #{channel.name}")
        else:
            print("[WELCOME] ⚠️ Banner failed, fallback to embed...")
            await self._send_embed(channel, member, cfg, parsed_text)

    # ─────────────────────────────────────────────────────────────────────────
    # HELPER: Kirim Embed
    # ─────────────────────────────────────────────────────────────────────────
    async def _send_embed(self, channel, member, cfg, parsed_text):
        """Kirim welcome dalam format discord.Embed."""
        color_hex = cfg.get("embed_color", "#5865F2").lstrip("#")
        try:
            embed_color = discord.Color(int(color_hex, 16))
        except:
            embed_color = discord.Color(0x5865F2)

        raw_title = cfg.get("embed_title", "👋 Selamat Datang!")
        embed_title = self.parse_placeholders(raw_title, member)

        embed = discord.Embed(
            title=embed_title,
            description=parsed_text,
            color=embed_color
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        bg_image_url = cfg.get("bg_image_url", "").strip()
        if not bg_image_url:
            bg_image_url = self.DEFAULT_BG_IMAGE
        embed.set_image(url=bg_image_url)

        embed.set_footer(
            text=f"Member ke-{member.guild.member_count} • {member.guild.name}",
            icon_url=member.guild.icon.url if member.guild.icon else None
        )

        await channel.send(content=member.mention, embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # HELPER: Kirim Plain Text
    # ─────────────────────────────────────────────────────────────────────────
    async def _send_plain(self, channel, parsed_text):
        """Kirim welcome sebagai plain text."""
        await channel.send(content=parsed_text)


# =============================================================================
# SETUP
# =============================================================================
async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))
