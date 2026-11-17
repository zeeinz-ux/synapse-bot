"""
Synapse Bot - Main Entrypoint
Compatible with local execution, Docker, Wispbyte, Pterodactyl, Render, and Railway.
"""
import os
import sys
import glob
import threading

# 1. Pastikan project root ada di sys.path
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 2. Support prefix install (.local/lib/python*/site-packages) seperti di Wispbyte
for _site in glob.glob(os.path.join(_project_root, ".local", "lib", "python*", "site-packages")):
    if _site not in sys.path:
        sys.path.insert(0, _site)

# 3. Load environment variables (.env di root atau di folder backend/)
from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"))
load_dotenv(os.path.join(_project_root, "backend", ".env"))
load_dotenv()

def start_web_server():
    """Jalankan web server Flask di thread terpisah jika diaktifkan."""
    try:
        from backend.web.web_app import app
        port = int(os.getenv("PORT") or os.getenv("SERVER_PORT") or 8080)
        host = os.getenv("HOST", "0.0.0.0")
        print(f"[RUNNER] 🌐 Menjalankan Web Dashboard di {host}:{port}...")
        app.run(host=host, port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f"[RUNNER] [ERROR] Gagal menjalankan Web Dashboard: {e}")

if __name__ == "__main__":
    # Cek apakah user ingin menjalankan web dashboard juga (ENABLE_WEB=true atau START_WEB=true atau RUN_WEB=1)
    run_web = os.getenv("ENABLE_WEB", "").lower() in ("true", "1", "yes") or \
              os.getenv("START_WEB", "").lower() in ("true", "1", "yes") or \
              os.getenv("RUN_WEB", "").lower() in ("true", "1", "yes")
    
    if run_web:
        web_thread = threading.Thread(target=start_web_server, daemon=True)
        web_thread.start()

    # Jalankan bot Discord utama
    import backend.main
