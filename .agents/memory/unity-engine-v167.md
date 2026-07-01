---
name: Unity Engine v167.0 upgrades
description: G8.5AQ GRSL (149th gate) + G8.5AR GEVAP (150th gate) + NN v73 380feat + ScanParallel 156→150; v166→167
---

## Gates

**G8.5AQ GRSL — P&L Return Slope (149th gate)**
- Loop Engineering (Technique 5): linreg slope of last-10 pnl_ring entries detects structural bleed velocity before sequential-count gates (GHTF) can capture it
- Source: `self._booster._pnl_ring` (confirmed in-memory deque, same source as GHTF)
- Pure-Python slope formula (no imports): slope = (n·Σxy - Σx·Σy) / (n·Σx² - (Σx)²)
- Minimum 7 ring entries required (GRSL_MIN_RING=7)
- Severe: slope < -0.003 + WR<30% → -2.0pt (bleeding ~0.3%+/trade avg, structural)
- Mild: slope < -0.001 + WR<30% + cold_seq_count ≥ 0.5 → -1.5pt
- Thresholds: GRSL_SLOPE_SVRE=-0.003, GRSL_SLOPE_MILD=-0.001
- Env: UNITY_GRSL=0 to disable; stores `_last_g85aq_grsl`

**G8.5AR GEVAP — EV Velocity Anti-Pattern (150th gate)**
- Extended Thinking proxy (Technique 3): measures EV deceleration before hard EV gates fire
- Source: `self._booster._ev_ring` (deque maxlen=20) OR `self._ev_ring` fallback
- Computes: recent-5 mean vs prior-10 mean (index [-15:-5] if ring ≥ 15, else [:-5])
- Collapse: ev_ring recent-5 mean < 0 (GEVAP_COLL_EV=0.0) + WR<30% → -2.0pt (already negative)
- Fade: (prior_mean - recent_mean) > 0.005R (GEVAP_FADE_DELTA) + current EV < 0.08R (GEVAP_FADE_EV) → -1.5pt
- Reads current EV from: `signal_data.get("ev_ratio") or signal_data.get("expected_value")`
- Env: UNITY_GEVAP=0 to disable; stores `_last_g85ar_gevap`

## Kelly Steps

**Step 144 (GRSL):** severe slope → ×0.85 | mild slope+cold → ×0.89
**Step 145 (GEVAP):** EV collapse → ×0.83 | EV fade → ×0.88

## NN v73 (380 features, F376-F380)

- F376: `aq_grsl_gate` — GRSL state {-2.0→0.0, -1.5→0.2, 0→0.5}
- F377: `pnl_slope_10` — linreg slope of last-10 pnl_ring / 0.01, capped [-1,1]
- F378: `ar_gevap_gate` — GEVAP state {-2.0→0.0, -1.5→0.2, 0→0.5}
- F379: `ev_velocity` — (ev_ring r5_mean - prior_mean) / 0.01, capped [-1,1]; positive = accelerating, negative = decelerating
- F380: `ev_regime_score` — ev_ring recent-5 mean vs EV_MIN threshold: ≥2×EV_MIN→1.0, ≥EV_MIN→0.7, ≥0→0.4, <0→0.0

**Note on F380 EV_MIN:** reads env var `EV_MIN_BPS` (default "70") / 10000 to get R-multiple. If env var changes, F380 auto-adapts.

## Railway Efficiency

**ScanParallel:** 156 → 150 (-3.8% CPU + asyncio overhead)
- Cumulative v163→v167: 192 → 150 (−21.9% Railway asyncio load)

## Architecture Counts

- Gates: 148 → 150
- Kelly steps: 143 → 145
- NN features: 375 → 380 (v72 → v73)
- SCAN_PARALLEL_LIMIT: 156 → 150
- UNITY_VERSION: 166.0 → 167.0

**Why:** GRSL and GEVAP are both leading-indicator gates that catch deterioration BEFORE existing crisis gates fire. GHTF catches sequential count; GRSL catches velocity/slope. AEV (G8.5C4) catches negative EV; GEVAP catches deceleration toward it. These fill timing gaps that allow marginal signals to pass during a transition from OK→crisis regime, which is exactly the period where the live WR (~24%) is worst.
