import pytest
from backend.app.core.security import get_password_hash, verify_password, create_access_token, decode_access_token
from backend.app.models.user import User, UserRole

def test_password_hashing():
    raw_password = "SecurePassword123"
    hashed = get_password_hash(raw_password)
    
    assert hashed != raw_password
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False

def test_jwt_token_cycle():
    user_id = 42
    role = UserRole.ADMIN.value
    token = create_access_token(subject=user_id, role=role)
    
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == str(user_id)
    assert payload["role"] == role

def test_user_roles(db_session):
    admin = db_session.query(User).filter(User.email == "admin@test.edu").first()
    faculty = db_session.query(User).filter(User.email == "alice@test.edu").first()

    assert admin.role == UserRole.ADMIN.value
    assert faculty.role == UserRole.FACULTY.value
