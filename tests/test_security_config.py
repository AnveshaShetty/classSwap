import re
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.config import Settings, settings
from app.main import api_docs_urls, app


def _production_settings(**overrides: str | bool) -> Settings:
    config: dict[str, object] = {
        "_env_file": None,
        "ENV": "production",
        "DEBUG": False,
        "JWT_SECRET_KEY": "sufficiently-long-random-production-key-value",
        "COOKIE_SECURE": True,
        "APP_BASE_URL": "https://classswap.example",
        "SMTP_HOST": "smtp.example",
        "TOTP_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
        "ALLOWED_HOSTS": "classswap.example",
        "DATABASE_URL": (
            "postgresql+psycopg://app:password@database:5432/classswap?sslmode=require"
        ),
    }
    config.update(overrides)
    return Settings(**config)


def test_security_headers_and_csp_nonce_are_present() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/login")

    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    script_policy = next(part for part in csp.split(";") if part.strip().startswith("script-src"))
    style_policy = next(part for part in csp.split(";") if part.strip().startswith("style-src"))
    assert "'nonce-" in script_policy
    assert "'nonce-" in style_policy
    assert "'unsafe-inline'" not in csp
    assert "'unsafe-eval'" not in csp
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
    assert "nonce=" in response.text
    assert "integrity=\"sha384-" in response.text
    assert "fonts.googleapis.com" not in response.text
    assert "onclick=" not in response.text


def test_templates_use_nonce_styles_without_inline_style_attributes() -> None:
    templates_dir = Path(__file__).parent.parent / "app" / "templates"

    for template in templates_dir.glob("*.html"):
        content = template.read_text(encoding="utf-8")
        assert re.search(r"\sstyle\s*=", content, re.IGNORECASE) is None, template.name
        assert re.search(r"<style(?![^>]*\bnonce=)", content, re.IGNORECASE) is None, template.name


def test_authenticated_responses_are_not_cached() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        response = client.get(
            "/health",
            headers={"Cookie": "__Host-classswap_session=invalid"},
        )

    assert response.headers["cache-control"] == "no-store"


def test_production_responses_include_hsts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/health")

    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


def test_unknown_cors_origin_is_rejected() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_untrusted_host_is_rejected() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/health", headers={"Host": "attacker.example"})

    assert response.status_code == 400


def test_production_settings_require_hardened_transport_and_database() -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        _production_settings(DATABASE_URL="sqlite:///unsafe.db")
    with pytest.raises(ValueError, match="DEBUG=false"):
        _production_settings(DEBUG=True)
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        _production_settings(LOG_LEVEL="DEBUG")
    with pytest.raises(ValueError, match="wildcard"):
        Settings(
            _env_file=None,
            ENV="development",
            CORS_ALLOWED_ORIGINS="*",
        )


def test_production_disables_api_documentation() -> None:
    production_app = FastAPI(**api_docs_urls("production"))

    with TestClient(production_app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_production_database_requires_ssl_and_non_local_host() -> None:
    with pytest.raises(ValueError, match="sslmode=require"):
        _production_settings(
            DATABASE_URL="postgresql+psycopg://app:password@database/classswap"
        )
    with pytest.raises(ValueError, match="ALLOWED_HOSTS"):
        _production_settings(ALLOWED_HOSTS="localhost,127.0.0.1")
