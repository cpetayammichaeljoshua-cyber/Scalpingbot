---
name: Unity Engine v179.0 overconsensus dampener + persisted-gate-stats false alarm
description: G8.5CORR family correlation dampener for the ~59 chained Triple-X meta-gates; documents why a brand-new gate showing 0/0 in /gates right after deploy is NOT necessarily a dead-gate bug
---

## What shipped
G8.5CORR "Family Correlation Dampener" — a consolidated soft-gate inserted after the
G8.5Z5 block. Reads all ~59 `_last_g85XX_yyy` sentinel attributes written by the
Triple-X/Composite meta-gate family (G8.5A3 through G8.5Z5, v93.0-v143.0), and applies
a Wilson/√corr-style clawback (rho=0.65 engineering estimate) to `quality_score` when
≥6 of those sentinels are simultaneously active. This corrects a real overconsensus bug:
many of those 59 gates chain EARLIER meta-gate outputs as inputs to LATER meta-gates, so
a handful of true independent primitives (OFI/HMM/GEX/VPIN/funding/WR-trajectory) get
re-scored dozens of times as if each were fresh independent evidence.

## Debugging false alarm — read this before assuming a new gate is a dead no-op
Immediately after deploying, `/gates` showed the new gate at `0/0 total` while a sibling
gate (`gate_g85z5_ics`) already showed `pass=35`. This looked identical to the v178.0
class of bug (silent NameError-swallowed dead gates). It was NOT that bug. Two
independent, compounding causes made it look that way:

1. **`_gate_stats` is a lifetime accumulator persisted to disk** (`unity_filter_state_v6.json`)
   and merged back in in a key-safe way at boot (`for gate_key in self._gate_stats: if
   gate_key in persisted[...]: ...`). A gate that has existed across many prior process
   restarts (like z5) will show large persisted counts immediately at boot, before the new
   process has evaluated a single live signal. A brand-new gate key legitimately starts at
   0/0 because it has no history in the persisted file. Comparing raw totals between an
   old gate and a same-boot new gate is not a valid liveness check.

2. **Time-of-day hard-blocks can prevent the scoring function from ever being reached.**
   This engine hard-blocks ALL signals during Asian session (00-06h UTC) at a pre-gate
   stage before the deep quality-scoring method (`apply()`, ~5000 lines, houses the entire
   G8.5* gate chain) is ever invoked. If you deploy a new gate and test during an active
   hard-block window, `apply()` — and therefore your new gate — will correctly show 0
   calls all cycle, with zero exceptions logged, because it was never reached at all.

## How to actually verify a new soft-gate isn't dead
Don't rely solely on live `/gates` deltas right after deploy, especially near a hard-block
window. Instead: extract the exact gate code block via `sed`, dedent it, and `exec()` it
against a minimal mock `self` object (with `_gate_stats`, `_gate_stats_recent`, `_logger`,
`_record`) both with all-zero sentinels and with enough sentinels set to force the
`fired` branch. This proves the logic is exception-free and produces the expected
`quality_score` delta without needing to wait out a live hard-block window.

**Why:** an hour was nearly lost chasing a phantom "silently swallowed exception" bug
(the exact bug class this whole audit exists to catch) that turned out to be normal
persisted-stats + session-hard-block interaction.

**How to apply:** whenever validating a brand-new gate immediately after deploy, check
current UTC hour against known hard-block windows (Asian 0-6h, EU/TRANSITION per
`UNITY_NONUS_HARDBLOCK`) and check `unity_filter_state_v6.json`'s `gate_stats` for
pre-existing persisted counts before concluding a gate is dead from `/gates` alone.
