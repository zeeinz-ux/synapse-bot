# AGENTS.md — Synapse Discord Bot

## Two processes

- **Bot worker** — `backend/main.py`. Run with `python backend/main.py`. Loads `.env` from `backend/.env`. Inserts project root into `sys.path` at startup.
- **Web dashboard** — `backend/web/web_app.py` (Flask). Serves `frontend/templates/` + `frontend/static/`. Production entrypoint: `gunicorn backend.web.web_app:app`.
- Both run simultaneously via `honcho start -f Procfile` (`web:` + `worker:` lines).

## Firestore quirks

- Firestore writes are **debounced** (default 30s coalesce) and **circuit-broken** on 429 errors (default 15min cooldown). Tune via env vars `FIRESTORE_DEBOUNCE` and `FIRESTORE_CIRCUIT_SEC`.
- All writes use `asyncio.to_thread()` — the `firebase_admin` client is synchronous, never call Firestore methods directly in async context.
- Firebase key modes: base64 string, raw JSON string, or file path (searched in multiple directories).

## AI Chat fallback chain

`Gemini → Groq (Llama 3.3) → OpenRouter` — each failure bumps to the next provider.

## Cog loading

Cogs are auto-loaded via `os.walk` on `backend/cogs/`. Any `.py` with a `setup()` function is loaded. Files named `firebase_setup.py` are explicitly skipped.

## Environment

`.env` file goes in `backend/.env` (loaded manually in `web_app.py` too). Required keys: `TOKEN_BOT`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_REDIRECT_URI`, `FLASK_SECRET_KEY`, `FIREBASE_KEY`. AI Chat requires at least one of `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`.

## Commands

| Action | Command |
|--------|---------|
| Local dev (bot only) | `python backend/main.py` |
| Local dev (both processes) | `honcho start -f Procfile` |
| Production | Railway uses `honcho start -f Procfile` |

## No tests

Zero test files or test framework configured in the repo. No CI, lint, typecheck, or formatter config.

## Deployment

- Platform: Railway. Config in `railway.json`.
- Health: UptimeRobot pings every 5 min.
- Docker: `FROM python:3.11-slim`.
