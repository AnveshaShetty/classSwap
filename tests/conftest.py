from fastapi.testclient import TestClient

from app.core.csrf import CSRF_COOKIE_NAME


def configure_csrf_client(client: TestClient) -> None:
    response = client.get("/login")
    assert response.status_code == 200
    token = client.cookies.get(CSRF_COOKIE_NAME)
    assert token
    client.headers["X-CSRF-Token"] = token
    client.headers["Origin"] = str(client.base_url).rstrip("/")
