"""
SpotifyDown API Integration — Async Resolver dengan Multi-Fallback
===================================================================
Fallback chain:
    1. SpotifyDown API (async, no auth)
    2. Spotify ANONYMOUS API (async, no auth, no premium) — uses web-player token
    3. Spotify oEmbed (async, no auth)
    4. Spotify HTML scrape (async, no auth)

Cara pakai di cog:
    from .spotify_down import SpotifyResolver

    self.spotify = SpotifyResolver()  # No credentials needed!

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


# ==========================================================}
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
    query: str
    source: str


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
                        logger.warning("SpotifyDown %s pada %s, retry dalam %ss...", resp.status, endpoint, wait)
                        await asyncio.sleep(wait)
                    else:
                        logger.error("SpotifyDown error %s pada %s", resp.status, endpoint)
                        return None
            except asyncio.TimeoutError:
                logger.warning("SpotifyDown timeout (attempt %s/%s) pada %s", attempt + 1, MAX_RETRIES, endpoint)
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.error("SpotifyDown exception: %s", e)
                return None
        return None

    async def get_playlist_tracks(self, playlist_id: str) -> List[Dict]:
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
        data = await self._request("GET", f"/getId/{spotify_track_id}")
        if data and "id" in data:
            return data["id"]
        return None


# ==========================================================
# SPOTIFY ANONYMOUS API (Fallback 1 — NO PREMIUM NEEDED)
# ==========================================================
class SpotifyAnonymousClient:
    """
    Uses Spotify web-player anonymous/visitor token.
    NO Client ID, NO Client Secret, NO Premium required.
    This mimics how Spotify's own web player authenticates.
    """

    def __init__(self):
        self._token: Optional[str] = None
        self._token_expires = 0.0

    async def _get_token(self, session: aiohttp.ClientSession) -> Optional[str]:
        now = asyncio.get_event_loop().time()
        if self._token and now < self._token_expires:
            logger.warning("[SPOTIFY ANON] Reusing cached token.")
            return self._token

        logger.warning("[SPOTIFY ANON] Requesting anonymous token...")

        # Multiple endpoints to try
        endpoints = [
            "https://open.spotify.com/get_access_token?reason=transport&productType=web_player",
            "https://open.spotify.com/get_access_token?reason=transport&productType=web-player",
        ]

        for endpoint in endpoints:
            try:
                async with session.get(
                    endpoint,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "application/json",
                        "Referer": "https://open.spotify.com/",
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    body = await resp.text()
                    if resp.status == 200:
                        data = json.loads(body)
                        token = data.get("accessToken") or data.get("access_token")
                        if token:
                            expires_in = data.get("expiresIn", 3600)
                            self._token = token
                            self._token_expires = now + expires_in - 60
                            logger.warning("[SPOTIFY ANON] Token OK (expires_in=%s)", expires_in)
                            return token
                        else:
                            logger.error("[SPOTIFY ANON] Token field missing in response: %s", body[:200])
                    else:
                        logger.warning("[SPOTIFY ANON] Endpoint %s returned HTTP %s", endpoint, resp.status)
            except Exception as e:
                logger.warning("[SPOTIFY ANON] Endpoint %s failed: %s", endpoint, e)

        return None

    async def get_playlist_tracks(self, session: aiohttp.ClientSession, playlist_id: str) -> List[Dict]:
        token = await self._get_token(session)
        if not token:
            logger.error("[SPOTIFY ANON PLAYLIST] No token available.")
            return []

        tracks = []
        url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks?limit=100"
        page = 0
        while url:
            page += 1
            try:
                async with session.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get("items", [])
                        logger.warning("[SPOTIFY ANON PLAYLIST] Page %s — got %s items", page, len(items))
                        for item in items:
                            t = item.get("track")
                            if t:
                                tracks.append(t)
                        url = data.get("next")
                    elif resp.status == 401:
                        logger.error("[SPOTIFY ANON PLAYLIST] 401 Unauthorized — token expired.")
                        self._token = None
                        break
                    elif resp.status == 403:
                        body = await resp.text()
                        logger.error("[SPOTIFY ANON PLAYLIST] 403 Forbidden — Premium required? | %s", body[:300])
                        break
                    else:
                        body = await resp.text()
                        logger.error("[SPOTIFY ANON PLAYLIST] HTTP %s | %s", resp.status, body[:300])
                        break
            except Exception as e:
                logger.error("[SPOTIFY ANON PLAYLIST] Exception on page %s: %s", page, e)
                break

        logger.warning("[SPOTIFY ANON PLAYLIST] Total tracks collected: %s", len(tracks))
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
                    if resp.status == 200:
                        data = await resp.json()
                        tracks.extend(data.get("items", []))
                        url = data.get("next")
                    else:
                        break
            except Exception as e:
                logger.error("[SPOTIFY ANON ALBUM] Exception: %s", e)
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
                else:
                    body = await resp.text()
                    logger.error("[SPOTIFY ANON TRACK] HTTP %s | %s", resp.status, body[:300])
        except Exception as e:
            logger.error("[SPOTIFY ANON TRACK] Exception: %s", e)
        return None


# ==========================================================
# ASYNC OEMBED & HTML SCRAPE (Fallback 2 & 3)
# ==========================================================
async def _get_spotify_metadata_oembed(session: aiohttp.ClientSession, url: str) -> Dict | None:
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
    Flow: SpotifyDown → Spotify Anonymous API → oEmbed → HTML scrape
    """

    def __init__(
        self,
        fallback_client_id: Optional[str] = None,
        fallback_client_secret: Optional[str] = None,
    ):
        # Anonymous client — NO credentials needed, NO Premium required
        self.anon = SpotifyAnonymousClient()
        logger.warning("[SPOTIFY RESOLVER] Anonymous client CREATED (no credentials needed).")

    @staticmethod
    def parse_spotify_url(url: str) -> Optional[Tuple[str, str]]:
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

        # Fallback Anonymous API
        track_data = await self.anon.get_track(session, track_id)
        if track_data:
            return [
                self._track_to_resolved(track_data, track_id, "spotify_anon")
            ], "spotify_anon"

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
        logger.warning("[RESOLVE PLAYLIST] Step 1: SpotifyDown API...")
        raw = await sd.get_playlist_tracks(playlist_id)
        if raw:
            logger.warning("[RESOLVE PLAYLIST] SpotifyDown OK: %d tracks", len(raw))
            return self._convert_sd_tracks(raw), "spotifydown"
        logger.warning("[RESOLVE PLAYLIST] SpotifyDown FAIL.")

        # 2. Fallback ANONYMOUS API (NO Premium, NO credentials)
        logger.warning("[RESOLVE PLAYLIST] Step 2: Anonymous Spotify API...")
        raw = await self.anon.get_playlist_tracks(session, playlist_id)
        if raw:
            logger.warning("[RESOLVE PLAYLIST] Anonymous API OK: %d tracks", len(raw))
            return [
                self._track_to_resolved(t, t.get("id", ""), "spotify_anon")
                for t in raw
            ], "spotify_anon"
        logger.warning("[RESOLVE PLAYLIST] Anonymous API FAIL/EMPTY.")

        # 3. Fallback oEmbed
        logger.warning("[RESOLVE PLAYLIST] Step 3: oEmbed...")
        meta = await _get_spotify_metadata_oembed(session, original_url)
        if meta and meta.get("name"):
            logger.warning("[RESOLVE PLAYLIST] oEmbed got metadata (1 track = playlist name)")
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

        # 4. Fallback HTML scrape
        logger.warning("[RESOLVE PLAYLIST] Step 4: HTML scrape...")
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
        raw = await sd.get_album_tracks(album_id)
        if raw:
            return self._convert_sd_tracks(raw), "spotifydown"

        raw = await self.anon.get_album_tracks(session, album_id)
        if raw:
            album_info = None
            try:
                token = await self.anon._get_token(session)
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
                rt = self._track_to_resolved(t, t.get("id", ""), "spotify_anon")
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
            return result, "spotify_anon"

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

    # --- Discord.py extension entrypoint ---
async def setup(bot):
    pass
