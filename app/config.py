from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    database_url: str = "postgresql+psycopg://classswap:classswap@localhost:5432/classswap"
    jwt_secret_key: str = ""
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = 30
    auth_cookie_name: str = "__Host-classswap_session"
    cookie_secure: bool = True
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
        if self.environment == "production":
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
        return self

    @property
    def break_periods(self) -> tuple[int, ...]:
        return tuple(int(period.strip()) for period in self.break_after.split(",") if period.strip())


settings = Settings()
