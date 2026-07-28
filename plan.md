# AI Agent — Enhancement Plan

## Status: Draft Proposal

---

## PRD — Product Requirements Document

### 1. Run Code (Python Sandbox)

| Item | Detail |
|------|--------|
| **Purpose** | Agent bisa jalanin Python snippet — kalkulasi, parse data, generate teks, dsb |
| **User Story** | "Hitung jumlah member yang online dalam 7 hari terakhir" → agent jalanin Python buat hitung |
| **Constraint** | **Read-only sandbox**: no filesystem write, no network (kecuali API internal), timeout 10s |
| **Implementation** | `exec()` di sandbox terisolasi + `str` capture stdout |
| **Tool name** | `run_code` |

### 2. Web Browsing (Deeper)

| Item | Detail |
|------|--------|
| **Purpose** | Agent bisa fetch, extract, dan summarize konten web secara lebih dalem |
| **User Story** | "Cari tau berita terbaru tentang Discord" → agent scrape page + summarize |
| **Constraint** | Rate limited, max 3 pages per session, 30s timeout |
| **Implementation** | Extend `web_search.py` + `BeautifulSoup` / readability |
| **Tool name** | `web_browse` (bedain sama `web_search`) |

### 3. Memory Compression

| Item | Detail |
|------|--------|
| **Purpose** | Agent bisa inget >20 turns dengan compress history lama |
| **User Story** | "Ingetin gue tentang settings yang gue minta 50 message lalu" |
| **Implementation** | Summarize oldest 10 turns → simpan sebagai 1 merged summary. Trigger otomatis pas turn ke-20 |
| **Tool name** | N/A (otomatis, internal) |

### 4. Feedback Loop (Preference Learning)

| Item | Detail |
|------|--------|
| **Purpose** | Agent inget preferensi user per sesi |
| **User Story** | "Gua gak suka format panjang" → setelah itu agent pake format pendek |
| **Constraint** | Hanya per session (gak permanen) atau simpan ke Firestore per user+guild |
| **Implementation** | Inject preference cue ke prompt dari `_build_context()` |
| **Tool name** | N/A (otomatis via `_build_context`) |

### 5. Auto-Fix (Self-Healing)

| Item | Detail |
|------|--------|
| **Purpose** | Kalo tool return error, agent coba strategi alternatif |
| **User Story** | "Buat channel #general" → "Channel already exists" → agent pake rename |
| **Constraint** | Max 2 retries per step |
| **Implementation** | Di `_execute_step()`: kalo error, append hint ke step prompt dan re-invoke |
| **Tool name** | N/A (otomatis di `_execute_step`) |

### 6. Custom Command Creator

| Item | Detail |
|------|--------|
| **Purpose** | Agent bisa bikin command Discord baru dari deskripsi natural language |
| **User Story** | "Bikin command /ping yang reply Pong!" → agent bikin slash command |
| **Complexity** | **High** — butuh dynamic command registration. Firestore-backed. |
| **Constraint** | Basic commands only (no subcommands). Butuh restart bot buat sync slash. |
| **Implementation** | Simpan ke Firestore → Cog khusus `dynamic_commands.py` → sync on startup |
| **Tool name** | `create_command`, `delete_command`, `list_commands` |

---

## Priority Matrix

| Feature | Effort | Impact | Priority |
|---------|--------|--------|----------|
| Auto-Fix | **Low** (1-2h) | High | **P0** |
| Feedback Loop | **Low** (2-3h) | Medium | **P1** |
| Run Code | **Medium** (4-6h) | High | **P1** |
| Web Browsing | **Medium** (4-8h) | Medium | **P2** |
| Memory Compression | **Low** (2-4h) | High | **P2** |
| Custom Command Creator | **High** (16-24h) | High | **P3** |

---

## Workflow

### P0: Auto-Fix (Next)

```
User Request
    ↓
Agent selects tool + generates params
    ↓
_execute_step() runs tool
    ↓  error?
┌─── yes ──→ Append error + fix hint to step
│                ↓
│           Re-invoke LLM with original prompt + error context
│                ↓
│           Agent generates new params / different tool
│                ↓
│           Retry (max 2x)
│                ↓
│           success? → continue, else → respond with error
│
└─── no ───→ Continue to next step
```

### P1: Feedback Loop

```
User says "gak suka format panjang"
    ↓
Parse intent via regex/keywords
    ↓
Simpan preference ke session dict
    ↓
_build_context() injects preference ke system prompt
    ↓
Agent generates response sesuai preference
```

### P1: Run Code

```
Agent decides to run code
    ↓
Sanitize input: strip dangerous imports (os, subprocess, etc.)
    ↓
exec() in isolated namespace
    ↓
Capture stdout + stderr (max 4096 chars)
    ↓
Return result to LLM
    ↓
LLM interprets output and responds
```

### P2: Web Browsing

```
Agent decides to browse
    ↓
Fetch URL via httpx/aiohttp
    ↓
Extract readable content via BeautifulSoup
    ↓
Truncate to max 10000 chars
    ↓
Return content to LLM
    ↓
LLM summarizes / answers based on content
```

### P2: Memory Compression

```
Conversation reaches turn 18 (2 before limit)
    ↓
Summarize oldest 10 turns via LLM
    ↓
Store summary as single compressed entry
    ↓
Drop oldest 10 raw entries
    ↓
Continue with 11 remaining slots
```

### P3: Custom Command Creator

```
User: "Bikin command /greet yang reply Halo!"
    ↓
Agent validates command name + description
    ↓
Store in Firestore collection `custom_commands`
    ↓
Signal bot via control_queue untuk reload
    ↓
DynamicCommandsCog sync saat startup
    ↓
Slash command terdaftar (butuh restart → 5-10s downtime)
```

---

## Progress Tracking

| Feature | Status | Target |
|---------|--------|--------|
| Auto-Fix | ❌ Not started | P0 |
| Feedback Loop | ❌ Not started | P1 |
| Run Code | ❌ Not started | P1 |
| Web Browsing | ❌ Not started | P2 |
| Memory Compression | ❌ Not started | P2 |
| Custom Command Creator | ❌ Not started | P3 |

---

## Files Terkait

| File | Perubahan |
|------|-----------|
| `backend/cogs/ai_agent/agent_cog.py` | `_execute_step()` — auto-retry logic |
| `backend/cogs/ai_agent/agent_cog.py` | `_build_context()` — inject preference |
| `backend/cogs/ai_agent/agent_tools.py` | + `run_code`, + `web_browse`, + `create_command` |
| `backend/cogs/ai_agent/agent_tools.py` | `parse_tool_call()` — update regex |
| `backend/cogs/ai_chat/` | Web browsing (reuse `web_search.py`) |
| `backend/cogs/dynamic_commands.py` | **New file** — dinamik slash command cog |
| `backend/utils/sandbox.py` | **New file** — safe exec sandbox |
