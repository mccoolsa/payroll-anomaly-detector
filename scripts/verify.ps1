$ErrorActionPreference = "Stop"

.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest `
    --cov=app `
    --cov=data_generation `
    --cov=database `
    --cov-report=term-missing `
    --cov-fail-under=80
docker compose config --quiet
docker build --tag payroll-anomaly-detector:local .

