import sys
import os
import warnings

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

load_dotenv()

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

bot = commands.Bot(command_prefix="!", intents=intents)

# ===========================================================================
# REVISI DI SINI: Menyambungkan database Firebase agar bisa dipakai semua Cogs
# ===========================================================================
bot.db = firebase_setup.db
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

# Jalankan task-nya pas bot nyala
@bot.event
async def on_ready():
    # ... kode existing lu (sync command dll) ...
    
    if not sync_music_to_dashboard.is_running():
        sync_music_to_dashboard.start()
        print("[TASKS] ✅ Sync stats ke dashboard aktif!")
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
            text_channels = [
                {"id": str(ch.id), "name": ch.name}
                for ch in guild.text_channels
                if ch.permissions_for(guild.me).send_messages
            ]
            set_guild_channels(str(guild.id), text_channels)

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

                    set_music_state(guild_id_str, {
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
                    })
                else:
                    set_music_state(guild_id_str, {"connected": False})

    except Exception as e:
        print(f"[DASHBOARD STATS ERROR] {e}")


@update_stats.before_loop
async def before_update_stats():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    print("=" * 50)
    print(f"[STATUS] 🤖 {bot.user.name} SEKARANG SUDAH ONLINE!")
    print(f"[STATUS] Terhubung ke {len(bot.guilds)} server Discord.")
    print("=" * 50)

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
                    print(f"[COG] ⏭️ Skip non-cog: {module_path}")
                    continue
                
                await bot.load_extension(full_module)
                print(f"[COG] 📦 Loaded: {module_path}")
                cog_count += 1
                
            except Exception as e:
                print(f"[COG] ❌ Failed to load {module_path}: {e}")
        

    print(f"[COG] ✅ Total {cog_count} cogs loaded!")

    print("[STATUS] 🎵 Music: yt-dlp + FFmpeg mode (no Lavalink)")

    try:
        synced = await bot.tree.sync()
        print(f"[SYNC] ✅ {len(synced)} slash command(s) berhasil di-sync!")
        for cmd in synced:
            print(f"  - /{cmd.name}")
    except Exception as e:
        print(f"[SYNC] ❌ Gagal sync commands: {e}")

    await integrity_sweep(bot)

    if not update_stats.is_running():
        update_stats.start()
        print("[DASHBOARD] Stats updater aktif (5s).")

    print("=" * 50)


@bot.event
async def on_close():
    print("[SHUTDOWN] Bot dimatikan.")


TOKEN = os.getenv("TOKEN_BOT")
if not TOKEN:
    print("[ERROR] TOKEN_BOT tidak ditemukan di .env!")
    exit(1)

bot.run(TOKEN)