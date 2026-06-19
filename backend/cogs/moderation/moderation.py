import discord
from discord.ext import commands
import datetime
import asyncio
from ...utils.spam_engine import SpamEngine
from ..database.firebase_setup import db

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Inisialisasi engine di sini
        self.engine = SpamEngine()

    @commands.Cog.listener()
    async def on_message(self, message):
        # Abaikan bot & admin agar tidak terkena ban sendiri
        if message.author.bot or message.author.guild_permissions.administrator:
            await self.bot.process_commands(message) # 🌟 1. TARUH DI SINI (Biar admin tetep bisa pake command !)
            return

        # 1. Filter Heuristic (Cepat & Lokal)
        if self.engine.is_spam_heuristic(message):
            await self.handle_spam(message, "Filter Dasar: Terdeteksi kata kunci atau link mencurigakan")
            return

        # 2. Filter Akun Baru (Opsional - Sangat efektif cegah spammer baru)
        if self.engine.is_new_account(message) and len(message.content) > 30:
            await self.handle_spam(message, "Filter Keamanan: Akun baru mengirim pesan panjang")
            return

        # 3. Filter AI (Lapis Terakhir) - HANYA BERJALAN JIKA SKOR HEURISTIC MENCURIGAKAN
        # Misal: Skor di atas 0 tapi di bawah 5 (skor ban)
        current_score = self.engine.get_risk_score(message)
        if 0 < current_score < 5 and len(message.content) > 10:
            ai_cog = self.bot.get_cog('AIChat')
            if ai_cog:
                is_ai_spam = await ai_cog.analyze_spam(message.content)
                if is_ai_spam:
                    await self.handle_spam(message, "Filter AI: Terdeteksi konten mencurigakan oleh LLM")
                    return # Berhenti di sini kalau emang terbukti spam lewat AI

        # 🌟 2. TARUH DI PALING BAWAH SINI (Lapis Terakhir setelah lolos sensor spam)
        # Jika lolos semua filter, teruskan pesan agar perintah prefix (!) bisa diproses normal
        await self.bot.process_commands(message)

    async def handle_spam(self, message, reason):
        try:
            # 1. Hapus pesan spam
            await message.delete()

            # 2. Ambil/Update data strike dari Firestore
            user_id = str(message.author.id)
            doc_ref = db.collection("strikes").document(user_id)
            
            # Gunakan asyncio.to_thread karena Firestore memblokir thread utama
            doc = await asyncio.to_thread(doc_ref.get)
            strikes = doc.to_dict().get("count", 0) if doc.exists else 0
            
            strikes += 1
            await asyncio.to_thread(doc_ref.set, {"count": strikes})

            # 3. Logika Eskalasi Hukuman
            if strikes >= 3:
                # Strike 3: Ban Permanent
                await message.author.ban(reason=f"Auto-Ban: Spam berulang ({strikes}x) - {reason}")
                await message.channel.send(f"🚫 {message.author.mention} telah di-BAN permanen karena spam berulang.")
            
            elif strikes == 2:
                # Strike 2: Kick
                await message.author.kick(reason=f"Auto-Kick: Spam berulang ({strikes}x) - {reason}")
                await message.channel.send(f"⚠️ {message.author.mention} telah di-KICK karena pelanggaran spam berulang.")
            
            else:
                # Strike 1: Timeout 1 jam (Peringatan pertama)
                duration = datetime.timedelta(hours=1)
                await message.author.timeout(duration, reason=f"Spam: {reason}")
                await message.channel.send(f"⚠️ {message.author.mention} telah di-timeout 1 jam. Ini adalah peringatan ke-{strikes}.")

            print(f"[MODERATION] {message.author} Strike {strikes}: {reason}")
        
        except Exception as e:
            print(f"[ERROR] Gagal moderasi: {e}")

async def setup(bot):
    await bot.add_cog(Moderation(bot))
