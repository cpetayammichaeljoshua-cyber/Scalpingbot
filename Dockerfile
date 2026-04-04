# ──────────────────────────────────────────────────────────────────────────────
# MiroFish Swarm + G0DM0D3 AI Trading Bot — Production Dockerfile
# Optimised for Railway (and any Docker host)
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Build-time system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libffi-dev \
        libssl-dev \
        libgomp1 \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Install Python dependencies first (layer-cached) ──────────────────────────
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# ── Copy project ───────────────────────────────────────────────────────────────
COPY . .

# ── Persistent data directory (mount a Railway volume here for SQLite) ─────────
# Default: /data  (set DATA_DIR env var in Railway to override)
RUN mkdir -p /data/SignalMaestro /data/ml_models

# ── Runtime env vars (override in Railway dashboard) ──────────────────────────
ENV DATA_DIR=/data
ENV PORT=8080

# ── Health-check (Railway will poll /health every 60 s) ───────────────────────
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# ── Entrypoint ────────────────────────────────────────────────────────────────
CMD ["python3", "start_ultimate_bot.py"]
