import discord
from discord.ext import commands
import datetime
import asyncio
from ...utils.spam_engine import SpamEngine
from ..database.firebase_setup import db

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.engine = SpamEngine()
        self.report_channel_id = 1517948052537868449

    async def _get_config(self, guild_id: str) -> dict:
        if db is None:
            return {}
        try:
            doc_ref = db.collection("guild_settings").document(guild_id)
            doc = await asyncio.to_thread(doc_ref.get)
            if doc.exists:
                return doc.to_dict().get("moderation_config", {})
        except Exception:
            pass
        return {}

    async def _get_action(self, guild_id: str, strikes: int) -> dict:
        cfg = await self._get_config(guild_id)
        key = f"strike_{strikes}"
        defaults = {
            1: {"action": "timeout", "duration_hours": 1},
            2: {"action": "kick"},
            3: {"action": "ban"},
        }
        return cfg.get(key, defaults.get(strikes, {"action": "ban"}))

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.author.guild_permissions.administrator:
            await self.bot.process_commands(message)
            return

        guild_id = str(message.guild.id)
        cfg = await self._get_config(guild_id)
        if not cfg.get("enabled", True):
            await self.bot.process_commands(message)
            return

        if cfg.get("filter_heuristic", True) and self.engine.is_spam_heuristic(message):
            await self.handle_spam(message, "Filter Dasar: Terdeteksi kata kunci/link mencurigakan")
            return

        if cfg.get("filter_new_account", True) and self.engine.is_new_account(message) and len(message.content) > 30:
            await self.handle_spam(message, "Filter Keamanan: Akun baru mengirim pesan panjang")
            return

        if cfg.get("filter_ai", True):
            current_score = self.engine.get_risk_score(message)
            if 0 < current_score < 5 and len(message.content) > 10:
                ai_cog = self.bot.get_cog('AIChat')
                if ai_cog:
                    is_ai_spam = await ai_cog.analyze_spam(message.content)
                    if is_ai_spam:
                        await self.handle_spam(message, "Filter AI: Terdeteksi konten mencurigakan oleh LLM")
                        return

        await self.bot.process_commands(message)

    async def handle_spam(self, message, reason):
        try:
            guild_id = str(message.guild.id)
            cfg = await self._get_config(guild_id)
            if not cfg.get("enabled", True):
                return

            await message.delete()

            user_id = str(message.author.id)
            doc_ref = db.collection("strikes").document(user_id)
            doc = await asyncio.to_thread(doc_ref.get)
            strikes = doc.to_dict().get("count", 0) if doc.exists else 0
            strikes += 1
            await asyncio.to_thread(doc_ref.set, {"count": strikes})

            punishment_msg = ""
            action_cfg = await self._get_action(guild_id, min(strikes, 3))
            action = action_cfg.get("action", "ban")

            if action == "ban":
                await message.author.ban(reason=f"Auto-Ban: {reason}")
                punishment_msg = "BAN permanen"
            elif action == "kick":
                await message.author.kick(reason=f"Auto-Kick: {reason}")
                punishment_msg = "KICK"
            elif action == "timeout":
                hours = action_cfg.get("duration_hours", 1)
                duration = datetime.timedelta(hours=hours)
                await message.author.timeout(duration, reason=f"Spam: {reason}")
                punishment_msg = f"TIMEOUT {hours} jam"
            else:
                await message.author.ban(reason=f"Auto-Ban: {reason}")
                punishment_msg = "BAN permanen"

            report_ch_id = cfg.get("report_channel", "") or str(self.report_channel_id)
            report_channel = self.bot.get_channel(int(report_ch_id))
            if report_channel:
                embed = discord.Embed(
                    title="Laporan Spam",
                    color=discord.Color.red(),
                    description=f"User **{message.author.name}** ({message.author.id}) dihukum: **{punishment_msg}**"
                )
                embed.add_field(name="Alasan", value=reason, inline=False)
                embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                embed.add_field(name="Peringatan Ke", value=strikes, inline=True)
                embed.add_field(name="Isi Pesan", value=f"||{message.content[:500]}||", inline=False)
                await report_channel.send(embed=embed)

            try:
                await message.author.send(f"Peringatan! Kamu telah di-{punishment_msg} dari server {message.guild.name} karena melakukan spam. Ini adalah peringatan ke-{strikes}.")
            except discord.Forbidden:
                print(f"[MODERATION] Gagal kirim DM ke {message.author}, DM ditutup.")

            print(f"[MODERATION] {message.author} Strike {strikes}: {reason}")
        except Exception as e:
            print(f"[ERROR] Gagal moderasi: {e}")

async def setup(bot):
    await bot.add_cog(Moderation(bot))
