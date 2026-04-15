#!/usr/bin/env python3
"""
AEGIS GEX v1.0 — Production Entry Point
=========================================
Standalone launcher for the AEGIS GEX Dealer Flow Engine bot.
Completely isolated from all other trading strategies.

Usage:
  python3 start_aegis_gex_bot.py

Environment Variables (all optional with sensible defaults):
  TELEGRAM_BOT_TOKEN      — Telegram bot token (required)
  TELEGRAM_CHANNEL_ID     — Signal channel ID (default: @ichimokutradingsignal)
  TELEGRAM_CHAT_ID        — Fallback channel / admin chat
  ADMIN_CHAT_ID           — Admin personal chat for status pings

  GEX_SCAN_INTERVAL_SEC   — Seconds between scan cycles (default: 60)
  GEX_PARALLEL_LIMIT      — Max concurrent Binance requests (default: 20)
  GEX_SYMBOL_REFRESH_SEC  — Symbol universe refresh interval (default: 3600)
  GEX_MIN_CONFIDENCE      — Minimum GEX signal confidence 0-100 (default: 60)
  GEX_PRIMARY_TF          — Primary signal timeframe (default: 1h)
  GEX_CONFIRM_TF          — Confirmation timeframe (default: 4h)
  GEX_MAX_PER_HOUR        — Max signals per hour (default: 12)
  GEX_GLOBAL_GAP_SEC      — Min gap between any two signals (default: 60)
  GEX_SYMBOL_GAP_SEC      — Min gap per symbol (default: 300)
  GEX_DEDUP_MINUTES       — Same-direction dedup window (default: 30)
"""

import asyncio
import logging
import os
import sys
import signal
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────────────────────────────────────

def _setup_logging():
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
# Graceful shutdown
# ─────────────────────────────────────────────────────────────────────────────

_shutdown_event = asyncio.Event()

def _install_signal_handlers(loop: asyncio.AbstractEventLoop):
    def _on_sig(*_):
        logging.getLogger(__name__).info("🛑 Shutdown signal received")
        loop.call_soon_threadsafe(_shutdown_event.set)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _on_sig)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, _on_sig)


# ─────────────────────────────────────────────────────────────────────────────
# Health check (optional keep-alive for Replit uptime monitor)
# ─────────────────────────────────────────────────────────────────────────────

async def _health_server():
    """
    Minimal HTTP health check server on port 8080.
    Responds to GET / with 200 OK to satisfy Replit's uptime monitor.
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

        app.router.add_get("/", _health)
        app.router.add_get("/health", _health)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logging.getLogger(__name__).info(f"💓 Health check server on port {port}")
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

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        log.error("❌ TELEGRAM_BOT_TOKEN is not set. Bot cannot start.")
        ok = False
    else:
        log.info(f"✅ TELEGRAM_BOT_TOKEN present ({token[:10]}…)")

    ch = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    ct = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not ch and not ct:
        log.warning(
            "⚠️  Neither TELEGRAM_CHANNEL_ID nor TELEGRAM_CHAT_ID set. "
            "Defaulting to @ichimokutradingsignal (-1002453842816)."
        )

    tf = os.getenv("GEX_PRIMARY_TF", "1h")
    valid_tfs = {"1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d"}
    if tf not in valid_tfs:
        log.error(f"❌ GEX_PRIMARY_TF '{tf}' is invalid. Use one of: {valid_tfs}")
        ok = False

    conf = os.getenv("GEX_MIN_CONFIDENCE", "60")
    try:
        c = float(conf)
        if not (0 < c <= 100):
            raise ValueError
    except ValueError:
        log.error(f"❌ GEX_MIN_CONFIDENCE must be 0-100. Got: {conf}")
        ok = False

    return ok


# ─────────────────────────────────────────────────────────────────────────────
# Main async entrypoint
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    log = logging.getLogger(__name__)

    log.info("=" * 60)
    log.info("  AEGIS GEX v1.0 — Dealer Flow Engine")
    log.info("  Strategy: GEX Flip Entry + Dynamic TP")
    log.info("  Standalone — isolated from all other bots")
    log.info("=" * 60)

    if not _preflight():
        log.error("Pre-flight checks failed. Exiting.")
        sys.exit(1)

    from aegis_gex.aegis_gex_bot import AEGISGEXBot

    bot    = AEGISGEXBot()
    runner = None

    loop = asyncio.get_event_loop()
    _install_signal_handlers(loop)

    health_task = asyncio.create_task(_health_server())
    bot_task    = asyncio.create_task(bot.run())

    try:
        done, pending = await asyncio.wait(
            {bot_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
    except asyncio.CancelledError:
        log.info("Main task cancelled — shutting down")
    except Exception as e:
        log.error(f"Fatal error in main: {e}", exc_info=True)
    finally:
        if runner:
            try:
                await runner.cleanup()
            except Exception:
                pass
        log.info("✅ AEGIS GEX v1.0 exited")


# ─────────────────────────────────────────────────────────────────────────────
# Auto-restart wrapper — keeps the bot alive on unexpected crashes
# ─────────────────────────────────────────────────────────────────────────────

def _run_with_autorestart():
    """
    Wrap the async main() in a crash-recovery loop.
    Restarts after 15s on any unhandled exception, up to 1000 times.
    """
    import time as _time
    log = logging.getLogger(__name__)
    restart_count = 0
    max_restarts  = 1000

    while restart_count < max_restarts:
        try:
            asyncio.run(main())
            break  # Clean exit
        except KeyboardInterrupt:
            log.info("KeyboardInterrupt — stopping AEGIS GEX v1.0")
            break
        except SystemExit as e:
            log.info(f"SystemExit({e.code})")
            sys.exit(e.code)
        except Exception as e:
            restart_count += 1
            wait = min(15 * restart_count, 120)
            log.error(
                f"💥 Crash #{restart_count}: {e} — restarting in {wait}s",
                exc_info=True,
            )
            _time.sleep(wait)

    if restart_count >= max_restarts:
        log.critical(f"❌ Max restarts ({max_restarts}) reached. Giving up.")
        sys.exit(1)


if __name__ == "__main__":
    _setup_logging()
    _run_with_autorestart()
