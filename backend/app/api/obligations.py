"""Credits / installments / subscriptions and linking transactions to them (or to housing services)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.deps import require_family
from app.database import get_db
from app.services import housing as H
from app.services import obligations as O

router = APIRouter(tags=["obligations"])

KINDS = {"installment", "loan", "subscription"}


class ObligationIn(BaseModel):
    kind: Optional[str] = None
    name: Optional[str] = None
    icon: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    period: Optional[str] = None
    due_day: Optional[int] = None
    first_due: Optional[str] = None
    payments_total: Optional[int] = None
    end_date: Optional[str] = None
    total_amount: Optional[float] = None
    paid_before: Optional[int] = None
    match_pattern: Optional[str] = None
    category_id: Optional[int] = None
    user_id: Optional[int] = None
    remind: Optional[bool] = None
    is_active: Optional[bool] = None
    note: Optional[str] = None
    link_suggested: bool = False  # link matching past transactions right away


class LinkIn(BaseModel):
    type: str  # obligation | provider
    id: int


def _d(v: Optional[str]) -> Optional[date]:
    if not v:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        raise HTTPException(400, f"Невірна дата: {v}")


def _ob(db: Session, fid: int, oid: int) -> models.Obligation:
    o = db.query(models.Obligation).filter(models.Obligation.id == oid, models.Obligation.family_id == fid).first()
    if not o:
        raise HTTPException(404, "Не знайдено")
    return o


def _tx(db: Session, fid: int, tx_id: int) -> models.Transaction:
    t = db.query(models.Transaction).filter(models.Transaction.id == tx_id, models.Transaction.family_id == fid).first()
    if not t:
        raise HTTPException(404, "Транзакцію не знайдено")
    return t


def _tx_brief(t) -> dict:
    return {"id": t.id, "date": str(t.date), "amount": t.amount, "title": t.title.replace("❓ ", ""), "account": t.account}


def ob_out(o: models.Obligation, linked: list, sug: list | None = None, today: Optional[date] = None) -> dict:
    return {"id": o.id, "kind": o.kind, "name": o.name, "icon": o.icon or O.KIND_ICON.get(o.kind, "🧾"),
            "amount": o.amount, "currency": o.currency, "period": o.period, "due_day": o.due_day,
            "first_due": str(o.first_due) if o.first_due else None, "payments_total": o.payments_total,
            "end_date": str(o.end_date) if o.end_date else None, "total_amount": o.total_amount,
            "paid_before": o.paid_before or 0, "match_pattern": o.match_pattern or "", "category_id": o.category_id,
            "user_id": o.user_id, "remind": o.remind, "is_active": o.is_active, "note": o.note or "",
            "state": O.status(o, linked, today), "suggested": [_tx_brief(t) for t in (sug or [])[:12]]}


def _linked_by_ob(db: Session, fid: int) -> dict:
    out: dict = {}
    for t in db.query(models.Transaction).filter(models.Transaction.family_id == fid,
                                                 models.Transaction.obligation_id.isnot(None)):
        out.setdefault(t.obligation_id, []).append(t)
    return out


def list_obligations(db: Session, fid: int, include_inactive: bool = False) -> dict:
    q = db.query(models.Obligation).filter(models.Obligation.family_id == fid)
    if not include_inactive:
        q = q.filter(models.Obligation.is_active.is_(True))
    obs = q.order_by(models.Obligation.kind, models.Obligation.id).all()
    linked = _linked_by_ob(db, fid)
    sug = O.suggestions(db, fid)["obligations"]
    items = [ob_out(o, linked.get(o.id, []), sug.get(o.id)) for o in obs]
    active = [i for i in items if i["is_active"] and i["state"]["status"] != "finished"]
    totals = {
        "credits_monthly": round(sum(i["state"]["monthly"] for i in active if i["kind"] in O.CREDIT_KINDS), 2),
        "subscriptions_monthly": round(sum(i["state"]["monthly"] for i in active if i["kind"] == "subscription"), 2),
        "remaining_total": round(sum(i["state"]["remaining_amount"] or 0 for i in active if i["kind"] in O.CREDIT_KINDS), 2),
        "suggested": sum(len(i["suggested"]) for i in items),
    }
    return {"items": items, "totals": totals}


@router.get("/families/{family_id}/obligations")
def get_obligations(family_id: int, include_inactive: bool = False, _: None = Depends(require_family),
                    db: Session = Depends(get_db)):
    return list_obligations(db, family_id, include_inactive)


def _apply(o: models.Obligation, data: dict, db: Session, fid: int):
    if "kind" in data and data["kind"] not in KINDS:
        raise HTTPException(400, "Невірний тип")
    if "period" in data and data["period"] not in O.PERIOD_MONTHS:
        raise HTTPException(400, "Невірний період")
    for k in ("first_due", "end_date"):
        if k in data:
            data[k] = _d(data[k])
    if data.get("due_day") is not None and not 1 <= data["due_day"] <= 31:
        raise HTTPException(400, "День платежу 1–31")
    if data.get("category_id"):
        c = db.get(models.Category, data["category_id"])
        if not c or c.family_id != fid:
            raise HTTPException(400, "Невірна категорія")
    for k, v in data.items():
        setattr(o, k, v)
    if o.first_due and not o.due_day:
        o.due_day = o.first_due.day


@router.post("/families/{family_id}/obligations")
def create_obligation(family_id: int, payload: ObligationIn, _: None = Depends(require_family),
                      db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    link = data.pop("link_suggested", False)
    if not (data.get("name") or "").strip() or not data.get("amount") or data["amount"] <= 0:
        raise HTTPException(400, "Потрібні назва і сума")
    o = models.Obligation(family_id=family_id, kind="installment", period="month", currency="UAH")
    _apply(o, data, db, family_id)
    if not o.icon:
        o.icon = O.KIND_ICON.get(o.kind, "🧾")
    db.add(o)
    db.flush()
    if link:
        for t in O.suggestions(db, family_id, days=3650)["obligations"].get(o.id, []):
            O.link_obligation(db, t, o)
    db.commit()
    return ob_out(o, _linked_by_ob(db, family_id).get(o.id, []))


@router.put("/families/{family_id}/obligations/{obligation_id}")
def update_obligation(family_id: int, obligation_id: int, payload: ObligationIn, _: None = Depends(require_family),
                      db: Session = Depends(get_db)):
    o = _ob(db, family_id, obligation_id)
    data = payload.model_dump(exclude_unset=True)
    data.pop("link_suggested", None)
    _apply(o, data, db, family_id)
    db.commit()
    return ob_out(o, _linked_by_ob(db, family_id).get(o.id, []))


@router.delete("/families/{family_id}/obligations/{obligation_id}")
def delete_obligation(family_id: int, obligation_id: int, _: None = Depends(require_family),
                      db: Session = Depends(get_db)):
    """Archive when payments are linked (history stays), delete otherwise."""
    o = _ob(db, family_id, obligation_id)
    has = db.query(models.Transaction).filter(models.Transaction.obligation_id == o.id).count()
    if has:
        o.is_active = False
    else:
        db.delete(o)
    db.commit()
    return {"archived": bool(has)}


@router.get("/families/{family_id}/obligations/{obligation_id}/transactions", response_model=list[schemas.TransactionOut])
def obligation_transactions(family_id: int, obligation_id: int, _: None = Depends(require_family),
                            db: Session = Depends(get_db)):
    _ob(db, family_id, obligation_id)
    return (db.query(models.Transaction).filter(models.Transaction.obligation_id == obligation_id)
            .order_by(models.Transaction.date.desc(), models.Transaction.id.desc()).all())


@router.post("/families/{family_id}/obligations/{obligation_id}/link-suggested")
def link_suggested(family_id: int, obligation_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    o = _ob(db, family_id, obligation_id)
    txs = O.suggestions(db, family_id, days=3650)["obligations"].get(o.id, [])
    for t in txs:
        O.link_obligation(db, t, o)
    db.commit()
    return {"linked": len(txs), "item": ob_out(o, _linked_by_ob(db, family_id).get(o.id, []))}


# ---------------------------------------------------------------- transaction ↔ obligation / housing service

def _current_link(db: Session, tx) -> Optional[dict]:
    if tx.obligation_id:
        o = db.get(models.Obligation, tx.obligation_id)
        if o:
            st = O.status(o, db.query(models.Transaction).filter(models.Transaction.obligation_id == o.id).all())
            return {"type": "obligation", "id": o.id, "name": o.name, "icon": o.icon or O.KIND_ICON.get(o.kind),
                    "kind": o.kind, "progress": (f"{st['paid_count']} з {st['payments_total']}"
                                                 if st.get("paid_count") is not None and st.get("payments_total") else None)}
    pay = db.query(models.UtilityPayment).filter(models.UtilityPayment.transaction_id == tx.id).first()
    if pay:
        p = db.get(models.UtilityProvider, pay.provider_id)
        return {"type": "provider", "id": p.id, "name": p.name, "icon": p.icon, "kind": p.service, "progress": None}
    return None


@router.get("/families/{family_id}/transactions/{tx_id}/link")
def get_link(family_id: int, tx_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    tx = _tx(db, family_id, tx_id)
    obs = db.query(models.Obligation).filter(models.Obligation.family_id == family_id,
                                             models.Obligation.is_active.is_(True)).all()
    provs = db.query(models.UtilityProvider).filter(models.UtilityProvider.family_id == family_id,
                                                    models.UtilityProvider.is_active.is_(True)).all()
    cands = []
    for o in obs:
        s = O.obligation_score(o, tx)
        near = abs(tx.amount - o.amount) <= max(o.amount * 0.05, 2)
        cands.append({"type": "obligation", "id": o.id, "name": o.name, "icon": o.icon or O.KIND_ICON.get(o.kind),
                      "kind": o.kind, "hint": f"{o.amount:g} ₴", "match": s is not None,
                      "score": (s or 0) + (20 if near else 0)})
    for p in provs:
        m = O.text_matches(p.match_pattern, tx.title)
        cands.append({"type": "provider", "id": p.id, "name": p.name, "icon": p.icon, "kind": p.service,
                      "hint": H.SERVICE_META.get(p.service, {}).get("label", ""), "match": m, "score": 60 if m else 0})
    cands.sort(key=lambda c: (-c["score"], c["type"], c["name"]))
    return {"current": _current_link(db, tx), "candidates": cands}


@router.post("/families/{family_id}/transactions/{tx_id}/link")
def set_link(family_id: int, tx_id: int, payload: LinkIn, _: None = Depends(require_family),
             db: Session = Depends(get_db)):
    tx = _tx(db, family_id, tx_id)
    if tx.type != "Витрати":
        raise HTTPException(400, "Пов'язати можна лише витрату")
    O.unlink(db, tx)
    if payload.type == "obligation":
        O.link_obligation(db, tx, _ob(db, family_id, payload.id))
    elif payload.type == "provider":
        p = db.query(models.UtilityProvider).filter(models.UtilityProvider.id == payload.id,
                                                    models.UtilityProvider.family_id == family_id).first()
        if not p:
            raise HTTPException(404, "Послугу не знайдено")
        O.link_provider(db, tx, p, note="Пов'язано з операції")
    else:
        raise HTTPException(400, "Невірний тип")
    db.commit()
    db.refresh(tx)
    return {"current": _current_link(db, tx), "transaction": schemas.TransactionOut.model_validate(tx).model_dump(mode="json")}


@router.delete("/families/{family_id}/transactions/{tx_id}/link")
def delete_link(family_id: int, tx_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    tx = _tx(db, family_id, tx_id)
    was = O.unlink(db, tx)
    db.commit()
    return was


@router.get("/families/{family_id}/link-suggestions")
def link_suggestions(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    """Housing: expenses that look like a service payment but are not linked yet."""
    s = O.suggestions(db, family_id)
    return {"providers": {str(k): [_tx_brief(t) for t in v[:20]] for k, v in s["providers"].items()},
            "unassigned": [_tx_brief(t) for t in s["unassigned"][:30]]}


# ---------------------------------------------------------------- upcoming payments (Home)

def upcoming(db: Session, fid: int, days: int = 10, today: Optional[date] = None) -> list[dict]:
    today = today or H.today_kyiv()
    horizon = today + timedelta(days=days)
    out = []
    for i in list_obligations(db, fid)["items"]:
        nd = _d(i["state"]["next_due"])
        past_ok = i["kind"] in O.CREDIT_KINDS  # an overdue credit stays on top; subscriptions only ahead
        if nd and nd <= horizon and (nd >= today or past_ok) and i["state"]["status"] not in ("finished", "charged"):
            prog = (f" · {i['state']['paid_count'] + 1} з {i['state']['payments_total']}"
                    if i["kind"] in O.CREDIT_KINDS and i["state"]["payments_total"] else "")
            out.append({"date": str(nd), "title": i["name"], "icon": i["icon"], "amount": i["amount"],
                        "currency": i["currency"], "kind": "obligation", "id": i["id"], "status": i["state"]["status"],
                        "sub": ("Підписка" if i["kind"] == "subscription" else "Платіж") + prog})
    try:
        from app.api.housing import build_overview  # local import: avoid a cycle at startup
        ov = build_overview(db, fid, today)
    except Exception:
        ov = None
    if ov and ov.get("profile") and ov["profile"]["mode"] != "off":
        for p in ov["providers"]:
            b = p["balance"]
            if p["service"] in H.FIXED_SERVICES:
                nc = b.get("next_charge")
                nd = _d(nc["due"]) if nc else None
                if nd and nd <= horizon:
                    out.append({"date": str(nd), "title": p["name"], "icon": p["icon"], "amount": nc["amount"], "currency": "UAH",
                                "kind": "housing", "id": p["id"], "status": "overdue" if nd < today else "upcoming", "sub": "Житло"})
            else:
                nd = _d(b.get("next_due"))
                if nd and nd <= horizon and (b.get("to_pay_now") or 0) > 1:
                    out.append({"date": str(nd), "title": p["name"], "icon": p["icon"], "amount": round(b["to_pay_now"]),
                                "currency": "UAH", "kind": "housing", "id": p["id"], "status": "upcoming", "sub": "Житло · ≈"})
    out.sort(key=lambda x: x["date"])
    return out


@router.get("/families/{family_id}/upcoming")
def get_upcoming(family_id: int, days: int = Query(10, ge=1, le=62), _: None = Depends(require_family),
                 db: Session = Depends(get_db)):
    return upcoming(db, family_id, days)


def obligation_reminders(db: Session, fid: int, today: date) -> list[tuple[str, str]]:
    """(key, text) for credit payments due tomorrow / today that are not paid yet."""
    msgs = []
    for i in list_obligations(db, fid)["items"]:
        if not i["remind"] or i["kind"] not in O.CREDIT_KINDS:
            continue
        nd = _d(i["state"]["next_due"])
        if not nd or i["state"]["status"] == "finished":
            continue
        days = (nd - today).days
        if days in (1, 0):
            prog = (f" (платіж {i['state']['paid_count'] + 1} з {i['state']['payments_total']})"
                    if i["state"]["payments_total"] else "")
            msgs.append((f"ob:{i['id']}:{nd}:{days}",
                         f"{i['icon']} {i['name']}: {i['amount']:.0f} ₴ — {'сьогодні' if days == 0 else 'завтра'}{prog}"))
    return msgs
