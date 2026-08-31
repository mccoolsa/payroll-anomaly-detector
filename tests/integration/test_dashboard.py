"""Smoke test the populated Streamlit investigation workflow."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from streamlit.testing.v1 import AppTest

from app.config import get_settings
from app.services.pipeline import run_pipeline
from data_generation import GenerationConfig, SyntheticPayrollGenerator
from database.base import Base


def test_dashboard_renders_populated_alert_queue(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "dashboard.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    dataset = SyntheticPayrollGenerator(
        GenerationConfig(employee_count=30, month_count=7, seed=47, anomalies_per_type=1)
    ).generate()
    with Session(engine) as session:
        run_pipeline(
            dataset,
            session,
            artifact_path=tmp_path / "dashboard-model.joblib",
            random_state=47,
        )
        session.commit()
    monkeypatch.setenv("PAYROLL_DATABASE_URL", database_url)
    get_settings.cache_clear()

    dashboard_path = Path(__file__).parents[2] / "app" / "dashboard" / "main.py"
    app = AppTest.from_file(dashboard_path).run(timeout=20)

    assert not app.exception
    assert app.title[0].value == "Payroll Anomaly Detector"
    assert any(subheader.value == "Prioritised alert queue" for subheader in app.subheader)
    assert len(app.metric) == 4
    assert any("Why this alert exists" in markdown.value for markdown in app.markdown)
    engine.dispose()
    get_settings.cache_clear()
