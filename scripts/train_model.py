"""Train and evaluate the Isolation Forest on a reproducible dataset."""

import json
from pathlib import Path

from app.detection import DetectionContext, train_time_aware
from app.features import PayrollFeatureBuilder
from data_generation import GenerationConfig, SyntheticPayrollGenerator


def main() -> None:
    dataset = SyntheticPayrollGenerator(GenerationConfig()).generate()
    context = DetectionContext(
        dataset.payments,
        dataset.employees,
        dataset.payroll_runs,
        dataset.bank_accounts,
    )
    features = PayrollFeatureBuilder().build(context)
    detector, _, metrics = train_time_aware(features, dataset.labels)
    artifact_path = Path("models/isolation_forest.joblib")
    detector.save(artifact_path)
    print(json.dumps({"artifact": str(artifact_path), **metrics.as_dict()}, indent=2))


if __name__ == "__main__":
    main()
