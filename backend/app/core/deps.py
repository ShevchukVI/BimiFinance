"""FastAPI dependencies: authentication (internal bot key / user JWT) and authorization (family, admin).

Multi-family model:
- X-Family-Id header overrides the target family (falls back to user's current_active_family_id).
- X-User-Id header lets the internal BOT act on behalf of a specific user (bot = trusted proxy).
- Membership and role are ALWAYS verified against family_members in the DB (never trust client data alone).
"""
import threading
import time
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import crud
from app.core.security import decode_token, verify_api_key
from app.database import get_db


class Actor:
    """Authenticated principal: internal bot (optionally acting as a user) or a Mini App user."""

    def __init__(self, kind: str, user=None):
        self.kind = kind
        self.user = user

    @property
    def family_id(self):
        return self.user.current_active_family_id if self.user else None

    @property
    def user_id(self):
        return self.user.id if self.user else None

    @property
    def role(self):
        return self.user.role if self.user else "admin"


def require_internal_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    if not verify_api_key(x_api_key or ""):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def get_actor(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_user_id: Optional[int] = Header(None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> Actor:
    if x_api_key and verify_api_key(x_api_key):
        if x_user_id:
            user = crud.get_user_by_id(db, x_user_id)
            if not user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
            return Actor(kind="user", user=user)
        return Actor(kind="bot")
    if authorization and authorization.startswith("Bearer "):
        payload = decode_token(authorization.split(" ", 1)[1])
        user = crud.get_user_by_tg_id(db, int(payload["sub"]))
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return Actor(kind="user", user=user)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing credentials")


def _target_family(x_family_id: Optional[int], actor: Actor) -> int:
    target = x_family_id if x_family_id is not None else actor.family_id
    if not target:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active family")
    return target


def require_family(family_id: int, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    if actor.kind == "bot":
        return
    if not crud.is_family_member(db, actor.user_id, family_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def require_family_admin(family_id: int, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    if actor.kind == "bot":
        return
    role = crud.get_membership_role(db, actor.user_id, family_id)
    if role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")


def get_effective_family_id(
    x_family_id: Optional[int] = Header(None, alias="X-Family-Id"),
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
) -> int:
    if actor.kind == "bot":
        if not x_family_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Family-Id header required")
        return x_family_id
    target = _target_family(x_family_id, actor)
    if not crud.is_family_member(db, actor.user_id, target):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return target


def require_admin_in_family(
    x_family_id: Optional[int] = Header(None, alias="X-Family-Id"),
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
) -> int:
    if actor.kind != "user":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User authentication required")
    target = _target_family(x_family_id, actor)
    if crud.get_membership_role(db, actor.user_id, target) != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return target


def require_user(actor: Actor = Depends(get_actor)) -> Actor:
    if actor.kind != "user":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User authentication required")
    return actor


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
