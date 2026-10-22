"""Housing («Житло») calculations: pure functions over ORM objects (no DB writes).

Conventions:
- balance > 0 = debt (треба доплатити), balance < 0 = overpay (переплата).
- A bill covers one calendar month (`period` = first day). Payments dated after the
  end of that month are not yet reflected in it.
- Everything that is not taken from a real bill or reading is an estimate and is
  returned with an `estimated` flag / «≈» wording, so the UI can label it honestly.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

KYIV = ZoneInfo("Europe/Kyiv")
AVG_MONTH_DAYS = 30.44
MONEY_EPS = 0.5  # гривня-копійки: розбіжності менші за 50 коп. не показуємо

FIXED_SERVICES = {"rent", "mortgage"}  # charged in advance, "оплачено до"

SERVICE_META = {
    "electricity": {"icon": "⚡", "label": "Світло"},
    "gas": {"icon": "🔥", "label": "Газ"},
    "gas_delivery": {"icon": "🚚", "label": "Доставка газу"},
    "water": {"icon": "💧", "label": "Вода"},
    "heating": {"icon": "♨️", "label": "Опалення"},
    "maintenance": {"icon": "🏢", "label": "Утримання будинку"},
    "waste": {"icon": "🗑", "label": "Вивіз сміття"},
    "internet": {"icon": "🌐", "label": "Інтернет"},
    "rent": {"icon": "🏠", "label": "Оренда"},
    "mortgage": {"icon": "🏦", "label": "Іпотека"},
    "other": {"icon": "📄", "label": "Інше"},
}


def utcnow() -> datetime:
    """Naive UTC now (DB stores naive UTC timestamps)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today_kyiv() -> date:
    return datetime.now(KYIV).date()


# ---------------------------------------------------------------- dates

def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def due_date(month: date, due_day: Optional[int]) -> date:
    day = min(max(due_day or 1, 1), calendar.monthrange(month.year, month.month)[1])
    return month.replace(day=day)


def month_iter(start: date, end: date) -> Iterable[date]:
    m = month_start(start)
    while m <= end:
        yield m
        m = add_months(m, 1)


def r2(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(x + 0.0, 2)


# ---------------------------------------------------------------- meter series

@dataclass
class Point:
    date: date
    value: float


def series(readings) -> list[Point]:
    """Sorted readings; for the same date keep the highest value (re-entered photo)."""
    by_day: dict[date, float] = {}
    for r in readings:
        by_day[r.date] = max(by_day.get(r.date, r.value), r.value)
    return [Point(d, v) for d, v in sorted(by_day.items())]


def daily_rate(points: list[Point], ref: Optional[date] = None, window: int = 45,
               min_span: int = 5) -> Optional[float]:
    """Average consumption per day over the most recent window ending at the reading <= ref."""
    pts = [p for p in points if ref is None or p.date <= ref]
    if len(pts) < 2:
        return None
    last = pts[-1]
    older = [p for p in pts[:-1] if (last.date - p.date).days >= min_span]
    if not older:
        older = pts[:-1]
    in_window = [p for p in older if (last.date - p.date).days <= window]
    first = in_window[0] if in_window else older[-1]
    days = (last.date - first.date).days
    if days <= 0:
        return None
    return max(last.value - first.value, 0.0) / days


def value_at(points: list[Point], d: date, max_extrapolate_days: int = 45) -> tuple[Optional[float], bool]:
    """Meter value on date d: interpolated between readings, or extrapolated by the
    recent daily rate (estimated=True). Returns (value, estimated)."""
    if not points:
        return None, True
    for p in points:
        if p.date == d:
            return p.value, False
    before = [p for p in points if p.date < d]
    after = [p for p in points if p.date > d]
    if before and after:
        a, b = before[-1], after[0]
        span = (b.date - a.date).days
        v = a.value + (b.value - a.value) * (d - a.date).days / span
        return v, span > 10  # long gaps are effectively estimates
    if before:
        last = before[-1]
        gap = (d - last.date).days
        rate = daily_rate(points)
        if rate is None or gap > max_extrapolate_days:
            return (last.value if rate is None else None), True
        return last.value + rate * gap, True
    first = after[0]
    gap = (first.date - d).days
    rate = daily_rate(points)
    if rate is None or gap > max_extrapolate_days:
        return None, True
    return max(first.value - rate * gap, 0.0), True


def monthly_volume(points: list[Point], month: date, today: Optional[date] = None) -> tuple[Optional[float], bool]:
    """Consumption in a calendar month from readings (month start → next month start)."""
    today = today or today_kyiv()
    start = month_start(month)
    nxt = add_months(start, 1)
    v0, e0 = value_at(points, start)
    if nxt > today:
        v1, e1 = value_at(points, today)
    else:
        v1, e1 = value_at(points, nxt)
    if v0 is None or v1 is None:
        return None, True
    return max(v1 - v0, 0.0), (e0 or e1)


# ---------------------------------------------------------------- heating / outages context

def heating_active(notes, d: date) -> bool:
    for n in notes:
        if n.kind == "heating" and n.date <= d and (n.end_date is None or n.end_date >= d):
            return True
    return False


def heating_months(notes, month: date) -> bool:
    ms, me = month_start(month), month_end(month)
    return any(n.kind == "heating" and n.date <= me and (n.end_date is None or n.end_date >= ms) for n in notes)


def outage_hours(outages, start: datetime, end: datetime, now: Optional[datetime] = None) -> float:
    """Hours without power inside [start, end) (naive UTC datetimes)."""
    now = now or utcnow()
    total = 0.0
    for o in outages:
        o_end = o.ended_at or now
        lo, hi = max(o.started_at, start), min(o_end, end)
        if hi > lo:
            total += (hi - lo).total_seconds() / 3600
    return total


def kyiv_month_bounds_utc(month: date) -> tuple[datetime, datetime]:
    s = datetime(month.year, month.month, 1, tzinfo=KYIV)
    n = add_months(month_start(month), 1)
    e = datetime(n.year, n.month, 1, tzinfo=KYIV)
    utc = ZoneInfo("UTC")
    return s.astimezone(utc).replace(tzinfo=None), e.astimezone(utc).replace(tzinfo=None)


# ---------------------------------------------------------------- tariffs

def meter_tariff(meter, bills) -> Optional[float]:
    """Current tariff: meter.tariff if set, else the latest bill line tariff for the meter."""
    if meter.tariff:
        return meter.tariff
    for b in sorted(bills, key=lambda b: b.period, reverse=True):
        for ln in b.lines:
            if ln.meter_id == meter.id and ln.tariff:
                return ln.tariff
    return None


def last_billed_value(meter, bills) -> tuple[Optional[float], Optional[date]]:
    """Meter value at the end of the newest billed period: the bill line value if the
    bill carries meter values, else our own readings interpolated at that date."""
    if not bills:
        return None, None
    newest = max(bills, key=lambda b: b.period)
    end = add_months(newest.period, 1)
    for ln in newest.lines:
        if ln.meter_id == meter.id and ln.curr_value is not None:
            return ln.curr_value, end
    v, _est = value_at(series(meter.readings), end)
    return v, end


# ---------------------------------------------------------------- meter summary

def meter_summary(meter, bills, notes, today: Optional[date] = None) -> dict:
    today = today or today_kyiv()
    pts = series(meter.readings)
    last = pts[-1] if pts else None
    rate = daily_rate(pts)
    tariff = meter_tariff(meter, bills)
    billed_value, billed_on = last_billed_value(meter, bills)

    # «набігло» з останньої платіжки (або з першого показника, якщо платіжок немає)
    since_value, since_date = billed_value, billed_on
    if since_value is None and pts:
        since_value, since_date = pts[0].value, pts[0].date
    now_value, now_est = value_at(pts, today)
    since_volume = None
    if since_value is not None and now_value is not None:
        since_volume = max(now_value - since_value, 0.0)

    # поточний місяць: факт + прогноз до кінця місяця
    m0 = month_start(today)
    mtd, _ = monthly_volume(pts, m0, today)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    left = days_in_month - today.day + 1 if mtd is not None else days_in_month
    month_forecast = None
    if rate is not None:
        month_forecast = (mtd or 0.0) + rate * max(left - 1, 0) if mtd is not None else rate * days_in_month

    # торік у цьому ж місяці (сезонність)
    ly_volume, _ = monthly_volume(pts, add_months(m0, -12), today)

    return {
        "id": meter.id, "name": meter.name, "utility_type": meter.utility_type, "unit": meter.unit,
        "zone": meter.zone, "provider_id": meter.provider_id, "tariff": tariff, "is_active": meter.is_active,
        "last_value": last.value if last else None, "last_date": str(last.date) if last else None,
        "days_since_reading": (today - last.date).days if last else None,
        "daily_rate": r2(rate),
        "since_billed_volume": r2(since_volume), "since_billed_date": str(since_date) if since_date else None,
        "since_billed_cost": r2(since_volume * tariff) if (since_volume is not None and tariff) else None,
        "month_to_date": r2(mtd), "month_forecast": r2(month_forecast),
        "month_forecast_cost": r2(month_forecast * tariff) if (month_forecast is not None and tariff) else None,
        "last_year_month": r2(ly_volume),
        "heating_on": heating_active(notes, today),
    }


# ---------------------------------------------------------------- provider balance

def _manual_avg(bills, n: int = 3) -> Optional[float]:
    vals = [b.accrued for b in sorted(bills, key=lambda b: b.period)[-n:] if b.accrued]
    return sum(vals) / len(vals) if vals else None


def provider_balance(provider, meters, bills, payments, notes, today: Optional[date] = None) -> dict:
    """Debt / accrued-since / next-bill forecast for one provider."""
    today = today or today_kyiv()
    bills = sorted(bills, key=lambda b: b.period)
    payments = sorted(payments, key=lambda p: p.date)
    last_payment = payments[-1] if payments else None
    res = {
        "debt": 0.0, "accrued_since": 0.0, "to_pay_now": 0.0, "next_bill_forecast": None,
        "estimated": False, "basis": "", "last_bill": None, "next_due": None,
        "last_payment": ({"date": str(last_payment.date), "amount": last_payment.amount} if last_payment else None),
    }

    if provider.service in FIXED_SERVICES or (provider.billing == "fixed" and not bills):
        return {**res, **_fixed_ledger(provider, payments, today)}

    if bills:
        last = bills[-1]
        pend = month_end(last.period)
        paid_after = sum(p.amount for p in payments if p.date > pend)
        debt = last.to_pay - paid_after
        unbilled_from = add_months(last.period, 1)
        res["last_bill"] = {"id": last.id, "period": str(last.period), "to_pay": last.to_pay, "accrued": last.accrued}
        res["basis"] = "bill"
    else:
        start = provider.start_date or (payments[0].date if payments else today)
        debt = (provider.opening_balance or 0.0) - sum(p.amount for p in payments if p.date >= start)
        unbilled_from = month_start(start)
        res["basis"] = "opening" if provider.opening_balance else "none"

    accrued_since, next_bill, est = _unbilled_estimate(provider, meters, bills, notes, unbilled_from, today)
    res.update({
        "debt": r2(debt), "accrued_since": r2(accrued_since), "next_bill_forecast": r2(next_bill),
        "to_pay_now": r2(max(debt + (accrued_since or 0.0), 0.0)), "estimated": est,
    })
    if provider.due_day:
        nd = due_date(today, provider.due_day)
        res["next_due"] = str(nd if nd >= today else due_date(add_months(month_start(today), 1), provider.due_day))
    return res


def _unbilled_estimate(provider, meters, bills, notes, unbilled_from: date, today: date):
    """(accrued since the last bill up to today, forecast of the next bill, estimated?)."""
    if today < unbilled_from:
        return 0.0, None, False
    elapsed_months = ((today - unbilled_from).days + 1) / AVG_MONTH_DAYS
    if provider.billing == "fixed":
        amt = provider.fixed_amount or (_manual_avg(bills) or 0.0)
        return amt * elapsed_months, amt, True
    if provider.billing == "manual" or not meters:
        avg = _manual_avg(bills)
        if avg is None:
            return 0.0, None, True
        return avg * elapsed_months, avg, True

    accrued, forecast = 0.0, 0.0
    have_forecast = False
    for m in meters:
        s = meter_summary(m, bills, notes, today)
        tariff = s["tariff"] or 0.0
        if s["since_billed_volume"] is not None:
            accrued += s["since_billed_volume"] * tariff
        pts = series(m.readings)
        vol, _ = monthly_volume(pts, unbilled_from, today)
        if month_end(unbilled_from) >= today or vol is None:
            rate = daily_rate(pts)
            vol = rate * calendar.monthrange(unbilled_from.year, unbilled_from.month)[1] if rate is not None else None
        if vol is not None:
            forecast += vol * tariff
            have_forecast = True
    return accrued, (forecast if have_forecast else None), True


def _fixed_ledger(provider, payments, today: date) -> dict:
    """Rent / mortgage / fixed charges: monthly charge due on due_day, paid in advance.
    Returns debt, paid_until, next charge and per-month punctuality history."""
    amount = provider.fixed_amount or 0.0
    if amount <= 0 and payments:
        # amount not set (e.g. internet template): assume the usual payment, never a growing overpay
        recent = [p.amount for p in payments[-3:] if p.amount > 0]
        amount = sum(recent) / len(recent) if recent else 0.0
    start = month_start(provider.start_date or (payments[0].date if payments else today))
    opening = provider.opening_balance or 0.0
    pays = [p for p in payments if p.date >= start - timedelta(days=31)]
    total_paid = sum(p.amount for p in pays)
    due_months = [m for m in month_iter(start, today) if due_date(m, provider.due_day) <= today]
    debt = opening + amount * len(due_months) - total_paid if amount > 0 else 0.0

    history, paid_until, next_charge = [], None, None
    if amount > 0:
        # cumulative coverage: which payment closed each month
        credit = -opening
        cum_dates: list[tuple[float, date]] = []
        running = credit
        for p in pays:
            running += p.amount
            cum_dates.append((running, p.date))
        covered = int((credit + total_paid + 1e-6) // amount)
        if covered > 0:
            paid_until = month_end(add_months(start, covered - 1))
        horizon = max(len(due_months), covered)
        for i in range(horizon):  # full history: an old unpaid month must stay visible
            m = add_months(start, i)
            need = amount * (i + 1)
            closed = next((d for c, d in cum_dates if c + 1e-6 >= need), None)
            if credit + 1e-6 >= need:
                closed = start
            dd = due_date(m, provider.due_day)
            history.append({
                "month": str(m), "due": str(dd), "paid_on": str(closed) if closed else None,
                "days_late": (closed - dd).days if closed and closed > dd else (0 if closed else None),
                "status": "paid" if closed else ("overdue" if dd <= today else "upcoming"),
            })
        nm = add_months(start, covered)
        next_charge = {"month": str(nm), "due": str(due_date(nm, provider.due_day)), "amount": amount}
    late = [h for h in history if h["days_late"]]
    overdue = [h for h in history if h["status"] == "overdue"]
    return {
        "debt": r2(debt), "accrued_since": 0.0, "to_pay_now": r2(max(debt, 0.0)),
        "next_bill_forecast": amount or None, "estimated": False, "basis": "fixed",
        "paid_until": str(paid_until) if paid_until else None, "next_charge": next_charge,
        "next_due": next_charge["due"] if next_charge else None,
        "history": history[-12:],
        "overdue_months": len(overdue), "overdue_since": overdue[0]["due"] if overdue else None,
        "punctuality": {"months": len([h for h in history if h["status"] == "paid"]), "late": len(late),
                        "max_days_late": max((h["days_late"] for h in late), default=0)},
    }


# ---------------------------------------------------------------- bill checks (reconciliation)

def bill_flags(bill, prev_bill, payments, meters_by_id: dict, all_bills=None) -> list[dict]:
    """Checks that catch provider mistakes: arithmetic, debt continuity, payments,
    meter continuity, billed vs own readings, tariff changes."""
    flags: list[dict] = []

    def add(level, code, text, diff=None):
        flags.append({"level": level, "code": code, "text": text, "diff": r2(diff)})

    expected = (bill.opening_balance or 0) - (bill.paid or 0) + (bill.accrued or 0) + (bill.adjustment or 0)
    if abs(expected - (bill.to_pay or 0)) > MONEY_EPS:
        add("warn", "arithmetic",
            f"«До сплати» {bill.to_pay:.2f} не сходиться: борг {bill.opening_balance:.2f} − сплачено "
            f"{bill.paid:.2f} + нараховано {bill.accrued:.2f} = {expected:.2f}", bill.to_pay - expected)

    if prev_bill is not None and prev_bill.period == add_months(bill.period, -1):
        diff = (bill.opening_balance or 0) - (prev_bill.to_pay or 0)
        if abs(diff) > MONEY_EPS:
            add("warn", "continuity",
                f"Борг на початок {bill.opening_balance:.2f} ≠ «до сплати» з минулої платіжки "
                f"{prev_bill.to_pay:.2f} (різниця {diff:+.2f} ₴) — перевірте перерахунок", diff)

    ms, me = month_start(bill.period), month_end(bill.period)
    ours = sum(p.amount for p in payments if ms <= p.date <= me)
    if payments and abs(ours - (bill.paid or 0)) > MONEY_EPS:
        add("warn" if ours > (bill.paid or 0) else "info", "payments",
            f"У платіжці сплачено {bill.paid:.2f}, а у вас записано {ours:.2f} за цей місяць", (bill.paid or 0) - ours)

    for ln in bill.lines:
        m = meters_by_id.get(ln.meter_id)
        if ln.prev_value is not None and ln.curr_value is not None:
            vol = ln.curr_value - ln.prev_value
            if ln.volume is not None and abs(vol - ln.volume) > 0.01:
                add("warn", "volume", f"{ln.label or 'Лічильник'}: {ln.curr_value:g} − {ln.prev_value:g} = {vol:g}, "
                                      f"а в платіжці {ln.volume:g}", ln.volume - vol)
        if ln.volume is not None and ln.tariff and ln.amount is not None:
            calc = ln.volume * ln.tariff
            if abs(calc - ln.amount) > MONEY_EPS:
                add("warn", "line_amount", f"{ln.label or 'Рядок'}: {ln.volume:g} × {ln.tariff:g} = {calc:.2f}, "
                                           f"а в платіжці {ln.amount:.2f}", ln.amount - calc)
        adjacent = prev_bill is not None and prev_bill.period == add_months(bill.period, -1)
        if adjacent and m is not None and ln.prev_value is not None:
            pl = next((x for x in prev_bill.lines if x.meter_id == ln.meter_id), None)
            if pl is not None and pl.curr_value is not None and abs(pl.curr_value - ln.prev_value) > 0.01:
                add("warn", "meter_continuity",
                    f"{m.name}: попередній показник {ln.prev_value:g} ≠ поточному з минулої платіжки {pl.curr_value:g}",
                    ln.prev_value - pl.curr_value)
            if pl is not None and pl.tariff and ln.tariff and abs(pl.tariff - ln.tariff) > 0.005:
                add("info", "tariff", f"{m.name}: тариф змінився {pl.tariff:g} → {ln.tariff:g}", ln.tariff - pl.tariff)
        if m is not None and ln.curr_value is not None:
            pts = series(m.readings)
            own, est = value_at(pts, add_months(bill.period, 1), max_extrapolate_days=7)
            if own is not None and not est:
                diff = ln.curr_value - own
                tariff = ln.tariff or m.tariff or 0
                threshold = max(abs(ln.volume or 0) * 0.05, 3.0)
                if abs(diff) > threshold:
                    add("warn", "reading_mismatch",
                        f"{m.name}: у платіжці {ln.curr_value:g}, а за вашими показниками на "
                        f"{add_months(bill.period, 1):%d.%m} ≈ {own:.0f} ({diff:+.0f} {m.unit}"
                        + (f", ≈ {diff * tariff:+.0f} ₴)" if tariff else ")"), diff)
    return flags


# ---------------------------------------------------------------- bill draft

def bill_draft(provider, meters, bills, payments, period: date) -> dict:
    """Prefilled bill for quick entry: previous debt, payments in the month, meter lines."""
    period = month_start(period)
    prev = None
    for b in sorted(bills, key=lambda b: b.period):
        if b.period < period:
            prev = b
    opening = prev.to_pay if prev is not None else (provider.opening_balance or 0.0)
    ms, me = period, month_end(period)
    paid = sum(p.amount for p in payments if ms <= p.date <= me)
    lines, accrued = [], 0.0
    if provider.billing == "metered":
        for m in meters:
            pts = series(m.readings)
            pl = next((x for x in prev.lines if x.meter_id == m.id), None) if prev is not None else None
            prev_v = pl.curr_value if pl is not None and pl.curr_value is not None else value_at(pts, ms)[0]
            curr_v, est = value_at(pts, add_months(ms, 1), max_extrapolate_days=10)
            prev_v = round(prev_v) if prev_v is not None else None
            curr_v = round(curr_v) if curr_v is not None else None
            tariff = meter_tariff(m, bills)
            vol = (curr_v - prev_v) if (curr_v is not None and prev_v is not None) else None
            amount = r2(vol * tariff) if (vol is not None and tariff) else None
            accrued += amount or 0.0
            lines.append({"meter_id": m.id, "label": m.name, "prev_value": prev_v, "curr_value": curr_v,
                          "volume": vol, "tariff": tariff, "amount": amount, "estimated": est})
    elif provider.billing == "fixed":
        accrued = provider.fixed_amount or (_manual_avg(bills) or 0.0)
    else:
        accrued = _manual_avg(bills) or 0.0
    return {"provider_id": provider.id, "period": str(period), "issued_on": str(today_kyiv()),
            "opening_balance": r2(opening), "paid": r2(paid), "accrued": r2(accrued), "adjustment": 0.0,
            "to_pay": r2(opening - paid + accrued), "lines": lines}
