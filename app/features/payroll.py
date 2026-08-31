"""Leakage-safe payroll features for unsupervised anomaly detection."""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median, pstdev
from typing import TYPE_CHECKING

import pandas as pd

from database.models import Payment

if TYPE_CHECKING:
    from app.detection.rules import DetectionContext

FEATURE_COLUMNS = [
    "gross_pay",
    "gross_change_ratio",
    "gross_peer_ratio",
    "deduction_ratio",
    "other_deduction_ratio",
    "net_gross_ratio",
    "bonus_ratio",
    "payment_count_in_run",
    "days_since_bank_change",
    "bank_change_recency_score",
    "days_since_hire",
    "days_after_termination",
    "post_termination_indicator",
    "historical_pay_volatility",
]

MODEL_FEATURE_COLUMNS = [
    "gross_change_ratio",
    "gross_peer_ratio",
    "deduction_ratio",
    "other_deduction_ratio",
    "net_gross_ratio",
    "payment_count_in_run",
    "bank_change_recency_score",
    "post_termination_indicator",
    "historical_pay_volatility",
]


class PayrollFeatureBuilder:
    """Create features using only information available at scoring time."""

    version = "features-1.0"

    def build(self, context: DetectionContext) -> pd.DataFrame:
        rows: list[dict[str, float | int | str | pd.Timestamp]] = []
        history_by_employee: dict[str, list[float]] = defaultdict(list)
        payments_by_run: dict[str, list[Payment]] = defaultdict(list)
        for payment in context.payments:
            payments_by_run[payment.payroll_run_id].append(payment)

        for payroll_run in sorted(context.payroll_runs, key=lambda run: run.period_end):
            run_payments = payments_by_run.get(payroll_run.id, [])
            payment_counts = Counter(payment.employee_id for payment in run_payments)
            peer_gross = self._peer_medians(run_payments, context)

            for payment in sorted(run_payments, key=lambda item: item.payment_reference):
                employee = context.employees_by_id[payment.employee_id]
                history = history_by_employee[payment.employee_id][-6:]
                historical_median = median(history) if history else float(payment.gross_pay)
                historical_volatility = (
                    pstdev(history) / historical_median
                    if len(history) >= 2 and historical_median
                    else 0.0
                )
                peer_key = (employee.department, employee.job_grade)
                peer_median = peer_gross.get(peer_key, float(payment.gross_pay))
                gross = float(payment.gross_pay)
                account = context.accounts_by_token.get(payment.bank_account_token)
                days_since_change = (
                    (payroll_run.payment_date - account.effective_from).days
                    if account is not None
                    else 3650
                )
                days_after_termination = (
                    max((payroll_run.payment_date - employee.termination_date).days, 0)
                    if employee.termination_date
                    else 0
                )

                rows.append(
                    {
                        "payment_id": payment.id,
                        "employee_id": employee.id,
                        "payroll_run_id": payroll_run.id,
                        "payment_date": pd.Timestamp(payroll_run.payment_date),
                        "department": employee.department,
                        "job_grade": employee.job_grade,
                        "gross_pay": gross,
                        "gross_change_ratio": gross / historical_median
                        if historical_median
                        else 1.0,
                        "gross_peer_ratio": gross / peer_median if peer_median else 1.0,
                        "deduction_ratio": self._ratio(
                            payment.total_deductions,
                            payment.gross_pay,
                        ),
                        "other_deduction_ratio": self._ratio(
                            payment.other_deductions,
                            payment.gross_pay,
                        ),
                        "net_gross_ratio": self._ratio(payment.net_pay, payment.gross_pay),
                        "bonus_ratio": self._ratio(payment.bonus_pay, payment.gross_pay),
                        "payment_count_in_run": payment_counts[payment.employee_id],
                        "days_since_bank_change": max(days_since_change, 0),
                        "bank_change_recency_score": 1 / (1 + max(days_since_change, 0)),
                        "days_since_hire": max(
                            (payroll_run.payment_date - employee.hire_date).days,
                            0,
                        ),
                        "days_after_termination": days_after_termination,
                        "post_termination_indicator": int(days_after_termination > 0),
                        "historical_pay_volatility": historical_volatility,
                    }
                )

            for payment in run_payments:
                history_by_employee[payment.employee_id].append(float(payment.gross_pay))

        frame = pd.DataFrame(rows)
        if frame.empty:
            return pd.DataFrame(
                columns=[
                    "payment_id",
                    "employee_id",
                    "payroll_run_id",
                    "payment_date",
                    "department",
                    "job_grade",
                    *FEATURE_COLUMNS,
                ]
            )
        frame[FEATURE_COLUMNS] = frame[FEATURE_COLUMNS].astype(float)
        return frame.sort_values(["payment_date", "payment_id"]).reset_index(drop=True)

    @staticmethod
    def _peer_medians(
        payments: list[Payment],
        context: DetectionContext,
    ) -> dict[tuple[str, str], float]:
        groups: dict[tuple[str, str], list[float]] = defaultdict(list)
        for payment in payments:
            employee = context.employees_by_id[payment.employee_id]
            groups[(employee.department, employee.job_grade)].append(float(payment.gross_pay))
        return {key: median(values) for key, values in groups.items()}

    @staticmethod
    def _ratio(numerator, denominator) -> float:
        return float(numerator / denominator) if denominator else 0.0
