---
name: Unity Engine v177.0 — Markov overscoring fix + healthz DMS threshold
description: Wilson lower-bound fix for Markov SOVEREIGN bonus small-sample overscoring; healthz Dead-Man's Switch latency threshold fix (context for v176.0, not previously recorded)
---

## Markov SOVEREIGN overscoring (v177.0)

`UnityMarkovChainGate` granted a flat `MARKOV_BOOST_PTS=16.0` quality-score bonus
whenever raw sample proportion `p_ij >= MARKOV_CHAIN_THRESHOLD (0.87)`, with
`MARKOV_CHAIN_MIN_OBS=3`. At n=3 the only way to hit p_ij≥0.87 is 3/3 wins
(p_ij=1.0), which is pure small-sample noise (binomial σ≈19%) in a coarse
4-bucket state space (LONG/SHORT × MAJOR/ALT). +16pts alone can clear the
G9=73 floor from a base quality score as low as 57 — confirmed live: right
after boot, all 4 states independently showed `1.00(3)⚡` SOVEREIGN simultaneously.

**Fix:** added `UnityMarkovChainGate._wilson_lower_bound(p_hat, n, z=1.645)`
(one-sided 95% CI) and gated `quality_adjustment()`'s SOVEREIGN (+16) and
STRONG (+70%, MILD +8) tiers on the Wilson lower bound instead of raw p_ij.
n=3/3-wins now yields p_lb≈0.53 (no longer clears 0.87); a genuine n=200/90%
state still clears at p_lb≈0.86. Penalty tier (dynamic floor vs global_wr)
intentionally left on raw p_ij — conservative in the penalty direction, not
an overscoring vector. Dashboard `state_summary()` ⚡ indicator also switched
to the Wilson bound so display matches actual gating.

**Why:** any point-accumulation gate with a small min-observation count and a
raw-proportion threshold is vulnerable to this same failure mode — noise
masquerading as high-confidence evidence, disproportionately valuable because
a single such bonus can outweigh many gates' worth of genuine signal.

**How to apply:** when auditing other `+N pts` gates for "overscoring", check
(a) the minimum sample size before the gate activates, (b) whether the
threshold is applied to a raw sample proportion/mean rather than a confidence
interval, and (c) whether the point value alone is large enough to swing the
final gate decision independent of other evidence. If all three hold, that
gate is a strong overscoring candidate — apply a Wilson/Beta-binomial lower
bound rather than tightening MIN_OBS or the raw threshold (tightening MIN_OBS
just delays the same failure to a slightly larger unlucky streak).

## healthz Dead-Man's Switch (v176.0, undocumented until now)

`/healthz`'s DMS latency threshold was hard-coded at 500ms — far below a real
scan-cycle latency for an 80-symbol multi-layer engine, so `latency_breach`
was structurally always true. Raised `dms_limit_ms` to 90000ms. Verify via
`curl localhost:8080/healthz` → `latency_breach:false`.
