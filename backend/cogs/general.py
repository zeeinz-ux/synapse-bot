import discord
from discord.ext import commands
from discord import app_commands
import platform
import time

class GeneralCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()

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
