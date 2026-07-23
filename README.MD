<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=28&duration=3000&pause=1000&color=5865F2&center=true&vCenter=true&width=500&lines=%F0%9F%A7%A0+Synapse+Discord+Bot;AI-Powered+%E2%80%A2+Modular+%E2%80%A2+Smart" alt="Synapse Bot" />
  <br/>
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/discord.py-2.7.1-5865F2?logo=discord&logoColor=white" />
  <img src="https://img.shields.io/badge/Flask-3.1.3-000000?logo=flask&logoColor=white" />
  <img src="https://img.shields.io/badge/Firebase-Firestore-FFCA28?logo=firebase&logoColor=black" />
  <img src="https://img.shields.io/badge/ChromaDB-Vector-6C5CE7" />
  <br/>
  <a href="#-features-at-a-glance">Features</a> •
  <a href="#-tech-stack">Stack</a> •
  <a href="#-ai-chat-architecture">AI</a> •
  <a href="#-project-structure">Structure</a> •
  <a href="#-dashboard-routes">Dashboard</a> •
  <a href="#%EF%B8%8F-whats-new">What's New</a>
</p>

<div align="center">
  <sub>⚡ Multifunctional AI-powered Discord bot with web dashboard, 5-tier AI fallback, RAG knowledge base, voice rooms, anti-nuke, moderation & more.</sub>
</div>

<br/>

---

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&color=gradient&height=2&section=header&animation=twinkling" width="100%">
</p>

## ✨ Features at a Glance

| Category | Features |
|----------|----------|
| 🤖 **AI Chat** | 5-tier fallback: Gemini → Groq → Mistral → Cohere → OpenRouter · Streaming via `/ask` · RAG knowledge base with ChromaDB vector search · Web search · Intent routing + few-shot · Chain-of-Thought · Multi-turn conversation |
| 🛡️ **Moderation** | Heuristic spam scoring (URLs, keywords, homoglyphs) · 3-layer image spam detection (Gemini Vision + Google OCR) · 3-strike system (timeout → kick → ban) · New account detection · Raid protection · AI borderline analysis |
| 📊 **Web Dashboard** | Real-time server stats · Full per-guild config · RAG document upload · Message builder · i18n (ID/EN) · Discord OAuth2 |
| 🎮 **Community** | Leveling & XP with rank cards · Dual-style welcome (embed/banner) · Leave/ban/boost announcements · Boost tracker · Auto-responder · Photobox · Donation tracking |
| 🚨 **Anti-Nuke** | Sliding window detection (mass ban/kick/channel/role) · Auto-lockdown (@everyone deny send_messages) · Auto-restore · Whitelist (admin/user/role) · AI post-analysis via OpenRouter · Dashboard settings |
| 🎛️ **Voice Interface** | Join `➕ Create Caffee'` → auto-create `🗣️ {user}'s Caffee` · Button control panel via `✨・interface` · Rename, Privacy menu (Lock/Unlock/Hide/Show/Chat), Limit, Waiting, Trust, Block, Kick, Invite, Region, Delete · 🔐 Password protection (`/voice-password`, `/join`) · Auto-delete when empty · User preference persistence · Guild config (`/voice-config`, dashboard) · Commands: `/voice-info`, `/voice-bitrate`, `/find`, `/voice-reset`, `/dashboard` · ⭐ Premium: Claim & Transfer |
| ⚙️ **Server Setup** | `/setup` command · 7 categories, 21 channels · Permission presets · Live member stats · AFK channel · Auto-enable features |
| ⭐ **Premium** | Monthly ($3 / Rp 50k) & Yearly ($25 / Rp 400k) · Saweria/Sociabuzz webhook auto-activation · DM notification · Auto-expiry cleanup · Claim & Transfer in voice rooms |

---

## 🏗️ Tech Stack

<p align="center">
  <img src="https://skillicons.dev/icons?i=python,flask,firebase,docker,github,linux&theme=dark" />
</p>

| Layer | Technology |
|-------|-----------|
| ⚙️ **Runtime** | Python 3.11 |
| 🎮 **Bot Library** | discord.py 2.7.1 |
| 🌐 **Web Server** | Flask 3.1.3 + Gunicorn |
| 🗄️ **Primary DB** | Firebase Firestore (free tier) |
| 🔍 **Vector DB** | ChromaDB (persistent, file-based) |
| 🤖 **AI Providers** | Gemini · Groq · Mistral · Cohere · OpenRouter |
| 🖼️ **Image Processing** | Pillow, easy-pil |
| 🛡️ **Anti-Spam** | Heuristic scoring + pHash + Google Cloud Vision OCR |
| 🔐 **Sessions** | Flask-Session (server-side filesystem) |
| 🚀 **Deployment** | Docker → Railway / Render + UptimeRobot |

---

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&color=gradient&height=2&section=header&animation=twinkling" width="100%">
</p>

## 🧠 AI Chat Architecture

```
                    ┌──────────────┐
                    │  User Query  │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  Intent  │ │  RAG    │ │  Web    │
        │  Router  │ │ Vector  │ │ Search  │
        └──────────┘ │  Search │ └──────────┘
                     └──────────┘
                           │
                    ┌──────▼──────┐
                    │   System    │
                    │   Prompt    │
                    │ (Few-shot + │
                    │  CoT + RAG) │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  Gemini  │ │  Groq   │ │ Mistral  │
        │  (Tier1) │ │ (Tier2) │ │ (Tier3)  │
        └──────────┘ └──────────┘ └──────────┘
              │            │            │
        ┌──────────┐ ┌──────────┐ ┌────────────┐
        │  Cohere  │ │OpenRouter│ │  Fallback  │
        │ (Tier4)  │ │ (Tier5)  │ │  Handler   │
        └──────────┘ └──────────┘ └────────────┘
                           │
                    ┌──────▼──────┐
                    │   Response  │
                    │  (Streaming │
                    │  or Batch)  │
                    └─────────────┘
```

### 🔁 Fallback Chain

| Tier | Provider | Model | Condition |
|------|----------|-------|-----------|
| 1️⃣ | **Gemini** | `gemini-3.6-flash` | Primary — circuit breaker after 3 consecutive fails (2h cooldown), 200 requests reserved for vision |
| 2️⃣ | **Groq** | Llama 3.3 70B | Backup — used when Gemini is down or over quota |
| 3️⃣ | **Mistral** | open-mistral-nemo | Third tier |
| 4️⃣ | **Cohere** | command-a-03-2025 | Fourth tier |
| 5️⃣ | **OpenRouter** | Auto-prioritize free models | Last resort — also used for image analysis when Gemini is unavailable |

---

## 📁 Project Structure

```
discord-bot/
├── backend/
│   ├── cogs/                    # Discord bot modules (auto-loaded via os.walk)
│   │   ├── ai_chat/             # 🤖 AI Chat (5-tier + RAG + web search)
│   │   │   ├── providers/       #   └─ Modular providers per API
│   │   │   ├── ai_chat.py       #   └─ Main cog: orchestrator, rate limits, history
│   │   │   ├── prompt.py        #   └─ System prompts + few-shot + CoT
│   │   │   ├── chat_enhancer.py #   └─ User prefs, server context
│   │   │   └── web_search.py    #   └─ Web search integration
│   │   ├── anti_nuke/           # 🚨 Anti-nuke protection
│   │   ├── auto_response/       # 💬 Keyword auto-responder
│   │   ├── ban_settings/        # 🚫 Ban announcements
│   │   ├── boost/               # 📈 Boost tracker
│   │   ├── boost_announce/      # 🎉 Boost announcements
│   │   ├── database/            # 🔥 Firebase Firestore init
│   │   ├── general/             # ⚙️ /setup, server stats, ping
│   │   ├── help/                # ❓ Paginated help menu
│   │   ├── leave_settings/      # 👋 Leave announcements
│   │   ├── leveling/            # ⭐ XP/Leveling with rank cards
│   │   ├── moderation/          # 🛡️ Spam + image spam + raid protection
│   │   ├── photobox/            # 📸 Browser-capture photos
│   │   ├── voice_interface/     # 🎛️ Temp voice rooms + control panel
│   │   └── welcome/             # 🎊 Welcome embed/banner
│   ├── utils/                   # 🔧 Shared helpers
│   │   ├── rag_engine.py        #   └─ RAG chunking + vector & keyword search
│   │   ├── rag_vector.py        #   └─ ChromaDB wrapper + Gemini embedding
│   │   ├── spam_engine.py       #   └─ Heuristic spam scoring
│   │   ├── image_spam.py        #   └─ Perceptual hash + OCR detection
│   │   ├── intent_router.py     #   └─ AI chat intent classification
│   │   ├── firestore_stats.py   #   └─ Debounced, circuit-broken Firestore writes
│   │   ├── formatters.py        #   └─ Uptime formatter
│   │   ├── constants.py         #   └─ Bot constants
│   │   ├── auto_responder_store.py # └─ Auto-responder Firestore CRUD
│   │   └── logger.py            #   └─ Rotating file + stdout logger
│   ├── web/                     # 🌐 Flask dashboard
│   │   ├── web_app.py           #   └─ 70+ routes, OAuth2, settings pages
│   │   └── translations/        #   └─ i18n JSON files
│   ├── scripts/                 # 🛠️ Utility scripts
│   │   └── backup_firestore.py  #   └─ Firestore backup & restore CLI
│   └── main.py                  # 🚀 Bot entrypoint
├── frontend/
│   ├── pages/                   # 📄 Jinja2 HTML pages
│   └── static/                  # 🎨 CSS, JS, fonts
├── data/
│   └── chroma_db/               # 📊 ChromaDB vector store (gitignored)
├── control_queue/               # 📨 Dashboard → bot IPC
├── flask_session/               # 🔐 Session storage (gitignored)
├── Dockerfile                   # 🐳 Production image
├── Procfile / Procfile.dev      # 📋 Honcho process definitions
├── railway.json                 # 🚄 Railway deploy config
└── antigravity_agent_plan.md    # 🤖 Antigravity agent integration plan
```

---

## 🫨 What's New

<details open>
<summary><b>🔽 Click to expand latest updates</b></summary>

<br/>

### 🎛️ Voice Interface — Complete Overhaul

| Update | Detail |
|--------|--------|
| **Privacy Menu** | 🔒 Lock · 🔓 Unlock · 🙈 Hide · 👁️ Show · 💬 Open Chat · 🔕 Close Chat — all in 1 select menu |
| **Password Protection** | 🔐 `/voice-password <set/clear>` to protect room · `/join <password>` to join · Auto-kick on join without password · Trusted users bypass |
| **User Preference Persistence** | Room settings (lock, hide, waiting, limit, region) saved per user — restored on next room creation |
| **Guild Config** | `/voice-config`, name template & target category stored in Firestore — editable via dashboard |
| **Commands** | `/voice-info` (room status) · `/voice-bitrate` (change bitrate) · `/find` (search rooms) · `/voice-reset` (reset to default) · `/dashboard` (dashboard link) |
| **Per-Guild Interface** | Interface only appears in guilds with `➕ Create Caffee'` trigger channel |
| **Auto-Delete Room** | Owner leave + empty → immediate delete · Empty for 10s → auto delete |
| **Read-Only Interface** | User messages in `✨・interface` auto-deleted · Ephemeral responses auto-dismiss after 8s |
| **Duplicate Cleanup** | On restart, `_ensure_interface` searches channel history, deletes duplicate embeds, keeps only the latest |
| **Category Fallback** | New rooms created in trigger channel's category by default; override via `/voice-config` or dashboard |
| **Debug Logging** | Added logging to `on_voice_state_update`, `_create_room`, `_ensure_interface` |

### 🧾 Announcement Text Enhancement

| Cog | Change |
|-----|--------|
| 👋 Welcome | Description uses `-#` formatted text (larger, more prominent) |
| 👋 Leave | Description uses `-#` formatted text |
| 🚫 Ban | Description uses `-#` formatted text |
| 🎉 Boost | Description uses `-#` formatted text |

### ⚙️ /setup Enhancement

- Post-setup interface initialization — voice control panel auto-sent after `/setup` completes
- Interface message updated when `/setup` re-run

### 🤖 Antigravity Agent Plan

- New integration plan for **Antigravity** (Google AI agent model via Gemini API key)
- Multi-step reasoning, tool calling, admin-only destructive actions
- `antigravity_agent_plan.md` — full architecture, tool list, rate limit strategy
- *Status: Planning phase — not yet implemented*

</details>

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- Firebase service account (Firestore free tier)
- At least one AI API key (recommended: Gemini + Groq)

### Local Development

```bash
# 1️⃣ Install dependencies
pip install -r requirements.txt

# 2️⃣ Set up environment
cp backend/.env.example backend/.env
# Edit backend/.env with your tokens and keys

# 3️⃣ Run everything (bot + web dashboard)
honcho start -f Procfile.dev

# Or run individually:
python backend/main.py              # Bot only
python -m backend.web.web_app       # Web dashboard only
```

### Production (Railway / Render)

```dockerfile
# Dockerfile builds python:3.11-slim image
# Start command: honcho start -f Procfile
```

- **Web**: `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 backend.web.web_app:app`
- **Worker**: `python backend/main.py`
- **UptimeRobot** pings every 5 min to prevent free-tier services from sleeping
- `PYTHONPATH=/app` set via Dockerfile (required for `backend.` imports)

### Firestore Backup

```bash
python backend/scripts/backup_firestore.py backup              # 📦 Backup all collections
python backend/scripts/backup_firestore.py restore <file>      # ♻️ Restore from backup
python backend/scripts/backup_firestore.py restore <file> --dry-run  # 👁️ Preview restore
python backend/scripts/backup_firestore.py list                # 📋 List backups
python backend/scripts/backup_firestore.py info <file>         # ℹ️ Backup details
```

---

## 🔐 Required Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TOKEN_BOT` | ✅ | Discord bot token |
| `DISCORD_CLIENT_ID` | ✅ | Discord OAuth2 client ID |
| `DISCORD_CLIENT_SECRET` | ✅ | Discord OAuth2 client secret |
| `DISCORD_REDIRECT_URI` | ✅ | OAuth2 callback URL |
| `FLASK_SECRET_KEY` | ✅ | Flask session encryption key |
| `FIREBASE_KEY` | ✅ | Path/JSON/base64 of Firebase service account |
| `GEMINI_API_KEY` | ⚠️ | Primary AI provider (recommended) |
| `GROQ_API_KEY` | ⚠️ | Backup AI provider (recommended) |
| `GOOGLE_VISION_API_KEY` | ❔ | OCR spam detection |
| `PUBLIC_URL` | ❔ | Photobox public URL |

For full list, see `backend/.env.example`.

---

## 🏗️ Architecture Notes

### 🔥 Firestore
- **All writes go through `asyncio.to_thread()`** — the Firebase Admin SDK is synchronous
- Debounced writes (default 30s, env `FIRESTORE_DEBOUNCE`)
- Circuit breaker on 429 errors (default 15min cooldown, env `FIRESTORE_CIRCUIT_SEC`)
- Shared across cogs via `firestore_circuit_open()` and `trip_firestore_circuit()`

### 🔍 RAG Knowledge Base
- Documents (TXT/PDF) are chunked (500 chars, 50 overlap) on upload
- Chunks stored in **Firestore** (backup + listing) + **ChromaDB** (vector search)
- Embeddings: Gemini API (`models/gemini-embedding-001`, 3072-dim, free tier)
- Fallback: hash-based embedding if Gemini is down
- Auto-sync existing docs to ChromaDB on first RAG query per guild

### 🤖 AI Chat Enhancements
- **Few-shot examples** injected per intent (coding, akademik, sains)
- **Chain-of-Thought** instruction for technical/math/logic queries
- **Token-aware history** — storage capped at 5K tokens, context capped at 8K tokens
- **Query expansion** — multiple search variants for better RAG coverage
- **Multi-turn awareness** — follow-ups reference previous conversation context

### 🛡️ Anti-Spam Architecture
```
Text Detection                    Image Detection
┌──────────────┐                  ┌──────────────┐
│ Heuristic    │                  │ L1: Rate     │
│ Scoring      │  score≥5         │ Limit (4/10s)│
│ (keywords,   │ ───────────────► │              │
│  URLs, age,  │                  │ L2: pHash   │
│  duplicates) │  score 1-4      │ + Hamming    │
│              │ ───→ AI analyze ──► Distance   │
│ L1: skip AI  │                  │              │
│ if score≥10  │                  │ L3: Gemini  │
│ or account   │                  │ Vision +    │
│ < 60d        │                  │ Google OCR  │
└──────────────┘                  └──────────────┘
        │                               │
        └─────────── Strike System ─────┘
                    ┌──────────┐
                    │ Strike 1 │ → 24h timeout
                    ├──────────┤
                    │ Strike 2 │ → Kick
                    ├──────────┤
                    │ Strike 3 │ → Ban
                    └──────────┘
              (resets after 24h clean)
```

---

## 🌐 Dashboard Routes

| Page | Route | Description |
|------|-------|-------------|
| 🏠 | `/` | Landing page — bot stats |
| 📊 | `/dashboard/<guild>/` | Server overview — real-time stats |
| 👋 | `/dashboard/<guild>/welcome` | Welcome settings with live preview |
| 👋 | `/dashboard/<guild>/welcome/leave` | Leave announcement config |
| 🚫 | `/dashboard/<guild>/welcome/ban` | Ban announcement config |
| 🎉 | `/dashboard/<guild>/welcome/boost` | Boost announce config |
| 📈 | `/dashboard/<guild>/boost` | Boost history & stats |
| 💰 | `/dashboard/<guild>/donation` | Donation history & stats |
| ⚙️ | `/dashboard/<guild>/donation/settings` | Donation webhook, messages |
| 🤖 | `/dashboard/<guild>/ai-chat` | AI Chat settings |
| 📚 | `/dashboard/<guild>/rag` | RAG document management |
| 🛡️ | `/dashboard/<guild>/anti-spam` | Spam threshold & config |
| 🚨 | `/dashboard/<guild>/anti-nuke` | Anti-nuke settings, whitelist, lockdown config |
| 🎛️ | `/dashboard/<guild>/voice` | Voice room config (name template, category) |
| 💬 | `/dashboard/<guild>/auto-responders` | Auto-responder CRUD |
| ⚡ | `/dashboard/<guild>/actions` | Level rewards & actions |
| 📝 | `/dashboard/<guild>/templates` | Message templates |
| ✏️ | `/dashboard/<guild>/message-builder` | Compose & send messages |
| 🔧 | `/dashboard/<guild>/settings` | Guild feature toggles |

---

## 🌐 i18n / Multilingual Dashboard

| Feature | Detail |
|---------|--------|
| 🗄️ **Storage** | Flask session (`session["lang"]`) — persists across login |
| 🌏 **Default** | `id` (Indonesian) |
| ✅ **Available** | `id`, `en` |
| 🔄 **Switcher** | Dropdown in landing page navbar |
| 📁 **Files** | `backend/web/translations/{lang}.json` |
| 🎨 **Template** | `{{ "key" | t }}` Jinja2 filter |
| 🔁 **Fallback** | Missing keys → `id.json` → raw key |

---

<p align="center">
  <img src="https://profile-counter.glitch.me/synapse-bot/count.svg" />
  <br/>
  <b>Proprietary — All Rights Reserved.</b>
  <br/>
  <i>© 2026 zeeinz-ux. Unauthorized use, reproduction, modification, or distribution is prohibited.</i>
</p>