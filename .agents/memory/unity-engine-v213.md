---
name: Unity Engine v213.0 — exception-path recording gap (v4/v5 series)
description: 46 gates C4–V5 had bare 'except Exception: pass' with no fallback _record(); same root-cause as v190.0. Capability stamp updated Steps1-131→Steps1-162.
---

## Rule
Gates G8.5C4 through G8.5V5 (46 gates, v116.0–v143.0 era) used the OLD recording pattern — direct `_gate_stats[key]["pass"/"fail"] += 1` + `_gate_stats_recent[key].append()` inside `try` blocks, with bare `except Exception: pass` providing NO fallback recording on exception.

**Why:** These gates were introduced before the `self._record()` abstraction was standardized (post-v190.0). They correctly recorded in the happy path, but on any numpy error / missing data / uninitialized attribute, the gate silently showed zero calls in analytics — same as the v190.0 NameError swallowing that caused 4+ months of invisible logic.

**Fix (v213.0):** Replaced each bare `pass` in the except clause with `self._record(gate_key, True)` — neutral (pass) fallback recording. `_record()` method signature: `def _record(self, gate: str, passed: bool)`.

**How to apply:**
- Any gate that uses `self._gate_stats[key]` + `self._gate_stats_recent[key]` INSIDE a try block without a corresponding `self._record()` OUTSIDE the try block needs an exception-path `_record(key, True)` in the except clause.
- Run scan: `grep -n "except Exception:" file.py` in the gate scoring range (17000–22000), check each for direct `_gate_stats` mutations without a fallback.

## Capability Stamp
- Stamp was at "Steps1-131" (last updated v143.0 era) despite engine having 162 Kelly steps.
- v213.0 updated to "Steps1-162" and appended steps 132–162: GCWD[v157]→GSEV[v201].
- Actual code at line 27846: "Kelly Step 132 — GCWD Near-GXPR Pre-Block De-size [v157.0]"

## Architecture (v213.0)
30 layers · 177-gate filter · Kelly 162-steps · 105 CORR sentinels · NN v81 420-feature
35,166 lines | v213.0
