import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_public_pages():
    res = client.get("/")
    assert res.status_code == 200
    assert "Smart Substitutions. Zero Idle Hours." in res.text or "Smarter Timetables" in res.text

    res = client.get("/login")
    assert res.status_code == 200
    assert "Sign In to ClassSwap" in res.text or "Sign in to ClassSwap" in res.text

    res = client.get("/register")
    assert res.status_code == 200
    assert "Create Your Account" in res.text

def test_admin_navigation_pages():
    # Login as admin to get cookie
    login_res = client.post("/api/auth/login", json={
        "email": "admin@classswap.edu",
        "password": "Admin@123"
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    cookies = {"access_token": f"Bearer {token}"}

    admin_routes = [
        "/admin/dashboard",
        "/admin/timetable",
        "/admin/absences",
        "/admin/substitutions",
        "/admin/free-rooms",
        "/admin/faculty",
        "/admin/subjects",
        "/admin/sections",
        "/admin/rooms",
        "/admin/reports",
        "/admin/settings",
    ]

    for route in admin_routes:
        res = client.get(route, cookies=cookies)
        assert res.status_code == 200, f"Route {route} failed with status {res.status_code}"
        assert "ClassSwap" in res.text

def test_faculty_navigation_pages():
    login_res = client.post("/api/auth/login", json={
        "email": "priya.nair@classswap.edu",
        "password": "Faculty@123"
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    cookies = {"access_token": f"Bearer {token}"}

    faculty_routes = [
        "/faculty/dashboard",
        "/faculty/mark-absence",
        "/faculty/requests",
        "/faculty/history",
    ]

    for route in faculty_routes:
        res = client.get(route, cookies=cookies)
        assert res.status_code == 200, f"Route {route} failed with status {res.status_code}"
        assert "ClassSwap" in res.text

def test_form_login_admin_and_faculty():
    # Admin Form Login
    res_admin = client.post("/auth/login-form", data={
        "email": "admin@classswap.edu",
        "password": "Admin@123"
    }, follow_redirects=False)
    assert res_admin.status_code == 303
    assert res_admin.headers["location"] == "/admin/dashboard"
    admin_cookie = res_admin.cookies.get("access_token")
    assert admin_cookie is not None

    dash_admin = client.get("/admin/dashboard", cookies={"access_token": admin_cookie})
    assert dash_admin.status_code == 200
    assert "Overview" in dash_admin.text or "Dashboard" in dash_admin.text

    # Faculty Form Login
    res_fac = client.post("/auth/login-form", data={
        "email": "priya.nair@classswap.edu",
        "password": "Faculty@123"
    }, follow_redirects=False)
    assert res_fac.status_code == 303
    assert res_fac.headers["location"] == "/faculty/dashboard"
    fac_cookie = res_fac.cookies.get("access_token")
    assert fac_cookie is not None

    dash_fac = client.get("/faculty/dashboard", cookies={"access_token": fac_cookie})
    assert dash_fac.status_code == 200
    assert "Priya" in dash_fac.text or "Dashboard" in dash_fac.text
