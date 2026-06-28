import discord
from discord.ext import commands
from discord import app_commands
from firebase_admin import firestore

class DonationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="donasi", description="Catat donasi ke database")
    @app_commands.describe(
        nominal="Jumlah donasi dalam angka (contoh: 50000)",
        metode="Metode pembayaran (contoh: QRIS, DANA, OVO, Gopay)"
    )
    async def donasi(self, ctx: commands.Context, nominal: int, metode: str):
        # FIX 1: Memeriksa database melalui atribut bot (self.bot.db) yang dikirim dari main.py
        if not hasattr(self.bot, 'db') or not self.bot.db:
            await ctx.send("❌ Database tidak aktif!", ephemeral=True)
            return

        msg = await ctx.send("⏳ Memproses pencatatan donasi...", ephemeral=True)

        try:
            data_transaksi = {
                "user_id": str(ctx.author.id),
                "guild_id": str(ctx.guild.id),
                "type": "donation",
                "amount": nominal,
                "payment_method": metode,
                "status": "pending",
                "created_at": firestore.SERVER_TIMESTAMP
            }

            # FIX 2: Menggunakan self.bot.db (bukan variabel 'db' global yang bikin crash)
            _, doc_ref = self.bot.db.collection("transactions").add(data_transaksi)

            await msg.edit(
                content=f"✅ Donasi sebesar **Rp {nominal:,}** lewat **{metode.upper()}** berhasil dicatat!\n"
                        f"🆔 ID Transaksi: `{doc_ref.id}`\n"
                        f"👤 Oleh: {ctx.author.mention}"
            )
            print(f"[FIREBASE] ✅ Transaksi donasi tersimpan! ID: {doc_ref.id}")

        except Exception as e:
            await msg.edit(
                content="❌ Terjadi kesalahan saat menyimpan ke database."
            )
            print(f"[ERROR] ❌ Gagal menyimpan ke Firebase: {e}")

async def setup(bot):
    await bot.add_cog(DonationCog(bot))
