import asyncio
import os
import json
import re
import subprocess
import time
import shutil
import hashlib
import warnings
import logging
import glob
import random
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional
import aiohttp

from backend.utils.formatters import format_duration
import discord
import yt_dlp

logger = logging.getLogger("discord.bot.ytdlp")

# [AUDIT FIX 2] ThreadPool khusus agar eksekusi yt-dlp tidak memblokir Event Loop utama
_YTDLP_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ytdlp_worker")

# [OOM FIX] Batasi jumlah download simultan
_DOWNLOAD_SEMAPHORE = asyncio.Semaphore(2)

CACHE_DIR = "/tmp/discord_audio_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_COOKIES_DEFAULT = os.path.join(_PROJECT_ROOT, "cookies", "cookies.txt")

# Fitur QoL Railway: Bisa paste isi teks cookies Netscape langsung ke Environment Variable
_raw_cookies_env = os.getenv("YOUTUBE_COOKIES_TXT", "").strip()
if _raw_cookies_env:
    _tmp_cookie_path = "/tmp/youtube_cookies.txt"
    try:
        with open(_tmp_cookie_path, "w", encoding="utf-8") as _cf:
            _cf.write(_raw_cookies_env)
        COOKIES_FILE = _tmp_cookie_path
        logger.info("[YTDLP INIT] Berhasil menulis YOUTUBE_COOKIES_TXT ke /tmp/youtube_cookies.txt")
    except Exception as e:
        logger.error(f"[YTDLP INIT] Gagal menulis cookies env: {e}")
        COOKIES_FILE = os.getenv("COOKIES_FILE", _COOKIES_DEFAULT)
else:
    COOKIES_FILE = os.getenv("COOKIES_FILE", _COOKIES_DEFAULT)

COOKIES_FROM_BROWSER = os.getenv("COOKIES_FROM_BROWSER", "")
PO_TOKEN = os.getenv("YOUTUBE_PO_TOKEN", "")

logger.info(f"[YTDLP INIT] YOUTUBE_API_KEY={'SET' if os.getenv('YOUTUBE_API_KEY') else 'NOT SET'}")
logger.info(f"[YTDLP INIT] YOUTUBE_PO_TOKEN={'SET' if PO_TOKEN else 'NOT SET'}")
logger.info(f"[YTDLP INIT] Cookie File Terdeteksi={'YA' if os.path.isfile(COOKIES_FILE) else 'TIDAK'}")

_YTDLP_BASE = [
    "--retries", "3", "--fragment-retries", "3",
    "--add-header", "referer:youtube.com",
    "--add-header", "user-agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
]

if PO_TOKEN:
    _YTDLP_AUTH = ["--extractor-args", f"youtube:po_token=web+{PO_TOKEN};player_client=mweb,web"]
elif COOKIES_FROM_BROWSER:
    _YTDLP_AUTH = ["--cookies-from-browser", COOKIES_FROM_BROWSER]
elif os.path.isfile(COOKIES_FILE):
    _YTDLP_AUTH = ["--cookies", COOKIES_FILE, "--extractor-args", "youtube:player_client=mweb,web"]
else:
    _YTDLP_AUTH = ["--extractor-args", "youtube:player_client=mweb,web", "--throttled-rate", "100"]

YTDLP_AUTH_ARGS = _YTDLP_BASE + _YTDLP_AUTH

def _get_ytdlp_auth_opts() -> dict:
    # [AUDIT FIX 4] Memaksa koneksi IPv4 (0.0.0.0) agar tidak diblokir Datacenter Ban IPv6
    opts = {
        "retries": 3,
        "fragment_retries": 3,
        "throttledratelimit": 100,
        "source_address": "0.0.0.0"
    }
    if PO_TOKEN:
        opts["extractor_args"] = {"youtube": [f"po_token=web+{PO_TOKEN}", "player_client=mweb,web"]}
    elif COOKIES_FROM_BROWSER:
        opts["cookiefile"] = None
        opts["cookiesfrombrowser"] = (COOKIES_FROM_BROWSER,)
    elif os.path.isfile(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
        opts["extractor_args"] = {"youtube": ["player_client=mweb,web"]}
    else:
        opts["extractor_args"] = {"youtube": ["player_client=mweb,web"]}
    return opts

warnings.filterwarnings("ignore", message=".*line buffering.*binary mode.*")

def _find_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        logger.info(f"[FFMPEG] Found via shutil.which: {ffmpeg}")
        return ffmpeg

    common_paths = [
        "/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg.exe",
        r"C:\Program Files\KMPlayer 64X\LAVFilters64\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe", r"C:\ffmpeg\bin\ffmpeg.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
    ]
    for path in common_paths:
        if os.path.isfile(path):
            logger.info(f"[FFMPEG] Found via fallback path: {path}")
            return path

    logger.warning("[FFMPEG] ⚠️ ffmpeg tidak ditemukan di PATH. Musik mungkin tidak berfungsi.")
    return "ffmpeg"

FFMPEG_PATH = _find_ffmpeg()
_AUTH_OPTS = _get_ytdlp_auth_opts()

# [FIX 1] Format selector yang lebih robust dengan fallback chain
# bestaudio/best kadang fail karena YouTube serve format merged doang
YTDL_OPTS = {
    "format": "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best", 
    "quiet": True, 
    "no_warnings": True,
    "extract_flat": False, 
    "noplaylist": True, 
    "socket_timeout": 10,
    "retries": 1, 
    "proxy": os.getenv("YTDLP_PROXY"),
    **_AUTH_OPTS,
}

YTDL_SEARCH_OPTS = {
    "format": "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best", 
    "quiet": True, 
    "no_warnings": True,
    "default_search": "ytsearch", 
    "extract_flat": "in_playlist",
    "noplaylist": False, 
    "socket_timeout": 10, 
    "retries": 1, 
    "proxy": os.getenv("YTDLP_PROXY"),
    **_AUTH_OPTS,
}

YTDL_PLAYLIST_OPTS = {
    "quiet": True, "no_warnings": True, "extract_flat": "in_playlist",
    "skip_download": True, "dump_single_json": True, "socket_timeout": 10,
    "retries": 1, **_AUTH_OPTS,
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
            title=title, uri=uri, author=author, duration=duration,
            artwork=artwork, webpage_url=webpage_url, stream_url=stream_url,
            _ydl_info=info,
        )

    async def get_stream_url(self) -> str:
        if self.stream_url:
            return self.stream_url
        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(
                _YTDLP_EXECUTOR,
                lambda: yt_dlp.YoutubeDL(YTDL_OPTS).extract_info(self.webpage_url or self.uri, download=False)
            )
            url = info.get("url", "")
            self.stream_url = url
            return url
        except Exception as e:
            raise RuntimeError(f"Failed to get stream URL: {e}")

@dataclass
class YtDlpPlaylist:
    name: str
    tracks: list

async def _web_search_youtube(session, query: str) -> list:
    from urllib.parse import quote
    url = f"https://www.youtube.com/results?search_query={quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()
            ids = re.findall(r'/watch\?v=([a-zA-Z0-9_-]{11})', html)
            seen = set()
            unique = []
            for vid in ids:
                if vid not in seen:
                    seen.add(vid)
                    unique.append(f"https://youtube.com/watch?v={vid}")
                    if len(unique) >= 5:
                        break
            return unique
    except Exception as e:
        logger.warning(f"[WEB SCRAPE] Exception for q={query}: {e}")
    return []

class YtDlpSearcher:
    _cache: dict = {}
    _CACHE_TTL = 300

    @staticmethod
    def _parse_iso8601_duration(duration_str: str) -> int:
        if not duration_str:
            return 0
        match = re.match(r'PT?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return (hours * 3600 + minutes * 60 + seconds) * 1000

    @staticmethod
    def _yt_api_cache_path(query: str) -> str:
        h = hashlib.md5(query.encode()).hexdigest()
        return f"/tmp/yt_api_cache_{h}.json"

    @staticmethod
    def _yt_api_cache_read(query: str) -> Optional[list]:
        path = YtDlpSearcher._yt_api_cache_path(query)
        try:
            if os.path.isfile(path) and (time.time() - os.path.getmtime(path)) < 82800:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    tracks = [YtDlpTrack(**t) for t in data]
                    if tracks:
                        logger.info(f"[YT API CACHE] Cache hit for q={query} ({len(tracks)} tracks)")
                        return tracks
        except Exception:
            pass
        return None

    @staticmethod
    def _yt_api_cache_write(query: str, tracks: list):
        path = YtDlpSearcher._yt_api_cache_path(query)
        try:
            data = [{
                "title": t.title, "uri": t.uri, "author": t.author,
                "duration": t.duration, "artwork": t.artwork,
                "webpage_url": t.webpage_url or t.uri, "stream_url": t.stream_url
            } for t in tracks]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass

    @staticmethod
    async def _youtube_api_search(raw_query: str) -> list:
        api_key = os.getenv("YOUTUBE_API_KEY", "")
        if not api_key:
            return []

        cached = YtDlpSearcher._yt_api_cache_read(raw_query)
        if cached is not None:
            return cached

        try:
            session = aiohttp.ClientSession()
            try:
                params = {
                    "part": "snippet", "q": raw_query, "type": "video",
                    "maxResults": 5, "videoCategoryId": "10", "key": api_key,
                }
                async with session.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
            finally:
                await session.close()

            video_ids = []
            items = data.get("items", [])
            for item in items:
                vid = item.get("id", {}).get("videoId", "")
                if vid:
                    video_ids.append(vid)

            durations: dict = {}
            if video_ids:
                try:
                    session2 = aiohttp.ClientSession()
                    try:
                        params2 = {"part": "contentDetails", "id": ",".join(video_ids), "key": api_key}
                        async with session2.get("https://www.googleapis.com/youtube/v3/videos", params=params2, timeout=aiohttp.ClientTimeout(total=5)) as resp2:
                            if resp2.status == 200:
                                dur_data = await resp2.json()
                                for d_item in dur_data.get("items", []):
                                    dur_vid = d_item.get("id", "")
                                    content = d_item.get("contentDetails", {})
                                    if dur_vid:
                                        durations[dur_vid] = YtDlpSearcher._parse_iso8601_duration(content.get("duration", ""))
                    finally:
                        await session2.close()
                except Exception:
                    pass

            tracks = []
            for item in items:
                vid = item.get("id", {}).get("videoId", "")
                snippet = item.get("snippet", {})
                if not vid:
                    continue
                tracks.append(YtDlpTrack(
                    uri=f"https://www.youtube.com/watch?v={vid}",
                    title=snippet.get("title", "Unknown"),
                    author=snippet.get("channelTitle", "Unknown"),
                    duration=durations.get(vid, 0),
                    artwork=snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                    webpage_url=f"https://www.youtube.com/watch?v={vid}",
                ))
            YtDlpSearcher._yt_api_cache_write(raw_query, tracks)
            return tracks
        except Exception as e:
            logger.warning(f"[YT API] Exception for q={raw_query}: {e}")
            return []

    @staticmethod
    async def search(query: str) -> list:
        cache_key = f"search:{query}"
        cached = YtDlpSearcher._cache.get(cache_key)
        if cached and (time.time() - cached["ts"]) < YtDlpSearcher._CACHE_TTL:
            return cached["tracks"]

        if query.startswith("ytmsearch:"):
            actual_query = f"ytmsearch5:{query[len('ytmsearch:'):].strip()}"
        elif query.startswith("ytsearch:"):
            actual_query = f"ytsearch5:{query[len('ytsearch:'):].strip()}"
        else:
            actual_query = query

        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(
                _YTDLP_EXECUTOR,
                lambda: yt_dlp.YoutubeDL(YTDL_SEARCH_OPTS).extract_info(actual_query, download=False)
            )
        except Exception:
            info = None

        if info:
            entries = info.get("entries", [])
            if entries:
                tracks = [YtDlpTrack.from_info(e) for e in entries if e]
                if tracks:
                    YtDlpSearcher._cache[cache_key] = {"ts": time.time(), "tracks": tracks}
                    return tracks

        raw_query = query.split(":", 1)[-1].strip() if ":" in query else query
        tracks = await YtDlpSearcher._youtube_api_search(raw_query)
        if tracks:
            YtDlpSearcher._cache[cache_key] = {"ts": time.time(), "tracks": tracks}
        return tracks

    @staticmethod
    def _extract_video_id(url: str) -> Optional[str]:
        m = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})', url)
        return m.group(1) if m else None

    @staticmethod
    async def _yt_video_details(video_id: str) -> Optional[dict]:
        api_key = os.getenv("YOUTUBE_API_KEY", "")
        if not api_key:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                params = {"part": "snippet,contentDetails", "id": video_id, "key": api_key}
                async with session.get("https://www.googleapis.com/youtube/v3/videos", params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get("items", [])
                        if items:
                            snip = items[0].get("snippet", {})
                            cd = items[0].get("contentDetails", {})
                            return {
                                "title": snip.get("title", "Unknown"),
                                "author": snip.get("channelTitle", "Unknown"),
                                "duration": YtDlpSearcher._parse_iso8601_duration(cd.get("duration", "")),
                                "thumbnail": snip.get("thumbnails", {}).get("high", {}).get("url", ""),
                            }
        except Exception:
            pass
        return None

    @staticmethod
    async def extract_info(url: str) -> Optional[YtDlpTrack]:
        cache_key = f"info:{url}"
        cached = YtDlpSearcher._cache.get(cache_key)
        if cached and (time.time() - cached["ts"]) < YtDlpSearcher._CACHE_TTL:
            return cached["track"]

        loop = asyncio.get_event_loop()
        info = None
        try:
            info = await loop.run_in_executor(
                _YTDLP_EXECUTOR,
                lambda: yt_dlp.YoutubeDL(YTDL_OPTS).extract_info(url, download=False)
            )
        except Exception:
            pass

        if info:
            track = YtDlpTrack.from_info(info)
            YtDlpSearcher._cache[cache_key] = {"ts": time.time(), "track": track}
            return track

        vid = YtDlpSearcher._extract_video_id(url)
        if vid:
            details = await YtDlpSearcher._yt_video_details(vid)
            if details:
                track = YtDlpTrack(
                    title=details["title"], uri=url, author=details["author"],
                    duration=details["duration"], artwork=details["thumbnail"],
                    webpage_url=url,
                )
                YtDlpSearcher._cache[cache_key] = {"ts": time.time(), "track": track}
                return track
        return None

    @staticmethod
    async def extract_playlist(url: str) -> Optional[YtDlpPlaylist]:
        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(
                _YTDLP_EXECUTOR,
                lambda: yt_dlp.YoutubeDL(YTDL_PLAYLIST_OPTS).extract_info(url, download=False)
            )
        except Exception:
            return None

        if not info:
            return None

        entries = info.get("entries", [])
        return YtDlpPlaylist(
            name=info.get("title", "Unknown Playlist"),
            tracks=[YtDlpTrack.from_info(e) for e in entries if e]
        )


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
                await self.controller._now_playing_msg.edit(embed=self.controller._build_np_embed(), view=self)
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
        await self._ok(i, "⏭️ Skipped")

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
    def __init__(self, voice_client, text_channel=None, cog=None):
        self.vc = voice_client
        self.home = text_channel
        self._cog = cog
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
        self._state_file: str = "/tmp/discord_player_state.json"
        self._owner_id: Optional[int] = None
        self._playlist_url: Optional[str] = None
        self._playlist_tracks: list = []
        self._playlist_index: int = 0
        self._playlist_total: int = 0

    def set_owner(self, user_id: int):
        if self._owner_id is None:
            self._owner_id = user_id

    def is_owner(self, user_id: int) -> bool:
        return self._owner_id is not None and self._owner_id == user_id

    def _cache_path(self, url: str) -> str:
        h = hashlib.md5(url.encode()).hexdigest()
        return os.path.join(CACHE_DIR, f"{h}.opus")

    # [FIX 2] Download dengan multiple format fallback dan Cobalt API yang diperbaiki
    async def _download_track(self, url: str) -> Optional[str]:
        if not url or not isinstance(url, str) or not re.match(r'^https?://[^\s]+$', url):
            logger.error(f"[SECURITY] URL ditolak karena format mencurigakan: {url!r}")
            return None

        dest = self._cache_path(url)
        if os.path.isfile(dest):
            return dest

        async with _DOWNLOAD_SEMAPHORE:

            # [FIX 2a] Coba yt-dlp dengan format fallback chain
            format_attempts = [
                "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best",
                "bestaudio/best",
                "best",
            ]

            for fmt in format_attempts:
                try:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        _YTDLP_EXECUTOR,
                        lambda: subprocess.run(
                            ["yt-dlp", "-f", fmt, "-o", dest, "--no-part", "--no-progress", 
                             "--extract-audio", "--audio-format", "opus", url, *YTDLP_AUTH_ARGS],
                            capture_output=True, text=True, timeout=120,
                        )
                    )
                    if result.returncode == 0 and os.path.isfile(dest):
                        logger.info(f"[DOWNLOAD] yt-dlp sukses dengan format: {fmt}")
                        return dest
                    if result.returncode == 0:
                        prefix = dest.rsplit(".", 1)[0]
                        matches = glob.glob(prefix + ".*")
                        if matches:
                            os.rename(matches[0], dest)
                            if os.path.isfile(dest):
                                logger.info(f"[DOWNLOAD] yt-dlp sukses (renamed): {dest}")
                                return dest
                    if result.stderr:
                        logger.warning(f"[DOWNLOAD] yt-dlp format '{fmt}' stderr: {result.stderr[:200]}")
                except Exception as e:
                    logger.warning(f"[DOWNLOAD] yt-dlp format '{fmt}' exception: {e}")
                    continue

            # [FIX 2b] Fallback: download langsung stream URL dari yt-dlp tanpa extract audio
            logger.info(f"[DOWNLOAD] yt-dlp semua format gagal, coba fallback langsung stream...")
            try:
                loop = asyncio.get_event_loop()
                info = await loop.run_in_executor(
                    _YTDLP_EXECUTOR,
                    lambda: yt_dlp.YoutubeDL({
                        "quiet": True, "no_warnings": True,
                        "format": "bestaudio/best", "skip_download": True,
                        **_AUTH_OPTS,
                    }).extract_info(url, download=False)
                )
                direct_url = info.get("url") if info else None
                if direct_url:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(direct_url, timeout=aiohttp.ClientTimeout(total=120)) as sr:
                            if sr.status == 200:
                                with open(dest, "wb") as f:
                                    while True:
                                        chunk = await sr.content.read(65536)
                                        if not chunk:
                                            break
                                        f.write(chunk)
                                if os.path.isfile(dest):
                                    logger.info(f"[DOWNLOAD] Direct stream fallback sukses: {dest}")
                                    return dest
            except Exception as e:
                logger.warning(f"[DOWNLOAD] Direct stream fallback gagal: {e}")

            logger.error(f"[DOWNLOAD] SEMUA metode download gagal untuk {url}")
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
        return int((time.time() - self._start_time) * 1000)

    async def set_volume(self, vol: int):
        self._volume = max(0, min(1000, vol))
        if self.vc and self.vc.source and hasattr(self.vc.source, "volume"):
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
        embed.add_field(name="Progress", value=self._progress_bar(self.position, track.duration), inline=False)
        embed.add_field(name="In Queue", value=str(len(self.queue)), inline=True)
        embed.add_field(name="Autoplay", value="ON" if self.autoplay else "OFF", inline=True)
        embed.add_field(name="Loop", value={"single": "Single", "queue": "Queue Loop", "off": "OFF"}.get(self.loop_mode, "OFF"), inline=True)
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
        except (discord.NotFound, discord.Forbidden):
            self._now_playing_msg = None

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

    def _stop_watchdog(self):
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            self._watchdog_task = None

    async def _watchdog_loop(self, timeout: float):
        try:
            await asyncio.sleep(timeout)
            logger.warning(f"[WATCHDOG] Terdeteksi macet selama {timeout}s, memaksa skip lagu")
            if self.vc and self.vc.is_playing():
                self.vc.stop()
        except asyncio.CancelledError:
            pass

    def _start_watchdog(self, duration_ms: int):
        self._stop_watchdog()
        if duration_ms <= 0:
            return
        self._watchdog_task = asyncio.create_task(self._watchdog_loop((duration_ms / 1000) + 10))

    async def _sequential_preload(self):
        if _DOWNLOAD_SEMAPHORE.locked():
            return
        for track in list(self.queue[:3]):
            url = track.webpage_url or track.uri
            if not url or not re.match(r'^https?://[^\s]+$', url):
                continue
            dest = self._cache_path(url)
            if not os.path.isfile(dest):
                async with _DOWNLOAD_SEMAPHORE:
                    try:
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(
                            _YTDLP_EXECUTOR,
                            lambda u=url, d=dest: subprocess.run(
                                ["yt-dlp", "-f", "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best", 
                                 "-o", d, "--no-part", "--no-progress", "--extract-audio", "--audio-format", "opus", 
                                 u, *YTDLP_AUTH_ARGS],
                                capture_output=True, timeout=120,
                            )
                        )
                    except Exception:
                        pass

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

    async def _connection_recovery(self, target_channel, max_attempts=3):
        self._recovery_attempts += 1
        saved_track = self.current_track
        saved_position = self.position
        for attempt in range(max_attempts):
            try:
                logger.info(f"[RECOVERY] Mencoba koneksi ulang ({attempt + 1}/{max_attempts})")
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
                logger.warning(f"[RECOVERY] Percobaan {attempt + 1} gagal: {e}")
                await asyncio.sleep(2)
        self._recovery_attempts = 0
        await self._cleanup_np()

    def _save_state(self):
        if not self.current_track:
            return
        try:
            state = {
                "track": {
                    "title": self.current_track.title, "uri": self.current_track.webpage_url or self.current_track.uri,
                    "author": self.current_track.author, "duration": self.current_track.duration,
                    "artwork": self.current_track.artwork,
                },
                "position_ms": self.position, "paused": self._paused,
                "volume": self._volume, "loop_mode": self.loop_mode, "autoplay": self.autoplay,
                "queue": [
                    {"title": t.title, "uri": t.webpage_url or t.uri,
                     "author": t.author, "duration": t.duration, "artwork": t.artwork}
                    for t in self.queue[:20]
                ],
            }
            with open(self._state_file, "w") as f:
                json.dump(state, f)
        except Exception as e:
            logger.warning(f"[STATE SAVE ERROR] {e}")

    def _load_state(self) -> Optional[dict]:
        try:
            if os.path.isfile(self._state_file):
                with open(self._state_file) as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"[STATE LOAD ERROR] {e}")
        return None

    def _clear_state(self):
        try:
            if os.path.isfile(self._state_file):
                os.remove(self._state_file)
        except Exception:
            pass

    async def play(self, track: YtDlpTrack):
        if not track.artwork and (track.webpage_url or track.uri):
            enriched = await YtDlpSearcher.extract_info(track.webpage_url or track.uri)
            if enriched:
                track.artwork = enriched.artwork or track.artwork
                track.title = enriched.title or track.title
                if enriched.author != "Unknown":
                    track.author = enriched.author
                if enriched.duration:
                    track.duration = enriched.duration

        self.current_track = track
        self._single_loop_track = track

        if self.loop_mode == "queue" and track not in self._queue_history:
            self._queue_history.append(track)

        if self.vc.is_playing() or self.vc.is_paused():
            self.vc.stop()
            logger.info("[DEBUG PLAY] Menghentikan lagu sebelumnya.")

        url = track.webpage_url or track.uri
        if not url or not isinstance(url, str) or not url.startswith("http"):
            logger.error(f"[ERROR PLAY] URL tidak valid: {url!r}")
            await self._play_next()
            return

        file_path = self._preloaded_file if self._preloaded_for == url else None

        if file_path and os.path.isfile(file_path):
            logger.info(f"[DEBUG PLAY] Memakai file cache pre-load: {file_path}")
        else:
            logger.info(f"[DEBUG PLAY] Mulai mengunduh: {url}")
            file_path = await self._download_track(url)

        if not file_path or not os.path.isfile(file_path):
            logger.error(f"[ERROR PLAY] Gagal mengunduh berkas audio untuk {url}")
            await self._cleanup_current_file()
            await self._play_next()
            return

        self._current_file = file_path
        logger.info(f"[DEBUG PLAY] Menyiapkan audio stream: {file_path}")

        if not shutil.which("ffmpeg") and not os.path.isfile(FFMPEG_PATH):
            logger.critical(f"[CRITICAL] Mesin FFmpeg tidak ditemukan di {FFMPEG_PATH}")
            await self._cleanup_current_file()
            await self._play_next()
            return

        # [VOICE GUARD] Pastikan voice client masih terhubung
        if not self.vc or not self.vc.is_connected():
            logger.warning(f"[VOICE GUARD] Voice client tidak terhubung, mencoba reconnect...")
            if self.home and self.home.guild:
                for member_vc in self.home.guild.voice_channels:
                    if self.vc and self.vc.channel and self.vc.channel.id == member_vc.id:
                        try:
                            self.vc = await member_vc.connect(self_deaf=False)
                            logger.info("[VOICE GUARD] Reconnect sukses")
                        except Exception as e:
                            logger.error(f"[VOICE GUARD] Reconnect gagal: {e}")
                            await self._cleanup_current_file()
                            await self._play_next()
                            return
                        break
                else:
                    logger.error("[VOICE GUARD] Voice channel tidak ditemukan, skip")
                    await self._cleanup_current_file()
                    await self._play_next()
                    return
            else:
                logger.error("[VOICE GUARD] Tidak bisa reconnect (no guild/home)")
                await self._cleanup_current_file()
                await self._play_next()
                return

        try:
            source = discord.FFmpegPCMAudio(file_path, executable=FFMPEG_PATH)
            vol_source = discord.PCMVolumeTransformer(source, volume=self._volume / 100.0)

            self.vc.play(vol_source, after=self._on_track_end_wrapper)

            self._start_time = time.time()
            self._paused = False
            self._paused_position = 0.0
            self._pause_reason = "none"
            self._stopped = False
            self._start_watchdog(track.duration)
            asyncio.create_task(self._sequential_preload())
            await self._update_now_playing()
            self._start_np_updater()
            logger.info("[DEBUG PLAY] Pemutaran audio berhasil dimulai!")
        except Exception as e:
            logger.critical(f"[CRITICAL ERROR PLAY] FFmpeg gagal berputar: {e}")
            traceback.print_exc()
            await self._cleanup_current_file()
            if self.vc:
                try:
                    self.vc.stop()
                except Exception:
                    pass
            await self._play_next()

    async def _update_status(self, text: str):
        embed = discord.Embed(title=text, color=discord.Color.blue())
        try:
            if self._now_playing_msg:
                await self._now_playing_msg.edit(embed=embed)
            elif self.home:
                self._now_playing_msg = await self.home.send(embed=embed)
        except Exception:
            pass

    def _on_track_end_wrapper(self, error):
        if error:
            logger.error(f"[TRACK END ERROR] {error}")
        loop = self.vc.client.loop if (self.vc and hasattr(self.vc, "client") and self.vc.client) else asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(self._on_track_end(error), loop)

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
                if len(self.queue) < 5 and self._playlist_tracks and self._playlist_index < len(self._playlist_tracks):
                    asyncio.create_task(self._load_more_from_playlist())
                return
            if self._playlist_tracks and self._playlist_index < len(self._playlist_tracks):
                loaded = await self._load_more_from_playlist()
                if loaded > 0:
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
                    logger.warning(f"[AUTOPLAY ERROR] {e}")
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
        if not url or not re.match(r'^https?://[^\s]+$', url):
            return
        dest = self._cache_path(url)
        if os.path.isfile(dest):
            self._preloaded_file = dest
            self._preloaded_for = url
            return

        async with _DOWNLOAD_SEMAPHORE:
            format_attempts = [
                "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best",
                "bestaudio/best",
                "best",
            ]

            for fmt in format_attempts:
                try:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        _YTDLP_EXECUTOR,
                        lambda: subprocess.run(
                            ["yt-dlp", "-f", fmt, "-o", dest, "--no-part", "--no-progress", 
                             "--extract-audio", "--audio-format", "opus", url, *YTDLP_AUTH_ARGS],
                            capture_output=True, timeout=120,
                        )
                    )
                    if result.returncode == 0 and os.path.isfile(dest):
                        self._preloaded_file = dest
                        self._preloaded_for = url
                        return
                    if result.returncode == 0:
                        prefix = dest.rsplit(".", 1)[0]
                        matches = glob.glob(prefix + ".*")
                        if matches:
                            os.rename(matches[0], dest)
                            if os.path.isfile(dest):
                                self._preloaded_file = dest
                                self._preloaded_for = url
                                return
                except Exception:
                    continue

    async def _load_more_from_playlist(self, count: int = 50) -> int:
        if not self._cog or not self._playlist_tracks or self._playlist_index >= len(self._playlist_tracks):
            return 0
        batch = self._playlist_tracks[self._playlist_index:self._playlist_index + count]
        if not batch:
            return 0
        self._playlist_index += len(batch)
        sem = asyncio.Semaphore(15)
        results: list = []
        async def _search(rt):
            async with sem:
                r = await self._cog._search_single_resolved(rt)
                if r:
                    results.append(r)
        await asyncio.gather(*[_search(rt) for rt in batch])
        for r in results:
            self.queue.append(r)
        logger.info(f"[PLAYLIST AUTO] Berhasil memuat {len(results)} lagu tambahan ({self._playlist_index}/{len(self._playlist_tracks)})")
        return len(results)

    _GENRE_SEEDS = ["pop", "rock", "lofi", "electronic", "anime", "hip hop", "r&b", "jazz", "classical", "indie", "metal", "country", "folk", "blues", "reggae"]
    _AUTOPLAY_BAD_KEYWORDS = ["tutorial", "podcast", "unboxing", "interview", "review", "reaction", "asmr", "lecture", "speech", "commentary", "vlog", "gameplay", "let's play", "livestream", "stream"]

    async def _autoplay_search(self) -> Optional["YtDlpTrack"]:
        last = self._single_loop_track
        if not last:
            return None

        queries = []
        title_words = [w for w in (last.title or "").split() if len(w) > 3]
        if title_words:
            queries.append(f"ytmsearch:{last.author} {random.choice(title_words)}")

        queries.append(f"ytmsearch:{last.author} - {last.title}")

        title_lower = (last.title or "").lower()
        author_lower = (last.author or "").lower()
        matched = [g for g in self._GENRE_SEEDS if g in title_lower or g in author_lower]
        queries.append(f"ytmsearch:{random.choice(matched if matched else self._GENRE_SEEDS)} music")

        random.shuffle(queries)

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
                if any(bad in (r.title or "").lower() for bad in self._AUTOPLAY_BAD_KEYWORDS):
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
            source = discord.FFmpegPCMAudio(file_path, executable=FFMPEG_PATH, before_options=f"-ss {position_sec} -noaccurate_seek")
            vol_source = discord.PCMVolumeTransformer(source, volume=self._volume / 100.0)
            self.vc.play(vol_source, after=self._on_track_end_wrapper)
            self._start_time = time.time() - position_sec
            self._paused = False
            self._pause_reason = "none"
            self._start_watchdog(self.current_track.duration if self.current_track else 0)
            await self._update_now_playing()
            self._start_np_updater()
        except Exception as e:
            logger.error(f"[SEEK ERROR] {e}")

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
                await self._now_playing_msg.edit(embed=discord.Embed(title="⏹️ Stopped", color=discord.Color.dark_gray()), view=None)
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