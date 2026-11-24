from datetime import datetime, timezone
from collections.abc import Iterator

import pytest
import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from passlib.context import CryptContext
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings, settings
from app.core.dependencies import get_current_user, require_roles
from app.database import Base, get_db
from app.core.security import decode_access_token
from app.main import app
from app.models import User
from app.services.auth import authenticate_user
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
    with TestClient(app, base_url="https://testserver") as client:
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
    assert f"{settings.auth_cookie_name.lower()}=" in set_cookie
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


def test_unknown_and_known_login_failures_have_same_response(auth_client: TestClient) -> None:
    known = auth_client.post(
        "/auth/login",
        json={"email": "ravi.kulal@demo.edu", "password": "wrong"},
    )
    unknown = auth_client.post(
        "/auth/login",
        json={"email": "unknown@demo.edu", "password": "wrong"},
    )

    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json()


def test_legacy_bcrypt_hash_is_upgraded_after_successful_login() -> None:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    legacy_hash = CryptContext(schemes=["bcrypt"]).hash("legacy-password")

    with Session(test_engine) as session:
        user = User(
            name="Legacy User",
            email="legacy@demo.edu",
            password_hash=legacy_hash,
            role="faculty",
            department="Computer Science and Design",
            teaches=True,
        )
        session.add(user)
        session.commit()

        assert authenticate_user(session, user.email, "legacy-password") is user
        assert user.password_hash.startswith("$argon2id$")

    test_engine.dispose()


def test_login_is_locked_after_five_failures() -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        user = User(
            name="Lockout User",
            email="lockout@demo.edu",
            password_hash=CryptContext(schemes=["argon2"]).hash("correct-password"),
            role="faculty",
            department="Computer Science and Design",
            teaches=True,
        )
        session.add(user)
        session.commit()

        for _ in range(5):
            assert authenticate_user(
                session,
                user.email,
                "incorrect-password",
                "198.51.100.77",
            ) is None
        assert authenticate_user(
            session,
            user.email,
            "correct-password",
            "198.51.100.77",
        ) is None
    test_engine.dispose()


@pytest.mark.parametrize(
    "password",
    ["short", "password1234", "Ravi.Kulal$2026"],
)
def test_password_policy_rejects_weak_or_identifying_values(password: str) -> None:
    from app.services.auth import validate_new_password

    with pytest.raises(ValueError):
        validate_new_password(password, "Ravi Kulal", "ravi.kulal@demo.edu")


def test_login_cookie_is_secure_when_configured(auth_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cookie_secure", True)
    response = auth_client.post(
        "/auth/login",
        json={"email": "ravi.kulal@demo.edu", "password": "demo123"},
    )

    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "__host-classswap_session=" in cookie
    assert "secure" in cookie


def test_logout_invalidates_previously_issued_token(auth_client: TestClient) -> None:
    auth_client.cookies.clear()
    login = auth_client.post(
        "/auth/login",
        json={"email": "ravi.kulal@demo.edu", "password": "demo123"},
    )
    old_token = auth_client.cookies.get(settings.auth_cookie_name)
    assert login.status_code == 200 and old_token

    logout_response = auth_client.post("/auth/logout")
    auth_client.cookies.set(settings.auth_cookie_name, old_token)

    assert logout_response.status_code == 204
    assert auth_client.get("/me").status_code == 401


def test_password_change_invalidates_old_token(auth_client: TestClient) -> None:
    auth_client.cookies.clear()
    login = auth_client.post(
        "/auth/login",
        json={"email": "ravi.kulal@demo.edu", "password": "demo123"},
    )
    old_token = auth_client.cookies.get(settings.auth_cookie_name)
    assert login.status_code == 200 and old_token

    change_response = auth_client.post(
        "/auth/change-password",
        json={
            "current_password": "demo123",
            "new_password": "SecureLongPassphrase2026!",
        },
    )
    auth_client.cookies.set(settings.auth_cookie_name, old_token)

    assert change_response.status_code == 204
    assert auth_client.get("/me").status_code == 401
    auth_client.cookies.clear()
    new_login = auth_client.post(
        "/auth/login",
        json={
            "email": "ravi.kulal@demo.edu",
            "password": "SecureLongPassphrase2026!",
        },
    )
    assert new_login.status_code == 200


def test_tokens_reject_none_and_non_hs256_algorithms() -> None:
    now = int(datetime.now(timezone.utc).timestamp())
    claims = {
        "sub": "1",
        "iat": now,
        "exp": now + 300,
        "jti": "test-token-id",
        "ver": 0,
        "abs_exp": now + 28_800,
        "session_started": now,
    }
    none_token = jwt.encode(claims, key="", algorithm="none")
    wrong_algorithm_token = jwt.encode(claims, key=settings.jwt_secret_key, algorithm="HS384")

    assert decode_access_token(none_token) is None
    assert decode_access_token(wrong_algorithm_token) is None


@pytest.mark.parametrize(
    "secret",
    ["", "replace-this-local-development-key", "short"],
)
def test_production_settings_reject_unsafe_jwt_secret(secret: str) -> None:
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(
            _env_file=None,
            ENV="production",
            JWT_SECRET_KEY=secret,
            COOKIE_SECURE=True,
        )


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
