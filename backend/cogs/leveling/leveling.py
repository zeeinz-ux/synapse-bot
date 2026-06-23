import discord
import time
import random
import os
import asyncio
from discord.ext import commands, tasks
from discord import app_commands
from google.cloud import firestore
# Menggunakan absolute import agar lebih aman dan tidak pusing dengan path ../..
from backend.cogs.database.firebase_setup import db 
from easy_pil import Editor, Font

class LevelingCog(commands.Cog, name="Leveling"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._xp_buffer = {}  # {guild_id: {user_id: {"xp": 0, "last_msg": 0}}}
        
        # Path dinamis: dari backend/cogs/leveling/leveling.py naik ke Root
        # 1 level naik: leveling -> cogs
        # 2 level naik: cogs -> backend
        # 3 level naik: backend -> Root
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.font_path = os.path.join(base_dir, "..", "..", "..", "frontend", "static", "fonts", "Roboto-VariableFont_wdth,wght.ttf")
        
        self.sync_loop.start()

    def cog_unload(self):
        self.sync_loop.cancel()
        asyncio.create_task(self._sync_to_db())

    @tasks.loop(minutes=5)
    async def sync_loop(self):
        await self._sync_to_db()

    async def _sync_to_db(self):
        if not self._xp_buffer or db is None: return
        
        batch = db.batch()
        for guild_id, users in self._xp_buffer.items():
            for user_id, data in users.items():
                if data["xp"] > 0:
                    ref = db.collection("guilds").document(guild_id).collection("members").document(user_id)
                    # Atomik increment
                    batch.set(ref, {"xp": firestore.Increment(data["xp"])}, merge=True)
        
        try:
            await asyncio.to_thread(batch.commit)
            self._xp_buffer.clear()
            print("[LEVELING] ✅ XP buffer synced to Firestore.")
        except Exception as e:
            print(f"[LEVELING] ❌ Gagal sync ke DB: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return
        
        gid, uid = str(message.guild.id), str(message.author.id)
        now = time.time()
        
        if gid not in self._xp_buffer: self._xp_buffer[gid] = {}
        if uid not in self._xp_buffer[gid]: 
            self._xp_buffer[gid][uid] = {"xp": 0, "last_msg": 0}
        
        # Cooldown 60 detik
        if now - self._xp_buffer[gid][uid]["last_msg"] < 60: return
        
        xp_gain = random.randint(15, 25)
        self._xp_buffer[gid][uid]["xp"] += xp_gain
        self._xp_buffer[gid][uid]["last_msg"] = now

    @app_commands.command(name="rank", description="Lihat kartu level Anda")
    async def rank(self, interaction: discord.Interaction):
        await interaction.response.defer()
        # TODO: Implementasi easy-pil render di sini
        await interaction.followup.send("Fitur kartu rank sedang dalam pengembangan visual!")

    @app_commands.command(name="leaderboard", description="Top 10 member server")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.send_message("Fitur leaderboard sedang dalam pengembangan!")

async def setup(bot):
    await bot.add_cog(LevelingCog(bot))