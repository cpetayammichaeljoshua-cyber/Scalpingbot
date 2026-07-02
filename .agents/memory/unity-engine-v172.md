---
name: Unity Engine v172.0 upgrades
description: G8.5BA GLTB (159th gate) + G8.5BB GCMS (160th gate); Kelly 154+155; NN v78 405feat; ScanParallel 126
---

## v172.0 Key Changes

**G8.5BA GLTB — Loop-Thinking Directional Bias Sentinel (159th gate)**
- Technique 5: Loop Engineering. 10-signal direction ring `_v172_gltb_dir_ring` (updated in GMOM3 block alongside `_v161_dir_ring`)
- LONG-dominated (≥7/10) + WR<30% → -2.0pt; ≥6/10 + cold≥2 → -1.5pt
- SHORT-dominated (≥7/10) + WR≥32% → +1.5pt; ≥6/10 + WR≥30% → +1.0pt
- Guard: ≥8 signals in ring (GLTB_MIN_RING) before firing
- Data: LONG avgPnL=-0.28% vs SHORT+0.26% (trade_history analysis)
- Kelly Step 154: crisis-LONG→×0.85, cold-LONG→×0.88, SHORT-alpha→×1.03

**G8.5BB GCMS — Checker Meta-Score Synthesis Gate (160th gate)**
- Technique 6: Workflow Isolation. Reads 15 `_last_g85*` sentinels (aw_ghrz through gltb)
- neg≥5+WR<30% → -2.5pt; neg≥4+cold≥2 → -2.0pt; neg≥3+WR<32% → -1.5pt
- pos≥5+WR≥32% → +2.0pt; pos≥4+WR≥30% → +1.5pt
- Kelly Step 155: compound-hostile→×0.82/×0.85/×0.88; consensus→×1.04/×1.02

**NN v78:** INPUT_DIM 400→405, _TORCH_N_TOKENS 80→81 (81×5=405)
- F401: ba_gltb_gate, F402: dir_bias_ratio, F403: bb_gcms_gate, F404: neg_gate_density, F405: gate_consensus_score

**Infrastructure:** UNITY_VERSION 171.0→172.0; SCAN_PARALLEL 130→126; 158-gate→160-gate; 153-steps→155-steps

**Why:** LONG structural bias is the #1 EV bleed source at WR=29%. No single gate detects it; the loop (GLTB) and the meta-checker (GCMS) catch compound hostility invisible to individual gates.
