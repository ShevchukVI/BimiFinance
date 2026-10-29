"""«Bimi пропонує»: категорії з історії (назва + сума), MCC і відомих мереж; групове підтвердження."""
from app import models
from app.services import smart
from tests.conftest import BOT_HEADERS, client, make_tx


def _hdr(fid):
    return {**BOT_HEADERS, "X-Family-Id": str(fid)}


def _cats(db, fid, *names):
    out = {}
    for n in names:
        c = models.Category(family_id=fid, icon="•", name=n, color="#000", type="expense")
        db.add(c)
        db.flush()
        out[n] = c
    db.commit()
    return out


def test_history_amount_bands_mcc_chains_and_group_apply(db, seeded):
    fid, uid = seeded["family"].id, seeded["admin"].id
    pend = seeded["cats"]["Очікує"].id
    c = _cats(db, fid, "🚆 Громад. транспорт", "⛽ Паливо", "☕ Щоденні дрібниці", "🛒 Продукти")
    for _ in range(4):
        make_tx(db, fid, uid, c["🚆 Громад. транспорт"].id, 30, "Витрати", title="Київське метро", account="Монобанк")
    for amt in (60, 70, 95):
        make_tx(db, fid, uid, c["☕ Щоденні дрібниці"].id, amt, "Витрати", title="AZS 4", account="Монобанк")
    for amt in (1272, 1051):
        make_tx(db, fid, uid, c["⛽ Паливо"].id, amt, "Витрати", title="AZS 4", account="Монобанк")
    m1 = make_tx(db, fid, uid, pend, 30, "Витрати", title="❓ Київське метро", account="Монобанк")
    m2 = make_tx(db, fid, uid, pend, 30, "Витрати", title="❓ Київське метро", account="Монобанк")
    coffee = make_tx(db, fid, uid, pend, 65, "Витрати", title="❓ AZS 4", account="Монобанк")
    fill = make_tx(db, fid, uid, pend, 999.89, "Витрати", title="❓ AZS 4", account="Монобанк")
    silpo = make_tx(db, fid, uid, pend, 420, "Витрати", title="❓ Сільпо", account="Монобанк")
    wog = make_tx(db, fid, uid, pend, 1500, "Витрати", title="❓ Якась АЗС", account="Монобанк")
    wog.mcc = 5541
    unknown = make_tx(db, fid, uid, pend, 500, "Витрати", title="❓ ФОП Іваненко", account="Монобанк")
    db.commit()

    r = client.get(f"/families/{fid}/inbox/suggestions", headers=_hdr(fid)).json()
    by = {int(k): v for k, v in r["by_tx"].items()}
    assert by[m1.id]["category_id"] == c["🚆 Громад. транспорт"].id and by[m1.id]["confidence"] == "sure"
    assert by[coffee.id]["category_id"] == c["☕ Щоденні дрібниці"].id  # small sum at the station = coffee
    assert by[fill.id]["category_id"] == c["⛽ Паливо"].id  # big sum there = fuel
    assert "Продукти" in db.get(models.Category, by[silpo.id]["category_id"]).name
    assert by[silpo.id]["source"] == "chain" and by[silpo.id]["confidence"] == "likely"
    assert by[wog.id]["category_id"] == c["⛽ Паливо"].id and by[wog.id]["source"] == "mcc"
    assert unknown.id not in by
    metro = next(g for g in r["groups"] if g["title"] == "Київське метро")
    assert metro["count"] == 2 and set(metro["transaction_ids"]) == {m1.id, m2.id} and r["groups"][0]["confidence"] == "sure"

    # one tap for the group; a category set by hand meanwhile is never overwritten
    client.put(f"/transactions/{m2.id}", headers=_hdr(fid), json={"category_id": c["🛒 Продукти"].id})
    res = client.post(f"/families/{fid}/inbox/apply", headers=_hdr(fid), json={"items": [
        {"transaction_id": m1.id, "category_id": c["🚆 Громад. транспорт"].id},
        {"transaction_id": m2.id, "category_id": c["🚆 Громад. транспорт"].id}]}).json()
    assert res["applied"] == 1
    db.expire_all()
    assert db.get(models.Transaction, m1.id).category_id == c["🚆 Громад. транспорт"].id
    assert db.get(models.Transaction, m1.id).title == "Київське метро"
    assert db.get(models.Transaction, m2.id).category_id == c["🛒 Продукти"].id
    one = client.get(f"/families/{fid}/transactions/{fill.id}/suggest", headers=_hdr(fid)).json()
    assert one["category_name"] == "⛽ Паливо"


def test_income_category_never_suggested_for_expense(db, seeded):
    fid, uid = seeded["family"].id, seeded["admin"].id
    salary = seeded["cats"]["Зарплата"].id
    make_tx(db, fid, uid, salary, 1000, "Витрати", title="City24")  # odd old data
    make_tx(db, fid, uid, salary, 2000, "Витрати", title="City24")
    tx = make_tx(db, fid, uid, seeded["cats"]["Очікує"].id, 1500, "Витрати", title="❓ City24")
    assert smart.Brain(db, fid).suggest(tx) is None
