"""Controlled domain values persisted by the payroll application."""

from enum import StrEnum


class EmploymentStatus(StrEnum):
    ACTIVE = "active"
    TERMINATED = "terminated"
    LEAVE = "leave"


class PayrollRunStatus(StrEnum):
    DRAFT = "draft"
    PROCESSED = "processed"
    CLOSED = "closed"


class AlertSource(StrEnum):
    RULE = "rule"
    MODEL = "model"
    HYBRID = "hybrid"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"


class InvestigationOutcome(StrEnum):
    CONFIRMED_ISSUE = "confirmed_issue"
    LEGITIMATE_PAYMENT = "legitimate_payment"
    NEEDS_INFORMATION = "needs_information"


class AnomalyType(StrEnum):
    DUPLICATE_PAYMENT = "duplicate_payment"
    UNEXPECTED_PAY_INCREASE = "unexpected_pay_increase"
    ABNORMAL_DEDUCTION = "abnormal_deduction"
    RECENT_BANK_CHANGE = "recent_bank_change"
    POST_TERMINATION_PAYMENT = "post_termination_payment"
    INVALID_NET_GROSS_RATIO = "invalid_net_gross_ratio"
