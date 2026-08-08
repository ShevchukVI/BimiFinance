"""Multi-family M2M: family_members + current_active_family_id (drop users.family_id/role)

Revision ID: 0001
Revises:
Create Date: 2026-08-08

Перехід 1-to-many -> many-to-many:
- CREATE TABLE family_members (user_id, family_id, role) з композитним PK.
- ADD users.current_active_family_id.
- BACKFILL family_members зі старих users.family_id/role.
- SET current_active_family_id = family_id для існуючих.
- DROP users.family_id та users.role.

Гарди (IF EXISTS/IF NOT EXISTS + inspector) роблять міграцію безпечною
як для старої схеми, так і для свіжоствореної create_all.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _user_cols(bind):
    return [c["name"] for c in inspect(bind).get_columns("users")]


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Association table
    if not inspect(bind).has_table("family_members"):
        op.create_table(
            "family_members",
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
            sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), primary_key=True),
            sa.Column("role", sa.String(length=32), nullable=False, server_default="member"),
        )

    # 2. current_active_family_id
    if "current_active_family_id" not in _user_cols(bind):
        op.add_column("users", sa.Column("current_active_family_id", sa.Integer(),
                                         sa.ForeignKey("families.id"), nullable=True))

    # 3. Backfill + активна сім'я з legacy стовпців
    if "family_id" in _user_cols(bind):
        bind.execute(text("""
            INSERT INTO family_members (user_id, family_id, role)
            SELECT id, family_id, COALESCE(role, 'member')
            FROM users WHERE family_id IS NOT NULL
            ON CONFLICT (user_id, family_id) DO NOTHING
        """))
        bind.execute(text("""
            UPDATE users SET current_active_family_id = family_id
            WHERE current_active_family_id IS NULL AND family_id IS NOT NULL
        """))
        op.drop_column("users", "family_id")
    if "role" in _user_cols(bind):
        op.drop_column("users", "role")


def downgrade() -> None:
    bind = op.get_bind()

    if "family_id" not in _user_cols(bind):
        op.add_column("users", sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=True))
    if "role" not in _user_cols(bind):
        op.add_column("users", sa.Column("role", sa.String(length=32), nullable=False, server_default="member"))

    bind.execute(text("""
        UPDATE users u
        SET family_id = fm.family_id, role = fm.role
        FROM (
            SELECT DISTINCT ON (user_id) user_id, family_id, role
            FROM family_members ORDER BY user_id, family_id
        ) fm
        WHERE u.id = fm.user_id
    """))

    if "current_active_family_id" in _user_cols(bind):
        op.drop_column("users", "current_active_family_id")
    op.drop_table("family_members")
