import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "ClassSwap"
    TAGLINE: str = "Smart Substitutions. Zero Idle Hours."
    VERSION: str = "1.0.0"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "classswap-super-secret-production-key-2026-xyz-secure")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # SQLite default, easily overridable by DATABASE_URL env var for PostgreSQL
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./classswap.db")
    COLLEGE_NAME: str = os.getenv("COLLEGE_NAME", "Apex Institute of Science & Technology")
    PERIOD_DURATION_MINUTES: int = 50

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
