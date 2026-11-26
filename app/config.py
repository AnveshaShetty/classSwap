from typing import Literal
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.exc import ArgumentError
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    environment: Literal["development", "production", "test"] = Field(
        default="development",
        validation_alias="ENV",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    debug: bool = False
    database_url: str = "postgresql+psycopg://classswap:classswap@localhost:5432/classswap"
    jwt_secret_key: str = ""
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = 30
    auth_cookie_name: str = "__Host-classswap_session"
    cookie_secure: bool = True
    app_base_url: str = "http://localhost:8000"
    allowed_hosts: str = ""
    cors_allowed_origins: str = ""
    trusted_proxy_ips: str = Field(default="127.0.0.1", validation_alias="FORWARDED_ALLOW_IPS")
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_address: str = "ClassSwap <no-reply@classswap.local>"
    totp_encryption_key: str = ""
    max_period: int = 7
    break_after: str = "2,4"
    subject_match_weight: float = 0.35
    adjacent_free_weight: float = 0.25
    fairness_weight: float = 0.20
    same_semester_weight: float = 0.12
    same_department_weight: float = 0.08

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if not 1 <= self.access_token_expire_minutes <= 30:
            raise ValueError("Access tokens must expire within 30 minutes.")
        if self.auth_cookie_name.startswith("__Host-") and not self.cookie_secure:
            raise ValueError("__Host- authentication cookies require Secure.")
        if "*" in self.allowed_host_list:
            raise ValueError("ALLOWED_HOSTS cannot contain a wildcard.")
        if "*" in self.cors_origin_list:
            raise ValueError("CORS_ALLOWED_ORIGINS cannot contain a wildcard.")
        if "*" in self.trusted_proxy_list:
            raise ValueError("FORWARDED_ALLOW_IPS cannot contain a wildcard.")
        for origin in self.cors_origin_list:
            parsed_origin = urlsplit(origin)
            if (
                parsed_origin.scheme not in {"http", "https"}
                or not parsed_origin.netloc
                or parsed_origin.path
                or parsed_origin.query
                or parsed_origin.fragment
                or parsed_origin.username is not None
                or parsed_origin.password is not None
            ):
                raise ValueError("CORS_ALLOWED_ORIGINS must contain only explicit origins.")
        if self.environment == "production":
            if self.log_level == "DEBUG":
                raise ValueError("Production requires LOG_LEVEL to be INFO or higher.")
            secret = self.jwt_secret_key
            placeholders = (
                "replace-this",
                "replace-with",
                "change-me",
                "your-secret",
                "development-secret",
                "local-development",
            )
            if len(secret.encode("utf-8")) < 32 or any(
                marker in secret.lower() for marker in placeholders
            ):
                raise ValueError(
                    "Production requires a non-placeholder JWT_SECRET_KEY of at least 32 bytes."
                )
            if not self.cookie_secure:
                raise ValueError("Production requires Secure authentication cookies.")
            if not self.auth_cookie_name.startswith("__Host-"):
                raise ValueError("Production authentication cookies must use the __Host- prefix.")
            if not self.smtp_host:
                raise ValueError("Production requires SMTP_HOST for password-reset delivery.")
            if not self.app_base_url.startswith("https://"):
                raise ValueError("Production requires an HTTPS APP_BASE_URL.")
            if self.debug:
                raise ValueError("Production requires DEBUG=false.")
            local_hosts = {"localhost", "127.0.0.1", "::1", "testserver"}
            if not self.allowed_host_list or all(
                host.lower() in local_hosts for host in self.allowed_host_list
            ):
                raise ValueError("Production requires an explicit ALLOWED_HOSTS list.")
            try:
                database = make_url(self.database_url)
            except (ArgumentError, TypeError, ValueError) as error:
                raise ValueError("Production requires a valid PostgreSQL DATABASE_URL.") from error
            if database.get_backend_name() != "postgresql":
                raise ValueError("Production requires PostgreSQL; SQLite is not supported.")
            if database.query.get("sslmode") != "require":
                raise ValueError("Production PostgreSQL connections require sslmode=require.")
            try:
                Fernet(self.totp_encryption_key.encode("ascii"))
            except (UnicodeEncodeError, ValueError, TypeError) as error:
                raise ValueError("Production requires a valid TOTP_ENCRYPTION_KEY.") from error
        return self

    @property
    def allowed_host_list(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def trusted_proxy_list(self) -> list[str]:
        return [proxy.strip() for proxy in self.trusted_proxy_ips.split(",") if proxy.strip()]

    @property
    def break_periods(self) -> tuple[int, ...]:
        return tuple(int(period.strip()) for period in self.break_after.split(",") if period.strip())


settings = Settings()
