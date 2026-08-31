"""Responsible-AI segment validation tests."""

from app.detection import DetectionContext, RuleEngine, train_time_aware
from app.features import PayrollFeatureBuilder
from app.services import HybridAlertService
from app.validation import segment_alert_rates, summarise_segment_rates
from data_generation import GenerationConfig, SyntheticPayrollGenerator


def test_segment_report_covers_operational_dimensions() -> None:
    dataset = SyntheticPayrollGenerator(
        GenerationConfig(employee_count=50, month_count=9, seed=53, anomalies_per_type=1)
    ).generate()
    context = DetectionContext(
        dataset.payments,
        dataset.employees,
        dataset.payroll_runs,
        dataset.bank_accounts,
    )
    features = PayrollFeatureBuilder().build(context)
    detector, scores, _ = train_time_aware(features, dataset.labels, random_state=53)
    candidates = HybridAlertService().build_candidates(
        rule_findings=RuleEngine().detect(context),
        model_scores=scores,
        features=features,
        detector=detector,
    )

    report = segment_alert_rates(features, candidates, dataset.labels, dataset.employees)
    summary = summarise_segment_rates(report)

    assert set(report["dimension"]) == {"department", "location", "job_grade"}
    assert report["alert_rate"].between(0, 1).all()
    assert report["false_positive_rate"].between(0, 1).all()
    assert set(summary) == {"department", "location", "job_grade"}
