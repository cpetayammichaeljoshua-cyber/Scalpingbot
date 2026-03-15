#!/usr/bin/env python3
"""
Ultimate Trading Bot Launcher — MiroFish Swarm Edition
Trades BTCUSDT Perpetual Futures (Binance USDM)
Strategy: MiroFish Multi-Agent Swarm Intelligence (github.com/666ghj/MiroFish)
Comprehensive error handling, circuit breaker, exponential backoff restart.
"""

import os
import sys
import asyncio
import warnings
import logging
import time
from pathlib import Path

# ─────────────────────────────────────────────
# Configuration Constants
# ─────────────────────────────────────────────
SCAN_INTERVAL_MIN = 5        # Legacy — kept for backward compatibility (not used in parallel mode)
SCAN_INTERVAL_MAX = 15
assert SCAN_INTERVAL_MIN <= SCAN_INTERVAL_MAX, "SCAN_INTERVAL_MIN must be <= SCAN_INTERVAL_MAX"

# Parallel scanner inter-cycle sleep: all 80 symbols scanned simultaneously per cycle.
# Each cycle completes in ~20-40 seconds (network-bound, Semaphore=20 concurrent scans).
# CYCLE_SLEEP adds breathing room between full rounds before the next one starts.
CYCLE_SLEEP_MIN = 30   # seconds between full parallel scan cycles (minimum)
CYCLE_SLEEP_MAX = 60   # seconds between full parallel scan cycles (maximum)
assert CYCLE_SLEEP_MIN <= CYCLE_SLEEP_MAX, "CYCLE_SLEEP_MIN must be <= CYCLE_SLEEP_MAX"

# Maximum concurrent symbol scans within a single parallel cycle (Semaphore limit)
SCAN_PARALLEL_LIMIT = 20   # 20 concurrent Binance REST requests (well within rate limits)

SIGNAL_INTERVAL_MIN = 120  # 120s minimum between signals on 15m timeframe

SIGNALS_PER_HOUR_MIN = 5   # Strict global hourly floor (5/5)
SIGNALS_PER_HOUR_MAX = 5   # Strict global hourly cap  (5/5)
assert SIGNALS_PER_HOUR_MIN <= SIGNALS_PER_HOUR_MAX, "SIGNALS_PER_HOUR_MIN must be <= SIGNALS_PER_HOUR_MAX"

AI_THRESHOLD_PERCENT = 80  # Minimum confidence % required to send a signal (post-boost)
assert 0 <= AI_THRESHOLD_PERCENT <= 100, f"AI_THRESHOLD_PERCENT must be 0-100, got {AI_THRESHOLD_PERCENT}"

TP_ALLOCATION = (45, 35, 20)  # TP1/TP2/TP3 percentage allocations
assert sum(TP_ALLOCATION) == 100, f"TP_ALLOCATION must sum to 100%, got {sum(TP_ALLOCATION)}%"

MAX_LEVERAGE = 30          # Conservative max for BTC 15M (lower leverage on higher TF)
MIN_LEVERAGE = 3
assert MIN_LEVERAGE <= MAX_LEVERAGE, f"MIN_LEVERAGE ({MIN_LEVERAGE}) must be <= MAX_LEVERAGE ({MAX_LEVERAGE})"

# 15M-tuned SL/TP — ATR-scaled, strictly ordered TP1 < TP2 < TP3
# All levels computed consistently from the same ATR multiplier base:
#   SL   = max(ATR×1.5,  price×0.65%)
#   TP1  = max(ATR×1.5×(1.10/0.65), price×1.10%)
#   TP2  = max(ATR×1.5×(2.00/0.65), price×2.00%)  — always > TP1
#   TP3  = max(ATR×1.5×(3.10/0.65), price×3.10%)  — always > TP2
STOP_LOSS_PERCENT   = 0.65  # BTC 15M base SL %
TAKE_PROFIT_PERCENT = 1.10  # BTC 15M TP1 % (TP2=2.00%, TP3=3.10%)

SWARM_MIN_CONSENSUS = 0.72  # Minimum agent agreement (72%) to generate a signal

DEFAULT_MAX_RESTARTS     = 100
DEFAULT_RESTART_DELAY_BASE = 30
MAX_DELAY_SECONDS        = 300   # Hard cap: 5-minute delay max
ASYNCIO_TIMEOUT_SECONDS  = 3600  # 1-hour health check window

# Scanner operation timeout — None = continuous (no timeout)
try:
    SCANNER_OPERATION_TIMEOUT = int(os.getenv("SCANNER_TIMEOUT_SECONDS", "0"))
    if SCANNER_OPERATION_TIMEOUT == 0:
        SCANNER_OPERATION_TIMEOUT = None  # Default: no timeout
except (ValueError, TypeError):
    SCANNER_OPERATION_TIMEOUT = None

CIRCUIT_BREAKER_THRESHOLD = 5   # Trips after 5 consecutive failures
CIRCUIT_BREAKER_COOLDOWN  = 60  # Wait 60s before recovery attempt
SCANNER_HEARTBEAT_TIMEOUT = 300  # Alert if no heartbeat in 5 minutes

# ─────────────────────────────────────────────
# Warning Suppression
# ─────────────────────────────────────────────
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
os.environ["PYTHONWARNINGS"] = "ignore::FutureWarning,ignore::UserWarning,ignore::DeprecationWarning"

# ─────────────────────────────────────────────
# Path Setup
# ─────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent / "SignalMaestro"))
sys.path.insert(0, os.path.dirname(__file__))

# ─────────────────────────────────────────────
# Import Bot
# ─────────────────────────────────────────────
try:
    from SignalMaestro.fxsusdt_telegram_bot import FXSUSDTTelegramBot
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("🔧 Attempting fallback import...")
    try:
        from fxsusdt_telegram_bot import FXSUSDTTelegramBot
    except ImportError as e2:
        print(f"❌ Fatal Import Error: {e2}")
        sys.exit(1)

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
log_level = logging.DEBUG if os.getenv("DEBUG", "").lower() in ("1", "true", "yes") else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


# ─────────────────────────────────────────────
# Main Async Bot Runner
# ─────────────────────────────────────────────

async def main():
    """Main entry point — initializes and runs the MiroFish Swarm Bot"""
    logger = logging.getLogger(__name__)

    # Propagate launcher constants to env vars for child modules
    os.environ.setdefault("SIGNAL_INTERVAL_SECONDS", str(SIGNAL_INTERVAL_MIN))
    os.environ.setdefault("AI_THRESHOLD_PERCENT",    str(AI_THRESHOLD_PERCENT))
    os.environ.setdefault("SCAN_INTERVAL_MIN",       str(SCAN_INTERVAL_MIN))
    os.environ.setdefault("SCAN_INTERVAL_MAX",       str(SCAN_INTERVAL_MAX))
    # Parallel scanner env vars
    os.environ.setdefault("CYCLE_SLEEP_MIN",         str(CYCLE_SLEEP_MIN))
    os.environ.setdefault("CYCLE_SLEEP_MAX",         str(CYCLE_SLEEP_MAX))
    os.environ.setdefault("SCAN_PARALLEL_LIMIT",     str(SCAN_PARALLEL_LIMIT))
    # Hourly signal cap — strictly 5/5 (propagated to bot __init__)
    os.environ["SIGNALS_PER_HOUR_MAX"] = str(SIGNALS_PER_HOUR_MAX)
    os.environ["SIGNALS_PER_HOUR_MIN"] = str(SIGNALS_PER_HOUR_MIN)
    # Heartbeat interval — propagate launcher constant so scanner reads it
    os.environ.setdefault("HEARTBEAT_INTERVAL",      str(SCANNER_HEARTBEAT_TIMEOUT))
    # AI keys — log presence (never log values)
    _anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    _openai_key    = os.getenv("OPENAI_API_KEY", "").strip()
    logger.info(
        f"🤖 AI keys: Claude={'✅ CONFIGURED' if _anthropic_key else '❌ missing'} | "
        f"OpenAI={'✅ configured' if _openai_key else '⬜ not set (optional)'}"
    )
    del _anthropic_key, _openai_key  # never keep key values in scope

    # Verify required environment variables
    required_vars = ["TELEGRAM_BOT_TOKEN", "BINANCE_API_KEY", "BINANCE_API_SECRET"]
    missing = [v for v in required_vars if not os.getenv(v, "")]
    if missing:
        logger.error(f"❌ Missing critical env vars: {missing}")
        return False

    # ── Startup Banner ──
    logger.info("=" * 90)
    logger.info("🐟 MIROFISH SWARM TRADING BOT v4 — ALL USDM MARKETS — PRODUCTION DEPLOYMENT")
    logger.info("=" * 90)
    logger.info("📊 Markets:    ALL Binance USDM Perpetual Futures (up to 80, $50M+ 24h vol)")
    logger.info("🐟 Strategy:   MiroFish Multi-Agent Swarm Intelligence")
    logger.info("               github.com/666ghj/MiroFish")
    logger.info("⏱️  Timeframe:  15M (primary swing/scalp timeframe)")
    logger.info("📢 Channel:    @ichimokutradingsignal | InsiderTactics")
    logger.info("📋 Format:     Cornix-compatible signal format")
    logger.info(f"🔄 Scanner:    TRUE PARALLEL — {SCAN_PARALLEL_LIMIT} concurrent streams (asyncio.gather + Semaphore)")
    logger.info("")
    logger.info("✅ MIROFISH SWARM AGENTS (8 agents, 15M-tuned) — 100% MiroFish Architecture:")
    logger.info("   🐟 TrendAgent        — EMA 9/21 crossover + EMA200 + graph TrendState node    (22% w)")
    logger.info("   ⚡ MomentumAgent      — RSI + MACD + IndicatorState node → graph              (20% w)")
    logger.info("   📊 VolumeAgent       — OBV + vol surge + Catalyst node on 2x spike            (18% w)")
    logger.info("   🌊 VolatilityAgent    — BB + ATR + PriceLevel nodes (BB_Upper/Lower)          (15% w)")
    logger.info("   🕯️  OrderFlowAgent    — Candle patterns + Pattern graph nodes                 (15% w)")
    logger.info("   😱 SentimentAgent     — Fear/greed proxy + vol contraction regime             ( 5% w)")
    logger.info("   💹 FundingFlowAgent   — VWAP deviation + OI proxy + squeeze detection        ( 5% w)")
    logger.info("   🤖 AIOrchestration   — Claude 3.5 Haiku (primary) + GPT-4o-mini (fallback)   ( 5% w)")
    logger.info("                          ReACT: Reason → Act → Reflect → Conclude")
    logger.info("")
    logger.info("✅ MIROFISH ARCHITECTURE (github.com/666ghj/MiroFish):")
    logger.info("   ✓ Agent Profiles      — Each agent: persona, stance, influence_weight,")
    logger.info("                           activity_level, sentiment_bias, active_sessions")
    logger.info("   ✓ Market Ontology     — Entity types: TrendState, PriceLevel, Pattern,")
    logger.info("                           Signal, Catalyst, IndicatorState, AgentBelief")
    logger.info("   ✓ Graph-State Memory  — Typed nodes + temporal edges (valid_at/invalid_at)")
    logger.info("                           500 nodes / 1000 edges with auto-pruning")
    logger.info("   ✓ InsightForge        — Sub-query decomposition + graph retrieval (zep_tools)")
    logger.info("   ✓ ReACT Pattern       — AI: Reason → Act → Reflect (report_agent.py style)")
    logger.info("   ✓ Session Weights     — Asian/EU/US session-aware agent weight multipliers")
    logger.info("   ✓ Consensus Emergence — Weighted collective intelligence (simulation_runner)")
    logger.info(f"  ✓ Confidence Gate     — {AI_THRESHOLD_PERCENT}% minimum post-boost (pre-boost gate: 64%)")
    logger.info("   ✓ Circuit Breaker     — Auto-restart with exponential backoff")
    logger.info(f"  ✓ Multi-Level TP      — {TP_ALLOCATION[0]}% / {TP_ALLOCATION[1]}% / {TP_ALLOCATION[2]}%")
    logger.info(f"  ✓ Dynamic Leverage    — {MIN_LEVERAGE}–{MAX_LEVERAGE}x (BTC-optimized)")
    logger.info("")
    logger.info("📊 15M SL/TP CONFIGURATION (ATR-scaled, strictly ordered TP1<TP2<TP3):")
    logger.info(f"   • Stop Loss:       {STOP_LOSS_PERCENT}%  base (ATR×1.5 when ATR available)")
    logger.info(f"   • Take Profit 1:   {TAKE_PROFIT_PERCENT}%  base (ATR×2.54 when ATR available)")
    logger.info("   • Take Profit 2:   2.00% base (ATR×4.62 when ATR available) — always > TP1")
    logger.info("   • Take Profit 3:   3.10% base (ATR×7.15 when ATR available) — always > TP2")
    logger.info(f"   • Min Consensus:   {SWARM_MIN_CONSENSUS:.0%} agent agreement (weighted, was 62%)")
    logger.info(f"   • Min R:R Ratio:   1.50:1 (any signal below this is rejected, was 1.30)")
    logger.info(f"   • TP Allocation:   {TP_ALLOCATION[0]}% / {TP_ALLOCATION[1]}% / {TP_ALLOCATION[2]}%")
    logger.info("")
    logger.info("⚡ TIMING (PARALLEL MODE):")
    logger.info(f"   • Parallel streams:   {SCAN_PARALLEL_LIMIT} concurrent (asyncio.Semaphore)")
    logger.info(f"   • Full scan time:     ~20-40s for all 80 symbols")
    logger.info(f"   • Cycle sleep:        {CYCLE_SLEEP_MIN}–{CYCLE_SLEEP_MAX}s between full parallel rounds")
    logger.info(f"   • Signal Interval:    {SIGNAL_INTERVAL_MIN}s minimum per-symbol cooldown")
    logger.info(f"   • Est. Signals/Hour:  {SIGNALS_PER_HOUR_MIN} (strict 5/5 hourly cap)")
    logger.info("=" * 90)

    # ── Initialize Bot ──
    logger.info("🔧 Initializing MiroFish Swarm Bot...")
    bot = None
    try:
        bot = FXSUSDTTelegramBot()
        if bot is None:
            logger.error("❌ Bot initialization returned None")
            return False
        logger.info("✅ Bot components initialized successfully")
    except ImportError as e:
        logger.error(f"❌ Import Error: {e}")
        return False
    except ConnectionError as e:
        logger.error(f"❌ Connection Error: {e}")
        return False
    except ValueError as e:
        logger.error(f"❌ Configuration Error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Critical init failure: {type(e).__name__}: {e}")
        return False

    logger.info("=" * 90)
    logger.info("✅ ALL SYSTEMS ONLINE — STARTING CONTINUOUS SCANNER")
    logger.info(f"   Heartbeat timeout: {SCANNER_HEARTBEAT_TIMEOUT}s")
    logger.info(f"   Circuit breaker:   {CIRCUIT_BREAKER_THRESHOLD} consecutive failures")
    logger.info("=" * 90)

    try:
        if SCANNER_OPERATION_TIMEOUT is not None:
            await asyncio.wait_for(
                bot.run_continuous_scanner(),
                timeout=SCANNER_OPERATION_TIMEOUT
            )
        else:
            await bot.run_continuous_scanner()

        logger.info("✅ Scanner completed successfully")
        return True

    except asyncio.TimeoutError:
        logger.error(f"❌ Scanner timed out after {SCANNER_OPERATION_TIMEOUT}s — restarting")
        return False
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
        return True  # User stop = clean exit
    except RuntimeError as e:
        logger.error(f"❌ RuntimeError in scanner: {e}")
        return False
    except asyncio.CancelledError:
        logger.info("🔄 Bot task cancelled")
        return False
    except (ConnectionError, OSError) as e:
        logger.error(f"❌ Network/OS error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Fatal scanner error: {type(e).__name__}: {e}")
        logger.debug("Full traceback:", exc_info=True)
        return False
    finally:
        if bot is not None:
            try:
                # Gracefully close async HTTP sessions before garbage-collecting bot
                await bot.trader.aclose()
                await bot.close_tg_session()

                _ai_agent = getattr(
                    getattr(bot, "strategy", None), "ai_agent", None
                )
                # Close Claude (AsyncAnthropic) client HTTP pool
                _claude = getattr(_ai_agent, "claude_client", None)
                if _claude is not None:
                    try:
                        await _claude.close()
                    except Exception:
                        pass

                # Close OpenAI (AsyncOpenAI) client HTTP pool
                _openai = getattr(_ai_agent, "openai_client", None)
                if _openai is not None:
                    try:
                        await _openai.close()
                    except Exception:
                        pass

            except Exception as ce:
                logger.warning(f"⚠️ Cleanup error: {ce}")
            finally:
                del bot
        logger.debug("Scanner cleanup complete")


# ─────────────────────────────────────────────
# Launcher with Auto-Restart + Circuit Breaker
# ─────────────────────────────────────────────

def main_launcher():
    """Launcher with exponential backoff and circuit breaker"""
    logger = logging.getLogger(__name__)
    restart_count       = 0
    consecutive_failures = 0
    total_elapsed       = 0.0
    circuit_breaker_triggered = False
    circuit_breaker_time      = 0.0

    # Load configuration
    try:
        max_restarts = int(os.getenv("MAX_RESTARTS", str(DEFAULT_MAX_RESTARTS)))
        if max_restarts <= 0:
            logger.warning(f"⚠️ MAX_RESTARTS must be positive — using {DEFAULT_MAX_RESTARTS}")
            max_restarts = DEFAULT_MAX_RESTARTS
    except (ValueError, TypeError):
        max_restarts = DEFAULT_MAX_RESTARTS

    try:
        restart_delay_base = int(os.getenv("RESTART_DELAY_BASE", str(DEFAULT_RESTART_DELAY_BASE)))
        if restart_delay_base <= 0:
            restart_delay_base = DEFAULT_RESTART_DELAY_BASE
    except (ValueError, TypeError):
        restart_delay_base = DEFAULT_RESTART_DELAY_BASE

    logger.info("🐟 MiroFish Swarm Bot Launcher v4 — Production Ready")
    logger.info(f"📊 Markets: ALL Binance USDM Perpetual Futures (PARALLEL, up to 80 symbols, Semaphore={SCAN_PARALLEL_LIMIT})")
    logger.info("🌐 Starting with auto-restart protection...")
    logger.info(f"📋 Config: max_restarts={max_restarts}, base_delay={restart_delay_base}s")

    # ── Channel configuration ──
    # TELEGRAM_CHANNEL_ID → dedicated signal channel (@ichimokutradingsignal)
    # TELEGRAM_CHAT_ID    → admin / personal chat (notifications only)
    _ch_id = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    _admin = (os.getenv("TELEGRAM_CHAT_ID", "") or os.getenv("ADMIN_CHAT_ID", "")).strip()

    if not _ch_id:
        # If TELEGRAM_CHAT_ID is a channel (negative ID) treat it as signal channel too
        if _admin.startswith("-"):
            os.environ.setdefault("TELEGRAM_CHANNEL_ID", _admin)
            logger.info(f"✅ Signal channel (from TELEGRAM_CHAT_ID): {_admin}")
        else:
            # Hard-default: @ichimokutradingsignal
            os.environ.setdefault("TELEGRAM_CHANNEL_ID", "-1002453842816")
            logger.info("✅ Signal channel auto-configured: -1002453842816 (@ichimokutradingsignal)")
    else:
        logger.info(f"✅ Signal channel (TELEGRAM_CHANNEL_ID): {_ch_id}")

    if _admin:
        logger.info(f"🔔 Admin chat (TELEGRAM_CHAT_ID): {_admin}")

    # Verify required secrets
    required_vars = ["TELEGRAM_BOT_TOKEN", "BINANCE_API_KEY", "BINANCE_API_SECRET"]
    missing_vars  = [v for v in required_vars if not os.getenv(v, "")]
    if missing_vars:
        logger.error(f"❌ Missing required env vars: {missing_vars}")
        logger.error("Please set these in the Secrets tab in Replit")
        return

    # ── Main Restart Loop ──
    while restart_count < max_restarts:

        # Circuit breaker check
        if circuit_breaker_triggered:
            elapsed_since = time.time() - circuit_breaker_time
            if elapsed_since < CIRCUIT_BREAKER_COOLDOWN:
                remaining = CIRCUIT_BREAKER_COOLDOWN - elapsed_since
                logger.warning(f"⚠️ Circuit breaker active — waiting {remaining:.0f}s")
                time.sleep(1)
                continue
            else:
                logger.info("🔄 Circuit breaker expired — attempting recovery")
                circuit_breaker_triggered = False
                consecutive_failures      = 0

        try:
            logger.info(
                f"🎯 Starting bot (attempt #{restart_count + 1}/{max_restarts}, "
                f"consecutive_failures={consecutive_failures})"
            )

            start_time = time.time()
            success    = asyncio.run(main())
            elapsed    = time.time() - start_time
            total_elapsed += elapsed

            if not success:
                restart_count       += 1
                consecutive_failures += 1

                if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                    logger.error(f"🔴 Circuit breaker tripped: {consecutive_failures} consecutive failures")
                    circuit_breaker_triggered = True
                    circuit_breaker_time      = time.time()
                    continue

                if restart_count >= max_restarts:
                    logger.error(f"❌ Max restarts ({max_restarts}) reached. Stopping.")
                    break

                try:
                    delay = calculate_delay(restart_count, restart_delay_base)
                except ValueError as ve:
                    logger.warning(f"⚠️ Delay calc error: {ve}, using base delay")
                    delay = restart_delay_base

                logger.warning(
                    f"⚠️ Bot exited with error (#{restart_count}/{max_restarts}, "
                    f"runtime={elapsed:.1f}s, total={total_elapsed:.1f}s). "
                    f"Restarting in {delay}s..."
                )
                time.sleep(delay)

            else:
                # Clean exit
                consecutive_failures = 0
                logger.info(
                    f"✅ Bot completed cleanly in {elapsed:.1f}s "
                    f"(total={total_elapsed:.1f}s)"
                )
                break

        except KeyboardInterrupt:
            logger.info("🛑 Manual shutdown by user (Ctrl+C)")
            logger.info(f"✅ Launcher shutdown complete (total runtime {total_elapsed:.1f}s)")
            break

        except RuntimeError as e:
            restart_count += 1; consecutive_failures += 1
            logger.error(f"💥 RuntimeError #{restart_count}: {e}")
            if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                logger.error(f"🔴 Circuit breaker tripped: {consecutive_failures} consecutive failures")
                circuit_breaker_triggered = True
                circuit_breaker_time      = time.time()
                continue
            if restart_count >= max_restarts:
                logger.error("❌ Max restarts reached after RuntimeError.")
                break
            delay = _safe_delay(restart_count, restart_delay_base, logger)
            time.sleep(delay)

        except asyncio.CancelledError:
            restart_count += 1; consecutive_failures += 1
            logger.warning(f"⚠️ CancelledError #{restart_count}")
            if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                logger.error(f"🔴 Circuit breaker tripped: {consecutive_failures} consecutive failures")
                circuit_breaker_triggered = True
                circuit_breaker_time      = time.time()
                continue
            if restart_count >= max_restarts:
                break
            delay = _safe_delay(restart_count, restart_delay_base, logger)
            time.sleep(delay)

        except (ConnectionError, OSError) as e:
            restart_count += 1; consecutive_failures += 1
            logger.error(f"💥 {type(e).__name__} #{restart_count}: {e}")
            if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                logger.error(f"🔴 Circuit breaker tripped: {consecutive_failures} consecutive failures")
                circuit_breaker_triggered = True
                circuit_breaker_time      = time.time()
                continue
            if restart_count >= max_restarts:
                break
            delay = _safe_delay(restart_count, restart_delay_base, logger)
            time.sleep(delay)

        except Exception as e:
            restart_count += 1; consecutive_failures += 1
            logger.error(f"💥 {type(e).__name__} #{restart_count}: {e}")
            if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                logger.error(f"🔴 Circuit breaker tripped: {consecutive_failures} consecutive failures")
                circuit_breaker_triggered = True
                circuit_breaker_time      = time.time()
                continue
            if restart_count >= max_restarts:
                break
            delay = _safe_delay(restart_count, restart_delay_base, logger)
            time.sleep(delay)

    if restart_count >= max_restarts:
        logger.warning(f"⚠️ Maximum restart limit reached ({max_restarts})")

    logger.info(f"✅ Launcher shutdown complete (total runtime {total_elapsed:.1f}s)")


def _safe_delay(restart_count: int, base_delay: int, logger) -> int:
    """Helper: calculate delay safely with fallback"""
    try:
        return calculate_delay(restart_count, base_delay)
    except ValueError:
        return base_delay


def calculate_delay(restart_count: int, base_delay: int) -> int:
    """True exponential backoff delay with cap and validation.

    Delay = base_delay × 2^(restart_count − 1), capped at MAX_DELAY_SECONDS.
    Example (base=30): 30s, 60s, 120s, 240s, 300s (cap), 300s, ...

    Args:
        restart_count: Number of restarts so far (must be > 0)
        base_delay:    Base delay in seconds (must be > 0)

    Returns:
        Delay in seconds (capped at MAX_DELAY_SECONDS)

    Raises:
        ValueError: If inputs are invalid
    """
    if not isinstance(restart_count, int) or restart_count <= 0:
        raise ValueError(f"restart_count must be a positive int, got {restart_count}")
    if not isinstance(base_delay, int) or base_delay <= 0:
        raise ValueError(f"base_delay must be a positive int, got {base_delay}")

    # True exponential backoff: 2^(restart_count-1) × base_delay
    # Cap the exponent to avoid integer overflow on extreme restart counts
    exponent = min(restart_count - 1, 10)
    delay = base_delay * (2 ** exponent)
    return min(delay, MAX_DELAY_SECONDS)


# ─────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    try:
        main_launcher()
    except KeyboardInterrupt:
        print("\n\n🛑 Launcher interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Fatal launcher error: {type(e).__name__}: {e}")
        sys.exit(1)
