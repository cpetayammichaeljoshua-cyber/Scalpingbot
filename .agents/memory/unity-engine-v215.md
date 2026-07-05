---
name: Unity Engine v215.0 — _print_startup_banner INFO log stale gate count
description: Second architecture banner in _print_startup_banner() showed "167-gate filter" since v201; missed in v214 Launcher-banner pass.
---

## Rule
When fixing a gate-count banner, always grep for ALL occurrences of the old number — there are **two separate architecture banners** in the file:
1. **Launcher banner** — inside the `Launcher` class startup method (~line 35067), fixed v214.
2. **_print_startup_banner INFO log** — inside `_print_startup_banner()` (~line 30582), fixed v215.

Both must be updated in the same pass. The v214 fix only found the Launcher one.

## What changed
- `_print_startup_banner` INFO log: `"167-gate filter"` → `"177-gate filter"` (10 gates behind since v201.0 when GSEV was introduced as the 167th gate; gates v203–v214 were added without updating this second banner).
- Kelly stamp in that same banner: appended `·GSEV-OptimismTrap-167gate[v201.0]·GDLBkelly133-Functional[v214.0]·GTODkelly134-Functional[v214.0]·177gate[v215.0]` after `G8.5CORR-FamilyCorrDampener-additive[v179.0]`.

**Why:** The two banners are in different methods/classes and `grep "167-gate"` would have caught it — but the v214 pass only grepped for the specific old text it knew about ("176-gate"). Pattern: after any gate-count fix, always `grep -n "N-gate filter"` for both the old AND new numbers to confirm there are no other instances.

**How to apply:** After any banner gate-count update, run:
`grep -n "N-gate filter\|M-gate filter" start_unity_engine.py`
where N=old count and M=new count, to verify exactly two occurrences change to M (module docstring + both runtime banners all agree).
