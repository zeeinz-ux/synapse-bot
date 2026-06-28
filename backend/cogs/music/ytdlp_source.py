import asyncio
import os
import json
import subprocess
import time
import shutil
import hashlib
import warnings
from dataclasses import dataclass, field
from typing import Optional

from backend.utils.formatters import format_duration

import discord
import yt_dlp

CACHE_DIR = "/tmp/discord_audio_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_COOKIES_DEFAULT = os.path.join(_PROJECT_ROOT, "cookies", "cookies.txt")
COOKIES_FILE = os.getenv("COOKIES_FILE", _COOKIES_DEFAULT)
COOKIES_FROM_BROWSER = os.getenv("COOKIES_FROM_BROWSER", "")
PO_TOKEN = os.getenv("YOUTUBE_PO_TOKEN", "")

# Auth args for yt-dlp CLI (priority: PO Token > Browser Cookie > Cookie File > web client)
_YTDLP_BASE = ["--retries", "3", "--fragment-retries", "3",
               "--add-header", "referer:youtube.com",
               "--add-header", "user-agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"]

if PO_TOKEN:
    _YTDLP_AUTH = ["--extractor-args", f"youtube:po_token=web+{PO_TOKEN};player_client=web"]
elif COOKIES_FROM_BROWSER:
    _YTDLP_AUTH = ["--cookies-from-browser", COOKIES_FROM_BROWSER]
elif COOKIES_FILE and os.path.isfile(COOKIES_FILE):
    _YTDLP_AUTH = ["--cookies", COOKIES_FILE]
else:
    _YTDLP_AUTH = ["--extractor-args", "youtube:player_client=android"]

YTDLP_AUTH_ARGS = _YTDLP_BASE + _YTDLP_AUTH

# Auth opts for yt-dlp Python library
def _get_ytdlp_auth_opts() -> dict:
    opts = {"retries": 3, "fragment_retries": 3}
    if PO_TOKEN:
        opts["extractor_args"] = {"youtube": [f"po_token=web+{PO_TOKEN}", "player_client=web"]}
    elif COOKIES_FROM_BROWSER:
        opts["cookiefile"] = None
        opts["cookiesfrombrowser"] = (COOKIES_FROM_BROWSER,)
    elif COOKIES_FILE:
        opts["cookiefile"] = COOKIES_FILE
    else:
        opts["extractor_args"] = {"youtube": ["player_client=android"]}
    return opts

warnings.filterwarnings("ignore", message=".*line buffering.*binary mode.*")


def _find_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        print(f"[FFMPEG] Found via shutil.which: {ffmpeg}")
        return ffmpeg

    common_paths = [
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/usr/bin/ffmpeg.exe",
        r"C:\Program Files\KMPlayer 64X\LAVFilters64\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
    ]
    for path in common_paths:
        if os.path.isfile(path):
            print(f"[FFMPEG] Found via fallback path: {path}")
            return path

    print("[FFMPEG] ⚠️ ffmpeg tidak ditemukan di PATH. Musik mungkin tidak berfungsi.")
    print("[FFMPEG] Install: https://ffmpeg.org/download.html")
    return "ffmpeg"


FFMPEG_PATH = _find_ffmpeg()

_AUTH_OPTS = _get_ytdlp_auth_opts()

YTDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "noplaylist": True,
    "socket_timeout": 10,
    "retries": 1,
    **_AUTH_OPTS,
}

YTDL_SEARCH_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "extract_flat": "in_playlist",
    "noplaylist": False,
    "socket_timeout": 10,
    "retries": 1,
    **_AUTH_OPTS,
}

YTDL_PLAYLIST_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": "in_playlist",
    "skip_download": True,
    "dump_single_json": True,
    "socket_timeout": 10,
    "retries": 1,
    **_AUTH_OPTS,
}


@dataclass
class YtDlpTrack:
    title: str
    uri: str
    author: str = "Unknown"
    duration: int = 0
    artwork: str = ""
    webpage_url: str = ""
    stream_url: str = ""
    _ydl_info: dict = field(default_factory=dict, repr=False)

    @property
    def length(self) -> int:
        return self.duration

    @property
    def identifier(self) -> str:
        return self.webpage_url or self.uri

    @classmethod
    def from_info(cls, info: dict) -> "YtDlpTrack":
        title = info.get("title") or "Unknown"
        uri = info.get("url") or info.get("webpage_url", "")
        author = info.get("channel") or info.get("uploader") or info.get("artist", "Unknown")
        duration_raw = info.get("duration")
        duration = (int(duration_raw) * 1000) if duration_raw else 0
        artwork = info.get("thumbnail") or ""
        webpage_url = info.get("webpage_url") or uri
        stream_url = info.get("url") or ""
        return cls(
            title=title,
            uri=uri,
            author=author,
            duration=duration,
            artwork=artwork,
            webpage_url=webpage_url,
            stream_url=stream_url,
            _ydl_info=info,
        )

    async def get_stream_url(self) -> str:
        if self.stream_url:
            return self.stream_url
        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(YTDL_OPTS).extract_info(self.webpage_url, download=False))
            url = info.get("url", "")
            self.stream_url = url
            return url
        except Exception as e:
            raise RuntimeError(f"Failed to get stream URL: {e}")


@dataclass
class YtDlpPlaylist:
    name: str
    tracks: list


class YtDlpSearcher:
    _cache: dict = {}
    _CACHE_TTL = 300

    @staticmethod
    async def search(query: str) -> list:
        cache_key = f"search:{query}"
        cached = YtDlpSearcher._cache.get(cache_key)
        if cached and (time.time() - cached["ts"]) < YtDlpSearcher._CACHE_TTL:
            return cached["tracks"]

        if query.startswith("ytsearch:"):
            raw_query = query[len("ytsearch:"):].strip()
            actual_query = f"ytsearch5:{raw_query}"
        else:
            actual_query = query

        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(YTDL_SEARCH_OPTS).extract_info(actual_query, download=False)
            )
        except Exception:
            return []

        if not info:
            return []

        entries = info.get("entries", [])
        tracks = []
        for entry in entries:
            if not entry:
                continue
            track = YtDlpTrack.from_info(entry)
            tracks.append(track)

        YtDlpSearcher._cache[cache_key] = {"ts": time.time(), "tracks": tracks}
        return tracks

    @staticmethod
    async def extract_info(url: str) -> Optional[YtDlpTrack]:
        cache_key = f"info:{url}"
        cached = YtDlpSearcher._cache.get(cache_key)
        if cached and (time.time() - cached["ts"]) < YtDlpSearcher._CACHE_TTL:
            return cached["track"]

        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(YTDL_OPTS).extract_info(url, download=False)
            )
        except Exception:
            return None

        if info:
            track = YtDlpTrack.from_info(info)
            YtDlpSearcher._cache[cache_key] = {"ts": time.time(), "track": track}
            return track
        return None

    @staticmethod
    async def extract_playlist(url: str) -> Optional[YtDlpPlaylist]:
        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(YTDL_PLAYLIST_OPTS).extract_info(url, download=False)
            )
        except Exception:
            return None

        if not info:
            return None

        entries = info.get("entries", [])
        playlist_name = info.get("title", "Unknown Playlist")

        tracks = []
        for entry in entries:
            if not entry:
                continue
            track = YtDlpTrack.from_info(entry)
            tracks.append(track)

        return YtDlpPlaylist(name=playlist_name, tracks=tracks)


class NowPlayingView(discord.ui.View):
    def __init__(self, controller: "MusicController"):
        super().__init__(timeout=None)
        self.controller = controller
        self._loop_emojis = {"off": "➡️", "single": "🔂", "queue": "🔁"}

    async def _auth(self, i: discord.Interaction) -> bool:
        if not i.user.voice or i.user.voice.channel.id != self.controller.vc.channel.id:
            await i.response.send_message("Join the bot's voice channel first", ephemeral=True)
            return False
        if self.controller._owner_id is not None and self.controller._owner_id != i.user.id:
            owner = i.guild.get_member(self.controller._owner_id)
            name = owner.display_name if owner else "another user"
            await i.response.send_message(f"❌ Hanya **{name}** yang bisa mengontrol musik saat ini.", ephemeral=True)
            return False
        return True

    async def _ok(self, i: discord.Interaction, msg: str):
        if i.response.is_done():
            await i.followup.send(msg, ephemeral=True)
        else:
            await i.response.send_message(msg, ephemeral=True)

    async def _sync(self):
        if self.controller._now_playing_msg:
            try:
                await self.controller._now_playing_msg.edit(
                    embed=self.controller._build_np_embed(), view=self)
            except Exception:
                pass

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.secondary, custom_id="np_pause")
    async def pause_btn(self, i: discord.Interaction, btn: discord.ui.Button):
        if not await self._auth(i):
            return
        c = self.controller
        if c._paused:
            c.vc.resume()
            c._paused = False
            c._start_time = time.time() - c._paused_position
            btn.emoji = "⏸️"
            await self._ok(i, "▶️ Resumed")
        else:
            c._paused_position = time.time() - c._start_time
            c.vc.pause()
            c._paused = True
            btn.emoji = "▶️"
            await self._ok(i, "⏸️ Paused")
        await self._sync()

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="np_skip")
    async def skip_btn(self, i: discord.Interaction, btn: discord.ui.Button):
        if not await self._auth(i):
            return
        if not self.controller.queue:
            return await self._ok(i, "❌ No more tracks in queue")
        self.controller.vc.stop()
        await self._ok(i, f"⏭️ Skipped")

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="np_stop")
    async def stop_btn(self, i: discord.Interaction, btn: discord.ui.Button):
        if not await self._auth(i):
            return
        await self.controller.stop()
        await self._ok(i, "⏹️ Stopped")

    @discord.ui.button(emoji="📋", style=discord.ButtonStyle.primary, custom_id="np_queue")
    async def queue_btn(self, i: discord.Interaction, btn: discord.ui.Button):
        if not await self._auth(i):
            return
        c = self.controller
        lines = []
        if c.current_track:
            lines.append(f"**▶️ Now:** {c.current_track.title}")
        for n, t in enumerate(c.queue[:10], 1):
            lines.append(f"`{n}.` {t.title}")
        if len(c.queue) > 10:
            lines.append(f"*...and {len(c.queue)-10} more*")
        await self._ok(i, "\n".join(lines) or "Queue is empty")

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="np_shuffle")
    async def shuffle_btn(self, i: discord.Interaction, btn: discord.ui.Button):
        if not await self._auth(i):
            return
        import random
        random.shuffle(self.controller.queue)
        await self._ok(i, f"🔀 Shuffled {len(self.controller.queue)} tracks")

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, custom_id="np_volume")
    async def volume_btn(self, i: discord.Interaction, btn: discord.ui.Button):
        if not await self._auth(i):
            return
        class _Modal(discord.ui.Modal):
            def __init__(self, c):
                super().__init__(title="Volume")
                self.c = c
                self.input = discord.ui.TextInput(label="Volume (0-1000)", placeholder=str(c._volume), max_length=4)
                self.add_item(self.input)
            async def on_submit(self, m: discord.Interaction):
                try:
                    v = max(0, min(1000, int(self.input.value)))
                    await self.c.set_volume(v)
                    await m.response.send_message(f"🔊 Volume **{v}**", ephemeral=True)
                except ValueError:
                    await m.response.send_message("❌ Not a number", ephemeral=True)
        await i.response.send_modal(_Modal(self.controller))

    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.secondary, custom_id="np_loop")
    async def loop_btn(self, i: discord.Interaction, btn: discord.ui.Button):
        if not await self._auth(i):
            return
        c = self.controller
        c.loop_mode = {"off": "single", "single": "queue", "queue": "off"}.get(c.loop_mode, "off")
        btn.emoji = self._loop_emojis.get(c.loop_mode, "➡️")
        if c.loop_mode == "queue":
            c._queue_history.clear()
        if c.loop_mode == "off":
            c._single_loop_track = None
        await self._ok(i, f"Loop: {c.loop_mode}")
        await self._sync()

    @discord.ui.button(emoji="🎲", style=discord.ButtonStyle.secondary, custom_id="np_autoplay")
    async def autoplay_btn(self, i: discord.Interaction, btn: discord.ui.Button):
        if not await self._auth(i):
            return
        c = self.controller
        c.autoplay = not c.autoplay
        btn.style = discord.ButtonStyle.success if c.autoplay else discord.ButtonStyle.secondary
        await self._ok(i, f"Autoplay: {'ON' if c.autoplay else 'OFF'}")
        await self._sync()


class MusicController:
    def __init__(self, voice_client, text_channel=None):
        self.vc = voice_client
        self.home = text_channel
        self.queue = []
        self.current_track: Optional[YtDlpTrack] = None
        self.loop_mode = "off"
        self.autoplay = False
        self._volume = 100
        self._start_time = 0.0
        self._paused = False
        self._paused_position = 0.0
        self._pause_reason: str = "none"
        self._last_track_id = None
        self._last_embed_time = 0.0
        self._alone_task = None
        self._track_lock = asyncio.Lock()
        self._queue_history = []
        self._single_loop_track = None
        self._guild_id = None
        self._current_file: Optional[str] = None
        self._preloaded_file: Optional[str] = None
        self._preloaded_for: Optional[str] = None
        self._now_playing_msg: Optional[discord.Message] = None
        self._np_updater_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._recovery_task: Optional[asyncio.Task] = None
        self._recovery_attempts: int = 0
        self._stopped: bool = False
        self._state_file: str = f"/tmp/discord_player_state.json"
        self._owner_id: Optional[int] = None

    def set_owner(self, user_id: int):
        if self._owner_id is None:
            self._owner_id = user_id

    def is_owner(self, user_id: int) -> bool:
        return self._owner_id is not None and self._owner_id == user_id

    def _cache_path(self, url: str) -> str:
        h = hashlib.md5(url.encode()).hexdigest()
        return os.path.join(CACHE_DIR, f"{h}.opus")

    async def _download_track(self, url: str) -> Optional[str]:
        dest = self._cache_path(url)
        if os.path.isfile(dest):
            return dest
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["yt-dlp", "-f", "bestaudio", "-o", dest, "--no-part", "--no-progress", "--extract-audio", "--audio-format", "opus", url, *YTDLP_AUTH_ARGS],
                    capture_output=True, timeout=120,
                )
            )
            if result.returncode != 0:
                stderr = result.stderr.decode(errors="replace")[:500] if result.stderr else ""
                print(f"[DOWNLOAD ERROR] yt-dlp exited {result.returncode} for {url[:60]}: {stderr}")
                return None
            if os.path.isfile(dest):
                return dest
            import glob as _glob
            prefix = dest.rsplit(".", 1)[0]
            matches = _glob.glob(prefix + ".*")
            if matches:
                print(f"[DOWNLOAD] yt-dlp wrote to {matches[0]} instead of {dest}")
                os.rename(matches[0], dest)
                return dest if os.path.isfile(dest) else None
            stderr = result.stderr.decode(errors="replace")[:500] if result.stderr else ""
            print(f"[DOWNLOAD ERROR] File not found at {dest} or any {prefix}.* variant. stderr: {stderr}")
            return None
        except Exception as e:
            print(f"[DOWNLOAD ERROR] {url[:60]}: {e}")
            return None

    @property
    def channel(self):
        return self.vc.channel if self.vc else None

    @property
    def guild(self):
        return self.vc.guild if self.vc else None

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def position(self) -> int:
        if not self.current_track or not self.vc:
            return 0
        if self._paused:
            return int(self._paused_position * 1000)
        elapsed = time.time() - self._start_time
        return int(elapsed * 1000)

    async def set_volume(self, vol: int):
        self._volume = max(0, min(1000, vol))
        if self.vc and self.vc.source:
            if hasattr(self.vc.source, "volume"):
                self.vc.source.volume = self._volume / 100.0

    @staticmethod
    def _progress_bar(current_ms: int, total_ms: int, length: int = 12) -> str:
        if total_ms <= 0:
            return "🔴 LIVE"
        ratio = min(current_ms / total_ms, 1.0)
        filled = int(ratio * length)
        bar = "▬" * filled + "🔘" + "▬" * (length - filled - 1)
        return f"{bar} `{format_duration(current_ms)} / {format_duration(total_ms)}`"

    def _build_np_embed(self) -> discord.Embed:
        track = self.current_track
        if not track:
            return discord.Embed(title="⏹️ Nothing Playing", color=discord.Color.dark_gray())
        embed = discord.Embed(
            title="▶️ Now Playing",
            description=f"[{track.title}]({track.uri})",
            color=discord.Color.green(),
        )
        embed.add_field(name="Author", value=track.author or "Unknown", inline=True)
        embed.add_field(name="Duration", value=format_duration(track.duration), inline=True)
        position = self.position
        embed.add_field(
            name="Progress",
            value=self._progress_bar(position, track.duration),
            inline=False,
        )
        embed.add_field(name="In Queue", value=str(len(self.queue)), inline=True)
        embed.add_field(name="Autoplay", value="ON" if self.autoplay else "OFF", inline=True)
        loop_text = {"single": "Single", "queue": "Queue Loop", "off": "OFF"}.get(self.loop_mode, "OFF")
        embed.add_field(name="Loop", value=loop_text, inline=True)
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
        return embed

    async def _update_now_playing(self):
        embed = self._build_np_embed()
        view = NowPlayingView(self) if self.current_track else None
        try:
            if self._now_playing_msg:
                await self._now_playing_msg.edit(embed=embed, view=view)
            elif self.home:
                self._now_playing_msg = await self.home.send(embed=embed, view=view)
        except discord.NotFound:
            self._now_playing_msg = None
        except discord.Forbidden:
            pass

    async def _np_updater_loop(self):
        try:
            tick = 0
            while True:
                await asyncio.sleep(10)
                tick += 1
                if not self.current_track or (not self.vc.is_playing() and not self.vc.is_paused()):
                    continue
                await self._update_now_playing()
                if tick % 3 == 0:
                    self._save_state()
        except asyncio.CancelledError:
            pass

    def _start_np_updater(self):
        self._stop_np_updater()
        self._np_updater_task = asyncio.create_task(self._np_updater_loop())

    def _stop_np_updater(self):
        if self._np_updater_task and not self._np_updater_task.done():
            self._np_updater_task.cancel()
            self._np_updater_task = None

    # ==========================================================
    # WATCHDOG — detect stuck playback (Beatra parity)
    # ==========================================================
    def _stop_watchdog(self):
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            self._watchdog_task = None

    async def _watchdog_loop(self, timeout: float):
        try:
            await asyncio.sleep(timeout)
            print(f"[WATCHDOG] Track stuck for {timeout}s, forcing skip")
            if self.vc and self.vc.is_playing():
                self.vc.stop()
        except asyncio.CancelledError:
            pass

    def _start_watchdog(self, duration_ms: int):
        self._stop_watchdog()
        if duration_ms <= 0:
            return
        timeout = (duration_ms / 1000) + 10
        self._watchdog_task = asyncio.create_task(self._watchdog_loop(timeout))

    # ==========================================================
    # SEQUENTIAL PRELOAD — preload all queued tracks (Beatra parity)
    # ==========================================================
    async def _sequential_preload(self):
        tracks = list(self.queue[:10])
        for track in tracks:
            url = track.webpage_url or track.uri
            dest = self._cache_path(url)
            if not os.path.isfile(dest):
                try:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda u=url, d=dest: subprocess.run(
                            ["yt-dlp", "-f", "bestaudio", "-o", d, "--no-part", "--no-progress", "--extract-audio", "--audio-format", "opus", u, *YTDLP_AUTH_ARGS],
                            capture_output=True, timeout=120,
                        )
                    )
                except Exception:
                    pass
            await asyncio.sleep(0.1)

    # ==========================================================
    # PAUSE REASONS — manual, alone, mute (Beatra parity)
    # ==========================================================
    async def pause_for(self, reason: str = "manual"):
        if self._paused:
            return
        self._paused_position = time.time() - self._start_time
        self._pause_reason = reason
        self._paused = True
        if self.vc and self.vc.is_playing():
            self.vc.pause()
        await self._update_now_playing()

    async def resume_for(self, reason: str = "manual"):
        if not self._paused:
            return
        self._pause_reason = "none"
        self._paused = False
        self._start_time = time.time() - self._paused_position
        if self.vc and self.vc.is_paused():
            self.vc.resume()
        await self._update_now_playing()

    # ==========================================================
    # INACTIVITY TIMER — auto-pause when alone (Beatra parity)
    # ==========================================================
    async def _alone_pause(self):
        await asyncio.sleep(30)
        if not self._paused and self.vc and self.vc.channel:
            humans = [m for m in self.vc.channel.members if not m.bot]
            if not humans:
                await self.pause_for("alone")
                if self.home:
                    try:
                        await self.home.send("⏸️ Auto-paused — no one in voice channel")
                    except Exception:
                        pass

    def _start_alone_timer(self):
        self._stop_alone_timer()
        self._alone_task = asyncio.create_task(self._alone_pause())

    def _stop_alone_timer(self):
        if self._alone_task and not self._alone_task.done():
            self._alone_task.cancel()
            self._alone_task = None

    def _cancel_alone_timer(self):
        self._stop_alone_timer()

    # ==========================================================
    # CONNECTION RECOVERY — auto-reconnect + resume (Beatra parity)
    # ==========================================================
    async def _connection_recovery(self, target_channel, max_attempts=3):
        self._recovery_attempts += 1
        saved_track = self.current_track
        saved_position = self.position
        for attempt in range(max_attempts):
            try:
                print(f"[RECOVERY] Attempt {attempt + 1}/{max_attempts}")
                vc = await target_channel.connect(self_deaf=False)
                self.vc = vc
                self._recovery_attempts = 0
                if saved_track:
                    await self.play(saved_track)
                    if saved_position > 3000:
                        await asyncio.sleep(0.5)
                        await self.seek(saved_position)
                return
            except Exception as e:
                print(f"[RECOVERY] Attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(2)
        self._recovery_attempts = 0
        await self._cleanup_np()

    # ==========================================================
    # STATE PERSISTENCE — save/restore player state (Beatra parity)
    # ==========================================================
    def _save_state(self):
        if not self.current_track:
            return
        try:
            state = {
                "track": {
                    "title": self.current_track.title,
                    "uri": self.current_track.webpage_url or self.current_track.uri,
                    "author": self.current_track.author,
                    "duration": self.current_track.duration,
                    "artwork": self.current_track.artwork,
                },
                "position_ms": self.position,
                "paused": self._paused,
                "volume": self._volume,
                "loop_mode": self.loop_mode,
                "autoplay": self.autoplay,
                "queue": [
                    {"title": t.title, "uri": t.webpage_url or t.uri,
                     "author": t.author, "duration": t.duration, "artwork": t.artwork}
                    for t in self.queue[:20]
                ],
            }
            with open(self._state_file, "w") as f:
                json.dump(state, f)
        except Exception as e:
            print(f"[STATE SAVE ERROR] {e}")

    def _load_state(self) -> Optional[dict]:
        try:
            if os.path.isfile(self._state_file):
                with open(self._state_file) as f:
                    return json.load(f)
        except Exception as e:
            print(f"[STATE LOAD ERROR] {e}")
        return None

    def _clear_state(self):
        try:
            if os.path.isfile(self._state_file):
                os.remove(self._state_file)
        except Exception:
            pass

    async def play(self, track: YtDlpTrack):
        # Enrich flat-extracted playlist tracks with full metadata (thumbnail, etc.)
        if not track.artwork and (track.webpage_url or track.uri):
            enriched = await YtDlpSearcher.extract_info(track.webpage_url or track.uri)
            if enriched and enriched.artwork:
                track.artwork = enriched.artwork
                if enriched.title:
                    track.title = enriched.title
                if enriched.author != "Unknown":
                    track.author = enriched.author
                if enriched.duration:
                    track.duration = enriched.duration

        self.current_track = track
        self._single_loop_track = track
        if self.vc.is_playing() or self.vc.is_paused():
            self.vc.stop()
            print("[DEBUG PLAY] Menghentikan lagu sebelumnya.")

        url = track.webpage_url or track.uri
        file_path = self._preloaded_file if self._preloaded_for == url else None

        if file_path and os.path.isfile(file_path):
            print(f"[DEBUG PLAY] Menggunakan cache: {file_path}")
        else:
            print(f"[DEBUG PLAY] Mendownload: {url}")
            file_path = await self._download_track(url)

        if not file_path or not os.path.isfile(file_path):
            print(f"[ERROR PLAY] File tidak ditemukan/gagal download: {file_path}")
            await self._play_next()
            return

        self._current_file = file_path
        print(f"[DEBUG PLAY] Mencoba memutar file: {file_path}")
        
        try:
            # Audit FFmpeg: Pastikan executable benar-benar ada
            print(f"[DEBUG PLAY] Menggunakan FFmpeg di: {FFMPEG_PATH}")
            source = discord.FFmpegPCMAudio(file_path, executable=FFMPEG_PATH)
            vol_source = discord.PCMVolumeTransformer(source, volume=self._volume / 100.0)
            
            self.vc.play(vol_source, after=self._on_track_end_wrapper)
            
            print("[DEBUG PLAY] self.vc.play() berhasil dipanggil.")
            self._start_time = time.time()
            self._paused = False
            self._paused_position = 0.0
            self._pause_reason = "none"
            self._stopped = False
            self._start_watchdog(track.duration)
            asyncio.create_task(self._sequential_preload())
            await self._update_now_playing()
            self._start_np_updater()
            print("[DEBUG PLAY] Play command executed successfully.")
        except Exception as e:
            print(f"[CRITICAL ERROR PLAY] Gagal inisialisasi FFmpeg: {e}")
            import traceback
            traceback.print_exc()
            await self._play_next()

    async def _update_status(self, text: str):
        if self._now_playing_msg:
            try:
                embed = discord.Embed(title=text, color=discord.Color.blue())
                await self._now_playing_msg.edit(embed=embed)
            except Exception:
                pass
        elif self.home:
            try:
                embed = discord.Embed(title=text, color=discord.Color.blue())
                self._now_playing_msg = await self.home.send(embed=embed)
            except Exception:
                pass

    def _on_track_end_wrapper(self, error):
        if error:
            print(f"[TRACK END ERROR] {error}")
        asyncio.run_coroutine_threadsafe(self._on_track_end(error), self.vc.client.loop if self.vc and self.vc.client else None)

    async def _on_track_end(self, error=None):
        self._stop_watchdog()
        self._save_state()
        await asyncio.sleep(0.3)
        async with self._track_lock:
            if self.loop_mode == "single" and self._single_loop_track:
                await self.play(self._single_loop_track)
                return
            if self.loop_mode == "queue" and not self.queue and self._queue_history:
                self.queue = list(self._queue_history)
                self._queue_history.clear()
            if self.queue:
                next_track = self.queue.pop(0)
                asyncio.create_task(self._preload_next(next_track))
                await self.play(next_track)
                return
            if self.autoplay and self._single_loop_track:
                try:
                    next_track = await self._autoplay_search()
                    if next_track:
                        asyncio.create_task(self._preload_next(next_track))
                        await self.play(next_track)
                        return
                except Exception as e:
                    print(f"[AUTOPLAY ERROR] {e}")
            self.current_track = None
            self._single_loop_track = None
            self._stop_np_updater()
            await self._cleanup_current_file()
            self._clear_state()
            await self._update_now_playing()

    async def _play_next(self):
        if self.queue:
            next_track = self.queue.pop(0)
            asyncio.create_task(self._preload_next(next_track))
            await self.play(next_track)

    async def _preload_next(self, track: YtDlpTrack):
        url = track.webpage_url or track.uri
        dest = self._cache_path(url)
        if os.path.isfile(dest):
            self._preloaded_file = dest
            self._preloaded_for = url
            return
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["yt-dlp", "-f", "bestaudio", "-o", dest, "--no-part", "--no-progress", "--extract-audio", "--audio-format", "opus", url, *YTDLP_AUTH_ARGS],
                    capture_output=True, timeout=120,
                )
            )
            if os.path.isfile(dest):
                self._preloaded_file = dest
                self._preloaded_for = url
        except Exception:
            pass

    # ── Genre‑aware autoplay ──
    _GENRE_SEEDS = [
        "pop", "rock", "lofi", "electronic", "anime",
        "hip hop", "r&b", "jazz", "classical", "indie",
        "metal", "country", "folk", "blues", "reggae",
    ]
    _AUTOPLAY_BAD_KEYWORDS = [
        "tutorial", "podcast", "unboxing", "interview", "review",
        "reaction", "asmr", "lecture", "speech", "commentary",
        "vlog", "gameplay", "let's play", "livestream", "stream",
    ]

    async def _autoplay_search(self) -> Optional["YtDlpTrack"]:
        last = self._single_loop_track
        if not last:
            return None

        import random as _random
        queries = []

        # 1. Related-video style: author + a descriptive keyword from the title
        title_words = [w for w in (last.title or "").split() if len(w) > 3]
        if title_words:
            kw = _random.choice(title_words)
            queries.append(f"ytmsearch:{last.author} {kw}")

        # 2. Same-author mix (original fallback)
        queries.append(f"ytmsearch:{last.author} - {last.title}")

        # 3. Genre-based — guess a genre from title + author
        title_lower = (last.title or "").lower()
        author_lower = (last.author or "").lower()
        matched = [g for g in self._GENRE_SEEDS if g in title_lower or g in author_lower]
        if matched:
            genre = _random.choice(matched)
            queries.append(f"ytmsearch:{genre} music")
        else:
            queries.append(f"ytmsearch:{_random.choice(self._GENRE_SEEDS)} music")

        _random.shuffle(queries)

        for q in queries:
            try:
                results = await YtDlpSearcher.search(q)
            except Exception:
                continue
            if not results:
                continue
            for r in results:
                dur = r.duration or 0
                if dur < 30000 or dur > 600000:
                    continue
                title_l = (r.title or "").lower()
                if any(bad in title_l for bad in self._AUTOPLAY_BAD_KEYWORDS):
                    continue
                if r.uri == getattr(last, "uri", None):
                    continue
                return r
        return None

    async def seek(self, position_ms: int):
        if not self.current_track or not self.vc:
            return
        self.vc.stop()

        url = self.current_track.webpage_url or self.current_track.uri
        position_sec = position_ms / 1000

        file_path = self._current_file
        if not file_path or not os.path.isfile(file_path):
            file_path = await self._download_track(url)
        if not file_path or not os.path.isfile(file_path):
            return

        try:
            source = discord.FFmpegPCMAudio(
                file_path, executable=FFMPEG_PATH,
                before_options=f"-ss {position_sec} -noaccurate_seek",
            )
            vol_source = discord.PCMVolumeTransformer(source, volume=self._volume / 100.0)
            self.vc.play(vol_source, after=lambda e: self._on_track_end_wrapper(e))
            self._start_time = time.time() - position_sec
            self._paused = False
            self._pause_reason = "none"
            self._start_watchdog(self.current_track.duration if self.current_track else 0)
            await self._update_now_playing()
            self._start_np_updater()
        except Exception as e:
            print(f"[SEEK ERROR] {e}")

    async def _cleanup_current_file(self):
        if self._current_file and os.path.isfile(self._current_file):
            try:
                os.remove(self._current_file)
            except Exception:
                pass
            self._current_file = None
        if self._preloaded_file and self._preloaded_file != self._current_file:
            try:
                os.remove(self._preloaded_file)
            except Exception:
                pass
        self._preloaded_file = None
        self._preloaded_for = None

    async def _cleanup_np(self):
        self._stop_np_updater()
        if self._now_playing_msg:
            try:
                await self._now_playing_msg.edit(
                    embed=discord.Embed(title="⏹️ Stopped", color=discord.Color.dark_gray()),
                    view=None,
                )
            except Exception:
                pass
            self._now_playing_msg = None

    async def stop(self):
        self._stopped = True
        self._stop_watchdog()
        if self._recovery_task and not self._recovery_task.done():
            self._recovery_task.cancel()
            self._recovery_task = None
        self._recovery_attempts = 0
        await self._cleanup_current_file()
        await self._cleanup_np()
        self.loop_mode = "off"
        self.autoplay = False
        self._queue_history.clear()
        self._single_loop_track = None
        self._last_track_id = None
        self.queue.clear()
        self._clear_state()
        if self.vc:
            self.vc.stop()
            try:
                await self.vc.disconnect()
            except Exception:
                pass

    async def disconnect(self):
        self._stopped = True
        self._stop_watchdog()
        self._clear_state()
        self._cancel_alone_timer()
        if self._recovery_task and not self._recovery_task.done():
            self._recovery_task.cancel()
            self._recovery_task = None
        await self._cleanup_current_file()
        await self._cleanup_np()
        if self.vc:
            self.vc.stop()
            try:
                await self.vc.disconnect()
            except Exception:
                pass
