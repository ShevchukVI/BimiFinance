from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.core.deps import Actor, get_actor, require_admin_in_family, require_family, require_family_admin, require_user
from app.database import get_db

router = APIRouter(prefix="/families", tags=["families"])


@router.get("", response_model=list[schemas.FamilyOut])
def get_families(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    if actor.kind == "bot":
        return crud.get_families(db)
    rows = crud.get_user_families(db, actor.user_id)
    rows.sort(key=lambda item: (0 if actor.family_id == item[0].id else 1, item[0].id))
    return [fam for fam, _ in rows]


@router.get("/by-invite/{invite_code}", response_model=schemas.FamilyOut)
def get_family_by_invite(invite_code: str, db: Session = Depends(get_db)):
    family = crud.get_family_by_invite(db, invite_code)
    if not family:
        raise HTTPException(status_code=404, detail="Invite not found")
    return family


@router.post("", response_model=schemas.FamilyOut)
def create_family(family: schemas.FamilyCreate, db: Session = Depends(get_db)):
    return crud.create_family(db, family.name)


@router.post("/invite", response_model=schemas.FamilyOut)
def generate_invite(family_id: int = Depends(require_admin_in_family), db: Session = Depends(get_db)):
    family = crud.regenerate_invite(db, family_id)
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")
    return family


@router.post("/join", response_model=schemas.FamilyOut)
def join_family(payload: schemas.JoinFamilyRequest, actor: Actor = Depends(require_user),
                db: Session = Depends(get_db)):
    family = crud.join_family_by_invite(db, actor.user, payload.invite_code)
    if not family:
        raise HTTPException(status_code=404, detail="Invalid invite code")
    return family


@router.post("/{family_id}/regenerate-invite", response_model=schemas.FamilyOut)
def regenerate_invite(family_id: int, _: None = Depends(require_family_admin), db: Session = Depends(get_db)):
    return crud.regenerate_invite(db, family_id)


@router.get("/{family_id}/stats", response_model=schemas.FamilyStatsOut)
def get_family_stats(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    return crud.get_family_stats(db, family_id)


@router.get("/{family_id}/users", response_model=list[schemas.UserOut])
def get_users(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    return crud.get_users(db, family_id)
