import discord
from discord.ext import commands
import asyncio
import os
import re
import time
import random
import sys
from yt_dlp import YoutubeDL

try:
    from backend.cogs.database.firebase_setup import db
    _HAS_FS = True
except Exception:
    db = None
    _HAS_FS = False

LOFI_DEFAULT_URL = "https://play.streamafrica.net/lofiradio"
LOFI_KEYWORDS = {"lofi", "lo-fi", "lo_fi", "lofi radio", "default", "radio"}


def _update_ytdlp():
    import subprocess, importlib.metadata
    try:
        ver = importlib.metadata.version("yt-dlp")
        print(f"[MUSIC] yt-dlp version: {ver}", flush=True)
    except Exception:
        ver = "?"
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True, timeout=60, check=False
        )
        new_ver = importlib.metadata.version("yt-dlp")
        if new_ver != ver:
            print(f"[MUSIC] yt-dlp upgraded: {ver} -> {new_ver}", flush=True)
    except Exception as e:
        print(f"[MUSIC] yt-dlp update skipped: {e}", flush=True)


def _get_cookies_path():
    for p in ["cookies/cookies.txt", "cookies.txt", "/etc/secrets/cookies.txt"]:
        if os.path.isfile(p):
            size = os.path.getsize(p)
            print(f"[MUSIC] Found cookies file: {p} ({size} bytes)", flush=True)
            return p
    print("[MUSIC] No cookies file found", flush=True)
    return None
VOICE_STATE_COLLECTION = "voice_state"
COLOR = 0x5865F2


def _is_youtube_url(url: str) -> bool:
    return bool(re.search(r'(youtube\.com|youtu\.be)', url, re.IGNORECASE))


def _clean_url(url: str) -> str:
    if "youtube.com/watch?" in url:
        url = re.sub(r'&list=[^&]*', '', url)
        url = re.sub(r'&start_radio=[^&]*', '', url)
        url = re.sub(r'&index=[^&]*', '', url)
    return url


_YT_FORMATS = ["ba/b", "bestaudio*", "worstaudio/worst"]
_YT_CLIENTS_PREFERRED = [
    ["tv", "mweb", "android_vr", "visionos"],
    ["web"],
    ["android"],
]
_YT_CLIENTS_FALLBACK = [
    ["ios"],
    ["web_safari"],
]

_PO_TOKEN_RAW = os.environ.get("YOUTUBE_PO_TOKEN") or os.environ.get("PO_TOKEN", "")
if _PO_TOKEN_RAW:
    print(f"[MUSIC] PO_TOKEN detected ({len(_PO_TOKEN_RAW)} chars)", flush=True)
    print(f"[MUSIC] PO_TOKEN first 20: {_PO_TOKEN_RAW[:20]}...", flush=True)
else:
    print("[MUSIC] PO_TOKEN not set in env (checked YOUTUBE_PO_TOKEN and PO_TOKEN)", flush=True)
    print(f"[MUSIC] Env keys with PO: {[k for k in os.environ if 'PO' in k.upper() or 'TOKEN' in k.upper()]}", flush=True)

def _build_extractor_args(client_list: list[str], use_cookies: bool, use_po: bool) -> dict:
    ea = {"youtube": {"player_client": client_list}}
    if use_po and _PO_TOKEN_RAW:
        contexts = ["gvs", "player"]
        prefixed = []
        for ctx in contexts:
            for c in client_list:
                prefixed.append(f"{c}.{ctx}+{_PO_TOKEN_RAW}")
        ea["youtube"]["po_token"] = prefixed
    if not use_cookies:
        ea["youtube"]["player_skip"] = ["webpage", "configs"]
    return ea

def _yt_fetch(url_or_query: str) -> dict | None:
    cookies_file = _get_cookies_path()
    has_po = bool(_PO_TOKEN_RAW)
    print(f"[MUSIC DEBUG] _PO_TOKEN_RAW len={len(_PO_TOKEN_RAW)} has_po={has_po}", flush=True)
    if has_po:
        print(f"[MUSIC DEBUG] PO_TOKEN prefix: {_PO_TOKEN_RAW[:30]}...", flush=True)

    # Phases: no-cookie -> cookie -> cookie+po_token
    # Preferred clients tried first, fallback clients only if preferred fail
    phases = [(False, False), (True, False)]
    if has_po:
        phases.append((True, True))

    for use_cookies, use_po in phases:
        tag = "no-cookie"
        if use_cookies and use_po:
            tag = "cookie+po"
        elif use_cookies:
            tag = "cookie"
        client_groups = _YT_CLIENTS_PREFERRED
        if use_cookies:
            client_groups = _YT_CLIENTS_PREFERRED + _YT_CLIENTS_FALLBACK
        for clients in client_groups:
            for fmt in _YT_FORMATS:
                ea = _build_extractor_args(clients, use_cookies, use_po)
                opts = dict(format=fmt)
                opts.update(
                    noplaylist=True,
                    quiet=True,
                    no_warnings=True,
                    ignoreerrors=True,
                    extract_flat=False,
                    socket_timeout=15,
                    extractor_retries=0,
                    ignore_no_formats_error=True,
                    extractor_args=ea,
                )
                if use_cookies and cookies_file:
                    opts["cookiefile"] = cookies_file
                try:
                    with YoutubeDL(opts) as ydl:
                        data = ydl.extract_info(url_or_query, download=False)
                        if not data:
                            continue
                        if data.get("is_live"):
                            continue
                        title = data.get("title", "Unknown")
                        if isinstance(title, str):
                            title = title.encode("utf-8", errors="replace").decode("utf-8")
                        webpage_url = data.get("webpage_url") or data.get("url", "")
                        if not webpage_url:
                            formats = data.get("formats", [])
                            print(f"[MUSIC] {tag} (clients={clients}, fmt={fmt}): no webpage_url, {len(formats)} formats", flush=True)
                            continue
                        print(f"[MUSIC] {tag} (clients={clients}, fmt={fmt}) metadata: {title[:60]}", flush=True)
                        return {
                            "webpage_url": webpage_url,
                            "title": title,
                            "thumbnail": data.get("thumbnail", ""),
                        }
                except Exception as e:
                    print(f"[MUSIC] {tag} (clients={clients}, fmt={fmt}) exception: {e}", flush=True)

    print(f"[MUSIC] all attempts failed for: {url_or_query[:80]}", flush=True)
    return None


class SearchSelect(discord.ui.Select):
    def __init__(self, tracks: list[dict], cog):
        options = []
        for i, t in enumerate(tracks[:5]):
            label = t.get("title", "Unknown")[:90]
            options.append(discord.SelectOption(label=label, value=str(i)))
        super().__init__(placeholder="Pilih lagu...", options=options, min_values=1, max_values=1)
        self.tracks = tracks
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        idx = int(self.values[0])
        track = self.tracks[idx]
        await interaction.response.defer()
        gid = interaction.guild_id
        vc = interaction.guild.voice_client
        if not vc:
            if interaction.user.voice and interaction.user.voice.channel:
                vc = await interaction.user.voice.channel.connect()
            else:
                await interaction.followup.send("Bot gak di voice. Join voice dulu.", ephemeral=True)
                return
        if vc.is_playing():
            current = self.cog._now_playing.get(gid)
            is_stream = current and not _is_youtube_url(current.get("url", ""))
            if is_stream:
                self.cog._intentional_stop.add(gid)
                vc.stop()
                await asyncio.sleep(0.3)
                self.cog._add_to_queue(gid, track)
                self.cog._current_index[gid] = len(self.cog._queues[gid]) - 1
                self.cog._now_playing[gid] = track
                self.cog._play_looping(vc, track["url"])
                embed = discord.Embed(
                    title="\u25b6 Now Playing",
                    description=f"**{track.get('title', 'Unknown')}**",
                    color=COLOR
                )
                if track.get("thumbnail"):
                    embed.set_thumbnail(url=track["thumbnail"])
            else:
                pos = self.cog._add_to_queue(gid, track)
                embed = discord.Embed(
                    title="\u2795 Added to Queue",
                    description=f"**{track.get('title', 'Unknown')}**\nPosisi #{pos + 1}",
                    color=COLOR
                )
                if track.get("thumbnail"):
                    embed.set_thumbnail(url=track["thumbnail"])
        else:
            self.cog._add_to_queue(gid, track)
            self.cog._current_index[gid] = len(self.cog._queues[gid]) - 1
            self.cog._now_playing[gid] = track
            self.cog._play_looping(vc, track["url"])
            embed = discord.Embed(
                title="\u25b6 Now Playing",
                description=f"**{track.get('title', 'Unknown')}**",
                color=COLOR
            )
            if track.get("thumbnail"):
                embed.set_thumbnail(url=track["thumbnail"])
        if not self.cog._is_now_playing_dup(gid, track):
            await interaction.followup.send(embed=embed)


class SearchView(discord.ui.View):
    def __init__(self, tracks: list[dict], cog, *, timeout=60):
        super().__init__(timeout=timeout)
        self.add_item(SearchSelect(tracks, cog))


class MusicCog(commands.Cog, name="Music"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._voice_states: dict[int, dict] = {}
        self._intentional_stop: set[int] = set()
        self._queues: dict[int, list[dict]] = {}
        self._current_index: dict[int, int] = {}
        self._loop_mode: dict[int, str] = {}
        self._now_playing: dict[int, dict] = {}
        self._last_now_playing_url: dict[int, str] = {}
        self._last_now_playing_at: dict[int, float] = {}
        self._ytdlp_procs = {}

    # --- state persistence ---
    def _save_state(self, guild_id: int, channel_id: int, url: str):
        data = {"guild_id": guild_id, "channel_id": channel_id, "url": url, "updated_at": time.time()}
        self._voice_states[guild_id] = data
        if _HAS_FS and db is not None:
            try:
                asyncio.ensure_future(asyncio.to_thread(
                    lambda: db.collection(VOICE_STATE_COLLECTION).document(str(guild_id)).set(data)
                ))
            except Exception:
                pass

    def _clear_state(self, guild_id: int):
        self._voice_states.pop(guild_id, None)
        if _HAS_FS and db is not None:
            try:
                asyncio.ensure_future(asyncio.to_thread(
                    lambda: db.collection(VOICE_STATE_COLLECTION).document(str(guild_id)).delete()
                ))
            except Exception:
                pass

    async def _restore_states(self):
        if not _HAS_FS or db is None:
            return
        try:
            docs = await asyncio.to_thread(
                lambda: list(db.collection(VOICE_STATE_COLLECTION).stream())
            )
        except Exception:
            return
        for doc in docs:
            data = doc.to_dict()
            if not data:
                continue
            gid = data.get("guild_id")
            cid = data.get("channel_id")
            url = data.get("url", LOFI_DEFAULT_URL)
            if not gid or not cid:
                continue
            guild = self.bot.get_guild(int(gid))
            if not guild:
                continue
            channel = guild.get_channel(int(cid))
            if not channel or not isinstance(channel, discord.VoiceChannel):
                continue
            vc = guild.voice_client
            if vc:
                continue
            try:
                vc = await channel.connect()
                await asyncio.sleep(0.5)
                self._play_looping(vc, url)
                self._save_state(guild.id, channel.id, url)
                print(f"[MUSIC] Auto-resume: {guild.name} / {channel.name}")
            except Exception as e:
                print(f"[MUSIC] Auto-resume failed for {guild.name}: {e}")

    MAX_QUEUE_SIZE = 20

    # --- queue helpers ---
    def _ensure_queue(self, guild_id: int):
        if guild_id not in self._queues:
            self._queues[guild_id] = []
        if guild_id not in self._current_index:
            self._current_index[guild_id] = -1

    def _add_to_queue(self, guild_id: int, track: dict) -> int:
        self._ensure_queue(guild_id)
        q = self._queues[guild_id]
        if len(q) >= self.MAX_QUEUE_SIZE:
            return -1
        q.append(track)
        return len(q) - 1

    def _clear_queue(self, guild_id: int):
        self._queues.pop(guild_id, None)
        self._current_index.pop(guild_id, None)
        self._now_playing.pop(guild_id, None)
        self._last_now_playing_at.pop(guild_id, None)
        self._last_now_playing_url.pop(guild_id, None)

    def _is_now_playing_dup(self, guild_id: int, track: dict) -> bool:
        now = time.time()
        last_url = self._last_now_playing_url.get(guild_id)
        last_at = self._last_now_playing_at.get(guild_id, 0)
        if last_url == track.get("url") and now - last_at < 2:
            return True
        self._last_now_playing_url[guild_id] = track.get("url", "")
        self._last_now_playing_at[guild_id] = now
        return False

    # --- playback core ---
    def _play_looping(self, vc, url: str):
        gid = vc.guild.id if vc and vc.guild else None
        if gid is not None:
            self._intentional_stop.discard(gid)
        try:
            source = None
            if _is_youtube_url(url):
                import subprocess as _sp
                clean = _clean_url(url)
                cookies_file = _get_cookies_path()
                ytdlp_args = [
                    sys.executable, '-m', 'yt_dlp',
                    '--format', 'ba/b',
                    '--output', '-',
                    '--no-playlist',
                    '--quiet',
                    '--no-warnings',
                    '--extractor-args', 'youtube:player_client=tv,mweb,android_vr,visionos',
                ]
                if cookies_file:
                    ytdlp_args.extend(['--cookies', cookies_file])
                ytdlp_args.append(clean)
                print(f"[MUSIC] Spawning yt-dlp subprocess for {clean[:60]}...", flush=True)
                proc = _sp.Popen(ytdlp_args, stdout=_sp.PIPE, stderr=_sp.PIPE)
                source = discord.FFmpegPCMAudio(proc.stdout, pipe=True)
                self._ytdlp_procs[gid] = proc
                def _log_stderr(p):
                    err = p.stderr.read().decode('utf-8', errors='replace')[:500]
                    if err:
                        print(f"[MUSIC] yt-dlp stderr: {err}", flush=True)
                import threading as _th
                _th.Thread(target=_log_stderr, args=(proc,), daemon=True).start()
            else:
                ffmpeg_opts = {
                    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -reconnect_at_eof 1 -reconnect_on_network_error 1",
                    "options": "-vn",
                }
                source = discord.FFmpegPCMAudio(url, **ffmpeg_opts)
            if source:
                vc.play(source, after=lambda e: self._on_track_end(vc, url, e))
        except Exception as e:
            print(f"[MUSIC] _play_looping error: {e}")

    def _on_track_end(self, vc, url: str, error):
        gid = vc.guild.id if vc and vc.guild else None
        if gid:
            proc = self._ytdlp_procs.pop(gid, None)
            if proc:
                proc.kill()
        if gid and gid in self._intentional_stop:
            self._intentional_stop.discard(gid)
            print(f"[MUSIC] Intentional stop for guild {gid}, not restarting.")
            return
        if error:
            print(f"[MUSIC] Audio error: {error}")
        if not vc or not vc.is_connected():
            return
        if not _is_youtube_url(url):
            print(f"[MUSIC] Stream ended, restarting...")
            self._play_looping(vc, url)
            return
        if gid is None:
            return
        loop = self._loop_mode.get(gid, "off")
        if loop == "track":
            print(f"[MUSIC] Loop track, replaying...")
            self._play_looping(vc, url)
            return
        self._ensure_queue(gid)
        if loop == "queue":
            idx = self._current_index.get(gid, -1)
            if 0 <= idx < len(self._queues[gid]):
                t = self._queues[gid].pop(idx)
                self._queues[gid].append(t)
            if self._queues[gid]:
                t = self._queues[gid][0]
                self._current_index[gid] = 0
                self._now_playing[gid] = t
                print(f"[MUSIC] Loop queue: next {t.get('title', 'Unknown')}")
                self._play_looping(vc, t["url"])
                return
        next_idx = self._current_index.get(gid, -1) + 1
        if 0 <= next_idx < len(self._queues[gid]):
            t = self._queues[gid][next_idx]
            self._current_index[gid] = next_idx
            self._now_playing[gid] = t
            print(f"[MUSIC] Next track: {t.get('title', 'Unknown')}")
            self._play_looping(vc, t["url"])
        else:
            print(f"[MUSIC] Queue empty, stopping.")
            self._current_index[gid] = -1
            self._now_playing.pop(gid, None)

    # --- events ---
    @commands.Cog.listener()
    async def on_ready(self):
        await asyncio.sleep(3)
        await self._restore_states()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.id != self.bot.user.id:
            return
        if before.channel and after.channel and before.channel.id != after.channel.id:
            state = self._voice_states.get(member.guild.id)
            if state:
                state["channel_id"] = after.channel.id
                self._save_state(member.guild.id, after.channel.id, state["url"])
                print(f"[MUSIC] Moved to {after.channel.name}, state updated")
            return
        if before.channel and not after.channel:
            print(f"[MUSIC] Disconnected from {before.channel.name}, state preserved for restart auto-resume")

    # --- commands ---
    @commands.command(name="connect", aliases=["joinvc"])
    async def connect(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):
        if not channel:
            if ctx.author.voice and ctx.author.voice.channel:
                channel = ctx.author.voice.channel
            else:
                embed = discord.Embed(description="Sebut nama voice channel atau join voice dulu biar bot ngikut.", color=COLOR)
                await ctx.send(embed=embed)
                return
        vc = ctx.guild.voice_client
        if vc:
            if vc.channel.id == channel.id:
                embed = discord.Embed(description=f"Udah di {channel.mention} kok.", color=COLOR)
                await ctx.send(embed=embed)
                return
            if vc.is_playing():
                self._intentional_stop.add(ctx.guild.id)
            await vc.disconnect()
            await asyncio.sleep(0.5)
        try:
            vc = await channel.connect()
        except discord.Forbidden:
            embed = discord.Embed(description="Gak punya izin Connect/Speak di channel itu.", color=0xFF0000)
            await ctx.send(embed=embed)
            return
        except Exception as e:
            embed = discord.Embed(description=f"\u274c Gagal: {e}", color=0xFF0000)
            await ctx.send(embed=embed)
            return
        await asyncio.sleep(0.5)
        try:
            self._play_looping(vc, LOFI_DEFAULT_URL)
            self._save_state(ctx.guild.id, channel.id, LOFI_DEFAULT_URL)
            self._clear_queue(ctx.guild.id)
            embed = discord.Embed(
                title="\u25b6 Connected",
                description=f"Join **{channel.name}** dan muterin LoFi radio.",
                color=COLOR
            )
            await ctx.send(embed=embed)
        except discord.ClientException:
            embed = discord.Embed(description=f"\u2705 Join **{channel.name}** (voice tersambung, tapi audio error)", color=COLOR)
            await ctx.send(embed=embed)
        except Exception:
            embed = discord.Embed(description=f"\u2705 Join **{channel.name}**", color=COLOR)
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="play", aliases=["p"], description="Putar lagu dari YouTube")
    @discord.app_commands.describe(query="Nama lagu atau URL YouTube")
    async def play(self, ctx: commands.Context, *, query: str = None):
        await ctx.defer()
        vc = ctx.guild.voice_client
        if not vc:
            if ctx.author.voice and ctx.author.voice.channel:
                vc = await ctx.author.voice.channel.connect()
            else:
                embed = discord.Embed(description="Bot gak di voice. Pake `!connect` dulu atau join voice dulu.", color=COLOR)
                await ctx.send(embed=embed)
                return
        q = (query or "").strip()
        q_lower = q.lower()
        track = None
        if not q or q_lower in LOFI_KEYWORDS:
            track = {"url": LOFI_DEFAULT_URL, "title": "LoFi Radio", "thumbnail": "", "requester": str(ctx.author)}
        elif q.startswith("http://") or q.startswith("https://"):
            url = _clean_url(q)
            if _is_youtube_url(url):
                info = await asyncio.to_thread(_yt_fetch, url)
                if info:
                    track = {"url": info["webpage_url"] or url, "title": info.get("title", "Unknown"), "thumbnail": info.get("thumbnail", ""), "requester": str(ctx.author)}
                else:
                    track = {"url": url, "title": url[:80], "thumbnail": "", "requester": str(ctx.author)}
            else:
                track = {"url": url, "title": url[:80], "thumbnail": "", "requester": str(ctx.author)}
        else:
            embed = discord.Embed(description="\U0001F50D Cari **{}** di YouTube...".format(q), color=COLOR)
            msg = await ctx.send(embed=embed)
            info = await asyncio.to_thread(_yt_fetch, f'ytsearch1:{q}')
            if not info:
                embed = discord.Embed(description=f"\u274c Gak nemu hasil buat \"{q}\".", color=0xFF0000)
                await msg.edit(embed=embed)
                return
            track = {"url": info["webpage_url"] or q, "title": info.get("title", "Unknown"), "thumbnail": info.get("thumbnail", ""), "requester": str(ctx.author)}
            await msg.delete()
        if vc.is_playing():
            current = self._now_playing.get(ctx.guild.id)
            is_stream = current and not _is_youtube_url(current.get("url", ""))
            if is_stream:
                self._intentional_stop.add(ctx.guild.id)
                vc.stop()
                await asyncio.sleep(0.3)
                self._ensure_queue(ctx.guild.id)
                self._queues[ctx.guild.id].append(track)
                self._current_index[ctx.guild.id] = len(self._queues[ctx.guild.id]) - 1
                self._now_playing[ctx.guild.id] = track
                self._play_looping(vc, track["url"])
                embed = discord.Embed(
                    title="\u25b6 Now Playing",
                    description=f"**{track['title']}**",
                    color=COLOR
                )
                if track["thumbnail"]:
                    embed.set_thumbnail(url=track["thumbnail"])
                embed.set_footer(text=f"Diminta oleh {ctx.author}")
                self._save_state(ctx.guild.id, vc.channel.id, track["url"])
                if not self._is_now_playing_dup(ctx.guild.id, track):
                    await ctx.send(embed=embed)
            else:
                pos = self._add_to_queue(ctx.guild.id, track)
                if pos == -1:
                    embed = discord.Embed(description=f"\U0001f6ab Queue penuh (max {self.MAX_QUEUE_SIZE})!", color=0xFF0000)
                    await ctx.send(embed=embed)
                    return
                embed = discord.Embed(
                    title="\u2795 Added to Queue",
                    description=f"**{track['title']}**\nPosisi #{pos + 1}",
                    color=COLOR
                )
                if track["thumbnail"]:
                    embed.set_thumbnail(url=track["thumbnail"])
                embed.set_footer(text=f"Diminta oleh {ctx.author}")
                await ctx.send(embed=embed)
        else:
            q = self._queues.get(ctx.guild.id, [])
            if len(q) >= self.MAX_QUEUE_SIZE:
                embed = discord.Embed(description=f"\U0001f6ab Queue penuh (max {self.MAX_QUEUE_SIZE})!", color=0xFF0000)
                await ctx.send(embed=embed)
                return
            self._ensure_queue(ctx.guild.id)
            self._queues[ctx.guild.id].append(track)
            self._current_index[ctx.guild.id] = len(self._queues[ctx.guild.id]) - 1
            self._now_playing[ctx.guild.id] = track
            self._play_looping(vc, track["url"])
            self._save_state(ctx.guild.id, vc.channel.id, track["url"])
            embed = discord.Embed(
                title="\u25b6 Now Playing",
                description=f"**{track['title']}**",
                color=COLOR
            )
            if track["thumbnail"]:
                embed.set_thumbnail(url=track["thumbnail"])
            embed.set_footer(text=f"Diminta oleh {ctx.author}")
            if not self._is_now_playing_dup(ctx.guild.id, track):
                await ctx.send(embed=embed)

    @commands.hybrid_command(name="search", description="Cari dan pilih lagu dari YouTube")
    @discord.app_commands.describe(query="Kata kunci pencarian")
    async def search(self, ctx: commands.Context, *, query: str):
        await ctx.defer()
        q = query.strip()
        if not q:
            embed = discord.Embed(description="Masukin kata kunci pencarian.", color=COLOR)
            await ctx.send(embed=embed, ephemeral=True)
            return
        loading = discord.Embed(description="\U0001F50D Mencari **{}**...".format(q), color=COLOR)
        await ctx.send(embed=loading)
        tracks = []
        for i in range(5):
            info = await asyncio.to_thread(_yt_fetch, f'ytsearch{i+1}:{q}')
            if info:
                tracks.append({"url": info["webpage_url"] or q, "title": info.get("title", "Unknown"), "thumbnail": info.get("thumbnail", ""), "requester": str(ctx.author)})
        if not tracks:
            embed = discord.Embed(description=f"\u274c Gak nemu hasil buat \"{q}\".", color=0xFF0000)
            await ctx.send(embed=embed)
            return
        view = SearchView(tracks, self)
        embed = discord.Embed(
            title="\U0001F50D Hasil Pencarian",
            description=f"Pilih lagu dari hasil pencarian **{q}**:",
            color=COLOR
        )
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="nowplaying", aliases=["np"], description="Lihat lagu yang sedang diputar")
    async def nowplaying(self, ctx: commands.Context):
        track = self._now_playing.get(ctx.guild.id)
        vc = ctx.guild.voice_client
        if not track or not vc or not vc.is_playing():
            embed = discord.Embed(description="Gak ada lagu yang diputar.", color=COLOR)
            await ctx.send(embed=embed)
            return
        embed = discord.Embed(
            title="\u25b6 Now Playing",
            description=f"**{track.get('title', 'Unknown')}**",
            color=COLOR
        )
        if track.get("thumbnail"):
            embed.set_thumbnail(url=track["thumbnail"])
        loop = self._loop_mode.get(ctx.guild.id, "off")
        embed.set_footer(text=f"Loop: {loop} | Diminta oleh {track.get('requester', 'Unknown')}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="queue", aliases=["q"], description="Lihat antrian lagu")
    async def queue(self, ctx: commands.Context):
        q = self._queues.get(ctx.guild.id, [])
        if not q:
            embed = discord.Embed(description="Antrian kosong.", color=COLOR)
            await ctx.send(embed=embed)
            return
        loop = self._loop_mode.get(ctx.guild.id, "off")
        now_idx = self._current_index.get(ctx.guild.id, -1)
        desc_lines = []
        for i, t in enumerate(q):
            marker = " \u25b6" if i == now_idx else ""
            desc_lines.append(f"`#{i + 1}`{marker} **{t.get('title', 'Unknown')}** — {t.get('requester', '?')}")
        embed = discord.Embed(
            title=f"\U0001f39b Queue ({len(q)} lagu)",
            description="\n".join(desc_lines),
            color=COLOR
        )
        embed.set_footer(text=f"Loop: {loop}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="skip", aliases=["next"], description="Lewati lagu yang sedang diputar")
    async def skip(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc or not vc.is_playing():
            embed = discord.Embed(description="Gak ada lagu yang diputar buat di-skip.", color=COLOR)
            await ctx.send(embed=embed)
            return
        vc.stop()
        embed = discord.Embed(description="\u23ed Skipped", color=COLOR)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="stop", description="Hentikan musik dan kosongkan antrian")
    async def stop(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc or not vc.is_playing():
            embed = discord.Embed(description="Gak ada audio yang diputar.", color=COLOR)
            await ctx.send(embed=embed)
            return
        self._clear_queue(ctx.guild.id)
        self._intentional_stop.add(ctx.guild.id)
        vc.stop()
        embed = discord.Embed(description="\u23f9 Stopped", color=COLOR)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="pause", description="Jeda lagu yang sedang diputar")
    async def pause(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc or not vc.is_playing():
            embed = discord.Embed(description="Gak ada lagu yang diputar.", color=COLOR)
            await ctx.send(embed=embed)
            return
        vc.pause()
        embed = discord.Embed(description="\u23f8 Paused", color=COLOR)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="resume", description="Lanjutkan lagu yang dijeda")
    async def resume(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc or not vc.is_paused():
            embed = discord.Embed(description="Gak ada lagu yang di-pause.", color=COLOR)
            await ctx.send(embed=embed)
            return
        vc.resume()
        embed = discord.Embed(description="\u25b6 Resumed", color=COLOR)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="shuffle", description="Acak antrian lagu")
    async def shuffle(self, ctx: commands.Context):
        q = self._queues.get(ctx.guild.id, [])
        if len(q) < 2:
            embed = discord.Embed(description="Antrian terlalu pendek buat di-acak.", color=COLOR)
            await ctx.send(embed=embed)
            return
        idx = self._current_index.get(ctx.guild.id, -1)
        if 0 <= idx < len(q):
            remaining = q[idx + 1:]
            random.shuffle(remaining)
            self._queues[ctx.guild.id] = q[:idx + 1] + remaining
        else:
            random.shuffle(q)
            self._queues[ctx.guild.id] = q
            self._current_index[ctx.guild.id] = -1
        embed = discord.Embed(description="\U0001F500 Queue di-acak!", color=COLOR)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="loop", aliases=["repeat"], description="Set mode loop: off, track, atau queue")
    @discord.app_commands.describe(mode="Pilih mode loop: off, track, atau queue")
    async def loop(self, ctx: commands.Context, mode: str = None):
        if mode is None:
            current = self._loop_mode.get(ctx.guild.id, "off")
            embed = discord.Embed(description=f"Loop saat ini: **{current}**\nGunakan `{ctx.clean_prefix}loop off|track|queue`", color=COLOR)
            await ctx.send(embed=embed)
            return
        m = mode.lower().strip()
        if m not in ("off", "track", "queue"):
            embed = discord.Embed(description="Mode harus: `off`, `track`, atau `queue`.", color=0xFF0000)
            await ctx.send(embed=embed)
            return
        self._loop_mode[ctx.guild.id] = m
        embed = discord.Embed(description="\U0001F501 Loop: **{}**".format(m), color=COLOR)
        await ctx.send(embed=embed)

    @commands.command(name="leave")
    async def leave(self, ctx: commands.Context):
        vc = ctx.guild.voice_client
        if not vc:
            embed = discord.Embed(description="Gak ada di voice channel.", color=COLOR)
            await ctx.send(embed=embed)
            return
        name = vc.channel.name
        if vc.is_playing():
            self._intentional_stop.add(ctx.guild.id)
            vc.stop()
        await vc.disconnect()
        self._clear_queue(ctx.guild.id)
        self._clear_state(ctx.guild.id)
        embed = discord.Embed(description=f"\U0001f44b Leave **{name}**", color=COLOR)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    _update_ytdlp()
    await bot.add_cog(MusicCog(bot))
