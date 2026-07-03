---
name: Unity Engine v178.0 critical dead-gate fix
description: 36 consecutive gates (v142.0-v175.0) were silently non-functional due to undefined-variable NameErrors swallowed by broad exception handling
---

## The bug
In `start_unity_engine.py`, every gate added across roughly 4 months of iteration
(v142.0 "WNZ" through v175.0 "GLCV" — 36 gates in total) used two undefined names
inside their `try` blocks:
- bare `_record(...)` instead of `self._record(...)`
- `score += / score -=` instead of `quality_score += / quality_score -=`

Neither `score` nor a module-level `_record` exists in that scope. Every one of
these gates raised a `NameError` on its very first executed line past the
`_gate_stats` bookkeeping update, and each gate's own `except Exception: pass`
silently swallowed it. Net effect: the point adjustment never applied, and the
gate never registered with `self._record` (the authoritative tracker feeding
`/gates`, `gate_stats_summary()`, and bottleneck reporting) — while the raw
`_gate_stats` dict entry immediately before the crash point *did* still update,
making the gates appear "alive" on dashboards despite doing nothing.

## Why this matters
This is very likely the primary reason live win rate stayed pinned at ~29%
despite dozens of "improvements" layered in from v142.0 to v177.0 — none of
that scoring logic ever actually executed. This confirms and extends the
long-standing project lesson (see other unity-engine-v1xx memory files) that
adding more gates without validating they actually run is not the same as
improving the strategy.

## How it was found
Manual line-range grep across the whole 34k-line file for `_record(` (bare,
not `self._record(`) and `score +=`/`score -=` outside of any local variable
assignment for `score`, confirmed no nested function in that scope ever
defines `score`.

## Fix applied
Scoped regex replace within the exact broken line range (verified before/after
diff touched *only* that range): `_record(` → `self._record(`, `score +=` /
`score -=` → `quality_score +=` / `quality_score -=`, and one `float(score)` →
`float(quality_score)`. Verified with `ast.parse` and a live boot showing zero
exceptions across multiple full scan cycles, with gates correctly rejecting/
passing signals (e.g. ASIAN_SESSION hard-block, BLACKLIST WR<30%).

## Unrelated infra note
During validation, `restart_workflow` reported the workflow as FAILED even
though the process was healthy — the health server bound to port 8080 in
~38s and the app ran cleanly for multiple cycles before being killed. This
appears to be a pre-existing workflow-readiness-timeout quirk for this
heavy multi-service background bot, not a regression from this fix.
