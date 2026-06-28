import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import time
import os
import random
import re
import json
import logging
import sys
from typing import Optional
import aiohttp
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
if not logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setLevel(logging.INFO)
    _h.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

from backend.utils.formatters import format_duration
from backend.cogs.music.spotify_down import SpotifyResolver, ResolvedTrack

from backend.cogs.music.ytdlp_source import YtDlpTrack, YtDlpPlaylist, YtDlpSearcher, MusicController, _web_search_youtube

def get_db():
    try:
        from backend.cogs.database.firebase_setup import db
        return db
    except Exception as e:
        logger.info(f"[FIREBASE LAZY IMPORT] {e}")
        return None


def _find_spotify_tracks_in_json(data, depth=0):
    """Recursively search parsed JSON for track-like entries."""
    if depth > 8:
        return []
    results = []

    if isinstance(data, dict):
        # Direct trackList key (covers SD-like format)
        tl = data.get('trackList') or data.get('tracks')
        if isinstance(tl, list) and len(tl) >= 1:
            for t in tl:
                tid = t.get('id') or t.get('uri', '').split(':')[-1] if isinstance(t.get('uri'), str) else ''
                title = t.get('title') or t.get('name') or ''
                artist = t.get('artist') or t.get('artists') or ''
                if isinstance(artist, list):
                    artist = ', '.join(
                        a.get('name', '') if isinstance(a, dict) else str(a) for a in artist
                    )
                cover = t.get('cover') or t.get('artwork') or ''
                if isinstance(cover, list):
                    cover = cover[0].get('url', '') if cover else ''
                duration = t.get('duration_ms') or t.get('duration')
                if tid or title:
                    results.append((tid, title, artist, cover, duration))

        # Spotify items in entity
        items = data.get('items')
        if isinstance(items, list) and len(items) >= 1:
            for it in items:
                if isinstance(it, dict) and 'track' in it:
                    t = it['track']
                    if isinstance(t, dict) and t.get('id'):
                        artists = ', '.join(a['name'] for a in t.get('artists', []) if isinstance(a, dict))
                        images = t.get('album', {}).get('images', [])
                        cover = images[0].get('url', '') if images else ''
                        results.append((
                            t['id'], t.get('name', ''),
                            artists, cover,
                            t.get('duration_ms'),
                        ))

        # Recurse into all values
        for v in data.values():
            results.extend(_find_spotify_tracks_in_json(v, depth + 1))

    elif isinstance(data, list):
        # Try items directly
        if len(data) > 1:
            for it in data:
                if isinstance(it, dict) and ('track' in it or 'id' in it):
                    t = it.get('track') or it
                    if isinstance(t, dict) and (t.get('id') or t.get('name')):
                        tid = t.get('id') or ''
                        title = t.get('name') or ''
                        artist_v = t.get('artist') or t.get('artists') or ''
                        if isinstance(artist_v, list):
                            artist_v = ', '.join(
                                a.get('name', '') if isinstance(a, dict) else str(a) for a in artist_v
                            )
                        cover = ''
                        albums = t.get('album')
                        if isinstance(albums, dict):
                            imgs = albums.get('images', [])
                            cover = imgs[0].get('url', '') if imgs else ''
                        results.append((
                            tid, title, artist_v, cover,
                            t.get('duration_ms'),
                        ))
                    break
        for item in data:
            results.extend(_find_spotify_tracks_in_json(item, depth + 1))

    return results


def _extract_tracks_from_scripts(script_contents):
    """Try to parse React state JSON from Spotify script tags."""
    known_vars = [
        'window.__INITIAL_STATE__',
        'window.__PRELOADED_STATE__',
        'window.__remixContext',
        'window.__spotify__',
        'window.__data__',
        'window.__STORE__',
    ]

    for content in script_contents:
        content = content.strip()

        # Try known variable patterns
        for var in known_vars:
            escaped_var = re.escape(var)
            m = re.search(rf'{escaped_var}\s*=\s*(\S.*)', content, re.DOTALL)
            if m:
                raw = m.group(1).rstrip(';').strip()
                try:
                    decoder = json.JSONDecoder()
                    data, _ = decoder.raw_decode(raw)
                    tracks = _find_spotify_tracks_in_json(data)
                    if len(tracks) >= 1:
                        return tracks
                except (json.JSONDecodeError, ValueError, StopIteration):
                    continue

        # Try parsing whole content as JSON
        if content.startswith('{') or content.startswith('['):
            try:
                decoder = json.JSONDecoder()
                data, _ = decoder.raw_decode(content)
                tracks = _find_spotify_tracks_in_json(data)
                if len(tracks) >= 1:
                    return tracks
            except (json.JSONDecodeError, ValueError, StopIteration):
                continue

    return []


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.controllers = {}
        self._spotify_enabled = True
        self._session: Optional[aiohttp.ClientSession] = None
        self.spotify = SpotifyResolver(
            fallback_client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            fallback_client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        )
        logger.info("[SPOTIFY] SpotifyDown API resolver aktif (fallback: Official API)")
        logger.info(f"[DEBUG SPOTIFY] Client ID Terdeteksi: {os.getenv('SPOTIFY_CLIENT_ID')[:5]}***" if os.getenv('SPOTIFY_CLIENT_ID') else "[DEBUG SPOTIFY] Client ID TIDAK DITEMUKAN!")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def get_controller(self, guild_id: int) -> MusicController:
        if guild_id not in self.controllers:
            vc = None
            for g in self.bot.guilds:
                if g.id == guild_id:
                    vc = g.voice_client
                    break
            self.controllers[guild_id] = MusicController(vc, cog=self)
        return self.controllers[guild_id]

    def get_music_player(self, guild_id: int):
        return self.get_controller(guild_id)

    # ==========================================================
    # SPOTIFY URL HELPERS
    # ==========================================================
    def _is_spotify_url(self, query: str) -> bool:
        return "open.spotify.com" in query or "spotify:" in query

    def _extract_spotify_id(self, url: str) -> tuple[str, str] | None:
        patterns = [
            (r'open\.spotify\.com/track/([a-zA-Z0-9]+)', 'track'),
            (r'open\.spotify\.com/playlist/([a-zA-Z0-9]+)', 'playlist'),
            (r'open\.spotify\.com/album/([a-zA-Z0-9]+)', 'album'),
            (r'open\.spotify\.com/artist/([a-zA-Z0-9]+)', 'artist'),
            (r'track/([a-zA-Z0-9]+)', 'track'),
            (r'playlist/([a-zA-Z0-9]+)', 'playlist'),
            (r'album/([a-zA-Z0-9]+)', 'album'),
            (r'artist/([a-zA-Z0-9]+)', 'artist'),
        ]
        for pattern, type_ in patterns:
            match = re.search(pattern, url)
            if match:
                return (type_, match.group(1))
        return None

    # ==========================================================
    # SEARCH via yt-dlp
    @staticmethod
    def _title_similarity(a: str, b: str) -> float:
        a = a.lower().strip()
        b = b.lower().strip()
        if not a or not b:
            return 0.0
        a_words = set(a.split())
        b_words = set(b.split())
        intersection = a_words & b_words
        union = a_words | b_words
        return len(intersection) / len(union) if union else 0.0

    async def _search_single_resolved(self, track: ResolvedTrack) -> YtDlpTrack | None:
        try:
            query = (track.query or "").strip()
            if query.startswith("http://") or query.startswith("https://"):
                try:
                    return await asyncio.wait_for(YtDlpSearcher.extract_info(query), timeout=20.0)
                except (asyncio.TimeoutError, Exception):
                    return None

            for prefix in ["ytsearch:", "ytmsearch:", "scsearch:", "spsearch:"]:
                if query.lower().startswith(prefix):
                    query = query[len(prefix):].strip()

            artists = track.artists or ""
            name = track.name or ""
            keywords = f"{artists} {name}".strip()
            if not query:
                query = keywords

            target_dur = track.duration_ms
            if not query:
                logger.info(f"[YOUTUBE SEARCH] Empty query for track {track.spotify_id}")
                return None

            # Coba beberapa variasi search, balikin hasil pertama yg lolos minimal threshold
            search_variations = []

            # 1. Query original (dengan artist + nama)
            search_variations.append(f"ytmsearch:{query}")

            # 2. Hanya nama lagu (tanpa artist) — kadang lebih akurat
            if name and artists and name not in query:
                search_variations.append(f"ytmsearch:{name}")

            # 3. Official audio / music video
            if artists:
                search_variations.append(f"ytmsearch:{artists} - {name} official audio")
                search_variations.append(f"ytmsearch:{artists} - {name} music video")

            # 4. Artist + name (jika query berbeda)
            if keywords and keywords != query:
                search_variations.append(f"ytmsearch:{keywords}")

            attempted = set()
            for sq in search_variations:
                if sq in attempted:
                    continue
                attempted.add(sq)
                try:
                    results = await asyncio.wait_for(
                        YtDlpSearcher.search(sq),
                        timeout=15.0,
                    )
                except (asyncio.TimeoutError, Exception):
                    continue
                if not results:
                    continue

                for r in results:
                    score = self._title_similarity(f"{artists} {name}", f"{r.author or ''} {r.title or ''}")
                    dur_diff = abs((r.duration or 0) - (target_dur or 0)) if target_dur else 0
                    if score > 0.15 or not target_dur or dur_diff < 10000:
                        return r

            # Fallback terakhir: ytmsearch dengan nama aja, return apapun
            final_query = name or query
            try:
                results = await asyncio.wait_for(
                    YtDlpSearcher.search(f"ytmsearch:{final_query}"),
                    timeout=15.0,
                )
                if results:
                    return results[0]
            except (asyncio.TimeoutError, Exception):
                pass

            logger.info(f"[YOUTUBE SEARCH] All yt-dlp search failed for: {artists} - {name}, coba web scrape...")
            try:
                session = await self._get_session()
                video_url = await asyncio.wait_for(
                    _web_search_youtube(session, (name or query)),
                    timeout=10.0,
                )
                if video_url:
                    result = await asyncio.wait_for(
                        YtDlpSearcher.extract_info(video_url),
                        timeout=15.0,
                    )
                    if result:
                        return result
            except (asyncio.TimeoutError, Exception):
                pass
            logger.info(f"[YOUTUBE SEARCH] Web scrape also failed for: {artists} - {name}")
        except Exception as e:
            logger.info(f"[YOUTUBE SEARCH ERROR] {track.name}: {e}")
        return None

    async def _search_youtube_for_tracks_concurrent(
        self,
        tracks: list[ResolvedTrack],
        max_concurrent: int = 3,
    ) -> tuple[int, list[YtDlpTrack]]:
        added = 0
        playables: list[YtDlpTrack | None] = [None] * len(tracks)
        semaphore = asyncio.Semaphore(max_concurrent)

        async def search_and_queue(index: int, rt: ResolvedTrack):
            nonlocal added
            async with semaphore:
                playable = await self._search_single_resolved(rt)
                if playable:
                    playables[index] = playable
                    added += 1
                    return True
                return False

        tasks = [search_and_queue(i, t) for i, t in enumerate(tracks)]
        await asyncio.gather(*tasks, return_exceptions=True)
        return added, [p for p in playables if p is not None]

    # ==========================================================
    # HELPERS
    # ==========================================================
    def _progress_bar(self, current_ms: int, total_ms: int, length: int = 12) -> str:
        if total_ms == 0:
            return "🔴 LIVE"
        ratio = min(current_ms / total_ms, 1.0)
        filled = int(ratio * length)
        bar = "▬" * filled + "🔘" + "▬" * (length - filled - 1)
        return f"{bar} `{format_duration(current_ms)} / {format_duration(total_ms)}`"

    async def _alone_pause(self, controller: MusicController, home: discord.TextChannel | None):
        await asyncio.sleep(30)
        if controller and controller.vc and controller.vc.channel:
            humans = [m for m in controller.vc.channel.members if not m.bot]
            if not humans:
                try:
                    await controller.pause_for("alone")
                except Exception:
                    pass
                if home:
                    try:
                        await home.send("⏸️ Auto-paused — no one in voice channel")
                    except Exception:
                        pass

    def _cancel_alone_task(self, guild_id: int):
        mp = self.get_music_player(guild_id)
        mp._cancel_alone_timer()

    # ==========================================================
    # EVENTS
    # ==========================================================
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild_id = member.guild.id
        controller = self.controllers.get(guild_id)
        if not controller:
            return

        # Detect bot disconnect -> start connection recovery
        if member.id == self.bot.user.id:
            before_ch = before.channel
            after_ch = after.channel
            if before_ch and not after_ch and not controller._stopped:
                if controller.current_track:
                    logger.info(f"[RECOVERY] Bot disconnected from {before_ch.name}, attempting recovery")
                    controller._recovery_task = asyncio.create_task(
                        controller._connection_recovery(before_ch)
                    )
            return

        if not controller.vc or not controller.vc.channel:
            return

        vc = controller.vc.channel
        humans = [m for m in vc.members if not m.bot]

        if not humans:
            if controller._alone_task is None or controller._alone_task.done():
                controller._alone_task = asyncio.create_task(self._alone_pause(controller, getattr(controller, 'home', None)))
        else:
            self._cancel_alone_task(guild_id)
            # Auto-resume if was paused for being alone
            if controller._pause_reason == "alone":
                await controller.resume_for("manual")

    def _check_owner(self, ctx: commands.Context) -> bool:
        controller = self.get_controller(ctx.guild.id)
        if controller._owner_id is not None and controller._owner_id != ctx.author.id:
            owner = ctx.guild.get_member(controller._owner_id)
            name = owner.display_name if owner else "another user"
            ctx.command_failed = True
            raise commands.CommandError(f"Hanya **{name}** yang bisa mengontrol musik saat ini.")
        return True

    # ==========================================================
    # COMMANDS
    # ==========================================================
    @commands.hybrid_command(name="play", description="Putar lagu dari URL atau search query", aliases=["p"])
    @app_commands.describe(query="URL (YouTube/Spotify/SoundCloud) atau nama lagu", channel="Voice channel tujuan (opsional, default: channel kamu sekarang)")
    async def play(
        self,
        ctx: commands.Context,
        query: str,
        channel: Optional[discord.VoiceChannel] = None,
    ):
        logger.info(f"[PLAY CMD] Called by {ctx.author} with query: {query}")
        await ctx.defer()

        vc = channel or (ctx.author.voice.channel if ctx.author.voice else None)
        if not vc:
            await ctx.send("❌ Kamu harus join voice channel dulu!")
            return

        voice_client = ctx.guild.voice_client
        if not voice_client:
            logger.info("[PLAY CMD] Creating new player...")
            try:
                voice_client = await vc.connect(self_deaf=False)
            except Exception as e:
                logger.info(f"[PLAY CMD] Connect error: {e}")
                await ctx.send(f"❌ Gagal connect ke voice: {e}")
                return
        elif voice_client.channel != vc:
            logger.info("[PLAY CMD] Moving to new channel...")
            try:
                await voice_client.move_to(vc, self_deaf=False)
            except Exception as e:
                logger.info(f"[PLAY CMD] Move error: {e}")
                await ctx.send(f"❌ Gagal pindah channel: {e}")
                return

        guild_id = ctx.guild.id
        controller = self.get_controller(guild_id)
        controller.vc = voice_client
        controller.home = ctx.channel

        # Set owner hanya sekali (saat pertama bot connect)
        if controller._owner_id is None:
            controller._owner_id = ctx.author.id
            logger.info(f"[PLAY CMD] Owner set: {ctx.author} (ID: {ctx.author.id})")

        # Only owner can add tracks or hijack the session
        if controller.current_track and controller._owner_id != ctx.author.id:
            await ctx.send(f"❌ Hanya <@{controller._owner_id}> yang bisa menambah lagu saat ini.", ephemeral=True)
            return

        logger.info(f"[PLAY CMD] Player ready. Current: {controller.current_track}")
        search_query = query.strip()

        # ==========================================================
        # HANDLE SPOTIFY URL
        # ==========================================================
        if self._is_spotify_url(search_query):
            spotify_info = self._extract_spotify_id(search_query)
            if not spotify_info:
                await ctx.send("❌ URL Spotify tidak valid.")
                return
            spotify_type, spotify_id = spotify_info
            logger.info(f"[SPOTIFY] Detected {spotify_type} with ID: {spotify_id}")

            loading_msg = await ctx.send(
                f"🎵 Mengambil metadata Spotify ({spotify_type}) via SpotifyDown API..."
            )

            session = await self._get_session()
            resolved_tracks, source = await self.spotify.resolve(search_query, session)

            if not resolved_tracks:
                await loading_msg.edit(
                    content=(
                        "❌ Gagal mengambil metadata dari Spotify.\n"
                        "SpotifyDown API sedang down dan fallback ke Spotify Official juga gagal.\n"
                        "Coba lagi nanti atau gunakan URL YouTube langsung."
                    )
                )
                return

            source_emoji = {
                "spotifydown": "🟢",
                "spotify_official": "🟡",
                "ytsearch": "🟠",
            }.get(source, "⚪")

            # SINGLE TRACK
            if spotify_type == "track":
                rt = resolved_tracks[0]
                logger.info(f"[SPOTIFY TRACK] Resolved via {source} | Query: {rt.query}")

                clean_query = rt.query
                for prefix in ["ytsearch:", "ytmsearch:", "scsearch:", "spsearch:"]:
                    if clean_query.lower().startswith(prefix):
                        clean_query = clean_query[len(prefix):].strip()

                try:
                    tracks = await asyncio.wait_for(
                        YtDlpSearcher.search(f"ytmsearch:{clean_query}"),
                        timeout=30.0,
                    )
                except asyncio.TimeoutError:
                    logger.info("[SPOTIFY TRACK] YouTube search timeout (30s), coba web scrape...")
                    await loading_msg.edit(content="⏳ Search timeout, coba metode alternatif...")
                    session = await self._get_session()
                    video_url = await asyncio.wait_for(
                        _web_search_youtube(session, clean_query),
                        timeout=12.0,
                    )
                    if video_url:
                        track = await asyncio.wait_for(
                            YtDlpSearcher.extract_info(video_url),
                            timeout=15.0,
                        )
                        if track:
                            tracks = [track]
                        else:
                            await loading_msg.edit(content="❌ Lagu tidak ditemukan di YouTube.")
                            return
                    else:
                        await loading_msg.edit(content="❌ Gagal mencari lagu di YouTube. Coba link langsung.")
                        return
                except Exception as e:
                    logger.info(f"[SPOTIFY TRACK ERROR] {e}")
                    await loading_msg.edit(content=f"❌ Gagal mencari lagu di YouTube.\n`{e}`")
                    return

                if not tracks:
                    await loading_msg.edit(content="❌ Lagu tidak ditemukan di YouTube.")
                    return

                track = tracks[0]
                controller.queue.append(track)
                if not controller.current_track:
                    await controller.set_volume(100)
                    await asyncio.sleep(0.3)
                    next_track = controller.queue.pop(0)
                    await controller.play(next_track)

                embed = discord.Embed(
                    title=f"{source_emoji} Added from Spotify",
                    description=f"[{track.title}]({track.uri})",
                    color=discord.Color.green(),
                )
                artwork = rt.artwork or track.artwork
                if artwork:
                    embed.set_thumbnail(url=artwork)
                embed.set_footer(text=f"Source: {source} | Spotify ID: {rt.spotify_id}")

                await loading_msg.edit(content=None, embed=embed)
                return

            # PLAYLIST / ALBUM
            else:
                original_total_tracks = len(resolved_tracks)

                if original_total_tracks <= 1 and source in ("oembed", "html_scrape", "failed"):
                    rebuilt = []

                    # 1) Coba extract JSON dari halaman Spotify (React state)
                    logger.info(f"[SPOTIFY FALLBACK] Semua primary source gagal (source={source}), coba extract JSON dari page...")
                    await loading_msg.edit(content="⏳ Membaca playlist Spotify...")
                    try:
                        html_headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Language": "en-US,en;q=0.5",
                        }
                        async with session.get(search_query, headers=html_headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                            if resp.status == 200:
                                html = await resp.text()
                                logger.info(f"[SPOTIFY FALLBACK] Page fetched OK ({len(html)} bytes)")

                                # Extract all script content and try to parse Spotify React state JSON
                                script_contents = re.findall(
                                    r'<script[^>]*>(.*?)</script>',
                                    html,
                                    re.DOTALL | re.IGNORECASE,
                                )

                                found_tracks = _extract_tracks_from_scripts(script_contents)

                                if found_tracks:
                                    logger.info(f"[SPOTIFY FALLBACK] Found {len(found_tracks)} tracks via JSON parsing")
                                    seen_ids = set()
                                    for tid, title, artist, cover, duration_ms in found_tracks:
                                        if not title:
                                            continue
                                        if tid and tid in seen_ids:
                                            continue
                                        seen_ids.add(tid)
                                        q = f"ytmsearch:{artist} - {title}" if artist and artist not in ("Unknown", "Spotify") else f"ytmsearch:{title}"
                                        rebuilt.append(ResolvedTrack(
                                            name=title,
                                            artists=artist or "Unknown",
                                            album=None,
                                            duration_ms=duration_ms,
                                            artwork=cover,
                                            spotify_id=tid,
                                            youtube_id=None,
                                            query=q,
                                            source="json_scrape",
                                        ))
                    except Exception as e:
                        logger.info(f"[SPOTIFY FALLBACK] JSON extract error (non-fatal): {e}")

                    # 2) Jika JSON gagal, coba regex track ID + oEmbed
                    if len(rebuilt) <= 1:
                        logger.info("[SPOTIFY FALLBACK] JSON gagal, coba regex + oEmbed...")
                        try:
                            async with session.get(search_query, headers=html_headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                                if resp.status == 200:
                                    html = await resp.text()
                                    track_ids = list(dict.fromkeys(re.findall(r'(?:spotify:track:|/track/)([A-Za-z0-9]+)', html)))
                                    if track_ids:
                                        logger.info(f"[SPOTIFY FALLBACK] Found {len(track_ids)} track IDs via regex")
                                        sem = asyncio.Semaphore(5)
                                        async def fetch_oembed(tid):
                                            async with sem:
                                                try:
                                                    async with session.get(f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{tid}", timeout=aiohttp.ClientTimeout(total=8)) as r:
                                                        if r.status == 200:
                                                            d = await r.json()
                                                            title = d.get("title", "").strip()
                                                            artist = d.get("author_name", "").strip()
                                                            if title:
                                                                q = f"ytmsearch:{artist} - {title}" if artist and artist != "Spotify" else f"ytmsearch:{title}"
                                                                return ResolvedTrack(name=title, artists=artist or "Unknown", album=None, duration_ms=None, artwork=d.get("thumbnail_url"), spotify_id=tid, youtube_id=None, query=q, source="scrape_oembed")
                                                except Exception:
                                                    pass
                                                return None
                                        oembed_results = await asyncio.gather(*[fetch_oembed(tid) for tid in track_ids])
                                        rebuilt = [rt for rt in oembed_results if rt is not None]
                                        logger.info(f"[SPOTIFY FALLBACK] Regex + oEmbed: {len(rebuilt)} tracks resolved")
                        except Exception as e:
                            logger.info(f"[SPOTIFY FALLBACK] Regex scrape error: {e}")

                    # 3) Jika semua gagal, coba yt-dlp extractor dengan timeout
                    if len(rebuilt) <= 1:
                        logger.info("[SPOTIFY FALLBACK] Semua scrape gagal, coba yt-dlp (timeout 20s)...")
                        await loading_msg.edit(content="⏳ Mencoba yt-dlp...")
                        try:
                            yt_playlist = await asyncio.wait_for(YtDlpSearcher.extract_playlist(search_query), timeout=20.0)
                            if yt_playlist and yt_playlist.tracks and len(yt_playlist.tracks) > 1:
                                rebuilt = []
                                for t in yt_playlist.tracks:
                                    raw = getattr(t, '_ydl_info', {}) or {}
                                    artists = raw.get('artist') or raw.get('creators') or raw.get('uploader') or ''
                                    if isinstance(artists, list):
                                        artists = ', '.join(filter(None, artists))
                                    name = raw.get('title') or t.title or 'Unknown'
                                    tid = raw.get('id') or t.uri or ''
                                    rt_q = f"ytmsearch:{artists} - {name}" if artists else f"ytmsearch:{name}"
                                    rebuilt.append(ResolvedTrack(name=name, artists=artists or 'Unknown', album=yt_playlist.name, duration_ms=None, artwork=t.artwork or '', spotify_id=tid, youtube_id=None, query=rt_q, source="ytdlp_extractor"))
                                logger.info(f"[SPOTIFY FALLBACK] yt-dlp berhasil: {len(rebuilt)} tracks")
                        except asyncio.TimeoutError:
                            logger.info("[SPOTIFY FALLBACK] yt-dlp timeout")
                        except Exception as e:
                            logger.info(f"[YTDLP FALLBACK ERROR] {e}")

                    if len(rebuilt) > 1:
                        resolved_tracks = rebuilt
                        source = "json_scrape"
                        original_total_tracks = len(resolved_tracks)
                        logger.info(f"[SPOTIFY FALLBACK] ✅ Total {original_total_tracks} tracks resolved via {source}")
                        await loading_msg.edit(content=f"📋 Berhasil memuat `{original_total_tracks}` lagu dari Spotify, sedang mencari di YouTube...")
                    else:
                        await loading_msg.edit(content="❌ Gagal mengambil daftar lagu dari Spotify. Coba link YouTube langsung.")
                        return

                # Simpen semua resolved tracks buat auto-load nanti
                controller._playlist_url = search_query
                controller._playlist_tracks = resolved_tracks  # all tracks
                controller._playlist_index = 0
                controller._playlist_total = original_total_tracks
                # Search batch pertama (100)
                batch = resolved_tracks[:100]
                total_tracks = len(batch)
                resolved_tracks = batch
                logger.info(f"[SPOTIFY {spotify_type.upper()}] {original_total_tracks} total, batch pertama {total_tracks} via {source}")

                # spotify_down → YouTube search concurrent (15 paralel)
                total_ms = sum(t.duration_ms or 0 for t in resolved_tracks)
                total_duration = format_duration(total_ms) if total_ms > 0 else "Unknown"

                thumbnail = None
                for t in resolved_tracks:
                    if t.artwork:
                        thumbnail = t.artwork
                        break

                await loading_msg.edit(content=f"⏳ Mencari {total_tracks} lagu di YouTube... (0/{total_tracks})")

                playables: list[Optional[YtDlpTrack]] = [None] * total_tracks
                sem = asyncio.Semaphore(15)

                async def load_one(index: int, rt: ResolvedTrack):
                    async with sem:
                        playables[index] = await self._search_single_resolved(rt)
                    if (index + 1) % 5 == 0 or index == total_tracks - 1:
                        done = sum(1 for p in playables if p is not None)
                        try:
                            await loading_msg.edit(content=f"⏳ Mencari {total_tracks} lagu di YouTube... ({done}/{total_tracks})")
                        except Exception:
                            pass

                await asyncio.gather(*[load_one(i, rt) for i, rt in enumerate(resolved_tracks)])

                valid = [p for p in playables if p is not None]
                if not valid:
                    await loading_msg.edit(content="❌ Gagal menemukan satupun lagu dari playlist ini di YouTube.")
                    return

                first_track = valid[0]
                controller.queue.extend(valid[1:])

                if not controller.current_track:
                    await controller.set_volume(100)
                    await asyncio.sleep(0.3)
                    await controller.play(first_track)
                else:
                    controller.queue.insert(0, first_track)

                playlist_name = resolved_tracks[0].album or f"Spotify {spotify_type.title()}"
                skipped = total_tracks - len(valid)

                final_embed = discord.Embed(
                    description=f"📁 **{playlist_name}**",
                    color=discord.Color.from_rgb(29, 185, 84)
                )
                final_embed.set_author(
                    name=f"🎶 Added to Queue ({spotify_type.title()})",
                    icon_url=ctx.author.display_avatar.url
                )
                final_embed.add_field(name="🔢 Jumlah Lagu", value=f"`{total_tracks}` lagu" + (" (Dibatasi 100)" if original_total_tracks > 100 else ""), inline=True)
                final_embed.add_field(name="⏳ Total Durasi", value=f"`{total_duration}`", inline=True)
                final_embed.add_field(name="👤 Request Oleh", value=ctx.author.mention, inline=True)
                if thumbnail:
                    final_embed.set_thumbnail(url=thumbnail)
                status_text = f"▶️ Sekarang Memutar: {first_track.title[:35]}..."
                if skipped:
                    status_text += f"\n⚠️ {skipped} lagu tidak ditemukan di YouTube"
                final_embed.set_footer(
                    text=status_text,
                    icon_url=self.bot.user.display_avatar.url
                )

                await loading_msg.edit(content=None, embed=final_embed)
                return

        # ==========================================================
        # HANDLE URL LANGSUNG (YouTube, SoundCloud, etc.)
        # ==========================================================
        is_url = search_query.startswith("http://") or search_query.startswith("https://")

        if is_url:
            logger.info(f"[PLAY CMD] Direct URL detected: {search_query}")

            is_playlist_url = (
                "/playlist?" in search_query.lower() or
                "list=" in search_query.lower() or
                "soundcloud.com/" in search_query.lower() and "/sets/" in search_query.lower()
            )

            if is_playlist_url:
                playlist = await asyncio.wait_for(
                    YtDlpSearcher.extract_playlist(search_query),
                    timeout=30.0,
                )
                if playlist and playlist.tracks:
                    added = 0
                    for t in playlist.tracks[:100]:
                        controller.queue.append(t)
                        added += 1
                    logger.info(f"[PLAY CMD] Added {added} tracks from playlist: {playlist.name}")
                    if not controller.current_track and controller.queue:
                        await controller.set_volume(100)
                        await asyncio.sleep(0.3)
                        next_track = controller.queue.pop(0)
                        await controller.play(next_track)
                    
                    msg = f"✅ Playlist ditambahkan! ({added} lagu dari {playlist.name})"
                    if len(playlist.tracks) > 100:
                        msg += " (Dibatasi 100)"
                    await ctx.send(msg)
                    return
                else:
                    await ctx.send("❌ Gagal memuat playlist.")
                    return

            try:
                track = await asyncio.wait_for(YtDlpSearcher.extract_info(search_query), timeout=30.0)
            except asyncio.TimeoutError:
                await ctx.send("❌ Timeout memuat lagu (30s).")
                return
            if track:
                controller.queue.append(track)
                if not controller.current_track:
                    await controller.set_volume(100)
                    await asyncio.sleep(0.3)
                    next_track = controller.queue.pop(0)
                    await controller.play(next_track)
                embed = discord.Embed(
                    title="✅ Added to Queue",
                    description=f"[{track.title}]({track.uri})",
                    color=discord.Color.blue(),
                )
                if track.artwork:
                    embed.set_thumbnail(url=track.artwork)
                await ctx.send(embed=embed)
                return
            else:
                await ctx.send("❌ Gagal memproses URL.")
                return

        # ==========================================================
        # HANDLE SEARCH QUERY (atau URL yang bukan playlist)
        # ==========================================================
        # Jika bukan URL playlist, kita anggap sebagai search query
        clean_input = search_query
        
        # Cek apakah ini sebenarnya search query yang disamarkan (misal: "ytsearch:...")
        prefixes = ["ytsearch:", "ytmsearch:", "scsearch:", "spsearch:"]
        for p in prefixes:
            if clean_input.lower().startswith(p):
                clean_input = clean_input[len(p):].strip()

        logger.info(f"[PLAY CMD] Searching/Processing: {clean_input}")
        try:
            # Kita coba search dengan prefix ytsearch agar lebih stabil
            tracks = await asyncio.wait_for(
                YtDlpSearcher.search(f"ytmsearch:{clean_input}"),
                timeout=30.0,
            )
            logger.info(f"[PLAY CMD] Search returned: count: {len(tracks) if tracks else 0}")
        except asyncio.TimeoutError:
            logger.info("[PLAY CMD] SEARCH TIMEOUT after 30s")
            await ctx.send("⏱️ Search timeout (30s). Coba lagi atau gunakan query lain.")
            return
        except Exception as e:
            logger.info(f"[PLAY CMD] SEARCH ERROR: {type(e).__name__}: {e}")
            await ctx.send(f"❌ Gagal mencari lagu: `{e}`")
            return

        if not tracks:
            logger.info("[PLAY CMD] No tracks found")
            await ctx.send("❌ Lagu tidak ditemukan.")
            return

        # Ambil lagu pertama sebagai hasil pencarian
        track = tracks[0]
        logger.info(f"[PLAY CMD] Playing track: {track.title}")
        controller.queue.append(track)
        
        if not controller.current_track:
            await controller.set_volume(100)
            await asyncio.sleep(0.3)
            next_track = controller.queue.pop(0)
            await controller.play(next_track)
        else:
            embed = discord.Embed(
                title="✅ Added to Queue",
                description=f"[{track.title}]({track.uri})",
                color=discord.Color.blue(),
            )
            if track.artwork:
                embed.set_thumbnail(url=track.artwork)
            await ctx.send(embed=embed)
            return


    @commands.hybrid_command(name="pause", description="Pause lagu yang sedang diputar")
    async def pause(self, ctx: commands.Context):
        if not self._check_owner(ctx):
            return
        voice_client = ctx.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            await ctx.send("❌ Tidak ada lagu yang sedang diputar.", ephemeral=True)
            return
        voice_client.pause()
        controller = self.get_controller(ctx.guild.id)
        controller._paused = True
        controller._paused_position = time.time() - controller._start_time
        await controller._update_now_playing()
        await ctx.send("⏸️ Pause")

    @commands.hybrid_command(name="resume", description="Lanjutkan lagu yang di-pause")
    async def resume(self, ctx: commands.Context):
        if not self._check_owner(ctx):
            return
        voice_client = ctx.guild.voice_client
        if not voice_client or not voice_client.is_paused():
            await ctx.send("❌ Tidak ada lagu yang di-pause.", ephemeral=True)
            return
        voice_client.resume()
        controller = self.get_controller(ctx.guild.id)
        controller._paused = False
        controller._start_time = time.time() - controller._paused_position
        await controller._update_now_playing()
        await ctx.send("▶️ Resume")

    @commands.hybrid_command(name="skip", description="Skip ke lagu berikutnya")
    async def skip(self, ctx: commands.Context):
        if not self._check_owner(ctx):
            return
        controller = self.get_controller(ctx.guild.id)
        voice_client = ctx.guild.voice_client
        if not voice_client or not controller.current_track:
            await ctx.send("❌ Tidak ada lagu yang sedang diputar.", ephemeral=True)
            return
        skipped = controller.current_track
        voice_client.stop()
        if controller.queue:
            await ctx.send(
                f"⏭️ Skipped: **{skipped.title}**"
            )
        else:
            await ctx.send(
                f"⏭️ Skipped: **{skipped.title}** | Queue kosong."
            )

    @commands.hybrid_command(name="stop", description="Stop lagu, clear queue, keluar voice channel")
    async def stop(self, ctx: commands.Context):
        if not self._check_owner(ctx):
            return
        controller = self.get_controller(ctx.guild.id)
        voice_client = ctx.guild.voice_client
        if not voice_client:
            await ctx.send("❌ Bot tidak ada di voice channel.", ephemeral=True)
            return
        await controller.stop()
        await ctx.send("⏹️ Music player dihentikan dan queue di-clear.")

    @commands.hybrid_command(name="queue", description="Lihat antrian lagu")
    async def queue(self, ctx: commands.Context):
        try:
            await ctx.defer()
        except Exception:
            pass
        controller = self.get_controller(ctx.guild.id)
        voice_client = ctx.guild.voice_client
        if not voice_client:
            await ctx.send("📭 Queue kosong.")
            return

        if not controller.home:
            controller.home = ctx.channel
        await controller._update_now_playing()

        embed = discord.Embed(title="🎶 Music Queue", color=discord.Color.purple())

        try:
            if controller.current_track:
                loop_emoji = {"single": "🔁", "queue": "🔂", "off": ""}.get(controller.loop_mode, "")
                title = controller.current_track.title or "Unknown"
                embed.add_field(
                    name=f"▶️ Now Playing {loop_emoji}",
                    value=f"**{title}**\n`{format_duration(controller.current_track.duration)}`",
                    inline=False,
                )

            items = controller.queue
            if items:
                total_ms = sum(t.duration or 0 for t in items)
                queue_text = ""
                for i, track in enumerate(items[:15], 1):
                    t_title = track.title or "Unknown"
                    duration = format_duration(track.duration) if track.duration else "?"
                    display = t_title[:40]
                    if len(t_title) > 40:
                        display += "..."
                    queue_text += f"`{i:02d}.` {display} (`{duration}`)\n"

                embed.add_field(name="⏭️ Up Next", value=queue_text or "...", inline=False)
                embed.set_footer(text=f"{len(items)} lagu | Total durasi: {format_duration(total_ms)}")
            else:
                embed.set_footer(text="Queue kosong — tambah lagu dengan /play")
        except Exception as e:
            logger.info(f"[QUEUE ERROR] {e}")
            await ctx.send("❌ Gagal menampilkan queue.")
            return

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="nowplaying", description="Info detail lagu yang sedang diputar")
    async def nowplaying(self, ctx: commands.Context):
        controller = self.get_controller(ctx.guild.id)
        voice_client = ctx.guild.voice_client
        if not voice_client or not controller.current_track:
            await ctx.send("❌ Tidak ada lagu yang sedang diputar.", ephemeral=True)
            return

        try:
            await ctx.defer(ephemeral=True)
        except Exception:
            pass

        if not controller.home:
            controller.home = ctx.channel
        await controller._update_now_playing()
        await ctx.send("▶️ Cek pesan **Now Playing** di atas untuk info lengkap.", ephemeral=True)

    @commands.hybrid_command(name="volume", description="Atur volume bot (0-1000)")
    @app_commands.describe(level="Volume level 0-1000 (default 100)")
    async def volume(self, ctx: commands.Context, level: int):
        if not self._check_owner(ctx):
            return
        if not 0 <= level <= 1000:
            await ctx.send("❌ Volume harus antara 0-1000.", ephemeral=True)
            return
        voice_client = ctx.guild.voice_client
        if not voice_client:
            await ctx.send("❌ Bot tidak ada di voice channel.", ephemeral=True)
            return
        controller = self.get_controller(ctx.guild.id)
        await controller.set_volume(level)
        await ctx.send(f"🔊 Volume diatur ke **{level}%**.")

    @commands.hybrid_command(name="loop", description="Atur mode loop lagu/queue")
    @app_commands.describe(mode="Pilih mode loop")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Single (Lagu Ini)", value="single"),
        app_commands.Choice(name="Queue (Semua Lagu)", value="queue"),
    ])
    async def loop(self, ctx: commands.Context, mode: app_commands.Choice[str]):
        if not self._check_owner(ctx):
            return
        controller = self.get_controller(ctx.guild.id)
        controller.loop_mode = mode.value
        if mode.value == "queue":
            controller._queue_history.clear()
        if mode.value == "off":
            controller._single_loop_track = None
        await ctx.send(f"🔁 Loop mode: **{mode.name}**")

    @commands.hybrid_command(name="shuffle", description="Acak antrian lagu")
    async def shuffle(self, ctx: commands.Context):
        if not self._check_owner(ctx):
            return
        controller = self.get_controller(ctx.guild.id)
        if not controller.queue:
            await ctx.send("📭 Queue kosong, tidak ada yang bisa diacak.", ephemeral=True)
            return
        random.shuffle(controller.queue)
        controller._queue_history.clear()
        await ctx.send(f"🔀 Queue diacak! ({len(controller.queue)} lagu)")

    @commands.hybrid_command(name="autoplay", description="Toggle autoplay: bot cari lagu serupa ketika queue habis")
    async def autoplay(self, ctx: commands.Context):
        if not self._check_owner(ctx):
            return
        controller = self.get_controller(ctx.guild.id)
        controller.autoplay = not controller.autoplay
        status = "ON ✅" if controller.autoplay else "OFF ❌"
        await ctx.send(f"🤖 Autoplay sekarang: **{status}**")

    @commands.hybrid_command(name="seek", description="Skip ke posisi tertentu dalam lagu")
    @app_commands.describe(position="Format: 1:30 atau 90 (detik)")
    async def seek(self, ctx: commands.Context, position: str):
        if not self._check_owner(ctx):
            return
        controller = self.get_controller(ctx.guild.id)
        voice_client = ctx.guild.voice_client
        if not voice_client or not controller.current_track:
            await ctx.send("❌ Tidak ada lagu yang sedang diputar.", ephemeral=True)
            return
        total_seconds = 0
        try:
            if ':' in position:
                parts = position.split(':')
                if len(parts) == 2:
                    total_seconds = int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 3:
                    total_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            else:
                total_seconds = int(position)
        except ValueError:
            await ctx.send("❌ Format salah. Gunakan `1:30` atau `90`.", ephemeral=True)
            return
        ms = total_seconds * 1000
        if controller.current_track.duration and ms > controller.current_track.duration:
            await ctx.send("❌ Posisi melebihi durasi lagu.", ephemeral=True)
            return

        await controller.seek(ms)
        await ctx.send(f"⏩ Skip ke `{format_duration(ms)}`.")

    @commands.hybrid_command(name="remove", description="Hapus lagu dari queue berdasarkan nomor")
    @app_commands.describe(index="Nomor lagu di /queue")
    async def remove(self, ctx: commands.Context, index: int):
        if not self._check_owner(ctx):
            return
        controller = self.get_controller(ctx.guild.id)
        if not controller.queue:
            await ctx.send("📭 Queue kosong.", ephemeral=True)
            return
        if index < 1:
            await ctx.send("❌ Nomor harus mulai dari 1.", ephemeral=True)
            return
        if index > len(controller.queue):
            await ctx.send(f"❌ Queue cuma ada {len(controller.queue)} lagu.", ephemeral=True)
            return
        async with controller._track_lock:
            removed = controller.queue.pop(index - 1)
        await ctx.send(f"🗑️ Dihapus dari queue: **{removed.title}**")

    @commands.hybrid_command(name="move", description="Pindah posisi lagu di queue")
    @app_commands.describe(from_index="Posisi asal", to_index="Posisi tujuan")
    async def move(self, ctx: commands.Context, from_index: int, to_index: int):
        if not self._check_owner(ctx):
            return
        controller = self.get_controller(ctx.guild.id)
        if not controller.queue:
            await ctx.send("📭 Queue kosong.", ephemeral=True)
            return
        if not (1 <= from_index <= len(controller.queue)) or not (1 <= to_index <= len(controller.queue)):
            await ctx.send(f"❌ Index harus antara 1 dan {len(controller.queue)}.", ephemeral=True)
            return
        async with controller._track_lock:
            track = controller.queue.pop(from_index - 1)
            controller.queue.insert(to_index - 1, track)
        await ctx.send(f"↔️ Dipindah: **{track.title}** ke posisi `{to_index}`")

    @commands.hybrid_command(name="skipto", description="Skip ke lagu nomor tertentu di queue")
    @app_commands.describe(index="Nomor lagu di /queue")
    async def skipto(self, ctx: commands.Context, index: int):
        if not self._check_owner(ctx):
            return
        controller = self.get_controller(ctx.guild.id)
        voice_client = ctx.guild.voice_client
        if not voice_client or not controller.queue:
            await ctx.send("📭 Queue kosong.", ephemeral=True)
            return
        if not (1 <= index <= len(controller.queue)):
            await ctx.send(f"❌ Index harus antara 1 dan {len(controller.queue)}.", ephemeral=True)
            return
        async with controller._track_lock:
            target = controller.queue.pop(index - 1)
            controller.queue.insert(0, target)
        voice_client.stop()
        await ctx.send(f"⏭️ Skip ke: **{target.title}**")

    @commands.hybrid_command(name="disconnect", description="Keluar dari voice channel")
    async def disconnect(self, ctx: commands.Context):
        if not self._check_owner(ctx):
            return
        controller = self.get_controller(ctx.guild.id)
        voice_client = ctx.guild.voice_client
        if not voice_client:
            await ctx.send("❌ Bot tidak di voice channel.", ephemeral=True)
            return
        await controller.disconnect()
        await ctx.send("🔌 Keluar dari voice channel.")

    @commands.hybrid_command(name="clearqueue", description="Kosongkan queue tanpa menghentikan lagu yang sedang diputar")
    async def clearqueue(self, ctx: commands.Context):
        if not self._check_owner(ctx):
            return
        controller = self.get_controller(ctx.guild.id)
        if not controller.queue:
            await ctx.send("📭 Queue sudah kosong.", ephemeral=True)
            return
        controller.queue.clear()
        controller._queue_history.clear()
        await ctx.send("🧹 Queue dikosongkan. Lagu yang sedang diputar tetap jalan.")

    @commands.hybrid_command(name="replay", description="Putar ulang lagu dari awal")
    async def replay(self, ctx: commands.Context):
        if not self._check_owner(ctx):
            return
        controller = self.get_controller(ctx.guild.id)
        voice_client = ctx.guild.voice_client
        if not voice_client or not controller.current_track:
            await ctx.send("❌ Tidak ada lagu yang sedang diputar.", ephemeral=True)
            return
        await controller.play(controller.current_track)
        await ctx.send("🔁 Replay dari awal.")

    @commands.hybrid_command(name="lyrics", description="Cari lirik lagu yang sedang diputar atau dari judul")
    @app_commands.describe(query="Judul lagu (opsional, default: lagu yang sedang diputar)")
    async def lyrics(self, ctx: commands.Context, query: str = None):
        if not query:
            controller = self.get_controller(ctx.guild.id)
            if controller.current_track:
                query = f"{controller.current_track.title} {controller.current_track.author or ''}"
        if not query:
            await ctx.send("❌ Tidak ada lagu yang diputar. Berikan judul!")
            return
        await ctx.defer()
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://lrclib.net/api/search?q={query.strip().replace(' ', '%20')}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        await ctx.send("❌ Lirik tidak ditemukan.")
                        return
                    data = await resp.json()
            if not data:
                await ctx.send("❌ Lirik tidak ditemukan.")
                return
            song = data[0]
            title = song.get('trackName', 'Unknown')
            artist = song.get('artistName', 'Unknown')
            plain = song.get('plainLyrics', 'Tidak ada lirik tersedia.')
            if len(plain) > 3900:
                plain = plain[:3900] + "\n..."
            embed = discord.Embed(
                title=f"🎤 {title}",
                description=f"by **{artist}**\n\n```{plain}```",
                color=discord.Color.pink(),
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logger.info(f"[LYRICS ERROR] {e}")
            await ctx.send("❌ Gagal mengambil lirik. Coba judul lain.")

    # ==========================================================
    # PLAYLIST GROUP
    # ==========================================================
    @commands.group(name="playlist", description="Simpan dan muat playlist lagu")
    async def playlist(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Gunakan: `save`, `load`, `delete`, atau `list`")

    @playlist.command(name="save", description="Simpan queue saat ini sebagai playlist")
    @app_commands.describe(name="Nama playlist")
    async def playlist_save(self, ctx: commands.Context, name: str):
        db = get_db()
        if db is None:
            await ctx.send("❌ Fitur playlist tidak tersedia (Firebase tidak terhubung).", ephemeral=True)
            return
        controller = self.get_controller(ctx.guild.id)
        tracks = []
        if controller.current_track:
            tracks.append({
                "title": controller.current_track.title,
                "uri": controller.current_track.uri,
                "author": controller.current_track.author or "Unknown",
                "artwork": controller.current_track.artwork or "",
                "length": controller.current_track.duration or 0,
            })
        for track in controller.queue:
            tracks.append({
                "title": track.title,
                "uri": track.uri,
                "author": track.author or "Unknown",
                "artwork": track.artwork or "",
                "length": track.duration or 0,
            })
        if not tracks:
            await ctx.send("📭 Tidak ada lagu untuk disimpan.", ephemeral=True)
            return
        doc_id = f"{ctx.guild.id}_{ctx.author.id}_{name}"
        get_db().collection("playlists").document(doc_id).set({
            "guild_id": str(ctx.guild.id),
            "user_id": str(ctx.author.id),
            "name": name,
            "tracks": tracks,
            "created_at": datetime.now(timezone.utc),
        })
        await ctx.send(f"💾 Playlist **{name}** disimpan! ({len(tracks)} lagu)")

    @playlist.command(name="load", description="Muat playlist ke queue")
    @app_commands.describe(name="Nama playlist")
    async def playlist_load(self, ctx: commands.Context, name: str):
        db = get_db()
        if db is None:
            await ctx.send("❌ Fitur playlist tidak tersedia (Firebase tidak terhubung).", ephemeral=True)
            return
        await ctx.defer()
        doc_id = f"{ctx.guild.id}_{ctx.author.id}_{name}"
        doc = get_db().collection("playlists").document(doc_id).get()
        if not doc.exists:
            await ctx.send(f"❌ Playlist **{name}** tidak ditemukan.")
            return
        data = doc.to_dict()
        track_data = data.get("tracks", [])
        if not track_data:
            await ctx.send("📭 Playlist kosong.")
            return
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ Kamu harus join voice channel dulu!")
            return
        vc = ctx.author.voice.channel
        voice_client = ctx.guild.voice_client
        if not voice_client:
            voice_client = await vc.connect(self_deaf=False)
            controller = self.get_controller(ctx.guild.id)
            controller.vc = voice_client
            controller.home = ctx.channel
        elif voice_client.channel != vc:
            await voice_client.move_to(vc, self_deaf=False)

        controller = self.get_controller(ctx.guild.id)
        added = 0
        failed = 0
        semaphore = asyncio.Semaphore(5)

        async def load_single_track(t):
            nonlocal added, failed
            async with semaphore:
                try:
                    track = await YtDlpSearcher.extract_info(t['uri'])
                    if track:
                        return track
                except Exception as e:
                    logger.info(f"[PLAYLIST CONCURRENT LOAD ERROR] {e}")
                return None

        tasks = [load_single_track(t) for t in track_data]
        playables = await asyncio.gather(*tasks)

        for p in playables:
            if p:
                controller.queue.append(p)
                added += 1
            else:
                failed += 1

        if not controller.current_track and controller.queue:
            await controller.set_volume(100)
            await asyncio.sleep(0.3)
            next_track = controller.queue.pop(0)
            await controller.play(next_track)

        msg = f"📂 Playlist **{name}** dimuat! ({added} lagu ditambahkan)"
        if failed:
            msg += f" | {failed} gagal dimuat"
        await ctx.send(msg)

    @playlist.command(name="list", description="Lihat daftar playlist-mu")
    async def playlist_list(self, ctx: commands.Context):
        db = get_db()
        if db is None:
            await ctx.send("❌ Fitur playlist tidak tersedia (Firebase tidak terhubung).", ephemeral=True)
            return
        playlists = (get_db().collection("playlists")
            .where("guild_id", "==", str(ctx.guild.id))
            .where("user_id", "==", str(ctx.author.id))
            .stream())
        embed = discord.Embed(title="📂 Playlist-mu", color=discord.Color.blue())
        count = 0
        for doc in playlists:
            data = doc.to_dict()
            track_count = len(data.get("tracks", []))
            created = data.get("created_at")
            if created:
                created_str = created.strftime("%Y-%m-%d %H:%M") if isinstance(created, datetime) else str(created)
            else:
                created_str = "Unknown"
            embed.add_field(name=data['name'], value=f"{track_count} lagu · {created_str}", inline=False)
            count += 1
        if count == 0:
            embed.description = "📭 Belum ada playlist. Gunakan `/playlist save` untuk membuat satu."
        await ctx.send(embed=embed)

    @playlist.command(name="delete", description="Hapus playlist")
    @app_commands.describe(name="Nama playlist yang mau dihapus")
    async def playlist_delete(self, ctx: commands.Context, name: str):
        db = get_db()
        if db is None:
            await ctx.send("❌ Fitur playlist tidak tersedia (Firebase tidak terhubung).", ephemeral=True)
            return
        doc_id = f"{ctx.guild.id}_{ctx.author.id}_{name}"
        doc_ref = get_db().collection("playlists").document(doc_id)
        doc = doc_ref.get()
        if not doc.exists:
            await ctx.send(f"❌ Playlist **{name}** tidak ditemukan.", ephemeral=True)
            return
        doc_ref.delete()
        await ctx.send(f"🗑️ Playlist **{name}** dihapus.")


    async def cog_unload(self):
        if self._session and not self._session.closed:
            await self._session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
