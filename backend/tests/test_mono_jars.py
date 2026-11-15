# Банки Monobank як цілі: синхронізація, перекази в/з банки — не витрати, чужі збори не чіпаємо.
from datetime import date

from app import models
from app.services import mono_jars as MJ
from tests.conftest import BOT_HEADERS, client, make_tx


def _hdr(fid):
    return {**BOT_HEADERS, "X-Family-Id": str(fid)}


def test_parse_titles():
    assert MJ.parse_jar_title("❓ Поповнення «На життя»") == ("in", "На життя")
    assert MJ.parse_jar_title("❓ Часткове зняття банки «На життя»") == ("out", "На життя")
    assert MJ.parse_jar_title("Зняття з банки «GTA 6»") == ("out", "GTA 6")
    assert MJ.parse_jar_title("Фора") is None


def test_sync_creates_goals_and_reclassifies_transfers(seeded, db):
    fam, u, c = seeded["family"], seeded["admin"], seeded["cats"]
    u.mono_token = "x"; db.commit()
    t_in = make_tx(db, fam.id, u.id, c["Очікує"].id, 1, "Витрати", title="❓ Поповнення «На життя»", account="Монобанк")
    t_out = make_tx(db, fam.id, u.id, c["Очікує"].id, 2, "Поповнення", title="❓ Часткове зняття банки «На життя»", account="Монобанк")
    charity = make_tx(db, fam.id, u.id, c["Очікує"].id, 104, "Витрати", title="❓ Поповнення «Розіграш смартфона»", account="Монобанк")
    from app.core import security
    orig = security.decrypt_secret
    security.decrypt_secret = lambda v: "token"
    try:
        res = MJ.sync_family(db, fam.id, fetch=lambda token: [
            {"id": "j1", "title": "На життя", "currencyCode": 980, "balance": 5000, "goal": 1000000}])
    finally:
        security.decrypt_secret = orig
    assert res == {"family_id": fam.id, "jars": 1, "reclassified": 2}
    db.expire_all()
    jar = db.query(models.Jar).filter_by(mono_jar_id="j1").one()
    assert jar.goal == 10000 and jar.bank_balance == 50
    a, b, ch = db.get(models.Transaction, t_in.id), db.get(models.Transaction, t_out.id), db.get(models.Transaction, charity.id)
    assert (a.jar_id, a.type, a.category_id, a.title) == (jar.id, "Поповнення", None, "У банку «На життя»")
    assert (b.jar_id, b.type) == (jar.id, "Витрати")
    assert ch.jar_id is None  # somebody else's jar stays a normal expense
    jars = client.get(f"/families/{fam.id}/jars", headers=_hdr(fam.id)).json()
    assert jars[0]["balance"] == 50 and jars[0]["mono_jar_id"] == "j1"
    # jar moves are not spending
    stats = client.get(f"/families/{fam.id}/stats", headers=_hdr(fam.id)).json()
    assert stats["expense"] == 104
    # Bimi cannot top up a Monobank jar by itself
    assert client.post(f"/jars/{jar.id}/topup", headers=BOT_HEADERS, json={"amount": 10}).status_code == 400


def test_new_webhook_transfer_goes_to_jar(seeded, db):
    fam, u, c = seeded["family"], seeded["admin"], seeded["cats"]
    db.add(models.Jar(family_id=fam.id, name="ДБЖ", goal=4000, mono_jar_id="j2", user_id=u.id, bank_balance=0)); db.commit()
    r = client.post("/transactions", headers=BOT_HEADERS, json={
        "family_id": fam.id, "user_id": u.id, "category_id": c["Очікує"].id, "amount": 500, "type": "Витрати",
        "title": "❓ Поповнення «ДБЖ»", "account": "Монобанк", "date": str(date.today())}).json()
    assert r["jar_id"] and r["type"] == "Поповнення" and r["category_id"] is None


def test_edit_and_delete_goals(seeded, db):
    fam, u = seeded["family"], seeded["admin"]
    h = _hdr(fam.id)
    empty = client.post("/jars", headers=h, json={"family_id": fam.id, "name": "Мейкап", "goal": 1000}).json()
    r = client.put(f"/jars/{empty['id']}", headers=h, json={"name": "Мейкап 2", "goal": 2000}).json()
    assert (r["name"], r["goal"]) == ("Мейкап 2", 2000)
    assert client.delete(f"/jars/{empty['id']}", headers=h).json() == {"ok": True, "archived": False}
    assert db.get(models.Jar, empty["id"]) is None
    # cash goal with money: refuse; after withdrawal: hidden, history stays
    cash = client.post("/jars", headers=h, json={"family_id": fam.id, "name": "Відпустка", "goal": 500}).json()
    client.post(f"/jars/{cash['id']}/topup", headers=h, json={"amount": 100})
    assert client.delete(f"/jars/{cash['id']}", headers=h).status_code == 400
    client.post(f"/jars/{cash['id']}/withdraw", headers=h, json={"amount": 100})
    assert client.delete(f"/jars/{cash['id']}", headers=h).json()["archived"] is True
    assert cash["id"] not in [j["id"] for j in client.get(f"/families/{fam.id}/jars", headers=h).json()]
    # Monobank jar: name is the bank's; hidden one stays hidden on sync while empty, reappears when money comes in
    MJ.upsert_jars(db, fam.id, u.id, [{"id": "g", "title": "GTA VI", "currencyCode": 980, "balance": 0, "goal": 0}]); db.commit()
    gta = db.query(models.Jar).filter_by(mono_jar_id="g").one()
    assert client.put(f"/jars/{gta.id}", headers=h, json={"name": "x"}).status_code == 400
    assert client.delete(f"/jars/{gta.id}", headers=h).json()["archived"] is True
    MJ.upsert_jars(db, fam.id, u.id, [{"id": "g", "title": "GTA VI", "currencyCode": 980, "balance": 0}]); db.commit()
    assert gta.id not in [j["id"] for j in client.get(f"/families/{fam.id}/jars", headers=h).json()]
    MJ.upsert_jars(db, fam.id, u.id, [{"id": "g", "title": "GTA VI", "currencyCode": 980, "balance": 500}]); db.commit()
    assert gta.id in [j["id"] for j in client.get(f"/families/{fam.id}/jars", headers=h).json()]
