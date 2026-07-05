---
name: Unity Engine v208.0
description: Ramp-sync sweep — 3 inline WR multiplier copies still used old 0.25→0.40 ramp after v207.0 updated _wr_dampen to 0.30→0.45; H4/I4/J4 positive paths undampened since v119-v120
---

# Unity Engine v208.0 — Inline WR-Mult Ramp Sync + H4/I4/J4 Positive Dampening

## Bugs Fixed

### Bug 1: Three inline WR-mult copies lagging behind v207.0 _wr_dampen update
`_wr_dampen()` was updated in v207.0 to use ramp 0.30→0.45, but three inline copies of the same formula still used the OLD ramp 0.25→0.40:

| Location | Variable | Gates affected |
|---|---|---|
| Line 12723 (G7 GEX gate) | `_gex_wr_mult` | 6 GEX bonus paths (align, FLIP, GZ-prox, VOL-trig ×2, GZ-MR, GZ-TF) |
| Line 14156 (G8.5U MomConsensus) | `_g85u_wr_mult` | G8.5U overconsensus dampener (inline before _wr_dampen) |
| Line 18075 (G8.5N4 TFCMeta) | `_n4_wr_mult` | G8.5N4 positive-side overconsensus dampener |

**At WR=29% (live):**
- Old (pre-v208.0): mult = max(0.70, 0.70 + (0.29-0.25)/0.15 × 0.30) = **0.78**
- New (v208.0): mult = max(0.70, 0.70 + (0.29-0.30)/0.15 × 0.30) = max(0.70, 0.698) = **0.70** (floor)

All three copies now use `(WR - 0.30) / 0.15` to match `_wr_dampen()`.

**Why this matters for GEX specifically**: GEX max alignment bonus = 12pt. At WR=29%:
- Pre-v208.0: 12.0 × 0.78 = **9.36pt**
- Post-v208.0: 12.0 × 0.70 = **8.40pt** (0.96pt tighter)
Total GEX bonus suite at max could reach ~35pt raw; v208.0 reduces this to ~24.5pt at WR=29%.

**Why G8.5U has double-dampening**: G8.5U applies `_g85u_wr_mult` inline (overconsensus guard) THEN passes to `_wr_dampen()`. This double-dampening is intentional (v191.0 design) — raw 5-gate consensus vote is especially susceptible to false-positive stacking. Both layers must be synchronized.

### Bug 2: G8.5H4/I4/J4 positive paths undampened since creation (v119.0/v120.0)
Three TimesFM-family gates applied their positive adjustments (+2.0/+1.5pt) as raw values with no `_wr_dampen()`:
- G8.5H4 TPEPatchEnsemble: `quality_score += _h4_adj` (was raw)
- G8.5I4 DrawdownGuardTF: `quality_score += _i4_adj` (was raw)
- G8.5J4 TFMSMultiScale: `quality_score += _j4_adj` (was raw)

These were added in v119.0-v120.0, before the systematic dampening sweep (v178.0+). Fix: positive side wrapped with `self._wr_dampen()` inline:
```python
quality_score += (self._wr_dampen(_h4_adj) if _h4_adj > 0.0 else _h4_adj)
```
Negative side preserved at full strength (all three gates' negative tiers are protective vetos).

Note: G8.5N4 already had its own inline dampener (v191.0) — only the formula ramp needed updating.

## Impact Summary at WR=29%

| Path | Before | After |
|---|---|---|
| GEX max align (12pt) | +9.36pt | +8.40pt |
| GEX FLIP bonus (5.5pt) | +4.29pt | +3.85pt |
| GEX GZ-proximity (3-4pt) | +2.34-3.12pt | +2.10-2.80pt |
| G8.5H4 aligned×5 (+2.0pt) | +2.00pt raw | +1.40pt |
| G8.5I4 low-DD + TF-votes (+2.0pt) | +2.00pt raw | +1.40pt |
| G8.5J4 aligned×7 (+2.0pt) | +2.00pt raw | +1.40pt |

## Pattern: After any _wr_dampen ramp change, must also update ALL inline copies
The engine has 3 sites where the ramp is hardcoded as a local formula instead of calling `_wr_dampen()`:
1. `_gex_wr_mult` (Gate 7 GEX) — GEX has a pre-computed mult applied to raw bonuses
2. `_g85u_wr_mult` (G8.5U MomConsensus) — overconsensus layer before main dampener
3. `_n4_wr_mult` (G8.5N4 TFCMeta) — overconsensus layer before addition

**Why not call `_wr_dampen()`?**: GEX applies mult to the raw bonus before addition (can't pass through `_wr_dampen` directly since the bonus varies). G8.5U/N4 apply inline then pass to `_wr_dampen()`. Any future ramp change MUST touch all 3 sites + `_wr_dampen()` def.

## Boot Confirmation
- v208.0: 21/21 layers online, Semaphore(110) ✅
- No errors, clean boot
