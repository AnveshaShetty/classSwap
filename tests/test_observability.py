import logging

from fastapi.testclient import TestClient

from app.core.observability import SecurityRedactionFilter
from app.main import app


def test_redaction_filter_removes_email_and_password_values() -> None:
    record = logging.LogRecord(
        name="app.security",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="Login failed for person@example.edu password=very-secret-value",
        args=(),
        exc_info=None,
    )

    SecurityRedactionFilter().filter(record)

    assert "person@example.edu" not in record.getMessage()
    assert "very-secret-value" not in record.getMessage()
    assert "[REDACTED_EMAIL]" in record.getMessage()


def test_responses_include_a_server_generated_request_id() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/health", headers={"X-Request-ID": "caller-value"})

    request_id = response.headers["x-request-id"]
    assert request_id != "caller-value"
    assert len(request_id) == 32
