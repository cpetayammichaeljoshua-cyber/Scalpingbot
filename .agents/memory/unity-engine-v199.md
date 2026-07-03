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

## Recurring false-positive pattern: "overconsensus meta-gate double-counting"
A second explorer pass (same session) flagged several meta-gates (G8.5U MomentumConsensus, G8.5A3 VPIN-OFI-Funding, G8.5Y3 MomentumCoh-TripleSync) as "double-counting" because they re-read `_last_gXX_adj`/`_last_gXX_mcs` sentinels from other gates that already applied their own `quality_score` adjustment. Verified all three directly in code: every one already wraps its positive-consensus output in `self._wr_dampen(...)` (tagged `v191.0-FIX`/`v192.0-FIX` "overconsensus dampener"), and negative/veto outputs are intentionally left undampened (confirmed-risk signals, not overconfidence).

**Why:** this architecture is a genuine multi-gate confluence design (individual signal contributes once directly, then again — dampened — when it participates in a majority/consensus vote among peer gates). That's an intentional "boost real edges, don't let raw agreement alone inflate score" pattern, not a bug. The mitigation (WR-dampening the positive side only) was already systematically applied across the v189–v199 sweeps.

**How to apply:** when an explorer flags a meta-gate "TripleSync"/"Consensus"/"Composite" as double-counting, check whether its `quality_score +=` line is already wrapped in `self._wr_dampen(...)`. If yes, it's not a bug — skip it. Also verified in this pass: Kelly Step 132's `self._pnl_ring` (flagged as a possible dead attribute) is a real, populated `deque(maxlen=100)` initialized at engine startup — not a no-op.

## Walk-forward / CPCV assessment (no changes made, verified twice this session)
Reviewed `SignalMaestro/neural_signal_trainer.py` CPCV implementation (K=3 folds, embargo `min(5, n//8)`, 51% floor, 9% gap threshold) twice — once for general soundness, once specifically hunting for look-ahead bias/leakage. Confirmed: chronological train/val split is correct (train = older indices, val = newer), embargo is actually applied as an index-range gap (not just computed and discarded), and the z-score normalizer is fit on training data only (`_fit_normaliser(X_tr_raw)`) before being applied to both splits — no global-fit-before-split leakage. `gate_backtester.py` is a read-only replay tool with no fit step, so leakage doesn't apply there. There is no gate-pruning/kill-switch mechanism tied to WF results, but the system is continuous soft-scoring (points added/subtracted) rather than hard pass/fail gates by design — not a bug. Considered settled; do not re-audit without a new specific hypothesis.

## Standing philosophy (carried from v178 finding)
Live win rate has been stuck ~29% for 4+ months despite 190+ version bumps of new gates. The fix pattern that actually matters is bug-fixing (dead gates, silent no-ops, missing dampeners) — not adding new gates. This pass continued that discipline: 0 new gates added, only consistency/correctness fixes to existing scoring paths.
