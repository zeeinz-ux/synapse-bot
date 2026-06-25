import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import time
import os
import random
import re
from typing import Optional
import aiohttp
from datetime import datetime, timezone

from backend.utils.formatters import format_duration
from backend.cogs.music.spotify_down import SpotifyResolver, ResolvedTrack

from backend.cogs.music.ytdlp_source import YtDlpTrack, YtDlpPlaylist, YtDlpSearcher, MusicController

def get_db():
    try:
        from backend.cogs.database.firebase_setup import db
        return db
    except Exception as e:
        print(f"[FIREBASE LAZY IMPORT] {e}")
        return None


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.controllers = {}
        self._spotify_enabled = True
        self.spotify = SpotifyResolver(
            fallback_client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            fallback_client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        )
        print("[SPOTIFY] SpotifyDown API resolver aktif (fallback: Official API)")
        print(f"[DEBUG SPOTIFY] Client ID Terdeteksi: {os.getenv('SPOTIFY_CLIENT_ID')[:5]}***" if os.getenv('SPOTIFY_CLIENT_ID') else "[DEBUG SPOTIFY] Client ID TIDAK DITEMUKAN!")

    def get_controller(self, guild_id: int) -> MusicController:
        if guild_id not in self.controllers:
            vc = None
            for g in self.bot.guilds:
                if g.id == guild_id:
                    vc = g.voice_client
                    break
            self.controllers[guild_id] = MusicController(vc)
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
                return await YtDlpSearcher.extract_info(query)

            for prefix in ["ytsearch:", "ytmsearch:", "scsearch:", "spsearch:"]:
                if query.lower().startswith(prefix):
                    query = query[len(prefix):].strip()

            artists = track.artists or ""
            name = track.name or ""
            if not query:
                query = f"{artists} {name}"

            target_dur = track.duration_ms

            search_queries = []
            if artists:
                search_queries = [
                    f"ytsearch:{artists} - {name}",
                    f"ytsearch:{artists} {name} official audio",
                    f"ytsearch:{artists} {name} lyrics",
                    f"ytsearch:{artists} {name}",
                ]
            else:
                search_queries = [f"ytsearch:{name}"]

            for sq in search_queries:
                results = await YtDlpSearcher.search(sq)
                if not results:
                    continue

                candidates = []
                for r in results:
                    score = self._title_similarity(f"{artists} {name}", f"{r.author or ''} {r.title or ''}")
                    dur_diff = abs((r.duration or 0) - (target_dur or 0)) if target_dur else 0
                    candidates.append((r, score, dur_diff))

                candidates.sort(key=lambda x: (-x[1], x[2]))
                best, best_score, best_diff = candidates[0]

                if target_dur and best_diff < 3000:
                    return best
                if best_score > 0.5:
                    return best
                if sq == search_queries[-1]:
                    return best

        except Exception as e:
            print(f"[YOUTUBE SEARCH ERROR] {track.name}: {e}")
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

    async def _alone_disconnect(self, controller: MusicController, home: discord.TextChannel | None):
        await asyncio.sleep(30)
        if controller and controller.vc and controller.vc.channel:
            humans = [m for m in controller.vc.channel.members if not m.bot]
            if not humans:
                try:
                    await controller.disconnect()
                except Exception:
                    pass
                if home:
                    try:
                        await home.send("👋 Keluar dari voice channel karena tidak ada user.")
                    except Exception:
                        pass

    def _cancel_alone_task(self, guild_id: int):
        mp = self.get_music_player(guild_id)
        if mp._alone_task and not mp._alone_task.done():
            mp._alone_task.cancel()
            mp._alone_task = None

    # ==========================================================
    # EVENTS
    # ==========================================================
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild_id = member.guild.id
        controller = self.controllers.get(guild_id)
        if not controller or not controller.vc or not controller.vc.channel:
            return

        vc = controller.vc.channel
        humans = [m for m in vc.members if not m.bot]

        if not humans:
            if controller._alone_task is None or controller._alone_task.done():
                controller._alone_task = asyncio.create_task(self._alone_disconnect(controller, getattr(controller, 'home', None)))
        else:
            self._cancel_alone_task(guild_id)

    # ==========================================================
    # COMMANDS
    # ==========================================================
    @app_commands.command(name="play", description="Putar lagu dari URL atau search query")
    @app_commands.describe(query="URL (YouTube/Spotify/SoundCloud) atau nama lagu", channel="Voice channel tujuan (opsional, default: channel kamu sekarang)")
    async def play(
        self,
        interaction: discord.Interaction,
        query: str,
        channel: Optional[discord.VoiceChannel] = None,
    ):
        print(f"[PLAY CMD] Called by {interaction.user} with query: {query}")
        try:
            await interaction.response.defer()
        except Exception as e:
            print(f"[PLAY CMD] defer error: {e}")
            return
        vc = channel or (interaction.user.voice.channel if interaction.user.voice else None)
        if not vc:
            await interaction.followup.send("❌ Kamu harus join voice channel dulu atau tentukan channel tujuan!")
            return
        print(f"[PLAY CMD] Voice channel: {vc.name}")

        voice_client = interaction.guild.voice_client
        if not voice_client:
            print("[PLAY CMD] Creating new player...")
            try:
                voice_client = await vc.connect(self_deaf=False)
            except Exception as e:
                print(f"[PLAY CMD] Connect error: {e}")
                await interaction.followup.send(f"❌ Gagal connect ke voice: {e}")
                return
        elif voice_client.channel != vc:
            print("[PLAY CMD] Moving to new channel...")
            try:
                await voice_client.move_to(vc, self_deaf=False)
            except Exception as e:
                print(f"[PLAY CMD] Move error: {e}")
                await interaction.followup.send(f"❌ Gagal pindah channel: {e}")
                return

        guild_id = interaction.guild.id
        controller = self.get_controller(guild_id)
        controller.vc = voice_client
        controller.home = interaction.channel

        print(f"[PLAY CMD] Player ready. Current: {controller.current_track}")
        search_query = query.strip()

        # ==========================================================
        # HANDLE SPOTIFY URL
        # ==========================================================
        if self._is_spotify_url(search_query):
            spotify_info = self._extract_spotify_id(search_query)
            if not spotify_info:
                await interaction.followup.send("❌ URL Spotify tidak valid.")
                return
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
                return

            source_emoji = {
                "spotifydown": "🟢",
                "spotify_official": "🟡",
                "ytsearch": "🟠",
            }.get(source, "⚪")

            # SINGLE TRACK
            if spotify_type == "track":
                rt = resolved_tracks[0]
                print(f"[SPOTIFY TRACK] Resolved via {source} | Query: {rt.query}")

                clean_query = rt.query
                for prefix in ["ytsearch:", "ytmsearch:", "scsearch:", "spsearch:"]:
                    if clean_query.lower().startswith(prefix):
                        clean_query = clean_query[len(prefix):].strip()

                try:
                    tracks = await YtDlpSearcher.search(f"ytsearch:{clean_query}")
                except Exception as e:
                    print(f"[SPOTIFY TRACK ERROR] {e}")
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
                total_tracks = len(resolved_tracks)
                print(f"[SPOTIFY {spotify_type.upper()}] {total_tracks} tracks resolved via {source}")

                total_ms = sum(t.duration_ms or 0 for t in resolved_tracks)
                total_duration = format_duration(total_ms) if total_ms > 0 else "Unknown"

                thumbnail = None
                for t in resolved_tracks:
                    if t.artwork:
                        thumbnail = t.artwork
                        break

                await loading_msg.edit(content=f"⏳ Mencari {total_tracks} lagu di YouTube... (0/{total_tracks})")

                playables: list[Optional[YtDlpTrack]] = [None] * total_tracks
                sem = asyncio.Semaphore(5)

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
                    icon_url=interaction.user.display_avatar.url
                )
                final_embed.add_field(name="🔢 Jumlah Lagu", value=f"`{total_tracks} Lagu`", inline=True)
                final_embed.add_field(name="⏳ Total Durasi", value=f"`{total_duration}`", inline=True)
                final_embed.add_field(name="👤 Request Oleh", value=interaction.user.mention, inline=True)
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
            print(f"[PLAY CMD] Direct URL detected: {search_query}")

            is_playlist_url = (
                "/playlist?" in search_query.lower() or
                "list=" in search_query.lower() or
                "soundcloud.com/" in search_query.lower() and "/sets/" in search_query.lower()
            )

            if is_playlist_url:
                playlist = await YtDlpSearcher.extract_playlist(search_query)
                if playlist and playlist.tracks:
                    added = 0
                    for t in playlist.tracks:
                        controller.queue.append(t)
                        added += 1
                    print(f"[PLAY CMD] Added {added} tracks from playlist: {playlist.name}")
                    if not controller.current_track and controller.queue:
                        await controller.set_volume(100)
                        await asyncio.sleep(0.3)
                        next_track = controller.queue.pop(0)
                        await controller.play(next_track)
                    await interaction.followup.send(f"✅ Playlist ditambahkan! ({added} lagu dari {playlist.name})")
                    return
                else:
                    await interaction.followup.send("❌ Gagal memuat playlist.")
                    return

            track = await YtDlpSearcher.extract_info(search_query)
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
                await interaction.followup.send(embed=embed)
                return
            else:
                await interaction.followup.send("❌ Gagal memproses URL.")
                return

        # ==========================================================
        # HANDLE SEARCH QUERY
        # ==========================================================
        clean_input = search_query
        prefixes = ["ytsearch:", "ytmsearch:", "scsearch:", "spsearch:"]
        for p in prefixes:
            if clean_input.lower().startswith(p):
                clean_input = clean_input[len(p):].strip()

        print(f"[PLAY CMD] Searching: ytsearch:{clean_input}")
        try:
            tracks = await asyncio.wait_for(
                YtDlpSearcher.search(f"ytsearch:{clean_input}"),
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

        track = tracks[0]
        print(f"[PLAY CMD] Single track: {track.title}")
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
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="pause", description="Pause lagu yang sedang diputar")
    async def pause(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            await interaction.response.send_message("❌ Tidak ada lagu yang sedang diputar.", ephemeral=True)
            return
        voice_client.pause()
        controller = self.get_controller(interaction.guild_id)
        controller._paused = True
        controller._paused_position = time.time() - controller._start_time
        await controller._update_now_playing()
        await interaction.response.send_message("⏸️ Lagu di-pause.")

    @app_commands.command(name="resume", description="Lanjutkan lagu yang di-pause")
    async def resume(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_paused():
            await interaction.response.send_message("❌ Tidak ada lagu yang di-pause.", ephemeral=True)
            return
        voice_client.resume()
        controller = self.get_controller(interaction.guild_id)
        controller._paused = False
        controller._start_time = time.time() - controller._paused_position
        await controller._update_now_playing()
        await interaction.response.send_message("▶️ Lagu dilanjutkan.")

    @app_commands.command(name="skip", description="Skip ke lagu berikutnya")
    async def skip(self, interaction: discord.Interaction):
        controller = self.get_controller(interaction.guild_id)
        voice_client = interaction.guild.voice_client
        if not voice_client or not controller.current_track:
            await interaction.response.send_message("❌ Tidak ada lagu yang sedang diputar.", ephemeral=True)
            return
        skipped = controller.current_track
        if controller.queue:
            next_track = controller.queue.pop(0)
            voice_client.stop()
            await asyncio.sleep(0.2)
            await controller.play(next_track)
            await interaction.response.send_message(
                f"⏭️ Skipped: **{skipped.title}** | Now Playing: **{next_track.title}**"
            )
        else:
            voice_client.stop()
            controller.current_track = None
            controller._last_track_id = None
            await interaction.response.send_message(
                f"⏭️ Skipped: **{skipped.title}** | Queue kosong."
            )

    @app_commands.command(name="stop", description="Stop lagu, clear queue, keluar voice channel")
    async def stop(self, interaction: discord.Interaction):
        controller = self.get_controller(interaction.guild_id)
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message("❌ Bot tidak ada di voice channel.", ephemeral=True)
            return
        await controller.stop()
        await interaction.response.send_message("⏹️ Music player dihentikan dan queue di-clear.")

    @app_commands.command(name="queue", description="Lihat antrian lagu")
    async def queue(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except Exception:
            pass
        controller = self.get_controller(interaction.guild_id)
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.followup.send("📭 Queue kosong.")
            return

        if not controller.home:
            controller.home = interaction.channel
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
            print(f"[QUEUE ERROR] {e}")
            await interaction.followup.send("❌ Gagal menampilkan queue.")
            return

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="nowplaying", description="Info detail lagu yang sedang diputar")
    async def nowplaying(self, interaction: discord.Interaction):
        controller = self.get_controller(interaction.guild_id)
        voice_client = interaction.guild.voice_client
        if not voice_client or not controller.current_track:
            await interaction.response.send_message("❌ Tidak ada lagu yang sedang diputar.", ephemeral=True)
            return

        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        if not controller.home:
            controller.home = interaction.channel
        await controller._update_now_playing()
        await interaction.followup.send("▶️ Cek pesan **Now Playing** di atas untuk info lengkap.", ephemeral=True)

    @app_commands.command(name="volume", description="Atur volume bot (0-1000)")
    @app_commands.describe(level="Volume level 0-1000 (default 100)")
    async def volume(self, interaction: discord.Interaction, level: int):
        if not 0 <= level <= 1000:
            await interaction.response.send_message("❌ Volume harus antara 0-1000.", ephemeral=True)
            return
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message("❌ Bot tidak ada di voice channel.", ephemeral=True)
            return
        controller = self.get_controller(interaction.guild_id)
        await controller.set_volume(level)
        await interaction.response.send_message(f"🔊 Volume diatur ke **{level}%**.")

    @app_commands.command(name="loop", description="Atur mode loop lagu/queue")
    @app_commands.describe(mode="Pilih mode loop")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Single (Lagu Ini)", value="single"),
        app_commands.Choice(name="Queue (Semua Lagu)", value="queue"),
    ])
    async def loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        controller = self.get_controller(interaction.guild_id)
        controller.loop_mode = mode.value
        if mode.value == "queue":
            controller._queue_history.clear()
        if mode.value == "off":
            controller._single_loop_track = None
        await interaction.response.send_message(f"🔁 Loop mode: **{mode.name}**")

    @app_commands.command(name="shuffle", description="Acak antrian lagu")
    async def shuffle(self, interaction: discord.Interaction):
        controller = self.get_controller(interaction.guild_id)
        if not controller.queue:
            await interaction.response.send_message("📭 Queue kosong, tidak ada yang bisa diacak.", ephemeral=True)
            return
        random.shuffle(controller.queue)
        controller._queue_history.clear()
        await interaction.response.send_message(f"🔀 Queue diacak! ({len(controller.queue)} lagu)")

    @app_commands.command(name="autoplay", description="Toggle autoplay: bot cari lagu serupa ketika queue habis")
    async def autoplay(self, interaction: discord.Interaction):
        controller = self.get_controller(interaction.guild_id)
        controller.autoplay = not controller.autoplay
        status = "ON ✅" if controller.autoplay else "OFF ❌"
        await interaction.response.send_message(f"🤖 Autoplay sekarang: **{status}**")

    @app_commands.command(name="seek", description="Skip ke posisi tertentu dalam lagu")
    @app_commands.describe(position="Format: 1:30 atau 90 (detik)")
    async def seek(self, interaction: discord.Interaction, position: str):
        controller = self.get_controller(interaction.guild_id)
        voice_client = interaction.guild.voice_client
        if not voice_client or not controller.current_track:
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
        if controller.current_track.duration and ms > controller.current_track.duration:
            await interaction.response.send_message("❌ Posisi melebihi durasi lagu.", ephemeral=True)
            return

        await controller.seek(ms)
        await interaction.response.send_message(f"⏩ Skip ke `{format_duration(ms)}`.")

    @app_commands.command(name="remove", description="Hapus lagu dari queue berdasarkan nomor")
    @app_commands.describe(index="Nomor lagu di /queue")
    async def remove(self, interaction: discord.Interaction, index: int):
        controller = self.get_controller(interaction.guild_id)
        if not controller.queue:
            await interaction.response.send_message("📭 Queue kosong.", ephemeral=True)
            return
        if index < 1:
            await interaction.response.send_message("❌ Nomor harus mulai dari 1.", ephemeral=True)
            return
        if index > len(controller.queue):
            await interaction.response.send_message(f"❌ Queue cuma ada {len(controller.queue)} lagu.", ephemeral=True)
            return
        async with controller._track_lock:
            removed = controller.queue.pop(index - 1)
        await interaction.response.send_message(f"🗑️ Dihapus dari queue: **{removed.title}**")

    @app_commands.command(name="move", description="Pindah posisi lagu di queue")
    @app_commands.describe(from_index="Posisi asal", to_index="Posisi tujuan")
    async def move(self, interaction: discord.Interaction, from_index: int, to_index: int):
        controller = self.get_controller(interaction.guild_id)
        if not controller.queue:
            await interaction.response.send_message("📭 Queue kosong.", ephemeral=True)
            return
        if not (1 <= from_index <= len(controller.queue)) or not (1 <= to_index <= len(controller.queue)):
            await interaction.response.send_message(f"❌ Index harus antara 1 dan {len(controller.queue)}.", ephemeral=True)
            return
        async with controller._track_lock:
            track = controller.queue.pop(from_index - 1)
            controller.queue.insert(to_index - 1, track)
        await interaction.response.send_message(f"↔️ Dipindah: **{track.title}** ke posisi `{to_index}`")

    @app_commands.command(name="skipto", description="Skip ke lagu nomor tertentu di queue")
    @app_commands.describe(index="Nomor lagu di /queue")
    async def skipto(self, interaction: discord.Interaction, index: int):
        controller = self.get_controller(interaction.guild_id)
        voice_client = interaction.guild.voice_client
        if not voice_client or not controller.queue:
            await interaction.response.send_message("📭 Queue kosong.", ephemeral=True)
            return
        if not (1 <= index <= len(controller.queue)):
            await interaction.response.send_message(f"❌ Index harus antara 1 dan {len(controller.queue)}.", ephemeral=True)
            return
        async with controller._track_lock:
            target = controller.queue.pop(index - 1)
            new_queue = [target] + controller.queue
            controller.queue = new_queue
        voice_client.stop()
        await asyncio.sleep(0.3)
        if controller.queue:
            next_track = controller.queue.pop(0)
            await controller.play(next_track)
            await interaction.response.send_message(f"⏭️ Skip ke: **{next_track.title}**")
        else:
            await interaction.response.send_message("📭 Queue kosong setelah reorder.")

    @app_commands.command(name="disconnect", description="Keluar dari voice channel")
    async def disconnect(self, interaction: discord.Interaction):
        controller = self.get_controller(interaction.guild_id)
        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message("❌ Bot tidak di voice channel.", ephemeral=True)
            return
        await controller.disconnect()
        await interaction.response.send_message("🔌 Keluar dari voice channel.")

    @app_commands.command(name="clearqueue", description="Kosongkan queue tanpa menghentikan lagu yang sedang diputar")
    async def clearqueue(self, interaction: discord.Interaction):
        controller = self.get_controller(interaction.guild_id)
        if not controller.queue:
            await interaction.response.send_message("📭 Queue sudah kosong.", ephemeral=True)
            return
        controller.queue.clear()
        controller._queue_history.clear()
        await interaction.response.send_message("🧹 Queue dikosongkan. Lagu yang sedang diputar tetap jalan.")

    @app_commands.command(name="replay", description="Putar ulang lagu dari awal")
    async def replay(self, interaction: discord.Interaction):
        controller = self.get_controller(interaction.guild_id)
        voice_client = interaction.guild.voice_client
        if not voice_client or not controller.current_track:
            await interaction.response.send_message("❌ Tidak ada lagu yang sedang diputar.", ephemeral=True)
            return
        await controller.play(controller.current_track)
        await interaction.response.send_message("🔁 Replay dari awal.")

    @app_commands.command(name="lyrics", description="Cari lirik lagu yang sedang diputar atau dari judul")
    @app_commands.describe(query="Judul lagu (opsional, default: lagu yang sedang diputar)")
    async def lyrics(self, interaction: discord.Interaction, query: str = None):
        if not query:
            controller = self.get_controller(interaction.guild_id)
            if controller.current_track:
                query = f"{controller.current_track.title} {controller.current_track.author or ''}"
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
        controller = self.get_controller(interaction.guild_id)
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
        voice_client = interaction.guild.voice_client
        if not voice_client:
            voice_client = await vc.connect(self_deaf=False)
            controller = self.get_controller(interaction.guild_id)
            controller.vc = voice_client
            controller.home = interaction.channel
        elif voice_client.channel != vc:
            await voice_client.move_to(vc, self_deaf=False)

        controller = self.get_controller(interaction.guild_id)
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
                    print(f"[PLAYLIST CONCURRENT LOAD ERROR] {e}")
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
