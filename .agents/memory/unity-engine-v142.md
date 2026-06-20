---
name: Unity Engine v142.0 upgrades
description: G8.5W5 WNZ Winsorization-Guard (133rd gate) + G8.5X5 ADF Stationarity-Proxy (134th gate); Kelly Steps 128/129; NN v68 355feat F351-F355; GODMODE Winsorization+ADF prompt; ScanParallel190; clean 134-gate boot 21/21
---

## G8.5W5 WNZ — Winsorization-Normalized Z-Score Guard (133rd gate) [v142.0]
- From FLOAM/StatArb framework: institutional quants winsorize extreme signals at ±3σ before blending
- EMERGENCY -3.5pts: |ofi_z|>2.5 AND |qs_z|>2.5 AND conflicting (opposing signs = capped-conflicting inputs)
- -2.0pts: OFI extreme + opposed to direction; -1.0pts: QS extreme opposed; +1.0pts: one extreme aligned
- +2.0pts: BOTH extremes aligned (peak institutional breakout signal)
- Uses `direction` local variable (scoring path); reads `_quality_score_ring`
- Sentinel: `self._last_g85w5_wnz`; Kelly Step 128 WNZ (×0.75 EMERGENCY / ×0.85 OFI-opposed / ×1.04 dual-aligned)

## G8.5X5 ADF — ADF-Stationarity-Proxy OU-Validity Gate (134th gate) [v142.0]
- Zero-API ADF proxy via lag-1 autocorrelation (ρ₁) + mean-crossing rate on `_quality_score_ring`
- Validates G8.5U5 OUP gate: OU mean-reversion signals are ONLY valid on stationary I(0) processes
- EMERGENCY -3.5pts: non-stationary (ρ₁>0.9 OR xcross<0.1) AND |OU_Z|≥2 (false OU signal)
- -2.0pts: strongly non-stationary (ρ₁>0.9); -1.0pts: weakly non-stationary (ρ₁>0.7)
- +1.0pts: stationary (ρ₁<0.7 + xcross>0.2); +2.0pts: stationary AND OU gate confirmed positive
- Reads `self._last_g85u5_oup` sentinel; Kelly Step 129 ADF (×0.75 EMERGENCY / ×0.85 non-stationary / ×1.04 stationary+OU)

## NN v68 — INPUT_DIM 350→355, _TORCH_N_TOKENS 70→71 [v142.0]
- F351=w5_wnz_gate (0→1 scale from -3→+2); F352=w5_qs_extremity (|qs_z|/4); F353=w5_ofi_extremity (|ofi_z|/4)
- F354=x5_adf_gate (0→1 scale from -3→+2); F355=x5_stationarity (1-|ρ₁|, inverted autocorrelation)
- Weight auto-reset on INPUT_DIM 350→355 mismatch

## GODMODE prompt update [v142.0]
- Winsorization Guard: conflicting ±3σ extremes (OFI+QS opposing) → NEUTRAL; dual-aligned extremes → +6pp
- ADF Stationarity: non-stationary quality ring while OU fires extremes → -15pp confidence

## Infrastructure
- SCAN_PARALLEL_LIMIT 188→190
- SOFT_GATE_KEYS: W5+X5 added (both confirmed non-blocking soft gates)
- All banners: 134-gate, Steps1-129, NN-v68-355feat, Layer 5 banner updated
- Clean boot confirmed: 21/21 layers, Semaphore(190), v142.0 ALL SYSTEMS ONLINE
