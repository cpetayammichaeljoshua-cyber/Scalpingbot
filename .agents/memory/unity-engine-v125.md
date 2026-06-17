---
name: Unity Engine v125.0 upgrades
description: v125.0 changes — G8.5V4/W4 gates (108th/109th), Kelly Steps 100-101, NN v55 290feat F286-F290, ScanParallel162, all banners synced
---

## G8.5V4 — EV-Recovery-Velocity (108th gate)
- Reads `booster._ev_ring` (deque of recent EV-R values), computes linreg slope over last-10 entries
- slope > +0.020 R/trade → +2.0pts; slope > +0.010 → +1.0pts; slope < -0.020 → -2.0pts; else 0
- Cold-start guard: ≥10 ev_ring samples required
- Sentinel: `_last_g85v4_erv` (+2/+1/0/-1)
- Kelly Step 100: ERV +2→×1.03, +1→×1.01, -1→×0.87

## G8.5W4 — WinRate-Acceleration-Coherence (109th gate)
- Reads `booster._pnl_ring` (deque of +1/-1 outcome flags), computes recent-10 WR vs prior-20 WR delta
- delta ≥ +15pp → +2.0pts; delta ≥ +8pp → +1.5pts; delta ≤ -15pp → -2.0pts; else 0
- Cold-start guard: ≥30 pnl_ring samples required
- Sentinel: `_last_g85w4_wac` (+2/+1/0/-1)
- Kelly Step 101: WAC +2→×1.02, +1→×1.01, -1→×0.88

## NN v55 — 290 features (F286-F290)
- F286: ev_recovery_rate — linreg slope×50 clipped [-1,1]
- F287: pnl_ring_mean — mean last-20 pnl outcomes [-1,1]
- F288: wr_10trade_recent — last-10 WR [0,1]
- F289: ev_ring_std_norm — std/0.2 [0,1]
- F290: filter_coherence — quality_score_ring mean/100 [0,1]
- neural_signal_trainer.py: INPUT_DIM=290, _TORCH_N_TOKENS=58, 290=58×5

## Gate stats / display / soft-gate keys
- `_gate_stats["gate_g85v4_erv"]` and `["gate_g85w4_wac"]` added with pass/fail/ring
- `_GATE_DISPLAY_LABELS` updated with both keys
- `_SOFT_GATE_KEYS` updated with both keys (soft-gate, cannot block signals)

## Banner strings synced (all 5 locations)
- Docstring header: v125.0, 109-gate, 101-steps
- IRONS prompt string: 109-gate filter [v125.0]
- _wire_components log: 109-gate, Kelly(Steps1-101·...), V4/W4 listed
- _print_startup_banner log: 109-gate, Kelly(Steps1-101·...), NN-v55-290feat, ScanParallel162
- Launcher stamp: 109-gate, V4/W4 listed
- Continuous scanner banner: 109-gate, G8.5V4+G8.5W4 in gate list

## Boot result
Clean 21/21 boot, Semaphore(162) confirmed in logs
