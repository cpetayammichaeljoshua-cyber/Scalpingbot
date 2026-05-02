# ═══════════════════════════════════════════════════════════════════════════════
# Unity Engine v8.2 — Multi-stage Production Dockerfile
# Optimised for Railway.app deployment
#
# Build:  docker build -t unity-engine:8.2 .
# Railway: Detected automatically via railway.json
#
# BASE IMAGE: python:3.11-slim  (Debian/glibc)
# ────────────────────────────────────────────────────────────────────────────────
# WHY NOT ALPINE?
#   Alpine uses musl libc.  scikit-learn==1.4.2 has no pre-built musllinux wheel.
#   When pip falls back to source compilation it requires numpy==2.0.0rc1, a
#   release candidate that was never published for musl — causing the Railway
#   build to fail at the pip install step.  python:3.11-slim (glibc) has fully
#   pre-built manylinux wheels for every package in requirements.txt and builds
#   in < 3 min on Railway's free tier.
# ────────────────────────────────────────────────────────────────────────────────
# v8.2 features in this image:
#   • Multi-key OpenRouter failover (OPENROUTER_API_KEY_BACKUP_1/2 in Railway)
#   • Redis state caching (set REDIS_URL in Railway Variables)
#   • orjson fast JSON, @watched_task auto-restart, asyncio.Queue pipeline
#   • Formal CLOSED/OPEN/HALF_OPEN circuit-breaker on every layer
#   • uvloop high-performance event loop (2-4× faster I/O)
#   • Monte Carlo VaR + Bayesian Kelly Criterion
#   • Dead-Man's Switch latency monitor (/healthz returns 503 if avg > 500 ms)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Stage 1: dependency builder ────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# glibc compile-time deps (only in builder — not copied to runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libffi-dev \
        libssl-dev \
        git \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps into a separate prefix for clean copying
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: minimal runtime image ────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="Unity Engine Bot" \
      version="8.2"                  \
      description="Unity Engine v8.2 — institution-grade multiparallel async trading intelligence"

# Non-root user for production security
RUN groupadd -r unity && useradd -r -g unity -d /app -s /sbin/nologin unity

WORKDIR /app

# Runtime system deps only (no compiler, no headers)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local

# Copy entire workspace (code, SignalMaestro, configs, etc.)
COPY --chown=unity:unity . /app

# ── /tmp always writable by non-root user ─────────────────────────────────────
# Railway may mount /app read-only; ut_bot_strategy and other log writers use
# /tmp instead of /app (patched in v8.0 — see ut_bot_strategy/orchestrator.py).
RUN chmod 1777 /tmp

# ── Persistent storage — Railway-compatible note ───────────────────────────────
# Railway does NOT support the Docker VOLUME instruction.
# To persist /app/SignalMaestro (SQLite DBs, NN weights) and /app/logs across
# deploys, add a Railway Volume via Dashboard → your service → Volumes:
#   Mount path: /app/SignalMaestro   (trade history, NN weights, metrics JSON)
#   Mount path: /app/logs            (engine rotating file logs)
# Without a Volume, state is ephemeral but the engine still runs correctly.

# ── Environment hardening ──────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    LOG_LEVEL=INFO \
    UNITY_ENV=production

# ── Railway: expose the health port ───────────────────────────────────────────
# Railway injects $PORT automatically; Unity Engine reads PORT → UNITY_HEALTH_PORT → 8080
EXPOSE 8080

# ── Fault-tolerance: HEALTHCHECK (k8s-style liveness + Dead-Man's Switch) ─────
# /healthz → 200 if layers online + scan not stalled + avg latency < 500ms
# /readyz  → 200 only after critical layers ready + first scan cycle complete
HEALTHCHECK --interval=60s --timeout=15s --start-period=60s --retries=3 \
    CMD curl -sf http://localhost:${PORT:-8080}/healthz || exit 1

USER unity

# ── Entrypoint ────────────────────────────────────────────────────────────────
CMD ["python3", "-u", "start_unity_engine.py"]
