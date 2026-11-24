"""add password-change state to users

Revision ID: ab41d63c9e72
Revises: 7eb7b019f570
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ab41d63c9e72"
down_revision: Union[str, None] = "7eb7b019f570"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=10), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("failures", sa.SmallInteger(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "key_hash", name="uq_login_attempt_scope_key"),
    )


def downgrade() -> None:
    op.drop_table("login_attempts")
    op.drop_column("users", "token_version")
    op.drop_column("users", "must_change_password")
