import sys
import os
import json
import warnings
import subprocess
import atexit
import shutil

os.environ["PYTHONUNBUFFERED"] = "1"
warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*line buffering.*binary mode.*")

# ==========================================================
# FIX: Agar Python bisa menemukan package 'backend'
# ==========================================================
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import discord
from discord.ext import commands, tasks
from discord import app_commands
import time
import threading
from dotenv import load_dotenv

import importlib
import traceback

load_dotenv()

# ===== WRITE COOKIES DARI ENV (Railway secret) =====
_cookies_raw = os.getenv("COOKIES_CONTENT")
if _cookies_raw:
    try:
        _cookies_dir = os.path.join(_project_root, "cookies")
        os.makedirs(_cookies_dir, exist_ok=True)
        _cookies_path = os.path.join(_cookies_dir, "cookies.txt")
        with open(_cookies_path, "w") as _f:
            _f.write(_cookies_raw)
        print(f"[COOKIES] ✅ Written from COOKIES_CONTENT env ({len(_cookies_raw)} chars)")
    except Exception as _e:
        print(f"[COOKIES] ❌ Gagal write cookies: {_e}")
# ===================================================

# ===== RUST POT PROVIDER — bypass YouTube bot detection =====
_pot_server_proc: subprocess.Popen | None = None

def _start_pot_server():
    global _pot_server_proc
    pot_bin = shutil.which("bgutil-pot")
    if not pot_bin:
        print("[POT] bgutil-pot binary not found — YouTube bot detection may fail")
        return
    try:
        _pot_server_proc = subprocess.Popen(
            [pot_bin, "server", "--host", "127.0.0.1", "--port", "4416"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"[POT] ✅ Server started (PID {_pot_server_proc.pid}) — PO tokens active")
    except Exception as e:
        print(f"[POT] ❌ Failed to start: {e}")

def _stop_pot_server():
    global _pot_server_proc
    if _pot_server_proc and _pot_server_proc.poll() is None:
        _pot_server_proc.terminate()
        try:
            _pot_server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _pot_server_proc.kill()
        print("[POT] Server stopped")

atexit.register(_stop_pot_server)
_start_pot_server()
# ============================================================

# ===== INIT FIREBASE SEBELUM LOAD COGS =====
from backend.cogs.database import firebase_setup
# ============================================

# ===== [DASHBOARD] Import Firestore stats bridge =====
from backend.utils.firestore_stats import set_stats, set_guild_channels, set_music_state, set_bot_instance, flush_now, delete_guild_from_map, delete_guild_settings, create_guild_settings_minimal, integrity_sweep, invalidate_stats_cache
# ==================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ===========================================================================
# REVISI DI SINI: Menyambungkan database Firebase agar bisa dipakai semua Cogs
# ===========================================================================
bot.db = firebase_setup.db


# ===========================================================================
# SETUP HOOK — muat semua cog sebelum bot connect
# ===========================================================================
async def setup_hook():
    cogs_dir = os.path.join(_project_root, "backend", "cogs")
    cog_count = 0

    for root, dirs, files in os.walk(cogs_dir):
        for filename in files:
            if not filename.endswith(".py") or filename == "__init__.py":
                continue

            if filename in ["firebase_setup.py", "spotify_down.py"]:
                continue

            rel_path = os.path.relpath(
                os.path.join(root, filename),
                os.path.join(_project_root, "backend")
            )
            module_path = rel_path.replace(os.sep, ".")[:-3]

            try:
                full_module = f"backend.{module_path}"
                module = importlib.import_module(full_module)

                if not hasattr(module, "setup"):
                    print(f"[COG] ⏭️ Skip non-cog: {module_path}", flush=True)
                    continue

                await bot.load_extension(full_module)
                print(f"[COG] 📦 Loaded: {module_path}", flush=True)
                cog_count += 1

            except Exception as e:
                print(f"[COG] ❌ Failed to load {module_path}: {e}", flush=True)
                traceback.print_exc()

    print(f"[COG] ✅ Total {cog_count} cogs loaded!", flush=True)
    print("[STATUS] 🎵 Music: yt-dlp + FFmpeg mode (no Lavalink)", flush=True)

bot.setup_hook = setup_hook
# ===========================================================================

@tasks.loop(seconds=20.0)
async def sync_music_to_dashboard():
    guilds_list = [
        {"id": str(g.id), "name": g.name, "member_count": g.member_count or 0}
        for g in bot.guilds
    ]
    stats = {
        "online": True,
        "guilds": len(bot.guilds),
        "members": sum(g.member_count for g in bot.guilds),
        "lavalink_connected": False,
        "guilds_list": guilds_list,
    }
    set_stats(stats)

@bot.event
async def on_guild_remove(guild):
    """Immediate stats update + full data cleanup when bot leaves a guild."""
    guild_id = str(guild.id)

    # 1. Build COMPLETE stats payload including guilds_list
    guilds_list = [
        {"id": str(g.id), "name": g.name, "member_count": g.member_count or 0}
        for g in bot.guilds
    ]
    stats = {
        "online": True,
        "guilds": len(bot.guilds),
        "members": sum(g.member_count for g in bot.guilds),
        "lavalink_connected": False,
        "guilds_list": guilds_list,
    }
    set_stats(stats)
    await flush_now("stats")

    invalidate_stats_cache()

    delete_guild_from_map("guild_channels", guild_id)
    delete_guild_from_map("music_states", guild_id)

    await delete_guild_settings(guild_id)

    print(f"[DASHBOARD] ✅ Guild removed: {guild.name} ({guild_id}) — stats updated ({len(bot.guilds)} guilds), data cleaned")

@bot.event
async def on_guild_join(guild):
    guild_id = str(guild.id)

    guilds_list = [
        {"id": str(g.id), "name": g.name, "member_count": g.member_count or 0}
        for g in bot.guilds
    ]
    stats = {
        "online": True,
        "guilds": len(bot.guilds),
        "members": sum(g.member_count for g in bot.guilds),
        "lavalink_connected": False,
        "guilds_list": guilds_list,
    }
    set_stats(stats)
    await flush_now("stats")

    # 2. Invalidate local cache
    invalidate_stats_cache()

    # 3. Create minimal guild_settings document (eager init for dashboard UX)
    await create_guild_settings_minimal(guild_id, guild.name)

    print(f"[DASHBOARD] ✅ Guild joined: {guild.name} ({guild_id}) — stats updated ({len(bot.guilds)} guilds), minimal settings created")

set_bot_instance(bot)
start_time = time.time()





# ===== [DASHBOARD] Stats updater loop =====
@tasks.loop(seconds=5)
async def update_stats():
    try:
        cog = bot.get_cog("Music")
        players = []
        if cog:
            for guild_id, controller in cog.controllers.items():
                if controller.current_track and controller.vc:
                    ch = controller.vc.channel
                    listeners = 0
                    if ch:
                        listeners = len([m for m in ch.members if not m.bot])
                    players.append({
                        "guild": controller.guild.name if controller.guild else "Unknown",
                        "track": controller.current_track.title,
                        "author": controller.current_track.author or "Unknown",
                        "duration": controller.current_track.duration or 0,
                        "position": controller.position,
                        "queue": len(controller.queue),
                        "listeners": listeners,
                        "paused": controller.paused,
                        "artwork": controller.current_track.artwork or ""
                    })

        for guild in bot.guilds:
            voice_channels = [
                {"id": str(ch.id), "name": ch.name}
                for ch in guild.voice_channels
                if ch.permissions_for(guild.me).connect
            ]
            set_guild_channels(str(guild.id), voice_channels)

        guilds_list = [
            {"id": str(g.id), "name": g.name, "member_count": g.member_count or 0}
            for g in bot.guilds
        ]

        set_stats(
            online=bot.is_ready(),
            username=bot.user.name if bot.user else "Hidden Hamlet",
            uptime=int(time.time() - start_time),
            guilds=len(bot.guilds),
            members=sum(g.member_count or 0 for g in bot.guilds),
            lavalink_connected=False,
            lavalink_node="N/A",
            players=players,
            guilds_list=guilds_list
        )

        if cog:
            for guild_id, controller in cog.controllers.items():
                guild_id_str = str(guild_id)
                if controller.current_track and controller.vc:
                    ch = controller.vc.channel
                    listeners = 0
                    if ch:
                        listeners = len([m for m in ch.members if not m.bot])

                    queue_list = []
                    queue_total_ms = 0
                    for t in list(controller.queue):
                        queue_list.append({
                            "title": t.title,
                            "author": t.author or "Unknown",
                            "duration": (t.duration or 0) // 1000,
                            "thumbnail": t.artwork or "",
                            "uri": t.uri or ""
                        })
                        queue_total_ms += (t.duration or 0)

                    music_data = {
                        "connected": True,
                        "playing": not controller.paused,
                        "paused": controller.paused,
                        "channel_name": ch.name if ch else "Unknown",
                        "channel_id": str(ch.id) if ch else None,
                        "position": controller.position // 1000,
                        "track": {
                            "title": controller.current_track.title,
                            "artist": controller.current_track.author or "Unknown",
                            "duration": (controller.current_track.duration or 0) // 1000,
                            "thumbnail": controller.current_track.artwork or "",
                            "uri": controller.current_track.uri or ""
                        },
                        "queue": queue_list,
                        "queue_count": len(queue_list),
                        "queue_duration": queue_total_ms // 1000,
                        "listeners": listeners,
                    }
                    set_music_state(guild_id_str, music_data)
                    _write_music_state_fast(guild_id_str, music_data)
                else:
                    set_music_state(guild_id_str, {"connected": False})
                    _write_music_state_fast(guild_id_str, {"connected": False})

    except Exception as e:
        print(f"[DASHBOARD STATS ERROR] {e}")


@update_stats.before_loop
async def before_update_stats():
    await bot.wait_until_ready()

# ===== [DASHBOARD] Fast music state file (bypasses Firestore debounce) =====
MUSIC_STATE_DIR = "/tmp/discord_music_state"

def _write_music_state_fast(guild_id: str, state: dict):
    try:
        os.makedirs(MUSIC_STATE_DIR, exist_ok=True)
        path = os.path.join(MUSIC_STATE_DIR, f"{guild_id}.json")
        with open(path, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print(f"[MUSIC STATE FILE] Write error: {e}")

# ===== [DASHBOARD] Control command processor (file-based IPC) =====
CONTROL_QUEUE_DIR = "/tmp/discord_control_queue"

async def _exec_control(cmd: dict):
    guild_id = cmd.get("guild_id")
    action = cmd.get("action")
    data = cmd.get("data", {})
    if not guild_id or not action:
        return
    guild = bot.get_guild(int(guild_id))
    if not guild:
        return
    cog = bot.get_cog("Music")
    if not cog:
        return
    vc = guild.voice_client
    controller = cog.get_controller(int(guild_id))

    if action == "pause":
        if vc and vc.is_playing():
            controller._paused_position = time.time() - controller._start_time
            controller._paused = True
            vc.pause()
    elif action == "play":
        if vc and vc.is_paused():
            controller._paused = False
            controller._start_time = time.time() - controller._paused_position
            vc.resume()
    elif action in ("skip", "next"):
        if vc: vc.stop()
    elif action == "stop":
        await controller.stop()
    elif action == "disconnect":
        await controller.disconnect()
    elif action == "clear":
        controller.queue.clear()
        controller._queue_history.clear()
    elif action == "volume":
        vol = int(data.get("volume", 100))
        await controller.set_volume(vol)
    elif action == "shuffle":
        import random
        random.shuffle(controller.queue)
        controller._queue_history.clear()
    elif action == "loop":
        modes = ["off", "single", "queue"]
        current = controller.loop_mode
        idx = modes.index(current) if current in modes else 0
        controller.loop_mode = modes[(idx + 1) % 3]
        if controller.loop_mode == "queue":
            controller._queue_history.clear()
        if controller.loop_mode == "off":
            controller._single_loop_track = None
    elif action == "join":
        channel_id = data.get("channel_id")
        if channel_id:
            ch = guild.get_channel(int(channel_id))
            if ch:
                try:
                    await ch.connect(self_deaf=False)
                except Exception:
                    pass
    elif action == "seek":
        pct = data.get("position_pct", 0)
        if controller.current_track:
            pos_ms = int(controller.current_track.duration * pct)
            await controller.seek(pos_ms)
    elif action == "setting":
        key = data.get("key")
        value = data.get("value")
        if key and bot.db:
            try:
                bot.db.collection("guild_settings").document(guild_id).set(
                    {key: value}, merge=True
                )
            except Exception as e:
                print(f"[SETTING] Write error: {e}")

@tasks.loop(seconds=1)
async def process_control_queue():
    if not os.path.isdir(CONTROL_QUEUE_DIR):
        return
    try:
        files = sorted(os.listdir(CONTROL_QUEUE_DIR))
        for fname in files:
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(CONTROL_QUEUE_DIR, fname)
            try:
                with open(fpath) as f:
                    cmd = json.load(f)
                await _exec_control(cmd)
            except Exception as e:
                print(f"[CONTROL QUEUE] Error processing {fname}: {e}")
            finally:
                try:
                    os.remove(fpath)
                except Exception:
                    pass
    except Exception as e:
        print(f"[CONTROL QUEUE] Scan error: {e}")


@bot.event
async def on_ready():
    print("=" * 50, flush=True)
    print(f"[STATUS] 🤖 {bot.user.name} SEKARANG SUDAH ONLINE!", flush=True)
    print(f"[STATUS] Terhubung ke {len(bot.guilds)} server Discord.", flush=True)
    print("=" * 50, flush=True)

    try:
        synced = await bot.tree.sync()
        print(f"[SYNC] ✅ {len(synced)} slash command(s) berhasil di-sync!", flush=True)
        for cmd in synced:
            print(f"  - /{cmd.name}", flush=True)
    except discord.HTTPException as e:
        print(f"[SYNC] ⚠️ HTTP {e.status} — {e.text}", flush=True)
        if e.status == 429:
            print("[SYNC] Rate limited, commands tetap pakai yang lama", flush=True)
    except Exception as e:
        print(f"[SYNC] ❌ Gagal sync commands: {e}", flush=True)

    await integrity_sweep(bot)

    if not update_stats.is_running():
        update_stats.start()
        print("[DASHBOARD] Stats updater aktif (5s).")

    if not process_control_queue.is_running():
        process_control_queue.start()
        print("[DASHBOARD] Control queue processor aktif (1s).")

    print("=" * 50)


@bot.event
async def on_close():
    print("[SHUTDOWN] Bot dimatikan.")


TOKEN = os.getenv("TOKEN_BOT")
if not TOKEN:
    print("[ERROR] TOKEN_BOT tidak ditemukan di .env!")
    exit(1)

bot.run(TOKEN)