import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.audit import AuditChainError, append_audit, verify_audit_chain
from app.database import Base
from app.models import AuditLog, User
from app.services.admin import anonymize_user


@pytest.fixture
def audit_engine():
    test_engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


def _user(user_id: int, role: str, email: str) -> User:
    return User(
        id=user_id,
        name="Test User %d" % user_id,
        email=email,
        password_hash="not-a-real-password-hash",
        role=role,
        department="Science",
        teaches=True,
    )


def test_audit_entries_form_a_verifiable_hash_chain(audit_engine) -> None:
    with Session(audit_engine, expire_on_commit=False) as session:
        actor = _user(1, "super_admin", "admin@example.edu")
        session.add(actor)
        session.flush()
        append_audit(session, actor, "test.first", "user:1")
        append_audit(session, actor, "test.second", "user:2")
        session.commit()

        verify_audit_chain(session)

        session.execute(
            update(AuditLog).where(AuditLog.action == "test.first").values(target="tampered")
        )
        session.commit()
        with pytest.raises(AuditChainError, match="entry 1"):
            verify_audit_chain(session)


def test_audit_entries_cannot_be_updated_or_deleted_through_orm(audit_engine) -> None:
    with Session(audit_engine, expire_on_commit=False) as session:
        actor = _user(1, "super_admin", "admin@example.edu")
        session.add(actor)
        session.flush()
        entry = append_audit(session, actor, "test.record", "user:1")
        session.commit()

        entry.target = "changed"
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
        session.rollback()

        entry = session.get(AuditLog, entry.id)
        session.delete(entry)
        with pytest.raises(ValueError, match="append-only"):
            session.flush()


def test_anonymizing_user_preserves_audit_chain_and_invalidates_sessions(audit_engine) -> None:
    with Session(audit_engine, expire_on_commit=False) as session:
        administrator = _user(1, "super_admin", "admin@example.edu")
        subject = _user(2, "faculty", "faculty@example.edu")
        session.add_all([administrator, subject])
        session.flush()
        append_audit(session, subject, "auth.login_succeeded", "user:2")
        session.commit()
        prior_token_version = subject.token_version

        anonymized = anonymize_user(session, administrator, subject.id)

        assert anonymized.name == "Deleted user 2"
        assert anonymized.email.endswith("@invalid.example")
        assert anonymized.token_version == prior_token_version + 1
        assert anonymized.must_change_password is True
        assert anonymized.totp_secret_encrypted is None
        assert session.scalar(
            select(AuditLog).where(AuditLog.action == "auth.login_succeeded")
        ) is not None
        verify_audit_chain(session)
