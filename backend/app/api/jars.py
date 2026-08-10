from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
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


@router.post("/jars/{jar_id}/topup", response_model=schemas.JarOut)
def topup_jar(jar_id: int, payload: schemas.JarTopUp, actor: Actor = Depends(get_actor),
              db: Session = Depends(get_db)):
    jar = crud.get_jar_by_id(db, jar_id)
    if not jar:
        raise HTTPException(status_code=404, detail="Jar not found")
    check_family_membership(db, actor, jar.family_id)
    user_id = actor.user_id if actor.kind == "user" else None
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
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
    user_id = actor.user_id if actor.kind == "user" else None
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    updated = crud.withdraw_jar(db, jar_id, payload.amount, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Jar not found")
    return updated
