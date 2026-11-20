from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.dependencies import get_current_user
from app.core.security import create_access_token
from app.database import get_db
from app.models import User
from app.schemas.auth import LoginRequest, UserRead
from app.services.auth import authenticate_user


router = APIRouter()


@router.post("/auth/login", response_model=UserRead)
def login(
    credentials: LoginRequest,
    response: Response,
    session: Session = Depends(get_db),
) -> User:
    user = authenticate_user(session, str(credentials.email), credentials.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
        )

    response.set_cookie(
        key=settings.auth_cookie_name,
        value=create_access_token(user.id),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    return user


@router.get("/me", response_model=UserRead)
def read_current_user(
    user: User = Depends(get_current_user),
) -> User:
    return user
