from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.core.deps import Actor, check_family_membership, get_actor, require_family
from app.database import get_db

router = APIRouter(tags=["jars"])


@router.get("/families/{family_id}/jars", response_model=list[schemas.JarOut])
def get_jars(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    return crud.get_jars(db, family_id)


@router.post("/jars", response_model=schemas.JarOut)
def create_jar(jar: schemas.JarCreate, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    check_family_membership(db, actor, jar.family_id)
    return crud.create_jar(db, jar.family_id, jar.name, jar.goal, jar.currency)


def _jar_actor_user_id(db: Session, actor: Actor, family_id: int):
    """user_id для jar-операцій: для Mini App user — його id; для bot — перший учасник
    сім'ї (щоб кожна jar-транзакція мала атрибуцію і cash_by_user збігався з
    cash_by_currency)."""
    if actor.kind == "user":
        return actor.user_id
    mem = db.query(models.FamilyMember).filter(
        models.FamilyMember.family_id == family_id).order_by(models.FamilyMember.user_id).first()
    return mem.user_id if mem else None


@router.post("/jars/{jar_id}/topup", response_model=schemas.JarOut)
def topup_jar(jar_id: int, payload: schemas.JarTopUp, actor: Actor = Depends(get_actor),
              db: Session = Depends(get_db)):
    jar = crud.get_jar_by_id(db, jar_id)
    if not jar:
        raise HTTPException(status_code=404, detail="Jar not found")
    check_family_membership(db, actor, jar.family_id)
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    user_id = _jar_actor_user_id(db, actor, jar.family_id)
    updated = crud.topup_jar(db, jar_id, payload.amount, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Jar not found")
    return updated


@router.post("/jars/{jar_id}/withdraw", response_model=schemas.JarOut)
def withdraw_jar(jar_id: int, payload: schemas.JarTopUp, actor: Actor = Depends(get_actor),
                 db: Session = Depends(get_db)):
    """Зняття зі скарбнички (наприклад, дістали гроші на покупку)."""
    jar = crud.get_jar_by_id(db, jar_id)
    if not jar:
        raise HTTPException(status_code=404, detail="Jar not found")
    check_family_membership(db, actor, jar.family_id)
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    user_id = _jar_actor_user_id(db, actor, jar.family_id)
    updated = crud.withdraw_jar(db, jar_id, payload.amount, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Jar not found")
    return updated
