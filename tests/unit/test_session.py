"""Transaction helper tests."""

import pytest
from sqlalchemy import Engine, func, select

from database.enums import EmploymentStatus
from database.models import Employee
from database.session import create_session_factory, session_scope


def employee_record(code: str) -> Employee:
    from datetime import date
    from decimal import Decimal

    return Employee(
        employee_code=code,
        department="Data",
        job_title="Data Scientist",
        job_grade="G3",
        location="Belfast",
        annual_salary=Decimal("50000"),
        hire_date=date(2023, 1, 1),
        employment_status=EmploymentStatus.ACTIVE,
    )


def test_session_scope_commits_successful_work(database_engine: Engine) -> None:
    factory = create_session_factory(database_engine)
    with session_scope(factory) as session:
        session.add(employee_record("EMP-COMMIT"))

    with factory() as session:
        assert session.scalar(select(func.count(Employee.id))) == 1


def test_session_scope_rolls_back_failures(database_engine: Engine) -> None:
    factory = create_session_factory(database_engine)
    with pytest.raises(RuntimeError, match="cancel"), session_scope(factory) as session:
        session.add(employee_record("EMP-ROLLBACK"))
        raise RuntimeError("cancel")

    with factory() as session:
        assert session.scalar(select(func.count(Employee.id))) == 0
