# AI Agent & AI Chat — Architecture Reference

> File ini dokumentasi workflow, alur data, dan semua perubahan yang udah kita buat.
> Gunakan ini sebagai konteks utama saat ngoding AI features biar gak kehilangan arah.

---

## 1. AI Agent (`backend/cogs/ai_agent/`)

### 1.1 Arsitektur Dasar

naive ReAct (Reasoning + Acting) loop:
Plan → Validate → Execute → Analyze → Repeat

```
User Input
    │
    ▼
┌──────────────────────────────────┐
│  _agent_react()                  │
│  ┌────────────┐  ┌────────────┐  │
│  │ PLAN phase │  │ BUILD phase│  │
│  │ (step 1)   │→│ (setiap    │  │
│  │ plan_prompt│  │  langkah)  │  │
│  └────────────┘  │ followup   │  │
│                  │ _prompt     │  │
│                  └─────┬──────┘  │
│                        ▼         │
│                  parse_tool_call()│
│                        │         │
│                  ┌─────▼──────┐  │
│                  │ validate   │  │
│                  │ _tool_call │  │
│                  │ auto-retry │  │
│                  │ (max 3x)   │  │
│                  └─────┬──────┘  │
│                        ▼         │
│                  execute_tool()  │
│                        │         │
│                  ┌─────▼──────┐  │
│                  │ update scan│  │
│                  │ cache + FS │  │
│                  └────────────┘  │
│                        │         │
│                  ── loop ────────│
│                  max 15 steps    │
└──────────────────────────────────┘
    │
    ▼
  Response ke user
```

### 1.2 File Map

| File | Fungsi |
|------|--------|
| `agent_cog.py` | Cog utama: `_agent_react()`, `/scan`, `/agent`, `/agent-toggle`, `/agent-mode`, `/agent-status` |
| `agent_tools.py` | `TOOL_DEFINITIONS` (18 tools), `TOOL_DESCRIPTION`, `DISCORD_PERMISSIONS_KNOWLEDGE`, `DISCORD_UI_KNOWLEDGE`, `parse_tool_call()`, `validate_tool_call()`, `execute_tool()` |

### 1.3 Tools (18)

AI Chat → `/ask`, `/rag-upload`, `/rag-list`, `/rag-delete`
AI Agent → `/scan`, `/agent`, `/agent-toggle`, `/agent-mode`, `/agent-status`

**Read-only:**
- `server_info` — statistik server
- `list_channels` — semua channel + kategori
- `list_roles` — semua role
- `list_members` — anggota (dengan filter role)
- `list_bans` — banned users

**Mutasi:**
- `create_channel` — bikin text/voice + auto-create category jika `category` parameter diisi
- `delete_channel` — hapus channel (butuh konfirmasi user)
- `rename_channel` — ganti nama channel/kategori
- `edit_channel_permissions` — atur permission channel
- `create_role` — bikin role baru
- `edit_role` — ubah role (merge permissions, hoist, mentionable, position)
- `delete_role` — hapus role (butuh konfirmasi user)
- `assign_role` — kasih role ke member
- `remove_role` — cabut role dari member
- `ban_member` — ban user
- `unban_member` — unban user
- `kick_member` — kick user
- `timeout_member` — timeout user

### 1.4 Memory System

```
RAM cache (_conversation_memory)  ←  Firestore (agent_memory/{user_id}_{guild_id})
       │                                         │
       └── L1 (cepat, hilang restart) ──────────┘
                                                 └── L2 (permanen, survive restart)
```

- **20 turns max** per user (naik dari 5)
- **No TTL** — memory permanen
- Auto-load dari Firestore kalo RAM kosong
- Auto-save ke Firestore tiap selesai `/agent` (async fire-and-forget)
- `agent_memory` collection di Firestore

### 1.5 Scan Cache System

```
RAM cache (_server_scan_cache)  ←  Firestore (agent_scan_cache/{guild_id})
       │                                         │
       └── L1 ──────────────────────────────────┘
                                                 └── L2 (permanen)
```

- `/scan` cukup sekali — hasilnya disimpen di Firestore
- Auto-update setelah tool mutation:
  - Channel ops → refresh `channels` + `categories`
  - Role ops → refresh `roles`
  - Assign/remove role → update `member_count`
  - Ban/unban → refresh `bans` + `member_count`
  - Kick/timeout → update `member_count`
- Simpan ke Firestore tiap update
- Load dari Firestore kalo RAM miss

### 1.6 Provider Fallback

```
_get_provider() → Zen → provider list (Gemini/Groq/Mistral/Cohere/OpenRouter)
                                                      │
                                         fallback di _agent_react()
                                         kalo call gagal → _get_next_provider()
```

### 1.7 Tool Call Parsing (3 formats)

1. **JSON format**: `[TOOL_CALL]\nFunction: x\nArguments: {"key": "val"}\n`
2. **Key=value**: `[TOOL_CALL]\nFunction: x\nArguments: key=val, key2=val2\n`
3. **Raw JSON**: `[TOOL_CALL]\n{"function": "x", "arguments": {...}}\n`

Auto-repair: single quotes → double quotes, trailing comma dihapus.

### 1.8 Auto-Retry

- Max 3 retries per step kalo validasi gagal
- Setiap retry kirim error message + minta AI kirim ulang format bener
- Kalo abis 3x masih gagal → skip tool call

### 1.9 Known Limitations

- **Bot bisa geser role hanya sampai posisi sendiri** — owner/server staff harus manual
- **Capped at 100 members, 50 bans** di scan (performa)
- **15 steps max, 120s timeout** per session
- **Firestore SDK sync-only** — semua akses lewat `asyncio.to_thread()`
- **Circuit breaker** di Firestore (15 menit kalo kena 429)

---

## 2. AI Chat (`backend/cogs/ai_chat/`)

### 2.1 Provider Chain

```
Gemini (gemini-3.6-flash) → Groq → Mistral → Cohere → OpenRouter
```

- Streaming: `/ask` pakai progressive message edits (~1s interval)
- Mention-based: batch mode (nunggu user selesai ngetik)
- Image analysis: **Gemini-only**

### 2.2 RAG System

- ChromaDB persistent di `data/chroma_db/`
- Embedding: Gemini API (`gemini-embedding-001`, 3072-dim) → fallback hash-based
- Graceful degradation kalo `chromadb` import gagal

### 2.3 Integration Points

- `SYSTEM_PROMPT_TEMPLATE` redirect server management ke `/agent`
- `_build_server_context()` untuk context-aware chat
- `is_agent_request()` ngedetect kalo user minta server management → redirect ke `/agent`

### 2.4 Personality System

4 personality: `friendly`, `formal`, `tsundere`, `wise`

---

## 3. All Changes Made (Chronological)

### 3.1 Agent ReAct Loop
- Implementasi Plan→Build loop dengan `[PLAN]...[/PLAN]` + `[TOOL_CALL]`
- Plan auto-summarize kalo >500 chars atau >5 lines
- `[SISA RENCANA]` context di setiap step

### 3.2 Provider Fallback
- `_get_next_provider()` — live fallback kalo provider gagal di tengah eksekusi
- Zen provider prioritaskan, fallback ke chain

### 3.3 Scan System
- `/scan` command + `_server_scan_cache` (RAM cache)
- `_build_scan_context()` — format data server buat prompt AI
- Scan cache injection ke system prompt, plan prompt, followup prompt

### 3.4 Tool Improvements
- `_edit_role` merge permissions (ganti sebagian, bukan replace semua)
- `_edit_role` support `hoist` + `mentionable`
- `find_channel()` support `ch_type` filter + numeric ID
- `delete_channel` + `rename_channel` dapet parameter `type`
- `create_channel` auto-create category kalo category parameter diisi

### 3.5 Validation & Error Handling
- `validate_tool_call()` — cek nama function, parameter types, required args
- Auto-retry 3x per step kalo validasi gagal
- Better Discord error messages (Forbidden, NotFound, HTTPException)
- `parse_tool_call()` enhanced: 3 formats + JSON repair

### 3.6 UX & Templates
- `/help` redesigned (embed, thumbnail, stats, links)
- Landing page commands grid 18→34 commands
- README.md rewritten (full 34 commands, Mermaid diagram, setup guide)

### 3.7 Persistent Memory (Firestore)
- Hapus TTL 5 menit
- MEMORY_MAX_TURNS 5→20
- `_save_memory_firestore()` / `_load_memory_firestore()`
- Collection `agent_memory/{user_id}_{guild_id}`

### 3.8 Persistent Scan Cache (Firestore)
- `_save_scan_firestore()` / `_load_scan_firestore()` — collection `agent_scan_cache/{guild_id}`
- `_update_scan_cache()` — partial update setelah tool mutation
- Auto-save ke Firestore tiap ada perubahan
- `/scan` cukup sekali — AI update sendiri

### 3.9 Channel Category Instruction
- `TOOL_DESCRIPTION` + aturan #9 tentang WAJIB pakai `category`
- `plan_prompt` + 2 contoh few-shot `create_channel` with category

---

## 4. Planned / Next Moves

Prioritas pribadi: **batch ops (#1) → server templates (#2) → settings tools (#3)** — ini yang paling sering bikin AI kelamaan/nyerah.

### AI Agent
1. **Batch operations** — `batch_create_channels` terima list channel + category sekali panggil, bukan 15 langkah
2. **Server templates** — "bikin server gaming" → AI terapin template lengkap (categories, channels, roles) dalam 1-2 langkah
3. **Server settings tools** — ganti nama server, verification level, AFK channel, dll. Belum ada sama sekali
4. **Rollback / snapshot** — simpan state server sebelum mutasi, biar bisa `!undo`
5. **Scheduler** — "jadwalin auto-role tiap hari Minggu" → simpan tugas ke Firestore + background task

### AI Chat
6. **Image generation** — gambar via provider yang support
7. **Channel personality** — beda personality tiap channel (misal `#game-discussion` pake "casual", `#help` pake "formal")
8. **Search memory** — "kemarin kita bahas apa tentang X?" → cari dari Firestore chat history

---

## 5. Key Files Reference

| Path | Desc |
|------|------|
| `backend/cogs/ai_agent/agent_cog.py` | Cog: `_agent_react`, `_scan_server`, `_update_scan_cache`, memory, `/agent`, `/scan` |
| `backend/cogs/ai_agent/agent_tools.py` | 18 tools, definitions, parsing, validation, execute |
| `backend/cogs/ai_chat/ai_chat.py` | `/ask`, mention handler, RAG, provider chain |
| `backend/cogs/ai_chat/prompt.py` | `SYSTEM_PROMPT_TEMPLATE` — redirect ke `/agent` |
| `backend/utils/firestore_stats.py` | Circuit breaker, Firestore helpers |
| `backend/web/language/id.json` | Indonesian translation (commands desc) |
| `backend/web/language/en.json` | English translation |
| `frontend/pages/landing.html` | Landing page (commands grid, features, CTA) |
| `docs/AI-AGENT-ARCHITECTURE.md` | **This file** |

---

## 6. Testing & Deployment Notes

- **No tests, no CI** — semua manual verification
- Run: `honcho start -f Procfile.dev` (bot + web)
- Bot only: `python backend/main.py`
- Environment: `.env` di `backend/.env`

### Firestore Rules
```
agent_memory/{docId} — history percakapan per user
agent_scan_cache/{guildId} — scan data server
```

### Quirks to Remember
- `asyncio.to_thread()` untuk SEMUA akses Firestore (SDK sync-only)
- Circuit breaker 15 menit kalo 429
- `_memory_ts` udah dihapus — gak ada TTL lagi
- `plan_prompt` isi few-shot examples — update kalo nambah tool
- `DISCORD_UI_KNOWLEDGE` di agent system prompt
- `DISCORD_PERMISSIONS_KNOWLEDGE` daftar permission Discord
