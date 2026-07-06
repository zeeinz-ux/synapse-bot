import os
import sys
import json
import base64
from datetime import datetime, timezone
from pathlib import Path

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

_BACKUP_DIR = os.path.join(_project_root, "backups")

def _lazy_init():
    import firebase_admin
    from firebase_admin import credentials, firestore

    if firebase_admin._apps:
        return firestore.client()

    firebase_key = os.getenv("FIREBASE_KEY", "").strip()
    if not firebase_key:
        print("[BACKUP] [ERROR] FIREBASE_KEY not set")
        return None

    try:
        cred = None
        if not firebase_key.startswith("{") and len(firebase_key) > 100:
            decoded_bytes = base64.b64decode(firebase_key)
            service_account_info = json.loads(decoded_bytes.decode("utf-8"))
            cred = credentials.Certificate(service_account_info)
        elif firebase_key.startswith("{"):
            service_account_info = json.loads(firebase_key)
            cred = credentials.Certificate(service_account_info)
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            possible_paths = [
                os.path.abspath(os.path.join(current_dir, firebase_key)),
                os.path.abspath(os.path.join(current_dir, "..", firebase_key)),
                os.path.abspath(os.path.join(current_dir, "../..", firebase_key)),
                os.path.abspath(os.path.join(current_dir, "../../..", firebase_key)),
                os.path.abspath(firebase_key),
            ]
            for path in possible_paths:
                if os.path.isfile(path):
                    cred = credentials.Certificate(path)
                    break
            if not cred:
                print(f"[BACKUP] [ERROR] Key file '{firebase_key}' not found")
                return None

        firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        print(f"[BACKUP] [ERROR] Firebase init failed: {e}")
        return None


def backup(collections: list[str] | None = None) -> str | None:
    db = _lazy_init()
    if not db:
        return None

    os.makedirs(_BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(_BACKUP_DIR, f"firestore_backup_{timestamp}.json")

    data = {"_meta": {"backup_at": timestamp, "collections": {}}}

    if collections is None:
        collections = [c.id for c in db.collections()]

    for col_name in collections:
        docs = db.collection(col_name).stream()
        col_data = {}
        for doc in docs:
            doc_dict = doc.to_dict()
            if doc_dict:
                _convert_timestamps(doc_dict)
            col_data[doc.id] = doc_dict
        if col_data:
            data["_meta"]["collections"][col_name] = len(col_data)
            data[col_name] = col_data
            print(f"[BACKUP]  {col_name}: {len(col_data)} docs")
        else:
            print(f"[BACKUP]  {col_name}: (empty)")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    print(f"[BACKUP] ✅ Saved to {filepath} ({os.path.getsize(filepath):,} bytes)")
    return filepath


def restore(filepath: str, dry_run: bool = False) -> bool:
    db = _lazy_init()
    if not db:
        return False

    if not os.path.isfile(filepath):
        print(f"[RESTORE] [ERROR] File not found: {filepath}")
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    collections = {k: v for k, v in data.items() if k != "_meta"}
    total_docs = sum(len(docs) for docs in collections.values())

    print(f"[RESTORE] Found {len(collections)} collections, {total_docs} docs in {filepath}")

    if dry_run:
        print("[RESTORE] Dry-run mode — no writes performed")
        return True

    for col_name, docs in collections.items():
        batch = db.batch()
        count = 0
        for doc_id, doc_data in docs.items():
            if doc_data is None:
                doc_data = {}
            ref = db.collection(col_name).document(doc_id)
            batch.set(ref, doc_data)
            count += 1
            if count % 500 == 0:
                batch.commit()
                batch = db.batch()
        batch.commit()
        print(f"[RESTORE]  {col_name}: {count} docs restored")

    print(f"[RESTORE] ✅ Done — {total_docs} docs restored from {filepath}")
    return True


def list_backups() -> list[dict]:
    os.makedirs(_BACKUP_DIR, exist_ok=True)
    files = sorted(Path(_BACKUP_DIR).glob("firestore_backup_*.json"), reverse=True)
    result = []
    for fp in files:
        result.append({
            "filename": fp.name,
            "path": str(fp),
            "size": fp.stat().st_size,
            "modified": datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc).isoformat(),
        })
    return result


def _convert_timestamps(d: dict):
    for k, v in list(d.items()):
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif isinstance(v, dict):
            _convert_timestamps(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    _convert_timestamps(item)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "backup"

    if action == "backup":
        cols = sys.argv[2:] if len(sys.argv) > 2 else None
        backup(cols)

    elif action == "restore":
        if len(sys.argv) < 3:
            print("Usage: python backend/scripts/backup_firestore.py restore <filepath> [--dry-run]")
            sys.exit(1)
        filepath = sys.argv[2]
        dry = "--dry-run" in sys.argv
        restore(filepath, dry_run=dry)

    elif action == "list":
        backups = list_backups()
        if backups:
            print(f"{'Filename':45s} {'Size':>12s}  {'Modified'}")
            print("-" * 75)
            for b in backups:
                size_str = f"{b['size']:,} bytes" if b['size'] < 1024 * 1024 else f"{b['size'] / 1024 / 1024:.1f} MB"
                print(f"{b['filename']:45s} {size_str:>12s}  {b['modified'][:19]}")
        else:
            print("[BACKUP] No backup files found")

    elif action == "info":
        if len(sys.argv) < 3:
            print("Usage: python backend/scripts/backup_firestore.py info <filepath>")
            sys.exit(1)
        filepath = sys.argv[2]
        if not os.path.isfile(filepath):
            print(f"[ERROR] File not found: {filepath}")
            sys.exit(1)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        meta = data.get("_meta", {})
        collections = {k: v for k, v in data.items() if k != "_meta"}
        total_docs = sum(len(docs) for docs in collections.values())
        print(f"Backup file: {filepath}")
        print(f"Backup time: {meta.get('backup_at', 'unknown')}")
        print(f"Collections: {len(collections)}")
        print(f"Total docs:  {total_docs}")
        print(f"File size:   {os.path.getsize(filepath):,} bytes")
        print()
        for col_name, docs in collections.items():
            print(f"  {col_name}: {len(docs)} docs")

    else:
        print(f"Unknown action: {action}")
        print("Usage: python backend/scripts/backup_firestore.py [backup|restore|list|info] [args]")
