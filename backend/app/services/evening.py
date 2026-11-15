"""Вечірній звіт (бот, 21:00): день і тиждень проти плану сім'ї, простою мовою, з підказкою, що робити далі.

План (family_plans.data) синхронізується зі сторінки плану власника скриптом ~/server/budget/sync:
  life / lean / lean_to — гроші на щоденне на місяць (lean діє до lean_to), events — заплановані події
  (k: inc | fix | util | wish | ny | save | note, a: сума, − = витрата), series — [дата, вільні гроші, подушка]
  на кінець кожного дня, start — вільні гроші на старт, limit — кредитний ліміт, tips — підказки по періодах.
«Щоденне» = усі витрати, крім оренди, кредитів/розстрочок, комуналки, робочих і візажу, а також покупок, які
збігаються з плановими (сума ±30 %, дата ±7 днів) — вони вже сидять у плані окремими рядками.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app import crud, models
from app.services.analytics import UAH, budgets_status, spent
from app.services.housing import month_start

NOT_LIFE = ("Оренда", "Кредити", "Комуналка", "Робочі", "Візаж")
BIG = 1000  # разова покупка: від цієї суми питаємо «чи була вона в плані»
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "нд"]


def fmt(v: float) -> str:
    return ("−" if v < 0 else "") + f"{abs(round(v)):,}".replace(",", " ")


def dm(d: date) -> str:
    return f"{d.day}.{d.month:02d}"


def cut(s: str, n: int = 60) -> str:
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0].rstrip(" ,—–(") + "…"


def load_plan(db: Session, fid: int) -> Optional[dict]:
    row = db.get(models.FamilyPlan, fid)
    return json.loads(row.data) if row else None


def per_day(plan: Optional[dict], d: date, fallback: float) -> float:
    if not plan:
        return fallback
    month = plan["lean"] if d.isoformat() < plan.get("lean_to", "") else plan["life"]
    return month * 12 / 365


def week_start(d: date) -> date:
    """Тиждень у плані — з неділі («Неділя — новий тиждень»)."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


def is_life(t) -> bool:
    name = t.category.name if t.category else ""
    return t.obligation_id is None and (t.currency or UAH) == UAH and not any(x in name for x in NOT_LIFE)


def match_planned(txs, events: list) -> dict:
    """tx.id → planned event for big purchases that the plan already counts (biggest first, one event each)."""
    pool = [e for e in events if e["k"] in ("wish", "ny") and e["a"] < 0]
    out = {}
    for t in sorted((t for t in txs if spent(t) >= BIG), key=lambda t: -spent(t)):
        for e in pool:
            want = -e["a"]
            if abs((date.fromisoformat(e["d"]) - t.date).days) <= 7 and abs(spent(t) - want) <= max(0.3 * want, 150):
                out[t.id] = e
                pool.remove(e)
                break
    return out


_D = re.compile(r"(\d{1,2})(?:\.(\d{1,2}))?")


def tip_range(when: str, year0: int, month0: int) -> Optional[tuple[date, date]]:
    """«15–19.11 · Старт» / «20.11 · Аванс» / «22.12–6.01 · …» / «З 5.02 · …» → (from, to). Рік — від початку плану."""
    head = when.split("·")[0].strip()
    parts = _D.findall(head)
    if not parts:
        return None

    def mk(day, mon):
        m = int(mon)
        return date(year0 + (1 if m < month0 else 0), m, int(day))
    try:
        if head.lower().startswith("з "):
            return mk(*parts[0]), date(9999, 12, 31)
        end = parts[-1]
        start = parts[0] if parts[0][1] else (parts[0][0], end[1])
        return mk(*start), mk(*end)
    except ValueError:
        return None


def current_tip(plan: dict, today: date) -> Optional[tuple[str, dict]]:
    """('Сьогодні' | 'Завтра', tip): завтрашній новий період важливіший за поточний."""
    f = date.fromisoformat(plan["from"])
    spans = [(tip_range(t["when"], f.year, f.month), t) for t in plan.get("tips", [])]
    spans = [(r, t) for r, t in spans if r]
    tomorrow = today + timedelta(days=1)
    for r, t in spans:
        if r[0] == tomorrow:
            return "Завтра", t
    for r, t in reversed(spans):
        if r[0] <= today <= r[1]:
            return "Зараз", t
    return None


def plan_balance(plan: dict, d: date) -> Optional[float]:
    if d.isoformat() < plan["from"]:
        return sum(plan["start"].values())
    for day, bal, _c in plan["series"]:
        if day == d.isoformat():
            return bal
    return None


def free_money(db: Session, fid: int, bank: list) -> Optional[tuple[float, float]]:
    """Власні гроші на картках (без кредитного ліміту) + готівка в Bimi, лише гривні. None — банк недоступний."""
    if not bank:
        return None
    cards = sum(a.balance for u in bank for a in u.accounts if a.currency == UAH)
    cash = sum(c["balance"] for c in crud.get_cash_balance_by_user(db, fid) if (c.get("currency") or UAH) == UAH)
    return cards, cash


def build(db: Session, fid: int, bank: list, today: date) -> str:
    plan = load_plan(db, fid)
    budgets = {b["name"]: b for b in budgets_status(db, fid, month_start(today), today)["items"]}
    fallback = sum(b["amount"] for n, b in budgets.items() if not any(x in n for x in NOT_LIFE)) * 12 / 365
    ws = week_start(today)
    txs = (db.query(models.Transaction).filter(models.Transaction.family_id == fid,
                                               models.Transaction.date >= ws, models.Transaction.date <= today).all())
    life = [t for t in txs if spent(t) and is_life(t)]
    planned = match_planned(life, plan["events"]) if plan else {}
    daily = [t for t in life if t.id not in planned]
    day_out = sum(spent(t) for t in daily if t.date == today and spent(t) > 0)
    day_back = -sum(spent(t) for t in daily if t.date == today and spent(t) < 0)
    week_spent = sum(spent(t) for t in daily)
    week_budget = sum(per_day(plan, ws + timedelta(days=i), fallback) for i in range(7))
    left, days_left = week_budget - week_spent, 6 - (today - ws).days
    pd = per_day(plan, today, fallback)

    L = [f"🌙 Вечір {WD[today.weekday()]} {dm(today)}", ""]
    L.append(f"💸 Сьогодні на щоденне: {fmt(day_out)} ₴ (план ≈{fmt(pd)})" + (" ✅" if day_out - day_back <= pd * 1.1 else "")
             + (f" · ↩️ повернули {fmt(day_back)}" if day_back else ""))
    if days_left and left > 0:
        L.append(f"📅 Тиждень: {fmt(week_spent)} з {fmt(week_budget)} · до неділі ≈{fmt(left / days_left)} ₴ на день")
    else:
        L.append(f"📅 Тиждень: {fmt(week_spent)} з {fmt(week_budget)}"
                 + (f" · понад план {fmt(-left)} ₴" if left < 0 else " · у межах ✅"))
    for t, e in [(t, planned[t.id]) for t in life if t.id in planned and t.date == today]:
        L.append(f"🧾 За планом: {e['t']} — {fmt(spent(t))} ₴ ✅")
    extra = [t for t in daily if t.date == today and spent(t) >= BIG and "Продукти" not in (t.category.name if t.category else "")]
    for t in extra:
        L.append(f"⚠️ Не було в плані: {cut(t.title.replace('❓ ', ''), 40)} — {fmt(spent(t))} ₴")

    tips: list[str] = []
    if left < 0:
        tips.append(f"Тиждень уже понад план на {fmt(-left)} ₴ — до неділі лише необхідне.")
    if extra:
        tips.append("Покупка понад 1 000 — спершу в план: якщо це разове, наступні дні тиснемо; якщо потрібне ще — додамо в план.")

    if plan:
        money = free_money(db, fid, bank)
        expect = plan_balance(plan, today)
        if money is not None and expect is not None:
            actual = sum(money)
            delta = actual - expect
            L.append("")
            mark = "по плану ✅" if abs(delta) < 500 else (f"попереду на {fmt(delta)} ✅" if delta > 0 else f"позаду на {fmt(-delta)}")
            L.append(f"💰 Вільні гроші: {fmt(actual)} ₴ (картки {fmt(money[0])}, готівка {fmt(money[1])})")
            L.append(f"    за планом {fmt(expect)} → {mark}")
            future = [(d, b) for d, b, _c in plan["series"] if d > today.isoformat()]
            if future:
                d_min, b_min = min(future, key=lambda x: x[1])
                proj, lim = b_min + delta, plan.get("limit") or 0
                if b_min < 0 or proj < 0:
                    ok = "✅ в межах ліміту" if -proj <= lim else f"⚠️ більше за ліміт {fmt(lim)}"
                    L.append(f"📉 Найглибший мінус попереду: ≈{fmt(proj)} ₴ ({dm(date.fromisoformat(d_min))}) · {ok}")
                    if -proj > lim:
                        nxt = next((e for e in plan["events"] if e["d"] > today.isoformat() and e["k"] in ("wish", "ny")), None)
                        tips.append(f"Щоб влізти в ліміт, бракує ≈{fmt(-proj - lim)} ₴"
                                    + (f": найпростіше зсунути «{nxt['t']}» ({fmt(-nxt['a'])} ₴, {dm(date.fromisoformat(nxt['d']))})." if nxt else "."))
            if delta <= -1000:
                inc = next((e for e in plan["events"] if e["d"] > today.isoformat() and e["k"] == "inc"), None)
                if inc:
                    days = max((date.fromisoformat(inc["d"]) - today).days, 1)
                    by = dm(date.fromisoformat(inc["d"]))
                    if pd + delta / days >= pd / 2:
                        tips.append(f"Щоб наздогнати план до {by}, витрачаймо ≈{fmt(pd + delta / days)} ₴ на день замість {fmt(pd)}.")
                    else:
                        wish = next((e for e in plan["events"] if e["d"] > today.isoformat() and e["k"] in ("wish", "ny")), None)
                        tips.append(f"Відстаємо на {fmt(-delta)} ₴ — до {by} економією це не наздогнати"
                                    + (f": краще зменшити чи зсунути «{wish['t']}» ({fmt(-wish['a'])} ₴)." if wish else "."))
            elif delta >= 1000:
                tips.append("Ми попереду плану — не витрачаймо цей запас: "
                            + ("він у «Подушку»." if today.isoformat() >= plan.get("save_from", "9999") else "він згладить мінус на святах."))
        nxt = [e for e in plan["events"] if today.isoformat() < e["d"] <= (today + timedelta(days=7)).isoformat()
               and e["k"] != "save" and (e["a"] or e["k"] == "note")]
        if nxt:
            L.append("")
            L.append("🔜 Тиждень наперед:")
            for e in nxt[:6]:
                a = f" {'+' if e['a'] > 0 else ''}{fmt(e['a'])}" if e["a"] else ""
                L.append(f"  {dm(date.fromisoformat(e['d']))} {cut(e['t'])}{a}")

    hot = [b for b in budgets.values() if b["pct"] >= 80 and not any(x in b["name"] for x in NOT_LIFE)][:3]
    if hot:
        L.append("🎯 Ліміти місяця: " + " · ".join(f"{b['name']} {b['pct']:.0f}%" for b in hot))
    pending = (db.query(models.Transaction).join(models.Category, models.Transaction.category_id == models.Category.id)
               .filter(models.Transaction.family_id == fid, models.Category.name.contains("Очікує"),
                       models.Transaction.date >= today - timedelta(days=30)).count())
    if pending:
        L.append(f"❓ Нерозібраних операцій: {pending} — розберіть, щоб звіт був точним")

    tip = current_tip(plan, today) if plan else None
    if tips or tip:
        L.append("")
    for s in tips[:3]:
        L.append(f"💡 {s}")
    if tip:
        L.append(f"🗓 {tip[0]} · {tip[1]['when']}: {tip[1]['text']}")
    return "\n".join(L)
