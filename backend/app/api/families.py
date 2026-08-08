from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.core.deps import Actor, get_actor, require_family, require_family_admin
from app.database import get_db

router = APIRouter(prefix="/families", tags=["families"])


@router.get("", response_model=list[schemas.FamilyOut])
def get_families(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    """Bot: all families. Mini App: only the authenticated user's family."""
    if actor.kind == "bot":
        return crud.get_families(db)
    family = crud.get_family_by_id(db, actor.family_id)
    return [family] if family else []


@router.get("/by-invite/{invite_code}", response_model=schemas.FamilyOut)
def get_family_by_invite(invite_code: str, db: Session = Depends(get_db)):
    """Public onboarding: the invite code is the secret."""
    family = crud.get_family_by_invite(db, invite_code)
    if not family:
        raise HTTPException(status_code=404, detail="Invite not found")
    return family


@router.post("", response_model=schemas.FamilyOut)
def create_family(family: schemas.FamilyCreate, db: Session = Depends(get_db)):
    """Public onboarding: creates the family; the first user becomes admin."""
    return crud.create_family(db, family.name)


@router.post("/{family_id}/regenerate-invite", response_model=schemas.FamilyOut)
def regenerate_invite(family_id: int, _: None = Depends(require_family_admin), db: Session = Depends(get_db)):
    return crud.regenerate_invite(db, family_id)


@router.get("/{family_id}/stats", response_model=schemas.FamilyStatsOut)
def get_family_stats(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    return crud.get_family_stats(db, family_id)


@router.get("/{family_id}/users", response_model=list[schemas.UserOut])
def get_users(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    return crud.get_users(db, family_id)
