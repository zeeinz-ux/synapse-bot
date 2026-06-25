import asyncio
import os
import subprocess
import time
import shutil
from dataclasses import dataclass, field
from typing import Optional

import discord
import yt_dlp


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

YTDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "noplaylist": True,
}

YTDL_SEARCH_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "extract_flat": "in_playlist",
    "noplaylist": False,
}

YTDL_PLAYLIST_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": "in_playlist",
    "skip_download": True,
    "dump_single_json": True,
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
    @staticmethod
    async def search(query: str) -> list:
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
        except Exception as e:
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
        return tracks

    @staticmethod
    async def extract_info(url: str) -> Optional[YtDlpTrack]:
        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(YTDL_OPTS).extract_info(url, download=False)
            )
        except Exception:
            return None

        if info:
            return YtDlpTrack.from_info(info)
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
        self._last_track_id = None
        self._last_embed_time = 0.0
        self._alone_task = None
        self._track_lock = asyncio.Lock()
        self._queue_history = []
        self._single_loop_track = None
        self._guild_id = None
        self._ytdlp_proc: Optional[subprocess.Popen] = None

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

    async def play(self, track: YtDlpTrack):
        self.current_track = track
        self._single_loop_track = track
        if self.vc.is_playing() or self.vc.is_paused():
            self.vc.stop()

        self._kill_ytdlp()

        url = track.webpage_url or track.uri
        try:
            proc = await asyncio.to_thread(
                lambda: subprocess.Popen(
                    ["yt-dlp", "-f", "bestaudio", "-o", "-", "--no-part", url],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
            )
        except Exception as e:
            print(f"[PLAY ERROR] Failed to start yt-dlp: {e}")
            if self.home:
                try:
                    await self.home.send(f"❌ Gagal memutar: {e}")
                except Exception:
                    pass
            await self._play_next()
            return

        self._ytdlp_proc = proc
        ffmpeg_opts = {
            "options": "-vn",
        }
        source = discord.FFmpegPCMAudio(proc.stdout, executable=FFMPEG_PATH, pipe=True, **ffmpeg_opts)
        vol_source = discord.PCMVolumeTransformer(source, volume=self._volume / 100.0)
        self.vc.play(vol_source, after=lambda e: self._on_track_end_wrapper(e))
        self._start_time = time.time()
        self._paused = False
        self._paused_position = 0.0

    def _on_track_end_wrapper(self, error):
        if error:
            print(f"[TRACK END ERROR] {error}")
        asyncio.run_coroutine_threadsafe(self._on_track_end(error), self.vc.client.loop if self.vc and self.vc.client else None)

    async def _on_track_end(self, error=None):
        self._kill_ytdlp()
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
                await self.play(next_track)
                return
            if self.autoplay and self._single_loop_track:
                try:
                    query = f"ytsearch:{self._single_loop_track.author} mix"
                    results = await YtDlpSearcher.search(query)
                    if results:
                        await self.play(results[0])
                        return
                except Exception as e:
                    print(f"[AUTOPLAY ERROR] {e}")
            self.current_track = None
            self._single_loop_track = None

    async def _play_next(self):
        if self.queue:
            next_track = self.queue.pop(0)
            await self.play(next_track)

    async def seek(self, position_ms: int):
        if not self.current_track or not self.vc:
            return
        self.vc.stop()
        self._kill_ytdlp()

        url = self.current_track.webpage_url or self.current_track.uri
        position_sec = position_ms / 1000
        try:
            proc = await asyncio.to_thread(
                lambda: subprocess.Popen(
                    ["yt-dlp", "-f", "bestaudio", "-o", "-", "--no-part", url],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
            )
        except Exception as e:
            if self.home:
                try:
                    await self.home.send(f"❌ Gagal seek: {e}")
                except Exception:
                    pass
            return

        self._ytdlp_proc = proc
        ffmpeg_opts = {
            "before_options": f"-ss {position_sec} -noaccurate_seek",
            "options": "-vn",
        }
        source = discord.FFmpegPCMAudio(proc.stdout, executable=FFMPEG_PATH, pipe=True, **ffmpeg_opts)
        vol_source = discord.PCMVolumeTransformer(source, volume=self._volume / 100.0)
        self.vc.play(vol_source, after=lambda e: self._on_track_end_wrapper(e))
        self._start_time = time.time() - position_sec
        self._paused = False

    def _kill_ytdlp(self):
        if self._ytdlp_proc:
            try:
                self._ytdlp_proc.kill()
            except Exception:
                pass
            try:
                self._ytdlp_proc.wait(timeout=2)
            except Exception:
                pass
            self._ytdlp_proc = None

    async def stop(self):
        self._kill_ytdlp()
        self.loop_mode = "off"
        self.autoplay = False
        self._queue_history.clear()
        self._single_loop_track = None
        self._last_track_id = None
        self.queue.clear()
        if self.vc:
            self.vc.stop()
            try:
                await self.vc.disconnect()
            except Exception:
                pass

    async def disconnect(self):
        self._kill_ytdlp()
        if self.vc:
            self.vc.stop()
            try:
                await self.vc.disconnect()
            except Exception:
                pass
