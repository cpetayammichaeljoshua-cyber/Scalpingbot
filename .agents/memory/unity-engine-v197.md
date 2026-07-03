---
name: Unity Engine v197.0 overscoring sweep — microstructure confluence bonuses
description: 24 flat directional-alignment bonuses in the G8.5D-O2 gate chain were unconditional (not WR-dampened) despite being the same risk category as bonuses fixed in v189-v196; includes an inconsistency where one gate's top consensus tier was dampened but its lower tier was not.
---

Round 6 of the ongoing overscoring/overconfidence sweep (started v178, continued v189-v196).

**Pattern found:** many G8.5 microstructure/confluence gates award a flat `quality_score += N`
bonus the moment a directional/flow signal "aligns" (OFI, CUSUM, VWAP extension, HMM transition,
spread liquidity, volume pressure, funding momentum, WR/EV streak regimes, BTC-GEX cross-pair,
portfolio-optimizer weight, Sortino/G9 regime confirmation). These are structurally identical to
the bonus classes already wrapped in `self._wr_dampen()` in v189-v196 (time-of-day, HTF alignment,
orderbook imbalance, EV estimate, TP1 proximity) — i.e. real-time market-state signals that are
NOT validated to be WR-independent, so they should scale down when live win-rate is suppressed.

**Concrete inconsistency caught:** G8.5E CrossCoherence's 3/3-vote tier (+2.0) was dampened in
v196.0, but its 2/3-vote tier (+0.8) was left as a raw, undampened addition — partial-consensus
signals were still getting an uncalibrated absolute bonus while full-consensus signals were not.

**How to apply:** when auditing quality_score paths for overscoring, don't just check whether a
gate family has *any* `_wr_dampen()` call — check every tier/branch within that gate independently.
A single dampened tier does not imply sibling tiers were covered by the same pass.

**Method used to find these:** `grep -n "quality_score += [0-9]" file.py | grep -v "_wr_dampen"`
lists every raw-literal positive addition; cross-reference against `quality_score -= N` siblings
in the same block to confirm the negative tier is intentionally left un-softened (penalties should
NOT be dampened at low WR — only unconditional positive/bonus paths should be).

**Read-tool line-count caveat still applies:** the `read` tool reports this file's total line count
inconsistently (has shown ~13.6k when `wc -l` reports ~34.8k); always use `sed -n 'X,Yp' file.py` or
`grep -n` with exact line numbers for reliable navigation, not `read` tool offsets on this file.
