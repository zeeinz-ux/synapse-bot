# ============================================================================
# auto_responder_store.py - Free-function bridge for AutoResponder persistence
# ============================================================================

import asyncio
import time
from typing import List, Dict, Any, Optional

try:
    from backend.cogs.database.firebase_setup import db
    FIRESTORE_AVAILABLE = True
except Exception:
    FIRESTORE_AVAILABLE = False
    db = None

try:
    from backend.utils.firestore_stats import (
        firestore_circuit_open,
        trip_firestore_circuit,
        firestore_retry_after,
        _is_quota_error,
    )
except Exception:
    firestore_circuit_open = lambda: False
    trip_firestore_circuit = lambda: None
    firestore_retry_after = lambda: 0.0
    def _is_quota_error(_):
        return False


_COLLECTION = "guild_settings"
_DEFAULT_TTL = 300

_settings_cache: Dict[str, Dict[str, Any]] = {}
_cooldown_cache: Dict[str, Dict[str, float]] = {}


async def ar_get_guild_settings(guild_id: str) -> Dict[str, Any]:
    """Read auto-responder settings for a guild. Cached for 5 minutes."""
    if firestore_circuit_open():
        return {"enabled": False, "responders": {}}

    now = time.time()
    cached = _settings_cache.get(guild_id)
    if cached and (now - cached["last_fetched"]) < _DEFAULT_TTL:
        return cached["data"]

    if db is None:
        return {"enabled": False, "responders": {}}

    try:
        doc_ref = db.collection(_COLLECTION).document(str(guild_id))
        doc = await asyncio.to_thread(doc_ref.get)

        if not doc.exists:
            settings = {"enabled": False, "responders": {}}
        else:
            data = doc.to_dict() or {}
            settings = {
                "enabled": data.get("auto_responders_enabled", False),
                "responders": data.get("auto_responders", {}),
            }

        _settings_cache[guild_id] = {"data": settings, "last_fetched": now}
        return settings

    except Exception as e:
        if _is_quota_error(e):
            trip_firestore_circuit()
        print(f"[AUTO-RESPONSE STORE] ⚠️ Error fetching settings: {e}")
        return {"enabled": False, "responders": {}}


async def ar_get_guild_settings_fresh(guild_id: str) -> Dict[str, Any]:
    """Read guild settings bypassing the in-process cache."""
    if firestore_circuit_open():
        return {"enabled": False, "responders": {}}
    if db is None:
        return {"enabled": False, "responders": {}}

    # Always invalidate before reading.
    _settings_cache.pop(guild_id, None)

    try:
        doc_ref = db.collection(_COLLECTION).document(str(guild_id))
        doc = await asyncio.to_thread(doc_ref.get)

        if not doc.exists:
            settings = {"enabled": False, "responders": {}}
        else:
            data = doc.to_dict() or {}
            settings = {
                "enabled": data.get("auto_responders_enabled", False),
                "responders": data.get("auto_responders", {}),
            }
        _settings_cache[guild_id] = {"data": settings, "last_fetched": time.time()}
        return settings
    except Exception as e:
        if _is_quota_error(e):
            trip_firestore_circuit()
        print(f"[AUTO-RESPONSE STORE] ⚠️ Error in fresh-fetch: {e}")
        return {"enabled": False, "responders": {}}


async def ar_save_responder(guild_id: str, responder_id: str, config: dict) -> bool:
    """Create or update a single responder in the guild's settings doc."""
    if firestore_circuit_open():
        return False
    if db is None:
        return False

    try:
        doc_ref = db.collection(_COLLECTION).document(str(guild_id))

        def _blocking_set():
            doc = doc_ref.get()
            existing = doc.to_dict().get("auto_responders", {}) if doc.exists else {}
            existing[responder_id] = config
            # FIX: Use update() instead of set(merge=True) for partial updates
            doc_ref.update({"auto_responders": existing})

        await asyncio.to_thread(_blocking_set)
        _settings_cache.pop(guild_id, None)
        return True

    except Exception as e:
        if _is_quota_error(e):
            trip_firestore_circuit()
        print(f"[AUTO-RESPONSE STORE] ⚠️ Error saving responder: {e}")
        return False


async def ar_delete_responder(guild_id: str, responder_id: str) -> bool:
    """Delete a single responder from the guild's settings doc."""
    if firestore_circuit_open():
        return False
    if db is None:
        return False

    try:
        doc_ref = db.collection(_COLLECTION).document(str(guild_id))

        def _blocking_delete():
            doc = doc_ref.get()
            if not doc.exists:
                return False
            existing = doc.to_dict().get("auto_responders", {})
            if responder_id not in existing:
                return False

            # FIX: Use Firestore delete field value to properly remove nested field
            from google.cloud import firestore as fs
            doc_ref.update({
                f"auto_responders.{responder_id}": fs.DELETE_FIELD
            })
            return True

        deleted = await asyncio.to_thread(_blocking_delete)
        _settings_cache.pop(guild_id, None)
        return deleted

    except Exception as e:
        if _is_quota_error(e):
            trip_firestore_circuit()
        print(f"[AUTO-RESPONSE STORE] ⚠️ Error deleting responder: {e}")
        return False


async def ar_list_responders(guild_id: str) -> List[Dict[str, Any]]:
    """Return a flat list of responder dicts for the dashboard."""
    # FIX: Always use fresh fetch to avoid stale cache issues
    settings = await ar_get_guild_settings_fresh(guild_id)
    result = []
    for rid, cfg in (settings.get("responders") or {}).items():
        result.append({"id": rid, **(cfg or {})})
    return result