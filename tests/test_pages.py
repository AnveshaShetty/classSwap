import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_public_pages():
    res = client.get("/")
    assert res.status_code == 200
    assert "Smart Substitutions. Zero Idle Hours." in res.text

    res = client.get("/login")
    assert res.status_code == 200
    assert "Sign in to ClassSwap" in res.text

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
