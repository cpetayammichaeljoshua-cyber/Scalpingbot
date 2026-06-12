---
name: Unity Engine v80.0 upgrades
description: v80.0 changes — G8.5L2 VolumePressure-Regime 47th gate, Kelly Step 39, NN v17 INPUT_DIM=100 (F96-F100), ScanParallel 82
---

## G8.5L2 VolumePressure-Regime Gate (47th gate, ±2.0/+1.5pts)
- Dict key: `gate_g85l2_vpr`; display label: `G8.5L2`
- vol_ratio ≥ 1.5 AND ofi_z × dir_sign < 0 → −2.0pts (opposed)
- vol_ratio ≥ 1.5 AND ofi_z × dir_sign > 0 → +1.5pts (aligned)
- Uses `volume_ratio` and `ofi_z` already in signal_data (zero-API-call)
- Stores `self._last_g85l2_vpr_signal` (+1/-1/0) for Kelly Step 39
- Registered in `_gate_stats`, `_gate_stats_recent`, `_GATE_DISPLAY_LABELS`, `_SOFT_GATE_KEYS`

## Kelly Step 39 — VolumePressure-Regime Sizing
- Source: `self._last_g85l2_vpr_signal` (set by G8.5L2 gate above)
- Opposed (−1) → Kelly ×0.85
- Aligned (+1) → Kelly ×1.04
- Neutral (0) → no change
- Non-fatal try/except

## NN v17 — INPUT_DIM 95→100 (F96-F100)
- `_TORCH_N_TOKENS = 20` (was 19), `_TORCH_TOKEN_DIM = 5` → 20×5=100
- F96: `vol_ofi_cross` — (vol_ratio−1)/1.5 × ofi_sign × dir_sign [-1,+1]
- F97: `funding_spread_cross` — funding_velocity_norm × (spread_ratio−1) [-1,+1]
- F98: `vpr_signal` — G8.5L2 gate result (+1/-1/0)
- F99: `spread_liq_score` — (spread_pres + liq_intensity_norm) / 2 [-1,+1]
- F100: `regime_5gate_meta` — (hmm_vote + ofi_sign + spr_vote + g85j + g85l2) / 5 [-1,+1]
- Injected at G4 F96-F100 stamping block (after v79.0 F91-F95 block)

## SCAN_PARALLEL_LIMIT 80→82 (+2.5% throughput)

## Version sync
- `UNITY_VERSION = "80.0"`
- Dockerfile: header v80.0, LABEL v80.0, verify string v80.0
- nixpacks.toml: header v80.0, banner "UNITY ENGINE v80.0", SCAN_PARALLEL 82, feature list v80.0
- requirements.txt: header v80.0, 100-feature NN v17
- All startup banners, wire-up log, ARCHITECTURE string updated to 47-gate / Kelly Steps1-39 / NN-v17-100feat
