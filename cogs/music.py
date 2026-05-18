import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os
import re
from urllib.parse import urlparse

# ==============================================================================
# YT-DLP CONFIG (Kualitas Jernih)
# ==============================================================================
YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '320',
    }],
    # Force high quality audio extraction
    'audioformat': 'mp3',
    'audioquality': '0',  # 0 = best
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -ar 48000 -ac 2 -b:a 320k',  # 48kHz, stereo, 320kbps
}

ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)

# ==============================================================================
# SPOTIFY SETUP
# ==============================================================================
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")

spotify = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    try:
        spotify_credentials = SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        )
        spotify = spotipy.Spotify(client_credentials_manager=spotify_credentials)
        print("[SPOTIFY] ✅ Spotify API connected!")
    except Exception as e:
        print(f"[SPOTIFY] ❌ Failed to connect: {e}")
else:
    print("[SPOTIFY] ⚠️ SPOTIFY_CLIENT_ID/SECRET not found. Spotify features disabled.")

# ==============================================================================
# MUSIC CLASSES
# ==============================================================================
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.uploader = data.get('uploader')
        self.webpage_url = data.get('webpage_url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

class Song:
    def __init__(self, source, requester):
        self.source = source
        self.requester = requester

class MusicPlayer:
    def __init__(self, bot, guild):
        self.bot = bot
        self.guild = guild
        self.queue = asyncio.Queue()
        self.next = asyncio.Event()
        self.current = None
        self.volume = 0.5
        self.np_message = None

        self.bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()

            try:
                async with asyncio.timeout(300):  # 5 menit timeout
                    song = await self.queue.get()
            except asyncio.TimeoutError:
                if self.guild.voice_client:
                    await self.guild.voice_client.disconnect()
                return

            self.current = song
            self.guild.voice_client.play(
                song.source, 
                after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set)
            )

            # Update now playing message
            await self.update_np_message(song)

            await self.next.wait()
            self.current = None

            # Cleanup
            song.source.cleanup()

    async def update_np_message(self, song):
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"[{song.source.title}]({song.source.webpage_url})",
            color=discord.Color.green()
        )
        embed.add_field(name="👤 Requested by", value=song.requester.mention, inline=True)
        embed.add_field(name="⏱️ Duration", value=self.format_duration(song.source.duration), inline=True)
        embed.set_thumbnail(url=song.source.thumbnail)
        embed.set_footer(text=f"Volume: {int(self.volume * 100)}%")

        if self.np_message:
            try:
                await self.np_message.edit(embed=embed)
            except:
                pass

    @staticmethod
    def format_duration(seconds):
        if not seconds:
            return "Unknown"
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

# ==============================================================================
# MUSIC COG
# ==============================================================================
class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}

    def get_player(self, guild):
        if guild.id not in self.players:
            self.players[guild.id] = MusicPlayer(self.bot, guild)
        return self.players[guild.id]

    def is_url(self, string):
        try:
            result = urlparse(string)
            return all([result.scheme, result.netloc])
        except:
            return False

    def is_spotify_url(self, url):
        return 'spotify.com' in url or 'open.spotify.com' in url

    def is_youtube_url(self, url):
        return any(x in url for x in ['youtube.com', 'youtu.be', 'music.youtube.com'])

    async def search_spotify(self, query):
        """Cari lagu di Spotify dan return YouTube search query"""
        if not spotify:
            return None

        try:
            # Extract track ID dari URL
            if 'track' in query:
                track_id = query.split('/track/')[1].split('?')[0]
                track = spotify.track(track_id)
            else:
                # Search by query
                results = spotify.search(q=query, type='track', limit=1)
                if not results['tracks']['items']:
                    return None
                track = results['tracks']['items'][0]

            # Format: "Artist - Title" untuk search di YouTube
            artists = ', '.join([a['name'] for a in track['artists']])
            search_query = f"{artists} - {track['name']} official audio"

            return {
                'title': track['name'],
                'artist': artists,
                'search_query': search_query,
                'duration': track['duration_ms'] // 1000,
                'thumbnail': track['album']['images'][0]['url'] if track['album']['images'] else None,
                'url': track['external_urls']['spotify']
            }
        except Exception as e:
            print(f"[SPOTIFY] Error: {e}")
            return None

    async def search_youtube(self, query):
        """Search YouTube dan return URL"""
        try:
            data = await self.bot.loop.run_in_executor(
                None, 
                lambda: ytdl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
            )
            return data
        except Exception as e:
            print(f"[YOUTUBE] Error: {e}")
            return None

    # ==========================================================================
    # SLASH COMMANDS
    # ==========================================================================

    @app_commands.command(name="play", description="Putar lagu dari YouTube atau Spotify")
    @app_commands.describe(query="Judul lagu, URL YouTube, atau URL Spotify")
    async def play(self, interaction: discord.Interaction, query: str):
        # Cek user di voice channel
        if not interaction.user.voice:
            await interaction.response.send_message(
                "❌ Kamu harus join voice channel dulu!", 
                ephemeral=True
            )
            return

        await interaction.response.send_message("🔍 Mencari lagu...", ephemeral=True)

        # Connect ke voice channel
        voice_channel = interaction.user.voice.channel
        if not interaction.guild.voice_client:
            await voice_channel.connect()
        elif interaction.guild.voice_client.channel != voice_channel:
            await interaction.guild.voice_client.move_to(voice_channel)

        # Proses query
        search_query = query
        spotify_info = None

        if self.is_url(query):
            if self.is_spotify_url(query):
                if not spotify:
                    await interaction.edit_original_response(
                        content="❌ Spotify API tidak tersedia. Tambahkan SPOTIFY_CLIENT_ID & SPOTIFY_CLIENT_SECRET di .env"
                    )
                    return

                await interaction.edit_original_response(content="🎵 Mengambil info dari Spotify...")
                spotify_info = await self.search_spotify(query)
                if not spotify_info:
                    await interaction.edit_original_response(content="❌ Lagu Spotify tidak ditemukan!")
                    return
                search_query = spotify_info['search_query']

            elif not self.is_youtube_url(query):
                await interaction.edit_original_response(content="❌ URL tidak valid! Hanya support YouTube dan Spotify.")
                return

        # Search & download dari YouTube
        await interaction.edit_original_response(content="⬇️ Mengunduh audio berkualitas tinggi...")

        try:
            if self.is_youtube_url(query):
                data = await self.bot.loop.run_in_executor(
                    None,
                    lambda: ytdl.extract_info(query, download=False)
                )
                if 'entries' in data:
                    data = data['entries'][0]
            else:
                data = await self.search_youtube(search_query)
                if not data:
                    await interaction.edit_original_response(content="❌ Lagu tidak ditemukan di YouTube!")
                    return

            # Buat source
            source = await YTDLSource.from_url(data['webpage_url'], loop=self.bot.loop, stream=True)

            # Override info kalau dari Spotify
            if spotify_info:
                source.title = f"{spotify_info['artist']} - {spotify_info['title']}"
                source.thumbnail = spotify_info['thumbnail']

            # Add to queue
            player = self.get_player(interaction.guild)
            song = Song(source, interaction.user)
            await player.queue.put(song)

            # Response
            queue_size = player.queue.qsize()
            embed = discord.Embed(
                title="🎵 Added to Queue" if queue_size > 1 else "🎵 Now Playing",
                description=f"[{source.title}]({source.webpage_url})",
                color=discord.Color.green()
            )
            embed.add_field(name="👤 Requested by", value=interaction.user.mention, inline=True)
            embed.add_field(name="🔊 Quality", value="320kbps | 48kHz | Stereo", inline=True)
            embed.add_field(name="📊 Queue Position", value=str(queue_size), inline=True)
            embed.set_thumbnail(url=source.thumbnail)

            await interaction.edit_original_response(content=None, embed=embed)

            # Set NP message channel
            player.np_message = await interaction.channel.send(embed=embed)

        except Exception as e:
            await interaction.edit_original_response(content=f"❌ Error: {str(e)}")
            print(f"[MUSIC ERROR] {e}")

    @app_commands.command(name="pause", description="Pause lagu yang sedang diputar")
    async def pause(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Lagu di-pause.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Tidak ada lagu yang diputar!", ephemeral=True)

    @app_commands.command(name="resume", description="Lanjutkan lagu yang di-pause")
    async def resume(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Lagu dilanjutkan.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Tidak ada lagu yang di-pause!", ephemeral=True)

    @app_commands.command(name="skip", description="Skip lagu yang sedang diputar")
    async def skip(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ Lagu di-skip.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Tidak ada lagu yang diputar!", ephemeral=True)

    @app_commands.command(name="stop", description="Stop lagu & keluar dari voice channel")
    async def stop(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc:
            # Clear queue
            player = self.get_player(interaction.guild)
            while not player.queue.empty():
                try:
                    player.queue.get_nowait()
                except:
                    break

            await vc.disconnect()
            if interaction.guild.id in self.players:
                del self.players[interaction.guild.id]

            await interaction.response.send_message("👋 Bot keluar dari voice channel.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bot tidak di voice channel!", ephemeral=True)

    @app_commands.command(name="queue", description="Lihat antrian lagu")
    async def queue(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)

        if player.queue.empty() and not player.current:
            await interaction.response.send_message("📭 Queue kosong!", ephemeral=True)
            return

        embed = discord.Embed(title="🎵 Music Queue", color=discord.Color.blue())

        # Current song
        if player.current:
            embed.add_field(
                name="▶️ Now Playing",
                value=f"[{player.current.source.title}]({player.current.source.webpage_url}) | {player.current.requester.mention}",
                inline=False
            )

        # Queue list
        queue_list = []
        temp_queue = list(player.queue._queue)
        for i, song in enumerate(temp_queue[:10], 1):
            queue_list.append(f"`{i}.` [{song.source.title}]({song.source.webpage_url}) | {song.requester.mention}")

        if queue_list:
            embed.add_field(
                name="📋 Up Next",
                value="\n".join(queue_list),
                inline=False
            )

        if len(temp_queue) > 10:
            embed.set_footer(text=f"Dan {len(temp_queue) - 10} lagu lainnya...")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="nowplaying", description="Lihat lagu yang sedang diputar")
    async def nowplaying(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)

        if not player.current:
            await interaction.response.send_message("❌ Tidak ada lagu yang diputar!", ephemeral=True)
            return

        source = player.current.source
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"[{source.title}]({source.webpage_url})",
            color=discord.Color.green()
        )
        embed.add_field(name="👤 Requested by", value=player.current.requester.mention, inline=True)
        embed.add_field(name="⏱️ Duration", value=player.format_duration(source.duration), inline=True)
        embed.add_field(name="🔊 Quality", value="320kbps | 48kHz | Stereo", inline=True)
        embed.set_thumbnail(url=source.thumbnail)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="volume", description="Atur volume bot (0-100)")
    @app_commands.describe(level="Volume level 0-100")
    async def volume(self, interaction: discord.Interaction, level: int):
        if not 0 <= level <= 100:
            await interaction.response.send_message("❌ Volume harus antara 0-100!", ephemeral=True)
            return

        player = self.get_player(interaction.guild)
        player.volume = level / 100

        if interaction.guild.voice_client and interaction.guild.voice_client.source:
            interaction.guild.voice_client.source.volume = player.volume

        await interaction.response.send_message(f"🔊 Volume diatur ke **{level}%**", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MusicCog(bot))
