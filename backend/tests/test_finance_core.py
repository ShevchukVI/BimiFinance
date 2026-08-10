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


# ---------- USER AUTH: Mini App категоризація (регресія 500) ----------

def _make_user_token(seeded, user_id):
    """JWT для Mini App user (імітація Telegram initData flow)."""
    from app.core.security import create_access_token
    tg_id = seeded["admin"].tg_id
    return create_access_token(tg_id, user_id, seeded["family"].id, "admin")


def test_user_categorize_pending_no_500(seeded, db):
    """Користувач Mini App має мати можливість категоризувати pending-транзакцію.
    Регресія: 'Depends object has no attribute query' -> 500."""
    fam, admin, cats = seeded["family"], seeded["admin"], seeded["cats"]
    tx = make_tx(db, fam.id, admin.id, cats["Очікує"].id, 77, "Витрати",
                 title="❓ Тест", account="Монобанк", mono_id=None)
    token = _make_user_token(seeded, admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.put(f"/transactions/{tx.id}", headers=headers,
                   json={"category_id": cats["Продукти"].id})
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    assert r.json()["category_id"] == cats["Продукти"].id
    # транзакція більше не pending
    assert client.get(f"/families/{fam.id}/pending", headers=_hdr(fam.id)).json() == []


def test_user_create_transaction_no_500(seeded):
    """Створення транзакції Mini App user не має падати (регресія require_family)."""
    fam = seeded["family"]
    token = _make_user_token(seeded, seeded["admin"].id)
    r = client.post("/transactions", headers={"Authorization": f"Bearer {token}"}, json={
        "family_id": fam.id, "user_id": seeded["admin"].id, "category_id": seeded["cats"]["Кафе"].id,
        "amount": 150, "type": "Витрати", "title": "Кава", "account": "Готівка",
        "date": "2026-08-10"})
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"


def test_user_create_note_no_500(seeded):
    fam = seeded["family"]
    token = _make_user_token(seeded, seeded["admin"].id)
    r = client.post("/notes", headers={"Authorization": f"Bearer {token}"},
                    json={"family_id": fam.id, "content": "тест"})
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"


# ---------- POST-CATEGORIZATION: title cleanup + user attribution ----------

def test_categorize_strips_pending_markers(seeded, db):
    """Після категоризації з назви зникають '❓', '(нерозібрано)', '(не розібрано)'."""
    fam, admin, cats = seeded["family"], seeded["admin"], seeded["cats"]
    token = _make_user_token(seeded, admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    for title in ("❓ Сільпо", "❓ Новус (нерозібрано)", "❓ Тест (не розібрано)"):
        tx = make_tx(db, fam.id, admin.id, cats["Очікує"].id, 50, "Витрати", title=title)
        r = client.put(f"/transactions/{tx.id}", headers=headers,
                       json={"category_id": cats["Продукти"].id})
        assert r.status_code == 200
        assert r.json()["title"] == title.replace("❓ ", "").replace(" (нерозібрано)", "").replace(" (не розібрано)", "").strip(), r.json()["title"]


def test_transaction_out_has_user_name(seeded, db):
    """TransactionOut містить user_name для атрибуції (хто створив)."""
    fam, admin, cats = seeded["family"], seeded["admin"], seeded["cats"]
    tx = make_tx(db, fam.id, admin.id, cats["Кафе"].id, 100, "Витрати", title="Кава")
    r = client.get(f"/families/{fam.id}/transactions?limit=100", headers=_hdr(fam.id))
    assert r.status_code == 200
    txs = r.json()
    mine = next(t for t in txs if t["id"] == tx.id)
    assert mine["user_name"] == "Admin"


def test_update_with_date_and_note_ok(seeded, db):
    """Регресія pydantic 2.13.4: 'Optional[date] = None' падав з 422 none_required.
    TxModal шле date:str + note — має зберегтись 200."""
    fam, admin, cats = seeded["family"], seeded["admin"], seeded["cats"]
    tx = make_tx(db, fam.id, admin.id, cats["Кафе"].id, 100, "Витрати", title="Кава")
    token = _make_user_token(seeded, admin.id)
    r = client.put(f"/transactions/{tx.id}", headers={"Authorization": f"Bearer {token}"},
                   json={"amount": 150, "type": "Витрати", "title": "Кава",
                         "category_id": cats["Кафе"].id, "date": "2026-08-10", "note": "123321"})
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    body = r.json()
    assert body["note"] == "123321"
    assert str(body["date"]) == "2026-08-10"


def test_bank_balances_empty_when_no_tokens(seeded):
    """Без підключених банків endpoint віддає порожній список (HomePage ховає блок)."""
    fam = seeded["family"]
    r = client.get(f"/banking/families/{fam.id}/bank-balances", headers=_hdr(fam.id))
    assert r.status_code == 200
    assert r.json() == []


# ---------- POST-RELEASE TWEAKS ----------

def test_categorize_preserves_original_user(seeded, db):
    """Категоризація чужої pending-транзакції НЕ повинна змінювати user_id.
    Адмін категоризує транзакцію учасника — вона лишається за учасником."""
    fam, admin, member, cats = seeded["family"], seeded["admin"], seeded["member"], seeded["cats"]
    # pending-транзакцію створив member
    tx = make_tx(db, fam.id, member.id, cats["Очікує"].id, 90, "Витрати",
                 title="❓ Чужі продукти", account="Монобанк", mono_id=None)
    token = _make_user_token(seeded, admin.id)
    r = client.put(f"/transactions/{tx.id}", headers={"Authorization": f"Bearer {token}"},
                   json={"category_id": cats["Продукти"].id})
    assert r.status_code == 200
    body = r.json()
    assert body["category_id"] == cats["Продукти"].id
    # user_id залишається у member (автор транзакції не перезаписується)
    assert body["user_id"] == member.id
    # і навіть якщо спробувати передати user_id в payload — він ігнорується
    r2 = client.put(f"/transactions/{tx.id}", headers={"Authorization": f"Bearer {token}"},
                    json={"note": "спроба змінити", "user_id": admin.id, "family_id": 999})
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["user_id"] == member.id
    assert body2["family_id"] == fam.id


def test_stats_cash_by_user(seeded, db):
    """stats.cash_by_user групує готівку по користувачах сім'ї."""
    fam, admin, member, cats = seeded["family"], seeded["admin"], seeded["member"], seeded["cats"]
    # admin: +5000 зарплата, -250 кава  (готівка)
    make_tx(db, fam.id, admin.id, cats["Зарплата"].id, 5000, "Поповнення", title="Зарплата")
    make_tx(db, fam.id, admin.id, cats["Кафе"].id, 250, "Витрати", title="Кава")
    # member: +1000 дохід, -100 витрата (готівка)
    make_tx(db, fam.id, member.id, cats["Зарплата"].id, 1000, "Поповнення", title="Дохід")
    make_tx(db, fam.id, member.id, cats["Кафе"].id, 100, "Витрати", title="Кава")

    stats = client.get(f"/families/{fam.id}/stats", headers=_hdr(fam.id)).json()
    by_user = {u["user_id"]: u for u in stats["cash_by_user"]}
    assert by_user[admin.id]["balance"] == 4750
    assert by_user[member.id]["balance"] == 900
    assert by_user[admin.id]["user_name"] == "Admin"
    assert stats["balances"]["Готівка"] == 5650  # загальна сума = сума по користувачах


# ---------- PHASE 2: MULTI-CURRENCY + DEEP JARS ----------

def _mk_jars(db, seeded, name="Відпустка"):
    fam = seeded["family"]
    r = client.post("/jars", headers=BOT_HEADERS,
                    json={"family_id": fam.id, "name": name, "goal": 30000, "currency": "UAH"})
    assert r.status_code == 200, r.text
    return r.json()


def test_create_jar_defaults_currency_and_dynamic_balance(seeded, db):
    fam = seeded["family"]
    jar = _mk_jars(db, seeded)
    assert jar["currency"] == "UAH"
    assert jar["balance"] == 0.0  # динамічний баланс без транзакцій = 0


def test_jar_topup_and_dynamic_balance(seeded, db):
    fam = seeded["family"]
    jar = _mk_jars(db, seeded)
    # поповнення через API
    r = client.post(f"/jars/{jar['id']}/topup", headers=BOT_HEADERS, json={"amount": 7500})
    assert r.status_code == 200, r.text
    assert r.json()["balance"] == 7500
    # повторний get_jars теж рахує динамічно
    jars = client.get(f"/families/{fam.id}/jars", headers=_hdr(fam.id)).json()
    assert jars[0]["balance"] == 7500


def test_jar_withdraw(seeded, db):
    fam = seeded["family"]
    jar = _mk_jars(db, seeded)
    client.post(f"/jars/{jar['id']}/topup", headers=BOT_HEADERS, json={"amount": 5000})
    r = client.post(f"/jars/{jar['id']}/withdraw", headers=BOT_HEADERS, json={"amount": 2000})
    assert r.status_code == 200, r.text
    assert r.json()["balance"] == 3000


def test_jar_transactions_excluded_from_stats(seeded, db):
    """Поповнення скарбнички НЕ має збільшувати місячний дохід/витрату."""
    fam, admin, cats = seeded["family"], seeded["admin"], seeded["cats"]
    make_tx(db, fam.id, admin.id, cats["Зарплата"].id, 5000, "Поповнення", title="Зарплата")
    jar = _mk_jars(db, seeded)
    client.post(f"/jars/{jar['id']}/topup", headers=BOT_HEADERS, json={"amount": 3000})
    stats = client.get(f"/families/{fam.id}/stats", headers=_hdr(fam.id)).json()
    assert stats["income"] == 5000  # 3000 у скарбничку не рахується
    assert stats["expense"] == 0


def test_stats_by_currency(seeded, db):
    """Місячні дохід/витрати групуються по валютах; income/expense — у UAH."""
    fam, admin, cats = seeded["family"], seeded["admin"], seeded["cats"]
    # UAH дохід 5000, UAH витрата 250
    make_tx(db, fam.id, admin.id, cats["Зарплата"].id, 5000, "Поповнення", title="Зарплата")
    make_tx(db, fam.id, admin.id, cats["Кафе"].id, 250, "Витрати", title="Кава")
    # USD дохід 1000, USD витрата 0
    make_tx(db, fam.id, admin.id, cats["Зарплата"].id, 1000, "Поповнення", title="Зарплата USD", currency="USD")
    make_tx(db, fam.id, admin.id, cats["Кафе"].id, 50, "Витрати", title="Кава USD", currency="USD")

    stats = client.get(f"/families/{fam.id}/stats", headers=_hdr(fam.id)).json()
    assert stats["income"] == 5000  # UAH only
    assert stats["expense"] == 250
    assert stats["by_currency"]["UAH"] == {"income": 5000.0, "expense": 250.0}
    assert stats["by_currency"]["USD"] == {"income": 1000.0, "expense": 50.0}


def test_cash_balance_grouped_by_currency(seeded, db):
    """Готівка групується по user_id І валюті; не змішується."""
    fam, admin, member, cats = seeded["family"], seeded["admin"], seeded["member"], seeded["cats"]
    make_tx(db, fam.id, admin.id, cats["Зарплата"].id, 5000, "Поповнення", title="UAH", currency="UAH")
    make_tx(db, fam.id, admin.id, cats["Зарплата"].id, 1000, "Поповнення", title="USD", currency="USD")
    make_tx(db, fam.id, admin.id, cats["Кафе"].id, 250, "Витрати", title="UAH витрата", currency="UAH")

    stats = client.get(f"/families/{fam.id}/stats", headers=_hdr(fam.id)).json()
    # по валютах
    by_cur = {c["currency"]: c["balance"] for c in stats["cash_by_currency"]}
    assert by_cur["UAH"] == 4750
    assert by_cur["USD"] == 1000
    # по користувачах+валюті
    by_user = {(u["user_id"], u["currency"]): u["balance"] for u in stats["cash_by_user"]}
    assert by_user[(admin.id, "UAH")] == 4750
    assert by_user[(admin.id, "USD")] == 1000
    # зворотна сумісність: balances['Готівка'] — UAH
    assert stats["balances"]["Готівка"] == 4750


def test_create_transaction_with_currency_and_jar(seeded, db):
    """Створення транзакції з currency та jar_id через API."""
    fam, admin, cats = seeded["family"], seeded["admin"], seeded["cats"]
    jar = _mk_jars(db, seeded)
    r = client.post("/transactions", headers=BOT_HEADERS, json={
        "family_id": fam.id, "user_id": admin.id, "category_id": cats["Кафе"].id,
        "amount": 100, "type": "Витрати", "title": "Кава USD", "account": "Готівка",
        "date": "2026-08-10", "currency": "USD", "jar_id": jar["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["currency"] == "USD"
    assert body["jar_id"] == jar["id"]
