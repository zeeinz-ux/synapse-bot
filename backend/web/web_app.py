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

from flask import Flask, render_template, jsonify, request, redirect, session, url_for, current_app
import requests
from functools import wraps
from datetime import datetime, timezone
from PIL import Image
from google.cloud.firestore_v1.base_query import FieldFilter

# ==========================================================
# Import relative dari dalam backend/ folder
# ==========================================================
from backend.utils.formatters import format_uptime
from firebase_admin import firestore
from backend.cogs.database.firebase_setup import db
from backend.utils.firestore_stats import (
    get_stats_snapshot,
    set_guild_channels,
    get_guild_channels,
    set_bot_instance,
    get_bot_instance,
    get_firestore_diagnostics,
    firestore_circuit_open,
    trip_firestore_circuit,
    firestore_retry_after,
    _is_quota_error,
    set_guild_roles,
    get_guild_roles,
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
    template_folder=os.path.join(_base_dir, "../../frontend/pages")
)

app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# Setelah app.secret_key
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


# ==========================================================
# Translation / i18n
# ==========================================================
_translations = {}
_trans_dir = os.path.join(os.path.dirname(__file__), "translations")
for _f in os.listdir(_trans_dir):
    if _f.endswith(".json"):
        _lang = _f.replace(".json", "")
        with open(os.path.join(_trans_dir, _f), "r", encoding="utf-8") as _fp:
            _translations[_lang] = json.load(_fp)

@app.template_filter("t")
def _translate(key):
    lang = session.get("lang", "id")
    return _translations.get(lang, {}).get(key, _translations.get("id", {}).get(key, key))

@app.context_processor
def _inject_lang():
    return dict(lang=session.get("lang", "id"))


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
# API — Boost Tracker
# ==========================================================

@app.route("/api/boosts/<guild_id>/history")
def api_boost_history(guild_id: str):
    if db is None:
        return jsonify({"success": False, "boosts": [], "message": "Firebase unavailable"}), 200
    try:
        docs = list(db.collection("boosts")
                     .where(filter=FieldFilter("guild_id", "==", str(guild_id)))
                     .limit(50).stream())
        # Resolve user info from Discord API via bot guild data
        bot_guilds = current_app.config.get("BOT_GUILDS", {})
        guild_data = bot_guilds.get(str(guild_id), {})
        members = {str(m["user"]["id"]): m["user"] for m in guild_data.get("members", [])}

        docs = [d for d in docs if d.to_dict().get("boosted_at") is not None]
        docs.sort(key=lambda d: d.to_dict()["boosted_at"], reverse=True)

        boosts = []
        for doc in docs:
            d = doc.to_dict()
            boosted_at = d.get("boosted_at")
            unboosted_at = d.get("unboosted_at")
            uid = d.get("user_id", "")
            user = members.get(uid, {})
            avatar_hash = user.get("avatar", "")
            boosts.append({
                "id": doc.id,
                "user_id": uid,
                "username": user.get("username", ""),
                "avatar_url": f"https://cdn.discordapp.com/avatars/{uid}/{avatar_hash}.png" if avatar_hash else "",
                "type": d.get("type", "server_boost"),
                "status": d.get("status", "active"),
                "boosted_at": boosted_at.isoformat() if hasattr(boosted_at, "isoformat") else str(boosted_at or ""),
                "unboosted_at": unboosted_at.isoformat() if hasattr(unboosted_at, "isoformat") else str(unboosted_at or ""),
                "note": d.get("note", ""),
            })
        return jsonify({"success": True, "boosts": boosts, "count": len(boosts)}), 200
    except Exception as e:
        traceback.print_exc()
        print(f"[BOOST API] ❌ history error: {e}")
        return jsonify({"success": False, "boosts": [], "message": str(e)}), 500


@app.route("/api/boosts/<guild_id>/stats")
def api_boost_stats(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 200
    try:
        docs = list(db.collection("boosts").where(filter=FieldFilter("guild_id", "==", str(guild_id))).stream())
        # Resolve user info
        bot_guilds = current_app.config.get("BOT_GUILDS", {})
        guild_data = bot_guilds.get(str(guild_id), {})
        members = {str(m["user"]["id"]): m["user"] for m in guild_data.get("members", [])}

        total = len(docs)
        active = sum(1 for d in docs if d.to_dict().get("status") == "active")
        expired = total - active

        user_counts = {}
        for d in docs:
            uid = d.to_dict().get("user_id", "unknown")
            user_counts[uid] = user_counts.get(uid, 0) + 1
        top = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        tiers = [(0, "None"), (2, "Tier 1"), (7, "Tier 2"), (14, "Tier 3")]
        current_tier = "None"
        next_tier = "Tier 1"
        next_at = 2
        for i, (req, label) in enumerate(tiers):
            if active >= req:
                current_tier = label
                if i + 1 < len(tiers):
                    next_tier = tiers[i + 1][1]
                    next_at = tiers[i + 1][0]
                else:
                    next_tier = "MAX"
                    next_at = active
        progress = min(active / next_at * 100, 100) if next_at > 0 else 100

        top_users_list = []
        for uid, count in top:
            user = members.get(uid, {})
            avatar_hash = user.get("avatar", "")
            top_users_list.append({
                "user_id": uid,
                "username": user.get("username", ""),
                "avatar_url": f"https://cdn.discordapp.com/avatars/{uid}/{avatar_hash}.png" if avatar_hash else "",
                "count": count,
            })

        return jsonify({
            "success": True,
            "total": total,
            "active": active,
            "expired": expired,
            "current_tier": current_tier,
            "next_tier": next_tier,
            "next_at": next_at,
            "progress": round(progress, 1),
            "top_users": top_users_list,
        }), 200
    except Exception as e:
        print(f"[BOOST API] ❌ stats error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ==========================================================
# API — Donation Tracker
# ==========================================================

@app.route("/api/donations/<guild_id>/history")
def api_donation_history(guild_id: str):
    if db is None:
        return jsonify({"success": False, "donations": [], "message": "Firebase unavailable"}), 200
    try:
        docs = list(db.collection("transactions")
                     .where(filter=FieldFilter("guild_id", "==", str(guild_id)))
                     .limit(50).stream())
        docs = [d for d in docs if d.to_dict().get("created_at") is not None]
        docs.sort(key=lambda d: d.to_dict()["created_at"], reverse=True)
        # Resolve user info from Discord API via bot guild data
        bot_guilds = current_app.config.get("BOT_GUILDS", {})
        guild_data = bot_guilds.get(str(guild_id), {})
        members = {str(m["user"]["id"]): m["user"] for m in guild_data.get("members", [])}

        donations = []
        for doc in docs:
            d = doc.to_dict()
            created = d.get("created_at")
            uid = d.get("user_id", "")
            user = members.get(uid, {})
            avatar_hash = user.get("avatar", "")
            donations.append({
                "id": doc.id,
                "user_id": uid,
                "username": user.get("username", ""),
                "avatar_url": f"https://cdn.discordapp.com/avatars/{uid}/{avatar_hash}.png" if avatar_hash else "",
                "amount": d.get("amount", 0),
                "payment_method": d.get("payment_method", ""),
                "status": d.get("status", "pending"),
                "note": d.get("note", ""),
                "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created or ""),
            })
        return jsonify({"success": True, "donations": donations, "count": len(donations)}), 200
    except Exception as e:
        traceback.print_exc()
        print(f"[DONATION API] ❌ history error: {e}")
        return jsonify({"success": False, "donations": [], "message": str(e)}), 500


@app.route("/api/donations/<guild_id>/stats")
def api_donation_stats(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 200
    try:
        docs = list(db.collection("transactions")
                     .where(filter=FieldFilter("guild_id", "==", str(guild_id)))
                     .stream())
        # Resolve user info
        bot_guilds = current_app.config.get("BOT_GUILDS", {})
        guild_data = bot_guilds.get(str(guild_id), {})
        members = {str(m["user"]["id"]): m["user"] for m in guild_data.get("members", [])}

        total_count = len(docs)
        total_amount = 0
        completed_count = 0
        user_amounts = {}
        method_counts = {}

        for doc in docs:
            d = doc.to_dict()
            amt = d.get("amount", 0)
            status = d.get("status", "pending")
            uid = d.get("user_id", "unknown")
            method = d.get("payment_method", "unknown")

            total_amount += amt
            if status == "completed":
                completed_count += 1

            user_amounts[uid] = user_amounts.get(uid, 0) + amt
            method_counts[method] = method_counts.get(method, 0) + 1

        top_donors = sorted(user_amounts.items(), key=lambda x: x[1], reverse=True)[:10]

        top_donors_list = []
        for uid, amt in top_donors:
            user = members.get(uid, {})
            avatar_hash = user.get("avatar", "")
            top_donors_list.append({
                "user_id": uid,
                "username": user.get("username", ""),
                "avatar_url": f"https://cdn.discordapp.com/avatars/{uid}/{avatar_hash}.png" if avatar_hash else "",
                "total": amt,
            })

        return jsonify({
            "success": True,
            "total_count": total_count,
            "total_amount": total_amount,
            "completed_count": completed_count,
            "average_amount": round(total_amount / total_count, 2) if total_count else 0,
            "top_donors": top_donors_list,
            "method_breakdown": [{"method": m, "count": c} for m, c in method_counts.items()],
        }), 200
    except Exception as e:
        print(f"[DONATION API] ❌ stats error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/donations/<guild_id>/confirm", methods=["POST"])
def api_donation_confirm(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 200
    payload = request.get_json(silent=True) or {}
    tx_id = payload.get("id")
    if not tx_id:
        return jsonify({"success": False, "message": "Missing transaction id"}), 400
    try:
        doc_ref = db.collection("transactions").document(tx_id)
        doc = doc_ref.get()
        if not doc.exists:
            return jsonify({"success": False, "message": "Transaction not found"}), 404
        data = doc.to_dict()
        if data.get("guild_id") != str(guild_id):
            return jsonify({"success": False, "message": "Guild mismatch"}), 403
        if data.get("status") == "completed":
            return jsonify({"success": True, "message": "Already completed"}), 200
        doc_ref.update({"status": "completed"})
        return jsonify({"success": True, "message": "Confirmed", "id": tx_id}), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/donations/<guild_id>/note", methods=["POST"])
def api_donation_note(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 200
    payload = request.get_json(silent=True) or {}
    tx_id = payload.get("id")
    note = payload.get("note", "")
    if not tx_id:
        return jsonify({"success": False, "message": "Missing transaction id"}), 400
    try:
        doc_ref = db.collection("transactions").document(tx_id)
        doc = doc_ref.get()
        if not doc.exists:
            return jsonify({"success": False, "message": "Transaction not found"}), 404
        data = doc.to_dict()
        if data.get("guild_id") != str(guild_id):
            return jsonify({"success": False, "message": "Guild mismatch"}), 403
        doc_ref.update({"note": note})
        return jsonify({"success": True, "message": "Note saved", "id": tx_id}), 200
    except Exception as e:
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

@app.route("/api/lang/<lang>")
def api_set_lang(lang):
    if lang in _translations:
        session["lang"] = lang
    next_url = request.args.get("next") or request.referrer or "/"
    return redirect(next_url)

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
    return _render_page("dashboard/dashboard.html", active_page="main", guild_id="")

@app.route("/dashboard/<guild_id>/")
@login_required
def dashboard_guild(guild_id: str):
    return _render_page("dashboard/dashboard.html", active_page="main", guild_id=guild_id)

# ==========================================================
# API — Settings
# ==========================================================

@app.route("/api/settings/<guild_id>/info")
@login_required
def api_settings_info(guild_id: str):
    try:
        stats = get_stats_snapshot()
        guild_info = {}
        for g in stats.get("guilds_list", []):
            if g["id"] == guild_id:
                guild_info = g
                break
        return jsonify({"success": True, "guild": guild_info}), 200
    except Exception as e:
        print(f"[SETTINGS API] info error: {e}")
        return jsonify({"success": False, "guild": {}}), 500


@app.route("/api/settings/<guild_id>/features")
@login_required
def api_settings_features(guild_id: str):
    if db is None:
        return jsonify({"success": True, "features": {}}), 200
    try:
        doc = db.collection("guild_settings").document(guild_id).get()
        data = doc.to_dict() if doc.exists else {}
        features = {
            "welcome": bool(data.get("welcome", {}).get("enabled", False)),
            "leave": bool(data.get("leave", {}).get("enabled", False)),
            "ban": bool(data.get("ban", {}).get("enabled", False)),
            "boost_announce": bool(data.get("boost_announce", {}).get("enabled", False)),
            "auto_responders": bool(data.get("auto_responders_enabled", False)),
            "ai_chat": bool(data.get("ai_chat", {}).get("enabled", False)),
            "level_rewards": bool(data.get("level_rewards", {}).get("enabled", False)),
            "moderation": bool(data.get("moderation_config", {}).get("enabled", True)),
        }
        return jsonify({"success": True, "features": features}), 200
    except Exception as e:
        print(f"[SETTINGS API] features error: {e}")
        return jsonify({"success": False, "features": {}}), 500


@app.route("/api/settings/<guild_id>/save", methods=["POST"])
@login_required
def api_settings_save(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 200
    try:
        payload = request.get_json() or {}
        data = {}
        if "log_channel" in payload:
            data["log_channel"] = payload["log_channel"]
        if "bot_language" in payload:
            data["bot_language"] = payload["bot_language"]
        if data:
            db.collection("guild_settings").document(guild_id).set(data, merge=True)
        return jsonify({"success": True}), 200
    except Exception as e:
        print(f"[SETTINGS API] save error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/settings/<guild_id>/reset", methods=["POST"])
@login_required
def api_settings_reset(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 200
    try:
        payload = request.get_json() or {}
        feature = payload.get("feature", "")
        valid = ["welcome", "leave", "ban", "boost_announce", "auto_responders", "ai_chat", "level_rewards", "moderation_config"]
        if not feature:
            return jsonify({"success": False, "message": "Feature name required"}), 400
        field = feature
        if feature == "auto_responders":
            field = "auto_responders_enabled"
            db.collection("guild_settings").document(guild_id).update({field: firestore.DELETE_FIELD})
            db.collection("guild_settings").document(guild_id).update({"auto_responders": firestore.DELETE_FIELD})
            return jsonify({"success": True}), 200
        if field in valid:
            db.collection("guild_settings").document(guild_id).update({field: firestore.DELETE_FIELD})
        return jsonify({"success": True}), 200
    except Exception as e:
        print(f"[SETTINGS API] reset error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/dashboard/<guild_id>/settings")
@login_required
def settings_page(guild_id: str):
    return _render_page("dashboard/settings.html", active_page="settings", guild_id=guild_id)

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
        "dashboard/welcome_settings.html",
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
        "dashboard/leave_settings.html",
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
        "dashboard/ban_settings.html",
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
        "dashboard/boost_announce.html",
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
    return _render_page("dashboard/boost_settings.html", active_page="boost_tracker", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/boost/stats")
@login_required
def boost_stats(guild_id: str):
    return _render_page("dashboard/boost_settings.html", active_page="boost_stats", guild_id=guild_id)

# ==========================================================
# ROUTES — Donation
# ==========================================================
@app.route("/dashboard/<guild_id>/donation")
@login_required
def donation_tracker(guild_id: str):
    return _render_page("dashboard/donation_settings.html", active_page="donation", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/donation/stats")
@login_required
def donation_stats(guild_id: str):
    return _render_page("dashboard/donation_settings.html", active_page="donation_stats", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/donation/settings")
@login_required
def donation_settings_page(guild_id: str):
    return _render_page("dashboard/donation_settings.html", active_page="donation_settings", guild_id=guild_id)

@app.route("/api/donations/<guild_id>/settings", methods=["GET"])
@login_required
def api_donation_get_settings(guild_id: str):
    cfg = _get_feature_config(str(guild_id), "donation_settings")
    defaults = {"enabled": True, "channel_id": "", "min_amount": 0, "webhook_url": "", "thank_you_message": ""}
    return jsonify({"success": True, "config": {**defaults, **cfg}}), 200


@app.route("/api/donations/<guild_id>/settings", methods=["POST"])
@login_required
def api_donation_save_settings(guild_id: str):
    payload = request.get_json(silent=True) or {}
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 200
    try:
        enabled = bool(payload.get("enabled", True))
        channel_id = str(payload.get("channel_id", ""))
        min_amount = int(payload.get("min_amount", 0))
        webhook_url = str(payload.get("webhook_url", ""))
        thank_you_message = str(payload.get("thank_you_message", ""))
        db.collection("guild_settings").document(str(guild_id)).set(
            {"donation_settings": {"enabled": enabled, "channel_id": channel_id, "min_amount": min_amount, "webhook_url": webhook_url, "thank_you_message": thank_you_message}},
            merge=True,
        )
        return jsonify({"success": True, "message": "Donation settings saved."}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ==========================================================
# Donation — Helpers
# ==========================================================

def _delete_donation_doc(doc_id: str):
    """Delete a transaction document by ID. Used for test donation cleanup."""
    try:
        db.collection("transactions").document(doc_id).delete()
        print(f"[DONATION] 🗑️ Deleted test donation {doc_id}")
    except Exception as e:
        print(f"[DONATION] ⚠️ Failed to delete test donation {doc_id}: {e}")


def _send_donation_webhook(webhook_url: str, content: str = "", embed: dict = None):
    """Send a text message + embed to a Discord webhook URL."""
    if not webhook_url:
        return
    try:
        payload = {"content": content}
        if embed:
            payload["embeds"] = [embed]
        requests.post(webhook_url, json=payload, timeout=10)
    except Exception as e:
        print(f"[WEBHOOK] ⚠️ Gagal kirim webhook: {e}")


def _render_thank_you(template: str, donor: str, amount: int, platform: str) -> str:
    """Replace variables in thank-you message template."""
    if not template:
        return ""
    amount_str = f"Rp {amount:,}"
    result = template.replace("{user}", donor).replace("{amount}", amount_str).replace("{platform}", platform)
    return result


# ==========================================================
# Webhook — Saweria
# ==========================================================

@app.route("/api/webhook/saweria/<guild_id>", methods=["POST"])
def webhook_saweria(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 503
    is_test = request.args.get("test") == "1"
    try:
        data = request.get_json(silent=True) or {}
        donatur = data.get("donatur_name", "Anonim")
        amount = int(data.get("amount", 0))
        message = data.get("message", "")
        tx_id_ext = data.get("transaction_id", "")
        created = data.get("created_at", "")

        if amount <= 0:
            return jsonify({"success": False, "message": "Invalid amount"}), 400

        doc_data = {
            "user_id": f"saweria:{donatur}",
            "guild_id": str(guild_id),
            "type": "donation",
            "source": "saweria",
            "amount": amount,
            "donor_name": donatur,
            "payment_method": "Saweria",
            "status": "completed",
            "note": message,
            "external_id": tx_id_ext,
            "created_at": firestore.SERVER_TIMESTAMP,
        }
        if is_test:
            doc_data["test"] = True

        doc_ref = db.collection("transactions").add(doc_data)
        tid = doc_ref[1].id

        if is_test:
            threading.Timer(60, lambda: _delete_donation_doc(tid)).start()
            print(f"[WEBHOOK-SAWERIA] 🧪 Test donasi Rp {amount:,} dari {donatur} — ID {tid} (auto-delete 60s)")
            return jsonify({"success": True, "message": "TEST_OK", "test": True, "id": tid}), 200

        # Send Discord webhook if configured
        cfg = _get_feature_config(str(guild_id), "donation_settings")
        webhook_url = (cfg or {}).get("webhook_url", "")
        if webhook_url:
            ty_msg = _render_thank_you((cfg or {}).get("thank_you_message", ""), donatur, amount, "Saweria")
            embed = {
                "title": "💰 Donasi Saweria Masuk",
                "description": f"**Rp {amount:,}** dari **{donatur}**",
                "color": 0x00FF00,
                "fields": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if message:
                embed["fields"].append({"name": "Pesan", "value": message, "inline": False})
            if tx_id_ext:
                embed["fields"].append({"name": "ID Eksternal", "value": tx_id_ext, "inline": True})
            embed["fields"].append({"name": "Status", "value": "✅ Completed (auto)", "inline": True})
            _send_donation_webhook(webhook_url, content=ty_msg, embed=embed)

        print(f"[WEBHOOK-SAWERIA] ✅ Donasi Rp {amount:,} dari {donatur} — ID {tid}")
        return jsonify({"success": True, "message": "OK"}), 200
    except Exception as e:
        print(f"[WEBHOOK-SAWERIA] ❌ Error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ==========================================================
# Webhook — Sociabuzz
# ==========================================================

@app.route("/api/webhook/sociabuzz/<guild_id>", methods=["POST"])
def webhook_sociabuzz(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 503
    is_test = request.args.get("test") == "1"
    try:
        data = request.get_json(silent=True) or {}
        donor = data.get("donor_name") or data.get("donor", "Anonim")
        raw_amount = data.get("amount", "0")
        amount = int(float(str(raw_amount).replace(",", "").replace(".", "")))
        message = data.get("message", "")
        tx_id_ext = data.get("transaction_id", "")
        payment_method = data.get("payment_method", "Sociabuzz")
        status_ext = data.get("status", "success")

        if amount <= 0:
            return jsonify({"success": False, "message": "Invalid amount"}), 400

        doc_data = {
            "user_id": f"sociabuzz:{donor}",
            "guild_id": str(guild_id),
            "type": "donation",
            "source": "sociabuzz",
            "amount": amount,
            "donor_name": donor,
            "payment_method": payment_method,
            "status": "completed" if status_ext == "success" else "pending",
            "note": message,
            "external_id": tx_id_ext,
            "created_at": firestore.SERVER_TIMESTAMP,
        }
        if is_test:
            doc_data["test"] = True

        doc_ref = db.collection("transactions").add(doc_data)
        tid = doc_ref[1].id

        if is_test:
            threading.Timer(60, lambda: _delete_donation_doc(tid)).start()
            print(f"[WEBHOOK-SOCIABUZZ] 🧪 Test donasi Rp {amount:,} dari {donor} — ID {tid} (auto-delete 60s)")
            return jsonify({"success": True, "message": "TEST_OK", "test": True, "id": tid}), 200

        # Send Discord webhook if configured
        cfg = _get_feature_config(str(guild_id), "donation_settings")
        webhook_url = (cfg or {}).get("webhook_url", "")
        if webhook_url:
            ty_msg = _render_thank_you((cfg or {}).get("thank_you_message", ""), donor, amount, "Sociabuzz")
            embed = {
                "title": "💰 Donasi Sociabuzz Masuk",
                "description": f"**Rp {amount:,}** dari **{donor}**",
                "color": 0x00FF00,
                "fields": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if message:
                embed["fields"].append({"name": "Pesan", "value": message, "inline": False})
            if tx_id_ext:
                embed["fields"].append({"name": "ID Eksternal", "value": tx_id_ext, "inline": True})
            embed["fields"].append({"name": "Status", "value": "✅ Completed (auto)", "inline": True})
            _send_donation_webhook(webhook_url, content=ty_msg, embed=embed)

        print(f"[WEBHOOK-SOCIABUZZ] ✅ Donasi Rp {amount:,} dari {donor} — ID {tid}")
        return jsonify({"success": True, "message": "OK"}), 200
    except Exception as e:
        print(f"[WEBHOOK-SOCIABUZZ] ❌ Error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ==========================================================
# API — Message Builder
# ==========================================================

@app.route("/api/message-builder/<guild_id>/channels")
@login_required
def api_mb_channels(guild_id: str):
    channels = get_guild_channels(str(guild_id))
    return jsonify({"success": True, "channels": channels or []}), 200


@app.route("/api/message-builder/<guild_id>/templates", methods=["GET"])
@login_required
def api_mb_templates_list(guild_id: str):
    if db is None:
        return jsonify({"success": False, "templates": []}), 200
    try:
        doc = db.collection("guild_settings").document(guild_id).get()
        templates = doc.to_dict().get("message_templates", {}) if doc.exists else {}
        result = []
        for tid, tpl in templates.items():
            tpl["id"] = tid
            result.append(tpl)
        result.sort(key=lambda t: t.get("updated_at") or 0, reverse=True)
        return jsonify({"success": True, "templates": result}), 200
    except Exception as e:
        print(f"[MB API] ❌ templates list error: {e}")
        return jsonify({"success": False, "templates": []}), 500


@app.route("/api/message-builder/<guild_id>/templates", methods=["POST"])
@login_required
def api_mb_templates_save(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 200
    try:
        data = request.get_json() or {}
        template_id = data.get("id") or str(int(time.time() * 1000))
        template = {
            "name": data.get("name", "Untitled"),
            "embed": data.get("embed", {}),
            "content": data.get("content", ""),
            "updated_at": int(time.time()),
        }
        db.collection("guild_settings").document(guild_id).set(
            {f"message_templates.{template_id}": template}, merge=True
        )
        return jsonify({"success": True, "id": template_id}), 200
    except Exception as e:
        print(f"[MB API] ❌ templates save error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/message-builder/<guild_id>/templates/<template_id>", methods=["DELETE"])
@login_required
def api_mb_templates_delete(guild_id: str, template_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 200
    try:
        db.collection("guild_settings").document(guild_id).update(
            {f"message_templates.{template_id}": firestore.DELETE_FIELD}
        )
        return jsonify({"success": True}), 200
    except Exception as e:
        print(f"[MB API] ❌ templates delete error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/message-builder/<guild_id>/send", methods=["POST"])
@login_required
def api_mb_send(guild_id: str):
    try:
        data = request.get_json() or {}
        channel_id = data.get("channel_id")
        embed = data.get("embed", {})
        content = data.get("content", "")
        if not channel_id:
            return jsonify({"success": False, "message": "channel_id required"}), 400
        _ensure_queue_dir()
        cmd_id = f"{int(time.time())}_{os.urandom(4).hex()}"
        cmd_file = os.path.join(CONTROL_QUEUE_DIR, f"{cmd_id}.json")
        with open(cmd_file, "w") as f:
            json.dump({
                "guild_id": guild_id,
                "action": "send_message",
                "data": {
                    "channel_id": channel_id,
                    "embed": embed,
                    "content": content,
                },
                "id": cmd_id,
            }, f)
        return jsonify({"success": True, "queued": True}), 200
    except Exception as e:
        print(f"[MB API] ❌ send error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ==========================================================
# ROUTES — Tools
# ==========================================================
@app.route("/dashboard/<guild_id>/message-builder")
@login_required
def message_builder(guild_id: str):
    return _render_page("dashboard/message_builder.html", active_page="message_builder", guild_id=guild_id)


# ==========================================================
# API — Templates (unified: message / announcement / auto_response)
# ==========================================================

@app.route("/api/templates/<guild_id>", methods=["GET"])
def api_templates_list(guild_id: str):
    if db is None:
        return jsonify({"success": False, "templates": []}), 200
    try:
        doc = db.collection("guild_settings").document(guild_id).get()
        templates = doc.to_dict().get("templates", {}) if doc.exists else {}
        result = []
        for tid, tpl in templates.items():
            tpl["id"] = tid
            result.append(tpl)
        result.sort(key=lambda t: t.get("updated_at", 0), reverse=True)
        return jsonify({"success": True, "templates": result}), 200
    except Exception as e:
        print(f"[TEMPLATES API] ❌ list error: {e}")
        return jsonify({"success": False, "templates": []}), 500


@app.route("/api/templates/<guild_id>", methods=["POST"])
def api_templates_save(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 200
    try:
        data = request.get_json() or {}
        template_id = data.get("id") or str(int(time.time() * 1000))
        template = {
            "name": data.get("name", "Untitled"),
            "type": data.get("type", "message"),
            "embed": data.get("embed", {}),
            "content": data.get("content", ""),
            "keywords": data.get("keywords", []),
            "response_type": data.get("response_type", "text"),
            "updated_at": int(time.time()),
        }
        db.collection("guild_settings").document(guild_id).set(
            {f"templates.{template_id}": template}, merge=True
        )
        return jsonify({"success": True, "id": template_id}), 200
    except Exception as e:
        print(f"[TEMPLATES API] ❌ save error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/templates/<guild_id>/<template_id>", methods=["DELETE"])
def api_templates_delete(guild_id: str, template_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 200
    try:
        db.collection("guild_settings").document(guild_id).update(
            {f"templates.{template_id}": firestore.DELETE_FIELD}
        )
        return jsonify({"success": True}), 200
    except Exception as e:
        print(f"[TEMPLATES API] ❌ delete error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/templates/<guild_id>/apply-announcement", methods=["POST"])
def api_templates_apply_announcement(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 200
    try:
        data = request.get_json() or {}
        target = data.get("target", "welcome")
        embed = data.get("embed", {})
        content = data.get("content", "")

        feature_key = {"welcome": "welcome", "leave": "leave", "ban": "ban", "boost": "boost_announce"}.get(target)
        if not feature_key:
            return jsonify({"success": False, "message": "Invalid target"}), 400

        config = {
            "style": "embed",
            "message_text": content,
            "embed_title": embed.get("title", ""),
            "embed_color": f"#{embed.get('color', '5865f2')}",
        }

        db.collection("guild_settings").document(guild_id).set(
            {feature_key: config}, merge=True
        )
        return jsonify({"success": True, "target": target}), 200
    except Exception as e:
        print(f"[TEMPLATES API] ❌ apply error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/templates/<guild_id>/add-autoresponder", methods=["POST"])
def api_templates_add_autoresponder(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 200
    try:
        data = request.get_json() or {}
        keywords = data.get("keywords", [])
        embed = data.get("embed", {})
        content = data.get("content", "")

        if not keywords:
            return jsonify({"success": False, "message": "Keywords required"}), 400

        keyword = keywords[0]
        responder_id = "ar_" + "".join(c for c in keyword.replace(" ", "_") if c.isalnum() or c == "_")[:40]

        config = {
            "keyword": keyword,
            "keywords": keywords,
            "response_type": "embed" if embed else "text",
            "text": content,
            "embed": embed,
            "case_sensitive": False,
            "regex": False,
            "whole_word": True,
        }

        db.collection("guild_settings").document(guild_id).set(
            {f"auto_responders.{responder_id}": config}, merge=True
        )
        db.collection("guild_settings").document(guild_id).set(
            {"auto_responders_enabled": True}, merge=True
        )
        return jsonify({"success": True, "id": responder_id}), 200
    except Exception as e:
        print(f"[TEMPLATES API] ❌ add-autoresponder error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/dashboard/<guild_id>/templates")
@login_required
def templates_page(guild_id: str):
    return _render_page("dashboard/templates.html", active_page="templates", guild_id=guild_id)

# ==========================================================
# API — Actions (Level Rewards + Moderation Config)
# ==========================================================

@app.route("/api/actions/<guild_id>/roles")
@login_required
def api_actions_roles(guild_id: str):
    try:
        roles = get_guild_roles(str(guild_id))
        roles.sort(key=lambda r: r.get("position", 0), reverse=True)
        return jsonify({"success": True, "roles": roles}), 200
    except Exception as e:
        print(f"[ACTIONS API] ❌ roles error: {e}")
        return jsonify({"success": False, "roles": []}), 500


@app.route("/api/actions/<guild_id>/channels")
@login_required
def api_actions_channels(guild_id: str):
    try:
        chs = get_guild_channels(str(guild_id))
        return jsonify({"success": True, "channels": chs}), 200
    except Exception as e:
        print(f"[ACTIONS API] ❌ channels error: {e}")
        return jsonify({"success": False, "channels": []}), 500


@app.route("/api/actions/<guild_id>/level-rewards", methods=["GET"])
@login_required
def api_actions_level_rewards_get(guild_id: str):
    if db is None:
        return jsonify({"success": False, "enabled": False, "rewards": [], "notify_channel": ""}), 200
    try:
        doc = db.collection("guild_settings").document(guild_id).get()
        config = doc.to_dict().get("level_rewards", {}) if doc.exists else {}
        rewards_list = []
        for lvl, role_id in config.get("rewards", {}).items():
            rewards_list.append({"level": int(lvl), "role_id": role_id})
        rewards_list.sort(key=lambda r: r["level"])
        return jsonify({
            "success": True,
            "enabled": config.get("enabled", False),
            "rewards": rewards_list,
            "notify_channel": config.get("notify_channel", ""),
        }), 200
    except Exception as e:
        print(f"[ACTIONS API] ❌ level-rewards get error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/actions/<guild_id>/level-rewards", methods=["POST"])
@login_required
def api_actions_level_rewards_save(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 200
    try:
        data = request.get_json() or {}
        rewards_map = {}
        for r in data.get("rewards", []):
            lvl = r.get("level")
            rid = r.get("role_id")
            if lvl and rid:
                rewards_map[str(lvl)] = str(rid)
        config = {
            "enabled": data.get("enabled", False),
            "rewards": rewards_map,
            "notify_channel": data.get("notify_channel", ""),
        }
        db.collection("guild_settings").document(guild_id).set(
            {"level_rewards": config}, merge=True
        )
        return jsonify({"success": True}), 200
    except Exception as e:
        print(f"[ACTIONS API] ❌ level-rewards save error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/actions/<guild_id>/moderation", methods=["GET"])
@login_required
def api_actions_moderation_get(guild_id: str):
    if db is None:
        return jsonify({"success": False, "enabled": True}), 200
    try:
        doc = db.collection("guild_settings").document(guild_id).get()
        config = doc.to_dict().get("moderation_config", {}) if doc.exists else {}
        return jsonify({
            "success": True,
            "enabled": config.get("enabled", True),
            "strike_1": config.get("strike_1", {"action": "timeout", "duration_hours": 1}),
            "strike_2": config.get("strike_2", {"action": "kick"}),
            "strike_3": config.get("strike_3", {"action": "ban"}),
            "report_channel": config.get("report_channel", ""),
            "filter_heuristic": config.get("filter_heuristic", True),
            "filter_new_account": config.get("filter_new_account", True),
            "filter_ai": config.get("filter_ai", True),
        }), 200
    except Exception as e:
        print(f"[ACTIONS API] ❌ moderation get error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/actions/<guild_id>/moderation", methods=["POST"])
@login_required
def api_actions_moderation_save(guild_id: str):
    if db is None:
        return jsonify({"success": False, "message": "Firebase unavailable"}), 200
    try:
        data = request.get_json() or {}
        config = {
            "enabled": data.get("enabled", True),
            "strike_1": data.get("strike_1", {"action": "timeout", "duration_hours": 1}),
            "strike_2": data.get("strike_2", {"action": "kick"}),
            "strike_3": data.get("strike_3", {"action": "ban"}),
            "report_channel": data.get("report_channel", ""),
            "filter_heuristic": data.get("filter_heuristic", True),
            "filter_new_account": data.get("filter_new_account", True),
            "filter_ai": data.get("filter_ai", True),
        }
        db.collection("guild_settings").document(guild_id).set(
            {"moderation_config": config}, merge=True
        )
        return jsonify({"success": True}), 200
    except Exception as e:
        print(f"[ACTIONS API] ❌ moderation save error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/dashboard/<guild_id>/actions")
@login_required
def actions_page(guild_id: str):
    return _render_page("dashboard/actions.html", active_page="actions", guild_id=guild_id)

@app.route("/dashboard/<guild_id>/auto-responders")
@login_required
def auto_responders(guild_id: str):
    return _render_page("dashboard/auto_responders.html", active_page="auto_responders", guild_id=guild_id)


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
    # Auto-assign order for new responders
    if "order" not in config:
        try:
            settings = _ar_bridge_response(guild_id, lambda: ar_get_guild_settings_fresh(str(guild_id)))
            existing = settings.get("responders", {}) or {}
            max_order = 0
            for c in existing.values():
                if isinstance(c, dict):
                    max_order = max(max_order, c.get("order", 0))
            config["order"] = max_order + 1
        except Exception:
            config["order"] = 0
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


@app.route("/api/auto-responders/<guild_id>/reorder", methods=["POST"])
def api_auto_responders_reorder(guild_id: str):
    if firestore_circuit_open():
        retry = int(firestore_retry_after())
        return jsonify({"success": False, "error": "circuit_open", "message": f"Database rate-limited. Retry in {retry}s.", "retry_after": retry}), 503
    payload = request.get_json(silent=True) or {}
    order_list = payload.get("order", [])
    if not order_list:
        return jsonify({"success": False, "message": "order list is empty."}), 400
    try:
        settings = _ar_bridge_response(guild_id, lambda: ar_get_guild_settings_fresh(str(guild_id)))
        responders = dict(settings.get("responders", {}) or {})
        for item in order_list:
            rid = item.get("id")
            new_order = item.get("order")
            if rid and new_order is not None and rid in responders:
                responders[rid]["order"] = new_order
        # Save whole responders dict
        doc_ref = db.collection("guild_settings").document(str(guild_id))
        def _blocking():
            doc_ref.set({"auto_responders": responders}, merge=True)
        _ar_bridge_response(guild_id, lambda: asyncio.to_thread(_blocking))
        return jsonify({"success": True, "message": "Reorder saved."}), 200
    except Exception as e:
        if _is_quota_error(e):
            trip_firestore_circuit()
        print(f"[AUTO-RESPONSE WEB] ❌ reorder failed: {e}")
        return jsonify({"success": False, "error": str(e), "message": "Reorder failed."}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# Anti-Spam Page & API
# ============================================================================
_MOD_DEFAULTS = {
    "enabled": True,
    "filter_heuristic": True,
    "filter_ai": True,
    "filter_new_account": True,
    "filter_image": True,
    "whitelist_users": [],
    "whitelist_roles": [],
    "report_channel": "",
    "custom_keywords": [],
    "raid_protection": False,
    "raid_threshold": 10,
    "raid_window": 300,
    "raid_action": "kick",
}

@app.route("/dashboard/<guild_id>/anti-spam")
@login_required
def anti_spam_page(guild_id: str):
    return _render_page("dashboard/anti_spam.html", active_page="anti_spam", guild_id=guild_id)

@app.route("/api/anti-spam/<guild_id>/config")
@login_required
def api_anti_spam_config(guild_id: str):
    try:
        doc = db.collection("guild_settings").document(guild_id).get()
        mod_cfg = doc.to_dict().get("moderation_config", {}) if doc.exists else {}
        config = {**_MOD_DEFAULTS, **mod_cfg}
        return jsonify({"success": True, "config": config}), 200
    except Exception as e:
        print(f"[ANTI-SPAM] ❌ config error: {e}")
        return jsonify({"success": False, "config": _MOD_DEFAULTS}), 200

@app.route("/api/anti-spam/<guild_id>/save", methods=["POST"])
@login_required
def api_anti_spam_save(guild_id: str):
    try:
        payload = request.get_json(silent=True) or {}
        mod_cfg = {k: payload.get(k, v) for k, v in _MOD_DEFAULTS.items()}
        doc_ref = db.collection("guild_settings").document(guild_id)
        doc_ref.set({"moderation_config": mod_cfg}, merge=True)
        return jsonify({"success": True, "message": "✅ Pengaturan anti spam berhasil disimpan!"}), 200
    except Exception as e:
        print(f"[ANTI-SPAM] ❌ save error: {e}")
        return jsonify({"success": False, "message": f"Gagal menyimpan: {e}"}), 500

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


@app.route("/api/guilds/<guild_id>/images", methods=["GET"])
@login_required
def api_guild_images(guild_id: str):
    images = []
    if db is None:
        return jsonify({"success": False, "images": [], "message": "Firestore tidak tersedia"}), 503
    try:
        doc = db.collection("guild_settings").document(str(guild_id)).get()
        if not doc.exists:
            return jsonify({"success": True, "images": []}), 200
        data = doc.to_dict()
        for feat in ("welcome", "leave", "ban", "boost_announce"):
            cfg = data.get(feat, {})
            for field, label in [("bg_image_url", "Background"), ("banner_bg_url", "Banner")]:
                url = cfg.get(field, "").strip()
                if url:
                    images.append({"url": url, "label": f"{feat} {label}", "source": feat})
    except Exception as e:
        print(f"[WEB-IMAGES] ❌ Gagal baca Firestore: {e}")
        return jsonify({"success": False, "images": [], "message": str(e)}), 500
    return jsonify({"success": True, "images": images, "count": len(images)}), 200


# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/dashboard/<guild_id>/ai-chat")
@login_required
def ai_chat_page(guild_id: str):
    channels = get_guild_channels(guild_id)
    ai_chat_enabled = False
    personality = "friendly"
    ai_chat_channel = ""
    temperature = 0.75
    dedicated_ai_channel = False

    try:
        if db is not None:
            doc_ref = db.collection("guild_settings").document(str(guild_id))
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                ai_chat_enabled = data.get("ai_chat_enabled", False)
                ai_cfg = data.get("ai_chat", {})
                personality = ai_cfg.get("personality", "friendly")
                ai_chat_channel = ai_cfg.get("channel_id", "")
                temperature = ai_cfg.get("temperature", 0.75)
                dedicated_ai_channel = ai_cfg.get("dedicated_ai_channel", False)
    except Exception:
        pass

    return _render_page(
        "dashboard/ai_chat.html",
        active_page="ai_chat",
        guild_id=guild_id,
        channels=channels,
        ai_chat_enabled=ai_chat_enabled,
        personality=personality,
        ai_chat_channel=ai_chat_channel,
        temperature=temperature,
        dedicated_ai_channel=dedicated_ai_channel,
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
            data = request.get_json(silent=True) or {}
        else:
            data = request.form.to_dict()

        personality = data.get("personality", "friendly")
        channel_id = data.get("channel_id", "").strip()
        temperature = float(data.get("temperature", 0.75))
        dedicated_ai_channel = data.get("dedicated_ai_channel", False)

        valid_personalities = ["friendly", "formal", "tsundere", "sarcastic", "wise"]
        if personality not in valid_personalities:
            personality = "friendly"

        if db is None:
            return jsonify({"success": False, "message": "Firebase tidak tersedia."}), 500

        doc_ref = db.collection("guild_settings").document(str(guild_id))
        
        doc_ref.set({
            "ai_chat": {
                "personality": personality,
                "channel_id": channel_id,
                "temperature": temperature,
                "dedicated_ai_channel": dedicated_ai_channel if channel_id else False,
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
        defaults = {
            "personality": "friendly",
            "channel_id": "",
            "temperature": 0.75,
            "dedicated_ai_channel": False,
        }

        if db is None:
            return jsonify({
                "success": True,
                "ai_chat_enabled": False,
                "ai_chat": defaults
            }), 200

        doc_ref = db.collection("guild_settings").document(str(guild_id))
        doc = doc_ref.get()

        if not doc.exists:
            return jsonify({
                "success": True,
                "ai_chat_enabled": False,
                "ai_chat": defaults
            }), 200

        data = doc.to_dict()
        ai_chat = data.get("ai_chat", {})
        return jsonify({
            "success": True,
            "ai_chat_enabled": data.get("ai_chat_enabled", False),
            "ai_chat": {
                "personality": ai_chat.get("personality", "friendly"),
                "channel_id": ai_chat.get("channel_id", ""),
                "temperature": ai_chat.get("temperature", 0.75),
                "dedicated_ai_channel": ai_chat.get("dedicated_ai_channel", False),
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
@login_required
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


# ==========================================================
# Photobox — Camera Frontend (no login needed)
# ==========================================================
@app.route("/photobox")
def photobox():
    """Serve the photobox camera page."""
    return render_template("photobox.html",
                           user=None, avatar_url="")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
