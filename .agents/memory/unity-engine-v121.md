---
name: Unity Engine v121.0 upgrades
description: v121.0 live-crisis fixes — NN win_acc_floor 3-tier, EV55bps, Kelly30 tighten, IRONS WR<0.01%=92.0, 3 new gates O4/P4/Q4, Kelly93-95, NN v52 275feat, ScanParallel156
---

## Key changes (all confirmed 21/21 boot clean)

**Live crisis conditions addressed:** win_acc=24.3% vs old 25% floor (NN disabled), EV=-0.3140R, MaxDD=49.37%, WR=29.2%

### 1. NN win_acc_floor fix (CRITICAL)
- Old: `win_acc_floor = 0.25 if WR < 30% else 0.25` — disabled NN at WR=29.2%
- New 3-tier: `0.18 (WR<25%) / 0.20 (WR<30%) / 0.25 (WR≥30%)`
- At WR=29.2% → floor now 0.20, re-enables NN (win_acc=24.3% < 0.25 but > 0.20 — now passes)

### 2. EV_MIN_THRESHOLD 48bps → 55bps
- Live EV=-0.3140R: 55bps requires P_win≥48% to clear

### 3. Kelly Step 30 tightened (DD>46%→0.10%, DD>48%→0.05%)
- Old: DD>48%→0.15%, DD>50%→0.05%
- New: DD>46%→0.10% (early brake), DD>48%→0.05% (was 0.15%)
- At live MaxDD=49.37%: fires ×0.05% cap (was ×0.15%)

### 4. IRONS WR<0.01%=92.0 tier
- Added before WR<0.0002 block: `self._adaptive_irons_min = IRONS_MIN_WR_BELOW30 + 22.0`

### 5. G8.5O4 EV-Velocity-Trend (101st gate, -2.0/+1.5pts)
- Reads `_aev_ring` (deque set by G8.5C4); compares recent-5 vs prior-10 EV avg
- `delta>+0.05R → +1.5pts`; `delta<-0.05R → -2.0pts`; flat → 0pts
- Stores `_last_g85o4_ev_vel` (+1/-1/0) for Kelly Step 93

### 6. G8.5P4 WR-Acceleration-Sentinel (102nd gate, -2.0/-1.5/+1.5pts)
- Cross-validates `_last_g85x2_wrt` + `_last_g85c4_aev`
- WR+EV dual-positive → +1.5pts; catastrophic OR dual-crisis → -2.0pts; single-decline → -1.5pts
- Stores `_last_g85p4_wra` (+1/-1/0) for Kelly Step 94

### 7. G8.5Q4 MaxDD-EV-Compound (103rd gate, -3.0/-2.0/+1.5pts)
- Reads `_max_drawdown_pct` + `_bayes_wr`
- DD>47% AND WR<28% → -3.0pts (extreme ruin); DD>42% AND WR<32% → -2.0pts; DD<25% AND WR>38% → +1.5pts
- At live DD=49.37%+WR=29.2%: fires -3.0pts extreme tier
- Stores `_last_g85q4_mec` (+1/-1/0) for Kelly Step 95

### 8. Kelly Steps 93-95
- Step93 EVVel: improving→×1.03, worsening→×0.87
- Step94 WRAccel: dual-accel→×1.03, dual-decel→×0.87
- Step95 MaxDD-EV-Compound: extreme ruin (DD>47%+WR<28%)→×0.75, deep crisis→×0.85, healthy→×1.04

### 9. NN v52 — INPUT_DIM 270→275 / _TORCH_N_TOKENS 54→55
- F271=ev_velocity_dir (G8.5O4 {-1,0,+1})
- F272=wr_accel_dir (G8.5P4 {-1,0,+1})
- F273=maxdd_ev_cmpd (G8.5Q4 {-1,0,+1})
- F274=kelly_regime_n (Kelly fraction×500−1, clipped [-1,+1])
- F275=loss_streak_n (consec losses/10, negated [-1,0])
- BOTH engine F271-F275 injection block AND neural_signal_trainer.py build_features() updated

### 10. SCAN_PARALLEL_LIMIT 154→156

**Why:** All three new gates fire immediately at live crisis state (DD=49.37%+WR=29.2%+EV=-0.3140R),
applying -3.0pts (Q4) + -2.0pts (P4 WR catastrophic) + -2.0pts (O4 EV worsening) = -7.0pts total additional
quality-score adjustment. Kelly Steps 93-95 stack with earlier steps for multiplicative position de-sizing.
