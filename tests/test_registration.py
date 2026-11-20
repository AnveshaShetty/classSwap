import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import SessionLocal
from backend.app.models.user import User, UserRole

client = TestClient(app)

def test_register_page_loads():
    """Verify registration page renders HTTP 200."""
    response = client.get("/register")
    assert response.status_code == 200
    assert "Create Your Account" in response.text
    assert "College Email" in response.text

def test_registration_and_login_flow():
    """Verify full registration and login flow for a new faculty member."""
    db = SessionLocal()
    test_email = "test.faculty.new@classswap.edu"
    test_empid = "EMP-TEST-999"

    # Clean up if existed
    existing = db.query(User).filter(User.email == test_email).first()
    if existing:
        db.delete(existing)
        db.commit()

    # 1. Register with password mismatch
    res_mismatch = client.post("/auth/register-form", data={
        "name": "Dr. Test Professor",
        "email": test_email,
        "employee_id": test_empid,
        "department": "Computer Science",
        "designation": "Assistant Professor",
        "password": "Password123!",
        "confirm_password": "WrongPassword!",
        "phone": "+91 99999 88888"
    })
    assert res_mismatch.status_code == 200
    assert "Passwords do not match" in res_mismatch.text

    # 2. Register with valid details
    res_success = client.post("/auth/register-form", data={
        "name": "Dr. Test Professor",
        "email": test_email,
        "employee_id": test_empid,
        "department": "Computer Science",
        "designation": "Assistant Professor",
        "password": "Password123!",
        "confirm_password": "Password123!",
        "phone": "+91 99999 88888"
    })
    assert res_success.status_code == 200
    assert "Account Created" in res_success.text or "Welcome" in res_success.text

    # Verify user exists in database with FACULTY role
    created_user = db.query(User).filter(User.email == test_email).first()
    assert created_user is not None
    assert created_user.role == UserRole.FACULTY.value
    assert created_user.employee_id == test_empid
    assert created_user.designation == "Assistant Professor"

    # 3. Duplicate registration attempt should be rejected
    res_dup = client.post("/auth/register-form", data={
        "name": "Dr. Another Person",
        "email": test_email,
        "employee_id": "EMP-OTHER-111",
        "department": "Information Technology",
        "designation": "Professor",
        "password": "Password123!",
        "confirm_password": "Password123!"
    })
    assert res_dup.status_code == 200
    assert "already registered" in res_dup.text

    # 4. Duplicate employee ID should be rejected
    res_dup_emp = client.post("/auth/register-form", data={
        "name": "Dr. Different Email",
        "email": "different.email@classswap.edu",
        "employee_id": test_empid,
        "department": "Information Technology",
        "designation": "Professor",
        "password": "Password123!",
        "confirm_password": "Password123!"
    })
    assert res_dup_emp.status_code == 200
    assert "already registered" in res_dup_emp.text

    # 5. Log in with the newly registered user
    login_res = client.post("/auth/login-form", data={
        "email": test_email,
        "password": "Password123!"
    }, follow_redirects=False)
    assert login_res.status_code == 303
    assert "/faculty/dashboard" in login_res.headers.get("location", "")
    assert "access_token" in login_res.headers.get("set-cookie", "")

    # Clean up
    db.delete(created_user)
    db.commit()
    db.close()
