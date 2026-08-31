"""End-to-end generation, detection, alerting, and persistence orchestration."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.detection import DetectionContext, RuleEngine, train_time_aware
from app.detection.model import ModelMetrics
from app.features import PayrollFeatureBuilder
from app.services.alerts import HybridAlertService
from data_generation.generator import GeneratedDataset
from database.models import AnomalyAlert, ModelRun


@dataclass
class PipelineResult:
    features: pd.DataFrame
    model_metrics: ModelMetrics
    model_run: ModelRun
    alerts: list[AnomalyAlert]


def run_pipeline(
    dataset: GeneratedDataset,
    session: Session,
    *,
    artifact_path: Path,
    random_state: int = 42,
) -> PipelineResult:
    dataset.persist(session)
    context = DetectionContext(
        dataset.payments,
        dataset.employees,
        dataset.payroll_runs,
        dataset.bank_accounts,
    )
    features = PayrollFeatureBuilder().build(context)
    rule_findings = RuleEngine().detect(context)
    detector, model_scores, metrics = train_time_aware(
        features,
        dataset.labels,
        random_state=random_state,
    )
    detector.save(artifact_path)
    alert_service = HybridAlertService()
    candidates = alert_service.build_candidates(
        rule_findings=rule_findings,
        model_scores=model_scores,
        features=features,
        detector=detector,
    )
    model_run, alerts = alert_service.persist(
        session,
        candidates=candidates,
        detector=detector,
        metrics=metrics,
        features=features,
        artifact_path=artifact_path,
    )
    session.flush()
    return PipelineResult(features, metrics, model_run, alerts)
