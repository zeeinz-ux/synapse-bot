web: gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 backend.web.web_app:app
worker: sh -c 'until python backend/main.py; do echo "worker crashed (rc=$?) - respawn in 5s"; sleep 5; done'