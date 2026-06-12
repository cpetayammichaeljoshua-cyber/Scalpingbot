---
name: Unity Engine v83.0 upgrades
description: v83.0 changes — CONSORTIUM MIN_VOTES fix, G8.5P2 EV-Crisis gate, Kelly Step 42, NN v20 F111-F115, build_features F106-F115 critical fix
---

## Summary
v83.0 (2026-06-12) — Primary focus: fix CONSORTIUM always falling to ULTRAPLINIAN (MIN_VOTES=2 with 1 responding model), add EV-Crisis quality gate targeting the current EV=−0.314R drawdown.

## Critical build_features Bug Fixed
**F106-F115 were NOT in neural_signal_trainer.py `build_features` function** — only in the inference injection path via `signal_data.setdefault()` in start_unity_engine.py G4 block. This caused `Feature shape 105 ≠ 115` training error on first boot of v83.0. Fixed by adding F106-F110 (v82.0) and F111-F115 (v83.0) to `build_features` in neural_signal_trainer.py, all defaulting to 0.0 for historical trades that predate these features.

**Why:** Every time INPUT_DIM grows, the new features must be added to BOTH: (1) the inference injection block in start_unity_engine.py, AND (2) the `build_features` function in neural_signal_trainer.py. Forgetting (2) causes immediate training crash on boot.

## CONSORTIUM MIN_VOTES Fix (godmod3_strategy.py)
`_CONSORTIUM_MIN_VOTES` 2 → **1**

Root cause: With MIN_MODELS=1 (v82.0) and MIN_VOTES=2, a single responding model can never satisfy the 2-vote directional consensus requirement. CONSORTIUM fails → falls through to ULTRAPLINIAN every cycle. MIN_VOTES=1 allows single-model CONSORTIUM (all quality checks still applied, just with 1 vote as the winning direction).

## New Gate: G8.5P2 EV-Crisis Quality Gate (50th gate)
- Init key: `gate_g85p2_evcrisis`, signal: `_last_g85p2_ev_crisis` (−1=ultra-crisis, 0=neutral)
- Logic: reads `self.expected_value_r` + `self.max_drawdown_pct`
  - EV < −0.30R → −3.0pts (ultra-crisis; fires immediately at current EV=−0.314R)
  - EV < −0.20R (and ≥ −0.30R) → −1.5pts (standard crisis)
  - MaxDD > 45% AND EV < −0.15R → additional −1.0pts (compound penalty)
  - Requires ≥10 resolved trades (sample guard)
- Added to `_GATE_DISPLAY_LABELS` and `_SOFT_GATE_KEYS`

## Kelly Step 42: EV-Crisis De-Sizing
- Ultra-crisis (`_last_g85p2_ev_crisis == -1`, EV < −0.30R) → Kelly ×0.80 (fires now)
- Standard crisis (EV < −0.20R, no ultra flag) → Kelly ×0.88
- Compound (MaxDD > 45% + EV < −0.15R) → Kelly ×0.85 (additive)

## NN v20: INPUT_DIM 110→115
- `_TORCH_N_TOKENS`: 22 → 23 (23×5=115)
- `INPUT_DIM`: 110 → 115
- F111: `ev_crisis_norm` — EV / 0.5, clipped [−1,+1]
- F112: `max_dd_norm` — −MaxDD / 50, clipped [−1,0]
- F113: `ev_crisis_gate` — G8.5P2 output (−1/0)
- F114: `kelly_fraction_norm` — (Kelly − 1%) / 1%, clipped [−1,+1]
- F115: `risk_composite` — (F111+F112+F113+F114)/4, clipped [−1,+1]

## SCAN_PARALLEL_LIMIT: 86 → 88

## Files Changed
- `SignalMaestro/godmod3_strategy.py` — _CONSORTIUM_MIN_VOTES 2→1
- `start_unity_engine.py` — version, scan_parallel, gate init/impl/labels/softkeys, Kelly Step 42, NN F111-F115 injection, docstring, KEY GATES, banner
- `SignalMaestro/neural_signal_trainer.py` — INPUT_DIM 110→115, _TORCH_N_TOKENS 22→23, F106-F115 in build_features (critical fix)
- `Dockerfile` / `nixpacks.toml` — version strings synced to v83.0
