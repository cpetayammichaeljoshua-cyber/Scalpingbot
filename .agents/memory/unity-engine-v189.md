---
name: Unity Engine v189.0 GEX overconfidence dampener
description: Gate 7 WR-aware dampener for all GEX bonus paths + NEUTRAL absence-bias removal
---

# Unity Engine v189.0 — GEX Overconfidence Dampener

## The rule
All Gate 7 (GEX) quality bonuses must be scaled by a **smooth WR-aware dampener** computed once per evaluation.  High GEX confidence in a losing regime (WR<30%) is overconfidence, not conviction — dealer flow signals at low WR are noisier than their confidence values suggest.

**Why:** Gate 7 unconditionally awarded up to +12pts (gex_conf≥90%) regardless of engine WR. In a WR<30% regime, +12pts GEX pushes marginal signals through G9 that shouldn't pass. The dampener proportionally reduces all GEX upside while preserving negative signals (mismatch penalty −18pts is not dampened).

**Formula:** `_gex_wr_mult = max(0.70, min(1.0, 0.70 + ((_gex_wr - 0.25) / 0.15) * 0.30))`
- WR≤25% → ×0.70 | WR=30% → ×0.80 | WR=35% → ×0.90 | WR≥40% → ×1.00
- Smooth linear ramp — no hard cliffs at boundary values.

**WR parsing pattern (copy-paste safe):**
```python
try:
    _gex_wr_raw = getattr(getattr(self, "_booster", None), "win_rate", 0.0)
    _gex_wr = float(str(_gex_wr_raw).strip("%").strip() or 0)
    _gex_wr = (_gex_wr / 100.0) if _gex_wr > 1.0 else _gex_wr
    _gex_wr = max(0.0, min(1.0, _gex_wr))
    if not math.isfinite(_gex_wr):
        raise ValueError("non-finite WR")
except Exception:
    _gex_wr = 0.30  # conservative: apply partial dampening
_gex_wr_mult = max(0.70, min(1.0, 0.70 + ((_gex_wr - 0.25) / 0.15) * 0.30))
```

## Paths covered by the dampener
All six G7 bonus paths are WR-conditioned (as of v189.0):
- POSITIVE/NEGATIVE alignment bonus (+7.5/+10/+12): floor ×0.70
- FLIP zone bonus (+5.5): floor ×0.70  
- NEUTRAL/UNKNOWN: 0.0 (absence-bias removed, was +3.75)
- Gamma Zero proximity: floor ×0.80 (price-level, lighter)
- Vol Trigger bonus: floor ×0.80
- GZ mean-revert (+3) / trend-follow (+4): floor ×0.80

## What is NOT dampened
The mismatch penalty (−18pts for regime-direction opposition) is intentionally not dampened — bad signals in low-WR regimes should still be penalized at full strength. Only upside bonuses are scaled.

## Lesson: compute dampener once, apply everywhere
The WR multiplier is computed once at the top of the GEX bonus section (before the if/elif/else), ensuring all downstream bonus paths use the same value and the WR parsing exception can't silently skip any bonus.
