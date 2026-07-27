from __future__ import annotations

import asyncio, os, json, re, time as time_module
from typing import List

import discord
from discord.ext import commands, tasks

from ..database.firebase_setup import db
from .agent_tools import (
    TOOL_DEFINITIONS, TOOL_DESCRIPTION, DISCORD_PERMISSIONS_KNOWLEDGE, DISCORD_UI_KNOWLEDGE,
    parse_tool_call, execute_tool, validate_tool_call,
)

MAX_AGENT_STEPS = 15
AGENT_TIMEOUT = 120
MEMORY_MAX_TURNS = 20  # maksimal 20 pasang Q&A disimpan (permanen di Firestore)


class AIChatAgent(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._active_sessions: set[int] = set()
        self._agent_channels: dict[int, float] = {}  # channel_id -> timestamp
        self._conversation_memory: dict[int, list[dict]] = {}  # user_id -> history (RAM cache)
        self._server_scan_cache: dict[int, dict] = {}  # guild_id -> scan data
        self._scheduler_loop.start()

    MUTATING_TOOLS = {
        "create_role", "edit_role", "delete_role", "assign_role", "remove_role",
        "create_channel", "delete_channel", "rename_channel", "edit_channel_permissions",
        "ban_member", "unban_member", "kick_member", "timeout_member",
        "batch_create_channels", "batch_create_roles", "apply_template",
        "edit_server", "save_snapshot", "rollback", "schedule_task",
        "send_message", "add_reaction",
        "run_command",
    }

    def cog_unload(self):
        self._scheduler_loop.cancel()

    @tasks.loop(seconds=60)
    async def _scheduler_loop(self):
        """Cek & eksekusi tugas terjadwal dari Firestore."""
        if db is None:
            return
        try:
            docs = await asyncio.to_thread(
                lambda: list(db.collection("agent_schedules").where("enabled", "==", True).stream())
            )
            now = time_module.time()
            for doc in docs:
                task = doc.to_dict()
                if task.get("next_run", 0) > now:
                    continue
                guild = self.bot.get_guild(task.get("guild_id", 0))
                if not guild:
                    continue
                action = task.get("action", "")
                params = task.get("params", {})
                try:
                    if action == "assign_role":
                        role_name = params.get("role", "")
                        member_name = params.get("member", "")
                        if role_name and member_name:
                            role = discord.utils.get(guild.roles, name=role_name)
                            member = discord.utils.find(lambda m: member_name.lower() in str(m).lower() or m.name.lower() == member_name.lower(), guild.members)
                            if role and member:
                                await member.add_roles(role, reason="AI Agent: scheduled task")
                    elif action == "remove_role":
                        role_name = params.get("role", "")
                        member_name = params.get("member", "")
                        if role_name and member_name:
                            role = discord.utils.get(guild.roles, name=role_name)
                            member = discord.utils.find(lambda m: member_name.lower() in str(m).lower() or m.name.lower() == member_name.lower(), guild.members)
                            if role and member:
                                await member.remove_roles(role, reason="AI Agent: scheduled task")
                    elif action == "send_message":
                        channel_name = params.get("channel", "")
                        message = params.get("message", "")
                        if channel_name and message:
                            ch = discord.utils.get(guild.text_channels, name=channel_name)
                            if ch:
                                await ch.send(message[:1900])
                    task["last_run"] = now
                    task["next_run"] = now + task.get("interval", 3600)
                    await asyncio.to_thread(
                        lambda d=doc.id, t=task: db.collection("agent_schedules").document(d).update({
                            "last_run": t["last_run"],
                            "next_run": t["next_run"],
                        })
                    )
                except Exception as e:
                    print(f"[AGENT SCHEDULER] Error executing task '{task.get('name')}': {e}")
        except Exception as e:
            print(f"[AGENT SCHEDULER] Error: {e}")

    # ── Firestore scan cache ──

    async def _save_scan_firestore(self, guild_id: int, data: dict):
        try:
            await asyncio.to_thread(
                lambda: db.collection("agent_scan_cache").document(str(guild_id)).set({
                    "guild_id": guild_id,
                    "data": data,
                    "updated_at": time_module.time(),
                })
            )
        except Exception as e:
            print(f"[AGENT] Error save scan to Firestore: {e}")

    async def _load_scan_firestore(self, guild_id: int) -> dict | None:
        try:
            doc = await asyncio.to_thread(
                lambda: db.collection("agent_scan_cache").document(str(guild_id)).get()
            )
            if doc.exists:
                data = doc.to_dict().get("data")
                if data:
                    self._server_scan_cache[guild_id] = data
                    return data
        except Exception as e:
            print(f"[AGENT] Error load scan from Firestore: {e}")
        return None

    async def _update_scan_cache(self, guild: discord.Guild, tool_fn: str):
        """Partial update scan cache setelah tool mutation, lalu simpan ke Firestore."""
        scan = self._server_scan_cache.get(guild.id)
        if not scan:
            return

        try:
            if tool_fn in ("create_channel", "delete_channel", "rename_channel", "edit_channel_permissions", "batch_create_channels", "apply_template"):
                channels = []
                categories = []
                for cat in guild.categories:
                    cat_info = {"name": cat.name, "id": cat.id, "position": cat.position, "channels": []}
                    for ch in cat.channels:
                        ch_info = {
                            "name": ch.name, "id": ch.id, "type": str(ch.type),
                            "position": ch.position, "topic": ch.topic if hasattr(ch, "topic") else None,
                            "nsfw": ch.nsfw if hasattr(ch, "nsfw") else False,
                            "bitrate": ch.bitrate if hasattr(ch, "bitrate") else None,
                            "user_limit": ch.user_limit if hasattr(ch, "user_limit") else 0,
                        }
                        cat_info["channels"].append(ch_info)
                        channels.append(ch_info)
                    categories.append(cat_info)
                uncat = [c for c in guild.channels if not c.category and not isinstance(c, discord.CategoryChannel)]
                if uncat:
                    cat_info = {"name": "[No Category]", "id": 0, "position": -1, "channels": []}
                    for ch in uncat:
                        ch_info = {
                            "name": ch.name, "id": ch.id, "type": str(ch.type),
                            "position": ch.position, "topic": ch.topic if hasattr(ch, "topic") else None,
                            "nsfw": ch.nsfw if hasattr(ch, "nsfw") else False,
                        }
                        cat_info["channels"].append(ch_info)
                        channels.append(ch_info)
                    categories.append(cat_info)
                scan["channels"] = channels
                scan["categories"] = categories

            elif tool_fn in ("create_role", "edit_role", "delete_role", "batch_create_roles", "apply_template"):
                scan["roles"] = []
                for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
                    if role.is_default() or role.is_bot_managed() or role.is_integration():
                        continue
                    scan["roles"].append({
                        "name": role.name, "id": role.id,
                        "color": str(role.color), "position": role.position,
                        "member_count": len(role.members),
                        "mentionable": role.mentionable, "hoist": role.hoist,
                        "permissions": [p for p, v in role.permissions if v],
                    })

            elif tool_fn in ("assign_role", "remove_role"):
                for role_entry in scan["roles"]:
                    role_obj = guild.get_role(role_entry["id"])
                    if role_obj:
                        role_entry["member_count"] = len(role_obj.members)

            elif tool_fn in ("ban_member", "unban_member"):
                bans = [{"user_name": str(b.user), "id": b.user.id, "reason": b.reason}
                        async for b in guild.bans()]
                scan["bans"] = bans
                scan["server"]["member_count"] = guild.member_count

            elif tool_fn in ("kick_member", "timeout_member"):
                scan["server"]["member_count"] = guild.member_count

            elif tool_fn == "edit_server":
                scan["server"]["name"] = guild.name
                scan["server"]["description"] = guild.description

            self._server_scan_cache[guild.id] = scan
            await self._save_scan_firestore(guild.id, scan)
        except Exception as e:
            print(f"[AGENT] Error updating scan cache for {tool_fn}: {e}")

    # ── Scan Server ──

    async def _scan_server(self, guild: discord.Guild) -> dict:
        """Scan seluruh data server dan return dict lengkap."""
        data = {
            "server": {
                "name": guild.name,
                "id": guild.id,
                "owner_name": str(guild.owner),
                "owner_id": guild.owner_id,
                "member_count": guild.member_count,
                "boost_level": guild.premium_tier,
                "boost_count": guild.premium_subscription_count,
                "features": list(guild.features),
                "created_at": guild.created_at.isoformat(),
                "description": guild.description,
                "afk_timeout": guild.afk_timeout,
            },
            "roles": [],
            "channels": [],
            "categories": [],
            "members": [],
            "bans": [],
            "emojis": [],
            "stickers": [],
        }

        # Roles
        for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
            if role.is_default() or role.is_bot_managed() or role.is_integration():
                continue
            data["roles"].append({
                "name": role.name,
                "id": role.id,
                "color": str(role.color),
                "position": role.position,
                "member_count": len(role.members),
                "mentionable": role.mentionable,
                "hoist": role.hoist,
                "permissions": [p for p, v in role.permissions if v],
            })

        # Categories + Channels
        for cat in guild.categories:
            cat_info = {
                "name": cat.name,
                "id": cat.id,
                "position": cat.position,
                "channels": [],
            }
            for ch in cat.channels:
                ch_info = {
                    "name": ch.name,
                    "id": ch.id,
                    "type": str(ch.type),
                    "position": ch.position,
                    "topic": ch.topic if hasattr(ch, "topic") else None,
                    "nsfw": ch.nsfw if hasattr(ch, "nsfw") else False,
                    "bitrate": ch.bitrate if hasattr(ch, "bitrate") else None,
                    "user_limit": ch.user_limit if hasattr(ch, "user_limit") else 0,
                }
                cat_info["channels"].append(ch_info)
                data["channels"].append(ch_info)
            data["categories"].append(cat_info)

        # Uncategorized channels
        uncat = [c for c in guild.channels if not c.category and not isinstance(c, discord.CategoryChannel)]
        if uncat:
            cat_info = {
                "name": "[No Category]",
                "id": 0,
                "position": -1,
                "channels": [],
            }
            for ch in uncat:
                ch_info = {
                    "name": ch.name,
                    "id": ch.id,
                    "type": str(ch.type),
                    "position": ch.position,
                    "topic": ch.topic if hasattr(ch, "topic") else None,
                    "nsfw": ch.nsfw if hasattr(ch, "nsfw") else False,
                }
                cat_info["channels"].append(ch_info)
                data["channels"].append(ch_info)
            data["categories"].append(cat_info)

        # Members (max 100)
        for m in guild.members[:100]:
            data["members"].append({
                "name": m.name,
                "display_name": m.display_name,
                "id": m.id,
                "bot": m.bot,
                "joined_at": m.joined_at.isoformat() if m.joined_at else None,
                "top_role": m.top_role.name if m.top_role.name != "@everyone" else None,
                "roles": [r.name for r in m.roles if r.name != "@everyone"][:5],
            })

        # Bans
        try:
            bans = [b async for b in guild.bans()]
            for b in bans[:50]:
                data["bans"].append({
                    "user_name": b.user.name,
                    "user_id": b.user.id,
                    "reason": b.reason,
                })
        except discord.Forbidden:
            data["bans"] = []

        # Emojis
        for e in guild.emojis:
            data["emojis"].append({
                "name": e.name,
                "id": e.id,
                "animated": e.animated,
            })

        # Stickers
        for s in guild.stickers:
            data["stickers"].append({
                "name": s.name,
                "id": s.id,
                "description": s.description,
            })

        await self._save_scan_firestore(guild.id, data)
        return data

    def _build_scan_context(self, data: dict) -> str:
        """Buat teks ringkasan dari hasil scan untuk disuntikkan ke prompt AI."""
        if not data:
            return ""
        s = data["server"]
        lines = [
            f"=== SERVER SCAN: {s['name']} (ID: {s['id']}) ===",
            f"Owner: {s['owner_name']} | Member: {s['member_count']} | Boost: Lv.{s['boost_level']} ({s['boost_count']})",
        ]

        # Roles
        roles = data.get("roles", [])
        lines.append(f"\n--- ROLES ({len(roles)}) ---")
        for r in roles[:30]:
            perms = ", ".join(r["permissions"][:8])
            if len(r["permissions"]) > 8:
                perms += f" +{len(r['permissions'])-8} lagi"
            lines.append(f"  {r['name']} (pos:{r['position']}, {r['member_count']} member)")
            if perms:
                lines.append(f"    perms: {perms}")

        # Categories & Channels
        cats = data.get("categories", [])
        lines.append(f"\n--- CHANNELS ({len(data.get('channels', []))}) ---")
        for cat in cats:
            lines.append(f"  ▸ {cat['name']}")
            for ch in cat.get("channels", []):
                nsfw_tag = " [NSFW]" if ch.get("nsfw") else ""
                extra = ""
                if ch.get("topic"):
                    extra = f" topic=\"{ch['topic'][:60]}\""
                if ch.get("bitrate"):
                    extra += f" bitrate={ch['bitrate']}"
                if ch.get("user_limit"):
                    extra += f" limit={ch['user_limit']}"
                lines.append(f"    - {ch['name']} ({ch['type']}){nsfw_tag}{extra}")

        # Members
        members = data.get("members", [])
        lines.append(f"\n--- MEMBERS ({s['member_count']}, showing {len(members)}) ---")
        for m in members[:30]:
            roles_str = ", ".join(m["roles"][:3]) if m["roles"] else "-"
            bot_tag = " [BOT]" if m["bot"] else ""
            lines.append(f"  {m['display_name']}{bot_tag} → {roles_str}")

        # Bans
        bans = data.get("bans", [])
        if bans:
            lines.append(f"\n--- BANS ({len(bans)}) ---")
            for b in bans[:10]:
                reason = f" reason: {b['reason'][:50]}" if b["reason"] else ""
                lines.append(f"  {b['user_name']}{reason}")

        # Emojis & Stickers
        emojis = data.get("emojis", [])
        if emojis:
            lines.append(f"\n--- CUSTOM EMOJIS ({len(emojis)}) ---")
            lines.append(f"  {', '.join(e['name'] for e in emojis[:20])}")
        stickers = data.get("stickers", [])
        if stickers:
            lines.append(f"\n--- CUSTOM STICKERS ({len(stickers)}) ---")
            lines.append(f"  {', '.join(s['name'] for s in stickers[:10])}")

        lines.append("\n=== END SCAN ===")
        return "\n".join(lines)

    def _is_recent_agent_channel(self, channel_id: int) -> bool:
        ts = self._agent_channels.get(channel_id)
        if ts and time_module.time() - ts < 120:
            return True
        return False

    def _memory_doc_id(self, user_id: int, guild_id: int) -> str:
        return f"{user_id}_{guild_id}"

    async def _load_memory_firestore(self, user_id: int, guild_id: int) -> list[dict]:
        """Load memory dari Firestore."""
        try:
            doc_id = self._memory_doc_id(user_id, guild_id)
            doc = await asyncio.to_thread(
                lambda: db.collection("agent_memory").document(doc_id).get()
            )
            if doc.exists:
                data = doc.to_dict()
                history = data.get("history", [])
                # Cache di RAM
                self._conversation_memory[user_id] = history
                return history
        except Exception as e:
            print(f"[AGENT] Error load memory from Firestore: {e}")
        return []

    async def _save_memory_firestore(self, user_id: int, guild_id: int, history: list[dict]):
        """Simpan memory ke Firestore (async, fire-and-forget)."""
        try:
            doc_id = self._memory_doc_id(user_id, guild_id)
            await asyncio.to_thread(
                lambda: db.collection("agent_memory").document(doc_id).set({
                    "user_id": user_id,
                    "guild_id": guild_id,
                    "history": history,
                    "updated_at": time_module.time(),
                })
            )
        except Exception as e:
            print(f"[AGENT] Error save memory to Firestore: {e}")

    def _get_memory(self, user_id: int) -> list[dict]:
        # Cek RAM cache dulu (tanpa TTL)
        return self._conversation_memory.get(user_id, [])

    def _save_memory(self, user_id: int, guild_id: int, new_user_msg: str, new_ai_msg: str):
        mem = self._get_memory(user_id)
        if new_user_msg:
            mem.append({"role": "user", "content": new_user_msg})
        if new_ai_msg:
            mem.append({"role": "assistant", "content": new_ai_msg})
        # Simpan maksimal MEMORY_MAX_TURNS pasang
        if len(mem) > MEMORY_MAX_TURNS * 2:
            mem = mem[-(MEMORY_MAX_TURNS * 2):]
        self._conversation_memory[user_id] = mem
        # Simpan ke Firestore (background)
        asyncio.ensure_future(self._save_memory_firestore(user_id, guild_id, mem))

    # ── Settings ──

    async def _get_agent_config(self, guild_id: str) -> dict:
        try:
            doc = await asyncio.to_thread(
                lambda: db.collection("guild_settings").document(str(guild_id)).get()
            )
            if not doc.exists:
                return {"agent_enabled": False, "agent_mode": "admin"}
            data = doc.to_dict()
            agent = data.get("agent", {}) if isinstance(data.get("agent"), dict) else {}
            return {
                "agent_enabled": agent.get("enabled", False),
                "agent_mode": agent.get("mode", "admin"),
            }
        except Exception as e:
            print(f"[AGENT] Error load config: {e}")
            return {"agent_enabled": False, "agent_mode": "admin"}

    async def _save_agent_config(self, guild_id: str, config: dict):
        try:
            payload = {
                "enabled": config.get("agent_enabled", False),
                "mode": config.get("agent_mode", "admin"),
            }
            await asyncio.to_thread(
                lambda: db.collection("guild_settings").document(str(guild_id)).set(
                    {"agent": payload}, merge=True
                )
            )
        except Exception as e:
            print(f"[AGENT] Error save config: {e}")

    # ── Permission check ──

    def _can_use_agent(self, member: discord.Member, config: dict) -> bool:
        if member == member.guild.owner:
            return True
        mode = config.get("agent_mode", "admin")
        if mode == "owner":
            return False
        return member.guild_permissions.administrator

    # ── Get AI Provider ──

    def _get_provider(self):
        ai = self.bot.get_cog("AIChat")
        if not ai:
            return None, None
        # Prioritaskan OpenCode Zen, fallback ke provider lain
        zen = None
        for p in ai._providers:
            if p and p.name == "OpenCode Zen":
                zen = p
                if p.is_available:
                    return ai, p
        # Zen unavailable — coba provider lain
        for p in ai._providers:
            if p and p.is_available and p is not zen:
                return ai, p
        # Zen ada tapi unavailable, return dia anyway (biar error message jelas)
        if zen:
            return ai, zen
        return ai, None

    def _get_next_provider(self, ai_cog, current_provider):
        if not ai_cog or not ai_cog._providers:
            return None
        found = False
        for p in ai_cog._providers:
            if p is current_provider:
                found = True
                continue
            if found and p and p.is_available:
                return p
        # Fallback ke provider pertama yang available
        for p in ai_cog._providers:
            if p and p.is_available:
                return p
        return None

    # ── ReAct Loop ──

    async def _agent_react(
        self,
        guild: discord.Guild,
        user_message: str,
        author: discord.Member,
        memory: list[dict] | None = None,
        channel: discord.TextChannel | None = None,
    ) -> str:
        ai_cog, provider = self._get_provider()
        if not provider:
            return "Tidak ada provider AI yang tersedia saat ini."
        if not ai_cog:
            return "Sistem AI tidak tersedia."

        tools_json = json.dumps(TOOL_DEFINITIONS, indent=2)
        scan_data = self._server_scan_cache.get(guild.id)
        # Kalo RAM kosong, coba dari Firestore
        if not scan_data:
            scan_data = await self._load_scan_firestore(guild.id)
        scan_context = self._build_scan_context(scan_data) if scan_data else ""
        scan_section_sys = (f"Berikut data hasil scan server terbaru:\n{scan_context}\n\n") if scan_context else ""
        system_prompt = (
            f"{TOOL_DESCRIPTION}\n\n"
            f"Berikut adalah tool yang tersedia:\n{tools_json}\n\n"
            f"{DISCORD_PERMISSIONS_KNOWLEDGE}\n\n"
            f"{DISCORD_UI_KNOWLEDGE}\n\n"
            f"Server ini: {guild.name} (ID: {guild.id})\n"
            f"Owner: {guild.owner}\n"
            f"User yang ngobrol: {author.name} (ID: {author.id})"
            f"{' — saat ini berada di voice channel: ' + author.voice.channel.name if author.voice and author.voice.channel else ''}\n"
            f"{scan_section_sys}"
            f"Kamu adalah AI Agent profesional yang paham seluruh struktur Discord server.\n"
            f"Gunakan pengetahuan permission di atas untuk memberikan saran terbaik ke user.\n"
            f"Ikuti aturan dengan ketat."
        )
        # Plan prompt — bikin rencana dulu sebelum eksekusi
        scan_section_plan = (f"Data hasil scan server:\n{scan_context}\n\n") if scan_context else ""
        plan_prompt = f"""{TOOL_DESCRIPTION}

Tool yang tersedia:
{tools_json}

Server: {guild.name}
Owner: {guild.owner}
User: {author.name}{' — di voice: ' + author.voice.channel.name if author.voice and author.voice.channel else ''}
{scan_section_plan}
SEKARANG KAMU HARUS MEMBUAT RENCANA DAHULU SEBELUM EKSEKUSI!

⚠️ LANGKAH WAJIB SEBELUM BIKIN RENCANA:
Sebelum membuat rencana dan sebelum menyentuh apapun, PANGGIL DAHULU:
1. server_info() — lihat statistik server
2. list_roles() — lihat semua role dan posisinya
3. list_channels() — lihat semua channel

Ini penting biar kamu tau kondisi real server, gak asal tebak atau buat sesuatu yang udah ada.

Setelah dapet data server, baru buat rencana:

Format jawaban:
[PLAN]
1. Langkah pertama — <tool yang dipakai>
2. Langkah kedua — <tool yang dipakai>
...
[/PLAN]

SETELAH itu, langsung eksekusi langkah pertama dengan format:
[TOOL_CALL]
Function: ...
Arguments: {{...}}

📌 CONTOH FORMAT TOOL CALL YANG BENAR:

[TOOL_CALL]
Function: create_role
Arguments: {{"name": "Moderator", "color": "#00BFFF", "permissions": {{"kick_members": true, "manage_messages": true}}}}

[TOOL_CALL]
Function: server_info
Arguments: {{}}

[TOOL_CALL]
Function: list_roles
Arguments: {{}}

[TOOL_CALL]
Function: edit_role
Arguments: {{"name": "Moderator", "hoist": true, "mentionable": true}}

[TOOL_CALL]
Function: assign_role
Arguments: {{"member": "@user", "role": "Moderator"}}

[TOOL_CALL]
Function: create_channel
Arguments: {{"name": "📜-rules", "type": "text", "category": "📢 Announcements", "topic": "Baca aturan server"}}

[TOOL_CALL]
Function: create_channel
Arguments: {{"name": "🎮-gaming", "type": "voice", "category": "🔊 Voice Channels"}}

[TOOL_CALL]
Function: batch_create_channels
Arguments: {{"categories": ["📢 Announcements", "🤖 Bots"], "channels": [{{"name": "📜-rules", "type": "text", "category": "📢 Announcements"}}, {{"name": "📢-announcements", "type": "text", "category": "📢 Announcements"}}, {{"name": "💻-bot-commands", "type": "text", "category": "🤖 Bots"}}, {{"name": "🎮-gaming", "type": "voice", "category": "🔊 Voice"}}]}}

[TOOL_CALL]
Function: batch_create_roles
Arguments: {{"roles": [{{"name": "Admin", "color": "#FF0000", "permissions": {{"administrator": true}}}}, {{"name": "Moderator", "color": "#00BFFF", "permissions": {{"kick_members": true, "manage_messages": true}}}}]}}

[TOOL_CALL]
Function: apply_template
Arguments: {{"template": "gaming"}}

JANGAN cuma bikinin plan doang — langsung kerjakan langkah pertama setelah plan!
"""
        # Prompt ringkas untuk step selanjutnya (tapi tool list tetap disertakan)
        tool_names = "\n".join(f"  - {t['name']}: {t['description']}" for t in TOOL_DEFINITIONS)
        scan_section = (scan_context + "\n") if scan_context else ""
        followup_prompt = (
            f"Kamu adalah AI Agent Discord.\n"
            f"Server: {guild.name}\n\n"
            f"Tool yang tersedia:\n{tool_names}\n\n"
            f"{scan_section}"
            f"Lanjutkan eksekusi rencana yang sudah dibuat.\n\n"
            f"Contoh format:\n"
            f"[TOOL_CALL]\nFunction: nama_tool\nArguments: {{\"key\": \"value\"}}\n\n"
            f"Atau:\n"
            f"[TOOL_CALL]\nFunction: nama_tool\nArguments: key=value, key2=value2\n"
        )

        # History untuk dikirim ke provider (tanpa system prompt)
        history: list[dict] = list(memory) if memory else []
        # Auto-save snapshot sebelum mulai (rollback safety)
        try:
            from .agent_tools import _build_snapshot
            snap = await _build_snapshot(guild)
            await asyncio.to_thread(
                lambda: db.collection("agent_snapshots").document(str(guild.id)).set(snap)
            )
        except Exception:
            pass  # snapshot gagal — tetap lanjut
        # Pesan user saat ini
        current_message = user_message
        step_count = 0
        conversation = []
        plan_summary = ""

        while step_count < MAX_AGENT_STEPS:
            step_count += 1

            # Step 1: plan prompt. Step 2+: followup ringkas
            used_prompt = plan_prompt if step_count == 1 else followup_prompt

            response, success = await provider.call(
                user_message=current_message,
                history=history,
                system_prompt=used_prompt,
                temperature=0.3,
            )

            if not success or not response:
                print(f"[AGENT] Provider {provider.name} failed: success={success}, response='{response}'")
                # Coba fallback ke provider lain
                next_provider = self._get_next_provider(ai_cog, provider)
                if next_provider:
                    print(f"[AGENT] Falling back to {next_provider.name}")
                    provider = next_provider
                    response, success = await provider.call(
                        user_message=current_message,
                        history=history,
                        system_prompt=used_prompt,
                        temperature=0.3,
                    )
                if not success or not response:
                    if conversation:
                        final = "\n\n".join(t for _, t in conversation)
                        return f"{final}\n\n---\nMaaf, terjadi error di langkah {step_count}. Coba lagi."
                    return "Maaf, terjadi error saat memproses permintaan. Coba lagi nanti."

            # Ambil plan kalo ada
            plan_match = re.search(r'\[PLAN\](.*?)\[/PLAN\]', response, re.DOTALL)
            if plan_match:
                plan_text = plan_match.group(1).strip()
                # Summarize plan biar gak overload context
                lines = plan_text.split('\n')
                if len(plan_text) > 500 or len(lines) > 5:
                    plan_summary = '\n'.join(lines[:5])
                    if len(lines) > 5:
                        plan_summary += f"\n  ... +{len(lines)-5} langkah lagi"
                else:
                    plan_summary = plan_text
                conversation.append(("PLAN", f"📋 **Rencana:**\n{plan_text}"))

            tool_calls = parse_tool_call(response)
            if not tool_calls:
                conversation.append(("AI", response))
                break

            for tc in tool_calls:
                fn_name = tc.get("function", "unknown")
                conversation.append(("TOOL_CALL", f"Memanggil {fn_name}..."))

                # Validasi dulu sebelum eksekusi
                validation_error = validate_tool_call(tc)
                if validation_error:
                    conversation.append(("TOOL_ERROR", f"❌ {validation_error}"))
                    # Auto-retry: kirim error balik ke AI biar diperbaiki (max 3x)
                    retry_count = 0
                    while retry_count < 3 and validation_error:
                        retry_count += 1
                        retry_msg = (
                            f"❌ Tool call `{fn_name}` gagal validasi:\n{validation_error}\n\n"
                            f"Perbaiki panggilan tool dan kirim ulang dengan format yang benar."
                        )
                        retry_resp, retry_ok = await provider.call(
                            user_message=retry_msg,
                            history=history,
                            system_prompt=used_prompt,
                            temperature=0.3,
                        )
                        if not retry_ok or not retry_resp:
                            break
                        # Parse ulang tool call dari respon retry
                        retry_calls = parse_tool_call(retry_resp)
                        if not retry_calls:
                            # AI gak ngirim tool call — anggep dia nyerah
                            conversation.append(("AI", retry_resp))
                            validation_error = None
                            break
                        # Coba validasi lagi
                        tc = retry_calls[0]
                        fn_name = tc.get("function", fn_name)
                        validation_error = validate_tool_call(tc)
                        if not validation_error:
                            conversation.append(("TOOL_CALL", f"Memanggil {fn_name} (retry #{retry_count})..."))
                    if validation_error:
                        # Abis retry 3x masih error — kirim error ke user
                        conversation.append(("AI", f"❌ Gagal setelah {retry_count}x percobaan: {validation_error}"))
                        continue
                    else:
                        # Retry sukses, lanjut ke eksekusi
                        pass

                result = await execute_tool(guild, tc, self.bot, channel=channel, author=author)
                conversation.append(("TOOL_RESULT", result[:500]))

                # Auto-update scan cache kalo tool memodifikasi server
                if fn_name in self.MUTATING_TOOLS:
                    asyncio.ensure_future(self._update_scan_cache(guild, fn_name))

                # Simpan interaksi ke history untuk konteks berikutnya
                history.append({"role": "user", "content": current_message})
                history.append({"role": "assistant", "content": response})
                # Hasil tool + sisa rencana dikirim sebagai user message berikutnya
                truncated = result[:1500]
                if len(result) > 1500:
                    truncated += "\n\n...(dipotong, total terlalu panjang)"
                plan_status = f"\n\n[SISA RENCANA]\n{plan_summary}\n[/SISA RENCANA]" if plan_summary else ""
                current_message = f"Hasil eksekusi {fn_name}:\n{truncated}{plan_status}\n\nLanjutkan langkah berikutnya dari rencana, atau berikan respon ke user jika sudah selesai."

                await asyncio.sleep(0.3)

        if step_count >= MAX_AGENT_STEPS:
            conversation.append(("AI", "Saya sudah mencapai batas maksimum langkah. Berikut ringkasan apa yang sudah dilakukan."))

        final_text = [t for speaker, t in conversation if speaker in ("AI", "PLAN")]
        return "\n\n".join(final_text) if final_text else response

    # ── Slash Commands ──

    @commands.hybrid_command(
        name="scan",
        description="Scan seluruh server — cache data roles, channels, members, bans untuk AI Agent.",
    )
    async def scan(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("Command ini hanya bisa digunakan di server.", ephemeral=True)
            return

        config = await self._get_agent_config(str(ctx.guild.id))
        if not self._can_use_agent(ctx.author, config):
            await ctx.send("❌ Hanya owner/admin yang bisa melakukan scan.", ephemeral=True)
            return

        await ctx.defer(ephemeral=False)
        msg = await ctx.send("🔍 **Mulai scan server...**")

        try:
            data = await self._scan_server(ctx.guild)
            self._server_scan_cache[ctx.guild.id] = data

            s = data["server"]
            summary = (
                f"✅ **Scan selesai!**\n\n"
                f"📊 **{s['name']}**\n"
                f"👑 Owner: {s['owner_name']}\n"
                f"👥 Member: {s['member_count']}\n"
                f"🎭 Roles: {len(data['roles'])}\n"
                f"📁 Channels: {len(data['channels'])}\n"
                f"📂 Categories: {len(data['categories'])}\n"
                f"🚫 Bans: {len(data['bans'])}\n"
                f"⭐ Boost: Lv.{s['boost_level']} ({s['boost_count']})\n"
                f"😀 Custom Emojis: {len(data['emojis'])}\n"
                f"🏷️ Custom Stickers: {len(data['stickers'])}\n\n"
                f"📋 Data scan sekarang otomatis dipakai oleh AI Agent dan tersimpan permanen.\n"
                f"AI Agent akan auto-update cache setiap ada perubahan dari tool.\n"
                f"Gunakan `/scan` lagi hanya jika ingin refresh manual."
            )
            await msg.edit(content=summary)
        except Exception as e:
            await msg.edit(content=f"❌ **Gagal scan:** {type(e).__name__}: {str(e)[:200]}")

    @commands.hybrid_command(
        name="agent",
        description="AI Agent untuk bantu manage server. Khusus owner/admin.",
    )
    async def agent(self, ctx: commands.Context, *, request: str):
        if not ctx.guild:
            await ctx.send("Command ini hanya bisa digunakan di server.", ephemeral=True)
            return

        config = await self._get_agent_config(str(ctx.guild.id))
        if not config.get("agent_enabled", False):
            await ctx.send(
                "⚠️ **AI Agent belum diaktifkan** di server ini.\n"
                "Minta owner untuk mengaktifkannya lewat dashboard atau `/agent-toggle`.",
                ephemeral=True,
            )
            return

        if not self._can_use_agent(ctx.author, config):
            await ctx.send(
                "❌ **Tidak punya akses.**\n"
                "AI Agent hanya bisa digunakan oleh **Owner Server** "
                + ("dan Admin." if config.get("agent_mode") == "admin" else "."),
                ephemeral=True,
            )
            return

        if ctx.author.id in self._active_sessions:
            await ctx.send(
                "⏳ Kamu masih punya sesi agent yang berjalan. Tunggu sampai selesai.",
                ephemeral=True,
            )
            return

        scan_hint = ""
        if ctx.guild.id not in self._server_scan_cache:
            # Coba Firestore dulu
            fs_scan = await self._load_scan_firestore(ctx.guild.id)
            if not fs_scan:
                scan_hint = "\n💡 *Server belum pernah di-scan. Gunakan `/scan` dulu biar AI paham kondisi server secara menyeluruh.*"

        defer_msg = await ctx.defer(ephemeral=False)

        self._active_sessions.add(ctx.author.id)
        try:
            memory = self._get_memory(ctx.author.id)
            # Kalo RAM kosong, coba load dari Firestore
            if not memory:
                memory = await self._load_memory_firestore(ctx.author.id, ctx.guild.id)
            result = await asyncio.wait_for(
                self._agent_react(ctx.guild, request, ctx.author, memory, ctx.channel),
                timeout=AGENT_TIMEOUT,
            )
            self._agent_channels[ctx.channel.id] = time_module.time()
            self._save_memory(ctx.author.id, ctx.guild.id, request, result[:1000])

            if len(result) > 1900:
                chunks = [result[i:i+1900] for i in range(0, len(result), 1900)]
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await ctx.send(f"🤖 **AI Agent — {ctx.author.display_name}**\n\n{chunk}{scan_hint}")
                    else:
                        await ctx.send(chunk)
            else:
                await ctx.send(f"🤖 **AI Agent — {ctx.author.display_name}**\n\n{result}{scan_hint}")
        except asyncio.TimeoutError:
            await ctx.send("⏰ **Waktu habis.** Agent butuh waktu terlalu lama. Coba dengan permintaan yang lebih sederhana.")
        except Exception as e:
            await ctx.send(f"❌ **Error:** {type(e).__name__}: {str(e)[:500]}")
        finally:
            self._active_sessions.discard(ctx.author.id)

    @commands.hybrid_command(
        name="agent-toggle",
        description="Aktifkan/nonaktifkan AI Agent di server ini. Khusus owner/admin.",
    )
    async def agent_toggle(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("Command ini hanya bisa digunakan di server.", ephemeral=True)
            return

        if not ctx.author.guild_permissions.administrator and ctx.author != ctx.guild.owner:
            await ctx.send("❌ Hanya owner dan admin yang bisa menggunakan ini.", ephemeral=True)
            return

        config = await self._get_agent_config(str(ctx.guild.id))
        config["agent_enabled"] = not config.get("agent_enabled", False)
        await self._save_agent_config(str(ctx.guild.id), config)

        status = "✅ **Diaktifkan**" if config["agent_enabled"] else "❌ **Dinonaktifkan**"
        mode = f"Mode: {'Owner + Admin' if config.get('agent_mode') == 'admin' else 'Owner Only'}"
        await ctx.send(f"{status}\n{mode}\nGunakan `/agent-mode` untuk mengubah siapa yang bisa akses.", ephemeral=True)

    @commands.hybrid_command(
        name="agent-mode",
        description="Ubah mode akses AI Agent: owner-only atau admin+owner.",
    )
    async def agent_mode(self, ctx: commands.Context, mode: str = "admin"):
        if not ctx.guild:
            await ctx.send("Command ini hanya bisa digunakan di server.", ephemeral=True)
            return

        if ctx.author != ctx.guild.owner:
            await ctx.send("❌ Hanya **Owner Server** yang bisa mengubah mode akses ini.", ephemeral=True)
            return

        mode = mode.lower()
        if mode not in ("owner", "admin"):
            await ctx.send("Mode harus `owner` atau `admin`.", ephemeral=True)
            return

        config = await self._get_agent_config(str(ctx.guild.id))
        config["agent_mode"] = mode
        await self._save_agent_config(str(ctx.guild.id), config)

        desc = "Hanya Owner Server" if mode == "owner" else "Owner + Admin"
        await ctx.send(f"✅ Mode akses AI Agent diubah ke: **{desc}**", ephemeral=True)

    @commands.hybrid_command(
        name="agent-status",
        description="Cek status AI Agent di server ini.",
    )
    async def agent_status(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("Command ini hanya bisa digunakan di server.", ephemeral=True)
            return

        config = await self._get_agent_config(str(ctx.guild.id))
        enabled = config.get("agent_enabled", False)
        mode = config.get("agent_mode", "admin")
        can_use = self._can_use_agent(ctx.author, config)

        embed = discord.Embed(
            title="🤖 AI Agent Status",
            color=discord.Color.green() if enabled else discord.Color.red(),
        )
        embed.add_field(name="Status", value="✅ Aktif" if enabled else "❌ Nonaktif", inline=False)
        embed.add_field(name="Mode Akses", value="Owner + Admin" if mode == "admin" else "Owner Only", inline=False)
        embed.add_field(name="Akses Kamu", value="✅ Bisa menggunakan" if can_use else "❌ Tidak bisa", inline=False)

        ai = self.bot.get_cog("AIChat")
        if ai:
            provider_names = [p.name for p in ai._providers if p and p.is_available]
            embed.add_field(name="Provider Tersedia", value=", ".join(provider_names) or "Tidak ada", inline=False)

        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChatAgent(bot))
