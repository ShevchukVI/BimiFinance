"""Credits, installments («оплата частинами») and subscriptions + linking transactions to them.

A payment of an obligation is an ordinary finance transaction with `obligation_id` set.
A payment of a housing service is a `utility_payments` row pointing to the transaction.
Matching is conservative: a bank description pattern must match AND (for obligations)
the amount must be within 5 % — so the same «Apple 44 ₴» charges split by due day.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app import models
from app.services.housing import add_months, today_kyiv

PERIOD_MONTHS = {"month": 1, "year": 12}
KIND_ICON = {"installment": "🧾", "loan": "🏦", "subscription": "🔁"}
CREDIT_KINDS = ("installment", "loan")


def _at_day(d: date, day: Optional[int]) -> date:
    if not day:
        return d
    return d.replace(day=min(day, calendar.monthrange(d.year, d.month)[1]))


def first_due(ob, today: Optional[date] = None) -> date:
    if ob.first_due:
        return ob.first_due
    today = today or today_kyiv()
    d = _at_day(today, ob.due_day)
    return d if d >= today else _at_day(add_months(today.replace(day=1), 1), ob.due_day)


def schedule(ob, until: date, today: Optional[date] = None) -> list[date]:
    step = PERIOD_MONTHS.get(ob.period or "month", 1)
    start = first_due(ob, today)
    out, i = [], 0
    while True:
        d = _at_day(add_months(start.replace(day=1), i * step), ob.due_day or start.day)
        if d > until or (ob.end_date and d > ob.end_date) or (ob.payments_total and i >= ob.payments_total):
            break
        out.append(d)
        i += 1
        if i > 600:
            break
    return out


def status(ob, linked: list, today: Optional[date] = None) -> dict:
    """Progress and the next payment. `linked` = transactions with obligation_id = ob.id."""
    today = today or today_kyiv()
    linked = sorted(linked, key=lambda t: (t.date, t.id))
    last = linked[-1] if linked else None
    res = {"paid_count": None, "payments_total": ob.payments_total, "remaining_count": None,
           "remaining_amount": None, "next_due": None, "last_date": str(last.date) if last else None,
           "last_amount": last.amount if last else None, "end": None, "status": "upcoming",
           "monthly": round(ob.amount / PERIOD_MONTHS.get(ob.period or "month", 1), 2), "linked_count": len(linked)}
    if ob.kind in CREDIT_KINDS:
        far = ob.end_date or date(today.year + 40, 12, 31)
        sched = schedule(ob, far, today)
        total = ob.payments_total or (len(sched) if ob.end_date else None)
        paid = (ob.paid_before or 0) + len(linked)
        res["paid_count"] = paid
        res["payments_total"] = total
        if total:
            res["remaining_count"] = max(total - paid, 0)
            res["remaining_amount"] = round(max(total - paid, 0) * ob.amount, 2)
            if len(sched) >= total:
                res["end"] = str(sched[total - 1])
        nxt = sched[paid] if paid < len(sched) else None
        if total and paid >= total:
            res["status"], nxt = "finished", None
        elif nxt is not None and nxt < today:
            res["status"] = "overdue"
        elif nxt is not None and (nxt - today).days <= 3:
            res["status"] = "due_soon"
        res["next_due"] = str(nxt) if nxt else None
        return res
    # subscription: next charge = the due day after the last seen charge
    step = PERIOD_MONTHS.get(ob.period or "month", 1)
    if ob.end_date and ob.end_date < today:
        res["status"] = "finished"
        return res
    if last is not None:
        nxt = _at_day(add_months(last.date.replace(day=1), step), ob.due_day or last.date.day)
        if nxt <= last.date or (nxt - last.date).days <= 5:
            # charged on/after the due day, or a few days early (31st for the 1st) → that cycle is paid
            nxt = _at_day(add_months(nxt.replace(day=1), step), ob.due_day or last.date.day)
        if nxt < today - timedelta(days=10):
            res["status"] = "stale"  # no charge seen for a cycle — cancelled or paid elsewhere
            while nxt < today:
                nxt = _at_day(add_months(nxt.replace(day=1), step), ob.due_day or nxt.day)
        elif nxt < today:
            res["status"] = "missing"  # expected a few days ago, no charge linked yet
            res["expected"] = str(nxt)
            nxt = _at_day(add_months(nxt.replace(day=1), step), ob.due_day or nxt.day)
        elif 0 <= (nxt - today).days <= 3:
            res["status"] = "due_soon"
        elif nxt > today:
            res["status"] = "charged"  # this cycle is already paid
    else:
        nxt = next((d for d in schedule(ob, add_months(today, 13), today) if d >= today), None)
        if nxt is not None and (nxt - today).days <= 3:
            res["status"] = "due_soon"
    res["next_due"] = str(nxt) if nxt else None
    return res


# ---------------------------------------------------------------- matching

def _patterns(raw: Optional[str]) -> list[str]:
    return [p.strip().lower() for p in re.split(r"[|,;]", raw or "") if p.strip()]


def text_matches(pattern: Optional[str], title: str) -> bool:
    pats = _patterns(pattern)
    t = (title or "").lower()
    return bool(pats) and any(p in t for p in pats)


def obligation_score(ob, tx) -> Optional[float]:
    """Higher is better; None = not a match."""
    if not ob.is_active or tx.type != "Витрати" or tx.jar_id is not None:
        return None
    if (tx.currency or "UAH") != (ob.currency or "UAH") or not text_matches(ob.match_pattern, tx.title):
        return None
    if abs(tx.amount - ob.amount) > max(ob.amount * 0.05, 2):
        return None
    if ob.end_date and tx.date > ob.end_date + timedelta(days=10):
        return None
    if ob.first_due and tx.date < ob.first_due - timedelta(days=10):
        return None
    score = 100.0
    if ob.due_day:
        dd = abs(tx.date.day - ob.due_day)
        score -= min(dd, 31 - dd)
    return score


def best_obligation(obligations: Iterable, tx):
    scored = [(obligation_score(o, tx), o) for o in obligations]
    scored = [(s, o) for s, o in scored if s is not None]
    return max(scored, key=lambda x: x[0])[1] if scored else None


def provider_for(providers: Iterable, tx):
    if tx.type != "Витрати" or tx.jar_id is not None:
        return None
    hits = [p for p in providers if p.is_active and text_matches(p.match_pattern, tx.title)]
    return hits[0] if len(hits) == 1 else None


def linked_tx_ids(db: Session, family_id: int) -> set[int]:
    """Transactions already used as a housing payment."""
    return {r[0] for r in db.query(models.UtilityPayment.transaction_id).filter(
        models.UtilityPayment.family_id == family_id, models.UtilityPayment.transaction_id.isnot(None))}


def _is_pending(db: Session, tx) -> bool:
    cat = db.get(models.Category, tx.category_id) if tx.category_id else None
    return cat is not None and "Очікує" in cat.name


def _clean_title(title: str) -> str:
    return (title or "").replace("❓ ", "").replace(" (нерозібрано)", "").replace(" (не розібрано)", "")


def housing_category(db: Session, family_id: int, service: str) -> Optional[int]:
    hints = {"rent": ("Оренда",), "mortgage": ("Кредит", "Оренда"), "internet": ("Інтернет", "Зв'язок")}
    cats = [c for c in db.query(models.Category).filter(models.Category.family_id == family_id,
                                                         models.Category.type == "expense") if "Очікує" not in c.name]
    for hint in hints.get(service, ()) + ("Комуналка", "Дім", "Інше"):
        c = next((c for c in cats if hint.lower() in c.name.lower()), None)
        if c:
            return c.id
    return cats[0].id if cats else None


def link_obligation(db: Session, tx, ob) -> None:
    tx.obligation_id = ob.id
    if ob.category_id and _is_pending(db, tx):
        tx.category_id = ob.category_id
        tx.title = _clean_title(tx.title)


def link_provider(db: Session, tx, provider, note: str = "") -> models.UtilityPayment:
    pay = models.UtilityPayment(family_id=tx.family_id, provider_id=provider.id, date=tx.date, amount=tx.amount,
                                user_id=tx.user_id, note=note, transaction_id=tx.id)
    db.add(pay)
    if _is_pending(db, tx):
        cat = housing_category(db, tx.family_id, provider.service)
        if cat:
            tx.category_id = cat
            tx.title = _clean_title(tx.title)
    return pay


def unlink(db: Session, tx) -> dict:
    was = {"obligation_id": tx.obligation_id, "payments": 0}
    tx.obligation_id = None
    for p in db.query(models.UtilityPayment).filter(models.UtilityPayment.transaction_id == tx.id).all():
        db.delete(p)
        was["payments"] += 1
    for l in db.query(models.VehicleLog).filter(models.VehicleLog.transaction_id == tx.id).all():
        db.delete(l)  # the car journal entry *is* this operation
        was["vehicle_logs"] = was.get("vehicle_logs", 0) + 1
    return was


def auto_link(db: Session, tx) -> Optional[str]:
    """Called for every new transaction (incl. Monobank webhooks). Never raises."""
    try:
        from app.services.mono_jars import classify  # own Monobank jar → goal history, not spending
        jar_id = classify(db, tx)
        if jar_id:
            db.commit()
            return f"jar:{jar_id}"
        if tx.type != "Витрати" or tx.jar_id is not None or tx.obligation_id:
            return None
        obs = db.query(models.Obligation).filter(models.Obligation.family_id == tx.family_id,
                                                 models.Obligation.is_active.is_(True)).all()
        ob = best_obligation(obs, tx)
        if ob is not None:
            link_obligation(db, tx, ob)
            db.commit()
            return f"obligation:{ob.id}"
        provs = db.query(models.UtilityProvider).filter(models.UtilityProvider.family_id == tx.family_id,
                                                        models.UtilityProvider.match_pattern != "").all()
        p = provider_for(provs, tx)
        if p is not None and tx.id not in linked_tx_ids(db, tx.family_id) and not _has_manual_payment(db, p, tx):
            link_provider(db, tx, p, note="Автоматично з банку")
            db.commit()
            return f"provider:{p.id}"
    except Exception:  # linking is a convenience — never break transaction creation
        db.rollback()
    return None


def _has_manual_payment(db: Session, provider, tx) -> bool:
    """Payment already recorded by hand (same amount ±1 ₴, ±3 days) — don't count it twice."""
    return db.query(models.UtilityPayment).filter(
        models.UtilityPayment.provider_id == provider.id,
        models.UtilityPayment.date.between(tx.date - timedelta(days=3), tx.date + timedelta(days=3)),
        models.UtilityPayment.amount.between(tx.amount - 1, tx.amount + 1)).first() is not None


def suggestions(db: Session, family_id: int, days: int = 180, today: Optional[date] = None) -> dict:
    """Unlinked recent transactions that look like payments: {"obligations": {id: [tx]}, "providers": {id: [tx]}}."""
    today = today or today_kyiv()
    obs = db.query(models.Obligation).filter(models.Obligation.family_id == family_id,
                                             models.Obligation.is_active.is_(True)).all()
    provs = db.query(models.UtilityProvider).filter(models.UtilityProvider.family_id == family_id,
                                                    models.UtilityProvider.is_active.is_(True)).all()
    used = linked_tx_ids(db, family_id)
    txs = (db.query(models.Transaction).filter(models.Transaction.family_id == family_id,
                                               models.Transaction.type == "Витрати",
                                               models.Transaction.obligation_id.is_(None),
                                               models.Transaction.jar_id.is_(None),
                                               models.Transaction.date >= today - timedelta(days=days))
           .order_by(models.Transaction.date.desc()).all())
    utility_cats = {c.id for c in db.query(models.Category).filter(models.Category.family_id == family_id)
                    if any(h in c.name for h in ("Комунал", "Оренд"))}
    out = {"obligations": {}, "providers": {}, "unassigned": []}
    for tx in txs:
        if tx.id in used:
            continue
        ob = best_obligation(obs, tx)
        if ob is not None:
            out["obligations"].setdefault(ob.id, []).append(tx)
            continue
        p = provider_for(provs, tx)
        if p is not None:
            out["providers"].setdefault(p.id, []).append(tx)
        elif tx.category_id in utility_cats and provs:
            out["unassigned"].append(tx)  # utilities/rent expense that is not tied to a service
    return out


def backfill(db: Session, family_id: int) -> int:
    """Link every obligation suggestion (amount-checked, safe). Housing ones stay suggestions."""
    sug = suggestions(db, family_id, days=3650)
    n = 0
    for ob_id, txs in sug["obligations"].items():
        ob = db.get(models.Obligation, ob_id)
        for tx in txs:
            link_obligation(db, tx, ob)
            n += 1
    db.flush()
    return n
