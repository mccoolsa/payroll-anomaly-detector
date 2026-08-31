"""Segment-level QA for alert burden and synthetic evaluation outcomes."""

from collections.abc import Iterable

import pandas as pd

from app.services import HybridAlertCandidate
from database.models import AnomalyLabel, Employee


def segment_alert_rates(
    features: pd.DataFrame,
    candidates: list[HybridAlertCandidate],
    labels: list[AnomalyLabel],
    employees: Iterable[Employee],
) -> pd.DataFrame:
    """Measure alert and false-positive rates across operational segments."""

    metadata = pd.DataFrame(
        [
            {
                "employee_id": employee.id,
                "department": employee.department,
                "location": employee.location,
                "job_grade": employee.job_grade,
            }
            for employee in employees
        ]
    )
    frame = features[["payment_id", "employee_id"]].merge(
        metadata,
        on="employee_id",
        how="left",
        validate="many_to_one",
    )
    alerted_ids = {candidate.payment_id for candidate in candidates}
    labelled_ids = {label.payment_id for label in labels}
    frame["alerted"] = frame["payment_id"].isin(alerted_ids)
    frame["labelled_anomaly"] = frame["payment_id"].isin(labelled_ids)
    frame["false_positive"] = frame["alerted"] & ~frame["labelled_anomaly"]

    rows = []
    for dimension in ("department", "location", "job_grade"):
        for segment, group in frame.groupby(dimension):
            anomaly_count = int(group["labelled_anomaly"].sum())
            normal_count = len(group) - anomaly_count
            detected_anomalies = int((group["alerted"] & group["labelled_anomaly"]).sum())
            rows.append(
                {
                    "dimension": dimension,
                    "segment": segment,
                    "records": len(group),
                    "alerts": int(group["alerted"].sum()),
                    "labelled_anomalies": anomaly_count,
                    "alert_rate": float(group["alerted"].mean()),
                    "false_positive_rate": _ratio(
                        int(group["false_positive"].sum()),
                        normal_count,
                    ),
                    "anomaly_recall": _ratio(detected_anomalies, anomaly_count),
                }
            )
    return pd.DataFrame(rows).sort_values(["dimension", "segment"]).reset_index(drop=True)


def summarise_segment_rates(report: pd.DataFrame) -> dict[str, dict[str, float | str]]:
    """Summarise alert-rate ranges without asserting real-world fairness."""

    summary = {}
    for dimension, group in report.groupby("dimension"):
        highest = group.loc[group["alert_rate"].idxmax()]
        lowest = group.loc[group["alert_rate"].idxmin()]
        summary[dimension] = {
            "highest_alert_segment": str(highest["segment"]),
            "highest_alert_rate": round(float(highest["alert_rate"]), 4),
            "lowest_alert_segment": str(lowest["segment"]),
            "lowest_alert_rate": round(float(lowest["alert_rate"]), 4),
            "max_false_positive_rate": round(float(group["false_positive_rate"].max()), 4),
        }
    return summary


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
