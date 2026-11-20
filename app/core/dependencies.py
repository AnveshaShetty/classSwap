from collections.abc import Callable

from datetime import date

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.core.security import get_token_user_id
from app.models import User
from app.services.admin import AdminNotFound, get_acting_admin


def get_current_user(
    request: Request,
    session: Session = Depends(get_db),
) -> User:
    token = request.cookies.get(settings.auth_cookie_name)
    user_id = get_token_user_id(token) if token else None
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please sign in to continue.",
        )

    user = session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session is no longer valid. Please sign in again.",
        )
    return user


def require_roles(*allowed_roles: str) -> Callable[..., User]:
    if not allowed_roles:
        raise ValueError("At least one role must be allowed.")

    def role_guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return user

    return role_guard


def require_acting_admin(permission: str) -> Callable[..., User]:
    if not permission:
        raise ValueError("An admin permission is required.")

    def acting_admin_guard(
        user: User = Depends(get_current_user),
        session: Session = Depends(get_db),
    ) -> User:
        if user.role == "super_admin":
            return user
        try:
            acting_user, _ = get_acting_admin(session, user.department, date.today())
        except AdminNotFound as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(error),
            ) from error
        if acting_user.id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the acting admin can perform this action.",
            )
        if user.role != "hod" and permission not in {"substitutions", "reports"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Stand-in admins may only manage substitutions and reports.",
            )
        return user

    return acting_admin_guard
