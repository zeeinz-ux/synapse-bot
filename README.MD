# Hidden Hamlet — Discord Bot v4.6+

A multifunctional Discord bot with a web dashboard, AI chat, music player, moderation, leveling, and server management tools.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.10+ |
| Bot Library | discord.py 2.7.1 |
| Web Server | Flask 3.1.3 |
| Database | Firebase Firestore (free tier) |
| Music | Lavalink + Wavelink 3.5.2 |
| AI Chat | Google Gemini → Groq (Llama 3.3) → OpenRouter (fallback chain) |
| Sessions | Flask-Session (server-side file) |
| Deployment | Gunicorn + Railway + UptimeRobot |

## Features

### Discord Cogs

| Cog | Description |
|-----|-------------|
| **Music** | Full playback via Lavalink — play, queue, loop, shuffle, autoplay, Spotify resolver, lyrics |
| **AI Chat** | Triple API fallback (Gemini → Groq → OpenRouter), personality, temperature, channel restriction, circuit breaker |
| **Welcome** | Dual-style embed/banner auto-welcome with drag-drop image upload |
| **Leave** | Auto-leave announcement (embed/banner) |
| **Ban** | Auto-ban announcement (embed/banner) |
| **Boost Announce** | Auto-boost announcement (embed/banner) |
| **Boost Tracker** | Track boost/unboost history |
| **Donation** | Track donation transactions |
| **Moderation** | Spam detection with 3-strike system (timeout → kick → ban) |
| **Leveling** | XP system with rank & leaderboard (in development) |
| **Auto-Responder** | Keyword-triggered replies with regex, cooldown, channel filters |
| **General** | Ping, stats, help commands |

### Web Dashboard

| Page | Description |
|------|-------------|
| `/` | Landing page with bot stats, sakura petals animation |
| `/dashboard/<guild>/` | Server overview — real-time stats, music players, Lavalink status |
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
backend/
├── cogs/                 # Discord bot modules
│   ├── ai_chat/          # AI Chat with triple API fallback
│   ├── auto_response/    # Keyword auto-responder
│   ├── ban_settings/     # Ban announcement
│   ├── boost/            # Boost tracker
│   ├── boost_announce/   # Boost announcement
│   ├── database/         # Firebase initialization
│   ├── donation/         # Donation tracker
│   ├── general/          # Ping, stats, help
│   ├── leave_settings/   # Leave announcement
│   ├── leveling/         # XP/Leveling system
│   ├── moderation/       # Spam detection
│   └── music/            # Lavalink music player
├── utils/                # Shared helpers
├── web/                  # Flask routes (web_app.py)
└── lavalink/             # Lavalink server
frontend/
├── templates/            # 21 Jinja2 HTML templates
├── static/
│   ├── css/              # Page-specific styles
│   └── js/               # Page-specific logic
```

## Deployment

- **Local:** `python backend/main.py`
- **Production:** `honcho start -f Procfile` (web: gunicorn + worker: bot)
- **24/7:** UptimeRobot pings every 5 min to prevent sleep

## Environment Variables

See `.env.example` for required variables (Discord bot token, OAuth2 credentials, Firebase service account, API keys, Lavalink config).

## License

All Rights Reserved.
