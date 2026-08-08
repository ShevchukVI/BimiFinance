from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import crud, schemas
from app.core import security
from app.core.deps import Actor, get_actor, rate_limit_ip, require_family_admin
from app.database import get_db

router = APIRouter(tags=["users"])


@router.post("/users", response_model=schemas.UserOut)
def create_user(payload: schemas.UserCreate, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    """Bot: trusted (family in body). Mini App: family admin only."""
    if actor.kind == "user":
        require_family_admin(payload.family_id, actor)
    mono_enc = security.encrypt_secret(payload.mono_token) if payload.mono_token else None
    return crud.create_user(db, payload.family_id, payload.name, payload.tg_id, mono_enc, payload.role)


@router.put("/users/me/token", response_model=schemas.UserOut)
def update_my_token(payload: schemas.UserTokenUpdate, actor: Actor = Depends(get_actor),
                    db: Session = Depends(get_db)):
    """Mini App: set your own Monobank token (encrypted at rest)."""
    if actor.kind != "user":
        raise HTTPException(status_code=403, detail="Mini App only")
    return crud.update_user_token(db, actor.user.tg_id, security.encrypt_secret(payload.mono_token))


@router.delete("/families/{family_id}/users/{user_id}")
def remove_user(family_id: int, user_id: int, _: None = Depends(require_family_admin),
                db: Session = Depends(get_db)):
    crud.remove_user(db, family_id, user_id)
