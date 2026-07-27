# AGENTS.md — Synapse Discord Bot

**Gitignored** — commit with `git add -f AGENTS.md`.

## Run

| Mode | Command |
|------|---------|
| Both (dev) | `honcho start -f Procfile.dev` |
| Both (prod) | `honcho start -f Procfile` |
| Bot only | `python backend/main.py` |
| Web only | `python -m backend.web.web_app` |

`.env` lives in `backend/.env`. Required: `TOKEN_BOT`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `FLASK_SECRET_KEY`, `FIREBASE_KEY`. AI: need at least one of `OPENCODE_ZEN_API_KEY`/`GEMINI_API_KEY`/`GROQ_API_KEY`/`MISTRAL_API_KEY`/`COHERE_API_KEY`/`OPENROUTER_API_KEY`.

Note: `.env.example` uses lowercase `token_bot` but `main.py` reads `TOKEN_BOT`. Also has `DISCORD_REDIRECT_URI` and `GOOGLE_VISION_API_KEY`.

## Procfile

- `Procfile` (prod): `web: gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 backend.web.web_app:app` / `worker: python backend/main.py`
- `Procfile.dev`: `web: python -m backend.web.web_app` / `worker: python backend/main.py`
- Flask entry point: `app.run(host="0.0.0.0", port=<PORT|8080>, debug=True)` in `web_app.py:3115-3117`.

## Key Quirks

- **Hybrid commands**: prefix `!` + slash. Slash sync on `on_ready` (`main.py:349-359`).
- **Cog auto-load**: `os.walk` on `backend/cogs/`, skips `__init__.py` and `firebase_setup.py`, loads any `.py` with `async def setup()`. 16 cogs total (verify by grepping `async def setup(bot`).
- **Intents**: `message_content`, `members`, `moderation`, `voice_states` enabled (`main.py:47-51`). Others default.
- **Memory monitor**: reads `/proc/*/status` VmRSS every 5 min → `gc.collect()` if >300MB. **Linux-only** — fails silently on Windows (`main.py:218-238`).
- **Stats updater**: `tasks.loop(seconds=30)` — Firestore stats + guild channels/roles/categories (`main.py:291-330`).
- **Control queue**: dashboard → bot IPC via JSON files in `control_queue/`. Web auto-creates dir (`_ensure_queue_dir`). Bot skips if absent (`main.py:100-216`). Actions: `send_message`, `refresh_rag_cache`, `refresh_settings_cache`.
- **Cookies**: `COOKIES_CONTENT` env var auto-written to `cookies/cookies.txt` at startup (`main.py:31-41`). Used for Discord external links (not YouTube).
- **Console logs**: Mix of Indonesian + English.
- **`_project_root`**: set in `main.py` via `sys.path.insert(0, ...)` so module resolution works locally. Dockerfile sets `ENV PYTHONPATH=/app`.
- **Frontend**: Jinja2 templates in `frontend/pages/`, Flask references them via relative paths from `backend/web/web_app.py`.
- **`web_app.py` is ~3100 lines** — single Flask file with 70+ routes, API, OAuth2, all dashboards. Largest file in repo.

## Firestore (Firebase Admin SDK)

- **Never call synchronously in async context** — All writes through `asyncio.to_thread()` (`firestore_stats.py`).
- **Debounced** (default 30s, env `FIRESTORE_DEBOUNCE`). **Circuit breaker** on 429 (default 15min, env `FIRESTORE_CIRCUIT_SEC`).
- Firebase key modes: base64 string, raw JSON string, or file path (searched in multiple dirs).
- Web endpoints and sync contexts create fresh event loops (`asyncio.new_event_loop()`) for async calls.
- Circuit breaker shared: `firestore_circuit_open()` / `trip_firestore_circuit()` (`backend/utils/firestore_stats.py`).

## AI Chat

`OpenCode Zen → Gemini → Groq → Mistral → Cohere → OpenRouter` (6 providers in `backend/cogs/ai_chat/providers/`).

- OpenCode Zen: **Tier 1 — Free priority**. Fetches free models from API at startup; fallback hardcoded list (`opencode_zen.py:10-23`). Vision models: `deepseek-v4-flash-free`, `nemotron-3-ultra-free`.
- Gemini: model `gemini-3.6-flash`. Circuit breaker (3 consecutive fails → skip 2h) + daily quota reserve for vision (1500/day, reserve 200).
- **Image analysis is NOT Gemini-only** — OpenRouter and OpenCode Zen also have vision models. Falls back through providers like chat does.
- OpenRouter: **Tier 6 — Last resort**. Auto-fetches `:free` models from API on startup, tries all free before paid fallback.
- Streaming: `/ask` uses progressive message edits (~1s). Mention-based chat uses batch mode.
- Intent router (`intent_router.py`) + web search (`web_search.py`) integrated in `ai_chat.py`.

## AI Agent (`backend/cogs/ai_agent/`)

- **ReAct loop** with Plan → Build phases. Plan prompt generates `[PLAN]...[/PLAN]`, Build executes step-by-step with `[SISA RENCANA]`.
- **29 tools**: `server_info`, `list_channels`, `list_roles`, `create_channel`, `delete_channel`, `rename_channel`, `create_role`, `edit_role`, `delete_role`, `assign_role`, `remove_role`, `list_members`, `ban_member`, `unban_member`, `kick_member`, `timeout_member`, `edit_channel_permissions`, `list_bans`, `edit_server`, `batch_create_channels`, `batch_create_roles`, `apply_template`, `save_snapshot`, `rollback`, `schedule_task`, `send_message`, `add_reaction`, `run_command`, `web_search`.
- Voice tools removed — agent uses `run_command("connect"/"play"/"leave"/"stop")` for voice.
- **`send_message`** auto-resolves `@Username` to real mention (`<@id>`).
- **`web_search`** uses DuckDuckGo (`backend/cogs/ai_chat/web_search.py`).
- **`run_command`** now captures command output (`ctx.send`/`ctx.reply`) and returns it to the AI, preventing hallucination.
- Bot voice state (connected channel + playing status) injected into system prompt per request.
- Tool validation, auto-retry (3x), snapshot/rollback, scheduler.
- Conversation memory: 20 turns, Firestore-backed, permanent per user+guild.

## RAG / Vector Search

- ChromaDB persistent at `data/chroma_db/` (env `CHROMA_DB_PATH` overrides).
- Embedding: Gemini API (`models/gemini-embedding-001`, 3072-dim). Fallback: hash-based.
- If `chromadb` import fails, vector features gracefully disabled (`rag_vector.py:11-15`).

## Voice Interface (`backend/cogs/voice_interface/`)

- Trigger channel `➕ Create Caffee'` → auto-creates `🗣️ {user}'s Caffee` on join.
- Control panel via `✨・interface` channel. User messages auto-deleted; ephemeral responses dismiss after 8s.
- Privacy menu: Lock/Unlock/Hide/Show/Open Chat/Close Chat (single select menu).
- Password protection: `/voice-password <set/clear>`, `/join <password>`. Trusted users bypass.
- User preferences (lock, hide, waiting, limit, region) persisted per user, restored on next room.
- Guild config via `/voice-config` or dashboard.
- Auto-delete: owner leave + empty → immediate; empty 10s → auto-delete.
- `/setup` command creates the voice infrastructure (7 categories, 21 channels).

## Music Player (`backend/cogs/music/music.py`) — LoFi Only

- **Commands**: `/play`, `/station`, `/song`, `/sleep`, `/stop`, `/fix-voice`, `!connect`/`!joinvc`, `!leave`.
- **YouTube removed**: Render IP diblokir YouTube total. Bot cuma muterin LoFi radio stream.
- LoFi radio stream (`play.streamafrica.net/lofiradio`) auto-restarts on EOF.
- Auto-resume: voice state saved to Firestore (`voice_state` collection), restored on cog `on_ready`.
- AI Agent accesses via `run_command("connect"/"play"/"leave"/"stop")`.

## Dashboard (Flask)

- Discord OAuth2: `identify` + `guilds`. Guild access filtered to `ADMINISTRATOR` or `MANAGE_GUILD`.
- Sessions: Flask-Session (filesystem) at `backend/flask_session/` (gitignored).
- `MAX_CONTENT_LENGTH = 50MB`. Images >400KB auto-compressed to base64 data URLs for Firestore.
- i18n: **Cookie-based** (`synapse_lang`), fallback to session → `"id"`. Template filter `{{ "key" | t }}`. Fallback: requested lang → `id.json` → raw key. Translations in `backend/web/language/`.
  - Language toggle in `navbar.js`: sets cookie via `document.cookie` + `location.reload()` — **not** a redirect to `/api/lang/<lang>`.
  - `_get_lang()` in `web_app.py:92`: `request.cookies.get("synapse_lang") or session.get("lang", "id")`.
  - No-cache headers on all `text/html` responses via `_no_cache()` (`web_app.py:66-72`).
  - `landing.js` commands counter uses server-rendered `data-template` attribute with `{n}` placeholder.

## Cogs Layout (16 dirs under `backend/cogs/`)

- **Small/simple cogs** (single file, ~100-500 lines): `ban_settings`, `boost`, `boost_announce`, `help`, `leave_settings`, `leveling`, `music`, `photobox`, `welcome`
- **Large cogs**: `ai_chat` (~1500 lines + 6 providers), `ai_agent` (2 files: `agent_cog.py` + `agent_tools.py`), `anti_nuke`, `auto_response`, `general`, `moderation`, `voice_interface`
- `database/` is not a cog — contains `firebase_setup.py` (excluded from auto-load)

## Moderation (spam, `backend/utils/`)

- 3-layer image spam: rate limit (4/10s) → pHash + Hamming → Gemini Vision + Google Cloud Vision OCR.
- 3-strike: timeout (24h) → kick → ban. Resets after 24h clean.

## Anti-Nuke (`backend/cogs/anti_nuke/anti_nuke.py`)

- Sliding window (default 10s). Thresholds: ban=3, kick=3, channel=3, role=3, admin=2.
- Admins auto-exempt. Configurable whitelist via `/antinuke-whitelist`.
- Lockdown: denies `send_messages`, `add_reactions`, `create_instant_invite` on @everyone. Auto-restores after `lockdown_duration` (default 1800s / 30 min).
- AI post-analysis: fire-and-forget to OpenRouter free model pool after lockdown.

## Premium

- Monthly ($3 / Rp 50k) & Yearly ($25 / Rp 400k). Saweria/Sociabuzz webhooks auto-activate.
- Premium features: voice room claim/transfer, priority access.

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

**Render.com** via Dockerfile. `python:3.11-slim`, installs `curl unzip fonts-dejavu-core ffmpeg`, runs `pip install --upgrade yt-dlp` saat build, lalu `honcho start -f Procfile`. UptimeRobot health ping every 5 min.
