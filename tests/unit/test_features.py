"""Feature correctness and temporal leakage checks."""

from app.detection import DetectionContext
from app.features import FEATURE_COLUMNS, PayrollFeatureBuilder
from data_generation import GenerationConfig, SyntheticPayrollGenerator


def build_dataset_and_features():
    dataset = SyntheticPayrollGenerator(
        GenerationConfig(employee_count=35, month_count=8, seed=31, anomalies_per_type=1)
    ).generate()
    context = DetectionContext(
        dataset.payments,
        dataset.employees,
        dataset.payroll_runs,
        dataset.bank_accounts,
    )
    return dataset, PayrollFeatureBuilder().build(context)


def test_features_are_complete_and_finite() -> None:
    _, features = build_dataset_and_features()

    assert list(features[FEATURE_COLUMNS].columns) == FEATURE_COLUMNS
    assert features[FEATURE_COLUMNS].notna().all().all()
    assert len(features) > 200


def test_future_payment_change_does_not_alter_past_features() -> None:
    dataset, original_features = build_dataset_and_features()
    final_run_id = dataset.payroll_runs[-1].id
    final_payment = next(
        payment for payment in dataset.payments if payment.payroll_run_id == final_run_id
    )
    final_payment.gross_pay *= 5
    context = DetectionContext(
        dataset.payments,
        dataset.employees,
        dataset.payroll_runs,
        dataset.bank_accounts,
    )
    changed_features = PayrollFeatureBuilder().build(context)
    earlier_mask = original_features["payment_date"] < original_features["payment_date"].max()

    assert original_features.loc[earlier_mask, FEATURE_COLUMNS].equals(
        changed_features.loc[earlier_mask, FEATURE_COLUMNS]
    )
