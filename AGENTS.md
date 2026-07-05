# AGENTS.md — Synapse Discord Bot

## Two processes

Bot worker (`backend/main.py`) + Flask dashboard (`backend/web/web_app.py`) run simultaneously via `honcho start -f Procfile`. The web process serves from `frontend/static/` + `frontend/templates/`.

- Bot only: `python backend/main.py` (loads `.env` from `backend/.env`, inserts project root into `sys.path`)
- Web production: `gunicorn backend.web.web_app:app` (2 workers, 120s timeout)
- Both: `honcho start -f Procfile`

## Bot specifics

- **Prefix `!`** alongside slash commands (hybrid, discord.py 2.7.1). Slash commands sync on `on_ready`.
- **Cog auto-load**: `os.walk` on `backend/cogs/`. Skips `__init__.py` and `firebase_setup.py`. Any `.py` with a `setup()` function is loaded.
- **Memory monitor**: Railway free tier is 512MB. The bot reads `/proc/self/status` VmRSS every 5 min and triggers `gc.collect()` when RSS exceeds 300MB. (`backend/main.py:108-136`)
- **Spam engine**: Regex-based (gambling keywords, URL shorteners) + account age heuristics. Score ≥5 triggers action. 3-strike escalation: timeout → kick → ban. (`backend/utils/spam_engine.py`)
- **Console language**: Mixed Indonesian + English (output and comments).

## Firestore quirks

- **Writes are debounced** (default 30s coalesce, env `FIRESTORE_DEBOUNCE`) and **circuit-broken** on 429 errors (default 15min cooldown, env `FIRESTORE_CIRCUIT_SEC`).
- **Never call Firestore methods directly in async context.** The `firebase_admin` client is synchronous — all writes go through `asyncio.to_thread()`.
- Firebase key modes: base64 string, raw JSON string, or file path (searched in multiple directories).
- Some web endpoints create fresh event loops (`asyncio.new_event_loop()`) to call async code from Flask sync context. (`backend/web/web_app.py:1235`, `backend/utils/firestore_stats.py:463`)

## Dashboard (Flask)

- Discord OAuth2 requires `identify` + `guilds` scopes. Guild access filtered to `ADMINISTRATOR` or `MANAGE_GUILD`.
- Server-side sessions via `Flask-Session` (filesystem).
- `MAX_CONTENT_LENGTH = 50MB`. Images >400KB are auto-compressed before storing as base64 data URLs in Firestore.
- `PYTHONPATH=/app` set via Dockerfile (important for `backend.` imports).

## AI Chat fallback chain

`Gemini → Groq (Llama 3.3) → OpenRouter` — each failure bumps to the next provider.

## Environment

`.env` in `backend/.env`. Required: `TOKEN_BOT`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_REDIRECT_URI`, `FLASK_SECRET_KEY`, `FIREBASE_KEY`. AI requires at least one of `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`.

## No tests / no lint / no CI

Zero test files, no pytest, no lint, no typecheck, no formatter, no CI workflows. The only quality check is manual.

## Deployment

Railway via `railway.json`. Runs `honcho start -f Procfile` inside `python:3.11-slim`. Docker installs `curl` + `unzip` (for potential debugging). Health pinged by UptimeRobot every 5 min.
