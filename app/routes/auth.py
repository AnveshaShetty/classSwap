from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models import User
from app.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    UserRead,
)
from app.services.auth import (
    authenticate_user,
    consume_password_reset_token,
    create_password_reset_token,
    validate_new_password,
)
from app.services.email import dispatch_password_reset_email


router = APIRouter()


@router.post("/auth/login", response_model=UserRead)
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


@router.post("/auth/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
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


@router.post("/auth/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
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


@router.get("/me", response_model=UserRead)
def read_current_user(
    user: User = Depends(get_current_user),
) -> User:
    return user
