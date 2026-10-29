"""«Розібрати» + «Bimi пропонує»: категорії для нерозібраних операцій, по одній або групою."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import crud, models
from app.api.transactions import _sync_housing_payments, _sync_vehicle_log
from app.core.deps import require_family
from app.database import get_db
from app.services import smart

router = APIRouter(tags=["inbox"])


@router.get("/families/{family_id}/inbox/suggestions")
def inbox_suggestions(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    out = smart.suggestions(db, family_id)
    fam = db.get(models.Family, family_id)
    since = date.today() - timedelta(days=7)
    out["smart_auto"] = bool(fam.smart_auto)
    out["auto_recent"] = db.query(models.Transaction).filter(models.Transaction.family_id == family_id,
                                                             models.Transaction.auto_category.is_(True),
                                                             models.Transaction.date >= since).count()
    return out


class RejectIn(BaseModel):
    title: str
    category_id: int


@router.post("/families/{family_id}/inbox/reject")
def reject(family_id: int, payload: RejectIn, _: None = Depends(require_family), db: Session = Depends(get_db)):
    """«Ні»: this place is not this category — Bimi stops offering it (and never applies it by itself)."""
    if not db.query(models.Category).filter(models.Category.id == payload.category_id,
                                            models.Category.family_id == family_id).first():
        raise HTTPException(404, "Категорію не знайдено")
    smart.reject(db, family_id, payload.title, payload.category_id)
    db.commit()
    return {"ok": True}


class SmartIn(BaseModel):
    smart_auto: bool


@router.put("/families/{family_id}/smart")
def set_smart(family_id: int, payload: SmartIn, _: None = Depends(require_family), db: Session = Depends(get_db)):
    fam = db.get(models.Family, family_id)
    fam.smart_auto = payload.smart_auto
    db.commit()
    return {"smart_auto": fam.smart_auto}


@router.get("/families/{family_id}/transactions/{tx_id}/suggest")
def suggest_one(family_id: int, tx_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    """For the bot: the category to offer first on a new bank operation."""
    tx = db.query(models.Transaction).filter(models.Transaction.id == tx_id, models.Transaction.family_id == family_id).first()
    if not tx:
        raise HTTPException(404, "Транзакцію не знайдено")
    s = smart.Brain(db, family_id).suggest(tx)
    if s and s.get("refund"):
        s = None  # shortcut: the bot keyboard has no ↩️ refund option yet, so it gets no hint for these
    if s:
        c = db.get(models.Category, s["category_id"])
        s["category_name"] = c.name if c else ""
    return s or {}


class ApplyItem(BaseModel):
    transaction_id: int
    category_id: int
    refund: bool = False  # ↩️ incoming money filed under the expense category it lowers


class ApplyIn(BaseModel):
    items: list[ApplyItem]


@router.post("/families/{family_id}/inbox/apply")
def apply(family_id: int, payload: ApplyIn, _: None = Depends(require_family), db: Session = Depends(get_db)):
    """Accept suggestions. Only operations still waiting in «Очікує» change — a category set by hand is never overwritten."""
    cats = {c.id: c for c in db.query(models.Category).filter(models.Category.family_id == family_id)}
    pending = {t.id for t in smart.pending_query(db, family_id).filter(
        models.Transaction.id.in_([i.transaction_id for i in payload.items]))}
    done = 0
    for it in payload.items:
        c = cats.get(it.category_id)
        if it.transaction_id not in pending or c is None or any(s in c.name for s in smart.SYSTEM):
            continue
        tx = db.get(models.Transaction, it.transaction_id)
        refund = it.refund and tx.type != "Витрати"
        if c.type != ("expense" if tx.type == "Витрати" or refund else "income") and "Переказ" not in c.name:
            continue
        updated = crud.update_transaction(db, tx.id, {"category_id": c.id, "refund": refund})
        _sync_housing_payments(db, updated)
        _sync_vehicle_log(db, updated)
        done += 1
    return {"applied": done, "pending": smart.pending_query(db, family_id).count()}
