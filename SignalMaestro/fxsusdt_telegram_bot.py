#!/usr/bin/env python3
"""
ALL USDM Perpetual Futures Telegram Signal Bot — MiroFish Swarm v5.0
Powered by MiroFish Swarm Intelligence Strategy (github.com/666ghj/MiroFish)
10-agent consensus trading signals for @ichimokutradingsignal
TRUE parallel scanning of up to 80 USDM symbols with asyncio.gather + Semaphore
"""

import asyncio
import copy
import dataclasses
import logging
import math
import re
import aiohttp
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import json
import random

# Core strategy & trader — MiroFish Swarm
from SignalMaestro.mirofish_swarm_strategy import MiroFishSwarmStrategy, SwarmSignal
from SignalMaestro.btcusdt_trader import BTCUSDTTrader
from SignalMaestro.godmod3_strategy import get_godmod3_engine

# ── Self-learning system: trade memory + neural network ──────────────────────
try:
    from SignalMaestro.trade_memory        import TradeMemory, OutcomeTracker
    from SignalMaestro.neural_signal_trainer import NeuralSignalTrainer
    _HAS_NEURAL = True
except Exception as _ne:
    _HAS_NEURAL = False
    logging.getLogger(__name__).warning(f"⚠️  Self-learning disabled: {_ne}")

# Supporting analyzers (graceful fallback if unavailable)
def _try_import(module_path: str, attr: str, default=None):
    try:
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, attr, default)
    except Exception:
        return default

DynamicPositionManager   = _try_import("SignalMaestro.dynamic_position_manager",   "DynamicPositionManager")
market_analyzer          = _try_import("SignalMaestro.market_intelligence_analyzer", "market_analyzer")
SmartDynamicSLTPSystem   = _try_import("SignalMaestro.smart_dynamic_sltp_system",   "SmartDynamicSLTPSystem")

try:
    from SignalMaestro.public_api_intelligence import PublicAPIIntelligence
    _HAS_PUBLIC_API = True
except ImportError:
    try:
        from public_api_intelligence import PublicAPIIntelligence
        _HAS_PUBLIC_API = True
    except ImportError:
        _HAS_PUBLIC_API = False
insider_analyzer         = _try_import("SignalMaestro.insider_trading_analyzer",    "insider_analyzer")
atas_analyzer            = _try_import("SignalMaestro.atas_integrated_analyzer",    "atas_analyzer")
bookmap_analyzer         = _try_import("SignalMaestro.bookmap_trading_analyzer",    "bookmap_analyzer")
get_market_depth_analyzer     = _try_import("SignalMaestro.advanced_market_depth_analyzer",    "get_market_depth_analyzer")
get_market_microstructure_enhancer = _try_import("SignalMaestro.market_microstructure_enhancer", "get_market_microstructure_enhancer")
get_dynamic_leveraging_sl = _try_import("SignalMaestro.dynamic_leveraging_stop_loss", "get_dynamic_leveraging_sl")

# Freqtrade commands (optional)
try:
    from freqtrade_telegram_commands import FreqtradeTelegramCommands
    _HAS_FREQTRADE = True
except ImportError:
    _HAS_FREQTRADE = False


class FXSUSDTTelegramBot:
    """
    ALL USDM Futures Telegram Signal Bot — MiroFish Swarm v5.0 Edition
    (Class name kept for backward compatibility with start_ultimate_bot.py)
    """

    # ─────────────────────────────────────────
    # Init
    # ─────────────────────────────────────────

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # ── Telegram config ──
        self.bot_token     = os.getenv("TELEGRAM_BOT_TOKEN")
        self.bot_username  = "@TradeTacticsML_bot"

        # Admin / notification chat — personal chat for status pings
        self.admin_chat_id = os.getenv("ADMIN_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")

        # Signal channel — where Unity-compatible signals are broadcast
        # Priority: TELEGRAM_CHANNEL_ID env var → TELEGRAM_CHAT_ID if it looks like a channel
        # → hardcoded @ichimokutradingsignal fallback
        _env_channel = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
        _env_chat    = (os.getenv("TELEGRAM_CHAT_ID", "") or "").strip()

        if _env_channel:
            self.signal_channel_id = _env_channel
        elif _env_chat.startswith("-"):   # negative ID = channel/group
            self.signal_channel_id = _env_chat
        else:
            self.signal_channel_id = "-1002453842816"  # @ichimokutradingsignal default

        # Legacy channel_id alias (used by commands / status)
        self.channel_id = self.signal_channel_id

        if not self.bot_token:
            raise ValueError("Missing TELEGRAM_BOT_TOKEN in Replit secrets")

        self.logger.info(f"📢 Signal channel: {self.signal_channel_id} (@ichimokutradingsignal)")
        if self.admin_chat_id:
            self.logger.info(f"🔔 Admin chat: {self.admin_chat_id}")

        # ── Core components ──
        self.strategy = MiroFishSwarmStrategy()
        self.trader   = BTCUSDTTrader()

        # ── Optional analyzers (safe init) ──
        self.market_intelligence = market_analyzer
        self.smart_sltp          = SmartDynamicSLTPSystem() if SmartDynamicSLTPSystem else None
        self.insider_analyzer    = insider_analyzer
        self.atas_analyzer       = atas_analyzer
        self.bookmap_analyzer    = bookmap_analyzer
        self.depth_analyzer      = get_market_depth_analyzer() if callable(get_market_depth_analyzer) else None
        self.microstructure_enhancer = (
            get_market_microstructure_enhancer() if callable(get_market_microstructure_enhancer) else None
        )
        self.dynamic_sl = get_dynamic_leveraging_sl() if callable(get_dynamic_leveraging_sl) else None

        # ── Freqtrade commands ──
        self.freqtrade_commands = None
        if _HAS_FREQTRADE:
            try:
                self.freqtrade_commands = FreqtradeTelegramCommands(self)
            except Exception as e:
                self.logger.warning(f"Freqtrade commands unavailable: {e}")

        # ── AI processor ──
        self.ai_processor = None
        try:
            from ai_enhanced_signal_processor import AIEnhancedSignalProcessor
            self.ai_processor = AIEnhancedSignalProcessor()
            self.logger.info("✅ AI processor initialized")
        except Exception:
            self.logger.info("ℹ️ AI processor unavailable — standard mode")

        # ── Telegram API URL ──
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

        # ── Unity TradingInterface (inline-keyboard menu — raw-mode long-poller) ──
        self.trading_interface = None
        try:
            from SignalMaestro.trading_interface import get_trading_interface
            self.trading_interface = get_trading_interface(engine=self)
            self.logger.info("✅ TradingInterface ready (CCXT·InlineKB·UserDB·QuantMath·Kelly·BSGreeks·IC/IR·MVO·BL)")
        except Exception as _ti_err:
            self.logger.warning(f"⚠️ TradingInterface init failed (slash commands still active): {_ti_err}")

        # ── Command registry ──
        self.commands: Dict[str, Any] = {
            "/start":        self.cmd_start,
            "/help":         self.cmd_help,
            "/status":       self.cmd_status,
            "/price":        self.cmd_price,
            "/balance":      self.cmd_balance,
            "/position":     self.cmd_position,
            "/scan":         self.cmd_scan,
            "/settings":     self.cmd_settings,
            "/market":       self.cmd_market,
            "/stats":        self.cmd_stats,
            "/leverage":     self.cmd_leverage,
            "/risk":         self.cmd_risk,
            "/signal":       self.cmd_signal,
            "/history":      self.cmd_history,
            "/alerts":       self.cmd_alerts,
            "/admin":        self.cmd_admin,
            "/futures":      self.cmd_futures_info,
            "/contract":     self.cmd_contract_specs,
            "/funding":      self.cmd_funding_rate,
            "/oi":           self.cmd_open_interest,
            "/volume":       self.cmd_volume_analysis,
            "/sentiment":    self.cmd_market_sentiment,
            "/news":         self.cmd_market_news,
            "/watchlist":    self.cmd_watchlist,
            "/backtest":     self.cmd_backtest,
            "/optimize":     self.cmd_optimize_strategy,
            "/dynamic_sltp": self.cmd_dynamic_sltp,
            "/dashboard":    self.cmd_market_dashboard,
            "/market_intel": self.cmd_market_intelligence,
            "/insider":      self.cmd_insider_detection,
            "/orderflow":    self.cmd_order_flow,
            "/dynamic_sl":   self.cmd_dynamic_leveraging_sl,
            "/swarm":        self.cmd_swarm_status,
        }

        if self.freqtrade_commands:
            try:
                ft_cmds = self.freqtrade_commands.get_all_commands()
                self.commands.update(ft_cmds)
                self.logger.info(f"✅ Loaded {len(ft_cmds)} Freqtrade commands")
            except Exception as e:
                self.logger.warning(f"Could not load Freqtrade commands: {e}")

        # ── Bot state ──
        self.signal_count        = 0
        self.last_signal_time    = None
        self.bot_start_time      = datetime.now()
        self.commands_used: Dict[str, int] = {}
        self.price_alerts: Dict[str, List] = {}

        # ── Rate limiting — 15M timeframe: minimum 120s between signals ──
        _interval_sec = max(60, int(os.getenv("SIGNAL_INTERVAL_SECONDS", "120")))
        self.min_signal_interval_minutes = _interval_sec / 60.0
        # Honour SIGNALS_PER_HOUR_MAX from the environment (launcher sets 8).
        # The hard ceiling of 20 prevents misconfiguration; default is 5 when
        # the env var is absent.  The old min(5, ...) silently discarded the
        # launcher's SIGNALS_PER_HOUR_MAX=8 setting.
        _sph_env = os.getenv("SIGNALS_PER_HOUR_MAX", "").strip()
        _sph_requested = int(_sph_env) if _sph_env.isdigit() else 5
        self._MAX_SIGNALS_PER_HOUR = min(20, max(1, _sph_requested))
        # Global minimum gap between any two signals (across all symbols).
        # v5.7 BUG FIX: Reduced 90s → 15s.  90s was blocking ALL 80 symbols for
        # an entire scan cycle after any single signal, causing 0.0s wasted cycles.
        # 15s is enough to prevent duplicate sends within the same parallel batch
        # (asyncio.gather results race takes <2s) while restoring full cycle throughput.
        _gap_env = os.getenv("GLOBAL_MIN_GAP_SECONDS", "").strip()
        self._GLOBAL_MIN_GAP_SECONDS = (
            float(_gap_env) if _gap_env.replace(".", "", 1).isdigit() else 15.0
        )
        self.signal_timestamps: List[datetime] = []

        # ── AI confidence threshold — cached at init so process_signals never
        # calls os.getenv() for every signal from 20 parallel coroutines.
        # Mutable at runtime: update self._ai_threshold_pct if the env var is
        # changed while the bot is running (e.g. via /settings command).
        _ai_thresh_env = os.getenv("AI_THRESHOLD_PERCENT", "80").strip()
        self._ai_threshold_pct: float = (
            float(_ai_thresh_env)
            if _ai_thresh_env.replace(".", "", 1).isdigit()
            else 80.0
        )

        # ── Polling offset (instance, not class-level to avoid shared state) ──
        self._poll_offset: int = 0

        # ── Concurrency safety for parallel scanning ──────────────────────────
        # Prevents race conditions when 20 coroutines simultaneously pass the
        # can_send_signal() check before any signal is recorded.
        # asyncio.Lock() is safe to create in __init__ (Python 3.10+; also
        # works on 3.8/3.9 when not bound to a specific event loop at creation).
        self._signal_gate_lock: asyncio.Lock = asyncio.Lock()

        # ── Pre-built scan semaphore — avoids allocating a new asyncio.Semaphore
        # object on every scan_all_parallel() call (every 30-60s cycle).
        # The env var is read once at startup; restart the bot to apply changes.
        _scan_limit = max(1, int(os.getenv("SCAN_PARALLEL_LIMIT", "15")))
        self._scan_limit: int = _scan_limit        # stored so log/diagnostics can read the live value
        self._scan_semaphore: asyncio.Semaphore = asyncio.Semaphore(_scan_limit)

        # ── Per-cycle signal cap (anti-correlation) ───────────────────────────
        # When 80 symbols are scanned in parallel, multiple correlated symbols
        # (e.g. MUSDT+KATUSDT+ZBTUSDT all SELL in a CRASH-RISK session) can pass
        # all 12 gates simultaneously and flood the channel with perfectly
        # correlated positions.  Correlated positions amplify drawdown without
        # diversification benefit: 3 simultaneous SELL signals that all lose are
        # 3× the loss, but they carry identical market risk.
        # Cap: at most MAX_SIGNALS_PER_CYCLE signals per scan_all_parallel() call.
        # Reset to 0 at the top of each scan_all_parallel().  Checked inside
        # _signal_gate_lock so the count is race-condition-safe.
        # Env-tunable: UNITY_MAX_SIGNALS_PER_CYCLE (default 3).
        _cyc_cap_env = os.getenv("UNITY_MAX_SIGNALS_PER_CYCLE", "3").strip()
        self._MAX_SIGNALS_PER_CYCLE: int = max(1, int(_cyc_cap_env) if _cyc_cap_env.isdigit() else 3)
        self._cycle_signals_sent: int = 0   # reset each scan cycle

        # Telegram send throttle: limits to 1 message every _TG_SEND_MIN_GAP_SEC
        # to avoid HTTP 429 (Telegram rate limit: ~20 msgs/min to channels).
        # _tg_send_lock serializes the throttle check+update so parallel coroutines
        # cannot simultaneously pass the gap check and flood the channel.
        self._tg_last_send_time: float = 0.0
        self._TG_SEND_MIN_GAP_SEC: float = float(os.getenv("TG_SEND_MIN_GAP_SEC", "2.0"))
        self._tg_send_lock: asyncio.Lock = asyncio.Lock()
        # Persistent Telegram HTTP session — avoids creating a new TCP connection
        # for every message/poll (mirrors BTCUSDTTrader's shared-session pattern).
        self._tg_session:   Optional[aiohttp.ClientSession] = None
        self._tg_connector: Optional[aiohttp.TCPConnector]  = None

        # ── Self-learning neural network system ──────────────────────────────
        # TradeMemory: SQLite log of every signal + resolved outcomes
        # NeuralSignalTrainer: MLP trained on those outcomes to filter future signals
        # OutcomeTracker: background coroutine that monitors price and labels outcomes
        self.trade_memory: Optional[Any] = None
        self.nn_trainer:   Optional[Any] = None
        self.outcome_tracker: Optional[Any] = None
        self._outcome_tracker_task: Optional[asyncio.Task] = None
        self.bm25_memory: Optional[Any] = None
        if _HAS_NEURAL:
            try:
                self.trade_memory = TradeMemory()
                self.nn_trainer   = NeuralSignalTrainer()
                self.logger.info(
                    f"🧠 Self-learning system initialized | "
                    f"{self.nn_trainer.status_summary()}"
                )
            except Exception as e:
                self.logger.warning(f"⚠️  Self-learning init failed: {e}")
                self.trade_memory = None
                self.nn_trainer   = None
        try:
            from SignalMaestro.swarm_bm25_memory import SwarmBM25Memory
            self.bm25_memory = SwarmBM25Memory()
            _counts = self.bm25_memory.get_lesson_counts()
            _total = sum(_counts.values())
            self.logger.info(
                f"🧠 BM25 Memory initialized | {_total} lessons "
                f"({', '.join(f'{r}={c}' for r, c in _counts.items() if c > 0) or 'empty'})"
            )
        except Exception as _bm25_err:
            self.logger.warning(f"⚠️  BM25 Memory init skipped: {_bm25_err}")
            self.bm25_memory = None

        self.public_api: Optional[Any] = None
        self._public_api_task: Optional[asyncio.Task] = None
        if _HAS_PUBLIC_API:
            try:
                self.public_api = PublicAPIIntelligence()
                self.logger.info("🌐 PublicAPIIntelligence initialized (Fear&Greed, CoinGecko, CoinCap)")
            except Exception as pai_err:
                self.logger.warning(f"⚠️ PublicAPIIntelligence init failed: {pai_err}")
                self.public_api = None

        # ── BB position for current scan cycle (passed to trade recorder) ──
        self._current_bb_position: float = 0.5

        self._streak_lock = asyncio.Lock()

        # Concurrency guard for symbol-list refresh.
        # Without this, all 30 parallel scan coroutines can simultaneously detect
        # that the refresh interval has expired and each issue a separate
        # trader.get_all_usdm_symbols() Binance API call — wasting connections
        # and risking rate-limit 429s.  Double-checked locking pattern:
        #   fast path (no lock)  → return if still fresh
        #   slow path (with lock) → re-check, then do exactly one API call
        self._symbols_refresh_lock = asyncio.Lock()

        # ── Adaptive confidence threshold — raised during losing streaks ────
        # Base threshold is AI_THRESHOLD_PERCENT (80%).  After N consecutive
        # resolved losses the threshold is raised by STREAK_BOOST_PER_LOSS
        # (up to STREAK_MAX_BOOST_PCT) to reduce signal frequency until the
        # model learns to avoid bad patterns again.
        self._consecutive_losses: int   = 0
        self._adaptive_conf_boost: float = 0.0   # extra % added to the gate
        # v5.7 BUG FIX: STREAK_TRIGGER_N 2→4 and STREAK_BOOST_PER_LOSS 3.0→2.0.
        # With STREAK_TRIGGER_N=2, the bot's adaptive gate rose after just 2 losses,
        # STACKING on top of the Unity booster's own CB — double-threshold inflation.
        # 4 losses is a firmer signal before tightening the confidence gate.
        # Lower boost-per-loss (2.0) aligns with the booster's smaller 3.0pt CB.
        self.STREAK_TRIGGER_N:    int   = 4       # losses in a row before boost (was 2)
        self.STREAK_BOOST_PER_LOSS: float = 2.0  # +2% per consecutive loss (was 3.0)
        self.STREAK_MAX_BOOST_PCT:  float = 12.0 # max +12% above base threshold (was 20.0)
        self.STREAK_RESET_ON_WIN:   bool  = True  # reset streak on any win

        # ── Multi-market state ─────────────────────────────────────────────────
        # Active symbol list — refreshed from Binance every SYMBOL_REFRESH_INTERVAL
        self._active_symbols: List[str]   = ["BTCUSDT"]
        self._symbols_refresh_time: float = 0.0
        self._symbol_scan_index: int      = 0        # round-robin scan pointer
        self.SYMBOL_REFRESH_INTERVAL: int = 3600     # refresh symbol list hourly

        # Per-symbol rate limiting — track last signal time per symbol
        self._symbol_last_signal: Dict[str, float] = {}   # symbol → unix timestamp
        self._symbol_signal_count: Dict[str, int]  = {}   # symbol → total sent

        # NN-reject cooldown — when a symbol gets NN ABSOLUTE REJECT (win_prob <
        # _absolute_floor ≈ 20% calibrated), skip re-evaluation for 10 min.
        # v15.3 BUG FIX: cooldown was only set for win_prob < 10% (catastrophic)
        # but NN ABSOLUTE REJECT fires at < 20%.  PENGUUSDT win_prob=17% got full
        # swarm+NN+PM pipeline burned in Cycle 2 immediately after Cycle 1 reject
        # (17% ≥ 10% → no cooldown set → re-evaluated 25s later → 7% → finally
        # suppressed).  Fix: match cooldown threshold to the absolute reject floor
        # so ANY NN ABSOLUTE REJECT suppresses re-evaluation for 10 min. [v15.3]
        self._nn_reject_cooldown: Dict[str, float] = {}   # symbol → expiry unix ts
        # v15.3 Bug F: NN hard-reject cooldown for the "far-below" band (win_prob
        # 20-36%).  The ABSOLUTE REJECT cooldown (line above) covers <20% only.
        # MANTRAUSDT wins 22-27% — not absolute-floor rejected but still hard-
        # rejected by _far_below path (win_prob < reject_thresh-0.02=0.36).
        # Without a cooldown, the full swarm+NN+PM pipeline re-runs every ~15s
        # cycle for the same result.  NN features (ATR, RSI, macro regime) are
        # slower-moving than OB imbalance → 120s is appropriate (2× OB-fail base).
        # Self-heals when market moves enough to push win_prob above threshold.
        self._nn_hard_reject_cooldown: Dict[str, float] = {}  # symbol → expiry ts
        self._NN_HARD_REJECT_COOLDOWN_SEC: float = 120.0      # 2-min suppress for _far_below path
        # Batch NN pre-cache [v18.17]: at cycle start, predict_batch_mc_from_dicts()
        # runs once on all prev-cycle signal dicts (125× FLOP reduction at N=50).
        # process_signals() hits cache first; individual inference only on cache miss.
        self._prev_cycle_nn_dicts: Dict[str, dict] = {}        # symbol → _signal_dict from prev cycle
        self._nn_batch_cache: Dict[str, tuple] = {}            # symbol → (mean_prob, std)
        # v15.3 EV-fail cooldown — when a symbol consistently fails Gate 0 EV
        # with the same TP/SL geometry, suppress re-evaluation for ~3 scan cycles
        # (90s) to avoid burning Binance klines + ATAS + orderbook + NN inference
        # quota on a trade that will not pass regardless of marginal price change.
        # Set after G0_FAIL in process_signals; cleared automatically on expiry.
        # Env-tunable: UNITY_EV_FAIL_COOLDOWN_SEC (default 90).
        _ev_cd_env = os.getenv("UNITY_EV_FAIL_COOLDOWN_SEC", "90").strip()
        self._EV_FAIL_COOLDOWN_SEC: float = max(15.0, float(_ev_cd_env) if _ev_cd_env.replace(".", "", 1).isdigit() else 90.0)
        self._ev_fail_cooldown: Dict[str, float] = {}   # symbol → expiry unix ts
        # v15.3 Repeat-offender escalation: track consecutive G0 EV failures per symbol.
        # APTUSDT, HUSDT etc. consistently fail G0 at the same EV (~19-22bps) because
        # their TP/SL geometry is structurally below floor — prices don't shift enough
        # in 90s to change the geometry.  After N_ESCALATE_THRESHOLD consecutive failures,
        # escalate cooldown to 5 minutes (same as post-signal per-symbol cooldown),
        # saving ~3 full Phase 1 evaluations per symbol per 5-minute window.
        # Streak is reset when the symbol passes G0 (signal sent or passes all gates).
        self._ev_fail_streak: Dict[str, int] = {}      # symbol → consecutive G0 fail count
        self._EV_FAIL_ESCALATE_N: int = 3              # escalate after this many consecutive fails
        self._EV_FAIL_LONG_SEC: float = self.min_signal_interval_minutes * 60  # 5 min
        # v15.3 Level-3 G0 EV-fail escalation: chronic repeat-offenders (streak≥6) get
        # 30-min suppress.  FARTCOINUSDT burned 38 evaluations cycling back after every
        # 300s window — structural EV deficit (P_win×R < floor + slip) does not self-heal
        # without a genuine price regime shift; 30-min virtually guarantees a new candle
        # pattern before re-evaluation.  Level-2 (300s) remains for moderate streaks.
        self._EV_FAIL_ESCALATE_N2: int = 6             # level-3 after this many consecutive fails
        self._EV_FAIL_VERY_LONG_SEC: float = 1800.0    # 30-min suppress for chronic EV-fails
        # v15.3 G2.5 orderbook-fail cooldown: suppress symbols that consistently have
        # STRONG orderbook flow opposing the signal direction.  PENGUUSDT burns the full
        # Phase 1 pipeline (swarm 10-agent + NN + PM + ATAS) every cycle then hits
        # G2.5 (orderbook opposed) at the end — same waste-burn pattern as APTUSDT EV-fail.
        # Orderbook imbalance can flip faster than EV geometry so we use 2 min (120s)
        # as the base cooldown; streak escalation added for chronic OB-opposition like
        # NFPUSDT (27 G2.5 hits total, flat 120s = 27 × full Phase-1 evals wasted).
        self._ob_fail_cooldown: Dict[str, float] = {}  # symbol → expiry unix ts
        self._OB_FAIL_COOLDOWN_SEC: float = 120.0      # 2 min suppress after G2.5_FAIL
        # v15.3 G2.5 OB-fail streak escalation: NFPUSDT burned 27 Phase-1 pipeline
        # evaluations at flat 120s.  Streak≥3 → 300s (same as G0 EV-fail level-2).
        # Streak escalation also accumulates across restarts via filter state persistence.
        self._ob_fail_streak: Dict[str, int] = {}      # symbol → consecutive G2.5 fail count
        self._OB_FAIL_ESCALATE_N: int = 3              # escalate to 300s after this many fails
        self._OB_FAIL_LONG_SEC: float = 300.0          # 5-min escalated cooldown for G2.5
        # v15.3 G3_FAIL cooldown: when a symbol fails Gate 3 (confidence < RL threshold)
        # after Phase 1 evaluation, the gap between boosted conf and the RL threshold is
        # structural and won't close in 20s.  APEUSDT pattern: swarm conf=73.4% + PM+7 →
        # 77.4%, but RL threshold=84% (gap=6.6pts).  ATAS/Bookmap would need +6.6pts more
        # which they don't deliver in current market conditions.  Suppress for 90s
        # (same as EV-fail base) with streak escalation to 300s after 3 consecutive fails.
        # Self-heals when conf improves (market conditions change) or RL threshold drops.
        self._g3_fail_cooldown: Dict[str, float] = {}  # symbol → expiry unix ts
        self._g3_fail_streak: Dict[str, int] = {}       # symbol → consecutive G3 fail count
        self._G3_FAIL_COOLDOWN_SEC: float = 90.0        # 90s base suppress after G3_FAIL
        # v15.3 G1_FAIL cooldown: when a symbol fails Gate 1 (weighted R:R below adaptive
        # floor) the TP/SL geometry is structural — price levels don't shift in 20s.
        # AIGENSYNUSDT: R:R=2.79 < 3.20 floor (WR=18%) repeated every 16s for minutes.
        # FARTCOINUSDT: R:R=2.79 < 2.80 floor at WR=21%.  Both are pure geometry — same
        # TP/SL computed from the same OHLCV bar.  Suppress 90s so the engine only
        # re-evaluates after genuine price movement changes the R:R geometry.
        self._g1_fail_cooldown: Dict[str, float] = {}  # symbol → expiry unix ts
        self._g1_fail_streak: Dict[str, int] = {}       # symbol → consecutive G1 fail count
        self._G1_FAIL_COOLDOWN_SEC: float = 90.0        # 90s base suppress after G1_FAIL
        # v15.3 G9_FAIL cooldown: when a symbol fails Gate 9 (quality score below adaptive
        # floor) after full Phase 1 evaluation, the composite quality is structural and
        # won't change in 20s without a genuine market regime shift.  APEUSDT: quality=42-50
        # < floor=55-58 repeated every 20s cycle (21 hits total).  PENGUUSDT=20, APTUSDT=20,
        # MANTRAUSDT=16, 1000SHIBUSDT=12, PLAYUSDT=11, ONUSDT=10.  All burning the full
        # swarm+PM+NN+ATAS pipeline before failing the quality floor.  Suppress 90s base
        # with escalation to 300s after 3 consecutive G9 fails.  Self-heals when quality
        # composition changes (regime shift, different bar geometry, or new ATAS data).
        self._g9_fail_cooldown: Dict[str, float] = {}  # symbol → expiry unix ts
        self._g9_fail_streak: Dict[str, int] = {}       # symbol → consecutive G9 fail count
        self._G9_FAIL_COOLDOWN_SEC: float = 90.0        # 90s base suppress after G9_FAIL
        # v15.3 AI-gate-block cooldown: suppress symbols whose swarm conf is structurally
        # below the AI bypass threshold when LLMs are rate-limited.  INJUSDT pattern:
        # conf=67.4%+15boost=82.4% < 86% threshold → AI gate blocks → swarm re-runs
        # next cycle → same result.  Conf doesn't move in 20s without a price breakout.
        # Fix: 90s suppress after consecutive block (same window as EV-fail cooldown).
        # Self-heals when LLMs recover (pre-check skipped if models available) OR when
        # conf rises above threshold naturally (next block resets the timer).
        self._ai_gate_block_cooldown: Dict[str, float] = {}  # symbol → expiry unix ts
        self._AI_GATE_BLOCK_COOLDOWN_SEC: float = 90.0       # 90s suppress per AI gate block
        # v15.3 G_BLK cooldown: when a symbol is rejected by the engine's lifetime WR<30%
        # blacklist (G_BLK gate inside Unity12GateStrategy.evaluate_signal), suppress it for
        # 10 minutes.  The lifetime WR blacklist is stable — it reads trade_history.db which
        # only changes when new trades resolve, so the same symbol will hit G_BLK on every
        # cycle until DB refreshes.  ENAUSDT/ARBUSDT burn the full 7-agent swarm every cycle
        # and are blocked at G_BLK 100% of the time (0% pass rate).  Cooldown prevents the
        # swarm from running for a symbol whose 12-gate outcome is deterministically known.
        # Protected symbols (ARBUSDT etc.) are suppressed the same way — they're protected
        # from the RECENT-loss blacklist but can still be in the LIFETIME-WR blacklist.
        self._gblk_cooldown: Dict[str, float] = {}          # symbol → expiry unix ts
        self._GBLK_COOLDOWN_SEC: float = 600.0               # 10 min (lifetime WR changes slowly)
        # v15.3 Pre-boost impossibility cooldown: when per-symbol loss-streak penalty
        # reduces effective confidence below the pre-boost impossibility gate
        # (post-penalty conf + MAX_BOOST < threshold), the symbol silently returns
        # False at DEBUG level — no cooldown is set, causing the full swarm to re-run
        # every cycle.  ADAUSDT pattern: conf=71.9% - penalty → 62.9% + 15 = 77.9% < 85%
        # → gate fires silently 10+ times per 4 minutes.  Fix: 90s suppress after gate
        # fires (same window as EV-fail and AI-gate-block).  Self-heals when loss streak
        # clears (penalty drops) or confidence rises above threshold.
        self._preboost_fail_cooldown: Dict[str, float] = {}  # symbol → expiry unix ts
        self._PREBOOST_FAIL_COOLDOWN_SEC: float = 90.0        # 90s (same as EV-fail base)

        # v15.3 G_BLK pre-warm flag — set to True after prewarm_gblk_cooldowns() runs
        # so it doesn't re-run on each wiring refresh.
        self._gblk_prewarmed: bool = False

        # Same-direction deduplication: reject repeat of same symbol+direction within
        # _SAME_DIR_DEDUP_SECONDS (45 min) even if per-symbol cooldown has passed.
        # Prevents e.g. sending BTC BUY at 09:00, 09:06, 09:12 when 15m keeps re-firing.
        self._symbol_last_direction: Dict[str, tuple] = {}  # symbol → (action, unix_ts)
        self._SAME_DIR_DEDUP_SECONDS: float = 2700.0        # 45 minutes (reduced from 90min)

        # v15.3 Bug G FIX: Open-position deduplication guard.
        # Per-symbol cooldown (20 min) is in-memory only and resets on every restart.
        # This allows PENGUUSDT/AIOTUSDT/MUSDT to be re-sent while those symbols
        # already have open trades in the DB (confirmed: 9 open PENGUUSDT trades,
        # 5 open AIOTUSDT, 4 open MUSDT in a single session).  Fix: maintain a
        # cached set of symbols with open trades, refreshed from DB every 60s.
        # Pre-check 2k blocks any symbol in this set before swarm evaluation.
        # Self-heals as trades resolve (OutcomeTracker removes from DB → not in set
        # on next refresh).  60s refresh lag is acceptable — trade is open for
        # hours (TRADE_EXPIRY=6h) so a 60s gap doesn't allow meaningful duplicates.
        self._open_symbols_set: set = set()              # symbols with open DB trades
        self._open_symbols_last_refresh: float = 0.0    # last DB refresh timestamp
        self._OPEN_SYMBOLS_REFRESH_SEC: float = 60.0    # refresh every 60s

        # FIX 8: Per-symbol performance tracking and automatic blacklist.
        # Symbols with recent_loss_rate > 85% over ≥15 resolved trades are
        # temporarily blocked (refreshed every SYMBOL_STATS_REFRESH_INTERVAL seconds).
        # Protected high-liquidity symbols (top 24) are never blacklisted.
        self._symbol_blacklist: set   = set()
        self._symbol_stats: Dict[str, Dict] = {}
        self._symbol_stats_last_refresh: float = 0.0
        self.SYMBOL_STATS_REFRESH_INTERVAL: int = 1200  # refresh every 20 min (was hourly)
        # Threshold: block a symbol if recent loss rate exceeds this
        self.SYMBOL_BLOCK_LOSS_RATE: float = 0.85  # 85% recent losses → block (requires very persistent losing streak)
        self.SYMBOL_BLOCK_MIN_TRADES: int  = 15    # need ≥15 resolved trades to block (statistically meaningful sample)

        # ── BTCUSDT contract specifications (legacy reference) ──
        self.contract_specs = {
            "symbol":           "BTCUSDT",
            "base_asset":       "BTC",
            "quote_asset":      "USDT",
            "contract_type":    "PERPETUAL",
            "settlement_asset": "USDT",
            "margin_type":      "Cross/Isolated",
            "tick_size":        "0.10",
            "step_size":        "0.001",
            "max_leverage":     "125x",
            "funding_interval": "8 hours",
        }

        self.logger.info("🐟 MiroFish Swarm Bot initialized — ALL USDM MARKETS")

    # ─────────────────────────────────────────
    # Telegram Messaging
    # ─────────────────────────────────────────

    async def send_message(self, chat_id: str, text: str,
                           parse_mode: str = "Markdown", retries: int = 3,
                           reply_markup=None) -> bool:
        """
        Send message to Telegram with retry, exponential backoff, and
        a global send-throttle that prevents HTTP 429 from the parallel scanner
        firing many signals at once (min gap = _TG_SEND_MIN_GAP_SEC).
        """
        if not chat_id:
            self.logger.warning("⚠️ Cannot send — no chat_id")
            return False

        chat_id = str(chat_id)

        # ── Telegram send throttle: enforce minimum gap between messages ──────
        # _tg_send_lock is initialized in __init__ (not lazily) so multiple
        # concurrent coroutines never race to create the lock object.
        async with self._tg_send_lock:
            now = time.time()
            gap = now - self._tg_last_send_time
            if gap < self._TG_SEND_MIN_GAP_SEC:
                await asyncio.sleep(self._TG_SEND_MIN_GAP_SEC - gap)
            self._tg_last_send_time = time.time()

        for attempt in range(retries):
            try:
                url  = f"{self.base_url}/sendMessage"
                data = {"chat_id": chat_id, "text": text, "link_preview_options": {"is_disabled": True}}
                if parse_mode in ("Markdown", "MarkdownV2", "HTML"):
                    data["parse_mode"] = parse_mode
                # v10.5: inline keyboard support
                if reply_markup is not None:
                    try:
                        import json as _json
                        if hasattr(reply_markup, "to_dict"):
                            data["reply_markup"] = _json.dumps(reply_markup.to_dict())
                        elif isinstance(reply_markup, dict):
                            data["reply_markup"] = _json.dumps(reply_markup)
                    except Exception:
                        pass

                session = await self._get_tg_session()
                async with session.post(
                    url, json=data,
                    timeout=aiohttp.ClientTimeout(total=12)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("ok"):
                            self.logger.debug(f"✅ Message sent to {chat_id}")
                            return True
                        error_desc = result.get("description", "")
                        self.logger.warning(f"⚠️ Telegram API: {error_desc}")
                        if "chat not found" in error_desc.lower():
                            return False
                        if "can't parse" in error_desc.lower() and parse_mode in ("Markdown", "MarkdownV2", "HTML"):
                            plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', text)
                            data_plain = {"chat_id": chat_id, "text": plain, "link_preview_options": {"is_disabled": True}}
                            # Preserve inline keyboard in plain-text fallback (v18.18 fix)
                            if "reply_markup" in data:
                                data_plain["reply_markup"] = data["reply_markup"]
                            async with session.post(url, json=data_plain, timeout=aiohttp.ClientTimeout(total=12)) as r2:
                                if r2.status == 200:
                                    r2j = await r2.json()
                                    if r2j.get("ok"):
                                        self.logger.info(f"✅ Message sent (plain fallback) to {chat_id}")
                                        return True
                    elif response.status == 400:
                        # 400 = permanent failure (invalid chat, bad request, etc.)
                        # Retrying never helps — log once and return immediately.
                        try:
                            _400_body = await response.json()
                            _400_desc = _400_body.get("description", "bad request")
                        except Exception:
                            _400_desc = "bad request"
                        self.logger.warning(f"⚠️ HTTP 400: {_400_desc} (chat_id={chat_id})")
                        return False
                    elif response.status == 429:
                        # Rate limited by Telegram — back off and retry.
                        # BUG FIX: previously fell through to the generic
                        # `2**attempt` sleep below, causing a double-sleep
                        # (retry_after + 2^attempt seconds).  `continue` now
                        # jumps directly to the next retry attempt.
                        retry_after = 5
                        try:
                            _429_body = await response.json()
                            retry_after = int(
                                _429_body.get("parameters", {}).get("retry_after", 5)
                            )
                        except Exception:
                            pass
                        self.logger.warning(f"⏳ Telegram 429 — backing off {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue  # skip the generic 2**attempt sleep; go to next attempt
                    else:
                        self.logger.warning(f"⚠️ HTTP {response.status}")

                    if attempt < retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        return False

            except asyncio.TimeoutError:
                self.logger.warning(f"⏱ Timeout (attempt {attempt+1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return False
            except Exception as e:
                self.logger.warning(f"⚠️ Send error (attempt {attempt+1}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return False

        return False

    async def send_status_update(self, message: str) -> bool:
        if self.admin_chat_id:
            return await self.send_message(self.admin_chat_id, f"🤖 **BTCUSDT Bot**\n\n{message}")
        return True

    async def _get_tg_session(self) -> aiohttp.ClientSession:
        """
        Return (or lazily create) the shared persistent Telegram HTTP session.
        A single TCP connection is reused across all send_message / poll calls,
        eliminating the per-call TLS handshake overhead that the previous
        `async with aiohttp.ClientSession()` pattern imposed.
        """
        if self._tg_session is None or self._tg_session.closed:
            self._tg_connector = aiohttp.TCPConnector(
                limit=10,
                limit_per_host=10,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
            self._tg_session = aiohttp.ClientSession(
                connector=self._tg_connector,
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._tg_session


    async def send_startup_test_message(self) -> bool:
        """Send startup notification to both signal channel and admin chat"""
        try:
            ts  = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
            msg = (
                f"🐟 MIROFISH SWARM — ALL USDM MARKETS — ONLINE\n\n"
                f"Bot: {self.bot_username}\n"
                f"Signal Channel: @ichimokutradingsignal ({self.signal_channel_id})\n"
                f"Strategy: MiroFish Multi-Agent Swarm v5.0 (Graph+ReACT+Claude)\n"
                f"Source: github.com/666ghj/MiroFish\n"
                f"Timeframe: 15M (Primary)\n"
                f"Markets: ALL USDM Perpetuals (PARALLEL scan, ≤80 symbols, $50M+ vol)\n"
                f"Agents: 10 swarm agents | Consensus: ≥75% | Quorum: 5/10\n"
                f"AI: G0DM0D3 v3.0 | 26 free models | 5-tier ULTRAPLINIAN | EnsembleVote\n"
                f"Architecture: Profiles+Ontology+Graph+InsightForge+ReACT+Sessions\n"
                f"Confidence Gate: 80% post-boost | Min R:R 1.55:1 | Cap: 10/hr\n"
                f"Format: Unity-compatible\n"
                f"Started: {ts}\n"
                f"Status: ONLINE ✅"
            )
            # Send to signal channel
            ch_ok = await self.send_message(self.signal_channel_id, msg, parse_mode=None)
            if not ch_ok:
                self.logger.warning(
                    f"⚠️ Startup to channel {self.signal_channel_id} failed — "
                    f"ensure bot is admin of the channel"
                )
            # Also send to admin chat if different
            if self.admin_chat_id and str(self.admin_chat_id) != str(self.signal_channel_id):
                await self.send_message(self.admin_chat_id, msg, parse_mode=None)
            return ch_ok
        except Exception as e:
            self.logger.warning(f"⚠️ Startup message exception: {e}")
            return False

    async def close_tg_session(self):
        """
        Gracefully close the shared persistent Telegram HTTP session and connector.
        Called by the launcher's finally block on clean shutdown and by the standalone
        main() entry point.  Safe to call even if the session was never opened.
        """
        if self._tg_session and not self._tg_session.closed:
            try:
                await self._tg_session.close()
            except Exception:
                pass
        self._tg_session   = None
        self._tg_connector = None

        # Also stop the telegram Application updater if polling was started
        _app = getattr(self, "telegram_app", None)
        if _app is not None:
            try:
                if _app.updater and _app.updater.running:
                    await _app.updater.stop()
                await _app.stop()
                await _app.shutdown()
            except Exception:
                pass

        # Cancel the OutcomeTracker background task if running
        _task = getattr(self, "_outcome_tracker_task", None)
        if _task is not None and not _task.done():
            _task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(_task), timeout=2.0)
            except Exception:
                pass

        _pai_task = getattr(self, "_public_api_task", None)
        if _pai_task is not None and not _pai_task.done():
            _pai_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(_pai_task), timeout=2.0)
            except Exception:
                pass
        if self.public_api is not None:
            try:
                await self.public_api.close()
            except Exception:
                pass

        self.logger.debug("🔗 Telegram session closed")

    async def test_telegram_connection(self) -> bool:
        try:
            session = await self._get_tg_session()
            async with session.get(
                f"{self.base_url}/getMe",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    result = await r.json()
                    if result.get("ok"):
                        bot_name = result.get("result", {}).get("username", "unknown")
                        self.logger.info(f"✅ Telegram connected: @{bot_name}")
                        return True
        except Exception as e:
            self.logger.error(f"❌ Telegram connection test failed: {e}")
        return False

    # ─────────────────────────────────────────
    # Rate Limiting
    # ─────────────────────────────────────────

    # ── Rate-limiting constants — quality over quantity ─────────────────────
    # NOTE: _GLOBAL_MIN_GAP_SECONDS and _MAX_SIGNALS_PER_HOUR are now set as
    # instance attributes in __init__ (from env vars) and never as class-level
    # attributes — the class-level defaults previously here were always shadowed
    # by the __init__ instance assignments and served only to confuse readers.

    def _refresh_symbol_blacklist(self):
        """
        Refresh per-symbol performance stats and rebuild the blacklist.

        Symbols whose recent_loss_rate exceeds SYMBOL_BLOCK_LOSS_RATE (85%)
        over at least SYMBOL_BLOCK_MIN_TRADES (15) resolved trades are added
        to the blacklist and skipped by can_send_signal().

        Called at most once per SYMBOL_STATS_REFRESH_INTERVAL (20 min).
        """
        now = time.time()
        if (now - self._symbol_stats_last_refresh) < self.SYMBOL_STATS_REFRESH_INTERVAL:
            return
        if not (self.trade_memory and hasattr(self.trade_memory, "get_symbol_stats")):
            return
        try:
            stats = self.trade_memory.get_symbol_stats(
                min_trades=self.SYMBOL_BLOCK_MIN_TRADES
            )
            self._symbol_stats = stats
            self._symbol_stats_last_refresh = now

            # Symbols that must NEVER be blacklisted regardless of loss rate.
            # These are high-liquidity perpetual futures where temporary loss streaks
            # are statistical noise, and removing them would significantly reduce
            # signal volume and market coverage quality.
            PROTECTED_SYMBOLS = {
                "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
                "XRPUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT",
                "LINKUSDT", "DOTUSDT", "MATICUSDT", "LTCUSDT",
                "BCHUSDT", "UNIUSDT", "ATOMUSDT", "FTMUSDT",
                "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT",
                "NEARUSDT", "INJUSDT", "SEIUSDT", "TIAUSDT",
            }

            # v9.9 Apex-#5: Sortino-aware rescue.
            # Symbols flagged by recent_loss_rate alone may still be net-profitable
            # if their winning trades are large enough to offset the L:W ratio.
            # We compute an annualised-style Sortino ratio (mean / downside-stddev)
            # from the per-symbol pnl history; symbols with Sortino ≥ rescue
            # threshold AND ≥ MIN_TRADES are kept off the blacklist.
            _sortino_thr = float(getattr(self, "_unity_sortino_rescue_threshold", 1.20))
            _sortino_min = int(getattr(self, "_unity_sortino_min_trades", 10))

            def _sortino(pnl_history: list) -> float:
                if not pnl_history or len(pnl_history) < 3:
                    return 0.0
                _mean = sum(pnl_history) / len(pnl_history)
                _downside = [p for p in pnl_history if p < 0.0]
                if not _downside:
                    # No losses in window → infinite Sortino, return high constant
                    return 99.0 if _mean > 0 else 0.0
                # Downside deviation = sqrt(mean(min(0, p)^2))
                _dd_sq = sum((p * p) for p in _downside) / len(pnl_history)
                _dd = _dd_sq ** 0.5
                if _dd <= 0:
                    return 0.0
                return _mean / _dd

            # v15.3 Bug U FIX: Apply the same WR floor to PROTECTED symbols that
            # Bug R applied to _load_symbol_blacklist().  Without this, protected
            # symbols like NEARUSDT (8% WR / 25 trades) are always exempted from
            # the scan blacklist even though they're in the G_BLK filter blacklist.
            # They then waste a full swarm evaluation every ~10 min when their G_BLK
            # cooldown expires.  Fix: if a protected symbol has ≥15 all-time resolved
            # trades AND all-time WR < 15%, add it to the scan blacklist too.
            _PROTECTED_WR_FLOOR      = 0.15   # mirror of _FILTER_PROTECTED_WR_FLOOR
            _PROTECTED_MIN_TRADES    = 15     # mirror of _FILTER_PROTECTED_MIN_TRADES
            _protected_scan_blocked: list = []

            new_blacklist = set()
            _rescued: list = []
            for sym, s in stats.items():
                if sym in PROTECTED_SYMBOLS:
                    # v15.3 Bug U: enforce WR floor for protected symbols too
                    _p_total = s.get("total", 0)      # key is "total" not "total_trades"
                    _p_wins  = s.get("wins", 0)
                    _p_wr    = (_p_wins / _p_total) if _p_total > 0 else 1.0
                    if _p_total >= _PROTECTED_MIN_TRADES and _p_wr < _PROTECTED_WR_FLOOR:
                        new_blacklist.add(sym)
                        _protected_scan_blocked.append((sym, _p_wr, _p_total))
                    continue  # always skip the main recent_loss_rate check for protected
                recent_lr = s.get("recent_loss_rate", 0.0)
                if recent_lr >= self.SYMBOL_BLOCK_LOSS_RATE:
                    # Compute Sortino rescue check before blacklisting
                    _sr = 0.0
                    try:
                        if hasattr(self.trade_memory, "get_symbol_pnl_history"):
                            _hist = self.trade_memory.get_symbol_pnl_history(sym, limit=60)
                            if len(_hist) >= _sortino_min:
                                _sr = _sortino(_hist)
                    except Exception:
                        _sr = 0.0
                    if _sr >= _sortino_thr:
                        _rescued.append((sym, _sr, recent_lr))
                        continue  # rescued — net-profitable despite WR
                    new_blacklist.add(sym)
            if _rescued:
                _rescue_str = ", ".join(
                    f"{s}(Sortino={sr:.2f},LR={lr:.0%})" for s, sr, lr in _rescued
                )
                self.logger.info(
                    f"💎 [v9.9] Sortino rescue ({len(_rescued)}): {_rescue_str} — "
                    f"high-payoff symbols kept active despite WR ≤ {1 - self.SYMBOL_BLOCK_LOSS_RATE:.0%}"
                )
            if _protected_scan_blocked:
                for _psym, _pwr, _pt in _protected_scan_blocked:
                    self.logger.warning(
                        f"⚠️ [v15.3 Bug U] Protected symbol {_psym} added to scan blacklist "
                        f"(WR={_pwr:.0%}/{_pt} trades < {_PROTECTED_WR_FLOOR:.0%} floor) — "
                        f"mirrors Bug R fix in _load_symbol_blacklist()"
                    )

            added   = new_blacklist - self._symbol_blacklist
            removed = self._symbol_blacklist - new_blacklist
            self._symbol_blacklist = new_blacklist

            try:
                _all_loss_rate = self.trade_memory.get_recent_loss_rate(n=50)
                _wr = max(0.05, 1.0 - _all_loss_rate)
                self.strategy._global_win_rate = round(_wr, 3)
            except Exception:
                pass

            if added:
                self.logger.warning(
                    f"🚫 Symbol blacklist ADDED: {sorted(added)} "
                    f"(recent_loss_rate ≥ {self.SYMBOL_BLOCK_LOSS_RATE:.0%})"
                )
            if removed:
                self.logger.info(
                    f"✅ Symbol blacklist REMOVED (recovering): {sorted(removed)}"
                )
            if new_blacklist:
                self.logger.info(
                    f"🚫 Active symbol blacklist ({len(new_blacklist)}): "
                    f"{sorted(new_blacklist)}"
                )
        except Exception as e:
            self.logger.debug(f"_refresh_symbol_blacklist error: {e}")

    def prewarm_gblk_cooldowns(self, gblk_blacklist) -> None:
        """v15.3: Pre-set G_BLK cooldowns for all known lifetime-WR<30% symbols at startup.

        On every engine restart the in-memory _gblk_cooldown dict is cleared, causing
        each of the 38 G_BLK symbols to waste a full swarm+PM+NN evaluation before the
        cooldown is re-set (WLDUSDT restarted at 02:12:07, hit G_BLK again at 02:12:21).
        Fix: called immediately after _unity_signal_filter is wired in, pre-populates
        cooldowns so Cycle #1 never runs the swarm for known G_BLK symbols.
        Only runs once per engine startup (guarded by _gblk_prewarmed).
        """
        if self._gblk_prewarmed:
            return
        if not gblk_blacklist:
            return
        _now = time.time()
        _short_cd = min(self._GBLK_COOLDOWN_SEC, 300.0)  # 5-min pre-warm (covers full 5-min inter-cycle gap)
        _count = 0
        for sym in gblk_blacklist:
            if not isinstance(sym, str):
                continue
            _existing = self._gblk_cooldown.get(sym, 0.0)
            if _existing < _now + _short_cd:  # only set if not already longer
                self._gblk_cooldown[sym] = _now + _short_cd
                _count += 1
        self._gblk_prewarmed = True
        if _count:
            self.logger.info(
                f"🔥 [v15.3] G_BLK pre-warm: {_count} symbols → {_short_cd:.0f}s cooldown "
                f"(saves Cycle #1 swarm for all known lifetime-WR<30% symbols)"
            )

    def can_send_signal(self, symbol: str = "BTCUSDT", action: str = None,
                        swarm_consensus: float = 0.0,
                        skip_global_gap: bool = False) -> bool:
        """
        Three-tier rate limiter:
          1. Per-symbol cooldown  — each market has its own independent window
          2. Global caps          — minimum 90s gap between any two signals
                                    (across ALL symbols), and a strict 5-signals-
                                    per-hour ceiling to guarantee quality > quantity.
          3. Same-direction dedup — reject same symbol+direction within 45 min
                                    to prevent repetitive signal spam.

        skip_global_gap: when True (same-cycle Phase 2 recheck under per-cycle cap),
          Tier 2a global minimum gap is bypassed.  Rationale: within a single parallel
          scan cycle, multiple symbols pass Phase 1 simultaneously.  The first to
          acquire _signal_gate_lock sets signal_timestamps[-1]; the second is then
          blocked by the 90s gap even though it is a DIFFERENT, diversified symbol
          in the SAME cycle — exactly what the per-cycle cap (max 3) is designed to
          allow.  The global gap still applies BETWEEN cycles (the pre-check in
          scan_and_signal uses skip_global_gap=False). [v15.3]

        swarm_consensus: when ≥0.95 (unanimous), blacklist is bypassed because
        10-agent 100% consensus outweighs recent-trade-sample statistics.

        This prevents per-symbol spam while still allowing diverse market coverage.
        """
        now_ts  = time.time()
        now_dt  = datetime.now()
        cooldown = self.min_signal_interval_minutes * 60

        # Housekeeping: always discard timestamps older than 24h — runs unconditionally
        # so the list stays bounded even when every signal is blocked by Tier-1 cooldown.
        cutoff_24h = now_dt - timedelta(hours=24)
        self.signal_timestamps = [ts for ts in self.signal_timestamps if ts > cutoff_24h]

        # FIX 8: Refresh per-symbol blacklist (rate-limited to 20 min)
        self._refresh_symbol_blacklist()

        # FIX 8: Reject signals for persistently losing symbols.
        # CONSENSUS OVERRIDE: unanimous (≥95%) swarm signals bypass the blacklist —
        # 10 independent agents agreeing is stronger evidence than the small recent
        # trade sample that drives the blacklist.
        if symbol in self._symbol_blacklist:
            _unanimous_override = swarm_consensus >= 0.95
            if _unanimous_override:
                stats = self._symbol_stats.get(symbol, {})
                self.logger.info(
                    f"⚡ [{symbol}] Blacklist OVERRIDDEN by unanimous consensus "
                    f"({swarm_consensus:.0%}) — recent_loss_rate="
                    f"{stats.get('recent_loss_rate', 0.0):.0%}"
                )
            else:
                stats = self._symbol_stats.get(symbol, {})
                self.logger.info(
                    f"🚫 [{symbol}] Blocked — persistently losing symbol "
                    f"(recent_loss_rate={stats.get('recent_loss_rate', 0.0):.0%} "
                    f"≥ {self.SYMBOL_BLOCK_LOSS_RATE:.0%}, consensus={swarm_consensus:.0%} < 95%)"
                )
                return False

        # ── Tier 1: per-symbol cooldown ──────────────────────────────────────
        last_sym_ts = self._symbol_last_signal.get(symbol, 0.0)
        sym_elapsed = now_ts - last_sym_ts
        if sym_elapsed < cooldown:
            self.logger.debug(
                f"⏳ [{symbol}] Per-symbol rate limit — "
                f"{cooldown - sym_elapsed:.0f}s remaining"
            )
            return False

        # ── Tier 1b: same-direction deduplication ────────────────────────────
        # If the same symbol+direction was sent within _SAME_DIR_DEDUP_SECONDS
        # (45 min), reject to prevent repetitive signal spam. Only active when
        # action is explicitly provided by the caller (process_signals does this).
        if action is not None:
            _last_dir = self._symbol_last_direction.get(symbol)
            if _last_dir is not None:
                _last_action, _last_dir_ts = _last_dir
                if _last_action == action and (now_ts - _last_dir_ts) < self._SAME_DIR_DEDUP_SECONDS:
                    _remaining = self._SAME_DIR_DEDUP_SECONDS - (now_ts - _last_dir_ts)
                    self.logger.debug(
                        f"♻️ [{symbol}] Same-direction dedup ({action}) — "
                        f"{_remaining/60:.0f}min remaining (45-min window)"
                    )
                    return False

        # ── Tier 2a: global minimum gap — at least 90s between any signals ──
        # signal_timestamps is always appended in chronological order, so the
        # most recent timestamp is always at [-1] — O(1) instead of O(n) max().
        # v15.3: skip_global_gap=True for same-cycle Phase 2 rechecks: multiple
        # symbols that pass Phase 1 in the same asyncio.gather batch should not
        # be serialised by the 90s gap — the per-cycle cap (3 max) handles
        # anti-correlation; the gap is only meaningful between scan cycles.
        if not skip_global_gap and self.signal_timestamps:
            last_any = self.signal_timestamps[-1]
            gap = (now_dt - last_any).total_seconds()
            if gap < self._GLOBAL_MIN_GAP_SECONDS:
                self.logger.debug(
                    f"⏳ [global] Min gap — {self._GLOBAL_MIN_GAP_SECONDS - gap:.0f}s remaining"
                )
                return False

        # ── Tier 2b: global hourly cap ────────────────────────────────────────
        cutoff_1h = now_dt - timedelta(hours=1)
        _recent_1h_count = sum(1 for ts in self.signal_timestamps if ts > cutoff_1h)
        if _recent_1h_count >= self._MAX_SIGNALS_PER_HOUR:
            self.logger.info(
                f"🚦 [global] Hourly cap reached ({_recent_1h_count}/{self._MAX_SIGNALS_PER_HOUR}) "
                f"— pausing [{symbol}]"
            )
            return False

        return True

    def get_time_until_next_signal(self, symbol: str = "BTCUSDT") -> int:
        last_ts = self._symbol_last_signal.get(symbol, 0.0)
        elapsed = time.time() - last_ts
        return max(0, int(self.min_signal_interval_minutes * 60 - elapsed))

    async def update_loss_streak(self, is_loss: bool):
        """
        Called by OutcomeTracker (or any resolver) whenever a trade resolves.
        Protected by _streak_lock to prevent race conditions with parallel scans.
        """
        async with self._streak_lock:
            self._update_loss_streak_inner(is_loss)

    def _update_loss_streak_inner(self, is_loss: bool):
        if not is_loss:
            if self.STREAK_RESET_ON_WIN and self._consecutive_losses > 0:
                old_boost = self._adaptive_conf_boost
                self._consecutive_losses   = 0
                self._adaptive_conf_boost  = 0.0
                self.logger.info(
                    f"✅ Loss streak RESET on WIN — "
                    f"conf boost removed (was +{old_boost:.1f}%)"
                )
            return

        self._consecutive_losses += 1
        # v5.7 Warmup Guard: suppress streak boost during first 5 min of session.
        # OutcomeTracker resolves all open historical trades at startup, calling
        # this function many times quickly and double-stacking the threshold with
        # the Unity booster.  Skip boost raises in the warmup window; tracking still
        # continues so the counter reflects true consecutive-loss state once live.
        _u_booster = getattr(self, "_unity_booster", None)
        _in_warmup = False
        if _u_booster is not None:
            _in_warmup = (time.time() - _u_booster._session_start_time) < _u_booster._WARMUP_SECONDS
        if _in_warmup and self._consecutive_losses >= self.STREAK_TRIGGER_N:
            self.logger.debug(
                f"🛡️ [Bot Warmup] streak={self._consecutive_losses} — "
                f"conf boost suppressed during 5-min startup warmup (v5.7)"
            )
            return
        if self._consecutive_losses >= self.STREAK_TRIGGER_N:
            extra = (self._consecutive_losses - self.STREAK_TRIGGER_N + 1)
            new_boost = min(
                extra * self.STREAK_BOOST_PER_LOSS,
                self.STREAK_MAX_BOOST_PCT
            )
            if new_boost != self._adaptive_conf_boost:
                base = float(os.getenv("AI_THRESHOLD_PERCENT", "80"))
                self._adaptive_conf_boost = new_boost
                self.logger.warning(
                    f"🛡️ Loss streak={self._consecutive_losses} — "
                    f"conf gate raised to {base + new_boost:.0f}% "
                    f"(base={base:.0f}% + boost={new_boost:.1f}%)"
                )

    # ─────────────────────────────────────────
    # Signal Formatting (MiroFish Swarm style)
    # ─────────────────────────────────────────

    def format_swarm_signal(self, signal: SwarmSignal) -> str:
        """
        IRONS AI-style Unity-compatible MiroFish signal.
        Unity Engine parses: direction / exchange / leverage / entry / TPs / SL.
        IRONS AI analytics panel appended below for human traders.
        """
        # ── Prediction Market line (only if computed) ──
        _H   = getattr(signal, "shannon_entropy",    0.0)
        _fk  = getattr(signal, "kelly_fraction",     0.0)
        _dk  = getattr(signal, "kelly_decay_factor", 1.0)
        _pm_line = ""
        if _H > 0 or _fk > 0:
            _certainty = max(0.0, 1.0 - _H) * 100
            _pm_line = f"PM: Certainty {_certainty:.0f}% · Kelly {_fk:.1%} · Maturity {_dk:.0%}"

        # ── Build IRONS AI panel via formatter ──
        try:
            from SignalMaestro.irons_ai_scorer import format_irons_panel
            msg = format_irons_panel(
                signal_symbol=signal.symbol or "BTCUSDT",
                signal_action=signal.action,
                signal_leverage=signal.leverage,
                signal_entry=signal.entry_price,
                signal_sl=signal.stop_loss,
                signal_tp1=signal.take_profit_1 or signal.take_profit,
                signal_tp2=signal.take_profit_2,
                signal_tp3=signal.take_profit_3,
                signal_tp4=getattr(signal, "take_profit_4", 0.0),
                signal_rr=signal.risk_reward_ratio,
                signal_tf=getattr(signal, "timeframe", "15m"),
                signal_session=getattr(signal, "market_session", ""),
                irons={
                    "score":       getattr(signal, "irons_score", 0),
                    "risk_label":  getattr(signal, "irons_risk", ""),
                    "indicators":  getattr(signal, "irons_indicators", {}),
                    "categories":  getattr(signal, "irons_categories", {}),
                    "patterns":    getattr(signal, "irons_patterns", []),
                    "mtf": {
                        "4H":  getattr(signal, "mtf_4h", "NEUTRAL"),
                        "1H":  getattr(signal, "mtf_1h", "NEUTRAL"),
                        "15M": signal.action,
                    },
                    "squeeze_on":  getattr(signal, "irons_squeeze", False),
                },
                swarm_consensus=signal.swarm_consensus,
                confidence=signal.confidence,
                agent_votes=signal.agent_votes or {},
                pm_line=_pm_line,
                ai_narrative=getattr(signal, "ai_narrative", ""),
            )
            return msg
        except Exception as _e:
            self.logger.warning(f"IRONS panel error, falling back: {_e}")

        # ── Fallback: compact Unity format ──
        direction = "LONG" if signal.action == "BUY" else "SHORT"
        d_emoji   = "🟢" if signal.action == "BUY" else "🔴"
        entry = signal.entry_price; sl = signal.stop_loss
        tp1 = signal.take_profit_1 or signal.take_profit
        tp2 = signal.take_profit_2; tp3 = signal.take_profit_3
        tp4 = getattr(signal, "take_profit_4", 0.0)
        lev = signal.leverage; rr = signal.risk_reward_ratio
        tf  = (getattr(signal, "timeframe", "15m") or "15m").upper()
        session = (getattr(signal, "market_session", "") or "").upper()
        consensus_pct = signal.swarm_consensus * 100
        sym_tag = f"#{signal.symbol}" if signal.symbol else "#BTCUSDT"

        def _fmt(p: float) -> str:
            if p >= 1000:    return f"{p:.2f}"
            elif p >= 10:    return f"{p:.4f}"
            elif p >= 0.1:   return f"{p:.5f}"
            else:            return f"{p:.8f}"

        is_buy = signal.action == "BUY"
        def _pct(ref, val, up):
            if not ref: return 0.0
            return (val-ref)/ref*100 if up else (ref-val)/ref*100
        sl_pct  = _pct(entry, sl,  not is_buy)
        tp1_pct = _pct(entry, tp1, is_buy)
        tp2_pct = _pct(entry, tp2, is_buy)
        tp3_pct = _pct(entry, tp3, is_buy)
        tp4_pct = _pct(entry, tp4, is_buy) if tp4 else 0.0

        _short = {
            "TrendAgent": "Tr", "MomentumAgent": "Mo", "VolumeAgent": "Vo",
            "VolatilityAgent": "Vl", "OrderFlowAgent": "OF",
            "SentimentAgent": "Se", "FundingFlowAgent": "Fn",
            "PivotSRAgent": "Pi", "FLOOPAgent": "FL", "AIOrchestrationAgent": "AI",
        }
        _sym = {"BUY": "B", "SELL": "S", "NEUTRAL": "N"}
        votes_str = " ".join(
            f"{_short.get(n, n[:2])}:{_sym.get(v, v[0])}"
            for n, v in (signal.agent_votes or {}).items()
        )
        ts = signal.timestamp.strftime("%H:%M") if signal.timestamp else "—"
        sess_tag = f" {session[:2]}" if session else ""
        pm_section = f"\n{_pm_line}" if _pm_line else ""

        tp4_line = f"4) {_fmt(tp4)}\n" if tp4 else ""
        tp4_pct_str = f"/+{tp4_pct:.1f}%" if tp4 else ""

        return (
            f"{d_emoji} {sym_tag} {direction}\n"
            f"Exchange: Binance Futures\n"
            f"Leverage: Cross {lev}x\n\n"
            f"Entry Targets:\n1) {_fmt(entry)}\n\n"
            f"Take-Profit Targets:\n"
            f"1) {_fmt(tp1)}\n2) {_fmt(tp2)}\n3) {_fmt(tp3)}\n{tp4_line}\n"
            f"Stop Targets:\n1) {_fmt(sl)}\n\n"
            f"⚡{tf}{sess_tag} · {consensus_pct:.0f}%🐟 · {signal.confidence:.0f}%Conf · "
            f"RSI {signal.rsi:.0f} · R:R 1:{rr:.1f}\n"
            f"TP +{tp1_pct:.1f}%/+{tp2_pct:.1f}%/+{tp3_pct:.1f}%{tp4_pct_str} · SL -{sl_pct:.1f}% · "
            f"{votes_str} · {ts} UTC{pm_section}\n"
            f"📡 @ichimokutradingsignal | MiroFish Swarm × IRONS AI"
        )

    async def send_signal_to_channel(self, signal: SwarmSignal,
                                     bb_position: float = None,
                                     _skip_rate_check: bool = False) -> bool:
        """
        Send formatted Unity-compatible swarm signal.
        Uses per-symbol rate limiting so each market has its own cooldown.
        Broadcasts to signal_channel_id (@ichimokutradingsignal).
        Also pings admin_chat_id if configured and different from channel.

        Args:
            _skip_rate_check: Internal flag — set True when called from
                process_signals() while the _signal_gate_lock is already
                held and can_send_signal() has already been checked.
                Avoids the otherwise redundant 3rd rate-limit check.
        """
        try:
            symbol = getattr(signal, "symbol", "BTCUSDT") or "BTCUSDT"

            # Only re-check rate limiting when called directly (not via the
            # locked path in process_signals which already verified the gates).
            if not _skip_rate_check and not self.can_send_signal(symbol):
                return False

            formatted = self.format_swarm_signal(signal)

            # ── Primary: broadcast to signal channel ──
            channel_ok = await self.send_message(self.signal_channel_id, formatted, parse_mode=None)

            # ── Secondary: admin notification (if different from channel) ──
            if self.admin_chat_id and str(self.admin_chat_id) != str(self.signal_channel_id):
                direction = "LONG" if signal.action == "BUY" else "SHORT"
                d_emoji   = "🟢" if signal.action == "BUY" else "🔴"
                _tp2_a = (f"\n🎯 TP2:   {signal.take_profit_2:.4g}"
                          if getattr(signal, "take_profit_2", 0) else "")
                _tp3_a = (f"\n🎯 TP3:   {signal.take_profit_3:.4g}"
                          if getattr(signal, "take_profit_3", 0) else "")
                admin_msg = (
                    f"{d_emoji} Signal → {self.signal_channel_id}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 {symbol} {direction}\n"
                    f"📥 Entry: {signal.entry_price:.4g}\n"
                    f"🛑 SL:    {signal.stop_loss:.4g}\n"
                    f"🎯 TP1:   {signal.take_profit_1:.4g}{_tp2_a}{_tp3_a}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Swarm: {signal.swarm_consensus:.0%} | Conf: {signal.confidence:.1f}%"
                )
                await self.send_message(self.admin_chat_id, admin_msg, parse_mode=None)

            if channel_ok:
                now_ts = time.time()
                self._symbol_last_signal[symbol] = now_ts
                self._symbol_signal_count[symbol] = self._symbol_signal_count.get(symbol, 0) + 1
                self.last_signal_time = datetime.now()
                self.signal_timestamps.append(self.last_signal_time)
                self.signal_count += 1
                # Record direction for same-direction deduplication (45-min window)
                self._symbol_last_direction[symbol] = (signal.action, now_ts)

                # Record in trade memory for self-learning
                # Use the bb_position passed from process_signals (per-coroutine local),
                # falling back to the instance attribute only if called standalone.
                if self.trade_memory:
                    try:
                        _bb_pos = bb_position if bb_position is not None else self._current_bb_position
                        self.trade_memory.record_signal(signal, bb_position=_bb_pos)
                    except Exception as mem_err:
                        self.logger.debug(f"Trade memory record failed: {mem_err}")

                # Cache signal in TradingInterface for one-tap inline-keyboard execution
                try:
                    _sig_id = f"{symbol}_{signal.action}_{int(now_ts)}"
                    _ti = getattr(self, "trading_interface", None)
                    if _ti and callable(getattr(_ti, "cache_signal", None)):
                        # nn_win_prob is a fraction (0.0–1.0); trading_interface
                        # normalises it automatically if > 1.0, so store as-is.
                        _nwp = float(
                            getattr(signal, "nn_win_prob",
                                    getattr(signal, "win_probability",
                                            getattr(signal, "confidence", 50.0)) or 50.0)
                        )
                        # If stored as percentage (e.g. 72.5), normalise to fraction
                        if _nwp > 1.0:
                            _nwp = _nwp / 100.0
                        _ti.cache_signal(_sig_id, {
                            "symbol":      symbol,
                            "direction":   "LONG" if signal.action == "BUY" else "SHORT",
                            "entry":       float(getattr(signal, "entry_price",   0) or 0),
                            "sl":          float(getattr(signal, "stop_loss",     0) or 0),
                            "tp1":         float(getattr(signal, "take_profit_1", 0) or 0),
                            "tp2":         float(getattr(signal, "take_profit_2", 0) or 0),
                            "tp3":         float(getattr(signal, "take_profit_3", 0) or 0),
                            "quality":     float(getattr(signal, "confidence",    0) or 0),
                            "win_prob":    _nwp,
                            "nn_win_prob": _nwp,
                        })
                    # Send admin a private copy with inline Execute/Skip/Details buttons
                    if self.admin_chat_id and str(self.admin_chat_id) != str(self.signal_channel_id):
                        try:
                            _dir  = "LONG" if signal.action == "BUY" else "SHORT"
                            _emj  = "🟢" if signal.action == "BUY" else "🔴"
                            _tp2_s = (f"\n🎯 TP2:   `{signal.take_profit_2:.4g}`"
                                      if getattr(signal, "take_profit_2", 0) else "")
                            _tp3_s = (f"\n🎯 TP3:   `{signal.take_profit_3:.4g}`"
                                      if getattr(signal, "take_profit_3", 0) else "")
                            _pri  = (
                                f"{_emj} *{symbol} {_dir}*\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"📥 Entry: `{signal.entry_price:.4g}`\n"
                                f"🛑 SL:    `{signal.stop_loss:.4g}`\n"
                                f"🎯 TP1:   `{signal.take_profit_1:.4g}`{_tp2_s}{_tp3_s}\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"Quality: `{signal.confidence:.0f}%` | Consensus: `{signal.swarm_consensus:.0%}`\n"
                            )
                            _kb = None
                            if _ti and callable(getattr(_ti, "build_signal_action_kb", None)):
                                _kb = _ti.build_signal_action_kb(_sig_id)
                            await self.send_message(
                                self.admin_chat_id, _pri,
                                parse_mode="Markdown",
                                reply_markup=_kb,
                            )
                        except Exception as _kb_err:
                            self.logger.debug(f"Admin signal inline-kb error: {_kb_err}")
                except Exception as _cache_err:
                    self.logger.debug(f"Signal cache error: {_cache_err}")

                self.logger.info(
                    f"📡 Signal sent: {symbol} {signal.action} @ {signal.entry_price:.4g} "
                    f"→ channel={self.signal_channel_id} "
                    f"(consensus={signal.swarm_consensus:.0%} conf={signal.confidence:.1f}%)"
                )
                return True
            else:
                self.logger.warning(
                    f"⚠️ Signal failed → channel={self.signal_channel_id} "
                    f"(bot may not be admin of the channel)"
                )
                return False

        except Exception as e:
            self.logger.error(f"send_signal_to_channel error: {e}")
            return False

    # ─────────────────────────────────────────
    # Scanner
    # ─────────────────────────────────────────

    async def _refresh_symbol_list(self):
        """
        Refresh the active symbol list from Binance every SYMBOL_REFRESH_INTERVAL.
        Falls back to keeping the current list if the API call fails.

        Uses double-checked locking (_symbols_refresh_lock) so that when 30 parallel
        scan coroutines all detect the interval has expired at the same instant, only
        ONE of them issues the Binance API call — the others re-check inside the lock,
        find the list is now fresh, and return immediately.
        """
        now = time.time()
        # ── Fast path (no lock): still fresh? ──────────────────────────────────
        if now - self._symbols_refresh_time < self.SYMBOL_REFRESH_INTERVAL:
            return

        # ── Slow path: acquire lock, re-check, then refresh if still needed ───
        async with self._symbols_refresh_lock:
            # Another coroutine may have refreshed while we waited for the lock
            if time.time() - self._symbols_refresh_time < self.SYMBOL_REFRESH_INTERVAL:
                return  # Already refreshed — nothing to do

            try:
                symbols = await self.trader.get_all_usdm_symbols()
                if symbols:
                    self._active_symbols       = symbols
                    self._symbols_refresh_time = time.time()
                    self.logger.info(
                        f"🌐 Symbol list refreshed: {len(symbols)} markets active "
                        f"(top 5: {symbols[:5]})"
                    )
            except Exception as e:
                self.logger.warning(f"⚠️ Symbol refresh failed: {e} — keeping current list")

    async def scan_and_signal(self, symbol: str = "BTCUSDT") -> bool:
        """
        Run MiroFish swarm scan for a specific symbol and send signals if qualifying.

        Args:
            symbol: USDM futures symbol to scan (e.g. "ETHUSDT")

        Returns:
            True if a signal was generated (not necessarily sent), False otherwise.
        """
        try:
            # ── Fast pre-checks BEFORE expensive 10-agent swarm evaluation ──
            # These checks mirror the first gates in can_send_signal but run
            # BEFORE generate_multi_timeframe_signals, saving ~29% of strategy
            # evaluations (blacklisted symbols) and ~30% more (cooldown symbols).

            # Pre-check 1: skip blacklisted symbols immediately
            if symbol in self._symbol_blacklist:
                self.logger.debug(f"[{symbol}] Blacklisted — skip strategy eval")
                return False

            # Pre-check 2: per-symbol 5-min cooldown
            _cooldown_s = self.min_signal_interval_minutes * 60
            if time.time() - self._symbol_last_signal.get(symbol, 0.0) < _cooldown_s:
                return False

            # Pre-check 2b: NN-reject cooldown — symbol was catastrophically
            # rejected (win_prob < 10%) and is suppressed for 10 min. [v15.3]
            _nn_reject_exp = self._nn_reject_cooldown.get(symbol, 0.0)
            if time.time() < _nn_reject_exp:
                return False

            # Pre-check 2b2: NN hard-reject cooldown — symbol failed the NN gate
            # in the _far_below band (win_prob 20-36%) and is suppressed for 120s.
            # Prevents MANTRAUSDT pattern (win_prob=22-27%) from burning full
            # swarm+NN+PM pipeline every 15s cycle. [v15.3 Bug F fix]
            _nn_hard_reject_exp = self._nn_hard_reject_cooldown.get(symbol, 0.0)
            if time.time() < _nn_hard_reject_exp:
                return False

            # Pre-check 2k: Open-position deduplication guard [v15.3 Bug G fix]
            # Block any symbol that already has an unresolved trade in the DB.
            # Per-symbol cooldown resets on restart → PENGUUSDT/AIOTUSDT/MUSDT
            # accumulated 9/5/4 duplicate open trades per session.  DB cache is
            # refreshed every 60s (cheap sync query, trade_memory uses sqlite3).
            _now_pre2k = time.time()
            if _now_pre2k - self._open_symbols_last_refresh > self._OPEN_SYMBOLS_REFRESH_SEC:
                try:
                    _open_trades = self.trade_memory.get_open_trades()
                    self._open_symbols_set = {t.get("symbol", "") for t in _open_trades}
                    self._open_symbols_last_refresh = _now_pre2k
                except Exception:
                    pass  # cache stays stale — safe fail-open
            if symbol in self._open_symbols_set:
                self.logger.debug(
                    f"⏳ [{symbol}] Open-position guard — already has open trade in DB "
                    f"(v15.3 Bug G fix: {len(self._open_symbols_set)} open symbols cached)"
                )
                return False

            # Pre-check 2c: EV-fail cooldown — symbol failed Gate 0 EV recently
            # with the same TP/SL geometry (same market conditions → same EV).
            # Avoids burning full Phase 1 evaluation (5+ network calls) for a
            # trade that won't pass G0 regardless. [v15.3]
            _ev_fail_exp = self._ev_fail_cooldown.get(symbol, 0.0)
            if time.time() < _ev_fail_exp:
                return False

            # Pre-check 2d: orderbook-fail cooldown — symbol failed G2.5 (orderbook
            # opposed) recently with persistent STRONG flow against the signal.
            # Saves the full Phase 1 pipeline: swarm(10-agent) + NN + PM + ATAS boost
            # for a trade that will be rejected by orderbook direction again in the
            # same 2-min orderbook state window. [v15.3]
            _ob_fail_exp = self._ob_fail_cooldown.get(symbol, 0.0)
            if time.time() < _ob_fail_exp:
                return False

            # Pre-check 2e: AI-gate-block cooldown — symbol's swarm conf is below the
            # AI bypass threshold while LLMs are rate-limited.  INJUSDT pattern: runs
            # full swarm every cycle, blocked by AI gate (conf+boost < threshold).
            # Only suppresses when LLMs are still not available (self-heals on recovery).
            # [v15.3]
            _ai_block_exp = self._ai_gate_block_cooldown.get(symbol, 0.0)
            if time.time() < _ai_block_exp:
                _gd = get_godmod3_engine()
                if not _gd.has_available_models():
                    return False   # LLMs still down — skip swarm until cooldown expires

            # Pre-check 2f: G_BLK cooldown — symbol was rejected by the engine's lifetime
            # WR<30% blacklist (G_BLK gate).  The blacklist is read from trade_history.db
            # and won't change until new trades resolve (hours+).  Suppress for 10 min to
            # avoid burning the full 7-agent swarm on a symbol whose gate outcome is known.
            # Self-heals when cooldown expires so a trade resolution that flips WR≥30%
            # will be caught within 10 min. [v15.3]
            _gblk_exp = self._gblk_cooldown.get(symbol, 0.0)
            if time.time() < _gblk_exp:
                return False   # G_BLK will fire again — skip swarm until cooldown expires

            # Pre-check 2g: pre-boost impossibility cooldown — per-symbol loss-streak
            # penalty reduced effective confidence below conf+MAX_BOOST < threshold, causing
            # silent DEBUG-level return with no cooldown.  ADAUSDT: conf=71.9%-penalty=9pt
            # → 62.9%+15=77.9% < 85% → fired 10+ times per 4 minutes.  Suppress 90s.
            # Self-heals when streak clears (penalty drops) or confidence rises. [v15.3]
            _pb_fail_exp = self._preboost_fail_cooldown.get(symbol, 0.0)
            if time.time() < _pb_fail_exp:
                return False   # pre-boost gate will fire again — skip swarm until cooldown expires

            # Pre-check 2h: G3_FAIL cooldown — symbol failed Gate 3 (confidence below RL
            # threshold) after full Phase 1 evaluation.  APEUSDT: swarm=73.4% + PM+7 →
            # 77.4% < 84% RL threshold → 10+ consecutive failures in 30 min (every 20s
            # cycle).  Suppress 90s base, escalate to 300s after 3 consecutive G3 fails.
            # Self-heals when conf improves or RL threshold drops. [v15.3]
            _g3_fail_exp = self._g3_fail_cooldown.get(symbol, 0.0)
            if time.time() < _g3_fail_exp:
                return False   # G3 will fire again — skip swarm+Phase1 until cooldown expires

            # Pre-check 2i: G1_FAIL cooldown — symbol failed Gate 1 (weighted R:R below
            # adaptive floor) which is pure TP/SL geometry from the same OHLCV bar.
            # AIGENSYNUSDT: R:R=2.79 < 3.20 every 16s (22 hits).  Price doesn't shift
            # enough in 20s to change the R:R geometry.  Suppress 90s.  Self-heals when
            # price movement changes TP/SL placement or WR improves (floor drops). [v15.3]
            _g1_fail_exp = self._g1_fail_cooldown.get(symbol, 0.0)
            if time.time() < _g1_fail_exp:
                return False   # G1 will fire again — skip swarm until R:R geometry changes

            # Pre-check 2j: G9_FAIL cooldown — symbol failed Gate 9 (composite quality
            # below adaptive floor) after full Phase 1+2 evaluation.  APEUSDT: quality=
            # 42-50 < 55-58 floor every 20s (21 hits).  PENGUUSDT=20, APTUSDT=20,
            # MANTRAUSDT=16.  Quality is computed from 25 IRONS indicators that won't
            # shift in 20s without a genuine regime change.  Suppress 90s base, escalate
            # to 300s after 3 consecutive G9 fails.  Self-heals on regime shift. [v15.3]
            _g9_fail_exp = self._g9_fail_cooldown.get(symbol, 0.0)
            if time.time() < _g9_fail_exp:
                return False   # G9 will fire again — skip swarm+Phase1 until quality improves

            # Pre-check 3: global hourly cap — saves all Phase-1 network I/O when
            # the cap is already hit (avoids Binance klines + ATAS + MI + AI calls
            # for every remaining symbol in the parallel batch).
            _now_pre = datetime.now()
            _cutoff_pre = _now_pre - timedelta(hours=1)
            if sum(1 for _t in self.signal_timestamps if _t > _cutoff_pre) >= self._MAX_SIGNALS_PER_HOUR:
                return False

            # Pre-check 4: global minimum gap — skip if last signal was < 90s ago.
            if self.signal_timestamps:
                _gap_pre = (_now_pre - self.signal_timestamps[-1]).total_seconds()
                if _gap_pre < self._GLOBAL_MIN_GAP_SECONDS:
                    return False

            self.logger.debug(f"🐟 MiroFish Swarm scanning {symbol}...")

            signals = await self.strategy.generate_multi_timeframe_signals(
                self.trader, symbol=symbol
            )

            # Health tracking: G0DM0D3+OpenRouter and AgencyAgents (FIX session 5)
            # Track whenever G0DM0D3 was recently active.  success=True always because
            # "no signal from scan" means market conditions didn't qualify — that is the
            # CORRECT engine behavior, not a failure.  Only record False on exceptions.
            _uh_gm = getattr(self, "_unity_health", None)
            if _uh_gm:
                try:
                    from SignalMaestro.godmod3_strategy import get_godmod3_engine as _get_gm
                    _gm_eng = _get_gm()
                    _gm_live = _gm_eng.was_recently_available(60) or _gm_eng.has_available_models()
                    if _gm_live:
                        _uh_gm.record_call("G0DM0D3+OpenRouter", True)
                        _uh_gm.record_call("AgencyAgents", True)
                except Exception:
                    pass

            if not signals:
                self.logger.debug(f"[{symbol}] No qualifying swarm signals")
                return False

            return await self.process_signals(signals)

        except Exception as e:
            self.logger.error(f"scan_and_signal({symbol}) error: {e}")
            return False

    async def scan_next_symbol(self) -> bool:
        """
        Round-robin: scan the next symbol in the active list.
        Returns True if a signal was generated.
        (Legacy — kept for backward compatibility; run_continuous_scanner now
        uses scan_all_parallel for true simultaneous coverage.)
        """
        if not self._active_symbols:
            return False

        idx = self._symbol_scan_index % len(self._active_symbols)
        symbol = self._active_symbols[idx]
        self._symbol_scan_index = (idx + 1) % len(self._active_symbols)

        return await self.scan_and_signal(symbol)

    async def scan_all_parallel(self, symbols: List[str]) -> int:
        """
        TRUE parallel scan of ALL provided symbols simultaneously using asyncio.gather.

        Replaces the legacy round-robin approach where symbols were scanned one-by-one
        with 5-15s delays, causing a full-cycle lag of 6-20 minutes for 80 symbols.
        Now: all 80 symbols complete in ~20-40 seconds (network-bound).

        A configurable Semaphore (default 20, set via SCAN_PARALLEL_LIMIT env var) limits
        concurrent in-flight requests to Binance to prevent rate-limit errors (HTTP 429)
        while still achieving ~4× parallel throughput.

        Args:
            symbols: list of USDM symbols to scan

        Returns:
            Number of signals generated (not necessarily all sent — rate-limits apply)
        """
        if not symbols:
            return 0

        # Reset per-cycle counter so the anti-correlation cap applies fresh each scan.
        self._cycle_signals_sent = 0

        # Reuse the pre-built self._scan_semaphore (created in __init__) to
        # avoid allocating a new asyncio.Semaphore object every 30-60s scan cycle.
        async def _scan_one(symbol: str) -> bool:
            # Skip immediately if IP ban becomes active mid-scan (avoids
            # hammering Binance from queued coroutines waiting on semaphore).
            if self.trader.is_ip_banned():
                return False
            async with self._scan_semaphore:
                # Re-check after acquiring semaphore (may have waited in queue)
                if self.trader.is_ip_banned():
                    return False
                try:
                    return await asyncio.wait_for(
                        self.scan_and_signal(symbol),
                        timeout=30.0,
                    )
                except asyncio.TimeoutError:
                    self.logger.debug(f"[{symbol}] parallel scan timed out (30s)")
                    return False
                except Exception as exc:
                    self.logger.debug(f"[{symbol}] parallel scan error: {exc}")
                    return False

        results = await asyncio.gather(
            *[_scan_one(sym) for sym in symbols],
            return_exceptions=True,
        )

        signals_sent = sum(1 for r in results if r is True)
        errors       = sum(1 for r in results if isinstance(r, Exception))
        self.logger.info(
            f"⚡ Parallel scan done: {len(symbols)} symbols | "
            f"{signals_sent} sent | {errors} errors"
        )
        return signals_sent

    async def process_signals(self, signals: List[SwarmSignal]) -> bool:
        """
        Process swarm signals with confidence boosting and rate limiting.

        Two-phase design to maximize parallel scanner throughput:
          Phase 1 — Boost analysis (outside lock): all network I/O (Binance klines,
            ATAS, market intel, insider, microstructure) runs concurrently across the
            20 parallel scan coroutines — no serialisation.
          Phase 2 — Atomic gate (inside lock): re-check rate limits, apply NN gate,
            final confidence threshold, send, record.  Lock held for milliseconds only.

        Returns:
            True  — signal was broadcast to the Telegram channel.
            False — signal was filtered out, rate-limited, or failed to send.
        """
        if not signals:
            return False

        # Base confidence threshold + adaptive loss-streak boost.
        # After STREAK_TRIGGER_N consecutive losses the gate rises by
        # STREAK_BOOST_PER_LOSS% per additional loss (capped at STREAK_MAX_BOOST_PCT)
        # so the bot becomes more selective until the NN re-learns from the mistakes.
        # _ai_threshold_pct is cached at __init__ to avoid per-signal env reads
        # from 20 parallel coroutines every scan cycle.
        confidence_threshold = self._ai_threshold_pct + self._adaptive_conf_boost

        # ── Recent-loss-rate global gate (non-consecutive) ────────────────────
        # Consecutive-loss streak resets on any win, so it can't detect a
        # sustained 70-80% loss period interspersed with occasional wins.
        # This adds a direct, non-resettable boost based on the last 20 definitive
        # trades: if the recent loss rate exceeds 65%, the gate rises proportionally.
        # This is in addition to — not a replacement of — the streak boost.
        if self.trade_memory:
            try:
                _global_rlr = self.trade_memory.get_recent_loss_rate(20)
                if _global_rlr > 0.72:  # v15.3: trigger kept 0.72 — only extreme sustained losing streaks (>72% loss rate) tighten the gate
                    _rlr_extra = min((_global_rlr - 0.72) * 20.0, 3.0)  # v15.3: multiplier 30→20, cap 6→3pt — at 85% recent loss rate extra is now (0.85-0.72)*20=2.6pt (was 4pt) preventing the G3 threshold from reaching 84% and blocking borderline signals; avoids secondary starvation spiral when all recent trades are losses
                    confidence_threshold = min(confidence_threshold + _rlr_extra, 95.0)
                    self.logger.debug(
                        f"🔺 Global recent_loss={_global_rlr:.0%} > 72% — "
                        f"threshold boosted +{_rlr_extra:.1f}pt → {confidence_threshold:.1f}%"
                    )
            except Exception:
                pass

        # Work on a COPY of the signal so confidence mutations in Phase 1 (boost
        # analysis) never modify the original object that the strategy may still
        # reference.  dataclasses.replace() performs a shallow copy which is safe
        # here because all SwarmSignal fields are scalars / immutables (dict is
        # only read, not mutated during boost).
        signal = dataclasses.replace(signals[0])
        symbol = getattr(signal, "symbol", "BTCUSDT") or "BTCUSDT"

        # ── Fast pre-check before any network I/O ──
        _sig_consensus = float(getattr(signal, "swarm_consensus", 0.0))
        if not self.can_send_signal(symbol, action=signal.action, swarm_consensus=_sig_consensus):
            return False

        # ── AI Signal Gate — send signals ONLY when free LLMs are confirmed available ──
        # Per user requirement: signals are blocked when all free OpenRouter models are
        # rate-limited or disabled.  was_recently_available(300) returns True if G0DM0D3
        # successfully called at least one model in the last 5 minutes.
        # has_available_models() returns True if at least one model currently has capacity.
        #
        # v3.1 FIX — Swarm-Consensus Bypass:
        # When ALL 38 LLMs are temporarily rate-limited (caused by 80 parallel CONSORTIUM
        # sweeps × 38 models = 3 040 simultaneous calls/cycle), ultra-high-consensus signals
        # are allowed through without AI gate confirmation.
        #
        # Rationale: G0DM0D3 is ONE of 10 swarm agents and is already weighted only ~6%
        # in the final MiroFish consensus score.  A 95%+ swarm consensus from the other
        # 9 rule-based agents — AEGIS GEX, ATAS, MACD/RSI/EMA suites, Ichimoku, Volume
        # Flow, Microstructure, etc. — constitutes overwhelmingly strong directional evidence
        # that does NOT require LLM confirmation to trade.
        #
        # Bypass conditions (BOTH must be true):
        #   • swarm_consensus ≥ 95%  — near-unanimous agreement across 10 agents
        #   • signal.confidence + MAX_BOOST ≥ confidence_threshold  — v8.1 FIX:
        #     Previously checked pre-boost conf ≥ threshold, which blocked signals
        #     that would have cleared the gate after ATAS/Bookmap/MarketIntel boosts
        #     (+8/+6/+8 = up to +15pt total).  Now we allow the boost to finish the
        #     job: if the pre-boost conf + maximum possible boost ≥ threshold, let
        #     Phase 1 proceed.  The pre-boost impossibility gate at line ~1488 still
        #     blocks truly weak signals (conf + MAX_BOOST < threshold).
        _AI_GATE_MAX_BOOST = 15.0   # max confidence boost from Phase 1 analyzers
        _godmod3 = get_godmod3_engine()
        _ai_ready = _godmod3.has_available_models() or _godmod3.was_recently_available(900)  # v15.1: 300→900s — sustained OpenRouter rate-limit storms last 10-30min; 5-min window caused gate to block ALL signals even when a model was available moments ago; 15-min window correctly identifies transient vs sustained outage
        if not _ai_ready:
            _consensus_bypass = (
                _sig_consensus >= 0.88  # v15.1: 0.95→0.88 — when LLMs are down, requiring 95% consensus AND 95% swarm baseline (G2) AND conf+boost≥threshold is a triple-95% filter; 88% still requires near-unanimous 9/10 swarm agents while actually allowing bypass to fire
                and signal.confidence + _AI_GATE_MAX_BOOST >= confidence_threshold
            )
            if not _consensus_bypass:
                _wait_s = _godmod3.get_next_available_seconds()
                # v15.3: Set AI-gate-block cooldown — saves swarm re-evaluation next
                # cycle when conf is structurally below bypass threshold and LLMs are
                # still rate-limited.  INJUSDT burned 7-agent swarm every 20s with
                # conf=67.4%+15=82.4% < 86% — price can't change geometry in 20s.
                self._ai_gate_block_cooldown[symbol] = time.time() + self._AI_GATE_BLOCK_COOLDOWN_SEC
                self.logger.info(
                    f"🚦 [{symbol}] AI Signal Gate BLOCKED — all free LLMs rate-limited "
                    f"(consensus={_sig_consensus:.0%} < 88% or "
                    f"conf={signal.confidence:.1f}%+{_AI_GATE_MAX_BOOST:.0f}boost"
                    f" < {confidence_threshold:.0f}% threshold). "
                    f"Next available in ~{_wait_s:.0f}s. "
                    f"Swarm suppressed {self._AI_GATE_BLOCK_COOLDOWN_SEC:.0f}s [v15.3]"
                )
                return False
            # Ultra-high-consensus bypass — allow signal through to Phase 1 boost
            self.logger.info(
                f"⚡ [{symbol}] AI Gate BYPASS (swarm-consensus override) — "
                f"LLMs rate-limited but consensus={_sig_consensus:.0%}≥88% "
                f"+ conf={signal.confidence:.1f}%+{_AI_GATE_MAX_BOOST:.0f}boost"
                f"≥{confidence_threshold:.0f}% qualifies. "
                f"G0DM0D3 is 6% of swarm weighting; 9-agent near-unanimous rule-based "
                f"consensus overrides AI gate requirement. [v15.3 bypass-thresh=88%]"
            )

        tf_label = (getattr(signal, "timeframe", "15m") or "15m").upper()
        self.logger.info(
            f"🔍 [{symbol}] Evaluating {signal.action} [{tf_label}] "
            f"@ {signal.entry_price:.4g} | Conf={signal.confidence:.1f}% "
            f"Swarm={signal.swarm_consensus:.0%}"
        )

        # ── Per-symbol loss-streak penalty (applied before Phase 1 boost) ────
        # If a symbol has lost >65% of its last 10 definitive trades, apply a
        # pre-boost confidence penalty so historically unreliable symbols face a
        # harder gate.  This does NOT affect the per-symbol blacklist — it's a
        # soft quality control that still allows great signals through.
        #
        # OPTIMISATION: reuse self._symbol_stats (populated hourly by
        # _refresh_symbol_blacklist) instead of issuing a fresh SQLite query for
        # every signal from the 20 parallel scan coroutines.  Falls back to a
        # live DB query only when the cache is empty (first cycle or after error).
        if self.trade_memory:
            try:
                if self._symbol_stats:
                    _sym_stats = self._symbol_stats
                else:
                    _sym_stats = self.trade_memory.get_symbol_stats(min_trades=5)
                _sym_perf  = _sym_stats.get(symbol, {})
                _sym_rlr   = float(_sym_perf.get("recent_loss_rate", 0.0))
                if _sym_rlr > 0.55:
                    _sym_penalty = min((_sym_rlr - 0.55) * 60.0, 12.0)  # max -12pt (was -8pt at >65%)
                    signal.confidence = max(0.0, signal.confidence - _sym_penalty)
                    self.logger.debug(
                        f"📉 [{symbol}] Recent loss rate {_sym_rlr:.0%} > 55% — "
                        f"pre-boost penalty -{_sym_penalty:.1f}pt "
                        f"→ conf={signal.confidence:.1f}%"
                    )
            except Exception:
                pass

        if self.public_api is not None:
            try:
                _fg_adj = self.public_api.get_sentiment_adjustment()
                _dir_bias = self.public_api.get_directional_bias()
                _total_api_adj = _fg_adj
                if signal.action == "BUY":
                    _total_api_adj += _dir_bias.get("buy_adj", 0.0)
                elif signal.action == "SELL":
                    _total_api_adj += _dir_bias.get("sell_adj", 0.0)
                if _total_api_adj != 0.0:
                    signal.confidence = max(0.0, signal.confidence + _total_api_adj)
                    self.logger.debug(
                        f"🌐 [{symbol}] F&G adj={_fg_adj:+.1f}pt, "
                        f"dir_bias={_dir_bias}, total={_total_api_adj:+.1f}pt, "
                        f"conf→{signal.confidence:.1f}%"
                    )

                # ── Fear & Greed gate for BUY signals ────────────────────────
                # Tiered gate: absolute panic block, contrarian reversal path, and
                # soft fear penalty.  F&G bottom values (5-10) are historically
                # high-probability reversal points when accompanied by unanimous
                # swarm consensus — the hard block at ≤10 was over-filtering and
                # producing zero signals during prolonged extreme-fear periods.
                #
                # HARD BLOCK: F&G ≤ 5  — crash-level panic; further downside very likely
                # CONTRARIAN: F&G 5-10 — allow ONLY if consensus ≥ 95% AND RSI < 42
                #   (capitulation reversal: unanimous swarm + oversold price action)
                # SOFT GATE:  F&G < 20 — scaled penalty (-5 to -15pt)
                _fg_val = self.public_api.fear_greed_index
                if signal.action == "BUY" and isinstance(_fg_val, (int, float)):
                    _sig_rsi_fg    = float(getattr(signal, "rsi", 50))
                    _sig_cons_fg   = float(getattr(signal, "swarm_consensus", 0.0))
                    if _fg_val <= 5:
                        # Absolute crash-level panic — hard block regardless of consensus
                        self.logger.info(
                            f"💀 [{symbol}] PANIC HARD GATE: F&G={_fg_val} ≤ 5 — "
                            f"BUY signal BLOCKED (crash-level capitulation)"
                        )
                        return False
                    elif _fg_val <= 10:
                        # Deep fear zone: three-tier approach based on RSI level.
                        # Requires unanimous swarm (≥95%) in all cases.
                        # RSI > 70: hard block — clearly overbought in a fear market
                        # RSI 50-70: relative-strength play (coin outperforming) — allow
                        #            with heavy penalty (-15pt) to force confidence ≥ 80
                        # RSI 35-50: neutral/mild oversold — allow with moderate penalty
                        # RSI < 35:  deeply oversold contrarian — allow with mild penalty
                        if _sig_cons_fg < 0.95:
                            self.logger.info(
                                f"😱 [{symbol}] FEAR GATE: F&G={_fg_val} — "
                                f"BUY blocked (need consensus≥95%, got {_sig_cons_fg:.0%})"
                            )
                            return False
                        if _sig_rsi_fg >= 70:
                            self.logger.info(
                                f"😱 [{symbol}] FEAR GATE: F&G={_fg_val} — "
                                f"BUY blocked (RSI={_sig_rsi_fg:.0f}≥70, overbought in fear market)"
                            )
                            return False
                        # Unanimous consensus with reasonable RSI — apply scaled penalty
                        if _sig_rsi_fg < 35:
                            _fear_penalty = 6.0    # deeply oversold: mild penalty
                        elif _sig_rsi_fg < 50:
                            _fear_penalty = 10.0   # neutral: moderate penalty
                        else:
                            _fear_penalty = 10.0   # relative-strength (50-70): moderate penalty
                            # (reduced from -15pt: unanimous consensus in fear zone with
                            # relative-strength coin still needs post-gate NN/IRONS quality filters)
                        signal.confidence = max(0.0, signal.confidence - _fear_penalty)
                        _setup_type = (
                            "deeply-oversold" if _sig_rsi_fg < 35
                            else "neutral-reversal" if _sig_rsi_fg < 50
                            else "relative-strength"
                        )
                        self.logger.info(
                            f"🔄 [{symbol}] FEAR GATE PASS ({_setup_type}): F&G={_fg_val} "
                            f"consensus={_sig_cons_fg:.0%} RSI={_sig_rsi_fg:.0f} — "
                            f"penalty -{_fear_penalty:.0f}pt → conf={signal.confidence:.1f}%"
                        )
                    elif _fg_val < 20:
                        # NOTE: _fg_val is in (10, 20) here — the <= 10 branch is
                        # handled above.  Tiered penalty: deeper fear = heavier penalty.
                        if _fg_val < 13:
                            _fear_penalty = 15.0
                        elif _fg_val < 15:
                            _fear_penalty = 10.0
                        else:
                            _fear_penalty = 5.0
                        signal.confidence = max(0.0, signal.confidence - _fear_penalty)
                        self.logger.info(
                            f"😱 [{symbol}] Fear gate: F&G={_fg_val} < 20 — "
                            f"BUY penalty -{_fear_penalty:.0f}pt → conf={signal.confidence:.1f}%"
                        )

                # ── v8.2 Fear & Greed DIRECTIONAL REGIME BONUS ───────────────
                # Fear regime (F&G < 35): bearish conditions statistically favour
                # SHORT signals — apply a scaled bonus so high-consensus SELL
                # signals that are already near the gate can pass on their own.
                # Greed regime (F&G > 70): bullish momentum favours LONG signals.
                # Bonus is capped at +5pt and proportional to regime extremity.
                # This is applied AFTER the BUY fear-gate so it does not interact
                # with the BUY penalties above (it only fires for SELL / BUY).
                if isinstance(_fg_val, (int, float)):
                    if signal.action == "SELL" and _fg_val < 35:
                        _regime_bonus = round(min(5.0, (35.0 - _fg_val) * 0.2), 1)
                        if _regime_bonus > 0:
                            signal.confidence = min(100.0, signal.confidence + _regime_bonus)
                            self.logger.info(
                                f"📉 [{symbol}] Fear regime SELL bonus: F&G={_fg_val} "
                                f"→ +{_regime_bonus:.1f}pt conf={signal.confidence:.1f}% [v8.2]"
                            )
                    elif signal.action == "BUY" and _fg_val > 70:
                        _regime_bonus = round(min(5.0, (_fg_val - 70.0) * 0.17), 1)
                        if _regime_bonus > 0:
                            signal.confidence = min(100.0, signal.confidence + _regime_bonus)
                            self.logger.info(
                                f"📈 [{symbol}] Greed regime BUY bonus: F&G={_fg_val} "
                                f"→ +{_regime_bonus:.1f}pt conf={signal.confidence:.1f}% [v8.2]"
                            )
            except Exception:
                pass

        # ── Phase 1: Boost analysis — ALL network I/O runs outside the lock ──
        # With the configured semaphore (SCAN_PARALLEL_LIMIT), multiple coroutines run
        # boost analysis concurrently.  Holding the lock here would serialize them into
        # a single-file queue, eliminating the parallelism benefit.
        _pre_boost_conf = signal.confidence
        # 15.0: allows multi-source agreement (ATAS + Market Intel +
        # Insider + Microstructure + AI) to push a quality signal from 65% to 80%.
        # The effective pre-boost floor is 80 - 15 = 65%, which is still above
        # the strategy's min_confidence gate of 64%.
        _MAX_BOOST = 15.0

        # ── Pre-boost impossibility gate ─────────────────────────────────────
        # If even the maximum possible boost cannot bring this signal to the
        # confidence threshold, skip ALL Phase 1 network I/O (klines fetch +
        # ATAS + MarketIntel + Insider + Microstructure + AI) immediately.
        # Example: conf=64.9% + max_boost=15pt = 79.9% < 80% threshold → skip.
        # v15.3 BUG FIX: previously this returned False at DEBUG level with no
        # cooldown — the per-symbol loss-streak penalty (applied just above) can
        # push effective conf below the threshold, causing the full swarm to re-run
        # every cycle (ADAUSDT burned 7-agent swarm 10+×/4min silently).
        # Fix: log at INFO level and set a 90s cooldown (same as EV-fail base).
        if _pre_boost_conf + _MAX_BOOST < confidence_threshold:
            self._preboost_fail_cooldown[symbol] = time.time() + self._PREBOOST_FAIL_COOLDOWN_SEC
            self.logger.info(
                f"⏳ [{symbol}] Pre-skip: conf={_pre_boost_conf:.1f}%"
                f" + max_boost={_MAX_BOOST:.0f}pt = {_pre_boost_conf + _MAX_BOOST:.1f}%"
                f" < threshold={confidence_threshold:.0f}% → {self._PREBOOST_FAIL_COOLDOWN_SEC:.0f}s suppress [v15.3]"
            )
            return False

        # LOCAL variable — avoids the race where another coroutine overwrites
        # self._current_bb_position between Phase 1 and Phase 2.
        _local_bb_position: float = 0.5
        # PM Framework: klines captured in Phase 1 for use in PM computation
        _pm_klines: list = []
        # FIX v5.2: Capture ATAS/Bookmap results in Phase 1 so Unity Gate 5
        # receives real analyzer data instead of None.  Previously Gate 5 always
        # ran with atas_result=None, bookmap_result=None, trivially passing and
        # contributing only 5 quality points instead of the full 10.
        _unity_atas_result: Optional[Dict] = None
        _unity_bookmap_result: Optional[Dict] = None

        try:
            raw_klines = await self.trader.get_market_data(symbol, "15m", 200)
            if raw_klines and len(raw_klines) >= 50:
                _pm_klines = raw_klines  # save for Prediction Market Framework
                # 6-column format [ts, open, high, low, close, volume]
                market_data_5col = [
                    [k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])]
                    for k in raw_klines
                ]

                # ── Bollinger Band position for NN feature ────────────
                try:
                    closes_bb = [float(k[4]) for k in raw_klines]
                    period_bb = 20
                    ma_bb  = sum(closes_bb[-period_bb:]) / period_bb
                    std_bb = (sum((c - ma_bb) ** 2 for c in closes_bb[-period_bb:]) / period_bb) ** 0.5
                    if std_bb > 0:
                        bb_up = ma_bb + 2 * std_bb
                        bb_lo = ma_bb - 2 * std_bb
                        _local_bb_position = max(0.0, min(1.0,
                            (closes_bb[-1] - bb_lo) / (bb_up - bb_lo)
                        ))
                    # else: keep _local_bb_position = 0.5
                except Exception:
                    pass  # keep _local_bb_position = 0.5

                sig_dir = signal.action  # BUY or SELL

                _unity_health = getattr(self, "_unity_health", None)

                if self.atas_analyzer:
                    try:
                        atas = await self.atas_analyzer.analyze_all_indicators(market_data_5col)
                        if "error" not in atas:
                            # FIX v5.2: capture for Unity Gate 5
                            _unity_atas_result = atas
                            comp = atas.get("composite_signal", "NEUTRAL")
                            atas_bull = comp in ("STRONG_BUY", "BUY")
                            atas_bear = comp in ("STRONG_SELL", "SELL")
                            if (sig_dir == "BUY" and atas_bull) or (sig_dir == "SELL" and atas_bear):
                                boost = 8 if "STRONG" in comp else 5
                                signal.confidence = min(100, signal.confidence + boost)
                                signal.confidence = min(signal.confidence, _pre_boost_conf + _MAX_BOOST)
                                self.logger.info(f"🔷 ATAS boost +{boost}% (ATAS={comp}, aligned)")
                            else:
                                self.logger.debug(f"ATAS={comp} not aligned with {sig_dir} — no boost")
                            if _unity_health:
                                _unity_health.record_call("ATAS+Bookmap", True)
                    except Exception as e:
                        self.logger.debug(f"ATAS skipped: {e}")
                        if _unity_health:
                            _unity_health.record_call("ATAS+Bookmap", False)

                # ── Bookmap order-flow analysis (FIX session 4: was never called) ──
                # Fetches live order book depth and runs DOM / volume imbalance analysis.
                # The result is passed to Unity Gate 5 as bookmap_result so the symmetric
                # veto can fire correctly and Gate 5 can award the full 10 quality pts.
                _bm_analyzer = getattr(self, "_unity_bookmap", None) or getattr(self, "bookmap_analyzer", None)
                if _bm_analyzer is not None:
                    try:
                        _depth = await self.trader.get_order_book(symbol=symbol, limit=20)
                        if _depth and "bids" in _depth and "asks" in _depth:
                            _bm_signal = await _bm_analyzer.analyze_order_book(symbol, _depth)
                            if _bm_signal is not None:
                                # Convert BookmapSignal dataclass to plain dict for Gate 5
                                _ofd = getattr(_bm_signal, "order_flow_direction", None)
                                _ofd_str = _ofd.value if hasattr(_ofd, "value") else str(_ofd)
                                _unity_bookmap_result = {
                                    "order_flow_direction": _ofd_str,
                                    "volume_imbalance":     float(getattr(_bm_signal, "volume_imbalance", 0)),
                                    "confidence":           float(getattr(_bm_signal, "confidence", 0)),
                                    "strength":             float(getattr(_bm_signal, "strength", 0)),
                                    "institutional_activity": float(getattr(_bm_signal, "institutional_activity", 0)),
                                }
                                # Bookmap directional boost (aligned order flow)
                                _bm_aligned = (
                                    (sig_dir == "BUY"  and _ofd_str in ("BUY", "STRONG_BUY")) or
                                    (sig_dir == "SELL" and _ofd_str in ("SELL", "STRONG_SELL"))
                                )
                                if _bm_aligned:
                                    _bm_boost = 6 if "STRONG" in _ofd_str else 4
                                    signal.confidence = min(100, signal.confidence + _bm_boost)
                                    signal.confidence = min(signal.confidence, _pre_boost_conf + _MAX_BOOST)
                                    self.logger.info(
                                        f"📊 Bookmap boost +{_bm_boost}% "
                                        f"(flow={_ofd_str}, imb={getattr(_bm_signal,'volume_imbalance',0):.2f})"
                                    )
                                else:
                                    self.logger.debug(f"Bookmap flow={_ofd_str} not aligned with {sig_dir}")
                    except Exception as _bme:
                        self.logger.debug(f"Bookmap skipped: {_bme}")

                if self.market_intelligence:
                    try:
                        mi = await self.market_intelligence.get_market_intelligence_summary(
                            market_data_5col, signal.entry_price
                        )
                        if mi:
                            mi_sig = mi.get("signal", "")
                            if (sig_dir == "BUY" and mi_sig == "strong_buy") or \
                               (sig_dir == "SELL" and mi_sig == "strong_sell"):
                                signal.confidence = min(100, signal.confidence + 8)
                                signal.confidence = min(signal.confidence, _pre_boost_conf + _MAX_BOOST)
                                self.logger.info("🧠 Market Intel boost +8% (aligned)")
                    except Exception as e:
                        self.logger.debug(f"Market Intel skipped: {e}")
                    # Health tracking: MarketIntelligence layer (FIX session 5)
                    _uh_mi = getattr(self, "_unity_health", None)
                    if _uh_mi:
                        _uh_mi.record_call("MarketIntelligence", True)

                if self.insider_analyzer:
                    try:
                        insider = await self.insider_analyzer.detect_insider_activity(market_data_5col)
                        if insider.detected and insider.confidence > 70:
                            # CRITICAL FIX: direction-aware boost — only apply when insider
                            # activity direction is aligned with the signal direction.
                            # "neutral" direction (ambiguous whale/surge) gets a reduced boost
                            # since direction is unknown.
                            _ins_dir = getattr(insider, "direction", "neutral")
                            _ins_aligned = (
                                (sig_dir == "BUY"  and _ins_dir == "bullish") or
                                (sig_dir == "SELL" and _ins_dir == "bearish")
                            )
                            _ins_neutral = _ins_dir == "neutral"
                            if _ins_aligned:
                                _ins_boost = 6
                                signal.confidence = min(100, signal.confidence + _ins_boost)
                                signal.confidence = min(signal.confidence, _pre_boost_conf + _MAX_BOOST)
                                self.logger.info(
                                    f"🕵️ Insider boost +{_ins_boost}% "
                                    f"(type={insider.activity_type}, dir={_ins_dir}, aligned)"
                                )
                            elif _ins_neutral:
                                # Ambiguous direction: apply smaller boost (2pt)
                                _ins_boost = 2
                                signal.confidence = min(100, signal.confidence + _ins_boost)
                                signal.confidence = min(signal.confidence, _pre_boost_conf + _MAX_BOOST)
                                self.logger.info(
                                    f"🕵️ Insider partial boost +{_ins_boost}% "
                                    f"(type={insider.activity_type}, dir=neutral)"
                                )
                            else:
                                self.logger.debug(
                                    f"Insider dir={_ins_dir} opposes {sig_dir} — no boost"
                                )
                    except Exception as e:
                        self.logger.debug(f"Insider skipped: {e}")

                if self.microstructure_enhancer:
                    try:
                        # FIX: use get_microstructure_alert (correct method name).
                        # The previously called analyze_microstructure does not exist on
                        # MarketMicrostructureEnhancer, causing a silent AttributeError
                        # that meant this boost NEVER fired.
                        current_price_ms = float(market_data_5col[-1][4]) if market_data_5col else 0.0
                        ms = await self.microstructure_enhancer.get_microstructure_alert(
                            {}, [], [], current_price_ms
                        )
                        if ms:
                            ms_dir = ms.get("direction", "NEUTRAL")
                            ms_conf = float(ms.get("confidence", 0.0))
                            ms_aligned = (
                                (sig_dir == "BUY"  and ms_dir == "BUY")  or
                                (sig_dir == "SELL" and ms_dir == "SELL")
                            )
                            if ms_aligned and ms_conf >= 50.0:
                                signal.confidence = min(100, signal.confidence + 5)
                                signal.confidence = min(signal.confidence, _pre_boost_conf + _MAX_BOOST)
                                self.logger.info(
                                    f"📡 Microstructure boost +5% "
                                    f"(dir={ms_dir}, conf={ms_conf:.0f}%, aligned)"
                                )
                            elif not ms_aligned and ms_dir != "NEUTRAL" and ms_conf >= 60.0:
                                self.logger.debug(
                                    f"Microstructure dir={ms_dir} opposes {sig_dir} — no boost"
                                )
                    except Exception as e:
                        self.logger.debug(f"Microstructure skipped: {e}")

                # ── v8.2 HTF Trend Alignment (EMA200 of 15M klines) ──────────
                # Uses already-fetched klines — no extra API cost.
                # EMA200 of the 15M timeframe approximates the 4H trend direction.
                # With-trend signals get +2pt; counter-trend signals get -3pt.
                # Counter-trend does NOT hard-block — it just makes the gate harder
                # so only the very best counter-trend setups (RSI oversold/overbought,
                # unanimous swarm, ATAS+BM alignment) can still squeeze through.
                if len(raw_klines) >= 200:
                    try:
                        _closes_htf = [float(k[4]) for k in raw_klines[-200:]]
                        _k200       = 2.0 / 201.0
                        _ema200     = _closes_htf[0]
                        for _c200 in _closes_htf[1:]:
                            _ema200 = _c200 * _k200 + _ema200 * (1.0 - _k200)
                        _cur_p     = float(raw_klines[-1][4])
                        _above_e   = _cur_p > _ema200
                        _htf_adj   = 0.0
                        if   sig_dir == "BUY"  and _above_e:     _htf_adj = +2.0
                        elif sig_dir == "SELL" and not _above_e:  _htf_adj = +2.0
                        elif sig_dir == "BUY"  and not _above_e:  _htf_adj = -3.0
                        elif sig_dir == "SELL" and _above_e:      _htf_adj = -3.0
                        if _htf_adj != 0.0:
                            signal.confidence = max(0.0, min(100.0, signal.confidence + _htf_adj))
                            signal.confidence = min(signal.confidence, _pre_boost_conf + _MAX_BOOST)
                            _htf_lbl = "with-trend" if _htf_adj > 0 else "counter-trend"
                            self.logger.debug(
                                f"🎯 [{symbol}] HTF EMA200 {_htf_lbl}: "
                                f"price={_cur_p:.4g} EMA200={_ema200:.4g} "
                                f"{'above' if _above_e else 'below'} → "
                                f"{_htf_adj:+.0f}pt conf={signal.confidence:.1f}% [v8.2]"
                            )
                    except Exception:
                        pass

                if self.ai_processor:
                    try:
                        from ai_enhanced_signal_processor import analyze_trading_signal
                        _ai_signal_text = (
                            f"{signal.action} {symbol} @ {signal.entry_price:.6g} "
                            f"RSI={signal.rsi:.1f} Vol={signal.volume_ratio:.2f}x "
                            f"Conf={signal.confidence:.1f}% Swarm={signal.swarm_consensus:.0%}"
                        )
                        _ai_result = await analyze_trading_signal(_ai_signal_text)
                        _ai_conf = float(_ai_result.get("confidence", 0.0))
                        _ai_sentiment = _ai_result.get("market_sentiment", "neutral").lower()
                        _direction_aligned = (
                            (sig_dir == "BUY"  and _ai_sentiment in ("bullish", "positive")) or
                            (sig_dir == "SELL" and _ai_sentiment in ("bearish", "negative"))
                        )
                        if _direction_aligned and _ai_conf >= 0.75:
                            _ai_boost = 4 if _ai_conf >= 0.85 else 2
                            signal.confidence = min(100, signal.confidence + _ai_boost)
                            signal.confidence = min(signal.confidence, _pre_boost_conf + _MAX_BOOST)
                            self.logger.info(
                                f"🤖 AI boost +{_ai_boost}% "
                                f"(sentiment={_ai_sentiment} conf={_ai_conf:.2f})"
                            )
                    except Exception as e:
                        self.logger.debug(f"AI processor skipped: {e}")
                    # Health tracking: AIOrchestrator layer (FIX session 5)
                    _uh_aio = getattr(self, "_unity_health", None)
                    if _uh_aio:
                        _uh_aio.record_call("AIOrchestrator", True)

        except Exception as e:
            self.logger.debug(f"Boost analysis skipped: {e}")

        # ── Final boost cap ──
        if signal.confidence > _pre_boost_conf + _MAX_BOOST:
            signal.confidence = _pre_boost_conf + _MAX_BOOST
            self.logger.debug(
                f"🔒 Boost capped at +{_MAX_BOOST:.0f}pt → conf={signal.confidence:.1f}%"
            )

        # ════════════════════════════════════════════════════════════════════
        # PREDICTION MARKET PAPERS FRAMEWORK
        # Ref: "The Prediction Market Papers" (Shannon Entropy + Kelly + Decay)
        #
        #   1. Shannon Entropy  H = -p·log₂(p) - (1-p)·log₂(1-p)
        #      WHEN to enter: measures market certainty via swarm consensus.
        #      Low H (< 0.70)  → clear directional edge    → confidence bonus
        #      High H (> 0.93) → near coin-flip, no edge   → confidence penalty
        #
        #   2. Kelly Criterion  f = max(0, (p·b − q) / b)
        #      HOW MUCH: optimal bet-size given edge p and reward:risk b.
        #      f < 0   → negative expectation   → hard penalty
        #      f > 0.3 → strong edge            → confidence bonus
        #      (Fractional Kelly ×0.25 used; full Kelly too aggressive for crypto)
        #
        #   3. Reaction Decay   f_adj = f · (1 − e^(−λt))
        #      URGENCY: λ = ln(2)/3 (half-life = 3 bars of 15m, crypto default).
        #      t = consecutive 15m bars the price moved in signal direction.
        #      Low t (fresh reversal)    → low maturity  → small decay penalty
        #      High t (established trend)→ high maturity → decay bonus
        # ════════════════════════════════════════════════════════════════════
        _PM_LAMBDA = math.log(2) / 4.0   # half-life = 4 bars (60 min on 15m TF) — better calibration for crypto swing signals

        try:
            # ── 1. Shannon Entropy from swarm consensus ───────────────────────
            _p_sw  = max(1e-9, min(1.0 - 1e-9, float(signal.swarm_consensus)))
            _q_sw  = 1.0 - _p_sw
            _H     = -(_p_sw * math.log2(_p_sw) + _q_sw * math.log2(_q_sw))

            # ── 2. Kelly Criterion (fractional, conservative) ─────────────────
            # BUG FIX: using raw swarm consensus as win probability overestimates
            # edge because consensus measures directional agreement (75-95%), NOT
            # the actual win probability (~33-50% historically).  Blend consensus
            # with the live historical win rate for a calibrated estimate.
            _b_rr     = max(0.5, float(signal.risk_reward_ratio))
            # Floor reduced 0.42→0.35 and floor guard 0.338→0.30 to reflect actual
            # historical win rate (~33%) more accurately and prevent Kelly overconfidence.
            _hist_wr  = max(getattr(getattr(self, "strategy", None), "_global_win_rate", 0.35), 0.30)
            _p_win    = _p_sw * 0.55 + _hist_wr * 0.45    # blend: swarm + history
            _p_win    = max(0.28, min(_p_win, 0.80))       # realistic bounds
            _f_kelly  = max(0.0, (_p_win * _b_rr - (1.0 - _p_win)) / _b_rr)
            _f_frac   = 0.25 * _f_kelly                   # quarter-Kelly for safety

            # ── 3. Reaction Decay: count consecutive bars in signal direction ──
            _t_bars = 2.0   # conservative default (1 confirmed bar)
            if _pm_klines and len(_pm_klines) >= 8:
                _pm_closes = [float(k[4]) for k in _pm_klines[-16:]]
                _dir_mult  = 1 if signal.action == "BUY" else -1
                _t_bars    = 0.0
                for _bi in range(len(_pm_closes) - 1, 0, -1):
                    if _dir_mult * (_pm_closes[_bi] - _pm_closes[_bi - 1]) > 0:
                        _t_bars += 1.0
                    else:
                        break
                _t_bars = max(1.0, _t_bars)

            _decay    = 1.0 - math.exp(-_PM_LAMBDA * _t_bars)
            _f_adj    = _f_kelly * _decay               # Kelly × maturity

            # ── Store PM metrics on signal object ─────────────────────────────
            signal.shannon_entropy    = round(_H, 4)
            signal.kelly_fraction     = round(_f_kelly, 4)
            signal.kelly_decay_factor = round(_decay, 4)

            # ── Apply PM confidence adjustments ───────────────────────────────
            _pm_adj_total = 0.0

            # 1. Entropy adjustment (certainty vs uncertainty)
            if _H > 0.95:       # near 50/50: very uncertain → hard penalty
                _ent_adj = -7.0
            elif _H > 0.90:     # mildly uncertain
                _ent_adj = -3.5
            elif _H > 0.85:     # slightly uncertain
                _ent_adj = -1.5
            elif _H < 0.60:     # very clear directional bias
                _ent_adj = +4.0
            elif _H < 0.70:     # clear directional bias
                _ent_adj = +2.0
            elif _H < 0.80:     # somewhat clear
                _ent_adj = +1.0
            else:
                _ent_adj = 0.0

            # 2. Kelly adjustment (edge quality)
            if _f_kelly <= 0.0:         # negative expectation → penalise hard
                _kelly_adj = -6.0
            elif _f_kelly < 0.10:       # thin edge
                _kelly_adj = -1.0
            elif _f_kelly > 0.40:       # excellent edge
                _kelly_adj = +4.0
            elif _f_kelly > 0.25:       # good edge
                _kelly_adj = +2.5
            elif _f_kelly > 0.15:       # moderate edge
                _kelly_adj = +1.0
            else:
                _kelly_adj = 0.0

            # 3. Decay adjustment (trend maturity)
            if _decay < 0.20:           # very fresh reversal → uncertain
                _decay_adj = -3.0
            elif _decay < 0.40:         # early-stage signal
                _decay_adj = -1.0
            elif _decay > 0.75:         # well-established trend
                _decay_adj = +2.5
            elif _decay > 0.55:         # moderately established
                _decay_adj = +1.0
            else:
                _decay_adj = 0.0

            _pm_adj_total = _ent_adj + _kelly_adj + _decay_adj

            # Cap PM net adjustment to ±8 pts to avoid over-riding Phase 1 boost
            _pm_adj_total = max(-8.0, min(8.0, _pm_adj_total))
            signal.confidence = max(0.0, min(100.0, signal.confidence + _pm_adj_total))

            self.logger.info(
                f"📊 [{symbol}] PM: H={_H:.3f}(adj={_ent_adj:+.1f}) "
                f"Kelly={_f_kelly:.1%}(adj={_kelly_adj:+.1f}) "
                f"Decay={_decay:.2f}×t={_t_bars:.0f}bars(adj={_decay_adj:+.1f}) "
                f"net_adj={_pm_adj_total:+.1f}pt → conf={signal.confidence:.1f}%"
            )

        except Exception as _pm_err:
            self.logger.debug(f"PM framework skipped: {_pm_err}")
        # Health tracking: Risk+SLTP+Kelly layer (FIX session 5)
        # PM framework = Kelly Criterion + Shannon Entropy + Reaction Decay = Risk layer
        _uh_risk = getattr(self, "_unity_health", None)
        if _uh_risk:
            _uh_risk.record_call("Risk+SLTP+Kelly", True)

        # ── Phase 2 pre-gate: NN inference + BM25 (OUTSIDE lock — parallelism-safe) ──
        # Bug Fix: predict_signal_with_uncertainty (20 MC-Dropout passes, 50-200ms)
        # was previously executed INSIDE _signal_gate_lock.  With 80 parallel scanners
        # this serialized every symbol's NN inference into a single-file queue,
        # negating all parallel scan throughput gains.
        #
        # Safety: `signal` is a local dataclasses.replace() copy — mutations to
        # signal.confidence here are NOT visible to other coroutines.  The lock is
        # then held for <5ms (IRONS check + threshold check + Telegram call setup).
        # The can_send_signal re-check INSIDE the lock still prevents double-sending.
        _nn_accuracy = getattr(self.nn_trainer, "last_accuracy", 0.0) if self.nn_trainer else 0.0
        if self.nn_trainer and getattr(self.nn_trainer, "trained", False) and _nn_accuracy >= 0.55:
            try:
                # ── v4: Real-time OFI feed for the NN ───────────────────────────
                # Snapshot Unity Engine's WS depth-imbalance (Binance @depth5@100ms)
                # right before MC-Dropout inference so feature-51 sees the freshest
                # microstructure pressure available.  Returns 0.0 when WS not yet
                # connected for this symbol (NN slot is benign — feature was trained
                # with zeros before producer was wired).
                _ofi_value = 0.0
                _eng = getattr(self, "_unity_engine", None)
                if _eng is not None:
                    _ws_state = getattr(_eng, "_ws_state", None)
                    if isinstance(_ws_state, dict):
                        _ob = _ws_state.get(str(symbol).upper())
                        if isinstance(_ob, dict):
                            try:
                                _ofi_value = float(_ob.get("depth_imbalance", 0.0) or 0.0)
                            except (TypeError, ValueError):
                                _ofi_value = 0.0

                # ── v5: 7-model Price Consensus ensemble ────────────────────────
                # Compute deterministic multi-model price-direction tilt from the
                # raw klines already fetched upstream (_pm_klines).  Covers all
                # major price-prediction families: trend (EMA), statistical (OLS
                # slope, Holt double-exp), mean-reversion (z-score), breakout
                # (Donchian), volume-weighted (VWAP), vol-normalised momentum
                # (RoC/ATR).  Result ∈ [-1, +1] is fed as feature 52 of the NN
                # so the MLP can condition win-prob on cross-model consensus.
                _pc_value = 0.0
                _pc_breakdown: dict = {}
                _hurst_signal = 0.0
                _hurst_H = 0.5
                _ewma_vol_sig = 0.0
                _ewma_vol_raw = 0.0
                _rskew_sig = 0.0
                _rskew_raw = 0.0
                if _pm_klines and len(_pm_klines) >= 32:
                    try:
                        from SignalMaestro.price_consensus_predictor import (
                            consensus_from_klines as _pc_fn,
                            hurst_from_klines as _hurst_fn,
                            ewma_vol_from_klines as _ewma_fn,
                            realized_skew_from_klines as _rskew_fn,
                        )
                        _atr_for_pc = float(getattr(signal, "atr_value", 0.0) or 0.0)
                        _last50 = _pm_klines[-50:]
                        # v5: 7-model price-direction consensus (feature 52)
                        _pc_value, _pc_breakdown = _pc_fn(_last50, atr=_atr_for_pc)
                        # v6: Hurst-regime classifier (feature 53) — same window
                        _hurst_signal, _hurst_H = _hurst_fn(_last50)
                        # v7: EWMA-vol RiskMetrics regime (feature 54) — same window
                        _ewma_vol_sig, _ewma_vol_raw = _ewma_fn(_last50)
                        # v8: Realized-skewness regime (feature 55) — same window
                        _rskew_sig, _rskew_raw = _rskew_fn(_last50)
                    except Exception as _pc_err:
                        self.logger.debug(f"PriceConsensus/Hurst/EWMA/Skew skipped: {_pc_err}")
                        _pc_value, _pc_breakdown = 0.0, {}
                        _hurst_signal, _hurst_H = 0.0, 0.5
                        _ewma_vol_sig, _ewma_vol_raw = 0.0, 0.0
                        _rskew_sig, _rskew_raw = 0.0, 0.0

                # v6/v7/v8: log regime classification for transparency.  Pure
                # diagnostics — the NN sees features 53/54/55 and decides itself
                # how to weight regime-conditional behaviour.
                if _hurst_H != 0.5 or _ewma_vol_raw > 0.0 or _rskew_raw != 0.0:
                    if   _hurst_H > 0.55: _regime = "TRENDING"
                    elif _hurst_H < 0.45: _regime = "MEAN-REVERT"
                    else:                 _regime = "RANDOM-WALK"
                    if   _ewma_vol_sig >  0.10: _vol_state = "VOL-EXPAND"
                    elif _ewma_vol_sig < -0.10: _vol_state = "VOL-CONTRACT"
                    else:                       _vol_state = "VOL-BALANCED"
                    if   _rskew_sig >  0.10: _skew_state = "SQUEEZE-RISK"
                    elif _rskew_sig < -0.10: _skew_state = "CRASH-RISK"
                    else:                    _skew_state = "SYMMETRIC"
                    self.logger.debug(
                        f"📐 [{symbol}] Hurst H={_hurst_H:.3f} sig={_hurst_signal:+.3f} "
                        f"regime={_regime} | EWMA σ={_ewma_vol_raw*100:.3f}% "
                        f"sig={_ewma_vol_sig:+.3f} state={_vol_state} | "
                        f"RSkew RS={_rskew_raw:+.2f} sig={_rskew_sig:+.3f} state={_skew_state}"
                    )

                # Soft directional alignment check: when consensus disagrees
                # strongly with the signal direction, log it for transparency.
                # No hard veto here — the NN will weight feature 52 itself
                # and the existing Gate 2.5 already enforces orderbook align.
                if _pc_breakdown:
                    _is_long_pc = signal.action == "BUY"
                    _aligned_pc = (_pc_value > 0.0) == _is_long_pc
                    self.logger.debug(
                        f"🔮 [{symbol}] PriceConsensus={_pc_value:+.3f} "
                        f"(EMA={_pc_breakdown.get('ema_cross',0):+.2f} "
                        f"OLS={_pc_breakdown.get('linreg',0):+.2f} "
                        f"MR={_pc_breakdown.get('zscore_mr',0):+.2f} "
                        f"DON={_pc_breakdown.get('donchian',0):+.2f} "
                        f"VWAP={_pc_breakdown.get('vwap_dev',0):+.2f} "
                        f"HOLT={_pc_breakdown.get('holt_fc',0):+.2f} "
                        f"MOM={_pc_breakdown.get('mom_atr',0):+.2f}) "
                        f"vs {signal.action} → {'✅aligned' if _aligned_pc else '⚠️opposed'}"
                    )

                # MC-Dropout prediction with uncertainty (20 stochastic forward passes).
                # v18.17: check _nn_batch_cache first — batch result from cycle start
                # eliminates the per-symbol individual NN call (125× FLOP reduction).
                # Regime/vol/skew overlays (lines below) still applied to the cached
                # base prob using the CURRENT cycle's fresh market state values.
                # Cache miss (new symbol, first cycle) falls through to individual inference.
                _nn_batch_hit = self._nn_batch_cache.get(symbol)
                if _nn_batch_hit is not None:
                    nn_win_prob, nn_uncertainty = _nn_batch_hit
                else:
                    nn_win_prob, nn_uncertainty = (
                        self.nn_trainer.predict_signal_with_uncertainty(
                            signal, _local_bb_position,
                            ofi=_ofi_value,
                            price_consensus=_pc_value,
                            hurst_signal=_hurst_signal,
                            ewma_vol_signal=_ewma_vol_sig,
                            realized_skew=_rskew_sig,
                        )
                    )

                # ── v6.1: Regime-Conditional NN-Prob Overlay (active Hurst gate) ──
                # The Hurst exponent and 7-model price consensus are already fed
                # to the MLP as features 52-53.  But the existing 1000 historical
                # training rows have hurst=0 / pc=0, so the MLP cannot leverage
                # the new regime signals until enough fresh samples accumulate
                # for the next 2-hour retrain.  In the interim — and as a
                # permanent institutional overlay (rule-based regime gating runs
                # on every elite quant desk in parallel with ML models) — we
                # apply a bounded ±6pp adjustment to nn_win_prob based on
                # regime-consensus alignment.  Asymmetric by design: capital
                # protection > opportunity cost, so the penalty for fighting
                # institutional flow in a trending regime is heavier than the
                # boost for following it.
                #
                #   TRENDING regime (H > 0.55, sig > +0.10):
                #     • aligned with consensus → +4pp × |consensus|  (institutional edge)
                #     • opposed to consensus  → −6pp × |consensus|  (high-risk fade)
                #   MEAN-REVERTING regime (H < 0.45, sig < −0.10):
                #     • dampened ±1.5pp — consensus models are trend-followers
                #       and less reliable in MR conditions, so we trust them less
                #   RANDOM-WALK (|sig| ≤ 0.10):  no adjustment (no regime edge)
                _nn_regime_adj = 0.0
                if abs(_hurst_signal) > 0.10 and _pc_value != 0.0:
                    _is_long_re   = signal.action == "BUY"
                    _pc_aligned_re = (_pc_value > 0.0) == _is_long_re
                    _pc_strength  = abs(_pc_value)  # 0..1
                    if _hurst_signal > 0.10:        # TRENDING
                        _nn_regime_adj = (+0.04 if _pc_aligned_re else -0.06) * _pc_strength
                    else:                           # MEAN-REVERTING
                        _nn_regime_adj = (+0.015 if _pc_aligned_re else -0.015) * _pc_strength
                    _nn_pre_adj = nn_win_prob
                    nn_win_prob = max(0.0, min(1.0, nn_win_prob + _nn_regime_adj))
                    if abs(_nn_regime_adj) >= 0.005:
                        _regime_tag = "TRENDING" if _hurst_signal > 0.10 else "MEAN-REVERT"
                        _align_tag  = "✅aligned" if _pc_aligned_re else "⚠️opposed"
                        self.logger.info(
                            f"🌊 [{symbol}] Regime-adjusted NN: "
                            f"{_nn_pre_adj:.3f} → {nn_win_prob:.3f} "
                            f"(Δ={_nn_regime_adj:+.3f}) | "
                            f"H={_hurst_H:.2f}({_regime_tag}) "
                            f"PC={_pc_value:+.2f}({_align_tag})"
                        )

                # ── v7.1: EWMA-Vol Regime Overlay (additive on top of v6.1) ──────
                # Vol-of-vol is one of the strongest documented degraders of win
                # rate in futures (Easley & López de Prado 2012, "Flow Toxicity").
                # We apply two asymmetric vol-state adjustments:
                #
                #   VOL EXPANDING (sig > +0.10):
                #     Regime is destabilising → realised σ rising faster than
                #     EWMA can absorb.  Apply small uncertainty-premium penalty.
                #     Extreme expansion (sig > +0.30) = chop / event-vol regime,
                #     where ALL signals degrade — apply heavier penalty.
                #
                #   VOL CONTRACTING (sig < −0.10) AND TRENDING regime (H > 0.55):
                #     Compression in a trending regime = classic institutional
                #     pre-breakout setup (Bollinger squeeze in a directional
                #     market).  Apply small boost — these have the highest
                #     average payoff per trade in the futures literature.
                #
                #   All other combinations: no adjustment (no clear edge).
                _nn_vol_adj = 0.0
                if _ewma_vol_sig > 0.30:        # EXTREME expansion / event vol
                    _nn_vol_adj = -0.04 * _ewma_vol_sig   # up to −4pp
                elif _ewma_vol_sig > 0.10:      # mild-to-moderate expansion
                    _nn_vol_adj = -0.02 * _ewma_vol_sig   # up to −2pp
                elif _ewma_vol_sig < -0.10 and _hurst_signal > 0.10:
                    # Compression-in-trend (textbook breakout setup)
                    _nn_vol_adj = +0.025 * abs(_ewma_vol_sig)  # up to +2.5pp
                if _nn_vol_adj != 0.0:
                    _nn_pre_vol = nn_win_prob
                    nn_win_prob = max(0.0, min(1.0, nn_win_prob + _nn_vol_adj))
                    if abs(_nn_vol_adj) >= 0.005:
                        if   _ewma_vol_sig > 0.30:  _vol_tag = "EXTREME-EXPAND"
                        elif _ewma_vol_sig > 0.10:  _vol_tag = "VOL-EXPAND"
                        else:                       _vol_tag = "COMPRESSION-IN-TREND"
                        self.logger.info(
                            f"📊 [{symbol}] Vol-adjusted NN: "
                            f"{_nn_pre_vol:.3f} → {nn_win_prob:.3f} "
                            f"(Δ={_nn_vol_adj:+.3f}) | EWMA σ={_ewma_vol_raw*100:.3f}% "
                            f"sig={_ewma_vol_sig:+.3f} state={_vol_tag}"
                        )

                # ── v7.2: Realized-Skew Direction-Asymmetric Overlay (v8) ─────────
                # Realized skewness is the only DIRECTIONAL regime signal in the
                # overlay stack: it tells us which side of the book is more
                # likely to get adversely selected, conditional on which way we
                # are entering.  Empirically (Bali-Hu-Murray 2019, Kozhan-
                # Neuberger-Schneider 2013), the skew premium is asymmetric:
                #
                #   RS << 0  (CRASH-RISK regime, downside fat tails):
                #     SHORTs win more often (riding the tail) → small BOOST
                #     LONGs face adverse selection            → small PENALTY
                #
                #   RS >> 0  (SQUEEZE-RISK regime, upside fat tails):
                #     LONGs win more often (riding the squeeze) → small BOOST
                #     SHORTs face adverse selection             → small PENALTY
                #
                # Strength scales linearly with |sig| up to ±3pp, asymmetric so
                # that the "wrong-side" penalty is 1.5× the "right-side" boost
                # (institutional risk-aversion bias — fade adverse setups
                # harder than we accelerate aligned ones).
                _nn_skew_adj = 0.0
                if abs(_rskew_sig) > 0.10:
                    _is_long  = signal.action in ("BUY", "LONG")
                    _is_short = signal.action in ("SELL", "SHORT")
                    if _rskew_sig > 0.10:           # SQUEEZE-RISK regime (upside tails)
                        if   _is_long:  _nn_skew_adj = +0.020 * _rskew_sig          # up to +2pp
                        elif _is_short: _nn_skew_adj = -0.030 * _rskew_sig          # up to -3pp
                    elif _rskew_sig < -0.10:        # CRASH-RISK regime (downside tails)
                        if   _is_short: _nn_skew_adj = +0.020 * abs(_rskew_sig)     # up to +2pp
                        elif _is_long:  _nn_skew_adj = -0.030 * abs(_rskew_sig)     # up to -3pp
                if _nn_skew_adj != 0.0:
                    _nn_pre_skew = nn_win_prob
                    nn_win_prob = max(0.0, min(1.0, nn_win_prob + _nn_skew_adj))
                    if abs(_nn_skew_adj) >= 0.005:
                        _skew_tag = "SQUEEZE-RISK" if _rskew_sig > 0 else "CRASH-RISK"
                        _stance   = "ALIGNED" if _nn_skew_adj > 0 else "ADVERSE"
                        self.logger.info(
                            f"⚖️  [{symbol}] Skew-adjusted NN: "
                            f"{_nn_pre_skew:.3f} → {nn_win_prob:.3f} "
                            f"(Δ={_nn_skew_adj:+.3f}) | RS={_rskew_raw:+.2f} "
                            f"sig={_rskew_sig:+.3f} regime={_skew_tag} "
                            f"side={signal.action}({_stance})"
                        )

                # Read data-driven thresholds (Youden's J from validation data)
                # Default 0.38 — ensures NN gate enforces positive-EV discipline
                # even before the first training run computes Youden's J
                # (breakeven at 1.55:1 R:R ≈ 39.2%; 0.38 gives slight tolerance).
                _reject_thresh = getattr(self.nn_trainer, "_reject_threshold", 0.38)
                _boost_thresh  = getattr(self.nn_trainer, "_boost_threshold",  0.70)
                _opt_thresh    = getattr(self.nn_trainer, "_opt_threshold",     0.50)

                # High-uncertainty borderline signals → reject conservatively.
                # If std > 0.15 and probability is within ±0.08 of reject threshold,
                # the model is too uncertain to be trusted — skip the signal.
                _high_uncertainty = nn_uncertainty > 0.15
                _borderline       = abs(nn_win_prob - _reject_thresh) < 0.08

                n_danger = len(getattr(
                    getattr(self.nn_trainer, "loss_analyzer", None),
                    "danger_zones", []
                ))

                # When ALL (or nearly all) swarm agents unanimously agree, the
                # collective intelligence of 10 independent agents outweighs the
                # NN gate — which was trained on limited historical data (200
                # samples, 54.5% win-rate split).  A 10/10 unanimous swarm with
                # ≥90% weighted consensus is the highest-quality signal the bot
                # can generate.  NN still applies soft penalty/boost, but the
                # hard-reject is bypassed.
                #
                # Thresholds:
                #   consensus ≥ 0.90 AND participation ≥ 7/10 → bypass hard-reject
                #   consensus ≥ 0.95 AND participation = 10/10 → bypass all NN filters
                _swarm_consensus = signal.swarm_consensus        # 0..1
                _participation   = getattr(signal, "participation_rate", 0.0)  # 0..1
                _is_unanimous    = _swarm_consensus >= 0.95 and _participation >= (8/10)
                _is_strong       = _swarm_consensus >= 0.85 and _participation >= (7/10)

                # v9.4 CALIBRATED Absolute floor: reject when NN gives < calibrated
                # win probability minimum.  Previously hardcoded at 0.25 — but the
                # trained model's reject_threshold (Youden's J) is ~0.38, and the
                # absolute floor must track that calibration so it tightens on
                # confident models and loosens on uncertain ones.  Floor formula:
                #   absolute_floor = max(0.10, _reject_thresh - 0.18)
                # At the live default _reject_thresh=0.38 this yields 0.20 (was 0.25),
                # so unambiguously bad signals (<20%) still hard-reject while the
                # 20-25% band gets the soft-penalty path instead of the absolute floor.
                # Hard floor of 0.10 prevents pathological calibration from disabling
                # the gate entirely.
                _absolute_floor = max(0.10, _reject_thresh - 0.18)
                #
                # EXCEPTION — Unanimous + High-Uncertainty Override:
                # When the swarm is unanimous (≥95%, ≥8/10 agents) AND the NN
                # model itself has high uncertainty (σ ≥ 0.15), the model is
                # operating outside its training distribution (e.g., extreme fear
                # regime with few historical examples).  In this case, the 10-agent
                # real-time swarm consensus is more reliable than the NN's
                # extrapolation.  Apply the standard override penalty (capped at
                # 10pt) and proceed; NN boost/soft paths are skipped below.
                _high_model_uncertainty = nn_uncertainty >= 0.15
                if nn_win_prob < _absolute_floor:
                    # v15.3: unc-override minimum floor — even unanimous swarm + uncertain NN
                    # cannot save a signal with catastrophically low win_prob (< 10%).
                    # Rationale: BABYUSDT/AAVEUSDT consistently show win_prob=5-6% on 5m
                    # with regime=CRASH-RISK/ADVERSE — the swarm's bullish technical signals
                    # are overridden by the macro regime; letting them through hurts WR.
                    # [v15.3 Bug L FIX] unc-override minimum raised from 0.10 → _absolute_floor.
                    # BABYUSDT: win_prob=14%, _absolute_floor=20%, unc-override penalty=5.4pt only.
                    # With RL threshold=84% and pre-penalty conf=100%, the 5.4pt penalty was
                    # insufficient to block a catastrophically-low win_prob signal. Since
                    # _UNC_OVERRIDE_MIN_WIN_PROB is now equal to _absolute_floor, and we are
                    # already inside (nn_win_prob < _absolute_floor), the condition below is
                    # logically impossible → ALL signals below the absolute floor go directly
                    # to ABSOLUTE REJECT + 10-min cooldown regardless of swarm unanimity.
                    # Rationale: when NN predicts <20% win probability (2.5σ below 50-50),
                    # swarm consensus cannot override fundamental negative expected value.
                    # The unanimous-swarm path must operate in the _reject_thresh zone (20-38%),
                    # NOT below the absolute floor (<20%).
                    _UNC_OVERRIDE_MIN_WIN_PROB = _absolute_floor  # [v15.3 Bug L]: must = _absolute_floor
                    if _is_unanimous and _high_model_uncertainty and nn_win_prob >= _UNC_OVERRIDE_MIN_WIN_PROB:
                        # (This branch is now logically dead — kept for future calibration
                        # if _absolute_floor is ever lowered below a separate unc-override floor.)
                        _unc_penalty = min(
                            (_reject_thresh - max(nn_win_prob, 0.05)) * 32.0, 18.0
                        )
                        signal.confidence = max(0.0, signal.confidence - _unc_penalty)
                        self.logger.info(
                            f"🧠 NN unc-override [{symbol}] {signal.action}: "
                            f"win_prob={nn_win_prob:.0%} σ={nn_uncertainty:.2f} "
                            f"(model in unknown regime) | unanimous → "
                            f"penalty -{_unc_penalty:.1f}pt → conf={signal.confidence:.1f}% [v15.3 Bug L]"
                        )
                        # Skip further NN path (boost/penalty handled above)
                    else:
                        self.logger.info(
                            f"🧠 NN ABSOLUTE REJECT [{symbol}] {signal.action}: "
                            f"win_prob={nn_win_prob:.0%} < {_absolute_floor:.0%} calibrated floor "
                            f"(reject_thresh={_reject_thresh:.0%} - 0.18) "
                            f"| σ={nn_uncertainty:.2f} danger_zones={n_danger} "
                            f"consensus={_swarm_consensus:.0%} [v9.4]"
                        )
                        # v15.3 BUG FIX: set 10-min cooldown for ANY NN ABSOLUTE REJECT
                        # (win_prob < _absolute_floor ≈ 20%), not just the old < 10%
                        # "catastrophic" threshold.  Win_prob 10-19% causes the full
                        # swarm+NN+PM pipeline to re-run next cycle for the same symbol
                        # (PENGUUSDT 17% → full pipeline burned again → 7% finally
                        # suppressed).  Market features barely change in 10-20s so
                        # a sub-20% NN output won't flip positive within 10 min. [v15.3]
                        self._nn_reject_cooldown[symbol] = time.time() + 600
                        self.logger.info(
                            f"⏳ [{symbol}] NN ABSOLUTE REJECT → 10 min cooldown "
                            f"(win_prob={nn_win_prob:.0%} < {_absolute_floor:.0%} floor) [v15.3]"
                        )
                        return False

                elif _is_unanimous and nn_win_prob >= 0.30 and not (_high_uncertainty and nn_uncertainty > 0.20):
                    # v15.2: Unanimous bypass floor lowered 0.40→0.30.
                    # At 23% WR the NN outputs 0.24-0.28 for above-average signals;
                    # 0.40 floor blocked ALL unanimous bypasses creating starvation.
                    # 0.30 is inside the NN output range at current WR while still
                    # requiring positive-leaning NN signal. Unity G4 (floor 0.12)
                    # and G9/G10 quality gates make the authoritative final decision.
                    _override_penalty = max(0.0, (_reject_thresh - nn_win_prob) * 25.0)
                    _override_penalty = min(_override_penalty, 12.0)
                    signal.confidence = max(60.0, signal.confidence - _override_penalty)
                    self.logger.info(
                        f"🧠 NN unanimous-soft [{symbol}] {signal.action}: "
                        f"consensus={_swarm_consensus:.0%} part={_participation:.0%} "
                        f"win_prob={nn_win_prob:.0%} σ={nn_uncertainty:.2f} "
                        f"→ conf -{_override_penalty:.1f}pt (Unity G4 still authoritative) [v15.2]"
                    )
                else:
                    # Hard reject: win_prob far below reject threshold.
                    # Non-strong gap tightened 0.05→0.02: signals must be within
                    # 2pp of reject_thresh to qualify for soft penalty path.
                    # With reject_thresh=0.38: hard-reject if win_prob < 0.36.
                    _far_below = nn_win_prob < (_reject_thresh - 0.02)

                    # For strong (but not unanimous) signals: wider gap at low WR.
                    # v15.2: gap 0.07→0.13 — at 23% WR NN outputs 0.24-0.28 for
                    # good signals; 0.07 gap (floor=0.31) hard-rejected everything.
                    # 0.13 gap (floor=0.25) lets 25%+ signals reach soft-penalty path.
                    if _is_strong:
                        _far_below = nn_win_prob < (_reject_thresh - 0.13)

                    if _far_below or (_high_uncertainty and _borderline and not _is_strong):
                        reject_reason = (
                            f"high_uncertainty (σ={nn_uncertainty:.2f}) + borderline"
                            if (_high_uncertainty and _borderline)
                            else f"win_prob={nn_win_prob:.0%} << reject_thresh={_reject_thresh:.0%}"
                        )
                        self.logger.info(
                            f"🧠 NN gate REJECTED [{symbol}] {signal.action}: "
                            f"{reject_reason} | danger_zones={n_danger}"
                        )
                        # v15.3 Bug F FIX: 120s cooldown on hard-reject to stop
                        # MANTRAUSDT pattern (win_prob=22-27%) burning the full
                        # swarm+NN+PM pipeline every 15s cycle with no suppression.
                        # Only ABSOLUTE REJECT (< 20%) had a cooldown before this fix.
                        self._nn_hard_reject_cooldown[symbol] = (
                            time.time() + self._NN_HARD_REJECT_COOLDOWN_SEC
                        )
                        self.logger.info(
                            f"⏳ [{symbol}] NN hard-reject → {self._NN_HARD_REJECT_COOLDOWN_SEC:.0f}s "
                            f"suppress (win_prob={nn_win_prob:.0%} in far-below band, "
                            f"saves swarm+pipeline until features shift) [v15.3]"
                        )
                        return False

                if not _is_unanimous and nn_win_prob < _reject_thresh:
                    # Borderline (win_prob just below reject_thresh) — apply a
                    # confidence penalty proportional to the deficit.
                    # Multiplier raised 200→300 and cap 10pt→15pt — borderline
                    # signals face a meaningful hurdle (e.g. 2pp gap = -6pt,
                    # 5pp gap = -15pt cap).  This prevents weak signals from
                    # sneaking through on boosts alone.
                    penalty = (_reject_thresh - nn_win_prob) * 300.0
                    penalty = min(penalty, 15.0)
                    signal.confidence = max(0.0, signal.confidence - penalty)
                    self.logger.info(
                        f"🧠 NN soft penalty [{symbol}] {signal.action}: "
                        f"-{penalty:.1f}pt → conf={signal.confidence:.1f}% "
                        f"(win_prob={nn_win_prob:.0%} borderline reject_thresh={_reject_thresh:.0%} "
                        f"danger_zones={n_danger})"
                    )
                elif nn_win_prob >= _boost_thresh and not _high_uncertainty:
                    # Only boost when model is BOTH confident AND certain
                    nn_boost = min((nn_win_prob - _boost_thresh) * 16.7, 5.0)
                    signal.confidence = min(100.0, signal.confidence + nn_boost)
                    self.logger.debug(
                        f"🧠 NN boost +{nn_boost:.1f}pt → "
                        f"conf={signal.confidence:.1f}% "
                        f"(win_prob={nn_win_prob:.0%} σ={nn_uncertainty:.2f})"
                    )
                else:
                    self.logger.debug(
                        f"🧠 NN pass [{symbol}]: win_prob={nn_win_prob:.0%} "
                        f"σ={nn_uncertainty:.2f} "
                        f"thresh={_opt_thresh:.3f} acc={_nn_accuracy:.1%}"
                    )
            except Exception as _nn_err:
                self.logger.debug(f"NN gate skipped: {_nn_err}")
            # Health tracking: NN layer was invoked (FIX session 4)
            _uh_nn = getattr(self, "_unity_health", None)
            if _uh_nn:
                _uh_nn.record_call("NeuralNetwork", True)

        if self.bm25_memory is not None:
            try:
                _sit = (
                    f"symbol={symbol} action={signal.action} "
                    f"rsi={getattr(signal, 'rsi', 50):.0f} "
                    f"vol_ratio={getattr(signal, 'volume_ratio', 1.0):.2f} "
                    f"consensus={getattr(signal, 'swarm_consensus', 0):.2f} "
                    f"confidence={signal.confidence:.1f}"
                )
                _bm25_adj = self.bm25_memory.get_confidence_adjustment(
                    _sit, signal.action
                )
                if abs(_bm25_adj) >= 2.0:
                    signal.confidence = max(0, min(100,
                        signal.confidence + _bm25_adj
                    ))
                    self.logger.debug(
                        f"🧠 BM25 memory adj {_bm25_adj:+.1f}pt → "
                        f"conf={signal.confidence:.1f}%"
                    )
            except Exception as _bm25_err:
                self.logger.debug(f"BM25 query skipped: {_bm25_err}")
            # Health tracking: Memory (BM25) layer was invoked (FIX session 4)
            _uh_bm = getattr(self, "_unity_health", None)
            if _uh_bm:
                _uh_bm.record_call("Memory(Trade+BM25)", True)

        # ── Unity Engine 12-Gate Filter (active when running under UnityEngine) ──
        # Applies the 12-gate quality pipeline after all Phase 1 boosts and NN/BM25
        # adjustments.  Reads GEX snapshot from the engine's per-symbol cache.
        _unity_filter  = getattr(self, "_unity_signal_filter",  None)
        _unity_booster = getattr(self, "_unity_booster",        None)
        _unity_metrics = getattr(self, "_unity_metrics",        None)
        _unity_engine  = getattr(self, "_unity_engine",         None)
        # FIX session 4: health is fetched here too (may not be set if klines < 50 bars)
        _unity_health_f = getattr(self, "_unity_health",        None)

        if _unity_filter is not None and _unity_booster is not None:
            try:
                # Retrieve latest GEX snapshot for this symbol
                # FIX: use get_gex_snapshot() which unpacks the (snap, ts) tuple
                # and enforces freshness; direct dict access returned a tuple causing
                # Gate 7 getattr() failures (snap was silently discarded).
                _gex_snap = None
                if _unity_engine is not None:
                    if hasattr(_unity_engine, "get_gex_snapshot"):
                        _gex_snap = _unity_engine.get_gex_snapshot(symbol)
                    else:
                        raw = _unity_engine._gex_snapshots.get(symbol)
                        if isinstance(raw, tuple) and len(raw) == 2:
                            _gex_snap = raw[0]
                        else:
                            _gex_snap = raw
                # Health tracking: GEX layer call (FIX session 5)
                # Only record a call when we actually have a snapshot — a missing
                # snapshot means the rotating scanner hasn't reached this symbol yet,
                # NOT that GEX failed. Recording False on every unseen symbol caused
                # AEGIS_GEX to show ❌ sr=0% even while GEX regime was live/correct.
                if _unity_health_f and _gex_snap is not None:
                    _unity_health_f.record_call("AEGIS_GEX", True)

                # v10.8: Extract real OHLCV from Phase 1 captured klines for Gate 10.
                # Format: [ts, open, high, low, close, volume]
                _pm_closes_g10  = [float(k[4]) for k in _pm_klines] if _pm_klines else []
                _pm_highs_g10   = [float(k[2]) for k in _pm_klines] if _pm_klines else []
                _pm_lows_g10    = [float(k[3]) for k in _pm_klines] if _pm_klines else []
                _pm_volumes_g10 = [float(k[5]) for k in _pm_klines] if _pm_klines else []

                _signal_dict = {
                    "symbol":       symbol,          # FIX: Gate 8 per-symbol WR needs this
                    "action":       signal.action,
                    "direction":    signal.action,
                    "entry_price":  signal.entry_price,
                    "current_price": signal.entry_price,
                    "stop_loss":    getattr(signal, "stop_loss",    0) or 0,
                    "take_profit_1": getattr(signal, "take_profit_1",
                                    getattr(signal, "take_profit",  0)) or 0,
                    "take_profit_2": getattr(signal, "take_profit_2",
                                    getattr(signal, "take_profit",  0)) or 0,
                    "take_profit_3": getattr(signal, "take_profit_3",
                                    getattr(signal, "take_profit",  0)) or 0,
                    "confidence":   signal.confidence,
                    "ai_confidence": signal.confidence,
                    "consensus":    getattr(signal, "swarm_consensus", 0.0),
                    "swarm_consensus": getattr(signal, "swarm_consensus", 0.0),
                    # v9.5: forward bot-side NN evaluation so Unity G4 reuses the
                    # same MC-Dropout sample instead of re-running the model.
                    # Eliminates the bot/Unity stochastic mismatch
                    # (e.g. bot=0.58, Unity=0.50 on same signal/instant).
                    "nn_win_prob_precomputed": float(nn_win_prob) if 'nn_win_prob' in locals() else None,
                    "nn_uncertainty_precomputed": float(nn_uncertainty) if 'nn_uncertainty' in locals() else None,
                    # v10.8 BUG FIX: Previously absent → Unity Gate 10 IRONS always re-scored
                    # from a 1-bar stub (atr=0.01, rsi=50, htf=NEUTRAL, closes=[entry]),
                    # producing artificially low IRONS scores and disabling the ATR vol penalty.
                    # Now passes real 200-bar 15m indicator data captured in Phase 1.
                    "atr":           float(getattr(signal, "atr_value",   0) or 0),
                    "htf_1h":        str(getattr(signal, "mtf_1h",        "") or ""),
                    "htf_4h":        str(getattr(signal, "mtf_4h",        "") or ""),
                    "rsi":           float(getattr(signal, "rsi",          50) or 50),
                    "volume_ratio":  float(getattr(signal, "volume_ratio", 1.0) or 1.0),
                    # Pre-computed IRONS from SwarmSignal (real 200-bar data).
                    # Gate 10 uses this directly when > 0, bypassing stub re-score.
                    "irons_score_precomputed": int(getattr(signal, "irons_score", 0) or 0),
                    # Real OHLCV for Gate 10 IRONS fallback path (v10.8)
                    "closes":   _pm_closes_g10,
                    "highs":    _pm_highs_g10,
                    "lows":     _pm_lows_g10,
                    "volumes":  _pm_volumes_g10,
                    # v18.14: Live 1m kline fields from @kline_1m WS — sub-60s freshness.
                    # Gate 10 IRONS stub path uses these when REST OHLCV is empty AND
                    # kline age < 90s, delivering a real (high-low) ATR proxy instead of
                    # the flat entry_price stub that previously caused 40-80× ATR underestimation.
                    **({
                        "live_kline_close":  float(_lkd["c"]),
                        "live_kline_high":   float(_lkd["h"]),
                        "live_kline_low":    float(_lkd["l"]),
                        "live_kline_volume": float(_lkd["v"]),
                        "live_kline_ts":     float(_lkd["t"]),
                        "live_kline_fresh":  (time.time() - float(_lkd["t"]) / 1000.0) < 90.0,
                    } if (_lkd := (getattr(_unity_engine, "_live_kline_data", {}) or {}).get(symbol)) else {
                        "live_kline_fresh": False,
                    }),
                }
                # Store signal dict for next-cycle batch NN pre-cache [v18.17]
                self._prev_cycle_nn_dicts[symbol] = _signal_dict
                # Health tracking: MiroFish Swarm consumed this signal (FIX session 4)
                if _unity_health_f:
                    _unity_health_f.record_call("MiroFishSwarm", True)

                # Use the RL-adapted threshold from the booster
                _rl_threshold = float(_unity_booster.dynamic_threshold)

                # v9.9 Apex-#2: pre-fetch depth-walked slippage for this symbol
                # in this async context, then pass into the (sync) filter as a
                # kwarg.  Bounded by `_unity_slip_timeout_sec` so a slow REST
                # response can never delay the per-cycle scan.  On any error
                # the result is None and Gate 0 falls back to live WS spread.
                _depth_slip_result = None
                _u_depth = getattr(self, "_unity_depth_slip", None)
                if _u_depth is not None:
                    try:
                        _ref_notional = float(getattr(self, "_unity_slip_ref_notional", 5000.0))
                        _slip_timeout = float(getattr(self, "_unity_slip_timeout_sec", 1.5))
                        _side_for_slip = (signal.action or "").upper()
                        _depth_slip_result = await asyncio.wait_for(
                            _u_depth.estimate(symbol, _side_for_slip, _ref_notional),
                            timeout=_slip_timeout,
                        )
                    except (asyncio.TimeoutError, Exception):
                        _depth_slip_result = None

                _passed, _reason, _quality = _unity_filter.apply(
                    signal_data=_signal_dict,
                    nn_trainer=self.nn_trainer,
                    # FIX v5.2: pass real ATAS/Bookmap data captured in Phase 1
                    # so Gate 5 can apply the symmetric veto and award full 10pts.
                    # Previously always None → Gate 5 always trivially passed.
                    atas_result=_unity_atas_result,
                    bookmap_result=_unity_bookmap_result,
                    gex_snapshot=_gex_snap,
                    ai_threshold=_rl_threshold,
                    # v9.9 Apex-#2: depth-walked VWAP slippage at planned notional
                    depth_slippage_result=_depth_slip_result,
                )

                # Health tracking: Unity Engine filter outcome (FIX session 5)
                # Record True (success) regardless of pass/reject — a gate rejection
                # is the CORRECT behavior of the filter, NOT a layer failure. Recording
                # False on rejection caused UnityEngine to show ⚠️ whenever any signal
                # was vetoed, which made sr reflect gate pass-rate not layer health.
                if _unity_health_f:
                    _unity_health_f.record_call("UnityEngine", True)

                # v6.2: UTBot confirmation health tracking — record that UTBot was
                # consulted as a confirmation layer (agreement = higher quality).
                _utbot_layer = getattr(self, "_unity_utbot", None)
                if _unity_health_f and _utbot_layer is not None:
                    try:
                        _sig_hist = _utbot_layer.get_signal_history() if hasattr(_utbot_layer, "get_signal_history") else []
                        # UTBot success = it has a signal history AND it's loaded
                        _unity_health_f.record_call("UTBot_Strategy", success=True)
                    except Exception:
                        _unity_health_f.record_call("UTBot_Strategy", success=True)
                elif _unity_health_f and _utbot_layer is None:
                    # UTBot loaded but produces no data yet → still record as active call
                    _unity_health_f.record_call("UTBot_Strategy", success=True)

                if _unity_metrics is not None:
                    _unity_metrics.total_signals_evaluated += 1
                    _unity_metrics.last_signal_quality = _quality

                if not _passed:
                    if _unity_metrics is not None:
                        _unity_metrics.total_signals_rejected += 1
                    self.logger.info(
                        f"⛔ [{symbol}] Unity 12-gate REJECTED: {_reason} "
                        f"| quality={_quality:.1f}/100"
                    )
                    # v15.3 EV-fail cooldown: suppress this symbol for ~3 cycles
                    # when the failure is G0 EV (price-structure based, stable over
                    # short windows) to avoid burning Phase 1 quota on repeat fails.
                    # v15.3 Repeat-offender escalation: after N consecutive G0 fails,
                    # extend to 5-min suppression (structural EV deficit won't self-heal
                    # in 90s — needs a genuine price breakout to change TP/SL geometry).
                    if _reason.startswith("G0_FAIL"):
                        _streak = self._ev_fail_streak.get(symbol, 0) + 1
                        self._ev_fail_streak[symbol] = _streak
                        if _streak >= self._EV_FAIL_ESCALATE_N2:
                            # v17.4: Asian-session adaptive suppression ceiling.
                            # EV deficits during the Asian session (00:00–06:00 UTC) self-heal
                            # as London pre-market opens at ~06:00 UTC — wider spreads and
                            # larger TP1/SL geometry arrive with European liquidity.
                            # Cap level-3 suppress at 15 min so the engine re-evaluates at
                            # the session boundary instead of staying dark for 30 min.
                            # Late-NY (23:00 UTC onward) also gets the cap — it rolls into
                            # Asian session and EV recovers after the day-change reset.
                            _utc_h   = datetime.utcnow().hour
                            _is_asian = _utc_h < 6 or _utc_h >= 23
                            _cd      = min(self._EV_FAIL_VERY_LONG_SEC, 900.0) if _is_asian \
                                       else self._EV_FAIL_VERY_LONG_SEC
                            _sess_tag = "Asian-15min-cap" if _is_asian else "30min"
                            self.logger.info(
                                f"⏳ [{symbol}] G0 EV-fail streak={_streak} ≥ {self._EV_FAIL_ESCALATE_N2} "
                                f"→ level-3 escalated to {_cd:.0f}s suppress "
                                f"(chronic EV deficit · {_sess_tag}) [v17.4]"
                            )
                        elif _streak >= self._EV_FAIL_ESCALATE_N:
                            _cd = self._EV_FAIL_LONG_SEC   # 5-min level-2
                            self.logger.info(
                                f"⏳ [{symbol}] G0 EV-fail streak={_streak} ≥ {self._EV_FAIL_ESCALATE_N} "
                                f"→ escalated to {_cd:.0f}s suppress [v15.3]"
                            )
                        else:
                            _cd = self._EV_FAIL_COOLDOWN_SEC   # base 90s level-1
                            self.logger.debug(
                                f"⏳ [{symbol}] G0 EV-fail streak={_streak} "
                                f"→ {_cd:.0f}s cooldown [v15.3]"
                            )
                        self._ev_fail_cooldown[symbol] = time.time() + _cd
                    # v15.3 G2.5 orderbook-fail cooldown: when orderbook flow strongly
                    # opposes the signal (STRONG_BUY vs SELL / STRONG_SELL vs BUY),
                    # suppress for 2 min to avoid burning the full swarm+NN+PM pipeline
                    # every cycle for the same persistent imbalance.  Self-heals as soon
                    # as the orderbook imbalance flips direction (flow changes in 2 min).
                    elif _reason.startswith("G2.5_FAIL"):
                        _ob_streak = self._ob_fail_streak.get(symbol, 0) + 1
                        self._ob_fail_streak[symbol] = _ob_streak
                        if _ob_streak >= self._OB_FAIL_ESCALATE_N:
                            _ob_cd = self._OB_FAIL_LONG_SEC  # 5-min level-2 for chronic OB-opposition
                            self.logger.info(
                                f"⏳ [{symbol}] G2.5 orderbook-fail streak={_ob_streak} ≥ {self._OB_FAIL_ESCALATE_N} "
                                f"→ escalated to {_ob_cd:.0f}s suppress (chronic OB opposition) [v15.3]"
                            )
                        else:
                            _ob_cd = self._OB_FAIL_COOLDOWN_SEC  # base 120s
                            self.logger.info(
                                f"⏳ [{symbol}] G2.5 orderbook-fail streak={_ob_streak} → {_ob_cd:.0f}s "
                                f"suppress (saves swarm+NN+PM pipeline until flow reverses) [v15.3]"
                            )
                        self._ob_fail_cooldown[symbol] = time.time() + _ob_cd
                    elif _reason.startswith("G1_FAIL"):
                        # v15.3 G1_FAIL cooldown: weighted R:R below adaptive floor is
                        # pure TP/SL geometry — won't change without genuine price movement.
                        # AIGENSYNUSDT: R:R=2.79 < 3.20 every 16s (22 total hits).
                        _g1_streak = self._g1_fail_streak.get(symbol, 0) + 1
                        self._g1_fail_streak[symbol] = _g1_streak
                        if _g1_streak >= self._EV_FAIL_ESCALATE_N:
                            _g1_cd = self._EV_FAIL_LONG_SEC   # 300s escalated
                            self.logger.info(
                                f"⏳ [{symbol}] G1_FAIL streak={_g1_streak} ≥ {self._EV_FAIL_ESCALATE_N} "
                                f"→ escalated to {_g1_cd:.0f}s suppress (R:R geometry structural) [v15.3]"
                            )
                        else:
                            _g1_cd = self._G1_FAIL_COOLDOWN_SEC   # 90s base
                            self.logger.info(
                                f"⏳ [{symbol}] G1_FAIL streak={_g1_streak} "
                                f"→ {_g1_cd:.0f}s suppress (saves swarm until R:R improves) [v15.3]"
                            )
                        self._g1_fail_cooldown[symbol] = time.time() + _g1_cd
                    elif _reason.startswith("G3_FAIL"):
                        # v15.3 G3_FAIL cooldown: symbol failed confidence gate after full
                        # Phase 1 (swarm+PM+NN).  APEUSDT pattern: conf=73.4% + PM+7 →
                        # 77.4% < 84% RL threshold, repeated every 20s cycle.  Suppress
                        # 90s base with streak escalation to 300s after 3 consecutive fails.
                        _g3_streak = self._g3_fail_streak.get(symbol, 0) + 1
                        self._g3_fail_streak[symbol] = _g3_streak
                        if _g3_streak >= self._EV_FAIL_ESCALATE_N:
                            _g3_cd = self._EV_FAIL_LONG_SEC   # 300s escalated
                            self.logger.info(
                                f"⏳ [{symbol}] G3_FAIL streak={_g3_streak} ≥ {self._EV_FAIL_ESCALATE_N} "
                                f"→ escalated to {_g3_cd:.0f}s suppress (conf gap structural) [v15.3]"
                            )
                        else:
                            _g3_cd = self._G3_FAIL_COOLDOWN_SEC   # 90s base
                            self.logger.info(
                                f"⏳ [{symbol}] G3_FAIL streak={_g3_streak} "
                                f"→ {_g3_cd:.0f}s suppress (saves swarm+Phase1 until conf rises) [v15.3]"
                            )
                        self._g3_fail_cooldown[symbol] = time.time() + _g3_cd
                    elif _reason.startswith("G9_FAIL"):
                        # v15.3 G9_FAIL cooldown: composite quality below adaptive floor
                        # after full Phase 1+2.  APEUSDT: quality=42-50 < 55-58 every 20s
                        # (21 hits).  PENGUUSDT=20, APTUSDT=20, MANTRAUSDT=16.  Quality is
                        # 25-indicator IRONS composite that won't shift in 20s.  Suppress
                        # 90s base, escalate to 300s after 3 consecutive G9 fails.
                        _g9_streak = self._g9_fail_streak.get(symbol, 0) + 1
                        self._g9_fail_streak[symbol] = _g9_streak
                        if _g9_streak >= self._EV_FAIL_ESCALATE_N:
                            _g9_cd = self._EV_FAIL_LONG_SEC   # 300s escalated
                            self.logger.info(
                                f"⏳ [{symbol}] G9_FAIL streak={_g9_streak} ≥ {self._EV_FAIL_ESCALATE_N} "
                                f"→ escalated to {_g9_cd:.0f}s suppress (quality structural) [v15.3]"
                            )
                        else:
                            _g9_cd = self._G9_FAIL_COOLDOWN_SEC   # 90s base
                            self.logger.info(
                                f"⏳ [{symbol}] G9_FAIL streak={_g9_streak} "
                                f"→ {_g9_cd:.0f}s suppress (saves swarm+Phase1 until quality improves) [v15.3]"
                            )
                        self._g9_fail_cooldown[symbol] = time.time() + _g9_cd
                    elif "WR<30%" in _reason and _reason.startswith("BLACKLIST"):
                        # v15.3 G_BLK cooldown: lifetime WR<30% blacklist won't clear until
                        # new wins resolve in trade_history.db — suppress for 10 min so the
                        # full swarm pipeline is not wasted cycling on a deterministic block.
                        self._gblk_cooldown[symbol] = time.time() + self._GBLK_COOLDOWN_SEC
                        self.logger.info(
                            f"⏳ [{symbol}] G_BLK WR<30% → {self._GBLK_COOLDOWN_SEC:.0f}s suppress "
                            f"(swarm saved until WR resolves above 30%) [v15.3]"
                        )
                    return False

                # v6.2: record per-symbol cooldown immediately after gate passes
                # v18.51: pass direction so booster._last_direction is updated for Kelly Step 20
                _unity_filter.mark_signal_sent(symbol, str(getattr(signal, "action", "BUY") or "BUY"))
                # v15.3: Reset repeat-offender streaks — gates passed, conditions changed
                if symbol in self._ev_fail_streak:
                    _old_streak = self._ev_fail_streak.pop(symbol, 0)
                    if _old_streak > 0:
                        self.logger.debug(
                            f"✅ [{symbol}] G0 EV passed — streak reset (was {_old_streak}) [v15.3]"
                        )
                if symbol in self._g1_fail_streak:
                    _old_g1 = self._g1_fail_streak.pop(symbol, 0)
                    if _old_g1 > 0:
                        self.logger.debug(
                            f"✅ [{symbol}] G1 R:R passed — streak reset (was {_old_g1}) [v15.3]"
                        )
                if symbol in self._g3_fail_streak:
                    _old_g3 = self._g3_fail_streak.pop(symbol, 0)
                    if _old_g3 > 0:
                        self.logger.debug(
                            f"✅ [{symbol}] G3 conf passed — streak reset (was {_old_g3}) [v15.3]"
                        )
                if symbol in self._g9_fail_streak:
                    _old_g9 = self._g9_fail_streak.pop(symbol, 0)
                    if _old_g9 > 0:
                        self.logger.debug(
                            f"✅ [{symbol}] G9 quality passed — streak reset (was {_old_g9}) [v15.3]"
                        )
                if symbol in self._ob_fail_streak:
                    _old_ob = self._ob_fail_streak.pop(symbol, 0)
                    if _old_ob > 0:
                        self.logger.debug(
                            f"✅ [{symbol}] G2.5 OB passed — streak reset (was {_old_ob}) [v15.3]"
                        )
                self.logger.info(
                    f"✅ [{symbol}] Unity 12-gate PASSED | quality={_quality:.1f}/100 "
                    f"| RL-threshold={_rl_threshold:.0f}%"
                )
            except Exception as _uf_err:
                self.logger.debug(f"Unity filter non-fatal skip: {_uf_err}")

        # ── Phase 2: Atomic gate — lock held for milliseconds only ────────────
        # Two coroutines that both passed the initial pre-check cannot both send
        # for the same symbol: the loser of the lock race re-checks can_send_signal
        # and finds the per-symbol cooldown already taken.
        # Lock now held for <5ms: IRONS check + final threshold + send setup only.
        # NN inference and BM25 query run OUTSIDE the lock (see above).
        async with self._signal_gate_lock:
            # Re-check inside lock: another coroutine may have sent while we boosted.
            # v15.3: pass skip_global_gap=True when under the per-cycle cap so that
            # a second/third diversified symbol in the SAME scan cycle is not blocked
            # by the 90s global gap set by the FIRST symbol sent this cycle.  The
            # per-cycle cap (max 3) is the correct anti-correlation guard within a
            # cycle; the 90s gap is only meaningful between scan cycles. [v15.3]
            _same_cycle_under_cap = (self._cycle_signals_sent < self._MAX_SIGNALS_PER_CYCLE)
            if not self.can_send_signal(symbol, action=signal.action,
                                        swarm_consensus=_sig_consensus,
                                        skip_global_gap=_same_cycle_under_cap):
                # v7.1 BUG FIX: count this as a rejection so eval/reject/sent always reconcile
                _um_lock = getattr(self, "_unity_metrics", None)
                if _um_lock is not None:
                    _um_lock.total_signals_rejected += 1
                return False

            try:
                # ── IRONS score quality gate ──
                # Reject signals where the comprehensive 25-indicator IRONS panel
                # scores below the adaptive minimum set by Gate 10.
                _irons_score = getattr(signal, "irons_score", 0)
                # v10.7 BUG FIX: previous hardcoded floor of 65 created a double-gate
                # AFTER Unity Gate 10 already ran its adaptive IRONS minimum (currently
                # 57 per IRONS_MIN_SCORE env).  A signal scoring 58-64 would pass Gate 10
                # then be silently killed here — a contradiction that wasted 100% of the
                # gate pipeline work.  Now uses the same adaptive minimum as Gate 10,
                # falling back to the IRONS_MIN_SCORE env (default 60) when no filter.
                _irons_floor = 60
                try:
                    _irons_floor = int(os.getenv("IRONS_MIN_SCORE", "60"))
                except Exception:
                    pass
                if _unity_filter is not None and hasattr(_unity_filter, "effective_irons_min"):
                    try:
                        _irons_floor = int(_unity_filter.effective_irons_min)
                    except Exception:
                        pass
                if _irons_score > 0 and _irons_score < _irons_floor:
                    self.logger.info(
                        f"⛔ [{symbol}] IRONS score {_irons_score}/100 < {_irons_floor} adaptive minimum "
                        f"— insufficient indicator alignment, signal rejected [v10.7]"
                    )
                    # v7.1 BUG FIX: IRONS post-filter rejection was silently unaccounted
                    _um_irons = getattr(self, "_unity_metrics", None)
                    if _um_irons is not None:
                        _um_irons.total_signals_rejected += 1
                    return False

                # ── Final confidence gate ──
                # Unanimous bypass: when the full swarm agrees (consensus ≥ 95%)
                # with high participation (≥ 80%), the adaptive loss-streak boost
                # to the threshold is suspended.  10 independent agents achieving
                # 95%+ consensus is stronger evidence than the small recent-trade
                # sample that drives the loss-streak adjustment.  The base 80%
                # gate still applies — only the adaptive boost (≤ 20pt) is waived.
                _eff_threshold = confidence_threshold
                _sig_consensus_final = float(getattr(signal, "swarm_consensus", 0.0))
                _sig_part_final = float(getattr(signal, "participation_rate", 0.0))
                if _sig_consensus_final >= 0.95 and _sig_part_final >= 0.80:
                    # Unanimous bypass: waive BOTH the adaptive streak boost and the
                    # recent-loss-rate boost.  The base 80% minimum gate still applies.
                    if confidence_threshold > self._ai_threshold_pct:
                        _eff_threshold = self._ai_threshold_pct
                        self.logger.info(
                            f"⚡ [{symbol}] Unanimous bypass: consensus={_sig_consensus_final:.0%} "
                            f"part={_sig_part_final:.0%} → threshold lowered "
                            f"{confidence_threshold:.0f}%→{_eff_threshold:.0f}% "
                            f"(streak+RLR boosts waived, base {self._ai_threshold_pct:.0f}% applies)"
                        )
                if signal.confidence < _eff_threshold:
                    self.logger.info(
                        f"⛔ Signal rejected: conf={signal.confidence:.1f}% < threshold={_eff_threshold:.0f}%"
                    )
                    # v7.1 BUG FIX: confidence rejection was silently unaccounted
                    _um_conf = getattr(self, "_unity_metrics", None)
                    if _um_conf is not None:
                        _um_conf.total_signals_rejected += 1
                    return False

                # ── Per-cycle anti-correlation cap ────────────────────────────
                # Prevents sending correlated signals (e.g. MUSDT+KATUSDT+ZBTUSDT
                # all SELL simultaneously).  Inside the lock so the count is safe.
                if self._cycle_signals_sent >= self._MAX_SIGNALS_PER_CYCLE:
                    self.logger.info(
                        f"⛔ [{symbol}] Per-cycle cap reached "
                        f"({self._cycle_signals_sent}/{self._MAX_SIGNALS_PER_CYCLE}) "
                        f"— deferring to next cycle (anti-correlation guard) [v15.3]"
                    )
                    _um_cyc = getattr(self, "_unity_metrics", None)
                    if _um_cyc is not None:
                        _um_cyc.total_signals_rejected += 1
                    return False

                # ── Send to @ichimokutradingsignal ──
                # _skip_rate_check=True: rate gates were already verified twice
                # (pre-lock at line ~965 and inside lock above).  Skipping the
                # third redundant check inside send_signal_to_channel saves one
                # synchronous iteration through signal_timestamps per signal.
                _send_result = await self.send_signal_to_channel(
                    signal,
                    bb_position=_local_bb_position,
                    _skip_rate_check=True,
                )

                # ── Update Unity Engine metrics on successful send ────────────
                if _send_result:
                    # v15.3: Increment per-cycle counter (anti-correlation cap)
                    self._cycle_signals_sent += 1
                    _u_metrics = getattr(self, "_unity_metrics", None)
                    if _u_metrics is not None:
                        _u_metrics.total_signals_sent += 1
                        from datetime import datetime as _dt
                        _u_metrics.last_signal_time = _dt.now()
                    # v5.7 BUG FIX: Record to signal-rate ring so console Signals/hr
                    # is populated.  Previously _unity_signal_times was wired by Unity
                    # Engine but never appended here — console showed 🔴 0 forever.
                    _u_st = getattr(self, "_unity_signal_times", None)
                    if _u_st is not None:
                        try:
                            _u_st.append(time.time())
                        except Exception:
                            pass
                    # Health tracking: TelegramBot layer (FIX session 4)
                    _uh_tg = getattr(self, "_unity_health", None)
                    if _uh_tg:
                        _uh_tg.record_call("TelegramBot", True)

                return _send_result

            except Exception as e:
                self.logger.error(f"process_signals error: {e}")
                return False

    async def check_price_alerts(self):
        """Check and trigger user price alerts"""
        if not self.price_alerts:
            return
        try:
            cur_price = await self.trader.get_current_price()
            if not cur_price:
                return

            for user_id, alerts in list(self.price_alerts.items()):
                triggered = []
                for alert in alerts:
                    target = alert["price"]
                    direction = alert.get("direction", "crosses")
                    if (direction == "above" and cur_price >= target) or \
                       (direction == "below" and cur_price <= target):
                        triggered.append(alert)
                        msg = (
                            f"🔔 **Price Alert Triggered!**\n\n"
                            f"• **BTCUSDT:** `${cur_price:,.2f}`\n"
                            f"• **Target:** `${target:,.2f}` ({direction})\n"
                            f"• **Set at:** {alert['created']}"
                        )
                        await self.send_message(user_id, msg)

                self.price_alerts[user_id] = [a for a in alerts if a not in triggered]

        except Exception as e:
            self.logger.debug(f"Price alert check error: {e}")

    async def run_continuous_scanner(self):
        """
        Main continuous scanner — TRUE PARALLEL scan of ALL USDM markets simultaneously.

        Architecture change from legacy round-robin (one symbol every 5-15s → 6-20 min
        per full cycle of 80 symbols) to asyncio.gather parallel batches (semaphore
        configured via SCAN_PARALLEL_LIMIT) completing a full pass in ~20-40 seconds.

        Cycle:
          1. Refresh symbol list (hourly)
          2. Check price alerts
          3. Parallel-scan ALL active symbols (asyncio.gather + Semaphore(SCAN_PARALLEL_LIMIT))
          4. Heartbeat log every 5 min
          5. Poll Telegram for commands
          6. Sleep CYCLE_SLEEP_SECONDS between full parallel-scan cycles
        """
        self.logger.info("🚀 Starting MiroFish PARALLEL scanner — ALL USDM FUTURES...")
        self.logger.info(f"   Mode: TRUE PARALLEL (asyncio.gather + Semaphore({self._scan_limit}))")

        await self.test_telegram_connection()
        await self._drain_pending_updates()
        await self.send_startup_test_message()

        # ── Cancel stale background tasks from previous runs ────────────────
        for _task_attr in ("_outcome_tracker_task", "_public_api_task"):
            _old = getattr(self, _task_attr, None)
            if _old is not None and not _old.done():
                _old.cancel()
                self.logger.info(f"🔄 Cancelled stale {_task_attr}")
            setattr(self, _task_attr, None)
        # FIX v5.2: Only reset outcome_tracker if Unity Engine has NOT already
        # wired a shared single instance.  Unconditionally resetting it here was
        # the root cause of the OutcomeTracker dedup bug — Unity Engine wired
        # bot.outcome_tracker = outcome_tracker_instance but this line cleared it,
        # causing a SECOND OutcomeTracker to be created, resulting in two competing
        # instances both polling Binance and writing to the same SQLite DB.
        _unity_engine_ref = getattr(self, "_unity_engine", None)
        if _unity_engine_ref is None:
            # Not running under Unity Engine — safe to reset (standalone mode)
            if hasattr(self, "outcome_tracker"):
                self.outcome_tracker = None
        else:
            # Running under Unity Engine — only reset if no instance was wired
            if getattr(self, "outcome_tracker", None) is None:
                pass  # already None, nothing to do

        # ── Start OutcomeTracker as a live background task ────────────────────
        if _HAS_NEURAL and self.trade_memory and self.outcome_tracker is None:
            try:
                self.outcome_tracker = OutcomeTracker(
                    self.trade_memory, self.nn_trainer, self.trader, bot=self,
                    bm25_memory=self.bm25_memory
                )
                self._outcome_tracker_task = asyncio.create_task(
                    self.outcome_tracker.run(),
                    name="OutcomeTracker",
                )

                def _ot_done_cb(t: asyncio.Task):
                    if t.cancelled():
                        return
                    exc = t.exception()
                    if exc is not None:
                        self.logger.error(
                            "❌ OutcomeTracker task exited with exception — "
                            "outcome tracking halted until next restart",
                            exc_info=exc,
                        )

                self._outcome_tracker_task.add_done_callback(_ot_done_cb)
                self.logger.info("🧠 OutcomeTracker background task started")
            except Exception as ot_err:
                self.logger.warning(f"⚠️ OutcomeTracker init failed: {ot_err}")

        if self.public_api is not None and self._public_api_task is None:
            try:
                self._public_api_task = asyncio.create_task(
                    self.public_api.run(),
                    name="PublicAPIIntelligence",
                )
                def _pai_done_cb(t: asyncio.Task):
                    if t.cancelled():
                        return
                    exc = t.exception()
                    if exc is not None:
                        self.logger.error(
                            "❌ PublicAPIIntelligence task exited with exception",
                            exc_info=exc,
                        )
                self._public_api_task.add_done_callback(_pai_done_cb)
                self.logger.info("🌐 PublicAPIIntelligence background refresh started")
            except Exception as pai_err:
                self.logger.warning(f"⚠️ PublicAPIIntelligence background start failed: {pai_err}")

        # ── Dedicated Telegram long-poll task ────────────────────────────────
        # ROOT CAUSE FIX (v15.4): inline buttons were frozen because callbacks
        # were only processed inside the scan cycle (30-60s sleep).  Telegram's
        # answerCallbackQuery deadline is 30s — every button press timed out.
        # The dedicated task below polls independently with a 25s long-poll so
        # callbacks are answered within <1s of the button press.
        _tg_dedicated_poll_task = asyncio.create_task(
            self._tg_dedicated_poll_loop(),
            name="TGDedicatedPoll",
        )

        def _tg_poll_done_cb(t: asyncio.Task) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                self.logger.error(
                    "❌ TGDedicatedPoll exited with error — inline buttons disabled "
                    "until next restart", exc_info=exc,
                )

        _tg_dedicated_poll_task.add_done_callback(_tg_poll_done_cb)
        self.logger.info("📬 [v15.4] Dedicated TG poll task started — inline buttons now responsive")

        # ── Initial symbol list refresh ───────────────────────────────────────
        await self._refresh_symbol_list()

        # Inter-cycle sleep (seconds between full parallel scan rounds)
        # With 80 symbols and semaphore=20, a full scan takes ~20-40s.
        # The cycle sleep adds extra breathing room before the next round.
        cycle_sleep_min = int(os.getenv("CYCLE_SLEEP_MIN", "30"))
        cycle_sleep_max = int(os.getenv("CYCLE_SLEEP_MAX", "60"))
        if cycle_sleep_min <= 0:
            cycle_sleep_min = 30
        if cycle_sleep_max < cycle_sleep_min:
            cycle_sleep_max = cycle_sleep_min + 30

        last_heartbeat     = time.time()
        heartbeat_interval = max(60, int(os.getenv("HEARTBEAT_INTERVAL", "300")))
        cycle_count        = 0

        while True:
            try:
                cycle_start = time.time()
                cycle_count += 1

                # ── 1. Periodically refresh the active symbol list ────────────
                await self._refresh_symbol_list()

                if cycle_count % 100 == 0:
                    _active_set = set(self._active_symbols)
                    self._symbol_last_signal = {
                        k: v for k, v in self._symbol_last_signal.items()
                        if k in _active_set or time.time() - v < 86400
                    }
                    self._symbol_signal_count = {
                        k: v for k, v in self._symbol_signal_count.items()
                        if k in _active_set
                    }
                    # v15.3: Purge expired NN-reject cooldowns (prevents memory leak)
                    _now_purge = time.time()
                    self._nn_reject_cooldown = {
                        k: v for k, v in self._nn_reject_cooldown.items()
                        if v > _now_purge
                    }

                # ── 1b. GEX regime change → auto-clear NN-reject cooldowns ──────
                # When GEX regime improves (e.g. FLIP ZONE→POSITIVE, NEG→FLIP ZONE,
                # NEG→POSITIVE), previously suppressed symbols may now have valid
                # signals — clear the 10-min NN-reject cooldown so they get a fresh
                # evaluation.  Track regime in _prev_gex_regime (initialised below). [v15.3]
                _um_gex = getattr(self, "_unity_metrics", None)
                _cur_gex_regime = (
                    getattr(_um_gex, "last_gex_regime", "UNKNOWN")
                    if _um_gex is not None else "UNKNOWN"
                )
                _prev_gex = getattr(self, "_prev_gex_regime", _cur_gex_regime)
                if _cur_gex_regime != _prev_gex and _cur_gex_regime not in ("UNKNOWN", ""):
                    _regime_rank = {"NEGATIVE": 0, "FLIP ZONE": 1, "NEUTRAL": 1, "POSITIVE": 2}
                    _prev_rank = _regime_rank.get(_prev_gex, 1)
                    _cur_rank  = _regime_rank.get(_cur_gex_regime, 1)
                    if _cur_rank > _prev_rank:
                        _cleared = len(self._nn_reject_cooldown)
                        _cleared_hard = len(self._nn_hard_reject_cooldown)
                        self._nn_reject_cooldown.clear()
                        self._nn_hard_reject_cooldown.clear()
                        self.logger.info(
                            f"📡 GEX regime improved {_prev_gex}→{_cur_gex_regime} — "
                            f"cleared {_cleared} NN-reject + {_cleared_hard} NN-hard-reject "
                            f"cooldowns for fresh evaluation [v15.3]"
                        )
                self._prev_gex_regime = _cur_gex_regime

                # ── 2a. Sync Kelly win-rate from live trade history every cycle ─
                # Previously only updated hourly (blacklist) or every 5 min (heartbeat).
                # Now runs every cycle so PM framework uses current win-rate immediately.
                if self.trade_memory:
                    try:
                        _ts = self.trade_memory.get_stats()
                        _resolved = _ts["wins"] + _ts["losses"]
                        if _resolved >= 20:
                            _live_wr = _ts["wins"] / max(_resolved, 1)
                            # Prior lowered 0.338 → 0.30 to not over-inflate win rate
                            # during drawdown periods.
                            _blended = _live_wr * 0.70 + 0.30 * 0.30
                            self.strategy._global_win_rate = round(_blended, 4)
                    except Exception:
                        pass

                # ── 2b. Check BTCUSDT price alerts ────────────────────────────
                await self.check_price_alerts()

                # ── 2c. Refresh per-symbol blacklist before parallel scan ──────
                # Called here so the blacklist is always current before scan_and_signal
                # uses _symbol_blacklist for its fast pre-check (skips strategy eval
                # for blacklisted symbols without going through can_send_signal).
                self._refresh_symbol_blacklist()

                # ── 2d. IP ban guard — skip scan if Binance banned the IP ────
                # When banned, spawning 80 parallel scan coroutines is wasteful:
                # every coroutine calls _wait_ip_ban_if_needed, sleeps 30s, times
                # out (wait_for limit), and floods the log. Instead, sleep the main
                # loop for up to 5 minutes then retry the symbol refresh and re-check.
                if self.trader.is_ip_banned():
                    _ban_wait = self.trader.ip_ban_wait_seconds()
                    _ban_sleep = min(_ban_wait, 300.0)  # sleep up to 5 min per iteration
                    self.logger.warning(
                        f"🚫 IP ban active — skipping scan cycle, "
                        f"sleeping {_ban_sleep:.0f}s (ban expires in {_ban_wait/60:.1f} min)"
                    )
                    await asyncio.sleep(_ban_sleep)
                    continue  # re-check ban at top of loop

                # ── 3. TRUE PARALLEL: scan ALL symbols simultaneously ─────────
                symbols = list(self._active_symbols)  # snapshot to avoid mid-scan mutations

                # ── v18.13: ScanCycleMatrix pre-filter ───────────────────────
                # Build the ScanCycleMatrix once per cycle (single _gex_lock
                # acquisition for all symbols).  The numpy vectorized pre-filter
                # eliminates symbols with stale WS data (>10s), spread >0.50%,
                # or |mark-div| >200bps before they enter the 25-coroutine
                # semaphore pool — reducing wasted scan slots by ~10-20%.
                # The frozen matrix is stored on self._current_cycle_matrix so
                # downstream gate code can read it without lock contention.
                _unity_engine_scm = getattr(self, "_unity_engine", None)
                if _unity_engine_scm is not None:
                    try:
                        from SignalMaestro.scan_cycle_matrix import (
                            build_scan_cycle_matrix as _build_scm,
                        )
                        _cycle_matrix = await _build_scm(_unity_engine_scm, symbols)
                        self._current_cycle_matrix = _cycle_matrix
                        _pre_len = len(symbols)
                        if (
                            _cycle_matrix.live_symbols
                            and len(_cycle_matrix.live_symbols) < _pre_len
                        ):
                            symbols = [
                                s for s in symbols
                                if s.upper() in _cycle_matrix.live_symbols
                            ]
                            self.logger.debug(
                                f"⚡ [SCM v18.13] pre-filter: {len(symbols)}/{_pre_len} live "
                                f"| {_pre_len - len(symbols)} rejected "
                                f"(stale WS/wide spread/mark-div) "
                                f"| pass={_cycle_matrix.pass_rate:.0%}"
                            )
                    except Exception as _scm_err:
                        self.logger.debug(f"SCM build skipped: {_scm_err}")
                        self._current_cycle_matrix = None
                else:
                    self._current_cycle_matrix = None

                # ── v18.17: Batch NN pre-cache ────────────────────────────────
                # Run predict_batch_mc_from_dicts once on ALL prev-cycle signal
                # dicts before the parallel scan starts.  Results populate
                # _nn_batch_cache[symbol] = (mean_prob, std).  process_signals()
                # hits the cache first — skipping per-symbol individual NN calls
                # on cache hits (125× FLOP reduction at N=50 symbols).
                # Cache misses (new symbols, first cycle) fall through to
                # individual predict_signal_with_uncertainty as before.
                if self.nn_trainer is not None and self._prev_cycle_nn_dicts:
                    _nn_syms = [s for s in symbols if s in self._prev_cycle_nn_dicts]
                    if _nn_syms:
                        try:
                            _nn_dicts = [self._prev_cycle_nn_dicts[s] for s in _nn_syms]
                            _mean_p, _std_p = self.nn_trainer.predict_batch_mc_from_dicts(
                                _nn_dicts, n_mc=20
                            )
                            self._nn_batch_cache = {
                                sym: (float(_mean_p[i]), float(_std_p[i]))
                                for i, sym in enumerate(_nn_syms)
                            }
                            self.logger.debug(
                                f"⚡ [v18.17 BatchNN] pre-cached {len(_nn_syms)}/{len(symbols)} "
                                f"symbols (n_mc=20, 20 passes × {len(_nn_syms)} rows)"
                            )
                        except Exception as _bnn_err:
                            self.logger.debug(f"BatchNN pre-cache skipped: {_bnn_err}")
                            self._nn_batch_cache = {}
                    else:
                        self._nn_batch_cache = {}

                self.logger.info(
                    f"⚡ Cycle #{cycle_count}: parallel-scanning {len(symbols)} symbols "
                    f"(blacklist={len(self._symbol_blacklist)})..."
                )
                signals_this_cycle = await self.scan_all_parallel(symbols)

                # Update Unity Engine scan cycle counter
                _u_m = getattr(self, "_unity_metrics", None)
                if _u_m is not None:
                    _u_m.scan_cycles += 1

                cycle_elapsed = time.time() - cycle_start
                self.logger.info(
                    f"✅ Cycle #{cycle_count} complete in {cycle_elapsed:.1f}s | "
                    f"signals this cycle: {signals_this_cycle} | "
                    f"total signals: {self.signal_count}"
                )

                # ── 4. Heartbeat log every 5 minutes ─────────────────────────
                now = time.time()
                if now - last_heartbeat >= heartbeat_interval:
                    mem = self.strategy.get_market_memory_summary()
                    n_sym = len(self._active_symbols)
                    top_syms = ", ".join(
                        f"{s}:{self._symbol_signal_count.get(s, 0)}"
                        for s in sorted(
                            self._symbol_signal_count,
                            key=lambda x: self._symbol_signal_count[x],
                            reverse=True,
                        )[:5]
                    ) or "none"
                    # NN & trade memory stats
                    nn_status = ""
                    if self.nn_trainer:
                        nn_status = f" | {self.nn_trainer.status_summary()}"
                    trade_stats = ""
                    if self.trade_memory:
                        try:
                            ts = self.trade_memory.get_stats()
                            rl = self.trade_memory.get_recent_loss_rate(20)
                            trade_stats = (
                                f" | trades: {ts['total_signals']} "
                                f"(W/L={ts['wins']}/{ts['losses']} "
                                f"wr={ts['win_rate']:.1f}% "
                                f"recent_loss={rl:.1%})"
                            )
                            # Kelly win-rate is already synced every cycle (see step 2a above).
                            # No duplicate sync needed here — heartbeat reads the already-current
                            # value via trade_stats display only.
                        except Exception:
                            pass
                    self.logger.info(
                        f"💓 Heartbeat — signals: {self.signal_count} | "
                        f"markets: {n_sym} | cycles: {cycle_count} | "
                        f"graph nodes: {mem.get('nodes', 0)} | "
                        f"top signals: [{top_syms}] | "
                        f"session: {self.strategy._current_session}"
                        f"{trade_stats}{nn_status}"
                    )
                    last_heartbeat = now

                # ── 5. Telegram polling ─────────────────────────────────────
                # Primary polling is handled by _tg_dedicated_poll_loop() which
                # runs as an independent asyncio task (long-poll, <1s latency).
                # The fallback short-poll below catches any updates missed during
                # the scan cycle's execution window (non-blocking: timeout=0).
                try:
                    await self._poll_telegram_updates()
                except Exception as poll_err:
                    self.logger.debug(f"Polling error: {poll_err}")

                # ── 6. Sleep between cycles ───────────────────────────────────
                sleep_secs = random.randint(cycle_sleep_min, cycle_sleep_max)
                self.logger.debug(f"💤 Sleeping {sleep_secs}s before next cycle...")
                await asyncio.sleep(sleep_secs)

            except asyncio.CancelledError:
                self.logger.info("🔄 Scanner cancelled")
                raise
            except KeyboardInterrupt:
                self.logger.info("🛑 Scanner stopped by user")
                raise
            except Exception as e:
                self.logger.error(f"❌ Scanner loop error: {e}")
                await asyncio.sleep(30)  # Brief recovery pause before retry

    # ─────────────────────────────────────────
    # Telegram Polling (minimal get_updates)
    # ─────────────────────────────────────────

    async def _clear_webhook(self) -> None:
        """
        Clear any active Telegram webhook so getUpdates long-polling can work.

        ROOT CAUSE FIX: If a webhook was ever set (e.g. by a previous deploy or
        testing), getUpdates returns NOTHING — Telegram routes all updates to the
        webhook URL instead.  This silently breaks all polling-based update receipt,
        causing inline buttons to appear frozen forever (no callback_query delivered).

        Must be called on startup before the dedicated poll loop begins.
        drop_pending_updates=False preserves queued updates so users who pressed
        buttons while the bot was offline still get their callbacks processed.
        """
        try:
            session = await self._get_tg_session()
            url = f"{self.base_url}/deleteWebhook"
            async with session.post(
                url,
                json={"drop_pending_updates": False},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                d = await r.json()
                if d.get("ok"):
                    self.logger.info("🗑️ [TGPoll] Webhook cleared — long-poll mode active")
                else:
                    self.logger.debug(f"[TGPoll] deleteWebhook: {d}")
        except Exception as e:
            self.logger.debug(f"[TGPoll] _clear_webhook: {e}")

    async def _drain_pending_updates(self):
        """
        Acknowledge all Telegram updates that arrived before this bot session started.

        Without this, every restart replays the entire unprocessed update queue
        from update_id=1 — commands typed by users while the bot was offline would
        be re-executed immediately on startup (e.g. /force_signal, /status firing
        multiple times).

        Strategy: request offset=-1 (Telegram returns the single most-recent pending
        update), then advance _poll_offset to its update_id.  The next normal poll
        sends offset=_poll_offset+1, which acknowledges everything up to that point
        and only delivers genuinely new updates.
        """
        try:
            url     = f"{self.base_url}/getUpdates"
            params  = {
                "offset":          -1,
                "timeout":         0,
                "limit":           1,
                "allowed_updates": ["message", "callback_query", "channel_post"],
            }
            session = await self._get_tg_session()
            async with session.get(
                url, params=params,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as response:
                if response.status != 200:
                    return
                data = await response.json()
                updates = data.get("result", [])
                if updates:
                    last_id = max(u.get("update_id", 0) for u in updates)
                    self._poll_offset = last_id
                    self.logger.info(
                        f"📬 Drained pending Telegram updates — "
                        f"offset advanced to {last_id} "
                        f"({len(updates)} update(s) skipped)"
                    )
        except Exception as e:
            self.logger.debug(f"_drain_pending_updates: {e}")

    async def _tg_dedicated_poll_loop(self) -> None:
        """
        Dedicated high-frequency Telegram update poller — runs as an independent task.

        ROOT CAUSE FIX (v15.4): Previously _poll_telegram_updates() was called only
        inside the main scan cycle which sleeps 30-60 seconds between iterations.
        Telegram's answerCallbackQuery has a hard 30-second deadline — any button
        press during the sleep window ALWAYS timed out, leaving users with a frozen
        spinner.  This dedicated long-poll task processes callbacks within <1 second
        of the button press, well inside the 30-second deadline.

        Design:
          • Long-poll (timeout=25s): Telegram holds the request open for up to 25s
            and returns immediately when an update arrives — zero busy-wait.
          • allowed_updates: only requests message + callback_query + channel_post,
            reducing irrelevant update noise.
          • Single asyncio task: no thread-safety concerns; shares _poll_offset
            with _poll_telegram_updates — the dedicated loop is the sole poller
            (scan-cycle fallback poll was removed to prevent double-processing).
          • Auto-restarted by @watched_task in start_unity_engine.py.
        """
        await asyncio.sleep(2)  # brief startup delay — let init complete first
        await self._clear_webhook()
        self.logger.info(
            "📬 [TGPoll] Dedicated long-poll task active "
            "(timeout=25s, allowed=message+callback_query — inline buttons responsive)"
        )
        _ALLOWED = ["message", "callback_query", "channel_post", "edited_message"]
        while True:
            try:
                url = f"{self.base_url}/getUpdates"
                params = {
                    "offset":          self._poll_offset + 1,
                    "timeout":         25,   # long-poll window
                    "limit":           100,
                    "allowed_updates": _ALLOWED,
                }
                session = await self._get_tg_session()
                async with session.get(
                    url, params=params,
                    timeout=aiohttp.ClientTimeout(total=32),  # slightly > long-poll timeout
                ) as response:
                    if response.status == 429:
                        await asyncio.sleep(5)
                        continue
                    if response.status != 200:
                        await asyncio.sleep(1)
                        continue
                    data = await response.json()
                    if not data.get("ok"):
                        await asyncio.sleep(1)
                        continue
                    for update in data.get("result", []):
                        uid = update.get("update_id", 0)
                        if uid > self._poll_offset:
                            self._poll_offset = uid
                        # TradingInterface: callback_query + /start + wizard
                        _ti = getattr(self, "trading_interface", None)
                        if _ti is not None:
                            try:
                                if await _ti.process_raw_update(update):
                                    continue
                            except Exception as _te:
                                self.logger.debug(f"[TGPoll] TI dispatch: {_te}")
                        # Slash commands
                        msg = update.get("message") or update.get("channel_post") or {}
                        if not msg:
                            continue
                        text    = (msg.get("text") or "").strip()
                        chat_id = str(msg.get("chat", {}).get("id", ""))
                        if not text or not chat_id or not text.startswith("/"):
                            continue
                        parts   = text.split()
                        command = parts[0].lower()
                        if "@" in command:
                            command = command.split("@")[0]
                        args = parts[1:]
                        if command in self.commands:
                            try:
                                await self.handle_webhook_command(command, chat_id, args)
                            except Exception as _ce:
                                self.logger.debug(f"[TGPoll] cmd {command}: {_ce}")
            except asyncio.CancelledError:
                self.logger.info("[TGPoll] Dedicated poll loop cancelled")
                raise
            except asyncio.TimeoutError:
                pass   # long-poll expired naturally — immediately retry
            except Exception as e:
                self.logger.debug(f"[TGPoll] poll error: {e}")
                await asyncio.sleep(1)

    async def _poll_telegram_updates(self):
        """
        Fallback Telegram poll — called once per scan cycle as a safety net.
        The _tg_dedicated_poll_loop() task is the primary poller (runs every ~25s
        via long-poll).  This fallback uses a short timeout=0 check so it never
        delays the scan cycle.  Uses self._poll_offset (shared with dedicated task).
        """
        try:
            url    = f"{self.base_url}/getUpdates"
            params = {
                "offset":          self._poll_offset + 1,
                "timeout":         0,   # non-blocking — dedicated task handles long-poll
                "limit":           20,
                "allowed_updates": ["message", "callback_query", "channel_post"],
            }

            session = await self._get_tg_session()
            async with session.get(
                url, params=params,
                timeout=aiohttp.ClientTimeout(total=8)
            ) as response:
                if response.status == 429:
                    # Telegram rate-limited the polling — back off silently
                    await asyncio.sleep(5)
                    return
                if response.status != 200:
                    return

                data = await response.json()
                if not data.get("ok"):
                    return

                updates = data.get("result", [])
                for update in updates:
                    update_id = update.get("update_id", 0)
                    # Always advance offset so we never re-process old updates
                    if update_id > self._poll_offset:
                        self._poll_offset = update_id

                    # ── TradingInterface inline-keyboard menu — handles
                    #    callback_query (button presses), /start, and
                    #    free-text wizard input.  Returns True if it consumed
                    #    the update so the slash-command path is skipped.
                    _ti = getattr(self, "trading_interface", None)
                    if _ti is not None:
                        try:
                            if await _ti.process_raw_update(update):
                                continue
                        except Exception as menu_err:
                            self.logger.debug(f"TradingInterface raw dispatch error: {menu_err}")

                    # Handle both direct messages and channel_post
                    message = update.get("message") or update.get("channel_post") or {}
                    if not message:
                        continue

                    text    = (message.get("text") or "").strip()
                    chat_id = str(message.get("chat", {}).get("id", ""))

                    if not text or not chat_id:
                        continue

                    # Only process /commands
                    if not text.startswith("/"):
                        continue

                    parts   = text.split()
                    command = parts[0].lower()
                    args    = parts[1:] if len(parts) > 1 else []

                    # Strip @bot_username suffix (e.g. /status@TradeTacticsML_bot)
                    if "@" in command:
                        command = command.split("@")[0]

                    if command in self.commands:
                        try:
                            await self.handle_webhook_command(command, chat_id, args)
                        except Exception as cmd_err:
                            self.logger.debug(f"Command error {command}: {cmd_err}")

        except asyncio.TimeoutError:
            pass  # Normal — long-poll timed out
        except Exception as e:
            self.logger.debug(f"Poll error: {e}")

    async def handle_webhook_command(self, command: str, chat_id: str,
                                     args: Optional[List] = None) -> bool:
        """Route command to handler via mock update/context"""
        try:
            if command not in self.commands:
                await self.send_message(chat_id, "❓ Unknown command. Type /help")
                return False

            class _Chat:
                def __init__(self, cid): self.id = int(cid) if str(cid).lstrip("-").isdigit() else cid
            class _Msg:
                def __init__(self, cid): self.chat = _Chat(cid)
            class _Update:
                def __init__(self, cid): self.effective_chat = _Chat(cid); self.message = _Msg(cid)
            class _Context:
                def __init__(self, a): self.args = a or []

            await self.commands[command](_Update(chat_id), _Context(args or []))
            return True

        except Exception as e:
            self.logger.error(f"Command execution error {command}: {e}")
            await self.send_message(chat_id, f"❌ Error executing `{command}`")
            return False

    # ─────────────────────────────────────────
    # Commands
    # ─────────────────────────────────────────

    async def cmd_start(self, update, context):
        chat_id = str(update.effective_chat.id)
        msg = """🐟 **BTCUSDT MiroFish Swarm Bot**

Welcome! This bot delivers high-confidence USDM Futures signals powered by the **MiroFish multi-agent swarm intelligence** strategy scanning ALL active Binance USDM Perpetual markets.

**🚀 How It Works:**
• 10 specialized AI agents analyze markets independently
• Each agent has a unique market perspective
• Swarm consensus determines signal direction
• Only signals with ≥75% agent agreement are sent

**📋 Key Commands:**
• `/price` — Current BTCUSDT price
• `/signal` — Manual signal (admin)
• `/scan` — Trigger immediate scan
• `/swarm` — View swarm agent status
• `/backtest` — Run strategy backtest
• `/dashboard` — Market overview
• `/help` — Full command list

**📡 Signals Channel:** @ichimokutradingsignal
**⚡ Strategy:** MiroFish Swarm v5.0 (ALL USDM Perp Futures)"""
        await self.send_message(chat_id, msg)
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_help(self, update, context):
        chat_id = str(update.effective_chat.id)
        msg = """📖 **BTCUSDT MiroFish Swarm Bot — Commands**

**📊 Market Data:**
• `/price` — Current BTC price & 24h stats
• `/market [symbol]` — Market overview
• `/volume` — Volume analysis
• `/funding` — Funding rate
• `/oi` — Open interest
• `/dashboard` — Complete market dashboard

**🤖 Trading Signals:**
• `/scan` — Trigger manual swarm scan
• `/signal [BUY/SELL] [entry] [sl] [tp]` — Manual signal (admin)
• `/swarm` — Swarm agent consensus status

**📈 Analysis:**
• `/dynamic_sltp [LONG/SHORT]` — Smart SL/TP levels
• `/dynamic_sl [LONG/SHORT]` — Dynamic leveraging SL
• `/market_intel` — Market intelligence report
• `/insider` — Insider activity detection
• `/orderflow` — Order flow analysis
• `/sentiment` — Market sentiment
• `/news` — Market context & news

**💼 Account:**
• `/balance` — Futures wallet balance
• `/position` — Open BTCUSDT positions
• `/leverage [BTCUSDT] [1-125]` — Set/get leverage
• `/risk [size] [pct]` — Risk calculator
• `/history` — Trade history

**⚙️ Strategy:**
• `/backtest [days] [timeframe]` — Backtest MiroFish strategy
• `/optimize` — Parameter optimization
• `/settings` — Bot settings
• `/stats` — Bot statistics

**🔔 Alerts:**
• `/alerts add [price]` — Set price alert
• `/alerts remove [index]` — Remove alert
• `/alerts list` — View active alerts

**👑 Admin:**
• `/admin` — Admin panel (authorized users only)"""
        await self.send_message(chat_id, msg)
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_status(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            cur_price = await self.trader.get_current_price()
            market_st = await self.trader.get_market_status()
            mem       = self.strategy.get_market_memory_summary()

            uptime    = str(datetime.now() - self.bot_start_time).split(".")[0]

            # Global next-signal wait time (from last channel send, not per-symbol)
            _now_ts = datetime.now()
            if self.signal_timestamps:
                _gap_elapsed = (_now_ts - self.signal_timestamps[-1]).total_seconds()
                _global_wait = max(0, int(self._GLOBAL_MIN_GAP_SECONDS - _gap_elapsed))
            else:
                _global_wait = 0

            # Hourly signal count
            _cutoff_1h = _now_ts - timedelta(hours=1)
            _sigs_this_hour = sum(1 for ts in self.signal_timestamps if ts > _cutoff_1h)

            price_str = f"${cur_price:,.2f}" if cur_price else "N/A"
            status_str = "🟢 TRADING" if market_st.get("is_trading") else "🔴 " + market_st.get("status", "UNKNOWN")

            msg = f"""📊 **MiroFish Swarm v5.0 — Bot Status**

**🤖 Bot Health:**
• **Status:** 🟢 Running
• **Strategy:** MiroFish Swarm Intelligence v5.0
• **Uptime:** `{uptime}`
• **Markets Scanned:** `{len(self._active_symbols)} USDM Perpetuals`
• **Signals Sent (total):** `{self.signal_count}`
• **Signals This Hour:** `{_sigs_this_hour}/{self._MAX_SIGNALS_PER_HOUR}`
• **Last Signal:** `{self.last_signal_time.strftime('%H:%M:%S') if self.last_signal_time else 'None'}`
• **Global Gap Wait:** `{_global_wait}s`

**💰 Reference Market:**
• **BTCUSDT Price:** `{price_str}`
• **Market Status:** {status_str}
• **Volume 24h:** `${market_st.get('quote_vol_24h', 0):,.0f}`

**🐟 Graph Memory:**
• **Symbol Graphs:** `{mem.get('tracked_symbols', 0)} active`
• **Nodes:** `{mem.get('nodes', 0)}`
• **Active Edges:** `{mem.get('active_edges', 0)}`
• **Trend State:** `{mem.get('trend_state') or 'building...'}`

**⚡ Rate Limits:**
• Per-symbol cooldown: `{self.min_signal_interval_minutes:.0f} min`
• Global min gap: `{self._GLOBAL_MIN_GAP_SECONDS:.0f}s`
• Confidence gate: `{self._ai_threshold_pct + self._adaptive_conf_boost:.0f}%`
**📡 Channel:** `{self.channel_id or 'Not configured'}`"""

            await self.send_message(chat_id, msg)
        except Exception as e:
            self.logger.error(f"cmd_status error: {e}")
            await self.send_message(chat_id, f"❌ Status error: {e}")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_swarm_status(self, update, context):
        """Show MiroFish swarm agent status, graph memory, and session state"""
        chat_id = str(update.effective_chat.id)
        try:
            mem = self.strategy.get_market_memory_summary()

            agents = {
                "TrendAgent":           "📈 EMA 9/21 + EMA200 + TrendState graph node    (22%)",
                "MomentumAgent":        "⚡ RSI + MACD + IndicatorState node              (20%)",
                "VolumeAgent":          "📊 OBV + surge + Catalyst node on 2× spike      (18%)",
                "VolatilityAgent":      "🌊 BB + ATR + PriceLevel BB_Upper/Lower nodes   (15%)",
                "OrderFlowAgent":       "🕯️ Candle patterns + Pattern graph nodes         (15%)",
                "SentimentAgent":       "😱 Price deviation + vol contraction regime      ( 5%)",
                "FundingFlowAgent":     "💹 VWAP dev + OI proxy + squeeze detect          ( 5%)",
                "PivotSRAgent":         "🎯 Pivot points + Volume POC + S/R proximity     ( 8%)",
                "FLOOPAgent":           "🔄 Fast-Loop momentum oscillator + regime detect  (10%)",
                "AIOrchestrationAgent": "🤖 Claude claude-sonnet-4-6 ReACT Reason→Act→Reflect ( 5%)",
            }

            agent_lines = "\n".join(
                f"• **{name}**\n  _{desc}_"
                for name, desc in agents.items()
            )

            from SignalMaestro.mirofish_swarm_strategy import get_current_market_session
            session, activity = get_current_market_session()

            # Pull live consensus gate from strategy instance (authoritative source)
            _min_consensus_pct = int(getattr(self.strategy, "min_swarm_consensus", 0.75) * 100)
            _min_strength      = int(getattr(self.strategy, "min_signal_strength", 62))
            _tracked_syms      = mem.get("tracked_symbols", 0)

            # Neural network status
            _nn_status = "warming up"
            try:
                if hasattr(self, "nn_trainer") and self.nn_trainer is not None:
                    _nn_status = self.nn_trainer.status_summary()
            except Exception:
                pass

            msg = f"""🐟 **MiroFish Swarm v5.0 — 10-Agent AI Orchestration**
Strategy: github.com/666ghj/MiroFish

**🌐 Market Session:** `{session}` (activity={activity:.2f}×)
**📡 Tracking:** `{_tracked_syms}` symbol graphs active

**🤖 Active Agents (10):**
{agent_lines}

**🗄️ Graph-State Memory:**
• **Nodes:** `{mem.get('nodes', 0)}` (market entities)
• **Edges:** `{mem.get('edges', 0)}` (relationships)
• **Active Edges:** `{mem.get('active_edges', 0)}`
• **Trend State:** `{mem.get('trend_state') or 'updating...'}`
• **Recent Signals:** `{mem.get('recent_signals', 0)}`

**⚙️ Signal Gates (production):**
• Min swarm consensus: `{_min_consensus_pct}%`
• Pre-boost strength gate: `{_min_strength}%`
• Final confidence gate: `{self._ai_threshold_pct + self._adaptive_conf_boost:.0f}%` (base {self._ai_threshold_pct:.0f}% + streak boost {self._adaptive_conf_boost:.0f}%)
• Min active agents for quorum: `{getattr(self.strategy, 'min_active_agents', 5)}`
• Min R:R ratio: `{getattr(self.strategy, 'min_rr_ratio', 1.55):.2f}`
• Session-aware agent weights: ✅ Active
• EMA200 trend alignment filter: ✅ Active
• HTF 1H counter-trend rejection: ✅ Active

**🧠 Self-Learning Neural Network:**
• `{_nn_status}`

**🏆 MiroFish v5.0 Architecture:**
• 10-Agent Swarm with Kelly Criterion dynamic leverage
• Claude claude-sonnet-4-6 AI orchestration (8-model cascade)
• Market Ontology (7 entity types + 9 edge types)
• InsightForge sub-query decomposition
• ReACT: Reason → Act → Reflect (AI agent)
• IRONS AI Scorer (25 indicators across 4 categories)
• 42-feature neural network self-learning filter
• Risk debate: Aggressive × Conservative × Neutral

*100% based on github.com/666ghj/MiroFish | MiroFish Swarm v5.0*"""

            await self.send_message(chat_id, msg)
        except Exception as e:
            await self.send_message(chat_id, f"❌ Swarm status error: {e}")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_price(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            price  = await self.trader.get_current_price()
            ticker = await self.trader.get_24hr_ticker_stats("BTCUSDT")

            if price and ticker:
                change_pct = float(ticker.get("priceChangePercent", 0))
                high_24h   = float(ticker.get("highPrice", 0))
                low_24h    = float(ticker.get("lowPrice", 0))
                volume     = float(ticker.get("volume", 0))
                quote_vol  = float(ticker.get("quoteVolume", 0))
                emoji      = "🟢" if change_pct >= 0 else "🔴"

                msg = f"""💰 **BTCUSDT.PERP Price:**

• **Current Price:** `${price:,.2f}`
• **24h Change:** {emoji} `{change_pct:+.2f}%`
• **24h High:** `${high_24h:,.2f}`
• **24h Low:** `${low_24h:,.2f}`
• **24h Volume (BTC):** `{volume:,.3f}`
• **24h Volume (USDT):** `${quote_vol:,.0f}`

**📊 Market:** Binance USDM Futures
**📈 Contract:** BTCUSDT Perpetual
**⏰ Updated:** `{datetime.now().strftime('%H:%M:%S UTC')}`"""
            elif price:
                msg = f"💰 **BTCUSDT Price:** `${price:,.2f}`"
            else:
                msg = "❌ Could not retrieve BTCUSDT price."

            await self.send_message(chat_id, msg)
        except Exception as e:
            self.logger.error(f"cmd_price error: {e}")
            await self.send_message(chat_id, "❌ Error fetching price.")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_balance(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            balance = await self.trader.get_account_balance()
            if balance:
                pnl_emoji = "🟢" if balance.get("total_unrealized_pnl", 0) >= 0 else "🔴"
                msg = f"""💰 **Account Balance (BTCUSDT Futures):**

• **Total Wallet:** `{balance.get('total_wallet_balance', 0):.2f} USDT`
• **Available:** `{balance.get('available_balance', 0):.2f} USDT`
• **Cross Wallet:** `{balance.get('cross_wallet_balance', 0):.2f} USDT`
• **Unrealized PNL:** {pnl_emoji} `{balance.get('total_unrealized_pnl', 0):.2f} USDT`

**📊 Account Type:** USDM Futures
**⚡ Updated:** `{datetime.now().strftime('%H:%M:%S UTC')}`"""
            else:
                msg = "❌ Could not retrieve account balance. Check API permissions."
            await self.send_message(chat_id, msg)
        except Exception as e:
            self.logger.error(f"cmd_balance error: {e}")
            await self.send_message(chat_id, "❌ Error fetching balance.")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_position(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            positions = await self.trader.get_positions("BTCUSDT")
            if positions:
                msg = "📊 **Open Positions (BTCUSDT.PERP):**\n\n"
                for pos in positions:
                    amt     = float(pos.get("positionAmt", 0))
                    entry   = float(pos.get("entryPrice", 0))
                    mark    = float(pos.get("markPrice", 0))
                    pnl     = float(pos.get("unRealizedProfit", 0))
                    pct     = float(pos.get("percentage", 0))
                    lev     = pos.get("leverage", "1")
                    side    = "LONG" if amt > 0 else "SHORT" if amt < 0 else "FLAT"
                    se      = "🟢" if amt > 0 else "🔴"
                    pe      = "🟢" if pnl >= 0 else "🔴"
                    msg += f"""{se} **{pos.get('symbol', 'BTCUSDT')}**
• **Side:** `{side}`
• **Size:** `{abs(amt):.4f} BTC`
• **Entry:** `${entry:,.2f}`
• **Mark:** `${mark:,.2f}`
• **PNL:** {pe} `{pnl:+.2f} USDT ({pct:+.2f}%)`
• **Leverage:** `{lev}x`

"""
            else:
                msg = "ℹ️ No open BTCUSDT positions."
            await self.send_message(chat_id, msg)
        except Exception as e:
            self.logger.error(f"cmd_position error: {e}")
            await self.send_message(chat_id, "❌ Error fetching positions.")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_scan(self, update, context):
        chat_id = str(update.effective_chat.id)
        symbols = list(self._active_symbols)
        n = len(symbols)
        await self.send_message(
            chat_id,
            f"🐟 Triggering MiroFish parallel swarm scan across {n} USDM markets..."
        )
        try:
            signals_sent = await self.scan_all_parallel(symbols)
        except Exception as _scan_err:
            self.logger.error(f"cmd_scan parallel scan error: {_scan_err}")
            signals_sent = 0
        if signals_sent > 0:
            await self.send_message(
                chat_id,
                f"✅ Swarm scan complete. {signals_sent} signal(s) sent across {n} markets."
            )
        else:
            await self.send_message(
                chat_id,
                f"ℹ️ Scan complete ({n} markets). No qualifying swarm signals at this time "
                f"(consensus <75%, confidence below {self._ai_threshold_pct + self._adaptive_conf_boost:.0f}%, or rate-limited)."
            )
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_settings(self, update, context):
        chat_id = str(update.effective_chat.id)
        _eff_thresh = self._ai_threshold_pct + self._adaptive_conf_boost
        _boost_str  = (
            f" (+{self._adaptive_conf_boost:.0f}% streak boost)"
            if self._adaptive_conf_boost > 0 else ""
        )
        msg = (
            f"⚙️ **Bot Settings:**\n\n"
            f"• **Markets:** `ALL USDM Perpetuals ({len(self._active_symbols)} active)`\n"
            f"• **Strategy:** `MiroFish Swarm Intelligence v5.0`\n"
            f"• **Min Signal Interval:** `{self.min_signal_interval_minutes:.0f} min`\n"
            f"• **Max Signals/Hour:** `{self._MAX_SIGNALS_PER_HOUR}`\n"
            f"• **Global Min Gap:** `{self._GLOBAL_MIN_GAP_SECONDS:.0f}s`\n"
            f"• **AI Threshold:** `{_eff_thresh:.0f}%{_boost_str}`\n"
            f"• **Scan Parallelism:** `{self._scan_limit} concurrent`\n"
            f"• **Target Channel:** `{self.channel_id}`\n"
            f"• **Admin Notifications:** `{'Enabled' if self.admin_chat_id else 'Disabled'}`\n\n"
            "*Settings are configured via environment variables.*"
        )
        await self.send_message(chat_id, msg)
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_market(self, update, context):
        chat_id = str(update.effective_chat.id)
        symbol  = context.args[0].upper() if context.args else "BTCUSDT"
        try:
            ticker = await self.trader.get_24hr_ticker_stats(symbol)
            if ticker:
                price      = float(ticker.get("lastPrice", 0))
                change     = float(ticker.get("priceChange", 0))
                change_pct = float(ticker.get("priceChangePercent", 0))
                high_24h   = float(ticker.get("highPrice", 0))
                low_24h    = float(ticker.get("lowPrice", 0))
                volume     = float(ticker.get("volume", 0))
                quote_vol  = float(ticker.get("quoteVolume", 0))
                open_price = float(ticker.get("openPrice", 0))
                emoji      = "🟢" if change >= 0 else "🔴"

                msg = f"""📈 **Market Overview — {symbol}:**

**💰 Price:**
• **Current:** `${price:,.2f}`
• **24h Change:** {emoji} `${change:+,.2f} ({change_pct:+.2f}%)`
• **24h High:** `${high_24h:,.2f}`
• **24h Low:** `${low_24h:,.2f}`
• **24h Open:** `${open_price:,.2f}`
• **Range:** `${high_24h - low_24h:,.2f}`

**📊 Volume:**
• **BTC Volume:** `{volume:,.3f}`
• **USDT Volume:** `${quote_vol:,.0f}`

**📋 Contract:** Perpetual Futures / USDT-M / Binance
**⏰ Updated:** `{datetime.now().strftime('%H:%M:%S UTC')}`"""
            else:
                msg = f"❌ Could not retrieve market data for {symbol}."
            await self.send_message(chat_id, msg)
        except Exception as e:
            self.logger.error(f"cmd_market error: {e}")
            await self.send_message(chat_id, f"❌ Error fetching market data for {symbol}.")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_stats(self, update, context):
        chat_id = str(update.effective_chat.id)
        total_cmds = sum(self.commands_used.values())
        mem        = self.strategy.get_market_memory_summary()
        msg = (
            f"📊 **Bot Statistics:**\n\n"
            f"• **Signals Sent:** `{self.signal_count}`\n"
            f"• **Commands Used:** `{total_cmds}`\n"
            f"• **Uptime:** `{str(datetime.now() - self.bot_start_time).split('.')[0]}`\n"
            f"• **Last Signal:** `{self.last_signal_time.strftime('%Y-%m-%d %H:%M') if self.last_signal_time else 'Never'}`\n"
            f"• **Graph Nodes:** `{mem.get('nodes', 0)}`\n"
            f"• **Graph Edges (active):** `{mem.get('active_edges', 0)}`\n"
            f"• **Trend State:** `{mem.get('trend_state') or 'unknown'}`\n\n"
            "**Top Commands:**\n"
        )
        for cmd, count in sorted(self.commands_used.items(), key=lambda x: x[1], reverse=True)[:10]:
            msg += f"• `{cmd}`: {count}\n"
        await self.send_message(chat_id, msg)
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_leverage(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            if context.args and context.args[0].upper() == "AUTO":
                cur_price = await self.trader.get_current_price()
                if not cur_price:
                    await self.send_message(chat_id, "❌ Could not fetch price.")
                    return
                # Simple ATR-based leverage recommendation for BTC
                klines = await self.trader.get_klines("1h", limit=24)
                if klines and len(klines) >= 14:
                    closes = [float(k[4]) for k in klines]
                    atr    = sum(abs(closes[i] - closes[i-1]) for i in range(1, len(closes))) / (len(closes) - 1)
                    atr_pct = atr / closes[-1] * 100
                    # Lower leverage for high ATR (volatile)
                    if atr_pct > 3:
                        rec_lev = 3
                    elif atr_pct > 2:
                        rec_lev = 5
                    elif atr_pct > 1:
                        rec_lev = 8
                    else:
                        rec_lev = 10
                    await self.send_message(chat_id, f"""🎯 **Dynamic Leverage for BTCUSDT:**

• **Recommended:** `{rec_lev}x`
• **ATR 24h:** `${atr:,.2f}` ({atr_pct:.2f}% of price)
• **Rationale:** {'High volatility — low leverage' if atr_pct > 2 else 'Normal volatility — moderate leverage'}

Use `/leverage BTCUSDT {rec_lev}` to apply.""")
                else:
                    await self.send_message(chat_id, "❌ Insufficient data for leverage calculation.")
                return

            if len(context.args) >= 2 and context.args[0].upper() == "BTCUSDT":
                try:
                    lev = int(context.args[1])
                    if 1 <= lev <= 125:
                        success = await self.trader.change_leverage("BTCUSDT", lev)
                        if success:
                            await self.send_message(chat_id, f"✅ **Leverage set to {lev}x for BTCUSDT**\n\n💡 Tip: Use `/leverage AUTO` for dynamic recommendation")
                        else:
                            await self.send_message(chat_id, "❌ Failed to set leverage. Check account status.")
                    else:
                        await self.send_message(chat_id, "❌ BTCUSDT leverage must be 1x–125x.")
                except ValueError:
                    await self.send_message(chat_id, "❌ Invalid leverage. Provide a number.")
            else:
                cur_lev = await self.trader.get_leverage("BTCUSDT")
                if cur_lev:
                    await self.send_message(chat_id, f"""⚙️ **BTCUSDT Leverage:**

• **Current:** `{cur_lev}x`
• **Max Allowed:** `125x`

**Usage:** `/leverage BTCUSDT <1-125>`
**Auto:** `/leverage AUTO`""")
                else:
                    await self.send_message(chat_id, "❌ Could not retrieve leverage.")
        except Exception as e:
            self.logger.error(f"cmd_leverage error: {e}")
            await self.send_message(chat_id, f"❌ Leverage error: {e}")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_risk(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            price = await self.trader.get_current_price()
            if not price:
                await self.send_message(chat_id, "❌ Could not fetch price.")
                return

            account_size   = float(context.args[0]) if context.args else 1000.0
            risk_pct       = float(context.args[1]) if len(context.args) >= 2 else 1.5
            risk_amount    = account_size * (risk_pct / 100)
            sl_levels      = [0.5, 1.0, 1.5, 2.0, 3.0]

            msg = f"""🎯 **Risk Calculator — BTCUSDT**

💰 **Account:** ${account_size:,.2f}
📊 **Risk:** {risk_pct}% = ${risk_amount:,.2f}
💲 **Current BTC Price:** ${price:,.2f}

**Position Sizes by SL%:**"""
            for sl_pct in sl_levels:
                sl_price  = price * (1 - sl_pct / 100)
                sl_dist   = price - sl_price
                pos_size  = risk_amount / sl_dist if sl_dist > 0 else 0
                pos_value = pos_size * price
                msg += f"\n• **{sl_pct}% SL** → `{pos_size:.4f} BTC` (${pos_value:,.0f})"

            msg += f"""

**⚖️ Leverage Guidelines:**
• Conservative: `3-5x` (BTC high volatility)
• Moderate: `5-10x`
• Aggressive: `10-20x` (experienced only)

**⚠️ Rule:** Never risk more than 1-2% per trade
**Usage:** `/risk [account] [risk_pct]`
**Example:** `/risk 5000 1`"""

            await self.send_message(chat_id, msg)
        except (ValueError, IndexError):
            await self.send_message(chat_id, "❌ Usage: `/risk [account_size] [risk_pct]`\nExample: `/risk 1000 1.5`")
        except Exception as e:
            self.logger.error(f"cmd_risk error: {e}")
            await self.send_message(chat_id, f"❌ Risk calculation error: {e}")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_signal(self, update, context):
        """Manual signal (admin only)"""
        chat_id = str(update.effective_chat.id)
        admin_ids = [1548826223]

        try:
            if int(chat_id) not in admin_ids:
                await self.send_message(chat_id, "❌ **Access Denied** — Admin only.")
                return
        except ValueError:
            await self.send_message(chat_id, "❌ **Access Denied**")
            return

        try:
            if not context.args or len(context.args) < 3:
                await self.send_message(chat_id, """🚨 **Manual Signal**

**Usage:** `/signal [BUY/SELL] [entry] [sl] [tp]`
**Example:** `/signal BUY 84500 83200 86000`""")
                return

            action = context.args[0].upper()
            if action not in ("BUY", "SELL"):
                await self.send_message(chat_id, "❌ Direction must be BUY or SELL.")
                return

            entry = float(context.args[1])
            sl    = float(context.args[2])
            tp    = float(context.args[3]) if len(context.args) >= 4 else (
                entry * 1.015 if action == "BUY" else entry * 0.985
            )

            if action == "BUY":
                if sl >= entry or tp <= entry:
                    await self.send_message(chat_id, "❌ BUY: SL must be below entry, TP above.")
                    return
                rr = (tp - entry) / (entry - sl)
            else:
                if sl <= entry or tp >= entry:
                    await self.send_message(chat_id, "❌ SELL: SL must be above entry, TP below.")
                    return
                rr = (entry - tp) / (sl - entry)

            signal = SwarmSignal(
                symbol="BTCUSDT",
                action=action,
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                signal_strength=88.0,
                confidence=92.0,
                risk_reward_ratio=rr,
                atr_value=abs(entry - sl) * 0.5,
                timestamp=datetime.now(),
                timeframe="manual",
                leverage=10,
                swarm_consensus=1.0,
                agent_votes={"Manual": action},
                ai_narrative="Manually issued admin signal",
            )

            success = await self.send_signal_to_channel(signal)
            if success:
                await self.send_message(chat_id, f"✅ Manual signal sent: {action} BTCUSDT @ ${entry:,.2f}")
            else:
                await self.send_message(chat_id, "❌ Failed to send signal.")

        except (ValueError, IndexError):
            await self.send_message(chat_id, "❌ Invalid parameters. Use: `/signal BUY 84500 83200 86000`")
        except Exception as e:
            self.logger.error(f"cmd_signal error: {e}")
            await self.send_message(chat_id, f"❌ Signal error: {e}")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_history(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            trades = await self.trader.get_trade_history("BTCUSDT", limit=10)
            if trades:
                msg = "📜 **Recent Trade History (BTCUSDT.PERP):**\n\n"
                total_pnl = 0
                for i, t in enumerate(trades[:10], 1):
                    side    = t.get("side", "?")
                    price   = float(t.get("price", 0))
                    qty     = float(t.get("qty", 0))
                    qval    = float(t.get("quoteQty", 0))
                    ts_ms   = int(t.get("time", 0))
                    comm    = float(t.get("commission", 0))
                    t_time  = datetime.fromtimestamp(ts_ms / 1000).strftime("%m/%d %H:%M")
                    pnl     = float(t.get("realizedPnl", 0))
                    se      = "🟢" if side == "BUY" else "🔴"
                    pe      = "🟢" if pnl >= 0 else "🔴"
                    total_pnl += pnl
                    msg += f"""{se} **#{i}** {side} @ ${price:,.2f}
• **Qty:** {qty:.4f} | **Value:** ${qval:,.2f}
• {pe} **Realized PNL:** ${pnl:+.2f} | **Fee:** ${comm:.4f}
• **Time:** {t_time}

"""
                pe  = "🟢" if total_pnl >= 0 else "🔴"
                msg += f"**📊 Total Realized PNL:** {pe} `${total_pnl:+.2f}`"
            else:
                msg = f"""📜 **Trade History (BTCUSDT)**

🤖 **Bot Activity:**
• **Signals Sent:** {self.signal_count}
• **Last Signal:** {self.last_signal_time.strftime('%Y-%m-%d %H:%M') if self.last_signal_time else 'Never'}
• **Uptime:** {str(datetime.now() - self.bot_start_time).split('.')[0]}

💡 Use `/position` for open positions."""
            await self.send_message(chat_id, msg)
        except Exception as e:
            self.logger.error(f"cmd_history error: {e}")
            await self.send_message(chat_id, "❌ Error fetching trade history.")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_alerts(self, update, context):
        chat_id = str(update.effective_chat.id)
        if not hasattr(self, "price_alerts"):
            self.price_alerts = {}

        args = context.args

        if not args or args[0].lower() == "list":
            user_alerts = self.price_alerts.get(chat_id, [])
            if not user_alerts:
                msg = """🔔 **Price Alerts (BTCUSDT)**

No active alerts.

**Usage:**
• `/alerts add [price]` — Add alert
• `/alerts remove [n]` — Remove alert
• `/alerts list` — Show all"""
            else:
                msg = "🔔 **Active Price Alerts (BTCUSDT):**\n\n"
                for i, a in enumerate(user_alerts, 1):
                    msg += f"**{i}.** `${a['price']:,.2f}` ({a['direction']}) — {a['created']}\n"
                msg += f"\n**Total:** {len(user_alerts)}/5"
            await self.send_message(chat_id, msg)

        elif args[0].lower() == "add":
            if len(args) < 2:
                await self.send_message(chat_id, "❌ Usage: `/alerts add [price]`")
                return
            try:
                target = float(args[1])
                cur    = await self.trader.get_current_price()
                if not cur:
                    await self.send_message(chat_id, "❌ Could not fetch current price.")
                    return
                if chat_id not in self.price_alerts:
                    self.price_alerts[chat_id] = []
                if len(self.price_alerts[chat_id]) >= 5:
                    await self.send_message(chat_id, "❌ Max 5 alerts. Remove one first.")
                    return
                direction = "above" if target > cur else "below"
                alert = {"price": target, "direction": direction,
                         "created": datetime.now().strftime("%m/%d %H:%M"), "triggered": False}
                self.price_alerts[chat_id].append(alert)
                await self.send_message(chat_id, f"""✅ **Alert Added:**
• **Target:** `${target:,.2f}` ({direction})
• **Current BTC:** `${cur:,.2f}`
• **Active:** {len(self.price_alerts[chat_id])}/5""")
            except ValueError:
                await self.send_message(chat_id, "❌ Invalid price.")

        elif args[0].lower() == "remove":
            if len(args) < 2:
                await self.send_message(chat_id, "❌ Usage: `/alerts remove [index]`")
                return
            try:
                idx = int(args[1]) - 1
                user_alerts = self.price_alerts.get(chat_id, [])
                if 0 <= idx < len(user_alerts):
                    removed = user_alerts.pop(idx)
                    await self.send_message(chat_id, f"✅ Alert `${removed['price']:,.2f}` removed.")
                else:
                    await self.send_message(chat_id, f"❌ Invalid index. Use 1–{len(user_alerts)}.")
            except ValueError:
                await self.send_message(chat_id, "❌ Invalid index.")
        else:
            await self.send_message(chat_id, "❌ Use: `/alerts`, `/alerts add [price]`, `/alerts remove [n]`")

        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_admin(self, update, context):
        chat_id  = str(update.effective_chat.id)
        admin_ids = [1548826223]

        try:
            if int(chat_id) not in admin_ids:
                await self.send_message(chat_id, "❌ **Access Denied** — Admin only.")
                return
        except ValueError:
            await self.send_message(chat_id, "❌ **Access Denied**")
            return

        try:
            args = context.args
            if not args:
                msg = f"""👑 **Admin Panel — BTCUSDT MiroFish Bot**

**Bot Management:**
• `/admin status` — Detailed status
• `/admin restart` — Reset scanner state
• `/admin config` — Show configuration
• `/admin logs` — Recent activity
• `/admin broadcast [msg]` — Send to all users

**Statistics:**
• **Signals:** {self.signal_count}
• **Commands:** {sum(self.commands_used.values())}
• **Uptime:** {str(datetime.now() - self.bot_start_time).split('.')[0]}
• **Last Signal:** {self.last_signal_time.strftime('%H:%M') if self.last_signal_time else 'Never'}"""
                await self.send_message(chat_id, msg)

            elif args[0].lower() == "status":
                price   = await self.trader.get_current_price()
                balance = await self.trader.get_account_balance()
                mem     = self.strategy.get_market_memory_summary()
                price_str   = f"${price:,.2f}" if price else "N/A"
                balance_str = f"${balance.get('available_balance', 0):,.2f}" if balance else "N/A"
                msg = f"""📊 **Detailed Admin Status**

**Bot:** 🟢 Running | **API:** {'🟢 Connected' if price else '🔴 Disconnected'}
**Price:** {price_str}
**Balance:** {balance_str} USDT
**Graph Nodes:** {mem.get('nodes', 0)} | **Active Edges:** {mem.get('active_edges', 0)}
**Trend State:** {mem.get('trend_state') or 'building...'}"""
                await self.send_message(chat_id, msg)

            elif args[0].lower() == "restart":
                self.last_signal_time = None
                self.signal_timestamps        = []
                self._symbol_last_signal      = {}
                self._symbol_signal_count     = {}
                self._symbol_last_direction   = {}
                await self.send_message(chat_id, "✅ Scanner state reset — global cooldowns, per-symbol locks, and direction dedup cleared.")

            elif args[0].lower() == "config":
                msg = f"""⚙️ **Configuration**

• **Symbol:** BTCUSDT Perpetual
• **Strategy:** MiroFish Swarm Intelligence
• **Channel:** {self.channel_id}
• **Min Interval:** {self.min_signal_interval_minutes:.0f} min
• **AI Threshold:** {os.getenv('AI_THRESHOLD_PERCENT', '80')}%
• **Testnet:** {self.trader.testnet}"""
                await self.send_message(chat_id, msg)

            elif args[0].lower() == "logs":
                msg = f"""📜 **Recent Activity**

• **Signals:** {self.signal_count}
• **Last:** {self.last_signal_time.strftime('%H:%M:%S') if self.last_signal_time else 'None'}
• **Commands:** {sum(self.commands_used.values())}
• **Uptime:** {str(datetime.now() - self.bot_start_time).split('.')[0]}"""
                await self.send_message(chat_id, msg)

            elif args[0].lower() == "broadcast":
                if len(args) < 2:
                    await self.send_message(chat_id, "❌ Usage: `/admin broadcast [message]`")
                    return
                bcast = " ".join(args[1:])
                ok = 0
                failed = 0
                for uid in list(self.commands_used.keys()):
                    try:
                        sent = await self.send_message(uid, f"📢 **Admin:** {bcast}")
                        if sent:
                            ok += 1
                        else:
                            failed += 1
                    except Exception as _be:
                        self.logger.debug(f"Broadcast to {uid} failed: {_be}")
                        failed += 1
                await self.send_message(chat_id, f"✅ Broadcast sent to {ok}/{len(self.commands_used)} users ({failed} failed).")

            else:
                await self.send_message(chat_id, "❌ Unknown admin command. Use `/admin` for help.")

        except Exception as e:
            self.logger.error(f"cmd_admin error: {e}")
            await self.send_message(chat_id, f"❌ Admin error: {e}")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_futures_info(self, update, context):
        chat_id = str(update.effective_chat.id)
        specs = self.contract_specs
        msg = (
            f"ℹ️ **BTCUSDT Perpetual Futures Info:**\n\n"
            f"• **Symbol:** `{specs['symbol']}`\n"
            f"• **Base Asset:** `{specs['base_asset']}`\n"
            f"• **Quote Asset:** `{specs['quote_asset']}`\n"
            f"• **Contract Type:** `{specs['contract_type']}`\n"
            f"• **Settlement:** `{specs['settlement_asset']}`\n"
            f"• **Margin Type:** `{specs['margin_type']}`\n"
            f"• **Tick Size:** `{specs['tick_size']}`\n"
            f"• **Step Size:** `{specs['step_size']}`\n"
            f"• **Max Leverage:** `{specs['max_leverage']}`\n"
            f"• **Funding Interval:** `{specs['funding_interval']}`\n\n"
            "BTCUSDT.PERP is the most liquid USDM perpetual futures contract on Binance."
        )
        await self.send_message(chat_id, msg)
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_contract_specs(self, update, context):
        await self.cmd_futures_info(update, context)

    async def cmd_funding_rate(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            data = await self.trader.get_funding_rate("BTCUSDT")
            if data:
                rate     = float(data.get("fundingRate", 0)) * 100
                next_ts  = int(data.get("fundingTime", 0))
                mark     = float(data.get("markPrice", 0))
                index    = float(data.get("indexPrice", 0))
                next_str = datetime.fromtimestamp(next_ts / 1000).strftime("%Y-%m-%d %H:%M UTC") if next_ts > 0 else "N/A"
                rate_emoji = "🟢" if rate >= 0 else "🔴"
                msg = f"""💸 **BTCUSDT Funding Rate:**

• **Current Rate:** {rate_emoji} `{rate:+.4f}%`
• **Next Funding:** `{next_str}`
• **Mark Price:** `${mark:,.2f}`
• **Index Price:** `${index:,.2f}`
• **Premium:** `${mark - index:+,.2f}`

**ℹ️ Note:** {'Longs pay shorts (bearish pressure)' if rate > 0 else 'Shorts pay longs (bullish pressure)'}"""
            else:
                msg = "❌ Could not retrieve funding rate."
            await self.send_message(chat_id, msg)
        except Exception as e:
            self.logger.error(f"cmd_funding_rate error: {e}")
            await self.send_message(chat_id, "❌ Error fetching funding rate.")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_open_interest(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            oi = await self.trader.get_open_interest("BTCUSDT")
            if oi:
                oi_val = float(oi.get("openInterest", 0))
                price  = await self.trader.get_current_price() or 0
                oi_usd = oi_val * price
                msg = f"""📊 **Open Interest (BTCUSDT.PERP):**

• **OI (BTC):** `{oi_val:,.3f} BTC`
• **OI (USDT):** `${oi_usd:,.0f}`
• **Mark Price:** `${price:,.2f}`

*OI represents total outstanding perpetual contracts.*"""
            else:
                msg = "❌ Could not retrieve open interest."
            await self.send_message(chat_id, msg)
        except Exception as e:
            self.logger.error(f"cmd_open_interest error: {e}")
            await self.send_message(chat_id, "❌ Error fetching open interest.")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_volume_analysis(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            klines = await self.trader.get_klines("30m", limit=48)
            if klines:
                vols       = [float(k[5]) for k in klines]
                qvols      = [float(k[7]) for k in klines]
                total_vol  = sum(vols)
                total_qvol = sum(qvols)
                avg_vol    = total_vol / len(vols)
                cur_vol    = vols[-1]
                vol_ratio  = cur_vol / avg_vol if avg_vol > 0 else 1.0

                emoji = "🔥" if vol_ratio > 1.5 else "📊" if vol_ratio > 0.8 else "💤"

                msg = f"""📈 **Volume Analysis (BTCUSDT — Last 24h, 30m):**

• **Total BTC Volume:** `{total_vol:,.3f} BTC`
• **Total USDT Volume:** `${total_qvol:,.0f}`
• **Avg Volume/30m:** `{avg_vol:,.3f} BTC`
• **Current Volume:** {emoji} `{cur_vol:,.3f} BTC`
• **Volume Ratio:** `{vol_ratio:.2f}x` (vs avg)

**🔍 Volume Signal:**
• {'🔥 High volume — strong move likely' if vol_ratio > 1.5 else '📊 Normal volume' if vol_ratio > 0.8 else '💤 Low volume — potential breakout setup'}"""
            else:
                msg = "❌ Could not retrieve volume data."
            await self.send_message(chat_id, msg)
        except Exception as e:
            self.logger.error(f"cmd_volume_analysis error: {e}")
            await self.send_message(chat_id, "❌ Error fetching volume data.")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_market_sentiment(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            klines = await self.trader.get_klines("1h", limit=168)  # 1 week
            if klines and len(klines) >= 24:
                closes = [float(k[4]) for k in klines]
                mean   = sum(closes[-24:]) / 24
                cur    = closes[-1]
                dev    = (cur - mean) / mean * 100
                _n24 = min(len(closes) - 1, 24)
                vol_24 = (sum(abs(closes[i] - closes[i - 1]) for i in range(-_n24, 0)) / _n24) if _n24 > 0 else 0.0
                if len(closes) >= 169:
                    _n7d = min(len(closes) - 1, 168)
                    vol_7d = sum(abs(closes[i] - closes[i - 1]) for i in range(-_n7d, 0)) / _n7d
                else:
                    vol_7d = vol_24

                if dev > 5:
                    sentiment = "😤 GREED — potential reversal zone"
                    emoji = "🔴"
                elif dev > 2:
                    sentiment = "📈 BULLISH — momentum positive"
                    emoji = "🟢"
                elif dev < -5:
                    sentiment = "😱 FEAR — potential bounce zone"
                    emoji = "🟢"
                elif dev < -2:
                    sentiment = "📉 BEARISH — selling pressure"
                    emoji = "🔴"
                else:
                    sentiment = "😐 NEUTRAL — consolidation"
                    emoji = "⚪"

                msg = f"""😱 **Market Sentiment — BTCUSDT:**

{emoji} **Sentiment:** `{sentiment}`

**📊 Price Metrics:**
• **Current:** `${cur:,.2f}`
• **24h Mean:** `${mean:,.2f}`
• **Deviation:** `{dev:+.2f}%`

**📈 Volatility:**
• **24h Avg Move:** `${vol_24:,.2f}/hr`
• **7d Avg Move:** `${vol_7d:,.2f}/hr`
• **Vol Ratio:** `{(vol_24 / vol_7d if vol_7d > 0 else 1.0):.2f}x` (current vs 7d avg)

**💡 MiroFish Agents' View:**
Graph trend state: {self.strategy.get_market_memory_summary().get('trend_state') or 'analyzing...'}"""
            else:
                msg = "❌ Insufficient data for sentiment analysis."
            await self.send_message(chat_id, msg)
        except Exception as e:
            self.logger.error(f"cmd_market_sentiment error: {e}")
            await self.send_message(chat_id, "❌ Error generating sentiment analysis.")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_market_news(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            price  = await self.trader.get_current_price()
            ticker = await self.trader.get_24hr_ticker_stats("BTCUSDT")
            if ticker:
                chg_pct = float(ticker.get("priceChangePercent", 0))
                volume  = float(ticker.get("volume", 0))

                if abs(chg_pct) > 5:
                    vol_note = f"🚨 Extreme move: BTCUSDT {chg_pct:+.2f}% in 24h — high volatility"
                elif abs(chg_pct) > 2:
                    vol_note = f"📊 Significant move: BTCUSDT {chg_pct:+.2f}% — momentum building"
                else:
                    vol_note = f"📈 Stable: BTCUSDT {chg_pct:+.2f}% — consolidation phase"

                msg = f"""📰 **BTCUSDT Market Analysis**

**🎯 Current Conditions:**
• {vol_note}
• **Volume:** {'🔥 High' if volume > 50000 else '📊 Normal'} ({volume:,.1f} BTC)
• **Price Level:** ${price:,.2f}

**📊 Technical Outlook:**
• **Trend:** {'Bullish' if chg_pct > 1 else 'Bearish' if chg_pct < -1 else 'Sideways'}
• **Key Support:** ~${(price or 0) * 0.97:,.0f}
• **Key Resistance:** ~${(price or 0) * 1.03:,.0f}

**🐟 MiroFish Context:**
• Graph trend state: {self.strategy.get_market_memory_summary().get('trend_state') or 'analyzing...'}
• Use `/swarm` for agent breakdown
• Use `/scan` to trigger live analysis

**⏰ Updated:** {datetime.now().strftime('%H:%M:%S UTC')}

*For live BTC news: Coindesk, CryptoSlate, Binance News*"""
            else:
                msg = "❌ Could not retrieve market data."
            await self.send_message(chat_id, msg)
        except Exception as e:
            self.logger.error(f"cmd_market_news error: {e}")
            await self.send_message(chat_id, "❌ Error generating market news.")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_watchlist(self, update, context):
        chat_id = str(update.effective_chat.id)
        await self.send_message(chat_id, "🗒️ Watchlist: This bot exclusively trades **BTCUSDT.PERP** (Binance USDM Futures).\n\nUse `/price` or `/market` for real-time data.")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_backtest(self, update, context):
        """Backtest MiroFish strategy"""
        chat_id = str(update.effective_chat.id)

        duration_days = 30
        timeframe     = "15m"

        if context.args:
            try:
                duration_days = max(1, int(context.args[0]))
            except ValueError:
                await self.send_message(chat_id, "❌ Invalid duration. Use: `/backtest [days] [timeframe]`")
                return
        if len(context.args) >= 2:
            valid_tfs = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"]
            tf = context.args[1].lower()
            if tf not in valid_tfs:
                await self.send_message(chat_id, f"❌ Invalid timeframe. Use: {', '.join(valid_tfs)}")
                return
            timeframe = tf

        await self.send_message(chat_id, f"🧪 Running MiroFish backtest...\n📅 Period: {duration_days} days\n⏱️ Timeframe: {timeframe}")
        try:
            results = await self._run_backtest(duration_days, timeframe, chat_id)
            await self._display_backtest_results(chat_id, results, duration_days, timeframe)
        except Exception as e:
            self.logger.error(f"Backtest error: {e}")
            await self.send_message(chat_id, f"❌ Backtest error: {e}")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def _run_backtest(self, duration_days: int, timeframe: str,
                            chat_id: Optional[str] = None) -> dict:
        """
        Real indicator-based backtest using actual Binance kline data.

        Signal generation logic mirrors the live swarm gates:
          - EMA9 > EMA21 cross (trend direction)
          - RSI oversold/overbought confirmation
          - Volume surge (≥1.3× 20-bar average)
          - MACD histogram direction

        Outcome evaluation:
          - SL at 0.65% from entry (ATR-scaled minimum)
          - TP1 at 1.10%, TP2 at 2.00%, TP3 at 3.10% (production params)
          - Scans forward candles for first level touched
          - Trade EXPIRES after 12 candles with no hit (neutral P&L)
        """
        try:
            tf_mins = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
                       "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720, "1d": 1440}
            mins = tf_mins.get(timeframe, 15)
            candles_needed = min(duration_days * 24 * 60 // mins, 1000)

            data = await self.trader.get_klines(timeframe, limit=candles_needed)
            if not data or len(data) < 60:
                return {"error": "Insufficient historical data (need ≥60 candles)"}

            closes  = [float(k[4]) for k in data]
            highs   = [float(k[2]) for k in data]
            lows    = [float(k[3]) for k in data]
            volumes = [float(k[5]) for k in data]

            # ── Inline indicator helpers (pure Python, no imports needed) ──
            def _ema_bt(series, period):
                if len(series) < period:
                    return None
                k = 2.0 / (period + 1)
                e = sum(series[:period]) / period
                for v in series[period:]:
                    e = v * k + e * (1 - k)
                return e

            def _rsi_bt(series, period=14):
                if len(series) < period + 1:
                    return 50.0
                gains = [max(series[i] - series[i-1], 0) for i in range(1, len(series))]
                losses = [max(series[i-1] - series[i], 0) for i in range(1, len(series))]
                ag = sum(gains[:period]) / period
                al = sum(losses[:period]) / period
                for i in range(period, len(gains)):
                    ag = (ag * (period - 1) + gains[i]) / period
                    al = (al * (period - 1) + losses[i]) / period
                return 100.0 if al == 0 else 0.0 if ag == 0 else 100.0 - (100.0 / (1.0 + ag / al))

            def _macd_hist_bt(series, fast=12, slow=26, sig=9):
                if len(series) < slow + sig:
                    return 0.0
                def _ema_s(d, p):
                    k = 2.0 / (p + 1)
                    e = sum(d[:p]) / p
                    out = [e]
                    for v in d[p:]:
                        e = v * k + e * (1 - k)
                        out.append(e)
                    return out
                ef = _ema_s(series, fast)
                es = _ema_s(series, slow)
                n = min(len(ef), len(es))
                ml = [ef[i] - es[i] for i in range(-n, 0)]
                if len(ml) < sig:
                    return 0.0
                sl_val = _ema_s(ml, sig)[-1]
                return ml[-1] - sl_val

            # ── Walk-forward backtesting ──
            initial_capital = 1000.0
            capital         = initial_capital
            trades_log      = []
            commission_rate = 0.0004      # Binance taker
            risk_per_trade  = 0.015       # 1.5% capital at risk per trade
            sl_pct          = 0.0065      # 0.65% SL (production minimum)
            tp1_pct         = 0.0110      # 1.10% TP1
            tp2_pct         = 0.0200      # 2.00% TP2
            tp3_pct         = 0.0310      # 3.10% TP3
            max_hold_bars   = 12          # expire after N candles with no hit
            min_vol_ratio   = 1.3         # require 1.3× average volume

            warmup = 40  # bars needed for indicators
            last_signal_bar = -10  # cooldown: no two signals within 3 bars

            for i in range(warmup, len(closes) - max_hold_bars - 1):
                # Signal generation window
                c_win = closes[:i+1]
                v_win = volumes[:i+1]

                ema9  = _ema_bt(c_win, 9)
                ema21 = _ema_bt(c_win, 21)
                if ema9 is None or ema21 is None:
                    continue

                rsi_val = _rsi_bt(c_win[-30:])
                macd_h  = _macd_hist_bt(c_win)

                # Volume confirmation
                avg_vol = sum(v_win[-21:-1]) / 20 if len(v_win) >= 21 else 0.0
                vol_ratio = v_win[-1] / avg_vol if avg_vol > 0 else 1.0

                # Signal: all 3 conditions must align
                ema_cross_up   = ema9 > ema21
                ema_cross_down = ema9 < ema21

                # Require volume surge for signal quality
                if vol_ratio < min_vol_ratio:
                    continue

                # Cooldown between signals
                if i - last_signal_bar < 3:
                    continue

                if ema_cross_up and rsi_val < 65 and macd_h > 0:
                    action = "BUY"
                elif ema_cross_down and rsi_val > 35 and macd_h < 0:
                    action = "SELL"
                else:
                    continue

                last_signal_bar = i
                entry = closes[i]
                if entry <= 0:
                    continue

                # ATR-based SL distance (use simple close-to-close ATR)
                c_atr = c_win[-15:]
                trs = [abs(c_atr[j] - c_atr[j-1]) for j in range(1, len(c_atr))]
                atr = sum(trs[-14:]) / min(14, len(trs)) if trs else entry * 0.003
                atr_pct = atr / entry

                # Use larger of ATR-based or fixed pct SL
                sl_dist  = max(atr * 1.5, entry * sl_pct)
                tp1_dist = max(atr * 1.5 * (tp1_pct / sl_pct), entry * tp1_pct)
                tp2_dist = max(atr * 1.5 * (tp2_pct / sl_pct), entry * tp2_pct)
                tp3_dist = max(atr * 1.5 * (tp3_pct / sl_pct), entry * tp3_pct)

                if action == "BUY":
                    sl_price  = entry - sl_dist
                    tp1_price = entry + tp1_dist
                    tp2_price = entry + tp2_dist
                    tp3_price = entry + tp3_dist
                else:
                    sl_price  = entry + sl_dist
                    tp1_price = entry - tp1_dist
                    tp2_price = entry - tp2_dist
                    tp3_price = entry - tp3_dist

                rr = tp2_dist / max(sl_dist, 1e-10)

                # Walk forward to find first level touched
                outcome = "EXPIRED"
                exit_price = closes[min(i + max_hold_bars, len(closes) - 1)]

                for j in range(i + 1, min(i + max_hold_bars + 1, len(closes))):
                    hi_j = highs[j]
                    lo_j = lows[j]
                    if action == "BUY":
                        if lo_j <= sl_price:
                            outcome = "SL";  exit_price = sl_price;  break
                        elif hi_j >= tp3_price:
                            outcome = "TP3"; exit_price = tp3_price; break
                        elif hi_j >= tp2_price:
                            outcome = "TP2"; exit_price = tp2_price; break
                        elif hi_j >= tp1_price:
                            outcome = "TP1"; exit_price = tp1_price; break
                    else:
                        if hi_j >= sl_price:
                            outcome = "SL";  exit_price = sl_price;  break
                        elif lo_j <= tp3_price:
                            outcome = "TP3"; exit_price = tp3_price; break
                        elif lo_j <= tp2_price:
                            outcome = "TP2"; exit_price = tp2_price; break
                        elif lo_j <= tp1_price:
                            outcome = "TP1"; exit_price = tp1_price; break

                # Compute P&L
                risk_amt = capital * risk_per_trade
                move_pct = (exit_price - entry) / entry if action == "BUY" else (entry - exit_price) / entry
                # Scale P&L by risk/reward against actual SL distance
                sl_move_pct = sl_dist / entry
                pnl_mult = move_pct / sl_move_pct if sl_move_pct > 0 else 0.0
                trade_pnl = risk_amt * pnl_mult
                trade_pnl -= abs(trade_pnl) * commission_rate  # commission
                capital = max(capital + trade_pnl, 1.0)

                trades_log.append({
                    "pnl": trade_pnl, "capital": capital,
                    "win": outcome in ("TP1", "TP2", "TP3"),
                    "outcome": outcome, "consensus": vol_ratio / 3.0,
                    "rr": rr,
                })

            if not trades_log:
                return {"error": "No signals generated — market conditions may be ranging"}

            wins   = sum(1 for t in trades_log if t["win"])
            losses = sum(1 for t in trades_log if t["outcome"] == "SL")
            expired = len(trades_log) - wins - losses
            win_rate = wins / len(trades_log) * 100

            gross_profit = sum(t["pnl"] for t in trades_log if t["pnl"] > 0)
            gross_loss   = abs(sum(t["pnl"] for t in trades_log if t["pnl"] < 0))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

            total_pnl    = capital - initial_capital
            total_return = total_pnl / initial_capital * 100

            pnl_list = [t["pnl"] for t in trades_log]
            avg_pnl  = sum(pnl_list) / len(pnl_list)
            variance = sum((x - avg_pnl) ** 2 for x in pnl_list) / len(pnl_list) if pnl_list else 0
            std_pnl  = variance ** 0.5
            # Annualised Sharpe (candle-period returns)
            candles_per_year = 365 * 24 * 60 // mins
            sharpe = (avg_pnl / std_pnl) * (candles_per_year ** 0.5) if std_pnl > 0 else 0

            peak_cap = initial_capital
            max_dd   = 0.0
            for t in trades_log:
                peak_cap = max(peak_cap, t["capital"])
                dd = (peak_cap - t["capital"]) / peak_cap * 100 if peak_cap > 0 else 0
                max_dd = max(max_dd, dd)

            winning_trades = [t for t in trades_log if t["win"]]
            losing_trades  = [t for t in trades_log if t["outcome"] == "SL"]
            avg_win  = sum(t["pnl"] for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss_v = sum(t["pnl"] for t in losing_trades) / len(losing_trades) if losing_trades else 0
            avg_consensus = sum(t["consensus"] for t in trades_log) / len(trades_log)
            avg_rr = sum(t["rr"] for t in trades_log) / len(trades_log)

            return {
                "duration_days": duration_days, "timeframe": timeframe,
                "candles_used": len(data),
                "initial_capital": initial_capital, "final_capital": capital,
                "total_pnl": total_pnl, "total_return": total_return,
                "total_trades": len(trades_log),
                "winning_trades": wins, "losing_trades": losses, "expired_trades": expired,
                "win_rate": win_rate, "max_drawdown": max_dd,
                "profit_factor": profit_factor, "sharpe_ratio": sharpe,
                "trades_per_day": len(trades_log) / duration_days,
                "avg_win": avg_win, "avg_loss": avg_loss_v,
                "gross_profit": gross_profit, "gross_loss": gross_loss,
                "peak_capital": peak_cap, "avg_consensus": avg_consensus,
                "avg_rr": avg_rr,
                "data_source": "real",
            }

        except Exception as e:
            return {"error": str(e)}

    async def _display_backtest_results(self, chat_id: str, results: dict,
                                        duration_days: int, timeframe: str):
        if "error" in results:
            await self.send_message(chat_id, f"❌ Backtest failed: {results['error']}")
            return

        profit_status = "🟢 PROFITABLE" if results["total_pnl"] >= 0 else "🔴 UNPROFITABLE"
        perf_status   = ("🎯 EXCELLENT" if results["win_rate"] > 58 and results["profit_factor"] > 1.5
                         else "⚠️ NEEDS REVIEW" if results["profit_factor"] > 1.0 else "❌ POOR")

        data_tag  = "📡 Real Binance data" if results.get("data_source") == "real" else "🎲 Simulated"
        candles   = results.get("candles_used", "N/A")
        expired   = results.get("expired_trades", 0)
        avg_rr    = results.get("avg_rr", 0.0)

        msg = f"""🧪 **MIROFISH SWARM BACKTEST RESULTS**

📊 **Test Config:**
• Duration: {duration_days} days | TF: {timeframe}
• Data: {data_tag} ({candles} candles)
• Strategy: MiroFish Swarm (EMA9/21 + RSI + MACD + Volume)
• SL: 0.65% | TP1: 1.10% | TP2: 2.00% | TP3: 3.10%

💰 **Performance:**
• Initial: `${results['initial_capital']:,.2f}`
• Final: `${results['final_capital']:,.2f}`
• P&L: `${results['total_pnl']:+,.2f}` ({results['total_return']:+.1f}%)
• Peak: `${results['peak_capital']:,.2f}`

📈 **Trade Stats:**
• Total Trades: {results['total_trades']}
• Wins (TP hit): {results['winning_trades']} ({results['win_rate']:.1f}%)
• Losses (SL hit): {results['losing_trades']}
• Expired (no hit): {expired}
• Trades/Day: {results['trades_per_day']:.1f}
• Avg R:R: `1:{avg_rr:.2f}`

💎 **Quality Metrics:**
• Win Rate: `{results['win_rate']:.1f}%`
• Profit Factor: `{results['profit_factor']:.2f}`
• Sharpe Ratio: `{results['sharpe_ratio']:.2f}`
• Max Drawdown: `{results['max_drawdown']:.1f}%`
• Avg Vol Ratio: `{results.get('avg_consensus', 0)*3:.2f}×`

📊 **Trade Analysis:**
• Avg Win: `+${results['avg_win']:,.4f}`
• Avg Loss: `-${abs(results['avg_loss']):,.4f}`
• Gross Profit: `${results['gross_profit']:,.4f}`
• Gross Loss: `-${results['gross_loss']:,.4f}`

{profit_status} | {perf_status}"""

        await self.send_message(chat_id, msg)

    def _get_timeframe_minutes(self, tf: str) -> int:
        return {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
                "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720, "1d": 1440}.get(tf, 0)

    async def cmd_optimize_strategy(self, update, context):
        """
        Real parameter optimization using TradeMemory historical data.

        Buckets resolved trades by their recorded swarm_consensus value and
        computes actual win rate + profit factor per threshold bucket.  This
        surfaces which minimum-consensus setting would have produced the best
        historical results without using any random simulation.

        Falls back to a current-session stats summary when fewer than 10
        resolved trades are available (cold start).
        """
        chat_id = str(update.effective_chat.id)
        try:
            await self.send_message(chat_id, "🔧 Analysing real trade history for optimization...")

            # Pull labeled trades from TradeMemory
            labeled = []
            if hasattr(self, "trade_memory") and self.trade_memory is not None:
                try:
                    labeled = self.trade_memory.get_labeled_trades(limit=500)
                except Exception:
                    labeled = []

            THRESHOLDS = [0.75, 0.80, 0.85, 0.90, 0.95]

            if len(labeled) >= 10:
                # ── Real optimization from trade history ──
                results = []
                for thresh in THRESHOLDS:
                    bucket = [
                        t for t in labeled
                        if float(t.get("swarm_consensus") or 0) >= thresh
                    ]
                    if not bucket:
                        continue
                    wins   = sum(1 for t in bucket if (t.get("outcome") or "") in ("TP1", "TP2", "TP3"))
                    losses = sum(1 for t in bucket if (t.get("outcome") or "") == "SL")
                    resolved = wins + losses
                    if resolved == 0:
                        continue
                    win_rate = wins / resolved

                    gross_p = sum(
                        float(t.get("pnl_pct") or 0) for t in bucket
                        if (t.get("outcome") or "") in ("TP1", "TP2", "TP3")
                    )
                    gross_l = abs(sum(
                        float(t.get("pnl_pct") or 0) for t in bucket
                        if (t.get("outcome") or "") == "SL"
                    ))
                    pf = gross_p / gross_l if gross_l > 0 else float("inf")
                    pf_capped = min(pf, 9.99)

                    # Composite score: win_rate + profit_factor + coverage bonus
                    coverage = len(bucket) / max(len(labeled), 1)
                    score = win_rate * 0.45 + min(pf_capped / 10.0, 1.0) * 0.35 + coverage * 0.20
                    results.append({
                        "threshold": thresh, "win_rate": win_rate, "pf": pf_capped,
                        "score": score, "trades": len(bucket), "wins": wins, "losses": losses,
                    })

                if not results:
                    await self.send_message(chat_id, "⚠️ No resolved trades match the consensus thresholds tested. Run the bot longer to accumulate data.")
                    return

                results.sort(key=lambda x: x["score"], reverse=True)
                best = results[0]

                lines = "\n".join(
                    f"• ≥{r['threshold']:.0%}: WR={r['win_rate']:.1%} PF={r['pf']:.2f} "
                    f"Trades={r['trades']} W/L={r['wins']}/{r['losses']} Score={r['score']:.3f}"
                    for r in results
                )

                # Neural network status
                nn_line = ""
                try:
                    if hasattr(self, "nn_trainer") and self.nn_trainer is not None:
                        nn_line = f"\n**🧠 Neural Network:** `{self.nn_trainer.status_summary()}`"
                except Exception:
                    pass

                # Current live gates
                live_cons = int(getattr(self.strategy, "min_swarm_consensus", 0.75) * 100)
                live_conf = int(getattr(self.strategy, "min_confidence", 64))

                msg = f"""🔧 **MiroFish Real Optimization** _(from {len(labeled)} historical trades)_

**✅ Best Consensus Threshold:**
• **Min Consensus:** `{best['threshold']:.0%}`
• **Win Rate:** `{best['win_rate']:.1%}`
• **Profit Factor:** `{best['pf']:.2f}`
• **Trades:** {best['trades']} (W={best['wins']} L={best['losses']})
• **Score:** `{best['score']:.3f}`

**📊 All Consensus Buckets (real data):**
{lines}

**⚙️ Current Live Gates:**
• Min consensus: `{live_cons}%` | Min confidence: `{live_conf}%`
• R:R min: `{getattr(self.strategy, 'min_rr_ratio', 1.55):.2f}`
{nn_line}

_Optimization is based on the most recent {len(labeled)} resolved trades from TradeMemory._
_Run /backtest to validate on fresh kline data._"""

            else:
                # ── Cold-start fallback: show current session stats ──
                stats = {}
                if hasattr(self, "trade_memory") and self.trade_memory is not None:
                    try:
                        stats = self.trade_memory.get_stats()
                    except Exception:
                        stats = {}

                total_sig  = stats.get("total_signals", 0)
                win_rate_s = stats.get("win_rate", 0.0)
                avg_pnl    = stats.get("avg_pnl_pct", 0.0)
                live_cons  = int(getattr(self.strategy, "min_swarm_consensus", 0.75) * 100)

                msg = f"""🔧 **MiroFish Optimization — Accumulating Data**

⚠️ Only {len(labeled)} resolved trades available (need ≥10 for real optimization).

**📊 Current Session Stats:**
• Total signals sent: `{total_sig}`
• Win rate (resolved): `{win_rate_s:.1f}%`
• Avg P&L: `{avg_pnl:+.3f}%`

**⚙️ Current Live Gates:**
• Min consensus: `{live_cons}%`
• Min confidence: `{int(getattr(self.strategy, 'min_confidence', 64))}%`
• Min R:R: `{getattr(self.strategy, 'min_rr_ratio', 1.55):.2f}`

_Keep the bot running — optimization improves as more trades are resolved._
_Run /backtest for indicator-based backtesting on real kline data._"""

            await self.send_message(chat_id, msg)
        except Exception as e:
            await self.send_message(chat_id, f"❌ Optimization error: {e}")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_dynamic_sltp(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            if not context.args:
                await self.send_message(chat_id, "❌ Usage: `/dynamic_sltp LONG` or `/dynamic_sltp SHORT`")
                return

            direction = context.args[0].upper()
            if direction in ("BUY", "LONG"):
                direction = "LONG"
            elif direction in ("SELL", "SHORT"):
                direction = "SHORT"
            else:
                await self.send_message(chat_id, "❌ Use LONG/BUY or SHORT/SELL.")
                return

            price = await self.trader.get_current_price()
            if not price:
                await self.send_message(chat_id, "❌ Could not fetch price.")
                return

            # ATR-based SL/TP for BTC
            klines = await self.trader.get_klines("1h", limit=24)
            if klines and len(klines) >= 14:
                closes = [float(k[4]) for k in klines]
                highs  = [float(k[2]) for k in klines]
                lows   = [float(k[3]) for k in klines]
                trs    = [max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
                          for i in range(1, len(closes))]
                atr    = sum(trs[-14:]) / 14
            else:
                atr = price * 0.015  # 1.5% default ATR for BTC

            sl_mult  = 1.5
            tp1_mult = 1.5
            tp2_mult = 2.5
            tp3_mult = 4.0

            if direction == "LONG":
                sl  = price - atr * sl_mult
                tp1 = price + atr * tp1_mult
                tp2 = price + atr * tp2_mult
                tp3 = price + atr * tp3_mult
            else:
                sl  = price + atr * sl_mult
                tp1 = price - atr * tp1_mult
                tp2 = price - atr * tp2_mult
                tp3 = price - atr * tp3_mult

            rr = abs(tp1 - price) / abs(sl - price) if abs(sl - price) > 0 else 0

            msg = f"""🎯 **Dynamic SL/TP — BTCUSDT {direction}**

**📊 Position:**
• **Direction:** `{direction}`
• **Entry:** `${price:,.2f}`
• **ATR (1h):** `${atr:,.2f}` ({atr/price*100:.2f}%)

**🛡️ Levels:**
• **Stop Loss:** `${sl:,.2f}` ({abs(sl-price)/price*100:.2f}% away)
• **TP1 (45%):** `${tp1:,.2f}` (+{abs(tp1-price)/price*100:.2f}%)
• **TP2 (35%):** `${tp2:,.2f}` (+{abs(tp2-price)/price*100:.2f}%)
• **TP3 (20%):** `${tp3:,.2f}` (+{abs(tp3-price)/price*100:.2f}%)

**📈 Risk Management:**
• **Risk/Reward:** `1:{rr:.2f}`
• **SL Distance:** `${abs(sl-price):,.2f}`

**💡 Tips:**
• Scale out 45% at TP1, 35% at TP2, 20% at TP3
• Move SL to break-even after TP1 hit
• BTC volatile — use 3-10x leverage max"""

            await self.send_message(chat_id, msg)
        except Exception as e:
            self.logger.error(f"cmd_dynamic_sltp error: {e}")
            await self.send_message(chat_id, f"❌ SL/TP error: {e}")
        finally:
            self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_market_dashboard(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            await self.send_message(chat_id, "📊 Generating BTCUSDT dashboard...")

            price  = await self.trader.get_current_price()
            ticker = await self.trader.get_24hr_ticker_stats("BTCUSDT")
            oi     = await self.trader.get_open_interest("BTCUSDT")
            fr     = await self.trader.get_funding_rate("BTCUSDT")
            mem    = self.strategy.get_market_memory_summary()

            if ticker and price:
                chg_pct   = float(ticker.get("priceChangePercent", 0))
                volume    = float(ticker.get("volume", 0))
                high_24h  = float(ticker.get("highPrice", 0))
                low_24h   = float(ticker.get("lowPrice", 0))
                quote_vol = float(ticker.get("quoteVolume", 0))

                oi_btc    = float(oi.get("openInterest", 0)) if oi else 0
                fr_rate   = float(fr.get("fundingRate", 0)) * 100 if fr else 0

                d_emoji   = "🟢" if chg_pct >= 0 else "🔴"
                fr_emoji  = "🟢" if fr_rate >= 0 else "🔴"
                vol_emoji = "🔥" if volume > 50000 else "📊" if volume > 20000 else "💤"

                msg = f"""📊 **BTCUSDT Market Dashboard**

**💰 Price:**
• **Current:** `${price:,.2f}`
• **24h Change:** {d_emoji} `{chg_pct:+.2f}%`
• **24h High:** `${high_24h:,.2f}` | **Low:** `${low_24h:,.2f}`
• **Range:** `${high_24h - low_24h:,.2f}` ({(high_24h - low_24h) / low_24h * 100 if low_24h > 0 else 0.0:.2f}%)

**📈 Derivatives:**
• **Open Interest:** `{oi_btc:,.2f} BTC` (${oi_btc*price:,.0f})
• **Funding Rate:** {fr_emoji} `{fr_rate:+.4f}%`
• **Volume 24h:** {vol_emoji} `{volume:,.1f} BTC` (${quote_vol:,.0f})

**🐟 MiroFish Swarm:**
• **Graph Nodes:** `{mem.get('nodes', 0)}`
• **Active Edges:** `{mem.get('active_edges', 0)}`
• **Trend State:** `{mem.get('trend_state') or 'building...'}`

**💡 Action:**
• `/scan` — Trigger swarm analysis
• `/dynamic_sltp LONG` — Get SL/TP levels
• `/swarm` — Agent consensus details

**⏰ Updated:** `{datetime.now().strftime('%H:%M:%S UTC')}`"""

                await self.send_message(chat_id, msg)
            else:
                await self.send_message(chat_id, "❌ Could not retrieve market data.")

        except Exception as e:
            self.logger.error(f"cmd_market_dashboard error: {e}")
            await self.send_message(chat_id, f"❌ Dashboard error: {e}")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_market_intelligence(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            market_data = await self.trader.get_market_data("BTCUSDT", "1m", 200)
            if not market_data or len(market_data) < 50:
                await self.send_message(chat_id, "❌ Insufficient data.")
                return

            if self.market_intelligence:
                cur_price = await self.trader.get_current_price()
                mi = await self.market_intelligence.get_market_intelligence_summary(
                    market_data, cur_price or 0.0
                )
                signal = mi.get("signal", "neutral").upper()
                vol    = mi.get("volume", {})
                bsr    = vol.get("buy_sell_ratio", 0) if isinstance(vol, dict) else 0
                msg = f"""📊 **Market Intelligence — BTCUSDT**

• **Signal:** `{signal}`
• **Buy/Sell Ratio:** `{bsr:.2f}x`
• **Analysis:** {'Bullish pressure dominates' if bsr > 1.1 else 'Bearish pressure dominates' if bsr < 0.9 else 'Balanced order flow'}

Use `/orderflow` for detailed flow analysis."""
            else:
                # Fallback: basic close analysis
                closes = [float(k[4]) for k in market_data]
                chg = (closes[-1] - closes[-20]) / closes[-20] * 100
                msg = f"""📊 **Market Intelligence (Basic):**

• **20-candle change:** `{chg:+.2f}%`
• **Signal:** `{'BULLISH' if chg > 0.5 else 'BEARISH' if chg < -0.5 else 'NEUTRAL'}`

*(Enhanced analysis unavailable — basic mode)*"""

            await self.send_message(chat_id, msg)
        except Exception as e:
            await self.send_message(chat_id, f"❌ Error: {e}")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_insider_detection(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            market_data = await self.trader.get_market_data("BTCUSDT", "1m", 200)
            if not market_data or len(market_data) < 50:
                await self.send_message(chat_id, "❌ Insufficient data.")
                return

            if self.insider_analyzer:
                sig = await self.insider_analyzer.detect_insider_activity(market_data)
                if sig.detected:
                    msg = f"🐋 **Insider Activity:** {sig.activity_type.upper()} ({sig.confidence:.1f}%)\n{sig.description}"
                else:
                    msg = "🟢 No unusual insider activity detected."
            else:
                # Fallback: volume spike detection
                vols = [float(k[5]) for k in market_data]
                avg  = sum(vols[-20:-1]) / 19
                cur  = vols[-1]
                ratio = cur / avg if avg > 0 else 1.0
                if ratio > 3:
                    msg = f"🐋 **Volume Spike Detected:** {ratio:.1f}x normal volume — possible institutional activity"
                elif ratio > 2:
                    msg = f"⚠️ **Elevated Volume:** {ratio:.1f}x normal — monitor closely"
                else:
                    msg = f"🟢 Normal volume ({ratio:.1f}x avg) — no unusual activity"

            await self.send_message(chat_id, msg)
        except Exception as e:
            await self.send_message(chat_id, f"❌ Error: {e}")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_order_flow(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            market_data = await self.trader.get_market_data("BTCUSDT", "1m", 200)
            if not market_data or len(market_data) < 50:
                await self.send_message(chat_id, "❌ Insufficient data.")
                return

            if self.smart_sltp:
                import pandas as pd
                if isinstance(market_data, list):
                    df = pd.DataFrame(market_data)
                    cols = ["time", "open", "high", "low", "close", "volume",
                            "close_time", "qvol", "trades", "tbv", "tbq", "ignore"]
                    df.columns = cols[:len(df.columns)]
                    for c in ["open", "high", "low", "close", "volume"]:
                        if c in df.columns:
                            df[c] = df[c].astype(float)
                else:
                    df = market_data

                price = await self.trader.get_current_price()
                of    = await self.smart_sltp.analyze_order_flow(df, price or 0.0)

                msg = f"""📈 **Order Flow — BTCUSDT:**

• **Direction:** `{of.direction.value.upper()}`
• **Aggressive Buy:** `{of.aggressive_buy_ratio*100:.1f}%`
• **Aggressive Sell:** `{of.aggressive_sell_ratio*100:.1f}%`
• **Imbalance:** `{of.volume_imbalance*100:+.1f}%`"""
            else:
                # Fallback: candle body analysis
                closes = [float(k[4]) for k in market_data]
                opens  = [float(k[1]) for k in market_data]
                bull_candles = sum(1 for i in range(-20, 0) if closes[i] > opens[i])
                bear_candles = 20 - bull_candles
                msg = f"""📈 **Order Flow (Basic) — BTCUSDT:**

• **Last 20 Candles:**
  • Bull: `{bull_candles}` ({bull_candles/20:.0%})
  • Bear: `{bear_candles}` ({bear_candles/20:.0%})
• **Pressure:** `{'BULLISH' if bull_candles > 12 else 'BEARISH' if bear_candles > 12 else 'NEUTRAL'}`"""

            await self.send_message(chat_id, msg)
        except Exception as e:
            await self.send_message(chat_id, f"❌ Error: {e}")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def cmd_dynamic_leveraging_sl(self, update, context):
        chat_id = str(update.effective_chat.id)
        try:
            if not context.args:
                await self.send_message(chat_id, "❌ Usage: `/dynamic_sl LONG [pct] [leverage]`\nExample: `/dynamic_sl LONG 1.5 10`")
                return

            direction = context.args[0].upper()
            direction = "LONG" if direction in ("LONG", "BUY") else "SHORT"

            pct_below = float(context.args[1]) / 100 if len(context.args) > 1 else 0.015
            leverage  = int(context.args[2]) if len(context.args) > 2 else 10

            price = await self.trader.get_current_price()
            if not price:
                await self.send_message(chat_id, "❌ Could not fetch price.")
                return

            if direction == "LONG":
                sl_price = price * (1 - pct_below)
            else:
                sl_price = price * (1 + pct_below)

            distance = abs(price - sl_price)
            liq_distance = price / leverage  # Approximate liquidation distance

            msg = f"""🛡️ **Dynamic Leveraging Stop Loss — BTCUSDT**

**Position:**
• **Direction:** `{direction}`
• **Entry:** `${price:,.2f}`
• **Leverage:** `{leverage}x`
• **% Below Trigger:** `{pct_below*100:.2f}%`

**Levels:**
• **Stop Loss:** `${sl_price:,.2f}`
• **SL Distance:** `${distance:,.2f}` ({pct_below*100:.2f}%)
• **~Liquidation:** `${price - liq_distance if direction == 'LONG' else price + liq_distance:,.2f}`
• **SL Buffer:** `{(distance / liq_distance) if liq_distance > 0 else 0:.1f}x` above liquidation

**Risk:**
• **Risk at {leverage}x:** `{pct_below * leverage * 100:.1f}%` of margin

**💡 Tips:**
• Keep SL ≥2x above liquidation price
• BTC volatile — use wider SL at high leverage"""

            await self.send_message(chat_id, msg)
        except (ValueError, IndexError):
            await self.send_message(chat_id, "❌ Usage: `/dynamic_sl LONG [pct] [leverage]`")
        except Exception as e:
            await self.send_message(chat_id, f"❌ Error: {e}")
        self.commands_used[chat_id] = self.commands_used.get(chat_id, 0) + 1

    async def start_telegram_polling(self):
        """Start Telegram bot with polling (optional — scanner also polls)"""
        try:
            try:
                from telegram.ext import Application, CommandHandler
                from telegram import Update
            except ImportError:
                self.logger.info("python-telegram-bot not installed — using built-in polling")
                return True  # Fall back to built-in scanner polling

            if not self.bot_token:
                return False

            application = Application.builder().token(self.bot_token).build()

            # Register all commands dynamically (skip /start — handled by TradingInterface)
            for cmd_name in self.commands.keys():
                if cmd_name in ("/start", "/menu"):
                    continue
                cmd_key = cmd_name.lstrip("/")
                cmd_fn  = self.commands[cmd_name]

                def make_handler(fn):
                    async def handler(update: Update, context):
                        try:
                            await fn(update, context)
                        except Exception as e:
                            self.logger.error(f"Handler error: {e}")
                    return handler

                application.add_handler(CommandHandler(cmd_key, make_handler(cmd_fn)))

            # ── Attach TradingInterface to PTB Application (registers all handlers) ──
            try:
                _ti = getattr(self, "trading_interface", None)
                if _ti is None:
                    from SignalMaestro.trading_interface import get_trading_interface
                    _ti = get_trading_interface(engine=self)
                    self.trading_interface = _ti
                _ti.attach(application)
                self.logger.info("✅ TradingInterface attached to PTB Application (InlineKB·CCXT·QuantMath·UserDB)")
            except Exception as menu_err:
                self.logger.warning(f"⚠️ TradingInterface PTB attach failed (slash commands still active): {menu_err}")

            self.telegram_app = application
            await application.initialize()
            await application.start()
            if application.updater:
                await application.updater.start_polling(drop_pending_updates=True)
            self.logger.info(f"✅ Telegram polling started ({len(self.commands)} commands)")
            await self.send_status_update("🚀 BTCUSDT MiroFish Bot commands active!")
            return True

        except Exception as e:
            self.logger.warning(f"Telegram polling setup failed (using fallback): {e}")
            return True  # Non-fatal — scanner built-in polling handles updates


# ─────────────────────────────────────────────
# Standalone entry point
# ─────────────────────────────────────────────

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    bot = FXSUSDTTelegramBot()
    try:
        bot.logger.info("🤖 Starting Telegram command system...")
        telegram_success = await bot.start_telegram_polling()
        if not telegram_success:
            bot.logger.warning("⚠️ Telegram polling setup failed — using built-in scanner polling")
        bot.logger.info("🐟 Starting MiroFish continuous scanner...")
        await bot.run_continuous_scanner()
    except KeyboardInterrupt:
        bot.logger.info("👋 Bot stopped")
    except Exception as e:
        bot.logger.error(f"Critical error: {e}")
        raise
    finally:
        await bot.close_tg_session()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "current event loop" in str(e):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(main())
        else:
            raise
