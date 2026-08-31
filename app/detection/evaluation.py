"""Evaluate findings against labels kept outside the detection pipeline."""

from dataclasses import dataclass

from app.detection.rules import RuleFinding
from database.enums import AnomalyType
from database.models import AnomalyLabel


@dataclass(frozen=True)
class DetectionMetrics:
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int
    recall_by_type: dict[str, float]

    def as_dict(self) -> dict[str, float | int | dict[str, float]]:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "recall_by_type": self.recall_by_type,
        }


def evaluate_findings(
    findings: list[RuleFinding],
    labels: list[AnomalyLabel],
) -> DetectionMetrics:
    predicted = {(finding.payment_id, finding.anomaly_type) for finding in findings}
    actual = {(label.payment_id, label.anomaly_type) for label in labels}
    true_positives = len(predicted & actual)
    false_positives = len(predicted - actual)
    false_negatives = len(actual - predicted)
    precision = _safe_ratio(true_positives, true_positives + false_positives)
    recall = _safe_ratio(true_positives, true_positives + false_negatives)
    f1 = _safe_ratio(2 * precision * recall, precision + recall)

    recall_by_type = {}
    for anomaly_type in AnomalyType:
        actual_type = {item for item in actual if item[1] == anomaly_type}
        detected_type = actual_type & predicted
        recall_by_type[anomaly_type.value] = round(
            _safe_ratio(len(detected_type), len(actual_type)),
            4,
        )

    return DetectionMetrics(
        precision,
        recall,
        f1,
        true_positives,
        false_positives,
        false_negatives,
        recall_by_type,
    )


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
