"""Isolation Forest training, evaluation, and artifact tests."""

from pathlib import Path

from app.detection import DetectionContext, IsolationForestDetector, train_time_aware
from app.features import PayrollFeatureBuilder
from data_generation import GenerationConfig, SyntheticPayrollGenerator


def training_fixture():
    dataset = SyntheticPayrollGenerator(
        GenerationConfig(employee_count=80, month_count=12, seed=37, anomalies_per_type=2)
    ).generate()
    context = DetectionContext(
        dataset.payments,
        dataset.employees,
        dataset.payroll_runs,
        dataset.bank_accounts,
    )
    features = PayrollFeatureBuilder().build(context)
    return dataset, features


def test_time_aware_model_prioritises_injected_anomalies() -> None:
    dataset, features = training_fixture()
    _, scores, metrics = train_time_aware(
        features,
        dataset.labels,
        contamination=0.04,
        random_state=37,
    )

    labelled_ids = {label.payment_id for label in dataset.labels}
    anomaly_mean = scores.loc[
        scores["payment_id"].isin(labelled_ids),
        "model_risk_score",
    ].mean()
    normal_mean = scores.loc[
        ~scores["payment_id"].isin(labelled_ids),
        "model_risk_score",
    ].mean()

    assert anomaly_mean > normal_mean
    assert metrics.recall_at_k >= 0.30
    assert metrics.evaluation_records > 0


def test_model_artifact_round_trip(tmp_path: Path) -> None:
    dataset, features = training_fixture()
    detector, scores, _ = train_time_aware(features, dataset.labels, random_state=37)
    artifact_path = tmp_path / "detector.joblib"

    detector.save(artifact_path)
    loaded = IsolationForestDetector.load(artifact_path)
    loaded_scores = loaded.score(features[features["payment_id"].isin(scores["payment_id"])])

    assert loaded.version == detector.version
    assert loaded_scores["model_flagged"].tolist() == scores["model_flagged"].tolist()
