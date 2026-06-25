---
name: Unity Engine v148.0 structural R:R + behavioral circuit-breaker upgrades
description: Three data-grounded surgical changes targeting the realized R:R collapse and per-symbol streak losses — NOT gate-churn
---

## v148.0 Power-Mode Convictions (Fable 5 / Mythos 5)

### The Honest Data Picture
- Gate-churning has NOT moved outcome-WR off ~24–29% across 100+ versions
- RSI>70 filter = no-op (only 4 filtered in WF backtest — bot rarely takes them)
- Confidence score is MISCALIBRATED — 90%+ confidence has WORSE avgPnL than 70-80%
- swarm_consensus = dead column (all zeros — any gate on it is a no-op)
- The ONLY WF-validated edges: session + vol_spike (already live as hard-blocks)
- **Root cause: realized R:R collapse** (target 2.75, realized 1.46 long / 1.19 short)
- EXPIRED bleeders = 855/3298 trades (26%) — dilute realized R:R by running to ~zero P&L

### Changes

#### 1. MIN_TP1_DISTANCE_PCT: 0.50% → 0.65% (G0.8)
Directly attacks the EXPIRED bleeder problem. Setups with TP1 < 0.65% from entry:
- Get eaten by slippage (5-10bps) + spread before target is reached
- Time out as EXPIRED (zero P&L), diluting avgWin
Math: at 0.65% TP1 + RR=2.75, implied SL=0.24% — above round-trip friction cost.

#### 2. G4 WR-adaptive cap: add WR<30% tier → 0.50
Before: WR<25%→0.44 / WR<28%→0.46 / else→0.52
After:  WR<25%→0.44 / WR<28%→0.46 / **WR<30%→0.50** / else→0.52
At WR=29% we were in the 0.52 ("standard") band — now correctly in crisis tier 0.50.
Coherent with NN_WIN_PROB_GATE=0.58 (absolute gate already higher).

#### 3. GSLK Gate — Per-Symbol Streak-Loss Kill (Phase 2.0)
Position: Pre-Gate A1.5 — after GBLK, before GASN
Trigger: symbol.consecutive_losses ≥ 3 → 5400s (90min) per-symbol hard-block
Early exit: cancelled if consecutive_losses resets to 0 (a win occurred)
State: `self._slk_until: dict` (symbol → unblock_timestamp)
Stats key: `"gate_gslk"` in `_gate_stats`
Env override: `UNITY_GSLK=0` to disable
Uses existing `SymbolPerformanceTracker.consecutive_losses(symbol)` — zero new overhead
Comparison to GBLK: GBLK = long-run statistical block (≥20 trades, WR<25%); GSLK = fast-path current streak block (3 consecutive losses, any WR)

### UNITY_VERSION
147.0 → 148.0

### Architecture Principle (reinforced)
The data confirms: behavioral/circuit-breaker hard-blocks (session, vol_spike, GCLH, GSLK) are the only mechanisms that have shown structural impact. Quality threshold cranks on their own have not moved WR across 100+ versions.

### What Was NOT Done (and why)
- RSI>70 gate: only 4 signals filtered in WF backtest — near-zero impact
- Confidence ceiling: no WF validation for contrarian AI-score interpretation
- VOL_SPIKE_RATIO_THRESH 2.0→1.85: extrapolation beyond WF-tested boundary
- More quality gates: data explicitly says gate-churn hasn't worked
