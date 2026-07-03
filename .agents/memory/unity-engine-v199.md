---
name: Unity Engine v199.0 overscoring dampener completeness pass
description: 9 remaining undampened positive quality-score bonuses found and WR-dampened; explorer-reported "bugs" that were already fixed or false positives
---

## What changed
Audited the full ~34,900-line file for dead gates, double-counting, and overscoring/overconfidence bugs across 5 parallel explorer passes, then hand-verified every finding against live code before touching anything (explorers repeatedly cited stale changelog *comments* as if they described current behavior — always re-read the actual code path, not the inline comment history, before trusting an audit finding).

Found 9 positive quality-score bonuses that were never wrapped in the codebase's standard `self._wr_dampen(pts)` scaling (defined ~line 7299; scales bonus points ×0.70 at WR≤25% up to ×1.0 at WR≥40%, linear between, only ever applied to positive bonuses). These were inconsistent with ~150+ other bonus sites already dampened in prior version passes (v189/v194/v195/v197/v198). Wrapped all 9 in `self._wr_dampen(...)`, tagged `# v199.0: WR-dampened`.

## False positives ruled out this pass (do not re-flag)
- `self._kelly_ceil`/`self._kelly_floor` AttributeError-swallow bug — already fixed in a prior commit before this session (v199.0-FIX comment present at the top of all read sites).
- GEX_GAMMA_ZERO/VOL_TRIGGER bonuses — already dampened since v189.0.
- GSDD/GHTF "double-record" claims — false positive; both properly guarded by `if self._last_x == 0.0` sentinels, not double-counting.

**Why:** explorer subagents pattern-match on comment text and changelog banners, which lag behind actual code edits by design (this file keeps historical `[vNN.N]` tags in log strings even after later versions patch the logic). Trusting a comment instead of the executed branch produces false-positive "dead gate" reports.

**How to apply:** for any future audit pass on this file, always grep the *current* logic around a flagged line — not just the nearest version-tag comment — before spending an edit on it.

## Walk-forward / CPCV assessment (no changes made)
Reviewed `SignalMaestro/neural_signal_trainer.py` CPCV implementation (K=3 folds, embargo `min(5, n//8)`, 51% floor, 9% gap threshold). Judged reasonably implemented for a soft-scoring architecture — there is no gate-pruning/kill-switch mechanism tied to WF results, but the system is designed as continuous soft-scoring (points added/subtracted) rather than hard pass/fail gates, so this is an architectural choice, not a bug. Left as-is.

## Standing philosophy (carried from v178 finding)
Live win rate has been stuck ~29% for 4+ months despite 190+ version bumps of new gates. The fix pattern that actually matters is bug-fixing (dead gates, silent no-ops, missing dampeners) — not adding new gates. This pass continued that discipline: 0 new gates added, only consistency/correctness fixes to existing scoring paths.
