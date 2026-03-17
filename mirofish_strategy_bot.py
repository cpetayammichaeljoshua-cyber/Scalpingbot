#!/usr/bin/env python3
"""
mirofish_strategy_bot.py — MiroFish Swarm Intelligence Trading Bot
═══════════════════════════════════════════════════════════════════
Strategy:  MiroFish Multi-Agent Swarm Intelligence
Source:    https://github.com/666ghj/MiroFish
Markets:   ALL Binance USDM Perpetual Futures (≤80 symbols, $50M+ 24h vol)
Timeframe: 15M primary
Channel:   @ichimokutradingsignal | InsiderTactics (Cornix-compatible)

MiroFish Architecture (strictly implemented):
  ✓ Agent Profiles      — Persona / stance / influence_weight / activity_level /
                          sentiment_bias / response_delay / active_sessions
  ✓ Market Ontology     — Entity types: TrendState, PriceLevel, Pattern,
                          Signal, Catalyst, IndicatorState, AgentBelief
  ✓ Graph-State Memory  — Typed nodes + temporal edges (valid_at/invalid_at)
                          500 nodes / 1000 edges with O(1) look-up + auto-pruning
  ✓ InsightForge        — Sub-query decomposition + graph retrieval
  ✓ ReACT Pattern       — Reason → Act → Reflect loop (report_agent.py style)
  ✓ Session Weights     — Asian/EU/US session-aware agent weight multipliers
  ✓ Consensus Emergence — Weighted collective intelligence (simulation_runner)
  ✓ Circuit Breaker     — Exponential backoff + trip/cooldown/recovery
  ✓ Parallel Scanner    — asyncio.gather + Semaphore(20) — all 80 symbols in ~30s
  ✓ Self-Learning       — Neural network trained on resolved trade outcomes
  ✓ Adaptive Threshold  — Confidence gate raised during consecutive loss streaks
  ✓ Symbol Blacklist    — Auto-blocks persistently losing symbols (>70% loss rate)
  ✓ Graceful Shutdown   — SIGTERM/SIGINT handler + full async resource cleanup
"""

# ─────────────────────────────────────────────────────────────────────────────
# Standard Library
# ─────────────────────────────────────────────────────────────────────────────
import os
import sys
import asyncio
import signal
import warnings
import logging
import logging.handlers
import time
import gc
import traceback
import threading
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Warning Suppression  (must be before any third-party imports)
# ─────────────────────────────────────────────────────────────────────────────
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*coroutine.*was never awaited.*")
os.environ["PYTHONWARNINGS"] = (
    "ignore::FutureWarning,ignore::UserWarning,ignore::DeprecationWarning"
)

# ─────────────────────────────────────────────────────────────────────────────
# Path Setup  (SignalMaestro package + repo root)
# ─────────────────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_REPO_ROOT / "SignalMaestro"))
sys.path.insert(0, str(_REPO_ROOT))

# ─────────────────────────────────────────────────────────────────────────────
# ██████████████████  CONFIGURATION  ████████████████████████████████████████
# ─────────────────────────────────────────────────────────────────────────────

# --- Parallel Scanner ----------------------------------------------------------
SCAN_PARALLEL_LIMIT  = int(os.getenv("SCAN_PARALLEL_LIMIT", "20"))   # Semaphore cap
CYCLE_SLEEP_MIN      = int(os.getenv("CYCLE_SLEEP_MIN",     "30"))   # s between rounds (min)
CYCLE_SLEEP_MAX      = int(os.getenv("CYCLE_SLEEP_MAX",     "60"))   # s between rounds (max)
SCAN_INTERVAL_MIN    = 5   # Legacy (kept for env-var backward compatibility)
SCAN_INTERVAL_MAX    = 15

# --- Signal Rate Limiting -----------------------------------------------------
SIGNAL_INTERVAL_MIN      = 120   # minimum seconds between signals on same symbol
SIGNALS_PER_HOUR_MIN     = 5     # strict hourly floor (5/5)
SIGNALS_PER_HOUR_MAX     = 5     # strict hourly cap  (5/5)
GLOBAL_MIN_GAP_SECONDS   = 90    # minimum gap between ANY two signals (all symbols)

# --- AI Confidence Gate -------------------------------------------------------
AI_THRESHOLD_PERCENT = int(os.getenv("AI_THRESHOLD_PERCENT", "80"))  # minimum post-boost %
assert 0 <= AI_THRESHOLD_PERCENT <= 100, (
    f"AI_THRESHOLD_PERCENT must be 0–100, got {AI_THRESHOLD_PERCENT}"
)

# --- Take-Profit Allocation ---------------------------------------------------
TP_ALLOCATION = (45, 35, 20)          # TP1 / TP2 / TP3 percentage splits
assert sum(TP_ALLOCATION) == 100, (
    f"TP_ALLOCATION must sum to 100%, got {sum(TP_ALLOCATION)}%"
)

# --- Leverage -----------------------------------------------------------------
MIN_LEVERAGE = int(os.getenv("MIN_LEVERAGE", "3"))
MAX_LEVERAGE = int(os.getenv("MAX_LEVERAGE", "30"))
assert MIN_LEVERAGE <= MAX_LEVERAGE, (
    f"MIN_LEVERAGE ({MIN_LEVERAGE}) must be ≤ MAX_LEVERAGE ({MAX_LEVERAGE})"
)

# --- Stop-Loss / Take-Profit Percentages (15M ATR-scaled base) ----------------
STOP_LOSS_PERCENT   = 0.65   # base SL % (ATR×1.5 when ATR available)
TAKE_PROFIT_PERCENT = 1.10   # base TP1% (TP2=2.00%, TP3=3.10%)

# --- Swarm Consensus ----------------------------------------------------------
SWARM_MIN_CONSENSUS = 0.72   # 72% weighted agent agreement required

# --- Restart / Circuit Breaker ------------------------------------------------
DEFAULT_MAX_RESTARTS       = int(os.getenv("MAX_RESTARTS",        "100"))
DEFAULT_RESTART_DELAY_BASE = int(os.getenv("RESTART_DELAY_BASE",  "30"))   # seconds
MAX_DELAY_SECONDS          = 300    # hard cap: 5 minutes
CIRCUIT_BREAKER_THRESHOLD  = 5     # trips after N consecutive failures
CIRCUIT_BREAKER_COOLDOWN   = 60    # seconds before recovery attempt
SCANNER_HEARTBEAT_TIMEOUT  = 300   # alert if no heartbeat in 5 minutes

# --- Asyncio ------------------------------------------------------------------
ASYNCIO_DEBUG = os.getenv("ASYNCIO_DEBUG", "").lower() in ("1", "true", "yes")

# --- Optional scanner operation timeout (0 = run forever) --------------------
try:
    _raw = int(os.getenv("SCANNER_TIMEOUT_SECONDS", "0"))
    SCANNER_OPERATION_TIMEOUT: Optional[int] = None if _raw == 0 else _raw
except (ValueError, TypeError):
    SCANNER_OPERATION_TIMEOUT = None

# --- Validation ---------------------------------------------------------------
assert CYCLE_SLEEP_MIN <= CYCLE_SLEEP_MAX,        "CYCLE_SLEEP_MIN must be ≤ CYCLE_SLEEP_MAX"
assert SIGNALS_PER_HOUR_MIN <= SIGNALS_PER_HOUR_MAX, "SIGNALS_PER_HOUR_MIN must be ≤ SIGNALS_PER_HOUR_MAX"
assert DEFAULT_MAX_RESTARTS > 0,                  "MAX_RESTARTS must be > 0"
assert DEFAULT_RESTART_DELAY_BASE > 0,            "RESTART_DELAY_BASE must be > 0"
assert SCAN_PARALLEL_LIMIT >= 1,                  "SCAN_PARALLEL_LIMIT must be ≥ 1"


# ─────────────────────────────────────────────────────────────────────────────
# Logging Setup
# ─────────────────────────────────────────────────────────────────────────────

def _configure_logging() -> None:
    """Configure structured console + optional rotating-file logging."""
    _debug = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")
    level  = logging.DEBUG if _debug else logging.INFO

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)-30s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    # Remove any pre-existing handlers (avoid duplicate log lines on restart)
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()

    # Console handler (always on)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # Optional rotating file handler
    log_file = os.getenv("LOG_FILE", "")
    if log_file:
        try:
            fh = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
            )
            fh.setLevel(level)
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError as e:
            root.warning(f"⚠️  Cannot open log file '{log_file}': {e}")

    # Quiet noisy libraries
    for noisy in ("urllib3", "asyncio", "aiohttp", "httpcore", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


_configure_logging()
_LOG = logging.getLogger("mirofish_bot")


# ─────────────────────────────────────────────────────────────────────────────
# Graceful Shutdown State
# ─────────────────────────────────────────────────────────────────────────────

_SHUTDOWN_REQUESTED = threading.Event()


def _handle_signal(sig_num: int, frame) -> None:  # noqa: ANN001
    """POSIX signal handler — requests graceful shutdown without raising."""
    sig_name = signal.Signals(sig_num).name
    _LOG.info(f"🛑 Signal received: {sig_name} — requesting graceful shutdown")
    _SHUTDOWN_REQUESTED.set()


# Register SIGTERM / SIGINT (SIGINT also raised by KeyboardInterrupt)
signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT,  _handle_signal)


# ─────────────────────────────────────────────────────────────────────────────
# Bot Import  (with robust fallback chain)
# ─────────────────────────────────────────────────────────────────────────────

def _import_bot_class():
    """
    Import FXSUSDTTelegramBot with a three-level fallback chain:
      1. SignalMaestro package import (preferred)
      2. Direct module import from sys.path
      3. Fatal error with actionable message

    Returns the class or raises SystemExit.
    """
    import_errors = []

    # Attempt 1: package-relative
    try:
        from SignalMaestro.fxsusdt_telegram_bot import FXSUSDTTelegramBot
        _LOG.debug("✅ Bot imported via SignalMaestro package")
        return FXSUSDTTelegramBot
    except ImportError as e:
        import_errors.append(f"Package import: {e}")

    # Attempt 2: direct module
    try:
        from fxsusdt_telegram_bot import FXSUSDTTelegramBot  # noqa: F401
        _LOG.debug("✅ Bot imported via direct module path")
        return FXSUSDTTelegramBot
    except ImportError as e:
        import_errors.append(f"Direct import: {e}")

    # Attempt 3: importlib with explicit path
    try:
        import importlib.util
        _bot_file = _REPO_ROOT / "SignalMaestro" / "fxsusdt_telegram_bot.py"
        if not _bot_file.exists():
            raise FileNotFoundError(f"Bot file not found: {_bot_file}")
        spec = importlib.util.spec_from_file_location("fxsusdt_telegram_bot", _bot_file)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _LOG.debug("✅ Bot imported via importlib.util")
        return mod.FXSUSDTTelegramBot
    except Exception as e:
        import_errors.append(f"importlib.util: {e}")

    _LOG.critical("❌ FATAL — Cannot import FXSUSDTTelegramBot:")
    for err in import_errors:
        _LOG.critical(f"   • {err}")
    _LOG.critical(
        "💡 Ensure SignalMaestro/fxsusdt_telegram_bot.py exists and all "
        "dependencies are installed (pip install -r requirements.txt)"
    )
    sys.exit(1)


FXSUSDTTelegramBot = _import_bot_class()


# ─────────────────────────────────────────────────────────────────────────────
# Environment Validation
# ─────────────────────────────────────────────────────────────────────────────

_REQUIRED_ENV_VARS = ["TELEGRAM_BOT_TOKEN", "BINANCE_API_KEY", "BINANCE_API_SECRET"]
_OPTIONAL_AI_VARS  = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]


def _validate_environment() -> bool:
    """
    Check all required secrets exist and log AI key presence (values never logged).

    Returns True if all required vars are set, False otherwise.
    """
    # Required vars
    missing = [v for v in _REQUIRED_ENV_VARS if not os.getenv(v, "").strip()]
    if missing:
        _LOG.error(f"❌ Missing required environment variables: {missing}")
        _LOG.error("   → Set these in the Replit Secrets tab and restart")
        return False

    # AI keys — log presence only
    for key in _OPTIONAL_AI_VARS:
        val = os.getenv(key, "").strip()
        short_name = key.replace("_API_KEY", "")
        status = "✅ configured" if val else "⬜ not set (optional)"
        _LOG.info(f"🤖 {short_name}: {status}")

    return True


def _configure_channel() -> None:
    """
    Resolve and propagate the Telegram signal channel ID.

    Priority:
      1. TELEGRAM_CHANNEL_ID env var (explicit override)
      2. TELEGRAM_CHAT_ID if it looks like a channel (starts with "-")
      3. Hardcoded default: -1002453842816 (@ichimokutradingsignal)
    """
    ch_id  = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    admin  = (os.getenv("TELEGRAM_CHAT_ID", "") or os.getenv("ADMIN_CHAT_ID", "")).strip()

    if ch_id:
        _LOG.info(f"📢 Signal channel (TELEGRAM_CHANNEL_ID): {ch_id}")
    elif admin.startswith("-"):
        os.environ.setdefault("TELEGRAM_CHANNEL_ID", admin)
        _LOG.info(f"📢 Signal channel (from TELEGRAM_CHAT_ID): {admin}")
    else:
        os.environ.setdefault("TELEGRAM_CHANNEL_ID", "-1002453842816")
        _LOG.info("📢 Signal channel (default): -1002453842816 (@ichimokutradingsignal)")

    if admin:
        _LOG.info(f"🔔 Admin chat: {admin}")


def _propagate_env_vars() -> None:
    """
    Propagate launcher configuration constants to child modules via environment
    variables so that all sub-modules read the same values regardless of import
    order.  Uses setdefault where the child module should be able to override.
    """
    os.environ.setdefault("SIGNAL_INTERVAL_SECONDS", str(SIGNAL_INTERVAL_MIN))
    os.environ.setdefault("AI_THRESHOLD_PERCENT",    str(AI_THRESHOLD_PERCENT))
    os.environ.setdefault("SCAN_INTERVAL_MIN",       str(SCAN_INTERVAL_MIN))
    os.environ.setdefault("SCAN_INTERVAL_MAX",       str(SCAN_INTERVAL_MAX))
    os.environ.setdefault("CYCLE_SLEEP_MIN",         str(CYCLE_SLEEP_MIN))
    os.environ.setdefault("CYCLE_SLEEP_MAX",         str(CYCLE_SLEEP_MAX))
    os.environ.setdefault("SCAN_PARALLEL_LIMIT",     str(SCAN_PARALLEL_LIMIT))
    os.environ.setdefault("GLOBAL_MIN_GAP_SECONDS",  str(GLOBAL_MIN_GAP_SECONDS))
    os.environ.setdefault("HEARTBEAT_INTERVAL",      str(SCANNER_HEARTBEAT_TIMEOUT))
    os.environ.setdefault("MIN_LEVERAGE",            str(MIN_LEVERAGE))
    os.environ.setdefault("MAX_LEVERAGE",            str(MAX_LEVERAGE))
    os.environ.setdefault("SWARM_MIN_CONSENSUS",     str(SWARM_MIN_CONSENSUS))
    # Strict hourly cap — always override (never allow child to loosen it)
    os.environ["SIGNALS_PER_HOUR_MAX"] = str(SIGNALS_PER_HOUR_MAX)
    os.environ["SIGNALS_PER_HOUR_MIN"] = str(SIGNALS_PER_HOUR_MIN)


# ─────────────────────────────────────────────────────────────────────────────
# Startup Banner
# ─────────────────────────────────────────────────────────────────────────────

def _print_banner() -> None:
    sep = "=" * 90
    _LOG.info(sep)
    _LOG.info("🐟  MIROFISH SWARM TRADING BOT  —  ALL USDM MARKETS  —  PRODUCTION")
    _LOG.info(sep)
    _LOG.info(f"📊  Markets:     ALL Binance USDM Perpetual Futures  (≤80, $50M+ 24h vol)")
    _LOG.info(f"🐟  Strategy:    MiroFish Multi-Agent Swarm Intelligence")
    _LOG.info(f"                 https://github.com/666ghj/MiroFish")
    _LOG.info(f"⏱️   Timeframe:   15M  (primary swing/scalp)")
    _LOG.info(f"📢  Channel:     @ichimokutradingsignal  |  InsiderTactics")
    _LOG.info(f"📋  Format:      Cornix-compatible signal format")
    _LOG.info(f"🔄  Scanner:     TRUE PARALLEL — {SCAN_PARALLEL_LIMIT} concurrent streams "
              f"(asyncio.gather + Semaphore)")
    _LOG.info("")
    _LOG.info("✅  MIROFISH SWARM AGENTS  (8 agents, 15M-tuned, 100% MiroFish):")
    _LOG.info("   🐟 TrendAgent          EMA 9/21 cross + EMA200 + graph TrendState    (22%w)")
    _LOG.info("   ⚡ MomentumAgent        RSI + MACD + IndicatorState → graph           (20%w)")
    _LOG.info("   📊 VolumeAgent         OBV + vol surge + Catalyst node on 2× spike   (18%w)")
    _LOG.info("   🌊 VolatilityAgent      BB + ATR + PriceLevel nodes (BB_Upper/Lower)  (15%w)")
    _LOG.info("   🕯️  OrderFlowAgent      Candle patterns + Pattern graph nodes          (15%w)")
    _LOG.info("   😱 SentimentAgent       Fear/greed proxy + vol contraction regime     ( 5%w)")
    _LOG.info("   💹 FundingFlowAgent     VWAP deviation + OI proxy + squeeze           ( 5%w)")
    _LOG.info("   🤖 AIOrchestration     Claude 3.5 Haiku → GPT-4o-mini → rule-based   ( 5%w)")
    _LOG.info("                           ReACT: Reason → Act → Reflect → Conclude")
    _LOG.info("")
    _LOG.info("✅  MIROFISH ARCHITECTURE:")
    _LOG.info("   ✓ Agent Profiles      persona / stance / influence_weight / activity_level /")
    _LOG.info("                         sentiment_bias / response_delay / active_sessions")
    _LOG.info("   ✓ Market Ontology     TrendState / PriceLevel / Pattern / Signal /")
    _LOG.info("                         Catalyst / IndicatorState / AgentBelief")
    _LOG.info("   ✓ Graph-State Memory  Typed nodes + temporal edges (valid_at/invalid_at)")
    _LOG.info("                         500 nodes / 1000 edges with O(1) look-up + auto-prune")
    _LOG.info("   ✓ InsightForge        Sub-query decomposition + graph retrieval")
    _LOG.info("   ✓ ReACT Pattern       Reason → Act → Reflect  (report_agent.py)")
    _LOG.info("   ✓ Session Weights     Asian/EU/US session-aware weight multipliers")
    _LOG.info("   ✓ Consensus Emergence Weighted collective intelligence  (simulation_runner)")
    _LOG.info(f"   ✓ Confidence Gate    {AI_THRESHOLD_PERCENT}% post-boost minimum  (pre-boost gate: 64%)")
    _LOG.info("   ✓ Circuit Breaker    Auto-restart with exponential backoff + cooldown")
    _LOG.info(f"   ✓ Multi-Level TP     {TP_ALLOCATION[0]}% / {TP_ALLOCATION[1]}% / {TP_ALLOCATION[2]}%")
    _LOG.info(f"   ✓ Dynamic Leverage   {MIN_LEVERAGE}–{MAX_LEVERAGE}× (BTC-optimised)")
    _LOG.info("   ✓ Self-Learning       Neural network trained on resolved trade outcomes")
    _LOG.info("   ✓ Adaptive Threshold  Confidence gate raised during consecutive loss streaks")
    _LOG.info("   ✓ Symbol Blacklist    Blocks symbols with >70% recent loss rate")
    _LOG.info("")
    _LOG.info("📊  15M SL/TP CONFIGURATION  (ATR-scaled, strictly ordered TP1 < TP2 < TP3):")
    _LOG.info(f"   • Stop Loss:         {STOP_LOSS_PERCENT}%  base  (ATR×1.5 when ATR available)")
    _LOG.info(f"   • Take Profit 1:     {TAKE_PROFIT_PERCENT}%  base  (ATR×2.54 when available)  — TP1")
    _LOG.info("   • Take Profit 2:     2.00% base  (ATR×4.62 when available)  — always > TP1")
    _LOG.info("   • Take Profit 3:     3.10% base  (ATR×7.15 when available)  — always > TP2")
    _LOG.info(f"   • Min Consensus:     {SWARM_MIN_CONSENSUS:.0%} weighted agent agreement")
    _LOG.info("   • Min R:R Ratio:     1.50:1  (signals below this are rejected)")
    _LOG.info(f"   • TP Allocation:     {TP_ALLOCATION[0]}% / {TP_ALLOCATION[1]}% / {TP_ALLOCATION[2]}%")
    _LOG.info("")
    _LOG.info("⚡  TIMING  (TRUE PARALLEL MODE):")
    _LOG.info(f"   • Parallel streams:   {SCAN_PARALLEL_LIMIT} concurrent (asyncio.Semaphore)")
    _LOG.info("   • Full scan time:     ~20–40 s for all 80 symbols  (network-bound)")
    _LOG.info(f"   • Cycle sleep:        {CYCLE_SLEEP_MIN}–{CYCLE_SLEEP_MAX} s between full parallel rounds")
    _LOG.info(f"   • Signal interval:    {SIGNAL_INTERVAL_MIN} s minimum per-symbol cooldown")
    _LOG.info(f"   • Global gap:         {GLOBAL_MIN_GAP_SECONDS} s minimum between any two signals")
    _LOG.info(f"   • Hourly cap:         {SIGNALS_PER_HOUR_MAX}/hr (strict {SIGNALS_PER_HOUR_MIN}/{SIGNALS_PER_HOUR_MAX})")
    _LOG.info(sep)


# ─────────────────────────────────────────────────────────────────────────────
# Delay / Backoff Helpers
# ─────────────────────────────────────────────────────────────────────────────

def calculate_backoff_delay(restart_count: int, base_delay: int) -> int:
    """
    True exponential backoff: delay = base × 2^(restart-1), capped at MAX_DELAY_SECONDS.

    Examples (base=30s): 30 → 60 → 120 → 240 → 300 (cap) → 300 → …

    Args:
        restart_count: number of restarts completed so far (must be ≥ 1)
        base_delay:    base delay in seconds (must be ≥ 1)

    Returns:
        Delay in seconds, always in [base_delay, MAX_DELAY_SECONDS].

    Raises:
        ValueError: if either argument is invalid.
    """
    if not isinstance(restart_count, int) or restart_count < 1:
        raise ValueError(f"restart_count must be a positive int, got {restart_count!r}")
    if not isinstance(base_delay, int) or base_delay < 1:
        raise ValueError(f"base_delay must be a positive int, got {base_delay!r}")

    exponent = min(restart_count - 1, 10)   # cap exponent to avoid overflow
    return min(base_delay * (2 ** exponent), MAX_DELAY_SECONDS)


def _safe_backoff(restart_count: int, base_delay: int, logger: logging.Logger) -> int:
    """calculate_backoff_delay with a fallback to base_delay on bad inputs."""
    try:
        return calculate_backoff_delay(restart_count, base_delay)
    except (ValueError, TypeError) as exc:
        logger.warning(f"⚠️  Backoff calculation error ({exc}) — using base delay {base_delay}s")
        return base_delay


# ─────────────────────────────────────────────────────────────────────────────
# Async Cleanup Helper
# ─────────────────────────────────────────────────────────────────────────────

async def _cleanup_bot(bot, logger: logging.Logger) -> None:
    """
    Gracefully close all async resources held by the bot:
      • BTCUSDTTrader aiohttp session
      • Telegram HTTP session
      • Claude (AsyncAnthropic) client connection pool
      • OpenAI (AsyncOpenAI) client connection pool
    Exceptions are caught and logged — cleanup must never raise.
    """
    if bot is None:
        return

    async def _close(obj, name: str) -> None:
        if obj is None:
            return
        for meth in ("aclose", "close"):
            fn = getattr(obj, meth, None)
            if callable(fn):
                try:
                    result = fn()
                    if asyncio.iscoroutine(result):
                        await result
                    logger.debug(f"🔒 Closed {name}")
                    return
                except Exception as exc:
                    logger.debug(f"⚠️  Close {name}: {exc}")
                    return

    try:
        # Trader aiohttp session
        await _close(getattr(bot, "trader", None), "BTCUSDTTrader.aclose")
        # Telegram session
        await _close(bot, "FXSUSDTTelegramBot.close_tg_session")

        # AI agent clients
        _strategy  = getattr(bot, "strategy", None)
        _ai_agent  = getattr(_strategy,  "ai_agent", None)

        await _close(getattr(_ai_agent, "claude_client", None), "Claude AsyncAnthropic")
        await _close(getattr(_ai_agent, "openai_client", None), "OpenAI AsyncOpenAI")

        # OutcomeTracker (self-learning)
        _tracker = getattr(bot, "outcome_tracker", None)
        if _tracker is not None:
            stop_fn = getattr(_tracker, "stop", None)
            if callable(stop_fn):
                try:
                    r = stop_fn()
                    if asyncio.iscoroutine(r):
                        await r
                    logger.debug("🔒 OutcomeTracker stopped")
                except Exception as exc:
                    logger.debug(f"⚠️  OutcomeTracker.stop: {exc}")

    except Exception as exc:
        logger.warning(f"⚠️  Cleanup encountered an error: {exc}")
    finally:
        # Force-delete the bot reference and collect cycles
        try:
            del bot
        except Exception:
            pass
        gc.collect()
        logger.debug("♻️  GC cycle complete — cleanup done")


# ─────────────────────────────────────────────────────────────────────────────
# Single-Run Async Main
# ─────────────────────────────────────────────────────────────────────────────

async def _run_bot_once() -> bool:
    """
    Initialise and run the MiroFish Swarm Bot for one lifecycle.

    Returns:
        True  — clean exit (user stop, normal completion).
        False — error exit (will be restarted by the launcher).
    """
    logger = logging.getLogger("mirofish_bot.run")
    bot    = None

    # ── Propagate configuration ──────────────────────────────────────────────
    _propagate_env_vars()

    # ── Environment validation ───────────────────────────────────────────────
    if not _validate_environment():
        return False

    # ── Channel resolution ───────────────────────────────────────────────────
    _configure_channel()

    # ── Banner ───────────────────────────────────────────────────────────────
    _print_banner()

    # ── Bot initialisation ───────────────────────────────────────────────────
    logger.info("🔧 Initialising MiroFish Swarm Bot…")
    try:
        bot = FXSUSDTTelegramBot()
        if bot is None:
            logger.error("❌ FXSUSDTTelegramBot() returned None — aborting")
            return False
        logger.info("✅ Bot components initialised successfully")
    except ValueError as exc:
        logger.error(f"❌ Configuration error during init: {exc}")
        return False
    except ImportError as exc:
        logger.error(f"❌ Import error during init: {exc}")
        return False
    except ConnectionError as exc:
        logger.error(f"❌ Connection error during init: {exc}")
        return False
    except MemoryError:
        logger.critical("❌ Out of memory during bot initialisation")
        return False
    except Exception as exc:
        logger.error(
            f"❌ Fatal init failure: {type(exc).__name__}: {exc}\n"
            f"{traceback.format_exc()}"
        )
        return False

    # ── Health check lines ───────────────────────────────────────────────────
    sep = "=" * 90
    logger.info(sep)
    logger.info("✅  ALL SYSTEMS ONLINE — STARTING CONTINUOUS PARALLEL SCANNER")
    logger.info(f"   Heartbeat timeout : {SCANNER_HEARTBEAT_TIMEOUT}s")
    logger.info(f"   Circuit breaker   : {CIRCUIT_BREAKER_THRESHOLD} consecutive failures")
    logger.info(f"   Shutdown flag     : {'set' if _SHUTDOWN_REQUESTED.is_set() else 'clear'}")
    logger.info(sep)

    # ── Check for pre-launch shutdown request ───────────────────────────────
    if _SHUTDOWN_REQUESTED.is_set():
        logger.info("🛑 Shutdown was requested before scanner start — exiting cleanly")
        await _cleanup_bot(bot, logger)
        return True

    # ── Main scanner loop ────────────────────────────────────────────────────
    try:
        if SCANNER_OPERATION_TIMEOUT is not None:
            logger.info(
                f"⏱️  Scanner will run for at most {SCANNER_OPERATION_TIMEOUT}s "
                "(SCANNER_TIMEOUT_SECONDS)"
            )
            await asyncio.wait_for(
                bot.run_continuous_scanner(),
                timeout=SCANNER_OPERATION_TIMEOUT,
            )
        else:
            await bot.run_continuous_scanner()

        logger.info("✅ Scanner completed normally")
        return True

    except asyncio.TimeoutError:
        logger.warning(
            f"⏱️  Scanner timed out after {SCANNER_OPERATION_TIMEOUT}s — "
            "restarting (increase SCANNER_TIMEOUT_SECONDS to disable)"
        )
        return False

    except KeyboardInterrupt:
        logger.info("🛑 KeyboardInterrupt — user-initiated shutdown")
        _SHUTDOWN_REQUESTED.set()
        return True   # user stop = clean exit

    except asyncio.CancelledError:
        logger.info("🔄 Scanner task cancelled")
        return False

    except MemoryError:
        logger.critical("❌ Out of memory in scanner — restarting")
        return False

    except (ConnectionError, OSError) as exc:
        logger.error(f"❌ Network/OS error in scanner: {type(exc).__name__}: {exc}")
        return False

    except RuntimeError as exc:
        # "Event loop is closed" or similar asyncio internals
        logger.error(f"❌ RuntimeError in scanner: {exc}")
        return False

    except Exception as exc:
        logger.error(
            f"❌ Unexpected error in scanner: {type(exc).__name__}: {exc}\n"
            f"{traceback.format_exc()}"
        )
        return False

    finally:
        await _cleanup_bot(bot, logger)


# ─────────────────────────────────────────────────────────────────────────────
# Circuit Breaker  (stateful object for the restart loop)
# ─────────────────────────────────────────────────────────────────────────────

class CircuitBreaker:
    """
    Trips after CIRCUIT_BREAKER_THRESHOLD consecutive failures.
    Remains tripped for CIRCUIT_BREAKER_COOLDOWN seconds, then resets.
    Thread-safe for use from the main launcher thread.
    """

    def __init__(
        self,
        threshold: int = CIRCUIT_BREAKER_THRESHOLD,
        cooldown: int  = CIRCUIT_BREAKER_COOLDOWN,
    ) -> None:
        self.threshold         = threshold
        self.cooldown          = cooldown
        self._consecutive      = 0
        self._tripped          = False
        self._trip_time        = 0.0
        self._lock             = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def record_failure(self) -> bool:
        """Record a failure.  Returns True if the breaker just tripped."""
        with self._lock:
            self._consecutive += 1
            if not self._tripped and self._consecutive >= self.threshold:
                self._tripped   = True
                self._trip_time = time.time()
                return True
            return False

    def record_success(self) -> None:
        """Record a clean run — reset consecutive failure counter."""
        with self._lock:
            self._consecutive = 0
            self._tripped     = False

    @property
    def is_tripped(self) -> bool:
        return self._tripped

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive

    def seconds_until_recovery(self) -> float:
        """Seconds remaining in the cooldown window (0 if already recovered)."""
        if not self._tripped:
            return 0.0
        elapsed = time.time() - self._trip_time
        return max(0.0, self.cooldown - elapsed)

    def try_recover(self) -> bool:
        """
        Attempt recovery after cooldown.  Returns True if the breaker was reset.
        """
        with self._lock:
            if not self._tripped:
                return False
            elapsed = time.time() - self._trip_time
            if elapsed >= self.cooldown:
                _LOG.info(
                    f"🔄 Circuit breaker recovered after {elapsed:.0f}s cooldown "
                    f"({self._consecutive} consecutive failures reset to 0)"
                )
                self._tripped    = False
                self._consecutive = 0
                return True
            return False

    def wait_for_cooldown(self, logger: logging.Logger) -> None:
        """Block (sleeping 1 s at a time) until the cooldown window expires."""
        while True:
            remaining = self.seconds_until_recovery()
            if remaining <= 0:
                break
            logger.warning(
                f"⚠️  Circuit breaker OPEN — recovery in {remaining:.0f}s "
                f"({self._consecutive} consecutive failures)"
            )
            time.sleep(min(1.0, remaining))
        self.try_recover()


# ─────────────────────────────────────────────────────────────────────────────
# Metrics Tracker  (lightweight, thread-safe)
# ─────────────────────────────────────────────────────────────────────────────

class BotMetrics:
    """Track restart statistics for health-monitoring / log reporting."""

    def __init__(self) -> None:
        self._lock           = threading.Lock()
        self.total_runs      = 0
        self.clean_exits     = 0
        self.error_exits     = 0
        self.total_elapsed   = 0.0
        self.start_ts        = time.time()

    def record(self, success: bool, elapsed: float) -> None:
        with self._lock:
            self.total_runs    += 1
            self.total_elapsed += elapsed
            if success:
                self.clean_exits  += 1
            else:
                self.error_exits  += 1

    def summary(self) -> str:
        with self._lock:
            uptime = time.time() - self.start_ts
            avg    = self.total_elapsed / self.total_runs if self.total_runs else 0.0
            return (
                f"runs={self.total_runs} clean={self.clean_exits} "
                f"errors={self.error_exits} "
                f"avg_runtime={avg:.0f}s total_uptime={uptime:.0f}s"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Launcher  (restart loop with circuit breaker + backoff)
# ─────────────────────────────────────────────────────────────────────────────

def _new_event_loop() -> asyncio.AbstractEventLoop:
    """Create a fresh event loop, enabling asyncio debug mode if requested."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    if ASYNCIO_DEBUG:
        loop.set_debug(True)
        _LOG.info("🐛 asyncio debug mode ENABLED (ASYNCIO_DEBUG=1)")
    return loop


def main_launcher() -> None:
    """
    Production launcher with:
      • Exponential backoff restart (capped at MAX_DELAY_SECONDS)
      • Circuit breaker (trips after N consecutive failures, cooldown C seconds)
      • Graceful shutdown on SIGTERM / SIGINT / _SHUTDOWN_REQUESTED flag
      • Per-run metrics tracking and console reporting
      • Fresh asyncio event loop each run (avoids 'loop is closed' residue)
    """
    logger = logging.getLogger("mirofish_bot.launcher")

    logger.info("🐟  MiroFish Strategy Bot Launcher  —  Production Ready")
    logger.info(f"📊  Markets: ALL Binance USDM Perpetual Futures "
                f"(PARALLEL, ≤80 symbols, Semaphore={SCAN_PARALLEL_LIMIT})")
    logger.info(f"📋  Config:  max_restarts={DEFAULT_MAX_RESTARTS}  "
                f"base_delay={DEFAULT_RESTART_DELAY_BASE}s  "
                f"circuit_breaker={CIRCUIT_BREAKER_THRESHOLD}/{CIRCUIT_BREAKER_COOLDOWN}s")

    breaker  = CircuitBreaker()
    metrics  = BotMetrics()
    restarts = 0

    while restarts < DEFAULT_MAX_RESTARTS and not _SHUTDOWN_REQUESTED.is_set():

        # ── Circuit breaker cooldown ─────────────────────────────────────────
        if breaker.is_tripped:
            breaker.wait_for_cooldown(logger)
            if _SHUTDOWN_REQUESTED.is_set():
                break
            if not breaker.try_recover():
                # Still tripped (shouldn't happen after wait_for_cooldown)
                time.sleep(1)
                continue

        # ── Launch attempt ───────────────────────────────────────────────────
        restarts += 1
        logger.info(
            f"🎯  Starting bot  (attempt #{restarts}/{DEFAULT_MAX_RESTARTS}  "
            f"consecutive_failures={breaker.consecutive_failures})"
        )

        run_start = time.time()
        success   = False

        try:
            loop    = _new_event_loop()
            success = loop.run_until_complete(_run_bot_once())
        except KeyboardInterrupt:
            logger.info("🛑 Manual shutdown (Ctrl+C) — exiting cleanly")
            _SHUTDOWN_REQUESTED.set()
            break
        except MemoryError:
            logger.critical(f"❌ MemoryError on attempt #{restarts} — will retry")
        except Exception as exc:
            logger.error(
                f"💥 Unhandled launcher exception #{restarts}: "
                f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            )
        finally:
            elapsed = time.time() - run_start
            metrics.record(success, elapsed)
            try:
                loop.close()
            except Exception:
                pass
            gc.collect()

        # ── Post-run evaluation ──────────────────────────────────────────────
        if _SHUTDOWN_REQUESTED.is_set():
            logger.info(
                f"🛑 Shutdown requested — stopping launcher  ({metrics.summary()})"
            )
            break

        if success:
            breaker.record_success()
            logger.info(
                f"✅ Bot completed cleanly in {elapsed:.1f}s  ({metrics.summary()})"
            )
            break  # Clean exit — no restart needed

        # Error exit — check circuit breaker
        just_tripped = breaker.record_failure()

        if just_tripped:
            logger.error(
                f"🔴 Circuit breaker TRIPPED after "
                f"{breaker.consecutive_failures} consecutive failures  "
                f"— cooling down for {CIRCUIT_BREAKER_COOLDOWN}s"
            )
            # Cooldown is handled at the top of the loop
            continue

        if restarts >= DEFAULT_MAX_RESTARTS:
            logger.error(
                f"❌ Maximum restart limit ({DEFAULT_MAX_RESTARTS}) reached  "
                f"— giving up.  ({metrics.summary()})"
            )
            break

        delay = _safe_backoff(restarts, DEFAULT_RESTART_DELAY_BASE, logger)
        logger.warning(
            f"⚠️  Bot exited with error on attempt #{restarts}/{DEFAULT_MAX_RESTARTS}  "
            f"(runtime={elapsed:.1f}s  {metrics.summary()})  "
            f"— restarting in {delay}s…"
        )

        # Interruptible sleep
        _wait_interruptible(delay)

        if _SHUTDOWN_REQUESTED.is_set():
            logger.info("🛑 Shutdown requested during restart delay — exiting")
            break

    logger.info(f"✅  MiroFish Bot Launcher stopped  ({metrics.summary()})")


def _wait_interruptible(seconds: float) -> None:
    """Sleep for `seconds` in 1-second ticks, stopping early on shutdown."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _SHUTDOWN_REQUESTED.is_set():
            return
        time.sleep(min(1.0, deadline - time.time()))


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        main_launcher()
    except KeyboardInterrupt:
        print("\n\n🛑 Launcher interrupted by user (Ctrl+C)")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"\n\n❌ Fatal launcher error: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        sys.exit(1)
