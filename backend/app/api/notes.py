from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.core.deps import Actor, get_actor, require_family
from app.database import get_db

router = APIRouter(tags=["notes"])


@router.get("/families/{family_id}/notes", response_model=list[schemas.NoteOut])
def get_notes(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    return crud.get_notes(db, family_id)


@router.post("/notes", response_model=schemas.NoteOut)
def create_note(note: schemas.NoteCreate, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    require_family(note.family_id, actor)
    return crud.create_note(db, note.family_id, note.content)


@router.put("/notes/{note_id}", response_model=schemas.NoteOut)
def update_note(note_id: int, payload: schemas.NoteCreate, actor: Actor = Depends(get_actor),
                db: Session = Depends(get_db)):
    note = crud.get_note_by_id(db, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if actor.kind == "user":
        require_family(note.family_id, actor)
    return crud.update_note(db, note_id, payload.content)


@router.delete("/notes/{note_id}")
def delete_note(note_id: int, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    note = crud.get_note_by_id(db, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if actor.kind == "user":
        require_family(note.family_id, actor)
    crud.delete_note(db, note_id)
