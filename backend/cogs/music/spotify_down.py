"""
Spotify resolver — User OAuth2 refresh token primary, embed scrape as fallback.

Auth priority:
    1. User OAuth2 Refresh Token (SPOTIFY_USER_REFRESH_TOKEN) — bypasses Sandbox 403
    2. Spotify Official API (Client Credentials — works for tracks, 403 for playlists)
    3. Spotify Embed page scrape -> JSON state -> track titles/artists directly
    4. Spotify oEmbed metadata (playlist name only, no individual tracks)

Embed page URL: https://open.spotify.com/embed/{type}/{id}
This page is designed for iframes and contains track data in <script> JSON.
"""

import asyncio
import base64
import json
import logging
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import aiohttp

logger = logging.getLogger(__name__)
if not logger.handlers and not logging.getLogger().handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setLevel(logging.DEBUG)
    _h.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

SPOTIFY_URL_PATTERNS = [
    r"(?:https?://)?(?:open\.spotify\.com/(?:intl-[a-z]{2}/)?)?(?P<type>track|playlist|album|artist)/(?P<id>[A-Za-z0-9]+)",
    r"spotify:(?P<type>track|playlist|album|artist):(?P<id>[A-Za-z0-9]+)",
]
REQUEST_TIMEOUT = 10


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

    def to_clean_dict(self, status: int = 200, message: str = "Track successfully resolved") -> dict:
        if self.duration_ms:
            minutes = int((self.duration_ms / 1000) // 60)
            seconds = int((self.duration_ms / 1000) % 60)
            readable_dur = f"{minutes:02d}:{seconds:02d}"
        else:
            readable_dur = "00:00"

        return {
            "status": status,
            "message": message,
            "source_api": self.source,
            "track_details": {
                "id": self.spotify_id,
                "title": self.name,
                "artist": self.artists,
                "album": self.album if self.album else "Single",
                "duration_ms": self.duration_ms,
                "readable_duration": readable_dur,
                "artwork_url": self.artwork,
            },
            "search_query": {
                "engine": "youtube",
                "raw_query": self.query,
            },
        }


# ==========================================================
# EMBED PAGE SCRAPER — extracts track metadata from JSON in <script> tags
# ==========================================================
def _find_tracks_in_json(data: Any, depth: int = 0) -> List[Tuple[str, str, str, str, Optional[int]]]:
    """Recursively search parsed JSON for track-like entries.
    Returns list of (track_id, title, artist, artwork_url, duration_ms)."""
    if depth > 8:
        return []
    results: List[Tuple[str, str, str, str, Optional[int]]] = []

    if isinstance(data, dict):
        # Direct trackList / tracks key
        tl = data.get("trackList") or data.get("tracks")
        if isinstance(tl, list):
            for t in tl:
                tid = t.get("id") or ""
                title = t.get("title") or t.get("name") or ""
                artist = t.get("artist") or t.get("artists") or ""
                if isinstance(artist, list):
                    artist = ", ".join(
                        a.get("name", "") if isinstance(a, dict) else str(a) for a in artist
                    )
                if not artist and isinstance(t, dict):
                    for k in ("author", "creator", "uploader", "channel"):
                        v = t.get(k)
                        if v:
                            artist = str(v) if isinstance(v, str) else ", ".join(
                                x.get("name", "") if isinstance(x, dict) else str(x) for x in (v if isinstance(v, list) else [v])
                            ) if v else ""
                            if artist:
                                break
                cover = t.get("cover") or t.get("artwork") or ""
                if isinstance(cover, list):
                    cover = cover[0].get("url", "") if cover else ""
                duration = t.get("duration_ms") or t.get("duration")
                if tid or title:
                    results.append((tid, title, artist, cover, duration))

        # Spotify items (Official API format page: {items: [{track: {...}}]})
        items = data.get("items")
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and "track" in it:
                    t = it["track"]
                    if isinstance(t, dict) and t.get("id"):
                        artists = ", ".join(
                            a["name"] for a in t.get("artists", []) if isinstance(a, dict)
                        )
                        if not artists:
                            for k in ("author", "creator", "uploader", "channel"):
                                v = t.get(k)
                                if v:
                                    artists = str(v) if isinstance(v, str) else ", ".join(
                                        x.get("name", "") if isinstance(x, dict) else str(x) for x in (v if isinstance(v, list) else [v])
                                    )
                                    if artists:
                                        break
                        images = t.get("album", {}).get("images", [])
                        cover = images[0].get("url", "") if images else ""
                        results.append((
                            t["id"], t.get("name", ""),
                            artists, cover,
                            t.get("duration_ms"),
                        ))

        # Recurse into all dict values
        for v in data.values():
            results.extend(_find_tracks_in_json(v, depth + 1))

    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and ("track" in item or "id" in item):
                t = item.get("track") or item
                if isinstance(t, dict) and (t.get("id") or t.get("name")):
                    tid = t.get("id") or ""
                    title = t.get("name") or ""
                    artist_v = t.get("artist") or t.get("artists") or ""
                    if isinstance(artist_v, list):
                        artist_v = ", ".join(
                            a.get("name", "") if isinstance(a, dict) else str(a) for a in artist_v
                        )
                    cover = ""
                    if isinstance(t.get("album"), dict):
                        imgs = t["album"].get("images", [])
                        cover = imgs[0].get("url", "") if imgs else ""
                    results.append((
                        tid, title, artist_v, cover,
                        t.get("duration_ms"),
                    ))
                    break
            results.extend(_find_tracks_in_json(item, depth + 1))

    return results


def _extract_tracks_from_scripts(script_contents: List[str]) -> List[Tuple[str, str, str, str, Optional[int]]]:
    """Parse React state JSON from Spotify embed script tags."""
    known_vars = [
        "window.__INITIAL_STATE__",
        "window.__PRELOADED_STATE__",
        "window.__remixContext",
        "window.__spotify__",
        "window.__data__",
        "window.__STORE__",
    ]

    for content in script_contents:
        content = content.strip()

        # Try known variable patterns
        for var in known_vars:
            m = re.search(re.escape(var) + r"\s*=\s*(\S.*)", content, re.DOTALL)
            if m:
                raw = m.group(1).rstrip(";").strip()
                try:
                    decoder = json.JSONDecoder()
                    data, _ = decoder.raw_decode(raw)
                    tracks = _find_tracks_in_json(data)
                    if len(tracks) >= 1:
                        logger.debug(
                            "[SPOTIFY JSON] Matched %s -> %d tracks from %d bytes",
                            var, len(tracks), len(raw[:200]),
                        )
                        return tracks
                except (json.JSONDecodeError, ValueError):
                    continue

        # Try parsing whole content as JSON
        if content.startswith("{") or content.startswith("["):
            try:
                decoder = json.JSONDecoder()
                data, _ = decoder.raw_decode(content)
                tracks = _find_tracks_in_json(data)
                if len(tracks) >= 1:
                    return tracks
            except (json.JSONDecodeError, ValueError):
                continue

    return []


async def _scrape_embed_page(
    session: aiohttp.ClientSession,
    content_type: str,
    content_id: str,
) -> Optional[List[Dict]]:
    """Fetch Spotify embed page and extract track list from embedded JSON.
    Returns list of {title, artist, artwork, spotify_id} or None."""
    embed_url = f"https://open.spotify.com/embed/{content_type}/{content_id}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        async with session.get(
            embed_url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=12),
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                logger.warning("[SPOTIFY EMBED] HTTP %s on %s", resp.status, embed_url)
                return None

            html = await resp.text()
            if len(html) < 2000:
                logger.warning(
                    "[SPOTIFY EMBED] Page too small (%d bytes), likely blocked",
                    len(html),
                )
                return None

            logger.info("[SPOTIFY EMBED] Fetched OK (%d bytes)", len(html))

            script_contents = re.findall(
                r"<script[^>]*>(.*?)</script>",
                html,
                re.DOTALL | re.IGNORECASE,
            )

            found = _extract_tracks_from_scripts(script_contents)
            if not found:
                logger.warning("[SPOTIFY EMBED] No track data found in scripts")
                return None

            logger.info("[SPOTIFY EMBED] Extracted %d tracks", len(found))
            if found:
                sample = found[0]
                logger.info(
                    "[SPOTIFY EMBED] Sample track: tid=%s title=%s artist=%s",
                    sample[0], sample[1][:40], sample[2][:40],
                )
            return [
                {
                    "spotify_id": tid,
                    "title": title,
                    "artist": artist,
                    "artwork": artwork,
                    "duration_ms": duration_ms,
                }
                for tid, title, artist, artwork, duration_ms in found
                if title
            ]

    except asyncio.TimeoutError:
        logger.error("[SPOTIFY EMBED] Timeout fetching %s", embed_url)
    except Exception as e:
        logger.error("[SPOTIFY EMBED] Exception: %s", e)

    return None


# ==========================================================
# SPOTIFY OFFICIAL API
# ==========================================================
class SpotifyOfficialClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: Optional[str] = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._token: Optional[str] = None
        self._token_expires = 0.0
        if refresh_token:
            logger.info(
                "[SPOTIFY AUTH] User OAuth2 refresh token tersedia — akan bypass Sandbox 403"
            )

    async def _get_token(self, session: aiohttp.ClientSession) -> Optional[str]:
        if self._token and asyncio.get_running_loop().time() < self._token_expires:
            return self._token
        try:
            creds = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()

            if self.refresh_token:
                grant_type = "refresh_token"
                data_payload = {
                    "grant_type": grant_type,
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                }
                logger.info("[SPOTIFY AUTH] Requesting user-authorized token via refresh_token")
            else:
                grant_type = "client_credentials"
                data_payload = {"grant_type": grant_type}
                logger.info("[SPOTIFY AUTH] Requesting client credentials token (Sandbox)")

            async with session.post(
                "https://accounts.spotify.com/api/token",
                headers={
                    "Authorization": f"Basic {creds}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=data_payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._token = data["access_token"]
                    self._token_expires = (
                        asyncio.get_running_loop().time()
                        + int(data.get("expires_in", 3600))
                        - 60
                    )
                    logger.info(
                        "[SPOTIFY AUTH] Token %s obtained (expires in %s sec)",
                        grant_type,
                        data.get("expires_in", 3600),
                    )
                    return self._token
                else:
                    body = await resp.text()
                    logger.error(
                        "[SPOTIFY AUTH] HTTP %s on %s: %s",
                        resp.status,
                        grant_type,
                        body[:200],
                    )
        except Exception as e:
            logger.error("[SPOTIFY AUTH] Exception: %s", e)
        return None

    async def get_track(self, session: aiohttp.ClientSession, track_id: str) -> Optional[Dict]:
        token = await self._get_token(session)
        if not token:
            return None
        async with session.get(
            f"https://api.spotify.com/v1/tracks/{track_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                return await resp.json()
        return None

    async def get_playlist_tracks(
        self, session: aiohttp.ClientSession, playlist_id: str
    ) -> List[Dict]:
        token = await self._get_token(session)
        if not token:
            return []
        url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks?limit=50"
        items: List[Dict] = []
        while url:
            try:
                async with session.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 401:
                        self._token = None
                        token = await self._get_token(session)
                        if not token:
                            break
                        continue
                    if resp.status != 200:
                        logger.error(
                            "[SPOTIFY OFFICIAL] %s on %s",
                            resp.status,
                            url.split("?")[0],
                        )
                        break
                    data = await resp.json()
                    for item in data.get("items", []):
                        t = item.get("track") if isinstance(item, dict) else item
                        if isinstance(t, dict) and t.get("id"):
                            items.append(t)
                    if len(items) >= 100:
                        return items[:100]
                    url = data.get("next")
            except asyncio.TimeoutError:
                logger.error("[SPOTIFY OFFICIAL] Timeout fetching: %s", url.split("?")[0])
                break
            except Exception as e:
                logger.error("[SPOTIFY OFFICIAL] Exception: %s", e)
                break
        return items

    async def get_album_tracks(
        self, session: aiohttp.ClientSession, album_id: str
    ) -> List[Dict]:
        token = await self._get_token(session)
        if not token:
            return []
        items: List[Dict] = []
        url = f"https://api.spotify.com/v1/albums/{album_id}/tracks?limit=50"
        while url:
            try:
                async with session.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=aiohttp.ClientTimeout(total=10),
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
                    items.extend(data.get("items", []))
                    url = data.get("next")
            except Exception:
                break
        return items

    async def get_artist_top_tracks(
        self, session: aiohttp.ClientSession, artist_id: str
    ) -> List[Dict]:
        token = await self._get_token(session)
        if not token:
            return []
        try:
            async with session.get(
                f"https://api.spotify.com/v1/artists/{artist_id}/top-tracks",
                params={"market": "US"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("tracks", [])[:10]
        except Exception:
            pass
        return []


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
                    "artists": data.get("author_name")
                    or data.get("provider_name", "Spotify"),
                    "artwork": data.get("thumbnail_url"),
                }
    except Exception as e:
        logger.error("oEmbed exception: %s", e)
    return None


async def _get_spotify_track_oembed(
    session: aiohttp.ClientSession,
    track_id: str,
) -> Optional[Dict]:
    try:
        track_url = f"https://open.spotify.com/track/{track_id}"
        async with session.get(
            "https://open.spotify.com/oembed",
            params={"url": track_url},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
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
        user_refresh_token: Optional[str] = None,
    ):
        if fallback_client_id and fallback_client_secret:
            self.official = SpotifyOfficialClient(
                fallback_client_id,
                fallback_client_secret,
                refresh_token=user_refresh_token,
            )
            if user_refresh_token:
                logger.info("[SPOTIFY] User OAuth2 client initialized: %s...", fallback_client_id[:8])
            else:
                logger.info("[SPOTIFY] Official API client initialized: %s...", fallback_client_id[:8])
        else:
            self.official = None
            logger.warning("[SPOTIFY] Official API TIDAK diinisialisasi")

    @staticmethod
    def parse_url(url: str) -> Optional[Tuple[str, str]]:
        for pattern in SPOTIFY_URL_PATTERNS:
            m = re.search(pattern, url, flags=re.IGNORECASE)
            if m:
                return m.group("type").lower(), m.group("id")
        return None

    async def resolve(
        self, url: str, session: aiohttp.ClientSession
    ) -> Tuple[List[ResolvedTrack], str]:
        parsed = self.parse_url(url)
        if not parsed:
            return [], "failed"

        content_type, content_id = parsed

        if content_type == "track":
            return await self._resolve_track(content_id, session, url)
        if content_type == "playlist":
            return await self._resolve_playlist(content_id, session, url)
        if content_type == "album":
            return await self._resolve_album(content_id, session, url)
        if content_type == "artist":
            return await self._resolve_artist(content_id, session, url)

        return [], "failed"

    async def _resolve_track(
        self,
        track_id: str,
        session: aiohttp.ClientSession,
        original_url: str,
    ) -> Tuple[List[ResolvedTrack], str]:
        # 1) Official API
        if self.official:
            data = await self.official.get_track(session, track_id)
            if data:
                logger.info("[SPOTIFY TRACK] Official API: %s", data.get("name", track_id))
                return [self._track_to_resolved(data, track_id, "official_api")], "official_api"

        # 2) oEmbed fallback
        meta = await _get_spotify_track_oembed(session, track_id)
        if meta and meta.get("title"):
            logger.info("[SPOTIFY TRACK] oEmbed: %s - %s", meta["artist"], meta["title"])
            return [
                ResolvedTrack(
                    name=meta["title"],
                    artists=meta["artist"],
                    album=None,
                    duration_ms=None,
                    artwork=meta.get("artwork"),
                    spotify_id=track_id,
                    youtube_id=None,
                    query=(
                        f"ytmsearch:{meta['artist']} - {meta['title']}"
                        if meta.get("artist") and meta["artist"] != "Spotify"
                        else f"ytmsearch:{meta['title']}"
                    ),
                    source="oembed_track",
                )
            ], "oembed_track"

        # 3) Embed page scrape
        embed_data = await _scrape_embed_page(session, "track", track_id)
        if embed_data:
            t = embed_data[0]
            q = (
                f"ytmsearch:{t['artist']} - {t['title']}"
                if t["artist"]
                else f"ytmsearch:{t['title']}"
            )
            return [
                ResolvedTrack(
                    name=t["title"],
                    artists=t["artist"] or "Unknown",
                    album=None,
                    duration_ms=t.get("duration_ms"),
                    artwork=t.get("artwork"),
                    spotify_id=t["spotify_id"],
                    youtube_id=None,
                    query=q,
                    source="embed_scrape",
                )
            ], "embed_scrape"

        logger.error("[SPOTIFY TRACK] ALL sources failed for %s", track_id)
        return [], "failed"

    async def _resolve_playlist(
        self,
        playlist_id: str,
        session: aiohttp.ClientSession,
        original_url: str,
    ) -> Tuple[List[ResolvedTrack], str]:
        # 1) Official API
        if self.official:
            raw = await self.official.get_playlist_tracks(session, playlist_id)
            if raw:
                logger.info("[SPOTIFY RESOLVE] Official API: %d tracks", len(raw))
                return (
                    [self._track_to_resolved(t, t.get("id", ""), "spotify_official") for t in raw],
                    "spotify_official",
                )
            logger.warning("[SPOTIFY RESOLVE] Official API empty — fallthrough")

        # 2) Embed page scrape (primary method)
        embed_data = await _scrape_embed_page(session, "playlist", playlist_id)
        if embed_data:
            logger.info("[SPOTIFY RESOLVE] Embed scrape: %d tracks", len(embed_data))
            tracks = []
            for t in embed_data:
                q = (
                    f"ytmsearch:{t['artist']} - {t['title']}"
                    if t["artist"]
                    else f"ytmsearch:{t['title']}"
                )
                tracks.append(
                    ResolvedTrack(
                        name=t["title"],
                        artists=t["artist"] or "Unknown",
                        album=None,
                        duration_ms=t.get("duration_ms"),
                        artwork=t.get("artwork"),
                        spotify_id=t["spotify_id"],
                        youtube_id=None,
                        query=q,
                        source="embed_scrape",
                    )
                )
            return tracks, "embed_scrape"

        # 3) oEmbed — metadata only (no individual tracks)
        meta = await _get_spotify_metadata_oembed(session, original_url)
        if meta and meta.get("name"):
            logger.warning("[SPOTIFY RESOLVE] oEmbed fallback — metadata only")
            return [
                ResolvedTrack(
                    name=meta["name"],
                    artists=meta["artists"],
                    album=None,
                    duration_ms=None,
                    artwork=meta.get("artwork"),
                    spotify_id=playlist_id,
                    youtube_id=None,
                    query=f"ytmsearch:{meta['name']} {meta['artists']} playlist",
                    source="oembed",
                )
            ], "oembed"

        logger.error("[SPOTIFY RESOLVE] ALL sources failed for playlist %s", playlist_id)
        return [], "failed"

    async def _resolve_album(
        self,
        album_id: str,
        session: aiohttp.ClientSession,
        original_url: str,
    ) -> Tuple[List[ResolvedTrack], str]:
        # 1) Official API
        if self.official:
            raw = await self.official.get_album_tracks(session, album_id)
            if raw:
                logger.info("[SPOTIFY RESOLVE] Album Official API: %d tracks", len(raw))
                return (
                    [self._track_to_resolved(t, t.get("id", ""), "spotify_official") for t in raw],
                    "spotify_official",
                )

        # 2) Embed page scrape
        embed_data = await _scrape_embed_page(session, "album", album_id)
        if embed_data:
            logger.info("[SPOTIFY RESOLVE] Album embed scrape: %d tracks", len(embed_data))
            tracks = []
            for t in embed_data:
                q = (
                    f"ytmsearch:{t['artist']} - {t['title']}"
                    if t["artist"]
                    else f"ytmsearch:{t['title']}"
                )
                tracks.append(
                    ResolvedTrack(
                        name=t["title"],
                        artists=t["artist"] or "Unknown",
                        album=None,
                        duration_ms=t.get("duration_ms"),
                        artwork=t.get("artwork"),
                        spotify_id=t["spotify_id"],
                        youtube_id=None,
                        query=q,
                        source="embed_scrape",
                    )
                )
            return tracks, "embed_scrape"

        # 3) oEmbed
        meta = await _get_spotify_metadata_oembed(session, original_url)
        if meta and meta.get("name"):
            logger.warning("[SPOTIFY RESOLVE] Album oEmbed fallback — metadata only")
            return [
                ResolvedTrack(
                    name=meta["name"],
                    artists=meta["artists"],
                    album=meta["name"],
                    duration_ms=None,
                    artwork=meta.get("artwork"),
                    spotify_id=album_id,
                    youtube_id=None,
                    query=f"ytmsearch:{meta['name']} {meta['artists']} album",
                    source="oembed",
                )
            ], "oembed"

        logger.error("[SPOTIFY RESOLVE] ALL sources failed for album %s", album_id)
        return [], "failed"

    async def _resolve_artist(
        self,
        artist_id: str,
        session: aiohttp.ClientSession,
        original_url: str,
    ) -> Tuple[List[ResolvedTrack], str]:
        # 1) Official API
        if self.official:
            raw = await self.official.get_artist_top_tracks(session, artist_id)
            if raw:
                logger.info("[SPOTIFY RESOLVE] Artist Official API: %d tracks", len(raw))
                return (
                    [self._track_to_resolved(t, t.get("id", ""), "spotify_official") for t in raw],
                    "spotify_official",
                )

        # 2) oEmbed
        meta = await _get_spotify_metadata_oembed(session, original_url)
        if meta and meta.get("name"):
            artist_name = meta["name"]
            logger.info("[SPOTIFY RESOLVE] Artist oEmbed: %s", artist_name)
            return [
                ResolvedTrack(
                    name=f"{artist_name} - Top Tracks",
                    artists=artist_name,
                    album=None,
                    duration_ms=None,
                    artwork=meta.get("artwork"),
                    spotify_id=artist_id,
                    youtube_id=None,
                    query=f"ytmsearch:{artist_name} top tracks",
                    source="ytsearch",
                )
            ], "ytsearch"

        logger.error("[SPOTIFY RESOLVE] ALL sources failed for artist %s", artist_id)
        return [], "failed"

    @staticmethod
    def _track_to_resolved(track_data: Dict, track_id: str, source: str) -> ResolvedTrack:
        name = track_data.get("name", "Unknown")
        artists = SpotifyResolver._artists_to_string(track_data.get("artists", []))
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

        query = f"ytmsearch:{artists} - {name}".strip()
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
    return
