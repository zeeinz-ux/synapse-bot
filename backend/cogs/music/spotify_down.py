"""
Spotify resolver with resilient multi-fallback support.

Fallback chain:
    1. Spotify Official API (Client Credentials)
    2. SpotifyDown API (unofficial)
    3. Spotify public page scrape -> track IDs -> track oEmbed
    4. Spotify oEmbed / page metadata fallback
"""

import asyncio
import base64
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import aiohttp

logger = logging.getLogger(__name__)

SPOTIFYDOWN_BASE = "https://api.spotifydown.com"
SPOTIFY_URL_PATTERNS = [
    r"(?:https?://)?(?:open\.spotify\.com/(?:intl-[a-z]{2}/)?)?(?P<type>track|playlist|album)/(?P<id>[A-Za-z0-9]+)",
    r"spotify:(?P<type>track|playlist|album):(?P<id>[A-Za-z0-9]+)",
]
REQUEST_TIMEOUT = 15
MAX_RETRIES = 2
CONCURRENT_FETCH_LIMIT = 5


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
# SPOTIFYDOWN CLIENT (Unofficial)
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
                    method,
                    url,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                    **kwargs,
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()

                    if resp.status in (429, 502, 503):
                        await asyncio.sleep(2 ** attempt)
                        continue

                    body = await resp.text()
                    logger.error("SpotifyDown error %s pada %s | body=%s", resp.status, endpoint, body[:200])
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

            batch = data.get("trackList") or []
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

            batch = data.get("trackList") or []
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
# SPOTIFY OFFICIAL API (Fallback)
# ==========================================================
class SpotifyOfficialClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: Optional[str] = None
        self._token_expires = 0.0

    async def _get_token(self, session: aiohttp.ClientSession) -> Optional[str]:
        loop = asyncio.get_running_loop()
        if self._token and loop.time() < self._token_expires:
            return self._token

        try:
            creds = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            async with session.post(
                "https://accounts.spotify.com/api/token",
                headers={
                    "Authorization": f"Basic {creds}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error("[SPOTIFY AUTH] Token request failed HTTP %s | body=%s", resp.status, body[:250])
                    return None

                data = await resp.json()
                self._token = data["access_token"]
                self._token_expires = loop.time() + int(data.get("expires_in", 3600)) - 60
                return self._token
        except Exception as e:
            logger.error("[SPOTIFY AUTH] Exception: %s", e)
            return None

    async def get_playlist_tracks(self, session: aiohttp.ClientSession, playlist_id: str) -> List[Dict]:
        token = await self._get_token(session)
        if not token:
            return []

        tracks: List[Dict] = []
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
                        self._token = None
                        token = await self._get_token(session)
                        if not token:
                            break
                        continue

                    if resp.status != 200:
                        body = await resp.text()
                        
                        logger.error("[SPOTIFY DEBUG] URL=%s", url)
                        logger.error("[SPOTIFY DEBUG] STATUS=%s", resp.status)
                        logger.error("[SPOTIFY DEBUG] BODY=%s", body[:1000])
                        break

                    data = await resp.json()
                    for item in data.get("items", []):
                        track = item.get("track")
                        if track and track.get("id"):
                            tracks.append(track)

                    url = data.get("next")
                    params = {}
            except Exception as e:
                logger.error("[SPOTIFY AUTH] Exception saat fetch tracks: %s", e)
                break

        return tracks

    async def get_album_tracks(self, session: aiohttp.ClientSession, album_id: str) -> List[Dict]:
        token = await self._get_token(session)
        if not token:
            return []

        tracks: List[Dict] = []
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
                    if resp.status == 401:
                        self._token = None
                        token = await self._get_token(session)
                        if not token:
                            break
                        continue

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
# HELPERS
# ==========================================================
async def _get_spotify_metadata_oembed(
    session: aiohttp.ClientSession,
    url: str,
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
                    "artists": data.get("author_name") or data.get("provider_name", "Spotify"),
                    "artwork": data.get("thumbnail_url"),
                }
    except Exception as e:
        logger.error("oEmbed exception: %s", e)
    return None


async def _get_spotify_metadata_html(
    session: aiohttp.ClientSession,
    url: str,
) -> Optional[Dict]:
    try:
        async with session.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                html = await resp.text()
                title_match = re.search(r"<title>([^<]+)</title>", html, flags=re.IGNORECASE)
                if title_match:
                    title = title_match.group(1).replace(" | Spotify", "").strip()
                    return {"name": title, "artists": "Unknown", "artwork": None}
    except Exception as e:
        logger.error("HTML scrape exception: %s", e)
    return None


def _extract_track_ids_from_html(html: str) -> List[str]:
    """
    Best-effort extraction of track IDs from Spotify public page HTML.
    """
    patterns = [
        r'"uri":"spotify:track:([A-Za-z0-9]+)"',
        r'spotify:track:([A-Za-z0-9]+)',
        r'spotify%3Atrack%3A([A-Za-z0-9]+)',
        r'/track/([A-Za-z0-9]+)',
    ]

    seen = set()
    ordered_ids: List[str] = []

    for pattern in patterns:
        for track_id in re.findall(pattern, html, flags=re.IGNORECASE):
            if track_id not in seen:
                seen.add(track_id)
                ordered_ids.append(track_id)

    return ordered_ids


async def _get_spotify_track_oembed(
    session: aiohttp.ClientSession,
    track_id: str,
) -> Optional[Dict]:
    """
    Fetch track metadata from Spotify oEmbed using a track URL.
    """
    try:
        track_url = f"https://open.spotify.com/track/{track_id}"
        async with session.get(
            "https://open.spotify.com/oembed",
            params={"url": track_url},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()

                print("=" * 50)
                print(f"[OEMBED RAW] Track ID: {track_id}")
                print(data)
                print("=" * 50)
                
                title = (data.get("title") or "").strip()
                artist = (data.get("author_name") or data.get("provider_name") or "Spotify").strip()
                artwork = data.get("thumbnail_url")
                return {"title": title, "artist": artist, "artwork": artwork}
    except Exception as e:
        logger.error("Track oEmbed exception for %s: %s", track_id, e)
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
            logger.info("[SPOTIFY] SpotifyOfficialClient initialized: %s...", fallback_client_id[:8])
        else:
            self.official = None
            logger.warning("[SPOTIFY] SpotifyOfficialClient TIDAK diinisialisasi - env vars kosong!")

    @staticmethod
    def parse_url(url: str) -> Optional[Tuple[str, str]]:
        for pattern in SPOTIFY_URL_PATTERNS:
            m = re.search(pattern, url, flags=re.IGNORECASE)
            if m:
                return m.group("type").lower(), m.group("id")
        return None

    async def resolve(self, url: str, session: aiohttp.ClientSession) -> Tuple[List[ResolvedTrack], str]:
        parsed = self.parse_url(url)
        if not parsed:
            return [], "failed"

        content_type, content_id = parsed
        sd = SpotifyDownClient(session)

        try:
            if content_type == "playlist":
                tracks, source = await self._resolve_playlist(content_id, sd, session, url)
            elif content_type == "album":
                tracks, source = await self._resolve_album(content_id, sd, session, url)
            elif content_type == "track":
                tracks, source = await self._resolve_track(content_id, sd, session, url)
            else:
                return [], "failed"
        except Exception as e:
            logger.exception("[SPOTIFY RESOLVE] Unhandled exception: %s", e)
            return [], "failed"

        logger.info("[SPOTIFY RESOLVE] %d tracks resolved via %s", len(tracks), source)
        return tracks, source

    async def _resolve_playlist(
        self,
        playlist_id: str,
        sd: SpotifyDownClient,
        session: aiohttp.ClientSession,
        original_url: str,
    ) -> Tuple[List[ResolvedTrack], str]:
        # 1) Spotify Official API
        if self.official:
            raw = await self.official.get_playlist_tracks(session, playlist_id)
            if raw:
                return [self._track_to_resolved(t, t.get("id", ""), "spotify_official") for t in raw], "spotify_official"

        # 2) SpotifyDown API
        raw = await sd.get_playlist_tracks(playlist_id)
        if raw:
            return self._convert_sd_tracks(raw), "spotifydown"

        # 3) Best-effort scrape of public playlist page -> track IDs -> track oEmbed
        scraped_tracks = await self._resolve_public_page_track_ids(
            session=session,
            page_url=original_url,
            container_name="playlist",
            container_id=playlist_id,
        )
        if scraped_tracks:
            return scraped_tracks, "scrape_oembed"

        # 4) Playlist metadata only
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

    async def _resolve_album(
        self,
        album_id: str,
        sd: SpotifyDownClient,
        session: aiohttp.ClientSession,
        original_url: str,
    ) -> Tuple[List[ResolvedTrack], str]:
        # 1) Spotify Official API
        if self.official:
            raw = await self.official.get_album_tracks(session, album_id)
            if raw:
                return [self._track_to_resolved(t, t.get("id", ""), "spotify_official") for t in raw], "spotify_official"

        # 2) SpotifyDown API
        raw = await sd.get_album_tracks(album_id)
        if raw:
            return self._convert_sd_tracks(raw), "spotifydown"

        # 3) Public page scrape
        scraped_tracks = await self._resolve_public_page_track_ids(
            session=session,
            page_url=original_url,
            container_name="album",
            container_id=album_id,
        )
        if scraped_tracks:
            return scraped_tracks, "scrape_oembed"

        # 4) Album metadata only
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

        return [], "failed"

    async def _resolve_track(
        self,
        track_id: str,
        sd: SpotifyDownClient,
        session: aiohttp.ClientSession,
        original_url: str,
    ) -> Tuple[List[ResolvedTrack], str]:
        # 1) SpotifyDown direct mapping
        yt_id = await sd.get_youtube_id(track_id)
        if yt_id:
            return [
                ResolvedTrack(
                    name=track_id,
                    artists="",
                    album=None,
                    duration_ms=None,
                    artwork=None,
                    spotify_id=track_id,
                    youtube_id=yt_id,
                    query=f"https://youtube.com/watch?v={yt_id}",
                    source="spotifydown",
                )
            ], "spotifydown"

        # 2) Track oEmbed
        meta = await _get_spotify_track_oembed(session, track_id)
        if meta and meta.get("title"):
            return [
                ResolvedTrack(
                    name=meta["title"],
                    artists=meta["artist"],
                    album=None,
                    duration_ms=None,
                    artwork=meta.get("artwork"),
                    spotify_id=track_id,
                    youtube_id=None,
                    query=f"ytsearch:{meta['title']} {meta['artist']}",
                    source="oembed_track",
                )
            ], "oembed_track"

        # 3) Track page title fallback
        meta = await _get_spotify_metadata_oembed(session, original_url)
        if meta and meta.get("name"):
            return [
                ResolvedTrack(
                    name=meta["name"],
                    artists=meta["artists"],
                    album=None,
                    duration_ms=None,
                    artwork=meta.get("artwork"),
                    spotify_id=track_id,
                    youtube_id=None,
                    query=f"ytsearch:{meta['name']} {meta['artists']}",
                    source="oembed",
                )
            ], "oembed"

        return [], "failed"

    async def _resolve_public_page_track_ids(
        self,
        session: aiohttp.ClientSession,
        page_url: str,
        container_name: str,
        container_id: str,
    ) -> List[ResolvedTrack]:
        """
        Best-effort scrape:
        - download public Spotify page HTML
        - collect track IDs
        - resolve each track via track oEmbed
        """
        try:
            async with session.get(
                page_url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=aiohttp.ClientTimeout(total=12),
            ) as resp:
                if resp.status != 200:
                    return []

                html = await resp.text()
        except Exception as e:
            logger.error("[SPOTIFY SCRAPE] Failed to fetch %s page: %s", container_name, e)
            return []

        track_ids = _extract_track_ids_from_html(html)
        if not track_ids:
            return []

        semaphore = asyncio.Semaphore(CONCURRENT_FETCH_LIMIT)
        resolved: List[Optional[ResolvedTrack]] = [None] * len(track_ids)

        async def worker(index: int, track_id: str) -> None:
            async with semaphore:
                meta = await _get_spotify_track_oembed(session, track_id)
                if meta and meta.get("title"):
                    title = meta["title"]
                    artist = meta["artist"]
                    artwork = meta.get("artwork")
                else:
                    title = f"Spotify Track {track_id}"
                    artist = "Spotify"
                    artwork = None

                resolved[index] = ResolvedTrack(
                    name=title,
                    artists=artist,
                    album=container_id if container_name == "album" else None,
                    duration_ms=None,
                    artwork=artwork,
                    spotify_id=track_id,
                    youtube_id=None,
                    query=f"ytsearch:{artist} {title}",
                    source="scrape_oembed",
                )

        await asyncio.gather(*(worker(i, tid) for i, tid in enumerate(track_ids)))

        # type ignore not needed; filter None entries while preserving order
        return [track for track in resolved if track is not None]

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

        query = f"ytsearch:{artists} - {name}".strip()

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
            joined = ", ".join(filter(None, names))
            return joined if joined else "Unknown"
        return str(artists) if artists else "Unknown"


async def setup(bot):
    # utility module only
    return
