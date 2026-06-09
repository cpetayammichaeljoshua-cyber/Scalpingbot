---
name: Unity Engine v51.0 gate analytics fix
description: G8.5w and G8.5x were invisible to health analytics (no _record calls, not in _gate_stats); fixed in v51.0.
---

## Root cause
G8.5w (MTF-Momentum) and G8.5x (LiqCascade-Direction) were added in v49.0, data-pipeline fixed in v50.0, but **never called `self._record()`**. This meant:
- They did not appear in `gate_stats_summary()` (console HUD)
- They did not appear in `gate_bottleneck_str()` (worst-3 bottleneck display)
- They did not appear in the `/gates` health endpoint
- Operators had NO visibility into whether the gates were firing or skipping

## Fix (v51.0)
1. Added `self._gate_stats["gate_g85w"] = {"pass": 0, "fail": 0}` and `self._gate_stats_recent["gate_g85w"]` in `UnitySignalFilter.__init__()` after `gate_vibe` entries (around line 3967)
2. Same for `gate_g85x`
3. Added `"gate_g85w": "G8.5w"` and `"gate_g85x": "G8.5x"` to `_GATE_DISPLAY_LABELS` dict
4. In G8.5w gate block: added `_g85w_fired = False` flag, set `True` when ≥4 return bars available, then `self._record("gate_g85w", _g85w_fired)` after the scoring block
5. In G8.5x gate block: `_g85x_fired = _g85x_net_liq in ("LONG","SHORT") and _g85x_liq_mag > 0`, then `self._record("gate_g85x", _g85x_fired)` after the scoring block
6. Improved G8.5w debug log: moved outside `adj != 0` guard (any evaluation logged), added `bars={len(_g85w_rets)}` for visibility

## Semantics for pass/fail
- **pass** = gate had sufficient data to evaluate (kline buf ≥4 bars for G8.5w; liq WS <90s old for G8.5x)
- **fail** = gate skipped due to no data (cold start, WS not yet connected, etc.)

This is a pattern to follow for ALL future quality-adjuster gates — even soft gates (no hard pass/fail) MUST call `_record()` to be visible in analytics.

## Rule for future gates
When adding a new gate to `UnitySignalFilter.apply()`:
1. Add `self._gate_stats["gate_XXX"] = {"pass": 0, "fail": 0}` in `__init__`
2. Add `self._gate_stats_recent["gate_XXX"] = deque(maxlen=self._gate_stats_window_n)` in `__init__`
3. Add `"gate_XXX": "GX.Xn"` to `_GATE_DISPLAY_LABELS`
4. Call `self._record("gate_XXX", fired_bool)` in the gate block — even for soft/quality-adjuster gates

**Why:** Without `_record()`, the gate is completely invisible to diagnostics, `/gates` endpoint, and the rolling window analytics. This caused 2 consecutive version cycles of invisible gates (v49.0 and v50.0) before being caught.
