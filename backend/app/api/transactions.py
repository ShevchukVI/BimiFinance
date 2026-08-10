from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.core.deps import Actor, check_family_membership, get_actor, require_family
from app.database import get_db

router = APIRouter(tags=["transactions"])


@router.get("/families/{family_id}/transactions", response_model=list[schemas.TransactionOut])
def get_transactions(family_id: int, skip: int = 0, limit: int = 100,
                     _: None = Depends(require_family), db: Session = Depends(get_db)):
    return crud.get_transactions(db, family_id, skip=skip, limit=limit)


@router.get("/families/{family_id}/pending", response_model=list[schemas.TransactionOut])
def get_pending_transactions(family_id: int, _: None = Depends(require_family),
                             db: Session = Depends(get_db)):
    """Inbox Zero: транзакції в службовій категорії 'Очікує'."""
    return crud.get_pending_transactions(db, family_id)


@router.post("/transactions", response_model=schemas.TransactionOut)
def create_transaction(tx: schemas.TransactionCreate, actor: Actor = Depends(get_actor),
                       db: Session = Depends(get_db)):
    if actor.kind == "bot":
        family_id, user_id = tx.family_id, tx.user_id
    else:
        check_family_membership(db, actor, tx.family_id)
        family_id, user_id = actor.family_id, actor.user_id  # family_id never trusted from body
    return crud.create_transaction(db, family_id, user_id, tx.category_id, tx.amount, tx.type, tx.title,
                                   tx.note, tx.account, tx.date, tx.mono_id)


@router.post("/transactions/transfer", response_model=list[schemas.TransactionOut])
def create_transfer(tx: schemas.TransferCreate, actor: Actor = Depends(get_actor),
                    db: Session = Depends(get_db)):
    """Переказ Cash ↔ Bank. Пара зігнованих транзакцій типу 'Переказ' — не дохід/витрата."""
    if actor.kind == "bot":
        family_id, user_id = tx.family_id, tx.user_id
    else:
        check_family_membership(db, actor, tx.family_id)
        family_id, user_id = actor.family_id, actor.user_id
    if tx.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if tx.from_account == tx.to_account:
        raise HTTPException(status_code=400, detail="Accounts must differ")
    pair = crud.create_transfer(db, family_id, user_id, tx.amount, tx.from_account,
                                tx.to_account, mono_id=tx.mono_id)
    if pair is None:  # дубль за mono_id
        raise HTTPException(status_code=409, detail="Transfer already exists")
    return pair


@router.put("/transactions/{tx_id}", response_model=schemas.TransactionOut)
def update_transaction(tx_id: int, payload: schemas.TransactionUpdate, actor: Actor = Depends(get_actor),
                       db: Session = Depends(get_db)):
    tx = crud.get_transaction_by_id(db, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if actor.kind == "user":
        check_family_membership(db, actor, tx.family_id)
    return crud.update_transaction(db, tx_id, payload.model_dump(exclude_unset=True))


@router.put("/transactions/by-mono/{mono_id}", response_model=schemas.TransactionOut)
def update_tx_by_mono(mono_id: str, payload: schemas.TransactionUpdate, actor: Actor = Depends(get_actor),
                      db: Session = Depends(get_db)):
    tx = crud.get_tx_by_mono(db, mono_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if actor.kind == "user":
        check_family_membership(db, actor, tx.family_id)
    return crud.update_tx_by_mono(db, mono_id, payload.model_dump(exclude_unset=True))


@router.delete("/transactions/{tx_id}")
def delete_transaction(tx_id: int, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    tx = crud.get_transaction_by_id(db, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if actor.kind == "user":
        check_family_membership(db, actor, tx.family_id)
    crud.delete_transaction(db, tx_id)
