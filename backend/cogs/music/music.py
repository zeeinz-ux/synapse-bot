import discord
from discord.ext import commands
from discord import app_commands
import wavelink
import asyncio
import os
import random
import re
import aiohttp
from datetime import datetime, timezone

from backend.utils.formatters import format_duration
from backend.cogs.music.spotify_down import SpotifyResolver, ResolvedTrack
from backend.cogs.music.queue_manager import MusicPlayer

def get_db():
    try:
        from backend.cogs.database.firebase_setup import db
        return db
    except Exception as e:
        print(f"[FIREBASE LAZY IMPORT] {e}")
        return None

class MusicService:
    def __init__(self):
        self._spotify_enabled = True
        self.spotify = SpotifyResolver(
            fallback_client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            fallback_client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        )
        print("[SPOTIFY] SpotifyDown API resolver aktif (fallback: Official API)")
        print(f"[DEBUG SPOTIFY] Client ID Terdeteksi: {os.getenv('SPOTIFY_CLIENT_ID')[:5]}***" if os.getenv('SPOTIFY_CLIENT_ID') else "[DEBUG SPOTIFY] Client ID TIDAK DITEMUKAN!")

    # ==========================================================
    # SPOTIFY URL HELPERS
    # ==========================================================
    def _is_spotify_url(self, query: str) -> bool:
        # FIX: Menggunakan deteksi URL Spotify asli dan bentuk URI skema resmi
        return "open.spotify.com" in query or "spotify:" in query

    def _extract_spotify_id(self, url: str) -> tuple[str, str] | None:
        patterns = [
            (r'open\.spotify\.com/track/([a-zA-Z0-9]+)', 'track'),
            (r'open\.spotify\.com/playlist/([a-zA-Z0-9]+)', 'playlist'),
            (r'open\.spotify\.com/album/([a-zA-Z0-9]+)', 'album'),
            (r'track/([a-zA-Z0-9]+)', 'track'),
            (r'playlist/([a-zA-Z0-9]+)', 'playlist'),
            (r'album/([a-zA-Z0-9]+)', 'album'),
        ]
        for pattern, type_ in patterns:
            match = re.search(pattern, url)
            if match:
                return (type_, match.group(1))
        return None

    # ==========================================================
    # ASYNC CONCURRENT SEARCH (Updated untuk ResolvedTrack)
    # ==========================================================
    async def _search_single_resolved(self, track: ResolvedTrack) -> wavelink.Playable | None:
        """Search satu ResolvedTrack di YouTube/Lavalink tanpa double prefix."""
        try:
            # Ambil nama dan artis polosan
            artists = track.artists or ""
            name = track.name or ""
            
            if artists:
                clean_query = f"{artists} - {name}"
            else:
                clean_query = name

            # 🛠️ ANTI-DOUBLE PREFIX: Buang semua prefix bawaan scraper jika ada yang bocor
            for prefix in ["ytsearch:", "ytmsearch:", "scsearch:", "spsearch:"]:
                if clean_query.lower().startswith(prefix):
                    clean_query = clean_query[len(prefix):].strip()

            print(f"[YT SEARCH] {clean_query}")

            # Paksa pencarian menggunakan YouTube Music agar jauh lebih akurat
            results = await wavelink.Playable.search(clean_query, source=wavelink.TrackSource.YouTubeMusic)
            
            print("=" * 80)
            print(f"[YT RESULT TYPE] {type(results)}")
            print(f"[YT RESULT RAW] {results}")

            if results and len(results) > 0:
                print(f"[YT FOUND] {results[0].title}")
                return results[0]
            print(f"[YT NOT FOUND] {clean_query}")

        except Exception as e:
            print(f"[YOUTUBE SEARCH ERROR] {track.name}: {e}")
        return None
    
    async def _search_youtube_for_tracks_concurrent(
        self,
        tracks: list[ResolvedTrack],
        player: wavelink.Player,
        max_concurrent: int = 1,
    ) -> tuple[int, list[wavelink.Playable]]:
        """
        Search YouTube secara concurrent dengan semaphore.
        Returns: (added_count, list_of_playables)
        """
        added = 0
        playables: list[wavelink.Playable | None] = [None] * len(tracks)
        semaphore = asyncio.Semaphore(max_concurrent)

        async def search_and_queue(index: int, track: ResolvedTrack):
            nonlocal added
            async with semaphore:
                playable = await self._search_single_resolved(track)
                if playable:
                    playables[index] = playable
                    added += 1
                    return True
                return False

        tasks = [search_and_queue(i, t) for i, t in enumerate(tracks)]
        await asyncio.gather(*tasks, return_exceptions=True)
        return added, [p for p in playables if p is not None]

    async def resolve_spotify_track(self, search_query: str, interaction: discord.Interaction) -> wavelink.Playable | None:
        """Resolve Spotify track to wavelink playable."""
        spotify_info = self._extract_spotify_id(search_query)
        if not spotify_info:
            await interaction.followup.send("❌ URL Spotify tidak valid.")
            return None
        spotify_type, spotify_id = spotify_info
        print(f"[SPOTIFY] Detected {spotify_type} with ID: {spotify_id}")

        loading_msg = await interaction.followup.send(
            f"🎵 Mengambil metadata Spotify ({spotify_type}) via SpotifyDown API..."
        )

        async with aiohttp.ClientSession() as session:
            resolved_tracks, source = await self.spotify.resolve(search_query, session)

        if not resolved_tracks:
            await loading_msg.edit(
                content=(
                    "❌ Gagal mengambil metadata dari Spotify.\n"
                    "SpotifyDown API sedang down dan fallback ke Spotify Official juga gagal.\n"
                    "Coba lagi nanti atau gunakan URL YouTube langsung."
                )
            )
            return None

        source_emoji = {
            "spotifydown": "🟢",
            "spotify_official": "🟡",
            "ytsearch": "🟠",
        }.get(source, "⚪")

        if spotify_type == "track":
            rt = resolved_tracks[0]
            print(f"[SPOTIFY TRACK] Resolved via {source} | Query: {rt.query}")

            clean_query = rt.query
            for prefix in ["ytsearch:", "ytmsearch:", "scsearch:", "spsearch:"]:
                if clean_query.lower().startswith(prefix):
                    clean_query = clean_query[len(prefix):].strip()

            try:
                tracks = await wavelink.Playable.search(clean_query, source=wavelink.TrackSource.YouTubeMusic)
            except Exception as e:
                print(f"[SPOTIFY TRACK ERROR] {e}")
                await loading_msg.edit(content=f"❌ Gagal mencari lagu di YouTube.\n`{e}`")
                return None

            if not tracks:
                await loading_msg.edit(content="❌ Lagu tidak ditemukan di YouTube.")
                return None

            track = tracks[0]
            return track, source_emoji, rt, loading_msg

        return None, None, None, loading_msg

    async def resolve_spotify_playlist(self, search_query: str, interaction: discord.Interaction, player: wavelink.Player, loading_msg) -> tuple[list[wavelink.Playable], str, ResolvedTrack, discord.Embed]:
        """Resolve Spotify playlist to wavelink playables."""
        spotify_info = self._extract_spotify_id(search_query)
        if not spotify_info:
            await interaction.followup.send("❌ URL Spotify tidak valid.")
            return None, None, None, None
        spotify_type, spotify_id = spotify_info
        print(f"[SPOTIFY {spotify_type.upper()}] Resolving playlist...")

        async with aiohttp.ClientSession() as session:
            resolved_tracks, source = await self.spotify.resolve(search_query, session)

        if not resolved_tracks:
            await loading_msg.edit(
                content=(
                    "❌ Gagal mengambil metadata dari Spotify.\n"
                    "SpotifyDown API sedang down dan fallback ke Spotify Official juga gagal.\n"
                    "Coba lagi nanti atau gunakan URL YouTube langsung."
                )
            )
            return None, None, None, None

        source_emoji = {
            "spotifydown": "🟢",
            "spotify_official": "🟡",
            "ytsearch": "🟠",
        }.get(source, "⚪")

        total_tracks = len(resolved_tracks)
        print(f"[SPOTIFY {spotify_type.upper()}] {total_tracks} tracks resolved via {source}")

        total_ms = sum(t.duration_ms or 0 for t in resolved_tracks)
        total_duration = format_duration(total_ms) if total_ms > 0 else "Unknown"

        thumbnail = None
        for t in resolved_tracks:
            if t.artwork:
                thumbnail = t.artwork
                break

        first_track = None
        first_track_index = 0
        for i, rt in enumerate(resolved_tracks):
            first_track = await self._search_single_resolved(rt)
            if first_track:
                first_track_index = i
                break

        if not first_track:
            await loading_msg.edit(content="❌ Gagal menemukan satupun lagu dari playlist ini di YouTube.")
            return None, None, None, None

        remaining_resolved = resolved_tracks[first_track_index + 1:]

        if not player.current:
            await player.set_volume(100)
            await asyncio.sleep(0.3)
            await player.play(first_track)
        else:
            await player.queue.put_wait(first_track)

        async def bg_playlist_loader(player_obj, tracks_to_load):
            for rt_track in tracks_to_load:
                await asyncio.sleep(0.5)
                playable = await self._search_single_resolved(rt_track)
                if playable:
                    await player_obj.queue.put_wait(playable)
                    if not player_obj.current and player_obj.queue.count == 1:
                        try:
                            await player_obj.play(player_obj.queue.get())
                        except Exception:
                            pass

        asyncio.create_task(bg_playlist_loader(player, remaining_resolved))

        playlist_name = resolved_tracks[0].album or f"Spotify {spotify_type.title()}"

        final_embed = discord.Embed(
            description=f"📁 **{playlist_name}**",
            color=discord.Color.from_rgb(29, 185, 84)
        )

        final_embed.set_author(
            name=f"🎶 Added to Queue ({spotify_type.title()})",
            icon_url=interaction.user.display_avatar.url
        )

        final_embed.add_field(
            name="🔢 Jumlah Lagu",
            value=f"`{total_tracks} Lagu`",
            inline=True
        )
        final_embed.add_field(
            name="⏳ Total Durasi",
            value=f"`{total_duration}`",
            inline=True
        )
        final_embed.add_field(
            name="👤 Request Oleh",
            value=interaction.user.mention,
            inline=True
        )

        if thumbnail:
            final_embed.set_thumbnail(url=thumbnail)

        if player.current == first_track:
            status_text = f"▶️ Sekarang Memutar: {first_track.title[:35]}..."
        else:
            status_text = "📥 Dimasukkan ke ujung antrean"

        final_embed.set_footer(
            text=f"{status_text} | ⚡ Sisa lagu dimuat di background.",
            icon_url=interaction.guild.me.display_avatar.url
        )

        return [first_track] + [await self._search_single_resolved(rt) for rt in remaining_resolved if await self._search_single_resolved(rt)], source_emoji, resolved_tracks[0], final_embed

    async def search_and_queue_track(self, search_query: str, player: wavelink.Player) -> wavelink.Playable | None:
        """Search and queue a track from search query."""
        prefixes = ["ytsearch:", "ytmsearch:", "scsearch:", "spsearch:"]
        clean_input = search_query
        for p in prefixes:
            if clean_input.lower().startswith(p):
                clean_input = clean_input[len(p):].strip()

        if not (clean_input.startswith("http://") or clean_input.startswith("https://")):
            search_query = f"ytsearch:{clean_input}"
        else:
            search_query = clean_input

        print(f"[PLAY CMD] Searching Final Query: {search_query}")
        try:
            tracks = await asyncio.wait_for(wavelink.Playable.search(search_query), timeout=30.0)
        except Exception as e:
            print(f"[PLAY CMD] SEARCH ERROR: {type(e).__name__}: {e}")
            return None

        if not tracks:
            print("[PLAY CMD] No tracks found")
            return None

        if isinstance(tracks, wavelink.Playlist):
            print(f"[PLAY CMD] Playlist detected: {tracks.name} with {len(tracks.tracks)} tracks")
            added = 0
            for t in tracks.tracks:
                try:
                    await player.queue.put_wait(t)
                    added += 1
                except Exception as e:
                    print(f"[PLAY CMD] Queue put error: {e}")
                    break
            print(f"[PLAY CMD] Added {added} tracks to queue")
            if not player.current and not player.queue.is_empty:
                try:
                    first = player.queue.get()
                    print(f"[PLAY CMD] Starting playback with: {first.title}")
                    await player.set_volume(100)
                    await asyncio.sleep(0.3)
                    await player.play(first)
                except Exception as e:
                    print(f"[PLAY CMD] Play error: {e}")
            return tracks

        track = tracks[0] if hasattr(tracks, '__getitem__') else tracks
        print(f"[PLAY CMD] Single track: {track.title}")
        try:
            await player.queue.put_wait(track)
            print("[PLAY CMD] Track queued")
        except Exception as e:
            print(f"[PLAY CMD] Queue error: {e}")
            return None

        if not player.current:
            try:
                next_track = player.queue.get()
                print(f"[PLAY CMD] Starting playback: {next_track.title}")
                await player.set_volume(100)
                await asyncio.sleep(0.5)
                await player.play(next_track)
            except Exception as e:
                print(f"[PLAY CMD] Play error: {e}")
                return None

        return track

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players = {}
        self.music_service = MusicService()

    # ==========================================================
    # [POLISH] HELPERS
    # ==========================================================
    def _progress_bar(self, current_ms: int, total_ms: int, length: int = 12) -> str:
        if total_ms == 0:
            return "🔴 LIVE"
        ratio = min(current_ms / total_ms, 1.0)
        filled = int(ratio * length)
        bar = "▬" * filled + "🔘" + "▬" * (length - filled - 1)
        return f"{bar} `{format_duration(current_ms)} / {format_duration(total_ms)}`"

    async def _alone_disconnect(self, player: wavelink.Player, home: discord.TextChannel | None):
        await asyncio.sleep(30)
        if player and player.channel:
            humans = [m for m in player.channel.members if not m.bot]
            if not humans:
                await player.disconnect()
                if home:
                    try:
                        await home.send("👋 Keluar dari voice channel karena tidak ada user.")
                    except Exception:
                        pass

    def _cancel_alone_task(self, guild_id: int):
        mp = self.get_player(guild_id)
        if mp._alone_task and not mp._alone_task.done():
            mp._alone_task.cancel()
            mp._alone_task = None

    # ==========================================================
    # EVENTS
    # ==========================================================
    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        print(f"[LAVALINK] Node {payload.node.identifier} ready! (Session ID: {payload.session_id})")

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload):
        print(f"[LAVALINK EXCEPTION] Track: {payload.track.title} | Error: {payload.exception}")
        if payload.player and payload.player.home:
            try:
                await payload.player.home.send(f"❌ Error track: `{payload.exception}`")
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: wavelink.TrackStuckEventPayload):
        print(f"[LAVALINK STUCK] Track: {payload.track.title} | Threshold: {payload.threshold_ms}ms")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player = payload.player
        
        if player is None:
            print("[TRACK START] player is None")
            return
    
        if getattr(player, "guild", None) is None:
            print("[TRACK START] guild is None")
            return
        
        track = payload.track
        guild_id = player.guild.id
        mp = self.get_player(guild_id)

        track_id = getattr(track, 'identifier', track.title)
        now = asyncio.get_event_loop().time()
        if mp._last_track_id == track_id and (now - mp._last_embed_time) < 3.0:
            print(f"[TRACK START] Duplicate/cooldown suppressed: {track.title}")
            return
        mp._last_track_id = track_id
        mp._last_embed_time = now
        mp._single_loop_track = track
        if mp.loop_mode == "queue":
            mp._queue_history.append(track)
        embed = discord.Embed(
            title="Now Playing",
            description=f"[{track.title}]({track.uri})",
            color=discord.Color.green()
        )
        if track.author:
            embed.add_field(name="Author", value=track.author, inline=True)
        embed.add_field(name="Duration", value=format_duration(track.length), inline=True)
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
        if player.home:
            try:
                await player.home.send(embed=embed)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        guild_id = player.guild.id
        mp = self.get_player(guild_id)
        # FIX: Cast ke string dahulu agar aman jika tipe data aslinya adalah Enum objek
        reason = str(getattr(payload, 'reason', 'unknown')).lower()
        print(f"[TRACK END] reason={reason}, track={getattr(payload.track, 'title', 'unknown')}")
        if reason in ("stopped", "replaced", "cleanup"):
            print(f"[TRACK END] Ignoring reason={reason}, no auto-action")
            return
        async with mp._track_lock:
            if mp.loop_mode == "single" and mp._single_loop_track:
                await player.play(mp._single_loop_track)
                return
            if mp.loop_mode == "queue" and player.queue.is_empty and mp._queue_history:
                for t in mp._queue_history:
                    await player.queue.put_wait(t)
                mp._queue_history.clear()
            if not player.queue.is_empty:
                try:
                    next_track = player.queue.get()
                    await player.play(next_track)
                    print(f"[TRACK END] Auto-played next: {next_track.title}")
                except Exception as e:
                    print(f"[QUEUE NEXT ERROR] {e}")
                return
            if mp.autoplay and mp._single_loop_track:
                try:
                    query = f"ytsearch:{mp._single_loop_track.author} mix"
                    results = await wavelink.Playable.search(query)
                    if results:
                        await player.play(results[0])
                except Exception as e:
                    print(f"[AUTOPLAY ERROR] {e}")

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player):
        await player.disconnect()
        if player.home:
            try:
                await player.home.send("Bot keluar dari voice channel karena idle terlalu lama.")
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        player = member.guild.voice_client
        if not player or not player.channel:
            return

        guild_id = member.guild.id
        mp = self.get_player(guild_id)
        vc = player.channel
        humans = [m for m in vc.members if not m.bot]

        if not humans:
            if mp._alone_task is None or mp._alone_task.done():
                mp._alone_task = asyncio.create_task(self._alone_disconnect(player, getattr(player, 'home', None)))
        else:
            self._cancel_alone_task(guild_id)

    # ==========================================================
    # COMMANDS
    # ==========================================================
    @app_commands.command(name="play", description="Putar lagu dari URL atau search query")
    @app_commands.describe(query="URL (YouTube/Spotify/SoundCloud) atau nama lagu")
    async def play(self, interaction: discord.Interaction, query: str):
        print(f"[PLAY CMD] Called by {interaction.user} with query: {query}")
        try:
            await interaction.response.defer()
        except Exception as e:
            print(f"[PLAY CMD] defer error: {e}")
            return
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("❌ Kamu harus join voice channel dulu!")
            return
        vc = interaction.user.voice.channel
        print(f"[PLAY CMD] Voice channel: {vc.name}")
        player = interaction.guild.voice_client
        if not player:
            print("[PLAY CMD] Creating new player...")
            try:
                player = await vc.connect(cls=wavelink.Player, self_deaf=False)
                player.home = interaction.channel
            except Exception as e:
                print(f"[PLAY CMD] Connect error: {e}")
                await interaction.followup.send(f"❌ Gagal connect ke voice: {e}")
                return
        elif player.channel != vc:
            print("[PLAY CMD] Moving to new channel...")
            try:
                await player.move_to(vc, self_deaf=False)
                player.home = interaction.channel
            except Exception as e:
                print(f"[PLAY CMD] Move error: {e}")
                await interaction.followup.send(f"❌ Gagal pindah channel: {e}")
                return
        print(f"[PLAY CMD] Player ready. Current: {player.current}")
        search_query = query.strip()

        # ==========================================================
        # HANDLE SPOTIFY URL — SPOTIFYDOWN API INTEGRATION
        # ==========================================================
        if self.music_service._is_spotify_url(search_query):
            spotify_info = self.music_service._extract_spotify_id(search_query)
            if not spotify_info:
                await interaction.followup.send("❌ URL Spotify tidak valid.")
                return
            spotify_type, spotify_id = spotify_info
            print(f"[SPOTIFY] Detected {spotify_type} with ID: {spotify_id}")

            loading_msg = await interaction.followup.send(
                f"🎵 Mengambil metadata Spotify ({spotify_type}) via SpotifyDown API..."
            )

            if spotify_type == "track":
                result = await self.music_service.resolve_spotify_track(search_query, interaction)
                if not result:
                    return
                track, source_emoji, rt, loading_msg = result

                await player.queue.put_wait(track)
                if not player.current:
                    await player.set_volume(100)
                    await asyncio.sleep(0.3)
                    await player.play(player.queue.get())

                embed = discord.Embed(
                    title=f"{source_emoji} Added from Spotify",
                    description=f"[{track.title}]({track.uri})",
                    color=discord.Color.green(),
                )
                artwork = rt.artwork or track.artwork
                if artwork:
                    embed.set_thumbnail(url=artwork)
                embed.set_footer(text=f"Source: spotifydown | Spotify ID: {rt.spotify_id}")

                await loading_msg.edit(content=None, embed=embed)
                return

            elif spotify_type in ["playlist", "album"]:
                result = await self.music_service.resolve_spotify_playlist(search_query, interaction, player, loading_msg)
                if not result:
                    return
                tracks, source_emoji, first_rt, final_embed = result
                await loading_msg.edit(content=None, embed=final_embed)
                return

        # HANDLE URL LANGSUNG (YouTube, SoundCloud, dll)
        elif search_query.startswith("http://") or search_query.startswith("https://"):
            print("[PLAY CMD] Direct URL detected, Lavalink will auto-resolve")
            pass
        # 2. HANDLE SEARCH QUERY & URL LANGSUNG
        else:
            result = await self.music_service.search_and_queue_track(search_query, player)
            if not result:
                return
            if isinstance(result, wavelink.Playlist):
                await interaction.followup.send(f"✅ Playlist ditambahkan! ({len(result.tracks)} lagu)")
                return
            track = result

        # ==========================================================
        # SEARCH VIA WAVELINK (Non-Spotify flow)
        # ==========================================================
        print(f"[PLAY CMD] Searching: {search_query}")
        try:
            tracks = await asyncio.wait_for(
                wavelink.Playable.search(search_query),
                timeout=30.0,
            )
            print(f"[PLAY CMD] Search returned: {type(tracks)} | count: {len(tracks) if hasattr(tracks, '__len__') else 'N/A'}")
        except asyncio.TimeoutError:
            print("[PLAY CMD] SEARCH TIMEOUT after 30s")
            await interaction.followup.send("⏱️ Search timeout (30s). Coba lagi atau gunakan query lain.")
            return
        except Exception as e:
            print(f"[PLAY CMD] SEARCH ERROR: {type(e).__name__}: {e}")
            await interaction.followup.send(f"❌ Gagal mencari lagu: `{e}`")
            return

        if not tracks:
            print("[PLAY CMD] No tracks found")
            await interaction.followup.send("❌ Lagu tidak ditemukan.")
            return

        # Handle playlist
        if isinstance(tracks, wavelink.Playlist):
            print(f"[PLAY CMD] Playlist detected: {tracks.name} with {len(tracks.tracks)} tracks")
            added = 0
            for t in tracks.tracks:
                try:
                    await player.queue.put_wait(t)
                    added += 1
                except Exception as e:
                    print(f"[PLAY CMD] Queue put error: {e}")
                    break
            print(f"[PLAY CMD] Added {added} tracks to queue")
            if not player.current and not player.queue.is_empty:
                try:
                    first = player.queue.get()
                    print(f"[PLAY CMD] Starting playback with: {first.title}")
                    await player.set_volume(100)
                    await asyncio.sleep(0.3)
                    await player.play(first)
                except Exception as e:
                    print(f"[PLAY CMD] Play error: {e}")
            await interaction.followup.send(f"✅ Playlist ditambahkan! ({added} lagu dari {tracks.name})")
            return

        # Single track
        track = tracks[0] if hasattr(tracks, '__getitem__') else tracks
        print(f"[PLAY CMD] Single track: {track.title}")
        try:
            await player.queue.put_wait(track)
            print("[PLAY CMD] Track queued")
        except Exception as e:
            print(f"[PLAY CMD] Queue error: {e}")
            await interaction.followup.send(f"❌ Gagal add ke queue: `{e}`")
            return
        if not player.current:
            try:
                next_track = player.queue.get()
                print(f"[PLAY CMD] Starting playback: {next_track.title}")
                await player.set_volume(100)
                await asyncio.sleep(0.5)
                await player.play(next_track)
            except Exception as e:
                print(f"[PLAY CMD] Play error: {e}")
                await interaction.followup.send(f"❌ Gagal memutar: `{e}`")
                return
        else:
            embed = discord.Embed(
                title="✅ Added to Queue",
                description=f"[{track.title}]({track.uri})",
                color=discord.Color.blue(),
            )
            if track.artwork:
                embed.set_thumbnail(url=track.artwork)
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="pause", description="Pause lagu yang sedang diputar")
    async def pause(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player or not player.current:
            await interaction.response.send_message("❌ Tidak ada lagu yang sedang diputar.", ephemeral=True)
            return
        await player.pause(True)
        await interaction.response.send_message("⏸️ Lagu di-pause.")

    @app_commands.command(name="resume", description="Lanjutkan lagu yang di-pause")
    async def resume(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player or not player.paused:
            await interaction.response.send_message("❌ Tidak ada lagu yang di-pause.", ephemeral=True)
            return
        await player.pause(False)
        await interaction.response.send_message("▶️ Lagu dilanjutkan.")

    @app_commands.command(name="skip", description="Skip ke lagu berikutnya")
    async def skip(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player or not player.current:
            await interaction.response.send_message("❌ Tidak ada lagu yang sedang diputar.", ephemeral=True)
            return
        skipped_track = player.current
        if not player.queue.is_empty:
            next_track = player.queue.get()
            await player.stop()
            await asyncio.sleep(0.2)
            await player.play(next_track)
            await interaction.response.send_message(
                f"⏭️ Skipped: **{skipped_track.title}** | Now Playing: **{next_track.title}**"
            )
        else:
            await player.stop()
            mp = self.get_player(interaction.guild_id)
            mp._last_track_id = None
            await interaction.response.send_message(
                f"⏭️ Skipped: **{skipped_track.title}** | Queue kosong."
            )

    @app_commands.command(name="stop", description="Stop lagu, clear queue, keluar voice channel")
    async def stop(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player:
            await interaction.response.send_message("❌ Bot tidak ada di voice channel.", ephemeral=True)
            return
        mp = self.get_player(interaction.guild_id)
        mp.loop_mode = "off"
        mp.autoplay = False
        mp._queue_history.clear()
        mp._single_loop_track = None
        mp._last_track_id = None
        player.queue.clear()
        await player.stop()
        await player.disconnect()
        await interaction.response.send_message("⏹️ Music player dihentikan dan queue di-clear.")

    @app_commands.command(name="queue", description="Lihat antrian lagu")
    async def queue(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player:
            await interaction.response.send_message("📭 Queue kosong.", ephemeral=True)
            return

        mp = self.get_player(interaction.guild_id)
        embed = discord.Embed(title="🎶 Music Queue", color=discord.Color.purple())

        if player.current:
            loop_emoji = {"single": "🔁", "queue": "🔂", "off": ""}.get(mp.loop_mode, "")
            embed.add_field(
                name=f"▶️ Now Playing {loop_emoji}",
                value=f"**{player.current.title}**\n`{format_duration(player.current.length)}`",
                inline=False,
            )

        items = list(player.queue)
        if items:
            total_ms = sum(t.length or 0 for t in items)
            queue_text = ""
            for i, track in enumerate(items[:15], 1):
                duration = format_duration(track.length) if track.length else "?"
                queue_text += f"`{i:02d}.` {track.title[:40]}{'...' if len(track.title) > 40 else ''} (`{duration}`)\n"

            embed.add_field(name="⏭️ Up Next", value=queue_text or "...", inline=False)
            embed.set_footer(text=f"{len(items)} lagu | Total durasi: {format_duration(total_ms)}")
        else:
            embed.set_footer(text="Queue kosong — tambah lagu dengan /play")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="nowplaying", description="Info detail lagu yang sedang diputar")
    async def nowplaying(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player or not player.current:
            await interaction.response.send_message("❌ Tidak ada lagu yang sedang diputar.", ephemeral=True)
            return

        track = player.current
        mp = self.get_player(interaction.guild_id)
        embed = discord.Embed(
            title="▶️ Now Playing",
            description=f"[{track.title}]({track.uri})",
            color=discord.Color.green(),
        )
        embed.add_field(name="Author", value=track.author or "Unknown", inline=True)
        embed.add_field(name="Duration", value=format_duration(track.length), inline=True)

        position = getattr(player, 'position', 0) or 0
        embed.add_field(
            name="Progress",
            value=self._progress_bar(position, track.length),
            inline=False,
        )

        embed.add_field(name="Autoplay", value="ON" if mp.autoplay else "OFF", inline=True)
        loop_text = {"single": "Single", "queue": "Queue", "off": "OFF"}.get(mp.loop_mode, "OFF")
        embed.add_field(name="Loop", value=loop_text, inline=True)

        if track.artwork:
            embed.set_thumbnail(url=track.artwork)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="volume", description="Atur volume bot (0-1000)")
    @app_commands.describe(level="Volume level 0-1000 (default 100)")
    async def volume(self, interaction: discord.Interaction, level: int):
        if not 0 <= level <= 1000:
            await interaction.response.send_message("❌ Volume harus antara 0-1000.", ephemeral=True)
            return
        player = interaction.guild.voice_client
        if not player:
            await interaction.response.send_message("❌ Bot tidak ada di voice channel.", ephemeral=True)
            return
        await player.set_volume(level)
        await interaction.response.send_message(f"🔊 Volume diatur ke **{level}%**.")

    @app_commands.command(name="loop", description="Atur mode loop lagu/queue")
    @app_commands.describe(mode="Pilih mode loop")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Single (Lagu Ini)", value="single"),
        app_commands.Choice(name="Queue (Semua Lagu)", value="queue"),
    ])
    async def loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        mp = self.get_player(interaction.guild_id)
        mp.loop_mode = mode.value
        if mode.value == "queue":
            mp._queue_history.clear()
        if mode.value == "off":
            mp._single_loop_track = None
        await interaction.response.send_message(f"🔁 Loop mode: **{mode.name}**")

    @app_commands.command(name="shuffle", description="Acak antrian lagu")
    async def shuffle(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player or player.queue.is_empty:
            await interaction.response.send_message("📭 Queue kosong, tidak ada yang bisa diacak.", ephemeral=True)
            return
        mp = self.get_player(interaction.guild_id)
        items = list(player.queue)
        random.shuffle(items)
        player.queue.clear()
        for item in items:
            await player.queue.put_wait(item)
        mp._queue_history.clear()
        await interaction.response.send_message(f"🔀 Queue diacak! ({len(items)} lagu)")

    @app_commands.command(name="autoplay", description="Toggle autoplay: bot cari lagu serupa ketika queue habis")
    async def autoplay(self, interaction: discord.Interaction):
        mp = self.get_player(interaction.guild_id)
        mp.autoplay = not mp.autoplay
        status = "ON ✅" if mp.autoplay else "OFF ❌"
        await interaction.response.send_message(f"🤖 Autoplay sekarang: **{status}**")

    # ==========================================================
    # [POLISH] NEW COMMANDS
    # ==========================================================
    @app_commands.command(name="seek", description="Skip ke posisi tertentu dalam lagu")
    @app_commands.describe(position="Format: 1:30 atau 90 (detik)")
    async def seek(self, interaction: discord.Interaction, position: str):
        player = interaction.guild.voice_client
        if not player or not player.current:
            await interaction.response.send_message("❌ Tidak ada lagu yang sedang diputar.", ephemeral=True)
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
            await interaction.response.send_message("❌ Format salah. Gunakan `1:30` atau `90`.", ephemeral=True)
            return

        ms = total_seconds * 1000
        if player.current.length and ms > player.current.length:
            await interaction.response.send_message("❌ Posisi melebihi durasi lagu.", ephemeral=True)
            return

        await player.seek(ms)
        await interaction.response.send_message(f"⏩ Skip ke `{format_duration(ms)}`.")

    @app_commands.command(name="remove", description="Hapus lagu dari queue berdasarkan nomor")
    @app_commands.describe(index="Nomor lagu di /queue")
    async def remove(self, interaction: discord.Interaction, index: int):
        player = interaction.guild.voice_client
        if not player or player.queue.is_empty:
            await interaction.response.send_message("📭 Queue kosong.", ephemeral=True)
            return
        if index < 1:
            await interaction.response.send_message("❌ Nomor harus mulai dari 1.", ephemeral=True)
            return

        items = list(player.queue)
        if index > len(items):
            await interaction.response.send_message(f"❌ Queue cuma ada {len(items)} lagu.", ephemeral=True)
            return

        mp = self.get_player(interaction.guild_id)
        async with mp._track_lock:
            removed = items.pop(index - 1)
            player.queue.clear()
            for item in items:
                await player.queue.put_wait(item)

        await interaction.response.send_message(f"🗑️ Dihapus dari queue: **{removed.title}**")

    @app_commands.command(name="move", description="Pindah posisi lagu di queue")
    @app_commands.describe(from_index="Posisi asal", to_index="Posisi tujuan")
    async def move(self, interaction: discord.Interaction, from_index: int, to_index: int):
        player = interaction.guild.voice_client
        if not player or player.queue.is_empty:
            await interaction.response.send_message("📭 Queue kosong.", ephemeral=True)
            return

        items = list(player.queue)
        if not (1 <= from_index <= len(items)) or not (1 <= to_index <= len(items)):
            await interaction.response.send_message(f"❌ Index harus antara 1 dan {len(items)}.", ephemeral=True)
            return

        mp = self.get_player(interaction.guild_id)
        async with mp._track_lock:
            track = items.pop(from_index - 1)
            items.insert(to_index - 1, track)
            player.queue.clear()
            for item in items:
                await player.queue.put_wait(item)

        await interaction.response.send_message(f"↔️ Dipindah: **{track.title}** ke posisi `{to_index}`")

    @app_commands.command(name="skipto", description="Skip ke lagu nomor tertentu di queue")
    @app_commands.describe(index="Nomor lagu di /queue")
    async def skipto(self, interaction: discord.Interaction, index: int):
        player = interaction.guild.voice_client
        if not player or player.queue.is_empty:
            await interaction.response.send_message("📭 Queue kosong.", ephemeral=True)
            return

        items = list(player.queue)
        if not (1 <= index <= len(items)):
            await interaction.response.send_message(f"❌ Index harus antara 1 dan {len(items)}.", ephemeral=True)
            return

        mp = self.get_player(interaction.guild_id)
        async with mp._track_lock:
            target = items.pop(index - 1)
            new_queue = [target] + items
            player.queue.clear()
            for item in new_queue:
                await player.queue.put_wait(item)

        await player.stop()
        await asyncio.sleep(0.3)
        if not player.queue.is_empty:
            next_track = player.queue.get()
            await player.play(next_track)
            await interaction.response.send_message(f"⏭️ Skip ke: **{next_track.title}**")
        else:
            await interaction.response.send_message("📭 Queue kosong setelah reorder.")

    @app_commands.command(name="disconnect", description="Keluar dari voice channel")
    async def disconnect(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player:
            await interaction.response.send_message("❌ Bot tidak di voice channel.", ephemeral=True)
            return
        await player.disconnect()
        await interaction.response.send_message("🔌 Keluar dari voice channel.")

    @app_commands.command(name="clearqueue", description="Kosongkan queue tanpa menghentikan lagu yang sedang diputar")
    async def clearqueue(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player or player.queue.is_empty:
            await interaction.response.send_message("📭 Queue sudah kosong.", ephemeral=True)
            return
        player.queue.clear()
        mp = self.get_player(interaction.guild_id)
        mp._queue_history.clear()
        await interaction.response.send_message("🧹 Queue dikosongkan. Lagu yang sedang diputar tetap jalan.")

    @app_commands.command(name="replay", description="Putar ulang lagu dari awal")
    async def replay(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player or not player.current:
            await interaction.response.send_message("❌ Tidak ada lagu yang sedang diputar.", ephemeral=True)
            return
        await player.seek(0)
        await interaction.response.send_message("🔁 Replay dari awal.")

    @app_commands.command(name="lyrics", description="Cari lirik lagu yang sedang diputar atau dari judul")
    @app_commands.describe(query="Judul lagu (opsional, default: lagu yang sedang diputar)")
    async def lyrics(self, interaction: discord.Interaction, query: str = None):
        if not query and interaction.guild.voice_client and interaction.guild.voice_client.current:
            track = interaction.guild.voice_client.current
            query = f"{track.title} {track.author or ''}"

        if not query:
            await interaction.response.send_message("❌ Tidak ada lagu yang diputar. Berikan judul!")
            return

        await interaction.response.defer()

        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://lrclib.net/api/search?q={query.strip().replace(' ', '%20')}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        await interaction.followup.send("❌ Lirik tidak ditemukan.")
                        return
                    data = await resp.json()

            if not data:
                await interaction.followup.send("❌ Lirik tidak ditemukan.")
                return

            song = data[0]
            title = song.get('trackName', 'Unknown')
            artist = song.get('artistName', 'Unknown')
            plain = song.get('plainLyrics', 'Tidak ada lirik tersedia.')

            # FIX: Ganti batasan teks menjadi 3900 dan pindahkan teks dari Embed Field ke Embed Description 
            # untuk menghindari penolakan Discord API karena batas isi field maksimal hanya 1024 karakter.
            if len(plain) > 3900:
                plain = plain[:3900] + "\n..."

            embed = discord.Embed(
                title=f"🎤 {title}",
                description=f"by **{artist}**\n\n```{plain}```",
                color=discord.Color.pink(),
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"[LYRICS ERROR] {e}")
            await interaction.followup.send("❌ Gagal mengambil lirik. Coba judul lain.")

    # ==========================================================
    # PLAYLIST GROUP
    # ==========================================================
    playlist = app_commands.Group(name="playlist", description="Simpan dan muat playlist lagu")

    @playlist.command(name="save", description="Simpan queue saat ini sebagai playlist")
    @app_commands.describe(name="Nama playlist")
    async def playlist_save(self, interaction: discord.Interaction, name: str):
        db = get_db()
        if db is None:
            await interaction.response.send_message("❌ Fitur playlist tidak tersedia (Firebase tidak terhubung).", ephemeral=True)
            return
        player = interaction.guild.voice_client
        tracks = []
        if player and player.current:
            tracks.append({
                "title": player.current.title,
                "uri": player.current.uri,
                "author": player.current.author or "Unknown",
                "artwork": player.current.artwork or "",
                "length": player.current.length or 0,
            })
        if player:
            for track in list(player.queue):
                tracks.append({
                    "title": track.title,
                    "uri": track.uri,
                    "author": track.author or "Unknown",
                    "artwork": track.artwork or "",
                    "length": track.length or 0,
                })
        if not tracks:
            await interaction.response.send_message("📭 Tidak ada lagu untuk disimpan.", ephemeral=True)
            return
        doc_id = f"{interaction.guild_id}_{interaction.user.id}_{name}"
        get_db().collection("playlists").document(doc_id).set({
            "guild_id": str(interaction.guild_id),
            "user_id": str(interaction.user.id),
            "name": name,
            "tracks": tracks,
            "created_at": datetime.now(timezone.utc),
        })
        await interaction.response.send_message(f"💾 Playlist **{name}** disimpan! ({len(tracks)} lagu)")

    @playlist.command(name="load", description="Muat playlist ke queue")
    @app_commands.describe(name="Nama playlist")
    async def playlist_load(self, interaction: discord.Interaction, name: str):
        db = get_db()
        if db is None:
            await interaction.response.send_message("❌ Fitur playlist tidak tersedia (Firebase tidak terhubung).", ephemeral=True)
            return
        await interaction.response.defer()
        doc_id = f"{interaction.guild_id}_{interaction.user.id}_{name}"
        doc = get_db().collection("playlists").document(doc_id).get()
        if not doc.exists:
            await interaction.followup.send(f"❌ Playlist **{name}** tidak ditemukan.")
            return
        data = doc.to_dict()
        track_data = data.get("tracks", [])
        if not track_data:
            await interaction.followup.send("📭 Playlist kosong.")
            return
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("❌ Kamu harus join voice channel dulu!")
            return
        vc = interaction.user.voice.channel
        player = interaction.guild.voice_client
        if not player:
            player = await vc.connect(cls=wavelink.Player, self_deaf=False)
            player.home = interaction.channel
        elif player.channel != vc:
            await player.move_to(vc, self_deaf=False)
            player.home = interaction.channel
            
        added = 0
        failed = 0
        
        # OPTIMASI: Memproses track_data secara concurrent menggunakan semaphore (max 5)
        # agar muat playlist berisi puluhan lagu tidak memakan waktu lama (blocking)
        semaphore = asyncio.Semaphore(5)
        
        async def load_single_track(t):
            nonlocal added, failed
            async with semaphore:
                try:
                    results = await wavelink.Playable.search(t['uri'])
                    if results:
                        return results[0]
                except Exception as e:
                    print(f"[PLAYLIST CONCURRENT LOAD ERROR] {e}")
                return None

        tasks = [load_single_track(track) for track in track_data]
        playables = await asyncio.gather(*tasks)
        
        for p in playables:
            if p:
                await player.queue.put_wait(p)
                added += 1
            else:
                failed += 1

        if not player.current and not player.queue.is_empty:
            await player.play(player.queue.get())
        msg = f"📂 Playlist **{name}** dimuat! ({added} lagu ditambahkan)"
        if failed:
            msg += f" | {failed} gagal dimuat"
        await interaction.followup.send(msg)

    @playlist.command(name="list", description="Lihat daftar playlist-mu")
    async def playlist_list(self, interaction: discord.Interaction):
        db = get_db()
        if db is None:
            await interaction.response.send_message("❌ Fitur playlist tidak tersedia (Firebase tidak terhubung).", ephemeral=True)
            return
        playlists = (get_db().collection("playlists")
            .where("guild_id", "==", str(interaction.guild_id))
            .where("user_id", "==", str(interaction.user.id))
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
        await interaction.response.send_message(embed=embed)

    @playlist.command(name="delete", description="Hapus playlist")
    @app_commands.describe(name="Nama playlist yang mau dihapus")
    async def playlist_delete(self, interaction: discord.Interaction, name: str):
        db = get_db()
        if db is None:
            await interaction.response.send_message("❌ Fitur playlist tidak tersedia (Firebase tidak terhubung).", ephemeral=True)
            return
        doc_id = f"{interaction.guild_id}_{interaction.user.id}_{name}"
        doc_ref = get_db().collection("playlists").document(doc_id)
        doc = doc_ref.get()
        if not doc.exists:
            await interaction.response.send_message(f"❌ Playlist **{name}** tidak ditemukan.", ephemeral=True)
            return
        doc_ref.delete()
        await interaction.response.send_message(f"🗑️ Playlist **{name}** dihapus.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
