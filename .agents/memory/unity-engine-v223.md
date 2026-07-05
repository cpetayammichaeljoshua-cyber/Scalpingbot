---
name: Unity Engine v223.0 — Kelly boost WR floor guard batch fix (112 sites)
description: All 112 Kelly boost paths in Steps 36-162 were firing unconditionally at WR=29%; fixed with shared _kW variable and inline WR≥30% ternary guard.
---

## Rule
All Kelly boost paths (multiplier > 1.0) in Steps 36–162 must be gated by `_kW >= 0.30` (the shared method-scope WR snapshot). The pattern is: `BOOST_EXPR if _kW >= 0.30 else self.last_kelly_fraction`. Additionally, every boost assignment must include a ceiling clamp via `min(..., self._kelly_ceil)` or an existing `max(floor, min(cap, ...))` wrapper.

**Why:** At live WR=29%, the engine's own regime evidence shows no positive edge. 112 boost steps were firing unconditionally, compounding ×1.03/×1.04 stacks that contradicted the crisis-de-size logic running in parallel. E.g., Steps 95×0.75 × 97×0.75 (crises) could be immediately offset by 5–6 boost steps firing at WR=29%.

**How to apply:**
- `_kW` is inserted at one location in `_update_kelly()`, immediately after Step 35 ends (~line 25382). It defaults to 0.0 (safe: no boosts) and is computed from `self._booster._win_ring` when ≥10 trades available.
- Steps 32/33/34/35 (v221.0-fixed) retain their own per-step WR guards — NOT guarded by `_kW` to avoid double-guarding.
- De-size paths (multiplier < 1.0) are intentionally left unguarded — crisis protection always fires.
- Total: 112 `_kW >= 0.30` guards added; 14 simple direct-multiply boost paths also got `min(..., self._kelly_ceil)` ceiling clamp.

## Pattern
```python
# BEFORE (fires at WR=29%):
self.last_kelly_fraction = min(self._kelly_ceil, self.last_kelly_fraction * 1.03)

# AFTER v223.0 (blocked at WR<30%):
self.last_kelly_fraction = min(self._kelly_ceil, self.last_kelly_fraction * 1.03) if _kW >= 0.30 else self.last_kelly_fraction  # v223.0: WR≥30% guard
```

## Verification
```bash
grep -c "if _kW >= 0.30" start_unity_engine.py  # expect 112
grep -n "last_kelly_fraction = self.last_kelly_fraction \* 1\." start_unity_engine.py | grep "_kW" | wc -l  # expect 0 (all now have min(ceil,...))
```
