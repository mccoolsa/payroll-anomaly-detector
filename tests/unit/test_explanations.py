"""Model explanation tests."""

import pandas as pd

from app.explanations import explain_model_features
from app.features import MODEL_FEATURE_COLUMNS


def test_model_explanations_are_ranked_and_plain_language() -> None:
    row = pd.Series({feature: 1.0 for feature in MODEL_FEATURE_COLUMNS})
    row["gross_change_ratio"] = 2.0
    reference = {
        feature: {"median": 1.0, "q1": 0.95, "q3": 1.05} for feature in MODEL_FEATURE_COLUMNS
    }

    reasons = explain_model_features(row, reference, limit=2)

    assert reasons[0]["feature"] == "gross_change_ratio"
    assert "recent median" in reasons[0]["explanation"]
    assert len(reasons) == 2
