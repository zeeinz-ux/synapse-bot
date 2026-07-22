# AGENTS.md — Synapse Discord Bot

## Two processes

Bot worker (`backend/main.py`) + Flask dashboard (`backend/web/web_app.py`) run simultaneously.

- **Both**: `honcho start -f Procfile` (production) or `honcho start -f Procfile.dev` (local)
- **Bot only**: `python backend/main.py` (loads `.env` from `backend/.env`, inserts project root into `sys.path`)
- **Web only (dev)**: `python -m backend.web.web_app`
- **Web production**: `gunicorn backend.web.web_app:app` (2 workers, 120s timeout)

## Bot specifics

- **Prefix `!`** alongside slash commands (hybrid, discord.py 2.7.1). Slash commands sync on `on_ready`.
- **Cog auto-load**: `os.walk` on `backend/cogs/`. Skips `__init__.py` and `firebase_setup.py`. Any `.py` with a `setup()` function is loaded.
- **Memory monitor**: Railway free tier is 512MB. Reads `/proc/self/status` VmRSS every 5 min, triggers `gc.collect()` when RSS exceeds 300MB. (`backend/main.py:188-208`)
- **Control queue**: Dashboard sends Discord messages via JSON files in `control_queue/` — consumed every 5s by the bot. (`backend/main.py:95-186`)
- **Console language**: Mixed Indonesian + English (output and comments).

## Firestore quirks

- **Writes are debounced** (default 30s, env `FIRESTORE_DEBOUNCE`) and **circuit-broken** on 429 errors (default 15min cooldown, env `FIRESTORE_CIRCUIT_SEC`).
- **Never call Firestore methods directly in async context.** The `firebase_admin` client is synchronous — all writes go through `asyncio.to_thread()`.
- Firebase key modes: base64 string, raw JSON string, or file path (searched in multiple directories).
- Some web endpoints create fresh event loops (`asyncio.new_event_loop()`) to call async code from Flask sync context. (`backend/web/web_app.py`, `backend/utils/firestore_stats.py:463`)
- Other cogs can check `firestore_circuit_open()` / call `trip_firestore_circuit()` from `firestore_stats` to share the circuit breaker.

## AI Chat fallback chain

`Gemini → Groq → Mistral → Cohere → OpenRouter` (5 tiers). Gemini has a circuit breaker (3 consecutive fails → skip for 2h) and a daily quota reserve (200 requests reserved for Vision). Image analysis is Gemini-only — if Gemini fails, image features are unavailable. OpenRouter auto-prioritizes free models (fetched from API on startup, hardcoded fallback if fetch fails). (`backend/cogs/ai_chat/` — providers split into `providers/gemini.py`, `providers/groq.py`, `providers/mistral.py`, `providers/cohere.py`, `providers/openrouter.py`)

## Dashboard (Flask)

- Discord OAuth2 requires `identify` + `guilds` scopes. Guild access filtered to `ADMINISTRATOR` or `MANAGE_GUILD`.
- Server-side sessions via `Flask-Session` (filesystem).
- `MAX_CONTENT_LENGTH = 50MB`. Images >400KB are auto-compressed before storing as base64 data URLs in Firestore.
- `PYTHONPATH=/app` set via Dockerfile (important for `backend.` imports).
- i18n: session-based (`session["lang"]`), defaults to `id` (Indonesian). Jinja2 filter `{{ "key" | t }}`. Fallback chain: requested lang → `id.json` → raw key. Translation files in `backend/web/translations/`.

## Environment

`.env` in `backend/.env`. Required: `TOKEN_BOT`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_REDIRECT_URI`, `FLASK_SECRET_KEY`, `FIREBASE_KEY`. AI requires at least one of `GEMINI_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `COHERE_API_KEY`, `OPENROUTER_API_KEY`.

## No tests / no lint / no CI

Zero test files, no pytest, no lint, no typecheck, no formatter, no CI workflows. The only quality check is manual.

## Deployment

Railway via `railway.json`. Runs `honcho start -f Procfile` inside `python:3.11-slim`. Docker installs `curl` + `unzip` (for potential debugging). Health pinged by UptimeRobot every 5 min.
