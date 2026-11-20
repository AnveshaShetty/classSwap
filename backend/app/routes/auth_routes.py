from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from datetime import timedelta

from backend.app.database import get_db
from backend.app.core.security import verify_password, get_password_hash, create_access_token
from backend.app.core.dependencies import get_current_user, get_current_user_optional
from backend.app.models.user import User, UserRole
from backend.app.schemas.auth import LoginRequest, Token, UserCreate, UserResponse
from backend.app.config import settings

router = APIRouter(tags=["Authentication"])

@router.post("/api/auth/login", response_model=Token)
def api_login(credentials: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Authenticate user with email and password, returning JWT and setting cookie."""
    user = db.query(User).filter(User.email == credentials.email.lower().strip()).first()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password."
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated.")

    access_token = create_access_token(subject=user.id, role=user.role)
    
    # Set HTTP-only cookie for browser navigation
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=False  # Allow local HTTP development
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        role=user.role,
        name=user.name,
        email=user.email,
        user_id=user.id
    )

@router.post("/auth/login-form")
def form_login(
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handle standard HTML form submission for login."""
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not verify_password(password, user.password_hash):
        return RedirectResponse(url="/login?error=Invalid+credentials", status_code=status.HTTP_303_SEE_OTHER)

    access_token = create_access_token(subject=user.id, role=user.role)
    redirect_url = "/admin/dashboard" if user.role == UserRole.ADMIN.value else "/faculty/dashboard"
    
    res = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    res.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=False
    )
    return res

@router.post("/api/auth/register", response_model=UserResponse)
def api_register(user_in: UserCreate, db: Session = Depends(get_db)):
    """Register a new faculty or admin member."""
    existing = db.query(User).filter(User.email == user_in.email.lower().strip()).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is already registered.")

    new_user = User(
        name=user_in.name.strip(),
        email=user_in.email.lower().strip(),
        password_hash=get_password_hash(user_in.password),
        role=user_in.role if user_in.role in [UserRole.ADMIN.value, UserRole.FACULTY.value] else UserRole.FACULTY.value,
        department=user_in.department.strip(),
        phone=user_in.phone.strip() if user_in.phone else None,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.get("/api/auth/me")
def api_me(current_user: User = Depends(get_current_user)):
    """Return profile data of currently authenticated user."""
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "department": current_user.department,
        "phone": current_user.phone
    }

@router.get("/logout")
@router.post("/api/auth/logout")
def logout(response: Response):
    """Log out user by clearing cookie."""
    res = RedirectResponse(url="/login?msg=Logged+out+successfully", status_code=status.HTTP_303_SEE_OTHER)
    res.delete_cookie("access_token")
    return res
