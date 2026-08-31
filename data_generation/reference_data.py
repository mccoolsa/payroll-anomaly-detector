"""Aggregate-informed synthetic company distributions.

Ranges are intentionally rounded rather than copied employee-level observations.
They are inspired by UK ONS ASHE occupation and regional earnings aggregates.
"""

ROLE_PROFILES = (
    ("Engineering", "Software Engineer", "G2", 36000, 47000, 0.24),
    ("Engineering", "Senior Software Engineer", "G3", 48000, 68000, 0.17),
    ("Data", "Data Analyst", "G2", 33000, 46000, 0.10),
    ("Data", "Data Scientist", "G3", 43000, 65000, 0.08),
    ("Consulting", "Business Consultant", "G2", 34000, 49000, 0.12),
    ("Consulting", "Senior Consultant", "G3", 50000, 72000, 0.09),
    ("Product", "Product Manager", "G3", 47000, 68000, 0.06),
    ("Finance", "Payroll Analyst", "G2", 30000, 43000, 0.05),
    ("People", "People Operations Specialist", "G2", 30000, 42000, 0.04),
    ("Operations", "Operations Coordinator", "G1", 25000, 34000, 0.05),
)

LOCATION_FACTORS = {
    "Belfast": 0.90,
    "Birmingham": 0.96,
    "Bristol": 1.02,
    "Edinburgh": 1.00,
    "London": 1.15,
    "Manchester": 0.98,
}
