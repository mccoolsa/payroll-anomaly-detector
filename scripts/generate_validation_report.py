"""Generate reproducible evaluation and segment-QA artefacts."""

import json
from pathlib import Path

from app.detection import DetectionContext, RuleEngine, evaluate_findings, train_time_aware
from app.features import PayrollFeatureBuilder
from app.services import HybridAlertService
from app.validation import segment_alert_rates, summarise_segment_rates
from data_generation import GenerationConfig, SyntheticPayrollGenerator


def main() -> None:
    output_directory = Path("reports")
    output_directory.mkdir(parents=True, exist_ok=True)
    dataset = SyntheticPayrollGenerator(GenerationConfig()).generate()
    context = DetectionContext(
        dataset.payments,
        dataset.employees,
        dataset.payroll_runs,
        dataset.bank_accounts,
    )
    features = PayrollFeatureBuilder().build(context)
    rule_findings = RuleEngine().detect(context)
    rule_metrics = evaluate_findings(rule_findings, dataset.labels)
    detector, model_scores, model_metrics = train_time_aware(features, dataset.labels)
    candidates = HybridAlertService().build_candidates(
        rule_findings=rule_findings,
        model_scores=model_scores,
        features=features,
        detector=detector,
    )
    segment_report = segment_alert_rates(
        features,
        candidates,
        dataset.labels,
        dataset.employees,
    )
    segment_report.to_csv(output_directory / "segment-alert-rates.csv", index=False)
    evaluation = {
        "dataset": dataset.summary,
        "rule_baseline": rule_metrics.as_dict(),
        "isolation_forest": model_metrics.as_dict(),
        "hybrid_alerts": len(candidates),
        "segment_summary": summarise_segment_rates(segment_report),
        "caveat": (
            "Segment results use synthetic operational attributes and do not establish "
            "fairness for a real workforce."
        ),
    }
    (output_directory / "evaluation-metrics.json").write_text(
        json.dumps(evaluation, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(evaluation, indent=2))


if __name__ == "__main__":
    main()
