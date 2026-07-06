import sys
import os
import time
import warnings
import asyncio

os.environ["PYTHONUNBUFFERED"] = "1"
warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*line buffering.*binary mode.*")

from backend.utils.logger import setup_logging
log = setup_logging()

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

_cookies_raw = os.getenv("COOKIES_CONTENT")
if _cookies_raw:
    try:
        _cookies_dir = os.path.join(_project_root, "cookies")
        os.makedirs(_cookies_dir, exist_ok=True)
        _cookies_path = os.path.join(_cookies_dir, "cookies.txt")
        with open(_cookies_path, "w") as _f:
            _f.write(_cookies_raw)
        log.info("Cookies written from COOKIES_CONTENT env (%d chars)", len(_cookies_raw))
    except Exception as _e:
        log.error("Failed to write cookies: %s", _e)

from backend.cogs.database import firebase_setup

from backend.utils.firestore_stats import set_stats, set_guild_channels, set_guild_roles, set_bot_instance, flush_now, delete_guild_from_map, delete_guild_settings, create_guild_settings_minimal, integrity_sweep, invalidate_stats_cache

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

bot.db = firebase_setup.db

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
                    log.debug("Skip non-cog: %s", module_path)
                    continue

                await bot.load_extension(full_module)
                log.info("Loaded cog: %s", module_path)
                cog_count += 1

            except Exception as e:
                log.error("Failed to load %s: %s", module_path, e)
                traceback.print_exc()

    log.info("Total %d cogs loaded", cog_count)

bot.setup_hook = setup_hook

import os as _os
async def _memory_monitor():
    while True:
        try:
            await asyncio.sleep(300)
            with open(f"/proc/{_os.getpid()}/status") as f:
                rss_kb = 0
                for line in f:
                    if line.startswith("VmRSS:"):
                        rss_kb = int(line.split()[1])
                        break
            rss_mb = rss_kb / 1024
            if rss_mb > 300:
                import gc as _gc
                collected = _gc.collect()
                log.warning("Memory %.1fMB RSS (gc freed %d objects)", rss_mb, collected)
            else:
                log.info("Memory %.1fMB RSS", rss_mb)
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("Memory monitor error: %s", e)

@bot.event
async def on_guild_remove(guild):
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

    invalidate_stats_cache()

    delete_guild_from_map("guild_channels", guild_id)

    await delete_guild_settings(guild_id)

    log.info("Guild removed: %s (%s) — %d guilds, data cleaned", guild.name, guild_id, len(bot.guilds))

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

    invalidate_stats_cache()

    await create_guild_settings_minimal(guild_id, guild.name)

    log.info("Guild joined: %s (%s) — %d guilds, settings created", guild.name, guild_id, len(bot.guilds))

set_bot_instance(bot)
start_time = time.time()

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
        log.error("Stats update error: %s", e)

@update_stats.before_loop
async def before_update_stats():
    await bot.wait_until_ready()

@bot.event
async def on_ready():
    log.info("====== %s ONLINE ======", bot.user.name)
    log.info("Connected to %d Discord servers", len(bot.guilds))

    if not hasattr(bot, "_memory_monitor_task") or bot._memory_monitor_task.done():
        bot._memory_monitor_task = asyncio.create_task(_memory_monitor())
        log.info("Memory monitor started (5 min interval)")

    try:
        synced = await bot.tree.sync()
        log.info("%d slash command(s) synced", len(synced))
        for cmd in synced:
            log.info("  - /%s", cmd.name)
    except discord.HTTPException as e:
        log.warning("Sync HTTP %d — %s", e.status, e.text)
        if e.status == 429:
            log.warning("Rate limited, using old commands")
    except Exception as e:
        log.error("Failed to sync commands: %s", e)

    await integrity_sweep(bot)

    if not update_stats.is_running():
        update_stats.start()
        log.info("Stats updater active (30s interval)")

@bot.event
async def on_close():
    log.info("Bot shutting down")

TOKEN = os.getenv("TOKEN_BOT")
if not TOKEN:
    log.critical("TOKEN_BOT not found in .env!")
    exit(1)

bot.run(TOKEN)
