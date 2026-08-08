import secrets
from datetime import datetime
from sqlalchemy import extract
from sqlalchemy.orm import Session
from app import models

# FAMILIES
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

# USERS & TOKENS
def get_users(db: Session, family_id: int):
    users = db.query(models.User).filter(models.User.family_id == family_id).order_by(models.User.id).all()
    for u in users: u.has_mono_token = bool(u.mono_token)
    return users

def get_user_by_tg_id(db: Session, tg_id: int):
    u = db.query(models.User).filter(models.User.tg_id == tg_id).first()
    if u: u.has_mono_token = bool(u.mono_token)
    return u

def create_user(db: Session, family_id: int, name: str, tg_id: int = None, mono_token: str = None, role: str = None):
    if role is None:
        is_first = db.query(models.User).filter(models.User.family_id == family_id).count() == 0
        role = "admin" if is_first else "member"
    obj = models.User(family_id=family_id, name=name, tg_id=tg_id, mono_token=mono_token, role=role)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    obj.has_mono_token = bool(obj.mono_token)
    return obj

def update_user_token(db: Session, tg_id: int, new_token: str):
    user = db.query(models.User).filter(models.User.tg_id == tg_id).first()
    if user:
        user.mono_token = new_token
        db.commit()
        db.refresh(user)
    return user

def get_all_mono_tokens(db: Session):
    return db.query(models.User).filter(models.User.mono_token != None).all()

def remove_user(db: Session, family_id: int, user_id: int):
    user = db.query(models.User).filter(models.User.id == user_id, models.User.family_id == family_id).first()
    if user:
        db.delete(user)
        db.commit()
    return user

# CATEGORIES
def get_categories(db: Session, family_id: int): return db.query(models.Category).filter(models.Category.family_id == family_id).order_by(models.Category.id).all()

def create_category(db: Session, family_id: int, icon: str, name: str, color: str, type: str):
    obj = models.Category(family_id=family_id, icon=icon, name=name, color=color, type=type)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

# TRANSACTIONS
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

def update_transaction(db: Session, tx_id: int, payload: dict):
    tx = db.query(models.Transaction).filter(models.Transaction.id == tx_id).first()
    if tx:
        for key, value in payload.items(): setattr(tx, key, value)
        db.commit()
        db.refresh(tx)
    return tx

def delete_transaction(db: Session, tx_id: int):
    tx = db.query(models.Transaction).filter(models.Transaction.id == tx_id).first()
    if tx:
        db.delete(tx)
        db.commit()
    return tx

# STATS
def get_family_stats(db: Session, family_id: int):
    now = datetime.now()
    txs = db.query(models.Transaction).filter(
        models.Transaction.family_id == family_id,
        extract('year', models.Transaction.date) == now.year,
        extract('month', models.Transaction.date) == now.month
    ).all()
    income = sum(t.amount for t in txs if t.type == "Поповнення" or "Дохід" in t.type)
    expense = sum(t.amount for t in txs if t.type == "Витрати")
    cats = {}
    for t in txs:
        if t.type == "Витрати":
            # БУЛО: cat_name = f"{t.category.icon} {t.category.name}"
            # СТАЛО: Просто беремо ім'я (в якому вже є емоджі після міграції)
            cat_name = t.category.name if t.category else "Інше"
            cats[cat_name] = cats.get(cat_name, 0) + t.amount
    top_cats = [{"name": k, "amount": v} for k, v in cats.items()]
    top_cats.sort(key=lambda x: x["amount"], reverse=True)
    return {"income": income, "expense": expense, "balance": income - expense, "top_categories": top_cats}

# NOTES (ЧЕРНЕТКА)
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

# JARS (СКАРБНИЧКИ)
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