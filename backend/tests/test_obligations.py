# Кредити / розстрочки / підписки: статус, автоприв'язка транзакцій, підказки, прив'язка до «Житла».
from datetime import date, timedelta
from types import SimpleNamespace as NS

from app import models
from app.services import obligations as O
from tests.conftest import BOT_HEADERS, client, make_tx


def _hdr(fid):
    return {**BOT_HEADERS, "X-Family-Id": str(fid)}


def _ob(**kw):
    base = dict(id=1, kind="installment", amount=2300.0, currency="UAH", period="month", due_day=13,
                first_due=date(2026, 4, 13), payments_total=10, end_date=None, paid_before=0, is_active=True,
                match_pattern="Citrus|Платіж за телевізор", category_id=None)
    base.update(kw)
    return NS(**base)


def _t(d, amount=2300.0, title="Щомісячний платіж Citrus - monomarket", tid=1):
    return NS(id=tid, date=d, amount=amount, title=title, type="Витрати", jar_id=None, currency="UAH")


def test_installment_progress_like_tv():
    ob = _ob()
    linked = [_t(date(2026, m, 13), tid=m) for m in range(4, 11)]  # Apr..Oct = 7 payments
    st = O.status(ob, linked, today=date(2026, 10, 21))
    assert st["paid_count"] == 7 and st["remaining_count"] == 3 and st["remaining_amount"] == 6900
    assert st["next_due"] == "2026-11-13" and st["end"] == "2027-01-13" and st["status"] == "upcoming"


def test_installment_overdue_and_paid_before():
    ob = _ob(amount=1500, due_day=11, first_due=date(2026, 3, 11), payments_total=12, paid_before=2)
    linked = [_t(date(2026, m, 11), 1500, tid=m) for m in (4, 5, 6, 7, 8)]  # 5 linked + 2 before = 7
    st = O.status(ob, linked, today=date(2026, 10, 21))
    assert st["paid_count"] == 7 and st["next_due"] == "2026-10-11" and st["status"] == "overdue"
    st = O.status(ob, linked + [_t(date(2026, 10, 11), 1500, tid=99)], today=date(2026, 10, 21))
    assert st["next_due"] == "2026-11-11" and st["end"] == "2027-02-11"


def test_installment_finished():
    ob = _ob(payments_total=2, first_due=date(2026, 8, 13))
    st = O.status(ob, [_t(date(2026, 8, 13)), _t(date(2026, 9, 13), tid=2)], today=date(2026, 10, 1))
    assert st["status"] == "finished" and st["remaining_amount"] == 0 and st["next_due"] is None


def test_subscription_next_charge_and_stale():
    ob = _ob(kind="subscription", amount=149, due_day=16, first_due=None, payments_total=None, match_pattern="YouTube")
    st = O.status(ob, [_t(date(2026, 10, 16), 149, "YouTube")], today=date(2026, 10, 21))
    assert st["status"] == "charged" and st["next_due"] == "2026-11-16" and st["monthly"] == 149
    st = O.status(ob, [_t(date(2026, 7, 16), 149, "YouTube")], today=date(2026, 10, 21))
    assert st["status"] == "stale"


def test_matching_splits_same_merchant_by_due_day():
    vadym = _ob(id=1, kind="subscription", amount=44.38, due_day=21, first_due=None, payments_total=None, match_pattern="Apple")
    anya = _ob(id=2, kind="subscription", amount=44.58, due_day=11, first_due=None, payments_total=None, match_pattern="Apple")
    assert O.best_obligation([vadym, anya], _t(date(2026, 10, 21), 44.78, "Apple")).id == 1
    assert O.best_obligation([vadym, anya], _t(date(2026, 10, 11), 44.58, "Apple")).id == 2
    assert O.best_obligation([vadym, anya], _t(date(2026, 10, 9), 319, "Apple")) is None  # amount differs


def test_api_create_autolink_and_backfill(seeded, db):
    fam, admin, cats = seeded["family"], seeded["admin"], seeded["cats"]
    old = make_tx(db, fam.id, admin.id, cats["Очікує"].id, 2299.9, "Витрати", title="❓ Щомісячний платіж Citrus - monomarket",
                  date=date.today() - timedelta(days=30))
    r = client.post(f"/families/{fam.id}/obligations", headers=_hdr(fam.id), json={
        "kind": "installment", "name": "Телевізор", "amount": 2300, "due_day": (date.today() - timedelta(days=30)).day,
        "payments_total": 10, "first_due": str(date.today() - timedelta(days=120)), "match_pattern": "Citrus",
        "category_id": cats["Інше"].id, "link_suggested": True})
    assert r.status_code == 200, r.text
    ob = r.json()
    assert ob["state"]["linked_count"] == 1
    db.expire_all()
    t = db.get(models.Transaction, old.id)
    assert t.obligation_id == ob["id"] and t.category_id == cats["Інше"].id and not t.title.startswith("❓")
    # a new Monobank-like transaction is linked on creation
    r = client.post("/transactions", headers=BOT_HEADERS, json={
        "family_id": fam.id, "user_id": admin.id, "category_id": cats["Очікує"].id, "amount": 2299.9, "type": "Витрати",
        "title": "❓ Щомісячний платіж Citrus - monomarket", "account": "Монобанк", "date": str(date.today())})
    assert r.json()["obligation_id"] == ob["id"]
    lst = client.get(f"/families/{fam.id}/obligations", headers=_hdr(fam.id)).json()
    assert lst["items"][0]["state"]["paid_count"] == 2 and lst["totals"]["credits_monthly"] == 2300


def test_link_sheet_candidates_and_housing_link(seeded, db):
    fam, admin, cats = seeded["family"], seeded["admin"], seeded["cats"]
    client.post(f"/housing/families/{fam.id}/setup", headers=_hdr(fam.id), json={"mode": "own", "templates": ["electricity"]})
    prov = db.query(models.UtilityProvider).filter_by(family_id=fam.id, service="electricity").first()
    tx = make_tx(db, fam.id, admin.id, cats["Очікує"].id, 401.76, "Витрати", title="Електроенергія")
    cand = client.get(f"/families/{fam.id}/transactions/{tx.id}/link", headers=_hdr(fam.id)).json()
    assert cand["current"] is None and any(c["type"] == "provider" for c in cand["candidates"])
    r = client.post(f"/families/{fam.id}/transactions/{tx.id}/link", headers=_hdr(fam.id), json={"type": "provider", "id": prov.id})
    assert r.status_code == 200 and r.json()["current"]["type"] == "provider"
    pays = client.get(f"/housing/families/{fam.id}/payments", headers=_hdr(fam.id)).json()
    assert pays[0]["transaction_id"] == tx.id and pays[0]["amount"] == 401.76
    assert client.delete(f"/families/{fam.id}/transactions/{tx.id}/link", headers=_hdr(fam.id)).json()["payments"] == 1
    assert client.get(f"/housing/families/{fam.id}/payments", headers=_hdr(fam.id)).json() == []


def test_provider_pattern_autolinks_new_payment(seeded, db):
    fam, admin, cats = seeded["family"], seeded["admin"], seeded["cats"]
    client.post(f"/housing/families/{fam.id}/setup", headers=_hdr(fam.id), json={"mode": "own", "templates": ["electricity"]})
    prov = db.query(models.UtilityProvider).filter_by(family_id=fam.id, service="electricity").first()
    client.put(f"/housing/families/{fam.id}/providers/{prov.id}", headers=_hdr(fam.id), json={"match_pattern": "Електроенергія"})
    client.post("/transactions", headers=BOT_HEADERS, json={
        "family_id": fam.id, "user_id": admin.id, "category_id": cats["Очікує"].id, "amount": 643.68, "type": "Витрати",
        "title": "❓ Електроенергія", "account": "Монобанк", "date": str(date.today())})
    pays = client.get(f"/housing/families/{fam.id}/payments", headers=_hdr(fam.id)).json()
    assert len(pays) == 1 and pays[0]["amount"] == 643.68 and pays[0]["transaction_id"]


def test_upcoming_and_reminders(seeded, db):
    from app.api.housing import compute_reminders
    fam = seeded["family"]
    tomorrow = date.today() + timedelta(days=1)
    client.post(f"/families/{fam.id}/obligations", headers=_hdr(fam.id), json={
        "kind": "installment", "name": "PS5", "amount": 2850, "first_due": str(tomorrow), "payments_total": 10})
    up = client.get(f"/families/{fam.id}/upcoming?days=5", headers=_hdr(fam.id)).json()
    assert up[0]["title"] == "PS5" and up[0]["sub"] == "Платіж · 1 з 10"
    rem = [r for r in compute_reminders(db) if r["family_id"] == fam.id]
    assert rem and "PS5" in rem[0]["text"] and rem[0]["tab"] == "payments"


def test_delete_obligation_archives_when_linked(seeded, db):
    fam, admin, cats = seeded["family"], seeded["admin"], seeded["cats"]
    ob = client.post(f"/families/{fam.id}/obligations", headers=_hdr(fam.id), json={
        "kind": "subscription", "name": "YouTube", "amount": 149, "due_day": 16, "match_pattern": "YouTube"}).json()
    tx = make_tx(db, fam.id, admin.id, cats["Інше"].id, 149, "Витрати", title="YouTube")
    client.post(f"/families/{fam.id}/transactions/{tx.id}/link", headers=_hdr(fam.id), json={"type": "obligation", "id": ob["id"]})
    assert client.delete(f"/families/{fam.id}/obligations/{ob['id']}", headers=_hdr(fam.id)).json()["archived"] is True


def test_svitlobot_channel_validated_on_save(seeded, monkeypatch):
    from app.services import svitlobot
    fam = seeded["family"]
    monkeypatch.setattr(svitlobot, "fetch_page", lambda ch, before=None, timeout=10: "<html>no posts</html>")
    r = client.put(f"/housing/families/{fam.id}/profile", headers=_hdr(fam.id), json={"svitlobot_channel": "some_channel"})
    assert r.status_code == 400 and "світлобота" in r.json()["detail"]


def test_linked_housing_payment_follows_transaction_edit_and_delete(seeded, db):
    fam, admin, cats = seeded["family"], seeded["admin"], seeded["cats"]
    client.post(f"/housing/families/{fam.id}/setup", headers=_hdr(fam.id), json={"mode": "own", "templates": ["electricity"]})
    prov = db.query(models.UtilityProvider).filter_by(family_id=fam.id, service="electricity").first()
    tx = make_tx(db, fam.id, admin.id, cats["Інше"].id, 400, "Витрати", title="Електроенергія")
    client.post(f"/families/{fam.id}/transactions/{tx.id}/link", headers=_hdr(fam.id), json={"type": "provider", "id": prov.id})
    client.put(f"/transactions/{tx.id}", headers=BOT_HEADERS, json={"amount": 450, "date": "2026-10-03"})
    pays = client.get(f"/housing/families/{fam.id}/payments", headers=_hdr(fam.id)).json()
    assert pays[0]["amount"] == 450 and pays[0]["date"] == "2026-10-03"
    assert client.delete(f"/transactions/{tx.id}", headers=BOT_HEADERS).status_code == 200
    assert client.get(f"/housing/families/{fam.id}/payments", headers=_hdr(fam.id)).json() == []


# ---------------------------------------------------------------- regressions from the review

def test_rent_overdue_visible_with_long_history():
    from app.services import housing as H
    rent = NS(service="rent", billing="fixed", fixed_amount=3000.0, due_day=1, start_date=date(2023, 1, 1), opening_balance=0.0)
    pays = [NS(date=date(2022, 12, 28) + timedelta(days=30 * i), amount=3000) for i in range(40)]  # through ~2026-04
    bal = H.provider_balance(rent, [], [], pays, [], today=date(2026, 10, 22))
    assert bal["debt"] > 0 and bal["overdue_months"] >= 1 and bal["overdue_since"].startswith("2026")


def test_installment_anchor_persisted_on_create(seeded):
    fam = seeded["family"]
    ob = client.post(f"/families/{fam.id}/obligations", headers=_hdr(fam.id), json={
        "kind": "installment", "name": "Пилосос", "amount": 1000, "due_day": 15, "payments_total": 10}).json()
    assert ob["first_due"] is not None  # schedule no longer drifts with «today»


def test_subscription_charged_a_day_early_counts_for_the_cycle():
    ob = _ob(kind="subscription", amount=100, due_day=1, first_due=None, payments_total=None, match_pattern="X")
    st = O.status(ob, [_t(date(2026, 10, 31), 100, "X")], today=date(2026, 11, 3))
    assert st["status"] == "charged" and st["next_due"] == "2026-12-01"


def test_same_day_reading_can_be_corrected_down(seeded):
    fam = seeded["family"]
    ov = client.post(f"/housing/families/{fam.id}/setup", headers=_hdr(fam.id), json={"mode": "own", "templates": ["gas"]}).json()
    gas = ov["meters"][0]["id"]
    d = str(date.today())
    client.post(f"/housing/families/{fam.id}/readings", headers=_hdr(fam.id), json={"date": d, "items": [{"meter_id": gas, "value": 12450}]})
    r = client.post(f"/housing/families/{fam.id}/readings", headers=_hdr(fam.id), json={"date": d, "items": [{"meter_id": gas, "value": 1245}]})
    assert r.status_code == 200


def test_reminder_ack_dedupes_within_payload(seeded):
    fam = seeded["family"]
    r = client.post("/system/housing/reminders/ack", headers=BOT_HEADERS,
                    json={"items": [{"family_id": fam.id, "key": "k1"}, {"family_id": fam.id, "key": "k1"}]})
    assert r.status_code == 200 and r.json()["acked"] == 1


def test_bill_edit_updates_its_reading(seeded):
    fam = seeded["family"]
    ov = client.post(f"/housing/families/{fam.id}/setup", headers=_hdr(fam.id), json={"mode": "own", "templates": ["gas"]}).json()
    prov, gas = ov["providers"][0]["id"], ov["meters"][0]["id"]
    body = {"provider_id": prov, "period": "2026-08", "lines": [{"meter_id": gas, "label": "Газ", "prev_value": 100, "curr_value": 1500, "tariff": 8}]}
    b = client.post(f"/housing/families/{fam.id}/bills", headers=_hdr(fam.id), json=body).json()
    body["lines"][0]["curr_value"] = 150
    client.put(f"/housing/families/{fam.id}/bills/{b['id']}", headers=_hdr(fam.id), json=body)
    hist = client.get(f"/housing/families/{fam.id}/meters/{gas}/readings", headers=_hdr(fam.id)).json()
    assert [h["value"] for h in hist if h["date"] == "2026-09-01"] == [150]
