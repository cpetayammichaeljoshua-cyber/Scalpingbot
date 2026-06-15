---
name: Unity Engine v115.0 upgrades
description: Comprehensive optimization pass — scalar tightening, G8.5B4 88th gate, Kelly Step 80, NN v46 245feat, G9/IRONS floor recalibration, CPCV rejection tightened
---

## Changes

**Scalar tightening (all targeting WR improvement from 29.4%, EV=-0.314R):**
- EV_MIN_THRESHOLD: 28→40bps (+43% EV quality bar)
- SIGNAL_MIN_QUALITY_GATE: 67→70 (+3pt G9 floor)
- IRONS_MIN_WR_BELOW30: 70→73 (+3pt crisis floor)
- IRONS_MIN_WR_30_45: 67→69 (+2pt recovery tier)
- SOVEREIGN_RECOVERY_GATE: 70→73 (co-equal with IRONS)
- NN_WIN_PROB_GATE: 0.50→0.53 (filters 50-53% NN band)
- MIN_RR_RATIO: 2.50→2.65 (+6% RR floor)
- AI_THRESHOLD_PERCENT: 89→91 (top-9th-percentile LLM conviction)

**G9 WR-tier floors recalibrated (+3pt all tiers to match new base=70):**
- WR<15%→77, WR<20%→73, WR<25%→73, WR<30%→72, WR<35%→71

**G9 MaxDD adaptive floor raise:** >47%→+3, >43%→+2, >38%→+1

**update_adaptive_irons docstring updated:** WR<20%=76, WR<25%=74.5, WR<30%=73

**New gate G8.5B4 — RollingWR-Momentum-Sentinel (88th gate):**
- Uses _booster._pnl_ring last-15 trades
- WR<18%→-3pts, WR<27%→-2pts, WR<34%→-1pt, WR>45%→+1.5pts
- Cold-start (ring<8) → neutral=0
- Sentinel: _last_g85b4_rws
- Registered: _gate_stats, _gate_stats_recent, _GATE_DISPLAY_LABELS, _SOFT_GATE_KEYS

**Kelly Step 80 (RWS-RollingWR-Momentum Sizing):**
- hot (+1)→×1.03, losing/catastrophic (≤-2)→×0.88

**NN v46 — 245 features (F241-F245):**
- F241: b4_rws_gate, F242: b4_roll15_wr, F243: b4_wrt_trend, F244: b4_sharpe_floor, F245: b4_ev_min_dist
- INPUT_DIM 240→245, _TORCH_N_TOKENS 48→49
- trainer build_features updated with pad-on-mismatch pattern
- CPCV near-random rejection added: cpcv_avg<0.51 suppresses push

**CPCV floor:** 0.50→0.51 (near-random rejection)

**Banner/display strings all updated:** 87-gate→88-gate, Steps1-79→Steps1-80, NN-v45-240feat→NN-v46-245feat, Kelly 79-steps→Kelly 80-steps

**Build files:** Dockerfile, requirements.txt, nixpacks.toml headers → v115.0

**Boot result:** 21/21 layers online, clean boot confirmed
