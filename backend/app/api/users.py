import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.core import security
from app.core.deps import Actor, check_family_admin, get_actor, require_family_admin, require_user
from app.database import get_db

router = APIRouter(tags=["users"])


@router.post("/users", response_model=schemas.UserOut)
def create_user(payload: schemas.UserCreate, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    check_family_admin(db, actor, payload.family_id)
    mono_enc = security.encrypt_secret(payload.mono_token) if payload.mono_token else None
    return crud.create_user_in_family(db, payload.family_id, payload.name, payload.tg_id, mono_enc, payload.role)


@router.put("/users/me/token", response_model=schemas.UserOut)
def update_my_token(payload: schemas.UserTokenUpdate, actor: Actor = Depends(require_user),
                    db: Session = Depends(get_db)):
    return crud.update_user_token(db, actor.user.tg_id, security.encrypt_secret(payload.mono_token))


@router.get("/users/me/families", response_model=list[schemas.FamilyMembershipOut])
def get_my_families(actor: Actor = Depends(require_user), db: Session = Depends(get_db)):
    rows = crud.get_user_families(db, actor.user_id)
    active_id = actor.user.current_active_family_id
    result = []
    for family, role in rows:
        result.append(schemas.FamilyMembershipOut(
            family_id=family.id, name=family.name, role=role, is_active=(family.id == active_id),
        ))
    result.sort(key=lambda m: (not m.is_active, m.family_id))
    return result


@router.patch("/users/me/active-family", response_model=schemas.UserOut)
def set_active_family(payload: schemas.SetActiveFamilyRequest, actor: Actor = Depends(require_user),
                      db: Session = Depends(get_db)):
    user = crud.set_active_family(db, actor.user_id, payload.family_id)
    if not user:
        raise HTTPException(status_code=403, detail="Not a member of this family")
    return user


@router.delete("/families/{family_id}/users/{user_id}")
def remove_user(family_id: int, user_id: int, _: None = Depends(require_family_admin),
                db: Session = Depends(get_db)):
    crud.remove_user(db, family_id, user_id)


@router.put("/users/me/tabs", response_model=schemas.UserOut)
def set_my_tab(payload: schemas.TabPrefsUpdate, actor: Actor = Depends(require_user), db: Session = Depends(get_db)):
    """Personal bottom bar: hide a section you don't use (or bring it back)."""
    user = actor.user
    try:
        prefs = json.loads(user.tab_prefs or "{}")
    except ValueError:
        prefs = {}
    if payload.show is None:
        prefs.pop(payload.tab, None)
    else:
        prefs[payload.tab] = payload.show
    user.tab_prefs = json.dumps(prefs) if prefs else None
    db.commit()
    db.refresh(user)
    return user
