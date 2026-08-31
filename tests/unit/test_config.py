"""Tests for environment-based application configuration."""

from app.config import Settings


def test_settings_have_safe_development_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.app_title == "Payroll Anomaly Detector"
    assert settings.log_level == "INFO"
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_settings_can_be_overridden_by_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PAYROLL_ENVIRONMENT", "test")
    monkeypatch.setenv("PAYROLL_APP_TITLE", "Test Payroll App")

    settings = Settings(_env_file=None)

    assert settings.environment == "test"
    assert settings.app_title == "Test Payroll App"
