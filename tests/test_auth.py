from collections.abc import Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_user, require_roles
from app.database import Base, get_db
from app.main import app
from app.models import User
from scripts.seed import load_seed


@pytest.fixture(scope="module")
def auth_client() -> Iterator[TestClient]:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        with session.begin():
            load_seed(session)

    def override_get_db() -> Iterator[Session]:
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    test_engine.dispose()


def test_login_sets_http_only_cookie_and_me_returns_user(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/auth/login",
        json={"email": "ravi.kulal@demo.edu", "password": "demo123"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "ravi.kulal@demo.edu"
    assert "access_token" not in response.json()
    set_cookie = response.headers["set-cookie"].lower()
    assert "classswap_access=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert auth_client.get("/me").json()["role"] == "faculty"


def test_invalid_credentials_and_missing_cookie_are_rejected(auth_client: TestClient) -> None:
    auth_client.cookies.clear()
    invalid_login = auth_client.post(
        "/auth/login",
        json={"email": "ravi.kulal@demo.edu", "password": "wrong"},
    )
    unauthenticated = auth_client.get("/me")

    assert invalid_login.status_code == 401
    assert unauthenticated.status_code == 401


def test_role_guard_allows_admin_roles_and_rejects_faculty() -> None:
    guarded_app = FastAPI()

    @guarded_app.get("/admin")
    def admin_page(user: User = Depends(require_roles("hod", "super_admin"))) -> dict[str, str]:
        return {"role": user.role}

    current_user = User(
        id=1,
        name="Demo",
        email="demo@demo.edu",
        password_hash="",
        role="faculty",
        department="Computer Science and Design",
        teaches=True,
    )
    guarded_app.dependency_overrides[get_current_user] = lambda: current_user
    client = TestClient(guarded_app)
    assert client.get("/admin").status_code == 403

    current_user.role = "hod"
    assert client.get("/admin").json() == {"role": "hod"}
    current_user.role = "super_admin"
    assert client.get("/admin").json() == {"role": "super_admin"}
    guarded_app.dependency_overrides.clear()
