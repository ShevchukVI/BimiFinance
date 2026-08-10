import secrets
from datetime import date, datetime
from sqlalchemy import extract
from sqlalchemy.orm import Session
from app import models

# --- Джерела коштів / типи ---
ACCOUNT_CASH = "Готівка"
TYPE_INCOME = "Поповнення"
TYPE_EXPENSE = "Витрати"
TYPE_TRANSFER = "Переказ"
DEFAULT_CURRENCY = "UAH"


def _attach_derived(db: Session, user, family_id: int = None):
    user.has_mono_token = bool(user.mono_token)
    user.role = None
    target = family_id or user.current_active_family_id
    if target:
        mem = (db.query(models.FamilyMember)
               .filter(models.FamilyMember.user_id == user.id,
                       models.FamilyMember.family_id == target).first())
        if mem:
            user.role = mem.role
    return user


def get_families(db: Session): return db.query(models.Family).order_by(models.Family.id).all()
def get_family_by_id(db: Session, family_id: int): return db.query(models.Family).filter(models.Family.id == family_id).first()
def get_family_by_invite(db: Session, invite_code: str): return db.query(models.Family).filter(models.Family.invite_code == invite_code).first()
def create_family(db: Session, name: str):
    inv_code = secrets.token_urlsafe(8)
    obj = models.Family(name=name, invite_code=inv_code)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
def regenerate_invite(db: Session, family_id: int):
    family = db.query(models.Family).filter(models.Family.id == family_id).first()
    if family:
        family.invite_code = secrets.token_urlsafe(8)
        db.commit()
        db.refresh(family)
    return family


def is_family_member(db: Session, user_id: int, family_id: int) -> bool:
    return (db.query(models.FamilyMember)
            .filter(models.FamilyMember.user_id == user_id,
                    models.FamilyMember.family_id == family_id).first()) is not None

def get_membership_role(db: Session, user_id: int, family_id: int):
    mem = (db.query(models.FamilyMember)
           .filter(models.FamilyMember.user_id == user_id,
                   models.FamilyMember.family_id == family_id).first())
    return mem.role if mem else None

def add_membership(db: Session, user_id: int, family_id: int, role: str = "member"):
    if not is_family_member(db, user_id, family_id):
        db.add(models.FamilyMember(user_id=user_id, family_id=family_id, role=role))
        db.commit()

def get_user_families(db: Session, user_id: int):
    return (db.query(models.Family, models.FamilyMember.role)
            .join(models.FamilyMember, models.Family.id == models.FamilyMember.family_id)
            .filter(models.FamilyMember.user_id == user_id)
            .order_by(models.Family.id).all())

def set_active_family(db: Session, user_id: int, family_id: int):
    if not is_family_member(db, user_id, family_id):
        return None
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return None
    user.current_active_family_id = family_id
    db.commit()
    db.refresh(user)
    return _attach_derived(db, user, family_id)

def join_family_by_invite(db: Session, user, invite_code: str):
    family = get_family_by_invite(db, invite_code)
    if not family:
        return None
    if not is_family_member(db, user.id, family.id):
        add_membership(db, user.id, family.id, "member")
    user.current_active_family_id = family.id
    db.commit()
    db.refresh(user)
    return family


def get_users(db: Session, family_id: int):
    users = (db.query(models.User)
             .join(models.FamilyMember, models.User.id == models.FamilyMember.user_id)
             .filter(models.FamilyMember.family_id == family_id)
             .order_by(models.User.id).all())
    return [_attach_derived(db, u, family_id) for u in users]

def get_user_by_tg_id(db: Session, tg_id: int):
    u = db.query(models.User).filter(models.User.tg_id == tg_id).first()
    if u:
        _attach_derived(db, u)
    return u

def get_user_by_id(db: Session, user_id: int):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if u:
        _attach_derived(db, u)
    return u

def create_user_in_family(db: Session, family_id: int, name: str, tg_id: int = None, mono_token: str = None,
                          role: str = None):
    is_first = db.query(models.FamilyMember).filter(models.FamilyMember.family_id == family_id).count() == 0
    if role is None:
        role = "admin" if is_first else "member"
    user = models.User(name=name, tg_id=tg_id, mono_token=mono_token, current_active_family_id=family_id)
    db.add(user)
    db.flush()
    db.add(models.FamilyMember(user_id=user.id, family_id=family_id, role=role))
    db.commit()
    db.refresh(user)
    return _attach_derived(db, user, family_id)

def update_user_token(db: Session, tg_id: int, new_token: str):
    user = db.query(models.User).filter(models.User.tg_id == tg_id).first()
    if user:
        user.mono_token = new_token
        db.commit()
        db.refresh(user)
        _attach_derived(db, user)
    return user

def get_all_mono_tokens(db: Session):
    return db.query(models.User).filter(models.User.mono_token != None).all()

def remove_user(db: Session, family_id: int, user_id: int):
    mem = (db.query(models.FamilyMember)
           .filter(models.FamilyMember.user_id == user_id,
                   models.FamilyMember.family_id == family_id).first())
    if not mem:
        return None
    db.delete(mem)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user and user.current_active_family_id == family_id:
        remaining = db.query(models.FamilyMember.family_id).filter(
            models.FamilyMember.user_id == user_id).all()
        user.current_active_family_id = remaining[0][0] if remaining else None
    if user and db.query(models.FamilyMember).filter(models.FamilyMember.user_id == user_id).count() == 0:
        db.delete(user)
        db.commit()
        return user
    db.commit()
    if user:
        _attach_derived(db, user)
    return user


def get_categories(db: Session, family_id: int): return db.query(models.Category).filter(models.Category.family_id == family_id).order_by(models.Category.id).all()

def create_category(db: Session, family_id: int, icon: str, name: str, color: str, type: str):
    obj = models.Category(family_id=family_id, icon=icon, name=name, color=color, type=type)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_transactions(db: Session, family_id: int, skip: int = 0, limit: int = 100): return db.query(models.Transaction).filter(models.Transaction.family_id == family_id).order_by(models.Transaction.date.desc(), models.Transaction.id.desc()).offset(skip).limit(limit).all()

def get_transaction_by_id(db: Session, tx_id: int): return db.query(models.Transaction).filter(models.Transaction.id == tx_id).first()

def get_tx_by_mono(db: Session, mono_id: str): return db.query(models.Transaction).filter(models.Transaction.mono_id == mono_id).first()

def create_transaction(db: Session, family_id: int, user_id: int, category_id: int, amount: float, type: str, title: str, note: str, account: str, date, mono_id=None,
                       currency: str = DEFAULT_CURRENCY, jar_id: int = None):
    if mono_id:
        existing = db.query(models.Transaction).filter(models.Transaction.mono_id == mono_id).first()
        if existing: return existing
    obj = models.Transaction(family_id=family_id, user_id=user_id, category_id=category_id, amount=amount,
                             type=type, title=title, note=note, account=account, mono_id=mono_id,
                             date=date, currency=currency or DEFAULT_CURRENCY, jar_id=jar_id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

_PENDING_TITLE_PATTERNS = [
    ("❓ ", ""),  # префікс вебхука
    (" (нерозібрано)", ""),  # seed
    (" (не розібрано)", ""),
]


def _clean_pending_title(title: str) -> str:
    """Прибирає з назви маркери 'Очікує' (❓ / нерозібрано) після категоризації."""
    t = title or ""
    for old, new in _PENDING_TITLE_PATTERNS:
        t = t.replace(old, new)
    return t.strip()


def _coerce_date(value):
    """'YYYY-MM-DD' → date. TransactionUpdate.date приходить як str (див. schemas)."""
    if value is None or isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    return value


# Ключі, які НІКОЛИ не можна змінювати через оновлення транзакції:
# user_id/family_id — атрибуція та сімейна ізоляція. Навіть якщо їх спробують
# передати в payload, вони ігноруються.
_IMMUTABLE_TX_FIELDS = {"user_id", "family_id", "mono_id"}


def update_transaction(db: Session, tx_id: int, payload: dict):
    tx = db.query(models.Transaction).filter(models.Transaction.id == tx_id).first()
    if tx:
        # Категоризація pending → очищаємо назву від маркерів нерозібраності
        payload = dict(payload)
        for f in _IMMUTABLE_TX_FIELDS:
            payload.pop(f, None)
        if payload.get("category_id") is not None:
            if payload.get("title") is None:
                payload["title"] = _clean_pending_title(tx.title)
        if "date" in payload:
            payload["date"] = _coerce_date(payload["date"])
        for key, value in payload.items(): setattr(tx, key, value)
        db.commit()
        db.refresh(tx)
    return tx

def update_tx_by_mono(db: Session, mono_id: str, payload: dict):
    tx = get_tx_by_mono(db, mono_id)
    if not tx:
        return None
    payload = dict(payload)
    for f in _IMMUTABLE_TX_FIELDS:
        payload.pop(f, None)
    if payload.get("category_id") is not None:
        if payload.get("title") is None:
            payload["title"] = _clean_pending_title(tx.title)
    if "date" in payload:
        payload["date"] = _coerce_date(payload["date"])
    for key, value in payload.items():
        setattr(tx, key, value)
    db.commit()
    db.refresh(tx)
    return tx


def delete_transaction(db: Session, tx_id: int):
    tx = db.query(models.Transaction).filter(models.Transaction.id == tx_id).first()
    if tx:
        db.delete(tx)
        db.commit()
    return tx


def _is_jar_tx(t) -> bool:
    """Транзакція скарбнички (jar_id задано) — внутрішній рух, не дохід/витрата."""
    return getattr(t, "jar_id", None) is not None


def _add_to_currency_bucket(bucket: dict, currency: str, income: float = 0.0, expense: float = 0.0):
    cur = bucket.setdefault(currency, {"income": 0.0, "expense": 0.0})
    cur["income"] = round(cur["income"] + income, 2)
    cur["expense"] = round(cur["expense"] + expense, 2)
    return cur


def get_family_stats(db: Session, family_id: int):
    now = datetime.now()
    txs = db.query(models.Transaction).filter(
        models.Transaction.family_id == family_id,
        extract('year', models.Transaction.date) == now.year,
        extract('month', models.Transaction.date) == now.month
    ).all()
    # Місячні дохід/витрати — окремо по кожній валюті. Скарбнички та перекази виключені.
    by_currency = {}
    cats = {}  # top categories за UAH (зворотна сумісність)
    for t in txs:
        cur = t.currency or DEFAULT_CURRENCY
        if t.type == TYPE_INCOME or "Дохід" in t.type:
            if not _is_jar_tx(t):
                _add_to_currency_bucket(by_currency, cur, income=t.amount)
        elif t.type == TYPE_EXPENSE:
            if not _is_jar_tx(t):
                _add_to_currency_bucket(by_currency, cur, expense=t.amount)
                if cur == DEFAULT_CURRENCY:
                    cat_name = t.category.name if t.category else "Інше"
                    cats[cat_name] = cats.get(cat_name, 0) + t.amount
    # Зворотна сумісність: income/expense/balance — у UAH.
    uah = by_currency.get(DEFAULT_CURRENCY, {"income": 0.0, "expense": 0.0})
    income, expense = uah["income"], uah["expense"]
    top_cats = [{"name": k, "amount": v} for k, v in cats.items()]
    top_cats.sort(key=lambda x: x["amount"], reverse=True)
    return {"income": income, "expense": expense, "balance": round(income - expense, 2),
            "top_categories": top_cats, "pending_count": count_pending_transactions(db, family_id),
            "balances": {ACCOUNT_CASH: get_account_balance(db, family_id, ACCOUNT_CASH, DEFAULT_CURRENCY)},
            "cash_by_user": get_cash_balance_by_user(db, family_id),
            "by_currency": by_currency,
            "cash_by_currency": get_cash_balance_by_currency(db, family_id)}


def _cash_delta(t_type: str, amt: float, is_jar: bool) -> float:
    """Вплив транзакції на готівку.
    Звичайні: дохід +, витрата -, переказ зігнований.
    Jar-транзакції — це рух готівки ↔ скарбничка:
      депозит у скарбничку (Поповнення, jar_id) → готівка зменшується (-amt)
      зняття зі скарбнички (Витрати, jar_id)   → готівка збільшується (+amt)
    Jar-транзакції НЕ входять у місячні income/expense (див. get_family_stats)."""
    if is_jar:
        return -amt if t_type == TYPE_INCOME else (+amt if t_type == TYPE_EXPENSE else 0.0)
    if t_type == TYPE_INCOME:
        return amt
    if t_type == TYPE_EXPENSE:
        return -amt
    if t_type == TYPE_TRANSFER:
        return amt  # зігновані
    return 0.0


def get_cash_balance_by_user(db: Session, family_id: int) -> list:
    """Готівка, згрупована по користувачах І валютах:
    [{user_id, user_name, currency, balance}, ...].
    Jar-депозити зменшують готівку, jar-зняття — збільшують."""
    rows = (db.query(models.Transaction.user_id,
                     models.Transaction.type,
                     models.Transaction.amount,
                     models.Transaction.currency,
                     models.Transaction.jar_id)
            .filter(models.Transaction.family_id == family_id,
                    models.Transaction.account == ACCOUNT_CASH).all())
    by_key = {}  # (user_id, currency) -> balance
    for user_id, t_type, amt, cur, jar_id in rows:
        if user_id is None:
            continue
        key = (user_id, cur or DEFAULT_CURRENCY)
        by_key[key] = by_key.get(key, 0.0) + _cash_delta(t_type, amt, jar_id is not None)
    result = []
    for (user_id, cur), bal in by_key.items():
        user = db.query(models.User).filter(models.User.id == user_id).first()
        result.append({
            "user_id": user_id,
            "user_name": user.name if user else f"User {user_id}",
            "currency": cur,
            "balance": round(bal, 2),
        })
    result.sort(key=lambda r: (r["user_id"], r["currency"]))
    return result


def get_cash_balance_by_currency(db: Session, family_id: int) -> list:
    """Готівка по валютах (за всіма користувачами): [{"currency": "UAH", "balance": ..}, ...].
    Jar-депозити зменшують готівку, jar-зняття — збільшують."""
    rows = (db.query(models.Transaction.type,
                     models.Transaction.amount,
                     models.Transaction.currency,
                     models.Transaction.jar_id)
            .filter(models.Transaction.family_id == family_id,
                    models.Transaction.account == ACCOUNT_CASH).all())
    by_cur = {}
    for t_type, amt, cur, jar_id in rows:
        cur = cur or DEFAULT_CURRENCY
        by_cur[cur] = by_cur.get(cur, 0.0) + _cash_delta(t_type, amt, jar_id is not None)
    return [{"currency": cur, "balance": round(bal, 2)} for cur, bal in sorted(by_cur.items())]


def get_account_balance(db: Session, family_id: int, account: str,
                        currency: str = DEFAULT_CURRENCY) -> float:
    """Баланс джерела коштів (наприклад, готівки) за всіма транзакціями сім'ї
    в ОДНІЙ валюті. Jar-депозити зменшують готівку, jar-зняття — збільшують.
    Банківські рахунки так НЕ рахуємо — реальний баланс дає банківський API."""
    rows = (db.query(models.Transaction.type, models.Transaction.amount, models.Transaction.jar_id)
            .filter(models.Transaction.family_id == family_id,
                    models.Transaction.account == account,
                    models.Transaction.currency == currency).all())
    bal = 0.0
    for t_type, amt, jar_id in rows:
        bal += _cash_delta(t_type, amt, jar_id is not None)
    return round(bal, 2)


def create_transfer(db: Session, family_id: int, user_id: int, amount: float,
                    from_account: str, to_account: str, date=None, mono_id: str = None,
                    currency: str = DEFAULT_CURRENCY):
    """Переказ між джерелами коштів (наприклад, Monobank → Готівка при знятті).
    Зберігається як пара ЗІГНОВАНИХ транзакцій типу 'Переказ' (-from / +to),
    які НЕ впливають на доходи/витрати в статистиці. category_id = NULL."""
    date = date or datetime.now().date()
    currency = currency or DEFAULT_CURRENCY
    if mono_id:  # dedup для банківських вебхуків
        existing = db.query(models.Transaction).filter(models.Transaction.mono_id == mono_id).first()
        if existing:
            return None
    out_row = models.Transaction(family_id=family_id, user_id=user_id, category_id=None,
                                 amount=-amount, type=TYPE_TRANSFER,
                                 title=f"Переказ → {to_account}", account=from_account,
                                 mono_id=mono_id, date=date, currency=currency)
    in_row = models.Transaction(family_id=family_id, user_id=user_id, category_id=None,
                                amount=amount, type=TYPE_TRANSFER,
                                title=f"Переказ ← {from_account}", account=to_account,
                                mono_id=None, date=date, currency=currency)
    db.add(out_row)
    db.add(in_row)
    db.commit()
    db.refresh(out_row)
    db.refresh(in_row)
    return [out_row, in_row]


def _pending_query(db: Session, family_id: int):
    """Транзакції в службовій категорії 'Очікує' (Inbox Zero)."""
    return (db.query(models.Transaction)
            .join(models.Category, models.Transaction.category_id == models.Category.id)
            .filter(models.Transaction.family_id == family_id,
                    models.Category.name.like("%Очікує%")))


def get_pending_transactions(db: Session, family_id: int, limit: int = 100):
    return (_pending_query(db, family_id)
            .order_by(models.Transaction.date.desc(), models.Transaction.id.desc())
            .limit(limit).all())


def count_pending_transactions(db: Session, family_id: int) -> int:
    return _pending_query(db, family_id).count()


def get_notes(db: Session, family_id: int): return db.query(models.Note).filter(models.Note.family_id == family_id).order_by(models.Note.id.desc()).all()

def get_note_by_id(db: Session, note_id: int): return db.query(models.Note).filter(models.Note.id == note_id).first()

def create_note(db: Session, family_id: int, content: str):
    obj = models.Note(family_id=family_id, content=content)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
def update_note(db: Session, note_id: int, content: str):
    note = db.query(models.Note).filter(models.Note.id == note_id).first()
    if note:
        note.content = content
        db.commit()
        db.refresh(note)
    return note
def delete_note(db: Session, note_id: int):
    note = db.query(models.Note).filter(models.Note.id == note_id).first()
    if note:
        db.delete(note)
        db.commit()
    return note


def get_jar_balance(db: Session, jar_id: int, currency: str = None) -> float:
    """Динамічний баланс скарбнички: поповнення (+) мінус зняття (-) за транзакціями.
    Якщо currency задано — тільки в цій валюті, інакше за валютою скарбнички."""
    q = (db.query(models.Transaction.type, models.Transaction.amount, models.Transaction.currency)
         .filter(models.Transaction.jar_id == jar_id))
    rows = q.all()
    bal = 0.0
    for t_type, amt, cur in rows:
        if currency and cur != currency:
            continue
        if t_type == TYPE_INCOME:
            bal += amt
        elif t_type == TYPE_EXPENSE:
            bal -= amt
        # Перекази в скарбничці не очікуємо; ігноруємо
    return round(bal, 2)


def get_jars(db: Session, family_id: int):
    jars = db.query(models.Jar).filter(models.Jar.family_id == family_id).order_by(models.Jar.id).all()
    result = []
    for j in jars:
        j.balance = get_jar_balance(db, j.id)
        result.append(j)
    return result


def get_jar_by_id(db: Session, jar_id: int): return db.query(models.Jar).filter(models.Jar.id == jar_id).first()

def create_jar(db: Session, family_id: int, name: str, goal: float, currency: str = DEFAULT_CURRENCY):
    obj = models.Jar(family_id=family_id, name=name, balance=0.0, goal=goal,
                     currency=currency or DEFAULT_CURRENCY)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def topup_jar(db: Session, jar_id: int, amount: float, user_id: int = None,
              note: str = "", currency: str = None):
    """Поповнення скарбнички: створює транзакцію типу 'Поповнення' з jar_id.
    Баланс скарбнички обчислюється динамічно з цих транзакцій."""
    jar = db.query(models.Jar).filter(models.Jar.id == jar_id).first()
    if not jar:
        return None
    cur = currency or jar.currency or DEFAULT_CURRENCY
    tx = models.Transaction(family_id=jar.family_id, user_id=user_id, category_id=None,
                            amount=amount, type=TYPE_INCOME,
                            title=note or f"Поповнення: {jar.name}",
                            account=ACCOUNT_CASH, mono_id=None,
                            date=datetime.now().date(), currency=cur, jar_id=jar_id)
    db.add(tx)
    db.commit()
    db.refresh(tx)
    jar.balance = get_jar_balance(db, jar_id, cur)
    return jar


def withdraw_jar(db: Session, jar_id: int, amount: float, user_id: int = None,
                 note: str = "", currency: str = None):
    """Зняття зі скарбнички: створює транзакцію типу 'Витрати' з jar_id."""
    jar = db.query(models.Jar).filter(models.Jar.id == jar_id).first()
    if not jar:
        return None
    cur = currency or jar.currency or DEFAULT_CURRENCY
    tx = models.Transaction(family_id=jar.family_id, user_id=user_id, category_id=None,
                            amount=amount, type=TYPE_EXPENSE,
                            title=note or f"Зняття: {jar.name}",
                            account=ACCOUNT_CASH, mono_id=None,
                            date=datetime.now().date(), currency=cur, jar_id=jar_id)
    db.add(tx)
    db.commit()
    db.refresh(tx)
    jar.balance = get_jar_balance(db, jar_id, cur)
    return jar


# BANK ACCOUNTS (persistent Monobank/other bank account → user mapping)
def get_user_bank_accounts(db: Session, user_id: int):
    return db.query(models.BankAccount).filter(models.BankAccount.user_id == user_id).all()

def upsert_bank_account(db: Session, user_id: int, provider: str, external_account_id: str, name: str = None):
    existing = (db.query(models.BankAccount)
                .filter(models.BankAccount.user_id == user_id,
                        models.BankAccount.provider == provider,
                        models.BankAccount.external_account_id == external_account_id).first())
    if existing:
        if name:
            existing.name = name
        db.commit()
        return existing
    obj = models.BankAccount(user_id=user_id, provider=provider, external_account_id=external_account_id, name=name)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

def get_all_bank_accounts(db: Session):
    """Bot на старті: отримує всі банківські рахунки для наповнення карт."""
    return db.query(models.BankAccount).all()

def clear_user_bank_accounts(db: Session, user_id: int):
    db.query(models.BankAccount).filter(models.BankAccount.user_id == user_id).delete()
    db.commit()
