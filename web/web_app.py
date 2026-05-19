import os
import threading
from flask import Flask, render_template, jsonify
from datetime import datetime, timezone

from utils.formatters import format_duration, format_uptime

# ==========================================================
# Flask app dengan static & template folder eksplisit
# ==========================================================
# __file__ = web/app.py → parent = web/ → static di web/static/
_base_dir = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    static_folder=os.path.join(_base_dir, "static"),
    template_folder=os.path.join(_base_dir, "templates")
)

# ==========================================================
# Shared stats (thread-safe) — di-write oleh bot, di-read oleh Flask
# ==========================================================
_stats_lock = threading.Lock()
_bot_stats = {
    "online": False,
    "username": "Hidden Hamlet",
    "uptime": 0,
    "guilds": 0,
    "members": 0,
    "lavalink_connected": False,
    "lavalink_node": "N/A",
    "players": [],
    "last_updated": "-"
}


def set_stats(**kwargs):
    """Dipanggil dari main.py (bot thread) untuk update stats."""
    with _stats_lock:
        _bot_stats.update(kwargs)
        _bot_stats["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def get_stats_snapshot():
    """Dipanggil dari Flask routes untuk baca stats (thread-safe)."""
    with _stats_lock:
        raw = dict(_bot_stats)

    players = []
    for p in raw.get("players", []):
        dur = p.get("duration", 0)
        pos = p.get("position", 0)
        pct = (pos / dur * 100) if dur else 0
        players.append({
            "guild": p.get("guild", "Unknown"),
            "track": p.get("track", "Unknown"),
            "author": p.get("author", "Unknown"),
            "artwork": p.get("artwork", "") or "https://via.placeholder.com/80?text=No+Art",
            "queue": p.get("queue", 0),
            "listeners": p.get("listeners", 0),
            "paused": p.get("paused", False),
            "progress_percent": round(pct, 1),
            "position_fmt": format_duration(pos),
            "duration_fmt": format_duration(dur),
        })

    return {
        "online": raw.get("online", False),
        "username": raw.get("username", "Hidden Hamlet"),
        "uptime_fmt": format_uptime(raw.get("uptime", 0)),
        "guilds": raw.get("guilds", 0),
        "members": raw.get("members", 0),
        "lavalink_connected": raw.get("lavalink_connected", False),
        "lavalink_node": raw.get("lavalink_node", "N/A"),
        "players": players,
        "last_updated": raw.get("last_updated", "-")
    }


@app.route("/")
def home():
    return (
        "<h1>🤖 Bot is running!</h1>"
        '<p><a href="/dashboard">Open Dashboard</a> • '
        '<a href="/api/stats">API JSON</a></p>'
    )


@app.route("/dashboard")
def dashboard():
    s = get_stats_snapshot()
    return render_template("dashboard.html", s=s)


@app.route("/api/stats")
def api_stats():
    with _stats_lock:
        return jsonify(dict(_bot_stats))