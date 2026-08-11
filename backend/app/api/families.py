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


@router.get("/{family_id}/members", response_model=list[schemas.FamilyMemberOut])
def list_members(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    """Список учасників сім'ї (доступний будь-якому члену сім'ї)."""
    return crud.get_family_members(db, family_id)


@router.patch("/{family_id}/members/{user_id}", response_model=schemas.FamilyMemberOut)
def change_member_role(family_id: int, user_id: int, payload: schemas.MemberRoleUpdate,
                       _: None = Depends(require_family_admin), db: Session = Depends(get_db)):
    """Зміна ролі учасника (admin ↔ member). Лише для адміна."""
    member, err = crud.set_member_role(db, family_id, user_id, payload.role)
    if err == "Member not found":
        raise HTTPException(status_code=404, detail=err)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return member


@router.delete("/{family_id}/members/{user_id}", response_model=schemas.FamilyMemberOut)
def kick_member(family_id: int, user_id: int, actor: Actor = Depends(require_user),
                _: None = Depends(require_family_admin), db: Session = Depends(get_db)):
    """Вигнати учасника. Лише для адміна. Не можна вигнати себе чи останнього адміна."""
    member, err = crud.kick_member(db, family_id, user_id, actor.user_id)
    if err == "Member not found":
        raise HTTPException(status_code=404, detail=err)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return member


@router.delete("/{family_id}/leave", response_model=schemas.FamilyMemberOut)
def leave_family(family_id: int, actor: Actor = Depends(require_user),
                 _: None = Depends(require_family), db: Session = Depends(get_db)):
    """Поточний користувач виходить з сім'ї."""
    member, err = crud.leave_family(db, family_id, actor.user_id)
    if err == "Not a member":
        raise HTTPException(status_code=404, detail=err)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return member
