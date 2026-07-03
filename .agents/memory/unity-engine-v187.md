---
name: Unity Engine v187.0 scoring/walk-forward fix
description: Three bugs — G5 no-data +3.0 overcounting, GBT CPCV embargo too small, GBLK stale docstring
---

## Rule
Three bugs fixed in v187.0 (no new gates, pure calibration/WF fix release).

**Bug 1 — G5 "no data" +3.0 overcounting bias (start_unity_engine.py ~line 12186)**
Gate 5 (ATAS+Bookmap alignment quality scoring) was awarding +3.0 quality pts when BOTH
analyzers returned no data (atas_dir is None and bm_dir is None). This rewarded ABSENCE
of contradicting evidence rather than actual confirmation. Most signals for low-volume
symbols or when analyzers are offline received this unconditional boost, inflating
quality_score and weakening the G9 quality threshold as a filter.
The other +3.0 cases in the codebase are all CONDITION-based (require liquidity, vol_ratio,
GEX alignment, etc.) — G5 was the only unconditional "reward for no data" case.
Fix: +3.0 → 0 (pass statement). Signals without external data are now truly neutral.
Effect: borderline signals that passed G9 solely on this free +3.0 are now filtered out.

**Bug 2 — GBT CPCV embargo too small (neural_signal_trainer.py ~line 3402)**
Embargo was `min(3, _train_end // 10)` — capped at 3 samples regardless of dataset size.
Rolling features with 8-20 bar lookback (OFI ring, VPIN, EMA-8, HMM state, AVWAP) produce
autocorrelation that spans more than 3 samples at 3-7 min candle resolution.
At n=30: embargo=2 (was). At n=50-300: embargo=3 (was).
Fix: `min(5, _train_end // 8)`. New values: n=30→3, n=50+→5.
Consistent with v186.0 Torch embargo cap (also 5 samples).
Note: min(5,3)=3 at n=30 — no breakage at minimum dataset size.

**Bug 3 — GBLK stale docstring (start_unity_engine.py ~line 6507)**
Docstring said "WR<30% over ≥10 resolved trades" — predated v101.0 (10→20 trades, 30%→25%
WR) and v149.0 (fast-path ≥15/WR<28%). Actual SQL HAVING clause uses:
(total>=15 AND WR<0.28) OR (total>=20 AND WR<0.25) OR zero-win safety nets (≥5,≥7 trades)
OR WR<15%/≥8 trades. Fixed to match actual SQL.

**Why:** Multi-parallel deep scan (4 simultaneous subagents) covering scoring, Kelly sizing,
trainer path, and hard-block gates. The G5 no-data bias was the only "reward for absence"
pattern in the entire quality_score pipeline; all other +3.0 additions require real conditions.

**How to apply:**
- When reviewing G-gate quality_score additions: distinguish "condition-based" (requires a
  real signal) from "absence-based" (rewarding lack of contradicting data). Only the former
  is valid. The latter inflates quality_score unconditionally.
- CPCV embargo should cap at ≥5 samples for feature sets with 8-20 bar lookback windows.
- When adding new CPCV/WF logic, keep embargo consistent with the Torch embargo (both cap 5).
