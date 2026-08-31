"""Generate longitudinal synthetic payroll records with known anomalies."""

from __future__ import annotations

import hashlib
from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from random import Random
from uuid import NAMESPACE_URL, uuid5

import pandas as pd
from faker import Faker
from sqlalchemy.orm import Session

from data_generation.config import GenerationConfig
from data_generation.reference_data import LOCATION_FACTORS, ROLE_PROFILES
from database.enums import (
    AnomalyType,
    EmploymentStatus,
    PayrollRunStatus,
)
from database.models import (
    AnomalyLabel,
    BankAccountHistory,
    Employee,
    Payment,
    PayrollRun,
)

PENCE = Decimal("0.01")


@dataclass
class GeneratedDataset:
    """Related ORM records plus evaluation-only labels."""

    employees: list[Employee]
    bank_accounts: list[BankAccountHistory]
    payroll_runs: list[PayrollRun]
    payments: list[Payment]
    labels: list[AnomalyLabel]

    @property
    def summary(self) -> dict[str, int]:
        return {
            "employees": len(self.employees),
            "bank_accounts": len(self.bank_accounts),
            "payroll_runs": len(self.payroll_runs),
            "payments": len(self.payments),
            "anomaly_labels": len(self.labels),
        }

    def persist(self, session: Session) -> None:
        """Persist the full dataset in dependency order."""

        session.add_all(self.employees)
        session.add_all(self.payroll_runs)
        session.add_all(self.bank_accounts)
        session.add_all(self.payments)
        session.add_all(self.labels)
        session.flush()

    def export_csv(self, output_directory: Path) -> None:
        """Export human-inspectable, synthetic-only CSV snapshots."""

        output_directory.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            [
                {
                    "employee_id": employee.id,
                    "employee_code": employee.employee_code,
                    "department": employee.department,
                    "job_title": employee.job_title,
                    "job_grade": employee.job_grade,
                    "location": employee.location,
                    "annual_salary": float(employee.annual_salary),
                    "hire_date": employee.hire_date,
                    "termination_date": employee.termination_date,
                    "employment_status": employee.employment_status.value,
                }
                for employee in self.employees
            ]
        ).to_csv(output_directory / "employees.csv", index=False)
        pd.DataFrame(
            [
                {
                    "payment_id": payment.id,
                    "payment_reference": payment.payment_reference,
                    "employee_id": payment.employee_id,
                    "payroll_run_id": payment.payroll_run_id,
                    "base_pay": float(payment.base_pay),
                    "overtime_pay": float(payment.overtime_pay),
                    "bonus_pay": float(payment.bonus_pay),
                    "gross_pay": float(payment.gross_pay),
                    "total_deductions": float(payment.total_deductions),
                    "net_pay": float(payment.net_pay),
                    "bank_account_token": payment.bank_account_token,
                }
                for payment in self.payments
            ]
        ).to_csv(output_directory / "payments.csv", index=False)
        pd.DataFrame(
            [
                {
                    "payment_id": label.payment_id,
                    "anomaly_type": label.anomaly_type.value,
                    "injection_details": label.injection_details,
                }
                for label in self.labels
            ]
        ).to_csv(output_directory / "evaluation_labels.csv", index=False)


class SyntheticPayrollGenerator:
    """Create plausible data without real employee or banking information."""

    def __init__(self, config: GenerationConfig) -> None:
        self.config = config
        self.random = Random(config.seed)
        self.faker = Faker("en_GB")
        self.faker.seed_instance(config.seed)

    def generate(self) -> GeneratedDataset:
        payroll_runs = self._generate_payroll_runs()
        employees, bank_accounts = self._generate_employees(payroll_runs)
        payments = self._generate_normal_payments(employees, payroll_runs)
        labels = self._inject_anomalies(employees, bank_accounts, payroll_runs, payments)
        return GeneratedDataset(employees, bank_accounts, payroll_runs, payments, labels)

    def _generate_payroll_runs(self) -> list[PayrollRun]:
        runs = []
        current = self.config.first_period.replace(day=1)
        for month_index in range(self.config.month_count):
            period_start = self._add_months(current, month_index)
            period_end = date(
                period_start.year,
                period_start.month,
                monthrange(period_start.year, period_start.month)[1],
            )
            payment_date = period_end - timedelta(days=3)
            runs.append(
                PayrollRun(
                    id=self._id(f"run-{period_start.isoformat()}"),
                    period_start=period_start,
                    period_end=period_end,
                    payment_date=payment_date,
                    status=PayrollRunStatus.PROCESSED,
                    created_at=datetime.combine(payment_date, datetime.min.time(), tzinfo=UTC),
                )
            )
        return runs

    def _generate_employees(
        self,
        payroll_runs: list[PayrollRun],
    ) -> tuple[list[Employee], list[BankAccountHistory]]:
        employees = []
        accounts = []
        role_weights = [profile[-1] for profile in ROLE_PROFILES]
        locations = list(LOCATION_FACTORS)
        termination_count = max(
            self.config.anomalies_per_type * 2, self.config.employee_count // 20
        )
        termination_indices = set(
            self.random.sample(range(self.config.employee_count), termination_count)
        )

        for index in range(self.config.employee_count):
            department, title, grade, lower, upper, _ = self.random.choices(
                ROLE_PROFILES,
                weights=role_weights,
                k=1,
            )[0]
            location = self.random.choice(locations)
            salary = self.random.triangular(lower, upper, (lower + upper) / 2)
            salary *= LOCATION_FACTORS[location]
            salary_decimal = self._money(round(salary / 250) * 250)
            earliest_hire = self.config.first_period - timedelta(days=365 * 8)
            latest_hire = self.config.first_period - timedelta(days=30)
            hire_date = self.faker.date_between(start_date=earliest_hire, end_date=latest_hire)
            termination_date = None
            status = EmploymentStatus.ACTIVE
            if index in termination_indices:
                termination_run = self.random.choice(payroll_runs[len(payroll_runs) // 2 : -1])
                termination_date = termination_run.period_end
                status = EmploymentStatus.TERMINATED

            employee_code = f"EMP-{index + 1:05d}"
            employee = Employee(
                id=self._id(employee_code),
                employee_code=employee_code,
                department=department,
                job_title=title,
                job_grade=grade,
                location=location,
                annual_salary=salary_decimal,
                hire_date=hire_date,
                termination_date=termination_date,
                employment_status=status,
                created_at=datetime.combine(hire_date, datetime.min.time(), tzinfo=UTC),
            )
            token = self._bank_token(f"{employee_code}-initial")
            account = BankAccountHistory(
                id=self._id(f"{employee_code}-account-initial"),
                employee_id=employee.id,
                account_token=token,
                effective_from=hire_date,
                changed_at=datetime.combine(hire_date, datetime.min.time(), tzinfo=UTC),
                change_reason="Synthetic initial account",
            )
            employees.append(employee)
            accounts.append(account)
        return employees, accounts

    def _generate_normal_payments(
        self,
        employees: list[Employee],
        payroll_runs: list[PayrollRun],
    ) -> list[Payment]:
        payments = []
        for payroll_run in payroll_runs:
            for employee in employees:
                if employee.hire_date > payroll_run.period_end:
                    continue
                if (
                    employee.termination_date
                    and employee.termination_date < payroll_run.period_start
                ):
                    continue
                base_pay = self._money(employee.annual_salary / Decimal(12))
                overtime = (
                    self._money(base_pay * Decimal(str(self.random.uniform(0.01, 0.08))))
                    if self.random.random() < 0.12
                    else Decimal("0.00")
                )
                bonus = (
                    self._money(base_pay * Decimal(str(self.random.uniform(0.05, 0.20))))
                    if payroll_run.period_start.month in {3, 12} and self.random.random() < 0.18
                    else Decimal("0.00")
                )
                gross = self._money(base_pay + overtime + bonus)
                deductions = self._calculate_deductions(gross, base_pay)
                employee_number = employee.employee_code.removeprefix("EMP-")
                reference = f"PAY-{payroll_run.period_start:%Y%m}-{employee_number}"
                payments.append(
                    Payment(
                        id=self._id(reference),
                        payment_reference=reference,
                        employee_id=employee.id,
                        payroll_run_id=payroll_run.id,
                        base_pay=base_pay,
                        overtime_pay=overtime,
                        bonus_pay=bonus,
                        gross_pay=gross,
                        bank_account_token=self._bank_token(f"{employee.employee_code}-initial"),
                        **deductions,
                    )
                )
        return payments

    def _inject_anomalies(
        self,
        employees: list[Employee],
        bank_accounts: list[BankAccountHistory],
        payroll_runs: list[PayrollRun],
        payments: list[Payment],
    ) -> list[AnomalyLabel]:
        labels: list[AnomalyLabel] = []
        protected_payment_ids: set[str] = set()

        candidates = [
            payment
            for payment in payments
            if payment.payroll_run_id in {run.id for run in payroll_runs[-4:]}
        ]

        for original in self._select(candidates, protected_payment_ids):
            duplicate_reference = f"{original.payment_reference}-DUP"
            duplicate = Payment(
                id=self._id(duplicate_reference),
                payment_reference=duplicate_reference,
                employee_id=original.employee_id,
                payroll_run_id=original.payroll_run_id,
                base_pay=original.base_pay,
                overtime_pay=original.overtime_pay,
                bonus_pay=original.bonus_pay,
                gross_pay=original.gross_pay,
                income_tax=original.income_tax,
                national_insurance=original.national_insurance,
                pension=original.pension,
                other_deductions=original.other_deductions,
                total_deductions=original.total_deductions,
                net_pay=original.net_pay,
                bank_account_token=original.bank_account_token,
            )
            payments.append(duplicate)
            protected_payment_ids.add(duplicate.id)
            labels.append(
                self._label(
                    duplicate,
                    AnomalyType.DUPLICATE_PAYMENT,
                    {"original_payment_id": original.id},
                )
            )

        for payment in self._select(candidates, protected_payment_ids):
            original_gross = payment.gross_pay
            multiplier = Decimal(str(self.random.uniform(1.75, 2.10)))
            payment.base_pay = self._money(payment.base_pay * multiplier)
            payment.gross_pay = self._money(
                payment.base_pay + payment.overtime_pay + payment.bonus_pay
            )
            self._apply_deductions(payment)
            labels.append(
                self._label(
                    payment,
                    AnomalyType.UNEXPECTED_PAY_INCREASE,
                    {
                        "original_gross_pay": float(original_gross),
                        "injected_gross_pay": float(payment.gross_pay),
                    },
                )
            )

        for payment in self._select(candidates, protected_payment_ids):
            payment.other_deductions = self._money(payment.gross_pay * Decimal("0.46"))
            payment.total_deductions = self._money(
                payment.income_tax
                + payment.national_insurance
                + payment.pension
                + payment.other_deductions
            )
            payment.net_pay = self._money(payment.gross_pay - payment.total_deductions)
            labels.append(
                self._label(
                    payment,
                    AnomalyType.ABNORMAL_DEDUCTION,
                    {"other_deduction_ratio": float(payment.other_deductions / payment.gross_pay)},
                )
            )

        employees_by_id = {employee.id: employee for employee in employees}
        accounts_by_employee = {
            account.employee_id: account
            for account in bank_accounts
            if account.effective_to is None
        }
        for payment in self._select(candidates, protected_payment_ids):
            payroll_run = next(run for run in payroll_runs if run.id == payment.payroll_run_id)
            employee = employees_by_id[payment.employee_id]
            old_account = accounts_by_employee[employee.id]
            effective_from = payroll_run.payment_date - timedelta(days=2)
            old_account.effective_to = effective_from - timedelta(days=1)
            token = self._bank_token(f"{employee.employee_code}-{payment.payment_reference}-recent")
            new_account = BankAccountHistory(
                id=self._id(f"{payment.id}-recent-account"),
                employee_id=employee.id,
                account_token=token,
                effective_from=effective_from,
                changed_at=datetime.combine(effective_from, datetime.min.time(), tzinfo=UTC),
                change_reason="Synthetic anomaly injection",
            )
            bank_accounts.append(new_account)
            accounts_by_employee[employee.id] = new_account
            payment.bank_account_token = token
            labels.append(
                self._label(
                    payment,
                    AnomalyType.RECENT_BANK_CHANGE,
                    {"days_before_payment": 2},
                )
            )

        terminated = [employee for employee in employees if employee.termination_date is not None]
        for employee in terminated[: self.config.anomalies_per_type]:
            eligible_run = payroll_runs[-1]
            base_pay = self._money(employee.annual_salary / Decimal(12))
            deductions = self._calculate_deductions(base_pay, base_pay)
            reference = (
                f"PAY-{eligible_run.period_start:%Y%m}-"
                f"{employee.employee_code.removeprefix('EMP-')}-TERM"
            )
            payment = Payment(
                id=self._id(reference),
                payment_reference=reference,
                employee_id=employee.id,
                payroll_run_id=eligible_run.id,
                base_pay=base_pay,
                overtime_pay=Decimal("0.00"),
                bonus_pay=Decimal("0.00"),
                gross_pay=base_pay,
                bank_account_token=self._bank_token(f"{employee.employee_code}-initial"),
                **deductions,
            )
            payments.append(payment)
            labels.append(
                self._label(
                    payment,
                    AnomalyType.POST_TERMINATION_PAYMENT,
                    {"termination_date": employee.termination_date.isoformat()},
                )
            )

        for payment in self._select(candidates, protected_payment_ids):
            payment.net_pay = self._money(payment.gross_pay * Decimal("1.08"))
            labels.append(
                self._label(
                    payment,
                    AnomalyType.INVALID_NET_GROSS_RATIO,
                    {"net_to_gross_ratio": 1.08},
                )
            )

        return labels

    def _select(self, candidates: list[Payment], protected_ids: set[str]) -> list[Payment]:
        available = [payment for payment in candidates if payment.id not in protected_ids]
        self.random.shuffle(available)
        selected: list[Payment] = []
        selected_employees: set[str] = set()
        for payment in available:
            if payment.employee_id in selected_employees:
                continue
            selected.append(payment)
            selected_employees.add(payment.employee_id)
            if len(selected) == self.config.anomalies_per_type:
                break
        if len(selected) != self.config.anomalies_per_type:
            raise ValueError("Not enough distinct employees to inject configured anomalies")
        protected_ids.update(payment.id for payment in selected)
        return selected

    def _apply_deductions(self, payment: Payment) -> None:
        deductions = self._calculate_deductions(payment.gross_pay, payment.base_pay)
        for field, value in deductions.items():
            setattr(payment, field, value)

    def _calculate_deductions(
        self,
        gross_pay: Decimal,
        base_pay: Decimal,
    ) -> dict[str, Decimal]:
        monthly_allowance = Decimal("1047.50")
        monthly_basic_band = Decimal("3141.67")
        taxable = max(gross_pay - monthly_allowance, Decimal("0"))
        basic_taxable = min(taxable, monthly_basic_band)
        higher_taxable = max(taxable - monthly_basic_band, Decimal("0"))
        income_tax = self._money(basic_taxable * Decimal("0.20") + higher_taxable * Decimal("0.40"))

        ni_primary_threshold = Decimal("1048")
        ni_upper_limit = Decimal("4189")
        main_ni = max(min(gross_pay, ni_upper_limit) - ni_primary_threshold, Decimal("0"))
        upper_ni = max(gross_pay - ni_upper_limit, Decimal("0"))
        national_insurance = self._money(main_ni * Decimal("0.08") + upper_ni * Decimal("0.02"))
        pension = self._money(base_pay * Decimal("0.05"))
        other = Decimal("0.00")
        total = self._money(income_tax + national_insurance + pension + other)
        return {
            "income_tax": income_tax,
            "national_insurance": national_insurance,
            "pension": pension,
            "other_deductions": other,
            "total_deductions": total,
            "net_pay": self._money(gross_pay - total),
        }

    def _label(
        self,
        payment: Payment,
        anomaly_type: AnomalyType,
        details: dict[str, float | str],
    ) -> AnomalyLabel:
        return AnomalyLabel(
            id=self._id(f"label-{payment.id}-{anomaly_type.value}"),
            payment_id=payment.id,
            anomaly_type=anomaly_type,
            injection_details=details,
        )

    def _id(self, name: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"payroll-{self.config.seed}-{name}"))

    def _bank_token(self, value: str) -> str:
        digest = hashlib.sha256(f"{self.config.seed}-{value}".encode()).hexdigest()[:16]
        return f"BANK-{digest.upper()}"

    @staticmethod
    def _money(value: Decimal | float | int) -> Decimal:
        return Decimal(str(value)).quantize(PENCE, rounding=ROUND_HALF_UP)

    @staticmethod
    def _add_months(value: date, months: int) -> date:
        month_index = value.month - 1 + months
        return date(value.year + month_index // 12, month_index % 12 + 1, 1)
