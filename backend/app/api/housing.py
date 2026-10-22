"""Housing («Житло»): utilities, meters, bills, payments, rent/mortgage, outages.

Thin HTTP layer: calculations live in app/services/housing.py, outage scraping in
app/services/svitlobot.py. Every route is family-scoped (membership checked).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app import crud, models
from app import schemas_housing as S
from app.core.deps import Actor, get_actor, require_family, require_internal_key
from app.database import get_db
from app.services import housing as H
from app.services import svitlobot

log = logging.getLogger(__name__)

router = APIRouter(prefix="/housing", tags=["housing"])
system_router = APIRouter(prefix="/system/housing", tags=["system"])

# ---------------------------------------------------------------- templates

TEMPLATES = {
    "electricity_2zone": {"title": "Світло (день/ніч)", "provider": {"name": "Світло", "service": "electricity", "billing": "metered", "due_day": 20},
                          "meters": [{"name": "Світло · день", "utility_type": "electricity", "unit": "кВт·год", "zone": "day", "tariff": 4.32},
                                     {"name": "Світло · ніч", "utility_type": "electricity", "unit": "кВт·год", "zone": "night", "tariff": 2.16}]},
    "electricity": {"title": "Світло (одна зона)", "provider": {"name": "Світло", "service": "electricity", "billing": "metered", "due_day": 20},
                    "meters": [{"name": "Світло", "utility_type": "electricity", "unit": "кВт·год", "tariff": 4.32}]},
    "gas": {"title": "Газ", "provider": {"name": "Газ", "service": "gas", "billing": "metered", "due_day": 20},
            "meters": [{"name": "Газ", "utility_type": "gas", "unit": "м³", "tariff": 7.96}]},
    "gas_delivery": {"title": "Доставка газу", "provider": {"name": "Доставка газу", "service": "gas_delivery", "billing": "fixed"}},
    "water": {"title": "Вода", "provider": {"name": "Вода", "service": "water", "billing": "metered", "due_day": 20},
              "meters": [{"name": "Вода", "utility_type": "water", "unit": "м³", "tariff": 29.21}]},
    "heating": {"title": "Опалення (центральне)", "provider": {"name": "Опалення", "service": "heating", "billing": "manual", "due_day": 20}},
    "maintenance": {"title": "Утримання будинку", "provider": {"name": "Утримання будинку", "service": "maintenance", "billing": "fixed", "due_day": 20}},
    "waste": {"title": "Вивіз сміття", "provider": {"name": "Вивіз сміття", "service": "waste", "billing": "fixed", "fixed_amount": 40, "due_day": 20}},
    "internet": {"title": "Інтернет", "provider": {"name": "Інтернет", "service": "internet", "billing": "fixed"}},
    "rent": {"title": "Оренда", "provider": {"name": "Оренда", "service": "rent", "billing": "fixed", "due_day": 1}},
    "mortgage": {"title": "Іпотека / кредит за житло", "provider": {"name": "Іпотека", "service": "mortgage", "billing": "fixed", "due_day": 1}},
    "other": {"title": "Інша послуга", "provider": {"name": "Послуга", "service": "other", "billing": "manual"}},
}


@router.get("/templates")
def get_templates():
    return [{"key": k, "title": v["title"], "icon": H.SERVICE_META[v["provider"]["service"]]["icon"],
             "service": v["provider"]["service"], "meters": len(v.get("meters", []))}
            for k, v in TEMPLATES.items()]


# ---------------------------------------------------------------- helpers

def _d(value: Optional[str], default: Optional[date] = None) -> Optional[date]:
    if value in (None, ""):
        return default
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise HTTPException(400, f"Невірна дата: {value}")


def _period(value: str) -> date:
    try:
        return date.fromisoformat(value[:7] + "-01")
    except ValueError:
        raise HTTPException(400, f"Невірний період: {value}")


def _actor_user_id(db: Session, actor: Actor, family_id: int) -> Optional[int]:
    if actor.kind == "user":
        return actor.user_id
    m = (db.query(models.FamilyMember).filter(models.FamilyMember.family_id == family_id)
         .order_by(models.FamilyMember.user_id).first())
    return m.user_id if m else None


def _profile(db: Session, fid: int) -> Optional[models.HousingProfile]:
    return db.query(models.HousingProfile).filter(models.HousingProfile.family_id == fid).first()


def _provider(db: Session, fid: int, pid: int) -> models.UtilityProvider:
    p = db.query(models.UtilityProvider).filter(models.UtilityProvider.id == pid,
                                                models.UtilityProvider.family_id == fid).first()
    if not p:
        raise HTTPException(404, "Постачальника не знайдено")
    return p


def _meter(db: Session, fid: int, mid: int) -> models.UtilityMeter:
    m = db.query(models.UtilityMeter).filter(models.UtilityMeter.id == mid,
                                             models.UtilityMeter.family_id == fid).first()
    if not m:
        raise HTTPException(404, "Лічильник не знайдено")
    return m


def _load(db: Session, fid: int):
    """Everything the calculations need, in a handful of queries."""
    providers = (db.query(models.UtilityProvider).filter(models.UtilityProvider.family_id == fid)
                 .order_by(models.UtilityProvider.sort_order, models.UtilityProvider.id).all())
    meters = (db.query(models.UtilityMeter).options(selectinload(models.UtilityMeter.readings))
              .filter(models.UtilityMeter.family_id == fid)
              .order_by(models.UtilityMeter.sort_order, models.UtilityMeter.id).all())
    bills = (db.query(models.UtilityBill).options(selectinload(models.UtilityBill.lines))
             .filter(models.UtilityBill.family_id == fid).order_by(models.UtilityBill.period).all())
    payments = (db.query(models.UtilityPayment).filter(models.UtilityPayment.family_id == fid)
                .order_by(models.UtilityPayment.date, models.UtilityPayment.id).all())
    notes = (db.query(models.HousingNote).filter(models.HousingNote.family_id == fid)
             .order_by(models.HousingNote.date.desc(), models.HousingNote.id.desc()).all())
    return providers, meters, bills, payments, notes


def _by(items, attr):
    out: dict = {}
    for it in items:
        out.setdefault(getattr(it, attr), []).append(it)
    return out


def provider_out(p: models.UtilityProvider) -> dict:
    return {"id": p.id, "name": p.name, "service": p.service, "icon": p.icon or H.SERVICE_META.get(p.service, {}).get("icon", "📄"),
            "billing": p.billing, "fixed_amount": p.fixed_amount, "due_day": p.due_day,
            "account_number": p.account_number or "", "pay_url": p.pay_url or "",
            "start_date": str(p.start_date) if p.start_date else None, "opening_balance": p.opening_balance or 0.0,
            "note": p.note or "", "match_pattern": p.match_pattern or "", "is_active": p.is_active,
            "sort_order": p.sort_order or 0}


def profile_out(p: Optional[models.HousingProfile]) -> Optional[dict]:
    if p is None:
        return None
    return {"mode": p.mode, "title": p.title or "", "area_m2": p.area_m2, "heating": p.heating,
            "svitlobot_channel": p.svitlobot_channel, "readings_day": p.readings_day or 1,
            "reminders_enabled": p.reminders_enabled}


def bill_out(b: models.UtilityBill, flags: list) -> dict:
    return {"id": b.id, "provider_id": b.provider_id, "period": str(b.period),
            "issued_on": str(b.issued_on) if b.issued_on else None,
            "opening_balance": b.opening_balance, "paid": b.paid, "accrued": b.accrued, "adjustment": b.adjustment,
            "to_pay": b.to_pay, "consumption": b.consumption, "note": b.note or "",
            "lines": [{"id": ln.id, "meter_id": ln.meter_id, "label": ln.label, "prev_value": ln.prev_value,
                       "curr_value": ln.curr_value, "volume": ln.volume, "tariff": ln.tariff, "amount": ln.amount}
                      for ln in b.lines],
            "flags": flags}


def payment_out(p: models.UtilityPayment) -> dict:
    return {"id": p.id, "provider_id": p.provider_id, "date": str(p.date), "amount": p.amount, "note": p.note or "",
            "user_name": p.user.name if p.user else None, "transaction_id": p.transaction_id}


def note_out(n: models.HousingNote) -> dict:
    return {"id": n.id, "date": str(n.date), "end_date": str(n.end_date) if n.end_date else None,
            "kind": n.kind, "text": n.text or "", "provider_id": n.provider_id}


def _flags_for(provider_bills, provider_payments, meters_by_id):
    """{bill_id: flags} for one provider's bills (chronological)."""
    out, prev = {}, None
    for b in sorted(provider_bills, key=lambda x: x.period):
        out[b.id] = H.bill_flags(b, prev, provider_payments, meters_by_id)
        prev = b
    return out


# ---------------------------------------------------------------- overview

def build_overview(db: Session, fid: int, today: Optional[date] = None) -> dict:
    today = today or H.today_kyiv()
    profile = _profile(db, fid)
    providers, meters, bills, payments, notes = _load(db, fid)
    meters_by_id = {m.id: m for m in meters}
    bills_by_p, pays_by_p = _by(bills, "provider_id"), _by(payments, "provider_id")
    meters_by_p = _by([m for m in meters if m.is_active], "provider_id")

    out_providers, alerts, missing = [], [], []
    totals = {"to_pay_now": 0.0, "debt": 0.0, "accrued_since": 0.0, "next_month_forecast": 0.0}
    for p in providers:
        if not p.is_active:
            continue
        pb, pp = bills_by_p.get(p.id, []), pays_by_p.get(p.id, [])
        bal = H.provider_balance(p, meters_by_p.get(p.id, []), pb, pp, notes, today)
        flags = _flags_for(pb, pp, meters_by_id)
        recent_warn = [f for b in sorted(pb, key=lambda x: x.period)[-2:] for f in flags.get(b.id, []) if f["level"] == "warn"]
        out_providers.append({**provider_out(p), "balance": bal,
                              "meter_ids": [m.id for m in meters_by_p.get(p.id, [])],
                              "bills_count": len(pb), "warnings": len(recent_warn)})
        totals["to_pay_now"] += bal.get("to_pay_now") or 0.0
        totals["debt"] += bal.get("debt") or 0.0
        totals["accrued_since"] += bal.get("accrued_since") or 0.0
        totals["next_month_forecast"] += bal.get("next_bill_forecast") or 0.0

        # alerts: due soon / overdue
        if p.service in H.FIXED_SERVICES:
            since = _d(bal.get("overdue_since"))
            nc = bal.get("next_charge")
            ncd = _d(nc["due"]) if nc else None
            if since and since < today and (bal.get("debt") or 0) > 1:
                alerts.append({"level": "warn", "kind": "pay", "provider_id": p.id,
                               "text": f"{p.name}: прострочено {bal['debt']:.0f} ₴ (з {since:%d.%m.%Y})"})
            elif ncd and 0 <= (ncd - today).days <= 5:
                alerts.append({"level": "info", "kind": "pay", "provider_id": p.id,
                               "text": f"{p.name}: {nc['amount']:.0f} ₴ до {ncd:%d.%m}"})
        else:
            debt = bal.get("to_pay_now") or 0.0
            nd = _d(bal.get("next_due"))
            if debt > 1 and nd is not None and (nd - today).days <= 5:
                alerts.append({"level": "info", "kind": "pay", "provider_id": p.id,
                               "text": f"{p.name}: сплатити ≈ {debt:.0f} ₴ до {nd:%d.%m}"})
        # metered usage that the provider does not charge for (readings not passed?)
        unbilled = _zero_accrual_usage(p, meters_by_p.get(p.id, []), pb, today)
        if unbilled:
            alerts.append({"level": "warn", "kind": "bill", "provider_id": p.id, "text": unbilled})
        for f in recent_warn[:2]:
            alerts.append({"level": "warn", "kind": "bill", "provider_id": p.id, "text": f"{p.name}: {f['text']}"})
        # missing bill for last month (providers that already have bills) — one combined alert
        if pb and p.service not in H.FIXED_SERVICES and today.day >= 10:
            if max(b.period for b in pb) < H.add_months(H.month_start(today), -1):
                missing.append(p.name)

    if missing:
        alerts.append({"level": "info", "kind": "bill",
                       "text": f"Внесіть платіжки за {_month_name(H.add_months(H.month_start(today), -1))}: "
                               + ", ".join(missing)})

    from app.services.obligations import suggestions as _suggestions  # local import: avoid a cycle
    sug = _suggestions(db, fid, today=today)
    for po in out_providers:
        po["suggested"] = len(sug["providers"].get(po["id"], []))
    loose = sum(po["suggested"] for po in out_providers) + len(sug["unassigned"])
    if loose:
        alerts.append({"level": "info", "kind": "link",
                       "text": f"{loose} {'оплата схожа' if loose == 1 else 'оплати схожі'} на комуналку, але не пов'язані з послугою — розкласти?"})

    meter_rows = [H.meter_summary(m, bills_by_p.get(m.provider_id, []), notes, today) for m in meters if m.is_active]
    if meter_rows:
        rd = (profile.readings_day if profile else 1) or 1
        due = H.due_date(today, rd)
        newest = max((_d(m["last_date"]) for m in meter_rows if m["last_date"]), default=None)
        if today >= due and (newest is None or newest < due - timedelta(days=3)):
            alerts.insert(0, {"level": "warn", "kind": "readings",
                              "text": "Час внести показники лічильників" + (f" (останні {newest:%d.%m})" if newest else "")})

    heating = next((n for n in notes if n.kind == "heating" and n.end_date is None and n.date <= today), None)
    hint = _heating_hint(profile, meters, heating, today)
    if hint:
        alerts.append(hint)
    alerts.sort(key=lambda a: 0 if a["level"] == "warn" else 1)
    return {
        "today": str(today), "profile": profile_out(profile),
        "totals": {k: H.r2(v) for k, v in totals.items()},
        "providers": out_providers, "meters": meter_rows, "alerts": alerts[:8],
        "heating": {"on": heating is not None, "since": str(heating.date) if heating else None,
                    "note_id": heating.id if heating else None},
        "power": _power_summary(db, profile, today),
    }


HEATING_UTILITY = {"electric": "electricity", "gas": "gas"}


def _heating_hint(profile, meters, heating, today: date) -> Optional[dict]:
    """Season marker is set twice a year, so instead of a permanent switch we suggest it
    when the heating meter (electricity for electric heaters) jumps in a cold month."""
    if profile is None:
        return None
    if heating is not None:
        if today.month in (5, 6, 7, 8, 9) and (today - heating.date).days > 30:
            return {"level": "info", "kind": "heating", "text": "Опалювальний сезон ще позначений — завершити його?"}
        return None
    utility = HEATING_UTILITY.get(profile.heating or "")
    if not utility or today.month not in (10, 11, 12, 1, 2, 3, 4):
        return None
    for m in meters:
        if not m.is_active or m.utility_type != utility:
            continue
        pts = H.series(m.readings)
        if len(pts) < 3 or (today - pts[-1].date).days > 21:
            continue
        recent = H.daily_rate(pts, ref=pts[-1].date, window=21)
        base = H.daily_rate(pts, ref=pts[-1].date - timedelta(days=21), window=45)
        if recent and base and recent >= base * 1.3 and recent - base >= 0.8:
            return {"level": "info", "kind": "heating",
                    "text": f"Схоже, почали обігрів: {m.name} ≈ {recent:.1f} {m.unit}/день (+{(recent / base - 1) * 100:.0f}%). "
                            "Позначити опалювальний сезон?"}
    return None


def _zero_accrual_usage(p, meters, bills, today: date) -> Optional[str]:
    """Metered provider whose bills charge nothing while the meter keeps turning."""
    if p.billing != "metered" or len(bills) < 2 or not meters or any(b.accrued for b in bills[-2:]):
        return None
    zero_from = min(b.period for b in bills if not b.accrued)
    for b in sorted(bills, key=lambda x: x.period):
        if b.accrued:
            zero_from = H.add_months(b.period, 1)
    vol = cost = 0.0
    unit = meters[0].unit
    for m in meters:
        pts = H.series(m.readings)
        v0, _ = H.value_at(pts, zero_from)
        v1, _ = H.value_at(pts, today)
        if v0 is None or v1 is None:
            continue
        vol += max(v1 - v0, 0)
        cost += max(v1 - v0, 0) * (H.meter_tariff(m, bills) or 0)
    if vol < 1:
        return None
    return (f"{p.name}: з {zero_from:%d.%m} за лічильником спожито ≈ {vol:.0f} {unit}"
            + (f" (≈ {cost:.0f} ₴)" if cost else "") + ", а в платіжках нараховано 0 — перевірте, чи передані "
            "показники (можливий донарахунок)")


_MONTHS = ["січень", "лютий", "березень", "квітень", "травень", "червень", "липень", "серпень",
           "вересень", "жовтень", "листопад", "грудень"]


def _month_name(d: date) -> str:
    return _MONTHS[d.month - 1]


def _iso(dt: datetime) -> str:
    return dt.isoformat() + "Z"


def _power_summary(db: Session, profile, today: date) -> Optional[dict]:
    channel = profile.svitlobot_channel if profile else None
    if not channel:
        return None
    q = db.query(models.PowerOutage).filter(models.PowerOutage.channel == channel)
    last = q.order_by(models.PowerOutage.started_at.desc()).first()
    ms, me = H.kyiv_month_bounds_utc(H.month_start(today))
    month_rows = q.filter(models.PowerOutage.started_at < me).filter(
        (models.PowerOutage.ended_at.is_(None)) | (models.PowerOutage.ended_at > ms)).all()
    state = db.get(models.PowerSyncState, channel)
    return {
        "channel": channel,
        "state": None if last is None else ("off" if last.ended_at is None else "on"),
        "since": _iso((last.started_at if last.ended_at is None else last.ended_at)) if last else None,
        "month_off_hours": round(H.outage_hours(month_rows, ms, min(me, H.utcnow())), 1),
        "month_outages": len(month_rows),
        "synced_at": _iso(state.synced_at) if state and state.synced_at else None,
    }


@router.get("/families/{family_id}/overview")
def overview(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    return build_overview(db, family_id)


# ---------------------------------------------------------------- profile / setup

@router.put("/families/{family_id}/profile")
def update_profile(family_id: int, payload: S.ProfileIn, _: None = Depends(require_family),
                   db: Session = Depends(get_db)):
    p = _profile(db, family_id) or models.HousingProfile(family_id=family_id)
    data = payload.model_dump(exclude_unset=True)
    if "mode" in data and data["mode"] not in S.MODES:
        raise HTTPException(400, "Невірний режим")
    if "heating" in data and data["heating"] not in S.HEATING:
        raise HTTPException(400, "Невірний тип опалення")
    if "svitlobot_channel" in data:
        raw = data["svitlobot_channel"]
        data["svitlobot_channel"] = svitlobot.normalize_channel(raw)
        if raw and not data["svitlobot_channel"]:
            raise HTTPException(400, "Невірна назва каналу світлобота")
        if data["svitlobot_channel"] and data["svitlobot_channel"] != (p.svitlobot_channel or None):
            svitlobot.validate_channel(data["svitlobot_channel"])
    for k, v in data.items():
        setattr(p, k, v)
    db.add(p)
    db.commit()
    return profile_out(p)


def _create_from_template(db: Session, fid: int, key: str, sort: int, overrides: Optional[dict] = None):
    t = TEMPLATES.get(key)
    if not t:
        raise HTTPException(400, f"Невідомий шаблон: {key}")
    pdata = {**t["provider"], **(overrides or {})}
    prov = models.UtilityProvider(family_id=fid, icon=H.SERVICE_META[pdata["service"]]["icon"], sort_order=sort,
                                  start_date=H.month_start(H.today_kyiv()), **pdata)
    db.add(prov)
    db.flush()
    for i, m in enumerate(t.get("meters", [])):
        db.add(models.UtilityMeter(family_id=fid, provider_id=prov.id, sort_order=sort * 10 + i, **m))
    return prov


@router.post("/families/{family_id}/setup")
def setup(family_id: int, payload: S.SetupIn, _: None = Depends(require_family), db: Session = Depends(get_db)):
    """Onboarding in one tap: housing mode + chosen templates."""
    if payload.mode not in S.MODES:
        raise HTTPException(400, "Невірний режим")
    p = _profile(db, family_id) or models.HousingProfile(family_id=family_id)
    p.mode = payload.mode
    if payload.area_m2 is not None:
        p.area_m2 = payload.area_m2
    if payload.heating:
        p.heating = payload.heating
    if payload.svitlobot_channel:
        p.svitlobot_channel = svitlobot.normalize_channel(payload.svitlobot_channel)
    db.add(p)
    existing = {pr.service for pr in db.query(models.UtilityProvider).filter(
        models.UtilityProvider.family_id == family_id, models.UtilityProvider.is_active.is_(True))}
    keys = list(payload.templates)
    if payload.mode in ("rent", "mortgage") and payload.mode not in keys:
        keys.insert(0, payload.mode)
    for i, key in enumerate(keys):
        service = TEMPLATES.get(key, {}).get("provider", {}).get("service")
        if service in existing and service in ("rent", "mortgage"):
            continue
        overrides = None
        if key in ("rent", "mortgage") and payload.rent_amount:
            overrides = {"fixed_amount": payload.rent_amount, "due_day": payload.rent_day or 1}
        _create_from_template(db, family_id, key, i, overrides)
    db.commit()
    return build_overview(db, family_id)


# ---------------------------------------------------------------- providers

def _apply_provider(p: models.UtilityProvider, data: dict):
    if "service" in data and data["service"] not in S.SERVICES:
        raise HTTPException(400, "Невірний тип послуги")
    if "billing" in data and data["billing"] not in S.BILLING:
        raise HTTPException(400, "Невірний тип нарахування")
    if "start_date" in data:
        data["start_date"] = _d(data["start_date"])
    for k, v in data.items():
        setattr(p, k, v)


@router.post("/families/{family_id}/providers")
def create_provider(family_id: int, payload: S.ProviderIn, _: None = Depends(require_family),
                    db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    if not data.get("name") or not data.get("service"):
        raise HTTPException(400, "Потрібні назва і тип послуги")
    p = models.UtilityProvider(family_id=family_id, billing="metered", start_date=H.month_start(H.today_kyiv()))
    _apply_provider(p, data)
    if not p.icon:
        p.icon = H.SERVICE_META.get(p.service, {}).get("icon", "📄")
    db.add(p)
    db.commit()
    return provider_out(p)


@router.put("/families/{family_id}/providers/{provider_id}")
def update_provider(family_id: int, provider_id: int, payload: S.ProviderIn, _: None = Depends(require_family),
                    db: Session = Depends(get_db)):
    p = _provider(db, family_id, provider_id)
    _apply_provider(p, payload.model_dump(exclude_unset=True))
    db.commit()
    return provider_out(p)


@router.delete("/families/{family_id}/providers/{provider_id}")
def delete_provider(family_id: int, provider_id: int, _: None = Depends(require_family),
                    db: Session = Depends(get_db)):
    """Archive if it has history (bills/payments), delete if empty."""
    p = _provider(db, family_id, provider_id)
    has_history = bool(p.bills) or bool(p.payments) or any(m.readings for m in p.meters)
    if has_history:
        p.is_active = False
        for m in p.meters:
            m.is_active = False
    else:
        for m in list(p.meters):
            db.delete(m)
        db.delete(p)
    db.commit()
    return {"archived": has_history}


# ---------------------------------------------------------------- meters & readings

@router.post("/families/{family_id}/meters")
def create_meter(family_id: int, payload: S.MeterIn, _: None = Depends(require_family), db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    if not data.get("name") or not data.get("unit"):
        raise HTTPException(400, "Потрібні назва і одиниця")
    if data.get("provider_id"):
        _provider(db, family_id, data["provider_id"])
    m = models.UtilityMeter(family_id=family_id, utility_type=data.pop("utility_type", None) or "other", **data)
    db.add(m)
    db.commit()
    return {"id": m.id}


@router.put("/families/{family_id}/meters/{meter_id}")
def update_meter(family_id: int, meter_id: int, payload: S.MeterIn, _: None = Depends(require_family),
                 db: Session = Depends(get_db)):
    m = _meter(db, family_id, meter_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("provider_id"):
        _provider(db, family_id, data["provider_id"])
    for k, v in data.items():
        setattr(m, k, v)
    db.commit()
    return {"id": m.id}


@router.delete("/families/{family_id}/meters/{meter_id}")
def delete_meter(family_id: int, meter_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    m = _meter(db, family_id, meter_id)
    in_bills = db.query(models.UtilityBillLine).filter(models.UtilityBillLine.meter_id == m.id).first() is not None
    if m.readings or in_bills:
        m.is_active = False
    else:
        db.delete(m)
    db.commit()
    return {"ok": True}


@router.get("/families/{family_id}/meters/{meter_id}/readings")
def meter_readings(family_id: int, meter_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    m = _meter(db, family_id, meter_id)
    rows = sorted(m.readings, key=lambda r: (r.date, r.id), reverse=True)
    out, by_date = [], H.series(m.readings)
    rate_by_date = {}
    for a, b in zip(by_date, by_date[1:]):
        days = (b.date - a.date).days
        rate_by_date[b.date] = H.r2((b.value - a.value) / days) if days else None
    for r in rows:
        out.append({"id": r.id, "date": str(r.date), "value": r.value, "note": r.note or "", "source": r.source,
                    "rate": rate_by_date.get(r.date)})
    return out


@router.post("/families/{family_id}/readings")
def add_readings(family_id: int, payload: S.ReadingsIn, actor: Actor = Depends(get_actor),
                 _: None = Depends(require_family), db: Session = Depends(get_db)):
    """Batch entry (one form for all meters). Rejects a value lower than the previous
    reading unless allow_decrease (meter replaced)."""
    d = _d(payload.date, H.today_kyiv())
    if d > H.today_kyiv() + timedelta(days=1):
        raise HTTPException(400, "Дата показника в майбутньому")
    uid = _actor_user_id(db, actor, family_id)
    saved = []
    for it in payload.items:
        m = _meter(db, family_id, it.meter_id)
        prev = [r for r in m.readings if r.date < d]  # same-day value may be corrected
        nxt = [r for r in m.readings if r.date > d]
        if not payload.allow_decrease:
            if prev and it.value < max(r.value for r in prev) - 1e-9:
                raise HTTPException(400, f"{m.name}: {it.value:g} менше за попередній показник "
                                         f"{max(r.value for r in prev):g}")
            if nxt and it.value > min(r.value for r in nxt) + 1e-9:
                raise HTTPException(400, f"{m.name}: {it.value:g} більше за пізніший показник "
                                         f"{min(r.value for r in nxt):g}")
        same = next((r for r in m.readings if r.date == d), None)
        if same is not None:
            same.value, same.note, same.user_id = it.value, payload.note or same.note, uid
            r = same
        else:
            r = models.UtilityReading(meter_id=m.id, date=d, value=it.value, note=payload.note, source="manual",
                                      user_id=uid)
            db.add(r)
        db.flush()
        saved.append({"meter_id": m.id, "reading_id": r.id})
    db.commit()
    return {"saved": saved, "overview": build_overview(db, family_id)}


@router.delete("/families/{family_id}/readings/{reading_id}")
def delete_reading(family_id: int, reading_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    r = (db.query(models.UtilityReading).join(models.UtilityMeter)
         .filter(models.UtilityReading.id == reading_id, models.UtilityMeter.family_id == family_id).first())
    if not r:
        raise HTTPException(404, "Показник не знайдено")
    db.delete(r)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- bills

@router.get("/families/{family_id}/bills")
def list_bills(family_id: int, provider_id: Optional[int] = None, _: None = Depends(require_family),
               db: Session = Depends(get_db)):
    providers, meters, bills, payments, _n = _load(db, family_id)
    meters_by_id = {m.id: m for m in meters}
    pays_by_p = _by(payments, "provider_id")
    out = []
    for pid, pb in _by(bills, "provider_id").items():
        if provider_id and pid != provider_id:
            continue
        flags = _flags_for(pb, pays_by_p.get(pid, []), meters_by_id)
        out += [bill_out(b, flags[b.id]) for b in pb]
    out.sort(key=lambda b: (b["period"], b["provider_id"]), reverse=True)
    return out


@router.get("/families/{family_id}/bills/draft")
def draft_bill(family_id: int, provider_id: int, period: Optional[str] = None,
               _: None = Depends(require_family), db: Session = Depends(get_db)):
    p = _provider(db, family_id, provider_id)
    per = _period(period) if period else H.add_months(H.month_start(H.today_kyiv()), -1)
    _, meters, bills, payments, _n = _load(db, family_id)
    pm = [m for m in meters if m.provider_id == p.id and m.is_active]
    draft = H.bill_draft(p, pm, [b for b in bills if b.provider_id == p.id],
                         [x for x in payments if x.provider_id == p.id], per)
    existing = next((b for b in bills if b.provider_id == p.id and b.period == per), None)
    draft["existing_id"] = existing.id if existing else None
    return draft


def _save_bill(db: Session, fid: int, bill: models.UtilityBill, payload: S.BillIn, user_id: Optional[int]):
    p = _provider(db, fid, payload.provider_id)
    bill.provider_id = p.id
    bill.period = _period(payload.period)
    bill.issued_on = _d(payload.issued_on)
    bill.opening_balance = payload.opening_balance
    bill.paid = payload.paid
    bill.adjustment = payload.adjustment
    lines = []
    for ln in payload.lines:
        if ln.meter_id:
            _meter(db, fid, ln.meter_id)
        vol = ln.volume
        if vol is None and ln.curr_value is not None and ln.prev_value is not None:
            vol = ln.curr_value - ln.prev_value
        amount = ln.amount
        if amount is None and vol is not None and ln.tariff:
            amount = round(vol * ln.tariff, 2)
        lines.append(models.UtilityBillLine(meter_id=ln.meter_id, label=ln.label, prev_value=ln.prev_value,
                                            curr_value=ln.curr_value, volume=vol, tariff=ln.tariff, amount=amount))
    bill.lines = lines
    accrued = payload.accrued
    if not accrued and lines:
        accrued = round(sum(x.amount or 0 for x in lines), 2)
    bill.accrued = accrued
    bill.to_pay = payload.to_pay if payload.to_pay is not None else round(
        payload.opening_balance - payload.paid + accrued + payload.adjustment, 2)
    bill.consumption = payload.consumption if payload.consumption is not None else (
        round(sum(x.volume or 0 for x in lines), 3) if lines else None)
    bill.note = payload.note
    bill.user_id = user_id
    db.add(bill)
    db.flush()
    if payload.save_readings:
        rd = H.add_months(bill.period, 1)
        for ln in lines:
            if ln.meter_id and ln.curr_value is not None:
                m = _meter(db, fid, ln.meter_id)
                same = next((r for r in m.readings if r.date == rd), None)
                if same is None:
                    db.add(models.UtilityReading(meter_id=m.id, date=rd, value=ln.curr_value, source="bill",
                                                 note="З платіжки", user_id=user_id))
                elif same.source == "bill":
                    same.value = ln.curr_value  # bill corrected → its reading follows
                pd = bill.period
                if ln.prev_value is not None and not m.readings and not any(r.date == pd for r in m.readings):
                    db.add(models.UtilityReading(meter_id=m.id, date=pd, value=ln.prev_value, source="bill",
                                                 note="З платіжки", user_id=user_id))
            if ln.meter_id and ln.tariff:
                m = _meter(db, fid, ln.meter_id)
                # keep the meter's current tariff in sync with the newest bill
                newer = db.query(models.UtilityBill).filter(models.UtilityBill.provider_id == p.id,
                                                            models.UtilityBill.period > bill.period).first()
                if newer is None:
                    m.tariff = ln.tariff
    db.commit()
    return bill


@router.post("/families/{family_id}/bills")
def create_bill(family_id: int, payload: S.BillIn, actor: Actor = Depends(get_actor),
                _: None = Depends(require_family), db: Session = Depends(get_db)):
    per = _period(payload.period)
    _provider(db, family_id, payload.provider_id)  # family check before revealing duplicates
    if db.query(models.UtilityBill).filter(models.UtilityBill.provider_id == payload.provider_id,
                                           models.UtilityBill.period == per).first():
        raise HTTPException(409, "Платіжка за цей місяць уже є — відредагуйте її")
    bill = _save_bill(db, family_id, models.UtilityBill(family_id=family_id), payload,
                      _actor_user_id(db, actor, family_id))
    return _bill_with_flags(db, family_id, bill.id)


@router.put("/families/{family_id}/bills/{bill_id}")
def update_bill(family_id: int, bill_id: int, payload: S.BillIn, actor: Actor = Depends(get_actor),
                _: None = Depends(require_family), db: Session = Depends(get_db)):
    bill = db.query(models.UtilityBill).filter(models.UtilityBill.id == bill_id,
                                               models.UtilityBill.family_id == family_id).first()
    if not bill:
        raise HTTPException(404, "Платіжку не знайдено")
    clash = db.query(models.UtilityBill).filter(models.UtilityBill.provider_id == payload.provider_id,
                                                models.UtilityBill.period == _period(payload.period),
                                                models.UtilityBill.id != bill_id).first()
    if clash:
        raise HTTPException(409, "Платіжка за цей місяць уже є")
    _save_bill(db, family_id, bill, payload, _actor_user_id(db, actor, family_id))
    return _bill_with_flags(db, family_id, bill.id)


def _bill_with_flags(db: Session, fid: int, bill_id: int) -> dict:
    return next(b for b in list_bills(fid, None, None, db) if b["id"] == bill_id)


@router.delete("/families/{family_id}/bills/{bill_id}")
def delete_bill(family_id: int, bill_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    bill = db.query(models.UtilityBill).filter(models.UtilityBill.id == bill_id,
                                               models.UtilityBill.family_id == family_id).first()
    if not bill:
        raise HTTPException(404, "Платіжку не знайдено")
    db.delete(bill)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- payments

_CATEGORY_HINTS = {"rent": ("Оренда",), "mortgage": ("Кредит", "Оренда"), "internet": ("Інтернет", "Зв'язок")}


def _payment_category(db: Session, fid: int, service: str) -> Optional[int]:
    cats = [c for c in crud.get_categories(db, fid) if c.type == "expense" and "Очікує" not in c.name]
    for hint in _CATEGORY_HINTS.get(service, ()) + ("Комуналка", "Дім", "Інше"):
        c = next((c for c in cats if hint.lower() in c.name.lower()), None)
        if c:
            return c.id
    return cats[0].id if cats else None


@router.get("/families/{family_id}/payments")
def list_payments(family_id: int, provider_id: Optional[int] = None, limit: int = Query(100, le=500),
                  _: None = Depends(require_family), db: Session = Depends(get_db)):
    q = db.query(models.UtilityPayment).filter(models.UtilityPayment.family_id == family_id)
    if provider_id:
        q = q.filter(models.UtilityPayment.provider_id == provider_id)
    return [payment_out(p) for p in q.order_by(models.UtilityPayment.date.desc(), models.UtilityPayment.id.desc()).limit(limit)]


@router.post("/families/{family_id}/payments")
def create_payment(family_id: int, payload: S.PaymentIn, actor: Actor = Depends(get_actor),
                   _: None = Depends(require_family), db: Session = Depends(get_db)):
    if payload.amount == 0:
        raise HTTPException(400, "Сума не може бути 0")
    p = _provider(db, family_id, payload.provider_id)
    d = _d(payload.date, H.today_kyiv())
    uid = _actor_user_id(db, actor, family_id)
    pay = models.UtilityPayment(family_id=family_id, provider_id=p.id, date=d, amount=payload.amount,
                                note=payload.note, user_id=uid)
    if payload.create_transaction and payload.amount > 0 and uid:
        cat_id = _payment_category(db, family_id, p.service)
        tx = crud.create_transaction(db, family_id, uid, cat_id, payload.amount, crud.TYPE_EXPENSE,
                                     f"{p.icon or ''} {p.name}".strip(), payload.note or "Житло", payload.account, d)
        pay.transaction_id = tx.id
    db.add(pay)
    db.commit()
    return {"payment": payment_out(pay), "overview": build_overview(db, family_id)}


@router.delete("/families/{family_id}/payments/{payment_id}")
def delete_payment(family_id: int, payment_id: int, delete_transaction: bool = False,
                   _: None = Depends(require_family), db: Session = Depends(get_db)):
    pay = db.query(models.UtilityPayment).filter(models.UtilityPayment.id == payment_id,
                                                 models.UtilityPayment.family_id == family_id).first()
    if not pay:
        raise HTTPException(404, "Оплату не знайдено")
    tx_id = pay.transaction_id
    db.delete(pay)
    if delete_transaction and tx_id:
        tx = crud.get_transaction_by_id(db, tx_id)
        if tx and tx.family_id == family_id:
            db.delete(tx)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- notes & heating

NOTE_KINDS = {"note", "heating", "away", "repair"}


@router.get("/families/{family_id}/notes")
def list_notes(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    rows = (db.query(models.HousingNote).filter(models.HousingNote.family_id == family_id)
            .order_by(models.HousingNote.date.desc(), models.HousingNote.id.desc()).limit(200).all())
    return [note_out(n) for n in rows]


@router.post("/families/{family_id}/notes")
def create_note(family_id: int, payload: S.NoteIn, actor: Actor = Depends(get_actor),
                _: None = Depends(require_family), db: Session = Depends(get_db)):
    if payload.provider_id:
        _provider(db, family_id, payload.provider_id)
    if (payload.kind or "note") not in NOTE_KINDS:
        raise HTTPException(400, "Невірний тип примітки")
    n = models.HousingNote(family_id=family_id, date=_d(payload.date, H.today_kyiv()), end_date=_d(payload.end_date),
                           kind=payload.kind or "note", text=payload.text.strip(), provider_id=payload.provider_id,
                           user_id=_actor_user_id(db, actor, family_id))
    db.add(n)
    db.commit()
    return note_out(n)


@router.put("/families/{family_id}/notes/{note_id}")
def update_note(family_id: int, note_id: int, payload: S.NoteIn, _: None = Depends(require_family),
                db: Session = Depends(get_db)):
    n = db.query(models.HousingNote).filter(models.HousingNote.id == note_id,
                                            models.HousingNote.family_id == family_id).first()
    if not n:
        raise HTTPException(404, "Примітку не знайдено")
    if payload.provider_id:
        _provider(db, family_id, payload.provider_id)
    if payload.kind not in NOTE_KINDS:
        raise HTTPException(400, "Невірний тип примітки")
    n.date = _d(payload.date, n.date)
    n.end_date = _d(payload.end_date)
    n.kind, n.text, n.provider_id = payload.kind, payload.text.strip(), payload.provider_id
    db.commit()
    return note_out(n)


@router.delete("/families/{family_id}/notes/{note_id}")
def delete_note(family_id: int, note_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    n = db.query(models.HousingNote).filter(models.HousingNote.id == note_id,
                                            models.HousingNote.family_id == family_id).first()
    if not n:
        raise HTTPException(404, "Примітку не знайдено")
    db.delete(n)
    db.commit()
    return {"ok": True}


@router.post("/families/{family_id}/heating")
def toggle_heating(family_id: int, payload: S.HeatingIn, actor: Actor = Depends(get_actor),
                   _: None = Depends(require_family), db: Session = Depends(get_db)):
    """One tap «Опалення увімкнули / вимкнули» → heating period note (used by forecasts & charts)."""
    d = _d(payload.date, H.today_kyiv())
    open_note = (db.query(models.HousingNote).filter(models.HousingNote.family_id == family_id,
                                                     models.HousingNote.kind == "heating",
                                                     models.HousingNote.end_date.is_(None)).first())
    if payload.on and open_note is None:
        db.add(models.HousingNote(family_id=family_id, date=d, kind="heating", text="Опалення увімкнено",
                                  user_id=_actor_user_id(db, actor, family_id)))
    elif not payload.on and open_note is not None:
        open_note.end_date = max(d, open_note.date)
        open_note.text = "Опалювальний період"
    db.commit()
    return build_overview(db, family_id)["heating"]


# ---------------------------------------------------------------- stats

@router.get("/families/{family_id}/stats")
def stats(family_id: int, months: int = Query(12, ge=1, le=36), _: None = Depends(require_family),
          db: Session = Depends(get_db)):
    today = H.today_kyiv()
    profile = _profile(db, family_id)
    providers, meters, bills, payments, notes = _load(db, family_id)
    first = H.add_months(H.month_start(today), -(months - 1))
    month_list = list(H.month_iter(first, today))
    bills_by_p, pays_by_p = _by(bills, "provider_id"), _by(payments, "provider_id")

    outages = []
    channel = profile.svitlobot_channel if profile else None
    if channel:
        s0, _e = H.kyiv_month_bounds_utc(first)
        outages = db.query(models.PowerOutage).filter(models.PowerOutage.channel == channel).filter(
            (models.PowerOutage.ended_at.is_(None)) | (models.PowerOutage.ended_at > s0)).all()
    now = H.utcnow()
    power = []
    for m in month_list:
        s, e = H.kyiv_month_bounds_utc(m)
        e = min(e, now)
        hours_total = max((e - s).total_seconds() / 3600, 0)
        off = H.outage_hours(outages, s, e, now) if channel else None
        count = sum(1 for o in outages if o.started_at < e and (o.ended_at or now) > s) if channel else None
        power.append({"month": str(m), "off_hours": H.r2(off), "outages": count, "hours": H.r2(hours_total)})

    meter_series = []
    for mt in meters:
        if not mt.is_active and not mt.readings:
            continue
        pts = H.series(mt.readings)
        mbills = bills_by_p.get(mt.provider_id, [])
        tariff = H.meter_tariff(mt, mbills)
        rows = []
        for i, m in enumerate(month_list):
            line = next((ln for b in mbills if b.period == m for ln in b.lines if ln.meter_id == mt.id), None)
            if line is not None and line.volume is not None:
                vol, cost, source = line.volume, line.amount, "bill"
            else:
                vol, est = H.monthly_volume(pts, m, today)
                cost = vol * tariff if (vol is not None and tariff) else None
                source = None if vol is None else ("estimate" if est else "readings")
            row = {"month": str(m), "volume": H.r2(vol), "cost": H.r2(cost), "source": source,
                   "heating": H.heating_months(notes, m), "partial": m == H.month_start(today)}
            if mt.utility_type == "electricity" and power[i]["off_hours"] is not None and vol is not None:
                powered = max(power[i]["hours"] - power[i]["off_hours"], 1)
                row["per_powered_hour"] = round(vol / powered, 3)
            rows.append(row)
        meter_series.append({"meter_id": mt.id, "name": mt.name, "unit": mt.unit, "utility_type": mt.utility_type,
                             "provider_id": mt.provider_id, "points": rows})

    provider_series = []
    for p in providers:
        pb, pp = bills_by_p.get(p.id, []), pays_by_p.get(p.id, [])
        if not p.is_active and not pb and not pp:
            continue
        # fixed charges are only expected from the start of tracking (start date, first bill or payment)
        starts = [H.month_start(p.start_date)] if p.start_date else []
        starts += [b.period for b in pb] + [H.month_start(x.date) for x in pp]
        tracked_from = min(starts) if starts else H.month_start(today)
        rows = []
        for m in month_list:
            b = next((b for b in pb if b.period == m), None)
            paid = sum(x.amount for x in pp if H.month_start(x.date) == m)
            accrued, est = (b.accrued, False) if b is not None else (None, True)
            if b is None and p.billing == "fixed" and p.fixed_amount and tracked_from <= m <= H.month_start(today):
                accrued = p.fixed_amount
            rows.append({"month": str(m), "accrued": H.r2(accrued), "paid": H.r2(paid), "estimated": est})
        provider_series.append({"provider_id": p.id, "name": p.name, "icon": p.icon, "service": p.service, "points": rows})

    return {"months": [str(m) for m in month_list], "meters": meter_series, "providers": provider_series,
            "power": power if channel else [], "insights": _insights(meter_series, power if channel else [], notes, today)}


def _insights(meter_series, power, notes, today: date) -> list[str]:
    out = []
    cur, prev = str(H.month_start(today)), str(H.add_months(H.month_start(today), -1))
    for ms in meter_series:
        pts = {p["month"]: p for p in ms["points"]}
        c, p = pts.get(cur), pts.get(prev)
        if c and p and c["volume"] and p["volume"] and today.day >= 7:
            # compare daily averages (current month is partial)
            days_c = today.day
            days_p = H.month_end(H.add_months(H.month_start(today), -1)).day
            dc, dp = c["volume"] / days_c, p["volume"] / days_p
            if dp > 0 and abs(dc / dp - 1) >= 0.15:
                out.append(f"{ms['name']}: {dc:.1f} {ms['unit']}/день — {'+' if dc > dp else '−'}"
                           f"{abs(dc / dp - 1) * 100:.0f}% до минулого місяця")
    if power:
        last = power[-1]
        if last["off_hours"]:
            share = last["off_hours"] / max(last["hours"], 1) * 100
            out.append(f"Без світла цього місяця: {last['off_hours']:.0f} год ({share:.0f}% часу), "
                       f"{last['outages']} відключень")
    heating = next((n for n in notes if n.kind == "heating" and n.end_date is None), None)
    if heating:
        out.append(f"Опалення увімкнено з {heating.date:%d.%m} — прогнози рахуються за зимовим споживанням")
    return out[:5]


# ---------------------------------------------------------------- outages

@router.get("/families/{family_id}/outages")
def list_outages(family_id: int, days: int = Query(30, ge=1, le=400), _: None = Depends(require_family),
                 db: Session = Depends(get_db)):
    profile = _profile(db, family_id)
    if not profile or not profile.svitlobot_channel:
        return {"channel": None, "items": [], "daily": []}
    since = H.utcnow() - timedelta(days=days)
    rows = (db.query(models.PowerOutage).filter(models.PowerOutage.channel == profile.svitlobot_channel)
            .filter((models.PowerOutage.ended_at.is_(None)) | (models.PowerOutage.ended_at > since))
            .order_by(models.PowerOutage.started_at.desc()).all())
    now = H.utcnow()
    items = [{"id": o.id, "started_at": _iso(o.started_at),
              "ended_at": _iso(o.ended_at) if o.ended_at else None,
              "minutes": round(((o.ended_at or now) - o.started_at).total_seconds() / 60)} for o in rows]
    daily = []
    for i in range(min(days, 60) - 1, -1, -1):
        d = H.today_kyiv() - timedelta(days=i)
        s = datetime(d.year, d.month, d.day, tzinfo=H.KYIV).astimezone(H.ZoneInfo("UTC")).replace(tzinfo=None)
        daily.append({"date": str(d), "off_hours": H.r2(H.outage_hours(rows, s, min(s + timedelta(days=1), now), now))})
    return {"channel": profile.svitlobot_channel, "items": items, "daily": daily}


@router.post("/families/{family_id}/outages/sync")
def sync_outages(family_id: int, _: None = Depends(require_family), db: Session = Depends(get_db)):
    profile = _profile(db, family_id)
    if not profile or not profile.svitlobot_channel:
        raise HTTPException(400, "Канал світлобота не налаштовано")
    state = db.get(models.PowerSyncState, profile.svitlobot_channel)
    if state and state.synced_at and H.utcnow() - state.synced_at < timedelta(minutes=2):
        return {"channel": profile.svitlobot_channel, "skipped": True}
    try:
        return svitlobot.sync_channel(db, profile.svitlobot_channel)
    except Exception as exc:  # network / layout change — never 500 the UI
        db.rollback()
        log.warning("svitlobot sync failed: %s", exc)
        raise HTTPException(502, "Не вдалося отримати дані світлобота")


# ---------------------------------------------------------------- system (bot)

@system_router.post("/outages/sync")
def system_sync_outages(_: None = Depends(require_internal_key), db: Session = Depends(get_db)):
    channels = {p.svitlobot_channel for p in db.query(models.HousingProfile).all() if p.svitlobot_channel}
    results = []
    for ch in sorted(channels):
        try:
            results.append(svitlobot.sync_channel(db, ch))
        except Exception as exc:
            db.rollback()
            results.append({"channel": ch, "error": type(exc).__name__})
    return results


def compute_reminders(db: Session, today: Optional[date] = None) -> list[dict]:
    """Due reminders that were not sent yet: readings day, payments, rent."""
    from app.api.obligations import obligation_reminders  # local import: avoid a cycle
    today = today or H.today_kyiv()
    out = []
    profiles = {p.family_id: p for p in db.query(models.HousingProfile).all()}
    ob_families = {r[0] for r in db.query(models.Obligation.family_id).filter(models.Obligation.is_active.is_(True),
                                                                              models.Obligation.remind.is_(True))}
    from app.services.analytics import budgets_status  # local import: avoid a cycle
    budget_families = {r[0] for r in db.query(models.Budget.family_id).distinct()}
    for fid in sorted(set(profiles) | ob_families | budget_families):
        profile = profiles.get(fid)
        msgs: list[tuple[str, str]] = []
        if fid in ob_families and (profile is None or profile.reminders_enabled):
            msgs += obligation_reminders(db, fid, today)
        if fid in budget_families and (profile is None or profile.reminders_enabled):
            bs = budgets_status(db, fid, H.month_start(today), today)
            for b in bs["items"]:
                level = 100 if b["spent"] > b["amount"] else 80 if b["pct"] >= 80 else None
                if level:
                    msgs.append((f"budget:{b['category_id']}:{today:%Y-%m}:{level}",
                                 f"🎯 {b['name']}: {b['spent']:.0f} з {b['amount']:.0f} ₴ ({b['pct']:.0f}%)"
                                 + (" — ліміт перевищено" if level == 100 else f", до кінця місяця {bs['days_left']} дн.")))
        if profile is None or not profile.reminders_enabled or profile.mode == "off":
            profile = None
        ov = build_overview(db, fid, today) if profile is not None else {"meters": [], "providers": []}
        ym = f"{today:%Y-%m}"
        rd = H.due_date(today, (profile.readings_day if profile else 1) or 1)
        if ov["meters"] and today in (rd, rd + timedelta(days=2)):
            newest = max((_d(m["last_date"]) for m in ov["meters"] if m["last_date"]), default=None)
            if newest is None or newest < rd - timedelta(days=3):
                msgs.append((f"readings:{ym}:{(today - rd).days}",
                             "📸 Час внести показники лічильників — це 1 хвилина в «Житлі»."))
        for p in ov["providers"]:
            bal = p["balance"]
            since = _d(bal.get("overdue_since"))
            if p["service"] in H.FIXED_SERVICES and since and since < today and (bal.get("debt") or 0) > 1 \
                    and (today - since).days % 7 == 1:
                msgs.append((f"overdue:{p['id']}:{since}:{(today - since).days // 7}",
                             f"⚠️ {p['name']}: прострочено {bal['debt']:.0f} ₴ (з {since:%d.%m})"))
            due = _d(bal.get("next_due"))
            if due is None:
                continue
            days = (due - today).days
            if days not in (3, 0):
                continue
            if p["service"] in H.FIXED_SERVICES:
                nc = bal.get("next_charge") or {}
                if nc and _d(nc.get("due")) == due:
                    msgs.append((f"pay:{p['id']}:{due}:{days}",
                                 f"{p['icon']} {p['name']}: {nc['amount']:.0f} ₴ — {'сьогодні' if days == 0 else f'до {due:%d.%m}'}"))
            elif (bal.get("to_pay_now") or 0) > 1:
                msgs.append((f"pay:{p['id']}:{due}:{days}",
                             f"{p['icon']} {p['name']}: до сплати ≈ {bal['to_pay_now']:.0f} ₴ "
                             f"{'сьогодні' if days == 0 else f'до {due:%d.%m}'}"))
        if not msgs:
            continue
        sent = {r.key for r in db.query(models.HousingReminderLog).filter(
            models.HousingReminderLog.family_id == fid,
            models.HousingReminderLog.key.in_([k for k, _t in msgs]))}
        fresh = [(k, t) for k, t in msgs if k not in sent]
        if not fresh:
            continue
        tg_ids = [u.tg_id for u in crud.get_users(db, fid) if u.tg_id]
        out.append({"family_id": fid, "tg_ids": tg_ids, "keys": [k for k, _t in fresh],
                    "text": "🔔 Нагадування Bimi\n" + "\n".join(t for _k, t in fresh),
                    "tab": "readings" if any(k.startswith("readings:") for k, _t in fresh)
                    else "housing" if any(k.startswith(("pay:", "overdue:")) for k, _t in fresh)
                    else "payments" if any(k.startswith("ob:") for k, _t in fresh) else "analytics"})
    return out


@system_router.get("/reminders")
def system_reminders(_: None = Depends(require_internal_key), db: Session = Depends(get_db)):
    return compute_reminders(db)


@system_router.post("/reminders/ack")
def system_reminders_ack(payload: S.ReminderAck, _: None = Depends(require_internal_key),
                         db: Session = Depends(get_db)):
    today = H.today_kyiv()
    n = 0
    pairs = {(it.get("family_id"), str(it.get("key") or "")[:120]) for it in payload.items}
    for fid, key in sorted(p for p in pairs if p[0] and p[1]):
        exists = db.query(models.HousingReminderLog).filter(models.HousingReminderLog.family_id == fid,
                                                            models.HousingReminderLog.key == key).first()
        if not exists:
            db.add(models.HousingReminderLog(family_id=fid, key=key, sent_on=today))
            n += 1
    db.commit()
    return {"acked": n}
