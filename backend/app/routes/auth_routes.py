from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import Optional

from backend.app.database import get_db
from backend.app.core.security import verify_password, get_password_hash, create_access_token
from backend.app.core.dependencies import get_current_user, get_current_user_optional
from backend.app.models.user import User, UserRole
from backend.app.schemas.auth import LoginRequest, Token, UserCreate, UserResponse
from backend.app.config import settings

router = APIRouter(tags=["Authentication"])
templates = Jinja2Templates(directory="backend/app/templates")

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
        value=access_token,
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
@router.post("/login")
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
        value=access_token,
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

@router.get("/register", response_class=HTMLResponse)
@router.get("/auth/register", response_class=HTMLResponse)
def auth_register_page(request: Request, db: Session = Depends(get_db)):
    """Faculty Registration Page."""
    current_user = get_current_user_optional(request, db=db)
    if current_user:
        if current_user.role == UserRole.ADMIN.value:
            return RedirectResponse(url="/admin/dashboard", status_code=303)
        return RedirectResponse(url="/faculty/dashboard", status_code=303)
    return templates.TemplateResponse(request, "register.html", {
        "request": request,
        "college_name": settings.COLLEGE_NAME
    })

@router.post("/auth/register-form")
@router.post("/register")
def form_register(
    request: Request,
    response: Response,
    name: str = Form(...),
    email: str = Form(...),
    employee_id: str = Form(...),
    department: str = Form(...),
    designation: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Handle HTML registration form submission — creates faculty account only."""
    # Validate passwords match
    if password != confirm_password:
        return templates.TemplateResponse(request, "register.html", {
            "request": request,
            "error": "Passwords do not match.",
            "form_name": name, "form_email": email, "form_employee_id": employee_id
        })
    if len(password) < 8:
        return templates.TemplateResponse(request, "register.html", {
            "request": request,
            "error": "Password must be at least 8 characters.",
            "form_name": name, "form_email": email, "form_employee_id": employee_id
        })
    # Check duplicate email
    existing = db.query(User).filter(User.email == email.lower().strip()).first()
    if existing:
        return templates.TemplateResponse(request, "register.html", {
            "request": request,
            "error": "This email is already registered. Please sign in.",
            "form_name": name, "form_email": email, "form_employee_id": employee_id
        })

    # Check duplicate employee ID
    clean_emp_id = employee_id.strip() if employee_id else None
    if clean_emp_id:
        existing_emp = db.query(User).filter(User.employee_id == clean_emp_id).first()
        if existing_emp:
            return templates.TemplateResponse(request, "register.html", {
                "request": request,
                "error": f"Employee ID '{clean_emp_id}' is already registered.",
                "form_name": name, "form_email": email, "form_employee_id": employee_id
            })

    # Build display name
    display_name = name.strip()

    new_user = User(
        name=display_name,
        email=email.lower().strip(),
        employee_id=clean_emp_id,
        designation=designation.strip() if designation else "Faculty",
        password_hash=get_password_hash(password),
        role=UserRole.FACULTY.value,  # always faculty for public registration
        department=department.strip(),
        phone=phone.strip() if phone and phone.strip() else None,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return templates.TemplateResponse(request, "register.html", {
        "request": request,
        "success": f"Welcome, {new_user.name}! Your faculty account has been created."
    })


@router.get("/logout")
@router.post("/api/auth/logout")
def logout(response: Response):
    """Log out user by clearing cookie."""
    res = RedirectResponse(url="/login?msg=Logged+out+successfully", status_code=status.HTTP_303_SEE_OTHER)
    res.delete_cookie("access_token")
    return res
