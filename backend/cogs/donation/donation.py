import discord
from discord.ext import commands
from discord import app_commands
from firebase_admin import firestore

class DonationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="donasi", description="Catat donasi ke database")
    @app_commands.describe(
        nominal="Jumlah donasi dalam angka (contoh: 50000)",
        metode="Metode pembayaran (contoh: QRIS, DANA, OVO, Gopay)"
    )
    async def donasi(self, interaction: discord.Interaction, nominal: int, metode: str):
        # FIX 1: Memeriksa database melalui atribut bot (self.bot.db) yang dikirim dari main.py
        if not hasattr(self.bot, 'db') or not self.bot.db:
            await interaction.response.send_message("❌ Database tidak aktif!", ephemeral=True)
            return

        await interaction.response.send_message("⏳ Memproses pencatatan donasi...", ephemeral=True)

        try:
            data_transaksi = {
                "user_id": str(interaction.user.id),
                "guild_id": str(interaction.guild_id),
                "type": "donation",
                "amount": nominal,
                "payment_method": metode,
                "status": "pending",
                "created_at": firestore.SERVER_TIMESTAMP
            }

            # FIX 2: Menggunakan self.bot.db (bukan variabel 'db' global yang bikin crash)
            _, doc_ref = self.bot.db.collection("transactions").add(data_transaksi)

            await interaction.edit_original_response(
                content=f"✅ Donasi sebesar **Rp {nominal:,}** lewat **{metode.upper()}** berhasil dicatat!\n"
                        f"🆔 ID Transaksi: `{doc_ref.id}`\n"
                        f"👤 Oleh: {interaction.user.mention}"
            )
            print(f"[FIREBASE] ✅ Transaksi donasi tersimpan! ID: {doc_ref.id}")

        except Exception as e:
            await interaction.edit_original_response(
                content="❌ Terjadi kesalahan saat menyimpan ke database."
            )
            print(f"[ERROR] ❌ Gagal menyimpan ke Firebase: {e}")

async def setup(bot):
    await bot.add_cog(DonationCog(bot))
