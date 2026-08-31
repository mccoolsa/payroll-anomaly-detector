"""Generate, persist, and optionally export a synthetic demonstration dataset."""

import argparse
from pathlib import Path

from data_generation import GenerationConfig, SyntheticPayrollGenerator
from database.session import create_database_engine, create_session_factory, session_scope


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--employees", type=int, default=250)
    parser.add_argument("--months", type=int, default=18)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--anomalies-per-type", type=int, default=4)
    parser.add_argument("--export-directory", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = GenerationConfig(
        employee_count=args.employees,
        month_count=args.months,
        seed=args.seed,
        anomalies_per_type=args.anomalies_per_type,
    )
    dataset = SyntheticPayrollGenerator(config).generate()
    factory = create_session_factory(create_database_engine())
    with session_scope(factory) as session:
        dataset.persist(session)
    if args.export_directory:
        dataset.export_csv(args.export_directory)
    print(dataset.summary)


if __name__ == "__main__":
    main()
