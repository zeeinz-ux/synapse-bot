import discord
from discord.ext import commands
from discord import app_commands
import firebase_admin
from firebase_admin import firestore

# Ambil db dari main (sudah di-init)
db = firestore.client()

NOTIF_CHANNEL_ID = 1505826133097316434

class BoostCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ==========================================================================
    # EVENT: AUTO DETEKSI BOOST/UNBOOST
    # ==========================================================================
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
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

                _, doc_ref = db.collection("boosts").add(data_boost)
                print(f"[FIREBASE] ✅ Data boost tersimpan! ID: {doc_ref.id}")

                # Kirim notif ke channel
                log_channel = self.bot.get_channel(NOTIF_CHANNEL_ID)
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
                boosts_ref = db.collection("boosts")
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
                log_channel = self.bot.get_channel(NOTIF_CHANNEL_ID)
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
    @app_commands.command(name="cekboost", description="Cek riwayat boost user di database")
    @app_commands.describe(member="User yang mau dicek (kosongkan = diri sendiri)")
    async def cekboost(self, interaction: discord.Interaction, member: discord.Member = None):
        if member is None:
            member = interaction.user

        await interaction.response.send_message("⏳ Mengambil data boost...", ephemeral=True)

        try:
            boosts_ref = db.collection("boosts")
            query = boosts_ref.where("user_id", "==", str(member.id))
            docs = list(query.stream())

            if not docs:
                await interaction.edit_original_response(
                    content=f"📭 {member.mention} belum pernah boost server ini."
                )
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
            embed.set_footer(text=f"Requested by {interaction.user.name}")

            await interaction.edit_original_response(content=None, embed=embed)

        except Exception as e:
            await interaction.edit_original_response(content="❌ Gagal mengambil data boost.")
            print(f"[ERROR] ❌ {e}")

    # ==========================================================================
    # SLASH COMMAND: /testboost (Admin Only)
    # ==========================================================================
    @app_commands.command(name="testboost", description="Simulasi boost untuk testing (Admin only)")
    @app_commands.describe(member="User yang mau di-simulasi boost (kosongkan = diri sendiri)")
    @app_commands.checks.has_permissions(administrator=True)
    async def testboost(self, interaction: discord.Interaction, member: discord.Member = None):
        if member is None:
            member = interaction.user

        await interaction.response.send_message("⏳ Memproses simulasi boost...", ephemeral=True)

        try:
            data_boost = {
                "user_id": str(member.id),
                "guild_id": str(interaction.guild_id),
                "type": "server_boost",
                "boosted_at": firestore.SERVER_TIMESTAMP,
                "status": "active",
                "note": "Manual slash command test"
            }

            _, doc_ref = db.collection("boosts").add(data_boost)

            # Kirim notif ke channel
            log_channel = self.bot.get_channel(NOTIF_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="🧪 Simulasi Boost (Test)",
                    description=f"{member.mention} di-simulasi **boost** oleh {interaction.user.mention}",
                    color=discord.Color.gold()
                )
                embed.add_field(name="👤 Target", value=member.mention, inline=True)
                embed.add_field(name="🧪 Tester", value=interaction.user.mention, inline=True)
                embed.add_field(name="🆔 Dokumen", value=f"`{doc_ref.id}`", inline=False)
                embed.set_footer(text="Ini hanya simulasi testing")
                await log_channel.send(embed=embed)

            await interaction.edit_original_response(
                content=f"✅ **Simulasi boost berhasil!**\n👤 User: {member.mention}\n🆔 ID Dokumen: `{doc_ref.id}`"
            )
            print(f"[TEST] ✅ Simulasi boost untuk {member.name} berhasil.")

        except Exception as e:
            await interaction.edit_original_response(content="❌ Gagal simulasi boost.")
            print(f"[ERROR] ❌ {e}")

    @testboost.error
    async def testboost_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ Kamu tidak punya izin! (Admin only)", ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(BoostCog(bot))
