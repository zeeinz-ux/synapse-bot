import discord
from discord.ext import commands
import datetime

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.banned_keywords = ["bonuses", "withdraw", "free", "crypto", "slot", "join now"]

    @commands.Cog.listener()
    async def on_message(self, message):
        # Abaikan bot & admin
        if message.author.bot or message.author.guild_permissions.administrator:
            return

        # 1. Filter Dasar (Cepat)
        if message.mention_everyone or any(word in message.content.lower() for word in self.banned_keywords):
            await self.handle_spam(message, "Filter Dasar: Kata kunci atau Mass Mention")
            return

        # 2. Filter AI (Lapis Kedua - Hanya jika panjang pesan > 10 karakter)
        if len(message.content) > 10:
            ai_cog = self.bot.get_cog('AIChat') # Pastikan nama class di ai_chat.py adalah AIChat
            if ai_cog:
                # Kita asumsikan ada fungsi `analyze_spam` di ai_chat.py yang mengembalikan True/False
                is_ai_spam = await ai_cog.analyze_spam(message.content)
                if is_ai_spam:
                    await self.handle_spam(message, "Filter AI: Terdeteksi konten mencurigakan")

    async def handle_spam(self, message, reason):
        try:
            await message.delete()
            # Timeout 1 jam sebagai hukuman
            duration = datetime.timedelta(hours=1)
            await message.author.timeout(duration, reason=f"Spam: {reason}")
            
            # Kirim notifikasi ke channel (opsional, ganti channel_id)
            # channel = self.bot.get_channel(ID_CHANNEL_LOG)
            # await channel.send(f"⚠️ {message.author.mention} di-timeout. Alasan: {reason}")
            
            print(f"[MODERATION] {message.author} terkena moderasi: {reason}")
        except Exception as e:
            print(f"[ERROR] Gagal moderasi: {e}")

async def setup(bot):
    await bot.add_cog(Moderation(bot))