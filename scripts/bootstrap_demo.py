"""Create a complete synthetic demonstration environment in the configured database."""

from pathlib import Path

from sqlalchemy import func, select

from app.services.pipeline import run_pipeline
from data_generation import GenerationConfig, SyntheticPayrollGenerator
from database.models import PayrollRun
from database.session import create_database_engine, create_session_factory, session_scope


def main() -> None:
    factory = create_session_factory(create_database_engine())
    with session_scope(factory) as session:
        existing_runs = session.scalar(select(func.count(PayrollRun.id))) or 0
        if existing_runs:
            print({"status": "skipped", "reason": "database already contains payroll runs"})
            return
        dataset = SyntheticPayrollGenerator(GenerationConfig()).generate()
        result = run_pipeline(
            dataset,
            session,
            artifact_path=Path("models/isolation_forest.joblib"),
        )
    print(
        {
            **dataset.summary,
            "alerts": len(result.alerts),
            "model_metrics": result.model_metrics.as_dict(),
        }
    )


if __name__ == "__main__":
    main()
