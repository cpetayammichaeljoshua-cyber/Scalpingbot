---
name: Unity Engine v198.0 overscoring sweep completion — variable-based adj bonuses
description: Closes the v178-started overscoring sweep by wrapping all 126 remaining `quality_score += _xxx_adj` variable-based bonus/penalty sites; documents the safe bulk-wrap trick (self._wr_dampen is a no-op on negatives) and the setdefault-only gate_stats pattern that looks like a bug but isn't.
---

**What this closes:** v178-v197 wrapped raw-literal `quality_score += N` positive bonuses across
dozens of gates. This left a second category untouched: `quality_score += _xxx_adj` where `_xxx_adj`
is a variable that can hold either sign depending on which branch set it (e.g. HMM regime quality,
VPIN/Kalman/Dispersion/PCA/CSM/IV quality adjustments, G8.5w-z and G8.5A-V2 families). 126 such sites
existed engine-wide.

**Key trick — bulk-wrap is safe here:** `self._wr_dampen(pts)` returns `pts` unchanged when `pts <= 0`.
That means wrapping `quality_score += _xxx_adj` as `quality_score += self._wr_dampen(_xxx_adj)`
is safe to apply *unconditionally* to every such site, even though the variable can be negative —
penalty branches pass through untouched, only positive branches get WR-scaled. This let a single
regex-based Python script fix all 126 sites in one pass instead of hand-editing each one (verify
with `ast.parse()` immediately after, then confirm total `self._wr_dampen(` call count increased by
the expected amount — 92→218 in this round).

**Pattern to search for next time a scoring sweep is needed:**
`grep -n "quality_score += _[a-zA-Z0-9_]*adj" file.py | grep -v "_wr_dampen"` — if this returns 0,
the adj-variable category is fully covered; combine with the existing literal-bonus grep
(`quality_score += [0-9]`) to confirm both categories are clean.

**False-positive to NOT "fix":** gates whose `_record()` key has no boot-time `_gate_stats` pre-init
entry (found via: keys used in `self._record("gate_x", ...)` minus keys pre-initialized via
`self._gate_stats["gate_x"] = {...}`) are NOT automatically dead gates — `_record()` has had a
`setdefault()` guard since v9.0 specifically to make this safe. ~20 foundational gates
(gate_blacklist, gate_ev, gate_gclh, gate_gdcr, session gates, etc.) intentionally rely on this
lazy-init and all have valid `_GATE_DISPLAY_LABELS` entries — only the boot-time `/gates` snapshot is
briefly incomplete until first fire, which is cosmetic, not a bug. Only add a genuine dead-gate fix
when the `_record()` call itself is unreachable (inside an `except:` that swallows a NameError —
the actual v178 pattern) or the display-label / soft-gate-key entry is missing.
