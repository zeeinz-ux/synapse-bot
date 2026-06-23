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
    # 1. Update stats umum (guild count, dll)
    stats = {
        "online": True,
        "guilds": len(bot.guilds),
        "members": sum(g.member_count for g in bot.guilds),
        "lavalink_connected": bool(wavelink.Pool.nodes)
    }
    set_stats(stats)

    # 2. Update status musik tiap guild
    for guild in bot.guilds:
        player = guild.voice_client
        if player:
            state = {
                "connected": True,
                "current": player.current.title if player.current else "None",
                "queue_count": len(player.queue)
            }
            set_music_state(str(guild.id), state)
        else:
            set_music_state(str(guild.id), {"connected": False})

# Jalankan task-nya pas bot nyala
@bot.event
async def on_ready():
    # ... kode existing lu (sync command dll) ...
    
    if not sync_music_to_dashboard.is_running():
        sync_music_to_dashboard.start()
        print("[TASKS] ✅ Sync stats ke dashboard aktif!")
set_bot_instance(bot)
start_time = time.time()


# ==========================================================
# [UPDATE] LAVALINK: PRIVATE COYEB SERVER CONNECTION
# ==========================================================
@bot.event
async def setup_hook():
    # Mengambil konfigurasi secara aman dari Environment Variables Render
    lavalink_url = os.getenv("LAVALINK_URL")
    lavalink_password = os.getenv("LAVALINK_PASSWORD")

    if not lavalink_url or not lavalink_password:
        print("[LAVALINK] ❌ ERROR: LAVALINK_URL atau LAVALINK_PASSWORD belum diset di Render Dashboard!")
        print("[LAVALINK] Fitur musik tidak akan berjalan dengan benar.")
        return

    # Inisialisasi Single Private Node milik lu sendiri
    node = wavelink.Node(
        identifier="PrivateLavalink",
        uri=lavalink_url,
        password=lavalink_password
    )

    try:
        print(f"[LAVALINK] 🔄 Mencoba terhubung ke Private Server: {lavalink_url}...")
        await asyncio.wait_for(
            wavelink.Pool.connect(nodes=[node], client=bot),
            timeout=15.0
        )
        print(f"[LAVALINK] ✅ BERHASIL TERHUBUNG: Node private lu siap digunakan!")
    except asyncio.TimeoutError:
        print(f"[LAVALINK] ⏱️ Timeout saat mencoba menghubungi server Koyeb.")
    except Exception as e:
        print(f"[LAVALINK] ❌ Gagal terkoneksi ke Private Node: {e}")


# ==========================================================
# [UPDATE] Lavalink auto-reconnect loop khusus Private Server
# ==========================================================
@tasks.loop(seconds=60)
async def lavalink_healthcheck():
    node = wavelink.Pool.nodes.get("PrivateLavalink")
    if node and node.status == wavelink.NodeStatus.CONNECTED:
        return
    
    print("[LAVALINK] ⚠️ Koneksi terputus, mencoba auto-reconnect ke Private Server...")
    lavalink_url = os.getenv("LAVALINK_URL")
    lavalink_password = os.getenv("LAVALINK_PASSWORD")
    
    if lavalink_url and lavalink_password:
        if node:
            try:
                await node.disconnect()
            except Exception:
                pass
        
        node = wavelink.Node(
            identifier="PrivateLavalink",
            uri=lavalink_url,
            password=lavalink_password
        )
        try:
            await wavelink.Pool.connect(nodes=[node], client=bot)
            print("[LAVALINK] ✅ Auto-reconnect Berhasil!")
        except Exception as e:
            print(f"[LAVALINK] ❌ Auto-reconnect Gagal: {e}")


@lavalink_healthcheck.before_loop
async def before_healthcheck():
    await bot.wait_until_ready()


# ===== [DASHBOARD] Stats updater loop =====
@tasks.loop(seconds=5)
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

        # Sync music state cache untuk Now Playing API
        for guild in bot.guilds:
            vc = guild.voice_client
            guild_id_str = str(guild.id)
            if vc and getattr(vc, "current", None):
                ch = getattr(vc, "channel", None)
                listeners = 0
                if ch:
                    listeners = len([m for m in ch.members if not m.bot])

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
        print("[LAVALINK] Health check loop aktif (60s).")

    if not update_stats.is_running():
        update_stats.start()
        print("[DASHBOARD] Stats updater aktif (5s).")

    print("=" * 50)


@bot.event
async def on_close():
    print("[SHUTDOWN] Menutup koneksi Lavalink...")
    for node in wavelink.Pool.nodes.values():
        try:
            await node.disconnect()
        except Exception:
            pass
    await wavelink.Pool.close()
    print("[SHUTDOWN] Lavalink pool ditutup.")


TOKEN = os.getenv("TOKEN_BOT")
if not TOKEN:
    print("[ERROR] TOKEN_BOT tidak ditemukan di .env!")
    exit(1)

bot.run(TOKEN)