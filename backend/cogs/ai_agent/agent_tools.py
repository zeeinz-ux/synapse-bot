from __future__ import annotations

import discord

DISCORD_PERMISSIONS_KNOWLEDGE = """
## Discord Permission System — Panduan Lengkap

### General Server Permissions
- View Channels — Melihat channel (termasuk private jika diizinkan)
- Manage Channels — Buat/edit/hapus channel
- Manage Roles — Buat/edit/hapus role (hanya role di bawah role tertinggi)
- Create Expressions — Tambah emoji/sticker/sound kustom
- Manage Expressions — Edit/hapus emoji/sticker/sound kustom
- View Audit Log — Lihat log perubahan di server
- View Server Insights — Lihat data pertumbuhan server
- Manage Webhooks — Buat/edit/hapus webhook
- Manage Server — Ubah nama server, region, invite, tambah app, atur AutoMod

### Membership Permissions
- Create Invite — Undang orang baru
- Change Nickname — Ubah nickname sendiri
- Manage Nicknames — Ubah nickname orang lain
- Kick Members — Kick anggota
- Ban Members — Ban permanen + hapus history chat
- Timeout Members — Nonaktifkan sementara (gak bisa chat/react/voice)

### Text Channel Permissions
- Send Messages — Kirim pesan & buat post di forum
- Send Messages in Threads — Kirim pesan di thread
- Create Public Threads — Buat thread publik
- Create Private Threads — Buat thread privat
- Embed Links — Tampilkan embed dari link
- Attach Files — Upload file/media
- Add Reactions — Tambah reaksi emoji
- Use External Emoji — Pakai emoji dari server lain (Nitro)
- Use External Stickers — Pakai sticker dari server lain (Nitro)
- Mention @everyone/@here/All Roles — Mention massal
- Manage Messages — Hapus/hide embed dari pesan
- Pin Messages — Pin/unpin pesan
- Read Message History — Baca pesan lama
- Send TTS Messages — Kirim pesan text-to-speech
- Send Voice Messages — Kirim voice message
- Create Polls — Buat polling
- Bypass Slowmode — Kirim pesan tanpa kena slowmode
- Manage Threads — Rename/delete/close thread

### Voice Channel Permissions
- Connect — Join voice channel
- Speak — Bicara di voice
- Video — Share video/screen/stream
- Use Soundboard — Kirim sound dari soundboard server
- Use External Sounds — Pakai sound dari server lain (Nitro)
- Use Voice Activity — Bicara tanpa push-to-talk
- Priority Speaker — Lebih didengar di voice
- Mute Members — Mute orang lain
- Deafen Members — Deaf orang lain
- Move Members — Pindahin atau disconnect orang dari voice
- Set Voice Channel Status — Edit status voice channel

### Apps Permissions
- Use Application Commands — Pakai slash command & context menu
- Use Activities — Pakai Activities (games, dll)
- Use External Apps — App dari member bisa posting

### Stage Channel Permissions
- Request to Speak — Minta bicara di Stage

### Events Permissions
- Create Events — Buat event
- Manage Events — Edit & cancel event

### Advanced
- Administrator — Semua permission + bypass semua batasan channel (DANGEROUS)

### Best Practices:
1. @everyone: minimal permissions (biasanya cuma View Channels, Send Messages, Read History)
2. Moderator role: Manage Messages, Kick, Ban, Timeout, Mute/Deafen Members
3. Admin role: Manage Channels, Manage Roles, Manage Server (tanpa Administrator biar aman)
4. JANGAN pernah kasih Administrator ke sembarang orang
5. Gunakan channel-specific overwrites untuk kontrol lebih detail
"""

TOOL_DEFINITIONS = [
    {
        "name": "server_info",
        "description": "Ambil informasi dasar tentang server (nama, ID, member count, owner, boost level, dll). Gunakan ketika user bertanya tentang kondisi server.",
        "parameters": {},
    },
    {
        "name": "list_channels",
        "description": "Daftar semua channel di server (nama, ID, tipe, kategori). Gunakan untuk melihat channel apa saja yang ada.",
        "parameters": {},
    },
    {
        "name": "list_roles",
        "description": "Daftar semua role di server (nama, ID, warna, jumlah member). Gunakan untuk melihat role apa saja yang ada.",
        "parameters": {},
    },
    {
        "name": "create_channel",
        "description": "Buat channel baru (text atau voice).",
        "parameters": {
            "name": "string — nama channel (huruf kecil, tanpa spasi, pakai dash atau emoji)",
            "type": "string — 'text' atau 'voice' (default: 'text')",
            "category": "string — nama kategori (optional). Jika tidak ada, kategori akan dibuat otomatis.",
            "topic": "string — deskripsi/topic channel (optional, hanya untuk text channel)",
        },
    },
    {
        "name": "delete_channel",
        "description": "Hapus channel berdasarkan nama. BERBAHAYA — minta konfirmasi user dulu sebelum eksekusi!",
        "parameters": {
            "name": "string — nama channel yang akan dihapus",
        },
    },
    {
        "name": "rename_channel",
        "description": "Ubah nama channel.",
        "parameters": {
            "old_name": "string — nama channel saat ini",
            "new_name": "string — nama baru",
        },
    },
    {
        "name": "create_role",
        "description": "Buat role baru dengan nama tertentu.",
        "parameters": {
            "name": "string — nama role",
            "color": "string — warna dalam hex (optional, contoh: '#FF0000'). Default: tidak ada warna.",
        },
    },
    {
        "name": "delete_role",
        "description": "Hapus role berdasarkan nama. BERBAHAYA — minta konfirmasi user dulu sebelum eksekusi!",
        "parameters": {
            "name": "string — nama role yang akan dihapus",
        },
    },
    {
        "name": "assign_role",
        "description": "Berikan role ke member. Cari member berdasarkan nama atau mention.",
        "parameters": {
            "member": "string — nama atau mention member",
            "role": "string — nama role yang akan diberikan",
        },
    },
    {
        "name": "remove_role",
        "description": "Hapus role dari member.",
        "parameters": {
            "member": "string — nama atau mention member",
            "role": "string — nama role yang akan dihapus",
        },
    },
    {
        "name": "list_members",
        "description": "Lihat daftar member di server. Bisa filter berdasarkan role.",
        "parameters": {
            "role": "string — nama role (optional). Jika dikosongkan, tampilkan semua member (max 50).",
        },
    },
    {
        "name": "ban_member",
        "description": "Ban member dari server. BERBAHAYA — minta konfirmasi user dulu!",
        "parameters": {
            "member": "string — nama atau ID member",
            "reason": "string — alasan ban (optional)",
        },
    },
    {
        "name": "unban_member",
        "description": "Unban member yang sudah di-ban sebelumnya.",
        "parameters": {
            "user_id": "string — ID user yang akan di-unban",
            "reason": "string — alasan (optional)",
        },
    },
    {
        "name": "kick_member",
        "description": "Kick member dari server. BERBAHAYA — minta konfirmasi user dulu!",
        "parameters": {
            "member": "string — nama atau ID member",
            "reason": "string — alasan kick (optional)",
        },
    },
    {
        "name": "timeout_member",
        "description": "Timeout member (disable sementara).",
        "parameters": {
            "member": "string — nama atau ID member",
            "duration": "string — durasi (contoh: '10m', '1h', '1d'). Default: '1h'",
            "reason": "string — alasan (optional)",
        },
    },
    {
        "name": "edit_channel_permissions",
        "description": "Ubah permission channel untuk role tertentu. Beri permission name dan nilai true/false.",
        "parameters": {
            "channel": "string — nama channel",
            "role": "string — nama role (atau '@everyone')",
            "permissions": "object — permission Discord beserta nilai true/false. Contoh: {\"send_messages\": false, \"read_messages\": true}",
        },
    },
    {
        "name": "list_bans",
        "description": "Lihat daftar member yang di-ban di server ini.",
        "parameters": {},
    },
]


TOOL_DESCRIPTION = """
Kamu adalah AI Agent untuk server Discord. Kamu bisa membantu owner/admin server mengelola server mereka menggunakan tool-tool di bawah ini.

ATURAN PENTING:
1. Jangan pernah setuju begitu saja. Beri rekomendasi, saran, atau koreksi jika menurutmu ada yang kurang tepat.
2. Untuk aksi BERBAHAYA (delete channel, delete role, ban, kick), ALWAYS minta konfirmasi user dulu.
3. Jika user minta sesuatu yang tidak jelas, tanyakan detailnya.
4. Jika tool gagal, jelaskan kenapa dan sarankan alternatif.
5. Gunakan server_info/list_channels/list_roles dulu untuk memahami kondisi server sebelum bertindak.
6. Format panggilan tool:
   [TOOL_CALL]
   Function: nama_function
   Arguments: {"key": "value"}

7. Setelah dapat hasil tool, analisis hasilnya lalu lanjutkan.
8. Jika sudah selesai semua, berikan ringkasan apa yang sudah dilakukan.
"""


import re as _re

AGENT_TRIGGER_KEYWORDS = [
    "bikin channel", "buat channel", "tambah channel", "hapus channel",
    "bikin role", "buat role", "tambah role", "hapus role",
    "kasih role", "assign role", "cabut role", "remove role",
    "ban", "kick", "timeout", "mute",
    "unban",
    "ganti nama channel", "rename channel",
    "setting server", "atur server",
    "server info", "info server", "statistik server",
    "daftar channel", "list channel", "channel apa aja",
    "daftar role", "list role", "role apa aja",
    "daftar member", "list member",
]


def is_agent_request(text: str) -> bool:
    text_lower = text.lower()
    # Exact keyword match
    for kw in AGENT_TRIGGER_KEYWORDS:
        if kw in text_lower:
            return True
    # Pattern-based detection
    patterns = [
        r"tolong\s+\w+\s+(channel|role|server|kategori)",
        r"bantu\s+\w+\s+(channel|role|server|kategori)",
        r"(channel|role|kategori)\s+(baru|new)",
        r"hapus\s+\w+\s+(channel|role|kategori)",
        r"\w+\s+(di-?ban|di-?kick|di-?mute)",
        r"buatin?\s+(channel|role|kategori)",
        r"tambahin?\s+(channel|role)",
    ]
    for p in patterns:
        if _re.search(p, text_lower):
            return True
    # Loose detection: both "hapus" and "channel" exist anywhere in text
    words = set(_re.findall(r'\w+', text_lower))
    loose_pairs = [
        ("hapus", "channel"), ("hapus", "role"), ("hapus", "kategori"),
        ("buat", "channel"), ("buat", "role"), ("buat", "kategori"),
        ("tambah", "role"), ("tambah", "channel"),
        ("ban", "member"), ("kick", "member"),
    ]
    for a, b in loose_pairs:
        if a in words and b in words:
            return True
    return False


def parse_tool_call(text: str) -> list[dict] | None:
    import re, json
    pattern = r'\[TOOL_CALL\]\s*Function:\s*(\w+)\s*Arguments:\s*(\{.*?\})'
    matches = re.findall(pattern, text, re.DOTALL)
    if not matches:
        return None
    calls = []
    for fn_name, args_str in matches:
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            args = {}
        calls.append({"function": fn_name, "arguments": args})
    return calls


def find_channel(guild: discord.Guild, name: str) -> discord.abc.GuildChannel | None:
    return discord.utils.get(guild.channels, name=name)


def find_role(guild: discord.Guild, name: str) -> discord.Role | None:
    role = discord.utils.get(guild.roles, name=name)
    if not role:
        role = discord.utils.get(guild.roles, name=name.lower())
    return role


def find_member(guild: discord.Guild, query: str) -> discord.Member | None:
    if query.startswith("<@") and query.endswith(">"):
        uid = query.strip("<@!>")
        return guild.get_member(int(uid))
    member = guild.get_member_named(query)
    if not member:
        member = discord.utils.get(guild.members, name=query)
    if not member:
        for m in guild.members:
            if query.lower() in m.display_name.lower():
                return m
    return member


async def execute_tool(guild: discord.Guild, tool_call: dict, bot) -> str:
    fn = tool_call.get("function", "")
    args = tool_call.get("arguments", {})
    try:
        if fn == "server_info":
            return await _server_info(guild)
        elif fn == "list_channels":
            return await _list_channels(guild)
        elif fn == "list_roles":
            return await _list_roles(guild)
        elif fn == "create_channel":
            return await _create_channel(guild, args)
        elif fn == "delete_channel":
            return await _delete_channel(guild, args)
        elif fn == "rename_channel":
            return await _rename_channel(guild, args)
        elif fn == "create_role":
            return await _create_role(guild, args)
        elif fn == "delete_role":
            return await _delete_role(guild, args)
        elif fn == "assign_role":
            return await _assign_role(guild, args)
        elif fn == "remove_role":
            return await _remove_role(guild, args)
        elif fn == "list_members":
            return await _list_members(guild, args)
        elif fn == "ban_member":
            return await _ban_member(guild, args)
        elif fn == "unban_member":
            return await _unban_member(guild, args)
        elif fn == "kick_member":
            return await _kick_member(guild, args)
        elif fn == "timeout_member":
            return await _timeout_member(guild, args)
        elif fn == "edit_channel_permissions":
            return await _edit_channel_permissions(guild, args)
        elif fn == "list_bans":
            return await _list_bans(guild)
        else:
            return f"[TOOL_RESULT]\nFunction: {fn}\nResult: {{\"success\": false, \"error\": \"Tool '{fn}' tidak dikenal\"}}"
    except discord.Forbidden:
        return f'[TOOL_RESULT]\nFunction: {fn}\nResult: {{"success": false, "error": "Bot tidak punya izin untuk melakukan ini. Pastikan bot punya role dengan permission yang cukup."}}'
    except Exception as e:
        return f'[TOOL_RESULT]\nFunction: {fn}\nResult: {{"success": false, "error": "{type(e).__name__}: {str(e)}"}}'


async def _server_info(guild: discord.Guild) -> str:
    owner = guild.owner
    boosts = guild.premium_subscription_count
    boost_tier = guild.premium_tier
    channels = len(guild.channels)
    roles = len(guild.roles)
    members = guild.member_count
    bots = sum(1 for m in guild.members if m.bot)
    humans = members - bots
    created = guild.created_at.strftime("%d %B %Y")
    info = {
        "name": guild.name,
        "id": guild.id,
        "owner": owner.name if owner else "Unknown",
        "member_count": members,
        "human_count": humans,
        "bot_count": bots,
        "channel_count": channels,
        "role_count": roles,
        "boost_level": boost_tier,
        "boost_count": boosts,
        "created_at": created,
    }
    return f'[TOOL_RESULT]\nFunction: server_info\nResult: {info}'


async def _list_channels(guild: discord.Guild) -> str:
    cats = {}
    for ch in guild.channels:
        cat_name = ch.category.name if ch.category else "(No Category)"
        if cat_name not in cats:
            cats[cat_name] = []
        ch_type = "📝" if isinstance(ch, discord.TextChannel) else "🔊" if isinstance(ch, discord.VoiceChannel) else "📁" if isinstance(ch, discord.CategoryChannel) else "❓"
        cats[cat_name].append(f"{ch_type} {ch.name} (ID: {ch.id})")
    result = {}
    for cat, channels in cats.items():
        result[cat] = channels
    return f'[TOOL_RESULT]\nFunction: list_channels\nResult: {result}'


async def _list_roles(guild: discord.Guild) -> str:
    roles = []
    for role in reversed(guild.roles):
        if role.name == "@everyone":
            continue
        roles.append({
            "name": role.name,
            "id": role.id,
            "color": str(role.color) if role.color.value else "None",
            "member_count": len(role.members),
            "position": role.position,
        })
    return f'[TOOL_RESULT]\nFunction: list_roles\nResult: {roles}'


async def _create_channel(guild: discord.Guild, args: dict) -> str:
    name = args.get("name", "").strip().lower().replace(" ", "-")
    if not name:
        return '{"success": false, "error": "Nama channel wajib diisi"}'
    ch_type = args.get("type", "text")
    category_name = args.get("category", "").strip()
    topic = args.get("topic", "")

    category = None
    if category_name:
        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            category = await guild.create_category(category_name, reason="AI Agent: channel setup")

    if ch_type == "voice":
        channel = await guild.create_voice_channel(name, category=category, reason="AI Agent: create channel")
    else:
        channel = await guild.create_text_channel(name, category=category, topic=topic, reason="AI Agent: create channel")

    return f'{{"success": true, "channel_id": "{channel.id}", "channel_name": "{channel.name}", "type": "{ch_type}"}}'


async def _delete_channel(guild: discord.Guild, args: dict) -> str:
    name = args.get("name", "").strip()
    if not name:
        return '{"success": false, "error": "Nama channel wajib diisi"}'
    channel = find_channel(guild, name)
    if not channel:
        return f'{{"success": false, "error": "Channel dengan nama \\"{name}\\" tidak ditemukan"}}'
    ch_name = channel.name
    await channel.delete(reason="AI Agent: delete channel")
    return f'{{"success": true, "deleted_channel": "{ch_name}"}}'


async def _rename_channel(guild: discord.Guild, args: dict) -> str:
    old = args.get("old_name", "").strip()
    new = args.get("new_name", "").strip()
    if not old or not new:
        return '{"success": false, "error": "old_name dan new_name wajib diisi"}'
    channel = find_channel(guild, old)
    if not channel:
        return f'{{"success": false, "error": "Channel \\"{old}\\" tidak ditemukan"}}'
    await channel.edit(name=new, reason="AI Agent: rename channel")
    return f'{{"success": true, "old_name": "{old}", "new_name": "{new}"}}'


async def _create_role(guild: discord.Guild, args: dict) -> str:
    name = args.get("name", "").strip()
    if not name:
        return '{"success": false, "error": "Nama role wajib diisi"}'
    color_hex = args.get("color", "")
    color = discord.Color.default()
    if color_hex:
        try:
            color = discord.Color(int(color_hex.lstrip("#"), 16))
        except ValueError:
            pass
    role = await guild.create_role(name=name, color=color, reason="AI Agent: create role")
    return f'{{"success": true, "role_id": "{role.id}", "role_name": "{role.name}"}}'


async def _delete_role(guild: discord.Guild, args: dict) -> str:
    name = args.get("name", "").strip()
    if not name:
        return '{"success": false, "error": "Nama role wajib diisi"}'
    role = find_role(guild, name)
    if not role:
        return f'{{"success": false, "error": "Role \\"{name}\\" tidak ditemukan"}}'
    role_name = role.name
    await role.delete(reason="AI Agent: delete role")
    return f'{{"success": true, "deleted_role": "{role_name}"}}'


async def _assign_role(guild: discord.Guild, args: dict) -> str:
    member_query = args.get("member", "").strip()
    role_name = args.get("role", "").strip()
    if not member_query or not role_name:
        return '{"success": false, "error": "member dan role wajib diisi"}'
    member = find_member(guild, member_query)
    if not member:
        return f'{{"success": false, "error": "Member \\"{member_query}\\" tidak ditemukan"}}'
    role = find_role(guild, role_name)
    if not role:
        return f'{{"success": false, "error": "Role \\"{role_name}\\" tidak ditemukan"}}'
    await member.add_roles(role, reason="AI Agent: assign role")
    return f'{{"success": true, "member": "{member.name}", "role": "{role.name}"}}'


async def _remove_role(guild: discord.Guild, args: dict) -> str:
    member_query = args.get("member", "").strip()
    role_name = args.get("role", "").strip()
    if not member_query or not role_name:
        return '{"success": false, "error": "member dan role wajib diisi"}'
    member = find_member(guild, member_query)
    if not member:
        return f'{{"success": false, "error": "Member \\"{member_query}\\" tidak ditemukan"}}'
    role = find_role(guild, role_name)
    if not role:
        return f'{{"success": false, "error": "Role \\"{role_name}\\" tidak ditemukan"}}'
    await member.remove_roles(role, reason="AI Agent: remove role")
    return f'{{"success": true, "member": "{member.name}", "role": "{role.name}"}}'


async def _list_members(guild: discord.Guild, args: dict) -> str:
    role_name = args.get("role", "").strip()
    if role_name:
        role = find_role(guild, role_name)
        if not role:
            return f'{{"success": false, "error": "Role \\"{role_name}\\" tidak ditemukan"}}'
        members = role.members
    else:
        members = guild.members
    result = []
    for m in members[:50]:
        roles_preview = [r.name for r in m.roles if r.name != "@everyone"][:3]
        result.append({
            "name": m.name,
            "display_name": m.display_name,
            "id": m.id,
            "bot": m.bot,
            "joined_at": m.joined_at.strftime("%Y-%m-%d") if m.joined_at else "unknown",
            "roles": roles_preview,
        })
    total = len(members)
    return f'{{"success": true, "total": {total}, "shown": {len(result)}, "members": {result}}}'


async def _ban_member(guild: discord.Guild, args: dict) -> str:
    member_query = args.get("member", "").strip()
    reason = args.get("reason", "AI Agent: banned by admin request")
    if not member_query:
        return '{"success": false, "error": "Nama/ID member wajib diisi"}'
    member = find_member(guild, member_query)
    if not member:
        return f'{{"success": false, "error": "Member \\"{member_query}\\" tidak ditemukan di server"}}'
    await member.ban(reason=reason)
    return f'{{"success": true, "banned": "{member.name}", "id": "{member.id}"}}'


async def _unban_member(guild: discord.Guild, args: dict) -> str:
    user_id = args.get("user_id", "").strip()
    reason = args.get("reason", "AI Agent: unbanned by admin request")
    if not user_id:
        return '{"success": false, "error": "user_id wajib diisi"}'
    try:
        user = await guild.fetch_ban(discord.Object(id=int(user_id)))
        await guild.unban(user.user, reason=reason)
        return f'{{"success": true, "unbanned": "{user.user.name}", "id": "{user_id}"}}'
    except discord.NotFound:
        return f'{{"success": false, "error": "User dengan ID {user_id} tidak ada di ban list"}}'


async def _kick_member(guild: discord.Guild, args: dict) -> str:
    member_query = args.get("member", "").strip()
    reason = args.get("reason", "AI Agent: kicked by admin request")
    if not member_query:
        return '{"success": false, "error": "Nama/ID member wajib diisi"}'
    member = find_member(guild, member_query)
    if not member:
        return f'{{"success": false, "error": "Member \\"{member_query}\\" tidak ditemukan di server"}}'
    await member.kick(reason=reason)
    return f'{{"success": true, "kicked": "{member.name}", "id": "{member.id}"}}'


async def _timeout_member(guild: discord.Guild, args: dict) -> str:
    member_query = args.get("member", "").strip()
    duration_str = args.get("duration", "1h")
    reason = args.get("reason", "AI Agent: timeout by admin request")
    if not member_query:
        return '{"success": false, "error": "Nama/ID member wajib diisi"}'
    import re
    match = re.match(r"(\d+)\s*(m|h|d|s)", duration_str)
    if not match:
        return f'{{"success": false, "error": "Format durasi tidak valid. Gunakan format seperti 10m, 1h, 1d"}}'
    value = int(match.group(1))
    unit = match.group(2)
    import datetime
    if unit == "m":
        delta = datetime.timedelta(minutes=value)
    elif unit == "h":
        delta = datetime.timedelta(hours=value)
    elif unit == "d":
        delta = datetime.timedelta(days=value)
    else:
        delta = datetime.timedelta(seconds=value)
    member = find_member(guild, member_query)
    if not member:
        return f'{{"success": false, "error": "Member \\"{member_query}\\" tidak ditemukan di server"}}'
    await member.timeout(delta, reason=reason)
    return f'{{"success": true, "timeout": "{member.name}", "duration": "{duration_str}", "until": "{datetime.datetime.now() + delta}"}}'


async def _edit_channel_permissions(guild: discord.Guild, args: dict) -> str:
    channel_name = args.get("channel", "").strip()
    role_name = args.get("role", "").strip()
    perms_dict = args.get("permissions", {})
    if not channel_name:
        return '{"success": false, "error": "Nama channel wajib diisi"}'
    if not role_name:
        return '{"success": false, "error": "Nama role wajib diisi"}'
    channel = find_channel(guild, channel_name)
    if not channel:
        return f'{{"success": false, "error": "Channel \\"{channel_name}\\" tidak ditemukan"}}'
    role = None
    if role_name == "@everyone":
        role = guild.default_role
    else:
        role = find_role(guild, role_name)
    if not role:
        return f'{{"success": false, "error": "Role \\"{role_name}\\" tidak ditemukan"}}'
    perm_kwargs = {}
    valid_perms = [
        "view_channel", "manage_channels", "manage_roles",
        "create_instant_invite", "change_nickname", "manage_nicknames",
        "kick_members", "ban_members", "timeout_members",
        "send_messages", "send_messages_in_threads", "create_public_threads",
        "create_private_threads", "embed_links", "attach_files",
        "add_reactions", "use_external_emoji", "use_external_stickers",
        "mention_everyone", "manage_messages", "manage_threads",
        "read_message_history", "send_tts_messages", "send_voice_messages",
        "create_polls", "connect", "speak", "stream", "use_soundboard",
        "use_voice_activity", "priority_speaker", "mute_members",
        "deafen_members", "move_members", "set_voice_channel_status",
        "request_to_speak", "use_application_commands", "use_activities",
    ]
    for key, value in perms_dict.items():
        normalized_key = key.lower().replace(" ", "_").replace("-", "_")
        if normalized_key in valid_perms:
            perm_kwargs[normalized_key] = bool(value)
    if not perm_kwargs:
        return '{"success": false, "error": "Tidak ada permission valid yang diberikan. Lihat DISCORD_PERMISSIONS_KNOWLEDGE untuk daftar permission."}'
    await channel.set_permissions(role, **perm_kwargs, reason="AI Agent: edit channel permissions")
    return f'{{"success": true, "channel": "{channel_name}", "role": "{role_name}", "permissions_set": {list(perm_kwargs.keys())}}}'


async def _list_bans(guild: discord.Guild) -> str:
    try:
        bans = [b async for b in guild.bans()]
        result = []
        for ban_entry in bans[:50]:
            result.append({
                "user": ban_entry.user.name,
                "id": ban_entry.user.id,
                "reason": ban_entry.reason or "Tidak ada alasan",
            })
        return f'{{"success": true, "total_bans": {len(bans)}, "bans": {result}}}'
    except discord.Forbidden:
        return '{"success": false, "error": "Bot tidak punya izin View Audit Log untuk melihat ban list"}'
