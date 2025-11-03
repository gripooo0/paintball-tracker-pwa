import time, os, json
from typing import Dict, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from jose import jwt, JWTError
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from fastapi.middleware.cors import CORSMiddleware

# --- Config ---
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-this")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 60 * 60 * 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI()
# serve static files (including PWA manifest and service worker)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# allow CORS from anywhere for demo (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DB (SQLite by default, can be replaced by DATABASE_URL env var) ---
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./paintball.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_admin = Column(Integer, default=0)

class Location(Base):
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    lat = Column(Float)
    lon = Column(Float)
    timestamp = Column(Integer)

Base.metadata.create_all(bind=engine)

# Create admin user at startup if not exists
def create_admin():
    db = SessionLocal()
    admin = db.query(User).filter(User.username == "admin1").first()
    if not admin:
        admin = User(username="admin1", hashed_password=pwd_context.hash("admin123"), is_admin=1)
        db.add(admin)
        db.commit()
    db.close()

create_admin()

# --- Simple token utils ---
def create_access_token(data: dict):
    to_encode = data.copy()
    to_encode.update({"exp": int(time.time()) + ACCESS_TOKEN_EXPIRE_SECONDS})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# --- Websocket manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.latest: Dict[str, dict] = {}
        self.history: Dict[str, List[dict]] = {}

    async def connect(self, username: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[username] = websocket

    def disconnect(self, username: str):
        if username in self.active_connections:
            del self.active_connections[username]

manager = ConnectionManager()
admin_connections: List[WebSocket] = []

# --- Routes: pages ---
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

# --- Auth endpoints ---
@app.post("/register")
def register(username: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    if db.query(User).filter(User.username == username).first():
        db.close()
        return RedirectResponse(url="/register?error=exists", status_code=302)
    user = User(username=username, hashed_password=pwd_context.hash(password), is_admin=0)
    db.add(user)
    db.commit()
    db.close()
    return RedirectResponse(url="/login?registered=1", status_code=302)

@app.post("/token")
def login_for_access_token(username: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    user = db.query(User).filter(User.username == username).first()
    db.close()
    if not user or not pwd_context.verify(password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    token = create_access_token({"sub": username, "is_admin": user.is_admin})
    return {"access_token": token, "token_type": "bearer"}

# --- WebSocket endpoints ---
@app.websocket("/ws/user/{token}")
async def websocket_user(websocket: WebSocket, token: str):
    try:
        username = verify_token(token)
    except HTTPException:
        await websocket.close(code=1008)
        return
    await manager.connect(username, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            import json
            obj = json.loads(data)
            lat = float(obj.get("lat"))
            lon = float(obj.get("lon"))
            ts = int(time.time())
            manager.latest[username] = {"lat": lat, "lon": lon, "ts": ts}
            manager.history.setdefault(username, []).append({"lat": lat, "lon": lon, "ts": ts})
            if len(manager.history[username]) > 200:
                manager.history[username].pop(0)
            db = SessionLocal()
            loc = Location(username=username, lat=lat, lon=lon, timestamp=ts)
            db.add(loc)
            db.commit()
            db.close()
            payload = {"type": "update", "username": username, "lat": lat, "lon": lon, "ts": ts}
            for admin_ws in list(admin_connections):
                try:
                    await admin_ws.send_text(json.dumps(payload))
                except Exception:
                    try:
                        admin_connections.remove(admin_ws)
                    except:
                        pass
    except WebSocketDisconnect:
        manager.disconnect(username)
    except Exception:
        manager.disconnect(username)

@app.websocket("/ws/admin/{token}")
async def websocket_admin(websocket: WebSocket, token: str):
    try:
        username = verify_token(token)
    except HTTPException:
        await websocket.close(code=1008)
        return
    db = SessionLocal()
    user = db.query(User).filter(User.username == username).first()
    db.close()
    if not user or user.is_admin == 0:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    admin_connections.append(websocket)
    import json
    initial = {"type": "initial", "latest": manager.latest, "history": manager.history}
    await websocket.send_text(json.dumps(initial))
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        try:
            admin_connections.remove(websocket)
        except:
            pass

# --- Simple endpoint to fetch history from DB (admin-only) ---
@app.get("/api/history/{username}")
def get_history(username: str, token: str):
    verify_token(token)
    db = SessionLocal()
    rows = db.query(Location).filter(Location.username == username).order_by(Location.timestamp.desc()).limit(200).all()
    db.close()
    return [{"lat": r.lat, "lon": r.lon, "ts": r.timestamp} for r in rows]
