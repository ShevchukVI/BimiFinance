from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.core.deps import Actor, get_actor, require_family
from app.database import get_db

router = APIRouter(tags=["jars"])


@router.get("/families/{family_id}/jars", response_model=list[schemas.JarOut])
def get_jars(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    return crud.get_jars(db, family_id)


@router.post("/jars", response_model=schemas.JarOut)
def create_jar(jar: schemas.JarCreate, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    require_family(jar.family_id, actor)
    return crud.create_jar(db, jar.family_id, jar.name, jar.goal)


@router.post("/jars/{jar_id}/topup", response_model=schemas.JarOut)
def topup_jar(jar_id: int, payload: schemas.JarTopUp, actor: Actor = Depends(get_actor),
              db: Session = Depends(get_db)):
    jar = crud.get_jar_by_id(db, jar_id)
    if not jar:
        raise HTTPException(status_code=404, detail="Jar not found")
    if actor.kind == "user":
        require_family(jar.family_id, actor)
    updated = crud.topup_jar(db, jar_id, payload.amount)
    if not updated:
        raise HTTPException(status_code=404, detail="Jar not found")
    return updated
