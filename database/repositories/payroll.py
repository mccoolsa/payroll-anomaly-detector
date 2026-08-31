"""Query and persistence operations used by services and the dashboard."""

from datetime import date
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from database.enums import AlertStatus, InvestigationOutcome
from database.models import (
    AnomalyAlert,
    Employee,
    Investigation,
    Payment,
    PayrollRun,
)


class PayrollRepository:
    """Keep SQLAlchemy queries out of presentation and detection code."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add_all(self, records: list[Any]) -> None:
        self.session.add_all(records)

    def get_payroll_runs(self) -> list[PayrollRun]:
        statement = select(PayrollRun).order_by(PayrollRun.period_start.desc())
        return list(self.session.scalars(statement))

    def get_payments_for_run(self, payroll_run_id: str) -> list[Payment]:
        statement = (
            select(Payment)
            .where(Payment.payroll_run_id == payroll_run_id)
            .options(joinedload(Payment.employee), joinedload(Payment.payroll_run))
            .order_by(Payment.payment_reference)
        )
        return list(self.session.scalars(statement).unique())

    def get_employee_payment_history(
        self,
        employee_id: str,
        *,
        before: date | None = None,
    ) -> list[Payment]:
        statement: Select[tuple[Payment]] = (
            select(Payment)
            .join(Payment.payroll_run)
            .where(Payment.employee_id == employee_id)
            .options(joinedload(Payment.payroll_run))
            .order_by(PayrollRun.period_end)
        )
        if before is not None:
            statement = statement.where(PayrollRun.period_end < before)
        return list(self.session.scalars(statement).unique())

    def list_alerts(
        self,
        *,
        payroll_run_id: str | None = None,
        status: AlertStatus | None = None,
    ) -> list[AnomalyAlert]:
        statement = (
            select(AnomalyAlert)
            .join(AnomalyAlert.payment)
            .options(
                joinedload(AnomalyAlert.payment).joinedload(Payment.employee),
                joinedload(AnomalyAlert.payment).joinedload(Payment.payroll_run),
            )
            .order_by(AnomalyAlert.risk_score.desc(), AnomalyAlert.created_at.desc())
        )
        if payroll_run_id is not None:
            statement = statement.where(Payment.payroll_run_id == payroll_run_id)
        if status is not None:
            statement = statement.where(AnomalyAlert.status == status)
        return list(self.session.scalars(statement).unique())

    def alert_counts_by_status(self) -> dict[str, int]:
        statement = select(AnomalyAlert.status, func.count(AnomalyAlert.id)).group_by(
            AnomalyAlert.status
        )
        return {status.value: count for status, count in self.session.execute(statement)}

    def record_investigation(
        self,
        alert: AnomalyAlert,
        *,
        outcome: InvestigationOutcome,
        notes: str,
        investigator: str,
    ) -> Investigation:
        investigation = Investigation(
            alert=alert,
            outcome=outcome,
            notes=notes.strip(),
            investigator=investigator.strip(),
        )
        alert.status = (
            AlertStatus.IN_REVIEW
            if outcome == InvestigationOutcome.NEEDS_INFORMATION
            else AlertStatus.RESOLVED
        )
        self.session.add(investigation)
        return investigation

    def get_employee(self, employee_id: str) -> Employee | None:
        return self.session.get(Employee, employee_id)
