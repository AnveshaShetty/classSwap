import pytest
from fastapi.testclient import TestClient

from app.core import rate_limit
from app.core.rate_limit import rate_limiter
from app.main import app
from tests.conftest import configure_csrf_client


@pytest.fixture(autouse=True)
def clear_rate_limiter():
    rate_limiter.clear()
    yield
    rate_limiter.clear()


def test_global_rate_limit_returns_429_and_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rate_limit, "GLOBAL_REQUEST_LIMIT", 2)
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 200

        limited = client.get("/health")

    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1


def test_login_has_a_stricter_ip_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rate_limit, "GLOBAL_REQUEST_LIMIT", 10)
    monkeypatch.setattr(rate_limit, "PUBLIC_REQUEST_LIMIT", 10)
    monkeypatch.setattr(rate_limit, "LOGIN_REQUEST_LIMIT", 2)
    with TestClient(app, base_url="https://testserver") as client:
        configure_csrf_client(client)
        rate_limiter.clear()
        payload = {"email": "unknown@example.edu", "password": "invalid"}
        first = client.post("/auth/login", json=payload)
        second = client.post("/auth/login", json=payload)
        limited = client.post("/auth/login", json=payload)

    assert first.status_code == second.status_code == 401
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1
