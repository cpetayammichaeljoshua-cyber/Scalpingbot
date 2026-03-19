"""
MiroFish Backend — Logging subsystem
Production-grade: rotating files, UTF-8, structured formatter, zero duplicate handlers.
"""

from __future__ import annotations

import os
import sys
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler

# ── Log directory ──
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# ── Is debug mode on? ──
_DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"


def _ensure_utf8_stdout() -> None:
    """Reconfigure stdout/stderr to UTF-8 (Windows / some container envs)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def setup_logger(
    name:  str = "mirofish",
    level: int | None = None,
) -> logging.Logger:
    """
    Create (or retrieve) a named logger with:
    - RotatingFileHandler: DEBUG+, 10 MB × 7 backups, UTF-8
    - StreamHandler (stdout): INFO+ in normal mode, DEBUG in debug mode
    Idempotent — calling twice returns the same logger unchanged.
    """
    log = logging.getLogger(name)

    if log.handlers:
        return log  # already configured

    if level is None:
        level = logging.DEBUG if _DEBUG else logging.INFO
    log.setLevel(logging.DEBUG)   # capture everything; handlers filter
    log.propagate = False

    _ensure_utf8_stdout()

    fmt_detail = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fmt_simple = logging.Formatter(
        "[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── Rotating file handler ──
    log_file = os.path.join(LOG_DIR, f"{datetime.now():%Y-%m-%d}.log")
    try:
        fh = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=7,
            encoding="utf-8",
            delay=True,
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt_detail)
        log.addHandler(fh)
    except (OSError, IOError) as exc:
        sys.stderr.write(f"[mirofish] WARNING: Cannot create log file {log_file}: {exc}\n")

    # ── Console handler ──
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if _DEBUG else logging.INFO)
    ch.setFormatter(fmt_simple)
    log.addHandler(ch)

    return log


def get_logger(name: str = "mirofish") -> logging.Logger:
    """Return existing logger or create one via setup_logger."""
    log = logging.getLogger(name)
    if not log.handlers:
        return setup_logger(name)
    return log


# ── Module-level default logger & convenience wrappers ──
logger = setup_logger()


def debug(msg: str, *args, **kwargs)    -> None: logger.debug(msg,    *args, **kwargs)
def info(msg: str, *args, **kwargs)     -> None: logger.info(msg,     *args, **kwargs)
def warning(msg: str, *args, **kwargs)  -> None: logger.warning(msg,  *args, **kwargs)
def error(msg: str, *args, **kwargs)    -> None: logger.error(msg,    *args, **kwargs)
def critical(msg: str, *args, **kwargs) -> None: logger.critical(msg, *args, **kwargs)
