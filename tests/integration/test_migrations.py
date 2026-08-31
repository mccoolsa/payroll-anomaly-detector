"""Verify the migration chain against a fresh relational database."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.config import get_settings


def test_migrations_upgrade_and_downgrade(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "migration_test.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("PAYROLL_DATABASE_URL", database_url)
    get_settings.cache_clear()

    config = Config("alembic.ini")
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    table_names = set(inspect(engine).get_table_names())
    assert {
        "employees",
        "payments",
        "payroll_runs",
        "anomaly_alerts",
        "investigations",
    }.issubset(table_names)

    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    engine.dispose()
    get_settings.cache_clear()
