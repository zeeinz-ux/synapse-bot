from __future__ import annotations

import asyncio
import datetime
import json
import time

import discord

try:
    from ..database.firebase_setup import db
    _HAS_FS = True
except Exception:
    db = None
    _HAS_FS = False

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

LOFI_DEFAULT_URL = "https://play.streamafrica.net/lofiradio"

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
            "type": "string — 'text', 'voice', atau 'category' (optional). Default cari semua tipe.",
        },
    },
    {
        "name": "rename_channel",
        "description": "Ubah nama DAN/ATAU topic/deskripsi channel text. Gunakan ini untuk edit topic channel.",
        "parameters": {
            "old_name": "string — nama channel/kategori saat ini",
            "new_name": "string — nama baru (optional, kosongkan jika cuma mau ganti topic)",
            "topic": "string — topic/deskripsi baru channel (optional, hanya untuk text channel). Kosongkan jika cuma mau ganti nama.",
            "type": "string — 'text', 'voice', atau 'category' (optional). Default cari semua tipe.",
        },
    },
    {
        "name": "create_role",
        "description": "Buat role baru dengan nama dan permission tertentu.",
        "parameters": {
            "name": "string — nama role",
            "color": "string — warna dalam hex (optional, contoh: '#FF0000'). Default: tidak ada warna.",
            "permissions": "object — permission apa yang ON. Contoh: {\"administrator\": false, \"kick_members\": true, \"manage_messages\": true}. Lihat DISCORD_PERMISSIONS_KNOWLEDGE untuk daftar permission. (optional)",
        },
    },
    {
        "name": "edit_role",
        "description": "Ubah role yang sudah ada: nama, warna, permission, posisi, hoist, atau mentionable. Cari role berdasarkan nama.",
        "parameters": {
            "name": "string — nama role yang akan diubah",
            "new_name": "string — nama baru (optional)",
            "color": "string — warna hex baru (optional, contoh: '#FFD700')",
            "permissions": "object — permission yang ingin diubah. Contoh: {\"administrator\": true, \"kick_members\": false}. Hanya permission yang disebut yang diubah. (optional)",
            "position": "integer — posisi role (0 = paling bawah). Semakin besar angka, semakin atas posisinya. (optional)",
            "hoist": "boolean — true = tampilkan member role ini terpisah di sidebar (Display role members separately). false = jangan. (optional)",
            "mentionable": "boolean — true = semua orang bisa @mention role ini. false = cuma yang punya permission. (optional)",
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
    {
        "name": "batch_create_channels",
        "description": "Bikin banyak channel + kategori sekaligus dalam SATU panggilan. Jauh lebih cepat & hemat token daripada create_channel satu-satu. Kirim array channel, tool akan buat kategori otomatis kalo belum ada.",
        "parameters": {
            "channels": "array of objects — WAJIB. Daftar channel yang mau dibuat. Format: [{\"name\": \"nama-channel\", \"type\": \"text\"|\"voice\", \"category\": \"Nama Kategori\" (optional, auto-create), \"topic\": \"deskripsi\" (optional)}]",
            "categories": "array of strings — (optional) Daftar kategori yang mau dibuat duluan. Contoh: [\"📢 Announcements\", \"🤖 Bots\"]",
        },
    },
    {
        "name": "batch_create_roles",
        "description": "Bikin banyak role sekaligus dalam SATU panggilan. Lebih cepat daripada create_role satu-satu.",
        "parameters": {
            "roles": "array of objects — WAJIB. Daftar role yang mau dibuat. Format: [{\"name\": \"nama-role\", \"color\": \"#HEX\" (optional), \"permissions\": {...} (optional)}]",
        },
    },
    {
        "name": "apply_template",
        "description": "Terapkan template server lengkap (kategori, channel, role) untuk berbagai tema. Bikin semua struktur server langsung jadi dalam 1 panggilan — jauh lebih cepat daripada make channel/role satu-satu.",
        "parameters": {
            "template": "string — nama template. Pilihan: 'gaming' (server gaming dengan voice), 'study' (server belajar/akademik), 'community' (server komunitas umum).",
        },
    },
    {
        "name": "edit_server",
        "description": "Ubah pengaturan server: nama, ikon, deskripsi, verification level, AFK channel, system channel, notifikasi. Hanya isi parameter yang mau diubah.",
        "parameters": {
            "name": "string — nama baru server (optional). Contoh: 'Server Keren'",
            "description": "string — deskripsi server (optional). Contoh: 'Server Discord komunitas kami'",
            "verification_level": "string — level verifikasi: 'none', 'low', 'medium', 'high', 'very_high' (optional)",
            "afk_channel": "string — nama voice channel untuk AFK (optional). Contoh: 'AFK'",
            "afk_timeout": "integer — detik timeout AFK: 60, 300, 900, 1800, 3600 (optional)",
            "system_channel": "string — nama channel untuk welcome messages & tips (optional)",
        },
    },
    {
        "name": "save_snapshot",
        "description": "Simpan snapshot kondisi server saat ini (roles, channels, categories, permissions). Berguna sebelum melakukan perubahan besar agar bisa di-rollback.",
        "parameters": {},
    },
    {
        "name": "rollback",
        "description": "Kembalikan server ke kondisi snapshot terakhir. Cocok kalo perubahan yang dilakukan AI Agent sebelumnya salah atau gak sesuai. Bisa restore: nama role, warna, permission, posisi, nama channel, kategori, topic.",
        "parameters": {
            "confirm": "boolean — WAJIB true. Konfirmasi bahwa kamu serius mau rollback.",
        },
    },
    {
        "name": "schedule_task",
        "description": "Jadwalkan tugas otomatis di server. Bot akan jalanin tugas secara background sesuai jadwal. Berguna untuk auto-role, pengumuman rutin, dll.",
        "parameters": {
            "name": "string — nama unik tugas (untuk referensi & management)",
            "action": "string — jenis aksi: 'assign_role' (kasih role ke member), 'send_message' (kirim pesan ke channel), 'remove_role' (cabut role dari member)",
            "params": "object — parameter aksi. assign_role/remove_role: {\"role\": \"nama-role\", \"member\": \"nama-member\"}. send_message: {\"channel\": \"nama-channel\", \"message\": \"teks pesan\"}",
            "schedule": "string — jadwal eksekusi. Format: 'interval:Xh' (tiap X jam), 'interval:Xm' (tiap X menit). Contoh: 'interval:24h' = tiap 24 jam, 'interval:30m' = tiap 30 menit",
            "enabled": "boolean — (optional) true = aktif, false = nonaktif. Default: true",
        },
    },
    {
        "name": "send_message",
        "description": "Kirim pesan ke channel text tertentu. Pesan bisa berupa teks biasa atau embed sederhana.",
        "parameters": {
            "channel": "string — nama channel tujuan",
            "message": "string — isi pesan yang akan dikirim (mendukung markdown Discord)",
        },
    },
    {
        "name": "add_reaction",
        "description": "Tambahkan reaksi emoji ke pesan tertentu di channel.",
        "parameters": {
            "channel": "string — nama channel tempat pesan berada",
            "message_id": "string — ID pesan yang akan direaksi",
            "emoji": "string — emoji yang akan ditambahkan (contoh: '👍', '🎉', '😄')",
        },
    },
    {
        "name": "join_voice",
        "description": "Bergabung ke voice channel dan mulai memutar aliran LoFi/lagu. Kalau parameter 'channel' dikosongkan, bot akan otomatis join ke voice channel tempat user berada. Gunakan parameter 'stream' untuk URL kustom, atau kosongkan untuk memutar LoFi default.",
        "parameters": {
            "channel": "string — (opsional) nama voice channel yang akan dimasuki. Kosongkan untuk otomatis mengikuti user.",
            "stream": "string — (opsional) URL audio stream untuk diputar. Kosongkan untuk LoFi default.",
        },
    },
    {
        "name": "leave_voice",
        "description": "Tinggalkan voice channel tempat bot berada. Otomatis menghentikan audio yang sedang diputar.",
        "parameters": {},
    },
    {
        "name": "play_audio",
        "description": "Putar audio/stream di voice channel tempat bot berada. Bisa ganti lagu tanpa harus leave-join.",
        "parameters": {
            "stream": "string — URL audio stream yang akan diputar. Kosongkan untuk kembali ke LoFi default.",
        },
    },
    {
        "name": "stop_audio",
        "description": "Hentikan audio yang sedang diputar di voice channel tanpa disconnect.",
        "parameters": {},
    },
    {
        "name": "run_command",
        "description": "Jalankan command Synapse Bot (prefix ! atau /). Gunakan untuk perintah Synapse Bot yang tidak ada tool khususnya, seperti ngecek rank, leaderboard, boost status, help, dll. CATATAN: hanya bisa menjalankan command Synapse Bot — TIDAK bisa menjalankan command milik bot lain (Dyno, Carl-bot, MEE6, dll). HATI-HATI: command yang mengubah data server hanya jalan jika authorized.",
        "parameters": {
            "command": "string — command Synapse Bot yang ingin dijalankan beserta argumennya. Contoh: 'rank @user', 'help', 'leaderboard', 'cekboost @user'",
        },
    },
]


TOOL_DESCRIPTION = """
Kamu adalah AI Agent bawaan dari Synapse Bot — sebuah Discord bot multifungsi yang berjalan di server ini. Kamu BUKAN bot terpisah. Kamu adalah fitur AI yang tertanam langsung di Synapse Bot. Semua command Synapse Bot (!help, !rank, /ask, /scan, dll) bisa dijalankan via tool run_command.

Tool run_command HANYA bisa menjalankan command milik Synapse Bot saja. Command milik bot lain (Dyno, Carl-bot, MEE6, Rythm, dll) TIDAK bisa dijalankan — karena bot Discord tidak bisa mengontrol bot lain. Jika user meminta menjalankan command bot lain, jelaskan bahwa itu tidak bisa dilakukan.

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
9. Saat membuat channel (create_channel), WAJIB tentukan parameter "category" agar channel langsung terkelompok dalam kategori. Jika kategori belum ada, tool akan membuatnya otomatis. Contoh: / create_channel name="📜-rules" category="📢 Announcements"
10. Untuk bikin banyak channel/role sekaligus, GUNAKAN batch_create_channels / batch_create_roles, bukan create_channel/create_role satu-satu. Batch tool jauh lebih cepat dan hemat token.
11. Jika user mau setup server dari awal (bikin struktur channel & role), GUNAKAN apply_template — itu tool template server lengkap dengan 3 pilihan: 'gaming', 'study', 'community'.
"""

DISCORD_UI_KNOWLEDGE = """
## Discord UI — Server & Channel Menu (right-click)

### Server Context Menu (klik kanan pada nama server di sidebar)
- Server Boost — Lihat status & manage Nitro boosts
- Invite to Server — Buat invite link
- Server Settings — Buka dashboard pengaturan server
- Create Channel — Buat channel baru (sama kaya tool create_channel)
- Create Category — Buat kategori baru
- Create Event — Buat event server
- App Directory — Cari & tambah aplikasi Discord
- Notification Settings — Atur notifikasi per-server
- Privacy Settings — Atur privacy per-server
- Edit Per-server Profile — Ubah nickname & avatar di server ini
- Hide Muted Channels — Sembunyikan channel yang di-mute
- Copy Server ID — Salin ID server ke clipboard

### Channel Context Menu (klik kanan pada channel)
- Mark As Read — Tandai semua pesan sudah dibaca
- Invite to Channel — Buat invite link ke channel ini
- Pin Channel to Top — Sematkan channel di atas daftar
- Copy Link — Salin link channel
- Mute Channel — Matikan notifikasi channel (15 menit, 1 jam, 3 jam, 8 jam, 24 jam, sampai di-unmute)
- Notification Settings — Atur notifikasi per-channel (All Messages, Only @mentions, Nothing)
- Edit Channel — Ubah nama, topic, kategori, dll (sama kaya tool rename_channel)
- Duplicate Channel — Duplikat channel beserta permission-nya
- Create Text Channel — Buat text channel baru di dalam kategori yang sama
- Delete Channel — Hapus channel (BERBAHAYA)
- Copy Channel ID — Salin ID channel ke clipboard

Gunakan pengetahuan ini untuk menjawab pertanyaan user tentang cara manual melakukan sesuatu di Discord.
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
    calls = []

    # Format 1: [TOOL_CALL] Function: xxx Arguments: {json} atau key=value
    pattern1 = r'\[TOOL_CALL\]\s*Function:\s*(\w+)\s*Arguments:\s*(.*?)(?=\[TOOL_CALL\]|\Z)'
    for fn_name, args_raw in re.findall(pattern1, text, re.DOTALL):
        calls.append(_parse_single_call(fn_name, args_raw.strip()))

    # Format 2: [TOOL_CALL] Function: xxx | arg1=val1, arg2=val2 (pipe separator, no Arguments label)
    pattern2 = r'\[TOOL_CALL\]\s*Function:\s*(\w+)\s*(?:\|\s*)?(.*?)(?=\[TOOL_CALL\]|\Z)'
    if not calls:
        for fn_name, args_raw in re.findall(pattern2, text, re.DOTALL):
            args_raw = args_raw.strip()
            if args_raw and not args_raw.startswith("Arguments"):
                calls.append(_parse_single_call(fn_name, args_raw))

    # Format 3: Raw JSON — {"function": "xxx", "arguments": {...}}
    if not calls:
        json_pattern = r'\{[^{]*"function"\s*:\s*"(\w+)"[^}]*"arguments"\s*:\s*(\{.*?\})[^}]*\}'
        for fn_name, args_str in re.findall(json_pattern, text, re.DOTALL):
            try:
                args = json.loads(args_str)
                calls.append({"function": fn_name, "arguments": args})
            except json.JSONDecodeError:
                pass

    # Format 4: XML-style — <tool_call><function=name><parameter=key>val</parameter></function></tool_call>
    if not calls:
        xml_pattern = r'<tool_call>(.*?)</tool_call>'
        for block in re.findall(xml_pattern, text, re.DOTALL):
            fn_match = re.search(r'<function=(\w+)>', block)
            if not fn_match:
                continue
            fn_name = fn_match.group(1)
            args = {}
            for param_match in re.finditer(r'<parameter=(\w+)>(.*?)</parameter>', block, re.DOTALL):
                key = param_match.group(1)
                val = param_match.group(2).strip()
                if val.lower() in ("true", "false"):
                    val = val.lower() == "true"
                else:
                    try:
                        num = float(val)
                        if "." in val or "e" in val.lower():
                            val = num
                        else:
                            val = int(val)
                    except ValueError:
                        pass
                args[key] = val
            calls.append({"function": fn_name, "arguments": args})

    return calls if calls else None


def _parse_single_call(fn_name: str, args_raw: str) -> dict:
    import json, re
    args_raw = args_raw.strip()
    # Coba parse sebagai JSON dulu
    if args_raw.startswith("{"):
        try:
            args = json.loads(args_raw)
        except json.JSONDecodeError:
            # JSON broken — coba fix dengan aggressive repair
            try:
                # Replace single quotes, normalize
                fixed = args_raw.replace("'", '"')
                # Fix trailing commas
                fixed = re.sub(r',\s*\}', '}', fixed)
                fixed = re.sub(r',\s*\]', ']', fixed)
                # Fix unquoted keys (true/false/null should be quoted?)
                args = json.loads(fixed)
            except (json.JSONDecodeError, re.error):
                args = {}
        return {"function": fn_name, "arguments": args}

    # Key=value pairs
    args = {}
    # Split by comma or pipe
    for part in re.split(r'[,|]', args_raw):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if v.lower() in ("true", "false"):
                v = v.lower() == "true"
            else:
                try:
                    float(v)
                    if "." in v or "e" in v.lower():
                        v = float(v)
                    else:
                        v = int(v)
                except ValueError:
                    pass
            args[k] = v
    return {"function": fn_name, "arguments": args}


def find_channel(guild: discord.Guild, name: str, ch_type: str = "") -> discord.abc.GuildChannel | None:
    channels = guild.channels
    if ch_type == "text":
        channels = [c for c in channels if isinstance(c, discord.TextChannel) and not isinstance(c, discord.CategoryChannel)]
    elif ch_type == "voice":
        channels = [c for c in channels if isinstance(c, discord.VoiceChannel)]
    elif ch_type == "category":
        channels = [c for c in channels if isinstance(c, discord.CategoryChannel)]
    # Cari by ID dulu kalo input numeric
    if name.isdigit():
        c = discord.utils.get(channels, id=int(name))
        if c:
            return c
    return discord.utils.get(channels, name=name)


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


# ── Tool Call Validation ──

def validate_tool_call(tool_call: dict) -> str | None:
    """Validasi tool call. Return string error kalo ada masalah, None kalo OK."""
    fn = tool_call.get("function", "")
    args = tool_call.get("arguments", {})

    if not fn:
        return "Function name kosong. Format: [TOOL_CALL] Function: nama_function Arguments: {...}"

    # Cari definisi tool
    tdef = None
    for t in TOOL_DEFINITIONS:
        if t["name"] == fn:
            tdef = t
            break

    if not tdef:
        # Tool gak dikenal — kasih saran
        suggestions = [t["name"] for t in TOOL_DEFINITIONS]
        return f"Tool '{fn}' tidak dikenal. Tool yang tersedia: {', '.join(suggestions)}"

    # Validasi tipe arguments dari parameter definition
    for pname, pdesc in tdef.get("parameters", {}).items():
        if pname in ("color", "new_name", "reason", "duration", "topic", "ch_type"):
            continue  # optional string
        is_optional = "(optional)" in pdesc.lower()
        if not is_optional and pname not in args:
            return f"Tool '{fn}' butuh parameter '{pname}' yang wajib diisi."

        if pname in args:
            val = args[pname]
            desc_lower = pdesc.lower()
            if "boolean" in desc_lower and not isinstance(val, bool):
                return f"Parameter '{pname}' untuk tool '{fn}' harus boolean (true/false), bukan '{type(val).__name__}'."
            if "integer" in desc_lower and not isinstance(val, (int, float)):
                return f"Parameter '{pname}' untuk tool '{fn}' harus angka (integer), bukan '{type(val).__name__}'."
            if "object" in desc_lower and not isinstance(val, dict):
                return f"Parameter '{pname}' untuk tool '{fn}' harus object (JSON), bukan '{type(val).__name__}'."

    return None


async def execute_tool(guild: discord.Guild, tool_call: dict, bot, channel=None, author=None) -> str:
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
        elif fn == "edit_role":
            return await _edit_role(guild, args)
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
        elif fn == "batch_create_channels":
            return await _batch_create_channels(guild, args)
        elif fn == "batch_create_roles":
            return await _batch_create_roles(guild, args)
        elif fn == "apply_template":
            return await _apply_template(guild, args)
        elif fn == "edit_server":
            return await _edit_server(guild, args)
        elif fn == "save_snapshot":
            return await _save_snapshot(guild, args)
        elif fn == "rollback":
            return await _rollback(guild, args)
        elif fn == "schedule_task":
            return await _schedule_task(guild, args)
        elif fn == "send_message":
            return await _send_message(guild, args)
        elif fn == "add_reaction":
            return await _add_reaction(guild, args)
        elif fn == "join_voice":
            return await _join_voice(guild, args, author=author)
        elif fn == "leave_voice":
            return await _leave_voice(guild)
        elif fn == "play_audio":
            return await _play_audio(guild, args)
        elif fn == "stop_audio":
            return await _stop_audio(guild)
        elif fn == "run_command":
            return await _run_command(guild, args, bot, channel, author)
        else:
            return f"[TOOL_RESULT]\nFunction: {fn}\nResult: {{\"success\": false, \"error\": \"Tool '{fn}' tidak dikenal\"}}"
    except discord.Forbidden:
        return f'[TOOL_RESULT]\nFunction: {fn}\nResult: {{"success": false, "error": "Bot tidak punya izin untuk melakukan ini. Pastikan bot punya role dengan permission yang cukup di Server Settings > Roles."}}'
    except discord.NotFound as e:
        return f'[TOOL_RESULT]\nFunction: {fn}\nResult: {{"success": false, "error": "Target tidak ditemukan: {str(e)[:100]}"}}'
    except discord.HTTPException as e:
        return f'[TOOL_RESULT]\nFunction: {fn}\nResult: {{"success": false, "error": "Discord API error (kode {e.status}): {str(e)[:200]}"}}'
    except Exception as e:
        return f'[TOOL_RESULT]\nFunction: {fn}\nResult: {{"success": false, "error": "{type(e).__name__}: {str(e)[:200]}"}}'


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


async def _batch_create_channels(guild: discord.Guild, args: dict) -> str:
    channels = args.get("channels", [])
    if not channels or not isinstance(channels, list):
        return '{"success": false, "error": "Parameter channels wajib diisi (array of objects)"}'

    # Categories explicit
    cat_order = args.get("categories", [])
    for cat_name in cat_order:
        if cat_name and not discord.utils.get(guild.categories, name=cat_name):
            await guild.create_category(cat_name, reason="AI Agent: batch channel setup")

    results = []
    errors = []
    for ch_def in channels:
        name = ch_def.get("name", "").strip().lower().replace(" ", "-")
        if not name:
            errors.append("Channel tanpa nama dilewati")
            continue
        ch_type = ch_def.get("type", "text")
        category_name = ch_def.get("category", "").strip()
        topic = ch_def.get("topic", "")

        category = None
        if category_name:
            category = discord.utils.get(guild.categories, name=category_name)
            if not category:
                try:
                    category = await guild.create_category(category_name, reason="AI Agent: batch channel setup")
                except Exception as e:
                    errors.append(f"Gagal buat kategori '{category_name}': {e}")
                    continue

        try:
            if ch_type == "voice":
                channel = await guild.create_voice_channel(name, category=category, reason="AI Agent: batch create channel")
            else:
                channel = await guild.create_text_channel(name, category=category, topic=topic, reason="AI Agent: batch create channel")
            results.append({"name": channel.name, "id": channel.id, "type": ch_type, "category": category_name or None})
        except Exception as e:
            errors.append(f"Gagal buat channel '{name}': {e}")

    summary = {"success": True, "created": len(results), "failed": len(errors)}
    if results:
        summary["channels"] = results
    if errors:
        summary["errors"] = errors
    return f"[TOOL_RESULT]\nFunction: batch_create_channels\nResult: {summary}"


async def _batch_create_roles(guild: discord.Guild, args: dict) -> str:
    roles = args.get("roles", [])
    if not roles or not isinstance(roles, list):
        return '{"success": false, "error": "Parameter roles wajib diisi (array of objects)"}'

    results = []
    errors = []
    for r_def in roles:
        name = r_def.get("name", "").strip()
        if not name:
            errors.append("Role tanpa nama dilewati")
            continue
        color_str = r_def.get("color", "").strip()
        color = discord.Color.default()
        if color_str:
            try:
                color = discord.Color.from_str(color_str)
            except Exception:
                pass
        perms = r_def.get("permissions", {})
        perm_obj = discord.Permissions()
        for perm_name, val in perms.items():
            if hasattr(perm_obj, perm_name):
                setattr(perm_obj, perm_name, bool(val))

        try:
            role = await guild.create_role(name=name, color=color, permissions=perm_obj, reason="AI Agent: batch create role")
            results.append({"name": role.name, "id": role.id})
        except Exception as e:
            errors.append(f"Gagal buat role '{name}': {e}")

    summary = {"success": True, "created": len(results), "failed": len(errors)}
    if results:
        summary["roles"] = results
    if errors:
        summary["errors"] = errors
    return f"[TOOL_RESULT]\nFunction: batch_create_roles\nResult: {summary}"


# ── Server Templates ──

SERVER_TEMPLATES = {
    "gaming": {
        "name": "🎮 Gaming Server",
        "categories": ["📢 Announcements", "💬 General", "🎮 Gaming", "🤖 Bots"],
        "channels": [
            {"name": "📜-rules", "type": "text", "category": "📢 Announcements", "topic": "Baca aturan server sebelum chat"},
            {"name": "📢-announcements", "type": "text", "category": "📢 Announcements", "topic": "Pengumuman resmi server"},
            {"name": "💬-general-chat", "type": "text", "category": "💬 General", "topic": "Ngobrol santai semua topik"},
            {"name": "🤝-looking-for-group", "type": "text", "category": "💬 General", "topic": "Cari temen buat main bareng"},
            {"name": "🎮-game-discussion", "type": "text", "category": "🎮 Gaming", "topic": "Diskusi game favorit"},
            {"name": "📸-screenshots", "type": "text", "category": "🎮 Gaming", "topic": "Share screenshot momen epic"},
            {"name": "💻-bot-commands", "type": "text", "category": "🤖 Bots", "topic": "Command dan interaksi bot"},
            {"name": "📊-bot-logs", "type": "text", "category": "🤖 Bots", "topic": "Log aktivitas bot"},
            {"name": "🎤-general-voice", "type": "voice", "category": "🎮 Gaming"},
        ],
        "roles": [
            {"name": "Admin", "color": "#FF0000", "permissions": {"administrator": True}},
            {"name": "Moderator", "color": "#00BFFF", "permissions": {"kick_members": True, "ban_members": True, "manage_messages": True, "mute_members": True, "deafen_members": True, "move_members": True}},
            {"name": "Member", "color": "#57F287"},
        ],
    },
    "study": {
        "name": "📚 Study Server",
        "categories": ["📢 Announcements", "📚 Study", "📝 Assignments", "🤖 Bots"],
        "channels": [
            {"name": "📜-rules", "type": "text", "category": "📢 Announcements", "topic": "Aturan server belajar"},
            {"name": "📢-announcements", "type": "text", "category": "📢 Announcements", "topic": "Pengumuman kelas dan jadwal"},
            {"name": "📚-study-general", "type": "text", "category": "📚 Study", "topic": "Diskusi umum seputar pelajaran"},
            {"name": "❓-tanya-jawab", "type": "text", "category": "📚 Study", "topic": "Tanya soal PR atau materi"},
            {"name": "📝-tugas", "type": "text", "category": "📝 Assignments", "topic": "Kumpulin tugas dan diskusi"},
            {"name": "📅-deadline-tracker", "type": "text", "category": "📝 Assignments", "topic": "Catat deadline tugas"},
            {"name": "💻-bot-commands", "type": "text", "category": "🤖 Bots", "topic": "Command bot"},
            {"name": "🔊-study-room", "type": "voice", "category": "📚 Study"},
        ],
        "roles": [
            {"name": "Admin", "color": "#FF0000", "permissions": {"administrator": True}},
            {"name": "Teacher", "color": "#FFD700", "permissions": {"kick_members": True, "manage_messages": True, "manage_channels": True}},
            {"name": "Student", "color": "#00FF88"},
        ],
    },
    "community": {
        "name": "🌍 Community Server",
        "categories": ["📢 Announcements", "💬 General", "🎨 Creations", "🤖 Bots"],
        "channels": [
            {"name": "📜-rules", "type": "text", "category": "📢 Announcements", "topic": "Aturan komunitas"},
            {"name": "📢-announcements", "type": "text", "category": "📢 Announcements", "topic": "Pengumuman resmi"},
            {"name": "💬-general-chat", "type": "text", "category": "💬 General", "topic": "Ngobrol santai"},
            {"name": "📸-media-share", "type": "text", "category": "💬 General", "topic": "Share foto, video, meme"},
            {"name": "🎨-showcase", "type": "text", "category": "🎨 Creations", "topic": "Pamerin karya kamu"},
            {"name": "💡-suggestions", "type": "text", "category": "🎨 Creations", "topic": "Kasih saran buat server"},
            {"name": "💻-bot-commands", "type": "text", "category": "🤖 Bots", "topic": "Command bot"},
            {"name": "🔊-community-voice", "type": "voice", "category": "💬 General"},
        ],
        "roles": [
            {"name": "Admin", "color": "#FF0000", "permissions": {"administrator": True}},
            {"name": "Moderator", "color": "#9B59B6", "permissions": {"kick_members": True, "manage_messages": True, "mute_members": True}},
            {"name": "Member", "color": "#3498DB"},
            {"name": "Creator", "color": "#E67E22", "permissions": {"attach_files": True, "embed_links": True}},
        ],
    },
}


async def _apply_template(guild: discord.Guild, args: dict) -> str:
    template_name = args.get("template", "").strip().lower()
    if template_name not in SERVER_TEMPLATES:
        available = ", ".join(SERVER_TEMPLATES.keys())
        return f'{{"success": false, "error": "Template \\"{template_name}\\" tidak dikenal. Pilihan: {available}"}}'

    tpl = SERVER_TEMPLATES[template_name]

    # 1. Buat kategori dulu
    cat_map = {}
    for cat_name in tpl.get("categories", []):
        existing = discord.utils.get(guild.categories, name=cat_name)
        if existing:
            cat_map[cat_name] = existing
        else:
            cat_map[cat_name] = await guild.create_category(cat_name, reason="AI Agent: template setup")

    # 2. Buat channel
    chan_results = []
    for ch_def in tpl.get("channels", []):
        name = ch_def["name"]
        ch_type = ch_def.get("type", "text")
        topic = ch_def.get("topic", "")
        category = cat_map.get(ch_def.get("category", ""))

        try:
            if ch_type == "voice":
                ch = await guild.create_voice_channel(name, category=category, reason="AI Agent: template setup")
            else:
                ch = await guild.create_text_channel(name, category=category, topic=topic, reason="AI Agent: template setup")
            chan_results.append({"name": ch.name, "id": ch.id, "type": ch_type})
        except Exception as e:
            chan_results.append({"name": name, "error": str(e)[:100]})

    # 3. Buat role
    role_results = []
    for r_def in tpl.get("roles", []):
        color = discord.Color.default()
        if r_def.get("color"):
            try:
                color = discord.Color.from_str(r_def["color"])
            except Exception:
                pass
        perms = discord.Permissions()
        for perm_name, val in r_def.get("permissions", {}).items():
            if hasattr(perms, perm_name):
                setattr(perms, perm_name, val)
        try:
            role = await guild.create_role(name=r_def["name"], color=color, permissions=perms, reason="AI Agent: template setup")
            role_results.append({"name": role.name, "id": role.id})
        except Exception as e:
            role_results.append({"name": r_def["name"], "error": str(e)[:100]})

    summary = {
        "success": True,
        "template": tpl["name"],
        "categories_created": len(cat_map),
        "channels_created": len(chan_results),
        "roles_created": len(role_results),
        "channels": chan_results,
        "roles": role_results,
    }
    return f"[TOOL_RESULT]\nFunction: apply_template\nResult: {summary}"


async def _edit_server(guild: discord.Guild, args: dict) -> str:
    edits = {}
    skipped = []

    name = args.get("name")
    if name:
        edits["name"] = str(name).strip()

    description = args.get("description")
    if description is not None:
        edits["description"] = str(description).strip()

    verification_str = args.get("verification_level")
    if verification_str:
        vmap = {
            "none": discord.VerificationLevel.none,
            "low": discord.VerificationLevel.low,
            "medium": discord.VerificationLevel.medium,
            "high": discord.VerificationLevel.high,
            "very_high": discord.VerificationLevel.very_high,
        }
        v = vmap.get(verification_str.strip().lower())
        if v is not None:
            edits["verification_level"] = v
        else:
            skipped.append(f"verification_level '{verification_str}' tidak dikenal")

    afk_channel_name = args.get("afk_channel")
    if afk_channel_name:
        ch = discord.utils.get(guild.voice_channels, name=afk_channel_name.strip())
        if ch:
            edits["afk_channel"] = ch
        else:
            skipped.append(f"AFK channel '{afk_channel_name}' tidak ditemukan")

    afk_timeout = args.get("afk_timeout")
    if afk_timeout is not None:
        try:
            edits["afk_timeout"] = int(afk_timeout)
        except (ValueError, TypeError):
            skipped.append(f"afk_timeout harus angka")

    system_channel_name = args.get("system_channel")
    if system_channel_name:
        ch = discord.utils.get(guild.text_channels, name=system_channel_name.strip())
        if ch:
            edits["system_channel"] = ch
        else:
            skipped.append(f"system channel '{system_channel_name}' tidak ditemukan")

    if not edits:
        return '{"success": false, "error": "Tidak ada parameter yang diisi. Isi minimal satu parameter."}'

    try:
        await guild.edit(**edits, reason="AI Agent: edit server")
    except discord.Forbidden:
        return '{"success": false, "error": "Bot tidak punya izin Manage Server untuk mengubah pengaturan ini."}'
    except Exception as e:
        return f'{{"success": false, "error": "{type(e).__name__}: {str(e)[:200]}"}}'

    result = {"success": True, "changes": list(edits.keys())}
    if skipped:
        result["skipped"] = skipped
    return f"[TOOL_RESULT]\nFunction: edit_server\nResult: {result}"


# ── Snapshot / Rollback ──

SNAPSHOT_COLLECTION = "agent_snapshots"


async def _snapshot_id(guild: discord.Guild) -> str:
    return f"snap_{guild.id}_{int(time.time())}"


async def _build_snapshot(guild: discord.Guild) -> dict:
    roles = []
    for r in sorted(guild.roles, key=lambda x: x.position, reverse=True):
        if r.is_default() or r.is_bot_managed() or r.is_integration():
            continue
        roles.append({
            "name": r.name, "id": r.id, "color": str(r.color),
            "position": r.position, "hoist": r.hoist, "mentionable": r.mentionable,
            "permissions": [p for p, v in r.permissions if v],
        })
    channels = []
    for ch in guild.channels:
        if isinstance(ch, discord.CategoryChannel):
            channels.append({
                "name": ch.name, "id": ch.id, "type": "category",
                "position": ch.position,
            })
        else:
            channels.append({
                "name": ch.name, "id": ch.id,
                "type": "text" if isinstance(ch, discord.TextChannel) else "voice",
                "position": ch.position,
                "category": ch.category.name if ch.category else None,
                "topic": ch.topic if isinstance(ch, discord.TextChannel) else None,
            })
    return {
        "guild_id": guild.id,
        "guild_name": guild.name,
        "timestamp": time.time(),
        "roles": roles,
        "channels": channels,
    }


async def _save_snapshot(guild: discord.Guild, args: dict) -> str:
    snap = await _build_snapshot(guild)
    if _HAS_FS and db is not None:
        try:
            await asyncio.to_thread(
                lambda: db.collection("agent_snapshots").document(str(guild.id)).set(snap)
            )
            return f'[TOOL_RESULT]\nFunction: save_snapshot\nResult: {{"success": true, "roles": {len(snap["roles"])}, "channels": {len(snap["channels"])}}}'
        except Exception as e:
            return f'{{"success": false, "error": "Gagal simpan snapshot: {e}"}}'
    return '{"success": false, "error": "Firestore tidak tersedia"}'

SNAPSHOT_CACHE: dict[int, dict] = {}

async def _load_snapshot(guild_id: int) -> dict | None:
    if guild_id in SNAPSHOT_CACHE:
        return SNAPSHOT_CACHE[guild_id]
    if _HAS_FS and db is not None:
        try:
            doc = await asyncio.to_thread(
                lambda: db.collection("agent_snapshots").document(str(guild_id)).get()
            )
            if doc.exists:
                data = doc.to_dict()
                SNAPSHOT_CACHE[guild_id] = data
                return data
        except Exception:
            pass
    return None


async def _rollback(guild: discord.Guild, args: dict) -> str:
    if not args.get("confirm"):
        return '{"success": false, "error": "Kamu harus set confirm=true untuk melanjutkan rollback. Ini aksi serius!"}'

    snap = await _load_snapshot(guild.id)
    if not snap:
        return '{"success": false, "error": "Tidak ada snapshot tersimpan untuk server ini. Gunakan save_snapshot dulu."}'

    results = {"roles_restored": 0, "roles_created": 0, "channels_restored": 0, "channels_created": 0, "errors": []}

    # Restore roles: cari by ID, kalo gak ada, cari by name terus update
    for r_snap in snap.get("roles", []):
        role = guild.get_role(r_snap["id"])
        if role:
            try:
                color = discord.Color.default()
                if r_snap.get("color") and r_snap["color"] != "None":
                    try:
                        color = discord.Color.from_str(r_snap["color"])
                    except Exception:
                        pass
                perms = discord.Permissions()
                for p_name in r_snap.get("permissions", []):
                    if hasattr(perms, p_name):
                        setattr(perms, p_name, True)
                await role.edit(
                    name=r_snap["name"], color=color,
                    hoist=r_snap.get("hoist", False),
                    mentionable=r_snap.get("mentionable", False),
                    permissions=perms,
                    reason="AI Agent: rollback roles",
                )
                results["roles_restored"] += 1
            except Exception as e:
                results["errors"].append(f"Role '{r_snap['name']}': {str(e)[:80]}")
        else:
            # Role udah kehapus — coba bikin ulang
            try:
                color = discord.Color.default()
                if r_snap.get("color") and r_snap["color"] != "None":
                    try:
                        color = discord.Color.from_str(r_snap["color"])
                    except Exception:
                        pass
                perms = discord.Permissions()
                for p_name in r_snap.get("permissions", []):
                    if hasattr(perms, p_name):
                        setattr(perms, p_name, True)
                await guild.create_role(
                    name=r_snap["name"], color=color, permissions=perms,
                    hoist=r_snap.get("hoist", False),
                    mentionable=r_snap.get("mentionable", False),
                    reason="AI Agent: rollback recreate role",
                )
                results["roles_created"] += 1
            except Exception as e:
                results["errors"].append(f"Create role '{r_snap['name']}': {str(e)[:80]}")

    # Restore channels
    for ch_snap in snap.get("channels", []):
        ch = guild.get_channel(ch_snap["id"])
        if ch:
            try:
                edits = {"name": ch_snap["name"], "position": ch_snap["position"]}
                if ch_snap.get("topic") is not None and hasattr(ch, "edit") and "topic" in ch.__dir__():
                    edits["topic"] = ch_snap["topic"]
                if ch_snap.get("category"):
                    cat = discord.utils.get(guild.categories, name=ch_snap["category"])
                    if cat:
                        edits["category"] = cat
                await ch.edit(**edits, reason="AI Agent: rollback channels")
                results["channels_restored"] += 1
            except Exception as e:
                results["errors"].append(f"Channel '{ch_snap['name']}': {str(e)[:80]}")
        else:
            # Channel udah kehapus — coba bikin ulang
            try:
                category = None
                if ch_snap.get("category"):
                    category = discord.utils.get(guild.categories, name=ch_snap["category"])
                ch_type = ch_snap.get("type", "text")
                if ch_type == "voice":
                    await guild.create_voice_channel(
                        ch_snap["name"], category=category,
                        reason="AI Agent: rollback recreate channel",
                    )
                elif ch_type == "category":
                    await guild.create_category(
                        ch_snap["name"],
                        reason="AI Agent: rollback recreate category",
                    )
                else:
                    await guild.create_text_channel(
                        ch_snap["name"], category=category,
                        topic=ch_snap.get("topic", ""),
                        reason="AI Agent: rollback recreate channel",
                    )
                results["channels_created"] += 1
            except Exception as e:
                results["errors"].append(f"Create channel '{ch_snap['name']}': {str(e)[:80]}")

    results["success"] = True
    return f"[TOOL_RESULT]\nFunction: rollback\nResult: {results}"


async def _schedule_task(guild: discord.Guild, args: dict) -> str:
    name = args.get("name", "").strip()
    action = args.get("action", "").strip()
    params = args.get("params", {})
    schedule = args.get("schedule", "").strip()
    enabled = args.get("enabled", True)

    if not name:
        return '{"success": false, "error": "Nama tugas wajib diisi"}'
    if action not in ("assign_role", "remove_role", "send_message"):
        return '{"success": false, "error": "Aksi harus salah satu: assign_role, remove_role, send_message"}'
    if not schedule:
        return '{"success": false, "error": "Jadwal wajib diisi. Contoh: interval:24h"}'

    interval_seconds = None
    if schedule.startswith("interval:"):
        raw = schedule[9:].strip()
        try:
            if raw.endswith("h"):
                interval_seconds = int(raw[:-1]) * 3600
            elif raw.endswith("m"):
                interval_seconds = int(raw[:-1]) * 60
            elif raw.endswith("d"):
                interval_seconds = int(raw[:-1]) * 86400
            else:
                interval_seconds = int(raw) * 60
        except ValueError:
            return f'{{"success": false, "error": "Format interval salah. Contoh: interval:24h, interval:30m"}}'
    else:
        return '{"success": false, "error": "Format jadwal tidak dikenal. Gunakan format: interval:24h"}'

    if interval_seconds < 300:
        interval_seconds = 300

    task_data = {
        "name": name,
        "action": action,
        "params": params,
        "interval": interval_seconds,
        "enabled": bool(enabled),
        "guild_id": guild.id,
        "created_at": time.time(),
        "last_run": 0,
        "next_run": time.time() + interval_seconds,
    }

    if _HAS_FS and db is not None:
        try:
            doc_id = f"{guild.id}_{name.lower().replace(' ', '-')}"
            await asyncio.to_thread(
                lambda: db.collection("agent_schedules").document(doc_id).set(task_data)
            )
            return f'[TOOL_RESULT]\nFunction: schedule_task\nResult: {{"success": true, "task": "{name}", "action": "{action}", "interval": "{interval_seconds}s", "next_run": "{time.ctime(time.time() + interval_seconds)}"}}'
        except Exception as e:
            return f'{{"success": false, "error": "Gagal simpan jadwal: {e}"}}'
    return '{"success": false, "error": "Firestore tidak tersedia"}'


async def _delete_channel(guild: discord.Guild, args: dict) -> str:
    name = args.get("name", "").strip()
    ch_type = args.get("type", "").strip().lower()
    if not name:
        return '{"success": false, "error": "Nama channel wajib diisi"}'
    channel = find_channel(guild, name, ch_type)
    if not channel:
        return f'{{"success": false, "error": "Channel dengan nama \\"{name}\\" tidak ditemukan"}}'
    ch_name = channel.name
    await channel.delete(reason="AI Agent: delete channel")
    return f'{{"success": true, "deleted_channel": "{ch_name}"}}'


async def _rename_channel(guild: discord.Guild, args: dict) -> str:
    old = args.get("old_name", "").strip()
    new = args.get("new_name", "").strip()
    topic = args.get("topic", "")
    ch_type = args.get("type", "").strip().lower()
    if not old:
        return '{"success": false, "error": "old_name wajib diisi"}'
    if not new and not topic:
        return '{"success": false, "error": "setidaknya new_name atau topic harus diisi"}'
    channel = find_channel(guild, old, ch_type)
    if not channel:
        return f'{{"success": false, "error": "Channel \\"{old}\\" tidak ditemukan"}}'
    edits = {"reason": "AI Agent: edit channel"}
    if new:
        edits["name"] = new
    if topic:
        if isinstance(channel, discord.TextChannel):
            edits["topic"] = topic
        else:
            return f'{{"success": false, "error": "Topic hanya bisa diatur untuk text channel"}}'
    await channel.edit(**edits)
    parts = []
    if new:
        parts.append(f'name "{old}" → "{new}"')
    if topic:
        parts.append(f'topic diubah')
    return f'{{"success": true, "changes": "{", ".join(parts)}"}}'


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
    perms_dict = args.get("permissions", {})
    perm_kwargs = {}
    if perms_dict:
        for key, value in perms_dict.items():
            normalized = key.lower().replace(" ", "_").replace("-", "_")
            perm_kwargs[normalized] = bool(value)
    permissions = discord.Permissions(**perm_kwargs) if perm_kwargs else discord.Permissions.none()
    role = await guild.create_role(
        name=name, color=color, permissions=permissions,
        reason="AI Agent: create role"
    )
    enabled = [k for k, v in perm_kwargs.items() if v]
    disabled = [k for k, v in perm_kwargs.items() if not v]
    result = {"success": True, "role_id": str(role.id), "role_name": role.name}
    if enabled:
        result["permissions_enabled"] = enabled
    if disabled:
        result["permissions_disabled"] = disabled
    return json.dumps(result)


async def _edit_role(guild: discord.Guild, args: dict) -> str:
    name = args.get("name", "").strip()
    if not name:
        return '{"success": false, "error": "Nama role wajib diisi"}'
    role = find_role(guild, name)
    if not role:
        return f'{{"success": false, "error": "Role \\"{name}\\" tidak ditemukan"}}'
    kwargs = {}
    changes = []

    new_name = args.get("new_name", "")
    if new_name:
        kwargs["name"] = new_name.strip()
        changes.append(f"nama: {name} → {new_name.strip()}")

    color_hex = args.get("color", "")
    if color_hex:
        try:
            kwargs["color"] = discord.Color(int(color_hex.lstrip("#"), 16))
            changes.append(f"warna: {color_hex}")
        except ValueError:
            pass

    perms_dict = args.get("permissions", {})
    if perms_dict:
        perm_kwargs = {}
        for key, value in perms_dict.items():
            normalized = key.lower().replace(" ", "_").replace("-", "_")
            perm_kwargs[normalized] = bool(value)
        if perm_kwargs:
            # Merge: ambil permission existing, update cuma yang disebut
            current_dict = dict(role.permissions)
            current_dict.update(perm_kwargs)
            kwargs["permissions"] = discord.Permissions(**current_dict)
            enabled = [k for k, v in perm_kwargs.items() if v]
            disabled = [k for k, v in perm_kwargs.items() if not v]
            if enabled:
                changes.append(f"permission ON: {', '.join(enabled)}")
            if disabled:
                changes.append(f"permission OFF: {', '.join(disabled)}")

    position = args.get("position")
    if position is not None:
        try:
            pos = int(position)
            if pos >= 0:
                kwargs["position"] = pos
                changes.append(f"posisi: {pos}")
        except (ValueError, TypeError):
            pass

    hoist = args.get("hoist")
    if hoist is not None:
        kwargs["hoist"] = bool(hoist)
        changes.append(f"hoist: {'ON' if hoist else 'OFF'}")

    mentionable = args.get("mentionable")
    if mentionable is not None:
        kwargs["mentionable"] = bool(mentionable)
        changes.append(f"mentionable: {'ON' if mentionable else 'OFF'}")

    if not kwargs:
        return '{"success": false, "error": "Tidak ada perubahan yang diberikan. Beri setidaknya satu: new_name, color, permissions, position, hoist, atau mentionable."}'

    await role.edit(**kwargs, reason="AI Agent: edit role")
    return f'{{"success": true, "role": "{name}", "changes": "{", ".join(changes)}"}}'


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


# ── New Tools ──


async def _send_message(guild: discord.Guild, args: dict) -> str:
    channel_name = args.get("channel", "").strip()
    message = args.get("message", "").strip()
    if not channel_name:
        return '{"success": false, "error": "Parameter channel wajib diisi"}'
    if not message:
        return '{"success": false, "error": "Parameter message wajib diisi"}'
    channel = find_channel(guild, channel_name, "text")
    if not channel:
        return f'{{"success": false, "error": "Channel \\"{channel_name}\\" tidak ditemukan"}}'
    try:
        sent = await channel.send(message[:1900])
        return f'{{"success": true, "channel": "{channel_name}", "message_id": {sent.id}}}'
    except discord.Forbidden:
        return '{"success": false, "error": "Bot tidak punya izin kirim pesan di channel tersebut"}'


async def _add_reaction(guild: discord.Guild, args: dict) -> str:
    channel_name = args.get("channel", "").strip()
    message_id = args.get("message_id", "").strip()
    emoji = args.get("emoji", "").strip()
    if not channel_name:
        return '{"success": false, "error": "Parameter channel wajib diisi"}'
    if not message_id:
        return '{"success": false, "error": "Parameter message_id wajib diisi"}'
    if not emoji:
        return '{"success": false, "error": "Parameter emoji wajib diisi"}'
    channel = find_channel(guild, channel_name, "text")
    if not channel:
        return f'{{"success": false, "error": "Channel \\"{channel_name}\\" tidak ditemukan"}}'
    try:
        mid = int(message_id)
    except ValueError:
        return f'{{"success": false, "error": "message_id harus berupa angka"}}'
    try:
        message = await channel.fetch_message(mid)
    except discord.NotFound:
        return f'{{"success": false, "error": "Pesan dengan ID {message_id} tidak ditemukan di channel {channel_name}"}}'
    except discord.Forbidden:
        return '{"success": false, "error": "Bot tidak punya izin membaca pesan di channel tersebut"}'
    try:
        await message.add_reaction(emoji)
        return f'{{"success": true, "emoji": "{emoji}", "message_id": "{message_id}", "channel": "{channel_name}"}}'
    except discord.HTTPException as e:
        return f'{{"success": false, "error": "Gagal menambah reaksi: {str(e)[:100]}"}}'


async def _join_voice(guild: discord.Guild, args: dict, author: discord.Member | None = None) -> str:
    channel_name = args.get("channel", "").strip()
    if not channel_name:
        if author and author.voice and author.voice.channel:
            channel = author.voice.channel
        else:
            return '{"success": false, "error": "Nama voice channel wajib diisi, atau join voice channel dulu biar bot otomatis ngikut."}'
    else:
        channel = find_channel(guild, channel_name, "voice")
        if not channel:
            return f'{{"success": false, "error": "Voice channel \\"{channel_name}\\" tidak ditemukan"}}'

    vc = guild.voice_client
    if vc:
        if vc.channel.id == channel.id:
            return f'{{"success": true, "message": "Sudah berada di voice channel \\"{channel.name}\\" dan sedang memutar audio"}}'
        await vc.disconnect()
        await asyncio.sleep(0.5)

    try:
        vc = await channel.connect()
    except discord.Forbidden:
        return '{"success": false, "error": "Bot tidak punya izin Connect atau Speak di voice channel tersebut"}'
    except Exception as e:
        return f'{{"success": false, "error": "{type(e).__name__}: {str(e)[:150]}"}}'

    stream_url = args.get("stream", "").strip() or LOFI_DEFAULT_URL
    try:
        ffmpeg_opts = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn",
        }
        source = discord.FFmpegPCMAudio(stream_url, **ffmpeg_opts)
        vc.play(source)
        return f'{{"success": true, "joined": "{channel.name}", "stream": "{stream_url}"}}'
    except Exception as e:
        return f'{{"success": true, "joined": "{channel.name}", "warning": "Terhubung tanpa audio: {str(e)[:100]}"}}'


async def _leave_voice(guild: discord.Guild) -> str:
    vc = guild.voice_client
    if not vc:
        return '{"success": false, "error": "Bot tidak sedang terhubung ke voice channel"}'
    channel_name = vc.channel.name
    if vc.is_playing():
        vc.stop()
    await vc.disconnect()
    return f'{{"success": true, "left": "{channel_name}"}}'


async def _play_audio(guild: discord.Guild, args: dict) -> str:
    vc = guild.voice_client
    if not vc:
        return '{"success": false, "error": "Bot tidak sedang terhubung ke voice channel. Gunakan join_voice dulu."}'
    stream_url = args.get("stream", "").strip() or LOFI_DEFAULT_URL
    vc.stop()
    try:
        ffmpeg_opts = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn",
        }
        source = discord.FFmpegPCMAudio(stream_url, **ffmpeg_opts)
        vc.play(source)
        return f'{{"success": true, "playing": "{stream_url}"}}'
    except Exception as e:
        return f'{{"success": false, "error": "Gagal memutar audio: {str(e)[:150]}"}}'


async def _stop_audio(guild: discord.Guild) -> str:
    vc = guild.voice_client
    if not vc:
        return '{"success": false, "error": "Bot tidak sedang terhubung ke voice channel"}'
    if not vc.is_playing():
        return '{"success": false, "error": "Tidak ada audio yang sedang diputar"}'
    vc.stop()
    return '{"success": true, "message": "Audio dihentikan"}'


async def _run_command(guild: discord.Guild, args: dict, bot, channel, author) -> str:
    cmd_str = args.get("command", "").strip()
    if not cmd_str:
        return '{"success": false, "error": "Parameter command wajib diisi"}'

    if not cmd_str.startswith(bot.command_prefix):
        cmd_str = f"{bot.command_prefix}{cmd_str}"

    parts = cmd_str[len(bot.command_prefix):].split()
    cmd_name = parts[0]
    cmd = bot.get_command(cmd_name)
    if not cmd:
        return f'{{"success": false, "error": "Command \\"{cmd_name}\\" tidak dikenal. Coba tanpa prefix."}}'

    try:
        from discord.message import Message

        now = datetime.datetime.now(datetime.timezone.utc)
        msg_data = {
            "id": discord.utils.time_snowflake(now),
            "type": 0,
            "content": cmd_str,
            "author": {
                "id": author.id,
                "username": author.name,
                "discriminator": getattr(author, "discriminator", "0"),
                "avatar": author.display_avatar.key if author.display_avatar else None,
            },
            "tts": False,
            "timestamp": now.isoformat(),
            "pinned": False,
            "mention_everyone": False,
            "mentions": [],
            "mention_roles": [],
            "mention_channels": [],
            "attachments": [],
            "embeds": [],
            "reactions": [],
            "edited_timestamp": None,
            "flags": 0,
            "webhook_id": None,
            "nonce": None,
        }
        msg = Message(state=channel._state, channel=channel, data=msg_data)
        ctx = await bot.get_context(msg)
        if not ctx.valid:
            return f'{{"success": false, "error": "Gagal memproses command \\"{cmd_name}\\"}}"}}'

        await bot.invoke(ctx)
        return f'{{"success": true, "command": "{cmd_name}", "invoked": true}}'
    except Exception as e:
        return f'{{"success": false, "error": "{type(e).__name__}: {str(e)[:150]}"}}'
