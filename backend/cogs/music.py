import discord
from discord.ext import commands
import asyncio
import os
import re
import yt_dlp

LOFI_DEFAULT_URL = "https://play.streamafrica.net/lofiradio"
LOFI_KEYWORDS = {"lofi", "lo-fi", "lo_fi", "lofi radio", "default", "radio"}
COOKIES_PATH = "cookies/cookies.txt"


def _is_youtube_url(url: str) -> bool:
    return bool(re.search(r'(youtube\.com|youtu\.be)', url, re.IGNORECASE))


def _clean_url(url: str) -> str:
    if "youtube.com/watch?" in url:
        url = re.sub(r'&list=[^&]*', '', url)
        url = re.sub(r'&start_radio=[^&]*', '', url)
        url = re.sub(r'&index=[^&]*', '', url)
    return url


def _resolve_url(url: str) -> str:
    if not _is_youtube_url(url):
        return url
    url = _clean_url(url)
    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
    }
    if os.path.isfile(COOKIES_PATH):
        ydl_opts["cookiefile"] = COOKIES_PATH
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info["url"]
    except Exception as e:
        raise Exception(f"yt-dlp: {e}")


class MusicCog(commands.Cog, name="Music"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="connect", aliases=["joinvc"])
    async def connect(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):
        if not channel:
            if ctx.author.voice and ctx.author.voice.channel:
                channel = ctx.author.voice.channel
            else:
                await ctx.send("Sebut nama voice channel atau join voice dulu biar bot ngikut.")
                return
        vc = ctx.guild.voice_client
        if vc:
            if vc.channel.id == channel.id:
                await ctx.send(f"Udah di {channel.mention} kok.")
                return
            await vc.disconnect()
            await asyncio.sleep(0.5)
        try:
            vc = await channel.connect()
        except discord.Forbidden:
            await ctx.send("Gak punya izin Connect/Speak di channel itu.")
            return
        except Exception as e:
            await ctx.send(f"❌ Gagal: {e}")
            return
        await asyncio.sleep(0.5)
        url = LOFI_DEFAULT_URL
        ffmpeg_opts = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -reconnect_at_eof 1 -reconnect_on_network_error 1",
            "options": "-vn",
        }
        try:
            src = _resolve_url(url)
            source = discord.FFmpegPCMAudio(src, **ffmpeg_opts)
            vc.play(source, after=lambda e: print(f"[MUSIC] Stream ended: {e}") if e else None)
            await ctx.send(f"✅ Join **{channel.name}** 🎵 LoFi")
        except discord.ClientException:
            await ctx.send(f"✅ Join **{channel.name}** (voice tersambung, tapi audio error — coba `!play` lagi)")
        except Exception:
            await ctx.send(f"✅ Join **{channel.name}**")

    @commands.command(name="leave")
    async def leave(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc:
            await ctx.send("Gak ada di voice channel.")
            return
        name = vc.channel.name
        if vc.is_playing():
            vc.stop()
        await vc.disconnect()
        await ctx.send(f"✅ Leave **{name}**")

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx: commands.Context, *, stream: str = None):
        vc = ctx.guild.voice_client
        if not vc:
            if ctx.author.voice and ctx.author.voice.channel:
                await ctx.author.voice.channel.connect()
                vc = ctx.guild.voice_client
            else:
                await ctx.send("Bot gak di voice. Pake `!connect` dulu atau join voice dulu.")
                return
        raw = (stream or "").strip().lower()
        if not raw or raw in LOFI_KEYWORDS:
            raw_url = LOFI_DEFAULT_URL
        elif raw.startswith("http://") or raw.startswith("https://"):
            raw_url = raw
        else:
            await ctx.send("Kalo mau LoFi tinggal `!play` aja (tanpa nama). Kalo mau link, kirim URL lengkapnya.")
            return
        ffmpeg_opts = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -reconnect_at_eof 1 -reconnect_on_network_error 1",
            "options": "-vn",
        }
        if vc.is_playing():
            vc.stop()
            await asyncio.sleep(0.3)
        try:
            url = _resolve_url(raw_url)
            source = discord.FFmpegPCMAudio(url, **ffmpeg_opts)
            vc.play(source, after=lambda e: print(f"[MUSIC] Playback ended: {e}") if e else None)
            label = "LoFi default" if not stream else (raw_url[:60] if _is_youtube_url(raw_url) else raw_url[:60])
            await ctx.send(f"🎵 Putar **{label}**")
        except discord.ClientException as e:
            await ctx.send(f"❌ Gagal: voice belum siap. Coba `!connect` dulu atau tunggu bentar. ({e})")
        except Exception as e:
            await ctx.send(f"❌ Gagal putar audio: {e}")

    @commands.command(name="stop")
    async def stop(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc or not vc.is_playing():
            await ctx.send("Gak ada audio yang diputar.")
            return
        vc.stop()
        await ctx.send("⏹ Audio dihentikan")


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
