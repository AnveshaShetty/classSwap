"""add append-only hash chain to audit log

Revision ID: c1a8f4d2e760
Revises: ef31a6c45b20
Create Date: 2026-11-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.audit import audit_digest, GENESIS_HASH


revision: str = "c1a8f4d2e760"
down_revision: Union[str, None] = "ef31a6c45b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("audit_log", sa.Column("previous_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_log", sa.Column("entry_hash", sa.String(length=64), nullable=True))

    connection = op.get_bind()
    records = connection.execute(
        sa.text(
            "SELECT id, user_id, acting_as, action, target, created_at "
            "FROM audit_log ORDER BY id"
        )
    ).mappings()
    previous_hash = GENESIS_HASH
    for record in records:
        entry_hash = audit_digest(
            previous_hash,
            record["user_id"],
            record["acting_as"],
            record["action"],
            record["target"],
            record["created_at"],
        )
        connection.execute(
            sa.text(
                "UPDATE audit_log SET previous_hash = :previous_hash, entry_hash = :entry_hash "
                "WHERE id = :id"
            ),
            {
                "previous_hash": previous_hash,
                "entry_hash": entry_hash,
                "id": record["id"],
            },
        )
        previous_hash = entry_hash

    op.alter_column("audit_log", "previous_hash", nullable=False)
    op.alter_column("audit_log", "entry_hash", nullable=False)
    op.create_unique_constraint("uq_audit_log_entry_hash", "audit_log", ["entry_hash"])
    op.execute(
        """
        CREATE FUNCTION prevent_audit_log_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_append_only
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER audit_log_append_only ON audit_log")
    op.execute("DROP FUNCTION prevent_audit_log_mutation()")
    op.drop_constraint("uq_audit_log_entry_hash", "audit_log", type_="unique")
    op.drop_column("audit_log", "entry_hash")
    op.drop_column("audit_log", "previous_hash")
