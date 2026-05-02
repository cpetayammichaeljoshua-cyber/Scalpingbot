"""
Gunicorn production configuration for MiroFish Backend.
Reference: https://docs.gunicorn.org/en/stable/configure.html

Usage:
    gunicorn -c gunicorn.conf.py "app:create_app()"
Or via mirofish_bot.py launcher (recommended).
"""

import os
import multiprocessing

# ── Binding ──
host = os.environ.get("FLASK_HOST", "0.0.0.0")
port = int(os.environ.get("FLASK_PORT", "8000"))
bind = f"{host}:{port}"

# ── Workers ──
# 2 × CPU cores + 1 is a common heuristic, capped at 4 for Replit resource limits.
_cpus = multiprocessing.cpu_count()
workers     = int(os.environ.get("GUNICORN_WORKERS", min(2 * _cpus + 1, 4)))
threads     = int(os.environ.get("GUNICORN_THREADS", 4))
worker_class = "gthread"

# ── Timeouts ──
timeout         = int(os.environ.get("GUNICORN_TIMEOUT", 120))
graceful_timeout = 30
keepalive        = 5

# ── Request limits ──
max_requests        = 1000
max_requests_jitter = 100
limit_request_line  = 8190
limit_request_fields = 100

# ── Logging ──
_log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_log_dir, exist_ok=True)

accesslog    = os.path.join(_log_dir, "gunicorn_access.log")
errorlog     = os.path.join(_log_dir, "gunicorn_error.log")
loglevel     = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'

# ── Performance ──
preload_app      = False   # False keeps worker isolation for crash recovery
capture_output   = True
enable_stdio_inheritance = True

# ── Proxy / Security ──
forwarded_allow_ips = "*"   # Trust all proxy headers (Replit edge → gunicorn)
proxy_allow_from    = "*"

# ── Lifecycle hooks ──
def on_starting(server):
    server.log.info("🐟 MiroFish gunicorn server starting up")

def on_exit(server):
    server.log.info("🛑 MiroFish gunicorn server shutting down")

def worker_exit(server, worker):
    server.log.info(f"👋 Worker {worker.pid} exiting")

def worker_abort(worker):
    worker.log.info(f"💥 Worker {worker.pid} aborted — will be replaced")
