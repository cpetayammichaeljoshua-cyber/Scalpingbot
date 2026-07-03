---
name: Unity Engine v191.0 power-mode bug hunt
description: Two gates with zero analytics wiring since original creation (not just misplaced _record); overconsensus dampener extended to 2 raw-vote-count meta-gates the v179/v189 sweep missed
---

## Two "invisible since creation" dead gates (distinct from the v178/v190 _record-inside-try pattern)

Gate 8.5k (IVCrush, since v18.72) and Gate 8.5r (FinRobot Funding-Rate Alignment, since v21.3) adjusted `quality_score` for 100+ versions but were **never given `_gate_stats`/`_record` wiring at all** — this is a different bug class than the v178.0/v190.0 mass fixes (which had wiring that was misplaced inside a try/except and silently swallowed). These two had *no* wiring whatsoever, so they never showed up in `/gates`, `gate_stats_summary()`, or bottleneck detection, yet were still actively scoring signals the whole time.

**Why this matters:** the v178.0 and v190.0 mass-fix sweeps searched for the *misplaced-_record-in-try* pattern specifically and would not have caught gates missing wiring entirely. A gate can be "dead to analytics" via at least two independent bug shapes:
1. `_record()` called, but positioned where an exception swallows it (v178.0/v190.0 pattern).
2. `_record()`/`_gate_stats` registration never added in the first place (this v191.0 pattern).

**How to apply:** when auditing for dead gates, don't just grep for `_record` inside `except: pass` blocks — also cross-check every gate that touches `quality_score` against the full `_gate_stats` key list and `_GATE_DISPLAY_LABELS`/`_SOFT_GATE_KEYS` registries. A gate present in scoring logic but absent from all three registries is a silent no-op to observability even though it's live in production.

## Overconsensus dampener sweep gaps

v179.0 (G8.5CORR) and v189.0 (G7 6-path GEX) both built WR-smoothing ramps for overconfident consensus bonuses, but the sweep wasn't applied file-wide — two more raw-vote-count meta-gates (G8.5U 5-gate momentum consensus, G8.5N4 5-model TimesFM consensus) still had unramped raw bonuses (+2.5/+1.5/+0.5, or -2.5/-2.0/+2.0/+2.5) up through v190.0.

**Why this matters:** raw "N out of 5 independent signals agree" is not itself calibrated evidence of edge, especially in a WR-suppressed regime — it just means correlated technical indicators moved together. Only the *negative* veto side of consensus (all oppose = something is wrong) has been empirically validated as a real edge; the positive "everyone agrees, ride it" side is the overconfidence risk.

**How to apply (pattern used, reusable for future consensus gates):** dampen only the positive branch, using: `mult = max(0.70, min(1.0, 0.70 + ((wr-0.25)/0.15)*0.30))` where `wr` is normalized to 0-1. Leave negative penalties/vetoes at full strength. When adding a new gate whose scoring is "count how many sub-signals agree," check whether it needs this same treatment before shipping — it's an easy category to miss during incremental additions since each new consensus gate looks locally reasonable in isolation.
