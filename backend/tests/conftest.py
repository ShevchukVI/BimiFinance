# DEV-only тести: sqlite in-memory, TestClient без lifespan (миграції не запускаються).
import os

# ENV має бути встановлено ДО імпорту app.* (settings fail-fast)
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("FERNET_KEY", "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=")
os.environ.setdefault("BOT_API_KEY", "test-bot-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base, get_db
from app.main import app

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)  # БЕЗ context manager — lifespan/міграції не запускаються

# Ключ беремо з фактичного env контейнера (compose env_file має пріоритет над setdefault)
BOT_HEADERS = {"X-API-Key": os.environ["BOT_API_KEY"]}


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seeded(db):
    """Сім'я + 2 користувачі + базові категорії."""
    fam = models.Family(name="Test Fam", invite_code="inv123")
    db.add(fam)
    db.flush()
    u1 = models.User(name="Admin", tg_id=111, current_active_family_id=fam.id)
    u2 = models.User(name="Member", tg_id=222, current_active_family_id=fam.id)
    db.add_all([u1, u2])
    db.flush()
    db.add(models.FamilyMember(user_id=u1.id, family_id=fam.id, role="admin"))
    db.add(models.FamilyMember(user_id=u2.id, family_id=fam.id, role="member"))
    cats = {}
    for name, ctype in [("Продукти", "expense"), ("Кафе", "expense"), ("Зарплата", "income"),
                        ("Очікує", "expense"), ("Інше", "expense")]:
        c = models.Category(family_id=fam.id, icon="•", name=name, color="#000", type=ctype)
        db.add(c)
        db.flush()
        cats[name] = c
    db.commit()
    return {"family": fam, "admin": u1, "member": u2, "cats": cats}


def make_tx(db, family_id, user_id, category_id, amount, t_type, title="t",
            account="Готівка", date="2026-08-05", mono_id=None):
    from datetime import datetime as _dt
    if isinstance(date, str):
        date = _dt.strptime(date, "%Y-%m-%d").date()
    tx = models.Transaction(family_id=family_id, user_id=user_id, category_id=category_id,
                            amount=amount, type=t_type, title=title, account=account,
                            date=date, mono_id=mono_id)
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx
