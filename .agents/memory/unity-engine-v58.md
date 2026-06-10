---
name: Unity Engine v58.0 upgrades
description: G8.5U MomentumConsensus meta-gate (29th gate); pre-init sentinel pattern; KEY GATES stamp fix; all file headers updated to v58.0
---

## G8.5U — Momentum Soft-Gate Consensus Meta-Gate (29th gate)

**Rule:** After G8.5T and before G8.5m, insert G8.5U which reads the already-computed `_g85w_adj/_g85w_fired`, `_g85x_adj/_g85x_fired`, `_g85t_adj/_g85t_fired` variables (all in local scope from prior try blocks) and aggregates their directional votes into a consensus adjustment.

**Why:** At WR=27%, signals pass G9 even when ALL 3 momentum data sources oppose direction. Each soft gate nudges quality by ±1–2.5pts individually, but their combined counter-consensus was never evaluated. G8.5U imposes −3.0pts when all 3 oppose — enough to push a borderline 67pt signal below the G9 quality floor.

**Scoring:**
- 3/3 positive adj (all agree with direction): +2.0pts
- 2/3 positive: +0.5pts
- 1/3 positive (split): −1.5pts
- 0/3 positive (all oppose): −3.0pts ← WR-killer filter
- Guard: only fires if `n_data ≥ 1` (at least 1 gate had live market data)
- Soft-gate: in `_SOFT_GATE_KEYS` → excluded from gate_bottleneck_str

**How to apply:** The gate lives in `_evaluate_signal_quality()` after G8.5T's `except Exception: pass` and before `# ── Gate 8.5m`. Fully wired: `_gate_stats`, `_gate_stats_recent`, `_GATE_DISPLAY_LABELS`, `_SOFT_GATE_KEYS`.

## Pre-init sentinel pattern

**Rule:** Add `_g85w_fired = False; _g85w_adj = 0.0 / _g85x_fired = False; _g85x_adj = 0.0 / _g85t_fired = False; _g85t_adj = 0.0` BEFORE the G8.5w gate comment. This ensures G8.5U never hits NameError even if any upstream gate try-block throws an exception early.

**Why:** Python does not have block scoping — variables set inside a try block ARE accessible outside. BUT if an exception fires before the assignment line, the variable is undefined. Pre-init eliminates this race.

## Version-sync notes (v58.0)

- UNITY_VERSION: 57.0 → 58.0
- Gate count: 28-gate → 29-gate (6 banner strings updated)
- KEY GATES docstring comment: "v49.0" → "v58.0" (was stale since v49.0 era)
- nixpacks.toml verify block: 28-gate → 29-gate, "Kelly25-TurboVec-G8.5T" → "Kelly25-G8.5U-MomentumConsensus"
- Dockerfile header: v57.0 → v58.0
- requirements.txt header + Last verified: v57.0 → v58.0
