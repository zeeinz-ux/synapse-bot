import discord
from discord.ext import commands
from discord import app_commands
import platform
import time
import asyncio
from backend.cogs.firebase_setup import db

class GeneralCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Create a default configuration when the bot joins a new guild."""
        if db is None:
            print("[General] Firestore DB not initialized. Skipping on_guild_join.")
            return

        guild_id = str(guild.id)
        doc_ref = db.collection("guild_settings").document(guild_id)

        try:
            # Run sync DB check in a separate thread to avoid blocking
            doc = await asyncio.to_thread(doc_ref.get)
            
            if doc.exists:
                print(f"[General] Config already exists for {guild.name} ({guild_id}). Skipping creation.")
                return

            print(f"[General] No config found for {guild.name} ({guild_id}). Creating default entry.")
            
            # Define default settings for a new server
            default_settings = {
                "welcome": {
                    "enabled": False,
                    "channel_id": None,
                    "message_text": "Welcome {user} to {server}! You are the {count}th member.",
                    "style": "embed",
                    "is_embed": True,
                    "embed_color": "#5865F2",
                    "embed_title": "👋 Welcome!",
                    "bg_image_url": "https://raw.githubusercontent.com/zeeinz-ux/my-discord-bot/main/frontend/static/images/default-welcome-bg.png",
                    "banner_bg_url": "https://raw.githubusercontent.com/zeeinz-ux/my-discord-bot/main/frontend/static/images/default-welcome-bg.png",
                    "banner_text": "WELCOME",
                    "banner_subtext": "Member #{count} • {server}",
                    "banner_font_color": "#FFFFFF",
                    "banner_avatar_ring": True
                },
                "ai_chat": {
                    "enabled": False,
                    "channel_id": None,
                    "persona": "Default: Gaul, keren, santai, pakai Bahasa Indonesia kasual (lu-gue/kamu-aku sesuai konteks).",
                    "temperature": 0.7
                },
                "boost": {
                    "enabled": False,
                    "channel_id": None
                },
                "donation": {
                    "enabled": False,
                    "log_channel_id": None
                }
            }

            # Run sync DB write in a separate thread
            await asyncio.to_thread(doc_ref.set, default_settings)
            print(f"[General] ✅ Created default config for guild: {guild.name} ({guild_id})")

        except Exception as e:
            print(f"[General] ❌ Firestore error in on_guild_join for {guild.name} ({guild_id}): {e}")

    @app_commands.command(name="ping", description="Cek latency bot")
    async def ping(self, interaction: discord.Interaction):
        # Latency ke Discord gateway
        ws_latency = round(self.bot.latency * 1000)

        # Latency ke message (round-trip)
        start = time.time()
        await interaction.response.send_message("🏓 Pong!", ephemeral=True)
        end = time.time()
        rt_latency = round((end - start) * 1000)

        embed = discord.Embed(
            title="🏓 Pong!",
            color=discord.Color.green()
        )
        embed.add_field(name="🌐 WebSocket Latency", value=f"`{ws_latency}ms`", inline=True)
        embed.add_field(name="📨 Round-Trip Latency", value=f"`{rt_latency}ms`", inline=True)
        embed.add_field(name="⏱️ Uptime", value=self.get_uptime(), inline=False)
        embed.set_footer(text=f"Requested by {interaction.user.name}")

        await interaction.edit_original_response(embed=embed)

    @app_commands.command(name="stats", description="Lihat statistik bot")
    async def stats(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📊 Bot Statistics",
            color=discord.Color.blue()
        )
        embed.add_field(name="🤖 Bot Name", value=self.bot.user.name, inline=True)
        embed.add_field(name="📦 Discord.py", value=discord.__version__, inline=True)
        embed.add_field(name="🐍 Python", value=platform.python_version(), inline=True)
        embed.add_field(name="🌐 Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="👥 Users", value=str(sum(g.member_count for g in self.bot.guilds)), inline=True)
        embed.add_field(name="⏱️ Uptime", value=self.get_uptime(), inline=True)
        embed.set_footer(text=f"Requested by {interaction.user.name}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    def get_uptime(self):
        uptime = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"

    @app_commands.command(name="help", description="Menampilkan daftar semua command")
    async def slash_help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📋 Daftar Slash Command",
            description="Gunakan `/` untuk melihat semua command yang tersedia:",
            color=discord.Color.blue()
        )

        # General Commands
        embed.add_field(
            name="🌐 General",
            value="`/ping` — Cek latency bot\n"
                  "`/stats` — Statistik bot\n"
                  "`/help` — Tampilkan pesan ini",
            inline=False
        )

        # Music Commands
        embed.add_field(
            name="🎵 Music",
            value="`/play <query>` — Putar lagu dari YouTube/Spotify\n"
                  "`/pause` — Pause lagu\n"
                  "`/resume` — Lanjutkan lagu\n"
                  "`/skip` — Skip lagu\n"
                  "`/stop` — Stop & keluar voice channel\n"
                  "`/queue` — Lihat antrian lagu\n"
                  "`/nowplaying` — Lagu yang sedang diputar",
            inline=False
        )

        # Boost Commands
        embed.add_field(
            name="🚀 Boost Tracker",
            value="`/cekboost [@user]` — Cek riwayat boost\n"
                  "`/testboost [@user]` — Simulasi boost (Admin only)",
            inline=False
        )

        # Donation Commands
        embed.add_field(
            name="💰 Donation",
            value="`/donasi <nominal> <metode>` — Catat donasi",
            inline=False
        )

        embed.set_footer(text=f"Requested by {interaction.user.name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(GeneralCog(bot))
