---
name: Unity Engine v87.0 upgrades
description: G8.5U2 VoV-StabilityRegime (55th gate), Kelly Step 47, NN v23 (130 features / 26×5 tokens), ScanParallel 94
---

## G8.5U2 — VoV-StabilityRegime Gate (55th gate)
- Uses module-level `_quant_layer_close_buf` (NOT `self.*` — v75.0 critical fix)
- CV = std(returns[-20:]) / (mean(|returns|[-20:]) + 1e-9)
- CV < 0.10 → +1.5pts, stable (`_last_g85u2_vov = 1`)
- CV < 0.20 → +0.8pts, stable-ish (`_last_g85u2_vov = 1`)
- CV 0.20–0.35 → 0.0pts, neutral (`_last_g85u2_vov = 0`)
- CV > 0.35 → −1.5pts, chaotic (`_last_g85u2_vov = -1`)
- Requires ≥10 closes in buf; fires `_record("gate_g85u2_vov", ...)`

## Kelly Step 47 — VoV-Stability Sizing
- `_last_g85u2_vov == 1` (stable) → `×1.03`
- `_last_g85u2_vov == -1` (chaotic) → `×0.85`

## NN v23 — 130 features / 26×5 tokens
- `INPUT_DIM = 130` in `neural_signal_trainer.py`
- `_TORCH_N_TOKENS = 25 → 26`
- F126: `vov_stability` (from `_last_g85u2_vov` via `setdefault`)
- F127: `funding_extreme_norm`
- F128: `oi_velocity_norm`
- F129: `depth_ratio_norm`
- F130: `liq_net_momentum`

## F126-F130 Stamping Block
- Located after F121-F125 block in G4 stamping section of `start_unity_engine.py`
- F126 reads `getattr(self, "_last_g85u2_vov", 0)` as a global module float

## Build Metadata
- `SCAN_PARALLEL_LIMIT = 94` (was 92)
- nixpacks.toml header: v87.0
- Dockerfile header: v87.0 / `docker build -t unity-engine:87.0`
- Confirmed boot: 21/21 layers, 55-gate filter, Semaphore(94)

**Why:** Volatility-of-volatility regime is a leading indicator of regime transitions; stable vol environments have higher signal reliability, chaotic vol reduces position size.
