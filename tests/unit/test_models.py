"""Domain model and constraint tests."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.enums import EmploymentStatus, PayrollRunStatus
from database.models import BankAccountHistory, Employee, Payment, PayrollRun


def make_employee() -> Employee:
    return Employee(
        employee_code="EMP-0001",
        department="Engineering",
        job_title="Software Engineer",
        job_grade="G3",
        location="Belfast",
        annual_salary=Decimal("48000"),
        hire_date=date(2023, 1, 10),
        employment_status=EmploymentStatus.ACTIVE,
    )


def test_employee_and_payment_relationships(db_session: Session) -> None:
    employee = make_employee()
    employee.bank_accounts.append(
        BankAccountHistory(
            account_token="BANK-TEST-001",
            effective_from=date(2023, 1, 10),
            changed_at=datetime(2023, 1, 10, tzinfo=UTC),
        )
    )
    payroll_run = PayrollRun(
        period_start=date(2025, 1, 1),
        period_end=date(2025, 1, 31),
        payment_date=date(2025, 1, 28),
        status=PayrollRunStatus.PROCESSED,
    )
    payment = Payment(
        payment_reference="PAY-202501-0001",
        employee=employee,
        payroll_run=payroll_run,
        base_pay=Decimal("4000"),
        overtime_pay=Decimal("0"),
        bonus_pay=Decimal("0"),
        gross_pay=Decimal("4000"),
        income_tax=Decimal("600"),
        national_insurance=Decimal("200"),
        pension=Decimal("200"),
        other_deductions=Decimal("0"),
        total_deductions=Decimal("1000"),
        net_pay=Decimal("3000"),
        bank_account_token="BANK-TEST-001",
    )
    db_session.add(payment)
    db_session.commit()

    assert payment.employee.employee_code == "EMP-0001"
    assert payment.payroll_run.period_end == date(2025, 1, 31)
    assert employee.bank_accounts[0].account_token == payment.bank_account_token


def test_duplicate_employee_code_is_rejected(db_session: Session) -> None:
    db_session.add_all([make_employee(), make_employee()])

    with pytest.raises(IntegrityError):
        db_session.commit()
