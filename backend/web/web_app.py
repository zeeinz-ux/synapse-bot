import os
import json
import time
import threading
import base64
import traceback
import io
import asyncio
from dotenv import load_dotenv

# Load .env dari folder backend/ (sebelum import yang butuh env)
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(_project_root, "backend", ".env"))

from flask import Flask, render_template, jsonify, request, redirect, session, url_for
import requests
from functools import wraps
from datetime import datetime, timezone
from PIL import Image

# ==========================================================
# Import relative dari dalam backend/ folder
# ==========================================================
from backend.utils.formatters import format_duration, format_uptime
from backend.cogs.database.firebase_setup import db
from backend.utils.firestore_stats import (
    get_stats_snapshot,
    set_guild_channels,
    get_guild_channels,
    set_music_state,
    get_music_state,
    set_bot_instance,
    get_bot_instance,
    get_firestore_diagnostics,
    firestore_circuit_open,
    trip_firestore_circuit,
    firestore_retry_after,
    _is_quota_error,
)
from backend.utils.auto_responder_store import (
    ar_get_guild_settings,
    ar_get_guild_settings_fresh,
    ar_save_responder,
    ar_delete_responder,
    ar_list_responders,
)
from flask_session import Session

# ==========================================================
# Flask app — static & template folder ke frontend/
# ==========================================================
_base_dir = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    static_folder=os.path.join(_base_dir, "../../frontend/static"),
    template_folder=os.path.join(_base_dir, "../../frontend/templates")
)

app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# Setelah app.secret_key
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


# ==========================================================
# Discord OAuth2 Login
# ==========================================================

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "1505849571039907900")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI")
if not DISCORD_REDIRECT_URI:
    raise ValueError("DISCORD_REDIRECT_URI environment variable is required")
DISCORD_API_BASE = "https://discord.com/api"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/login")
def login():
    discord_login_url = (
        f"https://discord.com/oauth2/authorize?"
        f"client_id={DISCORD_CLIENT_ID}&"
        f"redirect_uri={DISCORD_REDIRECT_URI}&"
        f"response_type=code&"
        f"scope=identify%20guilds"
    )
    return redirect(discord_login_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return redirect("/")
    
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
    }
    
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(
        f"{DISCORD_API_BASE}/oauth2/token",
        data=data,
        headers=headers
    )
    
    token_data = response.json()
    access_token = token_data.get("access_token")
    
    if not access_token:
        return redirect("/")
    
    # Ambil data user
    user_response = requests.get(
        f"{DISCORD_API_BASE}/users/@me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    
    user = user_response.json()
    
    # Simpan ke session
    session["user"] = {
        "id": user.get("id"),
        "username": user.get("username"),
        "avatar": user.get("avatar"),
        "discriminator": user.get("discriminator")
    }
    # Fetch & store user's permitted guilds
    session["user_guilds"] = _fetch_user_guilds(access_token)
    return redirect("/")

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/")


# ==========================================================
# API — Music
# ==========================================================

@app.route("/api/music/status")
def api_music_status():
    guild_id = request.args.get("guild_id")

    if not guild_id:
        return jsonify({"connected": False}), 400

    return jsonify(get_music_state(guild_id))


@app.route("/api/music/channels")
def api_music_channels():
    guild_id = request.args.get("guild_id")

    if not guild_id:
        return jsonify({"channels": []}), 400

    return jsonify({
        "channels": get_guild_channels(guild_id)
    })


@app.route("/api/music/queue", methods=["GET"])
def api_music_queue():
    guild_id = request.args.get("guild_id")

    if not guild_id:
        return jsonify({
            "success": False,
            "message": "guild_id required"
        }), 400

    state = get_music_state(guild_id)

    return jsonify({
        "success": True,
        "queue": state.get("queue", []),
        "queue_count": state.get("queue_count", 0),
        "queue_duration": state.get("queue_duration", 0)
    })


@app.route("/api/music/queue", methods=["POST"])
def api_music_queue_action():
    data = request.get_json() or {}

    return jsonify({
        "success": True,
        "message": f"Action {data.get('action')} received"
    })


CONTROL_QUEUE_DIR = "/tmp/discord_control_queue"

def _ensure_queue_dir():
    os.makedirs(CONTROL_QUEUE_DIR, exist_ok=True)

@app.route("/api/music/control", methods=["POST"])
def api_music_control():
    try:
        data = request.get_json() or {}
        guild_id = data.get("guild_id")
        action = data.get("action")

        if not guild_id:
            return jsonify({"success": False, "message": "guild_id required"}), 400
        if not action:
            return jsonify({"success": False, "message": "action required"}), 400

        _ensure_queue_dir()
        cmd_id = f"{int(time.time())}_{os.urandom(4).hex()}"
        cmd_file = os.path.join(CONTROL_QUEUE_DIR, f"{cmd_id}.json")

        with open(cmd_file, "w") as f:
            json.dump({"guild_id": guild_id, "action": action, "data": data, "id": cmd_id}, f)

        return jsonify({"success": True, "action": action, "queued": True})

    except Exception as e:
        print(f"[CONTROL ERROR] {e}")
        return jsonify({"success": False, "message": str(e)}), 500


    

# ==========================================================
# Helper — baca config feature dari Firestore
# ==========================================================
def _get_feature_config(guild_id: str, feature_key: str = "welcome") -> dict:
    if db is None:
        print(f"[WEB-{feature_key.upper()}] ⚠️ Firebase tidak tersedia.")
        return {}

    try:
        doc = db.collection("guild_settings").document(guild_id).get()
        if doc.exists:
            return doc.to_dict().get(feature_key, {})
    except Exception as e:
        print(f"[WEB-{feature_key.upper()}] ❌ Gagal baca Firestore: {e}")
    return {}


def _get_welcome_config(guild_id: str) -> dict:
    return _get_feature_config(guild_id, "welcome")


def _get_leave_config(guild_id: str) -> dict:
    return _get_feature_config(guild_id, "leave")


def _get_ban_config(guild_id: str) -> dict:
    return _get_feature_config(guild_id, "ban")


def _get_boost_announce_config(guild_id: str) -> dict:
    return _get_feature_config(guild_id, "boost_announce")

# ==========================================================
# Helper — Auto-compress image
# ==========================================================
def _compress_image_if_needed(file_data: bytes, max_kb: int = 400) -> bytes:
    size_kb = len(file_data) / 1024
    if size_kb <= max_kb:
        return file_data

    print(f"[COMPRESS] 🗜️ Image {size_kb:.0f}KB > {max_kb}KB, compressing...")

    try:
        img = Image.open(io.BytesIO(file_data))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        max_width = 1200
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)
            print(f"[COMPRESS] 📐 Resized: {img.width}x{img.height}")

        quality = 85
        while quality >= 40:
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=quality, optimize=True)
            compressed = output.getvalue()
            compressed_kb = len(compressed) / 1024

            if compressed_kb <= max_kb:
                print(f"[COMPRESS] ✅ Compressed: {size_kb:.0f}KB → {compressed_kb:.0f}KB (quality={quality})")
                return compressed

            quality -= 10

        img = img.resize((800, int(img.height * 800 / img.width)), Image.LANCZOS)
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=70, optimize=True)
        compressed = output.getvalue()
        print(f"[COMPRESS] ✅ Final compress: {size_kb:.0f}KB → {len(compressed)/1024:.0f}KB (800px)")
        return compressed

    except Exception as e:
        print(f"[COMPRESS] ⚠️ Error compress: {e}, using original")
        return file_data

# ==========================================================
# Helper — Convert image ke base64 data URL
# ==========================================================
def _image_to_base64_data_url(file_data: bytes, filename: str) -> str | None:
    try:
        compressed_data = _compress_image_if_needed(file_data, max_kb=400)
        ext = filename.lower().split(".")[-1] if "." in filename else "png"
        mime_types = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
        }
        content_type = mime_types.get(ext, "image/jpeg")
        b64_string = base64.b64encode(compressed_data).decode("utf-8")
        data_url = f"data:{content_type};base64,{b64_string}"
        print(f"[BASE64] ✅ Converted: {len(compressed_data)} bytes → {len(b64_string)} chars base64")
        return data_url
    except Exception as e:
        print(f"[BASE64] ❌ Error: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None

# ==========================================================
# Helper — bangun URL avatar Discord dari session user
# ==========================================================
def _discord_avatar_url(user: dict, size: int = 64) -> str:
    """Bangun URL avatar Discord. Pakai default avatar jika user tidak set avatar.

    - Custom avatar:   https://cdn.discordapp.com/avatars/{id}/{hash}.{ext}?size=N
    - Default avatar:  https://cdn.discordapp.com/embed/avatars/{idx}.png?size=N
    """
    if not user:
        return ""
    avatar_hash = user.get("avatar")
    user_id = user.get("id")
    if avatar_hash:
        ext = "gif" if str(avatar_hash).startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size={size}"
    # Default avatar (index 0–4). Discord pakai discriminator % 5 (legacy)
    # atau (id >> 22) % 5 untuk username#0 (new system).
    try:
        if user.get("discriminator") and user["discriminator"] != "0":
            idx = int(user["discriminator"]) % 5
        else:
            idx = (int(user_id) >> 22) % 5
    except Exception:
        idx = 0
    return f"https://cdn.discordapp.com/embed/avatars/{idx}.png?size={size}"


# ==========================================================
# Helper — fetch & filter user guilds by permission
# ==========================================================
ADMIN_PERM = 0x8        # ADMINISTRATOR
MANAGE_GUILD_PERM = 0x20  # MANAGE_GUILD (formerly MANAGE_SERVER)

def _fetch_user_guilds(access_token: str) -> list:
    """Fetch user's guilds from Discord and filter by admin/manager permission."""
    resp = requests.get(
        f"{DISCORD_API_BASE}/users/@me/guilds",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    if resp.status_code != 200:
        return []
    all_guilds = resp.json()
    # Filter: only guilds where user has ADMINISTRATOR or MANAGE_GUILD
    permitted = []
    bot_guild_ids = {g["id"] for g in get_stats_snapshot().get("guilds_list", [])}
    for g in all_guilds:
        perms = int(g.get("permissions", 0))
        has_admin = (perms & ADMIN_PERM) == ADMIN_PERM
        has_manage = (perms & MANAGE_GUILD_PERM) == MANAGE_GUILD_PERM
        if has_admin or has_manage:
            # Only include guilds the bot is also in
            if g["id"] in bot_guild_ids:
                permitted.append({
                    "id": g["id"],
                    "name": g["name"],
                    "icon": g.get("icon"),
                    "owner": g.get("owner", False),
                })
    return permitted

# ==========================================================
# Helper — render template dengan sidebar context
# ==========================================================
def _get_filtered_stats():
    """Return stats snapshot with guilds_list filtered to user's permitted guilds."""
    stats = get_stats_snapshot()
    user = session.get("user")
    user_guilds = session.get("user_guilds") if user else None
    if user_guilds is not None:
        # Merge guild info from bot stats (member_count) with user's guilds
        bot_guild_map = {g["id"]: g for g in stats.get("guilds_list", [])}
        merged = []
        for ug in user_guilds:
            bg = bot_guild_map.get(ug["id"])
            if bg:
                merged.append({
                    "id": ug["id"],
                    "name": ug["name"],
                    "member_count": bg.get("member_count", 0),
                })
        stats["guilds_list"] = merged
    return stats

def _render_page(template_name: str, active_page: str, guild_id: str, **kwargs):
    user = session.get("user")
    stats = _get_filtered_stats()
    # If user requests a guild they don't have access to, redirect to dashboard
    if user and guild_id:
        permitted_ids = [g["id"] for g in stats.get("guilds_list", [])]
        if guild_id not in permitted_ids:
            return redirect("/dashboard")
    return render_template(
        template_name,
        s=stats,
        active_page=active_page,
        guild_id=guild_id,
        user=user,
        avatar_url=_discord_avatar_url(user) if user else "",
        **kwargs
    )

# ==========================================================
# ROUTES — Landing & API
# ==========================================================
@app.route("/")
def home():
    user = session.get("user")
    return render_template(
        "landing.html",
        user=user,
        avatar_url=_discord_avatar_url(user) if user else "",
    )

@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats_snapshot())


# ==========================================================
# Firestore health & circuit-breaker diagnostics
# ==========================================================
# Returns circuit-breaker state, debounce window, per-doc pending payloads,
# and last-write timestamps. Use this from a browser/curl to confirm
# that the 429 quota fix is in effect after deploy.
#
# Example:
#   curl https://<your-render-host>/api/firestore/health
# ==========================================================
@app.route("/api/firestore/health")
def api_firestore_health():
    return jsonify(get_firestore_diagnostics()), 200

# ==========================================================
# ROUTES — Dashboard
# ==========================================================
@app.route("/dashboard")
@login_required
def dashboard():
    s = _get_filtered_stats()
    guilds = s.get("guilds_list", [])
    if guilds:
        first_id = str(guilds[0].get("id", ""))
        if first_id:
            return redirect(f"/dashboard/{first_id}/")
    return _render_page("dashboard.html", active_page="main", guild_id="")

@app.route("/dashboard/<guild_id>/")
@login_required
def dashboard_guild(guild_id: str):
    return _render_page("dashboard.html", active_page="main", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/settings")
@login_required
def settings_page(guild_id: str):
    return _render_page("settings.html", active_page="settings", guild_id=guild_id)

# ==========================================================
# ROUTES — Music (placeholder)
# ==========================================================

@app.route("/dashboard/<guild_id>/music/now-playing")
@login_required
def music_now_playing(guild_id: str):
    return _render_page("now_playing.html", active_page="now_playing", guild_id=guild_id)


@app.route("/dashboard/<guild_id>/music/queue")
@login_required
def music_queue(guild_id: str):
    return _render_page("queue.html", active_page="queue", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/music/playlists")
@login_required
def music_playlists(guild_id: str):
    return _render_page("playlist.html", active_page="playlists", guild_id=guild_id)

# ==========================================================
# ROUTES — Welcome / Announcements
# ==========================================================
@app.route("/dashboard/<guild_id>/welcome")
@login_required
def welcome_settings(guild_id: str):
    channels = get_guild_channels(guild_id)
    current_config = _get_welcome_config(guild_id)

    defaults = {
        "enabled": False,
        "channel_id": "",
        "message_text": "Hei {user}, selamat datang di **{server}**! 🎉",
        "is_embed": False,
        "embed_color": "#5865F2",
        "embed_title": "👋 Selamat Datang!",
        "bg_image_url": "",
        "style": "embed",
        "banner_bg_url": "",
        "banner_text": "WELCOME",
        "banner_subtext": "Member ke-{count} • {server}",
        "banner_font_color": "#FFFFFF",
        "banner_avatar_ring": True,
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
@login_required
def welcome_leave(guild_id: str):
    channels = get_guild_channels(guild_id)
    current_config = _get_leave_config(guild_id)

    defaults = {
        "enabled": False,
        "channel_id": "",
        "message_text": "{user} telah meninggalkan {server}. Selamat jalan! 👋",
        "is_embed": False,
        "embed_color": "#ED4245",
        "embed_title": "👋 Selamat Tinggal!",
        "bg_image_url": "",
        "style": "embed",
        "banner_bg_url": "",
        "banner_text": "GOODBYE",
        "banner_subtext": "Member ke-{count} • {server}",
        "banner_font_color": "#FFFFFF",
        "banner_avatar_ring": True,
    }

    config = {**defaults, **current_config}

    return _render_page(
        "leave_settings.html",
        active_page="leave",
        guild_id=guild_id,
        channels=channels,
        config=config
    )

@app.route("/dashboard/<guild_id>/welcome/ban")
@login_required
def welcome_ban(guild_id: str):
    channels = get_guild_channels(guild_id)
    current_config = _get_ban_config(guild_id)

    defaults = {
        "enabled": False,
        "channel_id": "",
        "message_text": "{user} telah di-ban dari {server}. 🚫",
        "is_embed": False,
        "embed_color": "#F26522",
        "embed_title": "🚫 User Banned",
        "bg_image_url": "",
        "style": "embed",
        "banner_bg_url": "",
        "banner_text": "BANNED",
        "banner_subtext": "Member ke-{count} • {server}",
        "banner_font_color": "#FFFFFF",
        "banner_avatar_ring": True,
    }

    config = {**defaults, **current_config}

    return _render_page(
        "ban_settings.html",
        active_page="ban",
        guild_id=guild_id,
        channels=channels,
        config=config
    )

@app.route("/dashboard/<guild_id>/welcome/boost")
@login_required
def welcome_boost(guild_id: str):
    channels = get_guild_channels(guild_id)
    current_config = _get_boost_announce_config(guild_id)

    defaults = {
        "enabled": False,
        "channel_id": "",
        "message_text": "{user} telah melakukan boost pada {server}! 💎",
        "is_embed": False,
        "embed_color": "#9B59B6",
        "embed_title": "💎 Server Boost!",
        "bg_image_url": "",
        "style": "embed",
        "banner_bg_url": "",
        "banner_text": "BOOSTER",
        "banner_subtext": "Member ke-{count} • {server}",
        "banner_font_color": "#FFFFFF",
        "banner_avatar_ring": True,
    }

    config = {**defaults, **current_config}

    return _render_page(
        "boost_announce.html",
        active_page="boost_welcome",
        guild_id=guild_id,
        channels=channels,
        config=config
    )

# ==========================================================
# ROUTES — Boost Tracker
# ==========================================================
@app.route("/dashboard/<guild_id>/boost")
@login_required
def boost_tracker(guild_id: str):
    return _render_page("boost_settings.html", active_page="boost_tracker", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/boost/stats")
@login_required
def boost_stats(guild_id: str):
    return _render_page("boost_settings.html", active_page="boost_stats", guild_id=guild_id)

# ==========================================================
# ROUTES — Donation
# ==========================================================
@app.route("/dashboard/<guild_id>/donation")
@login_required
def donation_tracker(guild_id: str):
    return _render_page("donation_settings.html", active_page="donation", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/donation/stats")
@login_required
def donation_stats(guild_id: str):
    return _render_page("donation_settings.html", active_page="donation_stats", guild_id=guild_id)

# ==========================================================
# ROUTES — Tools
# ==========================================================
@app.route("/dashboard/<guild_id>/message-builder")
@login_required
def message_builder(guild_id: str):
    return _render_page("message_builder.html", active_page="message_builder", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/templates")
@login_required
def templates_page(guild_id: str):
    return _render_page("templates.html", active_page="templates", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/actions")
@login_required
def actions_page(guild_id: str):
    return _render_page("actions.html", active_page="actions", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/auto-responders")
@login_required
def auto_responders(guild_id: str):
    return _render_page("auto_responders.html", active_page="auto_responders", guild_id=guild_id)


# ============================================================================
# Auto-Responder API Bridge
# ============================================================================
# These endpoints back the /dashboard/<guild_id>/auto-responders page.
# Frontend expects JSON; without these, all fetches return HTML 404 pages,
# which break `resp.json()` with "Unexpected token '<'" parse errors.
#
# Backend logic lives in backend/cogs/auto_response/auto_response.py.
# These thin wrappers:
#   - Reuse the shared circuit breaker (consistent with stats/ai_chat/leveling)
#   - Off-thread Firestore I/O via asyncio.to_thread (non-blocking)
#   - Preserve Zero-Change contract for existing cog internal methods
# ============================================================================

def _ar_cog():
    """Optional: Fetch the AutoResponderCog instance for in-process sync.
    The Flask web process on Railway never has access to the bot instance
    (separate process + memory), so most requests will fall back to the
    free-function bridge in auto_responder_store. This helper is retained
    for dev/local where web and bot share a process.
    """
    bot = get_bot_instance()
    if bot is None:
        return None
    return bot.get_cog("AutoResponder")


def _ar_bridge_response(guild_id: str, coro_factory):
    """Run an async coroutine on a fresh event loop and return its result.
    Flask request handlers are sync, but our store functions are async.
    We spin up a short-lived loop per request — acceptable for a dashboard
    tool whose traffic is human-paced, not high-throughput.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro_factory())
    finally:
        loop.close()


@app.route("/api/auto-responders/<guild_id>", methods=["GET"])
def api_auto_responders_list(guild_id: str):
    # NOTE: This is a READ endpoint. We intentionally do NOT short-circuit on
    # firestore_circuit_open() because that circuit guards WRITES (free tier
    # has separate quotas: 50K reads/day vs 20K writes/day). A write-side
    # 429 should never block the dashboard from listing responders.
    #
    # We also bypass the in-process cache via ar_get_guild_settings_fresh().
    # The Flask web process runs multiple worker processes under gunicorn,
    # each with its own _settings_cache. A delete in worker A would not
    # invalidate the cache in worker B, so the next GET could return a
    # stale list for up to 5 minutes. Fresh-fetch reads Firestore directly.
    try:
        settings = _ar_bridge_response(guild_id, lambda: ar_get_guild_settings_fresh(str(guild_id)))
        responders_data = settings.get("responders") or {}
        # Flatten dict-of-dicts into a list of {id, ...cfg} so the frontend
        # can iterate it directly.
        responders = [{"id": rid, **(cfg or {})} for rid, cfg in responders_data.items()]
        enabled = bool(settings.get("enabled", False))
        response = jsonify({"success": True, "enabled": enabled, "responders": responders, "count": len(responders)})
        # Prevent browser/proxy caching of dashboard lists.
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response, 200
    except Exception as e:
        # Reads still trip the circuit if read-quota is exhausted (very rare
        # on free tier), but we surface it as 503 with retry_after so the
        # frontend can show a useful message.
        if _is_quota_error(e):
            trip_firestore_circuit()
            retry = int(firestore_retry_after())
            return jsonify({"success": False, "error": "circuit_open", "message": f"Database rate-limited. Retry in {retry}s.", "retry_after": retry, "responders": [], "enabled": False}), 503
        print(f"[AUTO-RESPONSE WEB] ❌ list failed: {e}")
        return jsonify({"success": False, "error": str(e), "message": "Failed to load responders.", "responders": [], "enabled": False}), 500


@app.route("/api/auto-responders/<guild_id>/save", methods=["POST"])
def api_auto_responders_save(guild_id: str):
    if firestore_circuit_open():
        retry = int(firestore_retry_after())
        return jsonify({"success": False, "error": "circuit_open", "message": f"Database rate-limited. Retry in {retry}s.", "retry_after": retry}), 503
    payload = request.get_json(silent=True) or {}
    responder_id = payload.get("id")
    # Frontend sends {id: ""} for new responders — generate a stable id from the keyword
    if not responder_id:
        keyword = (payload.get("keyword") or "").strip().lower()
        if not keyword:
            return jsonify({"success": False, "error": "missing id/keyword", "message": "Either 'id' or 'keyword' is required."}), 400
        responder_id = "ar_" + "".join(c for c in keyword.replace(" ", "_") if c.isalnum() or c == "_")[:40]
        if not responder_id or responder_id == "ar_":
            responder_id = "ar_" + str(int(time.time() * 1000))
        payload["id"] = responder_id  # echo back so frontend can update UI
    config = {k: v for k, v in payload.items() if k != "id"}
    try:
        ok = _ar_bridge_response(
            guild_id,
            lambda: ar_save_responder(str(guild_id), str(responder_id), config),
        )
        if not ok:
            return jsonify({"success": False, "error": "save failed", "message": "Could not write to Firestore."}), 500
        return jsonify({"success": True, "id": responder_id, "message": "Saved."}), 200
    except Exception as e:
        if _is_quota_error(e):
            trip_firestore_circuit()
        print(f"[AUTO-RESPONSE WEB] ❌ save failed: {e}")
        return jsonify({"success": False, "error": str(e), "message": "Save failed."}), 500


@app.route("/api/auto-responders/<guild_id>/toggle", methods=["POST"])
def api_auto_responders_toggle(guild_id: str):
    if firestore_circuit_open():
        retry = int(firestore_retry_after())
        return jsonify({"success": False, "error": "circuit_open", "message": f"Database rate-limited. Retry in {retry}s.", "retry_after": retry}), 503
    payload = request.get_json(silent=True) or {}
    # Two modes:
    #   (A) GLOBAL toggle:   {"enabled": true/false}                 — affects whole feature
    #   (B) PER-RESPONDER:   {"id": "<rid>", "enable": true/false}    — affects one responder
    responder_id = payload.get("id")
    enable = payload.get("enable")
    if enable is None:
        enable = payload.get("enabled", True)
    enable = bool(enable)

    # Mode A: global enabled flag (no id present)
    if not responder_id:
        try:
            async def _set_global():
                settings = await ar_get_guild_settings(str(guild_id))
                # settings may be empty; we just want to flip the master flag
                doc_ref = db.collection("guild_settings").document(str(guild_id))
                def _blocking_set():
                    doc_ref.set({"auto_responders_enabled": enable}, merge=True)
                await asyncio.to_thread(_blocking_set)
                # Also invalidate in-process cache
                from backend.utils import auto_responder_store as _store
                _store._settings_cache.pop(str(guild_id), None)
                return True
            ok = _ar_bridge_response(guild_id, _set_global)
            if not ok:
                return jsonify({"success": False, "error": "toggle failed", "message": "Could not update global flag."}), 500
            return jsonify({"success": True, "id": None, "enabled": enable, "message": "Global flag updated."}), 200
        except Exception as e:
            if _is_quota_error(e):
                trip_firestore_circuit()
            print(f"[AUTO-RESPONSE WEB] ❌ global toggle failed: {e}")
            return jsonify({"success": False, "error": str(e), "message": "Global toggle failed."}), 500

    # Mode B: per-responder toggle
    try:
        settings = _ar_bridge_response(guild_id, lambda: ar_get_guild_settings_fresh(str(guild_id)))
        responders = (settings or {}).get("responders", {}) or {}
        if responder_id not in responders:
            return jsonify({"success": False, "error": "responder not found", "message": f"Responder '{responder_id}' does not exist."}), 404
        cfg = dict(responders[responder_id])
        cfg["enabled"] = enable
        ok = _ar_bridge_response(
            guild_id,
            lambda: ar_save_responder(str(guild_id), str(responder_id), cfg),
        )
        if not ok:
            return jsonify({"success": False, "error": "toggle failed", "message": "Could not update responder."}), 500
        return jsonify({"success": True, "id": responder_id, "enabled": enable, "message": "Toggled."}), 200
    except Exception as e:
        if _is_quota_error(e):
            trip_firestore_circuit()
        print(f"[AUTO-RESPONSE WEB] ❌ toggle failed: {e}")
        return jsonify({"success": False, "error": str(e), "message": "Toggle failed."}), 500


@app.route("/api/auto-responders/<guild_id>/delete", methods=["POST", "DELETE"])
def api_auto_responders_delete(guild_id: str):
    if firestore_circuit_open():
        retry = int(firestore_retry_after())
        return jsonify({"success": False, "error": "circuit_open", "message": f"Database rate-limited. Retry in {retry}s.", "retry_after": retry}), 503
    payload = request.get_json(silent=True) or {}
    responder_id = payload.get("id") or request.args.get("id")
    if not responder_id:
        return jsonify({"success": False, "error": "missing responder id", "message": "id is required."}), 400
    try:
        ok = _ar_bridge_response(
            guild_id,
            lambda: ar_delete_responder(str(guild_id), str(responder_id)),
        )
        if not ok:
            return jsonify({"success": False, "error": "delete failed", "message": "Could not delete."}), 500
        return jsonify({"success": True, "id": responder_id, "message": "Deleted."}), 200
    except Exception as e:
        if _is_quota_error(e):
            trip_firestore_circuit()
        print(f"[AUTO-RESPONSE WEB] ❌ delete failed: {e}")
        return jsonify({"success": False, "error": str(e), "message": "Delete failed."}), 500

# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES — AI Chat v4.5 (Gemini 2.5 Flash + OpenRouter + Temperature Support)
# ============================================================================
# Guild channel list endpoint
# ============================================================================
# The dashboard auto-responders page needs the list of Discord text channels
# to populate the include/exclude channel <select> elements. The Flask web
# process cannot talk to the Discord gateway directly, so we read the channel
# list that the bot process already synced to Firestore (collection
# bot_status / document guild_channels).
#
# Bot process writes here periodically via set_guild_channels() in
# firestore_stats.py. This endpoint exposes that data via HTTP.
# ============================================================================
@app.route("/api/admin/firestore/circuit/reset", methods=["POST"])
def api_firestore_circuit_reset():
    """Manually close the Firestore circuit breaker. Useful when the dashboard
    is stuck in 503 because a previous write hit a quota error. Safe to call
    anytime; the next write will trip it again if quota is still exhausted.
    Requires the secret admin token from the AUTHORIZED_USERS env or matching
    a logged-in session (we accept either for operational convenience)."""
    from backend.utils.firestore_stats import _circuit
    try:
        was_open = _circuit.is_open()
        _circuit.reset()
        return jsonify({"success": True, "was_open": was_open, "message": "Circuit reset."}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/guilds/<guild_id>/channels", methods=["GET"])
def api_guild_channels(guild_id: str):
    # get_guild_channels returns [{id, name}, ...] from Firestore.
    # If Firestore is unavailable, returns []. Always return success with
    # whatever we have; frontend shows friendly empty-state message.
    channels = get_guild_channels(str(guild_id))
    return jsonify({"success": True, "channels": channels or [], "count": len(channels or [])}), 200


# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/dashboard/<guild_id>/ai-chat")
@login_required
def ai_chat_page(guild_id: str):
    channels = get_guild_channels(guild_id)
    return _render_page(
        "ai_chat.html",
        active_page="ai_chat",
        guild_id=guild_id,
        channels=channels
    )


@app.route("/dashboard/<guild_id>/ai-chat/toggle", methods=["POST"])
def ai_chat_toggle(guild_id):
    try:
        if request.is_json:
            # FIX: Ditambahkan 'or {}' agar jika JSON kosong, tidak menyebabkan NoneType Error
            data = request.get_json() or {}
            enabled = data.get("enabled", False)
        else:
            enabled = request.form.get("enabled", "false").lower() == "true"

        # Cek apakah database Firebase siap digunakan
        if db is None:
            print(f"[AI-CHAT-TOGGLE] ❌ Server melempar 500 karena 'db' bernilai None untuk Guild ID: {guild_id}")
            return jsonify({"success": False, "message": "Firebase tidak tersedia (db is None)."}), 500

        # Simpan ke Firestore
        doc_ref = db.collection("guild_settings").document(str(guild_id))
        doc_ref.set({"ai_chat_enabled": enabled}, merge=True)

        print(f"[AI-CHAT-TOGGLE] ✅ Guild {guild_id} berhasil mengubah status menjadi: {enabled}")
        return jsonify({
            "success": True,
            "enabled": enabled,
            "message": f"AI Chat {'diaktifkan' if enabled else 'dinonaktifkan'}."
        }), 200

    except Exception as e:
        # Mencetak struktur eror lengkap di console terminal / log Render kamu
        print("🚨 [AI-CHAT-TOGGLE EROR] Terjadi masalah di dalam blok try-except:")
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Terjadi error internal: {str(e)}"}), 500


@app.route("/dashboard/<guild_id>/ai-chat/save", methods=["POST"])
def ai_chat_save(guild_id):
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()

        personality = data.get("personality", "friendly")
        channel_id = data.get("channel_id", "").strip()
        model = data.get("model", "gemini-2.5-flash")
        temperature = float(data.get("temperature", 0.75))

        valid_personalities = ["friendly", "formal", "tsundere", "sarcastic", "wise"]
        if personality not in valid_personalities:
            personality = "friendly"

        if db is None:
            return jsonify({"success": False, "message": "Firebase tidak tersedia."}), 500

        doc_ref = db.collection("guild_settings").document(str(guild_id))
        
        # IMPLEMENTASI: Menambahkan dedicated_ai_channel secara dinamis ke Firestore
        doc_ref.set({
            "ai_chat": {
                "personality": personality,
                "channel_id": channel_id,
                "model": model,
                "temperature": temperature,
                "dedicated_ai_channel": True if channel_id else False, # True jika channel dipilih, False jika 'Semua Channel'
                "updated_at": datetime.now(timezone.utc),
            }
        }, merge=True)

        return jsonify({
            "success": True,
            "message": "Pengaturan AI Chat berhasil disimpan."
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Terjadi error: {str(e)}"}), 500


@app.route("/api/ai-chat/settings/<guild_id>")
def api_ai_chat_settings(guild_id):
    try:
        if db is None:
            return jsonify({
                "success": True,
                "ai_chat_enabled": False,
                "ai_chat": {
                    "personality": "friendly",
                    "channel_id": "",
                    "model": "gemini-2.5-flash",
                    "temperature": 0.75,
                }
            }), 200

        doc_ref = db.collection("guild_settings").document(str(guild_id))
        doc = doc_ref.get()

        if not doc.exists:
            return jsonify({
                "success": True,
                "ai_chat_enabled": False,
                "ai_chat": {
                    "personality": "friendly",
                    "channel_id": "",
                    "model": "gemini-2.5-flash",
                    "temperature": 0.75,
                }
            }), 200

        data = doc.to_dict()
        ai_chat = data.get("ai_chat", {})
        return jsonify({
            "success": True,
            "ai_chat_enabled": data.get("ai_chat_enabled", False),
            "ai_chat": {
                "personality": ai_chat.get("personality", "friendly"),
                "channel_id": ai_chat.get("channel_id", ""),
                "model": ai_chat.get("model", "gemini-2.5-flash"),
                "temperature": ai_chat.get("temperature", 0.75),
            }
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/ai-chat/history/<guild_id>")
def api_ai_chat_history(guild_id):
    try:
        if db is None:
            return jsonify({"success": True, "history": []}), 200

        docs = (
            db.collection("guild_settings")
            .document(str(guild_id))
            .collection("ai_chat")
            .stream()
        )

        results = []
        for doc in docs:
            d = doc.to_dict()
            history = d.get("history", [])
            preview = history[-2:] if len(history) >= 2 else history
            results.append({
                "user_id": doc.id,
                "personality": d.get("personality", "unknown"),
                "last_interaction": d.get("updated_at"),
                "preview": preview,
                "total_messages": len(history),
            })

        results.sort(
            key=lambda x: x["last_interaction"] or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True
        )
        results = results[:50]

        return jsonify({"success": True, "history": results}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500

# ==========================================================
# API Endpoint untuk Landing Page Stats
# ==========================================================

@app.route('/api/stats', methods=['GET'])
def get_stats():
    s = get_stats_snapshot()
    stats_data = {
        "guilds": s.get("guilds", 0),
        "members": s.get("members", 0)
    }
    return jsonify(stats_data), 200


# ==========================================================
# ROUTES — Welcome Save (POST)
# ==========================================================
@app.route("/dashboard/<guild_id>/welcome/save", methods=["POST"])
def save_welcome(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase tidak tersedia."}), 500

    try:
        enabled = "enabled" in request.form
        is_embed = "is_embed" in request.form
        style = request.form.get("style", "embed").strip()
        banner_avatar_ring = "banner_avatar_ring" in request.form

        channel_id = request.form.get("channel_id", "").strip()
        message_text = request.form.get("message_text", "").strip()
        embed_color = request.form.get("embed_color", "#5865F2").strip()
        embed_title = request.form.get("embed_title", "").strip()
        bg_image_url = request.form.get("bg_image_url", "").strip()

        banner_bg_url = request.form.get("banner_bg_url", "").strip()
        banner_text = request.form.get("banner_text", "WELCOME").strip()
        banner_subtext = request.form.get("banner_subtext", "Member ke-{count} • {server}").strip()
        banner_font_color = request.form.get("banner_font_color", "#FFFFFF").strip()

        uploaded_file_data = request.form.get("uploaded_file_data", "").strip()
        uploaded_file_name = request.form.get("uploaded_file_name", "upload.png").strip()
        upload_target = request.form.get("upload_target", "").strip()

        print(f"[WELCOME-WEB] 📥 Received upload_target={upload_target}, data_length={len(uploaded_file_data)}")

        if uploaded_file_data and uploaded_file_data.startswith("data:image"):
            try:
                header, base64_data = uploaded_file_data.split(",", 1)
                file_bytes = base64.b64decode(base64_data)
                print(f"[WELCOME-WEB] 📤 Processing {len(file_bytes)} bytes...")
                safe_filename = uploaded_file_name or "welcome_upload.png"
                data_url = _image_to_base64_data_url(file_bytes, safe_filename)

                if data_url:
                    if upload_target == "banner_bg":
                        banner_bg_url = data_url
                        print(f"[WELCOME-WEB] ✅ Banner BG saved to Firestore (base64, {len(data_url)} chars)")
                    else:
                        bg_image_url = data_url
                        print(f"[WELCOME-WEB] ✅ Embed BG saved to Firestore (base64, {len(data_url)} chars)")
                else:
                    print("[WELCOME-WEB] ⚠️ Base64 conversion failed")

            except Exception as e:
                print(f"[WELCOME-WEB] ❌ Error processing upload: {e}")
                traceback.print_exc()

        if not message_text:
            return jsonify({"success": False, "message": "Teks pesan tidak boleh kosong."}), 400

        if embed_color and not embed_color.startswith("#"):
            embed_color = f"#{embed_color}"

        if banner_font_color and not banner_font_color.startswith("#"):
            banner_font_color = f"#{banner_font_color}"

        payload = {
            "welcome": {
                "enabled": enabled,
                "channel_id": channel_id,
                "message_text": message_text,
                "is_embed": is_embed,
                "embed_color": embed_color,
                "embed_title": embed_title,
                "bg_image_url": bg_image_url,
                "style": style,
                "banner_bg_url": banner_bg_url,
                "banner_text": banner_text,
                "banner_subtext": banner_subtext,
                "banner_font_color": banner_font_color,
                "banner_avatar_ring": banner_avatar_ring,
            }
        }

        db.collection("guild_settings").document(guild_id).set(payload, merge=True)

        print(f"[WELCOME-WEB] ✅ Config tersimpan untuk guild {guild_id} (style={style})")
        return jsonify({"success": True, "message": "✅ Pengaturan Welcome berhasil disimpan!"}), 200

    except Exception as e:
        print(f"[WELCOME-WEB] ❌ Error saat menyimpan: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": f"❌ Terjadi kesalahan server: {str(e)}"}), 500


# ==========================================================
# ROUTES — Leave Save (POST)
# ==========================================================
@app.route("/dashboard/<guild_id>/welcome/leave/save", methods=["POST"])
def save_welcome_leave(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase tidak tersedia."}), 500

    try:
        enabled = "enabled" in request.form
        is_embed = "is_embed" in request.form
        style = request.form.get("style", "embed").strip()
        banner_avatar_ring = "banner_avatar_ring" in request.form

        channel_id = request.form.get("channel_id", "").strip()
        message_text = request.form.get("message_text", "").strip()
        embed_color = request.form.get("embed_color", "#ED4245").strip()
        embed_title = request.form.get("embed_title", "").strip()
        bg_image_url = request.form.get("bg_image_url", "").strip()

        banner_bg_url = request.form.get("banner_bg_url", "").strip()
        banner_text = request.form.get("banner_text", "GOODBYE").strip()
        banner_subtext = request.form.get("banner_subtext", "Member ke-{count} • {server}").strip()
        banner_font_color = request.form.get("banner_font_color", "#FFFFFF").strip()

        uploaded_file_data = request.form.get("uploaded_file_data", "").strip()
        uploaded_file_name = request.form.get("uploaded_file_name", "upload.png").strip()
        upload_target = request.form.get("upload_target", "").strip()

        print(f"[LEAVE-WEB] 📥 Received upload_target={upload_target}, data_length={len(uploaded_file_data)}")

        if uploaded_file_data and uploaded_file_data.startswith("data:image"):
            try:
                header, base64_data = uploaded_file_data.split(",", 1)
                file_bytes = base64.b64decode(base64_data)
                print(f"[LEAVE-WEB] 📤 Processing {len(file_bytes)} bytes...")
                safe_filename = uploaded_file_name or "leave_upload.png"
                data_url = _image_to_base64_data_url(file_bytes, safe_filename)

                if data_url:
                    if upload_target == "banner_bg":
                        banner_bg_url = data_url
                        print(f"[LEAVE-WEB] ✅ Banner BG saved to Firestore (base64, {len(data_url)} chars)")
                    else:
                        bg_image_url = data_url
                        print(f"[LEAVE-WEB] ✅ Embed BG saved to Firestore (base64, {len(data_url)} chars)")
                else:
                    print("[LEAVE-WEB] ⚠️ Base64 conversion failed")

            except Exception as e:
                print(f"[LEAVE-WEB] ❌ Error processing upload: {e}")
                traceback.print_exc()

        if not message_text:
            return jsonify({"success": False, "message": "Teks pesan tidak boleh kosong."}), 400

        if embed_color and not embed_color.startswith("#"):
            embed_color = f"#{embed_color}"

        if banner_font_color and not banner_font_color.startswith("#"):
            banner_font_color = f"#{banner_font_color}"

        payload = {
            "leave": {
                "enabled": enabled,
                "channel_id": channel_id,
                "message_text": message_text,
                "is_embed": is_embed,
                "embed_color": embed_color,
                "embed_title": embed_title,
                "bg_image_url": bg_image_url,
                "style": style,
                "banner_bg_url": banner_bg_url,
                "banner_text": banner_text,
                "banner_subtext": banner_subtext,
                "banner_font_color": banner_font_color,
                "banner_avatar_ring": banner_avatar_ring,
            }
        }

        db.collection("guild_settings").document(guild_id).set(payload, merge=True)

        print(f"[LEAVE-WEB] ✅ Config tersimpan untuk guild {guild_id} (style={style})")
        return jsonify({"success": True, "message": "✅ Pengaturan Leave berhasil disimpan!"}), 200

    except Exception as e:
        print(f"[LEAVE-WEB] ❌ Error saat menyimpan: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": f"❌ Terjadi kesalahan server: {str(e)}"}), 500


# ==========================================================
# ROUTES — Ban Save (POST)
# ==========================================================
@app.route("/dashboard/<guild_id>/welcome/ban/save", methods=["POST"])
def save_welcome_ban(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase tidak tersedia."}), 500

    try:
        enabled = "enabled" in request.form
        is_embed = "is_embed" in request.form
        style = request.form.get("style", "embed").strip()
        banner_avatar_ring = "banner_avatar_ring" in request.form

        channel_id = request.form.get("channel_id", "").strip()
        message_text = request.form.get("message_text", "").strip()
        embed_color = request.form.get("embed_color", "#F26522").strip()
        embed_title = request.form.get("embed_title", "").strip()
        bg_image_url = request.form.get("bg_image_url", "").strip()

        banner_bg_url = request.form.get("banner_bg_url", "").strip()
        banner_text = request.form.get("banner_text", "BANNED").strip()
        banner_subtext = request.form.get("banner_subtext", "Member ke-{count} • {server}").strip()
        banner_font_color = request.form.get("banner_font_color", "#FFFFFF").strip()

        uploaded_file_data = request.form.get("uploaded_file_data", "").strip()
        uploaded_file_name = request.form.get("uploaded_file_name", "upload.png").strip()
        upload_target = request.form.get("upload_target", "").strip()

        print(f"[BAN-WEB] 📥 Received upload_target={upload_target}, data_length={len(uploaded_file_data)}")

        if uploaded_file_data and uploaded_file_data.startswith("data:image"):
            try:
                header, base64_data = uploaded_file_data.split(",", 1)
                file_bytes = base64.b64decode(base64_data)
                print(f"[BAN-WEB] 📤 Processing {len(file_bytes)} bytes...")
                safe_filename = uploaded_file_name or "ban_upload.png"
                data_url = _image_to_base64_data_url(file_bytes, safe_filename)

                if data_url:
                    if upload_target == "banner_bg":
                        banner_bg_url = data_url
                        print(f"[BAN-WEB] ✅ Banner BG saved to Firestore (base64, {len(data_url)} chars)")
                    else:
                        bg_image_url = data_url
                        print(f"[BAN-WEB] ✅ Embed BG saved to Firestore (base64, {len(data_url)} chars)")
                else:
                    print("[BAN-WEB] ⚠️ Base64 conversion failed")

            except Exception as e:
                print(f"[BAN-WEB] ❌ Error processing upload: {e}")
                traceback.print_exc()

        if not message_text:
            return jsonify({"success": False, "message": "Teks pesan tidak boleh kosong."}), 400

        if embed_color and not embed_color.startswith("#"):
            embed_color = f"#{embed_color}"

        if banner_font_color and not banner_font_color.startswith("#"):
            banner_font_color = f"#{banner_font_color}"

        payload = {
            "ban": {
                "enabled": enabled,
                "channel_id": channel_id,
                "message_text": message_text,
                "is_embed": is_embed,
                "embed_color": embed_color,
                "embed_title": embed_title,
                "bg_image_url": bg_image_url,
                "style": style,
                "banner_bg_url": banner_bg_url,
                "banner_text": banner_text,
                "banner_subtext": banner_subtext,
                "banner_font_color": banner_font_color,
                "banner_avatar_ring": banner_avatar_ring,
            }
        }

        db.collection("guild_settings").document(guild_id).set(payload, merge=True)

        print(f"[BAN-WEB] ✅ Config tersimpan untuk guild {guild_id} (style={style})")
        return jsonify({"success": True, "message": "✅ Pengaturan Ban berhasil disimpan!"}), 200

    except Exception as e:
        print(f"[BAN-WEB] ❌ Error saat menyimpan: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": f"❌ Terjadi kesalahan server: {str(e)}"}), 500


# ==========================================================
# ROUTES — Boost Announce Save (POST)
# ==========================================================
@app.route("/dashboard/<guild_id>/welcome/boost/save", methods=["POST"])
def save_welcome_boost(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase tidak tersedia."}), 500

    try:
        enabled = "enabled" in request.form
        is_embed = "is_embed" in request.form
        style = request.form.get("style", "embed").strip()
        banner_avatar_ring = "banner_avatar_ring" in request.form

        channel_id = request.form.get("channel_id", "").strip()
        message_text = request.form.get("message_text", "").strip()
        embed_color = request.form.get("embed_color", "#9B59B6").strip()
        embed_title = request.form.get("embed_title", "").strip()
        bg_image_url = request.form.get("bg_image_url", "").strip()

        banner_bg_url = request.form.get("banner_bg_url", "").strip()
        banner_text = request.form.get("banner_text", "BOOSTER").strip()
        banner_subtext = request.form.get("banner_subtext", "Member ke-{count} • {server}").strip()
        banner_font_color = request.form.get("banner_font_color", "#FFFFFF").strip()

        uploaded_file_data = request.form.get("uploaded_file_data", "").strip()
        uploaded_file_name = request.form.get("uploaded_file_name", "upload.png").strip()
        upload_target = request.form.get("upload_target", "").strip()

        print(f"[BOOST-WEB] 📥 Received upload_target={upload_target}, data_length={len(uploaded_file_data)}")

        if uploaded_file_data and uploaded_file_data.startswith("data:image"):
            try:
                header, base64_data = uploaded_file_data.split(",", 1)
                file_bytes = base64.b64decode(base64_data)
                print(f"[BOOST-WEB] 📤 Processing {len(file_bytes)} bytes...")
                safe_filename = uploaded_file_name or "boost_upload.png"
                data_url = _image_to_base64_data_url(file_bytes, safe_filename)

                if data_url:
                    if upload_target == "banner_bg":
                        banner_bg_url = data_url
                        print(f"[BOOST-WEB] ✅ Banner BG saved to Firestore (base64, {len(data_url)} chars)")
                    else:
                        bg_image_url = data_url
                        print(f"[BOOST-WEB] ✅ Embed BG saved to Firestore (base64, {len(data_url)} chars)")
                else:
                    print("[BOOST-WEB] ⚠️ Base64 conversion failed")

            except Exception as e:
                print(f"[BOOST-WEB] ❌ Error processing upload: {e}")
                traceback.print_exc()

        if not message_text:
            return jsonify({"success": False, "message": "Teks pesan tidak boleh kosong."}), 400

        if embed_color and not embed_color.startswith("#"):
            embed_color = f"#{embed_color}"

        if banner_font_color and not banner_font_color.startswith("#"):
            banner_font_color = f"#{banner_font_color}"

        payload = {
            "boost_announce": {
                "enabled": enabled,
                "channel_id": channel_id,
                "message_text": message_text,
                "is_embed": is_embed,
                "embed_color": embed_color,
                "embed_title": embed_title,
                "bg_image_url": bg_image_url,
                "style": style,
                "banner_bg_url": banner_bg_url,
                "banner_text": banner_text,
                "banner_subtext": banner_subtext,
                "banner_font_color": banner_font_color,
                "banner_avatar_ring": banner_avatar_ring,
            }
        }

        db.collection("guild_settings").document(guild_id).set(payload, merge=True)

        print(f"[BOOST-WEB] ✅ Config tersimpan untuk guild {guild_id} (style={style})")
        return jsonify({"success": True, "message": "✅ Pengaturan Boost berhasil disimpan!"}), 200

    except Exception as e:
        print(f"[BOOST-WEB] ❌ Error saat menyimpan: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": f"❌ Terjadi kesalahan server: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
