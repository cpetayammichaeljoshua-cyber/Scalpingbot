---
name: Unity Engine v146.0 upgrades
description: MEXC USDM Futures cross-exchange confluence hard-block gate + performance parameter tightening
---

## Key Changes

**Version:** 145.0 → 146.0

**MEXC Cross-Exchange Confluence Gate (Phase 1.95 HARD-BLOCK)**
- Added in `SignalMaestro/fxsusdt_telegram_bot.py` between Phase 1.9 (StochasticQuant) and Phase 2 (NN pre-gate)
- Fetches MEXC 15m klines for the same symbol (`BTCUSDT` → `BTC_USDT`) using the existing trader session
- Calculates EMA(8) vs EMA(21) with 0.15% separation threshold to call trend
- HARD-BLOCK if MEXC trend strongly diverges from signal direction (BULL vs SHORT or BEAR vs LONG)
- +2.5pt quality bonus if MEXC CONFIRMS the signal direction
- Fail-open: any network error → gate skipped silently (no block)
- Env gate: `UNITY_MEXC_GATE=0` to disable (default: enabled)
- Rationale: memory lesson "only HARD-BLOCK moves signal WR/Sharpe/maxDD"

**Performance Parameters Tightened**
- `AI_THRESHOLD_PERCENT`: 91 → 92
- `SWARM_MIN_CONSENSUS`: 0.96 → 0.97 (9.7/10 MiroFish agents required)
- `NN_WIN_PROB_GATE`: 0.53 → 0.56 (filters 53-56% marginal NN band)
- `EV_MIN_THRESHOLD`: 0.0060 → 0.0065 (60 → 65 bps)

**MEXC Trader Methods Added (`SignalMaestro/fxsusdt_trader.py`)**
- `FXSUSDTTrader.binance_to_mexc_symbol(sym)` — static, e.g. `BTCUSDT → BTC_USDT`
- `get_mexc_klines(symbol, interval, limit)` — public MEXC futures klines
- `get_mexc_ticker(symbol)` — public MEXC futures ticker
- `get_mexc_symbols()` — list all active MEXC USDM perpetuals
- `MEXC_FUTURES_URL = "https://contract.mexc.com"`
- MEXC kline interval format: `Min15`, `Min30`, `Hour1` (not `15m`)
- MEXC response shape: `data.close[]`, `data.open[]`, `data.high[]`, `data.low[]`

**Exchange Labels Updated**
- `SignalMaestro/irons_ai_scorer.py` line ~942: `"Exchange: Binance Futures"` → `"Exchange: Binance & MEXC USDM Futures"`
- `SignalMaestro/fxsusdt_telegram_bot.py` fallback format: same update
- Bot `/start` and `/market` and `/watchlist` messages updated to mention MEXC

**Why HARD-BLOCK not quality penalty:**
Memory lesson (v145.0): "for a SIGNAL bot only HARD-BLOCK (not Kelly de-size) moves signal WR/Sharpe/maxDD because de-sized bad signals still fire"

**MEXC API notes:**
- Public endpoints (no auth): `https://contract.mexc.com/api/v1/contract/kline/{symbol}`
- Symbol format uses underscore: `BTC_USDT` not `BTCUSDT`
- Success check: `data.get("success") or data.get("code") == 0`
- Kline data lives in `response["data"]["close"]` (list of floats)
