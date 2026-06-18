---
name: Unity Engine v131.0 — Kelly Step 108 ToD×Direction de-size
description: Kelly Step 108 time-of-day × direction de-size, and the durable rule for sourcing per-signal direction inside _update_kelly
---

# Unity Engine v131.0 — Kelly Step 108 (Time-of-Day × Direction de-size)

Adds Kelly Step 108: de-sizes (never blocks) the only 3 hour×direction pockets net-negative across ALL THREE datasets (bot trade_history.db, InsiderTactics 15k CSV, user's 15.4k dashboard): SHORT@22h ×0.55, LONG@15h ×0.60, LONG@20h ×0.75 (UTC). Module const `TOD_DIR_KELLY_DESIZE` keyed `(DIRECTION, utc_hour)`. These sit INSIDE the "US" session that Step 106 (`SESSION_KELLY_DESIZE`) keeps at full ×1.0, so the coarse session cut misses them — non-redundant gap. UTC hour via `time.gmtime().tm_hour`.

## DURABLE RULE: sourcing per-signal direction inside `_update_kelly`
When a Kelly step (or any `_update_kelly` logic) needs the *current signal's direction*, read `self._last_direction` — NOT a new scoring-path stash.
- **Why:** `_last_direction` is the canonical dispatch-path field, set by `note_last_signal()` which is called by `mark_signal_sent()` ONLY for signals that passed all gates. The sibling direction-aware Kelly Steps 20/23/26 already read it. A scoring-path stash (set in `UnitySignalFilter.apply()`) fires for every *rejected* candidate too, so it is staler/noisier and can de-size the wrong direction.
- **How to apply:** `_update_kelly` is called immediately after each dispatch/outcome (`note_last_signal`→`record_outcome`→`_update_kelly`) and also periodically; `_last_direction` therefore tracks the most-recently DISPATCHED signal. Values are `.upper()` → "BUY"/"SELL"/"LONG"/"SHORT"; normalize BUY/LONG→LONG, SELL/SHORT→SHORT. This is as correct as the established direction-aware steps — do not invent a parallel direction field.
- First implementation mistakenly added a redundant `_last_signal_dir` stashed in the scoring path; architect (evaluate_task) flagged the cross-direction-contamination risk; fix was to delete that field/stash and read `_last_direction`.

## Scope discipline (unchanged from prior turns)
Only the 3 triple-confirmed pockets are de-sized. Deliberately NOT implemented (single-dataset / naive-sim signals contradicting the bot's executed data): SL-tighten 25-30%, TP-extend, 70/30 short/long allocation, day-of-week & symbol filters, hours like short@03/long@13-14. De-size-only preserves no-bypass + no-zero-call + drought-safety.
