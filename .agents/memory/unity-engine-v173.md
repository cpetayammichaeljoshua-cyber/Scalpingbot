---
name: Unity Engine v173.0 upgrades
description: G8.5BC GDSA (161st gate) + G8.5BD GEVL (162nd gate), Kelly 156+157, NN v79 410feat, NN inference indentation bugfix
---

## Gates Added

### G8.5BC GDSA — Direction-Selective Alpha Gate (161st gate)
- **What**: Detects SHORT-side win-rate alpha by tracking direction-split rolling WR using `_v172_gltb_dir_ring` (existing).
- **Logic**: GDSA_HOSTILE_N=6 (min ring). When SHORT-WR clearly exceeds LONG-WR (alpha confirmed): +2.0/+1.0pt. When LONG-side is deeply hostile (SHORT crushed LONG): -1.0/-1.5pt.
- **Sentinel**: `self._last_g85bc_gdsa` (int), init 0.
- **signal_data keys injected**: `bc_gdsa_gate`, `short_alpha_score`
- **Kelly Step 156**: SHORT-alpha-full ×1.05 / mild ×1.02 / LONG-severe ×0.87 / crisis ×0.90.

### G8.5BD GEVL — EV Loss Velocity Gate (162nd gate)
- **What**: Linear-regression slope of `ev_ring` (existing). Detects accelerating EV deterioration.
- **Logic**: GEVL_MIN_RING=10. Slope < threshold = collapsing EV → -2.0/-1.5pt. Slope > 0 + positive EV → +1.0pt.
- **Sentinel**: `self._last_g85bd_gevl` (int), init 0.
- **signal_data keys injected**: `bd_gevl_gate`, `ev_velocity_norm`, `dir_ev_corr`
- **Kelly Step 157**: collapse ×0.82 / drift ×0.88 / recovery ×1.03.

## NN v79 — 410 Features (F406-F410)
- `_TORCH_N_TOKENS`: 81 → 82 (82×5=410)
- `INPUT_DIM`: 405 → 410
- F406: bc_gdsa_gate, F407: short_alpha_score, F408: bd_gevl_gate, F409: ev_velocity_norm, F410: dir_ev_corr
- Both `start_unity_engine.py` and `SignalMaestro/neural_signal_trainer.py` updated.

## Infrastructure Updates
- UNITY_VERSION: 172.0 → 173.0
- SCAN_PARALLEL: 126 → 122
- Gate stats init: added `gate_g85ba_gltb`, `gate_g85bb_gcms` (v172, were missing), `gate_g85bc_gdsa`, `gate_g85bd_gevl`
- `_GATE_DISPLAY_LABELS`: added G8.5BA/BB/BC/BD entries
- `_SOFT_GATE_KEYS`: added gate_g85ba_gltb, gate_g85bb_gcms, gate_g85bc_gdsa, gate_g85bd_gevl
- Boot logger Layer 5: "405-feature NN v78 (81×5 tokens" → "410-feature NN v79 (82×5 tokens"
- Boot logger gate filter: 160-GATE → 162-GATE (added GDSA+GEVL entries)
- Launcher banner: 160-gate → 162-gate; Kelly 155-steps → 157-steps; file header v172.0 → v173.0

## Critical Bug Fixed (NN Inference Indentation)
**Problem**: After inserting the F406-F410 try/except injection block, the `if isinstance(signal_data, dict) and callable(_pfd)` NN inference block (which sets `nn_prob`) was left at 20-space indentation — inside the F406-F410 `except Exception:` handler. This meant NN inference would only run when the F406-F410 injection threw an exception (i.e., never in normal operation).

**Fix**: Dedented `if isinstance` / `elif` / `else` and their bodies from 20→16 spaces and 24→20 spaces respectively, placing the NN inference block correctly outside the except, running always.

**Why**: The F406-F410 try/except was inserted BEFORE the `if isinstance` block, pushing the latter into the new except's scope. The identical issue would occur whenever a new try/except injection is added before this NN inference block.

**How to apply**: Any future F4xx injection block must be inserted BEFORE the `if isinstance` NN inference block, AND the `if isinstance` block must remain at 16-space indentation (outside all injection try/excepts).
