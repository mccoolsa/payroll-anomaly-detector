"""Isolation Forest training, scoring, persistence, and time-aware evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from app.features import MODEL_FEATURE_COLUMNS
from database.models import AnomalyLabel


@dataclass(frozen=True)
class ModelMetrics:
    split_date: str
    threshold: float
    precision: float
    recall: float
    f1: float
    precision_at_k: float
    recall_at_k: float
    top_k: int
    flagged_records: int
    evaluation_records: int

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            key: round(value, 4) if isinstance(value, float) else value
            for key, value in vars(self).items()
        }


class IsolationForestDetector:
    """Versioned unsupervised detector over the documented feature set."""

    version = "isolation-forest-1.0"

    def __init__(
        self,
        *,
        contamination: float = 0.02,
        random_state: int = 42,
        n_estimators: int = 300,
    ) -> None:
        self.contamination = contamination
        self.random_state = random_state
        self.n_estimators = n_estimators
        self.pipeline = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    IsolationForest(
                        n_estimators=n_estimators,
                        contamination=contamination,
                        random_state=random_state,
                        n_jobs=1,
                    ),
                ),
            ]
        )
        self.score_floor_: float | None = None
        self.score_ceiling_: float | None = None
        self.raw_threshold_: float | None = None
        self.feature_reference_: dict[str, dict[str, float]] = {}

    def fit(self, features: pd.DataFrame) -> IsolationForestDetector:
        matrix = features[MODEL_FEATURE_COLUMNS]
        self.pipeline.fit(matrix)
        raw_scores = -self.pipeline.decision_function(matrix)
        self.score_floor_ = float(np.quantile(raw_scores, 0.05))
        self.score_ceiling_ = float(np.quantile(raw_scores, 0.995))
        self.raw_threshold_ = float(np.quantile(raw_scores, 1 - self.contamination))
        self.feature_reference_ = {
            column: {
                "median": float(matrix[column].median()),
                "q1": float(matrix[column].quantile(0.25)),
                "q3": float(matrix[column].quantile(0.75)),
            }
            for column in MODEL_FEATURE_COLUMNS
        }
        return self

    def score(self, features: pd.DataFrame) -> pd.DataFrame:
        if self.raw_threshold_ is None or self.score_floor_ is None or self.score_ceiling_ is None:
            raise RuntimeError("The detector must be fitted before scoring")
        raw_scores = -self.pipeline.decision_function(features[MODEL_FEATURE_COLUMNS])
        denominator = max(self.score_ceiling_ - self.score_floor_, 1e-9)
        risk_scores = np.clip((raw_scores - self.score_floor_) / denominator, 0, 1)
        return pd.DataFrame(
            {
                "payment_id": features["payment_id"].to_numpy(),
                "raw_anomaly_score": raw_scores,
                "model_risk_score": risk_scores,
                "model_flagged": raw_scores >= self.raw_threshold_,
            }
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: Path) -> IsolationForestDetector:
        detector = joblib.load(path)
        if not isinstance(detector, IsolationForestDetector):
            raise TypeError("Artifact is not an IsolationForestDetector")
        return detector


def train_time_aware(
    features: pd.DataFrame,
    labels: list[AnomalyLabel],
    *,
    contamination: float = 0.02,
    random_state: int = 42,
    train_fraction: float = 0.70,
) -> tuple[IsolationForestDetector, pd.DataFrame, ModelMetrics]:
    """Train on earlier periods and evaluate only on later periods."""

    dates = sorted(features["payment_date"].drop_duplicates())
    split_index = min(max(int(len(dates) * train_fraction), 1), len(dates) - 1)
    split_date = pd.Timestamp(dates[split_index])
    labelled_ids = {label.payment_id for label in labels}
    training = features[
        (features["payment_date"] < split_date) & ~features["payment_id"].isin(labelled_ids)
    ]
    evaluation = features[features["payment_date"] >= split_date]

    detector = IsolationForestDetector(
        contamination=contamination,
        random_state=random_state,
    ).fit(training)
    scores = detector.score(evaluation)
    metrics = evaluate_model_scores(scores, labels, split_date=split_date)
    return detector, scores, metrics


def evaluate_model_scores(
    scores: pd.DataFrame,
    labels: list[AnomalyLabel],
    *,
    split_date: pd.Timestamp,
) -> ModelMetrics:
    actual_ids = {label.payment_id for label in labels}
    predicted_ids = set(scores.loc[scores["model_flagged"], "payment_id"])
    evaluation_ids = set(scores["payment_id"])
    actual_ids &= evaluation_ids
    true_positives = len(predicted_ids & actual_ids)
    precision = _ratio(true_positives, len(predicted_ids))
    recall = _ratio(true_positives, len(actual_ids))
    f1 = _ratio(2 * precision * recall, precision + recall)

    top_k = min(max(len(actual_ids) * 2, 10), len(scores))
    top_ids = set(scores.nlargest(top_k, "model_risk_score")["payment_id"])
    top_true_positives = len(top_ids & actual_ids)
    return ModelMetrics(
        split_date=split_date.date().isoformat(),
        threshold=float(scores.loc[scores["model_flagged"], "raw_anomaly_score"].min())
        if predicted_ids
        else 0.0,
        precision=precision,
        recall=recall,
        f1=f1,
        precision_at_k=_ratio(top_true_positives, top_k),
        recall_at_k=_ratio(top_true_positives, len(actual_ids)),
        top_k=top_k,
        flagged_records=len(predicted_ids),
        evaluation_records=len(scores),
    )


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
