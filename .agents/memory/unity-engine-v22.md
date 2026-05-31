---
name: Unity Engine v22.0–v28.0 upgrades
description: v22–v28 key changes: v28.0 klines Semaphore(8) 429-storm fix + cache TTL 180s + fxsusdt retry; v27.0 qwen slug fix; v26 GODMODE 11combos; v22–v25 gates/RL/NN/HTTP fixes.
---

## v28.0 Key Changes (deployed 2026-05-31)

### Klines 429 Storm Elimination (`btcusdt_trader.py`)
**Root cause:** 76 symbols × multiple timeframes all fire `get_klines()` via `asyncio.gather()` simultaneously → Binance klines endpoint returns HTTP 429 every scan cycle (visible in Railway logs as "backing off 5s" on every cycle).

**Fix — module-level lazy semaphore:**
```python
_KLINES_SEMAPHORE: Optional["asyncio.Semaphore"] = None

def _get_klines_semaphore() -> "asyncio.Semaphore":
    global _KLINES_SEMAPHORE
    if _KLINES_SEMAPHORE is None:
        _KLINES_SEMAPHORE = asyncio.Semaphore(8)
    return _KLINES_SEMAPHORE
```

**Fix — `get_klines()` tail replaced with semaphore wrapper:**
```python
async with _get_klines_semaphore():
    return await self._do_fetch_klines(sym, interval, limit, cache_key, now)
```

**New `_do_fetch_klines()` method** contains Phase 1 (FAPI endpoints) + Phase 2 (SPOT fallback). Cache hits bypass the semaphore entirely — only cache-miss paths are rate-limited.

**Exponential backoff for 429:** `min(60, _retry_base × 2^attempt + attempt)` — prevents thundering-herd re-retry.

**Why:** Semaphore(8) caps concurrent klines to 8. Remaining 68 callers queue behind, reducing Binance API pressure from ~76 simultaneous to ≤8 simultaneous — eliminates 429 storms.

### Klines Cache TTL 120s → 180s (`btcusdt_trader.py`)
`self._klines_cache_ttl = 180.0` — 50% more cache reuse per cycle, further reduces API calls without data staleness (candles only close every 15m–4h).

### fxsusdt_trader.py: 429 Retry with Exponential Backoff
Old `get_klines()` had no retry — silently returned `[]` on rate-limit. New version loops `_max_attempts=3` with `min(60, _retry_base × 2^attempt + attempt)` backoff.

---

## v27.0 Key Changes (deployed 2026-05-31)

### GODMODE_QWEN_SYSTEMATIC slug fix (`godmod3_strategy.py`, `smart_llm_router.py`)
`qwen3-next-80b-a3b-instruct:free` → `qwen/qwen3-72b:free` everywhere.
Root cause: no such model exists in Qwen3 lineup → 13 consecutive rate_limit errors → 960s disabled. See `unity-engine-v27-slug-fix.md`.

---

## v26.0 Key Changes (deployed 2026-05-31)

### GODMODE 9→11 Combos (`SignalMaestro/godmod3_strategy.py`)
Two new combos added to `GODMODE_COMBOS` list:

**10th: GODMODE_QWEN235B_SOVEREIGN** — `qwen/qwen3-235b-a22b-instruct:free`
- TradingAgents/SEC-EDGAR-inspired 4-step synthesis: institutional-flow → fundamental-catalyst → technical-structure → risk-weighted verdict
- 235B MoE flagship; largest model in the ensemble

**11th: GODMODE_GEMMA26B_VIBE** — `google/gemma-4-26b-a4b-it:free`
- HKUDS/Vibe-Trading IC/IR factor: momentum+volatility+volume+quality each scored ±1; net ≥+2→BUY, ≤-2→SELL
- Distinct from gemma-4-31b (GODMODE_OPENBB_MACRO) for true ensemble diversity

**Why:** Maximum model diversity reduces correlated errors. 11 distinct free-tier confirmed models vs 9. The two new combos cover angles not previously represented (sovereign multi-factor institutional + IC/IR factor scoring).

**How to apply:** Add both dicts before the closing `]` of `GODMODE_COMBOS`. Update header comment "9 combos"→"11 combos". Version string also confirms count at boot: `G0DM0D3 Engine initialised | GODMODE combos: 11 (11 distinct models)`.

### G2 Drought Relief (`evaluate_signal` G2 gate block)
After the WR-adaptive `_g2_min` tiers, before `passed_g2 = consensus >= _g2_min`:
```python
try:
    if self._booster is not None:
        _g2_drought_sec = self._signal_drought_seconds()
        if _g2_drought_sec > 1200:   # 20min drought
            _g2_sr = float(getattr(self._booster, "sharpe_ratio", 0.0) or 0.0)
            if _g2_sr < -4.0:
                _g2_min = max(0.93, _g2_min - 0.01)   # 1pp crisis drought relief [v26.0]
except Exception:
    pass
```
**Why:** At crisis (Sharpe<-4) + 20min drought, consensus gate fires at 0.95 (9.5/10 agents). A 1pp relaxation to 0.93 (9.3/10) gives ~5% more signals through G2 without material noise increase. 20min drought means every other gate has been rejecting for 20 consecutive minutes — G2 is likely the blocking bottleneck.

### EV Floor 15-Minute Crisis Tier (G0 gate, `_ev_floor` calculation)
Added between the 20min tier (1.05×) and the 10min tier (1.10×):
```python
elif _drought_ev > 900:   # NEW 15min tier
    _ev_floor = min(EV_MIN_THRESHOLD * 1.07, EV_MIN_THRESHOLD + 0.0002)
```
**Why:** Smooth monotonic EV relief curve: 10min=1.10× (24.2bps) → 15min=1.07× (23.5bps) → 20min=1.05× (23.1bps) → 45min=1.02× (22.4bps). Old curve had a step from 1.05→1.10 with no intermediate tier.

---

## v25.0 Key Changes (deployed 2026-05-31)

### RL Delta Sharpe-Aware Scaling (`_update_threshold_rl` in UnityProfitBooster)
Added after the bucket loop, before starvation-decay:
```python
if delta > 0.0:
    _delta_sr = float(getattr(self, "sharpe_ratio", 0.0) or 0.0)
    if _delta_sr < -5.0:
        delta *= 0.55   # ultra-ruin: heavy suppression
    elif _delta_sr < -4.0:
        delta *= 0.75   # crisis: moderate suppression
```
**Why:** At Sharpe=-4.87 WR<30%, bare delta=+1.5 → threshold=88.5%. With scaling: +1.5×0.75=+1.125 → 87.8%.
Negative deltas (good-WR threshold lowering) are never scaled — winning streaks exploit fully.

### RL Bucket WR 30-35% Recalibration (`_RL_BUCKETS`)
`(0.30, 0.35, +1.0)` → `(0.30, 0.35, +0.75)`

**Why:** WR=30-35% at RR=2.35 is EV-POSITIVE (EV=0.00R to +0.17R). Old +1.0 delta treated these
break-even signals as near-bad, raising threshold unnecessarily. +0.75 still selective but accurate.

### G3 DroughtRelax Crisis Threshold (`evaluate_signal` G3 gate)
Added crisis-aware drought window before the drought check:
```python
_g3_sr = float(getattr(self._booster, "sharpe_ratio", 0.0) or 0.0) if self._booster else 0.0
_g3_drought_threshold = 900.0 if _g3_sr < -4.0 else 1200.0   # 15min crisis, 20min standard
if _g3_drought_sec > _g3_drought_threshold:
    ...
```
**Why:** At Sharpe=-4.87, 20min window forced 5 extra minutes of starvation before relax fired per drought
epoch. 15min recovers ~0.3 signals/session/epoch at 4 signals/hr. Standard regimes still 20min.

### NN Deep-Crisis Retrain Tier (`_nn_retrain_task`)
Added new tier between ultra-crisis (<-5.0, 15min) and crisis (<-3.5, 20min):
```python
elif _crisis_sharpe < -4.5:
    _sleep_sec = 900   # 15min deep-crisis [v25.0]
```
**Why:** Sharpe -4.5 to -5.0 was previously "crisis-20min" but at Sharpe=-4.87 it's functionally
equivalent to ultra-ruin. 15min retrain = +33% faster NN adaptation.

### MODEL_COSTS Dead Model Cleanup (`smart_llm_router.py`)
Removed `tngtech/deepseek-r1t-chimera:free` and `deepseek/deepseek-r1-0528:free` from MODEL_COSTS dict.

---

## v24.0 Key Changes (deployed 2026-05-31)

### HTTP 202 Klines Soft-Skip (btcusdt_trader.py + fxsusdt_trader.py)
**Root cause:** Binance FAPI returns HTTP 202 for symbols in pre-delivery/maintenance/delist state.
Previously logged as ERROR → Railway log flood (1440+/hr).

**Fix:** `if r.status == 202: return None` (DEBUG log, not ERROR). 5xx/4xx → WARNING.

**How to apply:** Railway still needs git push to redeploy — old Railway deployment predates v24.0.

---

## v23.0 Key Changes (deployed 2026-05-31)

### G4 Pessimism-Aware Threshold Relief
Only fires when `_g4_pess_wr < 0.35`. Relief = `max(0, 0.02 × (1 - min(1, edge/0.10)))`.
Floor: `NN_WIN_PROB_GATE - 0.06`. At edge=0pp: 0.02pp relief. At edge≥10pp: 0.

### G9 WR Recovery Bonus
At WR≥42% AND positive Sharpe AND ≥15 samples: `_g9_floor -= 1.0`.

---

## v22.0 Key Changes (deployed 2026-05-31)

### NN Pessimism Correction (fxsusdt_telegram_bot.py)
`_floor_reduction = 0.07 × (1 - min(1, edge/0.10))` — absolute_floor 20%→16% at edge=4pp.
Cooldown 10min→3min when `_floor_reduction > 0.02`.

### G0 EV Quality Uplift
`_ev_q_uplift = min(0.030, max(0.0, (confidence - 75.0) / 833.0))` — adds +0→+3pp to p_win.

### CONSORTIUM Request Stagger (0.5s between models), HMM Contra-Regime -3→-4pts.
