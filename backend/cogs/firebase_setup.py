import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

def init_firebase():
    """Initialize Firebase Firestore with dual mode support (VS Code / Replit)"""

    if firebase_admin._apps:
        print("[FIREBASE] ℹ️ Firebase sudah di-init sebelumnya.")
        return firestore.client()

    firebase_key = os.getenv("FIREBASE_KEY", "")

    try:
        # Resolve path relative ke backend/ folder
        _backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cred_path = os.path.join(_backend_dir, firebase_key)

        # Mode 1: VS Code (file path)
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
            print(f"         Cek path: {cred_path}")
            return None

        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("[FIREBASE] ✅ Berhasil terhubung ke Firestore!")
        return db

    except Exception as e:
        print(f"[FIREBASE] ❌ Gagal init Firebase: {e}")
        return None

db = init_firebase()