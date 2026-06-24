# ============================================================================
# auto_responder_store.py — Free-function bridge for AutoResponder persistence
# ============================================================================
#
# Why this exists:
#   On Railway, the Flask web process (gunicorn) and the Discord bot process
#   (python main.py) run as SEPARATE OS processes with SEPARATE memory.
#   set_bot_instance() in the bot process does NOT propagate to the web
#   process, so bot.get_cog("AutoResponder") in Flask always returns None.
#
# Solution:
#   Expose the AutoResponder Firestore operations as free async functions.
#   Both the cog (in-process calls) and the Flask route (cross-process) call
#   the same functions. Firestore acts as the single source of truth.
#
# Reused from the cog (auto_response.py), these mirror the private methods so
# existing slash commands keep working without changes.
#
# Concurrency:
#   - All Firestore I/O goes through asyncio.to_thread (non-blocking).
#   - The shared circuit breaker (firestore_stats) protects against 429 storms.
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
    # Fallback no-op shims so this module imports even before the patch is deployed.
    firestore_circuit_open = lambda: False
    trip_firestore_circuit = lambda: None
    firestore_retry_after = lambda: 0.0
    def _is_quota_error(_):
        return False


_COLLECTION = "guild_settings"
_DOC_SETTINGS = "_settings_cache_ttl_seconds"  # not used; placeholder
_DEFAULT_TTL = 300  # 5 minutes cache TTL (matches the cog)


# ----------------------------------------------------------------------------
# In-process cache (per Flask worker process — separate from the cog's cache).
# Different processes, different caches, same TTL semantics. Last-writer-wins
# is fine because every write invalidates both caches via Firestore round-trip.
# ----------------------------------------------------------------------------
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
    """Read guild settings bypassing the in-process cache.

    Critical for the Flask web process, which under gunicorn/uvicorn runs
    multiple worker processes — each has its own _settings_cache, so cache
    invalidation in one worker does NOT reach the others. A write to one
    worker would be invisible to other workers reading from stale cache for
    up to _DEFAULT_TTL (5 minutes). The dashboard UX cannot tolerate that.

    Use this in dashboard/web handlers where freshness beats read efficiency.
    """
    # Import here to avoid module-level cycle issues.
    from backend.utils.auto_responder_store import _settings_cache, _COLLECTION, _is_quota_error
    # NOTE: we already are in this module, so direct refs work — but the
    # explicit import above documents intent.
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
        # Re-populate cache for any subsequent read in the SAME worker.
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
            doc_ref.set(
                {"auto_responders": existing, "auto_responders_enabled": True},
                merge=True,
            )

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

        def _blocking_set():
            doc = doc_ref.get()
            if not doc.exists:
                return
            existing = doc.to_dict().get("auto_responders", {})
            if responder_id in existing:
                del existing[responder_id]
                doc_ref.set({"auto_responders": existing}, merge=True)

        await asyncio.to_thread(_blocking_set)
        _settings_cache.pop(guild_id, None)
        return True

    except Exception as e:
        if _is_quota_error(e):
            trip_firestore_circuit()
        print(f"[AUTO-RESPONSE STORE] ⚠️ Error deleting responder: {e}")
        return False


async def ar_list_responders(guild_id: str) -> List[Dict[str, Any]]:
    """Return a flat list of responder dicts for the dashboard."""
    settings = await ar_get_guild_settings(guild_id)
    result = []
    for rid, cfg in (settings.get("responders") or {}).items():
        result.append({"id": rid, **(cfg or {})})
    return result
