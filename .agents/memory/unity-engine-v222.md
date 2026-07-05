---
name: Unity Engine v222.0 — de-size Kelly floor guard batch fix
description: 46 Kelly de-size paths (Steps 93-137) missing max(...,_kelly_floor) — could compound below 0.1% minimum in triple-crisis stacking
---

## Rule
Any Kelly de-size step using `min(ceil, fraction * multiplier)` MUST also wrap with `max(..., self._kelly_floor)` to prevent compounding below KELLY_MIN_FRACTION=0.001.

**Why:** In a multi-step crisis (WR=29%), Steps 95+97+99 all fire simultaneously with ×0.75/×0.75/×0.55 → compound ×0.309. At starting Kelly=0.5% this gives 0.154% which is below the 0.1% floor. Exchange may reject tiny orders or emit precision errors.

**How to apply:** Every future Kelly de-size step must use pattern:
`self.last_kelly_fraction = max(min(ceil, self.last_kelly_fraction * 0.XX), self._kelly_floor)`
Boost steps (multiplier > 1.0) need only ceiling: `min(fraction * 1.XX, ceil)`.

## Steps fixed in v222.0
Steps 93(EVVel), 94(WRAccel), 95(MaxDD-EV-Compound), 96(SOW), 97(SQC), 98(ERV), 99(TUC),
100(WAC), 101(SVR), 102(OWS), 103(ARC), 104(SVC), 105(EVPV), 124-131 (LSQ/MFR/OUP/MFA/WNZ/ADF/PCO/ICS),
132(GCWD), 135(GCAL), 136(GDIV), 137(GBATCH) — 46 total assignments.

## Prior related fixes
- v214.0: fixed ceiling-ONLY no-ops (de-size did NOTHING — different from this floor-missing bug)
- v221.0: fixed boost paths missing WR floor (boosts fired at WR=29% with no absolute edge guard)
- v222.0: fixed de-size paths missing position floor (could push Kelly below 0.1% minimum)
