---
name: Unity Engine v145.0 — US-session-only + vol-spike HARD-BLOCK
description: Why hard-block (not Kelly de-size) is the only lever that moves a SIGNAL bot's WR/Sharpe/maxDD, the two walk-forward-validated cuts shipped, and the structural-drought guard that stops blocked hours from loosening US thresholds.
---

# v145.0 — promote validated negative pockets from Kelly de-size to HARD-BLOCK

## The durable lesson (read this first)
For a SIGNAL bot (emits Telegram alerts, does NOT auto-execute), the headline
metrics the user cares about — signal win-rate, Sharpe, max-drawdown — are computed
over the signals that **FIRE**. Therefore **Kelly de-sizing CANNOT move those
numbers**: the bad signals still fire and their losing outcomes still land in the
WR/Sharpe/maxDD stats. The ONLY lever that moves them is **hard-blocking** (removing
the trades). All the v129.0 Step 106/107 session/vol Kelly de-sizes were therefore
cosmetic w.r.t. the user's stated goal. v145.0 promotes the two walk-forward-validated
negative pockets to deterministic pre-gates.

**Why:** Unity has NEGATIVE validated edge (~−0.09%/trade, source=`bot`). 125+ gates
and 355 NN features across 140+ versions never moved live WR off ~24–29%. The only
robust, out-of-sample-validated improvement is REMOVING the proven-negative pockets.
Best achievable = ~breakeven with roughly halved maxDD, NOT richly profitable. Do not
oversell this to the user.

## What was shipped (all in start_unity_engine.py, mirrors the v144.0 GASN pattern)
- Two default-on env toggles: `UNITY_NONUS_HARDBLOCK` → `NONUS_HARDBLOCK_ENABLED`
  (blocks EU 7-12h + TRANSITION 23h UTC) and `UNITY_VOLSPIKE_HARDBLOCK` →
  `VOLSPIKE_HARDBLOCK_ENABLED` (blocks `volume_ratio > VOL_SPIKE_RATIO_THRESH`=2.0).
  Set either to 0 to revert that cut to v129.0 Kelly-de-size-only behaviour.
- Two pre-gates in `apply()` right after GASN: `gate_session_nonus` (GEUT) and
  `gate_vol_spike` (GVSP). Registered in `_gate_stats`, `_GATE_DISPLAY_LABELS`, and
  `_SOFT_GATE_KEYS` (HUD bottleneck-exclusion — their low pass-rate is intended
  structural gating, not a tunable bottleneck). With GASN they complete the validated
  **US-session-only** filter. In the Asian session GASN returns first, so GEUT/GVSP
  show `---` (never reached) — that is correct, not a bug.
- `UNITY_VERSION` 143.0 → 145.0 (GASN had bumped comments to v144.0 but left the
  constant at 143.0).

## Structural-drought guard (the non-obvious part)
Blocking ~14h/day non-US interacts with the RL relief logic in
`_update_threshold_rl`. Both relief mechanisms — the starvation-decay (`_staleness`,
~19762) and the drought-base-cut (reuses `_staleness`) plus the ultra-ruin
`_floor_stale` (~19733) — key off `_staleness = now − self._last_outcome_ts`.
`_last_outcome_ts` is **outcome-based, not signal-opportunity-based**. Without a
guard, a long non-US block makes staleness huge by the US open, so starvation-decay
/ drought-cut would LOWER US-session thresholds and admit the very low-quality US
signals the cut is meant to filter — partially undoing the edge.

Guard: module-level `_in_structural_block_session()` (Asian if ASIAN_HARDBLOCK, or
EU/TRANSITION if NONUS_HARDBLOCK). At the top of `_update_threshold_rl` compute
`_struct_blocked` and stamp `self._struct_block_exit_ts = now` every blocked cycle
(BEFORE the `win_ring<10` early-return, so cold/warm-start ticks keep it fresh). Then
the relief reads use effective staleness = `0.0` if blocked else
`min(raw, now − _struct_block_exit_ts)` — measured from block-exit (US open), never
from an outcome that resolved before the block began. **Outcome rings untouched** —
only the relief calc's effective staleness moves, so genuine US-session starvation
relief still fires after the normal decay/grace window.

Restart hardening (architect-flagged): `_struct_block_exit_ts` is volatile, init 0.0.
If the process restarts ALREADY in the US session right after a long block, there's
no prior blocked tick to stamp it → clamp degrades to raw warm-start staleness
(`_last_outcome_ts` is pre-aged now−1800s) and starvation-decay fires at US open. Fix:
when not blocked and `_struct_block_exit_ts==0.0` and current UTC hour ∈ [13,22], init
it to 13:00 UTC today (US-open). A `logger.debug` prints raw vs effective staleness
after a block exit for live verification.

## Validation
py_compile OK; clean 21/21 boot as v145.0 (no tracebacks); HUD shows GASN=0% during
Asian, GEUT/GVSP registered, bottleneck row correctly excludes all three. Walk-forward
(`SignalMaestro/walk_forward_backtest.py --source bot --folds 6 --embargo 10`)
reconfirms the **session+vol combo**: OOS avgPnL −0.165% → +0.005% (Δ +0.170%),
Δ maxDD −137.7%, learned=session+vol in ALL 5 folds. rsi_overbought / confidence_high
remain no-ops (not predictive). Architect (evaluate_task) PASSED.

## Gotchas
- `_current_kelly_session()` UTC bands: US=13-22h, EU=7-12h, ASIAN=0-6h, TRANSITION=23h.
- The `read` tool mis-reports file length (~14.6k) vs real ~30.1k lines → use sed/grep
  for lines >14645. sqlite3 CLI absent → use python3.
- NEVER git-revert runtime *.db/*.json/weights (real trade + NN data).
