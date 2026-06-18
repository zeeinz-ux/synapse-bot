import sys
import os

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
import wavelink
import asyncio
import importlib

load_dotenv()

# ===== INIT FIREBASE SEBELUM LOAD COGS =====
from backend.cogs.database import firebase_setup
# ============================================

# ===== [DASHBOARD] Import Flask app dari web/ =====
from backend.web.web_app import (app, set_stats, set_guild_channels, set_music_state, set_bot_instance)
# ==================================================

# ===== [UTILS] Shared constants =====
from backend.utils.constants import LAVALINK_NODES
# =====================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
set_bot_instance(bot)
start_time = time.time()


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

# ===== LAVALINK: PUBLIC NODE =====
@bot.event
async def setup_hook():
    nodes = [
        wavelink.Node(uri=node["uri"], password=node["password"])
        for node in LAVALINK_NODES
    ]

    for i, node in enumerate(nodes, 1):
        try:
            await asyncio.wait_for(
                wavelink.Pool.connect(nodes=[node], client=bot),
                timeout=15.0
            )
            print(f"[LAVALINK] ✅ Node {i} tersambung: {node.uri}")
            return
        except asyncio.TimeoutError:
            print(f"[LAVALINK] ⏱️ Node {i} timeout: {node.uri}")
        except Exception as e:
            print(f"[LAVALINK] ❌ Node {i} gagal: {str(e)[:80]}")

    print("[LAVALINK] ⚠️ Lavalink tidak tersedia. Fitur musik mati.")

# [POLISH] Lavalink auto-reconnect loop
@tasks.loop(seconds=60)
async def lavalink_healthcheck():
    if not wavelink.Pool.nodes:
        print("[LAVALINK] ⚠️ Node tidak terdeteksi, mencoba reconnect...")
        node_cfg = LAVALINK_NODES[0]
        node = wavelink.Node(uri=node_cfg["uri"], password=node_cfg["password"])
        try:
            await wavelink.Pool.connect(nodes=[node], client=bot)
            print("[LAVALINK] ✅ Reconnect berhasil!")
        except Exception as e:
            print(f"[LAVALINK] ❌ Reconnect gagal: {e}")


@lavalink_healthcheck.before_loop
async def before_healthcheck():
    await bot.wait_until_ready()


# ===== [DASHBOARD] Stats updater loop =====
@tasks.loop(seconds=5)  # [FIX] Dipercepat dari 30s ke 5s untuk real-time
async def update_stats():
    try:
        nodes = wavelink.Pool.nodes
        lavalink_ok = len(nodes) > 0
        node_uri = "N/A"
        if nodes:
            first = list(nodes.values())[0]
            node_uri = getattr(first, "uri", "Unknown")

        players = []
        for guild in bot.guilds:
            vc = guild.voice_client
            if vc and getattr(vc, "current", None):
                ch = getattr(vc, "channel", None)
                listeners = 0
                if ch:
                    listeners = len([m for m in ch.members if not m.bot])
                players.append({
                    "guild": guild.name,
                    "track": vc.current.title,
                    "author": vc.current.author or "Unknown",
                    "duration": vc.current.length or 0,
                    "position": getattr(vc, "position", 0) or 0,
                    "queue": len(vc.queue) if hasattr(vc, "queue") else 0,
                    "listeners": listeners,
                    "paused": getattr(vc, "paused", False),
                    "artwork": vc.current.artwork or ""
                })

        # Sync guild channels untuk dropdown
        for guild in bot.guilds:
            # Text channels (untuk AI Chat, Welcome, dll)
            text_channels = [
                {"id": str(ch.id), "name": ch.name}
                for ch in guild.text_channels
                if ch.permissions_for(guild.me).send_messages
            ]
            set_guild_channels(str(guild.id), text_channels)

        # Guilds list untuk sidebar
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
            lavalink_connected=lavalink_ok,
            lavalink_node=node_uri,
            players=players,
            guilds_list=guilds_list
        )

        # ==========================================================
        # [FIX v4.6.1] Sync music state cache untuk Now Playing API
        # ==========================================================
        for guild in bot.guilds:
            vc = guild.voice_client
            guild_id_str = str(guild.id)
            if vc and getattr(vc, "current", None):
                ch = getattr(vc, "channel", None)
                listeners = 0
                if ch:
                    listeners = len([m for m in ch.members if not m.bot])

                # Build queue list with proper format for frontend
                queue_list = []
                queue_total_ms = 0
                if hasattr(vc, "queue"):
                    for t in list(vc.queue):
                        queue_list.append({
                            "title": t.title,
                            "author": t.author or "Unknown",
                            "duration": (t.length or 0) // 1000,
                            "thumbnail": t.artwork or "",
                            "uri": t.uri or ""
                        })
                        queue_total_ms += (t.length or 0)

                set_music_state(guild_id_str, {
                    "connected": True,
                    "playing": not getattr(vc, "paused", False),
                    "paused": getattr(vc, "paused", False),
                    "channel_name": ch.name if ch else "Unknown",
                    "channel_id": str(ch.id) if ch else None,
                    "position": (getattr(vc, "position", 0) or 0) // 1000,
                    "track": {
                        "title": vc.current.title,
                        "artist": vc.current.author or "Unknown",
                        "duration": (vc.current.length or 0) // 1000,
                        "thumbnail": vc.current.artwork or "",
                        "uri": vc.current.uri or ""
                    },
                    "queue": queue_list,
                    "queue_count": len(queue_list),
                    "queue_duration": queue_total_ms // 1000,
                    "listeners": listeners,
                })
            else:
                # Bersihkan state kalau bot tidak di VC atau tidak ada lagu
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

    # ===== FIX: Load cogs dari path absolut =====
    # [v4.1 UPDATE] Exclude spotify_down.py (utility, bukan cog)
    # ===== FIX: Load cogs dari subfolder (Rekursif) =====
    cogs_dir = os.path.join(_project_root, "backend", "cogs")
    cog_count = 0
    
    # os.walk akan mencari file di semua subfolder
    for root, dirs, files in os.walk(cogs_dir):
        for filename in files:
            # Skip file non-cog
            if not filename.endswith(".py") or filename == "__init__.py":
                continue
                
            # Abaikan file helper/utility yang bukan Cogs
            
            if filename in ["firebase_setup.py", "spotify_down.py"]:
                continue

            # Buat path module, contoh: backend.cogs.moderation.moderation
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

    if not wavelink.Pool.nodes:
        print("[STATUS] 🎵 Music: Lavalink TIDAK terhubung.")

    try:
        synced = await bot.tree.sync()
        print(f"[SYNC] ✅ {len(synced)} slash command(s) berhasil di-sync!")
        for cmd in synced:
            print(f"  - /{cmd.name}")
    except Exception as e:
        print(f"[SYNC] ❌ Gagal sync commands: {e}")

    if not lavalink_healthcheck.is_running():
        lavalink_healthcheck.start()
        print("[LAVALINK] 🔄 Health check loop aktif (60s).")

    if not update_stats.is_running():
        update_stats.start()
        print("[DASHBOARD] 📊 Stats updater aktif (5s).")

    print("=" * 50)


TOKEN = os.getenv("TOKEN_BOT")
if not TOKEN:
    print("[ERROR] TOKEN_BOT tidak ditemukan di .env!")
    exit(1)

bot.run(TOKEN)
