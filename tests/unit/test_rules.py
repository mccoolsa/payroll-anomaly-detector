"""Rule engine coverage over all injected anomaly categories."""

from collections import Counter

from app.detection import DetectionContext, RuleEngine, evaluate_findings
from data_generation import GenerationConfig, SyntheticPayrollGenerator
from database.enums import AnomalyType


def generate_findings():
    dataset = SyntheticPayrollGenerator(
        GenerationConfig(employee_count=50, month_count=9, seed=21, anomalies_per_type=2)
    ).generate()
    context = DetectionContext(
        dataset.payments,
        dataset.employees,
        dataset.payroll_runs,
        dataset.bank_accounts,
    )
    return dataset, RuleEngine().detect(context)


def test_rule_engine_detects_every_injected_category() -> None:
    _, findings = generate_findings()
    counts = Counter(finding.anomaly_type for finding in findings)

    assert all(counts[anomaly_type] >= 2 for anomaly_type in AnomalyType)
    assert all(finding.summary and finding.evidence for finding in findings)
    assert all(0 <= finding.risk_score <= 1 for finding in findings)


def test_rule_baseline_has_complete_recall_and_high_precision() -> None:
    dataset, findings = generate_findings()
    metrics = evaluate_findings(findings, dataset.labels)

    assert metrics.recall == 1.0
    assert metrics.precision >= 0.90
    assert set(metrics.recall_by_type.values()) == {1.0}
