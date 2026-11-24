import secrets

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.csrf import require_csrf
from app.core.dependencies import get_current_user, require_roles
from app.core.security import create_access_token, hash_password, verify_password
from app.core.totp import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    hash_backup_code,
    new_totp_secret,
    provisioning_uri,
    verify_totp,
)
from app.database import get_db
from app.models import TotpBackupCode, User
from app.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    TotpCodeRequest,
    UserRead,
)
from app.services.auth import (
    authenticate_user,
    consume_password_reset_token,
    create_password_reset_token,
    validate_new_password,
)
from app.services.email import dispatch_password_reset_email


router = APIRouter(dependencies=[Depends(require_csrf)])


@router.post(
    "/auth/login",
    response_model=UserRead,
    openapi_extra={"x-auth-policy": "public"},
)
def login(
    credentials: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> User:
    client_ip = request.client.host if request.client is not None else "unknown"
    user = authenticate_user(
        session,
        str(credentials.email),
        credentials.password,
        client_ip,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
        )

    response.set_cookie(
        key=settings.auth_cookie_name,
        value=create_access_token(user.id, token_version=user.token_version),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    return user


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> None:
    current_user.token_version += 1
    session.commit()
    response.delete_cookie(settings.auth_cookie_name, path="/")


@router.post("/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> None:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    try:
        validate_new_password(payload.new_password, current_user.name, current_user.email)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    current_user.password_hash = hash_password(payload.new_password)
    current_user.must_change_password = False
    current_user.token_version += 1
    session.commit()
    response.delete_cookie(settings.auth_cookie_name, path="/")


@router.post(
    "/auth/password-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    openapi_extra={"x-auth-policy": "public"},
)
def request_password_reset(
    payload: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
) -> dict[str, str]:
    reset = create_password_reset_token(session, str(payload.email))
    if reset is not None:
        background_tasks.add_task(dispatch_password_reset_email, *reset)
    return {
        "message": "If the email is associated with an account, password reset instructions will be sent."
    }


@router.post(
    "/auth/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    openapi_extra={"x-auth-policy": "public"},
)
def confirm_password_reset(
    payload: PasswordResetConfirm,
    session: Session = Depends(get_db),
) -> None:
    try:
        reset = consume_password_reset_token(session, payload.token, payload.new_password)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not reset:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset link is invalid or has expired.",
        )


@router.post("/auth/totp/setup")
def setup_totp(
    current_user: User = Depends(require_roles("hod", "super_admin")),
    session: Session = Depends(get_db),
) -> dict[str, str]:
    if current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Two-factor authentication is already enabled.",
        )
    try:
        secret = new_totp_secret()
        encrypted = encrypt_totp_secret(secret)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail="Two-factor setup is not configured.") from error
    current_user.totp_pending_secret_encrypted = encrypted
    session.commit()
    return {
        "secret": secret,
        "provisioning_uri": provisioning_uri(secret, current_user.email),
    }


@router.post("/auth/totp/enable")
def enable_totp(
    payload: TotpCodeRequest,
    current_user: User = Depends(require_roles("hod", "super_admin")),
    session: Session = Depends(get_db),
) -> dict[str, list[str]]:
    encrypted = current_user.totp_pending_secret_encrypted
    if not encrypted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Start two-factor setup before enabling it.",
        )
    try:
        secret = decrypt_totp_secret(encrypted)
    except (InvalidToken, RuntimeError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=503, detail="Two-factor setup could not be completed.") from error
    if not verify_totp(secret, payload.code):
        raise HTTPException(status_code=400, detail="The two-factor code is invalid.")

    backup_codes = [secrets.token_urlsafe(12) for _ in range(10)]
    current_user.totp_secret_encrypted = encrypted
    current_user.totp_pending_secret_encrypted = None
    current_user.totp_enabled = True
    session.add_all(
        [
            TotpBackupCode(
                user_id=current_user.id,
                code_hash=hash_backup_code(code),
            )
            for code in backup_codes
        ]
    )
    session.commit()
    return {"backup_codes": backup_codes}


@router.get("/me", response_model=UserRead)
def read_current_user(
    user: User = Depends(get_current_user),
) -> User:
    return user
