# AGENTS.md — Synapse Discord Bot

**Gitignored** — commit with `git add -f AGENTS.md`.

## Run

Python 3.11 (Dockerfile `python:3.11-slim`); code uses `X | None` unions, so 3.10+ required locally.

| Mode | Command |
|------|---------|
| Both (dev) | `honcho start -f Procfile.dev` |
| Both (prod) | `honcho start -f Procfile` |
| Bot only | `python backend/main.py` |
| Web only | `python -m backend.web.web_app` |

`.env` lives in `backend/.env` — loaded explicitly by both `main.py` (`load_dotenv()`) and `web_app.py` (`load_dotenv(backend/.env)`). Required: `TOKEN_BOT`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `FLASK_SECRET_KEY`, `FIREBASE_KEY`. AI: need at least one of `OPENCODE_ZEN_API_KEY`/`GEMINI_API_KEY`/`GROQ_API_KEY`/`MISTRAL_API_KEY`/`COHERE_API_KEY`/`OPENROUTER_API_KEY`.

Note: `.env.example` uses lowercase `token_bot` but `main.py` reads `TOKEN_BOT`. Also has `DISCORD_REDIRECT_URI` and `GOOGLE_VISION_API_KEY`.

## Procfile

- `Procfile` (prod): `web: gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 backend.web.web_app:app` / `worker: python backend/main.py`
- `Procfile.dev`: `web: python -m backend.web.web_app` / `worker: python backend/main.py`
- Flask entry point: `app.run(host="0.0.0.0", port=<PORT|8080>, debug=True, use_reloader=False)` in `web_app.py:3118-3120`.

## Key Quirks

- **Hybrid commands**: prefix `!` + slash. Slash sync on `on_ready` (`main.py:349-379`). First syncs to first guild (instant) then global sync, with 3 retries on 429.
- **Cog auto-load**: `os.walk` on `backend/cogs/`, skips `__init__.py` and `firebase_setup.py`, loads any `.py` with a `setup` attribute (`main.py:58-94`). 16 cogs. Grepping `async def setup` yields 17 matches: `general.py` defines a `/setup` hybrid command method (`general.py:329`) alongside its cog `setup` (`general.py:538`) — the command is unrelated, not an override.
- **`help` cog**: single file at `backend/cogs/help/help.py` — no `__init__.py`, loaded as `backend.cogs.help.help` (namespace package).
- **Intents**: `message_content`, `members`, `moderation`, `voice_states` enabled (`main.py:47-51`). Others default.
- **Memory monitor**: reads `/proc/*/status` VmRSS every 5 min → `gc.collect()` if >300MB. **Linux-only** — fails silently on Windows (`main.py:218-238`).
- **Stats updater**: `tasks.loop(seconds=30)` — Firestore stats + guild channels/roles/categories (`main.py:291-330`).
- **Control queue**: dashboard → bot IPC via JSON files in `control_queue/`. Web auto-creates dir (`_ensure_queue_dir`). Bot skips if absent (`main.py:100-216`). Actions: `send_message`, `refresh_rag_cache`, `refresh_settings_cache`.
- **Cookies**: `COOKIES_CONTENT` env var auto-written to `cookies/cookies.txt` at startup (`main.py:31-41`). Nothing in the code reads it back — write-only, no behavior depends on it.
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
- **Spam Intelligence Vision**: `analyze_image_spam_intelligence()` uses a merged mega-prompt combining crypto/phishing scam detection + threat intelligence + false positive policy. Returns structured JSON with indicators, action recommendations, and Firestore storage directives.
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
- `/setup` creates the full server infra (7 categories, 21 channels, from `CHANNEL_PLAN` in `general.py`); `/voice` only creates the 2-channel `💬 Create Voice` plan (`VOICE_CHANNEL_PLAN`) + interface message.

## Music Player (`backend/cogs/music/music.py`) — Radio Only

- **5 stations** (lofi/jazz/chill/study/sleep). `/play` + `/station` auto-complete. Each station has a primary `url` + 2 cross-referenced `fallbacks` (all fallbacks are primaries of other stations) rotated after `ROTATE_FAIL_THRESHOLD` (2) consecutive stream failures.
- `/sleep <minutes>`, `/fix-voice`, prefix `!connect`/`!joinvc`/`!leave`.
- Auto-restart on EOF, auto-resume via Firestore `voice_state` collection.
- **Watchdog** (per guild, `WATCHDOG_INTERVAL`=10s): if bot drops from voice → reconnect to saved channel + restart; if connected but silent/idle → `vc.stop()` + restart. Logs to `backend/logs/bot.log` via `logger.py`.
- ffmpeg flags: `-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10 -reconnect_at_eof 1 -reconnect_on_network_error 1 -nostdin` + `-vn -af aresample=async=1:min_hard_comp=0.1`.
- AI Agent: `run_command("connect"/"play"/"leave"/"stop")`.

## Dashboard (Flask)

- Discord OAuth2: `identify` + `guilds`. Guild access filtered to `ADMINISTRATOR` or `MANAGE_GUILD`.
- Sessions: Flask-Session (filesystem) at `backend/web/flask_session/` (gitignored via the `flask_session/` rule).
- `MAX_CONTENT_LENGTH = 50MB`. Images >400KB auto-compressed to base64 data URLs for Firestore.
- i18n: **Cookie-based** (`synapse_lang`), fallback to session → `"id"`. Template filter `{{ "key" | t }}`. Fallback: requested lang → `id.json` → raw key. Translations in `backend/web/language/`.
  - Language toggle in `navbar.js`: sets cookie via `document.cookie` + `location.reload()` — **not** a redirect to `/api/lang/<lang>`.
  - `_get_lang()` in `web_app.py:91`: `request.cookies.get("synapse_lang") or session.get("lang", "id")`.
  - No-cache headers on all `text/html` responses via `_no_cache()` (`web_app.py:66-72`).
  - `landing.js` commands counter uses server-rendered `data-template` attribute with `{n}` placeholder.

## Cogs Layout (16 cogs; 17 dirs under `backend/cogs/`)

- **Small/simple cogs** (single file, ~100-500 lines): `ban_settings`, `boost`, `boost_announce`, `help`, `leave_settings`, `leveling`, `music`, `photobox`, `welcome`
- **Large cogs**: `ai_chat` (~1635 lines + 6 providers + `prompt.py`/`chat_enhancer.py`), `ai_agent` (2 files: `agent_cog.py` + `agent_tools.py`), `anti_nuke`, `auto_response`, `general`, `moderation`, `voice_interface`
- `database/` is not a cog — contains `firebase_setup.py` (excluded from auto-load)

## Moderation (spam, `backend/utils/`)

**Message pipeline** (`on_message`, `moderation.py`) — bots + admins exempt. Per-message:
1. `SpamEngine.get_risk_score()` sums weighted signals: `@everyone`/`@here` **+2** (was +5 — tuned so casual mentions don't trip), suspicious URL/domain/typosquat/TLD +5, scam keyword +5, account <60d +5, joined recently +2..+5, rate-flooding +5, identical duplicate (3x/30s) +5.
2. **score >= 5** → heuristic trigger. Account <60d / score >=10 / (joined <7d **and** score >=8) → punish directly (`handle_spam`), skipping AI. Else AI (`ai_chat.analyze_spam`) decides: spam → `handle_spam`; **not spam → message passes** unless flooding/duplicate → `handle_spam_light`.
3. **score 1-4** → borderline AI check, **except benign mentions**: `SpamEngine.is_benign_mention()` (plain `@everyone`/`@here`, no URL/keyword/flood) from accounts >=60d skips AI entirely — zero false-positive risk.
4. Images checked **independently** of text score (`_check_image_spam`): rate limit (4/10s) → known pHash → duplicate → Gemini Vision (only suspicious users: <60d / joined <7d / flooding / dup>=2) → Google Vision OCR fallback → SpamIntelligence intel pre-check (known `scam_signatures` by pHash for ANY user).

**Punishment tiers** (`handle_spam`): reason containing `gambar mengandung` / `scam` / `judi` / `phishing` / `berbahaya` / `diverifikasi sebagai spam oleh ai` / `konten mencurigakan oleh llm` / `filter intel` → **`is_ai_serious` = immediate permanent ban** (no strike; DM says "Banding TIDAK DITERIMA"). Otherwise: account <60d → `new_account_action` (default ban); older accounts → 3-strike (timeout 24h → kick → ban, resets after 24h clean). `handle_spam_light` = delete message + 10-min timeout, no strike.

**Tuning history (2026)**: casual `@everyone` messages (e.g. `@everyone join dc`) were false-positive punished. Fixes: `@everyone` weight 5→2 (`spam_engine.py`), AI-cleared messages now pass unless flooding/duplicate, benign-mention skip for accounts >=60d. **New-joiner false positives**: `joined <7d` alone was skipping AI, so a first message in `#welcome` from an old account (<1h join = +5 score) was auto-punished → `skip_ai` now requires `score >= 8` when joined <7d, so old accounts get AI verification unless the content is clearly suspicious. Real spam still caught via URL/keyword/young-account signals + image layer.

- **3-layer image spam**: rate limit (4/10s) → pHash + Hamming → Gemini Vision + Google Cloud Vision OCR.
- **`analyze_spam` quirk** (`ai_chat.py:223`): returns `"YA" in response.upper()` — a verbose free-model reply can contain a stray "YA". Cached by md5 content hash (500 entries, TTL).
- **Vision gap**: Gemini Vision only runs for suspicious users (quota-saving) — a brand-new unknown scam image from an old, non-flooding account can slip through unless Google Vision OCR (`GOOGLE_VISION_API_KEY`) is configured.
- **SpamIntelligence** (`backend/utils/spam_intelligence.py`): AI engine with persistent Firestore `scam_signatures` collection. Pre-checks known scam templates by pHash before other layers. After flagging, runs structured Vision AI analysis → stores signatures if confidence >= 85 with >= 3 indicators.
- **Ban Evasion Detection** (`spam_intelligence.py:584-714`): Text fingerprinting via `_compute_text_fingerprint()` — extracts scam URLs, keywords, and mentions into a 24-char hash. On ban/kick, `store_ban_pattern()` persists fingerprint to Firestore `ban_patterns` collection with `timesBanned` counter. On each new message from accounts <60 days old (`moderation.py`), `check_ban_pattern()` compares against cache — exact hash match or partial URL domain match triggers evasion ban.
- **AUTO_BAN** on known threat match OR confidence >= 95 with >= 3 indicators + low false-positive risk. **AUTO_KICK** at >= 90 for image scams.
- 3-strike: timeout (24h) → kick → ban. Resets after 24h clean.

## Anti-Nuke (`backend/cogs/anti_nuke/anti_nuke.py`)

- Sliding window (default 10s). Thresholds: ban=3, kick=3, channel=3, role=3, admin=2.
- Admins auto-exempt. Configurable whitelist via `/antinuke-whitelist`.
- Lockdown: denies `send_messages`, `add_reactions`, `create_instant_invite` on @everyone. Auto-restores after `lockdown_duration` (default 1800s / 30 min).
- AI post-analysis: fire-and-forget to OpenRouter free model pool after lockdown.

## Premium

- Monthly (Rp 50k) & Yearly (Rp 400k). Saweria/Sociabuzz webhooks auto-activate.
- IDR thresholds env-overridable: `PREMIUM_MONTHLY_IDR` (50000) / `PREMIUM_YEARLY_IDR` (400000) (`web_app.py:1096-1097`). Activation is exact-amount match; the donation message must be a numeric Discord user ID to bind premium (`web_app.py:1099-1120`).
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

## OpenCode Config

- No `opencode.json` — tooling config only in `.opencode/package.json` (plugin dep).
- `.opencode/plans/dashboard-de-ai-slop.md` — existing plan file for dashboard work.

## Docs

5 files in `docs/` — architecture & redesign notes for AI Agent, dashboard, landing page.

## Deployment

**Render** via Dockerfile. `python:3.11-slim`, installs `curl unzip fonts-dejavu-core ffmpeg`. Runs `honcho start -f Procfile` (web + worker).


