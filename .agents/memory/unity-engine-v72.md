---
name: Unity Engine v72.0 upgrades
description: v72.0 changes — G8.5B OFI-Persistence gate, Kelly Step 31, G9 RegimeExpansion, NN v13 80-feature
---

## G8.5B OFI-Persistence Gate (37th gate, ±2.0pts)
- New soft-gate: `self._ofi_persist_ring` (deque maxlen=3) + `self._ofi_persist_last_update` (Dict)
- Reads `signal_data.get("ofi_z")`, threshold |ofi_z| ≥ 0.3; 45s min update interval per symbol
- 3/3 aligned → +2.0pts; 0/3 aligned → −2.0pts; else ±1.0pts proportional
- `_gate_stats["gate_g85b"]` + `_GATE_DISPLAY_LABELS["gate_g85b"] = "G8.5B"` + in `_SOFT_GATE_KEYS`
- `_record("gate_g85b", _g85b_fired)` call present in gate block

## Kelly Step 31 — Vol-Expansion Regime Scale (×0.80)
- Uses `_quant_layer_close_buf["BTCUSDT"]`, requires ≥31 bars
- Applies ×0.80 when 7-bar log-return realized vol > 1.5× 30-bar realized vol
- Non-fatal (wrapped in try/except pass)

## G9 HMM+GEX Regime-Expansion Bonus (+1.5pts)
- Applies +1.5pts quality_score when `self._hmm_regime.get_regime() == "EXPANSION"` AND `self._gex_snaps[-1].net_gex` aligns with trade direction

## NN v13 — 80-feature, 16×5 tokens
- `INPUT_DIM = 80`, `_TORCH_N_TOKENS = 16` in `SignalMaestro/neural_signal_trainer.py`
- F76: `ofi_persistence_score` (−1 to +1 rolling 3-cycle OFI direction agreement)
- F77: `regime_coherence_score` (−1 to +1 HMM+GEX dual-confirm alignment)
- F78: `vol_expansion_flag` (0/1 7-bar vol > 1.5× 30-bar baseline)
- F79: `hmm_expansion_prob_norm` = (P_exp − 0.5) × 2.0, from `hmm_expansion_prob`
- F80: `spread_regime_flag` (0/1 bid-ask spread > 2× 20-bar median)
- Shape mismatch on boot (75→80) triggers clean re-init via `_load_weights()` — retrain from existing labels

**Why:** 3-cycle OFI persistence isolates real institutional flow from noise; regime coherence captures HMM+GEX dual-confirmation missed by individual gates; vol expansion de-risks Kelly sizing during noisy regimes.

## File sync checklist (all updated)
- `start_unity_engine.py`: UNITY_VERSION="72.0", all "36-gate"→"37-gate", "Steps1-30"→"Steps1-31", Layer 5 boot log, architecture stamp, gate stats init, G8.5B block, Kelly Step 31, G9 bonus, signal gates / footer banner
- `SignalMaestro/neural_signal_trainer.py`: INPUT_DIM=80, _TORCH_N_TOKENS=16, F76-F80 appended to feature extractor
- `nixpacks.toml`: header + verify string (v71.0→v72.0, 75-feat v12→80-feat v13, 36-gate→37-gate)
- `Dockerfile`: line 2 + line 5 v71.0→v72.0

## Boot confirmation (2026-06-12)
Engine booted cleanly: "✅ UNITY ENGINE v72.0 — ALL SYSTEMS ONLINE", 21/21 layers, 37-gate filter confirmed in boot log, NN v13 retrained on 1000 trades without error.
