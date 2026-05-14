# ═══════════════════════════════════════════════════════════════════════════════
# Unity Engine v18.71 — Multi-stage Production Dockerfile
# Optimised for Railway.app deployment
#
# Build:  docker build -t unity-engine:18.71 .
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
# v18.61 changes in this image:
#   • STRICT torch install — NO silent || echo fallback.  Build fails fast if
#     torch CDN is unreachable so operators see the real error immediately
#     instead of getting a silently-degraded deploy showing "pytorch_transformer
#     degraded 0.75" in Railway logs.  Two CDN URLs tried in sequence; if both
#     fail the build exits non-zero and Railway retries.
#   • transformers==5.8.0 pinned (was >=4.51.0 — fixed in v18.41, kept here).
#   • All version labels updated to 18.56.
#   • Build-stage forward-pass smoke-test added after torch install.
#   • SCAN_PARALLEL_LIMIT 45→50 | NN_WIN_PROB_GATE 0.40→0.39.
#   • All 21 intelligence layers ONLINE — SOVEREIGN [1.00].
#   • Multi-key OpenRouter failover (OPENROUTER_API_KEY_BACKUP_1..7 in Railway)
#   • Redis state caching with heartbeat reconnector (set REDIS_URL in Railway)
#   • orjson fast JSON, @watched_task auto-restart, asyncio.Queue pipeline
#   • Formal CLOSED/OPEN/HALF_OPEN circuit-breaker on every layer
#   • uvloop high-performance event loop (2-4× faster I/O)
#   • Monte Carlo VaR + Bayesian Kelly Criterion + Omega Ratio gate
#   • Dead-Man's Switch latency monitor (/healthz returns 503 if avg > 500 ms)
#   • Lock-free GEX snap cache, CUSUM BLAS vectorization, OFI adaptive EV floor
#   • Markov death-spiral fix (v18.55): dynamic penalty_threshold = max(0.35, WR×0.85)
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
RUN pip install --upgrade pip 'setuptools>=70.0.0' wheel --root-user-action=ignore

# ── PyTorch CPU — STRICT install (no silent fallback) ─────────────────────────
# v18.56 FIX: Removed the "|| echo" fallback that was silently producing
# degraded Railway deploys showing "pytorch_transformer degraded 0.75".
# Strategy: try primary CDN first, then mirror CDN; both with --retries 5
# and --timeout 600.  If both CDNs are unreachable the build fails fast
# so Railway retries the deploy (better than a zombie-degraded bot).
RUN pip install --prefix=/install --no-cache-dir --root-user-action=ignore \
    --index-url https://download.pytorch.org/whl/cpu \
    --timeout 600 --retries 5 \
    torch==2.4.0+cpu \
    && echo "✅ [v18.56] torch==2.4.0+cpu installed from primary CDN" \
    || ( \
        echo "⚠️  [v18.56] Primary CDN failed — trying mirror CDN..." \
        && pip install --prefix=/install --no-cache-dir --root-user-action=ignore \
               --extra-index-url https://download.pytorch.org/whl/cpu \
               --index-url https://pypi.org/simple \
               --timeout 600 --retries 5 \
               torch==2.4.0+cpu \
        && echo "✅ [v18.56] torch==2.4.0+cpu installed from mirror CDN" \
    )

# ── Build-stage smoke-test — fail fast if forward pass is broken ───────────────
# This catches corrupted wheels, ABI mismatches, or CDN partial downloads
# before the image is promoted to the runtime stage.
RUN PYTHONPATH=/install/lib/python3.11/site-packages python3 -c "\
import torch, torch.nn as nn; \
layer = nn.TransformerEncoderLayer(d_model=64, nhead=4, batch_first=True, dropout=0.0); \
enc = nn.TransformerEncoder(layer, num_layers=2); \
enc.eval(); \
out = enc(torch.zeros(1, 8, 64)); \
assert out.shape == (1, 8, 64), f'shape mismatch: {out.shape}'; \
print(f'✅ [v18.56] torch {torch.__version__} TransformerEncoder forward-pass verified — SOVEREIGN [1.00]'); \
"

# ── Install all remaining packages (fast PyPI wheels) ─────────────────────────
RUN pip install --prefix=/install --no-cache-dir --root-user-action=ignore \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    --timeout 300 --retries 3 \
    -r requirements.txt

# ── HuggingFace transformers (pinned ==5.8.0 — after torch for correct resolution) ──
RUN pip install --prefix=/install --no-cache-dir --root-user-action=ignore \
    --timeout 180 --retries 3 \
    transformers==5.8.0 \
    && echo "✅ [v18.56] transformers==5.8.0 installed"


# ── Stage 2: minimal runtime image ────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="Unity Engine Bot" \
      version="18.71"                \
      description="Unity Engine v18.71 — G_BLK prewarm 300→150s; EV-fail L3 1800→1200s; Asian-cap 900→600s; NEARUSDT unprotected; INTERVAL 300→240s; bypass 88→86%; EV-fail escalate 6→7"

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
