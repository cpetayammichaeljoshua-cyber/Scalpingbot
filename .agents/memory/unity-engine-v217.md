---
name: Unity Engine v217.0 — GEX comment correctness + CORR rho stale count
description: _gex_wr_mult is identical to _wr_dampen() (both floor=0.70); old "v213.0-FIX" comment was factually wrong; CORR rho pool count updated 105→109
---

## Rule
`_gex_wr_mult` and `self._wr_dampen()` use IDENTICAL formulas:
```python
max(0.70, min(1.0, 0.70 + ((WR - 0.30) / 0.15) * 0.30))
```
Both give floor=×0.70 at WR≤30%, ramp to ×1.00 at WR≥45%. At live WR=29%, both give exactly 0.70.

**Why:** The old GEX comment claimed v213.0 changed the formula to `clamp(0.30+(WR-0.30)/0.15×0.70, 0.30, 1.0)` (floor=0.30). This was NEVER implemented. v213.0 only fixed recording gaps (46 bare-except gates). The correct sync happened in v208.0 (ramp start 0.25→0.30 matching v207.0 _wr_dampen tightening). Keeping the wrong comment would cause a future maintainer to think GEX was massively over-dampened (0.30 vs 0.70 "standard") and try to "fix" correct code.

**How to apply:**
- If a future scan shows "GEX giving 0.70× while _wr_dampen gives 0.30×" — this is WRONG. Both give 0.70×.
- If the GEX formula needs tightening below 0.70, `_wr_dampen()` must also be changed first — they must stay in sync.
- Do NOT trust the inline `# v213.0-FIX` label on any line; v213.0 was purely a recording-gap fix.

## Comprehensive scan results (v217 pass)
All potential overscoring/bug areas verified clean:
- 6 direct `quality_score +=` sites (GEX/PBO/VPIN): all correctly dampened via `_gex_wr_mult` or `_wr_dampen()` ✓
- `self._kelly_ceil`: initialized in `__init__` (line 23226) AND re-set before all boost steps ✓
- CORR sentinel tuple (109): complete coverage of all positive-path gate eras ✓
- GDOW hard-block: `_record(True)` only on pass/exception paths, `_record(False)` + return on block ✓
- CPCV/walk-forward: prior audits confirmed correct temporal splits + embargo ✓
- SOVEREIGN Wilson bound: correct ✓
- Swarm unanimous-consensus: double-counting was removed in prior pass ✓
- Kelly Steps 140-162: standard de-size/boost patterns, no v214-style no-ops ✓
- v162 era gap: doesn't exist (v161→v163 direct) ✓
- AA/AB/AD sentinels (CWD/XRSI/GTOD): all negative-only, correctly excluded from CORR ✓
