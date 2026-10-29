# Аналітика за місяць і бюджети по категоріях.
from datetime import date, timedelta

from app import models
from app.services import analytics as A
from tests.conftest import BOT_HEADERS, client, make_tx


def _hdr(fid):
    return {**BOT_HEADERS, "X-Family-Id": str(fid)}


def test_month_analytics_compares_with_previous_and_average(seeded, db):
    fam, u, c = seeded["family"], seeded["admin"], seeded["cats"]
    make_tx(db, fam.id, u.id, c["Продукти"].id, 1000, "Витрати", date="2026-09-10")
    make_tx(db, fam.id, u.id, c["Продукти"].id, 2000, "Витрати", title="Фора", date="2026-10-05")
    make_tx(db, fam.id, u.id, c["Кафе"].id, 500, "Витрати", title="Кава", date="2026-10-06")
    make_tx(db, fam.id, u.id, c["Зарплата"].id, 10000, "Поповнення", date="2026-10-07")
    make_tx(db, fam.id, u.id, c["Продукти"].id, 300, "Витрати", date="2026-10-08", currency="USD")
    jar_like = make_tx(db, fam.id, u.id, None, 700, "Поповнення", date="2026-10-09")
    jar = models.Jar(family_id=fam.id, name="J", goal=1, balance=0)
    db.add(jar); db.flush(); jar_like.jar_id = jar.id; db.commit()
    a = A.month_analytics(db, fam.id, date(2026, 10, 1), today=date(2026, 10, 22))
    assert a["expense"] == 2500 and a["income"] == 10000 and a["prev"]["expense"] == 1000
    prod = next(x for x in a["categories"] if x["name"] == "Продукти")
    assert prod["amount"] == 2000 and prod["prev"] == 1000 and round(prod["avg3"], 2) == 333.33
    assert a["other_currencies"]["USD"]["expense"] == 300
    assert a["forecast_expense"] == round(2500 / 22 * 31, 2)
    assert len(a["trend"]) == 12 and a["trend"][-1]["month"] == "2026-10-01"
    assert a["top_merchants"][0] == {"title": "Фора", "amount": 2000, "count": 1}


def test_past_month_has_no_forecast(seeded, db):
    fam = seeded["family"]
    a = A.month_analytics(db, fam.id, date(2026, 8, 1), today=date(2026, 10, 22))
    assert a["forecast_expense"] is None and a["days_elapsed"] == 31 and a["is_current"] is False


def test_budgets_crud_status_and_suggest(seeded, db):
    fam, u, c = seeded["family"], seeded["admin"], seeded["cats"]
    today = date.today()
    prev = (today.replace(day=1) - timedelta(days=1)).replace(day=10)
    for i in range(3):
        d = (today.replace(day=1) - timedelta(days=1 + 31 * i)).replace(day=10)
        make_tx(db, fam.id, u.id, c["Продукти"].id, 3000, "Витрати", date=d)
    make_tx(db, fam.id, u.id, c["Продукти"].id, 9000, "Витрати", date=today)
    sug = client.get(f"/families/{fam.id}/budgets/suggest", headers=_hdr(fam.id)).json()
    p = next(s for s in sug if s["name"] == "Продукти")
    assert p["suggested"] == 3200.0 and p["avg3"] == 3000
    r = client.post(f"/families/{fam.id}/budgets/bulk", headers=_hdr(fam.id),
                    json={"items": [{"category_id": c["Продукти"].id, "amount": 8000}]}).json()
    item = r["items"][0]
    assert item["spent"] == 9000 and item["status"] == "over" and item["remaining"] == -1000
    # analytics shows the budget next to the category
    a = client.get(f"/families/{fam.id}/analytics", headers=_hdr(fam.id)).json()
    assert next(x for x in a["categories"] if x["name"] == "Продукти")["budget"] == 8000
    # remove
    r = client.put(f"/families/{fam.id}/budgets/{c['Продукти'].id}", headers=_hdr(fam.id), json={"amount": None}).json()
    assert r["items"] == []
    assert prev  # silence unused


def test_budget_rejects_income_and_foreign_category(seeded, db):
    fam, c = seeded["family"], seeded["cats"]
    assert client.put(f"/families/{fam.id}/budgets/{c['Зарплата'].id}", headers=_hdr(fam.id), json={"amount": 100}).status_code == 400
    other = models.Family(name="O", invite_code="o1"); db.add(other); db.flush()
    oc = models.Category(family_id=other.id, icon="•", name="X", color="#000", type="expense"); db.add(oc); db.commit()
    assert client.put(f"/families/{fam.id}/budgets/{oc.id}", headers=_hdr(fam.id), json={"amount": 100}).status_code == 404


def test_budget_reminder_once_per_level(seeded, db):
    from app.api.housing import compute_reminders
    fam, u, c = seeded["family"], seeded["admin"], seeded["cats"]
    client.put(f"/families/{fam.id}/budgets/{c['Кафе'].id}", headers=_hdr(fam.id), json={"amount": 1000})
    make_tx(db, fam.id, u.id, c["Кафе"].id, 850, "Витрати", date=date.today())
    rem = [r for r in compute_reminders(db) if r["family_id"] == fam.id]
    assert rem and "85%" in rem[0]["text"] and rem[0]["tab"] == "analytics"
    client.post("/system/housing/reminders/ack", headers=BOT_HEADERS,
                json={"items": [{"family_id": fam.id, "key": k} for k in rem[0]["keys"]]})
    assert [r for r in compute_reminders(db) if r["family_id"] == fam.id] == []


def test_transactions_filter_by_month_and_category(seeded, db):
    fam, u, c = seeded["family"], seeded["admin"], seeded["cats"]
    make_tx(db, fam.id, u.id, c["Кафе"].id, 10, "Витрати", date="2026-09-01")
    make_tx(db, fam.id, u.id, c["Кафе"].id, 20, "Витрати", date="2026-10-01")
    make_tx(db, fam.id, u.id, c["Продукти"].id, 30, "Витрати", date="2026-10-02")
    r = client.get(f"/families/{fam.id}/transactions?month=2026-10&category_id={c['Кафе'].id}", headers=_hdr(fam.id)).json()
    assert [t["amount"] for t in r] == [20]


def test_refund_lowers_category_spending_not_income(seeded, db):
    # friends paid back their share of a Fora purchase: −expense in «Продукти», not income
    fam, u, c = seeded["family"], seeded["admin"], seeded["cats"]
    today = date.today()
    make_tx(db, fam.id, u.id, c["Продукти"].id, 1414, "Витрати", title="Фора", date=today)
    gift = make_tx(db, fam.id, u.id, c["Продукти"].id, 500, "Поповнення", title="подарунок", date=today)  # no mark → income
    r = client.post("/transactions", headers=BOT_HEADERS, json={
        "family_id": fam.id, "user_id": u.id, "category_id": c["Продукти"].id, "amount": 249, "type": "Поповнення",
        "title": "Від: Dubovyk David", "account": "Монобанк", "date": today.isoformat(), "refund": True})
    assert r.json()["refund"] is True
    a = A.month_analytics(db, fam.id, today.replace(day=1), today=today)
    assert a["expense"] == 1414 - 249 and a["income"] == 500
    assert next(x for x in a["categories"] if x["name"] == "Продукти")["amount"] == 1165
    client.post(f"/families/{fam.id}/budgets/bulk", headers=_hdr(fam.id), json={"items": [{"category_id": c["Продукти"].id, "amount": 1200}]})
    assert A.budgets_status(db, fam.id, today.replace(day=1), today=today)["items"][0]["spent"] == 1165
    st = client.get(f"/families/{fam.id}/stats", headers=_hdr(fam.id)).json()
    assert st["expense"] == 1165 and st["income"] == 500
    # moved to an income category → the mark goes by itself
    r = client.put(f"/transactions/{r.json()['id']}", headers=BOT_HEADERS, json={"category_id": c["Зарплата"].id})
    assert r.json()["refund"] is False and gift.refund is False


def test_work_owed_counts_costs_fees_and_reimbursements(seeded, db):
    from app import models
    fam, u = seeded["family"], seeded["admin"]
    work = models.Category(family_id=fam.id, icon="💼", color="#000", name="Робочі витрати", type="expense")
    db.add(work); db.commit()
    today = date.today()
    assert client.get(f"/families/{fam.id}/stats", headers=_hdr(fam.id)).json()["work"] is None
    fam.work_payer, fam.work_since, fam.work_opening = "Прего", today, -473
    db.commit()
    make_tx(db, fam.id, u.id, work.id, 2384, "Витрати", title="GMhost", date=today)
    make_tx(db, fam.id, u.id, work.id, 690, "Витрати", title="підтримка (послуга)", date=today)
    back = make_tx(db, fam.id, u.id, work.id, 1000, "Поповнення", title="City24", date=today)
    back.refund = True
    make_tx(db, fam.id, u.id, work.id, 999, "Витрати", title="before", date=today.replace(year=today.year - 1))
    db.commit()
    w = client.get(f"/families/{fam.id}/stats", headers=_hdr(fam.id)).json()["work"]
    assert w == {"payer": "Прего", "owed": -473 + 2384 + 690 - 1000}
