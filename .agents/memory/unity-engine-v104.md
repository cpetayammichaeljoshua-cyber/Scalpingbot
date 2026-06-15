---
name: Unity Engine v104.0 upgrades
description: v104.0 upgrades — G8.5J3 LLM-Technical-Coherence 70th gate, G8.5K3 StreakSession-Compound 71st gate, Kelly Steps 62+63, NN v36 195feat, IRONS WR<12% tier, NNQuality adaptive loss floor
---

## v104.0 Summary

### 1. G8.5J3 — LLM-Technical-Coherence (70th gate, ±2.0/±1.0/+1.5pts) [v104.0]
- Cross-validates LLM action (BUY/SELL) against 3 independent technical signals: OFI z-score direction, HMM regime direction, UTBot direction
- Unanimous (3/3 or 2/2 agree): +1.5pts; all oppose (0/3): -2.0pts; majority oppose (1/3 agree with total=3): -1.0pts
- Requires ≥2 signals to fire; zero-API; stores `_last_g85j3_ltc` (-1/0/+1) for Kelly Step 62
- OFI: |ofi_z|≥0.30 threshold; HMM: state string keyword matching (BULL/EXP/TREND vs BEAR/MEAN/CONT/REV)
- `action` key from `signal_data` used (not `direction` — see v99.0 direction-key bug)

### 2. G8.5K3 — StreakSession-Compound (71st gate, -2.0/+1.5pts) [v104.0]
- Compounds consecutive loss/win streaks with UTC session quality
- ConsecLoss≥3 + dead-zone UTC → -2.0pts; ConsecWin≥2 + prime-session UTC → +1.5pts
- Uses `_booster._consec_losses/_consec_wins` (getattr safe); inline `import datetime as _dt_k3`
- Stores `_last_g85k3_ssc` (-1/0/+1) for Kelly Step 63

### 3. Kelly Step 62 — NN-Quality-Dampener (v104.0)
- `trainer.trained=False` → Kelly ×0.72 (NN disabled = selectivity layer lost)
- `trainer.trained=True` AND `last_win_acc > 0.40` → Kelly ×1.03
- Uses `last_win_acc` attribute added to neural_signal_trainer.py

### 4. Kelly Step 63 — Streak-Session-Compound Sizing (v104.0)
- `_last_g85k3_ssc == -1` → Kelly ×0.78; `_last_g85k3_ssc == +1` → Kelly ×1.04

### 5. NN v36 — INPUT_DIM 190→195, _TORCH_N_TOKENS 38→39 (v104.0)
- F191: `nn_enabled_flag` (0.0/1.0 — trainer active)
- F192: `llm_tech_coh` (G8.5J3 output normalized)
- F193: `streak_session_compound` (G8.5K3 output normalized)
- F194: `consec_loss_norm` (consec_losses/5, capped [0,1])
- F195: `realized_ev_norm` (EV/R normalized [-1,+1])
- `last_win_acc` and `last_loss_acc` attributes added to trainer for Kelly Step 62 readback

### 6. Adaptive loss_acc floor (neural_signal_trainer.py)
- When WR<30%, `loss_acc_floor` drops from 0.50 → 0.40 (less strict selectivity requirement under crisis)
- Prevents the trainer from refusing to activate just because loss-side accuracy is mediocre in a low-WR regime

### 7. IRONS WR<12% ultra-ultra tier = 76.5 (v104.0)
- Added to `update_adaptive_irons()` as first-check highest-severity tier
- Tiers now: WR<12%→76.5, WR<15%→75.5, WR<17%→74.5, WR<20%→73, WR<22%→72, WR<25%→71.5, WR<30%→70, 30-45%→67, ≥45%→62

### 8. SCAN_PARALLEL_LIMIT 122→124
- Small throughput increment (+1.6%)

### 9. All banners/strings updated
- "69-GATE SIGNAL FILTER" → "71-GATE SIGNAL FILTER"
- KEY GATES gate list: J3+K3 added, "69-gate filter [v103.0]" → "71-gate filter [v104.0]"
- CAPABILITY_STAMP: "69-gate filter" → "71-gate filter", "Steps1-61" → "Steps1-63"
- ARCHITECTURE logger: "69-gate filter" → "71-gate filter", Steps1-61→63, NN-v35-190feat→NN-v36-195feat, ScanParallel122→ScanParallel124, IRONS-tiers string updated
- requirements.txt/Dockerfile/nixpacks.toml headers: v103.0→v104.0

**Why:** WR crisis (recent-20 WR=10%, Sharpe=-4.870, MaxDD=49.37%) requires new compounding selectivity layers:
- G8.5J3 adds cross-validation between LLM output and zero-API technical signals
- G8.5K3 punishes the worst-case scenario (losing streak in dead zone) hardest
- Kelly 62 de-risks automatically when NN is offline (selectivity layer missing)
- IRONS WR<12% tier catches extreme crisis before it becomes catastrophic
