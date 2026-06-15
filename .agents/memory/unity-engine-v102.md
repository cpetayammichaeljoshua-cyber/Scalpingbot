---
name: Unity Engine v102.0 upgrades
description: v102.0 changes — G8.5G3 gate, Kelly 58+59, NN v34 185feat, sentinel fix, neural trainer F181-F185
---

## Key changes in v102.0

1. **_last_g85f3_mlc sentinel FIX** — was missing from gate init block; added alongside `_last_g85e3_efo`.

2. **G8.5G3 SharpeVelocity-QualityMomentum** — 67th gate (±2.0/+1.5pts); reads `_last_g85x2_wrt` + `self._booster.sharpe_ratio`; requires ≥10 trades.

3. **Kelly Step 58 (MLC)** — G8.5F3 aligned→×1.02, diverge→×0.88.
   **Kelly Step 59 (SVQ)** — G8.5G3 momentum-up→×1.03, collapse→×0.87.

4. **NN v34 185 features** — F181-F185 (sharpe_velocity_norm, wrt_sharpe_sync, kelly_health_tier, g85g3_svq_gate, quality_momentum_composite).
   - `INPUT_DIM = 185`, `_TORCH_N_TOKENS = 37` (37×5=185) in `SignalMaestro/neural_signal_trainer.py`.
   - F181-F185 also appended in `build_features()` in `neural_signal_trainer.py`.

5. **Pad-on-mismatch fix in neural_signal_trainer.py** — shape check changed from strict `!=` raise to pad-with-zeros when `shape < INPUT_DIM`, raise only when `shape > INPUT_DIM`. Prevents training crash on old 180-feat stored trades after upgrade.

6. **SCAN_PARALLEL_LIMIT 118→120**.

## Files changed
- `start_unity_engine.py` — all gates, Kelly, NN injection, banners
- `SignalMaestro/neural_signal_trainer.py` — INPUT_DIM 185, _TORCH_N_TOKENS 37, F181-F185, pad fix
- `requirements.txt`, `Dockerfile`, `nixpacks.toml` — version strings synced to v102.0

**Why:** Standard per-version upgrade pattern. The pad-on-mismatch pattern must be applied in `neural_signal_trainer.py` every time INPUT_DIM increases, or startup NN retraining will throw `ValueError: Feature shape N ≠ M` on old stored trades.
