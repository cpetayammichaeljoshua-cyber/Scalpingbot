---
name: Unity Engine v77.0 upgrades
description: G8.5H FlowAsymmetry + G8.5I MicroTrend gates; Kelly Step 36; NN v15 INPUT_DIM 85→90 (F86-F90); 42-gate→44-gate string fixes; nixpacks v77.0
---

## What changed in v77.0

### G8.5H — Bid-Ask Flow Asymmetry (43rd gate, ±2.0/+1.5pts)
- Dual-source adverse-selection detector: OFI z-score × OB imbalance cross-product
- Source 1: `self._timing_state.ofi_zscore(symbol)` (aggTrade tick-rule)
- Source 2: `signal_data.get("ob_imbalance", 0.5)` (depth-5 snapshot, injected at F85 block)
- Scoring: `|ofi_z|≥1.5` + both oppose → −2.0pts; OFI alone oppose `|ofi_z|≥1.0` → −1.0pts; both align `|ofi_z|≥1.0` → +1.5pts; `|ofi_z|<0.5` → silent
- Stores `self._last_g85h_ofi_aligned` (+1=dual-align, -1=dual-oppose, 0=neutral) for Kelly Step 36
- Gate key: `gate_g85h`; display label: `G8.5H`

### G8.5I — Close-Microtrend Slope (44th gate, ±1.5pts)
- Linear regression slope of last 10 one-minute closes from module-level `_quant_layer_close_buf`
- Uses `numpy.polyfit` with manual OLS fallback (no-numpy guard)
- **Critical**: uses module-level `_quant_layer_close_buf.get(symbol.upper(), [])` NOT `self._quant_layer_close_buf` (pattern from v75.0 dead-gate fixes)
- Aligned slope → +1.5pts; opposed → -1.5pts; <5 closes in buffer → silent (cold-start guard)
- Gate key: `gate_g85i`; display label: `G8.5I`

### Kelly Step 36 — OFI-Flow Asymmetry Sizing
- Reads `self._last_g85h_ofi_aligned` (set by G8.5H gate above)
- dual-oppose (−1): Kelly ×0.83
- dual-align (+1): Kelly ×1.03
- neutral (0): no change
- Stacks after Step 35 (AVWAP-Extension)

### NN v15 — INPUT_DIM 85→90, 18×5 tokens
- `_TORCH_N_TOKENS = 18` (was 17); `INPUT_DIM = 90` (was 85)
- F86: `ofi_flow_asym_norm` — OFI z × OB imb cross-product [-1,+1]; fallback recomputes from raw `ofi_zscore`+`ob_imbalance`
- F87: `microtrend_slope_norm` — 10-bar close slope normalized [-1,+1]
- F88: `funding_velocity_norm` — funding rate delta last 2 readings [-1,+1]
- F89: `spread_ratio_norm` — spread vs 20-bar median ratio centered [-1,+1]
- F90: `liq_intensity_norm` — liquidation cascade notional [0,+1]
- F86-F90 injection in main engine at same G4/F81-F85 stamping block (setdefault pattern)
- **Why `_funding_rate_ring`**: F88 tries `self._funding_rate_ring.get(sym)` — if this attr doesn't exist, falls back to 0.0 (non-fatal guard)
- **Why `_spread_median_buf`**: F89 tries `self._spread_median_buf.get(sym)` — same non-fatal pattern

### String fixes
- All "42-gate" → "44-gate" across banners, wire_all(), ALL SYSTEMS ONLINE, headless stamp
- "Kelly 35-steps" → "Kelly 36-steps" in docstring/header
- nixpacks.toml: v76.0 → v77.0, 85-feature NN v14 → 90-feature NN v15, SCAN_PARALLEL 76→77

## Boot confirmation
`✅ UNITY ENGINE v77.0 — ALL SYSTEMS ONLINE` confirmed in boot log.
Signal gates line includes `G8.5H:FlowAsymmetry[v77.0] | G8.5I:MicroTrend[v77.0]`.
`💾 [v77.0] Startup state snapshot saved` also confirmed.
