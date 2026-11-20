from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.core.security import decode_access_token
from backend.app.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def get_token_from_request(request: Request, token: Optional[str] = Depends(oauth2_scheme)) -> Optional[str]:
    """Retrieve JWT token from Authorization header or 'access_token' cookie."""
    if token and isinstance(token, str):
        return token
    auth_header = request.headers.get("Authorization")
    if auth_header:
        auth_clean = auth_header.strip()
        if auth_clean.startswith("Bearer "):
            return auth_clean.split(" ", 1)[1].strip()
        return auth_clean
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        # Strip potential surrounding quotes and Bearer prefix
        clean_token = cookie_token.strip('"').strip("'").strip()
        if clean_token.startswith("Bearer "):
            clean_token = clean_token.split(" ", 1)[1].strip()
        return clean_token
    return None

def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Return User if token is valid, else None without raising 401."""
    token = get_token_from_request(request)
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        return None
    return user

def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """Enforce authentication; raise 401 if unauthorized."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or session expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = get_current_user_optional(request, db=db)
    if not user:
        raise credentials_exception
    return user

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Ensure user is an HOD / Admin."""
    if current_user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: HOD / Admin privileges required."
        )
    return current_user

def require_faculty(current_user: User = Depends(get_current_user)) -> User:
    """Ensure user is a Faculty member."""
    if current_user.role != UserRole.FACULTY.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Faculty privileges required."
        )
    return current_user
