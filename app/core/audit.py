import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, User


GENESIS_HASH = "0" * 64
AUDIT_LOCK_ID = 0x43535750


class AuditChainError(ValueError):
    pass


@event.listens_for(Session, "before_flush")
def _prevent_audit_mutation(session: Session, flush_context: object, instances: object) -> None:
    if any(isinstance(entry, AuditLog) for entry in session.deleted):
        raise ValueError("Audit log entries are append-only.")
    if any(
        isinstance(entry, AuditLog) and session.is_modified(entry, include_collections=True)
        for entry in session.dirty
    ):
        raise ValueError("Audit log entries are append-only.")


def _timestamp(value: datetime) -> str:
    normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return normalized.isoformat(timespec="microseconds")


def audit_digest(
    previous_hash: str,
    user_id: int,
    acting_as: str,
    action: str,
    target: str,
    created_at: datetime,
) -> str:
    payload = json.dumps(
        {
            "action": action,
            "acting_as": acting_as,
            "created_at": _timestamp(created_at),
            "previous_hash": previous_hash,
            "target": target,
            "user_id": user_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def append_audit(
    session: Session,
    actor: User,
    action: str,
    target: str,
    *,
    acting_as: str | None = None,
) -> AuditLog:
    session.flush()
    if session.get_bind().dialect.name == "postgresql":
        session.execute(select(func.pg_advisory_xact_lock(AUDIT_LOCK_ID)))
    previous_hash = session.scalar(
        select(AuditLog.entry_hash).order_by(AuditLog.id.desc()).limit(1).with_for_update()
    ) or GENESIS_HASH
    created_at = datetime.now(timezone.utc)
    role = acting_as or actor.role
    entry = AuditLog(
        user_id=actor.id,
        acting_as=role,
        action=action,
        target=target,
        created_at=created_at,
        previous_hash=previous_hash,
        entry_hash=audit_digest(previous_hash, actor.id, role, action, target, created_at),
    )
    session.add(entry)
    session.flush()
    return entry


def verify_audit_chain(session: Session) -> None:
    previous_hash = GENESIS_HASH
    entries = session.scalars(
        select(AuditLog).order_by(AuditLog.id).execution_options(stream_results=True)
    )
    for entry in entries:
        expected = audit_digest(
            previous_hash,
            entry.user_id,
            entry.acting_as,
            entry.action,
            entry.target,
            entry.created_at,
        )
        if entry.previous_hash != previous_hash or entry.entry_hash != expected:
            raise AuditChainError("Audit chain verification failed at entry %d." % entry.id)
        previous_hash = entry.entry_hash
