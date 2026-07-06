---
name: Unity Engine v224–v226 — Kelly de-size floor + boost guard completeness
description: Three-version batch fixing residual Kelly floor/guard gaps after v222/v223; full chain now sound.
---

## Summary of changes across v224–v226

### v224.0 — De-size floor guard: Steps 106–162 (50 sites)
Three patterns all changed to `max(..., self._kelly_floor)`:
- **Pattern A** (16 sites): `max(0.0, self.last_kelly_fraction * mult)` — zero floor allowed Kelly to hit zero in deep multi-step crisis.
- **Pattern B** (32 sites, ceiling-clamp): `max(self.last_kelly_fraction * 0.XX, 0.0005)` — `0.0005` literal is BELOW `KELLY_MIN_FRACTION = 0.001`.
- **Pattern C** (2 sites, Steps 133–134): `max(..., KELLY_MIN_FRACTION)` — standardised to `self._kelly_floor`.
- Not touched: `_k30_cap = 0.0005` (Step 30 ultra-ruin DD>48% **hard-cap** — intentional, not a de-size floor).

### v225.0 — GSEV guard for all Steps 36–162 boost ternaries (113 sites)
- Added `_kGSEV: bool` to the method-scope block beside `_kW`.
- All 113 boost ternaries: `if _kW >= 0.30 else ...` → `if _kW >= 0.30 and _kGSEV else ...`
- Default `True` (conservative: `_last_g85bi_gsev` defaults to 0.0; `0.0 > -1.5 = True`).

### v226.0 — Three residual fixes found by code review
1. **`_kGSEV` exception guard**: v225.0 left it as a bare assignment. Wrapped in `try/except`; failure → `True` (allows boosts — conservative).
2. **30 residual multi-line boost paths** (Steps 38–81): v223.0 fixed single-line ternary patterns but missed multi-line `max(_kelly_floor, min(_kelly_cap, * 1.0X))` blocks. All 29 Pattern-A and 1 Pattern-B (Step 81) sites wrapped as `(EXPR if _kW >= 0.30 and _kGSEV else self.last_kelly_fraction)`.
3. **Final kelly→last_kelly_fraction assignment**: `max(0.0, min(_kelly_ceil, kelly))` → `max(self._kelly_floor, ...)`. Prevents any signal entering Steps 28–162 with zero position size.

## Known non-issue
- Several boost debug log messages still print "Kelly ×1.0x" even when guard blocks the boost (observability mismatch only — sizing is correct).

## Confirmed clean after v226.0
- Code review passed: no remaining unguarded boost paths in Steps 36–162.
- No remaining `max(0.0, self.last_kelly_fraction * ...)` in executable code.
- `python3 -m py_compile` passes (no syntax errors from ternary wrapping).
- Engine started 21/21 layers healthy.

**Why:** Compounding Kelly de-sizes below exchange minimum (0.001) + unconditional Kelly boosts at WR=29% + GSEV crisis were three contradictory sizing behaviors that degraded live WR/Sharpe/MaxDD. These fixes ensure crisis de-sizing can never be overridden by boost compounding.
