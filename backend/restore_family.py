# restore_family.py — one-off data-fix
# Проблема: Alembic-міграція M2M створила family_members + users.current_active_family_id,
# але НЕ перенесла наявних користувачів. Засновники залишились "сиротами" без активної сім'ї.
#
# Фікс:
#   1. Гарантує існування Family(id=1, name="Main Family") (створює, якщо нема).
#   2. Для КОЖНОГО користувача users:
#      - current_active_family_id = 1
#      - upsert у family_members (user_id, family_id=1, role='admin')
#   3. Commit.
#
# Запуск (на сервері, у середовищі бекенду):
#   cd BimiFinance/backend && python restore_family.py
#
# Після УСПІШНОГО виконання на прод-БД скрипт можна видалити.
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv

# backend/.env лежить у батьківській директорії BimiFinance/.env
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402

FAMILY_ID = 1
FAMILY_NAME = "Main Family"
ROLE = "admin"


def main() -> int:
    db = SessionLocal()
    try:
        family = db.query(models.Family).filter(models.Family.id == FAMILY_ID).first()
        if not family:
            family = models.Family(id=FAMILY_ID, name=FAMILY_NAME, invite_code=secrets.token_urlsafe(8))
            db.add(family)
            db.flush()
            print(f"[restore] Family #{FAMILY_ID} '{FAMILY_NAME}' створено (invite: {family.invite_code})")
        else:
            print(f"[restore] Family #{FAMILY_ID} '{family.name}' вже існує")

        users = db.query(models.User).all()
        restored = 0
        for user in users:
            user.current_active_family_id = FAMILY_ID
            member = (db.query(models.FamilyMember)
                      .filter(models.FamilyMember.user_id == user.id,
                              models.FamilyMember.family_id == FAMILY_ID).first())
            if member:
                member.role = ROLE
            else:
                db.add(models.FamilyMember(user_id=user.id, family_id=FAMILY_ID, role=ROLE))
            restored += 1

        db.commit()
        print(f"[restore] [OK] Готово: {restored} user(s) відновлено до Family #{FAMILY_ID} ({FAMILY_NAME})")
        return 0
    except Exception as e:
        db.rollback()
        print(f"[restore] [ERROR] {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
