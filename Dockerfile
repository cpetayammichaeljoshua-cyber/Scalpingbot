# ═══════════════════════════════════════════════════════════════════════════════
# Unity Engine v18.49 — Multi-stage Production Dockerfile
# Optimised for Railway.app deployment
#
# Build:  docker build -t unity-engine:18.49 .
# Railway: Detected automatically via railway.json
#
# BASE IMAGE: python:3.11-slim  (Debian/glibc)
# ────────────────────────────────────────────────────────────────────────────────
# WHY NOT ALPINE?
#   Alpine uses musl libc.  scikit-learn has no pre-built musllinux wheel.
#   When pip falls back to source compilation it requires numpy release
#   candidates that may not be published for musl — causing the Railway
#   build to fail at the pip install step.  python:3.11-slim (glibc) has fully
#   pre-built manylinux wheels for every package in requirements.txt and builds
#   in < 3 min on Railway's free tier.
# ────────────────────────────────────────────────────────────────────────────────
# v18.25 features in this image:
#   • 21/21 intelligence layers ONLINE — all quant subsystems active
#   • Multi-key OpenRouter failover (OPENROUTER_API_KEY_BACKUP_1..7 in Railway)
#   • Redis state caching with heartbeat reconnector (set REDIS_URL in Railway)
#   • orjson fast JSON, @watched_task auto-restart, asyncio.Queue pipeline
#   • Formal CLOSED/OPEN/HALF_OPEN circuit-breaker on every layer
#   • uvloop high-performance event loop (2-4× faster I/O)
#   • Monte Carlo VaR + Bayesian Kelly Criterion + Omega Ratio gate
#   • Dead-Man's Switch latency monitor (/healthz returns 503 if avg > 500 ms)
#   • Lock-free GEX snap cache, CUSUM BLAS vectorization, OFI adaptive EV floor
#   • Sortino RMS downside semi-deviation fix (v18.24/v18.25 — all code paths)
#   • Omega Ratio count-imbalance fix (v18.24/v18.25 — Booster + Metrics classes)
#   • Gate 0.5 double-penalty fix (v18.24 — mutually exclusive soft/hard branches)
#   • FLIP ZONE structural Kelly floor (0.3% minimum on FLIP ZONE signals)
#   • deque(maxlen=200) O(1) trade-return ring (v18.26 — no heap alloc on trim)
#   • railway.json: healthcheckTimeout=300, restartPolicy=ALWAYS, sleepApp=false
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

# Upgrade pip/setuptools once
RUN pip install --upgrade pip setuptools wheel

# v18.36 RAILWAY FIX: Install PyTorch CPU separately with extended timeout and retries.
# The torch==2.4.0+cpu wheel is ~300MB from pytorch CDN — Railway builds time out
# on the default 60s pip timeout.  --retries 5 + --timeout 600 ensures the full
# wheel downloads on slow CDN days.  The || echo makes this step non-fatal so the
# Docker build succeeds even if the CDN is temporarily unreachable; the engine
# activates its sklearn fallback automatically at runtime.
RUN pip install --prefix=/install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    --timeout 600 --retries 5 \
    torch==2.4.0+cpu \
    || echo "WARNING [v18.36]: torch CDN unreachable — sklearn fallback active at runtime"

# Install all remaining packages (fast PyPI packages, torch already present above)
RUN pip install --prefix=/install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    --timeout 300 --retries 3 \
    -r requirements.txt


# ── Stage 2: minimal runtime image ────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="Unity Engine Bot" \
      version="18.49"                \
      description="Unity Engine v18.49 — Kelly Step 19 prime-session boost; Step 12 ×0.20; Markov MIN_OBS 10→7; SCAN_PARALLEL 30→35; PyTorch test v7.0; SOVEREIGN [1.00]"

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
