---
name: Unity Engine v119.0 upgrades
description: G8.5H4 TimesFM-PatchEnsemble 5-scale + G8.5I4 DrawdownGuard-TimesFM; Kelly86+87; NN v50 265feat; IRONS WR<0.05%=91.0; F259 key collision bug fix; 95-gate; ScanParallel152
---

## Key changes

- **G8.5H4 TimesFM-PatchEnsemble** (94th gate, ±2.0/±1.5pts): 5-scale pure-numpy patch ensemble (8/16/24/32/48-bar windows), 4 patches/scale, polyfit slope/ATR threshold=0.06. ≥4 aligned→+2.0, ≥3→+1.5, ≥3 opposed→-1.5, ≥4 opposed→-2.0. Stores `_last_g85h4_tpe` (+1/-1/0) + `_last_g85h4_conf` ([0,1]).
- **G8.5I4 DrawdownGuard-TimesFM** (95th gate, ±2.0/±1.5pts): MaxDD + TF-vote confluence (H4+F4+G4 sum, range -3 to +3). MaxDD>45%+votes≤-1→-2.0; MaxDD>40%+votes≤-2→-1.5; MaxDD<25%+votes≥+2→+2.0; MaxDD<30%+votes≥+1→+1.5. Stores `_last_g85i4_dgc`.
- **Kelly Step 86** TPE-PatchEnsemble: full-align(conf≥0.80)→×1.04, partial-align→×1.02, partial-oppose→×0.88, full-oppose(conf≥0.80)→×0.83.
- **Kelly Step 87** DGC-DrawdownGuard: healthy+TF→×1.03, ruin-territory+TF-opposed→×0.86.
- **NN v50**: INPUT_DIM 260→265, _TORCH_N_TOKENS 52→53. F261=timesfm_pe_dir, F262=timesfm_pe_conf, F263=timesfm_pe_votes_norm, F264=maxdd_regime_score, F265=dgc_composite.
- **IRONS WR<0.05%=91.0** (21-pt spread above base-70, absolute institutional ceiling).
- **EV_MIN**: 0.0043→0.0046 (43→46bps).
- **SCAN_PARALLEL_LIMIT**: 150→152.
- **F259 key collision BUG FIX** (v119.0): `sharpe_velocity_norm` collided with F181 (F181 always set first via setdefault → F259 was a silent no-op). Fixed: renamed to `sharpe_vel_tf_norm` in both start_unity_engine.py injection AND neural_signal_trainer.py build_features(). Backward-safe (old trades return 0.0).
- **All banners**: 93-gate→95-gate, Kelly Steps1-85→Steps1-87, NN-v49-260feat→NN-v50-265feat, ScanParallel150→152, IRONS-tiers prefix updated to include 91.0.
- **21/21 boot confirmed** — clean start, no errors.

## Why

**Why:**
- G8.5H4 provides a pure-numpy multi-scale temporal ensemble that complements single-patch TimesFM gates by voting across 5 bar horizons — catches momentum alignment that single-scale patches miss.
- G8.5I4 closes a compound risk gap: drawdown-stressed periods need TimesFM cross-gate confirmation, not just a DD gate alone; the joint condition dramatically reduces false positives in high-DD regimes.
- F259 key collision was causing the Sharpe velocity feature to be permanently 0.0 for every trade since v118.0 deployment; all signals since then had this feature zeroed, slightly degrading NN quality.
- IRONS WR<0.05%=91.0 closes the theoretical blind-spot left by v118.0's 90.5 ceiling.

## How to apply

- Gates require `_quant_layer_close_buf` global (≥48 bars for G8.5H4); reads `action` key for direction.
- F259 is now `sharpe_vel_tf_norm` everywhere — old DB trades will have 0.0 for this feature (backward-compatible, no retrain forced).
- Any future feature additions should check collision with all existing F-index keys before deploying.
