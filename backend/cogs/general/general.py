import discord
from discord.ext import commands, tasks
from discord import ui
import platform
import time
import asyncio
import os

CHANNEL_PLAN = {
    "📁 General": [
        {"name": "‼️・welcome", "type": "text", "everyone_read": True, "everyone_send": False},
        {"name": "👋・leave", "type": "text", "admin_only": True},
        {"name": "⚡・support-server", "type": "text"},
        {"name": "🚨・report-spam", "type": "text", "everyone_send": True},
    ],
    "📊 SERVER STATS": [
        {"name": "📊 ALL MEMBER", "type": "voice", "gembok": True},
        {"name": "📊 MEMBER", "type": "voice", "gembok": True},
        {"name": "📊 BOTS", "type": "voice", "gembok": True},
    ],
    "🎮 Music/Hiburan": [
        {"name": "📸・gallery", "type": "text", "everyone_send": True},
        {"name": "🎥・share-streaming", "type": "text", "everyone_send": True},
        {"name": "🔁・share-content", "type": "text", "everyone_send": True},
        {"name": "🤡・funny", "type": "text", "everyone_send": True},
        {"name": "📌・ping-test", "type": "text", "everyone_send": True},
        {"name": "🎶・req-music", "type": "text", "everyone_send": True},
    ],
    "💬 Create Voice": [
        {"name": "💬・talk", "type": "text", "everyone_send": True},
        {"name": "✨・interface", "type": "text"},
        {"name": "➕ Create Caffee'", "type": "voice"},
        {"name": "⌛ Lobby", "type": "voice", "everyone_send": True},
        {"name": "😴 AFK 💤", "type": "voice", "afk": True, "everyone_send": True, "user_limit": 15},
    ],
    "🎮 Game": [
        {"name": "🗣️ Caffee", "type": "voice", "everyone_send": True},
    ],
    "🎵 Music": [
        {"name": "🔊 Music", "type": "voice", "everyone_send": True},
    ],
    "🎬 Streaming": [
        {"name": "🎬 Stream", "type": "voice", "everyone_send": True},
    ],
}

STATS_CATEGORY = "📊 SERVER STATS"

VOICE_CHANNEL_PLAN = {
    "💬 Create Voice": [
        {"name": "✨・interface", "type": "text"},
        {"name": "➕ Create Caffee'", "type": "voice"},
    ],
}

FEATURE_TOGGLES = {
    "anti_spam": {"label": "🛡️ Anti Spam", "default": False},
    "anti_nuke": {"label": "🚨 Anti Nuke", "default": False},
    "welcome": {"label": "👋 Welcome Message", "default": False},
    "ai_chat": {"label": "🤖 AI Chat", "default": False},
}


class SetupConfirmView(ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.features = {k: v["default"] for k, v in FEATURE_TOGGLES.items()}

    @ui.button(label="▶️ Mulai", style=discord.ButtonStyle.success, row=0)
    async def start(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Bukan session kamu.", ephemeral=True)
        self.clear_items()
        await interaction.response.edit_message(view=self)
        await self.cog._run_setup(self.ctx, self.features)

    @ui.button(label="❌ Batal", style=discord.ButtonStyle.danger, row=0)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return
        self.clear_items()
        await interaction.response.edit_message(content="❌ Setup dibatalkan.", embed=None, view=self)


class VoiceConfirmView(ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx

    @ui.button(label="✅ Setuju", style=discord.ButtonStyle.success, row=0)
    async def start(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Bukan session kamu.", ephemeral=True)
        self.clear_items()
        await interaction.response.edit_message(view=self)
        await self.cog._run_voice_setup(self.ctx)

    @ui.button(label="❌ Tidak", style=discord.ButtonStyle.danger, row=0)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return
        self.clear_items()
        await interaction.response.edit_message(content="❌ Setup voice dibatalkan.", embed=None, view=self)


class FeatureSelectView(ui.View):
    def __init__(self, cog, ctx, parent_view):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.features = dict(parent_view.features)

    @ui.select(
        placeholder="Pilih fitur yang mau diaktifkan...",
        min_values=0, max_values=len(FEATURE_TOGGLES),
        options=[
            discord.SelectOption(
                label=v["label"],
                value=k,
                default=v["default"],
            ) for k, v in FEATURE_TOGGLES.items()
        ],
        row=0,
    )
    async def select_features(self, interaction: discord.Interaction, select: ui.Select):
        if interaction.user.id != self.ctx.author.id:
            return
        for opt in select.values:
            self.features[opt] = True
        for k in self.features:
            if k not in select.values:
                self.features[k] = False
        await interaction.response.defer()

    @ui.button(label="✅ Konfirmasi & Jalankan", style=discord.ButtonStyle.success, row=1)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return
        self.clear_items()
        await interaction.response.edit_message(view=self)
        await self.cog._run_setup(self.ctx, self.features)

    @ui.button(label="🔙 Kembali", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return
        await interaction.response.edit_message(
            embed=self.cog._setup_preview_embed(self.ctx.guild),
            view=SetupConfirmView(self.cog, self.ctx),
        )


class GeneralCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()
        self._active_setups: set[int] = set()
        self.stats_updater.start()

    async def cog_unload(self):
        self.stats_updater.cancel()

    @tasks.loop(minutes=5)
    async def stats_updater(self):
        for guild in self.bot.guilds:
            await self._update_server_stats(guild)

    @stats_updater.before_loop
    async def before_stats_updater(self):
        await self.bot.wait_until_ready()

    async def _update_server_stats(self, guild: discord.Guild):
        cat = discord.utils.get(guild.categories, name=STATS_CATEGORY)
        if not cat:
            return
        total = guild.member_count
        bots = sum(1 for m in guild.members if m.bot)
        humans = total - bots
        name_map = {
            "📊 ALL MEMBER": f"📊 ALL MEMBER: {total}",
            "📊 MEMBER": f"📊 MEMBER: {humans}",
            "📊 BOTS": f"📊 BOTS: {bots}",
        }
        for ch in cat.voice_channels:
            new_name = name_map.get(ch.name.split(":")[0].strip())
            if new_name and ch.name != new_name:
                try:
                    await ch.edit(name=new_name, reason="Server stats update")
                except Exception:
                    pass

    def _setup_preview_embed(self, guild: discord.Guild) -> discord.Embed:
        embed = discord.Embed(
            title="🚀 Server Setup Wizard",
            description="Bot akan membuat struktur channel dan mengaktifkan fitur untuk server ini.",
            color=discord.Color.blue(),
        )
        total = 0
        for cat_name, channels in CHANNEL_PLAN.items():
            names = "\n".join(f"  {'🔊' if ch['type']=='voice' else '📄'} {ch['name']}" for ch in channels)
            embed.add_field(name=f"📁 {cat_name}", value=names, inline=True)
            total += len(channels)
        embed.add_field(name="", value="", inline=False)
        embed.add_field(name="Total Channel", value=f"{total} channel", inline=True)
        embed.add_field(name="Permission Needed", value="Manage Channels\nManage Roles", inline=True)
        return embed

    async def _build_channel_preview(self, guild: discord.Guild) -> str:
        lines = []
        total = 0
        for cat_name, channels in CHANNEL_PLAN.items():
            lines.append(f"**📁 {cat_name}**")
            for ch in channels:
                icon = "🔊" if ch["type"] == "voice" else "📄"
                ch_info = [f"  {icon} #{ch['name']}"]
                if ch.get("gembok"):
                    ch_info.append("🔒")
                if ch.get("admin_only"):
                    ch_info.append("(admin only)")
                lines.append(" ".join(ch_info))
                total += 1
            lines.append("")
        lines.append(f"**Total**: {total} channel")
        return "\n".join(lines)

    def _voice_preview_embed(self, guild: discord.Guild) -> discord.Embed:
        embed = discord.Embed(
            title="🎛️ Setup Voice",
            description="Bot akan membuat channel voice dan interface untuk server ini.",
            color=discord.Color.blue(),
        )
        for cat_name, channels in VOICE_CHANNEL_PLAN.items():
            names = "\n".join(f"  {'🔊' if ch['type']=='voice' else '📄'} {ch['name']}" for ch in channels)
            embed.add_field(name=f"📁 {cat_name}", value=names, inline=True)
        return embed

    @commands.hybrid_command(name="voice", description="Setup channel voice & interface")
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def voice(self, ctx: commands.Context):
        embed = self._voice_preview_embed(ctx.guild)
        view = VoiceConfirmView(self, ctx)
        await ctx.send(embed=embed, view=view)

    async def _run_voice_setup(self, ctx: commands.Context):
        guild = ctx.guild
        guild_id = guild.id
        self._active_setups.add(guild_id)
        progress = await ctx.send("🔧 **Memulai setup voice...**")
        results = {"categories": 0, "channels": 0, "errors": []}

        try:
            trigger_id = None
            interface_id = None
            for cat_name, channels in VOICE_CHANNEL_PLAN.items():
                existing_cat = discord.utils.get(guild.categories, name=cat_name)
                if existing_cat:
                    category = existing_cat
                else:
                    try:
                        category = await guild.create_category(cat_name, reason="Voice setup")
                        results["categories"] += 1
                    except Exception as e:
                        results["errors"].append(f"Kategori {cat_name}: {e}")
                        continue

                for ch in channels:
                    ch_name = ch["name"]
                    ch_type = ch["type"]
                    existing = discord.utils.get(category.channels, name=ch_name)
                    if existing:
                        if ch_name == "✨・interface":
                            interface_id = existing.id
                        elif ch_name == "➕ Create Caffee'":
                            trigger_id = existing.id
                        results["channels"] += 1
                        continue
                    try:
                        perms = {}
                        if ch.get("gembok"):
                            perms[guild.default_role] = discord.PermissionOverwrite(connect=False, view_channel=True)
                        elif ch.get("everyone_send"):
                            perms[guild.default_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
                        else:
                            perms[guild.default_role] = discord.PermissionOverwrite(read_messages=True, send_messages=False)

                        if ch_type == "text":
                            tc = await guild.create_text_channel(ch_name, category=category, overwrites=perms, reason="Voice setup")
                            if ch_name == "✨・interface":
                                interface_id = tc.id
                        else:
                            vc_kwargs = {"category": category, "overwrites": perms, "reason": "Voice setup"}
                            if ch.get("user_limit"):
                                vc_kwargs["user_limit"] = ch["user_limit"]
                            vc = await guild.create_voice_channel(ch_name, **vc_kwargs)
                            if ch_name == "➕ Create Caffee'":
                                trigger_id = vc.id
                            if ch.get("afk"):
                                try:
                                    await guild.edit(afk_channel=vc, afk_timeout=3600)
                                except Exception:
                                    pass
                        results["channels"] += 1
                    except Exception as e:
                        results["errors"].append(f"Channel {ch_name}: {e}")

            voice_cog = self.bot.get_cog("VoiceInterfaceCog")
            if voice_cog:
                await voice_cog._ensure_interface(guild)
                if trigger_id and interface_id:
                    await voice_cog._save_channel_ids(guild.id, trigger_id, interface_id)

            summary = f"✅ **Setup voice selesai!**\n📁 **{results['categories']}** kategori\n📄 **{results['channels']}** channel"
            if results["errors"]:
                summary += f"\n⚠️ **{len(results['errors'])} error:**\n" + "\n".join(f"- {e}" for e in results["errors"][:3])
            embed = discord.Embed(title="✅ Setup Voice Selesai! 🎉", description=summary, color=discord.Color.green())
            await progress.edit(content=None, embed=embed)
        except Exception as e:
            await progress.edit(content=f"❌ Setup voice gagal: {e}")
        finally:
            self._active_setups.discard(guild_id)

    @commands.hybrid_command(name="setup", description="Auto-setup channel & fitur untuk server baru")
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def setup(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        if guild_id in self._active_setups:
            await ctx.send("⏳ Setup sedang berjalan di server ini. Tunggu selesai!", ephemeral=True)
            return

        embed = self._setup_preview_embed(ctx.guild)
        view = SetupConfirmView(self, ctx)
        await ctx.send(embed=embed, view=view)

    async def _run_setup(self, ctx: commands.Context, features: dict[str, bool]):
        guild = ctx.guild
        guild_id = guild.id
        self._active_setups.add(guild_id)

        progress = await ctx.send("🔧 **Memulai setup...**")

        results = {"categories": 0, "channels": 0, "features": 0, "errors": []}

        try:
            # ── 0. Clean up default + existing plan channels ──
            deleted_count = 0
            plan_cat_names = set(CHANNEL_PLAN.keys())
            # Also clean old-style names from previous failed runs
            old_plan_cat_names = {"📁 General", "💬 Create Voice"}
            all_cat_names = plan_cat_names | old_plan_cat_names | {"Text Channels", "Voice Channels"}
            keep_categories = {"🎮 Game"}
            for channel in list(guild.channels):
                # Default Discord channels
                if channel.name.lower() in {"general", "text-channels", "voice-channels", "general-1"} and not channel.category:
                    try:
                        await channel.delete(reason="Server setup")
                        deleted_count += 1
                    except Exception:
                        pass
                    continue

                # Existing plan categories (new + old naming)
                if isinstance(channel, discord.CategoryChannel) and channel.name in all_cat_names and channel.name not in keep_categories:
                    try:
                        for ch in list(channel.channels):
                            await ch.delete(reason="Server setup")
                            deleted_count += 1
                        await channel.delete(reason="Server setup")
                        deleted_count += 1
                    except Exception:
                        pass

            if deleted_count:
                await progress.edit(content=f"🔧 **Membersihkan {deleted_count} channel lama...**")
                await asyncio.sleep(1)

            # ── 1. Create categories & channels ──
            total_plan = sum(len(v) for v in CHANNEL_PLAN.values())
            done = 0
            trigger_id = None
            interface_id = None
            for cat_name, channels in CHANNEL_PLAN.items():
                existing_cat = discord.utils.get(guild.categories, name=cat_name)
                if existing_cat:
                    category = existing_cat
                else:
                    try:
                        category = await guild.create_category(cat_name, reason="Server setup")
                        results["categories"] += 1
                    except Exception as e:
                        results["errors"].append(f"Kategori {cat_name}: {e}")
                        continue

                for ch in channels:
                    ch_name = ch["name"]
                    ch_type = ch["type"]
                    existing = discord.utils.get(category.channels, name=ch_name)
                    if existing:
                        if ch_name == "✨・interface":
                            interface_id = existing.id
                        elif ch_name == "➕ Create Caffee'":
                            trigger_id = existing.id
                        results["channels"] += 1
                        done += 1
                        continue
                    try:
                        perms = {}
                        if ch.get("admin_only"):
                            perms[guild.default_role] = discord.PermissionOverwrite(read_messages=False)
                        elif ch.get("gembok"):
                            perms[guild.default_role] = discord.PermissionOverwrite(connect=False, view_channel=True)
                        elif ch.get("everyone_send"):
                            perms[guild.default_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
                        else:
                            perms[guild.default_role] = discord.PermissionOverwrite(read_messages=True, send_messages=False)

                        if ch_type == "text":
                            tc = await guild.create_text_channel(ch_name, category=category, overwrites=perms or None, reason="Server setup")
                            if ch_name == "✨・interface":
                                interface_id = tc.id
                        else:
                            vc_kwargs = {"category": category, "overwrites": perms or None, "reason": "Server setup"}
                            if ch.get("user_limit"):
                                vc_kwargs["user_limit"] = ch["user_limit"]
                            vc = await guild.create_voice_channel(ch_name, **vc_kwargs)
                            if ch_name == "➕ Create Caffee'":
                                trigger_id = vc.id
                            if ch.get("afk"):
                                try:
                                    await guild.edit(afk_channel=vc, afk_timeout=3600)
                                except Exception:
                                    pass

                        results["channels"] += 1
                        done += 1
                        if done % 5 == 0:
                            await progress.edit(content=f"🔧 **Membuat channel... ({done}/{total_plan})**")

                    except Exception as e:
                        results["errors"].append(f"Channel {ch_name}: {e}")
                        done += 1

            # ── 2. Stats count langsung ──
            await self._update_server_stats(guild)

            # ── 3. Init voice interface ──
            voice_cog = self.bot.get_cog("VoiceInterfaceCog")
            if voice_cog:
                await voice_cog._ensure_interface(guild)
                if trigger_id and interface_id:
                    await voice_cog._save_channel_ids(guild.id, trigger_id, interface_id)

            # ── 4. Enable features ──
            await self._enable_features(guild_id, features, results)

            # ── 4. Done ──
            summary = (
                f"✅ **Setup selesai!**\n\n"
                f"🗑️ **{deleted_count}** default channel dibersihkan\n"
                f"📁 **{results['categories']}** kategori\n"
                f"📄 **{results['channels']}** channel\n"
                f"⚙️ **{results['features']}** fitur diaktifkan\n"
            )
            if results["errors"]:
                summary += f"\n⚠️ **{len(results['errors'])} error:**\n" + "\n".join(f"- {e}" for e in results["errors"][:3])

            embed = discord.Embed(title="✅ Setup Selesai! 🎉", description=summary, color=discord.Color.green())
            embed.add_field(name="🖥️ Dashboard", value=f"Atur lanjutan di [Dashboard]({self._dashboard_url(guild_id)})", inline=False)
            await progress.edit(content=None, embed=embed)

        except Exception as e:
            await progress.edit(content=f"❌ Setup gagal: {e}")
        finally:
            self._active_setups.discard(guild_id)

    async def _enable_features(self, guild_id: int, features: dict[str, bool], results: dict):
        from ..database.firebase_setup import db
        if db is None:
            return

        try:
            import asyncio
            ref = db.collection("guild_settings").document(str(guild_id))

            if features.get("anti_spam"):
                await asyncio.to_thread(ref.set, {"moderation_config": {"enabled": True}}, merge=True)
                results["features"] += 1

            if features.get("anti_nuke"):
                await asyncio.to_thread(ref.set, {"anti_nuke": {"enabled": True}}, merge=True)
                results["features"] += 1

            if features.get("welcome"):
                await asyncio.to_thread(ref.set, {"welcome": {"enabled": True}}, merge=True)
                results["features"] += 1

            if features.get("ai_chat"):
                await asyncio.to_thread(ref.set, {"ai_chat": {"enabled": True}}, merge=True)
                results["features"] += 1
        except Exception as e:
            results["errors"].append(f"Gagal simpan fitur: {e}")

    def _dashboard_url(self, guild_id: int) -> str:
        base = os.getenv("DASHBOARD_URL", "https://synapse-bot-dk9u.onrender.com")
        return f"{base}/dashboard/{guild_id}/settings"

    def get_uptime(self):
        uptime = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"



async def setup(bot):
    await bot.add_cog(GeneralCog(bot))
