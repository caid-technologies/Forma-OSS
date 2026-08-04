# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.9.28 AS uv
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    SQLITE_DATABASE_URL=sqlite:////data/blueprint.db \
    A2A_SOCKET_HOST=0.0.0.0

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data /app

COPY --from=uv /uv /uvx /bin/
COPY apps/api/pyproject.toml apps/api/uv.lock ./apps/api/
RUN cd apps/api \
    && uv sync --locked --no-dev --no-install-project

COPY apps/__init__.py ./apps/__init__.py
COPY apps/api ./apps/api
COPY blueprint_core ./blueprint_core
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000 8766

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

CMD ["sh", "-c", "uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
