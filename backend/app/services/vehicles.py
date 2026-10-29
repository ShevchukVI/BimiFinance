"""«Авто»: recognising car expenses, reading fuel notes, consumption and cost statistics.

A journal entry (`vehicle_logs`) is a fill, a service visit, a wash… optionally paid by one finance
transaction (`transaction_id`). Notes are parsed the way people write them in Bimi:
«Газ до повного (52 л по 48,5 грн). Пробіг: 278297», «AZS 4 | Газ 18,6 за 42,9 грн. Пробіг: 280941».

Consumption (л/100 км) uses fills of one fuel between odometer readings:
- average: liters of every fill after the first reading up to the last one / km between them
  (tank level differences even out over many fills);
- full-to-full: liters between two «до повного» fills / km between them (exact for that stretch).
A bi-fuel car (ГБО) has one odometer for both fuels: l/100 is shown for the main fuel only; the second one
(petrol for warming up an LPG engine) gets liters per month instead — per total km it would be meaningless.

Learning: every confirmed entry teaches the journal about its bank merchant («AZS 4» → fills at «Пролюкс»,
LPG, ~1000 ₴; coffee there is ≤ 95 ₴). New operations from that merchant are then suggested with a
confidence, a station name, a fuel, a price and liters predicted from that history.
"""
from __future__ import annotations

import re
from collections import Counter
from statistics import median
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
FUEL_SURE_AMOUNT = 300  # a station bill above this (and well above the coffee there) is a fill
BRANDS = [  # station chains recognisable in a bank description or a note
    ("WOG", r"\bwog\b|\bвог[іуа]?\b"), ("OKKO", r"okko|окко"), ("SOCAR", r"socar|сокар"), ("UPG", r"\bupg\b"),
    ("KLO", r"\bklo\b|\bкло\b"), ("БРСМ-Нафта", r"брсм|brsm"), ("Shell", r"\bshell\b|шелл"), ("Авіас", r"авіас|avias"),
    ("Motto", r"motto|мотто"), ("AMIC", r"\bamic\b|амік"), ("Укрнафта", r"ukrnafta|укрнафт"),
    ("Пролюкс", r"proluks|пролюкс"), ("DEWASH", r"dewash"),
]

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


def merchant_key(title: Optional[str]) -> str:
    """«❓ AZS 4», «AZS 4 (Газ, 48 л…)», «AZS 4 | Нонстоп» → «azs 4» — what the bank calls the place."""
    t = _clean_title(title or "").lower()
    t = re.split(r"\s*[|(]", t)[0]
    return re.sub(r"\s+", " ", t).strip()


def brand(text: Optional[str]) -> Optional[str]:
    for name, rx in BRANDS:
        if re.search(rx, text or "", re.I):
            return name
    return None


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


def learn(db: Session, family_id: int) -> dict:
    """merchant key → what the journal knows about it: car entries (amounts, kind, fuel, station, price
    history) and other spending there (coffee at a station, operations marked «не авто»)."""
    logs = db.query(models.VehicleLog).filter(models.VehicleLog.family_id == family_id,
                                              models.VehicleLog.transaction_id.isnot(None)).all()
    by_tx = {l.transaction_id: l for l in logs}
    ignored = {r[0] for r in db.query(models.VehicleIgnoredTx.transaction_id).filter(
        models.VehicleIgnoredTx.family_id == family_id)}
    cars = auto_category_ids(db, family_id)
    pending = {c.id for c in db.query(models.Category).filter(models.Category.family_id == family_id)
               if "Очікує" in c.name}
    prof: dict = {}
    rows = db.query(models.Transaction.id, models.Transaction.title, models.Transaction.amount,
                    models.Transaction.category_id).filter(models.Transaction.family_id == family_id,
                                                           models.Transaction.type == "Витрати").all()
    for tid, title, amount, cat in rows:
        key = merchant_key(title)
        if not key:
            continue
        l = by_tx.get(tid)
        if l is not None:
            p = prof.setdefault(key, _blank())
            p["car"].append(amount or 0)
            p["kinds"][l.kind] += 1
            if l.kind == "fuel" and l.fuel:
                p["fuels"][l.fuel] += 1
            if l.place:
                p["places"][l.place] += 1
        elif tid in ignored or cat is not None and cat not in cars and cat not in pending:
            p = prof.setdefault(key, _blank())
            p["other"].append(amount or 0)
    for p in prof.values():
        p["kind"] = p["kinds"].most_common(1)[0][0] if p["kinds"] else None
        p["fuel"] = p["fuels"].most_common(1)[0][0] if p["fuels"] else None
        p["place"] = p["places"].most_common(1)[0][0] if p["places"] else None
    return prof


def _blank() -> dict:
    return {"car": [], "other": [], "kinds": Counter(), "fuels": Counter(), "places": Counter()}


def assess(amount: float, p: Optional[dict], station: bool) -> Optional[str]:
    """Is a pending operation from this merchant car spending? → "sure" | "maybe" | None.
    Learned from history: amounts of confirmed entries vs other spending there (coffee, snacks)."""
    amount = amount or 0
    if p and p["car"]:
        other = max(p["other"], default=0)
        car_min, car_med = min(p["car"]), median(p["car"])
        if other and amount <= other * 1.2 and amount < car_min * 0.5:
            return None
        if p["kind"] == "fuel":
            sure = max(other * 2, car_med * 0.4, FUEL_SURE_AMOUNT)
            floor = MIN_STATION_AMOUNT
        else:  # a wash costs 100–200 ₴ — its own history sets the bar
            sure = max(other * 2, car_min * 0.7)
            floor = car_min * 0.5
        return "sure" if amount >= sure else "maybe" if amount >= floor else None
    if p and p["other"] and not station:
        return None
    if station and amount >= MIN_STATION_AMOUNT:
        return "maybe"
    return None


def _price_at(logs: list, fuel: str, place: Optional[str], d: date) -> Optional[float]:
    """Latest known price of the fuel up to the date — at that station if it is known there."""
    known = sorted((l for l in logs if l.kind == "fuel" and l.fuel == fuel and l.price and l.date <= d),
                   key=_sort_key)
    at = [l for l in known if place and l.place == place]
    src = at or known
    return src[-1].price if src else None


def odometer_estimate(v, logs: list, d: date) -> Optional[int]:
    """Where the odometer probably is on a date: last reading + the usual km per day since then."""
    pts = odometer_points(v, logs)
    if not pts or d <= pts[-1][0]:
        return None
    (d0, o0), (d1, o1) = pts[0], pts[-1]
    days = (d1 - d0).days
    if days < 14 or o1 <= o0:
        return None
    return round(o1 + (o1 - o0) / days * (d - d1).days)


def draft_from_tx(db: Session, tx, vehicle, prof: Optional[dict] = None, logs: Optional[list] = None) -> dict:
    """Pre-filled journal entry for a transaction (also used by the «Пов'язати» sheet).
    What the note doesn't say is predicted from the merchant's history (`predicted` lists those fields)."""
    cat = db.get(models.Category, tx.category_id) if tx.category_id else None
    text = tx_text(tx)
    p = parse(text)
    prof = learn(db, tx.family_id) if prof is None else prof
    mp = prof.get(merchant_key(tx.title))
    station = bool(vehicle and text_matches(vehicle.match_pattern, tx.title))
    kind = classify(text, cat.name if cat else None, p, station=station)
    if mp and mp["kind"] and kind == "other" and not (cat and is_auto_category(cat.name)):
        kind = mp["kind"]
    if mp and mp["kind"] and mp["kind"] != "fuel" and kind == "fuel" and not (p["liters"] or p["fuel"]):
        kind = mp["kind"]  # «DEWASH» is a wash even though it matched the stations pattern
    d = {"vehicle_id": vehicle.id if vehicle else None, "kind": kind, "date": str(tx.date), "amount": tx.amount,
         "odometer": p["odometer"], "fuel": None, "liters": None, "price": None, "full_tank": False,
         "title": _clean_title(tx.title), "transaction_id": tx.id, "foreign_fuel": False,
         "place": brand(text) or (mp and mp["place"]) or None, "predicted": [], "odometer_hint": None,
         "confidence": assess(tx.amount, mp, station) if cat is None or _is_pending(db, tx) else "sure"}
    if vehicle is not None:
        logs = logs if logs is not None else db.query(models.VehicleLog).filter(
            models.VehicleLog.vehicle_id == vehicle.id).all()
        if not p["odometer"]:
            d["odometer_hint"] = odometer_estimate(vehicle, logs, tx.date)
    if kind == "fuel":
        fuel = p["fuel"] or (mp and mp["fuel"]) or (vehicle.fuel if vehicle else None)
        if not p["fuel"] and fuel:
            d["predicted"].append("fuel")
        liters, price = complete_fuel(p["liters"], p["price"], tx.amount)
        if not price and fuel and vehicle is not None:
            price = _price_at(logs, fuel, d["place"], tx.date)
            if price:
                d["predicted"].append("price")
                if not liters and tx.amount:
                    liters = round(tx.amount / price, 1)
                    d["predicted"].append("liters")
        d.update(fuel=fuel, liters=liters, price=price, full_tank=p["full_tank"],
                 foreign_fuel=bool(vehicle and fuel and fuel not in vehicle_fuels(vehicle)))
    return d


def log_from_draft(d: dict, family_id: int, user_id: Optional[int], source: str) -> models.VehicleLog:
    return models.VehicleLog(family_id=family_id, vehicle_id=d["vehicle_id"], date=date.fromisoformat(d["date"]),
                             kind=d["kind"], odometer=d["odometer"], fuel=d["fuel"], liters=d["liters"],
                             price=d["price"], full_tank=d["full_tank"], amount=d["amount"], title=d["title"],
                             source=source, transaction_id=d["transaction_id"], user_id=user_id,
                             place=d.get("place"))


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
               include_pending: bool = True, prof: Optional[dict] = None) -> list:
    """Unlinked expenses that look like car spending: an auto category, or a pending bank operation
    the history says is car spending (a learned merchant / the stations pattern, by amount — coffee stays out).
    → [(tx, "sure" | "maybe")]"""
    today = today or today_kyiv()
    used = logged_tx_ids(db, family_id) | linked_tx_ids(db, family_id) | {r[0] for r in db.query(
        models.VehicleIgnoredTx.transaction_id).filter(models.VehicleIgnoredTx.family_id == family_id)}
    cats = auto_category_ids(db, family_id)
    pats = "|".join(v.match_pattern or "" for v in db.query(models.Vehicle).filter(
        models.Vehicle.family_id == family_id, models.Vehicle.is_active.is_(True)))
    pending = {c.id for c in db.query(models.Category).filter(models.Category.family_id == family_id)
               if "Очікує" in c.name}
    txs = (db.query(models.Transaction).filter(models.Transaction.family_id == family_id,
                                               models.Transaction.type == "Витрати",
                                               models.Transaction.jar_id.is_(None),
                                               models.Transaction.obligation_id.is_(None),
                                               models.Transaction.date >= today - timedelta(days=days))
           .order_by(models.Transaction.date.desc(), models.Transaction.id.desc()).all())
    if include_pending and prof is None:
        prof = learn(db, family_id)
    out = []
    for tx in txs:
        if tx.id in used:
            continue
        if tx.category_id in cats:
            out.append((tx, "sure"))
        elif include_pending and tx.category_id in pending:
            c = assess(tx.amount, prof.get(merchant_key(tx.title)), text_matches(pats, tx.title))
            if c:
                out.append((tx, c))
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


def hints(v, logs: list, today: Optional[date] = None) -> dict:
    """What a new manual entry is likely to be: stations used (with their latest prices), usual liters,
    how often the tank is filled up, where the odometer probably is today."""
    today = today or today_kyiv()
    fills = sorted((l for l in logs if l.kind == "fuel"), key=_sort_key)
    places: dict = {}
    for l in sorted(logs, key=_sort_key):
        if not l.place:
            continue
        p = places.setdefault(l.place, {"name": l.place, "count": 0, "last_date": None, "prices": {}, "kinds": Counter()})
        p["count"] += 1
        p["last_date"] = str(l.date)
        p["kinds"][l.kind] += 1
        if l.kind == "fuel" and l.fuel and l.price:
            p["prices"][l.fuel] = l.price
    out_places = sorted(places.values(), key=lambda p: (p["last_date"], p["count"]), reverse=True)
    for p in out_places:
        p["kind"] = p.pop("kinds").most_common(1)[0][0]
    fuels = {}
    for f in vehicle_fuels(v) + [x.fuel for x in fills if x.fuel and x.fuel not in vehicle_fuels(v)]:
        ff = [x for x in fills if x.fuel == f]
        if not ff:
            continue
        lit = [x.liters for x in ff if x.liters]
        amt = [x.amount for x in ff if x.amount]
        fuels[f] = {"last_price": next((x.price for x in reversed(ff) if x.price), None),
                    "liters": round(median(lit[-10:]), 1) if lit else None,
                    "amount": round(median(amt[-10:])) if amt else None,
                    "full_share": round(sum(1 for x in ff[-10:] if x.full_tank) / len(ff[-10:]), 2)}
    last = fills[-1] if fills else None
    return {"places": out_places[:8], "fuels": fuels,
            "last_fuel": last.fuel if last else v.fuel,
            "odometer_estimate": odometer_estimate(v, logs, today)}


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


def fuel_stats(fills: list, segments_out: dict, secondary: bool = False, today: Optional[date] = None) -> dict:
    """secondary = the bi-fuel car's second fuel: no l/100 (km are driven mostly on the main one),
    liters per month instead."""
    fills = sorted(fills, key=_sort_key)
    prices = [(f.date, f.price) for f in fills if f.price]
    lit = [_liters_of(f, prices) for f in fills]
    res = {"fills": len(fills), "liters": round(sum(x[0] or 0 for x in lit), 1), "money": round(sum(f.amount or 0 for f in fills), 2),
           "avg_per100": None, "avg_km": None, "estimated": 0, "last_per100": None, "last_full_date": None,
           "last_price": prices[-1][1] if prices else None, "last_price_date": str(prices[-1][0]) if prices else None,
           "secondary": secondary, "per_month_l": None, "per_month_money": None, "last_date": str(fills[-1].date)}
    if secondary:
        days = max(((today or today_kyiv()) - fills[0].date).days, 30)
        res["per_month_l"] = round(res["liters"] / days * 30.44, 1)
        res["per_month_money"] = round(res["money"] / days * 30.44)
        return res
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
            fuels[f] = fuel_stats(fills, segments, secondary=f != v.fuel and v.fuel in fuels, today=today)
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
