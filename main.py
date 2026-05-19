import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import time
import threading
from dotenv import load_dotenv
import wavelink
import asyncio

load_dotenv()

# ===== INIT FIREBASE SEBELUM LOAD COGS =====
from cogs import firebase_setup
# ============================================

# ===== [DASHBOARD] Import Flask app dari web/ =====
from web.web_app import app, set_stats
# ==================================================

# ===== [UTILS] Shared constants =====
from utils.constants import LAVALINK_NODES
# =====================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
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
        wavelink.Node(
            uri=node["uri"],
            password=node["password"]
        )
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
# ======================================

# [POLISH] Lavalink auto-reconnect loop
@tasks.loop(seconds=60)
async def lavalink_healthcheck():
    if not wavelink.Pool.nodes:
        print("[LAVALINK] ⚠️ Node tidak terdeteksi, mencoba reconnect...")
        node_cfg = LAVALINK_NODES[0]
        node = wavelink.Node(
            uri=node_cfg["uri"],
            password=node_cfg["password"]
        )
        try:
            await wavelink.Pool.connect(nodes=[node], client=bot)
            print("[LAVALINK] ✅ Reconnect berhasil!")
        except Exception as e:
            print(f"[LAVALINK] ❌ Reconnect gagal: {e}")


@lavalink_healthcheck.before_loop
async def before_healthcheck():
    await bot.wait_until_ready()


# ===== [DASHBOARD] Stats updater loop =====
@tasks.loop(seconds=30)
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

        set_stats(
            online=bot.is_ready(),
            username=bot.user.name if bot.user else "Hidden Hamlet",
            uptime=int(time.time() - start_time),
            guilds=len(bot.guilds),
            members=sum(g.member_count or 0 for g in bot.guilds),
            lavalink_connected=lavalink_ok,
            lavalink_node=node_uri,
            players=players
        )
    except Exception as e:
        print(f"[DASHBOARD STATS ERROR] {e}")


@update_stats.before_loop
async def before_update_stats():
    await bot.wait_until_ready()
# ==========================================


@bot.event
async def on_ready():
    print("=" * 50)
    print(f"[STATUS] 🤖 {bot.user.name} SEKARANG SUDAH ONLINE!")
    print(f"[STATUS] Terhubung ke {len(bot.guilds)} server Discord.")
    print("=" * 50)

    cog_count = 0
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and filename not in ('__init__.py', 'firebase_setup.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f"[COG] 📦 Loaded: {filename}")
                cog_count += 1
            except Exception as e:
                print(f"[COG] ❌ Failed to load {filename}: {e}")

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
        print("[DASHBOARD] 📊 Stats updater aktif (30s).")

    print("=" * 50)


TOKEN = os.getenv("TOKEN_BOT")
if not TOKEN:
    print("[ERROR] TOKEN_BOT tidak ditemukan di .env!")
    exit(1)

bot.run(TOKEN)