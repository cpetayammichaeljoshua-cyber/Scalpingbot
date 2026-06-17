---
name: Unity Engine v129.0 — session+volume Kelly de-size + self._kelly_ceil dead-step finding
description: How the walk-forward-validated session/volume Kelly de-size was wired, and the critical discovery that self._kelly_ceil is never assigned (silently neutering ~51 existing Kelly-step reads)
---

# v129.0 — Walk-forward-validated Session + Volume Kelly DE-SIZE

Wired the OOS-validated session/volume de-size (from `SignalMaestro/walk_forward_backtest.py`)
into the live engine as two new **Kelly Steps 106 + 107**, appended at the END of
`_update_kelly` (after the Step 105 except block, before `@property paper_mode`).

- **Session de-size (Step 106)** — time-based, robust, signal-agnostic. Module helper
  `_current_kelly_session()` uses `time.gmtime().tm_hour` (no new import; `time` already
  imported). Windows mirror `get_current_market_session()` in
  `SignalMaestro/mirofish_swarm_strategy.py` (highest-activity tie-break):
  US=13-22h, EU=7-12h, ASIAN=0-6h, TRANSITION=23h. `SESSION_KELLY_DESIZE` keeps US ×1.0,
  de-sizes EU/ASIAN/TRANSITION ×0.55.
- **Volume de-size (Step 107)** — `vol_ratio > VOL_SPIKE_RATIO_THRESH (2.0)` → `×0.70`
  (`VOL_SPIKE_KELLY_DESIZE`). Reads `booster._last_vol_ratio`, which is stashed in the
  `UnitySignalFilter` scoring path where `_vcr = signal_data["volume_ratio"]` is read.
  ~1-signal staleness (Kelly is portfolio-level, recomputed every ~30s) — accepted as a
  coarse soft risk overlay, architect-reviewed OK.
- Both steps `max(0.0, frac*mult)` with **no `_kelly_ceil` clamp** (de-size only, mult<1
  keeps value below ceiling). Each wrapped in `try/except` (non-fatal), `_logger.debug`.
- Magnitudes 0.55/0.70 are deliberately SOFTER than the backtest's ×0 drop → **drought-safe**
  (engine has a zero-signal→restart-loop failure mode). Combined non-US+spike ≈ ×0.385.

**Why:** validated lever — US is the only positive-expectancy session; dropping the others
HALVES OOS maxDD. De-size (not hard-block) captures most of the drawdown benefit while
keeping signals flowing.

## CRITICAL durable facts about the Kelly path (verified, non-obvious)

- `_update_kelly(self)` is **signal-agnostic / portfolio-level** — takes NO `signal_data`.
  It recomputes `last_kelly_fraction` FRESH each call (cold-start path returns early at
  `<10` trades). Called periodically (~30s console loop) + on `record_outcome` +
  threshold-RL. → Appending de-size steps does **not** compound across calls.
- `last_kelly_fraction` drives position SIZE only; it is **not** used as a signal-emission
  gate. → De-sizing can never cause a signal drought.
- **`self._kelly_ceil` is NEVER assigned anywhere.** Only a LOCAL `_kelly_ceil` exists inside
  `_update_kelly` (set ~lines 18149/18155/18293). The ~51 `self._kelly_ceil` reads in the
  existing Kelly steps (from ~line 20422 onward, the `min(self._kelly_ceil, frac*1.0x)`
  fine-tuning steps) raise `AttributeError` → silently caught by each step's `try/except`
  → **those steps are NO-OPS, their multiplier is never applied.** This CORRECTS the prior
  v120 memory note that said "use self._kelly_ceil". Latent bug, left UNFIXED in v129.0
  (fixing would silently re-activate ~30 dormant steps = a big sizing change needing its own
  validation). **How to apply:** for any new Kelly step use the LOCAL `_kelly_ceil` (in scope
  throughout `_update_kelly`), or for a pure de-size (mult<1) skip the clamp entirely.
- `mark_signal_sent()` has NO caller in `start_unity_engine.py` (so `set_last_signal()` is
  likely dead) → the scoring-path stash is the reliable source for `_last_vol_ratio`.

## Status
- Boots clean (21/21 layers); `py_compile` OK; session classifier verified across all 24h.
- Architect verdict: SHIP, no must-fix items.
- Version constant left at v128.1 (banners not bumped); "v129.0" used only as a feature-wave
  label in comments. A full version-bump + Railway header sync was intentionally not done.
