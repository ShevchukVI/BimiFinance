"""FastAPI dependencies: authentication (internal bot key / user JWT) and authorization (family, admin)."""
import threading
import time
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import crud
from app.core.security import decode_token, verify_api_key
from app.database import get_db


class Actor:
    """Authenticated principal: either the internal bot or a Mini App user."""

    def __init__(self, kind: str, user=None):
        self.kind = kind          # 'bot' | 'user'
        self.user = user          # models.User | None

    @property
    def family_id(self):
        return self.user.family_id if self.user else None

    @property
    def user_id(self):
        return self.user.id if self.user else None

    @property
    def role(self):
        return self.user.role if self.user else "admin"  # bot is privileged


def require_internal_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    if not verify_api_key(x_api_key or ""):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def get_actor(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Actor:
    if x_api_key and verify_api_key(x_api_key):
        return Actor(kind="bot")
    if authorization and authorization.startswith("Bearer "):
        payload = decode_token(authorization.split(" ", 1)[1])
        user = crud.get_user_by_tg_id(db, int(payload["sub"]))
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return Actor(kind="user", user=user)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing credentials")


def require_family(family_id: int, actor: Actor = Depends(get_actor)):
    """IDOR guard: a 'user' actor may only touch its own family. The bot is trusted."""
    if actor.kind == "bot":
        return
    if actor.family_id != family_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def require_family_admin(family_id: int, actor: Actor = Depends(get_actor)):
    if actor.kind == "bot":
        return
    if actor.family_id != family_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if actor.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")


# ---------- Minimal in-memory rate limiting (per process) ----------
_RL_STORE = {}
_RL_LOCK = threading.Lock()


def rate_limit_ip(request: Request, limit: int, window: int):
    key = request.client.host if request.client else "unknown"
    now = time.time()
    with _RL_LOCK:
        hits = [t for t in _RL_STORE.get(key, []) if now - t < window]
        if len(hits) >= limit:
            raise HTTPException(status_code=429, detail="Too many requests")
        hits.append(now)
        _RL_STORE[key] = hits
