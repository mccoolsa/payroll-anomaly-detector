"""Repository integration tests using an isolated relational database."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from database.enums import (
    AlertSource,
    AlertStatus,
    EmploymentStatus,
    InvestigationOutcome,
    PayrollRunStatus,
    RiskLevel,
)
from database.models import AnomalyAlert, Employee, Payment, PayrollRun
from database.repositories import PayrollRepository


def test_repository_lists_alerts_and_records_investigation(db_session: Session) -> None:
    employee = Employee(
        employee_code="EMP-0099",
        department="Finance",
        job_title="Payroll Analyst",
        job_grade="G2",
        location="London",
        annual_salary=Decimal("42000"),
        hire_date=date(2022, 2, 1),
        employment_status=EmploymentStatus.ACTIVE,
    )
    payroll_run = PayrollRun(
        period_start=date(2025, 2, 1),
        period_end=date(2025, 2, 28),
        payment_date=date(2025, 2, 27),
        status=PayrollRunStatus.PROCESSED,
    )
    payment = Payment(
        payment_reference="PAY-202502-0099",
        employee=employee,
        payroll_run=payroll_run,
        base_pay=Decimal("3500"),
        overtime_pay=Decimal("0"),
        bonus_pay=Decimal("0"),
        gross_pay=Decimal("3500"),
        income_tax=Decimal("500"),
        national_insurance=Decimal("180"),
        pension=Decimal("175"),
        other_deductions=Decimal("0"),
        total_deductions=Decimal("855"),
        net_pay=Decimal("2645"),
        bank_account_token="BANK-TEST-099",
    )
    alert = AnomalyAlert(
        payment=payment,
        source=AlertSource.RULE,
        rule_code="DUPLICATE_PAYMENT",
        risk_score=0.95,
        risk_level=RiskLevel.CRITICAL,
        summary="Potential duplicate payment",
        evidence={"matching_count": 2},
        status=AlertStatus.OPEN,
        detector_version="rules-1.0",
    )
    db_session.add(alert)
    db_session.commit()

    repository = PayrollRepository(db_session)
    alerts = repository.list_alerts(payroll_run_id=payroll_run.id)
    investigation = repository.record_investigation(
        alerts[0],
        outcome=InvestigationOutcome.LEGITIMATE_PAYMENT,
        notes="Approved correction.",
        investigator="Portfolio reviewer",
    )
    db_session.commit()

    assert alerts == [alert]
    assert investigation.alert.status == AlertStatus.RESOLVED
    assert repository.alert_counts_by_status() == {"resolved": 1}
