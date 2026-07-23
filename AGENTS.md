# AGENTS.md — Synapse Discord Bot

**Gitignored** — commit with `git add -f AGENTS.md`.

## Run

| Mode | Command |
|------|---------|
| Both (dev) | `honcho start -f Procfile.dev` |
| Both (prod) | `honcho start -f Procfile` |
| Bot only | `python backend/main.py` |
| Web only | `python -m backend.web.web_app` |

`.env` lives in `backend/.env`. Required: `TOKEN_BOT`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `FLASK_SECRET_KEY`, `FIREBASE_KEY`. AI needs at least one of `GEMINI_API_KEY`/`GROQ_API_KEY`/`MISTRAL_API_KEY`/`COHERE_API_KEY`/`OPENROUTER_API_KEY`.

## Bot quirks

- **Hybrid commands**: prefix `!` + slash. Slash sync on `on_ready`.
- **Cog auto-load**: `os.walk` on `backend/cogs/`. Skips `__init__.py` and `firebase_setup.py`. Loads any `.py` with `setup()`.
- **Intents**: `message_content`, `members`, `moderation`, `voice_states` all enabled in `main.py:47-51`.
- **Memory monitor**: reads `/proc/self/status` VmRSS every 5 min, triggers `gc.collect()` if >300MB (`main.py:218-238`).
- **Stats updater**: `tasks.loop(seconds=30)` updates Firestore stats + guild channels/roles (`main.py:291-324`).
- **Control queue**: dashboard → bot IPC via JSON files in `control_queue/`, consumed every 5s. Actions: `send_message`, `refresh_rag_cache`, `refresh_settings_cache` (`main.py:96-216`).
- **Cookies**: `COOKIES_CONTENT` env var auto-written to `cookies/cookies.txt` at startup (`main.py:31-41`).
- **Console language**: mixed Indonesian + English.

## Firestore (Firebase Admin SDK)

- **Never call Firestore directly in async context** — SDK is synchronous. All writes through `asyncio.to_thread()`.
- **Debounced** (default 30s, env `FIRESTORE_DEBOUNCE`). **Circuit breaker** on 429 (default 15min, env `FIRESTORE_CIRCUIT_SEC`).
- Firebase key modes: base64 string, raw JSON string, or file path (searched in multiple dirs).
- Web endpoints create fresh event loops (`asyncio.new_event_loop()`) from Flask sync context.
- Shared circuit breaker: `firestore_circuit_open()` / `trip_firestore_circuit()` from `backend/utils/firestore_stats.py`.

## AI Chat fallback chain

`Gemini → Groq → Mistral → Cohere → OpenRouter` (5 tiers in `backend/cogs/ai_chat/providers/`).

- Gemini default model: `gemini-3.6-flash`. Circuit breaker (3 consecutive fails → skip 2h) + daily quota reserve (200 requests for Vision).
- Image analysis: Gemini-only (`gemini-3.6-flash` used for both text and vision). If Gemini down, image features unavailable.
- OpenRouter: auto-prioritizes free models (fetched from API on startup, hardcoded fallback).
- Streaming: `/ask` command uses progressive message edits (~1s interval). Mention-based chat uses batch mode.
- Intent router (`backend/utils/intent_router.py`) + web search (`web_search.py`) integrated in `ai_chat.py`.

## RAG / Vector Search

- ChromaDB (persistent, file-based at `data/chroma_db/`). Path overridable via `CHROMA_DB_PATH` env.
- Embedding: Gemini API (`models/gemini-embedding-001`, 3072-dim). Fallback: hash-based embedding.
- If `chromadb` import fails at startup, vector features are gracefully disabled (`rag_vector.py:11-15`).

## Dashboard (Flask)

- Discord OAuth2: `identify` + `guilds`. Guild access filtered to `ADMINISTRATOR` or `MANAGE_GUILD`.
- Sessions: Flask-Session (filesystem). Session storage in `backend/flask_session/` (gitignored).
- `MAX_CONTENT_LENGTH = 50MB`. Images >400KB auto-compressed to base64 data URLs for Firestore.
- `PYTHONPATH=/app` set via Dockerfile (required for `backend.` imports in production).
- i18n: session-based (`session["lang"]`), defaults to `id`. Jinja2 filter `{{ "key" | t }}`. Fallback: requested lang → `id.json` → raw key. Translations in `backend/web/translations/`.

## Moderation (spam)

- 3-layer image spam: rate limit (4/10s) → pHash + Hamming → Gemini Vision + Google Cloud Vision OCR.
- 3-strike system: timeout (24h) → kick → ban. Resets after 24h clean.
- Spam engine, image spam, intent router all in `backend/utils/`.

## Anti-Nuke (`backend/cogs/anti_nuke/anti_nuke.py`)

- Sliding window (default 10s) on destructive actions: mass ban/kick, channel/role create/delete, admin perm grants, webhook spam.
- Admins auto-exempt. Configurable user/role whitelist via `!antinuke-whitelist`.
- Lockdown: denies `send_messages`, `add_reactions`, `create_instant_invite` on @everyone for all channels. Auto-restores after `lockdown_duration` (default 30 min).
- AI post-analysis: fire-and-forget to OpenRouter free model pool after lockdown.
- Config in Firestore: `guild_settings/{guild_id}/anti_nuke`.

## Firestore Backup

```bash
python backend/scripts/backup_firestore.py backup       # all collections
python backend/scripts/backup_firestore.py restore <file> [--dry-run]
python backend/scripts/backup_firestore.py list
python backend/scripts/backup_firestore.py info <file>
```

## Build / test / lint / CI

None. Zero tests, no pytest, no lint, no typecheck, no formatter, no CI. Manual verification only.

## Deployment

Railway via `railway.json`. Dockerfile: `python:3.11-slim`, `CMD honcho start -f Procfile`. UptimeRobot health ping every 5 min.
