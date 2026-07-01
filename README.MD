# Synapse — Discord Bot v4.7

A multifunctional Discord bot with a web dashboard, AI chat, moderation, leveling, and server management tools.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.11 |
| Bot Library | discord.py 2.7.1 |
| Web Server | Flask 3.1.3 + Gunicorn |
| Database | Firebase Firestore (free tier) |
| AI Chat | Google Gemini → Groq (Llama 3.3) → OpenRouter (fallback chain) |
| Sessions | Flask-Session (server-side file) |
| Deployment | Docker → Railway + UptimeRobot |

## Features

### Discord Cogs

| Cog | Description |
|-----|-------------|
| **AI Chat** | Triple API fallback (Gemini → Groq → OpenRouter), personality, temperature, channel restriction, circuit breaker, personalized mentions. |
| **Welcome** | Dual-style embed/banner auto-welcome with drag-drop image upload (Firestore base64). |
| **Leave** | Auto-leave announcement (embed/banner). |
| **Ban** | Auto-ban announcement (embed/banner). |
| **Boost Announce** | Auto-boost announcement (embed/banner). |
| **Boost Tracker** | Track boost/unboost history. |
| **Donation** | Track donation transactions. |
| **Moderation** | Spam detection with 3-strike system (timeout → kick → ban). |
| **Leveling** | XP system with rank & leaderboard. |
| **Auto-Responder** | Keyword-triggered replies with regex, cooldown, channel filters. |
| **General** | Ping, stats, help commands. |

### Web Dashboard

| Page | Description |
|------|-------------|
| `/` | Landing page with bot stats, sakura petals animation |
| `/dashboard/<guild>/` | Server overview — real-time stats |
| `/dashboard/<guild>/welcome` | Welcome settings with live preview |
| `/dashboard/<guild>/welcome/leave` | Leave announcement config |
| `/dashboard/<guild>/welcome/ban` | Ban announcement config |
| `/dashboard/<guild>/welcome/boost` | Boost announce config |
| `/dashboard/<guild>/ai-chat` | AI Chat settings |
| `/dashboard/<guild>/auto-responders` | Auto-responder manager |

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
│   ├── cogs/                  # Discord bot modules (auto-loaded by setup_hook)
│   │   ├── ai_chat/           # AI Chat with triple API fallback
│   │   ├── auto_response/     # Keyword auto-responder
│   │   ├── ban_settings/      # Ban announcement
│   │   ├── boost/             # Boost tracker
│   │   ├── boost_announce/    # Boost announcement
│   │   ├── database/          # Firebase initialization (firebase_setup)
│   │   ├── donation/          # Donation tracker
│   │   ├── general/           # Ping, stats, help
│   │   ├── leave_settings/    # Leave announcement
│   │   ├── leveling/          # XP/Leveling system
│   │   ├── moderation/        # Spam detection
│   │   └── welcome/           # Welcome cog (embed/banner)
│   ├── utils/                 # Shared helpers (formatters, constants)
│   ├── web/                   # Flask routes (web_app.py)
│   └── main.py                # Bot entrypoint (setup_hook loads cogs)
├── frontend/
│   ├── templates/             # 21 Jinja2 HTML templates
│   └── static/
│       ├── css/               # Page-specific styles
│       └── js/                # Page-specific logic
├── cookies/                   # YouTube cookies (Netscape format, optional)
├── flask_session/             # Flask-Session file storage (gitignored)
├── Dockerfile                 # Production image
├── Procfile                   # honcho: web (gunicorn) + worker (bot)
└── railway.json               # Railway deploy config
```

## Deployment

### Local development

```bash
# Install deps
pip install -r requirements.txt

# Run bot + web dashboard
honcho start -f Procfile
# or
python backend/main.py
```

### Production (Railway)

- **Build:** `Dockerfile` (Python 3.11-slim)
- **Start:** `honcho start -f Procfile`
  - `web`: gunicorn `--bind 0.0.0.0:$PORT --workers 2 --timeout 120 backend.web.web_app:app`
  - `worker`: `python backend/main.py`
- **24/7:** UptimeRobot pings every 5 min to prevent sleep

### Module path

Bot modules are loaded as `backend.cogs.<name>` (with `backend/` on `sys.path` via `PYTHONPATH=/app` in the Dockerfile + runtime injection in `main.py`).

## Environment Variables

See `backend/.env.example` for the full list. Key variables:

- `DISCORD_TOKEN`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_REDIRECT_URI`
- `FLASK_SECRET_KEY`
- `FIREBASE_KEY` (path to service account JSON, or full JSON in single line)
- `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` (at least one for AI Chat)

## License

All Rights Reserved.