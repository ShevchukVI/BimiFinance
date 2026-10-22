"""Analytics for any month + monthly category budgets."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.core.deps import require_family
from app.database import get_db
from app.services import analytics as A

router = APIRouter(tags=["analytics"])


class BudgetIn(BaseModel):
    amount: Optional[float] = None  # null / 0 → remove the budget


class BudgetItem(BaseModel):
    category_id: int
    amount: Optional[float] = None


class BudgetsBulk(BaseModel):
    items: List[BudgetItem]


def _month(value: Optional[str]):
    try:
        return A.parse_month(value)
    except ValueError:
        raise HTTPException(400, f"Невірний місяць: {value}")


def _category(db: Session, fid: int, cid: int) -> models.Category:
    c = db.get(models.Category, cid)
    if not c or c.family_id != fid:
        raise HTTPException(404, "Категорію не знайдено")
    if c.type != "expense":
        raise HTTPException(400, "Бюджет можна задати лише для витрат")
    return c


def _set_budget(db: Session, fid: int, cid: int, amount: Optional[float]):
    _category(db, fid, cid)
    b = db.query(models.Budget).filter(models.Budget.family_id == fid, models.Budget.category_id == cid).first()
    if not amount or amount <= 0:
        if b:
            db.delete(b)
        return
    if amount > 10_000_000:
        raise HTTPException(400, "Завелика сума")
    if b:
        b.amount = round(amount, 2)
    else:
        db.add(models.Budget(family_id=fid, category_id=cid, amount=round(amount, 2)))


@router.get("/families/{family_id}/analytics")
def get_analytics(family_id: int, month: Optional[str] = None, _: None = Depends(require_family),
                  db: Session = Depends(get_db)):
    return A.month_analytics(db, family_id, _month(month))


@router.get("/families/{family_id}/budgets")
def get_budgets(family_id: int, month: Optional[str] = None, _: None = Depends(require_family),
                db: Session = Depends(get_db)):
    return A.budgets_status(db, family_id, _month(month))


@router.get("/families/{family_id}/budgets/suggest")
def suggest(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    return A.suggest_budgets(db, family_id)


@router.put("/families/{family_id}/budgets/{category_id}")
def put_budget(family_id: int, category_id: int, payload: BudgetIn, _: None = Depends(require_family),
               db: Session = Depends(get_db)):
    _set_budget(db, family_id, category_id, payload.amount)
    db.commit()
    return A.budgets_status(db, family_id, A.parse_month(None))


@router.post("/families/{family_id}/budgets/bulk")
def bulk_budgets(family_id: int, payload: BudgetsBulk, _: None = Depends(require_family), db: Session = Depends(get_db)):
    for it in payload.items:
        _set_budget(db, family_id, it.category_id, it.amount)
    db.commit()
    return A.budgets_status(db, family_id, A.parse_month(None))
