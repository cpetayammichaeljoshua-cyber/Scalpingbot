---
name: Unity Engine v180.0 upgrades
description: Dead-recording fix for G2.5b/G2.5c gates + G8.5CORR dampener expansion to v119-v120 composite gates
---

## Rules

**G2.5b (PatternRecognition) and G2.5c (VolConfirmation) dead-recording fix**
Both gates scored `quality_score` but had no `self._record()` call since their introduction (v11.0/v18.19) → invisible to `/gates`, `gate_stats_summary()`, `gate_bottleneck_str()`.

Fix pattern used:
- G2.5b: Initialize `_g25b_adj = 0.0` **outside** the if/try block → call `self._record("gate_g25b", _g25b_adj >= 0)` after the block. Neutral (adj=0) = pass.
- G2.5c: Initialize `_vcr = 1.0` (safe default) **outside** the try block → call `self._record("gate_g25c", _vcr >= 0.7)` **after** the try/except. Default 1.0 = pass-through (neutral vol).

**Why:** `_record` inside a try/except is swallowed on exception → no record. Always initialize the tracking variable outside, record outside.

**G8.5CORR dampener expansion**
6 missing composite gates from v119-v120 were absent from the Wilson/√corr clawback sentinel list:
- `_last_g85h4_tpe` (TimesFM PatchEnsemble 5-scale, v119)
- `_last_g85i4_dgc` (DrawdownGuard+TimesFM composite, v119)
- `_last_g85j4_tfms` (TimesFM MultiScale 7-scale, v120)
- `_last_g85l4_wsd` (WinRate-Sharpe-DD Triple, v120)
- `_last_g85m4_ofm` (OFI-VPIN-Funding MicroTriple, v120)
- `_last_g85n4_tfc` (TimesFM ConsensusCap Meta, v120)

All store +1/-1/0 int values, compatible with the corr_votes sign-only logic.

**Why:** G8.5CORR originally covered G8.5A3..Z5 (v93-v143 family) but the v119-v120 gates were added between v114 and v128 and missed. These are chained composite gates sharing OFI/HMM/TF primitives, so they're equally subject to the correlation overcounting the dampener was designed to fix.

**Wiring checklist for any new soft-gate (anti-dead-recording):**
1. `self._gate_stats["gate_XXX"] = {"pass":0,"fail":0}` + `_gate_stats_recent`
2. `_GATE_DISPLAY_LABELS["gate_XXX"] = "G?.?X"`
3. `_SOFT_GATE_KEYS` set entry
4. `self._record("gate_XXX", passed)` **outside** any try/except
5. If tracking var needed inside try: initialize outside with safe default first
