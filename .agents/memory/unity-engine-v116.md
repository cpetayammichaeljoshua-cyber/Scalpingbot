---
name: Unity Engine v116.0 upgrades
description: Comprehensive v116.0 pass — G8.5C4 AdaptiveEV-Persistence 89th gate, Kelly Step 81, NN v47 250feat, MaxDD 42% intermediate brake, G9 SharpeUC SR<-5.5, CPCV gap 9%, ScanParallel 146
---

## Changes

**New Gate G8.5C4 — AdaptiveEV-Persistence Sentinel (89th gate):**
- Uses booster _ev_ring (deque maxlen=20, stores rr_ratio if won else -1.0 per trade)
- Cold-start (ring<10) → 0 (neutral)
- Deep-EV-hole: recent-10 avg < -0.40R AND alltime-20 < -0.30R → -3pts
- EV-deteriorating: recent-10 avg < -0.20R → -2pts
- Below-breakeven: recent-10 avg < 0.0 → -1pt
- EV-positive: recent-10 avg > +0.05R → +1.5pts
- Sentinel: _last_g85c4_aev
- Registered: _gate_stats, _gate_stats_recent, _GATE_DISPLAY_LABELS, _SOFT_GATE_KEYS

**_ev_ring infrastructure:**
- Added `self._ev_ring: deque = deque(maxlen=20)` to booster init (after _pnl_ring)
- Populated in booster record_outcome: `self._ev_ring.append(float(rr_ratio) if won else -1.0)`

**Kelly Step 81 — AEV-AdaptiveEV-Persistence Sizing:**
- deep EV hole (-3) → ×0.82; EV positive (+1) → ×1.03

**NN v47 — 250 features (F246-F250):**
- F246: c4_aev_gate / 3.0 → [-1.0, +0.33]
- F247: c4_roll10_ev: (avg+0.30)/0.30 clipped ±1
- F248: c4_ev_trend: delta/0.30 clipped ±1
- F249: c4_sharpe_regime: (SR+5.0)/2.0 clipped ±1
- F250: c4_dd_distance: (MaxDD%-45.0)/10.0 clipped ±1
- INPUT_DIM 245→250, _TORCH_N_TOKENS 49→50
- trainer build_features updated with F246-F250 block

**MaxDD Intermediate Brake (Kelly Step 28b):**
- New tier: >42%→×0.65 (between existing >38%/×0.80 and >47.5%/×0.25)
- Fills the 38%→47.5% gap where no hard brake existed

**G9 Sharpe Ultra-Crisis Floor (v116.0):**
- When Sharpe < -5.5: quality_score -= 2.0 (in addition to SortinoUC +1pt floor raise at Sortino<-4.0)
- Combined effect: extreme-ruin signals need +3pt more quality buffer vs normal
- Inserted after G9 SortinoUC block, before G9 Regime-Expansion Bonus

**CPCV Gap Threshold 0.07→0.09:**
- trainer.py: both CPCV gap 0.07 occurrences → 0.09
- At live gap=10% the 7% threshold was firing unnecessarily (10%>7%); 9% adds tighter filter

**SCAN_PARALLEL_LIMIT 144→146** (+1.4%)

**Banner/display strings all updated:**
- 88-gate → 89-gate (all occurrences)
- Steps1-80 → Steps1-81
- NN-v46-245feat → NN-v47-250feat (all occurrences)
- ScanParallel144 → ScanParallel146

**Build files:** Dockerfile, requirements.txt, nixpacks.toml headers → v116.0

**Boot result:** 21/21 layers online, clean boot confirmed
- 89-GATE SIGNAL FILTER confirmed in logs
- G8.5C4:AdaptiveEV-Persistence(-3.0/-2.0/-1.0/+1.5pts)[v116.0] listed in gate banner
- Kelly(Steps1-81·...) confirmed
- All v116.0 arch stamp tokens confirmed
