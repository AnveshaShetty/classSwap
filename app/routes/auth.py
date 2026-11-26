import logging
import secrets

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.audit import append_audit
from app.core.csrf import require_csrf
from app.core.dependencies import get_current_user, require_roles, verify_admin_mfa_code
from app.core.security import (
    ADMIN_MFA_COOKIE_NAME,
    ADMIN_MFA_SESSION_LIFETIME,
    create_access_token,
    create_admin_mfa_token,
    hash_password,
    verify_password,
)
from app.core.totp import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    hash_backup_code,
    new_totp_secret,
    provisioning_uri,
    verify_totp,
)
from app.database import get_db
from app.models import (
    Absence,
    AuditLog,
    Leave,
    Room,
    Section,
    Subject,
    Substitution,
    Timetable,
    TotpBackupCode,
    User,
)
from app.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    TotpCodeRequest,
    TotpVerifyRequest,
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
security_logger = logging.getLogger("app.security")


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


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={303: {"description": "Browser logout redirects to sign-in."}},
)
def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> RedirectResponse | None:
    current_user.token_version += 1
    append_audit(session, current_user, "auth.logout", "user:%d" % current_user.id)
    session.commit()
    if "text/html" in request.headers.get("accept", "").lower():
        redirect = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        redirect.delete_cookie(settings.auth_cookie_name, path="/")
        redirect.delete_cookie(ADMIN_MFA_COOKIE_NAME, path="/")
        return redirect
    response.delete_cookie(settings.auth_cookie_name, path="/")
    response.delete_cookie(ADMIN_MFA_COOKIE_NAME, path="/")


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
    append_audit(session, current_user, "auth.password_changed", "user:%d" % current_user.id)
    session.commit()
    response.delete_cookie(settings.auth_cookie_name, path="/")
    response.delete_cookie(ADMIN_MFA_COOKIE_NAME, path="/")


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


@router.post("/auth/totp/verify")
def verify_totp_for_admin(
    payload: TotpVerifyRequest,
    response: Response,
    current_user: User = Depends(require_roles("hod", "super_admin")),
    session: Session = Depends(get_db),
) -> dict[str, bool]:
    if not current_user.totp_enabled or not current_user.totp_secret_encrypted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Set up two-factor authentication before using admin features.",
        )
    if not verify_admin_mfa_code(current_user, payload.code, session):
        security_logger.warning(
            "Admin MFA denied",
            extra={"user_id": current_user.id, "action": "mfa.invalid_code"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A valid two-factor code is required.",
        )

    response.set_cookie(
        key=ADMIN_MFA_COOKIE_NAME,
        value=create_admin_mfa_token(current_user.id, current_user.token_version),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=int(ADMIN_MFA_SESSION_LIFETIME.total_seconds()),
        path="/",
    )
    return {"verified": True}


@router.get("/me", response_model=UserRead)
def read_current_user(
    user: User = Depends(get_current_user),
) -> User:
    return user


@router.get("/me/export")
def export_current_user_data(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> JSONResponse:
    security_logger.info(
        "User data export requested",
        extra={"user_id": user.id, "action": "user.data_exported"},
    )
    timetable_rows = session.execute(
        select(Timetable, Section.name, Subject.name, Room.name)
        .join(Section, Section.id == Timetable.section_id)
        .join(Subject, Subject.id == Timetable.subject_id)
        .join(Room, Room.id == Timetable.room_id)
        .where(Timetable.faculty_id == user.id)
        .order_by(Timetable.day_of_week, Timetable.period_no)
    )
    absences = session.scalars(
        select(Absence).where(Absence.faculty_id == user.id).order_by(Absence.date, Absence.period_no)
    )
    substitutions = session.execute(
        select(Substitution, Absence.faculty_id)
        .join(Absence, Absence.id == Substitution.absence_id)
        .where(or_(Substitution.substitute_id == user.id, Absence.faculty_id == user.id))
        .order_by(Substitution.date, Substitution.period_no, Substitution.id)
    )
    leaves = session.scalars(
        select(Leave).where(Leave.user_id == user.id).order_by(Leave.date)
    )
    audit_entries = session.scalars(
        select(AuditLog).where(AuditLog.user_id == user.id).order_by(AuditLog.id)
    )
    data = {
        "schema_version": 1,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "department": user.department,
            "role": user.role,
            "teaches": user.teaches,
        },
        "timetable": [
            {
                "id": row.id,
                "day_of_week": row.day_of_week,
                "period": row.period_no,
                "section": section_name,
                "subject": subject_name,
                "room": room_name,
            }
            for row, section_name, subject_name, room_name in timetable_rows
        ],
        "absences": [
            {
                "id": absence.id,
                "date": absence.date.isoformat(),
                "period": absence.period_no,
                "reason": absence.reason,
            }
            for absence in absences
        ],
        "substitutions": [
            {
                "id": substitution.id,
                "date": substitution.date.isoformat(),
                "period": substitution.period_no,
                "status": substitution.status,
                "related_to_own_absence": faculty_id == user.id,
            }
            for substitution, faculty_id in substitutions
        ],
        "leaves": [{"date": leave.date.isoformat()} for leave in leaves],
        "audit_events": [
            {
                "id": entry.id,
                "action": entry.action,
                "target": entry.target,
                "created_at": entry.created_at.isoformat(),
                "entry_hash": entry.entry_hash,
            }
            for entry in audit_entries
        ],
    }
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": 'attachment; filename="classswap-user-data.json"'},
    )
