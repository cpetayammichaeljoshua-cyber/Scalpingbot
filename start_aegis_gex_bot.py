#!/usr/bin/env python3
"""
AEGIS GEX v1.0 — Production Entry Point
=========================================
Standalone launcher for the AEGIS GEX Dealer Flow Engine bot.
Completely isolated from all other trading strategies.

Usage:
  python3 start_aegis_gex_bot.py

Environment Variables (all optional with sensible defaults):
  TELEGRAM_BOT_TOKEN      — Telegram bot token (REQUIRED)
  TELEGRAM_CHANNEL_ID     — Signal channel ID (default: -1002453842816)
  TELEGRAM_CHAT_ID        — Fallback channel / admin chat
  ADMIN_CHAT_ID           — Admin personal chat for status pings

  GEX_SCAN_INTERVAL_SEC   — Seconds between scan cycles (default: 30)
  GEX_PARALLEL_LIMIT      — Max concurrent Binance requests (default: 30)
  GEX_SYMBOL_REFRESH_SEC  — Symbol universe refresh interval (default: 3600)
  GEX_MIN_CONFIDENCE      — Minimum GEX signal confidence 0-100 (default: 68)
  GEX_MIN_DGRP            — Minimum DGRP score (default: 40)
  GEX_PRIMARY_TF          — Primary signal timeframe (default: 5m)
  GEX_CONFIRM_TF          — Confirmation timeframe (default: 15m)
  GEX_MAX_PER_HOUR        — Max signals per hour (default: 15)
  GEX_GLOBAL_GAP_SEC      — Min gap between any two signals (default: 45)
  GEX_SYMBOL_GAP_SEC      — Min gap per symbol (default: 300)
  GEX_DEDUP_MINUTES       — Same-direction dedup window (default: 20)

  GEX_SL_ABS_FLOOR        — Absolute SL noise floor (default: 0.0005 = 0.05%)
  GEX_SL_ABS_CAP          — Absolute SL hard safety cap (default: 0.0050 = 0.50%)
  GEX_SL_FLOOR_ATR        — Min SL = N × ATR (default: 0.40)
  GEX_SL_BUDGET_ATR       — Max SL = N × ATR (default: 1.20)
  GEX_TP_RR1              — TP1 R:R multiplier (default: 3.0 → 3× SL risk)
  GEX_TP_RR2              — TP2 R:R multiplier (default: 6.0 → 6× SL risk)
  GEX_TP_RR3              — TP3 R:R multiplier (default: 9.0 → 9× SL risk)
  GEX_LEV_RISK_PCT        — Max account risk per trade for lev cap (default: 0.015 = 1.5%)

  GEX_HEALTH_PORT         — HTTP health check port (default: 8080)
  LOG_LEVEL               — Logging verbosity (default: INFO)
  LOG_DIR                 — Log file directory (default: .)
"""

import asyncio
import logging
import os
import sys
import signal as _signal
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────────────────────────────────────

def _setup_logging() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    numeric   = getattr(logging, log_level, logging.INFO)

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.setLevel(numeric)

    log_dir = os.getenv("LOG_DIR", ".")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "aegis_gex.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(numeric)

    root = logging.getLogger()
    root.setLevel(numeric)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)

    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


# ─────────────────────────────────────────────────────────────────────────────
# Health check server (Replit uptime monitor keep-alive)
# ─────────────────────────────────────────────────────────────────────────────

async def _health_server():
    """
    Minimal HTTP health check on port GEX_HEALTH_PORT (default 8080).
    Responds to GET / and GET /health with 200 OK.
    Returns the aiohttp AppRunner for proper cleanup.
    """
    try:
        from aiohttp import web
        port = int(os.getenv("GEX_HEALTH_PORT", "8080"))

        app = web.Application()

        async def _health(request):
            return web.Response(
                text=(
                    f"AEGIS GEX v1.0 OK | "
                    f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                ),
                content_type="text/plain",
            )

        app.router.add_get("/",       _health)
        app.router.add_get("/health", _health)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logging.getLogger(__name__).info(
            f"💓 Health check server listening on port {port}"
        )
        return runner
    except Exception as e:
        logging.getLogger(__name__).warning(f"Health server unavailable: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Pre-flight checks
# ─────────────────────────────────────────────────────────────────────────────

def _preflight() -> bool:
    """Validate critical environment variables before starting."""
    log = logging.getLogger(__name__)
    ok  = True

    # TELEGRAM_BOT_TOKEN — required
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        log.error("❌ TELEGRAM_BOT_TOKEN is not set. Bot cannot start.")
        ok = False
    else:
        log.info(f"✅ TELEGRAM_BOT_TOKEN present ({token[:10]}…)")

    # Channel / chat
    ch = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    ct = os.getenv("TELEGRAM_CHAT_ID",    "").strip()
    if not ch and not ct:
        log.warning(
            "⚠️  Neither TELEGRAM_CHANNEL_ID nor TELEGRAM_CHAT_ID set. "
            "Using default: -1002453842816"
        )

    # Timeframe validation — default is 5m (matching AEGISGEXBot.PRIMARY_TF)
    tf = os.getenv("GEX_PRIMARY_TF", "5m")
    valid_tfs = {"1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d"}
    if tf not in valid_tfs:
        log.error(f"❌ GEX_PRIMARY_TF '{tf}' is invalid. Use one of: {sorted(valid_tfs)}")
        ok = False
    else:
        log.info(f"✅ GEX_PRIMARY_TF = {tf}")

    # Confidence — default is 68 (matching AEGISGEXBot.MIN_CONF)
    conf_str = os.getenv("GEX_MIN_CONFIDENCE", "68")
    try:
        c = float(conf_str)
        if not (0 < c <= 100):
            raise ValueError
        log.info(f"✅ GEX_MIN_CONFIDENCE = {c:.0f}%")
    except ValueError:
        log.error(f"❌ GEX_MIN_CONFIDENCE must be 0-100. Got: {conf_str}")
        ok = False

    # ATR-adaptive SL / R:R sanity
    try:
        sl_floor = float(os.getenv("GEX_SL_ABS_FLOOR",  "0.0005"))
        sl_cap   = float(os.getenv("GEX_SL_ABS_CAP",    "0.0050"))
        rr1      = float(os.getenv("GEX_TP_RR1",        "3.0"))
        rr2      = float(os.getenv("GEX_TP_RR2",        "6.0"))
        rr3      = float(os.getenv("GEX_TP_RR3",        "9.0"))
        sl_f_atr = float(os.getenv("GEX_SL_FLOOR_ATR",  "0.40"))
        sl_b_atr = float(os.getenv("GEX_SL_BUDGET_ATR", "1.20"))
        if sl_floor <= 0 or sl_cap <= 0 or sl_floor >= sl_cap:
            raise ValueError("SL floor must be positive and less than SL cap")
        if rr1 < 2.0:
            raise ValueError(f"GEX_TP_RR1={rr1} must be ≥ 2.0")
        log.info(
            f"✅ SL=ATR×{sl_f_atr:.2f}–{sl_b_atr:.2f} "
            f"(floor {sl_floor*100:.2f}%, cap {sl_cap*100:.2f}%)  "
            f"TP1={rr1:.1f}×risk  TP2={rr2:.1f}×risk  TP3={rr3:.1f}×risk"
        )
    except (ValueError, ZeroDivisionError) as e:
        log.error(f"❌ ATR-adaptive SL/TP config invalid: {e}")
        ok = False

    return ok


# ─────────────────────────────────────────────────────────────────────────────
# Main async entrypoint
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    log = logging.getLogger(__name__)

    log.info("=" * 60)
    log.info("  AEGIS GEX v1.0 — Dealer Flow Engine")
    log.info("  5m Scalp: SL ATR-adaptive | TP 3×/6×/9× risk | ≥3:1 R:R")
    log.info("  Standalone — isolated from all other bots")
    log.info("=" * 60)

    if not _preflight():
        log.error("Pre-flight checks failed. Exiting.")
        sys.exit(1)

    from aegis_gex.aegis_gex_bot import AEGISGEXBot

    bot    = AEGISGEXBot()
    runner = None

    # ── Graceful shutdown event — created inside the running loop ─────────────
    # IMPORTANT: asyncio.Event() must be created inside an async context so it
    # binds to the current event loop (Python 3.10+ strict requirement).
    shutdown_event = asyncio.Event()

    def _on_shutdown_signal(*_):
        log.info("🛑 Shutdown signal received — cancelling bot")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (_signal.SIGTERM, _signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _on_shutdown_signal)
        except (NotImplementedError, RuntimeError):
            # Windows / environments that don't support loop signal handlers
            _signal.signal(sig, _on_shutdown_signal)

    # ── Start health server ───────────────────────────────────────────────────
    runner = await _health_server()

    # ── Run bot + shutdown watcher concurrently ───────────────────────────────
    bot_task      = asyncio.create_task(bot.run(),      name="aegis_gex_bot")
    shutdown_task = asyncio.create_task(shutdown_event.wait(), name="shutdown_watcher")

    try:
        done, pending = await asyncio.wait(
            {bot_task, shutdown_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel all remaining tasks cleanly
        for t in pending:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

        # Propagate any bot exception
        for t in done:
            exc = t.exception() if not t.cancelled() else None
            if exc:
                log.error(f"Bot task raised: {exc}", exc_info=exc)

    except asyncio.CancelledError:
        log.info("Main task cancelled — initiating graceful shutdown")
        bot_task.cancel()
        try:
            await bot_task
        except (asyncio.CancelledError, Exception):
            pass
    except Exception as e:
        log.error(f"Fatal error in main: {e}", exc_info=True)
    finally:
        if runner is not None:
            try:
                await runner.cleanup()
                log.info("Health server cleaned up")
            except Exception:
                pass
        log.info("✅ AEGIS GEX v1.0 — clean exit")


# ─────────────────────────────────────────────────────────────────────────────
# Auto-restart wrapper — keeps bot alive through crashes
# ─────────────────────────────────────────────────────────────────────────────

def _run_with_autorestart() -> None:
    """
    Wrap async main() in a crash-recovery loop.
    Uses capped exponential back-off: 15s → 30s → 45s … → 120s max.
    Stops after 1000 restarts (prevents infinite loops in fatal config errors).
    """
    import time as _time
    log           = logging.getLogger(__name__)
    restart_count = 0
    max_restarts  = 1000

    while restart_count < max_restarts:
        try:
            asyncio.run(main())
            log.info("Bot exited cleanly — not restarting")
            break
        except KeyboardInterrupt:
            log.info("KeyboardInterrupt — stopping AEGIS GEX v1.0")
            break
        except SystemExit as e:
            if e.code == 0:
                log.info("SystemExit(0) — clean exit")
            else:
                log.error(f"SystemExit({e.code}) — stopping")
                sys.exit(e.code)
            break
        except Exception as e:
            restart_count += 1
            # Capped linear back-off: 15 * n but no more than 120s
            wait = min(15 * restart_count, 120)
            log.error(
                f"💥 Crash #{restart_count}/{max_restarts}: {e} — "
                f"restarting in {wait}s",
                exc_info=True,
            )
            _time.sleep(wait)

    if restart_count >= max_restarts:
        log.critical(f"❌ Max restarts ({max_restarts}) reached. Exiting permanently.")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    _setup_logging()
    _run_with_autorestart()
