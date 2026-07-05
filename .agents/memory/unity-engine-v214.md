---
name: Unity Engine v214.0 — Kelly Steps 133/134 ceiling-only no-op
description: Steps 133 (GDLB) and 134 (GTOD) modified _kelly_ceil LOCAL variable only — never self.last_kelly_fraction — making both de-sizes silent no-ops since v159/v160.
---

## Rule
Kelly steps that do `_kelly_ceil = max(_kelly_ceil * mult, floor)` without also doing
`self.last_kelly_fraction = max(self.last_kelly_fraction * mult, KELLY_MIN_FRACTION)`
are **no-ops** for position sizing. The local `_kelly_ceil` variable (set at function start:
`_kelly_ceil = KELLY_MAX_FRACTION` at line ~24181) only constrains subsequent BOOST clamps
(`min(self._kelly_ceil, fraction * boost_mult)`). Since most subsequent steps are DE-SIZES
(multiply by <1.0), they rarely push the fraction up to the ceiling — so the ceiling
modification has no effect on actual position sizing.

**Why:** Step 133 (GDLB) was introduced v159.0, Step 134 (GTOD) at v160.0. Both intended
to de-size LONG/bad-ToD signals. The ceiling-only approach worked for boost steps AFTER them,
but not for the current trade's fraction.

**How to apply:**
- Any Kelly step that de-sizes must call:
  `self.last_kelly_fraction = max(self.last_kelly_fraction * mult, KELLY_MIN_FRACTION)`
- Optionally ALSO lower `_kelly_ceil` to constrain subsequent boosts in same pass.
- Steps 135+ (GCAL, GDIV, etc.) use `self.last_kelly_fraction = min(ceil, fraction * mult)` — correct pattern.

## Impact
- Step 133 GDLB: 16,305 terminal signals, LONG avgP=-0.28% vs SHORT +0.26%. De-size of
  ×0.90/×0.85 at WR<32%/28% was completely inactive since v159.0. Now active.
- Step 134 GTOD: LONG@13-14h avgP=-4.12%/-3.01%, SHORT@22h=-4.39%. De-sizes ×0.82/×0.88/×0.78
  now active in WR<35% crisis.

## Launcher Banner
- "176-gate filter" in Launcher startup banner was stale since v179.0 (when CORR was added
  as 177th gate). Updated to "177-gate filter" at line 35067.

## Constants
- `KELLY_MIN_FRACTION = 0.001` (module scope, line ~2948) — prevents collapse below 0.1%
- `KELLY_MAX_FRACTION = 0.08` — default ceiling reset each `_update_kelly` call
- `_kelly_ceil = KELLY_MAX_FRACTION` — LOCAL var at line 24181, function scope of `_update_kelly`
