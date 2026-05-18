import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

def init_firestore():
    try:
        # Coba dari environment variable dulu (untuk Replit/Production)
        firebase_key_json = os.environ.get("FIREBASE_KEY")
        
        if firebase_key_json:
            firebase_key_dict = json.loads(firebase_key_json)
            cred = credentials.Certificate(firebase_key_dict)
        else:
            # Fallback ke file lokal (untuk development di VS Code)
            cred = credentials.Certificate("serviceAccountKey.json")
            
        firebase_admin.initialize_app(cred)
        print("[FIREBASE] ✅ Berhasil terhubung ke Firestore!")
        return firestore.client()
        
    except Exception as e:
        print(f"[ERROR] ❌ Gagal konek ke Firebase: {e}")
        return None

db = init_firestore()