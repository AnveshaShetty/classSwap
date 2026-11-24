import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import (
    dummy_password_hash,
    hash_password,
    password_hash_needs_update,
    verify_password,
)
from app.models import LoginAttempt, PasswordResetToken, User


logger = logging.getLogger(__name__)
MAX_LOGIN_FAILURES = 5
INITIAL_LOCKOUT = timedelta(minutes=15)
MAX_LOCKOUT = timedelta(hours=24)
COMMON_PASSWORDS = {
    "password123",
    "password1234",
    "qwerty123456",
    "letmein12345",
    "welcome12345",
    "admin123456",
    "iloveyou1234",
}


def validate_new_password(password: str, name: str, email: str) -> None:
    normalized = password.casefold()
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    if normalized in COMMON_PASSWORDS:
        raise ValueError("Choose a less common password.")

    identities = [name.casefold().strip(), email.casefold().strip()]
    email_name = email.partition("@")[0].casefold()
    if len(email_name) >= 4:
        identities.append(email_name)
    if any(identity and identity in normalized for identity in identities):
        raise ValueError("Password must not contain your name or email.")


def _key_hash(value: str) -> str:
    return hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _attempts_for(session: Session, keys: list[tuple[str, str]]) -> list[LoginAttempt]:
    return [
        row
        for scope, key_hash in keys
        if (row := session.scalar(
            select(LoginAttempt)
            .where(LoginAttempt.scope == scope, LoginAttempt.key_hash == key_hash)
            .with_for_update()
        ))
        is not None
    ]


def _record_failure(
    session: Session,
    keys: list[tuple[str, str]],
    now: datetime,
) -> None:
    for scope, key_hash in keys:
        attempt = session.scalar(
            select(LoginAttempt)
            .where(LoginAttempt.scope == scope, LoginAttempt.key_hash == key_hash)
            .with_for_update()
        )
        if attempt is None:
            attempt = LoginAttempt(scope=scope, key_hash=key_hash, failures=0)
            session.add(attempt)
        attempt.failures += 1
        if attempt.failures >= MAX_LOGIN_FAILURES:
            multiplier = 2 ** (attempt.failures - MAX_LOGIN_FAILURES)
            duration = min(INITIAL_LOCKOUT * multiplier, MAX_LOCKOUT)
            attempt.locked_until = now + duration
        attempt.updated_at = now


def _clear_attempts(session: Session, attempts: list[LoginAttempt]) -> None:
    for attempt in attempts:
        session.delete(attempt)


def create_password_reset_token(
    session: Session,
    email: str,
) -> tuple[str, str] | None:
    normalized_email = email.strip().lower()
    user = session.scalar(select(User).where(User.email == normalized_email))
    if user is None:
        return None

    now = _now_utc()
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    previous_tokens = session.scalars(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .with_for_update()
    )
    for previous in previous_tokens:
        previous.used_at = now
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=now + timedelta(minutes=15),
        )
    )
    session.commit()
    return user.email, token


def consume_password_reset_token(
    session: Session,
    token: str,
    new_password: str,
) -> bool:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    reset = session.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == token_hash)
        .with_for_update()
    )
    if (
        reset is None
        or not hmac.compare_digest(reset.token_hash, token_hash)
        or reset.used_at is not None
        or _as_utc(reset.expires_at) <= _now_utc()
    ):
        return False

    user = session.get(User, reset.user_id)
    if user is None:
        return False
    validate_new_password(new_password, user.name, user.email)
    now = _now_utc()
    reset.used_at = now
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.token_version += 1
    for previous in session.scalars(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .with_for_update()
    ):
        previous.used_at = now
    session.commit()
    return True


def authenticate_user(
    session: Session,
    email: str,
    password: str,
    ip_address: str = "unknown",
) -> User | None:
    normalized_email = email.strip().lower()
    keys = [
        ("account", _key_hash(normalized_email)),
        ("ip", _key_hash(ip_address)),
    ]
    now = _now_utc()
    attempts = _attempts_for(session, keys)
    is_locked = any(
        attempt.locked_until is not None and _as_utc(attempt.locked_until) > now
        for attempt in attempts
    )
    user = session.scalar(select(User).where(User.email == normalized_email))
    password_valid = verify_password(
        password,
        user.password_hash if user is not None else dummy_password_hash,
    )
    if is_locked:
        logger.warning(
            "Authentication temporarily locked",
            extra={"account_hash": keys[0][1], "ip_hash": keys[1][1]},
        )
        return None
    if user is None or not password_valid:
        _record_failure(session, keys, now)
        session.commit()
        logger.warning(
            "Authentication failed",
            extra={"account_hash": keys[0][1], "ip_hash": keys[1][1]},
        )
        return None
    _clear_attempts(session, attempts)
    if password_hash_needs_update(user.password_hash):
        user.password_hash = hash_password(password)
    session.commit()
    return user
