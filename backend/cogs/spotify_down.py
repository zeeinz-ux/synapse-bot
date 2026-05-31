"""
SpotifyDown API Integration - Async Resolver dengan Multi-Fallback
===================================================================
Fallback chain:
    1. SpotifyDown API (async, no auth)
    2. Spotify Official API (async, Client Credentials)
    3. Spotify oEmbed (async, no auth)
    4. Spotify HTML scrape (async, no auth)
"""

import asyncio
import base64
import logging
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)

SPOTIFYDOWN_BASE = "https://api.spotifydown.com"
SPOTIFY_URL_PATTERNS = [
    r"open\.spotify\.com/(?P<type>track|playlist|album)/(?P<id>[a-zA-Z0-9]+)",
    r"spotify:(?P<type>track|playlist|album):(?P<id>[a-zA-Z0-9]+)",
]
REQUEST_TIMEOUT = 15
MAX_RETRIES = 2


@dataclass
class ResolvedTrack:
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
# SPOTIFYDOWN CLIENT (Primary)
# ==========================================================
class SpotifyDownClient:
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
                    method, url, headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT), **kwargs,
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status in (429, 502, 503):
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.error("SpotifyDown error %s pada %s", resp.status, endpoint)
                        return None
            except asyncio.TimeoutError:
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
# SPOTIFY OFFICIAL API (Fallback 1)
# ==========================================================
class SpotifyOfficialClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: Optional[str] = None
        self._token_expires = 0.0

    async def _get_token(self, session: aiohttp.ClientSession) -> Optional[str]:
        if self._token and asyncio.get_event_loop().time() < self._token_expires:
            logger.info("[SPOTIFY AUTH] Reusing cached token.")
            return self._token

        logger.info("[SPOTIFY AUTH] Requesting new token from accounts.spotify.com...")
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
                    logger.info("[SPOTIFY AUTH] Token berhasil didapat!")
                    return self._token
                else:
                    body = await resp.text()
                    logger.error(
                        "[SPOTIFY AUTH] GAGAL - HTTP %s | body: %s",
                        resp.status, body[:300]
                    )
        except Exception as e:
            logger.error("[SPOTIFY AUTH] Exception: %s", e)
        return None

    async def get_playlist_tracks(
        self, session: aiohttp.ClientSession, playlist_id: str
    ) -> List[Dict]:
        logger.info("[SPOTIFY AUTH] get_playlist_tracks dipanggil untuk: %s", playlist_id)
        token = await self._get_token(session)
        if not token:
            logger.error("[SPOTIFY AUTH] Tidak bisa dapat token, abort.")
            return []

        tracks = []
        url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
        params = {"limit": 100, "offset": 0}

        while url:
            try:
                async with session.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 401:
                        logger.warning("[SPOTIFY AUTH] Token expired, refresh...")
                        self._token = None
                        token = await self._get_token(session)
                        if not token:
                            break
                        continue
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error("[SPOTIFY AUTH] get_playlist_tracks HTTP %s: %s", resp.status, body[:200])
                        break
                    data = await resp.json()
                    items = data.get("items", [])
                    for item in items:
                        track = item.get("track")
                        if track and track.get("id"):
                            tracks.append(track)
                    next_url = data.get("next")
                    url = next_url
                    params = {}  # next URL sudah include params
            except Exception as e:
                logger.error("[SPOTIFY AUTH] Exception saat fetch tracks: %s", e)
                break

        logger.info("[SPOTIFY AUTH] Total tracks fetched: %d", len(tracks))
        return tracks

    async def get_album_tracks(
        self, session: aiohttp.ClientSession, album_id: str
    ) -> List[Dict]:
        token = await self._get_token(session)
        if not token:
            return []

        tracks = []
        url = f"https://api.spotify.com/v1/albums/{album_id}/tracks"
        params = {"limit": 50, "offset": 0}

        while url:
            try:
                async with session.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        break
                    data = await resp.json()
                    tracks.extend(data.get("items", []))
                    url = data.get("next")
                    params = {}
            except Exception as e:
                logger.error("[SPOTIFY AUTH] Exception saat fetch album tracks: %s", e)
                break
        return tracks


# ==========================================================
# HELPER FUNCTIONS (oEmbed & HTML scrape)
# ==========================================================
async def _get_spotify_metadata_oembed(
    session: aiohttp.ClientSession, url: str
) -> Optional[Dict]:
    try:
        async with session.get(
            "https://open.spotify.com/oembed",
            params={"url": url},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return {
                    "name": data.get("title", ""),
                    "artists": data.get("provider_name", "Spotify"),
                    "artwork": data.get("thumbnail_url"),
                }
    except Exception as e:
        logger.error("oEmbed exception: %s", e)
    return None


async def _get_spotify_metadata_html(
    session: aiohttp.ClientSession, url: str
) -> Optional[Dict]:
    try:
        async with session.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                html = await resp.text()
                title_match = re.search(r"<title>([^<]+)</title>", html)
                if title_match:
                    return {
                        "name": title_match.group(1).replace(" | Spotify", "").strip(),
                        "artists": "Unknown",
                        "artwork": None,
                    }
    except Exception as e:
        logger.error("HTML scrape exception: %s", e)
    return None


# ==========================================================
# MAIN RESOLVER
# ==========================================================
class SpotifyResolver:
    def __init__(
        self,
        fallback_client_id: Optional[str] = None,
        fallback_client_secret: Optional[str] = None,
    ):
        if fallback_client_id and fallback_client_secret:
            self.official = SpotifyOfficialClient(fallback_client_id, fallback_client_secret)
            logger.info("[SPOTIFY] SpotifyOfficialClient initialized dengan client_id: %s...", fallback_client_id[:8])
        else:
            self.official = None
            logger.warning("[SPOTIFY] SpotifyOfficialClient TIDAK diinisialisasi - env vars kosong!")

    @staticmethod
    def parse_url(url: str) -> Optional[Tuple[str, str]]:
        for pattern in SPOTIFY_URL_PATTERNS:
            m = re.search(pattern, url)
            if m:
                return m.group("type"), m.group("id")
        return None

    async def resolve(
        self, url: str, session: aiohttp.ClientSession
    ) -> List[ResolvedTrack]:
        parsed = self.parse_url(url)
        if not parsed:
            return []

        content_type, content_id = parsed
        sd = SpotifyDownClient(session)

        if content_type == "playlist":
            logger.info("[SPOTIFY] Detected playlist with ID: %s", content_id)
            tracks, source = await self._resolve_playlist(content_id, sd, session, url)
        elif content_type == "album":
            logger.info("[SPOTIFY] Detected album with ID: %s", content_id)
            tracks, source = await self._resolve_album(content_id, sd, session, url)
        elif content_type == "track":
            logger.info("[SPOTIFY] Detected track with ID: %s", content_id)
            tracks, source = await self._resolve_track(content_id, sd, session, url)
        else:
            return []

        logger.info("[SPOTIFY PLAYLIST] %d tracks resolved via %s", len(tracks), source)
        return tracks

    async def _resolve_playlist(
    self,
    playlist_id: str,
    sd: SpotifyDownClient,
    session: aiohttp.ClientSession,
    original_url: str,
) -> Tuple[List[ResolvedTrack], str]:
    """
    Resolves all tracks in a Spotify playlist using Official API first,
    fallback ke SpotifyDown API jika Official API gagal.
    """
    # 1. Gunakan Official API terlebih dahulu
    if self.official:
        raw = await self.official.get_playlist_tracks(session, playlist_id)
        if raw:
            return [
                self._track_to_resolved(t, t.get("id", ""), "spotify_official")
                for t in raw
            ], "spotify_official"

    # 2. Jika Official API gagal, coba SpotifyDown API
    raw = await sd.get_playlist_tracks(playlist_id)
    if raw:
        return self._convert_sd_tracks(raw), "spotifydown"

    # 3. Fallback: oEmbed / HTML (hanya 1 track info)
    meta = await _get_spotify_metadata_oembed(session, original_url)
    if meta:
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

    meta = await _get_spotify_metadata_html(session, original_url)
    if meta:
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

        if self.official:
            raw = await self.official.get_album_tracks(session, album_id)
            if raw:
                return [
                    self._track_to_resolved(t, t.get("id", ""), "spotify_official")
                    for t in raw
                ], "spotify_official"

        meta = await _get_spotify_metadata_oembed(session, original_url)
        if meta and meta.get("name"):
            return [
                ResolvedTrack(
                    name=meta["name"], artists=meta["artists"], album=meta["name"],
                    duration_ms=None, artwork=meta.get("artwork"),
                    spotify_id=album_id, youtube_id=None,
                    query=f"ytsearch:{meta['name']} {meta['artists']} album",
                    source="oembed",
                )
            ], "oembed"

        return [], "failed"

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
                    name=track_id, artists="", album=None, duration_ms=None,
                    artwork=None, spotify_id=track_id, youtube_id=yt_id,
                    query=f"https://youtube.com/watch?v={yt_id}",
                    source="spotifydown",
                )
            ], "spotifydown"

        meta = await _get_spotify_metadata_oembed(session, original_url)
        if meta and meta.get("name"):
            return [
                ResolvedTrack(
                    name=meta["name"], artists=meta["artists"], album=None,
                    duration_ms=None, artwork=meta.get("artwork"),
                    spotify_id=track_id, youtube_id=None,
                    query=f"ytsearch:{meta['name']} {meta['artists']}",
                    source="oembed",
                )
            ], "oembed"

        return [], "failed"

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
            query = f"https://youtube.com/watch?v={yt_id}" if yt_id else f"ytsearch:{name} {artists}"
            result.append(ResolvedTrack(
                name=name, artists=artists, album=album, duration_ms=duration,
                artwork=artwork, spotify_id=tid, youtube_id=yt_id,
                query=query, source="spotifydown",
            ))
        return result

    def _track_to_resolved(self, track_data: Dict, track_id: str, source: str) -> ResolvedTrack:
        name = track_data.get("name", "Unknown")
        artists = self._artists_to_string(track_data.get("artists", []))
        album = None
        album_obj = track_data.get("album")
        if isinstance(album_obj, dict):
            album = album_obj.get("name")
        duration = track_data.get("duration_ms")
        artwork = None
        if isinstance(album_obj, dict):
            images = album_obj.get("images", [])
            if images:
                artwork = images[0].get("url")
        query = f"ytsearch:{artists} - {name}".strip(" -")
        return ResolvedTrack(
            name=name, artists=artists, album=album, duration_ms=duration,
            artwork=artwork, spotify_id=track_id, youtube_id=None,
            query=query, source=source,
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


async def setup(bot):
    pass
