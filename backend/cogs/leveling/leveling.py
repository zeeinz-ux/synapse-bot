import discord
import time
import random
import os
import asyncio
import math
from discord.ext import commands, tasks
from google.cloud import firestore
from backend.cogs.database.firebase_setup import db
from easy_pil import Editor, Font


def calc_level(xp: int) -> int:
    return int(math.isqrt(xp // 100))


def xp_for_level(level: int) -> int:
    return level * level * 100


class LevelingCog(commands.Cog, name="Leveling"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._xp_buffer = {}
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.font_path = os.path.join(base_dir, "..", "..", "..", "frontend", "static", "fonts", "Roboto-Bold.ttf")
        self.sync_loop.start()

    def cog_unload(self):
        self.sync_loop.cancel()
        asyncio.create_task(self._sync_to_db())

    @tasks.loop(minutes=5)
    async def sync_loop(self):
        await self._sync_to_db()

    async def _sync_to_db(self):
        if not self._xp_buffer or db is None:
            return
        batch = db.batch()
        for guild_id, users in self._xp_buffer.items():
            for user_id, data in users.items():
                if data["xp"] > 0:
                    ref = db.collection("guilds").document(guild_id).collection("members").document(user_id)
                    batch.set(ref, {"xp": firestore.Increment(data["xp"])}, merge=True)
        try:
            await asyncio.to_thread(batch.commit)
            self._xp_buffer.clear()
            print("[LEVELING] XP buffer synced to Firestore.")
        except Exception as e:
            print(f"[LEVELING] Gagal sync ke DB: {e}")

    async def _get_user_xp(self, guild_id: str, user_id: str) -> int:
        try:
            ref = db.collection("guilds").document(guild_id).collection("members").document(user_id)
            doc = await asyncio.to_thread(ref.get)
            if doc.exists:
                return doc.to_dict().get("xp", 0)
        except Exception:
            pass
        return 0

    async def _check_level_rewards(self, guild: discord.Guild, member: discord.Member, new_level: int):
        if db is None:
            return
        try:
            doc_ref = db.collection("guild_settings").document(str(guild.id))
            doc = await asyncio.to_thread(doc_ref.get)
            if not doc.exists:
                return
            config = doc.to_dict().get("level_rewards", {})
            if not config.get("enabled"):
                return
            rewards = config.get("rewards", {})
            notify_ch_id = config.get("notify_channel", "")

            role_id = rewards.get(str(new_level))
            if role_id:
                role = guild.get_role(int(role_id))
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason=f"Level up reward: Level {new_level}")
                        print(f"[LEVELING] Role {role.name} diberikan ke {member} (Level {new_level})")
                    except Exception as e:
                        print(f"[LEVELING] Gagal kasih role: {e}")

            if notify_ch_id:
                ch = guild.get_channel(int(notify_ch_id))
                if ch:
                    try:
                        await ch.send(f"🎉 Selamat {member.mention}! Kamu naik ke **Level {new_level}**!")
                    except Exception:
                        pass
        except Exception as e:
            print(f"[LEVELING] Error check rewards: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        gid, uid = str(message.guild.id), str(message.author.id)
        now = time.time()
        if gid not in self._xp_buffer:
            self._xp_buffer[gid] = {}
        if uid not in self._xp_buffer[gid]:
            self._xp_buffer[gid][uid] = {"xp": 0, "last_msg": 0}
        if now - self._xp_buffer[gid][uid]["last_msg"] < 60:
            return
        old_xp = self._xp_buffer[gid][uid]["xp"]
        xp_gain = random.randint(15, 25)
        self._xp_buffer[gid][uid]["xp"] += xp_gain
        self._xp_buffer[gid][uid]["last_msg"] = now
        buffered = self._xp_buffer[gid][uid]["xp"]
        if buffered >= 100:
            total_xp = await self._get_user_xp(gid, uid)
            total_xp += buffered
            new_level = calc_level(total_xp)
            await self._check_level_rewards(message.guild, message.author, new_level)

    @commands.hybrid_command(name="rank", description="Lihat kartu level Anda")
    async def rank(self, ctx: commands.Context):
        await ctx.defer()
        await ctx.send("Fitur kartu rank sedang dalam pengembangan visual!")

    @commands.hybrid_command(name="leaderboard", description="Top 10 member server")
    async def leaderboard(self, ctx: commands.Context):
        await ctx.send("Fitur leaderboard sedang dalam pengembangan!")


async def setup(bot):
    await bot.add_cog(LevelingCog(bot))
