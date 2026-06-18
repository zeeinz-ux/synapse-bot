import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

db = None

def init_firebase():
    """Initialize Firebase Firestore with dual mode support (VS Code / Replit / Render)"""
    global db

    if firebase_admin._apps:
        print("[FIREBASE] ℹ️ Firebase sudah di-init sebelumnya.")
        db = firestore.client()
        return db

    firebase_key = os.getenv("FIREBASE_KEY", "")

    try:
        # Resolve path relative ke backend/ folder
        _backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cred_path = os.path.join(_backend_dir, firebase_key)

        # Fallback: kalau tidak ada di backend/, cek root project (untuk Render Secret Files)
        if not os.path.isfile(cred_path):
            root_dir = os.path.dirname(_backend_dir)
            cred_path = os.path.join(root_dir, firebase_key)
            print(f"[FIREBASE] 🔍 Fallback ke root: {cred_path}")

        # Mode 1: VS Code / Render dengan path file
        if os.path.isfile(cred_path):
            print(f"[FIREBASE] 📁 Menggunakan file: {cred_path}")
            cred = credentials.Certificate(cred_path)

        # Mode 2: Replit (JSON string 1 baris)
        elif firebase_key.strip().startswith("{"):
            print("[FIREBASE] 📄 Menggunakan JSON string (Replit mode)")
            service_account_info = json.loads(firebase_key)
            cred = credentials.Certificate(service_account_info)

        else:
            print("[FIREBASE] ❌ FIREBASE_KEY tidak valid!")
            print(f"         Cek path backend: {os.path.join(_backend_dir, firebase_key)}")
            print(f"         Cek path root: {os.path.join(os.path.dirname(_backend_dir), firebase_key)}")
            return None

        # ← HANYA Firestore, TIDAK pakai Storage (FREE tier)
        firebase_admin.initialize_app(cred)

        db = firestore.client()
        print("[FIREBASE] ✅ Berhasil terhubung ke Firestore!")
        return db

    except Exception as e:
        print(f"[FIREBASE] ❌ Gagal init Firebase: {e}")
        return None

# Init saat import module
db = init_firebase()