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


def test_auto_categorize_new_bank_operation_and_learn_from_corrections(db, seeded):
    fid, uid = seeded["family"].id, seeded["admin"].id
    pend = seeded["cats"]["Очікує"].id
    c = _cats(db, fid, "🚆 Громад. транспорт", "☕ Щоденні дрібниці")
    for _ in range(3):
        make_tx(db, fid, uid, c["🚆 Громад. транспорт"].id, 30, "Витрати", title="Київське метро", account="Монобанк")
    make_tx(db, fid, uid, c["☕ Щоденні дрібниці"].id, 60, "Витрати", title="Кавомашина", account="Монобанк")
    body = {"family_id": fid, "user_id": uid, "category_id": pend, "amount": 30, "type": "Витрати",
            "title": "❓ Київське метро", "account": "Монобанк", "date": "2026-10-29", "mcc": 4111}
    r = client.post("/transactions", headers=_hdr(fid), json=body).json()
    assert r["category_id"] == c["🚆 Громад. транспорт"].id and r["auto_category"] and r["title"] == "Київське метро"
    assert r["mcc"] == 4111
    # only one example → not automatic, stays in the Inbox with a suggestion
    r2 = client.post("/transactions", headers=_hdr(fid), json={**body, "title": "❓ Кавомашина", "amount": 60, "mcc": None}).json()
    assert r2["category_id"] == pend and not r2["auto_category"]
    # a person corrects Bimi → 🤖 mark gone, Bimi stops putting metro into transport
    fixed = client.put(f"/transactions/{r['id']}", headers=_hdr(fid), json={"category_id": c["☕ Щоденні дрібниці"].id}).json()
    assert not fixed["auto_category"]
    r3 = client.post("/transactions", headers=_hdr(fid), json=body).json()
    assert r3["category_id"] == pend
    # family switch off
    client.put(f"/families/{fid}/smart", headers=_hdr(fid), json={"smart_auto": False})
    s = client.get(f"/families/{fid}/inbox/suggestions", headers=_hdr(fid)).json()
    assert s["smart_auto"] is False


def test_reject_hides_suggestion(db, seeded):
    fid, uid = seeded["family"].id, seeded["admin"].id
    pend = seeded["cats"]["Очікує"].id
    c = _cats(db, fid, "🏥 Здоров'я")
    make_tx(db, fid, uid, c["🏥 Здоров'я"].id, 300, "Витрати", title="Нова пошта")
    tx = make_tx(db, fid, uid, pend, 250, "Витрати", title="❓ Нова пошта")
    assert str(tx.id) in client.get(f"/families/{fid}/inbox/suggestions", headers=_hdr(fid)).json()["by_tx"]
    client.post(f"/families/{fid}/inbox/reject", headers=_hdr(fid), json={"title": "Нова пошта", "category_id": c["🏥 Здоров'я"].id})
    by = client.get(f"/families/{fid}/inbox/suggestions", headers=_hdr(fid)).json()["by_tx"]
    assert by.get(str(tx.id), {}).get("category_id") != c["🏥 Здоров'я"].id


def test_monobank_accounts_readable_names_and_credit(monkeypatch):
    import asyncio
    from app.services.banking.monobank import MonobankProvider
    p = MonobankProvider()
    async def fake(token, ttl=60):
        return {"accounts": [
            {"id": "a", "type": "black", "currencyCode": 980, "balance": 5_300_00, "creditLimit": 5_000_00, "maskedPan": ["537541******1234"]},
            {"id": "b", "type": "white", "currencyCode": 840, "balance": 120_00, "creditLimit": 0, "maskedPan": []}]}
    monkeypatch.setattr(p, "get_client_info", fake)
    a, b = asyncio.run(p.get_accounts("t"))
    assert a.name == "Чорна картка" and a.last4 == "1234" and a.currency == "UAH" and a.balance - a.credit_limit == 300
    assert b.name == "Біла картка USD" and b.currency == "USD"


def test_refunds_learned_per_person_and_ordered(db, seeded):
    # friends paying back: ↩️ Соціальні події most often → first; a person's usual refund category is suggested
    fid, uid = seeded["family"].id, seeded["admin"].id
    pend = seeded["cats"]["Очікує"].id
    c = _cats(db, fid, "🍻 Соціальні події", "💼 Робочі витрати", "🎁 Подарунки")
    for title, cat in (("Від: Кирило", "🍻 Соціальні події"), ("Від: Кирило", "🍻 Соціальні події"),
                       ("Від: Саша", "🍻 Соціальні події"), ("Від: Олег", "💼 Робочі витрати")):
        make_tx(db, fid, uid, c[cat].id, 250, "Поповнення", title=title).refund = True
    make_tx(db, fid, uid, c["🎁 Подарунки"].id, 2000, "Поповнення", title="Від: Кирило")  # a gift, not a refund
    db.commit()
    t = make_tx(db, fid, uid, pend, 270, "Поповнення", title="❓ Від: Кирило (за піцу)")
    out = smart.suggestions(db, fid)
    assert out["refund_order"][:2] == [c["🍻 Соціальні події"].id, c["💼 Робочі витрати"].id]
    s = out["by_tx"][str(t.id)]
    assert s["category_id"] == c["🍻 Соціальні події"].id and s["refund"] is True
    g = next(g for g in out["groups"] if t.id in g["transaction_ids"])
    r = client.post(f"/families/{fid}/inbox/apply", headers=_hdr(fid), json={"items": [
        {"transaction_id": t.id, "category_id": g["category_id"], "refund": g["refund"]}]})
    assert r.json()["applied"] == 1
    db.refresh(t)
    assert t.refund is True and t.category_id == c["🍻 Соціальні події"].id


def test_family_transfer_pair_is_internal_and_auto(db, seeded):
    # Вадим sends Аня 500: −500 «Сонце 💖» + «Від: Вадим Шевчук» +500 → «Переказ», not expense nor income
    from datetime import date as _d
    from app.services import analytics as A
    fam, vadym, pend = seeded["family"], seeded["admin"], seeded["cats"]["Очікує"].id
    anya = models.User(tg_id=777001, name="Аня")
    db.add(anya); db.flush(); db.add(models.FamilyMember(family_id=fam.id, user_id=anya.id, role="member")); db.commit()
    vadym.name = "Вадим"
    tr = models.Category(family_id=fam.id, icon="🔄", name="🔄 Переказ", color="#000", type="income")
    db.add(tr); db.commit()
    today = _d.today()
    out = make_tx(db, fam.id, vadym.id, pend, 500, "Витрати", title="❓ Сонце 💖", account="Монобанк", date=today)
    r = client.post("/transactions", headers=BOT_HEADERS, json={
        "family_id": fam.id, "user_id": anya.id, "category_id": pend, "amount": 500, "type": "Поповнення",
        "title": "❓ Від: Вадим Шевчук", "account": "Монобанк", "date": today.isoformat()})
    assert r.json()["category_id"] == tr.id and r.json()["auto_category"] is True
    db.refresh(out)
    assert out.category_id == tr.id  # the partner leg went with it
    a = A.month_analytics(db, fam.id, today.replace(day=1), today=today)
    assert a["expense"] == 0 and a["income"] == 0
    assert client.get(f"/families/{fam.id}/stats", headers=_hdr(fam.id)).json()["expense"] == 0
    # a friend's «Від: Олег» +200 and Вадим's 200 ₴ shop the same day: suggested at most, never auto
    shop = make_tx(db, fam.id, vadym.id, pend, 200, "Витрати", title="❓ Сільпо", date=today)
    friend = make_tx(db, fam.id, anya.id, pend, 200, "Поповнення", title="❓ Від: Олег", date=today)
    s = smart.Brain(db, fam.id).suggest(friend)
    assert s["source"] == "family" and s["auto"] is False and shop.id == s["pair_id"]


def test_family_transfer_pairs_closest_mutual_leg(db, seeded):
    # 19.08 −400 bowling (Микола) must not take the pair of 20.08 «На каву» −400 «Сонце 💖» / +400 «Від: Вадим»
    from datetime import date as _d
    fam, vadym, pend = seeded["family"], seeded["admin"], seeded["cats"]["Очікує"].id
    anya = models.User(tg_id=777002, name="Аня")
    db.add(anya); db.flush(); db.add(models.FamilyMember(family_id=fam.id, user_id=anya.id, role="member"))
    db.add(models.Category(family_id=fam.id, icon="🔄", name="🔄 Переказ", color="#000", type="income")); db.commit()
    bowling = make_tx(db, fam.id, vadym.id, pend, 400, "Витрати", title="❓ Микола К.", date=_d(2026, 8, 19))
    got = make_tx(db, fam.id, anya.id, pend, 400, "Поповнення", title="❓ Від: Вадим Шевчук (На каву)", date=_d(2026, 8, 20))
    sent = make_tx(db, fam.id, vadym.id, pend, 400, "Витрати", title="❓ Сонце 💖 (На каву)", date=_d(2026, 8, 20))
    b = smart.Brain(db, fam.id)
    assert b.transfer_pair(got).id == sent.id and b.transfer_pair(sent).id == got.id
    assert b.transfer_pair(bowling) is None


def test_family_transfer_pair_with_sender_fee(db, seeded):
    # Аня sends 700 from credit funds: −728 «Вадим Ш.» (4 % fee) ↔ +700 «Від: Анна Казанець» at Вадим
    from datetime import date as _d
    fam, vadym, pend = seeded["family"], seeded["admin"], seeded["cats"]["Очікує"].id
    anya = models.User(tg_id=777003, name="Аня")
    db.add(anya); db.flush(); db.add(models.FamilyMember(family_id=fam.id, user_id=anya.id, role="member"))
    db.add(models.Category(family_id=fam.id, icon="🔄", name="🔄 Переказ", color="#000", type="income")); db.commit()
    sent = make_tx(db, fam.id, anya.id, pend, 728, "Витрати", title="❓ Вадим Ш.", date=_d(2026, 9, 22))
    got = make_tx(db, fam.id, vadym.id, pend, 700, "Поповнення", title="❓ Від: Анна Казанець", date=_d(2026, 9, 22))
    s = smart.Brain(db, fam.id).suggest(sent)
    assert s["source"] == "family" and s["pair_id"] == got.id and "комісія 28 ₴" in s["reason"]
