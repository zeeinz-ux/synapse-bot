import discord
from discord.ext import commands

_COG_ICONS = {
    "AIChat": "🤖",
    "General": "📋",
    "Boost": "💎",
    "BoostTracker": "💎",
    "BoostAnnounce": "💎",
    "Donation": "💰",
    "Leveling": "📊",
    "Moderation": "🛡️",
    "AutoResponse": "🤖",
    "AntiSpam": "🛡️",
    "Welcome": "👋",
    "Leave": "👋",
    "Ban": "🚫",
    "MessageBuilder": "✏️",
    "Templates": "📄",
    "PhotoBox": "🖼️",
    "Settings": "⚙️",
    "Help": "❓",
}

_COG_NAMES = {
    "AIChat": "AI Chat",
    "General": "General",
    "Boost": "Boost Tracker",
    "BoostTracker": "Boost Tracker",
    "BoostAnnounce": "Boost Announce",
    "Donation": "Donation",
    "Leveling": "Leveling",
    "Moderation": "Moderation",
    "AutoResponse": "Auto Response",
    "AntiSpam": "Anti Spam",
    "Welcome": "Welcome",
    "Leave": "Leave",
    "Ban": "Ban",
    "MessageBuilder": "Message Builder",
    "Templates": "Templates",
    "PhotoBox": "PhotoBox",
    "Settings": "Settings",
    "Help": "Help",
}


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="Lihat daftar semua command atau detail command tertentu")
    async def help(self, ctx: commands.Context, *, command_name: str | None = None):
        if command_name:
            await self._show_command_detail(ctx, command_name)
        else:
            await self._show_command_list(ctx)

    async def _show_command_list(self, ctx: commands.Context):
        cogs_map: dict[str, list[discord.app_commands.AppCommand]] = {}
        for cmd in self.bot.walk_commands():
            cog_name = cmd.cog.qualified_name if cmd.cog else "Other"
            if cog_name not in cogs_map:
                cogs_map[cog_name] = []
            cogs_map[cog_name].append(cmd)

        embed = discord.Embed(
            title="📚 Help — Synapse Bot",
            description=f"Gunakan `/help <command>` untuk detail.\nTotal **{len(self.bot.commands)}** command tersedia.",
            color=discord.Color.purple(),
        )

        for cog_name, cmds in sorted(cogs_map.items()):
            if not cmds:
                continue
            icon = _COG_ICONS.get(cog_name, "📦")
            label = _COG_NAMES.get(cog_name, cog_name)
            cmd_list = ", ".join(f"`/{c.name}`" for c in cmds if not c.hidden)
            if cmd_list:
                embed.add_field(
                    name=f"{icon} {label}",
                    value=cmd_list,
                    inline=False,
                )

        embed.set_footer(text="Synapse Bot • Gunakan /help <command> untuk detail")
        await ctx.send(embed=embed)

    async def _show_command_detail(self, ctx: commands.Context, command_name: str):
        cmd = self.bot.get_command(command_name)
        if not cmd:
            await ctx.send(f"❌ Command `/{command_name}` tidak ditemukan.")
            return

        embed = discord.Embed(
            title=f"`/{cmd.name}`",
            color=discord.Color.purple(),
        )

        if cmd.description:
            embed.add_field(name="Deskripsi", value=cmd.description, inline=False)

        if cmd.aliases:
            embed.add_field(name="Alias", value=", ".join(f"`{a}`" for a in cmd.aliases), inline=False)

        params = []
        for name, param in cmd.clean_params.items():
            required = "**(wajib)**" if param.default is param.empty else f"(opsional, default: `{param.default}`)" if param.default is not None else "(opsional)"
            params.append(f"`<{name}>` {required}")
        if params:
            embed.add_field(name="Parameter", value="\n".join(params), inline=False)

        usage = f"/{cmd.name}"
        if cmd.clean_params:
            for name, param in cmd.clean_params.items():
                if param.default is param.empty:
                    usage += f" <{name}>"
                else:
                    usage += f" [{name}]"
        embed.add_field(name="Penggunaan", value=f"```{usage}```", inline=False)

        cog_name = cmd.cog.qualified_name if cmd.cog else "Other"
        icon = _COG_ICONS.get(cog_name, "📦")
        embed.add_field(name="Kategori", value=f"{icon} {_COG_NAMES.get(cog_name, cog_name)}", inline=True)

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
