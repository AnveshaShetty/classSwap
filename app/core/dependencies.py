from collections.abc import Callable
import hmac
from datetime import date, datetime, timedelta, timezone
import logging

from cryptography.fernet import InvalidToken
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import create_access_token, decode_access_token
from app.core.authorization import can_act_as_admin
from app.core.totp import decrypt_totp_secret, hash_backup_code, verify_totp
from app.database import get_db
from app.models import TotpBackupCode, User
from app.services.admin import AdminNotFound, get_acting_admin


security_logger = logging.getLogger("app.security")


def _require_admin_mfa(user: User, request: Request, session: Session) -> None:
    if user.role not in {"hod", "super_admin"}:
        return
    if not user.totp_enabled or not user.totp_secret_encrypted:
        security_logger.warning(
            "Admin MFA denied",
            extra={"user_id": user.id, "action": "mfa.not_enabled"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Set up two-factor authentication before using admin features.",
        )

    code = request.headers.get("X-TOTP-Code", "")
    try:
        secret = decrypt_totp_secret(user.totp_secret_encrypted)
    except (InvalidToken, UnicodeDecodeError, RuntimeError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A valid two-factor code is required.",
        ) from None
    if verify_totp(secret, code):
        return

    code_hash = hash_backup_code(code)
    backup = session.scalar(
        select(TotpBackupCode)
        .where(TotpBackupCode.user_id == user.id, TotpBackupCode.code_hash == code_hash)
        .with_for_update()
    )
    if backup is not None and hmac.compare_digest(backup.code_hash, code_hash):
        session.delete(backup)
        session.commit()
        return
    security_logger.warning(
        "Admin MFA denied",
        extra={"user_id": user.id, "action": "mfa.invalid_code"},
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="A valid two-factor code is required.",
    )


def get_current_user(
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> User:
    token = request.cookies.get(settings.auth_cookie_name)
    claims = decode_access_token(token) if token else None
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please sign in to continue.",
        )

    user = session.scalar(select(User).where(User.id == int(claims["sub"])))
    if user is None or claims["ver"] != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session is no longer valid. Please sign in again.",
        )
    expires_at = datetime.fromtimestamp(int(claims["exp"]), timezone.utc)
    if expires_at - datetime.now(timezone.utc) <= timedelta(minutes=10):
        session_started_at = datetime.fromtimestamp(
            int(claims["session_started"]),
            timezone.utc,
        )
        response.set_cookie(
            key=settings.auth_cookie_name,
            value=create_access_token(
                user.id,
                token_version=user.token_version,
                session_started_at=session_started_at,
            ),
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=settings.access_token_expire_minutes * 60,
            path="/",
        )
    return user


def require_admin_mfa(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> User:
    _require_admin_mfa(user, request, session)
    return user


def require_roles(*allowed_roles: str) -> Callable[..., User]:
    if not allowed_roles:
        raise ValueError("At least one role must be allowed.")

    def role_guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            security_logger.warning(
                "Authorization denied",
                extra={"user_id": user.id, "action": "authorization.role_denied"},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return user

    return role_guard


def require_policy(policy: Callable[[User], bool]) -> Callable[..., User]:
    def policy_guard(user: User = Depends(get_current_user)) -> User:
        if not policy(user):
            security_logger.warning(
                "Authorization denied",
                extra={"user_id": user.id, "action": "authorization.policy_denied"},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return user

    return policy_guard


def require_acting_admin(permission: str) -> Callable[..., User]:
    if not permission:
        raise ValueError("An admin permission is required.")

    def acting_admin_guard(
        request: Request,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_db),
    ) -> User:
        if user.role == "super_admin":
            _require_admin_mfa(user, request, session)
            return user
        try:
            acting_user, _ = get_acting_admin(session, user.department, date.today())
        except AdminNotFound as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(error),
            ) from error
        if not can_act_as_admin(user, acting_user.id, permission):
            security_logger.warning(
                "Authorization denied",
                extra={"user_id": user.id, "action": "authorization.acting_admin_denied"},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to perform this admin action.",
            )
        _require_admin_mfa(user, request, session)
        return user

    return acting_admin_guard
