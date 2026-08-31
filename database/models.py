"""SQLAlchemy models for payroll, anomaly, and investigation data."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, new_uuid, utc_now
from database.enums import (
    AlertSource,
    AlertStatus,
    AnomalyType,
    EmploymentStatus,
    InvestigationOutcome,
    PayrollRunStatus,
    RiskLevel,
)

MONEY = Numeric(12, 2)


def portable_enum(enum_type: type) -> Enum:
    """Create a string-backed enum that works consistently across databases."""

    return Enum(
        enum_type, native_enum=False, values_callable=lambda values: [item.value for item in values]
    )


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint("annual_salary >= 0", name="ck_employee_salary_nonnegative"),
        CheckConstraint(
            "termination_date IS NULL OR termination_date >= hire_date",
            name="ck_employee_termination_after_hire",
        ),
        Index("ix_employees_department_grade", "department", "job_grade"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    employee_code: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    department: Mapped[str] = mapped_column(String(80), nullable=False)
    job_title: Mapped[str] = mapped_column(String(120), nullable=False)
    job_grade: Mapped[str] = mapped_column(String(20), nullable=False)
    location: Mapped[str] = mapped_column(String(80), nullable=False)
    annual_salary: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    termination_date: Mapped[date | None] = mapped_column(Date)
    employment_status: Mapped[EmploymentStatus] = mapped_column(
        portable_enum(EmploymentStatus),
        nullable=False,
        default=EmploymentStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    bank_accounts: Mapped[list["BankAccountHistory"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="employee")


class BankAccountHistory(Base):
    __tablename__ = "bank_account_history"
    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_bank_account_effective_range",
        ),
        UniqueConstraint(
            "employee_id",
            "account_token",
            "effective_from",
            name="uq_bank_account_version",
        ),
        Index("ix_bank_account_employee_effective", "employee_id", "effective_from"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_token: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    change_reason: Mapped[str | None] = mapped_column(String(120))

    employee: Mapped[Employee] = relationship(back_populates="bank_accounts")


class PayrollRun(Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="ck_payroll_run_period"),
        CheckConstraint("payment_date >= period_start", name="ck_payroll_run_payment_date"),
        UniqueConstraint("period_start", "period_end", name="uq_payroll_run_period"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[PayrollRunStatus] = mapped_column(
        portable_enum(PayrollRunStatus),
        nullable=False,
        default=PayrollRunStatus.PROCESSED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    payments: Mapped[list["Payment"]] = relationship(
        back_populates="payroll_run",
        cascade="all, delete-orphan",
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("base_pay >= 0", name="ck_payment_base_pay"),
        CheckConstraint("gross_pay >= 0", name="ck_payment_gross_pay"),
        CheckConstraint("total_deductions >= 0", name="ck_payment_deductions"),
        Index("ix_payments_employee_run", "employee_id", "payroll_run_id"),
        Index("ix_payments_bank_token", "bank_account_token"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    payment_reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
    )
    payroll_run_id: Mapped[str] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    base_pay: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    overtime_pay: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    bonus_pay: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    gross_pay: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    income_tax: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    national_insurance: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    pension: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    other_deductions: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    total_deductions: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    net_pay: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    bank_account_token: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    employee: Mapped[Employee] = relationship(back_populates="payments")
    payroll_run: Mapped[PayrollRun] = relationship(back_populates="payments")
    alerts: Mapped[list["AnomalyAlert"]] = relationship(
        back_populates="payment",
        cascade="all, delete-orphan",
    )
    labels: Mapped[list["AnomalyLabel"]] = relationship(
        back_populates="payment",
        cascade="all, delete-orphan",
    )


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    training_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    training_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    feature_names: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(260), nullable=False)

    alerts: Mapped[list["AnomalyAlert"]] = relationship(back_populates="model_run")


class AnomalyAlert(Base):
    __tablename__ = "anomaly_alerts"
    __table_args__ = (
        CheckConstraint("risk_score >= 0 AND risk_score <= 1", name="ck_alert_risk_score"),
        Index("ix_alerts_status_risk", "status", "risk_level"),
        Index("ix_alerts_payment", "payment_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    payment_id: Mapped[str] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_run_id: Mapped[str | None] = mapped_column(ForeignKey("model_runs.id"))
    source: Mapped[AlertSource] = mapped_column(portable_enum(AlertSource), nullable=False)
    rule_code: Mapped[str | None] = mapped_column(String(80))
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(portable_enum(RiskLevel), nullable=False)
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        portable_enum(AlertStatus),
        nullable=False,
        default=AlertStatus.OPEN,
    )
    detector_version: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    payment: Mapped[Payment] = relationship(back_populates="alerts")
    model_run: Mapped[ModelRun | None] = relationship(back_populates="alerts")
    investigations: Mapped[list["Investigation"]] = relationship(
        back_populates="alert",
        cascade="all, delete-orphan",
    )


class Investigation(Base):
    __tablename__ = "investigations"
    __table_args__ = (Index("ix_investigations_alert_created", "alert_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    alert_id: Mapped[str] = mapped_column(
        ForeignKey("anomaly_alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    outcome: Mapped[InvestigationOutcome] = mapped_column(
        portable_enum(InvestigationOutcome),
        nullable=False,
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    investigator: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    alert: Mapped[AnomalyAlert] = relationship(back_populates="investigations")


class AnomalyLabel(Base):
    """Evaluation-only ground truth kept separate from detection inputs."""

    __tablename__ = "anomaly_labels"
    __table_args__ = (
        UniqueConstraint("payment_id", "anomaly_type", name="uq_payment_anomaly_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    payment_id: Mapped[str] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
    )
    anomaly_type: Mapped[AnomalyType] = mapped_column(
        portable_enum(AnomalyType),
        nullable=False,
    )
    injection_details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    payment: Mapped[Payment] = relationship(back_populates="labels")
