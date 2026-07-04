---
name: Unity Engine v201.0 — WR/Sharpe/MaxDD targeted improvements
description: 3 data-confirmed fixes: G8.5BI GSEV gate (167th), NN loss-anchor tier, Kelly Step 162
---

## Rule
F297 (sharpe_ev_velocity = (sharpe_vel_norm+1)/2 × ev_ring_pct) is the #1 NN loss-predictor
(ExtraTrees importance=2.00 across multiple retrains). HIGH value in WR<30% predicts LOSSES
("Optimism Trap"). Gate G8.5BI GSEV fires only in crisis.

**Why:** Counterintuitive — system THINKS things are improving (EV ring + Sharpe velocity rising)
right before a reversion to negative-expectancy regime. Confirmed F297 importance=2.00 stable.

**How to apply:** G8.5BI GSEV: sharpe_ev_velocity>0.65+WR<30%→-1.5pts | >0.75+WR<28%→-2.0pts.
Kelly Step 162: ×0.78 (extreme) / ×0.84 (base). Sentinel: _last_g85bi_gsev.

## NN loss-anchor tier (neural_signal_trainer.py line ~3829)
Problem: training-set WR=37% (raw label ratio _wr_for_cap) → _win_acc_floor=0.25 (≥30% tier).
At win_acc=17.7%<0.25 → NN DISABLED even though loss_acc=87.5%.
Bayesian analysis: P(win|NN predicts WIN) = 211/(211+251) = 45.7% >> 29% baseline.

Fix: Tier-0 "loss-anchor" — loss_acc≥0.80 + _wr_for_cap≥0.30 → floor=0.15.
win_acc=17.7%>0.15 → NN RE-ENABLED with 87.5% loss-detection capability.

**Why:** NN quality gate prevents "always predict LOSS" models. At loss_acc=87.5% the model IS
making win predictions. Bayesian win-precision = 45.7% when NN says WIN vs 29% baseline.

**How to apply:** Only fires when training WR healthy (≥30%) but win_acc low in crisis.
Uses _wr_for_cap (training label ratio = wins/(wins+losses)), NOT live WR.

## G8.5BI vs G8.5A5 (complementary, not redundant)
G8.5A5 SVCSharpeVelConf: uses sharpe_velocity_norm + quality-slope (_last_g85x4_svr) bidirectionally.
G8.5BI GSEV: uses sharpe_ev_velocity (velocity × EV percentile) only as CRISIS penalty (WR<30%).
Confirmed by code review: no double-counting.

## Wiring checklist for any new G8.5B* gate (all required)
gate_stats init | gate_stats_recent init | _last_g85b*_xxx sentinel | persistence sentinel list |
gate logic block | _record() call | _GATE_DISPLAY_LABELS | _SOFT_GATE_KEYS | Kelly Step | banner update
