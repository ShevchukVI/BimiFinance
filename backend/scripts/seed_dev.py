# scripts/seed_dev.py
# DEV-ONLY seed сценарій. БЕЗПЕКА: запускається лише на БД, чиє ім'я закінчується на '_dev'.
# Створює зрозумілий набір тестових даних: сім'я, учасники, категорії, транзакції
# (готівка + Monobank + перекази + pending 'Очікує'), скарбничка, нотатка.
# Ідемпотентний: при повторному запуску чистить транзакції сім'ї та пересоздає.
#
# Запуск (в dev-контейнері):  python -m scripts.seed_dev
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models
from app.database import SessionLocal
from app import crud
from app.core import security


def main():
    db = SessionLocal()
    try:
        db_name = db.bind.url.database or ""
        if not db_name.endswith("_dev"):
            raise SystemExit(
                f"REFUSED: this is a DEV-only seed, but DB is '{db_name}'. Aborting.")

        # --- Сім'я ---
        family = db.query(models.Family).filter(models.Family.name == "Dev Family").first()
        if not family:
            family = models.Family(name="Dev Family", invite_code="devfamily123")
            db.add(family)
            db.commit()
            db.refresh(family)
        print(f"Family: {family.name} (id={family.id}, invite={family.invite_code})")

        # Очищення транзакцій сім'ї для ідемпотентності
        db.query(models.Transaction).filter(models.Transaction.family_id == family.id).delete()
        db.query(models.Jar).filter(models.Jar.family_id == family.id).delete()
        db.query(models.Note).filter(models.Note.family_id == family.id).delete()
        db.commit()

        # --- Користувачі ---
        def ensure_user(name, tg_id, role):
            u = db.query(models.User).filter(models.User.tg_id == tg_id).first()
            if not u:
                u = models.User(name=name, tg_id=tg_id, current_active_family_id=family.id)
                db.add(u)
                db.flush()
            if not crud.is_family_member(db, u.id, family.id):
                db.add(models.FamilyMember(user_id=u.id, family_id=family.id, role=role))
            else:
                mem = db.query(models.FamilyMember).filter(
                    models.FamilyMember.user_id == u.id,
                    models.FamilyMember.family_id == family.id).first()
                mem.role = role
            u.current_active_family_id = family.id
            db.commit()
            return u

        admin = ensure_user("Тест-Адмін", 111111, "admin")
        member = ensure_user("Тест-Учасник", 222222, "member")
        print(f"Users: {admin.name} (admin), {member.name} (member)")

        # --- Категорії ---
        CATS = [
            ("🛒", "Продукти", "expense"), ("☕", "Кафе", "expense"),
            ("🚕", "Транспорт", "expense"), ("🏠", "Дім", "expense"),
            ("💊", "Здоров'я", "expense"), ("🎉", "Розваги", "expense"),
            ("👕", "Одяг", "expense"), ("📱", "Зв'язок", "expense"),
            ("💼", "Робота", "income"), ("💶", "Фріланс", "income"),
            ("🗂️", "Інше", "expense"), ("🔄", "Переказ", "expense"),
            ("❓", "Очікує", "expense"),
        ]
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

        today = date.today()
        month_ago = today - timedelta(days=30)

        def add(amount, ctype, title, category, account="Готівка", days_ago=0, mono_id=None):
            tx = models.Transaction(
                family_id=family.id, user_id=admin.id,
                category_id=cats[category].id,
                amount=amount, type=ctype, title=title, account=account,
                date=today - timedelta(days=days_ago), mono_id=mono_id)
            db.add(tx)
            db.commit()
            return tx

        # --- Готівка: доходи + витрати (поточний місяць) ---
        add(25000, "Поповнення", "Зарплата за місяць", "Робота", days_ago=12)
        add(4000, "Поповнення", "Фріланс-проєкт", "Фріланс", days_ago=5)
        add(120, "Витрати", "Кава в коворкінгу", "Кафе", days_ago=0)
        add(1560, "Витрати", "Продукти на тиждень", "Продукти", days_ago=1)
        add(340, "Витрати", "Транспорт (метро+таксі)", "Транспорт", days_ago=2)
        add(1800, "Витрати", "Комуналка за місяць", "Дім", days_ago=3)
        add(750, "Витрати", "Аптека", "Здоров'я", days_ago=4)

        # --- Monobank (синхронізовані, вже з категорією) ---
        add(280, "Витрати", "Фора", "Продукти", account="Монобанк", days_ago=1, mono_id="seed-mono-1")
        add(95, "Витрати", "Кава Аптека 200", "Кафе", account="Монобанк", days_ago=2, mono_id="seed-mono-2")

        # --- Pending 'Очікує' (Inbox Zero) ---
        add(420, "Витрати", "❓ Сільпо (нерозібрано)", "Очікує", account="Монобанк", days_ago=0,
            mono_id="seed-pending-1")
        add(89, "Витрати", "❓ Новус (нерозібрано)", "Очікує", account="Монобанк", days_ago=1,
            mono_id="seed-pending-2")

        # --- Переказ Monobank → Готівка (зняття) ---
        crud.create_transfer(db, family.id, admin.id, 3000, "Монобанк", "Готівка",
                             date=today - timedelta(days=6), mono_id="seed-transfer-1")

        # --- Минулий місяць (для порівняння) ---
        add(24000, "Поповнення", "Зарплата", "Робота", days_ago=35)
        add(2100, "Витрати", "Продукти", "Продукти", days_ago=34)
        add(900, "Витрати", "Кафе та ресторани", "Кафе", days_ago=33)

        # --- Скарбничка та нотатка ---
        db.add(models.Jar(family_id=family.id, name="Відпустка", balance=7500, goal=30000))
        db.add(models.Note(family_id=family.id,
                           content="М'ясо 500 грн\nПиво 350.50 ₴\nОвочі 120 грн"))
        db.commit()
        print("Jars/Notes: 1 jar, 1 note")

        print("\n✅ DEV seed complete.")
        print("  Test user: tg_id=111111 (admin), 222222 (member)")
        print("  Pending: 2 transactions in 'Очікує' — тестуй Inbox Zero")
        print("  Cash balance включає зарплати/витрати/переказ")
    finally:
        db.close()


if __name__ == "__main__":
    main()
