FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system payroll \
    && useradd --system --gid payroll --create-home payroll

COPY pyproject.toml README.md ./
COPY app ./app
COPY data_generation ./data_generation
COPY database ./database
COPY scripts ./scripts
COPY alembic.ini ./

RUN python -m pip install --upgrade pip \
    && python -m pip install .

RUN mkdir -p /app/models \
    && chown -R payroll:payroll /app

USER payroll

EXPOSE 8501

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["python", "-m", "streamlit", "run", "app/dashboard/main.py", \
     "--server.address=0.0.0.0", "--server.port=8501", \
     "--browser.gatherUsageStats=false"]

