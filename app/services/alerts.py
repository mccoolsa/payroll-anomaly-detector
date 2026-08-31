"""Combine rule and model signals into one auditable alert per payment."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from math import prod
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.detection.model import IsolationForestDetector, ModelMetrics
from app.detection.rules import RuleFinding
from app.explanations import explain_model_features
from app.features import MODEL_FEATURE_COLUMNS, PayrollFeatureBuilder
from database.enums import AlertSource, AlertStatus, RiskLevel
from database.models import AnomalyAlert, ModelRun


@dataclass(frozen=True)
class HybridAlertCandidate:
    payment_id: str
    source: AlertSource
    risk_score: float
    risk_level: RiskLevel
    summary: str
    rule_codes: tuple[str, ...]
    evidence: dict[str, Any]


class HybridAlertService:
    """Merge independent signals and preserve their original evidence."""

    version = "hybrid-1.0"

    def build_candidates(
        self,
        *,
        rule_findings: list[RuleFinding],
        model_scores: pd.DataFrame,
        features: pd.DataFrame,
        detector: IsolationForestDetector,
    ) -> list[HybridAlertCandidate]:
        rules_by_payment: dict[str, list[RuleFinding]] = defaultdict(list)
        for finding in rule_findings:
            rules_by_payment[finding.payment_id].append(finding)
        scores_by_payment = model_scores.set_index("payment_id").to_dict("index")
        features_by_payment = features.set_index("payment_id")
        payment_ids = set(rules_by_payment)
        payment_ids.update(
            model_scores.loc[model_scores["model_flagged"], "payment_id"].astype(str)
        )

        candidates = []
        for payment_id in payment_ids:
            rules = sorted(
                rules_by_payment.get(payment_id, []),
                key=lambda finding: finding.risk_score,
                reverse=True,
            )
            model = scores_by_payment.get(payment_id)
            model_flagged = bool(model and model["model_flagged"])
            source = (
                AlertSource.HYBRID
                if rules and model_flagged
                else AlertSource.RULE
                if rules
                else AlertSource.MODEL
            )
            signals = [finding.risk_score for finding in rules]
            if model_flagged:
                signals.append(float(model["model_risk_score"]) * 0.75)
            risk_score = min(0.999, 1 - prod(1 - signal for signal in signals))
            model_reasons = (
                explain_model_features(
                    features_by_payment.loc[payment_id],
                    detector.feature_reference_,
                )
                if model is not None and payment_id in features_by_payment.index
                else []
            )
            summary = (
                rules[0].summary
                if rules
                else model_reasons[0]["explanation"]
                if model_reasons
                else "Unusual combination of payroll values requires review."
            )
            candidates.append(
                HybridAlertCandidate(
                    payment_id=payment_id,
                    source=source,
                    risk_score=risk_score,
                    risk_level=self._risk_level(risk_score),
                    summary=summary,
                    rule_codes=tuple(finding.rule_code for finding in rules),
                    evidence={
                        "rule_findings": [
                            {
                                "rule_code": finding.rule_code,
                                "summary": finding.summary,
                                "risk_score": round(finding.risk_score, 4),
                                "evidence": finding.evidence,
                            }
                            for finding in rules
                        ],
                        "model": {
                            "flagged": model_flagged,
                            "risk_score": round(float(model["model_risk_score"]), 4)
                            if model
                            else None,
                            "raw_score": round(float(model["raw_anomaly_score"]), 6)
                            if model
                            else None,
                            "reasons": model_reasons,
                        },
                        "versions": {
                            "hybrid": self.version,
                            "features": PayrollFeatureBuilder.version,
                            "model": detector.version,
                        },
                    },
                )
            )
        return sorted(candidates, key=lambda candidate: -candidate.risk_score)

    def persist(
        self,
        session: Session,
        *,
        candidates: list[HybridAlertCandidate],
        detector: IsolationForestDetector,
        metrics: ModelMetrics,
        features: pd.DataFrame,
        artifact_path: Path,
    ) -> tuple[ModelRun, list[AnomalyAlert]]:
        split_date = pd.Timestamp(metrics.split_date).date()
        model_run = ModelRun(
            model_name="Isolation Forest",
            model_version=detector.version,
            training_period_start=features["payment_date"].min().date(),
            training_period_end=split_date - timedelta(days=1),
            feature_names=MODEL_FEATURE_COLUMNS,
            parameters={
                "contamination": detector.contamination,
                "random_state": detector.random_state,
                "n_estimators": detector.n_estimators,
            },
            metrics=metrics.as_dict(),
            artifact_path=str(artifact_path),
        )
        session.add(model_run)
        session.flush()

        alerts = [
            AnomalyAlert(
                payment_id=candidate.payment_id,
                model_run_id=model_run.id,
                source=candidate.source,
                rule_code=",".join(candidate.rule_codes) or None,
                risk_score=candidate.risk_score,
                risk_level=candidate.risk_level,
                summary=candidate.summary,
                evidence=candidate.evidence,
                status=AlertStatus.OPEN,
                detector_version=self.version,
            )
            for candidate in candidates
        ]
        session.add_all(alerts)
        session.flush()
        return model_run, alerts

    @staticmethod
    def _risk_level(risk_score: float) -> RiskLevel:
        if risk_score >= 0.90:
            return RiskLevel.CRITICAL
        if risk_score >= 0.75:
            return RiskLevel.HIGH
        if risk_score >= 0.50:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
