---
name: Unity Engine v218.0 — _print_startup_banner 167-GATE persistent ghost
description: v215.0 wrote the 167→177 fix into the changelog but never committed the edit to the code; the runtime banner kept printing "167-GATE SIGNAL FILTER" for three more versions.
---

## Rule
After ANY gate-count banner fix: `grep` the ENTIRE file for the old number before declaring done. Both runtime banners (`_print_startup_banner` AND Launcher) must be updated in the same pass. A changelog narrative entry is not proof of a code change.

## What happened
- v201.0: G8.5BI/GSEV became the 167th gate; `_print_startup_banner` frozen at "167-GATE".
- v214.0: Launcher banner correctly updated to "177-gate filter".
- v215.0: Changelog documents "_print_startup_banner INFO log stale '167-gate filter' — FIXED", but the actual `logger.info(f"🔒 167-GATE SIGNAL FILTER …")` line at ~30655 was never edited. Bug persisted through v216.0 and v217.0 undetected.
- v218.0: Confirmed the line was still "167-GATE" via grep; fixed to "177-GATE".

**Why:** The changelog update and the code edit were written as the same step in the description but executed as two separate actions — the code edit was simply omitted.

**How to apply:** When fixing a stale number in a banner, run `grep -n "NNN-GATE\|NNN-gate" file` AFTER the edit to confirm zero runtime occurrences remain. Historical changelog mentions (docstring history) are acceptable; live logger.info strings with the old number are not.
