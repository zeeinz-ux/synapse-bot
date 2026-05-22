#fiebase_setup.py

import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

def initialize_firestore():
    """Initialize Firebase Firestore and return the client instance."""
    if firebase_admin._apps:
        print("[FIREBASE] ℹ️ Firebase sudah di-init sebelumnya.")
        try:
            db = firestore.client()
            return db
        except Exception as e:
            print(f"[FIREBASE] ❌ Gagal mendapatkan client Firestore yang ada: {e}")
            return None

    firebase_key = os.getenv("FIREBASE_KEY", "")
    if not firebase_key:
        print("[FIREBASE] ❌ Environment variable FIREBASE_KEY tidak ditemukan.")
        return None

    try:
        # Mode 1: FIREBASE_KEY adalah JSON string (umum di Render/Heroku)
        if firebase_key.strip().startswith("{"):
            print("[FIREBASE] 📄 Menggunakan JSON string dari environment variable.")
            service_account_info = json.loads(firebase_key)
            cred = credentials.Certificate(service_account_info)
        # Mode 2: FIREBASE_KEY adalah path ke file (umum di lokal/VM)
        else:
            # Resolve path relative ke root project
            _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            cred_path = os.path.join(_project_root, firebase_key)
            
            if os.path.isfile(cred_path):
                print(f"[FIREBASE] 📁 Menggunakan file: {cred_path}")
                cred = credentials.Certificate(cred_path)
            else:
                print(f"[FIREBASE] ❌ File kredensial tidak ditemukan di path: {cred_path}")
                return None

        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("[FIREBASE] ✅ Berhasil terhubung ke Firestore!")
        return db

    except Exception as e:
        print(f"[FIREBASE] ❌ Gagal init Firebase: {e}")
        return None
