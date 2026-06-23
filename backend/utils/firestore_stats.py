import time
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from backend.utils.formatters import format_duration, format_uptime

try:
    from backend.cogs.database.firebase_setup import get_db
    FIRESTORE_AVAILABLE = True
except Exception:
    FIRESTORE_AVAILABLE = False

_stats_lock = threading.Lock()
_local_stats: Dict[str, Any] = {
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

_guild_channels_lock = threading.Lock()
_local_guild_channels: Dict[str, list] = {}

_music_states_lock = threading.Lock()
_local_music_states: Dict[str, dict] = {}

_bot_instance = None
_bot_instance_lock = threading.Lock()

COLLECTION = "bot_status"
DOC_ID = "stats"

def _get_db():
    if not FIRESTORE_AVAILABLE:
        return None
    try:
        return get_db()
    except Exception:
        return None

def _write_to_firestore(data: Dict[str, Any]) -> bool:
    db = _get_db()
    if not db:
        return False
    try:
        db.collection(COLLECTION).document(DOC_ID).set(data, merge=True)
        return True
    except Exception as e:
        print(f"[FIRESTORE STATS] ❌ Write failed: {e}")
        return False

def _read_from_firestore() -> Optional[Dict[str, Any]]:
    db = _get_db()
    if not db:
        return None
    try:
        doc = db.collection(COLLECTION).document(DOC_ID).get()
        if doc.exists:
            return doc.to_dict()
    except Exception as e:
        print(f"[FIRESTORE STATS] ❌ Read failed: {e}")
    return None

def set_stats(**kwargs):
    with _stats_lock:
        _local_stats.update(kwargs)
        _local_stats["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    _write_to_firestore(dict(_local_stats))

def get_stats_snapshot() -> Dict[str, Any]:
    firestore_data = _read_from_firestore()
    
    with _stats_lock:
        if firestore_data:
            raw = firestore_data
        else:
            raw = dict(_local_stats)

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

def set_guild_channels(guild_id: str, channels: list):
    with _guild_channels_lock:
        _local_guild_channels[guild_id] = channels
    
    db = _get_db()
    if db:
        try:
            db.collection(COLLECTION).document("guild_channels").set(
                {guild_id: channels}, merge=True
            )
        except Exception as e:
            print(f"[FIRESTORE STATS] ❌ Write guild_channels failed: {e}")

def get_guild_channels(guild_id: str) -> list:
    db = _get_db()
    if db:
        try:
            doc = db.collection(COLLECTION).document("guild_channels").get()
            if doc.exists:
                data = doc.to_dict()
                return data.get(guild_id, [])
        except Exception:
            pass
    
    with _guild_channels_lock:
        return _local_guild_channels.get(guild_id, [])

def set_music_state(guild_id: str, state: dict):
    with _music_states_lock:
        _local_music_states[guild_id] = state
    
    db = _get_db()
    if db:
        try:
            db.collection(COLLECTION).document("music_states").set(
                {guild_id: state}, merge=True
            )
        except Exception as e:
            print(f"[FIRESTORE STATS] ❌ Write music_state failed: {e}")

def get_music_state(guild_id: str) -> dict:
    db = _get_db()
    if db:
        try:
            doc = db.collection(COLLECTION).document("music_states").get()
            if doc.exists:
                data = doc.to_dict()
                return data.get(guild_id, {"connected": False})
        except Exception:
            pass
    
    with _music_states_lock:
        return _local_music_states.get(guild_id, {"connected": False})

def set_bot_instance(bot):
    global _bot_instance
    with _bot_instance_lock:
        _bot_instance = bot

def get_bot_instance():
    with _bot_instance_lock:
        return _bot_instance