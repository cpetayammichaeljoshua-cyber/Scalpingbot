---
name: Unity Engine v188.0 absence-bias + CPCV embargo fix
description: Four gate absence-bias removals (G4/G6/G7/G8) and CPCV K=3 embargo sync
---

# Unity Engine v188.0 — Absence-Bias Purge + CPCV K=3 Embargo Sync

## The rule
Gates that auto-pass when their data source is absent must contribute **0 quality points**, not a "neutral baseline" partial credit. Rewarding absent data inflates quality scores for cold-start / degraded-infra runs and systematically biases towards signals where fewer data layers are available.

**Why:** Identified via overcounting audit. G4/G6/G7/G8 were each awarding +7.5/+3.75/+1.5/+2.5 pts respectively when their input data was missing or errored. These additions compound: a signal with all four layers absent gets +15.75 "free" quality points before any real signal assessment. With `SIGNAL_MIN_QUALITY_GATE=73`, this creates a +15.75pt head start for data-poor signals — the exact opposite of desired behavior.

**How to apply:** Any new gate that auto-passes on missing data must have its fallback credit set to `0.0`. The pattern is:
```python
else:  # data absent
    self._record("gate_X", True)
    quality_score += 0.0  # no data → no credit
```
Never use a "midpoint" (half of max credit) as a neutral baseline — use 0.

## CPCV K=3 embargo fix
The secondary CPCV K=3 fold purge was `min(3, _sp // 10)`, inconsistent with the main walk-forward embargo of `min(5, _train_end // 8)` (fixed v187.0). Fixed to `min(5, _sp // 8)` in `neural_signal_trainer.py` L3648.

**Why:** Rolling features (10-bar OFI ring, VPIN, EMA-8, HMM state) have lookback windows of 8-20 bars. A 3-sample cap at 3-7 min candles = only ~9-21 min purge — insufficient to break autocorrelation. Both embargo paths must match.

## Operational note (from code review)
Signal throughput will decrease in degraded-data / cold-start periods now that 4 gates contribute 0 instead of partial credit. If throughput collapses in production, tune via conditional floor relief policy — do NOT re-introduce absence credits.

## Gates changed
- G4 NN unavailable: +7.5 → 0.0 (start_unity_engine.py ~L12096)
- G6 F&G missing/error: +3.75 x2 → 0.0 (start_unity_engine.py ~L12250)
- G7 GEX absent/error: +3.75 x2 → 0.0 (start_unity_engine.py ~L12412)
- G8 insufficient/no symbol: +1.5/+2.5 → 0.0 (start_unity_engine.py ~L12480)
- CPCV purge: min(3,//10) → min(5,//8) (neural_signal_trainer.py ~L3648)
