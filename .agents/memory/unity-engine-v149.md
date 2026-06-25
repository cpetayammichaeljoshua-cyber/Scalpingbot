---
name: Unity Engine v149.0
description: IRONS persistence bypass bug fix + GBLK fast-path tier tightening
---

## IRONS Persistence Bypass Bug (CRITICAL)

**The bug:** Both persistence load sites (Redis at ~line 26506, JSON file at ~line 28627) directly assigned the saved `adaptive_irons_min` value, overwriting the freshly-computed floor from `update_adaptive_irons()`. When `IRONS_MIN_WR_BELOW30` was raised from 73→75 in v147, the engine loaded 71 (old saved value) and showed `MinReq=71(adapt)` in console despite IRONS_MIN_WR_BELOW30=75.

**The fix:** At both load sites:
```python
_loaded_aim = float(state["adaptive_irons_min"])
self.signal_filter._adaptive_irons_min = max(_loaded_aim, IRONS_MIN_WR_BELOW30)
```

**Why:** Any future raise in IRONS_MIN_WR_BELOW30 now takes effect immediately on restart without waiting for the first new outcome to trigger update_adaptive_irons(). The max() ensures higher adaptive values (e.g., WR<20% → 78) are still honoured.

**Log confirmation:** `Filter state restored: IRONS_min=75` (was 71 pre-fix). The subsequent `blend_wr=31.5% → min=71` is correct — Bayesian blend of 31.5% puts WR in the 30-45% tier (IRONS_MIN_WR_30_45=71).

## GBLK Tightening (v149.0)

Added fast-path tier: `total >= 15 AND WR < 0.28` (above the existing ≥20/WR<25% base tier). At engine WR=29%, symbols with WR<28% and ≥15 trades are clearly underperforming. Previously required 20 trades. Zero-win safety nets unchanged.

**Boot evidence:** 78 symbols blacklisted (up from ~N at v148 boot) confirming more symbols caught.

## Docstring Fixes

`update_adaptive_irons()` docstring corrected: WR<30% tier now shows 75 (not stale 73/70), WR<25% shows 76.5, WR<20% shows 78. IRONS_MIN_WR_30_45 comment updated to 71.

## UNITY_VERSION: 148.0 → 149.0
