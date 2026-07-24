# Banner Font Configuration

## Current (Final)
| Element | Size | Style | Canvas | Avatar |
|---------|------|-------|--------|--------|
| Title (WELCOME/GOODBYE/BANNED/BOOSTER) | **65px** | **Letter-spaced** (`" ".join`) | 1200×500 | size 200 |
| Username | **50px** | normal | | y=120 |
| Subtitle (Member ke-X • Server) | **26px** | normal | | ring=220 |

Spacing: `y_w = avatar_y + ring_size + 20`, `y_n = y_w + h_w + 3`, `y_s = y_n + h_n + 15`

## Change History

| Commit | Title | Username | Subtitle | Spacing | Canvas | Note |
|--------|-------|----------|----------|---------|--------|------|
| `fb55c0f` | **65** `" "` | **50** | **26** | `y_n = h_w + 3` | 1200×500 | Letter spacing + reduced gap |
| `4965c78` | **65** | **50** | **26** | `y_n = h_w + 5` | 1200×500 | Final — cocok dengan preview web |
| `2e792ec` | 130 | 100 | 42 | — | 1200×500 | Revert, keep Dockerfile font fix |
| `e071892` | 180 | 130 | 60 | — | 1200×720 | Too large |
| `a538abe` | 160 | 110 | 50 | — | 1200×500 | Still too small (font not loading) |
| `7949d23` | 180 | 130 | 60 | — | 1200×720 | First attempt, reverted |
| original | 130 | 100 | 42 | — | 1200×500 | Initial — fonts fell back to default on server |

## Root Cause
Docker image (`python:3.11-slim`) didn't have `fonts-dejavu-core` installed, causing `ImageFont.truetype()` to fail silently and fallback to `ImageFont.load_default()` (~10px bitmap). Fixed by:
1. Adding `fonts-dejavu-core` to `apt-get install` in Dockerfile
2. Adding auto-download fallback from GitHub (`/tmp/fonts/DejaVuSans-Bold.ttf`)

## Files Affected
- `backend/cogs/welcome/welcome.py`
- `backend/cogs/leave_settings/leave_settings.py`
- `backend/cogs/ban_settings/ban_settings.py`
- `backend/cogs/boost_announce/boost_announce.py`
- `Dockerfile`
