# cloud/app.py
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from cloud.state import LightState
from cloud.db import make_session_factory, log_command, recent_commands

API_TOKEN = os.environ.get("HEY_CINDY_TOKEN", "cindy-dev-token-123")

# Wire up the two stores once at startup.
light = LightState()                       # Redis (+ in-memory fallback)
session_factory = make_session_factory()   # PostgreSQL


def require_token(authorization: Optional[str]):
    if authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")


app = FastAPI(title="HeyCindy Cloud API", version="3.0")
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
    history = recent_commands(session_factory)
    return {"light": light.get(), "history": history, "count": len(history)}


@app.post("/command")
def post_command(req: CommandRequest, authorization: Optional[str] = Header(None)):
    require_token(authorization)
    if req.command not in ("on", "off"):
        raise HTTPException(status_code=400, detail="command must be 'on' or 'off'")

    light.set(req.command)               # critical path  -> Redis (with fallback)
    log_command(                         # non-critical   -> Postgres (errors swallowed)
        session_factory,
        command=req.command,
        raw_text=req.raw_text,
        source=req.source,
        confidence=req.confidence,
        reason=req.reason,
    )
    return {"ok": True, "light": req.command}


@app.get("/health")
def health():
    return {"status": "ok", "uptime": str(datetime.now(timezone.utc) - START_TIME)}
