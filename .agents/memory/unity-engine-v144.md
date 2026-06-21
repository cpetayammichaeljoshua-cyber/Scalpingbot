---
name: Unity Engine v144.0 Asian-session hard-block
description: Why/how the Asian session (0-6h UTC) was converted from soft Kelly de-size to a deterministic HARD-BLOCK gate (GASN); the walk-forward evidence and the constraints that make it safe.
---

# v144.0 — Asian-session HARD-BLOCK (GASN / gate_session_asian)

## What changed
The Asian session (0-6h UTC) was upgraded from a soft Kelly de-size (×0.55,
Step 106 / v129.0) to a deterministic HARD-BLOCK gate in `apply()`, placed as
"Pre-Gate A2" right AFTER `gate_blacklist` succeeds and BEFORE the consec-loss
circuit breaker (Pre-Gate B). Env-toggle `UNITY_ASIAN_HARDBLOCK` (default ON);
set `=0` to revert to de-size-only behaviour. Registered in `_gate_stats` init,
`_GATE_DISPLAY_LABELS` (label "GASN"), and the bottleneck-HUD exclusion set.

## Why
**The rule:** When chasing WR/profitability on THIS bot, the one robust,
repeatedly-validated edge is *cutting* the Asian session — not adding gates or NN
features.
**Evidence:** Fresh 6-fold purged/embargoed walk-forward on the `bot` source
(1,633 resolved trades, Jun-2026): the 0-7h UTC bucket = −0.279%/trade avgPnL,
the rule LEARNED in 4 of 5 OOS folds. REMOVING those trades (not de-sizing) lifts
OOS avgPnL +0.120% and HALVES OOS maxDD (−127.8pts). The ×0.55 de-size only
captured ~half the benefit because losing Asian trades still flowed; a gate-level
block also can't be overridden by the LLM (the soft "force NEUTRAL" prompt can).
**Bigger context:** this bot has a NEGATIVE validated edge overall; ~125+ gates
and 355 NN features across many versions NEVER moved live WR off ~24-29%. The
Asian cut is the only change with real OOS maxDD/avgPnL improvement. Do NOT keep
piling gates expecting WR to move.

## How to apply / gotchas
- GASN blocks via a DIRECT early-return `(False, reason, 0.0)` in `apply()`; it does
  NOT depend on any soft/hard classification downstream.
- `_SOFT_GATE_KEYS` is LOCAL to `gate_bottleneck_str()` (def ~18952, use ~19080) —
  it ONLY filters the bottleneck HUD; it does NOT govern block-vs-adjust semantics
  anywhere. Adding `gate_session_asian` there is a pure HUD-display exclusion so its
  intended 0%-pass during Asian hours doesn't mask the real tunable bottlenecks
  (G0/G4/G0.5). GASN is NOT a soft gate.
- GASN intentionally shows 0% in the Gates HUD during 0-6h UTC (everything blocked)
  and ~100% otherwise — correct, not a bug.
- US is the ONLY positive pocket; left fully untouched. EU/TRANSITION still de-sized
  via Kelly Steps 106/107.
- No global version-banner bump done (avoids the UNITY_VERSION spacing-quirk +
  hardcoded gate-count churn); the change is tagged `[v144.0]` in comments only.
  This is surgical/validated, NOT overfit gate-piling.
