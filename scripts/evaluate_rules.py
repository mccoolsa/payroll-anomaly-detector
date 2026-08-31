"""Evaluate deterministic controls against synthetic hidden labels."""

import json

from app.detection import DetectionContext, RuleEngine, evaluate_findings
from data_generation import GenerationConfig, SyntheticPayrollGenerator


def main() -> None:
    dataset = SyntheticPayrollGenerator(GenerationConfig()).generate()
    context = DetectionContext(
        dataset.payments,
        dataset.employees,
        dataset.payroll_runs,
        dataset.bank_accounts,
    )
    findings = RuleEngine().detect(context)
    metrics = evaluate_findings(findings, dataset.labels)
    print(json.dumps(metrics.as_dict(), indent=2))


if __name__ == "__main__":
    main()
