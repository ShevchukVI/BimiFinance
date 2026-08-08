"""Idempotent lightweight migrations (create_all + backfills for existing DBs)."""
from sqlalchemy import text

import app.models  # noqa: F401  (register models on Base before create_all)
from app.database import Base, engine


def run_migrations():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'member'"
        ))
