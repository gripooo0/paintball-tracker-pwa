# Paintball Tracker (PWA-ready)

This is a minimal demo of a Paintball Tracker:
- FastAPI backend (WebSockets) for live location streaming
- PWA frontend (installable on phone)
- Admin panel to watch live locations

## Run locally (development)
1. python -m venv .venv
2. Activate venv:
   - PowerShell: .\.venv\Scripts\Activate
   - CMD: .\.venv\Scripts\activate
3. pip install -r requirements.txt
4. uvicorn main:app --reload --host 0.0.0.0 --port 8000
5. Open http://localhost:8000

## Make it accessible on your phone (same Wi‑Fi)
1. Run server with host 0.0.0.0
2. Find PC local IP (e.g. 192.168.0.12)
3. On phone open: http://<PC_IP>:8000

## Deploy to Railway (example)
1. Create account on https://railway.app
2. Create new project → "Deploy from GitHub" or "Start from scratch"
3. Push this repo to GitHub or use Railway CLI
4. Set up service to run: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add env vars: SECRET_KEY (optional)
6. Railway provides public URL — open it on phone and install as PWA

## Notes
- This is a demo. Use only with consenting people.
- For production, secure SECRET_KEY, use HTTPS, and respect privacy laws.
