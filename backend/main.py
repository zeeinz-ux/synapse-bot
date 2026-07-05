import sys
import os
import time
import warnings
import asyncio  # [PHASE 6a fix] required by _memory_monitor's asyncio.sleep + create_task

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
# ============================================================

# ===== INIT FIREBASE SEBELUM LOAD COGS =====
from backend.cogs.database import firebase_setup
# ============================================

# ===== [DASHBOARD] Import Firestore stats bridge =====
from backend.utils.firestore_stats import set_stats, set_guild_channels, set_guild_roles, set_bot_instance, flush_now, delete_guild_from_map, delete_guild_settings, create_guild_settings_minimal, integrity_sweep, invalidate_stats_cache
# ==================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True


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

            if filename in ["firebase_setup.py"]:
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

bot.setup_hook = setup_hook
# ===========================================================================

# [PHASE 6a] Memory monitor for Railway free tier (512MB).
# Reads VmRSS from /proc/self/status (Linux only — Railway is Linux).
# Logs every 5 minutes so we can spot memory creep before OOM kills us.
import os as _os
async def _memory_monitor():
    while True:
        try:
            await asyncio.sleep(300)  # 5 min
            with open(f"/proc/{_os.getpid()}/status") as f:
                rss_kb = 0
                for line in f:
                    if line.startswith("VmRSS:"):
                        rss_kb = int(line.split()[1])
                        break
            rss_mb = rss_kb / 1024
            # Thresholds tuned for 512MB Railway free tier:
            #   < 300MB: healthy
            #   300-400MB: warning, log every cycle
            #   > 400MB: critical, log every cycle + trigger aggressive GC
            if rss_mb > 300:
                import gc as _gc
                collected = _gc.collect()
                print(f"[MEMORY] ⚠️ {rss_mb:.1f}MB RSS (gc freed {collected} objects)", flush=True)
            else:
                print(f"[MEMORY] ✅ {rss_mb:.1f}MB RSS", flush=True)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[MEMORY] Monitor error: {e}", flush=True)

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
        "guilds_list": guilds_list,
    }
    set_stats(stats)
    await flush_now("stats")

    invalidate_stats_cache()

    delete_guild_from_map("guild_channels", guild_id)

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
@tasks.loop(seconds=30)
async def update_stats():
    try:
        for guild in bot.guilds:
            text_channels = [
                {"id": str(ch.id), "name": ch.name}
                for ch in guild.text_channels
                if ch.permissions_for(guild.me).send_messages
            ]
            set_guild_channels(str(guild.id), text_channels)
            set_guild_roles(str(guild.id), [
                {"id": str(r.id), "name": r.name, "color": r.color.value, "position": r.position}
                for r in guild.roles if r.name != "@everyone"
            ])

        guilds_list = [
            {"id": str(g.id), "name": g.name, "member_count": g.member_count or 0}
            for g in bot.guilds
        ]

        set_stats(
            online=bot.is_ready(),
            username=bot.user.name if bot.user else "Synapse",
            uptime=int(time.time() - start_time),
            guilds=len(bot.guilds),
            members=sum(g.member_count or 0 for g in bot.guilds),
            guilds_list=guilds_list
        )
    except Exception as e:
        print(f"[DASHBOARD STATS ERROR] {e}")


@update_stats.before_loop
async def before_update_stats():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    print("=" * 50, flush=True)
    print(f"[STATUS] 🤖 {bot.user.name} SEKARANG SUDAH ONLINE!", flush=True)
    print(f"[STATUS] Terhubung ke {len(bot.guilds)} server Discord.", flush=True)
    print("=" * 50, flush=True)

    # [PHASE 6a] Start memory monitor task (Railway free tier = 512MB).
    if not hasattr(bot, "_memory_monitor_task") or bot._memory_monitor_task.done():
        bot._memory_monitor_task = asyncio.create_task(_memory_monitor())
        print("[MEMORY] Monitor started (5 min interval)", flush=True)

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
        print("[DASHBOARD] Stats updater aktif (30s).")

    print("=" * 50)


@bot.event
async def on_close():
    print("[SHUTDOWN] Bot dimatikan.")


TOKEN = os.getenv("TOKEN_BOT")
if not TOKEN:
    print("[ERROR] TOKEN_BOT tidak ditemukan di .env!")
    exit(1)

bot.run(TOKEN)