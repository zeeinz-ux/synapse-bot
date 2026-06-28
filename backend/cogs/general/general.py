import discord
from discord.ext import commands
import platform
import time

class GeneralCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()

    @commands.hybrid_command(name="ping", description="Cek latency bot")
    async def ping(self, ctx: commands.Context):
        ws_latency = round(self.bot.latency * 1000)

        start = time.time()
        msg = await ctx.send("🏓 Pong!", ephemeral=True)
        end = time.time()
        rt_latency = round((end - start) * 1000)

        embed = discord.Embed(
            title="🏓 Pong!",
            color=discord.Color.green()
        )
        embed.add_field(name="🌐 WebSocket Latency", value=f"`{ws_latency}ms`", inline=True)
        embed.add_field(name="📨 Round-Trip Latency", value=f"`{rt_latency}ms`", inline=True)
        embed.add_field(name="⏱️ Uptime", value=self.get_uptime(), inline=False)
        embed.set_footer(text=f"Requested by {ctx.author.name}")

        await msg.edit(content=None, embed=embed)

    @commands.hybrid_command(name="stats", description="Lihat statistik bot")
    async def stats(self, ctx: commands.Context):
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
        embed.set_footer(text=f"Requested by {ctx.author.name}")

        await ctx.send(embed=embed, ephemeral=True)

    def get_uptime(self):
        uptime = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"

    @commands.hybrid_command(name="help", description="Menampilkan daftar semua command")
    async def slash_help(self, ctx: commands.Context):
        embed = discord.Embed(
            title="📋 Daftar Slash Command",
            description=f"Total **{len(self.bot.commands)}** command terdaftar. Gunakan `/` untuk trigger:",
            color=discord.Color.blue()
        )

        cog_emoji = {
            "Music": "🎵",
            "GeneralCog": "🌐",
            "Leveling": "⭐",
            "Boost": "🚀",
            "AutoResponder": "🤖",
            "AIChat": "🧠",
            "Donation": "💰",
        }

        cogs: dict[str, list[commands.Command]] = {}
        for cmd in sorted(self.bot.commands, key=lambda c: c.name):
            cog_name = cmd.cog.qualified_name if cmd.cog else "Other"
            cogs.setdefault(cog_name, []).append(cmd)

        for cog_name, cmds in sorted(cogs.items()):
            emoji = cog_emoji.get(cog_name, "📦")
            lines = []
            for cmd in cmds:
                desc = (cmd.description or cmd.short_doc or "—").split("\n")[0][:60]
                sign = cmd.signature or ""
                lines.append(f"`/{cmd.name} {sign}` — {desc}")
            embed.add_field(name=f"{emoji} {cog_name}", value="\n".join(lines), inline=False)

        embed.set_footer(text=f"Requested by {ctx.author.name}")
        await ctx.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(GeneralCog(bot))
