# Synapse — Discord Bot

A multifunctional Discord bot with a web dashboard, AI chat (5-tier streaming + RAG), moderation with image spam detection, leveling, donation tracking, and server management tools.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.11 |
| Bot Library | discord.py 2.7.1 |
| Web Server | Flask 3.1.3 + Gunicorn |
| Database | Firebase Firestore (free tier) |
| AI Chat | Gemini → Groq → Mistral → Cohere → OpenRouter (5-tier fallback, streaming, RAG) |
| Image Processing | Pillow, easy-pil (leveling cards) |
| Anti-Spam | Heuristic scoring + average perceptual hash + Google Cloud Vision OCR |
| Sessions | Flask-Session (server-side filesystem) |
| Deployment | Docker → Railway + UptimeRobot |

## Features

### Discord Cogs

| Cog | Description |
|-----|-------------|
| **AI Chat** | 5-provider fallback with **streaming** (Gemini → Groq → Mistral → Cohere → OpenRouter), **RAG Knowledge Base** (TXT/PDF upload via dashboard, keyword search, auto-inject into context), web search, intent routing, personality, temperature, per-guild Gemini model selection, per-guild rate limits, channel restriction, circuit breaker, chat history (Firestore). |
| **Welcome** | Dual-style embed/banner auto-welcome with drag-drop image upload (Firestore base64). |
| **Leave** | Auto-leave announcement (embed/banner). |
| **Ban** | Auto-ban announcement (embed/banner). |
| **Boost Announce** | Auto-boost announcement (embed/banner). |
| **Boost Tracker** | Track boost/unboost history with stats. |
| **Moderation** | Spam detection with heuristic scoring + image spam (perceptual hash, OCR). 3-strike escalation (timeout 24h → kick → ban). New account detection with configurable action (ban/kick/timeout) and max age. |
| **Leveling** | XP system with rank card (easy-pil) & leaderboard. |
| **Auto-Responder** | Keyword-triggered replies with regex, cooldown, channel filters. |
| **Photobox** | `/photobox` command — creates a webhook + sends a link to take photos from browser directly into the channel. |
| **General** | Ping, stats, user info commands. |
| **Help** | Paginated help menu with per-command detail. |

### Image Spam Detection (3-Layer)

| Layer | Technique |
|-------|-----------|
| L1 | Image rate limit (2 images / 10s per user) |
| L2 | Average perceptual hash + Hamming distance — duplicate & known spam image matching |
| L3 | Google Cloud Vision OCR — text extraction + keyword matching on scam phrases |

### Web Dashboard

| Page | Route | Description |
|------|-------|-------------|
| Landing | `/` | Bot stats, sakura petals animation, language switcher |
| Dashboard | `/dashboard/<guild>/` | Server overview — real-time stats |
| Welcome | `/dashboard/<guild>/welcome` | Welcome settings with live preview |
| Leave | `/dashboard/<guild>/welcome/leave` | Leave announcement config |
| Ban | `/dashboard/<guild>/welcome/ban` | Ban announcement config |
| Boost | `/dashboard/<guild>/welcome/boost` | Boost announce config |
| Boost Tracker | `/dashboard/<guild>/boost` | Boost history & stats |
| Donation | `/dashboard/<guild>/donation` | Donation history & stats |
| Donation Settings | `/dashboard/<guild>/donation/settings` | Webhook URL, messages |
| AI Chat | `/dashboard/<guild>/ai-chat` | AI Chat settings (personality, temperature, model, rate limits) |
| RAG Knowledge | `/dashboard/<guild>/rag` | Upload/manage TXT/PDF documents for AI context |
| Anti-Spam | `/dashboard/<guild>/anti-spam` | Spam threshold config + new account settings |
| Auto-Responders | `/dashboard/<guild>/auto-responders` | Auto-responder CRUD |
| Actions | `/dashboard/<guild>/actions` | Level rewards & moderation actions |
| Templates | `/dashboard/<guild>/templates` | Message templates |
| Message Builder | `/dashboard/<guild>/message-builder` | Compose & send Discord messages from dashboard |
| Settings | `/dashboard/<guild>/settings` | Guild feature toggles |

### i18n / Multilingual Dashboard

The dashboard supports **session-based language switching** via JSON translation files.

| Feature | Detail |
|---------|--------|
| Storage | Flask session (`session["lang"]`) — persists across login |
| Default | `id` (Indonesian) |
| Available | `id`, `en` |
| Switcher | Dropdown in landing page navbar |
| File format | `backend/web/translations/{lang}.json` — plain key-value pairs |
| Template usage | `{% raw %}{{ "nav.home" \| t }}{% endraw %}` — Jinja2 filter |
| Fallback | Missing keys fall back to `id.json`, then return the key as-is |

Translation files live at `backend/web/translations/`. To add a new language:
1. Create `{code}.json` in that folder (copy structure from `en.json`)
2. Add a `<button data-lang="code">` in `frontend/pages/partials/navbar.html`

### Auth & Permissions

- Discord OAuth2 login (`identify` + `guilds` scopes)
- Guild sidebar filtered to servers where user has **ADMINISTRATOR** or **MANAGE_GUILD** and the bot is present
- Per-request guild access guard
- Feature-level per-guild settings in Firestore
- Guild lifecycle: auto-create settings on join, clean up on remove

## Project Structure

```
discord-bot/
├── backend/
│   ├── cogs/                  # Discord bot modules (auto-loaded via os.walk)
│   │   ├── ai_chat/           # AI Chat (5-tier streaming + RAG, web search, intent router)
│   │   │   └── providers/     # Modular providers: Gemini, Groq, Mistral, Cohere, OpenRouter
│   │   ├── auto_response/     # Keyword auto-responder
│   │   ├── ban_settings/      # Ban announcement
│   │   ├── boost/             # Boost tracker
│   │   ├── boost_announce/    # Boost announcement
│   │   ├── database/          # Firebase initialization (firebase_setup)
│   │   ├── general/           # Ping, stats, userinfo
│   │   ├── help/              # Help command
│   │   ├── leave_settings/    # Leave announcement
│   │   ├── leveling/          # XP/Leveling with rank cards
│   │   ├── moderation/        # Spam + image spam detection + new account detection
│   │   ├── photobox/          # Browser-capture photo to Discord via webhook
│   │   └── welcome/           # Welcome embed/banner
│   ├── utils/                 # Shared helpers
│   │   ├── rag_engine.py      # RAG chunking, keyword search, Firestore CRUD
│   │   ├── spam_engine.py     # Heuristic spam scoring + new account detection
│   │   ├── image_spam.py      # Perceptual hash + OCR detection
│   │   ├── intent_router.py   # AI chat intent classification
│   │   ├── auto_responder_store.py  # Auto-responder Firestore CRUD
│   │   ├── firestore_stats.py # Debounced, circuit-broken Firestore writes
│   │   ├── formatters.py      # Uptime formatter
│   │   ├── constants.py       # Bot constants
│   │   └── logger.py          # Rotating file + stdout logger
│   ├── web/                   # Flask dashboard
│   │   ├── web_app.py         # 70+ routes, OAuth2, settings pages
│   │   └── translations/      # JSON translation files (id.json, en.json, ...)
│   ├── scripts/               # Utility scripts
│   │   └── backup_firestore.py # Firestore backup & restore CLI
│   └── main.py                # Bot entrypoint (setup_hook auto-loads cogs)
├── frontend/
│   ├── pages/                 # Jinja2 HTML pages
│   │   ├── dashboard/         # Dashboard pages (extends base.html)
│   │   └── partials/          # navbar, footer, layout partials
│   └── static/
│       ├── css/               # Page-specific stylesheets
│       ├── js/                # Page-specific scripts
│       └── fonts/             # Roboto font family (variable + static)
├── control_queue/             # Inter-process message queue (dashboard → bot)
├── cookies/                   # YouTube cookies (Netscape format, optional — from env)
├── flask_session/             # Flask-Session file storage (gitignored)
├── Dockerfile                 # Production image (python:3.11-slim)
├── Procfile                   # honco: web (gunicorn) + worker (bot)
├── Procfile.dev               # Local dev Procfile
└── railway.json               # Railway deploy config
```

## Deployment

### Local development

```bash
# Install deps
pip install -r requirements.txt

# Run bot + web dashboard
honcho start -f Procfile.dev
# or just the bot:
python backend/main.py
# or web only:
python -m backend.web.web_app
```

### Production (Railway)

- **Build:** `Dockerfile` (Python 3.11-slim, installs curl + unzip)
- **Start:** `honcho start -f Procfile`
  - `web`: gunicorn `--bind 0.0.0.0:$PORT --workers 2 --timeout 120 backend.web.web_app:app`
  - `worker`: `python backend/main.py`
- **24/7:** UptimeRobot pings every 5 min to prevent sleep
- **Module path:** `PYTHONPATH=/app` set via Dockerfile + runtime injection in `main.py`

### Firestore Backup

```bash
python backend/scripts/backup_firestore.py backup       # backup all collections
python backend/scripts/backup_firestore.py restore <file> [--dry-run]
python backend/scripts/backup_firestore.py list
python backend/scripts/backup_firestore.py info <file>
```

## Environment Variables

See `backend/.env.example` for the full list. Key variables:

- `TOKEN_BOT`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_REDIRECT_URI`
- `FLASK_SECRET_KEY`
- `FIREBASE_KEY` — path to service account JSON, raw JSON string, or base64-encoded JSON
- `GEMINI_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `COHERE_API_KEY`, `OPENROUTER_API_KEY` — at least one for AI Chat (recommended: Gemini + Groq)
- `GOOGLE_VISION_API_KEY` — for OCR spam detection
- `PUBLIC_URL` — public-facing URL for photobox links
- `COOKIES_CONTENT` — optional YouTube cookies (written to `cookies/cookies.txt`)

### Firestore Tuning

| Env | Default | Description |
|-----|---------|-------------|
| `FIRESTORE_DEBOUNCE` | 30s | Write coalescing window |
| `FIRESTORE_CIRCUIT_SEC` | 900s (15 min) | Circuit breaker cooldown on 429 |
| `FIRESTORE_HASH_SALT` | synapse-v1 | Salt for dirty-check hashing |

## Architecture Notes

- **Firestore writes are debounced** (default 30s) and **circuit-broken** on 429 errors (default 15min cooldown). All writes go through `asyncio.to_thread()` — never call Firestore directly in async context.
- **AI Chat fallback chain**: Gemini → Groq → Mistral → Cohere → OpenRouter (5 tiers). Both batch and streaming modes use the same fallback chain. Circuit breaker on Gemini (3 consecutive fails → skip 2h). Gemini daily quota reserve (200 requests reserved for vision).
- **Streaming**: Real-time token-by-token response. `/ask` slash command uses streaming with progressive message edits (~1s interval). Mention-based chat uses batch mode.
- **RAG Knowledge Base**: Upload TXT/PDF documents via dashboard. Text is chunked (500 chars, 50 overlap), stored in Firestore. On each AI query, top 5 matching chunks (keyword frequency scoring) are injected into the system prompt. No embedding API cost.
- **Per-guild configuration**: Personality, temperature, Gemini model, rate limit max/window/cooldown, channel restriction — all configurable per server from the dashboard.
- **Cog auto-load**: `os.walk` on `backend/cogs/`. Skips `__init__.py` and `firebase_setup.py`. Any `.py` with a `setup()` function is loaded.
- **Memory monitor**: Reads `/proc/self/status` VmRSS every 5 min, triggers `gc.collect()` when RSS exceeds 300MB (Railway 512MB limit).
- **Control queue**: Inter-process communication via JSON files in `control_queue/`. Dashboard writes → bot consumes every 5s. Used for sending Discord messages and triggering RAG cache refreshes.
- **Prefix `!`** alongside slash commands (hybrid, discord.py). Slash commands sync on `on_ready`.
- **Console language**: Mixed Indonesian + English throughout codebase.
- **i18n**: Session-based multilingual dashboard via `backend/web/translations/*.json`. Uses a Jinja2 filter `{{ "key" | t }}` with automatic fallback to Indonesian. Add a new language by creating a JSON file + dropdown option.
- **Image uploads**: Images >400KB are auto-compressed before storing as base64 data URLs in Firestore. Max upload 50MB.
- **Anti-spam moderation**: 3-strike system (timeout 24h → kick → ban) per-guild. New accounts (< configurable max age) can be set to ban/kick/timeout directly. Configurable from dashboard anti-spam page.

## License

Proprietary — All Rights Reserved. See `LICENSE` for the full license agreement.

© 2026 zeeinz-ux. Unauthorized use, reproduction, modification, or distribution is prohibited.
