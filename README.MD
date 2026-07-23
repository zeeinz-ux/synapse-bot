# Synapse Discord Bot

Multi-purpose Discord bot with AI chat, anti-nuke protection, voice interface, and auto server setup.

## Features

### ⚙️ Server Setup (`/setup`)
Auto-creates server structure: 7 categories, 21 channels (12 text + 9 voice), enables features (anti-spam, anti-nuke, AI chat), cleans default Discord channels. Channel order and permissions are preset per type.

### 🚨 Anti-Nuke
Rule-based sliding window detection for mass ban/kick/channel/role destruction. Auto-lockdown by denying @everyone send_messages on all channels, auto-restore after configurable duration (default 30 min). Whitelist system (admin, user, role). AI post-analysis via OpenRouter free models after lockdown. Dashboard settings page.

### 🎛️ Voice Interface
Join `➕ Create Caffee'` → auto-create temp voice room named `🗣️ {user}'s Caffee` in Game category. Control panel via `✨・interface` text channel with 16 buttons:
- **Row 0:** Rename, Lock, Privacy, Limit, Waiting Room
- **Row 1:** Chat, Trust, Untrust, Block, Unblock
- **Row 2:** Kick, Invite, Region, Delete
- **Row 3:** ⭐ Claim, ⭐ Transfer (premium)

Auto-delete when empty (5 min delay). Owner leave >5 min → claimable by others.

### 🤖 AI Chat
Multi-tier fallback: Gemini → Groq → Mistral → Cohere → OpenRouter. Streaming via `/ask`, mention-based batch mode. RAG/vector search with ChromaDB + Gemini embedding (3072-dim). Image analysis (Gemini-only). Query expansion + multi-turn history.

### 📊 Server Stats
Background task (5 min interval) updates voice channel names in SERVER STATS category with live member/bot counts.

### ⭐ Premium
Subscription-based (monthly/yearly) via Sawiera/Sociabuzz webhook. Auto-activation, DM notification, auto-expiry cleanup.

### 🔧 AI Analysis Chain
Single OpenRouter fallback chain (6 models: openrouter/free → gemma-4 → nemotron → llama-3.3 → qwen → phi).

## Commands

| Command | Description |
|---------|-------------|
| `/setup` | Auto-create server channels & enable features |
| `/ask` | AI chat with streaming |
| `/antinuke` | Toggle anti-nuke protection |
| `/antinuke-whitelist` | Manage anti-nuke whitelist |
| `/antinuke-restore` | Restore lockdown manually |
| `/antinuke-status` | Show anti-nuke status |
| `!` prefix | Legacy prefix commands |

## Dashboard

Flask-based web dashboard with Discord OAuth2. Features management, anti-nuke settings, donation tracking, welcome/leave/ban/boost editors.

## Tech Stack

- **Bot:** discord.py 2.7.1 (hybrid commands)
- **AI:** Gemini, Groq, Mistral, Cohere, OpenRouter API
- **Vector DB:** ChromaDB (persistent file-based)
- **Web:** Flask, Flask-Session
- **Database:** Firestore (debounced writes, circuit breaker)
- **IPC:** File-based control queue (Flask → Bot)

## Environment

`.env` in `backend/`. Required: `TOKEN_BOT`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_REDIRECT_URI`, `FLASK_SECRET_KEY`, `FIREBASE_KEY`. AI requires at least one API key (Gemini/Groq/Mistral/Cohere/OpenRouter).

## Running

```bash
# Development
honcho start -f Procfile.dev

# Production
honcho start -f Procfile
```

## Deployment

Deployed on Railway via Docker (python:3.11-slim). Health-check by UptimeRobot (5 min interval).

## Premium Payment Flow

1. User clicks Buy Premium on dashboard
2. Pays via Sawiera/Sociabuzz (Rp 50k monthly / Rp 400k yearly)
3. Writes Discord user ID in message
4. Webhook auto-activates premium in Firestore
5. Bot sends DM confirmation with expiry date
6. Auto-cleanup of expired premiums every hour

## Firestore Data Model

```
guild_settings/{guild_id}/
  ├── premium_users/
  │   └── {user_id}: {expiry, tier, activated_at}
  ├── anti_nuke/  {enabled, thresholds, lockdown_duration, whitelist}
  ├── ai_chat/  {enabled}
  ├── welcome/  {enabled, message, embed config, banner config}
  └── ...
```