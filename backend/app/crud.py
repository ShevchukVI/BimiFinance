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

def create_transaction(db: Session, family_id: int, user_id: int, category_id: int, amount: float, type: str, title: str, note: str, account: str, date, mono_id=None):
    if mono_id:
        existing = db.query(models.Transaction).filter(models.Transaction.mono_id == mono_id).first()
        if existing: return existing
    obj = models.Transaction(family_id=family_id, user_id=user_id, category_id=category_id, amount=amount, type=type, title=title, note=note, account=account, mono_id=mono_id, date=date)
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


def update_transaction(db: Session, tx_id: int, payload: dict):
    tx = db.query(models.Transaction).filter(models.Transaction.id == tx_id).first()
    if tx:
        # Категоризація pending → очищаємо назву від маркерів нерозібраності
        if payload.get("category_id") is not None:
            payload = dict(payload)
            if payload.get("title") is None:
                payload["title"] = _clean_pending_title(tx.title)
        payload = dict(payload)
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
    if payload.get("category_id") is not None:
        payload = dict(payload)
        if payload.get("title") is None:
            payload["title"] = _clean_pending_title(tx.title)
    payload = dict(payload)
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


def get_family_stats(db: Session, family_id: int):
    now = datetime.now()
    txs = db.query(models.Transaction).filter(
        models.Transaction.family_id == family_id,
        extract('year', models.Transaction.date) == now.year,
        extract('month', models.Transaction.date) == now.month
    ).all()
    income = sum(t.amount for t in txs if t.type == TYPE_INCOME or "Дохід" in t.type)
    expense = sum(t.amount for t in txs if t.type == TYPE_EXPENSE)
    cats = {}
    for t in txs:
        if t.type == TYPE_EXPENSE:
            cat_name = t.category.name if t.category else "Інше"
            cats[cat_name] = cats.get(cat_name, 0) + t.amount
    top_cats = [{"name": k, "amount": v} for k, v in cats.items()]
    top_cats.sort(key=lambda x: x["amount"], reverse=True)
    return {"income": income, "expense": expense, "balance": income - expense,
            "top_categories": top_cats, "pending_count": count_pending_transactions(db, family_id),
            "balances": {ACCOUNT_CASH: get_account_balance(db, family_id, ACCOUNT_CASH)}}


def get_account_balance(db: Session, family_id: int, account: str) -> float:
    """Баланс джерела коштів (наприклад, готівки) за всіма транзакціями сім'ї.
    Поповнення: +сума; Витрати: -сума; Переказ: зігнована сума (-from / +to).
    Банківські рахунки так НЕ рахуємо — реальний баланс дає банківський API."""
    rows = (db.query(models.Transaction.type, models.Transaction.amount)
            .filter(models.Transaction.family_id == family_id,
                    models.Transaction.account == account).all())
    bal = 0.0
    for t_type, amt in rows:
        if t_type == TYPE_INCOME:
            bal += amt
        elif t_type == TYPE_EXPENSE:
            bal -= amt
        elif t_type == TYPE_TRANSFER:
            bal += amt  # перекази зберігаються зі знаком
    return round(bal, 2)


def create_transfer(db: Session, family_id: int, user_id: int, amount: float,
                    from_account: str, to_account: str, date=None, mono_id: str = None):
    """Переказ між джерелами коштів (наприклад, Monobank → Готівка при знятті).
    Зберігається як пара ЗІГНОВАНИХ транзакцій типу 'Переказ' (-from / +to),
    які НЕ впливають на доходи/витрати в статистиці. category_id = NULL."""
    date = date or datetime.now().date()
    if mono_id:  # dedup для банківських вебхуків
        existing = db.query(models.Transaction).filter(models.Transaction.mono_id == mono_id).first()
        if existing:
            return None
    out_row = models.Transaction(family_id=family_id, user_id=user_id, category_id=None,
                                 amount=-amount, type=TYPE_TRANSFER,
                                 title=f"Переказ → {to_account}", account=from_account,
                                 mono_id=mono_id, date=date)
    in_row = models.Transaction(family_id=family_id, user_id=user_id, category_id=None,
                                amount=amount, type=TYPE_TRANSFER,
                                title=f"Переказ ← {from_account}", account=to_account,
                                mono_id=None, date=date)
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


def get_jars(db: Session, family_id: int): return db.query(models.Jar).filter(models.Jar.family_id == family_id).order_by(models.Jar.id).all()

def get_jar_by_id(db: Session, jar_id: int): return db.query(models.Jar).filter(models.Jar.id == jar_id).first()

def create_jar(db: Session, family_id: int, name: str, goal: float):
    obj = models.Jar(family_id=family_id, name=name, balance=0.0, goal=goal)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

def topup_jar(db: Session, jar_id: int, amount: float):
    jar = db.query(models.Jar).filter(models.Jar.id == jar_id).first()
    if jar:
        jar.balance += amount
        db.commit()
        db.refresh(jar)
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
