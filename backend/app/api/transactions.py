from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.core.deps import Actor, check_family_membership, get_actor, require_family
from app.database import get_db
from app.services.obligations import auto_link

router = APIRouter(tags=["transactions"])


@router.get("/families/{family_id}/transactions", response_model=list[schemas.TransactionOut])
def get_transactions(family_id: int, skip: int = 0, limit: int = 100, month: str | None = None,
                     category_id: int | None = None, type: str | None = None,
                     _: None = Depends(require_family), db: Session = Depends(get_db)):
    if month is None and category_id is None and type is None:
        return crud.get_transactions(db, family_id, skip=skip, limit=limit)
    q = db.query(models.Transaction).filter(models.Transaction.family_id == family_id)
    if month:
        from app.services.analytics import parse_month
        from app.services.housing import month_end
        try:
            m = parse_month(month)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month")
        q = q.filter(models.Transaction.date >= m, models.Transaction.date <= month_end(m))
    if category_id is not None:
        q = q.filter(models.Transaction.category_id == category_id)
    if type:
        q = q.filter(models.Transaction.type == type)
    return (q.order_by(models.Transaction.date.desc(), models.Transaction.id.desc())
            .offset(skip).limit(min(limit, 500)).all())


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
    obj = crud.create_transaction(db, family_id, user_id, tx.category_id, tx.amount, tx.type, tx.title,
                                  tx.note, tx.account, tx.date, tx.mono_id,
                                  currency=tx.currency, jar_id=tx.jar_id)
    # credit / subscription / housing payment recognised by its bank description → linked automatically
    if auto_link(db, obj):
        db.refresh(obj)
    return obj


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
                                tx.to_account, mono_id=tx.mono_id, currency=tx.currency)
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
    updated = crud.update_transaction(db, tx_id, payload.model_dump(exclude_unset=True))
    _sync_housing_payments(db, updated)
    return updated


def _sync_housing_payments(db: Session, tx) -> None:
    """A housing payment linked to a transaction mirrors its amount and date."""
    if tx is None:
        return
    pays = db.query(models.UtilityPayment).filter(models.UtilityPayment.transaction_id == tx.id).all()
    for p in pays:
        p.amount, p.date = tx.amount, tx.date
    if pays:
        db.commit()
        db.refresh(tx)


@router.put("/transactions/by-mono/{mono_id}", response_model=schemas.TransactionOut)
def update_tx_by_mono(mono_id: str, payload: schemas.TransactionUpdate, actor: Actor = Depends(get_actor),
                      db: Session = Depends(get_db)):
    tx = crud.get_tx_by_mono(db, mono_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if actor.kind == "user":
        check_family_membership(db, actor, tx.family_id)
    updated = crud.update_tx_by_mono(db, mono_id, payload.model_dump(exclude_unset=True))
    _sync_housing_payments(db, updated)
    return updated


@router.delete("/transactions/{tx_id}")
def delete_transaction(tx_id: int, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    tx = crud.get_transaction_by_id(db, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if actor.kind == "user":
        check_family_membership(db, actor, tx.family_id)
    # the housing payment *is* this transaction — remove it too, otherwise it keeps counting
    db.query(models.UtilityPayment).filter(models.UtilityPayment.transaction_id == tx_id).delete(synchronize_session=False)
    db.commit()
    crud.delete_transaction(db, tx_id)
