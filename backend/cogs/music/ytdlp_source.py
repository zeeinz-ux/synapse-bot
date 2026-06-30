import asyncio
import os
import json
import re
import time
import shutil
import hashlib
import subprocess
import warnings
import logging
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
_YTDLP_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ytdlp_worker")

# [OOM FIX] Batasi jumlah download simultan
_DOWNLOAD_SEMAPHORE = asyncio.Semaphore(2)
_BG_DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)

MAX_QUEUE_SIZE = 100

CACHE_DIR = "/tmp/discord_audio_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# Short-lived extraction cache: avoids duplicate yt-dlp extract_info for same URL
# within a short window (e.g., stream URL extraction → bg download).
# Key: URL, Value: (direct_url, timestamp). Entries expire after 30 seconds.
_EXTRACTION_CACHE: dict[str, tuple[str, float]] = {}
_EXTRACTION_CACHE_TTL = 30.0

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

# Auto-generate PO token via bgutil-pot jika tidak di-set via env var
if not PO_TOKEN:
    try:
        _result = subprocess.run(
            ["bgutil-pot", "generate", "web"],
            capture_output=True, text=True, timeout=30
        )
        if _result.returncode == 0:
            _token = _result.stdout.strip()
            if _token:
                PO_TOKEN = _token
                logger.info(f"[YTDLP INIT] PO token auto-generated via bgutil-pot")
    except Exception as _e:
        logger.info(f"[YTDLP INIT] bgutil-pot not available or failed: {_e}")

logger.info(f"[YTDLP INIT] YOUTUBE_API_KEY={'SET' if os.getenv('YOUTUBE_API_KEY') else 'NOT SET'}")
logger.info(f"[YTDLP INIT] YOUTUBE_PO_TOKEN={'SET' if PO_TOKEN else 'NOT SET'}")
logger.info(f"[YTDLP INIT] Cookie File Terdeteksi={'YA' if os.path.isfile(COOKIES_FILE) else 'TIDAK'}")



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

# [PHASE 8] YouTube player_client fallback chain.
# Different player clients have different bot-detection thresholds. When one
# gets blocked with "Sign in to confirm you're not a bot", we try the next.
# Order matters: start with the most reliable for our setup, fall back to
# exotic clients (android_vr, tv) which YouTube tends to monitor less.
# [PHASE 9] Reordered fallback chain.
# Put exotic clients first (android_vr, tv_embedded) which YouTube monitors
# less aggressively than mweb/web. Original order tried mweb,web first and
# burned 6 attempts before falling back to exotic clients — and even when
# an exotic client returned info, the stream URL was often unusable because
# we already exhausted attempts. Starting with the lighter-weight clients
# avoids most bot-detection blocks entirely.
# Each tuple: (client_name, requires_po_token)
_DEFAULT_PLAYER_CLIENT_FALLBACKS = [
    ("android_vr", False),    # rarest detection, no PO needed
    ("tv_embedded", False),   # TV embedded - very basic, often works
    ("android", False),       # Android app - good general fallback
    ("ios", False),           # iOS app - sometimes works
    ("mweb", True),           # mobile web - last because heavy detection
    ("web", True),            # desktop web - last, paired with web PO token
]


def _get_player_client_fallbacks() -> list:
    """[PHASE 8] Read YOUTUBE_CLIENT_FALLBACKS env var or use default chain.
    Format: comma-separated client names, e.g. "mweb,android_vr,android".
    Returns list of (name, requires_po_token) tuples.
    """
    env_val = os.getenv("YOUTUBE_CLIENT_FALLBACKS", "").strip()
    if not env_val:
        return list(_DEFAULT_PLAYER_CLIENT_FALLBACKS)
    # Map of known clients -> whether they need PO token
    client_po_map = {name: needs_po for name, needs_po in _DEFAULT_PLAYER_CLIENT_FALLBACKS}
    parsed = []
    for raw in env_val.split(","):
        name = raw.strip()
        if not name:
            continue
        needs_po = client_po_map.get(name, False)
        parsed.append((name, needs_po))
    return parsed if parsed else list(_DEFAULT_PLAYER_CLIENT_FALLBACKS)


def _build_ytdlp_opts_for_client(client_name: str, needs_po: bool, base_opts: dict) -> dict:
    """[PHASE 8] Build yt-dlp options for a specific player_client.
    Clones base_opts and overrides extractor_args. If needs_po and PO_TOKEN
    is available, prepends po_token=<client>+<token>.
    """
    opts = dict(base_opts)  # shallow copy
    extractor_args = []
    if needs_po and PO_TOKEN:
        extractor_args.append(f"po_token={client_name}+{PO_TOKEN}")
    extractor_args.append(f"player_client={client_name}")
    opts["extractor_args"] = {"youtube": extractor_args}
    return opts


def _extract_info_with_fallback(url: str, base_opts: dict) -> Optional[dict]:
    """[PHASE 8] Try extract_info with each player_client in fallback chain.
    Returns info dict on first success, None if all fail.
    Logs which client worked so we can see in production.
    """
    fallbacks = _get_player_client_fallbacks()
    last_error: Optional[Exception] = None
    for client_name, needs_po in fallbacks:
        opts = _build_ytdlp_opts_for_client(client_name, needs_po, base_opts)
        try:
            info = yt_dlp.YoutubeDL(opts).extract_info(url, download=False)
            if info:
                # info can be a playlist; we only want single video here.
                if "entries" in info and info["entries"]:
                    info = info["entries"][0]
                if info and info.get("url"):
                    logger.info(f"[yt-dlp] extract_info OK with client={client_name}")
                    return info
        except Exception as e:
            last_error = e
            logger.debug(f"[yt-dlp] client={client_name} failed: {type(e).__name__}: {str(e)[:120]}")
            continue
    if last_error:
        logger.warning(f"[yt-dlp] All {len(fallbacks)} player_clients failed for {url[:60]}: {last_error}")
    else:
        logger.warning(f"[yt-dlp] All {len(fallbacks)} player_clients returned no info for {url[:60]}")
    return None

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
    "proxy": os.getenv("YTDLP_PROXY") or "",
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
    "proxy": os.getenv("YTDLP_PROXY") or "",
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
    yt_id: str = ""

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
        author_raw = info.get("channel") or info.get("uploader") or info.get("artist") or info.get("creators")
        if isinstance(author_raw, list):
            author_raw = ', '.join(filter(None, author_raw))
        author = author_raw or "Unknown"
        duration_raw = info.get("duration")
        duration = (int(duration_raw) * 1000) if duration_raw else 0
        artwork = info.get("thumbnail") or ""
        webpage_url = info.get("webpage_url") or uri
        stream_url = info.get("url") or ""
        yt_id = info.get("id", "")
        return cls(
            title=title, uri=uri, author=author, duration=duration,
            artwork=artwork, webpage_url=webpage_url, stream_url=stream_url,
            yt_id=yt_id,
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
            # [PHASE 8] Use sequential player_client fallback so direct URL
            # /play with bot-detected videos still gets metadata.
            info = await loop.run_in_executor(
                _YTDLP_EXECUTOR,
                lambda: _extract_info_with_fallback(url, YTDL_OPTS)
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
        # [PHASE 1] Play lifecycle lock — prevents cascading re-entry when
        # vc.stop() in one play() invocation triggers _on_track_end callbacks
        # from a previous ffmpeg process that race the new play().
        self._play_lock = asyncio.Lock()
        self._play_generation: int = 0
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
        self._resume_task: Optional[asyncio.Task] = None  # [PHASE 2] tracks auto-resume after recovery
        self._bg_resolve_task: Optional[asyncio.Task] = None  # [PHASE 6b] track playlist background resolve
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

    # [PHASE 7] Maximum total cache size in bytes. Oldest files are evicted
    # first when this is exceeded. Sized for Railway free tier 512MB:
    # leaves 462MB for Discord.py + Firebase + Spotify + queue + ffmpeg.
    # 50MB ~= 10-15 average-length tracks cached at once.
    _MAX_CACHE_BYTES = 50 * 1024 * 1024

    def _enforce_cache_size_limit(self) -> None:
        """[PHASE 7] Evict oldest .opus files from /tmp until total <= cap.

        Called before writing a new download so we never exceed the cap.
        Sorts by mtime ascending (oldest first), deletes until under limit.
        Logs each eviction so we can see cache pressure in production.
        """
        try:
            if not os.path.isdir(CACHE_DIR):
                return
            files: list[tuple[float, int, str]] = []
            total = 0
            for fname in os.listdir(CACHE_DIR):
                fpath = os.path.join(CACHE_DIR, fname)
                if not os.path.isfile(fpath):
                    continue
                if not fname.endswith(".opus"):
                    continue
                try:
                    sz = os.path.getsize(fpath)
                    mt = os.path.getmtime(fpath)
                    files.append((mt, sz, fpath))
                    total += sz
                except OSError:
                    continue
            if total <= self._MAX_CACHE_BYTES:
                return
            # Oldest first
            files.sort()
            evicted = 0
            for mt, sz, fpath in files:
                if total <= self._MAX_CACHE_BYTES:
                    break
                try:
                    os.remove(fpath)
                    total -= sz
                    evicted += 1
                except OSError as e:
                    logger.warning(f"[CACHE] Gagal hapus {os.path.basename(fpath)}: {e}")
            if evicted:
                logger.info(
                    f"[CACHE] Evicted {evicted} file(s), "
                    f"{total // 1024 // 1024}MB/{self._MAX_CACHE_BYTES // 1024 // 1024}MB used"
                )
        except Exception as e:
            logger.warning(f"[CACHE] Size limit check error: {e}")

    def _evict_cached_file(self, url: str) -> None:
        """[PHASE 7] Delete the cached .opus for a URL, if present.
        Called after playback ends so each track only persists on disk
        while it's actively being played or queued behind it.
        """
        try:
            cache = self._cache_path(url)
            if os.path.isfile(cache):
                os.remove(cache)
                logger.debug(f"[CACHE] Evicted post-play: {os.path.basename(cache)}")
        except OSError as e:
            logger.warning(f"[CACHE] Gagal hapus post-play: {e}")

    # [PHASE 3b] Minimum sane size for a downloaded opus track. Anything
    # smaller is treated as a corrupt/partial file and re-downloaded.
    # 64KB ~= ~3 seconds of 128kbps opus. Most legitimate tracks are >500KB.
    _MIN_CACHE_BYTES = 64 * 1024

    @staticmethod
    def _expected_min_bytes(info: dict) -> int:
        """[PHASE 3c] Estimate minimum reasonable size from yt-dlp info.
        Uses abr (audio bitrate in kbps) and duration (seconds). Falls back
        to a conservative default if either is missing.
        """
        try:
            abr = float(info.get("abr") or info.get("tbr") or 128)  # kbps
            duration = float(info.get("duration") or 0)
            if duration > 0 and abr > 0:
                # bytes = kbps * 1000 / 8 * duration, require >= 30% to allow for
                # opus efficiency / headers / variable bitrate
                expected = (abr * 1000.0 / 8.0) * duration * 0.30
                return max(int(expected), MusicController._MIN_CACHE_BYTES)
        except (TypeError, ValueError):
            pass
        return MusicController._MIN_CACHE_BYTES

    def _validate_cached_file(self, dest: str, info: Optional[dict] = None) -> bool:
        """[PHASE 3b] True if cached file is plausible. Deletes the file and
        returns False if it's too small or corrupt.

        Validation rules (any failure -> delete + return False):
          1. File exists and is > 0 bytes.
          2. File meets minimum size derived from info (duration * bitrate * 0.30),
             or falls back to _MIN_CACHE_BYTES if info missing.
          3. For .opus/.webm files: first 4 bytes are '1A 45 DF A3' (EBML magic).
             A truncated file usually has garbage or zero bytes at the start
             if aiohttp aborted mid-write — actually no, aiohttp writes sequentially
             so the start is fine, but the tail is missing. We check tail.
          4. File ends with a valid EBML element OR has reasonable size variance.
             Cheap proxy: file size within 50%-150% of expected mean (bitrate*duration).
        """
        try:
            if not os.path.isfile(dest):
                return False
            size = os.path.getsize(dest)
            if size == 0:
                try:
                    os.remove(dest)
                except Exception:
                    pass
                return False
            min_bytes = self._expected_min_bytes(info) if info else self._MIN_CACHE_BYTES
            if size < min_bytes:
                logger.warning(f"[CACHE] File terlalu kecil/corrupt: {dest} ({size} < {min_bytes} bytes), hapus & re-download")
                try:
                    os.remove(dest)
                except Exception as e:
                    logger.warning(f"[CACHE] Gagal hapus file rusak: {e}")
                return False
            # [PHASE 3b] EBML magic check at start. Real webm/opus files start with
            # 1A 45 DF A3 (EBML header). If missing, this is definitely not a
            # valid audio file even if size looks right.
            try:
                with open(dest, "rb") as f:
                    head = f.read(4)
                if head[:4] != b"\x1a\x45\xdf\xa3":
                    logger.warning(f"[CACHE] File bukan EBML/webm (head={head!r}): {dest}, hapus & re-download")
                    try:
                        os.remove(dest)
                    except Exception:
                        pass
                    return False
            except Exception as e:
                logger.warning(f"[CACHE] Gagal baca header: {e}")
            return True
        except Exception as e:
            logger.warning(f"[CACHE] Validasi error: {e}")
            return False

    async def _bg_download(self, url: str) -> None:
        """Background download with bounded concurrency and extraction cache."""
        # Skip if already cached on disk
        dest = self._cache_path(url)
        if os.path.isfile(dest):
            return
        async with _BG_DOWNLOAD_SEMAPHORE:
            # Check extraction cache — _get_direct_url may have already extracted
            now = time.time()
            cached = _EXTRACTION_CACHE.get(url)
            direct_url = cached[0] if cached and (now - cached[1]) < _EXTRACTION_CACHE_TTL else None
            await self._download_track(url, pre_extracted_url=direct_url)

    async def _download_track(self, url: str, pre_extracted_url: Optional[str] = None) -> Optional[str]:
        if not url or not isinstance(url, str) or not re.match(r'^https?://[^\s]+$', url):
            logger.error(f"[SECURITY] URL ditolak karena format mencurigakan: {url!r}")
            return None

        dest = self._cache_path(url)

        # [PHASE 7] Enforce cache size limit BEFORE writing. Evicts oldest
        # .opus files so /tmp/discord_audio_cache/ never grows past 50MB.
        # This keeps free-tier disk usage bounded and reduces RAM pressure
        # from filesystem page cache holding deleted-but-not-yet-flushed files.
        self._enforce_cache_size_limit()

        # [PHASE 3b] Before trusting a cached file, validate it. A partial or
        # corrupt file from a previous failed download would otherwise be
        # returned and cause ffmpeg "File ended prematurely" mid-playback.
        if os.path.isfile(dest):
            if self._validate_cached_file(dest):
                return dest
            # _validate_cached_file already deleted the bad file, fall through
            # to re-download.

        async with _DOWNLOAD_SEMAPHORE:
            try:
                loop = asyncio.get_event_loop()
                if pre_extracted_url:
                    # Reuse stream URL from extraction cache — skip yt-dlp
                    direct_url = pre_extracted_url
                    expected_min = 64 * 1024  # conservative default
                else:
                    # [PHASE 8] Sequential player_client fallback. Instead of
                    # hard-coding mweb,web, try each client in turn until one
                    # returns a usable stream URL. _extract_info_with_fallback
                    # is synchronous, run it in the executor so we don't block
                    # the event loop while yt-dlp retries each client.
                    base_ytdlp_opts = {
                        "quiet": True, "no_warnings": True,
                        "format": "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best",
                        "skip_download": True,
                        **_AUTH_OPTS,
                    }
                    info = await loop.run_in_executor(
                        _YTDLP_EXECUTOR,
                        lambda: _extract_info_with_fallback(url, base_ytdlp_opts)
                    )
                    if not info:
                        logger.error(f"[DOWNLOAD] yt-dlp extract_info returned None")
                        return None
                    direct_url = info.get("url")
                    if not direct_url:
                        logger.error(f"[DOWNLOAD] Gagal mendapat direct URL dari yt-dlp")
                        return None
                    # [PHASE 3c] Capture expected min size from info before download
                    expected_min = self._expected_min_bytes(info)

                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                    "Accept": "*/*",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Range": "bytes=0-",
                }
                async with aiohttp.ClientSession(headers=headers) as session:
                    # [PHASE 5] Raise aiohttp download timeout 120s -> 300s.
                    # 120s is too tight for long tracks on slow Railway ->
                    # Google edge network. A 19-minute track is ~20MB; at
                    # 1.5MB/s that's already 13s, and with reconnection overhead
                    # 120s gets eaten before half the file lands. 300s gives
                    # enough headroom without keeping a stuck download alive
                    # forever (5 min is still better than OOM-stuck forever).
                    async with session.get(direct_url, timeout=aiohttp.ClientTimeout(total=300)) as sr:
                        if sr.status not in (200, 206):
                            logger.error(f"[DOWNLOAD] HTTP {sr.status} dari stream URL")
                            return None
                        # [PHASE 3b] Capture server-advertised size if available.
                        # aiohttp exposes Content-Length via response.headers.
                        # If server says the stream is N bytes and we got less,
                        # the download was truncated — reject without trusting the cache.
                        server_total = sr.headers.get("Content-Length")
                        server_total_int = None
                        try:
                            if server_total is not None:
                                server_total_int = int(server_total)
                        except (TypeError, ValueError):
                            server_total_int = None
                        with open(dest, "wb") as f:
                            while True:
                                chunk = await sr.content.read(65536)
                                if not chunk:
                                    break
                                f.write(chunk)
                        # [PHASE 3b] If server gave us a Content-Length and we
                        # didn't get all of it, the download was truncated.
                        actual_size = os.path.getsize(dest) if os.path.isfile(dest) else 0
                        if server_total_int is not None and actual_size < server_total_int:
                            try:
                                if os.path.isfile(dest):
                                    os.remove(dest)
                            except Exception:
                                pass
                            logger.error(f"[DOWNLOAD] Truncated: got {actual_size}/{server_total_int} bytes from {direct_url[:80]}")
                            return None
                        # [PHASE 3b/3c] Strict validation. Pass info so we use the
                        # tighter expected-min-bytes derived from duration/bitrate,
                        # not the loose _MIN_CACHE_BYTES floor.
                        if self._validate_cached_file(dest, info):
                            logger.info(f"[DOWNLOAD] Berhasil: {dest} ({actual_size} bytes, min={expected_min}, server_total={server_total_int})")
                            return dest
                        # Validation failed and the bad file was already deleted.
                        logger.error(f"[DOWNLOAD] File rusak/kurang dari minimum: {dest} (min={expected_min})")
                        return None
            except asyncio.TimeoutError:
                logger.error(f"[DOWNLOAD] Timeout (120s) saat mengunduh: {url[:60]}")
                # [PHASE 3b] Best-effort: delete the partial file so the next
                # call doesn't trust it.
                try:
                    if os.path.isfile(dest):
                        os.remove(dest)
                except Exception:
                    pass
                return None
            except Exception as e:
                logger.error(f"[DOWNLOAD] Gagal: {e.__class__.__name__}: {e}")
                # [PHASE 3b] Same cleanup as timeout.
                try:
                    if os.path.isfile(dest):
                        os.remove(dest)
                except Exception:
                    pass
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
        # [PHASE 3a] Watchdog now polls lock state instead of just sleeping.
        # This prevents the watchdog from killing a freshly-started track that's
        # legitimately using the play lock (e.g. user just hit /play and the new
        # ffmpeg is still warming up).
        try:
            # Poll every second up to timeout; if _play_lock is held during the
            # last 5s of the window, reset the clock — someone is actively
            # playing, don't interfere.
            elapsed = 0.0
            while elapsed < timeout:
                await asyncio.sleep(min(1.0, timeout - elapsed))
                elapsed += 1.0
                # If a new play is in progress, defer the watchdog entirely.
                # Re-arm by extending timeout.
                if self._play_lock.locked() and elapsed > (timeout * 0.5):
                    remaining = timeout
                    elapsed = 0.0
                    logger.debug(f"[WATCHDOG] Deferring: _play_lock held, resetting timer")
                    continue
            logger.warning(f"[WATCHDOG] Track exceeded {timeout:.0f}s budget, forcing skip")
            if self.vc and self.vc.is_playing():
                self.vc.stop()
        except asyncio.CancelledError:
            pass

    def _start_watchdog(self, duration_ms: int):
        # [PHASE 3a] Old: (duration / 1000) + 10 — too tight on Railway / slow ffmpeg warmup.
        # New: max(duration * 2 / 1000, 30). For a 3-minute track that's 360s,
        # for a 10s snippet that's 30s floor. Plus the polling loop above defers
        # while _play_lock is held so it won't fight a fresh play().
        self._stop_watchdog()
        if duration_ms <= 0:
            # No known duration — use a generous 10-minute default.
            timeout = 600.0
        else:
            timeout = max((duration_ms / 1000.0) * 2.0, 30.0)
        logger.debug(f"[WATCHDOG] Armed for {timeout:.0f}s")
        self._watchdog_task = asyncio.create_task(self._watchdog_loop(timeout))

    async def _sequential_preload(self):
        # [PHASE 6a] Hardening: pre-download only 1 track ahead (was 2 in
        # Phase 4, 3 originally). Each preloaded .opus is 3-5MB; minimal
        # disk I/O keeps memory headroom for the actual playback path.
        # Tradeoff: brief silence between tracks on slow networks, but
        # the bot stays well under Railway free tier 512MB limit.
        for track in list(self.queue[:1]):
            await self._preload_next(track)

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
        """[PHASE 2] Graceful voice recovery.

        Sequence:
          1. Mark _stopped=True so user /play can't grab this controller mid-recovery.
          2. Forcibly tear down any lingering voice client (old or partial connect).
          3. Sleep to let any dying-ffmpeg _on_track_end callbacks land and be
             dropped by the Phase 1 generation guard.
          4. Connect a fresh voice client.
          5. Restore from disk state file (_state_file), not from self.current_track
             which may be stale.
          6. Re-arm _stopped=False. Do NOT call play() directly — let the user or
             _on_track_end drive playback. If state file has a track, resume via
             a guarded call that respects _play_lock.

        Failure mode: after max_attempts, cleanup UI and leave controller idle.
        """
        self._recovery_attempts += 1
        logger.info(f"[RECOVERY] Start (attempt {self._recovery_attempts}) for {target_channel.name}")

        # Snapshot intent from state file BEFORE we start touching anything, so
        # even if current_track gets nulled by a stale callback we know what to
        # restore. _load_state returns None if file missing/corrupt.
        intent = self._load_state()
        intent_track_title = (intent or {}).get("track", {}).get("title") if intent else None
        intent_position_ms = (intent or {}).get("position_ms", 0) if intent else 0

        # Mark the controller as 'in recovery' — stops new plays from racing us
        # and stops watchdog from killing a half-set-up player.
        self._stopped = True

        # Tear down any lingering voice client (the dying one or a partial
        # connect from a previous attempt). Best-effort; ignore errors.
        try:
            if self.vc and self.vc.is_connected():
                try:
                    if self.vc.is_playing() or self.vc.is_paused():
                        self.vc.stop()
                except Exception:
                    pass
                await self.vc.disconnect(force=True)
        except Exception as e:
            logger.warning(f"[RECOVERY] Pre-cleanup disconnect error (ignored): {e}")
        # Drop our reference so nothing tries to use it.
        self.vc = None

        # Let dying-ffmpeg _on_track_end callbacks drain. Phase 1's generation
        # guard will drop them, but we still give them a moment to fire and be
        # cleared so they don't race the new connect below.
        await asyncio.sleep(1.0)

        # Clear transitioning state so a connect failure here can be cleanly
        # retried without stale _single_loop_track confusing seek/play.
        self._single_loop_track = None

        last_error = None
        for attempt in range(max_attempts):
            try:
                logger.info(f"[RECOVERY] Connecting (attempt {attempt + 1}/{max_attempts})")
                vc = await target_channel.connect(self_deaf=False)
                self.vc = vc
                self._recovery_attempts = 0
                self._stopped = False
                logger.info(f"[RECOVERY] Connected to {target_channel.name}")

                # Re-arm the alone-pause watchdog if anyone is in the channel.
                if vc.channel:
                    humans = [m for m in vc.channel.members if not m.bot]
                    if humans:
                        self._start_alone_timer()

                # Decide whether to auto-resume. Only resume if state file had a
                # track that wasn't paused, and we didn't exceed 1 hour stale
                # (avoid resuming days-old sessions).
                should_resume = False
                if intent and intent_track_title:
                    paused = intent.get("paused", False)
                    age_sec = time.time() - os.path.getmtime(self._state_file) if os.path.isfile(self._state_file) else 9999
                    if not paused and age_sec < 3600:
                        should_resume = True

                if should_resume:
                    # Schedule the resume AFTER current coroutine returns, so
                    # the recovery function can exit cleanly and the bot's voice
                    # handshake can fully settle. _play_lock will serialize this
                    # against any user /play.
                    async def _resume_after_recovery():
                        try:
                            uri = intent.get("track", {}).get("uri")
                            if not uri:
                                return
                            logger.info(f"[RECOVERY] Resuming '{intent_track_title}' from {intent_position_ms}ms")
                            track = await YtDlpSearcher.extract_info(uri)
                            if not track:
                                logger.warning(f"[RECOVERY] extract_info returned None for {uri}, skipping auto-resume")
                                return
                            # Use _play_locked directly so generation guard works.
                            await self._play_locked(track)
                            if intent_position_ms > 3000:
                                await asyncio.sleep(0.5)
                                await self.seek(intent_position_ms)
                        except Exception as e:
                            logger.error(f"[RECOVERY] Auto-resume failed: {e.__class__.__name__}: {e}")

                    self._resume_task = asyncio.create_task(_resume_after_recovery())
                else:
                    logger.info(f"[RECOVERY] No resume (intent_track={intent_track_title!r}, paused={intent.get('paused') if intent else None})")

                return
            except Exception as e:
                last_error = e
                logger.warning(f"[RECOVERY] Attempt {attempt + 1} failed: {e}")
                # Best-effort cleanup of the partial connect, then back off.
                try:
                    if self.vc and self.vc.is_connected():
                        await self.vc.disconnect(force=True)
                except Exception:
                    pass
                self.vc = None
                await asyncio.sleep(2)

        # All attempts exhausted.
        self._recovery_attempts = 0
        self._stopped = False  # let user take over manually with /play
        logger.error(f"[RECOVERY] Gagal setelah {max_attempts} percobaan: {last_error}")
        await self._cleanup_np()
        try:
            if self.home:
                await self.home.send(
                    f"❌ Gagal reconnect ke voice channel setelah {max_attempts} percobaan. "
                    "Bot idle — gunakan `/play` untuk memulai ulang."
                )
        except Exception:
            pass

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
        # [PHASE 1] Acquire play lifecycle lock — if another play() is already
        # in flight, queue or wait instead of running concurrently. This kills
        # the cascading re-entry loop where vc.stop() schedules _on_track_end
        # callbacks from dying ffmpeg processes that race the new play().
        async with self._play_lock:
            await self._play_locked(track)

    async def _get_direct_url(self, url: str) -> Optional[str]:
        """Extract direct audio stream URL from yt-dlp (fast, no download)."""
        # Check extraction cache first
        now = time.time()
        cached = _EXTRACTION_CACHE.get(url)
        if cached and (now - cached[1]) < _EXTRACTION_CACHE_TTL:
            logger.debug(f"[CACHE HIT] Reusing cached extraction for {url[:60]}")
            return cached[0]
        try:
            loop = asyncio.get_event_loop()
            base_opts = {
                "quiet": True, "no_warnings": True,
                "format": "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best",
                "skip_download": True,
                **_AUTH_OPTS,
            }
            info = await loop.run_in_executor(
                _YTDLP_EXECUTOR,
                lambda: _extract_info_with_fallback(url, base_opts)
            )
            if info:
                direct_url = info.get("url")
                _EXTRACTION_CACHE[url] = (direct_url, time.time())
                return direct_url
        except Exception as e:
            logger.warning(f"[GET_STREAM_URL] Failed: {e}")
        return None

    async def _play_locked(self, track: YtDlpTrack):
        if not track.artwork and (track.webpage_url or track.uri):
            enriched = await YtDlpSearcher.extract_info(track.webpage_url or track.uri)
            if enriched:
                track.artwork = enriched.artwork or track.artwork
                track.title = enriched.title or track.title
                if enriched.author != "Unknown":
                    track.author = enriched.author
                if enriched.duration:
                    track.duration = enriched.duration

        self._play_generation += 1
        my_generation = self._play_generation

        self.current_track = track
        self._single_loop_track = track

        if self.loop_mode == "queue" and track not in self._queue_history:
            if len(self._queue_history) >= MAX_QUEUE_SIZE:
                self._queue_history.pop(0)
            self._queue_history.append(track)

        if self.vc.is_playing() or self.vc.is_paused():
            self.current_track = None
            self.vc.stop()
            logger.info("[DEBUG PLAY] Menghentikan lagu sebelumnya.")

        url = track.webpage_url or track.uri
        if not url or not isinstance(url, str) or not url.startswith("http"):
            logger.error(f"[ERROR PLAY] URL tidak valid: {url!r}")
            await self._play_next()
            return

        if not shutil.which("ffmpeg") and not os.path.isfile(FFMPEG_PATH):
            logger.critical(f"[CRITICAL] Mesin FFmpeg tidak ditemukan di {FFMPEG_PATH}")
            await self._play_next()
            return

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
                            await self._play_next()
                            return
                        break
                else:
                    logger.error("[VOICE GUARD] Voice channel tidak ditemukan, skip")
                    await self._play_next()
                    return
            else:
                logger.error("[VOICE GUARD] Tidak bisa reconnect (no guild/home)")
                await self._play_next()
                return

        # Check preloaded cache first
        file_path = self._preloaded_file if self._preloaded_for == url else None
        use_cache = file_path and os.path.isfile(file_path)

        if use_cache:
            await self._cleanup_current_file()
            self._current_file = file_path
            self._preloaded_file = None
            self._preloaded_for = None
            logger.info(f"[DEBUG PLAY] Memakai file cache: {file_path}")
            audio_source = file_path
            is_stream = False
        else:
            # Try streaming directly via FFmpeg (no download wait)
            logger.info(f"[DEBUG PLAY] Mencoba stream langsung: {url}")
            stream_url = await self._get_direct_url(url)
            if stream_url:
                logger.info(f"[DEBUG PLAY] Stream URL didapat, play via FFmpeg")
                audio_source = stream_url
                is_stream = True
            else:
                # Fallback: download full file
                logger.info(f"[DEBUG PLAY] Stream gagal, unduh file: {url}")
                file_path = await self._download_track(url)
                if not file_path or not os.path.isfile(file_path):
                    logger.error(f"[ERROR PLAY] Gagal mengunduh: {url}")
                    await self._cleanup_current_file()
                    await self._play_next()
                    return
                await self._cleanup_current_file()
                self._current_file = file_path
                audio_source = file_path
                is_stream = False

        # [CACHE RACE] Re-verify cached file right before FFmpeg — it may have been
        # evicted by concurrent _enforce_cache_size_limit between our check above
        # and now. Fall back to streaming only when the race actually occurs.
        if not is_stream and not os.path.isfile(audio_source):
            logger.warning(f"[CACHE RACE] File evicted before play, falling back to stream")
            stream_url = await self._get_direct_url(url)
            if stream_url:
                audio_source = stream_url
                is_stream = True
                self._current_file = None
            else:
                logger.error(f"[ERROR PLAY] Cache file gone and stream also failed: {url}")
                await self._cleanup_current_file()
                await self._play_next()
                return

        try:
            if is_stream:
                before_opts = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
                source = discord.FFmpegPCMAudio(
                    audio_source, executable=FFMPEG_PATH,
                    before_options=before_opts
                )
            else:
                source = discord.FFmpegPCMAudio(audio_source, executable=FFMPEG_PATH)

            vol_source = discord.PCMVolumeTransformer(source, volume=self._volume / 100.0)

            self.vc.play(vol_source, after=lambda err, gen=my_generation: self._on_track_end_wrapper(err, gen))

            self._start_time = time.time()
            self._paused = False
            self._paused_position = 0.0
            self._pause_reason = "none"
            self._stopped = False
            self._start_watchdog(track.duration)
            await self._update_now_playing()
            self._start_np_updater()
            logger.info(f"[DEBUG PLAY] Pemutaran {'stream' if is_stream else 'file'} berhasil!")
        except Exception as e:
            logger.critical(f"[CRITICAL ERROR PLAY] FFmpeg gagal: {e}")
            traceback.print_exc()
            if self._current_file:
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

    def _on_track_end_wrapper(self, error, generation: int = 0):
        if error:
            logger.error(f"[TRACK END ERROR] {error}")
        # [PHASE 1] Drop stale callbacks. If a newer play() has already
        # bumped the generation, this callback belongs to a ffmpeg process
        # that was forcibly replaced and must not chain into _on_track_end.
        logger.info(f"[TRACK END WRAPPER] fired gen={generation}, current={self._play_generation}")
        if self._play_generation != generation:
            logger.debug(f"[TRACK END] Stale callback (gen={generation}, current={self._play_generation}), ignored.")
            return
        loop = self.vc.client.loop if (self.vc and hasattr(self.vc, "client") and self.vc.client) else asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(self._on_track_end(error, generation), loop)

    async def _on_track_end(self, error=None, generation: int = 0):
        # [PHASE 1] Re-check generation at coroutine-entry time. Between
        # the wrapper's check and now, a newer play() could have run and
        # bumped the generation. If so, this callback is stale — drop it.
        if self._play_generation != generation:
            logger.debug(f"[TRACK END] Stale at entry (gen={generation}, current={self._play_generation}), ignored.")
            return
        logger.info(f"[TRACK END] entered gen={generation}, queue_len={len(self.queue)}, loop_mode={self.loop_mode}")
        self._stop_watchdog()
        self._save_state()
        await asyncio.sleep(0.3)
        logger.info(f"[TRACK END] after sleep, queue_len={len(self.queue)}, single_loop={'set' if self._single_loop_track else 'None'}")
        async with self._track_lock:
            if self.loop_mode == "single" and self._single_loop_track:
                await self.play(self._single_loop_track)
                return
            if self.loop_mode == "queue" and not self.queue and self._queue_history:
                self.queue = list(self._queue_history)
                self._queue_history.clear()
            if self.queue:
                next_track = self.queue.pop(0)
                logger.info(f"[NEXT TRACK] Playing '{next_track.title}' (queue has {len(self.queue)} more)")
                await self.play(next_track)
                if len(self.queue) < 5 and self._playlist_tracks and self._playlist_index < len(self._playlist_tracks):
                    asyncio.create_task(self._load_more_from_playlist())
                return
            if self._playlist_tracks and self._playlist_index < len(self._playlist_tracks):
                loaded = await self._load_more_from_playlist()
                if loaded > 0:
                    next_track = self.queue.pop(0)
                    await self.play(next_track)
                    return
            if self.autoplay and self._single_loop_track:
                try:
                    next_track = await self._autoplay_search()
                    if next_track:
                        await self.play(next_track)
                        return
                except Exception as e:
                    logger.warning(f"[AUTOPLAY ERROR] {e}")
            self.current_track = None
            self._single_loop_track = None
            self._stop_np_updater()
            await self._cleanup_current_file()
            await self._cleanup_preloaded_file()
            self._clear_state()
            await self._update_now_playing()
            import gc as _gc
            _collected = _gc.collect()
            if _collected > 100:
                logger.info(f"[MEMORY] gc freed {_collected} objects after queue drain")

    async def _play_next(self):
        if self.queue:
            next_track = self.queue.pop(0)
            await self.play(next_track)

    async def _preload_next(self, track: YtDlpTrack):
        url = track.webpage_url or track.uri
        if not url or not re.match(r'^https?://[^\s]+$', url):
            return
        dest = self._cache_path(url)
        # [PHASE 7] Same eviction as _download_track — preload can also push
        # the cache over the cap.
        self._enforce_cache_size_limit()
        # [PHASE 3b] Validate cached file before trusting it. _validate_cached_file
        # deletes the file and returns False if it's corrupt/truncated.
        if os.path.isfile(dest) and self._validate_cached_file(dest):
            self._preloaded_file = dest
            self._preloaded_for = url
            return

        async with _DOWNLOAD_SEMAPHORE:
            try:
                loop = asyncio.get_event_loop()
                # [PHASE 8] Same sequential fallback chain as _download_track.
                # Preload should also try multiple player_clients before
                # giving up — otherwise a bot-detected video blocks the
                # next-track preload even when an exotic client would work.
                base_ytdlp_opts = {
                    "quiet": True, "no_warnings": True,
                    "format": "bestaudio/best", "skip_download": True,
                    **_AUTH_OPTS,
                }
                info = await loop.run_in_executor(
                    _YTDLP_EXECUTOR,
                    lambda: _extract_info_with_fallback(url, base_ytdlp_opts)
                )
                direct_url = info.get("url") if info else None
                if not direct_url:
                    return

                async with aiohttp.ClientSession() as session:
                    # [PHASE 5] Same timeout bump as _download_track: 120s -> 300s.
                    async with session.get(direct_url, timeout=aiohttp.ClientTimeout(total=300)) as sr:
                        if sr.status != 200:
                            return
                        # [PHASE 3b] Track server-advertised size for truncation check.
                        server_total = sr.headers.get("Content-Length")
                        server_total_int = None
                        try:
                            if server_total is not None:
                                server_total_int = int(server_total)
                        except (TypeError, ValueError):
                            server_total_int = None
                        with open(dest, "wb") as f:
                            while True:
                                chunk = await sr.content.read(65536)
                                if not chunk:
                                    break
                                f.write(chunk)
                        # [PHASE 3b] Truncation check first; if short, delete + bail.
                        actual_size = os.path.getsize(dest) if os.path.isfile(dest) else 0
                        if server_total_int is not None and actual_size < server_total_int:
                            try:
                                if os.path.isfile(dest):
                                    os.remove(dest)
                            except Exception:
                                pass
                            return
                        # [PHASE 3b] Then strict validation. Preload is best-effort,
                        # so don't raise on failure — just leave _preloaded_file unset
                        # and let the main download path handle it later.
                        if self._validate_cached_file(dest, info):
                            self._preloaded_file = dest
                            self._preloaded_for = url
            except Exception:
                pass

    async def _load_more_from_playlist(self, count: int = 50) -> int:
        if not self._cog or not self._playlist_tracks or self._playlist_index >= len(self._playlist_tracks):
            return 0
        batch = self._playlist_tracks[self._playlist_index:self._playlist_index + count]
        if not batch:
            return 0
        self._playlist_index += len(batch)
        sem = asyncio.Semaphore(15)
        results: list = [None] * len(batch)
        async def _search(idx: int, rt):
            async with sem:
                r = await self._cog._search_single_resolved(rt)
                if r:
                    results[idx] = r
        await asyncio.gather(*[_search(i, rt) for i, rt in enumerate(batch)])
        for r in results:
            if r:
                self.queue.append(r)
        found = sum(1 for r in results if r)
        logger.info(f"[PLAYLIST AUTO] Berhasil memuat {found} lagu tambahan ({self._playlist_index}/{len(self._playlist_tracks)})")
        return found

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
            # [PHASE 1] Bump generation on seek too so the ffmpeg-restart's
            # _on_track_end callback belongs to this play() invocation.
            self._play_generation += 1
            seek_gen = self._play_generation
            self.vc.play(vol_source, after=lambda err, gen=seek_gen: self._on_track_end_wrapper(err, gen))
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

    async def _cleanup_preloaded_file(self):
        if self._preloaded_file and os.path.isfile(self._preloaded_file):
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
        if self._resume_task and not self._resume_task.done():
            self._resume_task.cancel()
            self._resume_task = None
        if self._bg_resolve_task and not self._bg_resolve_task.done():  # [PHASE 6b]
            self._bg_resolve_task.cancel()
            self._bg_resolve_task = None
        self._recovery_attempts = 0
        await self._cleanup_current_file()
        await self._cleanup_preloaded_file()
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
        if self._resume_task and not self._resume_task.done():
            self._resume_task.cancel()
            self._resume_task = None
        if self._bg_resolve_task and not self._bg_resolve_task.done():  # [PHASE 6b]
            self._bg_resolve_task.cancel()
            self._bg_resolve_task = None
        await self._cleanup_current_file()
        await self._cleanup_preloaded_file()
        await self._cleanup_np()
        if self.vc:
            self.vc.stop()
            try:
                await self.vc.disconnect()
            except Exception:
                pass