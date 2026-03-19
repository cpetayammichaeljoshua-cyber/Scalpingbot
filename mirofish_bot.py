"""
MiroFish Bot - Swarm Intelligence Prediction Engine
Source: https://github.com/666ghj/MiroFish.git

Production-grade launcher for the MiroFish backend Flask server.
Uses Gunicorn (production WSGI) with full circuit breaker, exponential
backoff auto-restart, graceful signal handling, and health monitoring.

Required environment variables:
  LLM_API_KEY   - Your LLM API key (OpenAI-compatible).
                  Falls back to OPENAI_API_KEY automatically.
  ZEP_API_KEY   - Your Zep Cloud API key for agent memory (optional;
                  disables graph-memory features when absent).

Optional environment variables:
  LLM_BASE_URL          - LLM API base URL (default: https://api.openai.com/v1)
  LLM_MODEL_NAME        - Model name to use (default: gpt-4o-mini)
  FLASK_HOST            - Host to bind (default: 0.0.0.0)
  FLASK_PORT            - Port to bind (default: 8000)
  FLASK_DEBUG           - Enable debug mode (default: False)
  GUNICORN_WORKERS      - Number of gunicorn worker processes (default: 2)
  GUNICORN_THREADS      - Threads per worker (default: 4)
  GUNICORN_TIMEOUT      - Worker timeout in seconds (default: 120)
  MAX_RESTARTS          - Maximum auto-restart attempts (default: 100)
  RESTART_DELAY_BASE    - Base restart delay in seconds (default: 5)
  CIRCUIT_BREAKER_FAILS - Consecutive failures to trip breaker (default: 5)
  CIRCUIT_BREAKER_COOL  - Circuit breaker cooldown in seconds (default: 60)
"""

from __future__ import annotations

import os
import sys
import time
import signal
import logging
import subprocess
import threading
import json
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# UTF-8 Encoding — must happen before any other I/O
# ─────────────────────────────────────────────────────────────────────────────
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────────────────────────────────────
# API Key Bridge: OPENAI_API_KEY → LLM_API_KEY
# If LLM_API_KEY is not set, transparently forward OPENAI_API_KEY so the
# MiroFish backend can make LLM calls without any manual reconfiguration.
# IMPORTANT: strip invisible Unicode characters (e.g. U+200E LEFT-TO-RIGHT MARK)
# that can appear when keys are pasted from certain text editors/browsers.
# ─────────────────────────────────────────────────────────────────────────────
import unicodedata as _unicodedata

def _sanitize_api_key(key: str) -> str:
    """Remove invisible/non-printable Unicode characters from an API key string."""
    return "".join(
        ch for ch in key
        if _unicodedata.category(ch) not in ("Cf", "Cc", "Cs", "Co", "Cn")
        and ch.isprintable()
    ).strip()


def _bridge_api_keys() -> None:
    """Bridge OPENAI_API_KEY → LLM_API_KEY, sanitizing invisible characters."""
    # Always sanitize OPENAI_API_KEY in-place if it exists (fixes U+200E etc.)
    raw_oai = os.environ.get("OPENAI_API_KEY", "")
    if raw_oai:
        clean_oai = _sanitize_api_key(raw_oai)
        if clean_oai != raw_oai:
            os.environ["OPENAI_API_KEY"] = clean_oai

    if not os.environ.get("LLM_API_KEY"):
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if openai_key:
            os.environ["LLM_API_KEY"] = openai_key

    # Also sanitize LLM_API_KEY if it was set directly with invisible chars
    raw_llm = os.environ.get("LLM_API_KEY", "")
    if raw_llm:
        clean_llm = _sanitize_api_key(raw_llm)
        if clean_llm != raw_llm:
            os.environ["LLM_API_KEY"] = clean_llm


_bridge_api_keys()

# Ensure port 8000 default
os.environ.setdefault("FLASK_PORT", "8000")

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
ROOT_DIR    = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "mirofish_backend"
LOG_DIR     = BACKEND_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(BACKEND_DIR))

# ─────────────────────────────────────────────────────────────────────────────
# Constants (from start_ultimate_bot.py pattern)
# ─────────────────────────────────────────────────────────────────────────────
_DEFAULT_MAX_RESTARTS       = int(os.environ.get("MAX_RESTARTS",          "100"))
_DEFAULT_RESTART_DELAY_BASE = int(os.environ.get("RESTART_DELAY_BASE",     "5"))
_MAX_DELAY_SECONDS          = 300
_CIRCUIT_BREAKER_THRESHOLD  = int(os.environ.get("CIRCUIT_BREAKER_FAILS",  "5"))
_CIRCUIT_BREAKER_COOLDOWN   = int(os.environ.get("CIRCUIT_BREAKER_COOL",  "60"))
_HEALTH_CHECK_INTERVAL      = 30   # seconds
_GUNICORN_WORKERS           = int(os.environ.get("GUNICORN_WORKERS",       "2"))
_GUNICORN_THREADS           = int(os.environ.get("GUNICORN_THREADS",       "4"))
_GUNICORN_TIMEOUT           = int(os.environ.get("GUNICORN_TIMEOUT",      "120"))
_GUNICORN_GRACEFUL_TIMEOUT  = 30
_FLASK_HOST                 = os.environ.get("FLASK_HOST", "0.0.0.0")
_FLASK_PORT                 = int(os.environ.get("FLASK_PORT", "8000"))
_DEBUG_MODE                 = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

# ─────────────────────────────────────────────────────────────────────────────
# Logging — structured, rotating, UTF-8
# ─────────────────────────────────────────────────────────────────────────────
def _build_logger() -> logging.Logger:
    log = logging.getLogger("mirofish_bot")
    if log.handlers:
        return log
    log.setLevel(logging.DEBUG if _DEBUG_MODE else logging.INFO)
    log.propagate = False

    fmt_detail = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fmt_simple = logging.Formatter(
        "[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Rotating file handler — 10 MB × 7 backups
    fh = RotatingFileHandler(
        LOG_DIR / "mirofish_bot.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=7,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt_detail)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt_simple)

    log.addHandler(fh)
    log.addHandler(ch)
    return log


logger = _build_logger()

# ─────────────────────────────────────────────────────────────────────────────
# Exponential Backoff (same algorithm as start_ultimate_bot.py)
# ─────────────────────────────────────────────────────────────────────────────
def _calculate_delay(restart_count: int, base_delay: int) -> int:
    exponent = min(restart_count - 1, 10)
    return min(base_delay * (2 ** exponent), _MAX_DELAY_SECONDS)


# ─────────────────────────────────────────────────────────────────────────────
# Shutdown event (shared across threads)
# ─────────────────────────────────────────────────────────────────────────────
_shutdown_event = threading.Event()
_current_process: Optional[subprocess.Popen] = None
_process_lock    = threading.Lock()


def _handle_signal(signum: int, _frame) -> None:
    sig_name = signal.Signals(signum).name
    logger.info(f"🛑 Signal received: {sig_name} — initiating graceful shutdown")
    _shutdown_event.set()
    with _process_lock:
        proc = _current_process
    if proc and proc.poll() is None:
        try:
            proc.send_signal(signal.SIGTERM)
            logger.info("📤 SIGTERM sent to gunicorn worker")
        except (ProcessLookupError, OSError):
            pass


# Register signal handlers for graceful shutdown
for _sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(_sig, _handle_signal)
try:
    signal.signal(signal.SIGHUP, _handle_signal)
except (AttributeError, OSError):
    pass   # SIGHUP not available on Windows


# ─────────────────────────────────────────────────────────────────────────────
# Config Validation
# ─────────────────────────────────────────────────────────────────────────────
def _validate_config() -> list[str]:
    """Return list of (non-fatal) configuration warnings."""
    from app.config import Config  # type: ignore[import]
    return Config.validate()


def _print_banner() -> None:
    host = _FLASK_HOST
    port = _FLASK_PORT
    print("=" * 60)
    print("  MiroFish - Swarm Intelligence Prediction Engine")
    print("  https://github.com/666ghj/MiroFish")
    print("=" * 60)

    try:
        warnings = _validate_config()
        if warnings:
            print("\n[WARNING] Configuration issues detected (non-fatal):")
            for w in warnings:
                print(f"  - {w}")
            print("\nAffected features will be unavailable until the vars are set.")
            print("  LLM_API_KEY  - Required for LLM-powered agent analysis")
            print("  ZEP_API_KEY  - Required for Zep graph memory operations")
            print()
    except Exception as exc:
        logger.debug(f"Config validation error (non-fatal): {exc}")

    print(f"\n[INFO] Starting MiroFish backend on http://{host}:{port}")
    print(f"[INFO] Debug mode: {_DEBUG_MODE}")
    print(f"[INFO] WSGI server: gunicorn ({_GUNICORN_WORKERS}w × {_GUNICORN_THREADS}t)")
    print(f"[INFO] LLM model: {os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')}")
    print(f"[INFO] LLM base URL: {os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')}")
    print(f"[INFO] LLM_API_KEY: {'✅ configured' if os.environ.get('LLM_API_KEY') else '❌ missing'}")
    print(f"[INFO] ZEP_API_KEY: {'✅ configured' if os.environ.get('ZEP_API_KEY') else '⚠️  missing (graph memory disabled)'}")
    print("\n[INFO] API Endpoints:")
    print(f"  GET  http://{host}:{port}/health")
    print(f"  *    http://{host}:{port}/api/graph/...")
    print(f"  *    http://{host}:{port}/api/simulation/...")
    print(f"  *    http://{host}:{port}/api/report/...")
    print("\n" + "=" * 60 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Gunicorn Process Builder
# ─────────────────────────────────────────────────────────────────────────────
def _build_gunicorn_cmd() -> list[str]:
    """Build the gunicorn command list."""
    access_log = str(LOG_DIR / "gunicorn_access.log")
    error_log  = str(LOG_DIR / "gunicorn_error.log")

    return [
        sys.executable, "-m", "gunicorn",
        # WSGI app module path (relative to BACKEND_DIR added to sys.path)
        "app:create_app()",
        "--bind",               f"{_FLASK_HOST}:{_FLASK_PORT}",
        "--workers",            str(_GUNICORN_WORKERS),
        "--threads",            str(_GUNICORN_THREADS),
        "--worker-class",       "gthread",
        "--timeout",            str(_GUNICORN_TIMEOUT),
        "--graceful-timeout",   str(_GUNICORN_GRACEFUL_TIMEOUT),
        "--keep-alive",         "5",
        "--max-requests",       "1000",
        "--max-requests-jitter","100",
        "--access-logfile",     access_log,
        "--error-logfile",      error_log,
        "--log-level",          "info",
        "--capture-output",
        "--enable-stdio-inheritance",
        "--forwarded-allow-ips", "*",
        "--proxy-allow-from",   "*",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Health Monitor Thread
# ─────────────────────────────────────────────────────────────────────────────
def _health_monitor(stop_event: threading.Event) -> None:
    """Periodically log health status of the running gunicorn process."""
    import urllib.request
    import urllib.error

    url = f"http://127.0.0.1:{_FLASK_PORT}/health"
    while not stop_event.wait(_HEALTH_CHECK_INTERVAL):
        if _shutdown_event.is_set():
            break
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())
                logger.debug(f"💚 Health OK: {data}")
        except urllib.error.URLError as exc:
            logger.warning(f"⚠️ Health check failed: {exc.reason}")
        except Exception as exc:
            logger.debug(f"Health check error (non-fatal): {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Single-Run: launch gunicorn, stream output, return True=success False=error
# ─────────────────────────────────────────────────────────────────────────────
def _run_once() -> bool:
    global _current_process

    cmd = _build_gunicorn_cmd()
    env = os.environ.copy()
    # Ensure BACKEND_DIR is first in PYTHONPATH for the subprocess
    old_pypath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(BACKEND_DIR) + (f":{old_pypath}" if old_pypath else "")

    logger.info(f"🚀 Launching gunicorn: {' '.join(cmd[2:])}")

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(BACKEND_DIR),
            env=env,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
    except FileNotFoundError:
        logger.error("❌ gunicorn not found — falling back to Flask dev server")
        return _run_flask_fallback()
    except Exception as exc:
        logger.error(f"❌ Failed to start gunicorn: {exc}")
        return False

    with _process_lock:
        _current_process = proc

    # Start health monitor
    stop_health = threading.Event()
    health_thread = threading.Thread(
        target=_health_monitor, args=(stop_health,), daemon=True, name="HealthMonitor"
    )
    health_thread.start()

    # Wait for process to exit or shutdown signal
    exit_code: Optional[int] = None
    while True:
        try:
            exit_code = proc.wait(timeout=1.0)
            break
        except subprocess.TimeoutExpired:
            if _shutdown_event.is_set():
                logger.info("🛑 Shutdown event — terminating gunicorn")
                try:
                    proc.terminate()
                    proc.wait(timeout=_GUNICORN_GRACEFUL_TIMEOUT)
                except subprocess.TimeoutExpired:
                    logger.warning("⚠️ Graceful timeout expired — killing gunicorn")
                    proc.kill()
                exit_code = proc.wait()
                break

    stop_health.set()
    with _process_lock:
        _current_process = None

    if _shutdown_event.is_set():
        logger.info(f"✅ Gunicorn exited cleanly on shutdown (code={exit_code})")
        return True

    if exit_code == 0:
        logger.info("✅ Gunicorn exited cleanly (code=0)")
        return True

    logger.error(f"❌ Gunicorn exited with code {exit_code}")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Flask Dev-Server Fallback (if gunicorn is unavailable)
# ─────────────────────────────────────────────────────────────────────────────
def _run_flask_fallback() -> bool:
    """Last-resort: run using Flask's built-in server (development only)."""
    logger.warning("⚠️  Using Flask development server — NOT recommended for production")
    try:
        from app import create_app  # type: ignore[import]
        from app.config import Config  # type: ignore[import]
        app = create_app()
        app.run(
            host=_FLASK_HOST,
            port=_FLASK_PORT,
            debug=_DEBUG_MODE,
            threaded=True,
            use_reloader=False,
        )
        return True
    except Exception as exc:
        logger.error(f"❌ Flask fallback failed: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main Launcher — Circuit Breaker + Exponential Backoff Auto-Restart
# (mirrors the pattern in start_ultimate_bot.py)
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    _print_banner()

    max_restarts         = max(1, _DEFAULT_MAX_RESTARTS)
    restart_delay_base   = max(1, _DEFAULT_RESTART_DELAY_BASE)
    restart_count        = 0
    consecutive_failures = 0
    total_elapsed        = 0.0
    cb_triggered         = False
    cb_trip_time         = 0.0

    logger.info("🐟 MiroFish Backend Launcher — Production Mode")
    logger.info(f"📋 Config: max_restarts={max_restarts}, base_delay={restart_delay_base}s, "
                f"circuit_breaker={_CIRCUIT_BREAKER_THRESHOLD} fails / {_CIRCUIT_BREAKER_COOLDOWN}s cooldown")
    logger.info(f"🌐 Binding: {_FLASK_HOST}:{_FLASK_PORT}")

    while restart_count < max_restarts and not _shutdown_event.is_set():

        # ── Circuit Breaker ──
        if cb_triggered:
            elapsed_since = time.time() - cb_trip_time
            if elapsed_since < _CIRCUIT_BREAKER_COOLDOWN:
                remaining = _CIRCUIT_BREAKER_COOLDOWN - elapsed_since
                logger.warning(f"⚠️  Circuit breaker active — {remaining:.0f}s remaining")
                if _shutdown_event.wait(min(remaining, 2.0)):
                    break
                continue
            logger.info("🔄 Circuit breaker reset — attempting recovery")
            cb_triggered         = False
            consecutive_failures = 0

        # ── Launch ──
        logger.info(
            f"🎯 Starting server (attempt #{restart_count + 1}/{max_restarts}, "
            f"failures={consecutive_failures})"
        )

        t0 = time.time()
        try:
            success = _run_once()
        except KeyboardInterrupt:
            logger.info("🛑 Keyboard interrupt — shutting down")
            _shutdown_event.set()
            break
        except Exception as exc:
            logger.error(f"💥 Unexpected launcher error: {type(exc).__name__}: {exc}", exc_info=True)
            success = False

        elapsed = time.time() - t0
        total_elapsed += elapsed

        if _shutdown_event.is_set():
            logger.info(f"✅ Launcher stopped by signal (total runtime {total_elapsed:.1f}s)")
            break

        if success:
            logger.info(f"✅ Server completed cleanly (runtime={elapsed:.1f}s, total={total_elapsed:.1f}s)")
            consecutive_failures = 0
            break

        restart_count        += 1
        consecutive_failures += 1

        # Trip circuit breaker?
        if consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD:
            logger.error(
                f"🔴 Circuit breaker tripped after {consecutive_failures} consecutive failures"
            )
            cb_triggered  = True
            cb_trip_time  = time.time()
            consecutive_failures = 0
            continue

        if restart_count >= max_restarts:
            logger.error(f"❌ Maximum restarts ({max_restarts}) reached — stopping")
            break

        delay = _calculate_delay(restart_count, restart_delay_base)
        logger.warning(
            f"⚠️  Server exited with error (attempt #{restart_count}/{max_restarts}, "
            f"runtime={elapsed:.1f}s). Restarting in {delay}s..."
        )
        if _shutdown_event.wait(delay):
            break

    logger.info(f"🏁 MiroFish launcher exited (total runtime {total_elapsed:.1f}s, restarts={restart_count})")


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 MiroFish launcher interrupted by user")
    except Exception as exc:
        print(f"\n\n❌ Fatal launcher error: {type(exc).__name__}: {exc}")
        sys.exit(1)
