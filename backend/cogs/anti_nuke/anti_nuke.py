import os
import discord
from discord.ext import commands
import asyncio
import time
import aiohttp
from datetime import datetime, timezone
from ..database.firebase_setup import db

# ── Constants ──
DEFAULT_CONFIG = {
    "enabled": False,
    "ban_threshold": 3,
    "kick_threshold": 3,
    "channel_threshold": 3,
    "role_threshold": 3,
    "admin_threshold": 2,
    "window_seconds": 10,
    "lockdown_duration": 1800,
    "whitelist_users": [],
    "whitelist_roles": [],
    "report_channel_id": "",
}

ADMIN_PERMISSIONS = [
    "administrator",
    "ban_members",
    "kick_members",
    "manage_channels",
    "manage_guild",
    "manage_roles",
    "manage_webhooks",
]

ACTION_DESCRIPTIONS = {
    "ban": "Mass Ban",
    "kick": "Mass Kick",
    "channel_create": "Mass Channel Create",
    "channel_delete": "Mass Channel Delete",
    "role_create": "Mass Role Create",
    "role_delete": "Mass Role Delete",
    "admin_grant": "Admin Permission Grant",
    "role_admin": "Role Admin Permission",
    "webhook_spam": "Webhook Abuse",
}


class AntiNuke(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._action_log: dict[str, dict[str, list[float]]] = {}
        self._lockdowns: dict[str, dict] = {}
        self._restore_tasks: dict[str, asyncio.Task] = {}
        self._session: aiohttp.ClientSession | None = None

    async def cog_load(self):
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))

    async def cog_unload(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get_config(self, guild_id: str) -> dict:
        if db is None:
            return dict(DEFAULT_CONFIG)
        try:
            doc_ref = db.collection("guild_settings").document(guild_id)
            doc = await asyncio.to_thread(doc_ref.get)
            if doc.exists:
                cfg = doc.to_dict().get("anti_nuke", {})
                merged = dict(DEFAULT_CONFIG)
                merged.update(cfg)
                return merged
        except Exception:
            pass
        return dict(DEFAULT_CONFIG)

    async def _save_config(self, guild_id: str, config: dict):
        if db is None:
            return
        try:
            doc_ref = db.collection("guild_settings").document(guild_id)
            await asyncio.to_thread(doc_ref.set, {"anti_nuke": config}, merge=True)
        except Exception as e:
            print(f"[ANTI-NUKE] Failed to save config: {e}")

    def _is_whitelisted(self, member: discord.Member, config: dict) -> bool:
        if member.guild_permissions.administrator:
            return True
        if str(member.id) in config.get("whitelist_users", []):
            return True
        user_roles = [str(r.id) for r in member.roles]
        if any(rid in config.get("whitelist_roles", []) for rid in user_roles):
            return True
        return False

    def _track_action(self, guild_id: str, user_id: str, action: str, config: dict) -> bool:
        window = config.get("window_seconds", 10)
        key = f"{user_id}:{action}"
        now = time.time()

        log = self._action_log.setdefault(guild_id, {}).setdefault(key, [])
        log[:] = [t for t in log if now - t < window]
        log.append(now)

        threshold_key = f"{action}_threshold"
        threshold = config.get(threshold_key, DEFAULT_CONFIG.get(threshold_key, 3))
        return len(log) >= threshold

    async def _lockdown(self, guild: discord.Guild, config: dict):
        guild_id = str(guild.id)
        if guild_id in self._lockdowns:
            return

        print(f"[ANTI-NUKE] Locking down {guild.name}")
        lockdown_data = {"channels": {}}
        try:
            for channel in guild.channels:
                overwrites = channel.overwrites_for(guild.default_role)
                lockdown_data["channels"][str(channel.id)] = {
                    "send_messages": overwrites.send_messages,
                    "add_reactions": overwrites.add_reactions,
                    "create_instant_invite": overwrites.create_instant_invite,
                }
                await channel.set_permissions(
                    guild.default_role,
                    send_messages=False,
                    add_reactions=False,
                    create_instant_invite=False,
                    reason="Anti-Nuke: Auto lockdown",
                )

            self._lockdowns[guild_id] = lockdown_data
            duration = config.get("lockdown_duration", 1800)

            report = config.get("report_channel_id", "")
            if report:
                ch = guild.get_channel(int(report))
                if ch:
                    await ch.send(
                        embed=discord.Embed(
                            title="LOCKDOWN ACTIVE",
                            description=(
                                f"Server is now in lockdown mode for **{duration//60} minutes**.\n"
                                f"All members cannot send messages while lockdown is active.\n"
                                f"Use `!antinuke restore` to lift early."
                            ),
                            color=discord.Color.red(),
                            timestamp=datetime.now(timezone.utc),
                        )
                    )

            self._restore_tasks[guild_id] = asyncio.create_task(
                self._delayed_restore(guild_id, duration)
            )

        except Exception as e:
            print(f"[ANTI-NUKE] Lockdown error on {guild.name}: {e}")

    async def _delayed_restore(self, guild_id: str, delay: int):
        await asyncio.sleep(delay)
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            await self._restore_permissions(guild)

    async def _restore_permissions(self, guild: discord.Guild):
        guild_id = str(guild.id)
        data = self._lockdowns.pop(guild_id, None)
        if not data:
            return

        task = self._restore_tasks.pop(guild_id, None)
        if task and not task.done():
            task.cancel()

        print(f"[ANTI-NUKE] Restoring permissions for {guild.name}")
        for ch_id, perms in data.get("channels", {}).items():
            channel = guild.get_channel(int(ch_id))
            if channel:
                try:
                    kw = {}
                    if perms.get("send_messages") is not None:
                        kw["send_messages"] = perms["send_messages"]
                    if perms.get("add_reactions") is not None:
                        kw["add_reactions"] = perms["add_reactions"]
                    if perms.get("create_instant_invite") is not None:
                        kw["create_instant_invite"] = perms["create_instant_invite"]
                    if kw:
                        await channel.set_permissions(
                            guild.default_role,
                            **kw,
                            reason="Anti-Nuke: Restoring permissions after lockdown",
                        )
                except Exception as e:
                    print(f"[ANTI-NUKE] Restore error on #{channel.name}: {e}")

        config = await self._get_config(guild_id)
        report = config.get("report_channel_id", "")
        if report:
            ch = guild.get_channel(int(report))
            if ch:
                await ch.send(
                    embed=discord.Embed(
                        title="LOCKDOWN LIFTED",
                        description="Server permissions have been restored.",
                        color=discord.Color.green(),
                        timestamp=datetime.now(timezone.utc),
                    )
                )

    async def _report(self, guild: discord.Guild, user: discord.User | discord.Member, action: str, details: str, config: dict):
        report = config.get("report_channel_id", "")
        if not report:
            return
        ch = guild.get_channel(int(report))
        if not ch:
            return

        embed = discord.Embed(
            title="Anti-Nuke Alert",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Action", value=ACTION_DESCRIPTIONS.get(action, action), inline=True)
        embed.add_field(name="User", value=f"{user.name} (`{user.id}`)", inline=True)
        embed.add_field(name="Details", value=details, inline=False)
        try:
            await ch.send(embed=embed)
        except Exception:
            pass

    # ── AI Post-Analysis (OpenRouter with free model fallback) ──

    async def _collect_audit_entries(self, guild: discord.Guild, window: int) -> list[dict]:
        entries = []
        after = discord.utils.utcnow() - discord.utils.MINUTES * (window / 60)
        audit_log_action_map = [
            discord.AuditLogAction.ban,
            discord.AuditLogAction.kick,
            discord.AuditLogAction.channel_create,
            discord.AuditLogAction.channel_delete,
            discord.AuditLogAction.role_create,
            discord.AuditLogAction.role_delete,
            discord.AuditLogAction.member_role_update,
            discord.AuditLogAction.role_update,
            discord.AuditLogAction.webhook_create,
        ]
        try:
            async for entry in guild.audit_logs(after=after, limit=50):
                if entry.action in audit_log_action_map:
                    entries.append({
                        "action": str(entry.action).split(".")[-1],
                        "user": str(entry.user),
                        "user_id": entry.user.id,
                        "target": str(entry.target) if entry.target else "unknown",
                        "reason": entry.reason or "",
                        "created_at": entry.created_at.strftime("%H:%M:%S"),
                    })
        except Exception as e:
            print(f"[ANTI-NUKE] Audit log collection error: {e}")
        return entries

    async def _ai_analyze_attack(self, guild: discord.Guild, action: str, mod_user: discord.User, config: dict):
        if not self._session:
            return

        window = config.get("window_seconds", 10)
        entries = await self._collect_audit_entries(guild, window)
        if not entries:
            return

        events_text = "\n".join(
            f"[{e['created_at']}] {e['action']} | by {e['user']} ({e['user_id']}) | target: {e['target']} | reason: {e['reason']}"
            for e in entries[:15]
        )

        system_prompt = (
            "You are a Discord anti-nuke attack analyst. Keep your response under 300 characters. "
            "Be direct, no fluff. Cover: attack type, severity (low/medium/high/critical), "
            "likely attacker, genuine attack or false positive, damage done, and one-line recommendation."
        )
        user_prompt = (
            f"Server '{guild.name}' triggered '{ACTION_DESCRIPTIONS.get(action, action)}' lockdown.\n"
            f"Events from last {window}s:\n{events_text}"
        )

        text = await self._call_openrouter(system_prompt, user_prompt)
        if not text:
            return

        report = config.get("report_channel_id", "")
        if report:
            ch = guild.get_channel(int(report))
            if ch:
                embed = discord.Embed(
                    title="AI Attack Analysis",
                    color=discord.Color.orange(),
                    description=text,
                    timestamp=datetime.now(timezone.utc),
                )
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass

    async def _call_openrouter(self, system_prompt: str, user_prompt: str) -> str | None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return None
        models = [
            "openrouter/free",
            "google/gemma-4-26b-a4b-it:free",
            "google/gemma-4-31b-it:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
            "nvidia/nemotron-3-nano-30b-a3b:free",
            "meta-llama/llama-3.3-70b-instruct",
        ]
        for model in models:
            payload = {
                "model": model,
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                "temperature": 0.3, "max_tokens": 512,
            }
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            try:
                async with self._session.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    text = data["choices"][0]["message"]["content"].strip()
                    if text:
                        print(f"[ANTI-NUKE] AI analysis via OpenRouter ({model})")
                        return text
            except Exception:
                continue
        print("[ANTI-NUKE] OpenRouter analysis failed — all models exhausted")
        return None

    def _check_admin_grant(self, before: discord.Member, after: discord.Member) -> bool:
        for perm in ADMIN_PERMISSIONS:
            if not getattr(before.guild_permissions, perm, False) and getattr(after.guild_permissions, perm, False):
                return True
        return False

    def _check_role_admin(self, before: discord.Role, after: discord.Role) -> bool:
        for perm in ADMIN_PERMISSIONS:
            if not getattr(before.permissions, perm, False) and getattr(after.permissions, perm, False):
                return True
        return False

    # ── Audit log helpers ──

    async def _audit_user(self, guild: discord.Guild, action_type: discord.AuditLogAction) -> discord.User | None:
        try:
            entry = await guild.audit_logs(action=action_type, limit=1).__anext__()
            return entry.user
        except (StopAsyncIteration, Exception):
            return None

    # ── Event: on_member_ban ──

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        guild_id = str(guild.id)
        config = await self._get_config(guild_id)
        if not config.get("enabled", False):
            return

        mod = await self._audit_user(guild, discord.AuditLogAction.ban)
        if mod is None or mod.id == self.bot.user.id:
            return
        if self._is_whitelisted(guild.get_member(mod.id) or mod, config):
            return

        if self._track_action(guild_id, str(mod.id), "ban", config):
            await self._lockdown(guild, config)
            await self._report(guild, mod, "ban", f"Threshold exceeded: {config.get('ban_threshold', 3)} bans in {config.get('window_seconds', 10)}s", config)
            asyncio.create_task(self._ai_analyze_attack(guild, "ban", mod, config))

    # ── Event: on_member_remove (kick detection via audit log) ──

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild_id = str(member.guild.id)
        config = await self._get_config(guild_id)
        if not config.get("enabled", False):
            return

        mod = await self._audit_user(member.guild, discord.AuditLogAction.kick)
        if mod is None or mod.id == self.bot.user.id:
            return
        if self._is_whitelisted(member.guild.get_member(mod.id) or mod, config):
            return

        if self._track_action(guild_id, str(mod.id), "kick", config):
            await self._lockdown(member.guild, config)
            await self._report(member.guild, mod, "kick", f"Threshold exceeded: {config.get('kick_threshold', 3)} kicks in {config.get('window_seconds', 10)}s", config)
            asyncio.create_task(self._ai_analyze_attack(member.guild, "kick", mod, config))

    # ── Event: on_guild_channel_create ──

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        guild_id = str(guild.id)
        config = await self._get_config(guild_id)
        if not config.get("enabled", False):
            return

        mod = await self._audit_user(guild, discord.AuditLogAction.channel_create)
        if mod is None or mod.id == self.bot.user.id:
            return
        if self._is_whitelisted(guild.get_member(mod.id) or mod, config):
            return

        if self._track_action(guild_id, str(mod.id), "channel_create", config):
            await self._lockdown(guild, config)
            await self._report(guild, mod, "channel_create", f"Threshold exceeded: {config.get('channel_threshold', 3)} channels created in {config.get('window_seconds', 10)}s", config)
            asyncio.create_task(self._ai_analyze_attack(guild, "channel_create", mod, config))

    # ── Event: on_guild_channel_delete ──

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        guild_id = str(guild.id)
        config = await self._get_config(guild_id)
        if not config.get("enabled", False):
            return

        mod = await self._audit_user(guild, discord.AuditLogAction.channel_delete)
        if mod is None or mod.id == self.bot.user.id:
            return
        if self._is_whitelisted(guild.get_member(mod.id) or mod, config):
            return

        if self._track_action(guild_id, str(mod.id), "channel_delete", config):
            await self._lockdown(guild, config)
            await self._report(guild, mod, "channel_delete", f"Threshold exceeded: {config.get('channel_threshold', 3)} channels deleted in {config.get('window_seconds', 10)}s", config)
            asyncio.create_task(self._ai_analyze_attack(guild, "channel_delete", mod, config))

    # ── Event: on_guild_role_create ──

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        guild = role.guild
        guild_id = str(guild.id)
        config = await self._get_config(guild_id)
        if not config.get("enabled", False):
            return

        mod = await self._audit_user(guild, discord.AuditLogAction.role_create)
        if mod is None or mod.id == self.bot.user.id:
            return
        if self._is_whitelisted(guild.get_member(mod.id) or mod, config):
            return

        if self._track_action(guild_id, str(mod.id), "role_create", config):
            await self._lockdown(guild, config)
            await self._report(guild, mod, "role_create", f"Threshold exceeded: {config.get('role_threshold', 3)} roles created in {config.get('window_seconds', 10)}s", config)
            asyncio.create_task(self._ai_analyze_attack(guild, "role_create", mod, config))

    # ── Event: on_guild_role_delete ──

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        guild_id = str(guild.id)
        config = await self._get_config(guild_id)
        if not config.get("enabled", False):
            return

        mod = await self._audit_user(guild, discord.AuditLogAction.role_delete)
        if mod is None or mod.id == self.bot.user.id:
            return
        if self._is_whitelisted(guild.get_member(mod.id) or mod, config):
            return

        if self._track_action(guild_id, str(mod.id), "role_delete", config):
            await self._lockdown(guild, config)
            await self._report(guild, mod, "role_delete", f"Threshold exceeded: {config.get('role_threshold', 3)} roles deleted in {config.get('window_seconds', 10)}s", config)
            asyncio.create_task(self._ai_analyze_attack(guild, "role_delete", mod, config))

    # ── Event: on_member_update (admin perms grant) ──

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.guild_permissions == after.guild_permissions:
            return
        if not self._check_admin_grant(before, after):
            return

        guild = after.guild
        guild_id = str(guild.id)
        config = await self._get_config(guild_id)
        if not config.get("enabled", False):
            return

        mod = await self._audit_user(guild, discord.AuditLogAction.member_role_update)
        if mod is None or mod.id == self.bot.user.id:
            return
        if self._is_whitelisted(guild.get_member(mod.id) or mod, config):
            return

        if self._track_action(guild_id, str(mod.id), "admin_grant", config):
            await self._lockdown(guild, config)
            await self._report(guild, mod, "admin_grant", f"{after.name} was granted admin perms by {mod.name}", config)
            asyncio.create_task(self._ai_analyze_attack(guild, "admin_grant", mod, config))

    # ── Event: on_guild_role_update (role gets admin) ──

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        if before.permissions == after.permissions:
            return
        if not self._check_role_admin(before, after):
            return

        guild = after.guild
        guild_id = str(guild.id)
        config = await self._get_config(guild_id)
        if not config.get("enabled", False):
            return

        mod = await self._audit_user(guild, discord.AuditLogAction.role_update)
        if mod is None or mod.id == self.bot.user.id:
            return
        if self._is_whitelisted(guild.get_member(mod.id) or mod, config):
            return

        if self._track_action(guild_id, str(mod.id), "role_admin", config):
            await self._lockdown(guild, config)
            await self._report(guild, mod, "role_admin", f"Role {after.name} was given admin perms by {mod.name}", config)
            asyncio.create_task(self._ai_analyze_attack(guild, "role_admin", mod, config))

    # ── Event: on_webhooks_update ──

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        guild_id = str(guild.id)
        config = await self._get_config(guild_id)
        if not config.get("enabled", False):
            return

        mod = await self._audit_user(guild, discord.AuditLogAction.webhook_create)
        if mod is None or mod.id == self.bot.user.id:
            return
        if self._is_whitelisted(guild.get_member(mod.id) or mod, config):
            return

        if self._track_action(guild_id, str(mod.id), "webhook_spam", config):
            await self._lockdown(guild, config)
            await self._report(guild, mod, "webhook_spam", f"Threshold exceeded: {config.get('channel_threshold', 3)} webhooks in {config.get('window_seconds', 10)}s", config)
            asyncio.create_task(self._ai_analyze_attack(guild, "webhook_spam", mod, config))

    # ══════════════════════════════════════════════════════════════════
    # COMMANDS
    # ══════════════════════════════════════════════════════════════════

    @commands.hybrid_command(name="antinuke", description="Toggle Anti-Nuke protection")
    @commands.has_permissions(administrator=True)
    async def antinuke_toggle(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        config = await self._get_config(guild_id)
        config["enabled"] = not config.get("enabled", False)
        await self._save_config(guild_id, config)
        status = "ON" if config["enabled"] else "OFF"
        await ctx.send(f"Anti-Nuke is now **{status}**.")

    @commands.hybrid_command(name="antinuke-whitelist", description="Add/remove users/roles from anti-nuke whitelist")
    @commands.has_permissions(administrator=True)
    async def antinuke_whitelist(self, ctx: commands.Context, target_type: str, target_id: str):
        guild_id = str(ctx.guild.id)
        config = await self._get_config(guild_id)
        if target_type == "user":
            key = "whitelist_users"
        elif target_type == "role":
            key = "whitelist_roles"
        else:
            await ctx.send("Use: `!antinuke-whitelist user <id>` or `!antinuke-whitelist role <id>`")
            return
        lst = config.get(key, [])
        if target_id in lst:
            lst.remove(target_id)
            action = "removed from"
        else:
            lst.append(target_id)
            action = "added to"
        config[key] = lst
        await self._save_config(guild_id, config)
        await ctx.send(f"`{target_id}` {action} {target_type} whitelist.")

    @commands.hybrid_command(name="antinuke-restore", description="Manually restore server permissions after lockdown")
    @commands.has_permissions(administrator=True)
    async def antinuke_restore(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        if guild_id not in self._lockdowns:
            await ctx.send("Server is not in lockdown.")
            return
        await self._restore_permissions(ctx.guild)
        await ctx.send("Permissions restored. Lockdown lifted.")

    @commands.hybrid_command(name="antinuke-status", description="View Anti-Nuke status and config")
    @commands.has_permissions(administrator=True)
    async def antinuke_status(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        config = await self._get_config(guild_id)
        in_lockdown = guild_id in self._lockdowns
        embed = discord.Embed(
            title="Anti-Nuke Status",
            color=discord.Color.blue() if config.get("enabled") else discord.Color.dark_gray(),
        )
        embed.add_field(name="Enabled", value=str(config.get("enabled", False)), inline=True)
        embed.add_field(name="Lockdown Active", value=str(in_lockdown), inline=True)
        embed.add_field(name="", value="", inline=False)
        embed.add_field(name="Ban Threshold", value=str(config.get("ban_threshold", 3)), inline=True)
        embed.add_field(name="Kick Threshold", value=str(config.get("kick_threshold", 3)), inline=True)
        embed.add_field(name="Channel Threshold", value=str(config.get("channel_threshold", 3)), inline=True)
        embed.add_field(name="Role Threshold", value=str(config.get("role_threshold", 3)), inline=True)
        embed.add_field(name="Admin Grant Threshold", value=str(config.get("admin_threshold", 2)), inline=True)
        embed.add_field(name="Window", value=f"{config.get('window_seconds', 10)}s", inline=True)
        embed.add_field(name="Lockdown Duration", value=f"{config.get('lockdown_duration', 1800)//60}m", inline=True)
        embed.add_field(name="Whitelist Users", value=str(len(config.get("whitelist_users", []))), inline=True)
        embed.add_field(name="Whitelist Roles", value=str(len(config.get("whitelist_roles", []))), inline=True)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AntiNuke(bot))