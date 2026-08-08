from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import crud, schemas
from app.core.deps import Actor, get_actor, require_family
from app.database import get_db

router = APIRouter(tags=["categories"])


@router.get("/families/{family_id}/categories", response_model=list[schemas.CategoryOut])
def get_categories(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    return crud.get_categories(db, family_id)


@router.post("/categories", response_model=schemas.CategoryOut)
def create_category(cat: schemas.CategoryCreate, actor: Actor = Depends(get_actor),
                    db: Session = Depends(get_db)):
    require_family(cat.family_id, actor)
    return crud.create_category(db, cat.family_id, cat.icon, cat.name, cat.color, cat.type)
