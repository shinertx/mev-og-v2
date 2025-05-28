# Multi-stage build for MEV-OG
# Stage 1: build dependencies with caching
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system deps required for web3 and tests
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libssl-dev libffi-dev git curl \
    && rm -rf /var/lib/apt/lists/*

ENV POETRY_VERSION=2.1.3
RUN pip install "poetry==$POETRY_VERSION"

COPY pyproject.toml poetry.lock ./
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes || true
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# Stage 2: runtime image
FROM python:3.11-slim
WORKDIR /app
RUN adduser --disabled-password --gecos "" mevog
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY . .

USER mevog
# Default command can be overridden at runtime
CMD ["python", "-m", "core.orchestrator", "--config=config.yaml", "--dry-run"]
