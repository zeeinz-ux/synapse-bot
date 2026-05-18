import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

def init_firebase():
    """Initialize Firebase Firestore with dual mode support (VS Code / Replit)"""

    # Guard: prevent double initialization
    if firebase_admin._apps:
        print("[FIREBASE] ℹ️ Firebase sudah di-init sebelumnya.")
        return firestore.client()

    firebase_key = os.getenv("FIREBASE_KEY", "")

    try:
        # Mode 1: VS Code (file path)
        if os.path.isfile(firebase_key):
            print(f"[FIREBASE] 📁 Menggunakan file: {firebase_key}")
            cred = credentials.Certificate(firebase_key)

        # Mode 2: Replit (JSON string 1 baris)
        elif firebase_key.strip().startswith("{"):
            print("[FIREBASE] 📄 Menggunakan JSON string (Replit mode)")
            service_account_info = json.loads(firebase_key)
            cred = credentials.Certificate(service_account_info)

        else:
            print("[FIREBASE] ❌ FIREBASE_KEY tidak valid!")
            print("         Pastikan isi .env dengan path file atau JSON string.")
            return None

        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("[FIREBASE] ✅ Berhasil terhubung ke Firestore!")
        return db

    except Exception as e:
        print(f"[FIREBASE] ❌ Gagal init Firebase: {e}")
        return None

# Auto-init when imported (for main.py)
db = init_firebase()