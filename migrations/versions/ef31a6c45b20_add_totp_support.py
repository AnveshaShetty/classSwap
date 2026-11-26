"""add encrypted TOTP secrets and hashed backup codes

Revision ID: ef31a6c45b20
Revises: cd9e2f147a63
Create Date: 2026-11-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ef31a6c45b20"
down_revision: Union[str, None] = "cd9e2f147a63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret_encrypted", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("totp_pending_secret_encrypted", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("totp_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_table(
        "totp_backup_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "code_hash", name="uq_totp_backup_user_code"),
    )


def downgrade() -> None:
    op.drop_table("totp_backup_codes")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_pending_secret_encrypted")
    op.drop_column("users", "totp_secret_encrypted")
