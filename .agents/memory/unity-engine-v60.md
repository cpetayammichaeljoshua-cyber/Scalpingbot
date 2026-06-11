---
name: Unity Engine v60.0 upgrades
description: Walk-forward CV, HistGBT ensemble, G8.5P 30th gate, G4 sigma boost, focal gamma 3.5 tier — all confirmed clean boot 21/21 layers
---

## What changed in v60.0

### neural_signal_trainer.py

**Walk-Forward Validation with Embargo (replaces 85/15 random split)**
- For n≥40 trades: 80/20 time-ordered split + min(3, train//10) embargo at boundary
- `_va_idx` pre-computed and passed to direction calibration (`_val_idx = _va_idx`)
- For n<40: falls back to 85/15 random split (backward compat)
- `_va_idx` is always defined before direction calibration block in both paths

**HistGradientBoosting Ensemble**
- `self._hgbt: Optional[Any] = None` initialized in `__init__`
- Trained in `train()` after `quality_ok` computed, before `loss_analyzer.fit()`
- `HistGradientBoostingClassifier(max_iter=100, max_depth=4, min_samples_leaf=4, lr=0.10, l2=1.0, class_weight="balanced")`
- Blend applied in `predict_signal()`: `0.70 * base_prob + 0.30 * hgbt_prob` (after Torch blend)
- Falls back to MLP-only if `_hgbt is None` (non-fatal)

### start_unity_engine.py

**G8.5P — BTC Cross-Pair Momentum Alignment (30th gate)**
- Inserted after G8.5U block, before G8.5m
- Uses `self._quant_layer_close_buf.get("BTCUSDT", [])` — no extra API calls
- 5-period vs 20-period MA for BTC direction; requires ≥20 samples
- Skip for BTCUSDT itself; +1.5pts aligned, -1.5pts opposed
- `_g85p_adj = 0.0; _g85p_fired = False` set BEFORE try block (always defined)
- Added to: `_gate_stats`, `_gate_stats_recent`, `_GATE_DISPLAY_LABELS`

**G4 MC Uncertainty Threshold Boost**
- Inserted after G4 compound crisis gate, before `# v37.0 STRICT` comment
- `_nn_sigma_g4 = getattr(nn_trainer, "_last_uncertainty", 0.0)`
- σ>0.15: `delta = min(0.02, (σ-0.15)*0.13)`, cap nn_threshold at 0.58

**Crisis Focal Gamma 3.5 Tier**
- In `_nn_retrain_task`: 3-tier gamma ladder
  - SR<-6 → `_gamma_extreme=True` → γ=3.5, time_decay=5.0
  - SR<-4 or WR<25% → `_gamma_crisis=True` → γ=3.0, time_decay=4.0
  - normal → γ=2.5, time_decay=2.0
- `_gamma_extreme` added to log line alongside `_gamma_crisis`

**30-gate filter banners** — all 4 occurrences updated (lines ~12118, ~12137, ~15657, ~16584)

### File headers
- Dockerfile, nixpacks.toml, requirements.txt: all updated to v60.0
- nixpacks.toml verify script: 29-gate→30-gate, v59.0→v60.0

## Boot confirmation
`✅ UNITY ENGINE v60.0 — ALL SYSTEMS ONLINE — 21/21 layers`
`Signal gates: 30-gate filter | ... G8.5P:BTC-CrossPair | ... [v60.0]`

**Why:**
- Walk-forward CV prevents look-ahead bias (random shuffle let future trades train the past)
- HistGBT adds axis-aligned threshold decisions orthogonal to MLP's smooth boundary
- G8.5P uses already-computed BTCUSDT close buffer — zero API cost
- G4 sigma boost: MC uncertainty is the most direct proxy for regime shift; high σ→higher bar
- Focal gamma 3.5: at SR<-6 the training distribution is most imbalanced; need max minority focus
