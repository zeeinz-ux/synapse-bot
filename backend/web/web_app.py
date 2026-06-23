import os
import threading
import base64
import traceback
import io
import asyncio
from flask import Flask, render_template, jsonify, request, redirect, session, url_for
import requests
from functools import wraps
from datetime import datetime, timezone
from PIL import Image

# ==========================================================
# Import relative dari dalam backend/ folder
# ==========================================================
from utils.formatters import format_duration, format_uptime
from backend.cogs.database.firebase_setup import db
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
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://192.168.1.29:8080/callback")
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
    
    return redirect("/dashboard")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ==========================================================
# Shared stats (thread-safe)
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
    "guilds_list": []
}

def set_stats(**kwargs):
    with _stats_lock:
        _bot_stats.update(kwargs)
        _bot_stats["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def get_stats_snapshot():
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
    with _guild_lock:
        _guild_channels[guild_id] = channels

def get_guild_channels(guild_id: str) -> list:
    with _guild_lock:
        return _guild_channels.get(guild_id, [])
    
# ==========================================================
# Shared music state (thread-safe)
# ==========================================================
_music_lock = threading.Lock()
_music_states: dict = {}

def set_music_state(guild_id: str, state: dict):
    with _music_lock:
        _music_states[guild_id] = state

def get_music_state(guild_id: str) -> dict:
    with _music_lock:
        return _music_states.get(guild_id, {"connected": False})
    
# ==========================================================
# Shared bot instance
# ==========================================================
_bot_instance = None

def set_bot_instance(bot):
    global _bot_instance
    _bot_instance = bot

def get_bot_instance():
    return _bot_instance
    

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


@app.route("/api/music/control", methods=["POST"])
def api_music_control():
    data = request.get_json() or {}

    guild_id = data.get("guild_id")
    action = data.get("action")

    if not guild_id:
        return jsonify({
            "success": False,
            "message": "guild_id required"
        }), 400

    bot = get_bot_instance()

    if not bot:
        return jsonify({
            "success": False,
            "message": "Bot unavailable"
        }), 500

    guild = bot.get_guild(int(guild_id))

    if not guild:
        return jsonify({
            "success": False,
            "message": "Guild not found"
        }), 404

    player = guild.voice_client

    if not player:
        return jsonify({
            "success": False,
            "message": "Player not connected"
        }), 404

    try:

        if action == "pause":
            asyncio.run_coroutine_threadsafe(
                player.pause(True),
                bot.loop
            )

        elif action == "play":
            asyncio.run_coroutine_threadsafe(
                player.pause(False),
                bot.loop
            )

        elif action == "skip":
            asyncio.run_coroutine_threadsafe(
                player.stop(),
                bot.loop
            )

        elif action == "stop":
            asyncio.run_coroutine_threadsafe(
                player.stop(),
                bot.loop
            )

        elif action == "disconnect":
            asyncio.run_coroutine_threadsafe(
                player.disconnect(),
                bot.loop
            )

        elif action == "volume":
            volume = int(data.get("volume", 100))

            asyncio.run_coroutine_threadsafe(
                player.set_volume(volume),
                bot.loop
            )

        return jsonify({
            "success": True,
            "action": action
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


    

# ==========================================================
# Helper — baca config welcome dari Firestore
# ==========================================================
def _get_welcome_config(guild_id: str) -> dict:
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
# Helper — render template dengan sidebar context
# ==========================================================
def _render_page(template_name: str, active_page: str, guild_id: str, **kwargs):
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
    # Ini bakal ngebuka file landing.html yang ada di folder templates lu
    return render_template("landing.html")

@app.route("/api/stats")
def api_stats():
    with _stats_lock:
        return jsonify(dict(_bot_stats))

# ==========================================================
# ROUTES — Dashboard
# ==========================================================
@app.route("/dashboard")
def dashboard():
    s = get_stats_snapshot()
    guilds = s.get("guilds_list", [])
    if guilds:
        first_id = str(guilds[0].get("id", ""))
        if first_id:
            return redirect(f"/dashboard/{first_id}/")
    return _render_page("dashboard.html", active_page="main", guild_id="")

@app.route("/dashboard/<guild_id>/")
def dashboard_guild(guild_id: str):
    return _render_page("dashboard.html", active_page="main", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/settings")
def settings_page(guild_id: str):
    return _render_page("settings.html", active_page="settings", guild_id=guild_id)

# ==========================================================
# ROUTES — Music (placeholder)
# ==========================================================

@app.route("/dashboard/<guild_id>/music/now-playing")
def music_now_playing(guild_id: str):
    return _render_page("now_playing.html", active_page="now_playing", guild_id=guild_id)


@app.route("/dashboard/<guild_id>/music/queue")
def music_queue(guild_id: str):
    return _render_page("queue.html", active_page="queue", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/music/playlists")
def music_playlists(guild_id: str):
    return _render_page("playlist.html", active_page="playlists", guild_id=guild_id)

# ==========================================================
# ROUTES — Welcome / Announcements
# ==========================================================
@app.route("/dashboard/<guild_id>/welcome")
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
def welcome_leave(guild_id: str):
    return _render_page("welcome_settings.html", active_page="leave", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/welcome/ban")
def welcome_ban(guild_id: str):
    return _render_page("welcome_settings.html", active_page="ban", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/welcome/boost")
def welcome_boost(guild_id: str):
    return _render_page("welcome_settings.html", active_page="boost_welcome", guild_id=guild_id)

# ==========================================================
# ROUTES — Boost Tracker
# ==========================================================
@app.route("/dashboard/<guild_id>/boost")
def boost_tracker(guild_id: str):
    return _render_page("boost_settings.html", active_page="boost_tracker", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/boost/stats")
def boost_stats(guild_id: str):
    return _render_page("boost_settings.html", active_page="boost_stats", guild_id=guild_id)

# ==========================================================
# ROUTES — Donation
# ==========================================================
@app.route("/dashboard/<guild_id>/donation")
def donation_tracker(guild_id: str):
    return _render_page("donation_settings.html", active_page="donation", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/donation/stats")
def donation_stats(guild_id: str):
    return _render_page("donation_settings.html", active_page="donation_stats", guild_id=guild_id)

# ==========================================================
# ROUTES — Tools
# ==========================================================
@app.route("/dashboard/<guild_id>/message-builder")
def message_builder(guild_id: str):
    return _render_page("message_builder.html", active_page="message_builder", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/templates")
def templates_page(guild_id: str):
    return _render_page("templates.html", active_page="templates", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/actions")
def actions_page(guild_id: str):
    return _render_page("actions.html", active_page="actions", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/auto-responders")
def auto_responders(guild_id: str):
    return _render_page("auto_responders.html", active_page="auto_responders", guild_id=guild_id)

# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES — AI Chat v4.5 (Gemini 2.5 Flash + OpenRouter + Temperature Support)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/dashboard/<guild_id>/ai-chat")
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
    # Pake lock biar datanya aman pas lagi di-update sama bot
    with _stats_lock:
        stats_data = {
            "guilds": _bot_stats.get("guilds", 0),
            "members": _bot_stats.get("members", 0)
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
