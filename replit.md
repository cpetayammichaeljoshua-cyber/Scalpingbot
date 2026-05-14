# Unity Engine — Sovereign CCXT Trading Bot

A comprehensive 21-layer autonomous trading signal engine for Binance USDM Futures, broadcasting high-conviction signals via Telegram with institutional-grade risk management.

## Run & Operate

```bash
python3 start_unity_engine.py   # main launcher (auto-restarts up to 100×)
```

**Workflows:** `python3 start_unity_engine.py` · `Unity Engine` (identical commands)
**Health endpoint:** `http://localhost:8080/health` (JSON status + gate pass-rates)
**Required env vars:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `OPENROUTER_API_KEY` (primary LLM); optional: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `REDIS_URL`

## Stack

- **Runtime:** Python 3.11.14 · uvloop (2-4× faster event loop)
- **ML/AI:** torch 2.4.0+cpu · transformers 5.8.0 · scikit-learn 1.8.0 · numpy 2.4.4 · pandas 3.0.2
- **Network:** aiohttp 3.13.5 · python-telegram-bot 22.7 · openai 2.34.0
- **Storage:** aiosqlite (SQLite TradeMemory) · orjson (fast JSON) · Redis (optional state cache)
- **Quant:** scipy 1.17.1 · ccxt · vaderSentiment · textblob · rank-bm25

## Where things live

```
start_unity_engine.py              # ~11,750-line master engine (v18.15)
SignalMaestro/                     # All AI/ML signal modules
  fxsusdt_telegram_bot.py          # Bot scanner + NN gate + signal pipeline
  neural_signal_trainer.py         # PyTorch Transformer + BitNet MLP
  ai_capability_checker.py         # Dependency/capability reporter (v5.0)
  backtest_overfitting_analyzer.py # PBO / Walk-Forward / DSR
  scan_cycle_matrix.py             # ScanCycleMatrix numpy pre-filter (v18.13)
aegis_gex/
  dynamic_backtester.py            # Per-symbol EMA/RSI backtest + PBO
  gex_engine.py                    # GEX / gamma exposure engine
  depth_slippage.py                # Depth-walked slippage estimator
requirements.txt                   # Pinned dependencies
nixpacks.toml                      # Railway build config with torch CPU install
```

## Architecture decisions

- **21-layer filter cascade**: Layer 0 (GEX/Deribit/OKX) → Layer 11 (Telegram) — each layer degrades gracefully if unavailable; no single failure kills signals
- **14-gate quality filter**: EV>0 → Session → MinTP1 → RR≥1.85 → Swarm≥95% → AI≥RL-threshold → NN → ATAS/Bookmap → Fear&Greed → GEX regime → PerSymbolWR → DynBacktest+PBO → QualityFloor≥59 → IRONS≥62
- **5-bucket RL threshold**: WR-adaptive AI confidence gate prevents trading through losing streaks; Kelly + Sortino/Calmar/Omega overlays for sizing
- **PBO anti-overfitting**: Walk-Forward Ratio + Bootstrap PBO + Deflated Sharpe integrated into Gate 8.5 — penalises curve-fitted proxy results -3 to -5 pts before quality gate
- **Starvation guards (v18.15)**: `_signal_drought_seconds()` wired into Gate 0 EV floor, Sortino EV escalation, Sortino quality penalty, and G0.5 dead-zone veto — breaks compounding death spiral at 60min+ drought

## Product

- Scans 50+ Binance USDM symbols every 12–25 seconds across 21 intelligence layers
- Sends Telegram signals with TP1/TP2/TP3, SL, Kelly position size, and regime context
- Tracks outcomes, retrains NN every 2h (45min in losing regime), adapts thresholds via 5-bucket RL
- `/status`, `/metrics`, `/gates`, `/layers`, `/pbo` Telegram commands for live monitoring
- Health check server on :8080 for uptime monitoring

## User preferences

- Production-grade deployment; all bugs hunted and fixed before delivery
- pytorch_transformers must show FULL (0.90), not DEGRADED (0.75)
- sklearn 0.75 is the correct MAX score for the sklearn tier — NOT degraded
- Backtesting overfitting probability must be integrated and visible in logs
- Workflow named exactly "python3 start_unity_engine.py" must exist

## Gotchas

- `torch` requires `--index-url https://download.pytorch.org/whl/cpu` — standard PyPI does NOT have the CPU wheel; nixpacks.toml handles this for Railway
- `aiohttp` must be installed — L11 (TelegramBot) and L0.5/L0.6/L0.8 depend on it
- `UNITY_DBT_ENABLED=1` (default) triggers DynamicBacktester which requires aiohttp + numpy
- PBO penalty fires only when ≥20 trades are in the proxy backtest result — cold-start is neutral
- `_writable_path()` always used for persistence files — never hardcode `/app/...` paths
- Quality bias range is [-13, +5] (was [-8, +5]) after PBO penalty in v18.11
- Starvation guard `_filter_wired_at` set at engine init; `_signal_drought_seconds()` uses session age when deque is empty — guards fire correctly even with zero historical signals this session

## Pointers

- Capability checker: `SignalMaestro/ai_capability_checker.py` (v5.0)
- Neural trainer: `SignalMaestro/neural_signal_trainer.py` (PyTorch Transformer + BitNet)
- PBO analyzer: `SignalMaestro/backtest_overfitting_analyzer.py` (v1.0)
- DynBacktester: `aegis_gex/dynamic_backtester.py` (v9.9.2 + PBO)
- Kelly engine: `start_unity_engine.py` class `UnityProfitBooster`
- Starvation guards: `UnitySignalFilter.set_signal_times()` + `_signal_drought_seconds()`
