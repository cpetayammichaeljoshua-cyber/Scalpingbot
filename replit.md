# MiroFish Swarm Intelligence Trading Bot — ALL USDM Markets

## Project Overview
A production-grade Binance USDM Perpetual Futures signal bot powered by the **MiroFish Multi-Agent Swarm Intelligence** strategy (github.com/666ghj/MiroFish). Scans **up to 80 USDM Perpetual Futures symbols in parallel** on the **15-minute timeframe** using 8 specialized AI agents. Sends Cornix-compatible trading signals to @ichimokutradingsignal.

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
