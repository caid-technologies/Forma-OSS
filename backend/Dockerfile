# syntax=docker/dockerfile:1

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATABASE_URL=sqlite:////data/blueprint.db \
    JOB_METADATA_DB_PATH=/data/blueprint_jobs.db \
    A2A_SOCKET_HOST=0.0.0.0

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r backend/requirements.txt

COPY backend ./backend
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000 8766

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
