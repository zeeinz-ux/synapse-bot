"""
SpotifyDown API Integration — Async Resolver dengan Multi-Fallback
===================================================================
Fallback chain:
    1. SpotifyDown API (async, no auth) — fastest, bisa down
    2. Spotify Official API (async, Client Credentials) — stable but rate-limited
    3. Spotify oEmbed (async, no auth) — simple metadata only
    4. Spotify HTML scrape (async, no auth) — last resort

Cara pakai di cog:
    from .spotify_down import SpotifyResolver

    self.spotify = SpotifyResolver(
        fallback_client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        fallback_client_secret=os.getenv("SPOTIFY_CLIENT_SECRET")
    )

    tracks = await self.spotify.resolve(url, session)
"""

import asyncio
import base64
import json
import logging
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)

# ==========================================================
# KONSTANTA
# ==========================================================
SPOTIFYDOWN_BASE = "https://api.spotifydown.com"
SPOTIFY_URL_PATTERNS = [
    r"open\.spotify\.com/(?P<type>track|playlist|album)/(?P<id>[a-zA-Z0-9]+)",
    r"spotify:(?P<type>track|playlist|album):(?P<id>[a-zA-Z0-9]+)",
]
REQUEST_TIMEOUT = 15
MAX_RETRIES = 2


# ==========================================================
# DATA CLASS
# ==========================================================
@dataclass
class ResolvedTrack:
    """Metadata track hasil resolve dari Spotify URL."""
    name: str
    artists: str
    album: Optional[str]
    duration_ms: Optional[int]
    artwork: Optional[str]
    spotify_id: str
    youtube_id: Optional[str]
    query: str          # Query untuk wavelink.Playable.search()
    source: str         # "spotifydown" | "spotify_official" | "oembed" | "html_scrape" | "ytsearch"


# ==========================================================
# SPOTIFYDOWN API CLIENT (Primary)
# ==========================================================
class SpotifyDownClient:
    """Client async untuk api.spotifydown.com — no auth required."""

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Origin": "https://spotifydown.com",
            "Referer": "https://spotifydown.com/",
        }

    async def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        """Safe request dengan retry + exponential backoff."""
        url = f"{SPOTIFYDOWN_BASE}{endpoint}"
        for attempt in range(MAX_RETRIES):
            try:
                async with self.session.request(
                    method,
                    url,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                    **kwargs,
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status in (429, 502, 503):
                        wait = 2 ** attempt
                        logger.warning(
                            "SpotifyDown %s pada %s, retry dalam %ss...",
                            resp.status, endpoint, wait,
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error("SpotifyDown error %s pada %s", resp.status, endpoint)
                        return None
            except asyncio.TimeoutError:
                logger.warning(
                    "SpotifyDown timeout (attempt %s/%s) pada %s",
                    attempt + 1, MAX_RETRIES, endpoint,
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.error("SpotifyDown exception: %s", e)
                return None
        return None

    async def get_playlist_tracks(self, playlist_id: str) -> List[Dict]:
        """Ambil semua track dari playlist (handle pagination)."""
        tracks: List[Dict] = []
        offset = 0
        while True:
            params = {"offset": offset} if offset else {}
            data = await self._request("GET", f"/trackList/playlist/{playlist_id}", params=params)
            if not data or "trackList" not in data:
                break
            batch = data["trackList"]
            if not batch:
                break
            tracks.extend(batch)
            next_offset = data.get("nextOffset")
            if next_offset is None or next_offset == offset:
                break
            offset = next_offset
        return tracks

    async def get_album_tracks(self, album_id: str) -> List[Dict]:
        """Ambil semua track dari album (handle pagination)."""
        tracks: List[Dict] = []
        offset = 0
        while True:
            params = {"offset": offset} if offset else {}
            data = await self._request("GET", f"/trackList/album/{album_id}", params=params)
            if not data or "trackList" not in data:
                break
            batch = data["trackList"]
            if not batch:
                break
            tracks.extend(batch)
            next_offset = data.get("nextOffset")
            if next_offset is None or next_offset == offset:
                break
            offset = next_offset
        return tracks

    async def get_youtube_id(self, spotify_track_id: str) -> Optional[str]:
        """Resolve Spotify track ID ke YouTube video ID."""
        data = await self._request("GET", f"/getId/{spotify_track_id}")
        if data and "id" in data:
            return data["id"]
        return None


# ==========================================================
# SPOTIFY OFFICIAL API (Fallback 1)
# ==========================================================
class SpotifyOfficialClient:
    """Fallback menggunakan Spotify Web API resmi dengan Client Credentials."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: Optional[str] = None
        self._token_expires = 0.0

    async def _get_token(self, session: aiohttp.ClientSession) -> Optional[str]:
        if self._token and asyncio.get_event_loop().time() < self._token_expires:
            return self._token
        try:
            creds = base64.b64encode(
                f"{self.client_id}:{self.client_secret}".encode()
            ).decode()
            async with session.post(
                "https://accounts.spotify.com/api/token",
                headers={
                    "Authorization": f"Basic {creds}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._token = data["access_token"]
                    self._token_expires = (
                        asyncio.get_event_loop().time() + data["expires_in"] - 60
                    )
                    logger.info("Spotify Official API token berhasil didapat.")
                    return self._token
                else:
                    body = await resp.text()
                    logger.error(
                        "Spotify auth GAGAL — status: %s | response: %s",
                        resp.status, body[:200]
                    )
        except Exception as e:
            logger.error("Spotify auth error: %s", e)
        return None

    async def get_playlist_tracks(self, session: aiohttp.ClientSession, playlist_id: str) -> List[Dict]:
        token = await self._get_token(session)
        if not token:
            return []
        tracks = []
        url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks?limit=100"
        while url:
            try:
                async with session.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        break
                    data = await resp.json()
                    for item in data.get("items", []):
                        t = item.get("track")
                        if t:
                            tracks.append(t)
                    url = data.get("next")
            except Exception as e:
                logger.error("Spotify official API error: %s", e)
                break
        return tracks

    async def get_album_tracks(self, session: aiohttp.ClientSession, album_id: str) -> List[Dict]:
        token = await self._get_token(session)
        if not token:
            return []
        tracks = []
        url = f"https://api.spotify.com/v1/albums/{album_id}/tracks?limit=50"
        while url:
            try:
                async with session.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        break
                    data = await resp.json()
                    tracks.extend(data.get("items", []))
                    url = data.get("next")
            except Exception as e:
                logger.error("Spotify official API error: %s", e)
                break
        return tracks

    async def get_track(self, session: aiohttp.ClientSession, track_id: str) -> Optional[Dict]:
        token = await self._get_token(session)
        if not token:
            return None
        try:
            async with session.get(
                f"https://api.spotify.com/v1/tracks/{track_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.error("Spotify official API error: %s", e)
        return None


# ==========================================================
# ASYNC OEMBED & HTML SCRAPE (Fallback 2 & 3)
# ==========================================================
async def _get_spotify_metadata_oembed(session: aiohttp.ClientSession, url: str) -> Dict | None:
    """Spotify oEmbed API (gratis, tidak perlu auth) — versi resmi."""
    try:
        encoded_url = url.replace(" ", "%20").replace("&", "%26")
        oembed_url = f"https://open.spotify.com/oembed?url={encoded_url}"
        async with session.get(
            oembed_url,
            timeout=aiohttp.ClientTimeout(total=10),
            headers={"User-Agent": "Mozilla/5.0"},
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return {
                "name": data.get("title", ""),
                "artists": data.get("author_name", ""),
                "artwork": data.get("thumbnail_url", ""),
                "album": None,
                "duration_ms": None,
            }
    except Exception as e:
        logger.error("[SPOTIFY OEMBED ERROR] %s", e)
        return None


async def _get_spotify_metadata_html(session: aiohttp.ClientSession, url: str) -> Dict | None:
    """Scrape metadata dari HTML Spotify page — async version."""
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=10),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as resp:
            if resp.status != 200:
                return None
            html = await resp.text()

            title_match = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]*)"', html)
            title = title_match.group(1) if title_match else ""

            desc_match = re.search(r'<meta[^>]*property="og:description"[^>]*content="([^"]*)"', html)
            description = desc_match.group(1) if desc_match else ""

            image_match = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]*)"', html)
            image = image_match.group(1) if image_match else ""

            artist = ""
            if " · " in description:
                parts = description.split(" · ")
                if len(parts) >= 1:
                    artist = parts[0].replace("Listen to ", "").replace(" on Spotify", "").strip()
            elif " - " in description:
                artist = description.split(" - ")[0].strip()

            if not artist and title:
                if " - " in title:
                    artist = title.split(" - ")[-1].strip()
                    title = title.split(" - ")[0].strip()
                elif " — " in title:
                    artist = title.split(" — ")[-1].strip()
                    title = title.split(" — ")[0].strip()

            return {
                "name": title,
                "artists": artist,
                "artwork": image,
                "album": None,
                "duration_ms": None,
            }
    except Exception as e:
        logger.error("[SPOTIFY HTML SCRAPE ERROR] %s", e)
        return None


# ==========================================================
# UNIFIED RESOLVER
# ==========================================================
class SpotifyResolver:
    """
    Resolver utama untuk Spotify URLs.
    Flow: SpotifyDown → Spotify Official → oEmbed → HTML scrape → ytsearch
    """

    def __init__(
        self,
        fallback_client_id: Optional[str] = None,
        fallback_client_secret: Optional[str] = None,
    ):
        self.official: Optional[SpotifyOfficialClient] = None
        if fallback_client_id and fallback_client_secret:
            self.official = SpotifyOfficialClient(fallback_client_id, fallback_client_secret)

    @staticmethod
    def parse_spotify_url(url: str) -> Optional[Tuple[str, str]]:
        """Parse Spotify URL → (type, id)."""
        for pattern in SPOTIFY_URL_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group("type"), match.group("id")
        return None

    async def resolve(
        self,
        url: str,
        session: aiohttp.ClientSession,
    ) -> Tuple[List[ResolvedTrack], str]:
        """
        Resolve Spotify URL jadi list ResolvedTrack.
        Returns: (tracks, source_name)
        """
        parsed = self.parse_spotify_url(url)
        if not parsed:
            return [], "invalid"

        spotify_type, spotify_id = parsed
        sd = SpotifyDownClient(session)

        if spotify_type == "track":
            return await self._resolve_track(spotify_id, sd, session, url)
        elif spotify_type == "playlist":
            return await self._resolve_playlist(spotify_id, sd, session, url)
        elif spotify_type == "album":
            return await self._resolve_album(spotify_id, sd, session, url)

        return [], "invalid"

    # --------------------------------------------------------
    # TRACK
    # --------------------------------------------------------
    async def _resolve_track(
        self,
        track_id: str,
        sd: SpotifyDownClient,
        session: aiohttp.ClientSession,
        original_url: str,
    ) -> Tuple[List[ResolvedTrack], str]:
        # 1. Coba SpotifyDown getId
        yt_id = await sd.get_youtube_id(track_id)
        if yt_id:
            return [
                ResolvedTrack(
                    name="Unknown",
                    artists="Unknown",
                    album=None,
                    duration_ms=None,
                    artwork=None,
                    spotify_id=track_id,
                    youtube_id=yt_id,
                    query=f"https://youtube.com/watch?v={yt_id}",
                    source="spotifydown",
                )
            ], "spotifydown"

        # 2. Fallback Spotify Official API
        if self.official:
            track_data = await self.official.get_track(session, track_id)
            if track_data:
                return [
                    self._track_to_resolved(track_data, track_id, "spotify_official")
                ], "spotify_official"

        # 3. Fallback oEmbed (async)
        meta = await _get_spotify_metadata_oembed(session, original_url)
        if meta and meta.get("name"):
            return [
                ResolvedTrack(
                    name=meta["name"],
                    artists=meta["artists"],
                    album=meta.get("album"),
                    duration_ms=meta.get("duration_ms"),
                    artwork=meta.get("artwork"),
                    spotify_id=track_id,
                    youtube_id=None,
                    query=f"ytsearch:{meta['name']} {meta['artists']}",
                    source="oembed",
                )
            ], "oembed"

        # 4. Fallback HTML scrape (async)
        meta = await _get_spotify_metadata_html(session, original_url)
        if meta and meta.get("name"):
            return [
                ResolvedTrack(
                    name=meta["name"],
                    artists=meta["artists"],
                    album=meta.get("album"),
                    duration_ms=meta.get("duration_ms"),
                    artwork=meta.get("artwork"),
                    spotify_id=track_id,
                    youtube_id=None,
                    query=f"ytsearch:{meta['name']} {meta['artists']}",
                    source="html_scrape",
                )
            ], "html_scrape"

        # 5. Ultimate fallback
        return [
            ResolvedTrack(
                name=f"Spotify Track {track_id}",
                artists="Unknown",
                album=None,
                duration_ms=None,
                artwork=None,
                spotify_id=track_id,
                youtube_id=None,
                query=f"ytsearch:spotify:{track_id}",
                source="ytsearch",
            )
        ], "ytsearch"

    # --------------------------------------------------------
    # PLAYLIST
    # --------------------------------------------------------
    async def _resolve_playlist(
        self,
        playlist_id: str,
        sd: SpotifyDownClient,
        session: aiohttp.ClientSession,
        original_url: str,
    ) -> Tuple[List[ResolvedTrack], str]:
        # 1. SpotifyDown
        raw = await sd.get_playlist_tracks(playlist_id)
        if raw:
            return self._convert_sd_tracks(raw), "spotifydown"

        # 2. Fallback Official
        if self.official:
            raw = await self.official.get_playlist_tracks(session, playlist_id)
            if raw:
                return [
                    self._track_to_resolved(t, t.get("id", ""), "spotify_official")
                    for t in raw
                ], "spotify_official"

        # 3. Fallback oEmbed (async) — cuma dapat 1 track = nama playlist
        meta = await _get_spotify_metadata_oembed(session, original_url)
        if meta and meta.get("name"):
            return [
                ResolvedTrack(
                    name=meta["name"],
                    artists=meta["artists"],
                    album=None,
                    duration_ms=None,
                    artwork=meta.get("artwork"),
                    spotify_id=playlist_id,
                    youtube_id=None,
                    query=f"ytsearch:{meta['name']} {meta['artists']} playlist",
                    source="oembed",
                )
            ], "oembed"

        # 4. Fallback HTML scrape (async)
        meta = await _get_spotify_metadata_html(session, original_url)
        if meta and meta.get("name"):
            return [
                ResolvedTrack(
                    name=meta["name"],
                    artists=meta["artists"],
                    album=None,
                    duration_ms=None,
                    artwork=meta.get("artwork"),
                    spotify_id=playlist_id,
                    youtube_id=None,
                    query=f"ytsearch:{meta['name']} {meta['artists']} playlist",
                    source="html_scrape",
                )
            ], "html_scrape"

        return [], "failed"

    # --------------------------------------------------------
    # ALBUM
    # --------------------------------------------------------
    async def _resolve_album(
        self,
        album_id: str,
        sd: SpotifyDownClient,
        session: aiohttp.ClientSession,
        original_url: str,
    ) -> Tuple[List[ResolvedTrack], str]:
        # 1. SpotifyDown
        raw = await sd.get_album_tracks(album_id)
        if raw:
            return self._convert_sd_tracks(raw), "spotifydown"

        # 2. Fallback Official
        if self.official:
            raw = await self.official.get_album_tracks(session, album_id)
            if raw:
                album_info = None
                try:
                    token = await self.official._get_token(session)
                    async with session.get(
                        f"https://api.spotify.com/v1/albums/{album_id}",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status == 200:
                            album_info = await resp.json()
                except Exception:
                    pass

                album_name = album_info.get("name") if album_info else None
                cover = album_info.get("images", [{}])[0].get("url") if album_info else None

                result = []
                for t in raw:
                    rt = self._track_to_resolved(t, t.get("id", ""), "spotify_official")
                    if album_name:
                        rt = ResolvedTrack(
                            name=rt.name,
                            artists=rt.artists,
                            album=album_name,
                            duration_ms=rt.duration_ms,
                            artwork=cover or rt.artwork,
                            spotify_id=rt.spotify_id,
                            youtube_id=rt.youtube_id,
                            query=rt.query,
                            source=rt.source,
                        )
                    result.append(rt)
                return result, "spotify_official"

        # 3. Fallback oEmbed (async)
        meta = await _get_spotify_metadata_oembed(session, original_url)
        if meta and meta.get("name"):
            return [
                ResolvedTrack(
                    name=meta["name"],
                    artists=meta["artists"],
                    album=meta["name"],
                    duration_ms=None,
                    artwork=meta.get("artwork"),
                    spotify_id=album_id,
                    youtube_id=None,
                    query=f"ytsearch:{meta['name']} {meta['artists']} album",
                    source="oembed",
                )
            ], "oembed"

        # 4. Fallback HTML scrape (async)
        meta = await _get_spotify_metadata_html(session, original_url)
        if meta and meta.get("name"):
            return [
                ResolvedTrack(
                    name=meta["name"],
                    artists=meta["artists"],
                    album=meta["name"],
                    duration_ms=None,
                    artwork=meta.get("artwork"),
                    spotify_id=album_id,
                    youtube_id=None,
                    query=f"ytsearch:{meta['name']} {meta['artists']} album",
                    source="html_scrape",
                )
            ], "html_scrape"

        return [], "failed"

    # --------------------------------------------------------
    # HELPERS
    # --------------------------------------------------------
    def _convert_sd_tracks(self, raw_tracks: List[Dict]) -> List[ResolvedTrack]:
        """Convert raw SpotifyDown trackList ke ResolvedTrack."""
        result = []
        for t in raw_tracks:
            name = t.get("title", t.get("name", "Unknown"))
            artists = t.get("artists", t.get("artist", "Unknown"))
            if isinstance(artists, list):
                artists = ", ".join(
                    a.get("name", "") if isinstance(a, dict) else str(a)
                    for a in artists
                )
            album = t.get("album")
            duration = t.get("duration")
            if duration and isinstance(duration, (int, float)) and duration < 10000:
                duration = int(duration * 1000)
            artwork = t.get("cover", t.get("album_cover", t.get("artwork", "")))
            tid = t.get("id", "")
            yt_id = t.get("youtube_id") or t.get("yt_id")

            if yt_id:
                query = f"https://youtube.com/watch?v={yt_id}"
            else:
                query = f"ytsearch:{name} {artists}"

            result.append(
                ResolvedTrack(
                    name=name,
                    artists=artists,
                    album=album,
                    duration_ms=duration,
                    artwork=artwork,
                    spotify_id=tid,
                    youtube_id=yt_id,
                    query=query,
                    source="spotifydown",
                )
            )
        return result

    def _track_to_resolved(
        self, track_data: Dict, track_id: str, source: str
    ) -> ResolvedTrack:
        """Convert Spotify Official API track object ke ResolvedTrack."""
        name = track_data.get("name", "Unknown")
        artists = self._artists_to_string(track_data.get("artists", []))
        album = track_data.get("album", {}).get("name") if isinstance(track_data.get("album"), dict) else None
        duration = track_data.get("duration_ms")
        artwork = None
        album_obj = track_data.get("album")
        if isinstance(album_obj, dict):
            images = album_obj.get("images", [])
            if images:
                artwork = images[0].get("url")
        query = self._build_search_query(track_data)
        return ResolvedTrack(
            name=name,
            artists=artists,
            album=album,
            duration_ms=duration,
            artwork=artwork,
            spotify_id=track_id,
            youtube_id=None,
            query=query,
            source=source,
        )

    @staticmethod
    def _artists_to_string(artists) -> str:
        if isinstance(artists, list):
            names = []
            for a in artists:
                if isinstance(a, dict):
                    names.append(a.get("name", ""))
                elif isinstance(a, str):
                    names.append(a)
            return ", ".join(filter(None, names))
        return str(artists) if artists else "Unknown"

    @staticmethod
    def _build_search_query(track_data: Dict) -> str:
        title = track_data.get("name", "")
        artists = SpotifyResolver._artists_to_string(track_data.get("artists", []))
        query = f"{artists} - {title}".strip(" -")
        return f"ytsearch:{query}"
    
    # --- Discord.py extension entrypoint (utility module, not a cog) ---
async def setup(bot):
    """Required by discord.py load_extension(). This module is a utility library used by music.py."""
    pass
