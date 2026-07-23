# Antigravity Agent — Integration Plan

> **Model**: Antigravity (via OpenRouter) — kategori "Agents"
> **Rate limit**: 0 RPM / 100 RPD (sangat rendah — dedicated untuk task, bukan chat)
> **Harga**: Gratis (0 token cost)

## 1. Apa itu Antigravity?

Antigravity adalah model reasoning/planning dari OpenRouter yang dikategorikan sebagai **Agents** — khusus untuk **orchestration multi-step**. Berbeda dengan chat model biasa:

| Sisi | Chat model (Gemini, GPT) | Antigravity |
|---|---|---|
| Fokus | Generate teks / jawab pertanyaan | Rencanain & execute langkah |
| Tool calling | Manual — lo panggil tool sendiri | Otomatis — dia tentuin kapan panggil tool |
| State management | Stateless per request | Bisa multi-turn internal |
| Rate limit | Tinggi (RPM 2-6) | Rendah (RPM ~0-1) |

## 2. Arsitektur

```
User: "Kick user yang spam sejak kemarin"
       │
       ▼
┌──────────────────────────────────┐
│  antigravity.py (Provider)       │
│  - Kirim prompt + tool list      │
│  - Parse response (tool calls)   │
│  - Loop execution                │
└──────┬───────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│  agent_tools.py (Tool defs)      │
│  - search_audit_logs()           │
│  - get_guild_config()            │
│  - send_message()                │
│  - ban_user() / kick_user()      │
│  - update_firestore()            │
│  - rag_search()                  │
│  - toggle_anti_nuke()            │
└──────┬───────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│  agent_runner.py (Execution)     │
│  - Call agent → parse → execute  │
│  - Feedback → loop → done        │
│  - Safety checks (admin only)    │
└──────┬───────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│  Discord (user)                  │
│  - /agent <task>                 │
│  - Mention bot with task         │
└──────────────────────────────────┘
```

## 3. Alur Eksekusi

1. **User** kirim task: `"Tambahin whitelist anti-nuke buat user 12345"`
2. **Bot** kirim ke Antigravity: prompt + tools definitions
3. **Antigravity** response pilih tool:
   ```json
   {
     "tool": "update_firestore",
     "args": {
       "collection": "guild_settings",
       "doc": "guild_id",
       "path": "anti_nuke.whitelist_users",
       "value": ["12345"]
     }
   }
   ```
4. **Bot** eksekusi update → sukses
5. **Bot** kirim hasil balik ke Antigravity
6. **Antigravity** response final: `"Udah, user 12345 udah di-whitelist"`
7. **Bot** kirim ke Discord

## 4. Tools yang Akan Didaftarkan

| Tool | Deskripsi | Admin only |
|---|---|---|
| `search_audit_logs` | Cari audit log (ban, kick, channel/role create) | Ya |
| `get_guild_config` | Ambil Firestore config guild | Ya |
| `update_firestore` | Update field Firestore mana pun | Ya |
| `ban_user` | Ban user dari server | Ya |
| `kick_user` | Kick user dari server | Ya |
| `send_message` | Kirim pesan ke channel tertentu | Tidak |
| `rag_search` | Cari dokumen di RAG ChromaDB | Tidak |
| `toggle_feature` | Enable/disable fitur (anti-spam, anti-nuke, dll) | Ya |
| `get_server_stats` | Statistik server (member, channel, dll) | Tidak |

## 5. File yang Akan Dibuat

| File | Isi |
|---|---|
| `backend/cogs/ai_chat/providers/antigravity.py` | Provider — panggil OpenRouter API + parse tool calls |
| `backend/cogs/ai_chat/agent_tools.py` | Definisi tools (schema JSON + fungsi Python) |
| `backend/cogs/ai_chat/agent_runner.py` | Loop eksekusi agent |
| `backend/cogs/ai_chat/agent_commands.py` | Command `/agent` & handler |

## 6. Rate Limit Strategy

Karena RPD cuma 100, Antigravity **tidak boleh dipakai untuk chat harian**.

- `/agent` command — **cooldown 60 detik per user**
- Mention-based agent — **hanya di channel khusus** (`#agent`)
- Queue — kalo lagi dipake, task berikutnya ditolak dengan pesan "Agent sedang sibuk"

## 7. Trigger Commands

### Slash Command

```
/agent task: <deskripsi task>
```

Contoh:
```
/agent task: Cari user yang invite 50 orang dalam 10 menit, kalo mencurigakan ban
/agent task: Setting anti-nuke threshold jadi 5 buat ban, 3 buat kick
/agent task: Rangkumin dokumen tentang Python di RAG
```

### Mention-based

```
@Synapse cari audit log ban dalam 24 jam terakhir
```

Hanya merespon di channel `#agent` atau channel yang sudah dikonfigurasi.

## 8. Safety

- Semua tool yang **destructive** (ban, kick, update config) hanya bisa dipakai oleh **Administrator**
- Tool **read-only** (search_audit_logs, rag_search, get_server_stats) bisa dipakai semua user
- Setiap eksekusi tool di-log ke console + channel report
- Semua action butuh **konfirmasi** sebelum dijalankan: "Yakin mau ban @user? [Ya / Tidak]"