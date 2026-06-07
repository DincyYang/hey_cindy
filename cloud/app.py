# app.py
import os
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# ── Config ───────────────────────────────────────────
API_TOKEN = os.environ.get("HEY_CINDY_TOKEN", "cindy-dev-token-123")
DB_URL    = os.environ.get("DATABASE_URL", "sqlite:////home/ubuntu/hey-cindy-cloud/hey_cindy.db")

# ── SQLite ────────────────────────────────────────────
engine       = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base         = declarative_base()

class CommandLog(Base):
    __tablename__ = "command_logs"
    id         = Column(Integer, primary_key=True, index=True)
    command    = Column(String(10))
    raw_text   = Column(String(500), nullable=True)
    source     = Column(String(20), default="voice")
    confidence = Column(Float, nullable=True)
    reason     = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(bind=engine)

# ── 内存状态（替代 Redis）────────────────────────────
_light_state = {"value": "off"}

def get_light_state() -> str:
    return _light_state["value"]

def set_light_state(state: str):
    _light_state["value"] = state

# ── Auth ──────────────────────────────────────────────
def require_token(authorization: str | None):
    if authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")

# ── FastAPI ───────────────────────────────────────────
app = FastAPI(title="HeyCindy Cloud API", version="2.0")
START_TIME = datetime.now(timezone.utc)

class CommandRequest(BaseModel):
    command: str
    raw_text: Optional[str] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None
    source: str = "voice"

@app.get("/state")
def get_state(authorization: Optional[str] = Header(None)):
    require_token(authorization)
    db = SessionLocal()
    logs = db.query(CommandLog).order_by(CommandLog.created_at.desc()).limit(10).all()
    db.close()
    return {
        "light": get_light_state(),
        "history": [
            {"timestamp": str(l.created_at), "raw": l.raw_text, "normalized": l.command}
            for l in reversed(logs)
        ],
        "count": len(logs),
    }

@app.post("/command")
def post_command(req: CommandRequest, authorization: Optional[str] = Header(None)):
    require_token(authorization)
    if req.command not in ("on", "off"):
        raise HTTPException(status_code=400, detail="command must be 'on' or 'off'")
    set_light_state(req.command)
    db = SessionLocal()
    log = CommandLog(
        command=req.command,
        raw_text=req.raw_text,
        source=req.source,
        confidence=req.confidence,
        reason=req.reason,
    )
    db.add(log)
    db.commit()
    db.close()
    return {"ok": True, "light": req.command}

@app.get("/health")
def health():
    return {"status": "ok", "uptime": str(datetime.now(timezone.utc) - START_TIME)}
