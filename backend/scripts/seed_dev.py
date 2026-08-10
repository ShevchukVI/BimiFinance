# scripts/seed_dev.py
# DEV-ONLY seed сценарій. БЕЗПЕКА: запускається лише на БД, чиє ім'я закінчується на '_dev'.
#
# Мета:
#  - дати реальному DEV-користувачу (за замовчуванням tg_id=527405868) повноцінну сім'ю
#    "Dev Family" з повним набором категорій і ~35 реалістичними транзакціями:
#    cash income/expense, bank (Monobank), pending ('Очікує'), transfers, минулий місяць;
#  - додати тестових учасників (111111 admin / 222222 member);
#  - скарбнички, нотатку.
# Ідемпотентний: повторний запуск чистить транзакції/скарбнички/нотатки сім'ї і пересоздає.
#
# Налаштування: DEV_SEED_TG_ID (env, default 527405868).
# Запуск (в dev-контейнері):  python -m scripts.seed_dev
import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models
from app.database import SessionLocal
from app import crud

# Категорії (icon, name, type) — повний набір, як у боті/онбордингу + доходи.
CATS = [
    ("🛒", "Продукти", "expense"), ("☕", "Кафе", "expense"),
    ("🚕", "Транспорт", "expense"), ("🏠", "Дім", "expense"),
    ("💊", "Здоров'я", "expense"), ("🎉", "Розваги", "expense"),
    ("👕", "Одяг", "expense"), ("📱", "Зв'язок", "expense"),
    ("🎓", "Освіта", "expense"), ("🐾", "Тварини", "expense"),
    ("🗂️", "Інше", "expense"),
    ("💼", "Робота", "income"), ("💶", "Фріланс", "income"),
    ("🎁", "Подарунки", "income"), ("📈", "Інвестиції", "income"),
    ("🔄", "Переказ", "expense"), ("❓", "Очікує", "expense"),
]

# (category, title, amount, account, days_ago)
# account: "Готівка" або "Монобанк"
TXS = [
    # --- Доходи (готівка) ---
    ("Робота", "Зарплата за місяць", 25000, "Готівка", 12),
    ("Робота", "Премія за проєкт", 5000, "Монобанк", 8),
    ("Фріланс", "Дизайн макетів", 4000, "Готівка", 5),
    ("Фріланс", "Консультація", 1200, "Монобанк", 2),
    ("Подарунки", "Гроші на день народження", 1500, "Готівка", 6),
    ("Інвестиції", "Дивіденди", 800, "Монобанк", 9),
    # --- Витрати готівкою (поточний місяць) ---
    ("Кафе", "Кава в коворкінгу", 120, "Готівка", 0),
    ("Продукти", "Продукти на тиждень", 1560, "Готівка", 1),
    ("Транспорт", "Метро + таксі", 340, "Готівка", 2),
    ("Дім", "Комуналка за місяць", 1800, "Готівка", 3),
    ("Здоров'я", "Аптека", 750, "Готівка", 4),
    ("Розваги", "Кіно з друзями", 420, "Готівка", 5),
    ("Одяг", "Футболка", 600, "Готівка", 7),
    ("Зв'язок", "Мобільний тариф", 200, "Готівка", 10),
    ("Освіта", "Курс англійської", 1500, "Готівка", 11),
    ("Тварини", "Корм для кота", 550, "Готівка", 13),
    ("Інше", "Дрібні витрати", 280, "Готівка", 14),
    # --- Витрати карткою (Monobank, вже з категорією) ---
    ("Продукти", "Фора", 280, "Монобанк", 1),
    ("Кафе", "Кава Аптека 200", 95, "Монобанк", 2),
    ("Транспорт", "Uklon", 210, "Монобанк", 4),
    ("Дім", "Інтернет", 300, "Монобанк", 6),
    ("Продукти", "Сільпо", 890, "Монобанк", 8),
    ("Розваги", "Стримінги", 250, "Монобанк", 9),
    # --- Pending 'Очікує' (Inbox Zero) ---
    ("Очікує", "❓ Сільпо (нерозібрано)", 420, "Монобанк", 0),
    ("Очікує", "❓ Новус (нерозібрано)", 89, "Монобанк", 1),
    # --- Минулий місяць (для порівняння/аналітики) ---
    ("Робота", "Зарплата", 24000, "Готівка", 35),
    ("Робота", "Зарплата", 24000, "Готівка", 65),
    ("Фріланс", "Лендінг", 6000, "Монобанк", 33),
    ("Продукти", "Продукти", 2100, "Готівка", 34),
    ("Кафе", "Кафе та ресторани", 900, "Готівка", 33),
    ("Транспорт", "Пальне", 1500, "Монобанк", 31),
    ("Дім", "Комуналка", 1750, "Готівка", 32),
    ("Одяг", "Кросівки", 2200, "Монобанк", 30),
    ("Розваги", "Подорож", 4500, "Готівка", 28),
    ("Продукти", "Сільпо", 640, "Монобанк", 40),
]

# Скарбнички та нотатки
JARS = [("Відпустка", 7500, 30000), ("Запас на чорний день", 12000, 50000)]
NOTES = "М'ясо 500 грн\nПиво 350.50 ₴\nОвочі 120 грн\nТаксі 180 грн"


def _dev_only(db) -> None:
    db_name = db.bind.url.database or ""
    if not db_name.endswith("_dev"):
        raise SystemExit(f"REFUSED: DEV-only seed, але DB='{db_name}'. Aborting.")


def main():
    db = SessionLocal()
    try:
        _dev_only(db)

        real_tg_id = int(os.getenv("DEV_SEED_TG_ID", "527405868"))
        family = db.query(models.Family).filter(models.Family.name == "Dev Family").first()
        if not family:
            family = models.Family(name="Dev Family", invite_code="devfamily123")
            db.add(family)
            db.commit()
            db.refresh(family)
        print(f"Family: {family.name} (id={family.id}, invite={family.invite_code})")

        # Ідемпотентність: чистимо дані сім'ї
        db.query(models.Transaction).filter(models.Transaction.family_id == family.id).delete()
        db.query(models.Jar).filter(models.Jar.family_id == family.id).delete()
        db.query(models.Note).filter(models.Note.family_id == family.id).delete()
        db.commit()

        # --- Користувачі ---
        def ensure_user(name, tg_id, role):
            u = db.query(models.User).filter(models.User.tg_id == tg_id).first()
            if not u:
                u = models.User(name=name, tg_id=tg_id)
                db.add(u)
                db.flush()
            mem = db.query(models.FamilyMember).filter(
                models.FamilyMember.user_id == u.id,
                models.FamilyMember.family_id == family.id).first()
            if not mem:
                db.add(models.FamilyMember(user_id=u.id, family_id=family.id, role=role))
            else:
                mem.role = role
            u.current_active_family_id = family.id
            db.commit()
            return u

        real = ensure_user("Тест-Користувач", real_tg_id, "admin")
        ensure_user("Тест-Учасник", 222222, "member")
        print(f"Users: real={real.name}(tg={real_tg_id}, admin), TestMember=222222")

        # --- Категорії (upsert) ---
        cats = {}
        for icon, name, ctype in CATS:
            c = db.query(models.Category).filter(
                models.Category.family_id == family.id,
                models.Category.name == name).first()
            if not c:
                c = models.Category(family_id=family.id, icon=icon, name=name,
                                    color="#7f8c8d", type=ctype)
                db.add(c)
                db.flush()
            cats[name] = c
        db.commit()
        print(f"Categories: {len(cats)}")

        # --- Транзакції ---
        today = date.today()
        mono_seq = 1

        def add(amount, ctype, title, category, account, days_ago, mono_id=None, user=real):
            tx = models.Transaction(
                family_id=family.id, user_id=user.id,
                category_id=cats[category].id, amount=amount, type=ctype,
                title=title, account=account,
                date=today - timedelta(days=days_ago), mono_id=mono_id)
            db.add(tx)
            db.commit()

        for cat, title, amount, account, days in TXS:
            if cat == "Очікує":
                ctype, ttype = "expense", "Витрати"
            elif cat in ("Робота", "Фріланс", "Подарунки", "Інвестиції"):
                ctype, ttype = "income", "Поповнення"
            else:
                ctype, ttype = "expense", "Витрати"
            mono_id = None
            if account == "Монобанк" and cat != "Очікує":
                mono_id = f"seed-mono-{mono_seq}"; mono_seq += 1
            add(amount, ttype, title, cat, account, days, mono_id=mono_id)

        # Перекази Cash ↔ Bank (не дохід/витрата)
        crud.create_transfer(db, family.id, real.id, 3000, "Монобанк", "Готівка",
                             date=today - timedelta(days=6), mono_id="seed-transfer-1")
        crud.create_transfer(db, family.id, real.id, 1000, "Готівка", "Монобанк",
                             date=today - timedelta(days=15))
        print(f"Transactions: {len(TXS)} + 2 transfers")

        # --- Скарбнички + нотатка ---
        for name, balance, goal in JARS:
            db.add(models.Jar(family_id=family.id, name=name, balance=balance, goal=goal))
        db.add(models.Note(family_id=family.id, content=NOTES))
        db.commit()
        print("Jars/Notes: 2 jars, 1 note")

        print("\n✅ DEV seed complete.")
        print(f"  Реальний користувач tg_id={real_tg_id} -> активна сім'я 'Dev Family' (admin)")
        print(f"  Cash balance: {crud.get_account_balance(db, family.id, 'Готівка')} ₴")
        print(f"  Pending: {crud.count_pending_transactions(db, family.id)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
