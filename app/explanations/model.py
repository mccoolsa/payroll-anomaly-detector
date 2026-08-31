"""Translate unusual model features into evidence-based review reasons."""

from typing import Any

import pandas as pd

FEATURE_LABELS = {
    "gross_change_ratio": "gross pay compared with recent employee history",
    "gross_peer_ratio": "gross pay compared with role-grade peers",
    "deduction_ratio": "total deductions as a share of gross pay",
    "other_deduction_ratio": "other deductions as a share of gross pay",
    "net_gross_ratio": "net pay as a share of gross pay",
    "payment_count_in_run": "number of payments for the employee in this run",
    "bank_change_recency_score": "recency of the destination bank change",
    "post_termination_indicator": "payment after the recorded termination date",
    "historical_pay_volatility": "recent variation in employee gross pay",
}


def explain_model_features(
    feature_row: pd.Series,
    reference: dict[str, dict[str, float]],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Rank robust deviations and return plain-language evidence."""

    deviations = []
    for feature, statistics in reference.items():
        value = float(feature_row[feature])
        centre = statistics["median"]
        spread = statistics["q3"] - statistics["q1"]
        scale = max(spread, abs(centre) * 0.10, 0.01)
        deviation = abs(value - centre) / scale
        deviations.append((deviation, feature, value, centre))

    reasons = []
    for deviation, feature, value, centre in sorted(deviations, reverse=True)[:limit]:
        reasons.append(
            {
                "feature": feature,
                "label": FEATURE_LABELS[feature],
                "value": round(value, 4),
                "training_median": round(centre, 4),
                "robust_deviation": round(deviation, 2),
                "explanation": _format_explanation(feature, value, centre),
            }
        )
    return reasons


def _format_explanation(feature: str, value: float, centre: float) -> str:
    if feature == "gross_change_ratio":
        return f"Gross pay is {value:.2f}× the employee's recent median."
    if feature == "gross_peer_ratio":
        return f"Gross pay is {value:.2f}× the median for comparable role-grade peers."
    if feature == "deduction_ratio":
        return f"Total deductions are {value:.1%} of gross pay."
    if feature == "other_deduction_ratio":
        return f"Other deductions are {value:.1%} of gross pay."
    if feature == "net_gross_ratio":
        return f"Net pay is {value:.1%} of gross pay."
    if feature == "payment_count_in_run":
        return f"The employee has {value:.0f} payments in this payroll run."
    if feature == "bank_change_recency_score":
        return "The destination bank change is unusually close to the payment date."
    if feature == "post_termination_indicator":
        return "The payment date falls after the recorded employment termination."
    direction = "above" if value >= centre else "below"
    return f"{FEATURE_LABELS[feature].capitalize()} is {direction} the training median."
