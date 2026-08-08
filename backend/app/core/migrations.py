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
