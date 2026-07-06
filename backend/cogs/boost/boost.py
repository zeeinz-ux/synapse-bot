import discord
import asyncio
import os
from discord.ext import commands
from discord import app_commands
from firebase_admin import firestore

class BoostCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ==========================================================================
    # STARTUP: Scan existing boosters di semua guild
    # ==========================================================================
    @commands.Cog.listener()
    async def on_ready(self):
        print("[BOOST] 🔍 Mulai scan existing boosters...")
        asyncio.create_task(self._scan_existing_boosters())

    async def _scan_existing_boosters(self):
        await asyncio.sleep(5)
        if not hasattr(self.bot, 'db') or not self.bot.db:
            print("[BOOST] ⚠️ Scan skipped — Firestore not available.")
            return
        for guild in self.bot.guilds:
            try:
                members = []
                async for m in guild.fetch_members(limit=None):
                    members.append(m)
            except Exception as e:
                print(f"[BOOST] ⚠️ Gagal fetch members {guild.name}: {e}")
                continue
            for member in members:
                if member.premium_since is None:
                    continue
                uid = str(member.id)
                gid = str(guild.id)
                existing = list(self.bot.db.collection("boosts")
                    .where("user_id", "==", uid)
                    .where("guild_id", "==", gid)
                    .where("status", "==", "active")
                    .limit(1).stream())
                if existing:
                    continue
                self.bot.db.collection("boosts").add({
                    "user_id": uid,
                    "guild_id": gid,
                    "type": "server_boost",
                    "boosted_at": member.premium_since,
                    "status": "active",
                })
                print(f"[BOOST] 📦 Existing booster recorded: {member.name} ({uid}) in {guild.name}")
        print("[BOOST] ✅ Scan existing boosters selesai.")

    async def _auto_delete(self, doc_ref, delay=60):
        await asyncio.sleep(delay)
        try:
            doc_ref.delete()
            print(f"[BOOST] Auto-deleted test boost {doc_ref.id}")
        except Exception as e:
            print(f"[BOOST] Auto-delete error: {e}")

    # ==========================================================================
    # EVENT: AUTO DETEKSI BOOST/UNBOOST
    # ==========================================================================
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        # Periksa apakah bot memiliki atribut db
        if not hasattr(self.bot, 'db') or not self.bot.db:
            print("[BOOST] ⚠️ Firestore DB tidak tersedia di bot.")
            return

        # CASE A: Member BARU boost
        if before.premium_since is None and after.premium_since is not None:
            user = after
            guild = after.guild
            print(f"[BOOST] 🚀 {user.name} ({user.id}) baru saja boost server {guild.name}!")

            try:
                data_boost = {
                    "user_id": str(user.id),
                    "guild_id": str(guild.id),
                    "type": "server_boost",
                    "boosted_at": firestore.SERVER_TIMESTAMP,
                    "status": "active"
                }

                _, doc_ref = self.bot.db.collection("boosts").add(data_boost)
                print(f"[FIREBASE] ✅ Data boost tersimpan! ID: {doc_ref.id}")

                # Kirim notif ke channel
                log_channel = self.bot.get_channel(int(os.getenv("BOOST_NOTIF_CHANNEL_ID", 0))) if os.getenv("BOOST_NOTIF_CHANNEL_ID") else None
                if log_channel:
                    embed = discord.Embed(
                        title="🚀 Server Boost Baru!",
                        description=f"{user.mention} baru saja **boost** server!\n\nTerima kasih atas dukungannya! 🎉",
                        color=discord.Color.purple()
                    )
                    embed.add_field(name="👤 User", value=f"{user.name}\n`{user.id}`", inline=True)
                    embed.add_field(name="🏠 Server", value=guild.name, inline=True)
                    embed.add_field(name="🆔 Dokumen", value=f"`{doc_ref.id}`", inline=False)
                    embed.set_thumbnail(url=user.display_avatar.url)
                    embed.timestamp = discord.utils.utcnow()
                    embed.set_footer(text="Boost Tracker Bot")

                    await log_channel.send(embed=embed)
                    print(f"[NOTIF] ✅ Notifikasi boost terkirim ke #{log_channel.name}")

            except Exception as e:
                print(f"[ERROR] ❌ Gagal menyimpan boost: {e}")

        # CASE B: Member BERHENTI boost
        elif before.premium_since is not None and after.premium_since is None:
            user = after
            print(f"[UNBOOST] 💔 {user.name} ({user.id}) berhenti boost server.")

            try:
                boosts_ref = self.bot.db.collection("boosts")
                query = boosts_ref.where("user_id", "==", str(user.id)).where("status", "==", "active")

                docs = query.stream()
                updated_count = 0
                for doc in docs:
                    doc.reference.update({
                        "status": "expired",
                        "unboosted_at": firestore.SERVER_TIMESTAMP
                    })
                    updated_count += 1

                print(f"[FIREBASE] ✅ Status boost {user.name} diupdate ke expired. ({updated_count} dokumen)")

                # Kirim notif unboost
                log_channel = self.bot.get_channel(int(os.getenv("BOOST_NOTIF_CHANNEL_ID", 0))) if os.getenv("BOOST_NOTIF_CHANNEL_ID") else None
                if log_channel:
                    embed = discord.Embed(
                        title="💔 Boost Berakhir",
                        description=f"{user.mention} telah **berhenti** boost server.",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="👤 User", value=f"{user.name}\n`{user.id}`", inline=True)
                    embed.add_field(name="🏠 Server", value=user.guild.name, inline=True)
                    embed.add_field(name="📊 Dokumen Diupdate", value=f"{updated_count} record", inline=False)
                    embed.set_thumbnail(url=user.display_avatar.url)
                    embed.timestamp = discord.utils.utcnow()
                    embed.set_footer(text="Boost Tracker Bot")

                    await log_channel.send(embed=embed)
                    print(f"[NOTIF] ✅ Notifikasi unboost terkirim ke #{log_channel.name}")

            except Exception as e:
                print(f"[ERROR] ❌ Gagal update status unboost: {e}")

    # ==========================================================================
    # SLASH COMMAND: /cekboost
    # ==========================================================================
    @commands.hybrid_command(name="cekboost", description="Cek riwayat boost user di database")
    @app_commands.describe(member="User yang mau dicek (kosongkan = diri sendiri)")
    async def cekboost(self, ctx: commands.Context, member: discord.Member = None):
        if not hasattr(self.bot, 'db') or not self.bot.db:
            return await ctx.send("❌ Koneksi database tidak tersedia.", ephemeral=True)

        if member is None:
            member = ctx.author

        msg = await ctx.send("⏳ Mengambil data boost...", ephemeral=True)

        try:
            boosts_ref = self.bot.db.collection("boosts")
            query = boosts_ref.where("user_id", "==", str(member.id))
            docs = list(query.stream())

            if not docs:
                await msg.edit(content=f"📭 {member.mention} belum pernah boost server ini.")
                return

            total_boosts = len(docs)
            active_boosts = sum(1 for d in docs if d.to_dict().get("status") == "active")
            expired_boosts = total_boosts - active_boosts

            embed = discord.Embed(
                title=f"📊 Data Boost - {member.name}",
                color=discord.Color.purple()
            )
            embed.add_field(name="📈 Total Boost", value=str(total_boosts), inline=True)
            embed.add_field(name="✅ Status Aktif", value=str(active_boosts), inline=True)
            embed.add_field(name="❌ Status Expired", value=str(expired_boosts), inline=True)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Requested by {ctx.author.name}")

            await msg.edit(content=None, embed=embed)

        except Exception as e:
            await msg.edit(content="❌ Gagal mengambil data boost.")
            print(f"[ERROR] ❌ {e}")

    # ==========================================================================
    # SLASH COMMAND: /testboost (Admin Only)
    # ==========================================================================
    @commands.hybrid_command(name="testboost", description="Simulasi boost untuk testing (Admin only)")
    @app_commands.describe(member="User yang mau di-simulasi boost (kosongkan = diri sendiri)")
    @commands.has_permissions(administrator=True)
    async def testboost(self, ctx: commands.Context, member: discord.Member = None):
        if not hasattr(self.bot, 'db') or not self.bot.db:
            return await ctx.send("❌ Koneksi database tidak tersedia.", ephemeral=True)

        if member is None:
            member = ctx.author

        msg = await ctx.send("⏳ Memproses simulasi boost...", ephemeral=True)

        try:
            data_boost = {
                "user_id": str(member.id),
                "guild_id": str(ctx.guild.id),
                "type": "server_boost",
                "boosted_at": firestore.SERVER_TIMESTAMP,
                "status": "active",
                "test": True,
                "note": "Manual slash command test"
            }

            _, doc_ref = self.bot.db.collection("boosts").add(data_boost)
            asyncio.create_task(self._auto_delete(doc_ref))

            # Kirim notif ke channel
            log_channel = self.bot.get_channel(NOTIF_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="🧪 Simulasi Boost (Test)",
                    description=f"{member.mention} di-simulasi **boost** oleh {ctx.author.mention}",
                    color=discord.Color.gold()
                )
                embed.add_field(name="👤 Target", value=member.mention, inline=True)
                embed.add_field(name="🧪 Tester", value=ctx.author.mention, inline=True)
                embed.add_field(name="🆔 Dokumen", value=f"`{doc_ref.id}`", inline=False)
                embed.set_footer(text="Ini hanya simulasi testing")
                await log_channel.send(embed=embed)

            await msg.edit(
                content=f"✅ **Simulasi boost berhasil!**\n👤 User: {member.mention}\n🆔 ID Dokumen: `{doc_ref.id}`\n⏳ Akan dihapus otomatis dalam 60 detik."
            )
            print(f"[TEST] ✅ Simulasi boost untuk {member.name} berhasil.")

        except Exception as e:
            await msg.edit(content="❌ Gagal simulasi boost.")
            print(f"[ERROR] ❌ {e}")

    @testboost.error
    async def testboost_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(
                "❌ Kamu tidak punya izin! (Admin only)", ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(BoostCog(bot))
