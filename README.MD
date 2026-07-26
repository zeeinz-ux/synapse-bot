<div align="center">

<!-- Animated Logo Banner -->
<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=6&height=200&section=header&text=Synapse%20Bot&fontSize=60&fontColor=ffffff&animation=fadeIn&desc=AI-Powered%20Discord%20Bot&descSize=18&descAlignY=70" width="100%" alt="Synapse Bot Banner"/>

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white&style=for-the-badge)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.7.1-5865F2?logo=discord&logoColor=white&style=for-the-badge)](https://discordpy.readthedocs.io/)
[![Flask](https://img.shields.io/badge/Flask-3.1.3-000000?logo=flask&logoColor=white&style=for-the-badge)](https://flask.palletsprojects.com/)
[![Firebase](https://img.shields.io/badge/Firebase_Firestore-FFCA28?logo=firebase&logoColor=black&style=for-the-badge)](https://firebase.google.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB_Vector-6C5CE7?logo=vector&logoColor=white&style=for-the-badge)](https://www.trychroma.com/)
[![Railway](https://img.shields.io/badge/Deployed_on-Railway-0B0D0E?logo=railway&logoColor=white&style=for-the-badge)](https://railway.app/)

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=20&duration=2000&pause=500&color=5865F2&center=true&vCenter=true&width=600&lines=🚀+AI+Chat+with+5+Provider+Fallback;📊+Web+Dashboard+with+Firestore;🎮+Voice+Room+Manager;🛡️+Anti-Nuke+%26+Moderation;🧠+RAG+Knowledge+Base" alt="Feature Rotator"/>

---

**🤖 Multifunctional AI-powered Discord bot** — Chat AI, server management agent, voice rooms, anti-nuke, moderation, auto-responder, leveling, and a full web dashboard.

</div>

---

## 📋 Table of Contents

- [✨ Features](#-features)
- [📝 Commands](#-commands)
- [🧠 AI Architecture](#-ai-architecture)
- [📊 Dashboard](#-dashboard)
- [🛠️ Tech Stack](#️-tech-stack)
- [📁 Project Structure](#-project-structure)
- [🚀 Getting Started](#-getting-started)
- [🌐 Deployment](#-deployment)

---

## ✨ Features

<table>
<tr>
<td width="50%" valign="top">

### 🤖 AI Chat & Agent
- Multi‑provider AI chat (Gemini → Groq → Mistral → Cohere → OpenRouter → OpenCode Zen)
- Streaming responses (progressive message edits)
- `/ask` command + mention‑based chat
- **AI Agent** — ReAct loop with Plan → Build phases
- 18 server management tools (roles, channels, members, bans)
- Conversation memory (5 turns, 5 min TTL)
- RAG Knowledge Base (ChromaDB vector search)

### 🛡️ Moderation & Anti‑Nuke
- 3‑layer image spam detection (rate limit → pHash → Gemini Vision)
- 3‑strike system: timeout → kick → ban
- Anti‑Nuke: sliding window for mass ban/kick/channel/role operations
- Auto‑lockdown with permission restore
- AI post‑analysis via OpenRouter

</td>
<td width="50%" valign="top">

### 🎵 Voice Room Manager
- Auto‑create voice rooms on join
- Control panel with buttons (lock, hide, limit, bitrate)
- Password protection + trusted users
- User preferences persisted per user
- Auto‑delete on empty
- Guild config via `/voice-config`

### 📊 Web Dashboard
- Discord OAuth2 login (identify + guilds)
- Server stats, roles, channels analytics
- Guild‑filtered access (ADMINISTRATOR / MANAGE_GUILD)
- Flask‑Session (filesystem)
- i18n: 🇮🇩 Indonesian + 🇬🇧 English
- Auto‑compressed images for Firestore

### ⚡ Utility
- Leveling system with rank cards
- Auto‑responder (trigger → reply)
- Welcome / Leave messages
- Boost tracker
- Donation tracker (Saweria / Sociabuzz webhooks)
- PhotoBox booth

</td>
</tr>
</table>

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&color=gradient&height=2&section=header&animation=twinkling" width="100%">
</p>

---

## 📝 Commands

<details open>
<summary><b>🤖 AI Chat (<code>ai_chat</code>)</b></summary>

| Command | Description |
|---------|-------------|
| `/ask` | Tanya apa saja ke AI Synapse |
| `/rag-upload` | Upload file ke RAG Knowledge Base |
| `/rag-list` | Lihat daftar dokumen di RAG Knowledge Base |
| `/rag-delete` | Hapus dokumen dari RAG Knowledge Base |

</details>

<details>
<summary><b>🧠 AI Agent (<code>ai_agent</code>)</b></summary>

| Command | Description |
|---------|-------------|
| `/scan` | Scan seluruh server — cache data roles, channels, members, bans untuk AI Agent |
| `/agent` | AI Agent untuk bantu manage server |
| `/agent-toggle` | Aktifkan/nonaktifkan AI Agent |
| `/agent-mode` | Ubah mode akses AI Agent (owner / admin) |
| `/agent-status` | Cek status AI Agent |

**Agent Tools:** `server_info`, `list_channels`, `list_roles`, `create_channel`, `delete_channel`, `rename_channel`, `create_role`, `edit_role` (name, color, permissions, position, hoist, mentionable), `delete_role`, `assign_role`, `remove_role`, `list_members`, `ban_member`, `unban_member`, `kick_member`, `timeout_member`, `edit_channel_permissions`, `list_bans`

</details>

<details>
<summary><b>🛡️ Anti‑Nuke</b></summary>

| Command | Description |
|---------|-------------|
| `/antinuke` | Toggle Anti-Nuke protection |
| `/antinuke-whitelist` | Add/remove users/roles from whitelist |
| `/antinuke-restore` | Manually restore server permissions after lockdown |
| `/antinuke-status` | View Anti-Nuke status and config |

</details>

<details>
<summary><b>🎮 Voice Room (<code>voice_interface</code>)</b></summary>

| Command | Description |
|---------|-------------|
| `/voice-config` | Atur setting voice room (nama, kategori) |
| `/dashboard` | Buka dashboard web |
| `/voice-info` | Lihat status voice room kamu |
| `/voice-bitrate` | Ubah bitrate voice room |
| `/voice-password` | Set password untuk voice room |
| `/join` | Join voice room pake password |
| `/find` | Cari user di voice channel mana |
| `/voice-reset` | Reset setting voice room ke default |

</details>

<details>
<summary><b>⚡ Auto‑Responder</b></summary>

| Command | Description |
|---------|-------------|
| `/ar-list` | Lihat semua auto-responder di server ini |
| `/ar-add` | Tambah auto-responder baru |
| `/ar-remove` | Hapus auto-responder |
| `/ar-edit` | Edit auto-responder yang sudah ada |
| `/ar-toggle` | Aktifkan/nonaktifkan auto-responder |

</details>

<details>
<summary><b>📊 Utility (<code>general</code>, <code>leveling</code>, <code>help</code>, <code>photobox</code>, <code>boost</code>)</b></summary>

| Command | Description |
|---------|-------------|
| `/setup` | Auto-setup channel & fitur untuk server baru |
| `/voice` | Setup channel voice & interface |
| `/help` | Lihat daftar semua command atau detail command tertentu |
| `/rank` | Lihat kartu level Anda |
| `/leaderboard` | Top 10 member server |
| `/cekboost` | Cek riwayat boost user di database |
| `/testboost` | Simulasi boost untuk testing (Admin only) |
| `/photobox` | 📸 Buka photobox buat ngambil foto langsung ke channel ini! |

</details>

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&color=gradient&height=2&section=header&animation=twinkling" width="100%">
</p>

---

## 🧠 AI Architecture

```mermaid
flowchart LR
    U[User] --> ASK[/ask or Mention/]
    U --> AG[/agent/]
    
    subgraph "AI Chat"
        ASK --> P[Provider Chain]
        P --> G[Gemini 🔵]
        P --> R[Groq 🟢]
        P --> M[Mistral 🟠]
        P --> C[Cohere 🟣]
        P --> O[OpenRouter 🔴]
        P --> Z[OpenCode Zen ⚡]
        G --> |vision|IMG[Image Analysis]
    end
    
    subgraph "AI Agent"
        AG --> SC[Scan Cache]
        SC --> PLAN[Plan Phase<br/>`[PLAN]...[/PLAN]`]
        PLAN --> BUILD[Build Phase<br/>Tool Execution]
        BUILD --> TC{Validate?}
        TC -->|Valid| EXEC[Execute Tool]
        TC -->|Invalid| RETRY[Auto-Retry 3x]
        RETRY --> TC
        EXEC --> NEXT[Next Step<br/>`[SISA RENCANA]`]
        NEXT -->|More steps| BUILD
        NEXT -->|Done| RESP[Response to User]
    end
    
    subgraph "Memory & RAG"
        CM[(Conversation Memory<br/>5 turns / 5 min)]
        CH[(ChromaDB<br/>Vector Store)]
    end
    
    ASK --> CM
    AG --> CM
    ASK --> CH
```

### Provider Fallback Chain

```
Gemini (vision capable)
  └─ Circuit breaker (3 fails → skip 2h)
  └─ Daily quota reserve for vision
     ↓
  Groq / Mistral / Cohere / OpenRouter / OpenCode Zen
     ↓
  OpenRouter auto‑prioritizes free models
```

### AI Agent Features

| Feature | Detail |
|---------|--------|
| **Plan Phase** | AI creates `[PLAN]...[/PLAN]` before executing |
| **Build Phase** | Executes tools step-by-step with `[SISA RENCANA]` context |
| **Tool Validation** | Args type-checked before execution |
| **Auto-Retry** | 3 retry attempts on invalid tool calls |
| **Provider Fallback** | If primary fails, auto-switches to next provider |
| **Scan Cache** | `/scan` caches full server state → injected into AI prompts |
| **Memory** | 5-turn / 5-minute conversation memory per user |
| **Format Support** | `[TOOL_CALL]` in JSON, key=value, or raw JSON format |

---

## 📊 Dashboard

| Route | Description |
|-------|-------------|
| `/` | Landing page (live stats: servers, members, uptime) |
| `/login` | Discord OAuth2 login |
| `/dashboard` | Guild selection |
| `/dashboard/<guild_id>` | Server management: stats, roles, channels, settings |
| `/api/stats` | Bot stats JSON endpoint |

### Dashboard Features

- **Discord OAuth2** — `identify` + `guilds` scopes, filtered to ADMINISTRATOR/MANAGE_GUILD
- **i18n** — Indonesian (default) + English via `session["lang"]`
- **Session** — Flask-Session (filesystem)
- **Image compression** — Images >400KB → base64 data URLs for Firestore
- **Control Queue** — Dashboard → Bot IPC via JSON files

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&color=gradient&height=2&section=header&animation=twinkling" width="100%">
</p>

---

## 🛠️ Tech Stack

<div align="center">

| Category | Technology |
|----------|-----------|
| **Runtime** | Python 3.11 |
| **Bot Framework** | discord.py 2.7.1 |
| **Web Framework** | Flask 3.1.3 + Flask-Session |
| **Database** | Firebase Firestore (Admin SDK) |
| **Vector DB** | ChromaDB (persistent, 3072-dim Gemini embeddings) |
| **AI Providers** | Gemini, Groq, Mistral, Cohere, OpenRouter, OpenCode Zen |
| **Image Processing** | Pillow, easy-pil |
| **HTTP** | aiohttp, requests |
| **Deployment** | Railway + Docker + Honcho (Procfile) |
| **Templating** | Jinja2 (23 templates) |
| **AI Agent** | ReAct loop, Plan→Build, tool validation, auto-retry |

</div>

---

## 📁 Project Structure

```
backend/
├── main.py                    # Bot entry point, startup, task loops
├── cogs/
│   ├── ai_chat/               # AI Chat (providers, RAG, streaming)
│   │   └── providers/         # Gemini, Groq, Mistral, Cohere, OpenRouter, OpenCode Zen
│   ├── ai_agent/              # AI Agent (ReAct loop, 18 tools)
│   ├── anti_nuke/             # Anti-Nuke protection
│   ├── auto_response/         # Auto-responder system
│   ├── boost/                 # Boost tracker
│   ├── boost_announce/        # Boost announcements
│   ├── donation/              # Donation tracker
│   ├── general/               # General commands & setup
│   ├── help/                  # Help command
│   ├── leave_settings/        # Leave messages
│   ├── leveling/              # Leveling & rank cards
│   ├── moderation/            # Spam detection, image spam, word filter
│   ├── photobox/              # PhotoBox booth
│   ├── settings/              # Server settings
│   ├── templates/             # Message templates
│   └── voice_interface/       # Voice room manager
├── web/
│   ├── web_app.py             # Flask app (70+ routes)
│   └── language/              # i18n translations (id.json, en.json)
└── utils/
    ├── firestore_stats.py     # Firestore stats & circuit breaker
    ├── formatters.py          # Uptime & data formatters
    └── ...

frontend/
├── pages/                     # Jinja2 templates (base, landing, dashboard, photobox)
│   ├── dashboard/             # Dashboard pages per guild
│   └── partials/              # Navbar, footer, SVG icons
└── static/
    ├── css/                   # landing.css, navbar.css, sidebar.css, footer.css, dashboard.css
    ├── js/                    # landing.js, navbar.js, footer.js, dashboard.js, stars.js
    └── images/                # Logos, banners
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- Discord Bot Token + Client ID/Secret
- Firebase service account key
- At least one AI API key (Gemini / Groq / Mistral / Cohere / OpenRouter / OpenCode Zen)

### Installation

```bash
# Clone repository
git clone https://github.com/zeeinz-ux/synapse-bot.git
cd synapse-bot

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp backend/.env.example backend/.env
# Edit backend/.env with your tokens & keys

# Run both bot + web (dev)
honcho start -f Procfile.dev

# Run bot only
python backend/main.py

# Run web only
python -m backend.web.web_app
```

### Required Environment Variables

```
TOKEN_BOT=<discord bot token>
DISCORD_CLIENT_ID=<oauth2 client id>
DISCORD_CLIENT_SECRET=<oauth2 client secret>
FLASK_SECRET_KEY=<session secret>
FIREBASE_KEY=<base64/raw JSON/path to firebase key>
```

**AI Keys (at least one required):**
`GEMINI_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `COHERE_API_KEY`, `OPENROUTER_API_KEY`, `OPENCODE_ZEN_API_KEY`

---

## 🌐 Deployment

The bot deploys on **Railway** via `railway.json`. The Dockerfile uses `python:3.11-slim` and runs both processes (bot + web) via `honcho start -f Procfile`.

```bash
# Docker
docker build -t synapse-bot .
docker run -p 5000:5000 --env-file backend/.env synapse-bot
```

---

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=6&height=120&section=footer&text=🚀%20Built%20with%20%E2%9D%A4%EF%B8%8F&fontSize=24&fontColor=ffffff" width="100%" alt="Footer"/>
  <br/>
  <sub>
    <a href="https://synapse-bot-dk9u.onrender.com/">🌐 Website</a> •
    <a href="https://discord.gg/synapse">💬 Support Server</a> •
    <a href="https://discord.com/oauth2/authorize?client_id=1505849571039907900&permissions=8&integration_type=0&scope=bot%20applications.commands">📄 Invite Bot</a>
  </sub>
</p>
