"""«Авто»: family cars, their journal (fills, service, washes…) and linking finance transactions to it."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import crud, models
from app.api.housing import _actor_user_id
from app.core.deps import Actor, get_actor, require_family
from app.database import get_db
from app.services import obligations as O
from app.services import vehicles as V

router = APIRouter(tags=["vehicles"])


class VehicleIn(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    plate: Optional[str] = None
    fuel: Optional[str] = None
    fuel2: Optional[str] = None
    tank_l: Optional[float] = None
    tank2_l: Optional[float] = None
    start_odometer: Optional[int] = None
    match_pattern: Optional[str] = None
    user_id: Optional[int] = None
    is_active: Optional[bool] = None
    note: Optional[str] = None


class LogIn(BaseModel):
    vehicle_id: Optional[int] = None
    kind: Optional[str] = None
    date: Optional[str] = None
    odometer: Optional[int] = None
    fuel: Optional[str] = None
    liters: Optional[float] = None
    price: Optional[float] = None
    full_tank: Optional[bool] = None
    amount: Optional[float] = None
    title: Optional[str] = None
    note: Optional[str] = None
    transaction_id: Optional[int] = None  # pay with an existing operation
    create_transaction: bool = False  # …or record a new expense in finances
    account: str = "Готівка"


def _d(v: Optional[str]) -> date:
    try:
        return date.fromisoformat(v[:10]) if v else V.today_kyiv()
    except ValueError:
        raise HTTPException(400, f"Невірна дата: {v}")


def _vehicle(db: Session, fid: int, vid: Optional[int]) -> models.Vehicle:
    v = db.query(models.Vehicle).filter(models.Vehicle.id == vid, models.Vehicle.family_id == fid).first()
    if not v:
        raise HTTPException(404, "Авто не знайдено")
    return v


def _log(db: Session, fid: int, lid: int) -> models.VehicleLog:
    l = db.query(models.VehicleLog).filter(models.VehicleLog.id == lid, models.VehicleLog.family_id == fid).first()
    if not l:
        raise HTTPException(404, "Запис не знайдено")
    return l


def _tx(db: Session, fid: int, tx_id: int) -> models.Transaction:
    t = db.query(models.Transaction).filter(models.Transaction.id == tx_id, models.Transaction.family_id == fid).first()
    if not t:
        raise HTTPException(404, "Транзакцію не знайдено")
    return t


def _tx_brief(t) -> dict:
    return {"id": t.id, "date": str(t.date), "amount": t.amount, "title": t.title.replace("❓ ", ""), "account": t.account,
            "note": "" if t.note == "Migrated" else (t.note or "")}


def vehicle_out(v: models.Vehicle, stats: Optional[dict] = None) -> dict:
    out = {"id": v.id, "name": v.name, "icon": v.icon or "🚗", "plate": v.plate or "", "fuel": v.fuel, "fuel2": v.fuel2,
           "tank_l": v.tank_l, "tank2_l": v.tank2_l, "start_odometer": v.start_odometer,
           "match_pattern": v.match_pattern or "", "user_id": v.user_id, "is_active": v.is_active, "note": v.note or ""}
    if stats is not None:
        out["stats"] = {k: x for k, x in stats.items() if k not in ("segments", "prices")}
    return out


def _logs(db: Session, fid: int, vid: Optional[int] = None) -> list[models.VehicleLog]:
    q = db.query(models.VehicleLog).filter(models.VehicleLog.family_id == fid)
    if vid is not None:
        q = q.filter(models.VehicleLog.vehicle_id == vid)
    return q.all()


def _fmt(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def tx_title(l: models.VehicleLog) -> str:
    """Expense title in the owner's own style: «⛽ Газ 30 л по 42,9 грн, до повного»."""
    icon, label = V.KINDS.get(l.kind, ("📦", "Авто"))
    if l.kind != "fuel":
        return f"{icon} {l.title or label}"
    parts = [V.FUELS.get(l.fuel or "", {}).get("label", "Пальне")]
    if l.liters:
        parts.append(f"{_fmt(l.liters)} {V.FUELS.get(l.fuel or '', {}).get('unit', 'л')}")
    if l.price:
        parts.append(f"по {_fmt(l.price)} грн")
    return f"{icon} {' '.join(parts)}{', до повного' if l.full_tank else ''}"


@router.get("/families/{family_id}/auto")
def overview(family_id: int, include_inactive: bool = False, _: None = Depends(require_family),
             db: Session = Depends(get_db)):
    q = db.query(models.Vehicle).filter(models.Vehicle.family_id == family_id)
    if not include_inactive:
        q = q.filter(models.Vehicle.is_active.is_(True))
    vs = q.order_by(models.Vehicle.is_active.desc(), models.Vehicle.sort_order, models.Vehicle.id).all()
    logs = _logs(db, family_id)
    items = [vehicle_out(v, V.vehicle_stats(v, [l for l in logs if l.vehicle_id == v.id])) for v in vs]
    sug = len(V.candidates(db, family_id)) if any(v.is_active for v in vs) else 0
    return {"vehicles": items, "suggested": sug}


def _apply_vehicle(v: models.Vehicle, data: dict, db: Session, fid: int):
    for k in ("fuel", "fuel2"):
        if data.get(k) and data[k] not in V.FUELS:
            raise HTTPException(400, "Невірне паливо")
    if "fuel2" in data and data["fuel2"] == (data.get("fuel") or v.fuel):
        data["fuel2"] = None
    if data.get("user_id") and not db.query(models.FamilyMember).filter(
            models.FamilyMember.family_id == fid, models.FamilyMember.user_id == data["user_id"]).first():
        raise HTTPException(400, "Невірний учасник")
    for k, x in data.items():
        setattr(v, k, x)


@router.post("/families/{family_id}/vehicles")
def create_vehicle(family_id: int, payload: VehicleIn, _: None = Depends(require_family), db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    if not (data.get("name") or "").strip():
        raise HTTPException(400, "Потрібна назва")
    v = models.Vehicle(family_id=family_id, fuel="petrol", match_pattern=V.DEFAULT_PATTERN)
    _apply_vehicle(v, data, db, family_id)
    db.add(v)
    db.commit()
    return vehicle_out(v, V.vehicle_stats(v, []))


@router.put("/families/{family_id}/vehicles/{vehicle_id}")
def update_vehicle(family_id: int, vehicle_id: int, payload: VehicleIn, _: None = Depends(require_family),
                   db: Session = Depends(get_db)):
    v = _vehicle(db, family_id, vehicle_id)
    _apply_vehicle(v, payload.model_dump(exclude_unset=True), db, family_id)
    db.commit()
    return vehicle_out(v, V.vehicle_stats(v, _logs(db, family_id, v.id)))


@router.delete("/families/{family_id}/vehicles/{vehicle_id}")
def delete_vehicle(family_id: int, vehicle_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    """Archive when the journal has entries (history stays), delete otherwise."""
    v = _vehicle(db, family_id, vehicle_id)
    has = db.query(models.VehicleLog).filter(models.VehicleLog.vehicle_id == v.id).count()
    if has:
        v.is_active = False
    else:
        db.delete(v)
    db.commit()
    return {"archived": bool(has)}


@router.get("/families/{family_id}/vehicles/{vehicle_id}/stats")
def stats(family_id: int, vehicle_id: int, months: int = Query(12, ge=1, le=60), _: None = Depends(require_family),
          db: Session = Depends(get_db)):
    v = _vehicle(db, family_id, vehicle_id)
    return V.vehicle_stats(v, _logs(db, family_id, v.id), months=months)


def log_out(l: models.VehicleLog, tx=None, km: Optional[int] = None, seg: Optional[dict] = None,
            users: Optional[dict] = None) -> dict:
    icon, label = V.KINDS.get(l.kind, ("📦", "Інше"))
    return {"id": l.id, "vehicle_id": l.vehicle_id, "date": str(l.date), "kind": l.kind, "icon": icon, "label": label,
            "odometer": l.odometer, "fuel": l.fuel, "liters": l.liters, "price": l.price, "full_tank": l.full_tank,
            "amount": l.amount or 0, "title": l.title or "", "note": l.note or "", "source": l.source,
            "transaction_id": l.transaction_id, "transaction": _tx_brief(tx) if tx is not None else None,
            "km_since": km, "segment": seg, "user_name": (users or {}).get(l.user_id)}


@router.get("/families/{family_id}/vehicles/{vehicle_id}/logs")
def list_logs(family_id: int, vehicle_id: int, kind: Optional[str] = None, limit: int = Query(500, le=2000),
              _: None = Depends(require_family), db: Session = Depends(get_db)):
    v = _vehicle(db, family_id, vehicle_id)
    logs = _logs(db, family_id, v.id)
    segs = V.vehicle_stats(v, logs, months=1)["segments"]
    kms = V.km_since(logs)
    txs = {t.id: t for t in db.query(models.Transaction).filter(
        models.Transaction.id.in_([l.transaction_id for l in logs if l.transaction_id]))} if logs else {}
    users = {u.id: u.name for u in db.query(models.User).filter(models.User.id.in_({l.user_id for l in logs if l.user_id}))}
    if kind:
        logs = [l for l in logs if l.kind == kind]
    logs.sort(key=lambda l: (l.date, l.odometer or 0, l.id), reverse=True)
    return [log_out(l, txs.get(l.transaction_id), kms.get(l.id), segs.get(l.id), users) for l in logs[:limit]]


def _apply_log(l: models.VehicleLog, data: dict, db: Session, fid: int):
    if "kind" in data and data["kind"] not in V.KINDS:
        raise HTTPException(400, "Невірний тип запису")
    if data.get("fuel") and data["fuel"] not in V.FUELS:
        raise HTTPException(400, "Невірне паливо")
    if "vehicle_id" in data:
        _vehicle(db, fid, data["vehicle_id"])
    if "date" in data:
        data["date"] = _d(data["date"])
    for k in ("amount", "liters", "price", "odometer"):
        if data.get(k) is not None and data[k] < 0:
            raise HTTPException(400, "Значення не може бути від'ємним")
    for k, x in data.items():
        setattr(l, k, x)
    if l.kind == "fuel":
        l.liters, l.price = V.complete_fuel(l.liters, l.price, l.amount)
    else:
        l.fuel, l.liters, l.price, l.full_tank = None, None, None, False
    l.full_tank = bool(l.full_tank)


def _attach_tx(db: Session, l: models.VehicleLog, tx: models.Transaction):
    if not V._linkable(tx):
        raise HTTPException(400, "Пов'язати можна лише витрату")
    O.unlink(db, tx)  # one operation = one purpose (credit / housing / car); drops its old journal entry
    db.flush()
    l.transaction_id, l.amount, l.date = tx.id, tx.amount, tx.date
    V.apply_category(db, tx, l.kind)


@router.post("/families/{family_id}/vehicle-logs")
def create_log(family_id: int, payload: LogIn, actor: Actor = Depends(get_actor), _: None = Depends(require_family),
               db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    tx_id = data.pop("transaction_id", None)
    create_tx = data.pop("create_transaction", False)
    account = data.pop("account", "Готівка")
    v = _vehicle(db, family_id, data.get("vehicle_id"))
    uid = _actor_user_id(db, actor, family_id)
    l = models.VehicleLog(family_id=family_id, vehicle_id=v.id, kind="fuel", amount=0.0, user_id=uid,
                          source="transaction" if tx_id else "manual")
    data.setdefault("date", None)
    _apply_log(l, data, db, family_id)
    if l.kind == "fuel" and not l.fuel:
        l.fuel = v.fuel
    if l.kind == "odometer" and not l.odometer:
        raise HTTPException(400, "Вкажіть пробіг")
    if tx_id:
        _attach_tx(db, l, _tx(db, family_id, tx_id))
    elif create_tx and (l.amount or 0) > 0 and uid:
        tx = crud.create_transaction(db, family_id, uid, V.category_for(db, family_id, l.kind), l.amount, crud.TYPE_EXPENSE,
                                     tx_title(l), l.note or (f"Пробіг: {l.odometer}" if l.odometer else v.name),
                                     account, l.date)
        l.transaction_id = tx.id
    db.add(l)
    db.commit()
    return log_out(l, db.get(models.Transaction, l.transaction_id) if l.transaction_id else None)


@router.put("/families/{family_id}/vehicle-logs/{log_id}")
def update_log(family_id: int, log_id: int, payload: LogIn, _: None = Depends(require_family),
               db: Session = Depends(get_db)):
    l = _log(db, family_id, log_id)
    data = payload.model_dump(exclude_unset=True)
    tx_id = data.pop("transaction_id", None)
    data.pop("create_transaction", None)
    data.pop("account", None)
    _apply_log(l, data, db, family_id)
    if tx_id and tx_id != l.transaction_id:
        _attach_tx(db, l, _tx(db, family_id, tx_id))
    elif l.transaction_id:
        tx = db.get(models.Transaction, l.transaction_id)
        if tx is not None:  # the operation mirrors what was corrected in the journal
            tx.amount, tx.date = l.amount, l.date
    db.commit()
    return log_out(l, db.get(models.Transaction, l.transaction_id) if l.transaction_id else None)


@router.delete("/families/{family_id}/vehicle-logs/{log_id}")
def delete_log(family_id: int, log_id: int, delete_transaction: bool = False, _: None = Depends(require_family),
               db: Session = Depends(get_db)):
    l = _log(db, family_id, log_id)
    tx_id = l.transaction_id
    db.delete(l)
    db.commit()
    if delete_transaction and tx_id:
        crud.delete_transaction(db, tx_id)
    return {"deleted": True, "transaction_deleted": bool(delete_transaction and tx_id)}


@router.get("/families/{family_id}/auto/suggestions")
def suggestions(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    """Car-looking expenses that are not in the journal yet, each with a pre-filled entry."""
    out = []
    for tx in V.candidates(db, family_id)[:60]:
        v = V.pick_vehicle(db, family_id, tx.user_id)
        out.append({"transaction": _tx_brief(tx), "draft": V.draft_from_tx(db, tx, v)})
    return out


@router.get("/families/{family_id}/auto/draft")
def draft(family_id: int, tx_id: int, vehicle_id: Optional[int] = None, _: None = Depends(require_family),
          db: Session = Depends(get_db)):
    tx = _tx(db, family_id, tx_id)
    v = _vehicle(db, family_id, vehicle_id) if vehicle_id else V.pick_vehicle(db, family_id, tx.user_id)
    return {"transaction": _tx_brief(tx), "draft": V.draft_from_tx(db, tx, v)}


class IgnoreIn(BaseModel):
    transaction_id: int


@router.post("/families/{family_id}/auto/ignore")
def ignore(family_id: int, payload: IgnoreIn, _: None = Depends(require_family), db: Session = Depends(get_db)):
    """«Не авто»: stop suggesting this operation."""
    tx = _tx(db, family_id, payload.transaction_id)
    if not db.query(models.VehicleIgnoredTx).filter(models.VehicleIgnoredTx.family_id == family_id,
                                                    models.VehicleIgnoredTx.transaction_id == tx.id).first():
        db.add(models.VehicleIgnoredTx(family_id=family_id, transaction_id=tx.id))
        db.commit()
    return {"ignored": tx.id}


@router.post("/families/{family_id}/vehicles/{vehicle_id}/import")
def import_history(family_id: int, vehicle_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    """Journal entries from every expense in a car category (notes parsed: liters, price, odometer).
    Fills of a fuel this car doesn't use (a borrowed diesel car) are left out for a manual decision."""
    v = _vehicle(db, family_id, vehicle_id)
    linked, skipped = 0, []
    for tx in V.candidates(db, family_id, days=3650, include_pending=False):
        d = V.draft_from_tx(db, tx, v)
        if d["foreign_fuel"]:
            skipped.append(_tx_brief(tx))
            continue
        db.add(V.log_from_draft(d, family_id, tx.user_id, "import"))
        linked += 1
    db.commit()
    return {"linked": linked, "skipped": skipped}
