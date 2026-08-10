# Тести фінансового ядра: перекази (Cash↔Bank), баланс готівки, stats, pending, note.
from tests.conftest import BOT_HEADERS, client, make_tx


def _hdr(fid):
    return {**BOT_HEADERS, "X-Family-Id": str(fid)}


# ---------- TRANSFERS (Cash ↔ Bank) ----------

def test_transfer_creates_signed_pair(seeded, db):
    fid = seeded["family"].id
    r = client.post("/transactions/transfer", headers=BOT_HEADERS, json={
        "family_id": fid, "user_id": seeded["admin"].id, "amount": 3000,
        "from_account": "Монобанк", "to_account": "Готівка"})
    assert r.status_code == 200
    pair = r.json()
    assert len(pair) == 2
    by_acc = {t["account"]: t for t in pair}
    assert by_acc["Монобанк"]["amount"] == -3000
    assert by_acc["Готівка"]["amount"] == 3000
    assert all(t["type"] == "Переказ" for t in pair)
    assert all(t["category_id"] is None for t in pair)


def test_transfer_validation(seeded):
    fid = seeded["family"].id
    r = client.post("/transactions/transfer", headers=BOT_HEADERS, json={
        "family_id": fid, "user_id": 1, "amount": -5,
        "from_account": "Монобанк", "to_account": "Готівка"})
    assert r.status_code == 400
    r = client.post("/transactions/transfer", headers=BOT_HEADERS, json={
        "family_id": fid, "user_id": 1, "amount": 5,
        "from_account": "Готівка", "to_account": "Готівка"})
    assert r.status_code == 400


def test_transfer_not_counted_as_income_or_expense(seeded, db):
    fid = seeded["family"].id
    client.post("/transactions/transfer", headers=BOT_HEADERS, json={
        "family_id": fid, "user_id": seeded["admin"].id, "amount": 3000,
        "from_account": "Монобанк", "to_account": "Готівка"})
    stats = client.get(f"/families/{fid}/stats", headers=_hdr(fid)).json()
    assert stats["income"] == 0
    assert stats["expense"] == 0
    # ...але баланс готівки зріс на суму зняття
    assert stats["balances"]["Готівка"] == 3000


# ---------- CASH BALANCE ----------

def test_cash_balance_full_cycle(seeded, db):
    """Зарплата готівкою 5000 → витрата 250 → зняття 3000 з банку → депозит 1000 на банк."""
    fam, admin, cats = seeded["family"], seeded["admin"], seeded["cats"]
    make_tx(db, fam.id, admin.id, cats["Зарплата"].id, 5000, "Поповнення")
    make_tx(db, fam.id, admin.id, cats["Кафе"].id, 250, "Витрати")
    client.post("/transactions/transfer", headers=BOT_HEADERS, json={
        "family_id": fam.id, "user_id": admin.id, "amount": 3000,
        "from_account": "Монобанк", "to_account": "Готівка"})
    client.post("/transactions/transfer", headers=BOT_HEADERS, json={
        "family_id": fam.id, "user_id": admin.id, "amount": 1000,
        "from_account": "Готівка", "to_account": "Монобанк"})
    stats = client.get(f"/families/{fam.id}/stats", headers=_hdr(fam.id)).json()
    # 5000 - 250 + 3000 - 1000 = 6750
    assert stats["balances"]["Готівка"] == 6750
    # місячна статистика враховує лише реальні доходи/витрати
    assert stats["income"] == 5000
    assert stats["expense"] == 250


def test_cash_balance_isolated_per_family(seeded, db):
    fam, admin, cats = seeded["family"], seeded["admin"], seeded["cats"]
    other = models_family = None
    from app import models
    fam2 = models.Family(name="Other", invite_code="other1")
    db.add(fam2)
    db.commit()
    make_tx(db, fam.id, admin.id, cats["Зарплата"].id, 1000, "Поповнення")
    s1 = client.get(f"/families/{fam.id}/stats", headers=_hdr(fam.id)).json()
    s2 = client.get(f"/families/{fam2.id}/stats", headers=_hdr(fam2.id)).json()
    assert s1["balances"]["Готівка"] == 1000
    assert s2["balances"]["Готівка"] == 0


# ---------- PENDING (Inbox Zero) ----------

def test_pending_flow(seeded, db):
    fam, admin, cats = seeded["family"], seeded["admin"], seeded["cats"]
    tx = make_tx(db, fam.id, admin.id, cats["Очікує"].id, 99.5, "Витрати",
                 title="❓ Фора", account="Монобанк", mono_id="m1")
    make_tx(db, fam.id, admin.id, cats["Кафе"].id, 50, "Витрати")

    pend = client.get(f"/families/{fam.id}/pending", headers=_hdr(fam)).json()
    assert len(pend) == 1 and pend[0]["title"] == "❓ Фора"

    stats = client.get(f"/families/{fam.id}/stats", headers=_hdr(fam.id)).json()
    assert stats["pending_count"] == 1

    # категоризація → зникає з pending
    r = client.put(f"/transactions/{tx.id}", headers=BOT_HEADERS,
                   json={"category_id": cats["Продукти"].id})
    assert r.status_code == 200
    assert client.get(f"/families/{fam.id}/pending", headers=_hdr(fam)).json() == []


# ---------- NOTE (user description) ----------

def test_note_update(seeded, db):
    fam, admin, cats = seeded["family"], seeded["admin"], seeded["cats"]
    tx = make_tx(db, fam.id, admin.id, cats["Кафе"].id, 150, "Витрати", title="Кава")
    r = client.put(f"/transactions/{tx.id}", headers=BOT_HEADERS,
                   json={"note": "цибуля 200 г, морква 500 г"})
    assert r.status_code == 200
    body = r.json()
    assert body["note"] == "цибуля 200 г, морква 500 г"
    assert body["title"] == "Кава"  # title не змінюється
