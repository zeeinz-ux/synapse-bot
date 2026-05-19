import discord
from discord.ext import commands
from discord import app_commands
import wavelink
import asyncio
import os
import random
import re
import requests
from datetime import datetime, timezone

# Firebase playlist support (lazy import to avoid init order issues)
def get_db():
    """Lazy import Firebase db to avoid circular/import order issues."""
    try:
        from cogs.firebase_setup import db
        return db
    except Exception as e:
        print(f"[FIREBASE LAZY IMPORT] {e}")
        return None


class MusicPlayer:
    """Wrapper untuk menyimpan state per guild."""
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.loop_mode = "off"          # off, single, queue
        self.autoplay = False
        self._queue_history = []         # untuk queue loop
        self._single_loop_track = None   # untuk single loop
        self._last_track_id = None       # Anti-duplikat embed
        self._last_embed_time = 0        # Cooldown timestamp (anti-spam)
        self._track_lock = asyncio.Lock() # Lock serialize track_end


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players = {}  # guild_id -> MusicPlayer
        self._spotify_token = None
        self._spotify_token_expiry = 0
        self._spotify_enabled = True

    def get_player(self, guild_id: int) -> MusicPlayer:
        if guild_id not in self.players:
            self.players[guild_id] = MusicPlayer(guild_id)
        return self.players[guild_id]

    # ==========================================================
    # SPOTIFY API HELPERS (with fallback)
    # ==========================================================
    def _get_spotify_token(self) -> str | None:
        """Get Spotify access token (cached)."""
        import time
        if self._spotify_token and time.time() < self._spotify_token_expiry - 60:
            return self._spotify_token

        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

        if not client_id or not client_secret:
            print("[SPOTIFY] No credentials in .env")
            return None

        try:
            response = requests.post(
                'https://accounts.spotify.com/api/token',
                data={'grant_type': 'client_credentials'},
                auth=(client_id, client_secret),
                timeout=10
            )

            try:
                data = response.json()
            except ValueError:
                print(f"[SPOTIFY] Invalid JSON response: {response.text[:200]}")
                return None

            if 'error' in data:
                print(f"[SPOTIFY] API Error: {data.get('error_description', data['error'])}")
                if data.get('error') == 'invalid_client':
                    print("[SPOTIFY] Client credentials invalid. Please check SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET")
                return None

            self._spotify_token = data.get('access_token')
            self._spotify_token_expiry = time.time() + data.get('expires_in', 3600)
            print(f"[SPOTIFY] Token refreshed, expires in {data.get('expires_in', 3600)}s")
            return self._spotify_token

        except Exception as e:
            print(f"[SPOTIFY TOKEN ERROR] {e}")
            return None

    def _is_spotify_url(self, query: str) -> bool:
        return "open.spotify.com" in query or "spotify.com" in query

    def _extract_spotify_id(self, url: str) -> tuple[str, str] | None:
        """Extract (type, id) from Spotify URL."""
        patterns = [
            (r'track/([a-zA-Z0-9]+)', 'track'),
            (r'playlist/([a-zA-Z0-9]+)', 'playlist'),
            (r'album/([a-zA-Z0-9]+)', 'album'),
        ]
        for pattern, type_ in patterns:
            match = re.search(pattern, url)
            if match:
                return (type_, match.group(1))
        return None

    def _extract_search_query_from_spotify_url(self, url: str) -> str:
        """Extract a search query from Spotify URL for YouTube fallback."""
        spotify_info = self._extract_spotify_id(url)
        if not spotify_info:
            return url.split('/')[-1].split('?')[0].replace('-', ' ')

        spotify_type, spotify_id = spotify_info

        token = self._get_spotify_token()
        if token:
            try:
                headers = {'Authorization': f'Bearer {token}'}
                if spotify_type == 'track':
                    response = requests.get(
                        f'https://api.spotify.com/v1/tracks/{spotify_id}',
                        headers=headers,
                        timeout=10
                    )
                    if response.status_code == 200:
                        data = response.json()
                        name = data.get('name', '')
                        artists = ', '.join([a['name'] for a in data.get('artists', [])])
                        return f"{name} {artists}"
                    elif response.status_code == 403:
                        print("[SPOTIFY] 403 Forbidden - Premium required. Using fallback.")
                        self._spotify_enabled = False

                elif spotify_type == 'playlist':
                    response = requests.get(
                        f'https://api.spotify.com/v1/playlists/{spotify_id}?fields=name',
                        headers=headers,
                        timeout=10
                    )
                    if response.status_code == 200:
                        data = response.json()
                        return data.get('name', 'playlist')
                    elif response.status_code == 403:
                        print("[SPOTIFY] 403 Forbidden - Premium required. Using fallback.")
                        self._spotify_enabled = False

            except Exception as e:
                print(f"[SPOTIFY FALLBACK ERROR] {e}")

        return url.split('/')[-1].split('?')[0].replace('-', ' ')

    async def _get_spotify_tracks(self, spotify_type: str, spotify_id: str) -> list[dict]:
        """Fetch tracks from Spotify API. Returns list of {name, artists}."""
        token = self._get_spotify_token()
        if not token:
            return []

        headers = {'Authorization': f'Bearer {token}'}
        tracks = []

        try:
            if spotify_type == 'track':
                response = requests.get(
                    f'https://api.spotify.com/v1/tracks/{spotify_id}',
                    headers=headers,
                    timeout=10
                )

                if response.status_code == 403:
                    print("[SPOTIFY] 403 Forbidden - Premium required. Disabling Spotify.")
                    self._spotify_enabled = False
                    return []

                data = response.json()
                if 'error' not in data:
                    tracks.append({
                        'name': data.get('name', ''),
                        'artists': ', '.join([a['name'] for a in data.get('artists', [])])
                    })

            elif spotify_type == 'playlist':
                test_response = requests.get(
                    f'https://api.spotify.com/v1/playlists/{spotify_id}?fields=name',
                    headers=headers,
                    timeout=10
                )

                if test_response.status_code == 403:
                    print("[SPOTIFY] 403 Forbidden - Premium required. Disabling Spotify.")
                    self._spotify_enabled = False
                    return []

                playlist_data = test_response.json()
                playlist_name = playlist_data.get('name', 'Unknown Playlist')
                print(f"[SPOTIFY] Loading playlist: {playlist_name}")

                url = f'https://api.spotify.com/v1/playlists/{spotify_id}/tracks?fields=items(track(name,artists(name))),next&limit=100'
                while url and len(tracks) < 500:
                    response = requests.get(url, headers=headers, timeout=10)

                    if response.status_code == 403:
                        print("[SPOTIFY] 403 Forbidden during pagination. Disabling.")
                        self._spotify_enabled = False
                        break

                    data = response.json()

                    if 'error' in data:
                        break

                    for item in data.get('items', []):
                        track = item.get('track')
                        if track and track.get('name'):
                            tracks.append({
                                'name': track.get('name', ''),
                                'artists': ', '.join([a['name'] for a in track.get('artists', [])])
                            })

                    url = data.get('next')

            elif spotify_type == 'album':
                url = f'https://api.spotify.com/v1/albums/{spotify_id}/tracks?limit=50'
                while url and len(tracks) < 500:
                    response = requests.get(url, headers=headers, timeout=10)

                    if response.status_code == 403:
                        print("[SPOTIFY] 403 Forbidden - Premium required. Disabling Spotify.")
                        self._spotify_enabled = False
                        break

                    data = response.json()

                    if 'error' in data:
                        break

                    for track in data.get('items', []):
                        if track.get('name'):
                            tracks.append({
                                'name': track.get('name', ''),
                                'artists': ', '.join([a['name'] for a in track.get('artists', [])])
                            })

                    url = data.get('next')

        except Exception as e:
            print(f"[SPOTIFY API ERROR] {e}")

        return tracks

    async def _search_youtube_for_tracks(self, tracks: list[dict], player: wavelink.Player) -> int:
        """Search each track on YouTube and add to queue. Returns count added."""
        added = 0
        for track_info in tracks:
            try:
                query = f"ytsearch:{track_info['name']} {track_info['artists']}"
                results = await wavelink.Playable.search(query)
                if results and len(results) > 0:
                    await player.queue.put_wait(results[0])
                    added += 1
            except Exception as e:
                print(f"[YOUTUBE SEARCH ERROR] {track_info['name']}: {e}")
            await asyncio.sleep(0.5)
        return added

    # ==========================================================
    # EVENTS
    # ==========================================================
    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        print(f"[LAVALINK] Node {payload.node.identifier} ready! (Session ID: {payload.session_id})")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player = payload.player
        track = payload.track
        guild_id = player.guild.id
        mp = self.get_player(guild_id)

        track_id = getattr(track, 'identifier', track.title)

        # Safety net: block duplicate embed dalam 3 detik (anti-spam)
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
        embed.add_field(name="Duration", value=self._format_duration(track.length), inline=True)
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

        # FIX: lowercase reason karena Lavalink kirim "stopped"/"replaced" (lowercase)
        reason = getattr(payload, 'reason', 'unknown').lower()
        print(f"[TRACK END] reason={reason}, track={getattr(payload.track, 'title', 'unknown')}")

        # Ignore kalau track di-stop/replace/cleanup oleh command
        if reason in ("stopped", "replaced", "cleanup"):
            print(f"[TRACK END] Ignoring reason={reason}, no auto-action")
            return

        # Hanya proses kalau track habis natural (finished) atau gagal load (load_failed)
        async with mp._track_lock:
            # 1. SINGLE LOOP
            if mp.loop_mode == "single" and mp._single_loop_track:
                await player.play(mp._single_loop_track)
                return

            # 2. QUEUE LOOP
            if mp.loop_mode == "queue" and player.queue.is_empty and mp._queue_history:
                for t in mp._queue_history:
                    await player.queue.put_wait(t)
                mp._queue_history.clear()

            # 3. AUTO-PLAY NEXT
            if not player.queue.is_empty:
                try:
                    next_track = player.queue.get()
                    await player.play(next_track)
                    print(f"[TRACK END] Auto-played next: {next_track.title}")
                except Exception as e:
                    print(f"[QUEUE NEXT ERROR] {e}")
                return

            # 4. AUTOPLAY
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

    # ==========================================================
    # HELPERS
    # ==========================================================
    def _format_duration(self, ms: int) -> str:
        if ms == 0:
            return "Live"
        seconds = ms // 1000
        minutes = seconds // 60
        hours = minutes // 60
        if hours > 0:
            return f"{hours}:{minutes % 60:02d}:{seconds % 60:02d}"
        return f"{minutes}:{seconds % 60:02d}"

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
            await interaction.followup.send("Kamu harus join voice channel dulu!")
            return

        vc = interaction.user.voice.channel
        print(f"[PLAY CMD] Voice channel: {vc.name}")

        # Dapatkan atau buat wavelink.Player
        player = interaction.guild.voice_client
        if not player:
            print("[PLAY CMD] Creating new player...")
            try:
                player = await vc.connect(cls=wavelink.Player)
                player.home = interaction.channel
            except Exception as e:
                print(f"[PLAY CMD] Connect error: {e}")
                await interaction.followup.send(f"Gagal connect ke voice: {e}")
                return
        elif player.channel != vc:
            print("[PLAY CMD] Moving to new channel...")
            try:
                await player.move_to(vc)
                player.home = interaction.channel
            except Exception as e:
                print(f"[PLAY CMD] Move error: {e}")
                await interaction.followup.send(f"Gagal pindah channel: {e}")
                return

        print(f"[PLAY CMD] Player ready. Current: {player.current}")

        search_query = query.strip()
        tracks = None

        # HANDLE SPOTIFY URL
        if self._is_spotify_url(search_query):
            spotify_info = self._extract_spotify_id(search_query)

            if not spotify_info:
                await interaction.followup.send("URL Spotify tidak valid. Gunakan format: https://open.spotify.com/track/... atau /playlist/... atau /album/...")
                return

            spotify_type, spotify_id = spotify_info

            # Send loading message
            loading_msg = await interaction.followup.send(f"Memuat dari Spotify ({spotify_type})...")

            # Try Spotify API first
            if self._spotify_enabled:
                spotify_tracks = await self._get_spotify_tracks(spotify_type, spotify_id)
            else:
                spotify_tracks = []
                print("[SPOTIFY] Skipped (disabled due to previous 403 error)")

            # If Spotify API failed, use YouTube fallback
            if not spotify_tracks:
                print("[FALLBACK] Using YouTube search for Spotify URL")
                fallback_query = self._extract_search_query_from_spotify_url(search_query)

                if spotify_type == 'track':
                    # Single track fallback
                    yt_query = f"ytsearch:{fallback_query}"
                    print(f"[FALLBACK] Searching: {yt_query}")
                    try:
                        tracks = await wavelink.Playable.search(yt_query)
                    except Exception as e:
                        print(f"[FALLBACK ERROR] {e}")
                        await loading_msg.edit(content="Gagal mencari lagu di YouTube.")
                        return

                    if not tracks:
                        await loading_msg.edit(content="Lagu tidak ditemukan di YouTube.")
                        return

                    track = tracks[0]
                    await player.queue.put_wait(track)
                    if not player.current:
                        await player.play(player.queue.get())

                    embed = discord.Embed(
                        title="Added from Spotify (YouTube Fallback)",
                        description=f"[{track.title}]({track.uri})",
                        color=discord.Color.green()
                    )
                    if track.artwork:
                        embed.set_thumbnail(url=track.artwork)
                    await loading_msg.edit(content=None, embed=embed)
                    return

                else:
                    # Playlist/Album fallback - search first track only (to avoid rate limit)
                    yt_query = f"ytsearch:{fallback_query}"
                    print(f"[FALLBACK] Searching playlist: {yt_query}")
                    try:
                        tracks = await wavelink.Playable.search(yt_query)
                        if tracks:
                            await player.queue.put_wait(tracks[0])
                            if not player.current:
                                await player.play(player.queue.get())
                            await loading_msg.edit(content=f"Spotify {spotify_type.title()} (fallback): **{tracks[0].title}** ditambahkan!")
                        else:
                            await loading_msg.edit(content="Gagal memuat dari Spotify dan YouTube.")
                    except Exception as e:
                        print(f"[FALLBACK ERROR] {e}")
                        await loading_msg.edit(content="Gagal memuat playlist.")
                    return

            # Spotify API worked - proceed as normal
            # Single track
            if spotify_type == 'track':
                track_info = spotify_tracks[0]
                yt_query = f"ytsearch:{track_info['name']} {track_info['artists']}"
                print(f"[SPOTIFY TRACK] Searching: {yt_query}")
                try:
                    tracks = await wavelink.Playable.search(yt_query)
                except Exception as e:
                    print(f"[SPOTIFY TRACK ERROR] {e}")
                    await loading_msg.edit(content="Gagal mencari lagu di YouTube.")
                    return

                if not tracks:
                    await loading_msg.edit(content="Lagu tidak ditemukan di YouTube.")
                    return

                track = tracks[0]
                await player.queue.put_wait(track)
                if not player.current:
                    await player.play(player.queue.get())

                embed = discord.Embed(
                    title="Added from Spotify",
                    description=f"[{track.title}]({track.uri})",
                    color=discord.Color.green()
                )
                if track.artwork:
                    embed.set_thumbnail(url=track.artwork)
                await loading_msg.edit(content=None, embed=embed)
                return

            # Playlist or Album
            else:
                total_tracks = len(spotify_tracks)
                await loading_msg.edit(content=f"Memuat {total_tracks} lagu dari Spotify {spotify_type}...")

                added = await self._search_youtube_for_tracks(spotify_tracks, player)

                if not player.current and not player.queue.is_empty:
                    await player.play(player.queue.get())

                msg = f"Spotify {spotify_type.title()} ditambahkan! ({added}/{total_tracks} lagu)"
                if added < total_tracks:
                    msg += f" | {total_tracks - added} lagu gagal dimuat"
                await loading_msg.edit(content=msg)
                return

        # HANDLE URL LANGSUNG (YouTube, SoundCloud, dll)
        elif search_query.startswith("http://") or search_query.startswith("https://"):
            print("[PLAY CMD] Direct URL detected, Lavalink will auto-resolve")
            pass

        # HANDLE SEARCH QUERY
        else:
            if not any(search_query.startswith(p) for p in ["ytsearch:", "scsearch:", "spsearch:"]):
                search_query = f"ytsearch:{search_query}"

        # SEARCH VIA WAVELINK
        if tracks is None:
            print(f"[PLAY CMD] Searching: {search_query}")
            try:
                # FIX: Tambah timeout 30 detik untuk menghindari hang
                tracks = await asyncio.wait_for(
                    wavelink.Playable.search(search_query),
                    timeout=30.0
                )
                print(f"[PLAY CMD] Search returned: {type(tracks)} | count: {len(tracks) if hasattr(tracks, '__len__') else 'N/A'}")
            except asyncio.TimeoutError:
                print("[PLAY CMD] SEARCH TIMEOUT after 30s")
                await interaction.followup.send("Search timeout (30s). Coba lagi atau gunakan query lain.")
                return
            except Exception as e:
                print(f"[PLAY CMD] SEARCH ERROR: {type(e).__name__}: {e}")
                await interaction.followup.send(f"Gagal mencari lagu: {e}")
                return

        if not tracks:
            print("[PLAY CMD] No tracks found")
            await interaction.followup.send("Lagu tidak ditemukan.")
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
                    await player.play(first)
                except Exception as e:
                    print(f"[PLAY CMD] Play error: {e}")

            await interaction.followup.send(f"Playlist ditambahkan! ({added} lagu dari {tracks.name})")
            return

        # Single track
        track = tracks[0] if hasattr(tracks, '__getitem__') else tracks
        print(f"[PLAY CMD] Single track: {track.title}")

        try:
            await player.queue.put_wait(track)
            print(f"[PLAY CMD] Track queued")
        except Exception as e:
            print(f"[PLAY CMD] Queue error: {e}")
            await interaction.followup.send(f"Gagal add ke queue: {e}")
            return

        if not player.current:
            try:
                next_track = player.queue.get()
                print(f"[PLAY CMD] Starting playback: {next_track.title}")
                await player.play(next_track)
            except Exception as e:
                print(f"[PLAY CMD] Play error: {e}")
                await interaction.followup.send(f"Gagal memutar: {e}")
                return
        else:
            embed = discord.Embed(
                title="Added to Queue",
                description=f"[{track.title}]({track.uri})",
                color=discord.Color.blue()
            )
            if track.artwork:
                embed.set_thumbnail(url=track.artwork)
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="pause", description="Pause lagu yang sedang diputar")
    async def pause(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player or not player.current:
            await interaction.response.send_message("Tidak ada lagu yang sedang diputar.")
            return
        await player.pause(True)
        await interaction.response.send_message("Lagu di-pause.")

    @app_commands.command(name="resume", description="Lanjutkan lagu yang di-pause")
    async def resume(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player or not player.paused:
            await interaction.response.send_message("Tidak ada lagu yang di-pause.")
            return
        await player.pause(False)
        await interaction.response.send_message("Lagu dilanjutkan.")

    @app_commands.command(name="skip", description="Skip ke lagu berikutnya")
    async def skip(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player or not player.current:
            await interaction.response.send_message("Tidak ada lagu yang sedang diputar.")
            return

        skipped_track = player.current

        if not player.queue.is_empty:
            next_track = player.queue.get()
            await player.stop()          # Trigger TrackEnd reason=stopped -> di-ignore handler
            await asyncio.sleep(0.2)
            await player.play(next_track)
            await interaction.response.send_message(
                f"Skipped: **{skipped_track.title}** | Now Playing: **{next_track.title}**"
            )
        else:
            await player.stop()
            mp = self.get_player(interaction.guild_id)
            mp._last_track_id = None
            await interaction.response.send_message(
                f"Skipped: **{skipped_track.title}** | Queue kosong."
            )

    @app_commands.command(name="stop", description="Stop lagu, clear queue, keluar voice channel")
    async def stop(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player:
            await interaction.response.send_message("Bot tidak ada di voice channel.")
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
        await interaction.response.send_message("Music player dihentikan dan queue di-clear.")

    @app_commands.command(name="queue", description="Lihat antrian lagu")
    async def queue(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player:
            await interaction.response.send_message("Queue kosong.")
            return

        mp = self.get_player(interaction.guild_id)
        embed = discord.Embed(title="Music Queue", color=discord.Color.purple())

        if player.current:
            loop_emoji = {"single": "🔁", "queue": "🔂", "off": ""}.get(mp.loop_mode, "")
            embed.add_field(name=f"Now Playing {loop_emoji}", value=player.current.title, inline=False)

        items = list(player.queue)
        for i, track in enumerate(items[:10], 1):
            embed.add_field(name=f"{i}.", value=track.title, inline=False)

        if len(items) > 10:
            embed.set_footer(text=f"...dan {len(items) - 10} lagu lainnya")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="nowplaying", description="Info detail lagu yang sedang diputar")
    async def nowplaying(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player or not player.current:
            await interaction.response.send_message("Tidak ada lagu yang sedang diputar.")
            return

        track = player.current
        mp = self.get_player(interaction.guild_id)

        embed = discord.Embed(
            title="Now Playing",
            description=f"[{track.title}]({track.uri})",
            color=discord.Color.green()
        )
        embed.add_field(name="Author", value=track.author or "Unknown", inline=True)
        embed.add_field(name="Duration", value=self._format_duration(track.length), inline=True)
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
            await interaction.response.send_message("Volume harus antara 0-1000.")
            return

        player = interaction.guild.voice_client
        if not player:
            await interaction.response.send_message("Bot tidak ada di voice channel.")
            return

        await player.set_volume(level)
        await interaction.response.send_message(f"Volume diatur ke {level}%.")

    # LOOP
    @app_commands.command(name="loop", description="Atur mode loop lagu/queue")
    @app_commands.describe(mode="Pilih mode loop")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Single (Lagu Ini)", value="single"),
        app_commands.Choice(name="Queue (Semua Lagu)", value="queue")
    ])
    async def loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        mp = self.get_player(interaction.guild_id)
        mp.loop_mode = mode.value
        if mode.value == "queue":
            mp._queue_history.clear()
        if mode.value == "off":
            mp._single_loop_track = None
        await interaction.response.send_message(f"Loop mode: {mode.name}")

    # SHUFFLE
    @app_commands.command(name="shuffle", description="Acak antrian lagu")
    async def shuffle(self, interaction: discord.Interaction):
        player = interaction.guild.voice_client
        if not player or player.queue.is_empty:
            await interaction.response.send_message("Queue kosong, tidak ada yang bisa diacak.")
            return

        mp = self.get_player(interaction.guild_id)
        items = list(player.queue)
        random.shuffle(items)
        player.queue.clear()
        for item in items:
            await player.queue.put_wait(item)

        mp._queue_history.clear()
        await interaction.response.send_message(f"Queue diacak! ({len(items)} lagu)")

    # AUTOPLAY
    @app_commands.command(name="autoplay", description="Toggle autoplay: bot cari lagu serupa ketika queue habis")
    async def autoplay(self, interaction: discord.Interaction):
        mp = self.get_player(interaction.guild_id)
        mp.autoplay = not mp.autoplay
        status = "ON" if mp.autoplay else "OFF"
        await interaction.response.send_message(f"Autoplay sekarang: {status}")

    # PLAYLIST GROUP
    playlist = app_commands.Group(name="playlist", description="Simpan dan muat playlist lagu")

    @playlist.command(name="save", description="Simpan queue saat ini sebagai playlist")
    @app_commands.describe(name="Nama playlist")
    async def playlist_save(self, interaction: discord.Interaction, name: str):
        db = get_db()
        if db is None:
            await interaction.response.send_message("Fitur playlist tidak tersedia (Firebase tidak terhubung).")
            return

        player = interaction.guild.voice_client
        tracks = []

        if player and player.current:
            tracks.append({
                "title": player.current.title,
                "uri": player.current.uri,
                "author": player.current.author or "Unknown",
                "artwork": player.current.artwork or "",
                "length": player.current.length or 0
            })

        if player:
            for track in list(player.queue):
                tracks.append({
                    "title": track.title,
                    "uri": track.uri,
                    "author": track.author or "Unknown",
                    "artwork": track.artwork or "",
                    "length": track.length or 0
                })

        if not tracks:
            await interaction.response.send_message("Tidak ada lagu untuk disimpan.")
            return

        doc_id = f"{interaction.guild_id}_{interaction.user.id}_{name}"
        get_db().collection("playlists").document(doc_id).set({
            "guild_id": str(interaction.guild_id),
            "user_id": str(interaction.user.id),
            "name": name,
            "tracks": tracks,
            "created_at": datetime.now(timezone.utc)
        })

        await interaction.response.send_message(f"Playlist {name} disimpan! ({len(tracks)} lagu)")

    @playlist.command(name="load", description="Muat playlist ke queue")
    @app_commands.describe(name="Nama playlist")
    async def playlist_load(self, interaction: discord.Interaction, name: str):
        db = get_db()
        if db is None:
            await interaction.response.send_message("Fitur playlist tidak tersedia (Firebase tidak terhubung).")
            return

        await interaction.response.defer()

        doc_id = f"{interaction.guild_id}_{interaction.user.id}_{name}"
        doc = get_db().collection("playlists").document(doc_id).get()

        if not doc.exists:
            await interaction.followup.send(f"Playlist {name} tidak ditemukan.")
            return

        data = doc.to_dict()
        track_data = data.get("tracks", [])

        if not track_data:
            await interaction.followup.send("Playlist kosong.")
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("Kamu harus join voice channel dulu!")
            return

        vc = interaction.user.voice.channel
        player = interaction.guild.voice_client
        if not player:
            player = await vc.connect(cls=wavelink.Player)
            player.home = interaction.channel
        elif player.channel != vc:
            await player.move_to(vc)
            player.home = interaction.channel

        added = 0
        failed = 0
        for t in track_data:
            try:
                results = await wavelink.Playable.search(t['uri'])
                if results:
                    await player.queue.put_wait(results[0])
                    added += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"[PLAYLIST LOAD ERROR] {e}")
                failed += 1

        if not player.current and not player.queue.is_empty:
            await player.play(player.queue.get())

        msg = f"Playlist {name} dimuat! ({added} lagu ditambahkan)"
        if failed:
            msg += f" | {failed} gagal dimuat"
        await interaction.followup.send(msg)

    @playlist.command(name="list", description="Lihat daftar playlist-mu")
    async def playlist_list(self, interaction: discord.Interaction):
        db = get_db()
        if db is None:
            await interaction.response.send_message("Fitur playlist tidak tersedia (Firebase tidak terhubung).")
            return

        playlists = (get_db().collection("playlists")
            .where("guild_id", "==", str(interaction.guild_id))
            .where("user_id", "==", str(interaction.user.id))
            .stream())

        embed = discord.Embed(title="Playlist-mu", color=discord.Color.blue())
        count = 0
        for doc in playlists:
            data = doc.to_dict()
            track_count = len(data.get("tracks", []))
            created = data.get("created_at")
            if created:
                created_str = created.strftime("%Y-%m-%d %H:%M") if isinstance(created, datetime) else str(created)
            else:
                created_str = "Unknown"
            embed.add_field(name=data['name'], value=f"{track_count} lagu - {created_str}", inline=False)
            count += 1

        if count == 0:
            embed.description = "Belum ada playlist. Gunakan /playlist save <nama> untuk membuat satu."

        await interaction.response.send_message(embed=embed)

    @playlist.command(name="delete", description="Hapus playlist")
    @app_commands.describe(name="Nama playlist yang mau dihapus")
    async def playlist_delete(self, interaction: discord.Interaction, name: str):
        db = get_db()
        if db is None:
            await interaction.response.send_message("Fitur playlist tidak tersedia (Firebase tidak terhubung).")
            return

        doc_id = f"{interaction.guild_id}_{interaction.user.id}_{name}"
        doc_ref = get_db().collection("playlists").document(doc_id)
        doc = doc_ref.get()

        if not doc.exists:
            await interaction.response.send_message(f"Playlist {name} tidak ditemukan.")
            return

        doc_ref.delete()
        await interaction.response.send_message(f"Playlist {name} dihapus.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))