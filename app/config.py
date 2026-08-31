"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration shared by application components."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PAYROLL_",
        extra="ignore",
    )

    environment: str = "development"
    app_title: str = "Payroll Anomaly Detector"
    log_level: str = "INFO"
    random_seed: int = 42
    model_artifact_path: str = "models/isolation_forest.joblib"
    database_url: str = Field(
        default="postgresql+psycopg://payroll:payroll@localhost:5432/payroll",
        repr=False,
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings object for the current process."""

    return Settings()
