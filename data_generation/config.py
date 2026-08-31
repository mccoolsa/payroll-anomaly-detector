"""Configuration profiles for reproducible synthetic payroll generation."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class GenerationConfig:
    """Control dataset scale without changing generation logic."""

    employee_count: int = 250
    month_count: int = 18
    first_period: date = date(2024, 1, 1)
    seed: int = 42
    anomalies_per_type: int = 4

    def __post_init__(self) -> None:
        if self.employee_count < 20:
            raise ValueError("employee_count must be at least 20")
        if self.month_count < 6:
            raise ValueError("month_count must be at least 6")
        if self.anomalies_per_type < 1:
            raise ValueError("anomalies_per_type must be positive")
