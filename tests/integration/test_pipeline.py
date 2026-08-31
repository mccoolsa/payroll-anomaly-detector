"""End-to-end persistence test for the hybrid detection pipeline."""

from pathlib import Path

from sqlalchemy.orm import Session

from app.services.pipeline import run_pipeline
from data_generation import GenerationConfig, SyntheticPayrollGenerator
from database.enums import AlertSource
from database.models import AnomalyAlert, ModelRun


def test_pipeline_persists_versioned_explainable_alerts(
    db_session: Session,
    tmp_path: Path,
) -> None:
    dataset = SyntheticPayrollGenerator(
        GenerationConfig(employee_count=50, month_count=9, seed=43, anomalies_per_type=1)
    ).generate()
    result = run_pipeline(
        dataset,
        db_session,
        artifact_path=tmp_path / "model.joblib",
        random_state=43,
    )
    db_session.commit()

    assert db_session.query(ModelRun).count() == 1
    assert db_session.query(AnomalyAlert).count() == len(result.alerts)
    assert len(result.alerts) >= len(dataset.labels)
    assert any(alert.source == AlertSource.HYBRID for alert in result.alerts)
    assert all(alert.evidence["versions"]["hybrid"] == "hybrid-1.0" for alert in result.alerts)
    assert all(alert.summary for alert in result.alerts)
