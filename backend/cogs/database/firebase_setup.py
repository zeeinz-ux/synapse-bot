import os
import json
import base64
import firebase_admin
from firebase_admin import credentials, firestore

# Variabel internal untuk menyimpan instance database
_db_instance = None

def init_firebase():
    """Inisialisasi Firebase aman untuk VS Code (Lokal) dan Render (Production)"""
    global _db_instance

    # Jika sudah terinisialisasi sebelumnya, pakai yang sudah ada
    if firebase_admin._apps:
        _db_instance = firestore.client()
        return _db_instance

    firebase_key = os.getenv("FIREBASE_KEY", "").strip()

    if not firebase_key:
        print("[FIREBASE] [ERROR] Error: Environment Variable 'FIREBASE_KEY' tidak ditemukan!")
        return None

    try:
        cred = None

        # --- MODE 1: BASE64 ENCODED (Rekomendasi Utama untuk Render) ---
        if not firebase_key.startswith("{") and len(firebase_key) > 100:
            print("[FIREBASE] [KEY] Mendeteksi mode Base64. Mengonversi ke JSON...")
            decoded_bytes = base64.b64decode(firebase_key)
            service_account_info = json.loads(decoded_bytes.decode("utf-8"))
            cred = credentials.Certificate(service_account_info)

        # --- MODE 2: RAW JSON STRING (Replit / Env String) ---
        elif firebase_key.startswith("{"):
            print("[FIREBASE] [FILE] Mendeteksi mode Raw JSON String.")
            service_account_info = json.loads(firebase_key)
            cred = credentials.Certificate(service_account_info)

        # --- MODE 3: FILE PATH FALLBACK (VS Code Lokal / Render Secret Files) ---
        else:
            print("[FIREBASE] [DIR] Mendeteksi mode File Path. Mencari lokasi file...")
            current_dir = os.path.dirname(os.path.abspath(__file__)) # backend/cogs/database
            
            # Melacak kecocokan file dari folder terdalam sampai root project
            possible_paths = [
                os.path.abspath(os.path.join(current_dir, firebase_key)),         # di folder database/
                os.path.abspath(os.path.join(current_dir, "..", firebase_key)),     # di folder cogs/
                os.path.abspath(os.path.join(current_dir, "../..", firebase_key)),   # di folder backend/
                os.path.abspath(os.path.join(current_dir, "../../..", firebase_key)), # di Root Project (/)
                os.path.abspath(firebase_key)                                       # Absolute path langsung
            ]

            for path in possible_paths:
                if os.path.isfile(path):
                    print(f"[FIREBASE] [OK] File ditemukan di: {path}")
                    cred = credentials.Certificate(path)
                    break
            
            if not cred:
                print(f"[FIREBASE] [ERROR] File '{firebase_key}' tidak ditemukan di folder manapun!")
                return None

        # Hubungkan ke Firebase
        firebase_admin.initialize_app(cred)
        _db_instance = firestore.client()
        print("[FIREBASE] [FIRE] Berhasil terhubung ke Firestore!")
        return _db_instance

    except Exception as e:
        print(f"[FIREBASE] [ERROR] Gagal total saat inisialisasi: {e}")
        _db_instance = None
        return None

def get_db():
    """Fungsi panggil global agar Flask selalu mendapatkan koneksi db yang siap pakai"""
    global _db_instance
    if _db_instance is None:
        return init_firebase()
    return _db_instance

# Jalankan otomatis saat bot/web pertama kali dinyalakan
db = init_firebase()