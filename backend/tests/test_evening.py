# Вечірній звіт: тиждень з неділі, планові покупки не з'їдають щоденне, періоди підказок, вільні гроші проти плану.
import json
from datetime import date, datetime
from types import SimpleNamespace as NS

from app import models
from app.services import evening as E
from tests.conftest import BOT_HEADERS, client, make_tx

PLAN = {
    "from": "2026-11-16", "to": "2027-02-28", "start": {"card": -1000, "cash": 4000, "anna": -3000},
    "limit": 15000, "life": 24800, "lean": 20000, "lean_to": "2027-01-07", "save_from": "2027-02-05",
    "events": [
        {"d": "2026-11-16", "k": "wish", "t": "Заправка газ", "a": -2750},
        {"d": "2026-11-20", "k": "inc", "t": "Аванс", "a": 17809},
        {"d": "2026-11-20", "k": "wish", "t": "Лампа", "a": -4100},
    ],
    "series": [["2026-11-16", -800, 0], ["2026-11-17", -1450, 0], ["2026-11-20", 9000, 0], ["2027-01-03", -8558, 0]],
    "tips": [{"when": "15–19.11 · Старт", "text": "Лише необхідне."}, {"when": "20.11 · Аванс", "text": "Закрити мінус."},
             {"when": "22.12–6.01 · Свята", "text": "x"}, {"when": "З 5.02 · Подушка", "text": "y"}],
}


def test_tip_ranges_and_week_start():
    assert E.tip_range("15–19.11 · Старт", 2026, 11) == (date(2026, 11, 15), date(2026, 11, 19))
    assert E.tip_range("22.12–6.01 · Свята", 2026, 11) == (date(2026, 12, 22), date(2027, 1, 6))
    assert E.tip_range("7–21.01 · Вихід", 2026, 11) == (date(2027, 1, 7), date(2027, 1, 21))
    assert E.tip_range("З 5.02 · Подушка", 2026, 11)[0] == date(2027, 2, 5)
    assert E.current_tip(PLAN, date(2026, 11, 19))[0] == "Завтра"  # 20.11 — новий період
    assert E.current_tip(PLAN, date(2026, 11, 17))[1]["when"].startswith("15–19.11")
    assert E.week_start(date(2026, 11, 15)) == date(2026, 11, 15)  # неділя
    assert E.week_start(date(2026, 11, 21)) == date(2026, 11, 15)  # субота


def test_evening_report_plan_vs_fact(seeded, db):
    fam, u, c = seeded["family"], seeded["admin"], seeded["cats"]
    rent = models.Category(family_id=fam.id, icon="•", name="🏠 Оренда", color="#000", type="expense")
    db.add(rent)
    db.add(models.FamilyPlan(family_id=fam.id, data=json.dumps(PLAN), synced_at=datetime(2026, 11, 15)))
    db.commit()
    make_tx(db, fam.id, u.id, c["Продукти"].id, 500, "Витрати", account="Mono", date="2026-11-16")
    make_tx(db, fam.id, u.id, c["Інше"].id, 2700, "Витрати", title="WOG газ", account="Mono", date="2026-11-17")  # = план «Заправка»
    make_tx(db, fam.id, u.id, c["Кафе"].id, 300, "Витрати", account="Mono", date="2026-11-17")
    make_tx(db, fam.id, u.id, c["Інше"].id, 1900, "Витрати", title="Rozetka", account="Mono", date="2026-11-17")  # поза планом
    back = make_tx(db, fam.id, u.id, c["Кафе"].id, 100, "Поповнення", account="Mono", date="2026-11-17")
    back.refund = True
    db.commit()
    make_tx(db, fam.id, u.id, rent.id, 3500, "Витрати", account="Mono", date="2026-11-17")  # не щоденне
    bank = [NS(accounts=[NS(currency="UAH", balance=-2000.0), NS(currency="USD", balance=50.0)])]
    text = E.build(db, fam.id, bank, date(2026, 11, 17))
    assert "Сьогодні на щоденне: 2 200 ₴ (план ≈658) · ↩️ повернули 100" in text  # 300 кафе + 1 900 Rozetka; газ і оренда — ні
    assert "За планом: Заправка газ — 2 700 ₴" in text
    assert "Не було в плані: Rozetka — 1 900 ₴" in text
    assert "Тиждень: 2 600 з" in text
    assert "Вільні гроші: −2 000 ₴ (картки −2 000, готівка 0)\n    за планом −1 450 → позаду на 550" in text
    assert "−9 108 ₴ (3.01) · ✅ в межах ліміту" in text
    assert "20.11 Аванс +17 809" in text and "20.11 Лампа −4 100" in text
    far = E.build(db, fam.id, [NS(accounts=[NS(currency="UAH", balance=-4000.0)])], date(2026, 11, 17))
    assert "Відстаємо на 2 550 ₴ — до 20.11 економією це не наздогнати: краще зменшити чи зсунути «Лампа» (4 100 ₴)." in far
    assert "15–19.11 · Старт" in text


def test_system_evening_once_per_day(seeded, db):
    fam = seeded["family"]
    db.add(models.FamilyPlan(family_id=fam.id, data=json.dumps(PLAN), synced_at=datetime(2026, 11, 15)))
    db.commit()
    r = client.get("/system/evening", headers=BOT_HEADERS).json()
    assert len(r) == 1 and r[0]["tg_ids"] == [111, 222] and r[0]["keys"][0].startswith("evening:")
    client.post("/system/housing/reminders/ack", headers=BOT_HEADERS,
                json={"items": [{"family_id": fam.id, "key": r[0]["keys"][0]}]})
    assert client.get("/system/evening", headers=BOT_HEADERS).json() == []
