"""Deterministic payroll controls with structured, auditable evidence."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from statistics import median

from database.enums import AnomalyType, RiskLevel
from database.models import BankAccountHistory, Employee, Payment, PayrollRun


@dataclass(frozen=True)
class RuleConfig:
    pay_increase_ratio: float = 1.50
    minimum_history: int = 3
    other_deduction_ratio: float = 0.30
    total_deduction_ratio: float = 0.55
    bank_change_window_days: int = 7


@dataclass(frozen=True)
class RuleFinding:
    payment_id: str
    anomaly_type: AnomalyType
    rule_code: str
    risk_score: float
    risk_level: RiskLevel
    summary: str
    evidence: dict[str, float | int | str]


@dataclass
class DetectionContext:
    payments: list[Payment]
    employees: list[Employee]
    payroll_runs: list[PayrollRun]
    bank_accounts: list[BankAccountHistory]
    employees_by_id: dict[str, Employee] = field(init=False)
    runs_by_id: dict[str, PayrollRun] = field(init=False)
    accounts_by_token: dict[str, BankAccountHistory] = field(init=False)

    def __post_init__(self) -> None:
        self.employees_by_id = {employee.id: employee for employee in self.employees}
        self.runs_by_id = {payroll_run.id: payroll_run for payroll_run in self.payroll_runs}
        self.accounts_by_token = {account.account_token: account for account in self.bank_accounts}


class RuleEngine:
    """Run known payroll controls independently of the user interface."""

    version = "rules-1.0"

    def __init__(self, config: RuleConfig | None = None) -> None:
        self.config = config or RuleConfig()

    def detect(self, context: DetectionContext) -> list[RuleFinding]:
        findings = [
            *self._duplicate_payments(context),
            *self._unexpected_pay_increases(context),
            *self._abnormal_deductions(context),
            *self._recent_bank_changes(context),
            *self._post_termination_payments(context),
            *self._invalid_net_gross_ratios(context),
        ]
        return sorted(findings, key=lambda item: (-item.risk_score, item.payment_id))

    def _duplicate_payments(self, context: DetectionContext) -> list[RuleFinding]:
        groups: dict[tuple, list[Payment]] = defaultdict(list)
        for payment in context.payments:
            key = (
                payment.employee_id,
                payment.payroll_run_id,
                payment.gross_pay,
                payment.net_pay,
                payment.bank_account_token,
            )
            groups[key].append(payment)

        findings = []
        for matches in groups.values():
            if len(matches) < 2:
                continue
            ordered = sorted(matches, key=lambda payment: payment.payment_reference)
            original = ordered[0]
            for duplicate in ordered[1:]:
                findings.append(
                    RuleFinding(
                        payment_id=duplicate.id,
                        anomaly_type=AnomalyType.DUPLICATE_PAYMENT,
                        rule_code="DUPLICATE_PAYMENT",
                        risk_score=0.98,
                        risk_level=RiskLevel.CRITICAL,
                        summary="Payment matches another employee payment in this payroll run.",
                        evidence={
                            "matching_payment_reference": original.payment_reference,
                            "gross_pay": float(duplicate.gross_pay),
                            "net_pay": float(duplicate.net_pay),
                        },
                    )
                )
        return findings

    def _unexpected_pay_increases(self, context: DetectionContext) -> list[RuleFinding]:
        by_employee: dict[str, list[Payment]] = defaultdict(list)
        for payment in context.payments:
            by_employee[payment.employee_id].append(payment)

        findings = []
        for employee_payments in by_employee.values():
            ordered = sorted(
                employee_payments,
                key=lambda payment: (
                    context.runs_by_id[payment.payroll_run_id].period_end,
                    payment.payment_reference,
                ),
            )
            history: list[Decimal] = []
            for payment in ordered:
                if len(history) >= self.config.minimum_history:
                    baseline = Decimal(str(median(history[-6:])))
                    ratio = float(payment.gross_pay / baseline) if baseline else 0.0
                    if ratio >= self.config.pay_increase_ratio:
                        findings.append(
                            RuleFinding(
                                payment_id=payment.id,
                                anomaly_type=AnomalyType.UNEXPECTED_PAY_INCREASE,
                                rule_code="UNEXPECTED_PAY_INCREASE",
                                risk_score=min(0.96, 0.55 + (ratio - 1) * 0.35),
                                risk_level=RiskLevel.HIGH,
                                summary=(
                                    "Gross pay is substantially above the employee's "
                                    "recent baseline."
                                ),
                                evidence={
                                    "gross_pay": float(payment.gross_pay),
                                    "six_period_median": float(baseline),
                                    "increase_ratio": round(ratio, 3),
                                    "history_periods": min(len(history), 6),
                                },
                            )
                        )
                history.append(payment.gross_pay)
        return findings

    def _abnormal_deductions(self, context: DetectionContext) -> list[RuleFinding]:
        findings = []
        for payment in context.payments:
            if payment.gross_pay <= 0:
                continue
            other_ratio = float(payment.other_deductions / payment.gross_pay)
            total_ratio = float(payment.total_deductions / payment.gross_pay)
            if (
                other_ratio >= self.config.other_deduction_ratio
                or total_ratio >= self.config.total_deduction_ratio
            ):
                findings.append(
                    RuleFinding(
                        payment_id=payment.id,
                        anomaly_type=AnomalyType.ABNORMAL_DEDUCTION,
                        rule_code="ABNORMAL_DEDUCTION",
                        risk_score=min(0.96, 0.58 + max(other_ratio, total_ratio) * 0.55),
                        risk_level=RiskLevel.HIGH,
                        summary="Deductions consume an unusually large proportion of gross pay.",
                        evidence={
                            "other_deduction_ratio": round(other_ratio, 3),
                            "total_deduction_ratio": round(total_ratio, 3),
                            "total_deductions": float(payment.total_deductions),
                        },
                    )
                )
        return findings

    def _recent_bank_changes(self, context: DetectionContext) -> list[RuleFinding]:
        findings = []
        for payment in context.payments:
            account = context.accounts_by_token.get(payment.bank_account_token)
            if account is None:
                continue
            payment_date = context.runs_by_id[payment.payroll_run_id].payment_date
            days_since_change = (payment_date - account.effective_from).days
            if 0 <= days_since_change <= self.config.bank_change_window_days:
                findings.append(
                    RuleFinding(
                        payment_id=payment.id,
                        anomaly_type=AnomalyType.RECENT_BANK_CHANGE,
                        rule_code="RECENT_BANK_CHANGE",
                        risk_score=0.84,
                        risk_level=RiskLevel.HIGH,
                        summary="Payment destination changed shortly before the payroll date.",
                        evidence={
                            "days_before_payment": days_since_change,
                            "change_date": account.effective_from.isoformat(),
                            "configured_window_days": self.config.bank_change_window_days,
                        },
                    )
                )
        return findings

    def _post_termination_payments(self, context: DetectionContext) -> list[RuleFinding]:
        findings = []
        for payment in context.payments:
            employee = context.employees_by_id[payment.employee_id]
            payroll_run = context.runs_by_id[payment.payroll_run_id]
            if employee.termination_date and payroll_run.period_start > employee.termination_date:
                findings.append(
                    RuleFinding(
                        payment_id=payment.id,
                        anomaly_type=AnomalyType.POST_TERMINATION_PAYMENT,
                        rule_code="POST_TERMINATION_PAYMENT",
                        risk_score=0.99,
                        risk_level=RiskLevel.CRITICAL,
                        summary="Payment occurs in a payroll period after employment ended.",
                        evidence={
                            "termination_date": employee.termination_date.isoformat(),
                            "payroll_period_start": payroll_run.period_start.isoformat(),
                            "days_after_termination": (
                                payroll_run.payment_date - employee.termination_date
                            ).days,
                        },
                    )
                )
        return findings

    def _invalid_net_gross_ratios(self, context: DetectionContext) -> list[RuleFinding]:
        findings = []
        for payment in context.payments:
            if payment.gross_pay <= 0:
                continue
            ratio = float(payment.net_pay / payment.gross_pay)
            if ratio > 1 or ratio < 0:
                findings.append(
                    RuleFinding(
                        payment_id=payment.id,
                        anomaly_type=AnomalyType.INVALID_NET_GROSS_RATIO,
                        rule_code="INVALID_NET_GROSS_RATIO",
                        risk_score=0.96,
                        risk_level=RiskLevel.CRITICAL,
                        summary="Net pay falls outside the valid range from zero to gross pay.",
                        evidence={
                            "gross_pay": float(payment.gross_pay),
                            "net_pay": float(payment.net_pay),
                            "net_to_gross_ratio": round(ratio, 3),
                        },
                    )
                )
        return findings


def build_detection_context(
    payments: list[Payment],
    employees: list[Employee],
    payroll_runs: list[PayrollRun],
    bank_accounts: list[BankAccountHistory],
) -> DetectionContext:
    return DetectionContext(payments, employees, payroll_runs, bank_accounts)


def payment_date(payment: Payment, context: DetectionContext) -> date:
    """Expose a stable payment-date lookup for feature engineering."""

    return context.runs_by_id[payment.payroll_run_id].payment_date
