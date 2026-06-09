---
name: Unity Engine v49.0 upgrades
description: NN v11 (70 features), G8.5w/G8.5x new gates, stale-comment purge, version sync across all deployment files
---

## NN v11: INPUT_DIM 65 → 70 (14 tokens × 5 dims)

`SignalMaestro/neural_signal_trainer.py`:
- `_TORCH_N_TOKENS = 14` (was 13), `INPUT_DIM = 70` (was 65)
- F66 `funding_extreme`: ±1.0 at |fr|≥0.10%, ±0.5 at ≥0.05%, else 0 (aligned to squeeze direction vs signal dir)
- F67 `ofi_aligned`: `ofi × direction` ∈ [-1,+1] — OFI already existed as raw F51; this version is direction-signed
- F68 `liq_cascade_dir`: SHORT_liq=+1 (bullish), LONG_liq=-1 (bearish), 0=neutral — from `trade["liq_net_side"]`
- F69 `momentum_aligned`: `tanh(sum(price_returns[:8]) × direction × 200)` ∈ [-1,+1]
- F70 `vol_spike_flag`: +1 if vol_ratio>1.8, -1 if <0.55, else 0
- Shape check: `build_features()` confirmed → 70 at runtime (validated via Python AST + unit test)
- Backwards compatible: all new fields default to 0 for legacy trade records

**Why:** Existing 65-feat vector had no direct microstructure signals beyond raw OFI. Adding funding, liquidation direction, signed momentum, and vol-regime flags gives the MLP direct evidence of the F&G=10 Extreme Fear regime currently live.

## G8.5w: Multi-Timeframe Momentum Alignment (±2.5pts)
In `start_unity_engine.py`, inserted **between G8.5r and G8.5m**:
- Uses `signal_data["price_returns"]` (8-bar lag array, same data as NN F43-F50)
- Short window = avg(ret[0], ret[1]); Medium window = avg(ret[2:8])
- Both aligned → +2.0pts; one aligned → +0.8pts; both oppose → -2.5pts; one opposes → -0.8/-1.0pts
- Threshold: >0.0005 for short (5bps per bar), >0.0003 for medium — skips noise

## G8.5x: Liquidation Cascade Direction (±2.0pts)
In `start_unity_engine.py`, inserted **between G8.5w and G8.5m**:
- Reads `signal_data["liq_net_side"]` (LONG/SHORT) and `signal_data["liq_magnitude"]` (0-1 float)
- Strong cascade (mag>0.5) confirms dir: +1.5pts; opposes: -2.0pts
- Moderate cascade: +0.8/-1.0pts
- Complements existing `gate_liq_cascade` (GLIQ) which is a hard pass/fail; G8.5x is the directional quality adjustment

## Stale comments purged
- `KEY GATES (v40.0)` → `KEY GATES (v49.0)` in docstring line 33
- `NN_v9:60feat(+5GEX)` → `NN_v11:70feat(+5regime+5microstructure)` in line 43
- `GODMODE:17models+11combos` → `GODMODE:10models+10combos` (accurate count)
- Added `27-gate filter [v49.0]` line to docstring

## Version sync
- `start_unity_engine.py`: `UNITY_VERSION = "49.0"`, v49.0 IMPROVEMENTS section added
- `Dockerfile`: VERIFY print + LABEL version/description → v49.0
- `nixpacks.toml`: header comment → v49.0
- `requirements.txt`: header + Last verified date → v49.0 / 2026-06-09
