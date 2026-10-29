# «Авто»: розбір нотаток про заправки, класифікація, витрата л/100 км, прив'язка транзакцій.
from datetime import date
from types import SimpleNamespace as NS

import pytest

from app import models
from app.services import vehicles as V
from tests.conftest import BOT_HEADERS, client, make_tx


def _hdr(fid):
    return {**BOT_HEADERS, "X-Family-Id": str(fid)}


@pytest.mark.parametrize("text, exp", [
    ("Газ до повного (52 л по 48,5 грн). Пробіг: 278297", dict(fuel="lpg", liters=52, price=48.5, odometer=278297, full_tank=True)),
    ("Бензин до повного (42 л по 59 грн). Пробіг: 277092", dict(fuel="petrol", liters=42, price=59, odometer=277092, full_tank=True)),
    ("18,5 л газу на пролюксі по 37.99 (276785)", dict(fuel="lpg", liters=18.5, price=37.99, odometer=276785, full_tank=False)),
    ("Газ на 1500 грн (33 л по 45,5 грн). Пробіг: 279121", dict(fuel="lpg", liters=33, price=45.5, odometer=279121)),
    ("Газ 20 л (20 л по 44 грн). Пробіг: ?", dict(fuel="lpg", liters=20, price=44, odometer=None)),
    ("Газ 20 л (20 л по 38,4 грн). Пробіг: 280274 (182 км з попередньої заправки)", dict(liters=20, price=38.4, odometer=280274)),
    ("Газ, 13 л за 38,4 грн. Пробіг: 280390", dict(fuel="lpg", liters=13, price=38.4, odometer=280390)),
    ("AZS 4 (Бензин, 41,8 л за 78,9 грн. Пробіг: 280500)", dict(fuel="petrol", liters=41.8, price=78.9, odometer=280500)),
    ("AZS 4 Газ 18,6 за 42,9 грн. Пробіг: 280941. На попередньому повном баці проїхав 413 км.",
     dict(fuel="lpg", liters=18.6, price=42.9, odometer=280941, full_tank=False)),
    ("Заправив 10 л дизеля на еско в джип", dict(fuel="diesel", liters=10)),
    ("Заправив близько повного баку. Пробіг: 277894", dict(fuel=None, liters=None, odometer=277894, full_tank=True)),
    ("Газ 20л KLO", dict(fuel="lpg", liters=20)),
    ("Бензин на 1000", dict(fuel="petrol", liters=None, price=None)),
])
def test_parse_owner_notes(text, exp):
    p = V.parse(text)
    for k, v in exp.items():
        assert p[k] == v, (k, p)


@pytest.mark.parametrize("text, cat, kind", [
    ("Газ 26 л", "⛽ Паливо", "fuel"),
    ("Мийка Плесецьке", "🚗 Авто інше", "wash"),
    ("Автомийка + пилосос на Плесецькому", "🚗 Авто інше", "wash"),
    ("Парковка в республіці", "🚗 Авто інше", "parking"),
    ("Перевзув резину на літню", "🚗 Авто інше", "tires"),
    ("Підкачка шин на шиномонтажі", "🛞 Ремонт авто", "tires"),
    ("СТО Андрія: Заміна резинок глушника, підварка кронштейна глушника", "🛞 Ремонт авто", "repair"),
    ("Кнопка аварійки Skoda Octavia Tour", "🛞 Ремонт авто", "repair"),
    ("Робота на СТО (себто усього за роботу віддали 6к)", "🛞 Ремонт авто", "repair"),
    ("Заміна масла і фільтрів, ТО-15", "🛞 Ремонт авто", "service"),
    ("Москітна сітка для вікон машини", "🚗 Авто інше", "other"),
    ("Омивайка для скла", "🚗 Авто інше", "other"),
    ("Поліс ОСЦПВ", "🚗 Авто інше", "insurance"),
])
def test_classify(text, cat, kind):
    assert V.classify(text, cat) == kind


def _log(i, d, kind="fuel", fuel="lpg", liters=None, price=None, odo=None, full=False, amount=0.0):
    return NS(id=i, date=d, kind=kind, fuel=fuel, liters=liters, price=price, odometer=odo, full_tank=full, amount=amount)


def test_consumption_full_to_full_and_average():
    car = NS(fuel="lpg", fuel2="petrol", start_odometer=None)
    logs = [
        _log(1, date(2026, 3, 2), liters=30, price=37.5, odo=277092, full=True, amount=1113),
        _log(2, date(2026, 3, 19), liters=55, price=44.5, odo=277593, full=True, amount=2417),
        _log(3, date(2026, 4, 1), odo=277894, full=True, amount=1908),  # no liters → estimated from nearest price
        _log(4, date(2026, 4, 21), liters=52, price=48.5, odo=278297, full=True, amount=2503),
        _log(5, date(2026, 3, 2), fuel="petrol", liters=42, price=59, odo=277092, full=True, amount=2431),
        _log(6, date(2026, 3, 20), kind="wash", fuel=None, amount=130),
    ]
    st = V.vehicle_stats(car, logs, today=date(2026, 4, 30), months=3)
    lpg = st["fuels"]["lpg"]
    assert st["segments"][2]["per100"] == pytest.approx(55 / 501 * 100, abs=0.05)
    assert st["segments"][3]["estimated"] is True
    assert lpg["last_per100"] == pytest.approx(52 / 403 * 100, abs=0.05)
    est = 1908 / 44.5  # nearest known price — 19.03 fill
    assert lpg["avg_per100"] == pytest.approx((55 + est + 52) / (278297 - 277092) * 100, abs=0.05)
    assert lpg["estimated"] == 1
    assert st["odometer"] == 278297 and st["km_tracked"] == 1205
    assert st["months"][-1]["month"] == "2026-04-01" and st["months"][-1]["fuel"] == 1908 + 2503
    assert st["months"][-2]["other"] == 130
    assert st["months"][-1]["km"] == 278297 - round(V.odometer_at(V.odometer_points(car, logs), date(2026, 3, 31)))
    assert V.km_since(logs) == {2: 501, 3: 301, 4: 403}


def _seed_car(db, seeded, **kw):
    fid = seeded["family"].id
    cats = {}
    for name in ("⛽ Паливо", "🚗 Авто інше", "🛞 Ремонт авто"):
        c = models.Category(family_id=fid, icon="•", name=name, color="#000", type="expense")
        db.add(c)
        db.flush()
        cats[name] = c
    v = models.Vehicle(family_id=fid, name="Skoda Octavia Tour", fuel="lpg", fuel2="petrol",
                       match_pattern=V.DEFAULT_PATTERN, **kw)
    db.add(v)
    db.commit()
    return v, cats


def test_new_fuel_transaction_lands_in_journal(db, seeded):
    v, cats = _seed_car(db, seeded)
    fid, uid = seeded["family"].id, seeded["admin"].id
    r = client.post("/transactions", headers=_hdr(fid), json={
        "family_id": fid, "user_id": uid, "category_id": cats["⛽ Паливо"].id, "amount": 1272, "type": "Витрати",
        "title": "AZS 4", "note": "Газ 30 л по 42,90. Пробіг: 281100", "account": "Монобанк", "date": "2026-08-19"})
    assert r.status_code == 200
    logs = client.get(f"/families/{fid}/vehicles/{v.id}/logs", headers=_hdr(fid)).json()
    assert len(logs) == 1 and logs[0]["kind"] == "fuel" and logs[0]["liters"] == 30 and logs[0]["price"] == 42.9
    assert logs[0]["odometer"] == 281100 and logs[0]["transaction"]["id"] == r.json()["id"]
    # a correction of the amount in finances is mirrored in the journal
    client.put(f"/transactions/{r.json()['id']}", headers=_hdr(fid), json={"amount": 1287})
    assert client.get(f"/families/{fid}/vehicles/{v.id}/logs", headers=_hdr(fid)).json()[0]["amount"] == 1287
    # deleting the operation removes its entry
    client.delete(f"/transactions/{r.json()['id']}", headers=_hdr(fid))
    assert client.get(f"/families/{fid}/vehicles/{v.id}/logs", headers=_hdr(fid)).json() == []


def test_pending_station_is_suggested_not_linked_and_inbox_links_it(db, seeded):
    v, cats = _seed_car(db, seeded)
    fid, uid = seeded["family"].id, seeded["admin"].id
    pend = seeded["cats"]["Очікує"].id
    coffee = make_tx(db, fid, uid, pend, 60, "Витрати", title="❓ KAVOVYY APARAT 1 AZS 4", account="Монобанк")
    fill = make_tx(db, fid, uid, pend, 999.89, "Витрати", title="❓ AZS 4", account="Монобанк")
    sug = client.get(f"/families/{fid}/auto/suggestions", headers=_hdr(fid)).json()
    assert [s["transaction"]["id"] for s in sug] == [fill.id]
    assert sug[0]["draft"]["kind"] == "fuel" and sug[0]["draft"]["fuel"] == "lpg"
    assert client.get(f"/families/{fid}/vehicles/{v.id}/logs", headers=_hdr(fid)).json() == []
    # categorised as fuel in the Inbox (with a note) → journal entry appears
    client.put(f"/transactions/{fill.id}", headers=_hdr(fid), json={"category_id": cats["⛽ Паливо"].id,
                                                                      "note": "Газ 23,3 л. Пробіг: 282000"})
    logs = client.get(f"/families/{fid}/vehicles/{v.id}/logs", headers=_hdr(fid)).json()
    assert len(logs) == 1 and logs[0]["liters"] == 23.3 and logs[0]["odometer"] == 282000
    assert client.get(f"/families/{fid}/auto", headers=_hdr(fid)).json()["suggested"] == 0
    hotdog = make_tx(db, fid, uid, pend, 256, "Витрати", title="❓ AZS 4", account="Монобанк")
    assert [s["transaction"]["id"] for s in client.get(f"/families/{fid}/auto/suggestions", headers=_hdr(fid)).json()] == [hotdog.id]
    client.post(f"/families/{fid}/auto/ignore", headers=_hdr(fid), json={"transaction_id": hotdog.id})
    assert client.get(f"/families/{fid}/auto/suggestions", headers=_hdr(fid)).json() == []
    assert coffee.id not in [s["transaction"]["id"] for s in client.get(f"/families/{fid}/auto/suggestions", headers=_hdr(fid)).json()]


def test_manual_fill_creates_expense_and_link_sheet(db, seeded):
    v, cats = _seed_car(db, seeded)
    fid = seeded["family"].id
    r = client.post(f"/families/{fid}/vehicle-logs", headers=_hdr(fid), json={
        "vehicle_id": v.id, "kind": "fuel", "fuel": "lpg", "liters": 40, "price": 42.9, "odometer": 281500,
        "full_tank": True, "date": "2026-10-20", "create_transaction": True, "account": "Готівка"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["amount"] == 0 and body["liters"] == 40  # amount not given → no expense
    r = client.post(f"/families/{fid}/vehicle-logs", headers=_hdr(fid), json={
        "vehicle_id": v.id, "kind": "fuel", "fuel": "lpg", "liters": 40, "price": 42.9, "amount": 1716, "odometer": 281900,
        "full_tank": True, "date": "2026-10-28", "create_transaction": True, "account": "Готівка"})
    tx = db.get(models.Transaction, r.json()["transaction_id"])
    assert tx.category_id == cats["⛽ Паливо"].id and tx.title == "⛽ Газ 40 л по 42,9 грн, до повного"
    assert tx.note == "Пробіг: 281900"
    # LinkSheet shows the car as the current link
    link = client.get(f"/families/{fid}/transactions/{tx.id}/link", headers=_hdr(fid)).json()
    assert link["current"]["type"] == "vehicle" and link["current"]["id"] == v.id
    # relinking to nothing drops the journal entry
    client.delete(f"/families/{fid}/transactions/{tx.id}/link", headers=_hdr(fid))
    assert len(client.get(f"/families/{fid}/vehicles/{v.id}/logs", headers=_hdr(fid)).json()) == 1


def test_link_sheet_vehicle_candidate_and_set_link(db, seeded):
    v, cats = _seed_car(db, seeded)
    fid, uid = seeded["family"].id, seeded["admin"].id
    wash = make_tx(db, fid, uid, seeded["cats"]["Очікує"].id, 140, "Витрати", title="❓ DEWASH", account="Монобанк")
    c = client.get(f"/families/{fid}/transactions/{wash.id}/link", headers=_hdr(fid)).json()["candidates"]
    assert c[0]["type"] == "vehicle" and c[0]["match"] is True
    r = client.post(f"/families/{fid}/transactions/{wash.id}/link", headers=_hdr(fid), json={"type": "vehicle", "id": v.id})
    assert r.json()["current"]["kind"] == "wash"
    db.refresh(wash)
    assert wash.category_id == cats["🚗 Авто інше"].id and wash.title == "DEWASH"


def test_import_history_skips_foreign_fuel(db, seeded):
    v, cats = _seed_car(db, seeded)
    fid, uid = seeded["family"].id, seeded["admin"].id
    f = cats["⛽ Паливо"].id
    make_tx(db, fid, uid, f, 2431, "Витрати", title="Бензин до повного (42 л по 59 грн). Пробіг: 277092", date="2026-03-02")
    make_tx(db, fid, uid, f, 870, "Витрати", title="Заправив 10 л дизеля на еско в джип", date="2026-05-08")
    make_tx(db, fid, uid, cats["🛞 Ремонт авто"].id, 1700, "Витрати", title="СТО Андрія: Заміна резинок глушника", date="2026-05-21")
    make_tx(db, fid, uid, seeded["cats"]["Продукти"].id, 500, "Витрати", title="АТБ", date="2026-05-21")
    r = client.post(f"/families/{fid}/vehicles/{v.id}/import", headers=_hdr(fid)).json()
    assert r["linked"] == 2 and [s["title"] for s in r["skipped"]] == ["Заправив 10 л дизеля на еско в джип"]
    kinds = sorted(l["kind"] for l in client.get(f"/families/{fid}/vehicles/{v.id}/logs", headers=_hdr(fid)).json())
    assert kinds == ["fuel", "repair"]
    # running it again links nothing new
    assert client.post(f"/families/{fid}/vehicles/{v.id}/import", headers=_hdr(fid)).json()["linked"] == 0


def test_vehicle_archive_and_tenant_isolation(db, seeded):
    v, _ = _seed_car(db, seeded)
    fid = seeded["family"].id
    other = models.Family(name="Other", invite_code="other1")
    db.add(other)
    db.commit()
    assert client.get(f"/families/{other.id}/vehicles/{v.id}/logs", headers=_hdr(other.id)).status_code == 404
    client.post(f"/families/{fid}/vehicle-logs", headers=_hdr(fid), json={"vehicle_id": v.id, "kind": "odometer", "odometer": 281000})
    assert client.delete(f"/families/{fid}/vehicles/{v.id}", headers=_hdr(fid)).json() == {"archived": True}
    assert client.get(f"/families/{fid}/auto", headers=_hdr(fid)).json()["vehicles"] == []


def test_learning_from_history_station_amounts_place_and_prediction(db, seeded):
    """«AZS 4»: fills ~1000–1300 ₴ (LPG at 42,9), coffee there ≤ 95 ₴ → a new 999,89 is surely a fill
    (LPG, ≈23,3 л, Пролюкс), 256 needs a look, 70 is coffee. Naming the station once names them all."""
    v, cats = _seed_car(db, seeded)
    fid, uid = seeded["family"].id, seeded["admin"].id
    pend, daily = seeded["cats"]["Очікує"].id, seeded["cats"]["Кафе"].id
    fuel = cats["⛽ Паливо"].id
    for amt, note, d in [(1272, "Газ 30 л по 42,90. Пробіг: 281100", "2026-08-19"),
                         (1051.09, "Газ 18,6 за 42,9 грн. Пробіг: 280500", "2026-07-21")]:
        client.post("/transactions", headers=_hdr(fid), json={
            "family_id": fid, "user_id": uid, "category_id": fuel, "amount": amt, "type": "Витрати",
            "title": "AZS 4", "note": note, "account": "Монобанк", "date": d})
    for amt in (60, 95, 75):
        make_tx(db, fid, uid, daily, amt, "Витрати", title="AZS 4", account="Монобанк", date="2026-08-20")
    logs = client.get(f"/families/{fid}/vehicles/{v.id}/logs", headers=_hdr(fid)).json()
    r = client.put(f"/families/{fid}/vehicle-logs/{logs[0]['id']}", headers=_hdr(fid), json={"place": "Пролюкс"})
    assert r.status_code == 200
    assert {l["place"] for l in client.get(f"/families/{fid}/vehicles/{v.id}/logs", headers=_hdr(fid)).json()} == {"Пролюкс"}

    big = make_tx(db, fid, uid, pend, 999.89, "Витрати", title="❓ AZS 4", account="Монобанк", date="2026-09-28")
    mid = make_tx(db, fid, uid, pend, 256, "Витрати", title="❓ AZS 4", account="Монобанк", date="2026-08-27")
    make_tx(db, fid, uid, pend, 70, "Витрати", title="❓ AZS 4", account="Монобанк", date="2026-09-14")
    wog = make_tx(db, fid, uid, pend, 1500, "Витрати", title="❓ WOG", account="Монобанк", date="2026-10-20")
    sug = {s["transaction"]["id"]: s["draft"] for s in client.get(f"/families/{fid}/auto/suggestions", headers=_hdr(fid)).json()}
    assert set(sug) == {big.id, mid.id, wog.id}
    b = sug[big.id]
    assert b["confidence"] == "sure" and b["fuel"] == "lpg" and b["price"] == 42.9 and b["liters"] == 23.3
    assert b["place"] == "Пролюкс" and set(b["predicted"]) == {"fuel", "price", "liters"}
    assert b["odometer_hint"] and b["odometer_hint"] > 281100
    assert sug[mid.id]["confidence"] == "maybe"
    assert sug[wog.id]["place"] == "WOG" and sug[wog.id]["confidence"] == "maybe"  # unknown merchant, pattern only
    ov = client.get(f"/families/{fid}/auto", headers=_hdr(fid)).json()
    assert ov["suggested"] == 3 and ov["suggested_sure"] == (1 if (date.today() - date(2026, 9, 28)).days <= 45 else 0)

    r = client.post(f"/families/{fid}/auto/suggestions/accept", headers=_hdr(fid), json={"transaction_ids": [big.id]})
    assert r.json() == {"added": 1}
    db.refresh(big)
    assert big.category_id == fuel and big.title == "AZS 4"
    h = client.get(f"/families/{fid}/vehicles/{v.id}/hints", headers=_hdr(fid)).json()
    assert h["places"][0]["name"] == "Пролюкс" and h["places"][0]["prices"]["lpg"] == 42.9 and h["last_fuel"] == "lpg"


def test_second_fuel_of_bifuel_car_has_no_per100():
    v = NS(fuel="lpg", fuel2="petrol", start_odometer=None)
    logs = [_log(1, date(2026, 3, 1), odo=279000, liters=40, price=42, full=True),
            _log(2, date(2026, 3, 2), fuel="petrol", liters=10, price=58, odo=279010),
            _log(3, date(2026, 4, 1), odo=279700, liters=35, price=42, full=True),
            _log(4, date(2026, 6, 1), fuel="petrol", liters=20, price=60, odo=280900)]
    st = V.vehicle_stats(v, logs, today=date(2026, 7, 1))
    assert st["fuels"]["lpg"]["avg_per100"] is not None and not st["fuels"]["lpg"]["secondary"]
    p = st["fuels"]["petrol"]
    assert p["secondary"] and p["avg_per100"] is None and p["per_month_l"] == round(30 / 121 * 30.44, 1)


def test_personal_tab_prefs(db, seeded):
    fid, uid = seeded["family"].id, seeded["admin"].id
    h = {**_hdr(fid), "X-User-Id": str(uid)}
    r = client.put("/users/me/tabs", headers=h, json={"tab": "auto", "show": False})
    assert r.status_code == 200 and r.json()["tab_prefs"] == {"auto": False}
    r = client.put("/users/me/tabs", headers=h, json={"tab": "auto", "show": None})
    assert r.json()["tab_prefs"] == {}
    assert client.put("/users/me/tabs", headers=h, json={"tab": "bogus", "show": True}).status_code == 422


def test_two_drivers_and_two_cars(db, seeded):
    fid, a, m = seeded["family"].id, seeded["admin"].id, seeded["member"].id
    v, cats = _seed_car(db, seeded)
    r = client.put(f"/families/{fid}/vehicles/{v.id}", headers=_hdr(fid), json={"driver_ids": [a, m]})
    assert r.json()["driver_ids"] == [a, m] and r.json()["user_id"] == a
    second = client.post(f"/families/{fid}/vehicles", headers=_hdr(fid), json={"name": "Jeep", "fuel": "diesel", "driver_ids": [m]}).json()
    client.put(f"/families/{fid}/vehicles/{v.id}", headers=_hdr(fid), json={"driver_ids": [a]})
    db.expire_all()
    assert V.pick_vehicle(db, fid, a).id == v.id and V.pick_vehicle(db, fid, m).id == second["id"]
    assert client.put(f"/families/{fid}/vehicles/{v.id}", headers=_hdr(fid), json={"driver_ids": [999]}).status_code == 400


def test_insurance_policy_file_link_and_payment(db, seeded):
    v, cats = _seed_car(db, seeded)
    fid = seeded["family"].id
    r = client.post(f"/families/{fid}/vehicle-documents", headers=_hdr(fid), json={
        "vehicle_id": v.id, "kind": "osago", "company": "ARX", "number": "EP-123", "start_date": "2026-03-10",
        "amount": 2100, "url": "https://policy.mtsbu.ua/x", "create_expense": True, "account": "Готівка"})
    d = r.json()
    assert r.status_code == 200 and d["end_date"] == "2027-03-09" and d["log_id"] and not d["has_file"]
    logs = client.get(f"/families/{fid}/vehicles/{v.id}/logs", headers=_hdr(fid)).json()
    assert logs[0]["kind"] == "insurance" and logs[0]["amount"] == 2100 and logs[0]["transaction_id"]
    assert client.post(f"/families/{fid}/vehicle-documents", headers=_hdr(fid), json={
        "vehicle_id": v.id, "url": "javascript:alert(1)"}).status_code == 400
    # PDF: raw body upload → signed link → inline file; wrong type / fake PDF refused
    up = client.put(f"/families/{fid}/vehicle-documents/{d['id']}/file?name=osago.pdf", headers={**_hdr(fid), "Content-Type": "application/pdf"},
                    content=b"%PDF-1.4 test")
    assert up.status_code == 200 and up.json()["has_file"]
    assert client.put(f"/families/{fid}/vehicle-documents/{d['id']}/file", headers={**_hdr(fid), "Content-Type": "application/pdf"},
                      content=b"<html>").status_code == 415
    path = client.get(f"/families/{fid}/vehicle-documents/{d['id']}/file-link", headers=_hdr(fid)).json()["path"]
    f = client.get(path)
    assert f.status_code == 200 and f.content == b"%PDF-1.4 test" and f.headers["content-type"] == "application/pdf"
    assert client.get(path.replace("t=", "t=x")).status_code == 403
    ov = client.get(f"/families/{fid}/auto", headers=_hdr(fid)).json()
    assert ov["vehicles"][0]["documents"][0]["number"] == "EP-123" and "days_left" in ov["vehicles"][0]["documents"][0]
