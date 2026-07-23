# AGENTS.md — Synapse Discord Bot

**File is gitignored** — `git add -f AGENTS.md` to commit changes.

## Two processes run simultaneously

| Process | Command | File |
|---------|---------|------|
| Both | `honcho start -f Procfile` (prod) or `Procfile.dev` (local) | Procfile |
| Bot | `python backend/main.py` | `backend/main.py` |
| Web (dev) | `python -m backend.web.web_app` | `backend/web/web_app.py` |
| Web (prod) | `gunicorn backend.web.web_app:app --workers 2 --timeout 120` | Procfile |

Bot loads `.env` via `load_dotenv()` at `backend/main.py:29` — `.env` lives in `backend/.env`.

## Bot quirks

- **Prefix `!`** + slash commands (hybrid, discord.py 2.7.1). Slash sync on `on_ready`.
- **Cog auto-load**: `os.walk` on `backend/cogs/`. Skips `__init__.py` and `firebase_setup.py`. Loads any `.py` with a `setup()` function.
- **Memory monitor**: Reads `/proc/self/status` VmRSS every 5 min, triggers `gc.collect()` if RSS > 300MB (Railway 512MB limit). (`backend/main.py:199-219`)
- **Control queue**: Dashboard → bot IPC via JSON files in `control_queue/`, consumed every 5s. Actions: `send_message`, `refresh_rag_cache`, `refresh_settings_cache`. (`backend/main.py:95-197`)
- **Console language**: Mixed Indonesian + English throughout.

## Firestore quirks

- **Never call Firestore directly in async context** — the `firebase_admin` client is synchronous. All writes go through `asyncio.to_thread()`.
- **Writes debounced** (default 30s, env `FIRESTORE_DEBOUNCE`) and **circuit-broken** on 429 (default 15min cooldown, env `FIRESTORE_CIRCUIT_SEC`).
- Firebase key modes: base64 string, raw JSON string, or file path (searched in multiple dirs).
- Web endpoints create fresh event loops (`asyncio.new_event_loop()`) from Flask sync context.
- Shared circuit breaker: cogs call `firestore_circuit_open()` / `trip_firestore_circuit()` from `backend/utils/firestore_stats.py`.

## AI Chat fallback chain

`Gemini → Groq → Mistral → Cohere → OpenRouter` (5 tiers). Providers in `backend/cogs/ai_chat/providers/{gemini,groq,mistral,cohere,openrouter}.py`.

- Gemini: circuit breaker (3 consecutive fails → skip 2h) + daily quota reserve (200 requests reserved for Vision).
- Image analysis: Gemini-only — if Gemini is down, image features unavailable.
- OpenRouter: auto-prioritizes free models (fetched from API on startup, hardcoded fallback).
- Streaming: `/ask` command uses progressive message edits (~1s interval). Mention-based chat uses batch mode.

## RAG / Vector Search

Uses **ChromaDB** (persistent, file-based at `data/chroma_db/`) for vector similarity search.
- Embedding: Gemini API (`models/gemini-embedding-001`, 3072-dim, free tier)
- Fallback: hash-based embedding (same dimensions) if Gemini API unavailable
- Query expansion + multi-turn history awareness in `ai_chat.py`
- Auto-sync: document upload/delete updates ChromaDB + Firestore simultaneously
- Existing docs auto-synced to ChromaDB on first RAG query per guild (`sync_existing_to_vector`)

## Prompt enhancements

- **Few-shot examples** per intent (coding, akademik, sains) injected dynamically in `prompt.py`
- **Chain-of-Thought instruction** added to all technical/math/logic prompts

## Dashboard (Flask)

- Discord OAuth2: `identify` + `guilds` scopes. Guild access filtered to `ADMINISTRATOR` or `MANAGE_GUILD`.
- Sessions: Flask-Session (filesystem).
- `MAX_CONTENT_LENGTH = 50MB`. Images >400KB are auto-compressed before storing as base64 data URLs in Firestore.
- `PYTHONPATH=/app` set via Dockerfile (required for `backend.` imports in production).
- i18n: session-based (`session["lang"]`), defaults to `id`. Jinja2 filter `{{ "key" | t }}`. Fallback: requested lang → `id.json` → raw key. Translation files in `backend/web/translations/`.

## Environment

`.env` in `backend/.env`. Required: `TOKEN_BOT`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_REDIRECT_URI`, `FLASK_SECRET_KEY`, `FIREBASE_KEY`. AI requires at least one of `GEMINI_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `COHERE_API_KEY`, `OPENROUTER_API_KEY`.

## Firestore Backup

```bash
python backend/scripts/backup_firestore.py backup       # all collections
python backend/scripts/backup_firestore.py restore <file> [--dry-run]
python backend/scripts/backup_firestore.py list
python backend/scripts/backup_firestore.py info <file>
```

## Build / test / lint / CI

None. Zero tests, no pytest, no lint, no typecheck, no formatter, no CI workflows. Manual verification only.

## Deployment

Railway via `railway.json`. Runs `honcho start -f Procfile` inside `python:3.11-slim` (Dockerfile). Health pinged by UptimeRobot every 5 min.