"""Synthetic dataset reproducibility, integrity, and anomaly tests."""

from collections import Counter
from decimal import Decimal

from sqlalchemy.orm import Session

from data_generation import GenerationConfig, SyntheticPayrollGenerator
from database.enums import AnomalyType
from database.models import AnomalyLabel, Employee, Payment


def test_generation_is_reproducible() -> None:
    config = GenerationConfig(employee_count=30, month_count=8, seed=7, anomalies_per_type=2)

    first = SyntheticPayrollGenerator(config).generate()
    second = SyntheticPayrollGenerator(config).generate()

    assert [employee.id for employee in first.employees] == [
        employee.id for employee in second.employees
    ]
    assert [payment.gross_pay for payment in first.payments] == [
        payment.gross_pay for payment in second.payments
    ]
    assert [label.anomaly_type for label in first.labels] == [
        label.anomaly_type for label in second.labels
    ]


def test_all_anomaly_types_are_injected_at_configured_count() -> None:
    config = GenerationConfig(employee_count=40, month_count=8, seed=11, anomalies_per_type=2)
    dataset = SyntheticPayrollGenerator(config).generate()
    counts = Counter(label.anomaly_type for label in dataset.labels)

    assert counts == {anomaly_type: 2 for anomaly_type in AnomalyType}
    assert all(payment.gross_pay >= Decimal("0") for payment in dataset.payments)
    assert len({payment.payment_reference for payment in dataset.payments}) == len(dataset.payments)


def test_generated_dataset_persists_with_relational_integrity(db_session: Session) -> None:
    config = GenerationConfig(employee_count=30, month_count=6, seed=13, anomalies_per_type=1)
    dataset = SyntheticPayrollGenerator(config).generate()

    dataset.persist(db_session)
    db_session.commit()

    assert db_session.query(Employee).count() == 30
    assert db_session.query(Payment).count() == len(dataset.payments)
    assert db_session.query(AnomalyLabel).count() == len(AnomalyType)
