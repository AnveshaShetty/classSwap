from datetime import datetime, timedelta, timezone
import secrets

import jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

from app.config import settings


password_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated=["bcrypt"],
    argon2__type="ID",
    argon2__time_cost=3,
    argon2__memory_cost=65536,
    argon2__parallelism=2,
)
dummy_password_hash = password_context.hash(secrets.token_urlsafe(32))
ABSOLUTE_SESSION_LIFETIME = timedelta(hours=8)
SLIDING_REFRESH_WINDOW = timedelta(minutes=10)


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_context.verify(password, password_hash)
    except (ValueError, UnknownHashError):
        return False


def password_hash_needs_update(password_hash: str) -> bool:
    return password_context.needs_update(password_hash)


def create_access_token(
    user_id: int,
    token_version: int = 0,
    session_started_at: datetime | None = None,
) -> str:
    issued_at = datetime.now(timezone.utc)
    session_started_at = session_started_at or issued_at
    absolute_expires_at = session_started_at + ABSOLUTE_SESSION_LIFETIME
    expires_at = min(
        issued_at + timedelta(minutes=settings.access_token_expire_minutes),
        absolute_expires_at,
    )
    claims = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": expires_at,
        "jti": secrets.token_urlsafe(16),
        "ver": token_version,
        "abs_exp": int(absolute_expires_at.timestamp()),
        "session_started": int(session_started_at.timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, object] | None:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=["HS256"],
            options={
                "require": [
                    "sub",
                    "iat",
                    "exp",
                    "jti",
                    "ver",
                    "abs_exp",
                    "session_started",
                ]
            },
        )
    except jwt.InvalidTokenError:
        return None

    subject = claims.get("sub")
    if (
        not isinstance(subject, str)
        or not subject.isdecimal()
        or not isinstance(claims.get("jti"), str)
        or not isinstance(claims.get("ver"), int)
        or not isinstance(claims.get("abs_exp"), int)
        or not isinstance(claims.get("session_started"), int)
    ):
        return None
    if datetime.now(timezone.utc).timestamp() >= claims["abs_exp"]:
        return None
    return claims


def get_token_user_id(token: str) -> int | None:
    claims = decode_access_token(token)
    if claims is None:
        return None
    return int(claims["sub"])
