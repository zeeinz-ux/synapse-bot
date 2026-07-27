import discord
from discord.ext import commands
import asyncio
import os
import time
import random

try:
    from backend.cogs.database.firebase_setup import db
    _HAS_FS = True
except Exception:
    db = None
    _HAS_FS = False

LOFI_DEFAULT_URL = "https://play.streamafrica.net/lofiradio"
LOFI_KEYWORDS = {"lofi", "lo-fi", "lo_fi", "lofi radio", "default", "radio"}
VOICE_STATE_COLLECTION = "voice_state"
COLOR = 0x5865F2

STATIONS = {
    "lofi": {"url": "https://play.streamafrica.net/lofiradio", "label": "LoFi Radio"},
    "jazz": {"url": "https://streams.calmradio.com/api/64/128/stream", "label": "LoFi Jazz"},
    "chill": {"url": "https://streams.calmradio.com/api/1027/128/stream", "label": "LoFi Chill"},
    "study": {"url": "https://streams.calmradio.com/api/1029/128/stream", "label": "LoFi Study"},
    "sleep": {"url": "https://streams.calmradio.com/api/1030/128/stream", "label": "LoFi Sleep"},
}


class MusicCog(commands.Cog, name="Music"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._voice_states: dict[int, dict] = {}
        self._guild_stations: dict[int, str] = {}
        self._sleep_timers: dict[int, asyncio.Task] = {}

    def _random_station_url(self) -> str:
        key = random.choice(list(STATIONS.keys()))
        return STATIONS[key]["url"]

    def _station_key(self, url: str) -> str:
        for k, v in STATIONS.items():
            if v["url"] == url:
                return k
        return "lofi"

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
        self._guild_stations[guild_id] = self._station_key(url)

    def _clear_state(self, guild_id: int):
        self._voice_states.pop(guild_id, None)
        self._guild_stations.pop(guild_id, None)
        self._cancel_sleep(guild_id)
        if _HAS_FS and db is not None:
            try:
                asyncio.ensure_future(asyncio.to_thread(
                    lambda: db.collection(VOICE_STATE_COLLECTION).document(str(guild_id)).delete()
                ))
            except Exception:
                pass

    def _cancel_sleep(self, guild_id: int):
        task = self._sleep_timers.pop(guild_id, None)
        if task and not task.done():
            task.cancel()

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
            url = data.get("url", self._random_station_url())
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

    def _play_looping(self, vc, url: str):
        gid = vc.guild.id if vc and vc.guild else None
        if gid:
            self._cancel_sleep(gid)
        try:
            ffmpeg_opts = {
                "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -reconnect_at_eof 1 -reconnect_on_network_error 1",
                "options": "-vn",
            }
            source = discord.FFmpegPCMAudio(url, **ffmpeg_opts)
            vc.play(source, after=lambda e: self._on_track_end(vc, url, e))
        except Exception as e:
            print(f"[MUSIC] _play_looping error: {e}")

    def _on_track_end(self, vc, url: str, error):
        if error:
            print(f"[MUSIC] Audio error: {error}")
        if not vc or not vc.is_connected():
            return
        print(f"[MUSIC] Stream ended, restarting...")
        self._play_looping(vc, url)

    @commands.Cog.listener()
    async def on_ready(self):
        await asyncio.sleep(3)
        await self._restore_states()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.id != self.bot.user.id:
            return
        if before.channel and after.channel and before.channel.id != after.channel.id:
            state = self._voice_states.get(member.guild.id)
            if state:
                state["channel_id"] = after.channel.id
                self._save_state(member.guild.id, after.channel.id, state["url"])
                print(f"[MUSIC] Moved to {after.channel.name}, state updated")
            return
        if before.channel and not after.channel:
            print(f"[MUSIC] Disconnected from {before.channel.name}, state preserved for restart auto-resume")

    @commands.command(name="connect", aliases=["joinvc"])
    async def connect(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):
        if not channel:
            if ctx.author.voice and ctx.author.voice.channel:
                channel = ctx.author.voice.channel
            else:
                embed = discord.Embed(description="Sebut nama voice channel atau join voice dulu biar bot ngikut.", color=COLOR)
                await ctx.send(embed=embed)
                return
        vc = ctx.guild.voice_client
        if vc:
            if vc.channel.id == channel.id:
                embed = discord.Embed(description=f"Udah di {channel.mention} kok.", color=COLOR)
                await ctx.send(embed=embed)
                return
            await vc.disconnect()
            await asyncio.sleep(0.5)
        try:
            vc = await channel.connect()
        except discord.Forbidden:
            embed = discord.Embed(description="Gak punya izin Connect/Speak di channel itu.", color=0xFF0000)
            await ctx.send(embed=embed)
            return
        except Exception as e:
            embed = discord.Embed(description=f"\u274c Gagal: {e}", color=0xFF0000)
            await ctx.send(embed=embed)
            return
        await asyncio.sleep(0.5)
        url = self._random_station_url()
        station_label = STATIONS[self._station_key(url)]["label"]
        try:
            self._play_looping(vc, url)
            self._save_state(ctx.guild.id, channel.id, url)
            embed = discord.Embed(
                title="\u25b6 Connected",
                description=f"Join **{channel.name}** — **{station_label}**",
                color=COLOR
            )
            await ctx.send(embed=embed)
        except discord.ClientException:
            embed = discord.Embed(description=f"\u2705 Join **{channel.name}** (voice tersambung, tapi audio error)", color=COLOR)
            await ctx.send(embed=embed)
        except Exception:
            embed = discord.Embed(description=f"\u2705 Join **{channel.name}**", color=COLOR)
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="play", aliases=["p"], description="Putar LoFi radio")
    @discord.app_commands.describe(query="Nama station (lofi, jazz, chill, study, sleep)")
    async def play(self, ctx: commands.Context, *, query: str = None):
        await ctx.defer()
        vc = ctx.guild.voice_client
        if not vc:
            if ctx.author.voice and ctx.author.voice.channel:
                vc = await ctx.author.voice.channel.connect()
            else:
                embed = discord.Embed(description="Bot gak di voice. Pake `!connect` dulu atau join voice dulu.", color=COLOR)
                await ctx.interaction.edit_original_response(embed=embed)
                return
        key = (query or "").strip().lower()
        if key and key not in STATIONS:
            available = ", ".join(STATIONS.keys())
            embed = discord.Embed(description=f"Station `{key}` gak ada. Yang tersedia: {available}", color=COLOR)
            await ctx.interaction.edit_original_response(embed=embed)
            return
        if not key:
            key = self._guild_stations.get(ctx.guild.id, "lofi")
        station = STATIONS[key]
        await _safe_stop(vc)
        await asyncio.sleep(0.3)
        self._play_looping(vc, station["url"])
        self._save_state(ctx.guild.id, vc.channel.id, station["url"])
        embed = discord.Embed(
            title="\u25b6 Now Playing",
            description=f"**{station['label']}** \ud83c\udfb5",
            color=COLOR
        )
        await ctx.interaction.edit_original_response(embed=embed)

    @commands.hybrid_command(name="station", description="Ganti station LoFi radio")
    @discord.app_commands.describe(name="Nama station: lofi, jazz, chill, study, sleep")
    async def station(self, ctx: commands.Context, *, name: str):
        key = name.strip().lower()
        if key not in STATIONS:
            available = ", ".join(STATIONS.keys())
            embed = discord.Embed(description=f"Station `{key}` gak ada. Yang tersedia: {available}", color=COLOR)
            await ctx.send(embed=embed)
            return
        vc = ctx.guild.voice_client
        if not vc or not vc.is_connected():
            embed = discord.Embed(description="Bot gak di voice channel.", color=COLOR)
            await ctx.send(embed=embed)
            return
        station = STATIONS[key]
        await _safe_stop(vc)
        await asyncio.sleep(0.3)
        self._play_looping(vc, station["url"])
        self._save_state(ctx.guild.id, vc.channel.id, station["url"])
        embed = discord.Embed(
            title="\U0001f3b5 Station Changed",
            description=f"Sekarang muterin **{station['label']}**",
            color=COLOR
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="song", description="Lihat station yang sedang diputar")
    async def song(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc or not vc.is_connected() or not vc.is_playing():
            embed = discord.Embed(description="Gak ada audio yang diputar.", color=COLOR)
            await ctx.send(embed=embed)
            return
        key = self._guild_stations.get(ctx.guild.id, "lofi")
        station = STATIONS[key]
        embed = discord.Embed(
            title="\u25b6 Now Playing",
            description=f"**{station['label']}** \ud83c\udfb5",
            color=COLOR
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="sleep", description="Set sleep timer untuk auto-disconnect")
    @discord.app_commands.describe(minutes="Menit sampai disconnect (contoh: 15, 30, 60)")
    async def sleep(self, ctx: commands.Context, minutes: int):
        vc = ctx.guild.voice_client
        if not vc or not vc.is_connected():
            embed = discord.Embed(description="Bot gak di voice channel.", color=COLOR)
            await ctx.send(embed=embed)
            return
        if minutes < 1 or minutes > 180:
            embed = discord.Embed(description="Timer harus antara 1-180 menit.", color=COLOR)
            await ctx.send(embed=embed)
            return
        self._cancel_sleep(ctx.guild.id)

        async def _sleep_timer(gid: int, mins: int):
            try:
                await asyncio.sleep(mins * 60)
                vc2 = self.bot.get_guild(gid).voice_client
                if vc2 and vc2.is_connected():
                    await vc2.disconnect()
                    self._clear_state(gid)
                    print(f"[MUSIC] Sleep timer: disconnected from guild {gid}")
            except asyncio.CancelledError:
                pass

        self._sleep_timers[ctx.guild.id] = asyncio.create_task(_sleep_timer(ctx.guild.id, minutes))
        embed = discord.Embed(
            description=f"\u23f0 Sleep timer: disconnect dalam **{minutes} menit**",
            color=COLOR
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="stop", aliases=["leave"], description="Tinggalkan voice channel")
    async def stop(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc:
            embed = discord.Embed(description="Gak ada di voice channel.", color=COLOR)
            await ctx.send(embed=embed)
            return
        name = vc.channel.name
        await _safe_stop(vc)
        await vc.disconnect()
        self._clear_state(ctx.guild.id)
        embed = discord.Embed(description=f"\U0001f44b Leave **{name}**", color=COLOR)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="fix-voice", description="Fix koneksi voice dengan reconnect")
    async def fix_voice(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc or not vc.is_connected():
            embed = discord.Embed(description="Bot gak di voice channel.", color=COLOR)
            await ctx.send(embed=embed)
            return
        channel = vc.channel
        url = self._voice_states.get(ctx.guild.id, {}).get("url", self._random_station_url())
        await _safe_stop(vc)
        await vc.disconnect()
        await asyncio.sleep(1)
        try:
            vc = await channel.connect()
            await asyncio.sleep(0.5)
            self._play_looping(vc, url)
            self._save_state(ctx.guild.id, channel.id, url)
            embed = discord.Embed(description="\u2705 Voice connection fixed!", color=COLOR)
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(description=f"\u274c Gagal reconnect: {e}", color=0xFF0000)
            await ctx.send(embed=embed)


async def _safe_stop(vc):
    try:
        if vc and vc.is_playing():
            vc.stop()
    except Exception:
        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
