import discord
from discord.ext import commands
import asyncio
import io
import os
import base64
from PIL import Image, ImageDraw, ImageFont
import aiohttp

from backend.cogs.database.firebase_setup import db


class BanSettingsCog(commands.Cog, name="BanSettings"):
    """Cog untuk mengirim pesan otomatis saat member di-ban dari server."""

    DEFAULT_BG_IMAGE = "https://raw.githubusercontent.com/zeeinz-ux/my-discord-bot/main/frontend/static/images/default-welcome-bg.png"
    DEFAULT_BANNER_BG = "https://raw.githubusercontent.com/zeeinz-ux/my-discord-bot/main/frontend/static/images/default-welcome-bg.png"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._ban_locks = {}
        print("[BAN] ✅ BanSettingsCog loaded")

    def _get_lock(self, guild_id: str, user_id: str) -> asyncio.Lock:
        key = f"{guild_id}:{user_id}"
        if key not in self._ban_locks:
            self._ban_locks[key] = asyncio.Lock()
        return self._ban_locks[key]

    def parse_placeholders(self, text: str, member: discord.Member) -> str:
        return (
            text
            .replace("{user}", member.mention)
            .replace("{server}", member.guild.name)
            .replace("{count}", str(member.guild.member_count))
        )

    async def get_ban_config(self, guild_id: str) -> dict | None:
        if db is None:
            return None
        def _fetch():
            return db.collection("guild_settings").document(guild_id).get()
        try:
            doc = await asyncio.to_thread(_fetch)
            if not doc.exists:
                return None
            cfg = doc.to_dict().get("ban", {})
            if not cfg.get("enabled", False):
                return None
            return cfg
        except Exception as e:
            print(f"[BAN] ❌ Firestore error: {e}")
            return None

    async def _send_ban(self, member: discord.Member):
        guild_id = str(member.guild.id)
        user_id = str(member.id)

        lock = self._get_lock(guild_id, user_id)
        async with lock:
            print(f"[BAN] 🚫 {member.name} banned from {member.guild.name}")

            cfg = await self.get_ban_config(guild_id)
            if cfg is None:
                return

            channel_id_str = cfg.get("channel_id", "")
            if not channel_id_str:
                return

            try:
                channel = member.guild.get_channel(int(channel_id_str))
            except (ValueError, TypeError):
                return

            if channel is None:
                return

            raw_text = cfg.get("message_text", "{user} telah di-ban dari {server}. 🚫")
            parsed_text = self.parse_placeholders(raw_text, member)

            style = cfg.get("style", "embed")
            is_embed = cfg.get("is_embed", False)

            if not cfg.get("embed_color"):
                cfg["embed_color"] = "#F26522"
            if not cfg.get("banner_text"):
                cfg["banner_text"] = "BANNED"
            if not cfg.get("embed_title"):
                cfg["embed_title"] = "🚫 User Banned"

            try:
                if style == "banner":
                    await self._send_banner(channel, member, cfg, parsed_text)
                elif is_embed:
                    await self._send_embed(channel, member, cfg, parsed_text)
                else:
                    await self._send_plain(channel, parsed_text)

                print(f"[BAN] ✅ Sent to #{channel.name} in {member.guild.name}")

            except Exception as e:
                print(f"[BAN] ❌ Error: {type(e).__name__}: {e}")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        print(f"[BAN] 📤 Ban: {user.name} @ {guild.name}")
        member = guild.get_member(user.id)
        if member is None:
            try:
                member = await guild.fetch_member(user.id)
            except discord.NotFound:
                member = None
        if member is None:
            member = user
        await self._send_ban(member)

    async def _download_image(self, url: str) -> bytes | None:
        if not url:
            return None
        if url.startswith("data:image"):
            try:
                header, b64_data = url.split(",", 1)
                image_bytes = base64.b64decode(b64_data)
                return image_bytes
            except Exception as e:
                print(f"[BAN] ⚠️ Base64 decode error: {type(e).__name__}: {e}")
                return None
        if url.startswith("/static/gallery/"):
            try:
                _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                fpath = os.path.join(_project_root, "frontend", "static", "gallery", os.path.basename(url))
                if os.path.exists(fpath):
                    with open(fpath, "rb") as f:
                        data = f.read()
                    print(f"[BAN] ✅ Read gallery file: {os.path.basename(url)} ({len(data)} bytes)")
                    return data
                print(f"[BAN] ⚠️ Gallery file not found: {fpath}")
                return None
            except Exception as e:
                print(f"[BAN] ⚠️ Gallery read error: {type(e).__name__}: {e}")
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
                        return data
                    else:
                        print(f"[BAN] ⚠️ HTTP {resp.status}")
                        return None
        except Exception as e:
            print(f"[BAN] ⚠️ Download error: {type(e).__name__}: {e}")
            return None

    async def _generate_banner_image(self, member: discord.Member, cfg: dict) -> discord.File | None:
        try:
            bg_url = cfg.get("banner_bg_url", "").strip()
            if not bg_url:
                bg_url = self.DEFAULT_BANNER_BG

            bg_bytes = await self._download_image(bg_url)
            if bg_bytes:
                bg_img = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
            else:
                bg_img = Image.new("RGBA", (1200, 500), (15, 15, 35, 255))
                draw = ImageDraw.Draw(bg_img)
                for y in range(500):
                    r = int(15 + (y / 500) * 30)
                    g = int(15 + (y / 500) * 20)
                    b = int(35 + (y / 500) * 40)
                    draw.line([(0, y), (1200, y)], fill=(r, g, b, 255))

            bg_img = bg_img.resize((1200, 500), Image.LANCZOS)
            overlay = Image.new("RGBA", (1200, 500), (0, 0, 0, 120))
            bg_img = Image.alpha_composite(bg_img, overlay)

            avatar_url = str(member.display_avatar.url)
            avatar_bytes = await self._download_image(avatar_url)
            if avatar_bytes:
                avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            else:
                avatar_img = Image.new("RGBA", (256, 256), (88, 101, 242, 255))

            avatar_size = 200
            avatar_img = avatar_img.resize((avatar_size, avatar_size), Image.LANCZOS)
            mask = Image.new("L", (avatar_size, avatar_size), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, avatar_size, avatar_size], fill=255)

            ring_size = avatar_size + 20
            ring_img = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
            ring_draw = ImageDraw.Draw(ring_img)

            if cfg.get("banner_avatar_ring", True):
                ring_draw.ellipse([0, 0, ring_size, ring_size], fill=(255, 255, 255, 255))

            ring_img.paste(avatar_img, (10, 10), mask)

            avatar_x = (1200 - ring_size) // 2
            avatar_y = 120
            bg_img.paste(ring_img, (avatar_x, avatar_y), ring_img)

            draw = ImageDraw.Draw(bg_img)
            _h = 500
            _title_sz = int(_h * 0.09)
            _name_sz = int(_h * 0.07)
            _sub_sz = max(int(_h * 0.045), 10)
            try:
                font_welcome = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", _title_sz)
                font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", _name_sz)
                font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", _sub_sz)
            except:
                try:
                    font_welcome = ImageFont.truetype("arialbd.ttf", _title_sz)
                    font_name = ImageFont.truetype("arialbd.ttf", _name_sz)
                    font_sub = ImageFont.truetype("arialbd.ttf", _sub_sz)
                except:
                    try:
                        font_welcome = ImageFont.truetype("arial.ttf", _title_sz)
                        font_name = ImageFont.truetype("arial.ttf", _name_sz)
                        font_sub = ImageFont.truetype("arial.ttf", _sub_sz)
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

            def get_text_size(draw, text, font):
                bbox = draw.textbbox((0, 0), text, font=font)
                return bbox[2] - bbox[0], bbox[3] - bbox[1]

            welcome_text = cfg.get("banner_text", "BANNED").upper()
            w_w, h_w = get_text_size(draw, welcome_text, font_welcome)
            x_w = (1200 - w_w) // 2
            y_w = avatar_y + ring_size + 15
            draw.text((x_w + 3, y_w + 3), welcome_text, font=font_welcome, fill=shadow_color, stroke_width=3, stroke_fill=(0,0,0,180))
            draw.text((x_w, y_w), welcome_text, font=font_welcome, fill=font_color, stroke_width=2, stroke_fill=font_color)

            username = member.name.upper()
            w_n, h_n = get_text_size(draw, username, font_name)
            x_n = (1200 - w_n) // 2
            y_n = y_w + h_w + 5
            draw.text((x_n + 2, y_n + 2), username, font=font_name, fill=shadow_color, stroke_width=2, stroke_fill=(0,0,0,180))
            draw.text((x_n, y_n), username, font=font_name, fill=font_color, stroke_width=1, stroke_fill=font_color)

            subtext = cfg.get("banner_subtext", f"Member ke-{member.guild.member_count} • {member.guild.name}")
            subtext = subtext.replace("{count}", str(member.guild.member_count)).replace("{server}", member.guild.name)
            w_s, h_s = get_text_size(draw, subtext, font_sub)
            x_s = (1200 - w_s) // 2
            y_s = y_n + h_n + 20
            draw.text((x_s + 1, y_s + 1), subtext, font=font_sub, fill=shadow_color, stroke_width=2, stroke_fill=(0,0,0,180))
            draw.text((x_s, y_s), subtext, font=font_sub, fill=(255, 255, 255, 230), stroke_width=1, stroke_fill=(255,255,255,230))

            output = io.BytesIO()
            bg_img.convert("RGB").save(output, format="PNG", optimize=True)
            output.seek(0)
            return discord.File(output, filename=f"ban_{member.id}.png")

        except Exception as e:
            print(f"[BAN] ❌ Banner error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def _send_banner(self, channel, member, cfg, parsed_text):
        banner_file = await self._generate_banner_image(member, cfg)
        if banner_file:
            await channel.send(content=parsed_text, file=banner_file)
            print(f"[BAN] 📤 Banner + text sent to #{channel.name}")
        else:
            await self._send_embed(channel, member, cfg, parsed_text)

    async def _send_embed(self, channel, member, cfg, parsed_text):
        color_hex = cfg.get("embed_color", "#F26522").lstrip("#")
        try:
            embed_color = discord.Color(int(color_hex, 16))
        except:
            embed_color = discord.Color(0xF26522)

        raw_title = cfg.get("embed_title", "🚫 User Banned")
        embed_title = self.parse_placeholders(raw_title, member)

        embed = discord.Embed(
            title=embed_title,
            description=f"-# {parsed_text}",
            color=embed_color
        )

        try:
            avatar_url = member.display_avatar.url
            embed.set_thumbnail(url=avatar_url)
        except Exception:
            pass

        bg_image_url = cfg.get("bg_image_url", "").strip()
        if not bg_image_url:
            bg_image_url = self.DEFAULT_BG_IMAGE
        embed.set_image(url=bg_image_url)

        try:
            footer_text = f"Member ke-{member.guild.member_count} • {member.guild.name}"
            icon_url = member.guild.icon.url if member.guild.icon else None
            embed.set_footer(text=footer_text, icon_url=icon_url)
        except Exception:
            embed.set_footer(text=member.guild.name)

        await channel.send(content=member.mention, embed=embed)

    async def _send_plain(self, channel, parsed_text):
        await channel.send(content=parsed_text)


async def setup(bot: commands.Bot):
    await bot.add_cog(BanSettingsCog(bot))
