import discord
from discord.ext import commands
from discord import app_commands
import os
import time
import threading
from flask import Flask
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ===== INIT FIREBASE SEBELUM LOAD COGS =====
# Firebase harus di-init DULU sebelum cog lain di-load
# karena boost.py & donation.py butuh firebase_admin sudah ter-init
from cogs import firebase_setup
# ============================================

# Bot setup
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
start_time = time.time()

# Flask keep-alive server
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)

# Start Flask in background thread
flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

@bot.event
async def on_ready():
    print("=" * 50)
    print(f"[STATUS] 🤖 {bot.user.name} SEKARANG SUDAH ONLINE!")
    print(f"[STATUS] Terhubung ke {len(bot.guilds)} server Discord.")
    print("=" * 50)

    # Auto-load cogs (SKIP firebase_setup.py dan __init__.py)
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

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"[SYNC] ✅ {len(synced)} slash command(s) berhasil di-sync!")
        for cmd in synced:
            print(f"  - /{cmd.name}")
    except Exception as e:
        print(f"[SYNC] ❌ Gagal sync commands: {e}")

    print("=" * 50)

# Run bot
TOKEN = os.getenv("TOKEN_BOT")
if not TOKEN:
    print("[ERROR] TOKEN_BOT tidak ditemukan di .env!")
    exit(1)

bot.run(TOKEN)