# MiroFish Swarm Intelligence Trading Bot — ALL USDM Markets

## Project Overview
A production-grade Binance USDM Perpetual Futures signal bot powered by the **MiroFish Multi-Agent Swarm Intelligence** strategy (github.com/666ghj/MiroFish). Scans **up to 80 USDM Perpetual Futures symbols in parallel** on the **15-minute timeframe** using 9 specialized AI agents. Sends Cornix-compatible trading signals to @ichimokutradingsignal.

## Bug Fixes & Enhancements (Session 9 — Current)

### `SignalMaestro/fxsusdt_telegram_bot.py` — Duplicate `close_tg_session` (CRITICAL)
- **ROOT CAUSE**: Two definitions of `close_tg_session` existed (lines 475–509 and 528–534). Python's class body executes sequentially — the second shorter definition at line 528 overwrote the first full version, stripping out:
  - `telegram_app` updater/shutdown (leaked PTB Application)
  - `_outcome_tracker_task` cancellation (leaked OutcomeTracker background coroutine)
- **FIX**: Removed the second, shorter duplicate definition (lines 528–534). The first full version (lines 475–509) is the canonical `close_tg_session`.

### `SignalMaestro/mirofish_swarm_strategy.py` — Claude Model Cascade Expanded (7 models)
- **ROOT CAUSE**: All 3 original cascade models returned 404 (account plan doesn't have access to those specific versioned Claude model IDs). The cascade was exhausted immediately, permanently disabling Claude on every run.
- **FIX**: Expanded `_CLAUDE_MODELS` from 3 → 7 models in order: `claude-3-7-sonnet-20250219` (Feb 2025 release), `claude-3-5-haiku-20241022`, `claude-3-5-sonnet-20241022`, `claude-3-5-sonnet-20240620`, `claude-3-haiku-20240307`, `claude-3-sonnet-20240229`, `claude-3-opus-20240229`. Any plan tier should find at least one accessible model.
- **FIX**: Added periodic 30-minute retry mechanism (`_CLAUDE_MODEL_RETRY_INTERVAL = 1800.0`). When `_claude_perm_disabled=True`, the check expires every 30 min, clears `_claude_failed_models`, and re-tests the full cascade — enabling automatic recovery after an account upgrade without a bot restart.

### `SignalMaestro/mirofish_swarm_strategy.py` — Rule-Based AI Fallback Overhauled (win rate)
- **ROOT CAUSE**: The old `_rule_based_analysis` used only agent vote counts with a simple confidence formula. When both Claude and OpenAI are unavailable (current state), every signal went through this path — making it the primary AI signal for all production signals.
- **FIX — Multi-layer technical confirmation**: RSI overbought/oversold, MACD histogram direction, and Bollinger band position now independently confirm or veto the rule-based vote. RSI overbought into a BUY (or oversold into a SELL) hard-vetoes the signal to prevent buying tops/selling bottoms.
- **FIX — Stricter quorum raised 3 → 4**: Requires 4 agents to agree (vs 3) before going directional.
- **FIX — Dominant-side margin gate**: Winning side must score ≥60% of total agent score (vs no gate). Thin-margin setups return NEUTRAL instead of marginal direction.
- **FIX — Confidence cap raised 82 → 88**: Allows genuine high-conviction setups (5+ aligned agents, RSI confirms, MACD confirms) to reach the 80% confidence gate more reliably.
- **FIX — Momentum uses 5-bar + 8-bar dual slope**: More robust than single 4-bar slope; both must confirm direction for a bonus.
- **FIX — 1H change scaled by magnitude**: Tail-wind bonus now `+6pt` for >1.5% move (vs flat `+4pt`) and `+3pt` for >0.5%; head-wind applies `-4pt` penalty.
- **FIX — Unanimity bonus for ≥5 aligned, 0 contrary**: `+4pt` bonus applied to unanimous large-quorum setups.

### `SignalMaestro/mirofish_swarm_strategy.py` — Signal Quality Gate Tightening (win rate)
- **FIX — `min_swarm_consensus` raised 0.72 → 0.75**: Requires 75% weighted consensus (vs 72%) before a signal is emitted. Reduces marginal-consensus signals.
- **FIX — `min_rr_ratio` raised 1.50 → 1.55**: Rejects signals with R:R below 1.55:1 (using TP2 as reward target).
- **FIX — Extreme volatility filter tightened 4% → 3%**: ATR > 3% of price now rejects the signal (was 4%), avoiding erratic alt-coin high-volatility signals.
- **FIX — Bollinger Band width chop filter added**: New pre-signal filter: when BB width < 0.5% of price (extreme compression/chop), direction is unknowable and signal is rejected. This prevents entering positions ahead of unpredictable breakouts.

### Production Validation (Session 9)
- 47 USDM symbols scanned in **4.6s** (parallel mode confirmed)
- Consensus gate confirmed: **75%** in logs
- First signal: UAIUSDT SELL — 9/9 agents unanimous, consensus=100%, conf=84.8%
- Symbol blacklist: RIVERUSDT, TRUMPUSDT, ZECUSDT auto-blocked (recent_loss_rate ≥ 70%)
- OutcomeTracker background task started cleanly (duplicate-bug fix verified)

## Bug Fixes & Enhancements (Session 8)

### `SignalMaestro/neural_signal_trainer.py` — `_save_weights` float32 serialization (critical)
- **ROOT CAUSE**: `danger_zones` tuples contain NumPy float32 bin-edge values from ndarray slicing (`lo`, `hi`); `feature_importance` is a plain Python `list()` of NumPy float32 scalars from `abs(win_mean - loss_mean) / ...`; several scalar fields (`class_weight_loss`, `_w_win`, `_w_loss`, etc.) may be float32 from NumPy arithmetic. `json.dump` raises `TypeError: Object of type float32 is not JSON serializable` on all of these.
- **FIX**: All fields in the `data` dict now use explicit Python-native casts:
  - `danger_zones`: list comprehension `[int(fi), float(lo), float(hi), float(lr)]`
  - `feature_importance`: `[float(x) for x in ...]`
  - All scalar fields (`n_samples_trained`, `last_train_time`, `last_accuracy`, `last_val_loss`, `last_win_rate`, `last_loss_rate`, `_t`, `_base_lr`, `class_weight_loss`, `_w_win`, `_w_loss`, `_opt_threshold`, `_reject_threshold`, `_boost_threshold`, `_buy_prob_offset`, `_sell_prob_offset`): wrapped with `int()`, `float()`, or `bool()` as appropriate.
- **EFFECT**: NN weights now persist to `SignalMaestro/nn_weights.json` after every training cycle. The bot no longer loses all training (acc=75.1%, 240 samples, 20 danger zones) on restart.
- **LOAD COMPATIBILITY**: `_load_weights` already converts each `danger_zones` entry via `tuple(z)`, so list-of-lists format from the fixed save is fully compatible.

### `SignalMaestro/mirofish_swarm_strategy.py` — `AIOrchestrationAgent.analyze` or-pattern
- **FIX**: Replaced falsy `or` pattern (`_rsi() or 50.0`, `_stochastic() or 50.0`, `_atr_close() or fallback`) with explicit `None` checks in `AIOrchestrationAgent.analyze`. A valid RSI=0 (perfectly falling market) or Stochastic=0 (at period low) would previously be replaced with the default.

## Bug Fixes & Enhancements (Session 7)

### `SignalMaestro/neural_signal_trainer.py` (5 bugs fixed)
- **FIX 1 — Cosine LR uses `_base_lr`**: `_cosine_lr()` previously computed from `self.lr` which was being overwritten every epoch. Added `_base_lr = lr` snapshot on init; scheduler now reads `_base_lr` throughout all 400 epochs.
- **FIX 4 — z-score feature normalisation**: `_feat_mean` / `_feat_std` are now fit on training-fold data only (not val). `_feat_fitted` flag prevents double-fitting on retrain; inference path calls `_normalize_features()` consistently.
- **FIX 5 — Youden's J optimal threshold**: `_compute_optimal_threshold()` sweeps the validation ROC curve and picks `argmax(TPR + TNR - 1)`. Sets `_opt_threshold`, `_reject_threshold = opt - 0.10`, `_boost_threshold = opt + 0.10` to replace all hardcoded 0.40/0.70 literals.
- **FIX 6 — MC-Dropout 20-pass uncertainty**: Added `predict_mc()` (stochastic forward passes with dropout active) and `predict_signal_with_uncertainty()` returning `(mean_prob, std)`. High std + borderline probability triggers conservative rejection.
- **FIX 7 — Dynamic class weight from actual W/L ratio**: Class weight computed from `wins / losses` of training data, clamped to `[1.0, 5.0]`. Replaces the old hardcoded `1.5`.

### `SignalMaestro/trade_memory.py` (4 bugs fixed)
- **FIX 2 — `_last_train_count` only updates on successful training**: Counter was updated before the training call; if training threw an exception the counter still advanced, suppressing future retrain attempts.
- **FIX 3 — `MIN_RETRAIN_INTERVAL = 1800s` cooldown**: Prevents infinite retrain loops when model is already up-to-date. Timer only resets on success.
- **FIX 9 — `COALESCE(outcome_timestamp, timestamp)` for NULL ordering**: `get_recent_loss_rate()` was failing to sort NULL `outcome_timestamp` rows correctly, silently miscounting win rate.
- **FIX 8 (partial) — `get_symbol_stats()` method added**: Queries per-symbol resolved trade counts and recent loss rates for blacklist use.

### `SignalMaestro/fxsusdt_telegram_bot.py` (3 enhancements)
- **FIX 8 — Per-symbol blacklist (complete)**: `_symbol_blacklist` set, `_symbol_stats` dict, and `_refresh_symbol_blacklist()` method added. Symbols with recent_loss_rate ≥ 70% over ≥10 resolved trades are blocked automatically. Refresh is rate-limited to once per hour. Cleared/recovered symbols are logged.
- **FIX 5 wired — Optimal threshold gate**: `process_signals` now reads `self.nn_trainer._reject_threshold` / `_boost_threshold` instead of hardcoded 0.40/0.70.
- **FIX 6 wired — MC-Dropout in gate**: `process_signals` calls `predict_signal_with_uncertainty()`. Signals with `uncertainty > 0.15` AND within ±0.08 of the reject threshold are conservatively rejected.

### Production validation (first cycle after restart)
- 67 USDM symbols scanned in 4.0s (parallel mode)
- Blacklist correctly blocked BTCUSDT, RIVERUSDT, TRUMPUSDT (recent_loss_rate = 80%)
- ETHUSDT BUY signal sent at 87.1% confidence, swarm=89%
- Trade #224 recorded to SQLite

---

## Bug Fixes Applied (Production-Ready)
- **CRITICAL FIX** (`ai_enhanced_signal_processor.py`): Replaced invalid `from openai import analyze_trading_signal, analyze_sentiment, get_openai_status` (those functions don't exist in the openai package) with correct `AsyncOpenAI` client integration. Real GPT-4o-mini is now called when `OPENAI_API_KEY` is set; otherwise a rule-based fallback is used.
- **FIX** (`ai_enhanced_signal_processor.py`): Wrapped `from config import Config` in try/except for robustness.
- **All 7 core files pass syntax checks** — zero compile-time errors.

## Bug Fixes & Enhancements (Session 6 — Current)

### `SignalMaestro/mirofish_swarm_strategy.py`
- **FIX — `SentimentAgent` EMA falsy pattern (3 lines)**: `ema_9 = _ema(closes, 9) or cur` used Python's `or`, which treats `0.0` as falsy and would incorrectly substitute `cur` for a valid EMA of exactly 0.0. Changed to explicit `None` checks: `_e9 = _ema(closes, 9); ema_9 = _e9 if _e9 is not None else cur`. Same fix applied to `ema_21` and `ema_50`.
- **FIX — `VolatilityAgent` ATR `None` not guarded**: When `highs and lows` are provided, `_true_atr()` was called but its return value was used directly — however `_true_atr()` can also return `None` if data is insufficient. Changed to a proper fallback chain: `atr_val = ((_true_atr(...) if (highs and lows) else None) or _atr_close(closes, 14) or 0.0)`.
- **FIX — `MomentumAgent` graph node `macd_hist` `None` format crash**: `f"hist={macd_hist:.4f}"` raises `TypeError` when `macd_hist` is `None` (which happens if `_macd()` returns `(None, None)` for short klines). Fixed to `f"hist={(macd_hist or 0.0):.4f}"`.
- **ENHANCEMENT — `_adx()` wired into `VolatilityAgent`**: `_adx()` was fully implemented as a module-level helper but never called anywhere in the analysis pipeline (dead code). Now called inside `VolatilityAgent.analyze()`: ADX ≥ 25 (trending) boosts directional confidence by up to +6 pts; ADX < 20 (ranging) reduces over-confident calls by -3 pts.

### `start_ultimate_bot.py`
- **FIX — `SCANNER_HEARTBEAT_TIMEOUT = 300` was dead code**: The constant was declared in the launcher but never referenced — `run_continuous_scanner()` hardcoded `heartbeat_interval = 300` locally. Wired up by propagating `SCANNER_HEARTBEAT_TIMEOUT` as env var `HEARTBEAT_INTERVAL` via `os.environ.setdefault(...)`.

### `SignalMaestro/fxsusdt_telegram_bot.py`
- **FIX — Heartbeat interval now reads from env var**: `heartbeat_interval` in `run_continuous_scanner()` changed from the hardcoded `300` literal to `max(60, int(os.getenv("HEARTBEAT_INTERVAL", "300")))`, making it configurable from the launcher constant.

### `SignalMaestro/neural_signal_trainer.py`
- **FIX — `assert` in `build_features()` replaced with `ValueError`**: `assert arr.shape[0] == INPUT_DIM` can be silently disabled when Python runs with the `-O` (optimise) flag. Replaced with an explicit `if arr.shape[0] != INPUT_DIM: raise ValueError(...)` to ensure the check always fires in production.

---

## Bug Fixes & Enhancements (Session 5 — Historical)

### `SignalMaestro/mirofish_swarm_strategy.py`
- **FIX — TrendAgent graph node `above_200` crash**: `ema_200` can be `None` (intentional None-safe fallback for short history). The graph node `add_node` call passed `cur > ema_200` unconditionally, raising `TypeError`. Fixed to `(cur > ema_200) if ema_200 is not None else None`.
- **FIX — MomentumAgent MACD histogram over-boost**: `norm_hist * 50` multiplier on a normalised `%` value caused extreme confidence spikes on low-price alts (tiny absolute histogram ÷ tiny price = large pct). Reduced multiplier to 25 and capped boost at +8 pts (`min(norm_hist * 25, 8.0)`).
- **NEW — MomentumAgent: Williams %R** (`_williams_r`, period=14) — oversold (<-80) boosts BUY +4 pts; overbought (>-20) boosts SELL +4 pts.
- **NEW — MomentumAgent: Rate of Change** (`_roc`, period=10) — momentum-aligned ROC adds up to +5 pts.
- **NEW — MomentumAgent: RSI divergence** — bullish divergence (price new low + rising RSI) boosts BUY +5 pts; bearish divergence boosts SELL +5 pts.
- **NEW — TrendAgent: Ichimoku Tenkan/Kijun crossover** (`_tenkan_kijun`) — Tenkan above Kijun boosts aligned vote +6 pts, contra -4 pts.
- **NEW — VolumeAgent: VWAP deviation confirmation** — 20-bar VWAP alignment boosts signal +3 pts; price far on wrong side of VWAP penalises -5 pts.
- **NEW — OrderFlowAgent: inside bar, outside bar, tweezer top/bottom patterns** — each pattern adds ±7-12 pts.
- **NEW helpers added at module level**: `_williams_r`, `_roc`, `_adx`, `_tenkan_kijun`, `_hma` (all None-safe, fully type-annotated).

### `SignalMaestro/trade_memory.py`
- **FIX — `get_stats` wins query counted non-settled trades**: `WHERE pnl_pct > 0` was missing `outcome IS NOT NULL`, inflating win count with open positions. Fixed to `WHERE outcome IS NOT NULL AND pnl_pct > 0` (and symmetrically for losses).
- **NEW — Warm-restart incremental retraining**: `_maybe_retrain` now detects when there are <30 new labels since last train and passes `warm_restart=True` to `NeuralSignalTrainer.train()`, fine-tuning existing weights in 200 epochs instead of cold-starting in 300. Cold restart is preserved for large batches.

### `SignalMaestro/neural_signal_trainer.py`
- **NEW — `warm_restart` parameter on `train()`**: When `warm_restart=True` and the model is already trained, skips `_xavier_init()` to preserve learned weights and Adam momentum state. This avoids discarding all learned patterns on every small incremental retrain and converges 3-5x faster on small batches.

### `SignalMaestro/btcusdt_trader.py`
- **FIX — klines cache key collision** (strategy 250 bars vs boost 200 bars): Added cross-key cache lookup — if a cached result with the same `(symbol, interval)` has `limit >= requested_limit` and is still fresh, it returns a slice instead of making a duplicate API call. Eliminates ~50% of duplicate Binance klines fetches.

## Bug Fixes (Session 5)
All fixes verified with zero compile-time errors across all modified files.

### `SignalMaestro/fxsusdt_telegram_bot.py`
- **FIX — `_MAX_SIGNALS_PER_HOUR` capped to 5 regardless of `SIGNALS_PER_HOUR_MAX` env var**: `__init__` used `min(5, max(1, _sph_requested))` which silently discarded the launcher's `SIGNALS_PER_HOUR_MAX=8` setting, leaving the hourly cap always at 5. Changed to `min(20, max(1, _sph_requested))` so the env var is honoured. The class-level default attribute comment was also corrected.
- **FIX — `can_send_signal` log message hardcoded "5/5"**: The hourly cap log line read `({len(recent_1h)}/{self._MAX_SIGNALS_PER_HOUR} — 5/5)` with a literal "5/5" suffix that was always wrong when the cap was not 5. Removed the hardcoded suffix; count is now shown dynamically as `{len}/{cap}`.

### `SignalMaestro/trade_memory.py`
- **FIX — `get_stats_by_session()` used `pnl_pct > 0` for win counting**: Inconsistent with the already-fixed `get_stats()`. EXPIRED trades with ~0% PnL were miscounted as losses, inflating per-session loss rates. Fixed to `outcome IN ('TP1','TP2','TP3')` for wins and `outcome = 'SL'` for losses, matching every other stat method. Win-rate denominator now uses `resolved` (wins+losses) instead of `total`, excluding EXPIRED from the rate.
- **FIX — `get_symbol_stats()` aggregate query used `pnl_pct > 0 / <= 0`**: The bulk per-symbol query for overall `win_rate` and `losses` had the same `pnl_pct` bug. Fixed to `outcome IN ('TP1','TP2','TP3')` for wins and `outcome = 'SL'` for losses. Win-rate denominator uses `resolved` instead of `total`. The per-symbol `recent_loss_rate` sub-loop was already correct and left unchanged.

## Bug Fixes (Session 4 — Historical)
- **CRITICAL FIX — `openai.py` shadowing the real `openai` package**: Root-level `openai.py` was intercepting every `from openai import AsyncOpenAI` call in `mirofish_swarm_strategy.py`, `ai_enhanced_signal_processor.py`, `ai_sentiment_analyzer.py`, and `ai_capability_checker.py`, causing `ImportError: cannot import name 'AsyncOpenAI'`. This completely disabled the AIOrchestrationAgent's GPT-4o-mini ReACT mode. Fixed by renaming `openai.py` → `openai_handler.py`. Real openai v2.9.0 is now resolved correctly. Confirmed at runtime: `✅ AIOrchestrationAgent: OpenAI GPT-4o-mini ready (async ReACT mode)`.
- **FIX — `dynamic_signal_integrator.py` and `bot_health_check.py` broken imports**: Both used `from openai import get_openai_status` — a function that lives in the local `openai_handler.py`, not the real openai package. After the rename both were updated to `from openai_handler import get_openai_status`.
- **FIX — `can_send_signal` housekeeping placement** (`fxsusdt_telegram_bot.py`): The 24-hour `signal_timestamps` list cleanup ran AFTER the Tier-1 per-symbol cooldown and Tier-2a global-gap checks, meaning it was skipped whenever either guard returned `False`. Under sustained load where every symbol is in cooldown, the list could grow unboundedly. Moved the cleanup unconditionally to the top of the function so it always runs regardless of which rate-limit fires.

## Runtime Bug Fixes (Session 3)
All fixes verified with zero compile-time errors across all modified files.

### `SignalMaestro/btcusdt_trader.py`
- **FIX — Authenticated calls leaked connections**: `get_account_balance`, `get_positions`, `get_trade_history`, `get_leverage`, and `change_leverage` all created a fresh `aiohttp.ClientSession()` per call, bypassing the shared TCPConnector pool. Fixed to reuse `await self._get_session()` with per-request auth headers.
- **FIX — Klines double-fetch**: Added 90-second TTL klines cache (`_klines_cache`) keyed by `(symbol, interval, limit)`. `process_signals` in the bot re-fetches the same 200 klines the scanner just pulled; the cache eliminates this duplicate Binance API hit (halves API load per symbol per cycle).
- **FIX — SETTLING/BREAK symbols in scan universe**: `get_all_usdm_symbols` previously filtered only by name pattern (`endswith("USDT")`, no `_`). Now fetches `/fapi/v1/exchangeInfo` to build a `frozenset` of `contractType=PERPETUAL AND status=TRADING` symbols (cached 1 hour). Symbols in SETTLING or BREAK state are excluded. Ticker fetch and exchangeInfo fetch run concurrently via `asyncio.gather`.
- **NEW** — `_fetch_all_tickers()` and `_get_perpetual_trading_set()` helpers extracted for clarity and testability.

### `SignalMaestro/mirofish_swarm_strategy.py`
- **FIX — `AIOrchestrationAgent._react_log` concurrent modification**: Replaced `List[Dict]` + manual two-step trim (`append` then `self._react_log = self._react_log[-50:]`) with `collections.deque(maxlen=50)`. `deque` appends are atomic and auto-evict the oldest entry, eliminating the non-atomic check-and-slice pattern that could corrupt the list under parallel coroutine writes.
- **FIX — `chg_1h` off-by-one in all timeframes**: `_tf_1h_candles` lookback values were off by one (e.g. 15m lookback=4 gave `closes[-4]` vs `closes[-1]` = 3 intervals = 45 min, not 60). Fixed to `{1m:61, 3m:21, 5m:13, 15m:5, 30m:3, 1h:2, 4h:2}` so comparisons span the correct number of candle intervals (60 min for the primary 15m timeframe). This corrects the AI ReACT prompt's "1-hour change" narrative.

### `start_ultimate_bot.py`
- **FIX — `AsyncOpenAI` HTTP pool never closed**: The `AIOrchestrationAgent.openai_client` maintains an internal `httpx.AsyncClient`. On shutdown, only `bot.trader.aclose()` and `bot.close_tg_session()` were called. Added `await openai_client.close()` in the `finally` cleanup block via safe `getattr` traversal.

### `SignalMaestro/trade_memory.py`
- **FIX — Double `PRAGMA table_info` call**: `_init_db` ran `PRAGMA table_info(trades)` twice (once for the `symbol` column check, once for `partial_outcome`). Consolidated into a single call; both checks now share the same `existing_cols` set.

## Entry Point
- **`start_ultimate_bot.py`** — Main launcher with circuit breaker, exponential backoff, and auto-restart (100 max restarts)

## Active Configuration (15M)
| Parameter | Value |
|-----------|-------|
| Timeframe | 15M primary |
| Scan interval | 5–15s |
| Signal interval | 120s minimum |
| Signals/hour | 3–10 (cap 10/h) |
| Quorum | ≥5 of 8 agents must vote non-NEUTRAL |
| Consensus gate | ≥72% weighted (was 62%) |
| Pre-boost confidence | ≥64% (was 52%) |
| Post-boost confidence | ≥80% (was 74%) |
| Boost cap | +8pt max (was +12pt) |
| Min signal strength | ≥62% (was 52%) |
| Stop Loss | 0.65% base (ATR×1.5 scaled) |
| TP1 | 1.10% base (ATR×2.54 scaled, min 1.0%) |
| TP2 | 2.00% base (ATR×4.62 scaled, min 1.8%, always > TP1) |
| TP3 | 3.10% base (ATR×7.15 scaled, min 2.8%, always > TP2) |
| Min R:R | 1.50:1 (was 1.30, signals below rejected) |
| TP allocation | 45% / 35% / 20% |
| Global gap | 90s between signals (was 30s) |
| Micro-price filter | Skip symbols priced < $0.0001 |

## Architecture

### Core Strategy Engine
- **`SignalMaestro/mirofish_swarm_strategy.py`** — MiroFish Swarm Intelligence strategy (v3.1)
  - 8 specialized swarm agents with independent market analysis personas
  - Weighted consensus voting (≥72% agreement, quorum ≥5 of 8 agents)
  - Graph-state memory (500 nodes / 1000 edges, MarketEntityType ontology)
  - InsightForge sub-query decomposition + graph retrieval
  - ReACT pattern for AI orchestration (Reason→Act→Reflect→Conclude)
  - Session-aware agent weights (Asian/EU/US multipliers)
  - ATR-scaled SL/TP with guaranteed TP1<TP2<TP3 ordering
  - $0.10 tick size rounding for all price levels

### Swarm Agents & Weights (MiroFish Architecture)
| Agent | Focus | Weight |
|-------|-------|--------|
| TrendAgent | EMA 9/21 crossover + EMA200 + graph TrendState | 20% |
| MomentumAgent | RSI + MACD + IndicatorState graph node | 22% |
| VolumeAgent | OBV + volume surge + Catalyst node on 2x spike | 18% |
| VolatilityAgent | Bollinger Bands + ATR + PriceLevel nodes | 15% |
| OrderFlowAgent | Candle patterns + Pattern graph nodes | 15% |
| SentimentAgent | Fear/greed proxy + vol contraction regime | 5% |
| FundingFlowAgent | VWAP deviation + OI proxy + squeeze detection | 5% |
| AIOrchestrationAgent | GPT-4o-mini ReACT overlay | 5% |

### Market Connector
- **`SignalMaestro/btcusdt_trader.py`** — Binance USDM Futures REST API wrapper
  - Symbol: BTCUSDT Perpetual (fapi.binance.com)
  - Handles klines, pricing, account balance, positions, leverage, funding rate, OI

### Telegram Bot
- **`SignalMaestro/fxsusdt_telegram_bot.py`** — Signal bot and command handler
  - Class: `FXSUSDTTelegramBot`
  - Compact Cornix-compatible signal format (15 lines max)
  - Instance-level poll offset (no shared class-state bug)
  - Boost cap: +8pt maximum from optional analyzers (hard cap, was +12pt)
  - Signal deduplication: 120s cooldown
  - 30+ Telegram commands (/price, /scan, /swarm, /balance, /position, etc.)

### Signal Format (Compact Cornix-compatible)
```
🔴 #BTCUSDT SHORT
Exchange: Binance Futures
Leverage: Cross 10x

Entry Targets:
1) 84250.10

Take-Profit Targets:
1) 83323.00
2) 81560.20
3) 79642.30

Stop Targets:
1) 84798.40

⚡15M US · 87%🐟 · 82%Conf · RSI 65 · R:R 1:1.7
TP -1.1%/-2.0%/-3.1% · SL -0.7% · Tr:S Mo:S Vo:S Vl:S OF:S Se:S Fn:N AI:S · 14:58 UTC
📡 @ichimokutradingsignal | MiroFish Swarm
```

### Optional Enhancement Analyzers (graceful fallback, max +12pt boost total)
- `market_intelligence_analyzer.py` — Market intelligence (+8pt conf boost)
- `atas_integrated_analyzer.py` — ATAS order flow (+8–15pt conf boost)
- `insider_trading_analyzer.py` — Institutional activity detection (+6pt)
- `market_microstructure_enhancer.py` — Microstructure signals (+5pt)
- `smart_dynamic_sltp_system.py` — Dynamic SL/TP management
- `dynamic_position_manager.py` — Position sizing with ATR
- `bookmap_trading_analyzer.py` — Bookmap liquidity analysis

## Environment Variables / Secrets Required
| Secret | Description |
|--------|-------------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_CHANNEL_ID` | Signal channel ID (e.g. -1003031984142) |
| `TELEGRAM_CHAT_ID` | Admin personal chat ID |
| `OPENAI_API_KEY` | OpenAI API key for AI orchestration agent |
| `BINANCE_API_KEY` | Binance API key (read-only, for account data) |
| `BINANCE_API_SECRET` | Binance API secret |

## Key Quality Gates (Signal Flow)
1. **Micro-price filter**: Skip symbols priced < $0.0001
2. **Quorum**: ≥5 of 8 agents must provide non-NEUTRAL votes (was 3)
3. **Consensus**: ≥72% weighted agreement across all 8 agents (was 62%)
4. **Pre-boost confidence**: ≥64% (was 52%)
5. **Min signal strength**: ≥62% (was 52%)
6. **Optional boosts**: Up to +8pt from external analyzers (was +12pt)
7. **Post-boost confidence**: ≥80% (was 74%)
8. **R:R filter**: ≥1.50:1 minimum (was 1.30, strict rejection)
9. **Global rate limit**: 90s minimum gap between any two signals (was 30s)
10. **Hourly cap**: ≤10 signals/hour (was 20)
11. **Minimum TP distances**: TP1≥1%, TP2≥1.8%, TP3≥2.8%

## Bug Fixes (current version)
- TP ordering bug fixed: TP1<TP2<TP3 guaranteed via ratio-scaled ATR formula
- SL/TP rounded to Binance $0.10 tick size (not `round(x,2)`)
- Confidence boost capped at +8pt max to prevent inflation (was +12pt)
- Poll offset uses instance variable (not class-level shared state)
- Klines fetch uses 15m (not 5m) in boost analyzers
- Scan interval defaults: 5–15s
- Signal interval default: 120s (not 45s)
- Telegram polling handles HTTP 429, channel_post, and /command filtering
- ATAS 5-column data bug fixed → now 6-column [ts,open,high,low,close,volume]
- ATAS composite signal bug fixed: denominator now ALL indicators (not buy+sell only);
  previously 5B/1S/8N → 83% STRONG_BUY; now correctly 5/14 = 36% → NEUTRAL
- aiohttp bare-integer timeout bug fixed across all files
- Syntax error in telegram_strategy_comparison.py fixed (triple-quote escape)

## Bug Fixes (latest pass — comprehensive audit)
- **CRITICAL — process_signals lock scope**: `_signal_gate_lock` was held during ALL boost
  analysis (klines fetch, ATAS, MI, insider, microstructure — ~2-5s of network I/O per symbol),
  which serialised all 20 parallel scan coroutines into a single-file queue, destroying
  parallelism. Fixed: Phase-1 (boost analysis) runs outside the lock; Phase-2 (atomic
  can_send_signal → NN gate → final threshold → send → record) acquires the lock for
  milliseconds only.
- **CRITICAL — send_message throttle race**: `_tg_last_send_time` check-and-update had no
  asyncio lock. 20 parallel coroutines could all see gap < threshold simultaneously, all
  sleep the same duration, and all fire messages back-to-back causing HTTP 429 floods.
  Fixed: `_tg_send_lock = asyncio.Lock()` serialises the throttle section.
- **Outer exception circuit breaker bypass**: RuntimeError, CancelledError, ConnectionError,
  OSError, and generic Exception handlers in `main_launcher()` incremented
  `consecutive_failures` but never checked the circuit-breaker threshold — those handlers
  could loop indefinitely through catastrophic crashes. Fixed: all five except blocks now
  check and trip the circuit breaker on ≥5 consecutive failures.
- **Unclosed aiohttp sessions on shutdown**: `main()` `finally` block called `del bot`
  synchronously, leaving `_tg_session` and `trader._session` open. Fixed: properly calls
  `await bot.trader.aclose()` and `await bot.close_tg_session()` (new method) before `del`.
- **test_telegram_connection own session**: Created a fresh `aiohttp.ClientSession()` per
  call instead of reusing the shared `_tg_session`, triggering "Unclosed session" warnings.
  Fixed: uses `_get_tg_session()` shared session.
- **signal_timestamps unbounded growth**: Pruning from the 24h cutoff only happened when
  returning True, not when returning False — the list could grow indefinitely during
  quiet periods. Fixed: pruning runs unconditionally before the hourly-cap check.
- **AIOrchestrationAgent sync OpenAI in executor**: Used synchronous `OpenAI` client
  wrapped in `loop.run_in_executor()`, consuming thread-pool workers and defeating async
  concurrency (20 simultaneous scans exhausted the default 10-thread pool). Fixed:
  switched to `AsyncOpenAI` — no executor needed, fully native async.
- **VolatilityAgent ATR comparison incompatible windows**: `atr_now = _atr_close(closes, 7)`
  used ALL candles (Wilder-smoothed over hundreds of bars) while `atr_prev` used
  `closes[-20:]` (20 bars only), making the "expanding ATR" comparison meaningless.
  Fixed: both windows now use the same 14-bar length: `closes[-14:]` vs `closes[-28:-14]`.
- **FundingFlowAgent VWAP near-zero division**: `vwap_dev = (c[-1] - vwap) / vwap * 100`
  could produce infinity/NaN for micro-price tokens with VWAP ≈ 0. Fixed: guard
  `vwap = max(vwap, 1e-9)` applied before the division.

## Bug Fixes (session 3 — deep architecture audit)

- **CRITICAL — Shared `MarketGraphMemory` across 62 parallel symbol scans**: A single
  `self.graph` instance was shared across all symbol scans running concurrently via
  `asyncio.gather`. TrendState, RSI_State, VWAP_State, and PriceLevel nodes were being
  overwritten by whichever symbol scan ran last, causing cross-symbol contamination:
  BTCUSDT's TrendState could influence ETHUSDT's confidence scores, etc. Fixed: replaced
  `self.graph = MarketGraphMemory(500, 1000)` with `self._symbol_graphs: Dict[str, MarketGraphMemory] = {}`,
  allocating an isolated 200-node / 400-edge graph per symbol. Graph is lazily created on
  first scan and capped at 120 tracked symbols to bound memory. `_analyze_timeframe`
  accepts the per-symbol `graph` as a parameter (all 12 `self.graph` references replaced).
  `get_market_memory_summary` now aggregates across all symbol graphs.

- **CRITICAL — `_current_bb_position` race condition under parallel scans**: Phase 1
  (boost analysis, no lock) wrote `self._current_bb_position` as an instance attribute.
  With 20 concurrent coroutines, coroutine A would compute `bb_position=0.7` for ETHUSDT
  then yield control; coroutine B would overwrite it with `bb_position=0.3` for SOLUSDT;
  then coroutine A's Phase 2 (inside the lock) would read the wrong `0.3` value for the
  NN gate and trade memory record. Fixed: `_local_bb_position: float = 0.5` is now a
  local variable scoped to each coroutine invocation. It is passed explicitly to:
  (a) `self.nn_trainer.predict_signal(signal, _local_bb_position)` in Phase 2,
  (b) `self.send_signal_to_channel(signal, bb_position=_local_bb_position)` for recording.
  `send_signal_to_channel` now accepts optional `bb_position` parameter, using
  `self._current_bb_position` only as a standalone-call fallback.

- **`AIOrchestrationAgent` hardcoded "BTCUSDT" in InsightForge query**: The graph
  InsightForge query in `AIOrchestrationAgent.analyze` always searched for
  `"BTCUSDT {timeframe} trading signal"` regardless of which symbol was being scanned.
  This meant ETHUSDT, SOLUSDT, etc. always retrieved BTC-related graph facts for their
  AI context. Fixed: replaced `"BTCUSDT"` with the `symbol` parameter at the query call.

- **`MarketGraphMemory._find_node_by_name` O(n) linear scan on every `add_node` call**:
  With 62 symbols × 8 agents × multiple nodes per agent cycle, `_find_node_by_name`
  iterated all `_nodes` on every call (up to O(500) per lookup). Fixed: added
  `_node_name_index: Dict[Tuple[name, entity_type], uuid]` for O(1) reverse lookup.
  `add_node` now uses the index for update-or-create. `_prune_nodes` now also removes
  evicted node entries from the reverse index to prevent stale references.

- **`_prune_nodes` stale reverse index entries**: The previous `_prune_nodes` only
  `del self._nodes[k]` without cleaning `_node_name_index`. After pruning, a
  name-based lookup could return a UUID that no longer existed in `_nodes`, causing
  `_find_node_by_name` to return a ghost reference. Fixed: `_prune_nodes` now calls
  `self._node_name_index.pop((node.name, node.entity_type), None)` for each evicted node.
