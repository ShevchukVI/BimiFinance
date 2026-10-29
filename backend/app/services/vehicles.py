"""«Авто»: recognising car expenses, reading fuel notes, consumption and cost statistics.

A journal entry (`vehicle_logs`) is a fill, a service visit, a wash… optionally paid by one finance
transaction (`transaction_id`). Notes are parsed the way people write them in Bimi:
«Газ до повного (52 л по 48,5 грн). Пробіг: 278297», «AZS 4 | Газ 18,6 за 42,9 грн. Пробіг: 280941».

Consumption (л/100 км) uses fills of one fuel between odometer readings:
- average: liters of every fill after the first reading up to the last one / km between them
  (tank level differences even out over many fills);
- full-to-full: liters between two «до повного» fills / km between them (exact for that stretch).
A bi-fuel car (ГБО) has one odometer for both fuels, so each fuel's figure is per km driven in total.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app import models
from app.services.housing import add_months, month_end, today_kyiv
from app.services.obligations import _clean_title, _is_pending, linked_tx_ids, text_matches

FUELS = {
    "lpg": {"label": "Газ", "unit": "л"},
    "petrol": {"label": "Бензин", "unit": "л"},
    "diesel": {"label": "Дизель", "unit": "л"},
    "electric": {"label": "Електро", "unit": "кВт·год"},
}
KINDS = {
    "fuel": ("⛽", "Заправка"), "service": ("🛢️", "ТО"), "repair": ("🔧", "Ремонт"), "tires": ("🛞", "Шини"),
    "wash": ("🧽", "Мийка"), "parking": ("🅿️", "Парковка"), "insurance": ("📄", "Страховка"),
    "fine": ("👮", "Штраф"), "other": ("📦", "Інше"), "odometer": ("📍", "Пробіг"),
}
MAINTENANCE = ("service", "repair", "tires")
DEFAULT_PATTERN = "AZS|АЗС|WOG|OKKO|ОККО|UPG|SOCAR|KLO|БРСМ|BRSM|Shell|Авіас|AMIC|Motto|DEWASH|Мийка|Parking|Паркінг"
MIN_STATION_AMOUNT = 200  # a pending «AZS 4» for 60 ₴ is coffee, not fuel

_N = r"(\d+(?:[.,]\d+)?)"
_FUEL_RE = [
    ("lpg", re.compile(r"\bгаз|пропан|\blpg\b|\bгбо\b", re.I)),
    ("diesel", re.compile(r"дизел|\bдп\b|\bдт\b|diesel", re.I)),
    ("petrol", re.compile(r"бенз|\bа-?9[25]\b|petrol|pulls\s*95|euro\s*95", re.I)),
    ("electric", re.compile(r"заряд|квт|\bkwh\b|електрозаряд", re.I)),
]
_LITERS = re.compile(_N + r"\s*(?:л|l|літр\w*|квт\S*|kwh)(?![a-zа-яіїєґ])", re.I)
_LITERS_BARE = re.compile(r"(?:\bгаз\w*|бенз\w*|дизел\w*)[,:]?\s+" + _N + r"\s+(?:за|по)\b", re.I)
_PRICE = re.compile(r"(?:\bпо|\bза)\s+" + _N + r"\s*(?:грн|₴)?", re.I)
_ODO = [re.compile(r"(?:пробіг|одометр)\w*\s*[:\-]?\s*(\d[\d\s]{3,8}\d)", re.I),
        re.compile(r"\((\d{5,7})\)"), re.compile(r"\b(\d{5,7})\s*км\b", re.I)]
_FULL = re.compile(r"до\s+повного|повн(?:ого|ий)\s+бак|\bfull\b", re.I)
_KIND_RE = [
    ("wash", re.compile(r"мийк|\bwash|dewash|пилосос|хімчистк", re.I)),
    ("parking", re.compile(r"парков|паркінг|parking", re.I)),
    ("tires", re.compile(r"\bшин[аиуі]?\b|шиномонтаж|\bрезин[аиуі]?\b|колес|коліс|перевзу|вулканіз|балансуван", re.I)),
    ("insurance", re.compile(r"страхов|осцпв|осаго|каско|автоцивілк|\bполіс", re.I)),
    ("fine", re.compile(r"штраф", re.I)),
    ("service", re.compile(r"(?-i:\bТО\b)|техобслуг|замін\w* масл|\bмасл[оа]\b|фільтр", re.I)),
    ("repair", re.compile(r"\bсто\b|ремонт|запчаст|деталь|розвал", re.I)),
]


def _num(s: str) -> float:
    return float(s.replace(",", ".").replace(" ", ""))


def tx_text(tx) -> str:
    note = "" if (tx.note or "").strip() == "Migrated" else (tx.note or "")
    return f"{_clean_title(tx.title)} {note}".strip()


def is_auto_category(name: Optional[str]) -> bool:
    n = (name or "").lower()
    return ("палив" in n or "авто" in n or "машин" in n) and "автобус" not in n


def auto_category_ids(db: Session, family_id: int) -> set[int]:
    return {c.id for c in db.query(models.Category).filter(models.Category.family_id == family_id,
                                                           models.Category.type == "expense")
            if is_auto_category(c.name)}


def parse(text: str) -> dict:
    """Fuel / liters / price per liter / odometer / «до повного» from a free-text note."""
    t = text or ""
    out: dict = {"fuel": None, "liters": None, "price": None, "odometer": None, "full_tank": bool(_FULL.search(t))}
    hits = [(m.start(), f) for f, rx in _FUEL_RE for m in [rx.search(t)] if m]
    if hits:
        out["fuel"] = min(hits)[1]
    m = _LITERS.search(t) or _LITERS_BARE.search(t)
    if m:
        out["liters"] = _num(m.group(1))
    for m in _PRICE.finditer(t):
        v = _num(m.group(1))
        if 5 <= v <= 300:
            out["price"] = v
            break
    for rx in _ODO:
        m = rx.search(t)
        if m:
            v = int(re.sub(r"\D", "", m.group(1)))
            if 1000 <= v <= 3_000_000:
                out["odometer"] = v
                break
    return out


def classify(text: str, category_name: Optional[str] = None, parsed: Optional[dict] = None, station: bool = False) -> str:
    """station = the bank description matches the car's stations pattern (a pending «AZS 4» is a fill)."""
    cat = (category_name or "").lower()
    if "палив" in cat:
        return "fuel"
    for kind, rx in _KIND_RE:
        if rx.search(text or ""):
            return kind
    p = parsed if parsed is not None else parse(text)
    if station or p["fuel"] and (p["liters"] or p["price"]) or re.search(r"заправ", text or "", re.I):
        return "fuel"
    if "ремонт" in cat or "сто" in cat.split():
        return "repair"
    return "other"


def complete_fuel(liters: Optional[float], price: Optional[float], amount: Optional[float]):
    """Two of (liters, price, amount) give the third; amount itself is never rewritten."""
    if amount and liters and not price:
        price = round(amount / liters, 2)
    elif amount and price and not liters:
        liters = round(amount / price, 2)
    return liters, price


def vehicle_fuels(v) -> list[str]:
    return [f for f in (v.fuel, v.fuel2) if f]


def draft_from_tx(db: Session, tx, vehicle) -> dict:
    """Pre-filled journal entry for a transaction (also used by the «Пов'язати» sheet)."""
    cat = db.get(models.Category, tx.category_id) if tx.category_id else None
    text = tx_text(tx)
    p = parse(text)
    kind = classify(text, cat.name if cat else None, p, station=bool(vehicle and text_matches(vehicle.match_pattern, tx.title)))
    d = {"vehicle_id": vehicle.id if vehicle else None, "kind": kind, "date": str(tx.date), "amount": tx.amount,
         "odometer": p["odometer"], "fuel": None, "liters": None, "price": None, "full_tank": False,
         "title": _clean_title(tx.title), "transaction_id": tx.id, "foreign_fuel": False}
    if kind == "fuel":
        fuel = p["fuel"] or (vehicle.fuel if vehicle else None)
        liters, price = complete_fuel(p["liters"], p["price"], tx.amount)
        d.update(fuel=fuel, liters=liters, price=price, full_tank=p["full_tank"],
                 foreign_fuel=bool(vehicle and fuel and fuel not in vehicle_fuels(vehicle)))
    return d


def log_from_draft(d: dict, family_id: int, user_id: Optional[int], source: str) -> models.VehicleLog:
    return models.VehicleLog(family_id=family_id, vehicle_id=d["vehicle_id"], date=date.fromisoformat(d["date"]),
                             kind=d["kind"], odometer=d["odometer"], fuel=d["fuel"], liters=d["liters"],
                             price=d["price"], full_tank=d["full_tank"], amount=d["amount"], title=d["title"],
                             source=source, transaction_id=d["transaction_id"], user_id=user_id)


def pick_vehicle(db: Session, family_id: int, user_id: Optional[int]):
    vs = (db.query(models.Vehicle).filter(models.Vehicle.family_id == family_id, models.Vehicle.is_active.is_(True))
          .order_by(models.Vehicle.sort_order, models.Vehicle.id).all())
    if len(vs) == 1:
        return vs[0]
    mine = [v for v in vs if v.user_id and v.user_id == user_id]
    return mine[0] if len(mine) == 1 else None


def logged_tx_ids(db: Session, family_id: int) -> set[int]:
    return {r[0] for r in db.query(models.VehicleLog.transaction_id).filter(
        models.VehicleLog.family_id == family_id, models.VehicleLog.transaction_id.isnot(None))}


def _linkable(tx) -> bool:
    return tx.type == "Витрати" and tx.jar_id is None and not tx.obligation_id


def candidates(db: Session, family_id: int, days: int = 365, today: Optional[date] = None,
               include_pending: bool = True) -> list:
    """Unlinked expenses that look like car spending: an auto category, or a pending bank
    operation at a station / wash (pending ones only from MIN_STATION_AMOUNT — coffee stays out)."""
    today = today or today_kyiv()
    used = logged_tx_ids(db, family_id) | linked_tx_ids(db, family_id) | {r[0] for r in db.query(
        models.VehicleIgnoredTx.transaction_id).filter(models.VehicleIgnoredTx.family_id == family_id)}
    cats = auto_category_ids(db, family_id)
    pats = "|".join(v.match_pattern or "" for v in db.query(models.Vehicle).filter(
        models.Vehicle.family_id == family_id, models.Vehicle.is_active.is_(True)))
    txs = (db.query(models.Transaction).filter(models.Transaction.family_id == family_id,
                                               models.Transaction.type == "Витрати",
                                               models.Transaction.jar_id.is_(None),
                                               models.Transaction.obligation_id.is_(None),
                                               models.Transaction.date >= today - timedelta(days=days))
           .order_by(models.Transaction.date.desc(), models.Transaction.id.desc()).all())
    out = []
    for tx in txs:
        if tx.id in used:
            continue
        if tx.category_id in cats:
            out.append(tx)
        elif (include_pending and tx.amount >= MIN_STATION_AMOUNT and text_matches(pats, tx.title)
              and _is_pending(db, tx)):
            out.append(tx)
    return out


def category_for(db: Session, family_id: int, kind: str) -> Optional[int]:
    cats = [c for c in db.query(models.Category).filter(models.Category.family_id == family_id,
                                                         models.Category.type == "expense")
            if "Очікує" not in c.name]
    hints = {"fuel": ("Палив",), "repair": ("Ремонт авто", "Ремонт"), "service": ("Ремонт авто",),
             "tires": ("Ремонт авто",)}.get(kind, ()) + ("Авто інше", "Авто", "Палив", "Інше")
    for h in hints:
        c = next((c for c in cats if h.lower() in c.name.lower()), None)
        if c:
            return c.id
    return cats[0].id if cats else None


def apply_category(db: Session, tx, kind: str) -> None:
    """A pending bank operation linked to the car gets a car category (like housing payments do)."""
    if _is_pending(db, tx):
        cat = category_for(db, tx.family_id, kind)
        if cat:
            tx.category_id = cat
            tx.title = _clean_title(tx.title)


def auto_link(db: Session, tx) -> Optional[int]:
    """New / re-categorised transaction in a car category → journal entry of the family's car.
    Pending bank operations are only suggested (a station sells coffee too). Never raises."""
    try:
        if not _linkable(tx) or tx.category_id not in auto_category_ids(db, tx.family_id):
            return None
        if db.query(models.VehicleLog).filter(models.VehicleLog.transaction_id == tx.id).first():
            return None
        if tx.id in linked_tx_ids(db, tx.family_id):
            return None
        v = pick_vehicle(db, tx.family_id, tx.user_id)
        if v is None:
            return None
        log = log_from_draft(draft_from_tx(db, tx, v), tx.family_id, tx.user_id, "transaction")
        db.add(log)
        db.commit()
        return log.id
    except Exception:  # linking is a convenience — never break transaction creation
        db.rollback()
    return None


def sync_from_tx(db: Session, tx) -> bool:
    """The entry mirrors its transaction's amount and date; empty fuel fields are re-read from the note."""
    log = db.query(models.VehicleLog).filter(models.VehicleLog.transaction_id == tx.id).first()
    if log is None:
        return False
    log.amount, log.date = tx.amount, tx.date
    p = parse(tx_text(tx))
    if log.odometer is None and p["odometer"]:
        log.odometer = p["odometer"]
    if log.kind == "fuel":
        if log.liters is None and log.price is None:
            log.liters, log.price = complete_fuel(p["liters"], p["price"], tx.amount)
        if p["full_tank"]:
            log.full_tank = True
    return True


# ---------------------------------------------------------------- statistics

def _sort_key(l):
    return (l.date, l.odometer or 0, l.id or 0)


def _liters_of(l, prices: list[tuple[date, float]]) -> tuple[Optional[float], bool]:
    """(liters, estimated) — a fill without liters is estimated from the nearest known price of that fuel."""
    if l.liters:
        return l.liters, False
    if l.price and l.amount:
        return l.amount / l.price, False
    if l.amount and prices:
        p = min(prices, key=lambda x: abs((x[0] - l.date).days))[1]
        return l.amount / p, True
    return None, False


def _fuel_cost(l) -> float:
    """What the fuel itself cost (a station receipt may include snacks)."""
    return l.liters * l.price if l.liters and l.price else (l.amount or 0)


def fuel_stats(fills: list, segments_out: dict) -> dict:
    fills = sorted(fills, key=_sort_key)
    prices = [(f.date, f.price) for f in fills if f.price]
    lit = [_liters_of(f, prices) for f in fills]
    res = {"fills": len(fills), "liters": round(sum(x[0] or 0 for x in lit), 1), "money": round(sum(f.amount or 0 for f in fills), 2),
           "avg_per100": None, "avg_km": None, "estimated": 0, "last_per100": None, "last_full_date": None,
           "last_price": prices[-1][1] if prices else None, "last_price_date": str(prices[-1][0]) if prices else None}
    idx = [i for i, f in enumerate(fills) if f.odometer]
    if len(idx) >= 2:
        a, b = idx[0], idx[-1]
        km = fills[b].odometer - fills[a].odometer
        span = lit[a + 1:b + 1]
        if km > 0 and all(x[0] is not None for x in span):
            res["avg_per100"] = round(sum(x[0] for x in span) / km * 100, 1)
            res["avg_km"] = km
            res["estimated"] = sum(1 for x in span if x[1])
    anchor = None
    for i, f in enumerate(fills):
        if not (f.full_tank and f.odometer):
            continue
        if anchor is not None:
            km = f.odometer - fills[anchor].odometer
            span = lit[anchor + 1:i + 1]
            if km > 0 and all(x[0] is not None for x in span):
                per100 = round(sum(x[0] for x in span) / km * 100, 1)
                segments_out[f.id] = {"km": km, "per100": per100, "estimated": any(x[1] for x in span)}
                res["last_per100"], res["last_full_date"] = per100, str(f.date)
        anchor = i
    return res


def odometer_points(v, logs: list) -> list[tuple[date, int]]:
    pts = sorted((l.date, l.odometer) for l in logs if l.odometer)
    out: list[tuple[date, int]] = []
    for d, o in pts:  # drop typos that go backwards
        if not out or o >= out[-1][1]:
            out.append((d, o))
    return out


def odometer_at(pts: list[tuple[date, int]], d: date) -> Optional[float]:
    """Linear interpolation inside the known readings; None outside."""
    if not pts or d < pts[0][0] or d > pts[-1][0]:
        return None
    for (d0, o0), (d1, o1) in zip(pts, pts[1:]):
        if d0 <= d <= d1:
            return o0 if d1 == d0 else o0 + (o1 - o0) * (d - d0).days / (d1 - d0).days
    return float(pts[-1][1])


def vehicle_stats(v, logs: list, today: Optional[date] = None, months: int = 12) -> dict:
    today = today or today_kyiv()
    logs = sorted(logs, key=_sort_key)
    spend = [l for l in logs if l.kind != "odometer"]
    segments: dict = {}
    fuels = {}
    for f in dict.fromkeys(vehicle_fuels(v) + [l.fuel for l in logs if l.kind == "fuel" and l.fuel]):
        fills = [l for l in logs if l.kind == "fuel" and l.fuel == f]
        if fills:
            fuels[f] = fuel_stats(fills, segments)
    pts = odometer_points(v, logs)
    if v.start_odometer and (not pts or v.start_odometer < pts[0][1]):
        first = logs[0].date if logs else today
        pts.insert(0, (first, v.start_odometer))
    month0 = today.replace(day=1)
    by_month = []
    for i in range(months - 1, -1, -1):
        m = add_months(month0, -i)
        end = min(month_end(m), today)
        ms = [l for l in spend if m <= l.date <= end]
        o0 = odometer_at(pts, m - timedelta(days=1)) if m > (pts[0][0] if pts else today) else None
        o1 = odometer_at(pts, min(end, pts[-1][0])) if pts and pts[-1][0] >= m else None  # km known so far
        by_month.append({"month": str(m), "fuel": round(sum(l.amount or 0 for l in ms if l.kind == "fuel"), 2),
                         "maintenance": round(sum(l.amount or 0 for l in ms if l.kind in MAINTENANCE), 2),
                         "other": round(sum(l.amount or 0 for l in ms if l.kind not in MAINTENANCE + ("fuel",)), 2),
                         "km": round(o1 - o0) if o0 is not None and o1 is not None else None,
                         "partial": end < month_end(m) or bool(pts) and pts[-1][0] < end})  # km known only so far
    res = {"odometer": pts[-1][1] if pts else None, "odometer_date": str(pts[-1][0]) if pts else None,
           "fuels": fuels, "months": by_month, "segments": segments,
           "month_spend": by_month[-1]["fuel"] + by_month[-1]["maintenance"] + by_month[-1]["other"],
           "year_spend": round(sum(l.amount or 0 for l in spend if l.date > today - timedelta(days=365)), 2),
           "total_spend": round(sum(l.amount or 0 for l in spend), 2),
           "first_date": str(logs[0].date) if logs else None, "logs": len(logs),
           "km_tracked": None, "km_per_month": None, "cost_per_km": None, "fuel_cost_per_km": None,
           "prices": [{"date": str(l.date), "fuel": l.fuel, "price": l.price} for l in logs if l.kind == "fuel" and l.price]}
    if len(pts) >= 2 and pts[-1][1] > pts[0][1]:
        (d0, o0), (d1, o1) = pts[0], pts[-1]
        km = o1 - o0
        window = [l for l in spend if d0 < l.date <= d1]
        res["km_tracked"] = km
        res["km_per_month"] = round(km / max((d1 - d0).days, 1) * 30.44) if (d1 - d0).days >= 14 else None
        res["fuel_cost_per_km"] = round(sum(_fuel_cost(l) for l in window if l.kind == "fuel") / km, 2)
        res["cost_per_km"] = round(sum(l.amount or 0 for l in window) / km, 2)
    return res


def km_since(logs: Iterable) -> dict:
    """log id → km since the previous odometer reading (any entry of that car)."""
    out, prev = {}, None
    for l in sorted((l for l in logs if l.odometer), key=_sort_key):
        if prev is not None and l.odometer > prev:
            out[l.id] = l.odometer - prev
        prev = l.odometer if prev is None or l.odometer > prev else prev
    return out
