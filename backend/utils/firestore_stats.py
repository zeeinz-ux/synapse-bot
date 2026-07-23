# ============================================================================
# firestore_stats.py — patched for quota-aware, debounced, async writes
#
# ROOT-LEVEL CHANGES vs original:
#   1. All Firestore writes are dispatched via asyncio.to_thread() so the
#      synchronous firebase_admin client never blocks the Discord event loop.
#   2. Each write path is debounced: many small updates within
#      WRITE_DEBOUNCE_SECONDS collapse into a single batched write.
#   3. A dirty-flag compares the new payload against the last successful
#      write — identical payloads short-circuit the network call.
#   4. A circuit breaker opens on 429 RESOURCE_EXHAUSTED / QUOTA_EXCEEDED
#      errors and disables all writes for CIRCUIT_OPEN_SECONDS. Writes that
#      arrive while the breaker is open are dropped (NOT queued — that's how
#      we got banned in the first place).
#   5. Public API surface is preserved: set_stats /
#      set_guild_channels / get_* functions keep the same signatures so
#      main.py and web_app.py need no changes.
# ============================================================================

import os
import time
import asyncio
import hashlib
import json
import sys
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Reconfigure stdout/stderr to UTF-8 so log emojis (⚡ ✅ ❌ 🔥) render
# correctly on Windows consoles (default cp1252 mangles them).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from backend.utils.formatters import format_uptime

try:
    from backend.cogs.database.firebase_setup import get_db
    FIRESTORE_AVAILABLE = True
except Exception:
    FIRESTORE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Tunables — adjust per environment via env vars (no code change required)
#
#   FIRESTORE_DEBOUNCE     Seconds to collapse writes (default 30)
#                          Lower = fresher data, more quota. Higher = staler data, safer.
#                          Free-tier safe default is 30s; drop to 10-15s on Blaze plan.
#   FIRESTORE_CIRCUIT_SEC  Seconds to disable all writes after a 429 trip (default 900 = 15 min)
#                          Anything below 60 risks triggering a Google API throttle-ban.
#                          Free-tier safe default is 900s; can be 300s on Blaze plan.
# ---------------------------------------------------------------------------
def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        print(f"[FIRESTORE STATS] ⚠️ Invalid {name}={raw!r}, falling back to default {default}")
        return default

# Free-tier defaults: longer debounce to stay under the 20K writes/day cap.
# Override with env vars FIRESTORE_DEBOUNCE / FIRESTORE_CIRCUIT_SEC for paid tiers.
WRITE_DEBOUNCE_SECONDS = _env_float("FIRESTORE_DEBOUNCE", 30.0)
CIRCUIT_OPEN_SECONDS   = _env_float("FIRESTORE_CIRCUIT_SEC", 900.0)
DIRTY_HASH_SALT        = os.getenv("FIRESTORE_HASH_SALT", "synapse-v1")

COLLECTION = "bot_status"
DOC_ID = "stats"


# ---------------------------------------------------------------------------
# In-memory state (always authoritative for reads, even when DB is open)
# ---------------------------------------------------------------------------
_local_stats: Dict[str, Any] = {
    "online": False,
    "username": "Synapse",
    "uptime": 0,
    "guilds": 0,
    "members": 0,
    "last_updated": "-",
    "guilds_list": [],
}

_stats_lock              = threading.Lock()
_guild_channels_lock     = threading.Lock()
_guild_roles_lock        = threading.Lock()
_guild_categories_lock   = threading.Lock()
_bot_instance_lock       = threading.Lock()

_local_guild_channels:   Dict[str, list] = {}
_local_guild_roles:      Dict[str, list] = {}
_local_guild_categories: Dict[str, list] = {}
_bot_instance:           Optional[Any] = None


# ---------------------------------------------------------------------------
# Per-document pending state + dirty tracking + debounce timers
# ---------------------------------------------------------------------------
class _PendingWrite:
    """Holds the latest payload destined for a single Firestore document,
    plus the bookkeeping needed for debounce + dirty-check + circuit breaker."""

    __slots__ = ("doc_id", "payload", "last_written_hash", "last_write_monotonic",
                 "debounce_task", "lock")

    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.payload: Optional[Dict[str, Any]] = None
        self.last_written_hash: Optional[str] = None
        self.last_write_monotonic: float = 0.0
        self.debounce_task: Optional[asyncio.Task] = None
        self.lock = threading.Lock()


_pending: Dict[str, _PendingWrite] = {
    DOC_ID:             _PendingWrite(DOC_ID),
    "guild_channels":   _PendingWrite("guild_channels"),
    "guild_roles":      _PendingWrite("guild_roles"),
    "guild_categories": _PendingWrite("guild_categories"),
}


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------
class _CircuitBreaker:
    """Trips on 429 errors. While OPEN, write calls are dropped immediately.
    HALF_OPEN after timeout → next write attempts; success closes it, fail re-opens."""

    def __init__(self, open_seconds: float):
        self.open_seconds = open_seconds
        self._open_until: float = 0.0
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        with self._lock:
            if self._open_until == 0.0:
                return False
            if time.monotonic() >= self._open_until:
                # Half-open: allow one probe
                return False
            return True

    def trip(self) -> None:
        with self._lock:
            self._open_until = time.monotonic() + self.open_seconds
            print(f"[FIRESTORE STATS] ⚡ Circuit breaker OPEN — writes suspended for "
                  f"{int(self.open_seconds)}s (Firestore returned 429 Quota exceeded)")

    def reset(self) -> None:
        with self._lock:
            if self._open_until != 0.0:
                print("[FIRESTORE STATS] ✅ Circuit breaker CLOSED — writes resumed")
                self._open_until = 0.0

    def retry_after(self) -> float:
        with self._lock:
            return max(0.0, self._open_until - time.monotonic())


_circuit = _CircuitBreaker(CIRCUIT_OPEN_SECONDS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _hash_payload(payload: Dict[str, Any]) -> str:
    """Stable hash for dirty-check. Sort keys so dict order doesn't matter."""
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(DIRTY_HASH_SALT.encode() + blob).hexdigest()


def _is_quota_error(exc: Exception) -> bool:
    """Detect Google API 429 RESOURCE_EXHAUSTED / QUOTA_EXCEEDED across message variants."""
    msg = (str(exc) or "").lower()
    return any(token in msg for token in (
        "429", "quota exceeded", "resource_exhausted", "rate_limit",
        "too many requests",
    ))


def _get_db():
    if not FIRESTORE_AVAILABLE:
        return None
    try:
        return get_db()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core write — debounced + dirty-checked + circuit-protected
# ---------------------------------------------------------------------------
async def _schedule_write(doc_id: str, payload: Dict[str, Any]) -> None:
    """Public entry. Updates the pending payload for `doc_id` and starts
    a debounce timer if none is running. When the timer fires it commits
    the latest payload off-thread."""

    if not payload:
        return

    pending = _pending.get(doc_id)
    if pending is None:
        _pending[doc_id] = _PendingWrite(doc_id)
        pending = _pending[doc_id]

    payload_hash = _hash_payload(payload)

    with pending.lock:
        # Skip identical writes when nothing is queued (already flushed).
        if pending.payload is None and pending.last_written_hash == payload_hash:
            return
        pending.payload = payload

    # Don't restart the timer if one is already ticking — just replace the
    # payload so it gets picked up when the timer fires.
    if pending.debounce_task and not pending.debounce_task.done():
        return

    async def _debounce_then_flush():
        try:
            await asyncio.sleep(WRITE_DEBOUNCE_SECONDS)
        except asyncio.CancelledError:
            return
        await _flush(doc_id)

    try:
        loop = asyncio.get_running_loop()
        pending.debounce_task = loop.create_task(_debounce_then_flush())
    except RuntimeError:
        await _flush(doc_id)


async def _flush(doc_id: str) -> None:
    """Snapshots the pending payload and writes it off-thread."""
    pending = _pending.get(doc_id)
    if pending is None:
        return

    with pending.lock:
        if pending.payload is None:
            return
        payload = pending.payload
        payload_hash = _hash_payload(payload)
        # Clear pending so subsequent identical writes re-fire after a successful flush.
        pending.payload = None

    if _circuit.is_open():
        # Don't queue; just drop. The next legitimate state change will retry.
        return

    # Run the sync firebase-admin call in the default thread pool so the
    # Discord event loop stays responsive even during a 60-second quota-induced stall.
    try:
        await asyncio.to_thread(_blocking_write, doc_id, payload, payload_hash)
    except Exception as e:
        if _is_quota_error(e):
            _circuit.trip()
            print(f"[FIRESTORE STATS] ❌ Write {doc_id} failed: {e}")
        else:
            print(f"[FIRESTORE STATS] ❌ Write {doc_id} failed: {e}")


async def flush_now(doc_id: str) -> None:
    """Force immediate flush of pending payload for `doc_id`, bypassing debounce.
    Use for critical state changes (guild join/leave) where stale reads are unacceptable."""
    pending = _pending.get(doc_id)
    if pending is None:
        return

    # Cancel any pending debounce timer
    if pending.debounce_task and not pending.debounce_task.done():
        pending.debounce_task.cancel()

    await _flush(doc_id)


def _blocking_write(doc_id: str, payload: Dict[str, Any], payload_hash: str) -> None:
    """Runs in a worker thread. Talks to firebase-admin synchronously."""

    # Re-check circuit inside the thread in case it tripped between scheduling and execution.
    if _circuit.is_open():
        return

    pending = _pending.get(doc_id)
    if pending is not None:
        with pending.lock:
            # Another identical write already landed? Skip.
            if pending.last_written_hash == payload_hash:
                pending.payload = None
                return

    db = _get_db()
    if db is None:
        return

    try:
        db.collection(COLLECTION).document(doc_id).set(payload, merge=True)
    except Exception as e:
        # Bubble up so the asyncio.to_thread wrapper can route by exception type.
        raise

    if pending is not None:
        with pending.lock:
            pending.last_written_hash = payload_hash
            pending.last_write_monotonic = time.monotonic()

    _circuit.reset()


# ---------------------------------------------------------------------------
# Reads — unchanged from original behavior
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Public API — synchronous setters translate into scheduled async writes.
# Callers (main.py, web_app.py) do NOT need to change.
# ---------------------------------------------------------------------------
def delete_guild_from_map(doc_id: str, guild_id: str) -> None:
    """Remove a specific guild_id key from a map-based document in bot_status.
    Used for guild_channels, guild_roles, etc. when bot leaves a guild."""
    async def _delete():
        db = _get_db()
        if not db:
            return
        try:
            from google.cloud.firestore import FieldValue
            db.collection(COLLECTION).document(doc_id).update({
                guild_id: FieldValue.delete()
            })
            print(f"[FIRESTORE STATS] 🗑️ Deleted guild {guild_id} from {doc_id}")
        except Exception as e:
            print(f"[FIRESTORE STATS] ❌ Failed to delete {guild_id} from {doc_id}: {e}")

    _fire_and_forget(_delete())


def invalidate_stats_cache() -> None:
    """Force refresh of local stats cache by clearing guilds_list.
    Call after guild join/remove to ensure get_stats_snapshot() reads fresh data."""
    with _stats_lock:
        _local_stats["guilds_list"] = []
        _local_stats["guilds"] = 0
        _local_stats["members"] = 0
    print("[FIRESTORE STATS] 🔄 Local stats cache invalidated (guilds_list cleared)")


def set_stats(**kwargs):
    with _stats_lock:
        _local_stats.update(kwargs)
        _local_stats["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        snapshot = dict(_local_stats)

    _fire_and_forget(_schedule_write(DOC_ID, snapshot))


def set_guild_channels(guild_id: str, channels: list):
    with _guild_channels_lock:
        _local_guild_channels[guild_id] = channels

    # Batched write — collect across all guilds in one document.
    with _guild_channels_lock:
        full_snapshot = {gid: chs for gid, chs in _local_guild_channels.items()}

    _fire_and_forget(_schedule_write("guild_channels", full_snapshot))


def get_stats_snapshot() -> Dict[str, Any]:
    firestore_data = _read_from_firestore()

    with _stats_lock:
        raw = firestore_data if firestore_data else dict(_local_stats)

    return {
        "online":             raw.get("online", False),
        "username":           raw.get("username", "Synapse"),
        "uptime_fmt":         format_uptime(raw.get("uptime", 0)),
        "guilds":             raw.get("guilds", 0),
        "members":            raw.get("members", 0),
        "last_updated":       raw.get("last_updated", "-"),
        "guilds_list":        raw.get("guilds_list", [])
    }


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


def set_guild_roles(guild_id: str, roles: list):
    with _guild_roles_lock:
        _local_guild_roles[guild_id] = roles
    with _guild_roles_lock:
        full_snapshot = {gid: rs for gid, rs in _local_guild_roles.items()}
    _fire_and_forget(_schedule_write("guild_roles", full_snapshot))


def get_guild_roles(guild_id: str) -> list:
    db = _get_db()
    if db:
        try:
            doc = db.collection(COLLECTION).document("guild_roles").get()
            if doc.exists:
                data = doc.to_dict()
                return data.get(guild_id, [])
        except Exception:
            pass
    with _guild_roles_lock:
        return _local_guild_roles.get(guild_id, [])


def set_guild_categories(guild_id: str, categories: list):
    with _guild_categories_lock:
        _local_guild_categories[guild_id] = categories
    with _guild_categories_lock:
        full_snapshot = {gid: chs for gid, chs in _local_guild_categories.items()}
    _fire_and_forget(_schedule_write("guild_categories", full_snapshot))


def get_guild_categories(guild_id: str) -> list:
    db = _get_db()
    if db:
        try:
            doc = db.collection(COLLECTION).document("guild_categories").get()
            if doc.exists:
                data = doc.to_dict()
                return data.get(guild_id, [])
        except Exception:
            pass
    with _guild_categories_lock:
        return _local_guild_categories.get(guild_id, [])





def set_bot_instance(bot):
    global _bot_instance
    with _bot_instance_lock:
        _bot_instance = bot


def get_bot_instance():
    with _bot_instance_lock:
        return _bot_instance


# ---------------------------------------------------------------------------
# Fire-and-forget helper — works from both sync and async contexts.
# ---------------------------------------------------------------------------
def _fire_and_forget(coro):
    """Schedule a coroutine on the running loop, or run it inline if no loop is active."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop (sync context). Run the coroutine to completion in this thread.
        # Safe because _schedule_write itself only sets pending state and returns
        # after creating the debounce task; if no loop is available we do a direct flush.
        try:
            loop2 = asyncio.new_event_loop()
            try:
                loop2.run_until_complete(coro)
            finally:
                loop2.close()
        except Exception:
            pass
        return

    loop.create_task(coro)


# ---------------------------------------------------------------------------
# Public helpers — reusable by other cogs that talk to Firestore.
# Other cogs (leveling, ai_chat, etc.) can call:
#
#   from backend.utils.firestore_stats import firestore_circuit_open, trip_firestore_circuit
#
#   if firestore_circuit_open():
#       return  # skip the write
#   try:
#       await asyncio.to_thread(...)
#   except Exception as e:
#       if is_quota_error(e):
#           trip_firestore_circuit()
# ---------------------------------------------------------------------------
def firestore_circuit_open() -> bool:
    """Return True when the shared circuit breaker is open (writes should be skipped)."""
    return _circuit.is_open()


def trip_firestore_circuit() -> None:
    """Manually trip the shared circuit breaker (used by other cogs on 429)."""
    _circuit.trip()


def firestore_retry_after() -> float:
    """Seconds until the shared circuit breaker allows probes again."""
    return _circuit.retry_after()


# ---------------------------------------------------------------------------
# Diagnostics (handy for /status command if you want one)
# ---------------------------------------------------------------------------
def get_firestore_diagnostics() -> Dict[str, Any]:
    out = {
        "available":          FIRESTORE_AVAILABLE,
        "circuit_open":       _circuit.is_open(),
        "circuit_retry_after": round(_circuit.retry_after(), 1),
        "debounce_seconds":   WRITE_DEBOUNCE_SECONDS,
        "pending_docs": {},
    }
    for doc_id, pending in _pending.items():
        with pending.lock:
            out["pending_docs"][doc_id] = {
                "has_pending_payload": pending.payload is not None,
                "last_write_hash":     (pending.last_written_hash or "")[:12],
                "seconds_since_last":  round(time.monotonic() - pending.last_write_monotonic, 1) if pending.last_write_monotonic else None,
            }
    return out


# ---------------------------------------------------------------------------
# Integrity & Cleanup — Guild Lifecycle Management
# ---------------------------------------------------------------------------
async def _delete_subcollections(db, guild_id: str, subcollections: list) -> None:
    """Recursively delete all documents in subcollections under guild_settings/{guild_id}."""
    for subcoll in subcollections:
        try:
            subcoll_ref = db.collection("guild_settings").document(guild_id).collection(subcoll)
            docs = await asyncio.to_thread(lambda: list(subcoll_ref.stream()))
            for doc in docs:
                await asyncio.to_thread(doc.reference.delete)
            if docs:
                print(f"[FIRESTORE CLEANUP] 🗑️ Deleted {len(docs)} docs from guild_settings/{guild_id}/{subcoll}")
        except Exception as e:
            print(f"[FIRESTORE CLEANUP] ❌ Failed to delete subcollection {subcoll} for {guild_id}: {e}")


async def delete_guild_settings(guild_id: str) -> None:
    """Delete guild_settings/{guild_id} and all its subcollections."""
    db = _get_db()
    if not db:
        return

    subcollections = ["ai_chat", "auto_responders", "leveling", "boost_settings"]

    # 1. Delete subcollections
    await _delete_subcollections(db, guild_id, subcollections)

    # 2. Delete parent document
    try:
        await asyncio.to_thread(
            db.collection("guild_settings").document(guild_id).delete
        )
        print(f"[FIRESTORE CLEANUP] ✅ Deleted guild_settings/{guild_id}")
    except Exception as e:
        print(f"[FIRESTORE CLEANUP] ❌ Failed to delete guild_settings/{guild_id}: {e}")


async def create_guild_settings_minimal(guild_id: str, guild_name: str) -> None:
    """Create minimal guild_settings document on guild join (eager init)."""
    db = _get_db()
    if not db:
        return

    try:
        from google.cloud.firestore import SERVER_TIMESTAMP
        await asyncio.to_thread(
            db.collection("guild_settings").document(guild_id).set,
            {"guild_name": guild_name, "created_at": SERVER_TIMESTAMP},
            merge=True
        )
        print(f"[FIRESTORE CLEANUP] ✅ Created minimal guild_settings/{guild_id} ({guild_name})")
    except Exception as e:
        print(f"[FIRESTORE CLEANUP] ❌ Failed to create guild_settings/{guild_id}: {e}")


async def integrity_sweep(bot) -> None:
    """Scan Firestore for orphaned guild_settings documents and delete them.
    Runs on bot startup to ensure data consistency."""
    db = _get_db()
    if not db:
        print("[FIRESTORE CLEANUP] ⚠️ Firestore unavailable, skipping integrity sweep")
        return

    try:
        # Get active guild IDs from Discord
        active_guild_ids = {str(g.id) for g in bot.guilds}

        # Get stored guild IDs from Firestore
        stored_docs = await asyncio.to_thread(
            lambda: list(db.collection("guild_settings").stream())
        )
        stored_guild_ids = {doc.id for doc in stored_docs}

        # Find orphaned guilds
        orphaned = stored_guild_ids - active_guild_ids

        if not orphaned:
            print("[FIRESTORE CLEANUP] ✅ Integrity sweep clean — no orphaned guilds")
            return

        print(f"[FIRESTORE CLEANUP] 🔍 Found {len(orphaned)} orphaned guild(s): {orphaned}")

        # Delete orphaned guild settings
        for guild_id in orphaned:
            await delete_guild_settings(guild_id)
            # Also clean up bot_status maps
            delete_guild_from_map("guild_channels", guild_id)

        print(f"[FIRESTORE CLEANUP] ✅ Integrity sweep complete — removed {len(orphaned)} orphaned guild(s)")

    except Exception as e:
        print(f"[FIRESTORE CLEANUP] ❌ Integrity sweep failed: {e}")
