# syntax=docker/dockerfile:1
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

# 1) System deps (lean)
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates curl tini; \
    rm -rf /var/lib/apt/lists/*

# 2) Global env
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 3) Non-root user
ARG APP_USER=appuser
RUN useradd -m -u 10001 -s /usr/sbin/nologin ${APP_USER}

# 4) Working dir & dep manifests
WORKDIR /app
COPY requirements.txt* pyproject.toml* poetry.lock* /app/

# 5) Install deps (prefer wheels)
ARG PIP_FLAGS="--no-cache-dir --prefer-binary"
RUN set -eux; \
    python -m pip install --upgrade pip setuptools wheel; \
    if [ -f requirements.txt ]; then pip install $PIP_FLAGS -r requirements.txt; fi; \
    if [ -f pyproject.toml ]; then pip install $PIP_FLAGS -e .; fi

# 6) Copy application (with ownership so tests can write under /app)
COPY --chown=${APP_USER}:${APP_USER} . /app

# 7) Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import sys; sys.exit(0)"

# 8) Drop privileges and set entrypoint
USER ${APP_USER}
ENTRYPOINT ["/usr/bin/tini", "--"]

# Default: safe no-op
CMD ["python", "-m", "app.io.sheets_runner", "ping"]
