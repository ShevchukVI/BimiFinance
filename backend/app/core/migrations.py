"""Idempotent lightweight migrations (create_all + backfills for existing DBs).

Alembic is the formal migration tool (see migrations/ + alembic.ini).
This module is a zero-friction fallback that performs the same transition
idempotently on every startup.
"""
from sqlalchemy import inspect, text

import app.models  # noqa: F401
from app.database import Base, engine


def run_migrations():
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        user_cols = [c["name"] for c in inspect(conn).get_columns("users")]

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS family_members (
                user_id INTEGER NOT NULL REFERENCES users(id),
                family_id INTEGER NOT NULL REFERENCES families(id),
                role VARCHAR(32) NOT NULL DEFAULT 'member',
                PRIMARY KEY (user_id, family_id)
            )
        """))

        has_legacy = "family_id" in user_cols
        if has_legacy:
            conn.execute(text("""
                INSERT INTO family_members (user_id, family_id, role)
                SELECT id, family_id, COALESCE(role, 'member')
                FROM users WHERE family_id IS NOT NULL
                ON CONFLICT (user_id, family_id) DO NOTHING
            """))

        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS current_active_family_id INTEGER REFERENCES families(id)"
        ))
        if has_legacy:
            conn.execute(text("""
                UPDATE users SET current_active_family_id = family_id
                WHERE current_active_family_id IS NULL AND family_id IS NOT NULL
            """))
        conn.execute(text("""
            UPDATE users u SET current_active_family_id = fm.family_id
            FROM family_members fm
            WHERE u.current_active_family_id IS NULL AND fm.user_id = u.id
        """))

        if has_legacy:
            conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS family_id"))
        if "role" in user_cols:
            conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS role"))

        # --- Phase 2: Multi-currency + Deep Jars ---
        # 1) transactions.currency (default UAH)
        conn.execute(text(
            "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS currency VARCHAR(8) NOT NULL DEFAULT 'UAH'"
        ))
        # 2) transactions.jar_id (FK, nullable)
        conn.execute(text(
            "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS jar_id INTEGER REFERENCES jars(id)"
        ))
        # 3) jars.currency (default UAH)
        conn.execute(text(
            "ALTER TABLE jars ADD COLUMN IF NOT EXISTS currency VARCHAR(8) NOT NULL DEFAULT 'UAH'"
        ))

        # --- Housing («Житло»): нові таблиці створює create_all; тут — колонки
        # для вже існуючих utility_meters / utility_readings (V1 foundation).
        for stmt in (
            "ALTER TABLE utility_meters ADD COLUMN IF NOT EXISTS provider_id INTEGER REFERENCES utility_providers(id)",
            "ALTER TABLE utility_meters ADD COLUMN IF NOT EXISTS zone VARCHAR",
            "ALTER TABLE utility_meters ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE utility_meters ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0",
            "ALTER TABLE utility_readings ADD COLUMN IF NOT EXISTS source VARCHAR DEFAULT 'manual'",
            "ALTER TABLE utility_readings ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)",
            "CREATE INDEX IF NOT EXISTS ix_utility_readings_meter_id ON utility_readings (meter_id)",
            "ALTER TABLE utility_providers ADD COLUMN IF NOT EXISTS match_pattern VARCHAR DEFAULT ''",
            # Obligations (credits / installments / subscriptions): link a transaction to one
            "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS obligation_id INTEGER REFERENCES obligations(id) ON DELETE SET NULL",
            "CREATE INDEX IF NOT EXISTS ix_transactions_obligation_id ON transactions (obligation_id)",
            # Monobank jars ↔ Bimi goals
            "ALTER TABLE jars ADD COLUMN IF NOT EXISTS mono_jar_id VARCHAR",
            "ALTER TABLE jars ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)",
            "ALTER TABLE jars ADD COLUMN IF NOT EXISTS bank_balance DOUBLE PRECISION",
            "ALTER TABLE jars ADD COLUMN IF NOT EXISTS synced_at TIMESTAMP",
            "CREATE INDEX IF NOT EXISTS ix_jars_mono_jar_id ON jars (mono_jar_id)",
            # Personal bottom-bar tabs + car journal: station of a fill
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS tab_prefs VARCHAR",
            "ALTER TABLE vehicle_logs ADD COLUMN IF NOT EXISTS place VARCHAR",
            "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS driver_ids VARCHAR",
            "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS mcc INTEGER",
            "UPDATE vehicles SET driver_ids = CAST(user_id AS VARCHAR) WHERE driver_ids IS NULL AND user_id IS NOT NULL",
        ):
            conn.execute(text(stmt))

        # Backfill: переносимо історичний баланс скарбничок у синтетичні транзакції
        # поповнення (type='Поповнення', jar_id=<id>), щоб динамічний баланс
        # (SUM amount WHERE jar_id=...) збігався зі старим збереженим balance.
        # Ідемпотентно: додаємо лише якщо для скарбнички ще немає жодної jar-транзакції.
        jars = conn.execute(text(
            "SELECT j.id, j.family_id, j.balance, j.name FROM jars j"
        )).fetchall()
        for jar in jars:
            jar_id, fam_id, bal, name = jar
            if not bal:
                continue
            has_tx = conn.execute(text(
                "SELECT 1 FROM transactions WHERE jar_id = :jid LIMIT 1"
            ), {"jid": jar_id}).fetchone()
            if has_tx:
                continue
            owner = conn.execute(text(
                "SELECT user_id FROM family_members WHERE family_id = :fid ORDER BY user_id LIMIT 1"
            ), {"fid": fam_id}).fetchone()
            owner_id = owner[0] if owner else None
            conn.execute(text(
                "INSERT INTO transactions (family_id, user_id, category_id, amount, type, title, note, account, mono_id, date, currency, jar_id) "
                "VALUES (:fam, :uid, NULL, :amt, 'Поповнення', :title, '', 'Готівка', NULL, CURRENT_DATE, 'UAH', :jid)"
            ), {"fam": fam_id, "uid": owner_id, "amt": bal, "title": f"Початковий баланс: {name}", "jid": jar_id})
