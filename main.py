import os
import json
import threading
from flask import Flask
import discord
from discord.ext import commands
from discord import app_commands
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

# ==============================================================================
# LOAD ENVIRONMENT VARIABLES
# ==============================================================================
load_dotenv()

# ==============================================================================
# FAKE WEB SERVER (Untuk UptimeRobot ping 24/7)
# ==============================================================================
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

# Jalankan web server di thread terpisah
threading.Thread(target=run_web, daemon=True).start()

# ==============================================================================
# KONFIGURASI BOT DISCORD
# ==============================================================================

TOKEN_BOT = os.environ.get("TOKEN_BOT")
if not TOKEN_BOT:
    raise ValueError("❌ TOKEN_BOT tidak ditemukan di Environment Variables!")

# ID Channel untuk notifikasi boost/unboost
NOTIF_CHANNEL_ID = 1505826133097316434

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==============================================================================
# FIREBASE SETUP (Dual Mode: File Path atau JSON String)
# ==============================================================================

def init_firebase():
    """
    Mode 1: FIREBASE_KEY = path file (VS Code lokal)
    Mode 2: FIREBASE_KEY = JSON string 1 baris (Replit Secrets)
    """
    try:
        firebase_key = os.environ.get("FIREBASE_KEY")
        if not firebase_key:
            raise ValueError("❌ FIREBASE_KEY tidak ditemukan di Environment Variables!")
        
        # Cek apakah FIREBASE_KEY adalah path file atau JSON string
        if os.path.isfile(firebase_key):
            # MODE 1: Path ke file JSON (VS Code lokal)
            print(f"[FIREBASE] 📁 Menggunakan file: {firebase_key}")
            cred = credentials.Certificate(firebase_key)
        else:
            # MODE 2: JSON string (Replit Secrets)
            print("[FIREBASE] 🔐 Menggunakan JSON string dari Environment Variable")
            firebase_key_dict = json.loads(firebase_key)
            cred = credentials.Certificate(firebase_key_dict)
        
        firebase_admin.initialize_app(cred)
        print("[FIREBASE] ✅ Berhasil terhubung ke Firestore!")
        return firestore.client()
        
    except json.JSONDecodeError as e:
        print(f"[ERROR] ❌ FIREBASE_KEY bukan JSON valid: {e}")
        print("[HINT] 💡 Kalau pakai file, pastikan path benar. Kalau pakai Replit, pastikan JSON 1 baris.")
        return None
    except Exception as e:
        print(f"[ERROR] ❌ Gagal konek Firebase: {e}")
        return None

db = init_firebase()

# ==============================================================================
# EVENT: BOT ONLINE
# ==============================================================================
@bot.event
async def on_ready():
    print(f"==================================================")
    print(f"[STATUS] 🤖 {bot.user.name} SEKARANG SUDAH ONLINE!")
    print(f"[STATUS] Terhubung ke {len(bot.guilds)} server Discord.")
    print(f"==================================================")
    
    # Cek channel notifikasi
    channel = bot.get_channel(NOTIF_CHANNEL_ID)
    if channel:
        print(f"[CHANNEL] ✅ Notif channel ditemukan: #{channel.name}")
        perms = channel.permissions_for(channel.guild.me)
        print(f"[PERM] Send Messages: {perms.send_messages}")
        print(f"[PERM] Embed Links: {perms.embed_links}")
    else:
        print(f"[WARNING] ⚠️ Channel ID {NOTIF_CHANNEL_ID} TIDAK ditemukan!")
        print("[WARNING] Pastikan bot sudah join server yang punya channel tersebut.")
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"[SYNC] ✅ {len(synced)} slash command(s) berhasil di-sync!")
        for cmd in synced:
            print(f"  - /{cmd.name}")
    except Exception as e:
        print(f"[ERROR] ❌ Gagal sync slash commands: {e}")
    print(f"==================================================")

# ==============================================================================
# SLASH COMMAND: /donasi
# ==============================================================================
@bot.tree.command(name="donasi", description="Catat donasi ke database")
@app_commands.describe(
    nominal="Jumlah donasi dalam angka (contoh: 50000)",
    metode="Metode pembayaran (contoh: QRIS, DANA, OVO, Gopay)"
)
async def slash_donasi(interaction: discord.Interaction, nominal: int, metode: str):
    if db is None:
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
        
        _, doc_ref = db.collection("transactions").add(data_transaksi)
        
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

# ==============================================================================
# EVENT: DETEKSI BOOSTING (AUTO)
# ==============================================================================
@bot.event
async def on_member_update(before, after):
    """
    Ter-trigger ketika data member berubah.
    Mendeteksi member yang mulai atau berhenti boost server.
    """
    
    # --- CASE A: Member BARU SAJA mulai boost ---
    if before.premium_since is None and after.premium_since is not None:
        
        user = after
        guild = after.guild
        
        print(f"[BOOST] 🚀 {user.name} ({user.id}) baru saja boost server {guild.name}!")
        
        try:
            # Simpan ke Firebase
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
            log_channel = bot.get_channel(NOTIF_CHANNEL_ID)
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
            else:
                print(f"[WARNING] ⚠️ Channel ID {NOTIF_CHANNEL_ID} tidak ditemukan! Notif tidak terkirim.")
                
        except Exception as e:
            print(f"[ERROR] ❌ Gagal menyimpan boost: {e}")

    # --- CASE B: Member BERHENTI boost ---
    elif before.premium_since is not None and after.premium_since is None:
        
        user = after
        print(f"[UNBOOST] 💔 {user.name} ({user.id}) berhenti boost server.")
        
        try:
            # Update status di Firebase
            boosts_ref = db.collection("boosts")
            query = boosts_ref.where("user_id", "==", str(user.id))\
                             .where("status", "==", "active")
            
            docs = query.stream()
            updated_count = 0
            for doc in docs:
                doc.reference.update({
                    "status": "expired",
                    "unboosted_at": firestore.SERVER_TIMESTAMP
                })
                updated_count += 1
            
            print(f"[FIREBASE] ✅ Status boost {user.name} diupdate ke expired. ({updated_count} dokumen)")
            
            # Kirim notif unboost ke channel
            log_channel = bot.get_channel(NOTIF_CHANNEL_ID)
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
            else:
                print(f"[WARNING] ⚠️ Channel ID {NOTIF_CHANNEL_ID} tidak ditemukan! Notif tidak terkirim.")
                
        except Exception as e:
            print(f"[ERROR] ❌ Gagal update status unboost: {e}")

# ==============================================================================
# SLASH COMMAND: /testboost (Admin Only)
# ==============================================================================
@bot.tree.command(name="testboost", description="Simulasi boost untuk testing (Admin only)")
@app_commands.describe(
    member="User yang mau di-simulasi boost (kosongkan = diri sendiri)"
)
@app_commands.checks.has_permissions(administrator=True)
async def slash_testboost(interaction: discord.Interaction, member: discord.Member = None):
    if member is None:
        member = interaction.user
    
    if db is None:
        await interaction.response.send_message("❌ Database tidak aktif!", ephemeral=True)
        return
        
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
        
        # Kirim notif ke channel juga untuk test
        log_channel = bot.get_channel(NOTIF_CHANNEL_ID)
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
            content=f"✅ **Simulasi boost berhasil!**\n"
                    f"👤 User: {member.mention}\n"
                    f"🆔 ID Dokumen: `{doc_ref.id}`"
        )
        print(f"[TEST] ✅ Simulasi boost untuk {member.name} berhasil.")
        
    except Exception as e:
        await interaction.edit_original_response(
            content="❌ Gagal simulasi boost."
        )
        print(f"[ERROR] ❌ {e}")

@slash_testboost.error
async def slash_testboost_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ Kamu tidak punya izin untuk menggunakan command ini! (Admin only)",
            ephemeral=True
        )

# ==============================================================================
# SLASH COMMAND: /cekboost
# ==============================================================================
@bot.tree.command(name="cekboost", description="Cek riwayat boost user di database")
@app_commands.describe(
    member="User yang mau dicek (kosongkan = diri sendiri)"
)
async def slash_cekboost(interaction: discord.Interaction, member: discord.Member = None):
    if member is None:
        member = interaction.user
    
    if db is None:
        await interaction.response.send_message("❌ Database tidak aktif!", ephemeral=True)
        return
        
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
        
        # Buat embed untuk tampilan lebih bagus
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
        await interaction.edit_original_response(
            content="❌ Gagal mengambil data boost."
        )
        print(f"[ERROR] ❌ {e}")

# ==============================================================================
# SLASH COMMAND: /help
# ==============================================================================
@bot.tree.command(name="help", description="Menampilkan daftar semua command yang tersedia")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📋 Daftar Slash Command",
        description="Gunakan `/` untuk melihat semua command yang tersedia:",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="💰 /donasi",
        value="Catat donasi ke database\n"
              "**Cara pakai:** `/donasi nominal:50000 metode:QRIS`",
        inline=False
    )
    
    embed.add_field(
        name="🚀 /testboost",
        value="Simulasi boost untuk testing\n"
              "**Cara pakai:** `/testboost member:@user`\n"
              "⚠️ *Hanya untuk Admin*",
        inline=False
    )
    
    embed.add_field(
        name="📊 /cekboost",
        value="Cek riwayat boost user\n"
              "**Cara pakai:** `/cekboost member:@user`",
        inline=False
    )
    
    embed.add_field(
        name="❓ /help",
        value="Menampilkan pesan ini",
        inline=False
    )
    
    embed.set_footer(text=f"Requested by {interaction.user.name}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==============================================================================
# JALANKAN BOT
# ==============================================================================
if __name__ == "__main__":
    if db is None:
        print("[STOP] ❌ Database tidak aktif. Periksa FIREBASE_KEY di Secrets!")
    else:
        bot.run(TOKEN_BOT)