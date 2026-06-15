---
name: Unity Engine v103.0 upgrades
description: G8.5H3 EmergencyBrake + G8.5I3 IRFlorSharpe compound gates; IRONS WR<15%=75.5 tier; NN v35 190feat; Kelly Steps 60+61; ScanParallel122; all banners/strings synced
---

## v103.0 changes (2026-06-15) — 69-gate filter, Kelly 61-steps, NN v35-190feat

### Gate 8.5H3 — RecentWR-EmergencyBrake (68th gate, -3.0/-2.0/+1.5pts)
- Reads `self._booster._pnl_ring[-10:]` (last 10 trade returns, >0=win)
- WR-10 < 15% → -3.0pts, `_last_g85h3_ewb = -2` (ultra-crisis)
- WR-10 < 20% → -2.0pts, `_last_g85h3_ewb = -1` (crisis)
- WR-10 > 40% → +1.5pts, `_last_g85h3_ewb = +1` (hot-streak)
- Requires ≥10 ring entries; cold-start neutral
- `_gate_stats["gate_g85h3_ewb"]` + `_last_g85h3_ewb: int = 0` sentinel added

### Gate 8.5I3 — IRONSFloor-Sharpe Compound (69th gate, -2.0/-1.5/+1.5/+1.0pts)
- Reads `self._adaptive_irons_min` + `self._rolling_sharpe` / `self._sharpe_ratio`
- IRONS ≥ 73 + Sharpe < -3.0 → -2.0pts, `_last_g85i3_ifm = -2`
- IRONS ≥ 73 + Sharpe < -2.0 → -1.5pts, `_last_g85i3_ifm = -1`
- IRONS ≤ 67 + Sharpe > -0.5 → +1.5pts, `_last_g85i3_ifm = +2`
- IRONS ≤ 70 + Sharpe > -1.5 → +1.0pts, `_last_g85i3_ifm = +1`
- `_gate_stats["gate_g85i3_ifm"]` + `_last_g85i3_ifm: int = 0` sentinel added

### Kelly Steps 60 + 61
- Step 60 (EWBrake): `_last_g85h3_ewb == -2` → ×0.60; `== -1` → ×0.80; `== +1` → ×1.04
- Step 61 (IRFlorSharpe): `_last_g85i3_ifm in (-1,-2)` → ×0.85; `in (+1,+2)` → ×1.04

### IRONS WR<15% ultra-crisis tier
- Added `current_wr < 0.15` check BEFORE `< 0.18` in `update_adaptive_irons()`
- `self._adaptive_irons_min = IRONS_MIN_WR_BELOW30 + 5.5  # 75.5`
- Closes blind spot where WR<15% = WR<17% = 74.5 (current crisis: WR=10%)

### NN v35 — INPUT_DIM 185→190, _TORCH_N_TOKENS 37→38
- F186 = `recent10_wr_norm` (recent-10 WR deviation from 30% baseline, [-2,+2])
- F187 = `bayes_wr_norm` (all-time Bayes WR deviation, uses `_bayes_alpha/_bayes_beta` on booster)
- F188 = `h3_ewb_gate` (G8.5H3 output float, -2/-1/0/+1)
- F189 = `i3_ifm_gate` (G8.5I3 output float, -2/-1/0/+1/+2)
- F190 = `crisis_depth_score` (IRONS-floor excess + Sharpe normalized, [-1,+1])
- Injection in signal_data block, inside existing F181-F185 try block (extended to F186-F190)
- Pad-on-mismatch remains for backward-compat

### File sync
- `start_unity_engine.py`: UNITY_VERSION="103.0", SCAN_PARALLEL_LIMIT=122
- `SignalMaestro/neural_signal_trainer.py`: INPUT_DIM=190, _TORCH_N_TOKENS=38, F186-F190 in build_features
- `requirements.txt`: header v102.0→v103.0
- `Dockerfile`: header v102.0→v103.0
- `nixpacks.toml`: all v102.0 strings→v103.0, 185-feat→190-feat, 67-gate→69-gate, ScanParallel120→122

**Why:** WR crisis (all-time 29.3%, recent-20 10%) needed zero-API emergency gates. G8.5H3 reads actual recent WR directly from pnl_ring — the most honest signal of trading health. G8.5I3 cross-validates the WR-adaptive IRONS floor against Sharpe to detect compound regimes. IRONS 75.5 tier prevents the 74.5 floor from being used as a false floor when WR falls to 10%.
