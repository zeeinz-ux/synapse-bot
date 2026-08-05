import discord
from discord.ext import commands
import asyncio
import time
import random
import logging

log = logging.getLogger("bot")

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

FFMPEG_BEFORE_OPTS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10 -reconnect_at_eof 1 -reconnect_on_network_error 1 -nostdin"
FFMPEG_OPTS = "-vn -af aresample=async=1:min_hard_comp=0.1"

WATCHDOG_INTERVAL = 10
RECONNECT_LOG_EVERY = 6
ROTATE_FAIL_THRESHOLD = 2

# `url` is the primary source; `fallbacks` are rotated to on repeated stream failures.
# All fallbacks are cross-references to other (verified) primary URLs so the bot
# keeps emitting audio even if a single radio host blocks/geo-restricts its IP.
STATIONS = {
    "lofi": {
        "url": "https://play.streamafrica.net/lofiradio",
        "label": "\U0001f3a7 Synapse Radio",
        "fallbacks": [
            "https://radio.loficafe.net/listen/japanese-lofi/radio.mp3",
            "https://live.lofiradio.ru/lofi_mp3_128",
        ],
    },
    "jazz": {
        "url": "https://radio.loficafe.net/listen/japanese-lofi/radio.mp3",
        "label": "\U0001f3b7 Synapse Jazz",
        "fallbacks": [
            "https://play.streamafrica.net/lofiradio",
            "https://streaming.hotmixradio.com/hotmix-lofi-en-mp3",
        ],
    },
    "chill": {
        "url": "https://radio.loficafe.net/listen/chilling/radio.mp3",
        "label": "\U0001f30a Synapse Chill",
        "fallbacks": [
            "https://radio.loficafe.net/listen/japanese-lofi/radio.mp3",
            "https://live.lofiradio.ru/lofi_mp3_128",
        ],
    },
    "study": {
        "url": "https://live.lofiradio.ru/lofi_mp3_128",
        "label": "\U0001f4da Synapse Study",
        "fallbacks": [
            "https://radio.loficafe.net/listen/japanese-lofi/radio.mp3",
            "https://play.streamafrica.net/lofiradio",
        ],
    },
    "sleep": {
        "url": "https://streaming.hotmixradio.com/hotmix-lofi-en-mp3",
        "label": "\U0001f634 Synapse Sleep",
        "fallbacks": [
            "https://radio.loficafe.net/listen/chilling/radio.mp3",
            "https://play.streamafrica.net/lofiradio",
        ],
    },
}


class MusicCog(commands.Cog, name="Music"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._voice_states: dict[int, dict] = {}
        self._guild_stations: dict[int, str] = {}
        self._sleep_timers: dict[int, asyncio.Task] = {}
        self._watchdog_tasks: dict[int, asyncio.Task] = {}
        self._fail_counts: dict[int, int] = {}
        self._play_tokens: dict[int, int] = {}

    def _random_station_url(self) -> str:
        key = random.choice(list(STATIONS.keys()))
        return STATIONS[key]["url"]

    def _station_key(self, url: str) -> str:
        for k, v in STATIONS.items():
            if v["url"] == url:
                return k
        return "lofi"

    def _candidates(self, key: str) -> list[str]:
        seen: list[str] = []
        for u in [STATIONS[key]["url"], *STATIONS[key].get("fallbacks", [])]:
            if u not in seen:
                seen.append(u)
        return seen

    def _rotate_url(self, gid: int) -> str | None:
        state = self._voice_states.get(gid)
        if not state:
            return None
        current = state.get("url", "")
        cands = self._candidates(self._station_key(current))
        if not cands:
            return None
        try:
            idx = cands.index(current)
        except ValueError:
            idx = -1
        nxt = cands[(idx + 1) % len(cands)]
        if nxt == current:
            return None
        state["url"] = nxt
        state["updated_at"] = time.time()
        return nxt

    async def _respond(self, ctx, **kwargs):
        if ctx.interaction:
            try:
                await ctx.interaction.edit_original_response(**kwargs)
                return
            except Exception:
                pass
        await ctx.send(**kwargs)

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
        self._fail_counts.pop(guild_id, None)
        self._cancel_sleep(guild_id)
        self._stop_watchdog(guild_id)
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
            try:
                self.bot.loop.call_soon_threadsafe(task.cancel)
            except Exception:
                pass

    def _invalidate_play(self, guild_id: int):
        self._play_tokens[guild_id] = self._play_tokens.get(guild_id, 0) + 1

    def _stop_watchdog(self, guild_id: int):
        task = self._watchdog_tasks.pop(guild_id, None)
        if task and not task.done():
            try:
                self.bot.loop.call_soon_threadsafe(task.cancel)
            except Exception:
                pass

    async def _ensure_watchdog(self, guild_id: int):
        task = self._watchdog_tasks.get(guild_id)
        if task and not task.done():
            return
        self._watchdog_tasks[guild_id] = asyncio.create_task(self._watchdog(guild_id))

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
            url = data.get("url", "")
            if url not in {v["url"] for v in STATIONS.values()}:
                url = self._random_station_url()
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
                await self._ensure_watchdog(guild.id)
                log.info("[MUSIC] Auto-resume: %s / %s", guild.name, channel.name)
            except Exception as e:
                log.warning("[MUSIC] Auto-resume failed for %s: %s", guild.name, e)

    def _play_looping(self, vc, url: str):
        gid = vc.guild.id if vc and vc.guild else None
        if gid:
            self._cancel_sleep(gid)
            self._invalidate_play(gid)
        token = self._play_tokens.get(gid, 0) if gid else 0
        try:
            source = discord.FFmpegPCMAudio(url, before_options=FFMPEG_BEFORE_OPTS, options=FFMPEG_OPTS)
        except Exception as e:
            # construction-time failure: ffmpeg missing/broken or Popen failed
            log.error("[MUSIC] Cannot start ffmpeg (guild %s): %s", gid, e)
            if gid:
                self._fail_counts[gid] = self._fail_counts.get(gid, 0) + 1
            raise
        try:
            vc.stop()
            vc.play(source, after=lambda e: self._on_track_end(vc, url, e, token))
        except Exception as e:
            log.warning("[MUSIC] _play_looping error (guild %s): %s", gid, e)
            if gid:
                self._fail_counts[gid] = self._fail_counts.get(gid, 0) + 1

    def _on_track_end(self, vc, url: str, error, token: int):
        if error:
            log.warning("[MUSIC] Audio error: %s", error)
        if not vc or not vc.is_connected():
            return
        gid = vc.guild.id if vc and vc.guild else None
        if not gid:
            return
        # stale callback from an intentionally stopped stream -> don't restart
        if token != self._play_tokens.get(gid):
            log.info("[MUSIC] Ignoring stale track-end (guild %s)", gid)
            return
        state = self._voice_states.get(gid)
        current = state["url"] if state and state.get("url") else url
        if error:
            fails = self._fail_counts.get(gid, 0) + 1
            self._fail_counts[gid] = fails
            if fails >= ROTATE_FAIL_THRESHOLD:
                nxt = self._rotate_url(gid)
                if nxt:
                    log.warning("[MUSIC] Rotating fallback URL (guild %s) -> %s", gid, nxt)
                    current = nxt
                    self._fail_counts[gid] = 0
                else:
                    # every candidate failing; throttle so we don't hot-loop ffmpeg
                    time.sleep(2)
        else:
            self._fail_counts.pop(gid, None)
        log.info("[MUSIC] Stream ended, restarting (guild %s)", gid)
        self._play_looping(vc, current)

    async def _safe_stop(self, vc):
        gid = vc.guild.id if vc and vc.guild else None
        if gid:
            self._invalidate_play(gid)
        try:
            if vc and vc.is_playing():
                vc.stop()
        except Exception:
            pass

    async def _watchdog(self, guild_id: int):
        log.info("[MUSIC] Watchdog started for guild %s", guild_id)
        silent_ticks = 0
        reconnect_fails = 0
        try:
            while guild_id in self._voice_states:
                await asyncio.sleep(WATCHDOG_INTERVAL)
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    break
                state = self._voice_states.get(guild_id)
                if not state:
                    break
                vc = guild.voice_client
                try:
                    if not vc or not vc.is_connected():
                        channel = guild.get_channel(int(state.get("channel_id", 0)))
                        if not isinstance(channel, discord.VoiceChannel):
                            log.warning("[MUSIC] Watchdog: saved channel gone (guild %s), clearing", guild_id)
                            self._clear_state(guild_id)
                            break
                        reconnect_fails += 1
                        try:
                            vc = await channel.connect()
                            await asyncio.sleep(0.5)
                            self._play_looping(vc, state["url"])
                            log.warning("[MUSIC] Watchdog reconnected (guild %s) -> #%s", guild_id, channel.name)
                            reconnect_fails = 0
                            silent_ticks = 0
                        except Exception as e:
                            if reconnect_fails == 1 or reconnect_fails % RECONNECT_LOG_EVERY == 0:
                                log.warning("[MUSIC] Watchdog reconnect failed %sx (guild %s): %s", reconnect_fails, guild_id, e)
                    elif vc.is_playing():
                        silent_ticks = 0
                        reconnect_fails = 0
                        self._fail_counts.pop(guild_id, None)
                    else:
                        silent_ticks += 1
                        log.warning("[MUSIC] Watchdog: silent %ss (guild %s), restarting", silent_ticks * WATCHDOG_INTERVAL, guild_id)
                        self._play_looping(vc, state.get("url") or self._random_station_url())
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.exception("[MUSIC] Watchdog error (guild %s): %s", guild_id, e)
        except asyncio.CancelledError:
            pass
        self._watchdog_tasks.pop(guild_id, None)
        log.info("[MUSIC] Watchdog stopped for guild %s", guild_id)

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
                log.info("[MUSIC] Moved to %s, state updated", after.channel.name)
            return
        if before.channel and not after.channel:
            log.info("[MUSIC] Disconnected from %s, state preserved for watchdog auto-resume", before.channel.name)

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
            log.warning("[MUSIC] connect failed to %s: %s", channel.name, e)
            embed = discord.Embed(description=f"\u274c Gagal: {e}", color=0xFF0000)
            await ctx.send(embed=embed)
            return
        await asyncio.sleep(0.5)
        url = self._random_station_url()
        station_label = STATIONS[self._station_key(url)]["label"]
        try:
            self._play_looping(vc, url)
            self._save_state(ctx.guild.id, channel.id, url)
            await self._ensure_watchdog(ctx.guild.id)
            embed = discord.Embed(
                title="\u25b6 Connected",
                description=f"Join **{channel.name}** - **{station_label}**",
                color=COLOR
            )
            await ctx.send(embed=embed)
        except discord.ClientException:
            embed = discord.Embed(description=f"\u2705 Join **{channel.name}** (voice tersambung, tapi audio error)", color=COLOR)
            await ctx.send(embed=embed)
        except Exception:
            embed = discord.Embed(description=f"\u2705 Join **{channel.name}**", color=COLOR)
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="play", aliases=["p"], description="Putar Synapse radio")
    @discord.app_commands.describe(query="Nama station (kosongin buat random)")
    @discord.app_commands.choices(query=[
        discord.app_commands.Choice(name=v["label"], value=k)
        for k, v in STATIONS.items()
    ])
    async def play(self, ctx: commands.Context, *, query: str = None):
        vc = ctx.guild.voice_client
        if not vc:
            if ctx.author.voice and ctx.author.voice.channel:
                if ctx.interaction:
                    await ctx.defer()
                try:
                    vc = await ctx.author.voice.channel.connect()
                except Exception as e:
                    log.warning("[MUSIC] /play connect failed: %s", e)
                    embed = discord.Embed(description=f"\u274c Gagal connect: {e}", color=0xFF0000)
                    await self._respond(ctx, embed=embed)
                    return
            else:
                embed = discord.Embed(description="Bot gak di voice. Pake `!connect` dulu atau join voice dulu.", color=COLOR)
                await ctx.send(embed=embed)
                return
        key = (query or "").strip().lower()
        if key and key not in STATIONS:
            available = ", ".join(STATIONS.keys())
            embed = discord.Embed(description=f"Station `{key}` gak ada. Yang tersedia: {available}", color=COLOR)
            await ctx.send(embed=embed)
            return
        if not key:
            key = random.choice(list(STATIONS.keys()))
        station = STATIONS[key]
        await self._safe_stop(vc)
        await asyncio.sleep(0.3)
        try:
            self._play_looping(vc, station["url"])
        except discord.ClientException:
            embed = discord.Embed(description="\u274c Audio error: ffmpeg gak bisa jalan di server. Cek log.", color=0xFF0000)
            await self._respond(ctx, embed=embed)
            return
        self._save_state(ctx.guild.id, vc.channel.id, station["url"])
        await self._ensure_watchdog(ctx.guild.id)
        embed = discord.Embed(
            title="\u25b6 Now Playing",
            description=f"**{station['label']}**",
            color=COLOR
        )
        await self._respond(ctx, embed=embed)

    @commands.hybrid_command(name="station", description="Ganti station atau lihat daftar station")
    @discord.app_commands.describe(name="Nama station (kosongin buat liat daftar)")
    @discord.app_commands.choices(name=[
        discord.app_commands.Choice(name=v["label"], value=k)
        for k, v in STATIONS.items()
    ])
    async def station(self, ctx: commands.Context, *, name: str = None):
        if not name:
            lines = "\n".join(f"{v['label']} \u2014 `{k}`" for k, v in STATIONS.items())
            embed = discord.Embed(
                title="\U0001f3b5 Synapse Stations",
                description=lines,
                color=COLOR
            )
            embed.set_footer(text="Gunakan: /station <nama> buat ganti station")
            await ctx.send(embed=embed)
            return
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
        await self._safe_stop(vc)
        await asyncio.sleep(0.3)
        try:
            self._play_looping(vc, station["url"])
        except discord.ClientException:
            embed = discord.Embed(description="\u274c Audio error: ffmpeg gak bisa jalan di server. Cek log.", color=0xFF0000)
            await ctx.send(embed=embed)
            return
        self._save_state(ctx.guild.id, vc.channel.id, station["url"])
        await self._ensure_watchdog(ctx.guild.id)
        embed = discord.Embed(
            title="\U0001f3b5 Station Changed",
            description=f"Sekarang muterin **{station['label']}**",
            color=COLOR
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="song", description="Lihat station yang sedang diputar")
    async def song(self, ctx: commands.Context):
        if ctx.interaction:
            await ctx.defer()
        vc = ctx.guild.voice_client
        if not vc or not vc.is_connected() or not vc.is_playing():
            embed = discord.Embed(description="Gak ada audio yang diputar.", color=COLOR)
            await self._respond(ctx, embed=embed)
            return
        key = self._guild_stations.get(ctx.guild.id, "lofi")
        station = STATIONS[key]
        embed = discord.Embed(
            title="\u25b6 Now Playing",
            description=f"**{station['label']}**",
            color=COLOR
        )
        await self._respond(ctx, embed=embed)

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
                    log.info("[MUSIC] Sleep timer: disconnected from guild %s", gid)
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
        await self._safe_stop(vc)
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
        url = self._voice_states.get(ctx.guild.id, {}).get("url", "")
        if url not in {v["url"] for v in STATIONS.values()}:
            url = self._random_station_url()
        await self._safe_stop(vc)
        await vc.disconnect()
        await asyncio.sleep(1)
        try:
            vc = await channel.connect()
            await asyncio.sleep(0.5)
            self._play_looping(vc, url)
            self._save_state(ctx.guild.id, channel.id, url)
            await self._ensure_watchdog(ctx.guild.id)
            embed = discord.Embed(description="\u2705 Voice connection fixed!", color=COLOR)
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(description=f"\u274c Gagal reconnect: {e}", color=0xFF0000)
            await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
