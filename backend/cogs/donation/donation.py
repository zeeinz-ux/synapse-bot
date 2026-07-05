import discord
import asyncio
from discord.ext import commands
from discord import app_commands
from firebase_admin import firestore

class DonationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _auto_delete(self, doc_ref, delay=60):
        await asyncio.sleep(delay)
        try:
            doc_ref.delete()
            print(f"[DONATION] Auto-deleted test donation {doc_ref.id}")
        except Exception as e:
            print(f"[DONATION] Auto-delete error: {e}")

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

    @commands.hybrid_command(name="testdonasi", description="Simulasi donasi untuk testing (Admin only)")
    @app_commands.describe(nominal="Jumlah donasi", metode="Metode pembayaran")
    @commands.has_permissions(administrator=True)
    async def testdonasi(self, ctx: commands.Context, nominal: int = 50000, metode: str = "TEST"):
        if not hasattr(self.bot, 'db') or not self.bot.db:
            return await ctx.send("❌ Database tidak aktif!", ephemeral=True)

        msg = await ctx.send("⏳ Memproses simulasi donasi...", ephemeral=True)

        try:
            data = {
                "user_id": str(ctx.author.id),
                "guild_id": str(ctx.guild.id),
                "type": "donation",
                "amount": nominal,
                "payment_method": metode,
                "status": "pending",
                "test": True,
                "created_at": firestore.SERVER_TIMESTAMP
            }

            _, doc_ref = self.bot.db.collection("transactions").add(data)

            asyncio.create_task(self._auto_delete(doc_ref))

            await msg.edit(
                content=f"✅ **Simulasi donasi berhasil!**\n"
                        f"💰 Rp {nominal:,} lewat {metode.upper()}\n"
                        f"🆔 ID: `{doc_ref.id}`\n"
                        f"⏳ Akan dihapus otomatis dalam 60 detik."
            )
            print(f"[TEST] ✅ Simulasi donasi oleh {ctx.author.name}")

        except Exception as e:
            await msg.edit(content="❌ Gagal simulasi donasi.")
            print(f"[ERROR] ❌ {e}")

    @testdonasi.error
    async def testdonasi_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Kamu tidak punya izin! (Admin only)", ephemeral=True)

    @commands.hybrid_command(name="donasi-confirm", description="Konfirmasi donasi pending menjadi completed (Admin)")
    @app_commands.describe(transaction_id="ID transaksi yang mau dikonfirmasi")
    @commands.has_permissions(administrator=True)
    async def donasi_confirm(self, ctx: commands.Context, transaction_id: str):
        if not hasattr(self.bot, 'db') or not self.bot.db:
            return await ctx.send("❌ Database tidak aktif!", ephemeral=True)
        try:
            doc_ref = self.bot.db.collection("transactions").document(transaction_id)
            doc = await asyncio.to_thread(doc_ref.get)
            if not doc.exists:
                await ctx.send(f"❌ Transaksi `{transaction_id}` tidak ditemukan.", ephemeral=True)
                return
            data = doc.to_dict()
            if data.get("status") == "completed":
                await ctx.send(f"⚠️ Transaksi `{transaction_id}` sudah completed.", ephemeral=True)
                return
            await asyncio.to_thread(doc_ref.update, {"status": "completed"})
            await ctx.send(
                f"✅ Donasi **Rp {data.get('amount', 0):,}** dari <@{data.get('user_id', '')}> dikonfirmasi!\n"
                f"🆔 ID: `{transaction_id}`",
                ephemeral=True
            )
        except Exception as e:
            await ctx.send("❌ Gagal mengkonfirmasi donasi.", ephemeral=True)
            print(f"[DONATION] ❌ Confirm error: {e}")

    @donasi_confirm.error
    async def donasi_confirm_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Kamu tidak punya izin! (Admin only)", ephemeral=True)

async def setup(bot):
    await bot.add_cog(DonationCog(bot))
