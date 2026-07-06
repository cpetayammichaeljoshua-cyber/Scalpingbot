---
name: Unity Engine v229.0 — G8.5C4 cold-start recording gap
description: G8.5C4 (AEV AdaptiveEV-Persistence) cold-start else branch set sentinel to 0 but never updated _gate_stats/_gate_stats_recent; gate invisible in bottleneck analytics before ev_ring warmed up; fix matches v143.1-FIX pattern already in D4/E4/F4/H4/J4.
---

## Bug

G8.5C4 (AEV AdaptiveEV-Persistence, line ~17670):

```python
else:
    self._last_g85c4_aev = 0  # cold-start
    # NO _gate_stats update here — gate invisible in analytics
```

When `ev_ring` has < 10 resolved trades (cold-start), the gate's sentinel is correctly
set to 0 (neutral), but neither `_gate_stats["gate_g85c4_aev"]` nor
`_gate_stats_recent["gate_g85c4_aev"]` is updated. This means the gate shows zero
calls in bottleneck analytics (`/gates`) until the ring warms up — typically ~10 trades
after each engine restart.

## Impact

- **Filtering**: None — `_last_g85c4_aev = 0` is neutral; Kelly Step 81 reads 0 → no
  de-size/boost. Signal quality is unaffected.
- **Analytics**: Gate appears dead (0 calls) in `/gates` endpoint for the first ~10
  resolved trades after restart. This can mislead the bottleneck diagnostic view.

## Fix

```python
else:
    self._last_g85c4_aev = 0  # cold-start
    # v229.0-FIX: cold-start path not recorded (gate invisible before ev_ring ≥ 10).
    # D4/E4/F4/H4/J4 all have this same fix (v143.1-FIX); C4 was missed.
    self._gate_stats["gate_g85c4_aev"]["pass"] += 1
    self._gate_stats_recent["gate_g85c4_aev"].append(True)
```

## Context / False Positives Found

Comprehensive bug-hunt pass that preceded this fix investigated:
- **Gate 10 (IRONS) exception path**: `except Exception` calls `self._record("gate10", True)` — no gap. ✅
- **G8.5G4 (SVTFC) cold-start**: Recording block is at 12-space indent (outside the 16-space Sharpe-computation `if _g4_pnl_list` block) — always runs. NOT a bug. ✅
- **CORR sentinel pool**: G8.5BA–BI (v172–v175) + G8.5BI GSEV (v201) all present in `_corr_sentinels` at lines 20453–20457. Complete at 109 sentinels. ✅
- **All overscoring paths**: DBT/_sim/_fac WR-dampened (v204), Markov WR-dampened (v200), all soft-gate bonuses WR-dampened (v198). ✅
- **Walk-forward validation**: CPCV K=3 present, temporal splits, no look-ahead bias. ✅
- **All banners**: 177-gate, Steps1-162, v228.0 correct at time of scan. ✅

## Pattern Note

Cold-start recording gaps in gates with explicit ring-size outer else branches:
- These are missed when the inner recording block is inside the `if ring >= N:` block
  but the outer `else:` (cold-start) only sets the sentinel.
- Pattern to check: any gate with `else: self._last_gXXX = 0  # cold-start` and no
  `_gate_stats` update in that same else block.
- The v143.1-FIX style (add `_gate_stats[key]["pass"] += 1` + `_gate_stats_recent[key].append(True)`) is the established pattern for these.
