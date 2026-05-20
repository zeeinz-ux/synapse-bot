import os
import threading
from flask import Flask, render_template, jsonify, request, redirect
from datetime import datetime, timezone

# ==========================================================
# Import relative dari dalam backend/ folder
# ==========================================================
from utils.formatters import format_duration, format_uptime

# Firestore instance untuk route Welcome
from cogs.firebase_setup import db

# ==========================================================
# Flask app — static & template folder ke frontend/
# ==========================================================
_base_dir = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    static_folder=os.path.join(_base_dir, "../../frontend/static"),
    template_folder=os.path.join(_base_dir, "../../frontend/templates")
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
    "last_updated": "-",
    "guilds_list": []  # ← WAJIB di-populate main.py: [{"id":"str","name":"str","member_count":int}, ...]
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
            "guild":            p.get("guild", "Unknown"),
            "track":            p.get("track", "Unknown"),
            "author":           p.get("author", "Unknown"),
            "artwork":          p.get("artwork", "") or "https://via.placeholder.com/80?text=No+Art",
            "queue":            p.get("queue", 0),
            "listeners":        p.get("listeners", 0),
            "paused":           p.get("paused", False),
            "progress_percent": round(pct, 1),
            "position_fmt":     format_duration(pos),
            "duration_fmt":     format_duration(dur),
        })

    return {
        "online":             raw.get("online", False),
        "username":           raw.get("username", "Hidden Hamlet"),
        "uptime_fmt":         format_uptime(raw.get("uptime", 0)),
        "guilds":             raw.get("guilds", 0),
        "members":            raw.get("members", 0),
        "lavalink_connected": raw.get("lavalink_connected", False),
        "lavalink_node":      raw.get("lavalink_node", "N/A"),
        "players":            players,
        "last_updated":       raw.get("last_updated", "-"),
        "guilds_list":        raw.get("guilds_list", [])
    }

# ==========================================================
# Shared guild channels (thread-safe)
# ==========================================================
_guild_lock = threading.Lock()
_guild_channels: dict = {}

def set_guild_channels(guild_id: str, channels: list):
    """Simpan daftar text channel yang bot punya izin kirim pesan."""
    with _guild_lock:
        _guild_channels[guild_id] = channels

def get_guild_channels(guild_id: str) -> list:
    """Ambil daftar channel untuk satu guild."""
    with _guild_lock:
        return _guild_channels.get(guild_id, [])

# ==========================================================
# Helper — baca config welcome dari Firestore (sync, untuk Flask)
# ==========================================================
def _get_welcome_config(guild_id: str) -> dict:
    """
    Baca konfigurasi welcome dari Firestore secara synchronous.
    Aman dipanggil dari Flask karena bukan async context.
    """
    if db is None:
        print("[WELCOME-WEB] ⚠️ Firebase tidak tersedia.")
        return {}

    try:
        doc = db.collection("guild_settings").document(guild_id).get()
        if doc.exists:
            return doc.to_dict().get("welcome", {})
    except Exception as e:
        print(f"[WELCOME-WEB] ❌ Gagal baca Firestore: {e}")
    return {}

# ==========================================================
# Helper — render template dengan sidebar context
# ==========================================================
def _render_page(template_name: str, active_page: str, guild_id: str, **kwargs):
    """
    Wrapper render_template yang otomatis inject:
    - s (stats snapshot)
    - active_page (untuk highlight sidebar)
    - guild_id (untuk nav links & dropdown)
    """
    return render_template(
        template_name,
        s=get_stats_snapshot(),
        active_page=active_page,
        guild_id=guild_id,
        **kwargs
    )

# ==========================================================
# ROUTES — Landing & API
# ==========================================================
@app.route("/")
def home():
    return (
        "<h1>🤖 Bot is running!</h1>"
        '<p><a href="/dashboard">Open Dashboard</a> • '
        '<a href="/api/stats">API JSON</a></p>'
    )

@app.route("/api/stats")
def api_stats():
    with _stats_lock:
        return jsonify(dict(_bot_stats))

# ==========================================================
# ROUTES — Dashboard (redirect ke guild pertama)
# ==========================================================
@app.route("/dashboard")
def dashboard():
    """Redirect ke guild pertama kalau ada, otherwise render tanpa guild."""
    s = get_stats_snapshot()
    guilds = s.get("guilds_list", [])
    if guilds:
        first_id = str(guilds[0].get("id", ""))
        if first_id:
            return redirect(f"/dashboard/{first_id}/")
    return _render_page("dashboard.html", active_page="main", guild_id="")

@app.route("/dashboard/<guild_id>/")
def dashboard_guild(guild_id: str):
    """Main dashboard untuk guild tertentu."""
    return _render_page("dashboard.html", active_page="main", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/settings")
def settings_page(guild_id: str):
    """Placeholder: Settings."""
    return _render_page("dashboard.html", active_page="settings", guild_id=guild_id)

# ==========================================================
# ROUTES — Music
# ==========================================================
@app.route("/dashboard/<guild_id>/music")
def music_settings(guild_id: str):
    """Placeholder: Music Player."""
    return _render_page("music_settings.html", active_page="music", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/music/queue")
def music_queue(guild_id: str):
    """Placeholder: Queue."""
    return _render_page("music_settings.html", active_page="queue", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/music/playlists")
def music_playlists(guild_id: str):
    """Placeholder: Playlists."""
    return _render_page("music_settings.html", active_page="playlists", guild_id=guild_id)

# ==========================================================
# ROUTES — Spotify
# ==========================================================
@app.route("/dashboard/<guild_id>/spotify")
def spotify_settings(guild_id: str):
    """Placeholder: Spotify Downloader."""
    return _render_page("spotify_settings.html", active_page="spotify", guild_id=guild_id)

# ==========================================================
# ROUTES — Welcome / Announcements
# ==========================================================
@app.route("/dashboard/<guild_id>/welcome")
def welcome_settings(guild_id: str):
    """GET — Render halaman form konfigurasi Welcome."""
    channels = get_guild_channels(guild_id)
    current_config = _get_welcome_config(guild_id)

    defaults = {
        "enabled": False,
        "channel_id": "",
        "message_text": "Hei {user}, selamat datang di **{server}**! 🎉",
        "is_embed": False,
        "embed_color": "#5865F2",
        "embed_title": "👋 Selamat Datang!",
        "bg_image_url": ""
    }

    config = {**defaults, **current_config}

    return _render_page(
        "welcome_settings.html",
        active_page="welcome",
        guild_id=guild_id,
        channels=channels,
        config=config
    )

@app.route("/dashboard/<guild_id>/welcome/leave")
def welcome_leave(guild_id: str):
    """Placeholder: Leave announcement."""
    return _render_page("welcome_settings.html", active_page="leave", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/welcome/ban")
def welcome_ban(guild_id: str):
    """Placeholder: Ban announcement."""
    return _render_page("welcome_settings.html", active_page="ban", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/welcome/boost")
def welcome_boost(guild_id: str):
    """Placeholder: Boost welcome announcement."""
    return _render_page("welcome_settings.html", active_page="boost_welcome", guild_id=guild_id)

# ==========================================================
# ROUTES — Boost Tracker
# ==========================================================
@app.route("/dashboard/<guild_id>/boost")
def boost_tracker(guild_id: str):
    """Placeholder: Boost riwayat."""
    return _render_page("boost_settings.html", active_page="boost_tracker", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/boost/stats")
def boost_stats(guild_id: str):
    """Placeholder: Boost statistik."""
    return _render_page("boost_settings.html", active_page="boost_stats", guild_id=guild_id)

# ==========================================================
# ROUTES — Donation
# ==========================================================
@app.route("/dashboard/<guild_id>/donation")
def donation_tracker(guild_id: str):
    """Placeholder: Donation riwayat."""
    return _render_page("donation_settings.html", active_page="donation", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/donation/stats")
def donation_stats(guild_id: str):
    """Placeholder: Donation statistik."""
    return _render_page("donation_settings.html", active_page="donation_stats", guild_id=guild_id)

# ==========================================================
# ROUTES — Tools
# ==========================================================
@app.route("/dashboard/<guild_id>/message-builder")
def message_builder(guild_id: str):
    """Placeholder: Message Builder."""
    return _render_page("dashboard.html", active_page="message_builder", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/templates")
def templates_page(guild_id: str):
    """Placeholder: Templates."""
    return _render_page("dashboard.html", active_page="templates", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/actions")
def actions_page(guild_id: str):
    """Placeholder: Actions."""
    return _render_page("dashboard.html", active_page="actions", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/auto-responders")
def auto_responders(guild_id: str):
    """Placeholder: Auto Responders."""
    return _render_page("dashboard.html", active_page="auto_responders", guild_id=guild_id)

# ==========================================================
# ROUTES — Welcome Save (POST, JSON response)
# ==========================================================
@app.route("/dashboard/<guild_id>/welcome/save", methods=["POST"])
def save_welcome(guild_id: str):
    """POST — Simpan config welcome ke Firestore dengan merge=True."""
    if db is None:
        return jsonify({
            "success": False,
            "message": "Firebase tidak tersedia."
        }), 500

    try:
        enabled = "enabled" in request.form
        is_embed = "is_embed" in request.form

        channel_id = request.form.get("channel_id", "").strip()
        message_text = request.form.get("message_text", "").strip()
        embed_color = request.form.get("embed_color", "#5865F2").strip()
        embed_title = request.form.get("embed_title", "").strip()
        bg_image_url = request.form.get("bg_image_url", "").strip()

        if not message_text:
            return jsonify({
                "success": False,
                "message": "Teks pesan tidak boleh kosong."
            }), 400

        if embed_color and not embed_color.startswith("#"):
            embed_color = f"#{embed_color}"

        payload = {
            "welcome": {
                "enabled": enabled,
                "channel_id": channel_id,
                "message_text": message_text,
                "is_embed": is_embed,
                "embed_color": embed_color,
                "embed_title": embed_title,
                "bg_image_url": bg_image_url
            }
        }

        db.collection("guild_settings").document(guild_id).set(
            payload, merge=True
        )

        print(f"[WELCOME-WEB] ✅ Config tersimpan untuk guild {guild_id}")
        return jsonify({
            "success": True,
            "message": "✅ Pengaturan Welcome berhasil disimpan!"
        }), 200

    except Exception as e:
        print(f"[WELCOME-WEB] ❌ Error saat menyimpan: {e}")
        return jsonify({
            "success": False,
            "message": f"❌ Terjadi kesalahan server: {str(e)}"
        }), 500