from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://classswap:classswap@localhost:5432/classswap"
    jwt_secret_key: str = "local-development-only"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    max_period: int = 7
    break_after: str = "2,4"
    subject_match_weight: float = 0.35
    adjacent_free_weight: float = 0.25
    fairness_weight: float = 0.20
    same_semester_weight: float = 0.12
    same_department_weight: float = 0.08

    @property
    def break_periods(self) -> tuple[int, ...]:
        return tuple(int(period.strip()) for period in self.break_after.split(",") if period.strip())


settings = Settings()
