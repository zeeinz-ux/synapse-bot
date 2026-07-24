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

Note: `.env.example` uses lowercase `token_bot` but `main.py` reads `TOKEN_BOT`.

## Key Quirks

- **Hybrid commands**: prefix `!` + slash. Slash sync on `on_ready`.
- **Cog auto-load**: `os.walk` on `backend/cogs/`. Skips `__init__.py` and `firebase_setup.py`. Loads any `.py` with `async def setup()`.
- **Intents**: `message_content`, `members`, `moderation`, `voice_states` enabled (`main.py:47-51`).
- **Memory monitor**: reads `/proc/*/status` VmRSS every 5 min → `gc.collect()` if >300MB (`main.py:218-238`). **Linux-only** — fails silently on Windows.
- **Stats updater**: `tasks.loop(seconds=30)` — Firestore stats + guild channels/roles (`main.py:291-324`).
- **Control queue**: dashboard → bot IPC via JSON files in `control_queue/` (dir must exist), consumed every 5s. Actions: `send_message`, `refresh_rag_cache`, `refresh_settings_cache` (`main.py:100-216`).
- **Cookies**: `COOKIES_CONTENT` env var auto-written to `cookies/cookies.txt` at startup (`main.py:31-41`).
- **Console language**: mixed Indonesian + English.

## Firestore (Firebase Admin SDK)

- **Never call Firestore directly in async context** — SDK is synchronous. All writes through `asyncio.to_thread()`.
- **Debounced** (default 30s, env `FIRESTORE_DEBOUNCE`). **Circuit breaker** on 429 (default 15min, env `FIRESTORE_CIRCUIT_SEC`).
- Firebase key modes: base64 string, raw JSON string, or file path (searched in multiple dirs).
- Web endpoints and sync contexts create fresh event loops (`asyncio.new_event_loop()`) for async calls.
- Circuit breaker shared: `firestore_circuit_open()` / `trip_firestore_circuit()` (`backend/utils/firestore_stats.py`).

## AI Chat

`Gemini → Groq → Mistral → Cohere → OpenRouter` (5 providers in `backend/cogs/ai_chat/providers/`).

- Gemini: model `gemini-3.6-flash`. Circuit breaker (3 consecutive fails → skip 2h) + daily quota reserve for vision.
- **Image analysis is Gemini-only** — if Gemini is down, image features unavailable.
- OpenRouter auto-prioritizes free models (fetched from API on startup, hardcoded fallback list).
- Streaming: `/ask` uses progressive message edits (~1s). Mention-based chat uses batch mode.
- Intent router (`intent_router.py`) + web search (`web_search.py`) integrated in `ai_chat.py`.

## RAG / Vector Search

- ChromaDB persistent at `data/chroma_db/` (overridable via `CHROMA_DB_PATH` env).
- Embedding: Gemini API (`models/gemini-embedding-001`, 3072-dim). Fallback: hash-based.
- If `chromadb` import fails, vector features gracefully disabled (`rag_vector.py:11-15`).

## Voice Interface (`backend/cogs/voice_interface/`)

- Trigger channel `➕ Create Caffee'` → auto-creates `🗣️ {user}'s Caffee` when joined.
- Control panel via `✨・interface` channel. User messages in interface auto-deleted; ephemeral responses dismiss after 8s.
- Privacy menu: Lock/Unlock/Hide/Show/Open Chat/Close Chat (single select menu).
- Password protection: `/voice-password <set/clear>`, `/join <password>`. Trusted users bypass.
- User preferences (lock, hide, waiting, limit, region) persisted per user, restored on next room.
- Guild config via `/voice-config` or dashboard.
- Auto-delete: owner leave + empty → immediate; empty 10s → auto-delete.
- `/setup` command creates the voice infrastructure (7 categories, 21 channels).
- Console language: mixed Indonesian + English.

## Dashboard (Flask)

- Discord OAuth2: `identify` + `guilds`. Guild access filtered to `ADMINISTRATOR` or `MANAGE_GUILD`.
- Sessions: Flask-Session (filesystem) at `backend/flask_session/` (gitignored).
- `MAX_CONTENT_LENGTH = 50MB`. Images >400KB auto-compressed to base64 data URLs for Firestore.
- `PYTHONPATH=/app` set via Dockerfile (required for `backend.` imports in production).
- i18n: `session["lang"]` defaults to `id`. Template filter `{{ "key" | t }}`. Fallback: requested lang → `id.json` → raw key. Translations in `backend/web/translations/`.

## Moderation (spam, `backend/utils/`)

- 3-layer image spam: rate limit (4/10s) → pHash + Hamming → Gemini Vision + Google Cloud Vision OCR.
- 3-strike: timeout (24h) → kick → ban. Resets after 24h clean.

## Anti-Nuke (`backend/cogs/anti_nuke/anti_nuke.py`)

- Sliding window (default 10s) on mass ban/kick, channel/role create/delete, admin perm grants, webhook spam.
- Admins auto-exempt. Configurable whitelist via `!antinuke-whitelist`.
- Lockdown: denies `send_messages`, `add_reactions`, `create_instant_invite` on @everyone. Auto-restores after `lockdown_duration` (default 30 min).
- AI post-analysis: fire-and-forget to OpenRouter free model pool after lockdown.

## Premium

- Monthly ($3 / Rp 50k) & Yearly ($25 / Rp 400k). Saweria/Sociabuzz webhooks auto-activate.
- Premium features include voice room claim/transfer and priority access.

## Firestore Backup

```bash
python backend/scripts/backup_firestore.py backup       # all collections
python backend/scripts/backup_firestore.py restore <file> [--dry-run]
python backend/scripts/backup_firestore.py list
python backend/scripts/backup_firestore.py info <file>
```

## Build / Test / Lint / CI

None. Zero tests, no pytest, no lint, no typecheck, no formatter, no CI. Manual verification only.

## Deployment

Railway via `railway.json`. Dockerfile: `python:3.11-slim`, `CMD honcho start -f Procfile`. UptimeRobot health ping every 5 min.
