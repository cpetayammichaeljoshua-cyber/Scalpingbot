---
name: Unity Engine v211.0-v212.0 double-record gate fix
description: 11 gates had both direct _gate_stats/_gate_stats_recent update AND self._record() called every evaluation — inflating pass/fail analytics by 2× and corrupting bottleneck diagnostics. Root cause and fix pattern.
---

# Double-Record Gate Bug (v211.0-v212.0)

## Rule
Any gate that calls `self._record()` must NOT also directly update `self._gate_stats["key"]["pass"/"fail"] += 1` or `self._gate_stats_recent["key"].append()` in the same code path. `self._record()` already does both.

**Why:** `self._record()` was added outside try blocks by the v192.0-FIX (to guarantee recording on exception). The pre-existing direct update block inside the try was never removed. Result: every evaluation incremented pass/fail and appended to the ring twice — 2× inflation in all analytics derived from those gates.

**How to apply:** When adding `self._record()` outside a try block (exception-safe pattern), always remove the old direct update block (typically 2 lines: `_gate_stats["key"]["pass"/"fail"] += 1` + `_gate_stats_recent["key"].append(...)`) from inside the try. For gates with `setdefault` + direct update + `self._record()` (IVCRUSH/FUNDING pattern), the entire 4-line setup block is redundant — `self._record()` includes the v9.0 `setdefault` guard.

## Affected gates (fixed v211.0-v212.0)
- **v211.0**: `gate_g85corr_fcd` (CORR) — direct update on 2 lines + `self._record()` on 1 line
- **v212.0** (10 gates):
  - `gate_g85aa_cwd` (AA-CWD), `gate_g85ab_xrsi` (AB-XRSI), `gate_g85ac_dlb` (AC-GDLB), `gate_g85ad_gtod` (AD-GTOD) — 2 duplicate lines inside try + `self._record()` outside try
  - `gate_g85k_ivcrush` (IVCRUSH), `gate_g85r_funding` (FUNDING) — 4-line setdefault+direct block before `self._record()` (all 4 lines redundant)
  - `gate_g85w5_wnz` (W5), `gate_g85x5_adf` (X5), `gate_g85y5_pco` (Y5), `gate_g85z5_ics` (Z5) — 2 direct update lines immediately before `self._record()`

## Detection pattern
Use AST-aware Python scan:
```python
# Flags any gate with both direct_gate_stats[key][...] update AND self._record(key)
# within 5 lines — in non-string-literal code context
```
See docstring for the full scanning script used in v212.0.

## Result
- Zero double-record gates after v212.0 (AST-verified, scanner-confirmed)
- Gate bottleneck analytics and recent-window WR now accurate for all 177 gates
