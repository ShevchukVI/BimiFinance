# Тести модуля «Житло»: розрахунки боргу/прогнозу, перевірки платіжок, оренда,
# API (setup, показники, платіжки, оплати → фінанси), світлобот, нагадування, ізоляція сімей.
from datetime import date, datetime, timedelta
from types import SimpleNamespace as NS

from app import models
from app.services import housing as H
from app.services import svitlobot
from tests.conftest import BOT_HEADERS, client


def _hdr(fid):
    return {**BOT_HEADERS, "X-Family-Id": str(fid)}


def _reading(d, v):
    return NS(date=d, value=v)


def _line(meter_id, prev, curr, tariff, amount=None, volume=None, label="Світло · день"):
    vol = volume if volume is not None else (curr - prev)
    return NS(meter_id=meter_id, label=label, prev_value=prev, curr_value=curr, volume=vol, tariff=tariff,
              amount=amount if amount is not None else round(vol * tariff, 2))


def _bill(period, opening, paid, accrued, to_pay, lines=(), adjustment=0.0, bid=1):
    return NS(id=bid, period=period, opening_balance=opening, paid=paid, accrued=accrued, adjustment=adjustment,
              to_pay=to_pay, lines=list(lines))


# ---------------------------------------------------------------- pure calculations

def test_value_at_interpolates_and_extrapolates():
    pts = H.series([_reading(date(2026, 9, 1), 8944), _reading(date(2026, 9, 9), 8976),
                    _reading(date(2026, 10, 4), 9037)])
    v, est = H.value_at(pts, date(2026, 9, 5))
    assert round(v) == 8960 and est is False
    v, est = H.value_at(pts, date(2026, 10, 14))
    assert est is True and v > 9037  # extrapolated by the recent rate


def test_daily_rate_uses_recent_window():
    pts = H.series([_reading(date(2026, 4, 1), 8453), _reading(date(2026, 9, 1), 8944),
                    _reading(date(2026, 10, 1), 9004)])
    assert abs(H.daily_rate(pts) - 2.0) < 0.01


def test_bill_flags_catch_ondo_style_mismatch():
    meter = NS(id=1, name="Світло · день", unit="кВт·год", tariff=4.32,
               readings=[_reading(date(2026, 5, 1), 8545), _reading(date(2026, 6, 1), 8630)])
    april = _bill(date(2026, 4, 1), 3315.76, 3315.76, 516.24, 516.24, bid=1)
    may = _bill(date(2026, 5, 1), 451.44, 0, 419.04, 870.48,
                lines=[_line(1, 8544, 8625, 4.32, amount=349.92)], bid=2)
    pays = [NS(date=date(2026, 5, 20), amount=100.0)]
    flags = H.bill_flags(may, april, pays, {1: meter})
    codes = {f["code"] for f in flags}
    assert "continuity" in codes  # 451.44 ≠ 516.24
    assert "payments" in codes  # we recorded 100 in May, bill says 0
    cont = next(f for f in flags if f["code"] == "continuity")
    assert cont["diff"] == -64.8


def test_bill_flags_arithmetic_and_reading_mismatch():
    meter = NS(id=1, name="Світло · день", unit="кВт·год", tariff=4.32,
               readings=[_reading(date(2026, 8, 30), 8900), _reading(date(2026, 9, 2), 8950)])
    bill = _bill(date(2026, 8, 1), 401.76, 0, 643.68, 1000.0,
                 lines=[_line(1, 8807, 9000, 4.32)])
    codes = {f["code"] for f in H.bill_flags(bill, None, [], {1: meter})}
    assert "arithmetic" in codes  # 401.76 + 643.68 ≠ 1000
    assert "reading_mismatch" in codes  # billed 9000, own ≈ 8933 on 01.09


def test_clean_bill_has_no_warnings():
    meter = NS(id=1, name="Світло · день", unit="кВт·год", tariff=4.32,
               readings=[_reading(date(2026, 9, 1), 8943)])
    prev = _bill(date(2026, 7, 1), -21.6, 0, 423.36, 401.76, lines=[_line(1, 8723, 8807, 4.32)], bid=1)
    bill = _bill(date(2026, 8, 1), 401.76, 0, 587.52, 989.28, lines=[_line(1, 8807, 8943, 4.32)], bid=2)
    assert [f for f in H.bill_flags(bill, prev, [], {1: meter}) if f["level"] == "warn"] == []


def test_fixed_ledger_rent_paid_until_and_lateness():
    rent = NS(service="rent", billing="fixed", fixed_amount=3500.0, due_day=3, start_date=date(2026, 8, 1),
              opening_balance=0.0)
    pays = [NS(date=date(2026, 8, 3), amount=3500), NS(date=date(2026, 9, 6), amount=3500),
            NS(date=date(2026, 9, 30), amount=3500)]
    bal = H.provider_balance(rent, [], [], pays, [], today=date(2026, 10, 21))
    assert bal["paid_until"] == "2026-10-31"
    assert bal["debt"] == 0
    assert bal["next_charge"]["month"] == "2026-11-01"
    assert bal["punctuality"]["late"] == 1 and bal["punctuality"]["max_days_late"] == 3


def test_provider_balance_from_last_bill_minus_later_payments():
    prov = NS(service="gas", billing="metered", fixed_amount=None, due_day=20, start_date=None, opening_balance=0)
    bills = [_bill(date(2026, 8, 1), 258.99, 0, 181.02, 440.01)]
    pays = [NS(date=date(2026, 8, 25), amount=999), NS(date=date(2026, 9, 10), amount=300)]
    bal = H.provider_balance(prov, [], bills, pays, [], today=date(2026, 9, 15))
    assert bal["debt"] == 140.01  # August payment already inside the bill


def test_fixed_provider_unbilled_estimate():
    prov = NS(service="maintenance", billing="fixed", fixed_amount=399.84, due_day=20, start_date=None,
              opening_balance=0)
    bills = [_bill(date(2026, 8, 1), 678.32, 0, 399.84, 1078.16)]
    bal = H.provider_balance(prov, [], bills, [], [], today=date(2026, 10, 15))
    assert bal["debt"] == 1078.16
    assert 550 < bal["accrued_since"] < 620  # ~1.5 months × 399.84
    assert bal["next_bill_forecast"] == 399.84


# ---------------------------------------------------------------- API

def _setup(fid, **extra):
    body = {"mode": "rent", "templates": ["electricity_2zone", "gas", "waste"], "rent_amount": 3500, "rent_day": 3}
    body.update(extra)
    r = client.post(f"/housing/families/{fid}/setup", headers=_hdr(fid), json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_setup_creates_providers_and_meters(seeded):
    fid = seeded["family"].id
    ov = _setup(fid)
    services = [p["service"] for p in ov["providers"]]
    assert services[0] == "rent" and "electricity" in services and "gas" in services
    assert len(ov["meters"]) == 3  # day + night + gas
    assert ov["profile"]["mode"] == "rent"
    # repeated setup does not duplicate rent
    ov2 = _setup(fid, templates=[])
    assert [p["service"] for p in ov2["providers"]].count("rent") == 1


def test_readings_batch_validation_and_summary(seeded):
    fid = seeded["family"].id
    ov = _setup(fid)
    day = next(m for m in ov["meters"] if m["zone"] == "day")
    today = date.today()
    d1, d2 = (today - timedelta(days=20)).isoformat(), (today - timedelta(days=2)).isoformat()
    r = client.post(f"/housing/families/{fid}/readings", headers=_hdr(fid),
                    json={"date": d1, "items": [{"meter_id": day["id"], "value": 9000}]})
    assert r.status_code == 200
    r = client.post(f"/housing/families/{fid}/readings", headers=_hdr(fid),
                    json={"date": d2, "items": [{"meter_id": day["id"], "value": 8990}]})
    assert r.status_code == 400 and "менше" in r.json()["detail"]
    r = client.post(f"/housing/families/{fid}/readings", headers=_hdr(fid),
                    json={"date": d2, "items": [{"meter_id": day["id"], "value": 9036}]})
    m = next(x for x in r.json()["overview"]["meters"] if x["id"] == day["id"])
    assert m["daily_rate"] == 2.0 and m["last_value"] == 9036
    hist = client.get(f"/housing/families/{fid}/meters/{day['id']}/readings", headers=_hdr(fid)).json()
    assert hist[0]["value"] == 9036 and hist[0]["rate"] == 2.0


def test_bill_create_autocalc_draft_and_flags(seeded):
    fid = seeded["family"].id
    ov = _setup(fid)
    elec = next(p for p in ov["providers"] if p["service"] == "electricity")
    day = next(m for m in ov["meters"] if m["zone"] == "day")
    r = client.post(f"/housing/families/{fid}/bills", headers=_hdr(fid), json={
        "provider_id": elec["id"], "period": "2026-07", "opening_balance": -21.6, "paid": 0,
        "lines": [{"meter_id": day["id"], "label": "день", "prev_value": 8723, "curr_value": 8807, "tariff": 4.32}]})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["accrued"] == 362.88 and b["to_pay"] == 341.28 and b["lines"][0]["volume"] == 84
    # duplicate period → 409
    assert client.post(f"/housing/families/{fid}/bills", headers=_hdr(fid), json={
        "provider_id": elec["id"], "period": "2026-07"}).status_code == 409
    # draft for August continues from July
    dr = client.get(f"/housing/families/{fid}/bills/draft?provider_id={elec['id']}&period=2026-08",
                    headers=_hdr(fid)).json()
    assert dr["opening_balance"] == 341.28
    assert next(ln for ln in dr["lines"] if ln["meter_id"] == day["id"])["prev_value"] == 8807
    # August bill with a wrong opening balance → continuity flag
    r = client.post(f"/housing/families/{fid}/bills", headers=_hdr(fid), json={
        "provider_id": elec["id"], "period": "2026-08", "opening_balance": 401.76, "paid": 0, "accrued": 100})
    codes = {f["code"] for f in r.json()["flags"]}
    assert "continuity" in codes
    # billed reading stored as a reading (source=bill)
    hist = client.get(f"/housing/families/{fid}/meters/{day['id']}/readings", headers=_hdr(fid)).json()
    assert any(h["source"] == "bill" and h["value"] == 8807 for h in hist)


def test_payment_with_transaction_and_delete(seeded, db):
    fid = seeded["family"].id
    db.add(models.Category(family_id=fid, icon="⚡", name="⚡️ Комуналка", color="#000", type="expense"))
    db.commit()
    ov = _setup(fid)
    gas = next(p for p in ov["providers"] if p["service"] == "gas")
    r = client.post(f"/housing/families/{fid}/payments", headers=_hdr(fid), json={
        "provider_id": gas["id"], "amount": 372, "create_transaction": True, "account": "Готівка"})
    assert r.status_code == 200, r.text
    pay = r.json()["payment"]
    tx = db.get(models.Transaction, pay["transaction_id"])
    assert tx.amount == 372 and tx.type == "Витрати" and tx.category.name == "⚡️ Комуналка"
    r = client.delete(f"/housing/families/{fid}/payments/{pay['id']}?delete_transaction=true", headers=_hdr(fid))
    assert r.status_code == 200
    db.expire_all()
    assert db.get(models.Transaction, pay["transaction_id"]) is None


def test_heating_toggle_and_notes(seeded):
    fid = seeded["family"].id
    _setup(fid)
    on = client.post(f"/housing/families/{fid}/heating", headers=_hdr(fid), json={"on": True}).json()
    assert on["on"] is True
    off = client.post(f"/housing/families/{fid}/heating", headers=_hdr(fid), json={"on": False}).json()
    assert off["on"] is False
    notes = client.get(f"/housing/families/{fid}/notes", headers=_hdr(fid)).json()
    assert notes[0]["kind"] == "heating" and notes[0]["end_date"]


def test_stats_and_overview_shapes(seeded):
    fid = seeded["family"].id
    ov = _setup(fid)
    gas = next(m for m in ov["meters"] if m["utility_type"] == "gas")
    t = date.today()
    client.post(f"/housing/families/{fid}/readings", headers=_hdr(fid),
                json={"date": (t - timedelta(days=40)).isoformat(), "items": [{"meter_id": gas["id"], "value": 800}]})
    client.post(f"/housing/families/{fid}/readings", headers=_hdr(fid),
                json={"date": t.isoformat(), "items": [{"meter_id": gas["id"], "value": 840}]})
    st = client.get(f"/housing/families/{fid}/stats?months=3", headers=_hdr(fid)).json()
    assert len(st["months"]) == 3
    series = next(s for s in st["meters"] if s["meter_id"] == gas["id"])
    assert sum(p["volume"] or 0 for p in series["points"]) > 30


def test_family_isolation_for_users(seeded, db):
    from app.core.security import create_access_token
    fid = seeded["family"].id
    other = models.Family(name="Other", invite_code="zzz999")
    db.add(other)
    db.flush()
    stranger = models.User(name="Stranger", tg_id=999, current_active_family_id=other.id)
    db.add(stranger)
    db.flush()
    db.add(models.FamilyMember(user_id=stranger.id, family_id=other.id, role="admin"))
    db.commit()
    token = create_access_token(999, stranger.id, other.id, "admin")
    r = client.get(f"/housing/families/{fid}/overview", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_provider_delete_archives_with_history(seeded):
    fid = seeded["family"].id
    ov = _setup(fid)
    waste = next(p for p in ov["providers"] if p["service"] == "waste")
    client.post(f"/housing/families/{fid}/payments", headers=_hdr(fid), json={"provider_id": waste["id"], "amount": 40})
    assert client.delete(f"/housing/families/{fid}/providers/{waste['id']}", headers=_hdr(fid)).json()["archived"]
    ov = client.get(f"/housing/families/{fid}/overview", headers=_hdr(fid)).json()
    assert waste["id"] not in [p["id"] for p in ov["providers"]]


# ---------------------------------------------------------------- svitlobot

PAGE = """
<div class="tgme_widget_message_wrap"><div data-post="svitlobot_test/10"><div class="tgme_widget_message_text js-message_text">🔴 17:24 Світло зникло<br>🕓 Воно було 6год 37хв</div><time datetime="2026-10-21T14:29:24+00:00"></time></div></div>
<div class="tgme_widget_message_wrap"><div data-post="svitlobot_test/11"><div class="tgme_widget_message_text js-message_text">🗓 Графік відключень на сьогодні</div><time datetime="2026-10-21T16:30:22+00:00"></time></div></div>
<div class="tgme_widget_message_wrap"><div data-post="svitlobot_test/12"><div class="tgme_widget_message_text js-message_text">🟢 21:13 Світло з&#39;явилося<br>🕓 Його не було 3год 49хв</div><time datetime="2026-10-21T18:13:57+00:00"></time></div></div>
"""
OLDER = """
<div class="tgme_widget_message_wrap"><div data-post="svitlobot_test/5"><div class="tgme_widget_message_text js-message_text">🟢 22:09 Світло з'явилося<br>🕓 Його не було 1год 59хв</div><time datetime="2026-10-20T19:09:19+00:00"></time></div></div>
"""


def test_svitlobot_parse_and_merge(db):
    events = svitlobot.parse_page(PAGE)
    assert [e.kind for e in events] == ["off", "on"]
    assert events[0].at == datetime(2026, 10, 21, 14, 24)
    assert events[1].duration_min == 229
    svitlobot.apply_events(db, "svitlobot_test", events)
    db.commit()
    rows = db.query(models.PowerOutage).all()
    assert len(rows) == 1
    assert rows[0].started_at == datetime(2026, 10, 21, 14, 24) and rows[0].ended_at == datetime(2026, 10, 21, 18, 13)
    # idempotent
    svitlobot.apply_events(db, "svitlobot_test", events)
    db.commit()
    assert db.query(models.PowerOutage).count() == 1


def test_svitlobot_sync_paginates_and_is_incremental(db):
    calls = []

    def fake_fetch(channel, before=None):
        calls.append(before)
        return PAGE if before is None else (OLDER if before == 10 else "")

    res = svitlobot.sync_channel(db, "svitlobot_test", fetch=fake_fetch)
    assert res["last_post_id"] == 12 and calls[:2] == [None, 10]
    assert db.query(models.PowerOutage).count() == 2  # on-only post restored an outage too
    calls.clear()
    res = svitlobot.sync_channel(db, "svitlobot_test", fetch=fake_fetch)
    assert res["events"] == 0 and calls == [None]


STALE = """
<div class="tgme_widget_message_wrap"><div data-post="svitlobot_test/20"><div class="tgme_widget_message_text js-message_text">🔴 08:00 Світло зникло<br>🕓 Воно було 5год</div><time datetime="2026-07-08T05:00:30+00:00"></time></div></div>
<div class="tgme_widget_message_wrap"><div data-post="svitlobot_test/22"><div class="tgme_widget_message_text js-message_text">🔴 18:00 Світло зникло<br>🕓 Воно було 2год</div><time datetime="2026-07-08T15:00:30+00:00"></time></div></div>
<div class="tgme_widget_message_wrap"><div data-post="svitlobot_test/23"><div class="tgme_widget_message_text js-message_text">🔴 23:00 Світло зникло</div><time datetime="2026-07-08T20:00:30+00:00"></time></div></div>
<div class="tgme_widget_message_wrap"><div data-post="svitlobot_test/24"><div class="tgme_widget_message_text js-message_text">🔴 23:50 Світло зникло</div><time datetime="2026-07-08T20:50:30+00:00"></time></div></div>
"""


def test_svitlobot_missed_on_post_does_not_count_forever(db):
    svitlobot.apply_events(db, "svitlobot_test", svitlobot.parse_page(STALE))
    db.commit()
    rows = db.query(models.PowerOutage).order_by(models.PowerOutage.started_at).all()
    # 08:00 outage ended when power came back at 16:00 (18:00 − «Воно було 2год»)
    assert rows[0].started_at == datetime(2026, 7, 8, 5, 0) and rows[0].ended_at == datetime(2026, 7, 8, 13, 0)
    # 23:00 outage had no follow-up info → closed with zero length, only the newest stays open
    assert rows[2].ended_at == rows[2].started_at
    assert [r.ended_at for r in rows].count(None) == 1 and rows[-1].ended_at is None


def test_svitlobot_channel_normalization():
    assert svitlobot.normalize_channel("https://t.me/s/svitlobot_example") == "svitlobot_example"
    assert svitlobot.normalize_channel("@svitlobot_example") == "svitlobot_example"
    assert svitlobot.normalize_channel("not a channel!") is None


def test_outage_hours_clips_to_range():
    rows = [NS(started_at=datetime(2026, 10, 31, 22), ended_at=datetime(2026, 11, 1, 2))]
    assert H.outage_hours(rows, datetime(2026, 11, 1), datetime(2026, 12, 1)) == 2.0


# ---------------------------------------------------------------- reminders

def test_reminders_readings_day_and_ack(seeded, db):
    from app.api.housing import compute_reminders
    fid = seeded["family"].id
    _setup(fid)
    client.put(f"/housing/families/{fid}/profile", headers=_hdr(fid), json={"readings_day": 5})
    rem = compute_reminders(db, today=date(2026, 11, 5))
    mine = next(r for r in rem if r["family_id"] == fid)
    assert any(k.startswith("readings:2026-11") for k in mine["keys"])
    assert set(mine["tg_ids"]) == {111, 222}
    r = client.post("/system/housing/reminders/ack", headers=BOT_HEADERS,
                    json={"items": [{"family_id": fid, "key": k} for k in mine["keys"]]})
    assert r.json()["acked"] == len(mine["keys"])
    again = [r for r in compute_reminders(db, today=date(2026, 11, 5)) if r["family_id"] == fid]
    assert again == []


def test_system_endpoints_require_key(seeded):
    assert client.get("/system/housing/reminders").status_code == 401


def test_stale_billed_reading_does_not_break_own_readings(seeded):
    # Джерело-20 kept billing water on the April reading 164 while the meter was at 242
    fid = seeded["family"].id
    ov = client.post(f"/housing/families/{fid}/setup", headers=_hdr(fid), json={"mode": "own", "templates": ["water"]}).json()
    prov, water = ov["providers"][0]["id"], ov["meters"][0]["id"]
    for d, v in (("2026-09-09", 235), ("2026-10-04", 242)):
        client.post(f"/housing/families/{fid}/readings", headers=_hdr(fid), json={"date": d, "items": [{"meter_id": water, "value": v}]})
    b = client.post(f"/housing/families/{fid}/bills", headers=_hdr(fid), json={
        "provider_id": prov, "period": "2026-09", "opening_balance": -287.08, "paid": 1, "accrued": 0,
        "lines": [{"meter_id": water, "label": "Вода", "prev_value": 164, "curr_value": 164, "tariff": 29.21, "amount": 0}]}).json()
    hist = client.get(f"/housing/families/{fid}/meters/{water}/readings", headers=_hdr(fid)).json()
    assert sorted(h["value"] for h in hist) == [235, 242]  # 164 not stored on 01.10
    flag = next(f for f in b["flags"] if f["code"] == "reading_mismatch")
    assert flag["diff"] < 0 and "старим показником" in flag["text"]
    client.post(f"/housing/families/{fid}/bills", headers=_hdr(fid), json={
        "provider_id": prov, "period": "2026-08", "opening_balance": -287.08, "accrued": 0,
        "lines": [{"meter_id": water, "label": "Вода", "prev_value": 164, "curr_value": 164, "tariff": 29.21, "amount": 0}]})
    texts = [a["text"] for a in client.get(f"/housing/families/{fid}/overview", headers=_hdr(fid)).json()["alerts"]]
    assert sum("старим показником" in t for t in texts) == 1  # same problem on two bills → one alert
