"""«Дані для ШІ»: one Markdown file with everything needed to plan the family budget in an ordinary AI chat
(works offline from Bimi — the owner forwards the file to Claude on the phone)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app import crud, models
from app.services.analytics import UAH, _clean, _is_income, _month_totals, _txs, budgets_status, spent
from app.services.housing import add_months, month_end, month_start, today_kyiv

DAYS = 90


def _m(v: Optional[float], cur: str = UAH) -> str:
    if v is None:
        return "—"
    s = f"{v:,.2f}".replace(",", " ").replace(".00", "")
    return s if cur == UAH else f"{s} {cur}"


def _kind(t) -> str:
    if t.jar_id is not None:
        return "скарбничка"
    if t.type == "Переказ" or crud.is_family_transfer(t):
        return "переказ"
    if crud.is_balancing(t):
        return "балансування"
    if t.refund:
        return "повернення"
    return "витрата" if t.type == "Витрати" else "дохід" if _is_income(t) else t.type


def build(db: Session, fid: int, bank: list, today: Optional[date] = None) -> str:
    """bank = family_bank_balances() output (list of BankUserBalancesOut), [] if Monobank is unreachable."""
    from app.api.obligations import list_obligations, upcoming  # local: api modules import services
    from app.api.housing import build_overview

    today = today or today_kyiv()
    fam = db.get(models.Family, fid)
    users = {u.id: u.name for u in crud.get_users(db, fid)}
    cats = {c.id: c.name for c in db.query(models.Category).filter(models.Category.family_id == fid)}
    L: list[str] = []
    w = L.append

    w(f"# Бюджет сім'ї «{fam.name}» — дані з Bimi на {today:%d.%m.%Y}")
    w("")
    w("Файл для планування бюджету в чаті з ШІ. Суми в гривнях, якщо не вказано інше. Правила обліку:")
    w("- «повернення» (↩️) — гроші, повернуті за покупку (друзі скинулись, робота компенсувала): це не дохід, а мінус витрата своєї категорії.")
    w("- «переказ» — рух грошей між членами сім'ї або між своїми рахунками: не дохід і не витрата.")
    w("- «скарбничка» — відкладання в цілі/банки: не витрата.")
    w("- «балансування» — виправлення залишку готівки до реальної суми: не дохід і не витрата.")
    w("- «Робочі витрати» — те, що член сім'ї оплачує за роботодавця, а той повертає (див. «винне»).")
    w("- «❓ Очікує» — операція з банку, ще не розкладена по категорії.")
    w(f"- Члени сім'ї: {', '.join(users.values())}.")
    w("")

    # ---- money now
    w("## Гроші зараз")
    for u in bank:
        for a in u.accounts:
            lim = f", кредитний ліміт {_m(a.credit_limit, a.currency)}, доступно {_m(a.available, a.currency)}" if a.credit_limit else ""
            w(f"- 💳 {u.user_name} · {a.name}{' ··' + a.last4 if a.last4 else ''}: власні кошти {_m(a.balance, a.currency)}{lim}")
    if not bank:
        w("- 💳 Банк: баланси карток зараз недоступні.")
    for c in crud.get_cash_balance_by_user(db, fid):
        w(f"- 💵 Готівка {c['user_name']}: {_m(c['balance'], c.get('currency') or UAH)} (за записами в Bimi)")
    for j in crud.get_jars(db, fid):
        w(f"- 🎯 Ціль «{j.name}»: {_m(j.balance, j.currency)} з {_m(j.goal, j.currency)}")
    work = crud.get_work_owed(db, fid)
    if work:
        o = work["owed"]
        w(f"- 💼 {work['payer']} винне: {_m(max(o, 0))}" + (f" (їхній запас у нас {_m(-o)})" if o < 0 else ""))
    w("")

    # ---- obligations
    obs = list_obligations(db, fid)
    w("## Кредити, розстрочки, підписки")
    for i in obs["items"]:
        s = i["state"]
        if s["status"] == "finished":
            continue
        kind = {"installment": "розстрочка", "loan": "кредит", "subscription": "підписка"}.get(i["kind"], i["kind"])
        parts = [f"{_m(i['amount'], i['currency'])}/{'рік' if i['period'] == 'year' else 'міс'}"]
        if i["due_day"]:
            parts.append(f"{i['due_day']}-го")
        if s.get("payments_total"):
            parts.append(f"сплачено {s['paid_count']} з {s['payments_total']}, лишилось {_m(s['remaining_amount'])}")
        if s.get("end"):
            parts.append(f"останній платіж {s['end']}")
        if s.get("next_due"):
            parts.append(f"наступний {s['next_due']}")
        w(f"- {i['name']} ({kind}): {', '.join(parts)}")
    t = obs["totals"]
    w(f"- Разом щомісяця: кредити/розстрочки {_m(t['credits_monthly'])}, підписки {_m(t['subscriptions_monthly'])}; "
      f"лишилось сплатити за кредитами {_m(t['remaining_total'])}")
    w("")

    w("## Найближчі платежі (31 день)")
    for p in upcoming(db, fid, days=31, today=today):
        w(f"- {p['date']}: {p['title']} — {_m(p['amount'], p['currency'])} ({p['sub']}{', прострочено' if p['status'] == 'overdue' else ''})")
    w("")

    try:
        ov = build_overview(db, fid, today)
    except Exception:
        ov = None
    if ov and ov.get("profile") and ov["profile"]["mode"] != "off":
        w("## Житло й комуналка")
        for p in ov["providers"]:
            b = p["balance"]
            bits = [f"до сплати зараз {_m(b.get('to_pay_now') or 0)}"]
            if b.get("debt"):
                bits.append(f"борг {_m(b['debt'])}")
            if b.get("next_bill_forecast"):
                bits.append(f"прогноз наступного рахунку {_m(b['next_bill_forecast'])}")
            if p.get("fixed_amount"):
                bits.append(f"фіксовано {_m(p['fixed_amount'])}/міс")
            w(f"- {p['name']}: {', '.join(bits)}")
        tt = ov["totals"]
        w(f"- Разом до сплати {_m(tt['to_pay_now'])}, прогноз на наступний місяць {_m(tt['next_month_forecast'])}")
        for a in ov["alerts"]:
            w(f"- ⚠️ {a.get('text', '')}")
        w("")

    # ---- months & categories
    cur_m = month_start(today)
    first = add_months(cur_m, -6)
    txs = _txs(db, fid, first, month_end(cur_m))
    by_month: dict = defaultdict(list)
    for x in txs:
        by_month[month_start(x.date)].append(x)
    w("## Помісячно (UAH; поточний місяць неповний)")
    w("| Місяць | Дохід | Витрати | Різниця |")
    w("|---|---|---|---|")
    for k in range(6, -1, -1):
        m = add_months(cur_m, -k)
        tot = _month_totals(by_month.get(m, []))
        w(f"| {m:%Y-%m}{' (до ' + today.strftime('%d.%m') + ')' if m == cur_m else ''} | {_m(tot['income'])} | {_m(tot['expense'])} | {_m(tot['income'] - tot['expense'])} |")
    w("")

    full = [add_months(cur_m, -k) for k in (3, 2, 1)]
    per: dict = defaultdict(lambda: defaultdict(float))
    for m in full + [cur_m]:
        for x in by_month.get(m, []):
            if spent(x) and (x.currency or UAH) == UAH:
                per[x.category_id][m] += spent(x)
    w(f"## Витрати по категоріях (середнє за {full[0]:%m.%Y}–{full[-1]:%m.%Y} і поточний місяць)")
    w("| Категорія | Середнє/міс | " + " | ".join(f"{m:%m.%Y}" for m in full) + f" | {cur_m:%m.%Y} (неповний) |")
    w("|---|---|" + "---|" * (len(full) + 1))
    rows = sorted(per.items(), key=lambda kv: -sum(kv[1][m] for m in full))
    for cid, vals in rows:
        avg = sum(vals[m] for m in full) / len(full)
        w(f"| {cats.get(cid, 'Без категорії')} | {_m(round(avg, 2))} | " + " | ".join(_m(round(vals[m], 2)) for m in full)
          + f" | {_m(round(vals[cur_m], 2))} |")
    w("")

    bs = budgets_status(db, fid, cur_m, today=today)
    if bs["items"]:
        w(f"## Бюджети (ліміти) на {cur_m:%m.%Y}, лишилось днів: {bs['days_left']}")
        for b in bs["items"]:
            w(f"- {b['name']}: ліміт {_m(b['amount'])}, витрачено {_m(b['spent'])}, лишилось {_m(b['remaining'])}, прогноз {_m(b['forecast'])}")
        w("")

    # ---- raw operations
    since = today - timedelta(days=DAYS)
    ops = sorted((x for x in _txs(db, fid, since, today)), key=lambda x: (x.date, x.id))
    w(f"## Усі операції за {DAYS} днів ({since:%d.%m.%Y}–{today:%d.%m.%Y}), {len(ops)} шт.")
    w("Формат: дата;хто;вид;сума;валюта;категорія;рахунок;опис")
    w("```csv")
    for x in ops:
        title = _clean(x.title).replace(";", ",").replace("\n", " ")
        note = f" ({x.note})" if x.note else ""
        w(f"{x.date};{users.get(x.user_id, '—')};{_kind(x)};{x.amount:g};{x.currency or UAH};"
          f"{cats.get(x.category_id, '—')};{x.account};{title}{note.replace(';', ',')}")
    w("```")
    return "\n".join(L) + "\n"
