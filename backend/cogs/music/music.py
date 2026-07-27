import discord
from discord.ext import commands, tasks
import asyncio
import os
import re
import subprocess as sp
import time

try:
    from backend.cogs.database.firebase_setup import db
    _HAS_FS = True
except Exception:
    db = None
    _HAS_FS = False

LOFI_DEFAULT_URL = "https://play.streamafrica.net/lofiradio"
LOFI_KEYWORDS = {"lofi", "lo-fi", "lo_fi", "lofi radio", "default", "radio"}
COOKIES_PATH = "cookies/cookies.txt"
VOICE_STATE_COLLECTION = "voice_state"


def _is_youtube_url(url: str) -> bool:
    return bool(re.search(r'(youtube\.com|youtu\.be)', url, re.IGNORECASE))


def _clean_url(url: str) -> str:
    if "youtube.com/watch?" in url:
        url = re.sub(r'&list=[^&]*', '', url)
        url = re.sub(r'&start_radio=[^&]*', '', url)
        url = re.sub(r'&index=[^&]*', '', url)
    return url


def _make_ytdl_source(url: str):
    args = ['yt-dlp', '-f', 'bestaudio', '-o', '-', '--no-playlist', url]
    if os.path.isfile(COOKIES_PATH):
        args.extend(['--cookies', COOKIES_PATH])
    proc = sp.Popen(args, stdout=sp.PIPE, stderr=sp.DEVNULL)
    return discord.FFmpegPCMAudio(proc.stdout, pipe=True)


def _yt_search(query: str) -> str | None:
    """Search YouTube by query, return first video URL or None."""
    try:
        result = sp.run(
            ['yt-dlp', '--no-playlist', '--print', 'url', '-f', 'bestaudio',
             f'ytsearch1:{query}', '--no-warnings'],
            capture_output=True, text=True, timeout=30
        )
        url = result.stdout.strip()
        if url and re.search(r'(youtube\.com|youtu\.be)', url):
            return url
    except Exception:
        pass
    return None


class MusicCog(commands.Cog, name="Music"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._voice_states: dict[int, dict] = {}
        self._intentional_stop: set[int] = set()

    def _save_state(self, guild_id: int, channel_id: int, url: str):
        data = {"guild_id": guild_id, "channel_id": channel_id, "url": url, "updated_at": time.time()}
        self._voice_states[guild_id] = data
        if _HAS_FS and db is not None:
            try:
                asyncio.ensure_future(asyncio.to_thread(
                    lambda: db.collection(VOICE_STATE_COLLECTION).document(str(guild_id)).set(data)
                ))
            except Exception:
                pass

    def _clear_state(self, guild_id: int):
        self._voice_states.pop(guild_id, None)
        if _HAS_FS and db is not None:
            try:
                asyncio.ensure_future(asyncio.to_thread(
                    lambda: db.collection(VOICE_STATE_COLLECTION).document(str(guild_id)).delete()
                ))
            except Exception:
                pass

    async def _restore_states(self):
        if not _HAS_FS or db is None:
            return
        try:
            docs = await asyncio.to_thread(
                lambda: list(db.collection(VOICE_STATE_COLLECTION).stream())
            )
        except Exception:
            return
        for doc in docs:
            data = doc.to_dict()
            if not data:
                continue
            gid = data.get("guild_id")
            cid = data.get("channel_id")
            url = data.get("url", LOFI_DEFAULT_URL)
            if not gid or not cid:
                continue
            guild = self.bot.get_guild(int(gid))
            if not guild:
                continue
            channel = guild.get_channel(int(cid))
            if not channel or not isinstance(channel, discord.VoiceChannel):
                continue
            vc = guild.voice_client
            if vc:
                continue
            try:
                vc = await channel.connect()
                await asyncio.sleep(0.5)
                self._play_looping(vc, url)
                self._save_state(guild.id, channel.id, url)
                print(f"[MUSIC] Auto-resume: {guild.name} / {channel.name}")
            except Exception as e:
                print(f"[MUSIC] Auto-resume failed for {guild.name}: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        await asyncio.sleep(3)
        await self._restore_states()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.id != self.bot.user.id:
            return
        if before.channel and not after.channel:
            state = self._voice_states.get(member.guild.id)
            if state:
                print(f"[MUSIC] Disconnected from {before.channel.name}, reconnecting in 5s...")
                await asyncio.sleep(5)
                guild = self.bot.get_guild(member.guild.id)
                if guild and not guild.voice_client:
                    channel = guild.get_channel(state["channel_id"])
                    if channel and isinstance(channel, discord.VoiceChannel):
                        try:
                            vc = await channel.connect()
                            await asyncio.sleep(0.5)
                            self._play_looping(vc, state["url"])
                            print(f"[MUSIC] Auto-reconnected to {channel.name}")
                        except Exception as e:
                            print(f"[MUSIC] Auto-reconnect failed: {e}")

    def _play_looping(self, vc, url: str):
        try:
            if _is_youtube_url(url):
                url = _clean_url(url)
                source = _make_ytdl_source(url)
            else:
                ffmpeg_opts = {
                    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -reconnect_at_eof 1 -reconnect_on_network_error 1",
                    "options": "-vn",
                }
                source = discord.FFmpegPCMAudio(url, **ffmpeg_opts)
            vc.play(source, after=lambda e: self._on_audio_end(vc, url, e))
        except Exception as e:
            print(f"[MUSIC] _play_looping error: {e}")

    def _on_audio_end(self, vc, url: str, error):
        gid = vc.guild.id if vc and vc.guild else None
        if gid and gid in self._intentional_stop:
            self._intentional_stop.discard(gid)
            print(f"[MUSIC] Intentional stop for guild {gid}, not restarting.")
            return
        if error:
            print(f"[MUSIC] Audio error: {error}")
        if vc and vc.is_connected():
            print(f"[MUSIC] Audio ended, restarting...")
            self._play_looping(vc, url)

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
            if vc.is_playing():
                self._intentional_stop.add(ctx.guild.id)
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
        try:
            self._play_looping(vc, LOFI_DEFAULT_URL)
            self._save_state(ctx.guild.id, channel.id, LOFI_DEFAULT_URL)
            await ctx.send(f"✅ Join **{channel.name}** 🎵 LoFi (auto-restart)")
        except discord.ClientException:
            await ctx.send(f"✅ Join **{channel.name}** (voice tersambung, tapi audio error)")
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
            self._intentional_stop.add(ctx.guild.id)
            vc.stop()
        await vc.disconnect()
        self._clear_state(ctx.guild.id)
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
        raw = (stream or "").strip()
        raw_lower = raw.lower()
        if not raw or raw_lower in LOFI_KEYWORDS:
            raw_url = LOFI_DEFAULT_URL
        elif raw.startswith("http://") or raw.startswith("https://"):
            raw_url = raw
        else:
            msg = await ctx.send(f"🔍 Cari **{raw}** di YouTube...")
            found = await asyncio.to_thread(_yt_search, raw)
            if not found:
                await msg.edit(content=f"❌ Gak nemu hasil buat \"{raw}\".")
                return
            raw_url = found
            await msg.edit(content=f"✅ Nemu: {_clean_url(raw_url)[:80]}")
        if vc.is_playing():
            self._intentional_stop.add(ctx.guild.id)
            vc.stop()
            await asyncio.sleep(0.3)
        try:
            self._play_looping(vc, raw_url)
            self._save_state(ctx.guild.id, vc.channel.id, raw_url)
            label = "LoFi default" if not stream else (_clean_url(raw_url)[:80] if _is_youtube_url(raw_url) else raw_url[:80])
            await ctx.send(f"🎵 Putar **{label}** (auto-restart)")
        except discord.ClientException as e:
            await ctx.send(f"❌ Gagal: voice belum siap. Coba `!connect` dulu. ({e})")
        except Exception as e:
            await ctx.send(f"❌ Gagal putar audio: {e}")

    @commands.command(name="stop")
    async def stop(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc or not vc.is_playing():
            await ctx.send("Gak ada audio yang diputar.")
            return
        self._intentional_stop.add(ctx.guild.id)
        vc.stop()
        await ctx.send("⏹ Audio dihentikan")


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
