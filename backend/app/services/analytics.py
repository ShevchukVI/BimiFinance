"""Monthly analytics and category budgets.

Rules (same as the Home stats): expenses = type «Витрати», incomes = «Поповнення» (or
«Дохід…»); jar operations and transfers are internal movements and never counted.
A refund (↩️ money back for a purchase) is not income: it lowers the expense of its category.
Category breakdown, budgets and trends are in UAH; other currencies only as totals.
"""
from __future__ import annotations

import calendar
import math
from collections import defaultdict
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app import models
from app.services.housing import add_months, month_end, month_start, today_kyiv

UAH = "UAH"
EXCLUDED_FROM_BUDGETS = ("Очікує", "Балансування", "Переказ")


def parse_month(value: Optional[str], today: Optional[date] = None) -> date:
    if not value:
        return month_start(today or today_kyiv())
    return date.fromisoformat(value[:7] + "-01")


def _is_income(t) -> bool:
    return (t.type == "Поповнення" or "Дохід" in (t.type or "")) and not t.refund


def spent(t) -> float:
    """Effect on spending: an expense +, a refund −, anything else 0 (jar moves and transfers excluded)."""
    if t.jar_id is not None or t.type == "Переказ":
        return 0.0
    return t.amount if t.type == "Витрати" else -t.amount if t.refund else 0.0


def _counted(t) -> bool:
    return t.jar_id is None and t.type != "Переказ"


def _txs(db: Session, fid: int, start: date, end: date):
    return (db.query(models.Transaction)
            .filter(models.Transaction.family_id == fid, models.Transaction.date >= start, models.Transaction.date <= end)
            .all())


def _clean(title: str) -> str:
    return (title or "").replace("❓ ", "").replace(" (нерозібрано)", "").replace(" (не розібрано)", "").strip()


def _month_totals(txs) -> dict:
    out = {"income": 0.0, "expense": 0.0}
    for t in txs:
        if not _counted(t) or (t.currency or UAH) != UAH:
            continue
        if spent(t):
            out["expense"] += spent(t)
        elif _is_income(t):
            out["income"] += t.amount
    return {k: round(v, 2) for k, v in out.items()}


def elapsed_days(month: date, today: date) -> tuple[int, int]:
    """(days counted so far, days in month): a past month counts fully, a future one as 0."""
    dim = calendar.monthrange(month.year, month.month)[1]
    if month_start(today) == month:
        return today.day, dim
    return (dim if month < month_start(today) else 0), dim


def month_analytics(db: Session, fid: int, month: date, today: Optional[date] = None) -> dict:
    today = today or today_kyiv()
    first = add_months(month, -11)
    txs = _txs(db, fid, first, month_end(month))
    cats = {c.id: c for c in db.query(models.Category).filter(models.Category.family_id == fid)}
    users = {u.id: u.name for u in db.query(models.User).join(models.FamilyMember).filter(models.FamilyMember.family_id == fid)}
    budgets = {b.category_id: b.amount for b in db.query(models.Budget).filter(models.Budget.family_id == fid)}

    by_month: dict[date, list] = defaultdict(list)
    for t in txs:
        by_month[month_start(t.date)].append(t)
    cur = by_month.get(month, [])
    prev_m, avg_months = add_months(month, -1), [add_months(month, -i) for i in (1, 2, 3)]

    def cat_sums(items) -> dict:
        s: dict = defaultdict(float)
        for t in items:
            if spent(t) and (t.currency or UAH) == UAH:
                s[t.category_id] += spent(t)
        return s

    cur_c, prev_c = cat_sums(cur), cat_sums(by_month.get(prev_m, []))
    avg_c: dict = defaultdict(float)
    for m in avg_months:
        for k, v in cat_sums(by_month.get(m, [])).items():
            avg_c[k] += v / 3
    totals = _month_totals(cur)
    prev_tot = _month_totals(by_month.get(prev_m, []))
    avg3_exp = round(sum(_month_totals(by_month.get(m, []))["expense"] for m in avg_months) / 3, 2)

    categories = []
    for cid in set(cur_c) | {k for k in budgets if k in cats}:
        c = cats.get(cid)
        name = c.name if c else "Без категорії"
        amount = round(cur_c.get(cid, 0.0), 2)
        categories.append({
            "category_id": cid, "name": name, "amount": amount,
            "prev": round(prev_c.get(cid, 0.0), 2), "avg3": round(avg_c.get(cid, 0.0), 2),
            "budget": budgets.get(cid), "share": round(amount / totals["expense"] * 100, 1) if totals["expense"] else 0.0,
            "pending": bool(c and "Очікує" in c.name),
        })
    categories.sort(key=lambda x: (-x["amount"], x["name"]))

    daily: dict = defaultdict(float)
    by_user: dict = defaultdict(float)
    merchants: dict = defaultdict(lambda: [0.0, 0])
    other_cur: dict = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    for t in cur:
        if not _counted(t):
            continue
        if (t.currency or UAH) != UAH:
            key = "expense" if spent(t) else "income" if _is_income(t) else None
            if key:
                other_cur[t.currency][key] = round(other_cur[t.currency][key] + (spent(t) or t.amount), 2)
            continue
        if not spent(t):
            continue
        daily[t.date.isoformat()] += spent(t)
        by_user[users.get(t.user_id, "—")] += spent(t)
        if t.refund:
            continue
        m = merchants[_clean(t.title)]
        m[0] += t.amount
        m[1] += 1

    done, dim = elapsed_days(month, today)
    forecast = round(totals["expense"] / done * dim, 2) if 0 < done < dim else None
    trend = []
    for i in range(11, -1, -1):
        m = add_months(month, -i)
        trend.append({"month": str(m), **_month_totals(by_month.get(m, []))})

    res = {
        "month": str(month), "is_current": month == month_start(today), "days_elapsed": done, "days_in_month": dim,
        **totals, "balance": round(totals["income"] - totals["expense"], 2),
        "prev": prev_tot, "avg3_expense": avg3_exp, "forecast_expense": forecast,
        "other_currencies": dict(other_cur),
        "categories": categories,
        "daily": [{"date": d, "expense": round(v, 2)} for d, v in sorted(daily.items())],
        "by_user": sorted(({"name": k, "expense": round(v, 2)} for k, v in by_user.items()), key=lambda x: -x["expense"]),
        "top_merchants": [{"title": k, "amount": round(v[0], 2), "count": v[1]}
                          for k, v in sorted(merchants.items(), key=lambda kv: -kv[1][0])[:5]],
        "trend": trend,
        "budget_total": round(sum(budgets.values()), 2) if budgets else None,
    }
    res["insights"] = _insights(res)
    return res


def _insights(a: dict) -> list[str]:
    out = []
    if a["prev"]["expense"] and a["days_elapsed"]:
        if not a["is_current"]:
            d = (a["expense"] / a["prev"]["expense"] - 1) * 100
            if abs(d) >= 10:
                out.append(f"Витрати {'більші' if d > 0 else 'менші'} на {abs(d):.0f}% ніж у попередньому місяці")
        elif a["forecast_expense"] and a["avg3_expense"]:
            d = (a["forecast_expense"] / a["avg3_expense"] - 1) * 100
            if abs(d) >= 10:
                out.append(f"Темп витрат {'вищий' if d > 0 else 'нижчий'} за звичний на {abs(d):.0f}% "
                           f"(прогноз ≈ {a['forecast_expense']:,.0f} ₴)".replace(",", " "))
    grow = [c for c in a["categories"] if not c["pending"] and c["avg3"] >= 300 and c["amount"] > c["avg3"] * 1.4]
    if grow:
        g = max(grow, key=lambda c: c["amount"] - c["avg3"])
        out.append(f"{g['name']}: {g['amount']:,.0f} ₴ — на {(g['amount'] / g['avg3'] - 1) * 100:.0f}% більше за середнє".replace(",", " "))
    if a["income"] > 0:
        rate = (a["income"] - a["expense"]) / a["income"] * 100
        out.append(f"Відкладено {rate:.0f}% доходу" if rate > 0 else f"Витрати перевищили дохід на {-rate:.0f}%")
    pending = sum(c["amount"] for c in a["categories"] if c["pending"])
    if pending and a["expense"] and pending / a["expense"] >= 0.15:
        out.append(f"{pending / a['expense'] * 100:.0f}% витрат без категорії — розберіть їх, щоб аналітика була точною")
    return out[:4]


# ---------------------------------------------------------------- budgets

def budgets_status(db: Session, fid: int, month: date, today: Optional[date] = None) -> dict:
    today = today or today_kyiv()
    budgets = db.query(models.Budget).filter(models.Budget.family_id == fid).all()
    cats = {c.id: c for c in db.query(models.Category).filter(models.Category.family_id == fid)}
    used: dict = defaultdict(float)
    for t in _txs(db, fid, month, month_end(month)):
        if spent(t) and (t.currency or UAH) == UAH:
            used[t.category_id] += spent(t)
    done, dim = elapsed_days(month, today)
    items = []
    for b in budgets:
        c = cats.get(b.category_id)
        s = round(used.get(b.category_id, 0.0), 2)
        fc = round(s / done * dim, 2) if 0 < done < dim else s
        pct = round(s / b.amount * 100, 1) if b.amount else 0.0
        status = "over" if s > b.amount else ("warn" if pct >= 80 or fc > b.amount * 1.05 else "ok")
        items.append({"category_id": b.category_id, "name": c.name if c else "—", "amount": b.amount, "spent": s,
                      "remaining": round(b.amount - s, 2), "pct": pct, "forecast": fc, "status": status,
                      "per_day_left": round(max(b.amount - s, 0) / (dim - done), 2) if 0 < dim - done and done else None})
    items.sort(key=lambda x: (-x["pct"], x["name"]))
    return {"month": str(month), "days_left": dim - done if done else dim, "items": items,
            "totals": {"amount": round(sum(i["amount"] for i in items), 2), "spent": round(sum(i["spent"] for i in items), 2),
                       "forecast": round(sum(i["forecast"] for i in items), 2)}}


def suggest_budgets(db: Session, fid: int, today: Optional[date] = None) -> list[dict]:
    """Average of the last 3 full months +5 %, rounded up to 100 ₴."""
    today = today or today_kyiv()
    m0 = month_start(today)
    start = add_months(m0, -3)
    cats = {c.id: c for c in db.query(models.Category).filter(models.Category.family_id == fid, models.Category.type == "expense")}
    sums: dict = defaultdict(float)
    for t in db.query(models.Transaction).filter(models.Transaction.family_id == fid, models.Transaction.date >= start,
                                                 models.Transaction.date < m0).all():
        if spent(t) and (t.currency or UAH) == UAH and t.category_id in cats:
            sums[t.category_id] += spent(t)
    budgets = {b.category_id: b.amount for b in db.query(models.Budget).filter(models.Budget.family_id == fid)}
    out = []
    for cid, total in sums.items():
        name = cats[cid].name
        if any(x in name for x in EXCLUDED_FROM_BUDGETS):
            continue
        avg = total / 3
        if avg < 100:
            continue
        out.append({"category_id": cid, "name": name, "avg3": round(avg, 2),
                    "suggested": float(math.ceil(avg * 1.05 / 100) * 100), "current": budgets.get(cid)})
    out.sort(key=lambda x: -x["avg3"])
    return out
