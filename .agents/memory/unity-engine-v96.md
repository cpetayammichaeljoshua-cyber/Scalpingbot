---
name: Unity Engine v96.0 upgrades
description: v96.0 changes — G8.5D3 RDWTripleRisk 64th gate, Kelly Step 56, NN v32 175feat, ScanParallel112; plus critical discovery that neural_signal_trainer.py was stuck at INPUT_DIM=155 (v92.0) through v96.0
---

# Unity Engine v96.0 Upgrades

## Key Changes
- **G8.5D3 Regime-Drawdown-WinRate Triple-Risk Gate** (64th gate, ±2.0/±1.5pts)
  - Sources: `_last_g85r2_rs` (RegimeSentiment) × `_last_g85w2_ddm` (DrawdownMomentum) × `_last_g85x2_wrt` (WinRateTrajectory)
  - +2.0pts: triple-aligned (all 3 agree direction); +1.5pts: dual-aligned
  - -2.0pts: triple-opposed; -1.5pts: dual-opposed
  - Stores `_last_g85d3_rdw`; gate stat key `gate_g85d3_rdw`
- **Kelly Step 56 RDWTripleRisk** — RISK-ON×1.03 / RISK-OFF×0.87
- **NN v32 INPUT_DIM 170→175** — F171-F175 Regime-Drawdown-WinRate features
  - F171: rs_ddm_sync_norm, F172: rs_wrt_sync_norm, F173: ddm_wrt_sync_norm
  - F174: triple_rdw_quality, F175: d3_gate_output
- **SCAN_PARALLEL_LIMIT 110→112**
- **All banners**: 64-gate filter, Steps1-56, NN-v32-175feat, ScanParallel112

## Critical Discovery: neural_signal_trainer.py was at v92.0 (INPUT_DIM=155)
- `SignalMaestro/neural_signal_trainer.py` holds `_TORCH_N_TOKENS` and `INPUT_DIM` — NOT start_unity_engine.py
- The file was stuck at `INPUT_DIM = 155`, `_TORCH_N_TOKENS = 29` (v92.0 level) through all sessions v93.0-v96.0
- Fixed in v96.0 session: added F156-F175 all at once, bumped to `INPUT_DIM = 175`, `_TORCH_N_TOKENS = 35`
- Previous sessions wrote the injection blocks in start_unity_engine.py (signal_data.setdefault calls) but never found/updated the trainer file
- NN weights auto-reset on INPUT_DIM mismatch — no manual action needed; retrain happens automatically

**Why:** The NN trainer is imported from a separate module file, not defined inline. All future NN INPUT_DIM / _TORCH_N_TOKENS / build_features() changes must target `SignalMaestro/neural_signal_trainer.py`, not start_unity_engine.py.

**How to apply:** For every new NN version:
1. Edit `SignalMaestro/neural_signal_trainer.py`: bump `INPUT_DIM` (+5), bump `_TORCH_N_TOKENS` (+1), add F(N+1)–F(N+5) block in `build_features()` before `arr = np.array(f, ...)`
2. Edit `start_unity_engine.py`: add F-injection block (signal_data.setdefault calls) before `if isinstance(signal_data, dict) and callable(_pfd):`

## Files Modified
- `start_unity_engine.py` — gate stats init, G8.5D3 gate code, Kelly Step 56, F171-F175 injection block, _GATE_DISPLAY_LABELS, _SOFT_GATE_KEYS, all 5 banners, UNITY_VERSION="96.0", SCAN_PARALLEL_LIMIT=112
- `SignalMaestro/neural_signal_trainer.py` — INPUT_DIM 155→175, _TORCH_N_TOKENS 29→35, F156-F175 in build_features()

## F156-F175 Key Map (all added in v96.0 session retroactively)
| F   | Key                   | Version |
|-----|-----------------------|---------|
| 156 | vpin_ofi_conf_norm    | v93.0   |
| 157 | vpin_fund_conf_norm   | v93.0   |
| 158 | ofi_fund_conf_norm    | v93.0   |
| 159 | triple_conf_quality   | v93.0   |
| 160 | vpc_gate_output       | v93.0   |
| 161 | hmm_ofi_sync_norm     | v94.0   |
| 162 | hmm_spread_sync_norm  | v94.0   |
| 163 | ofi_spread_sync_norm  | v94.0   |
| 164 | triple_hmm_quality    | v94.0   |
| 165 | b3_gate_output        | v94.0   |
| 166 | ofi_vpr_sync_norm     | v95.0   |
| 167 | ofi_ev_sync_norm      | v95.0   |
| 168 | vpr_ev_sync_norm      | v95.0   |
| 169 | triple_voe_quality    | v95.0   |
| 170 | c3_gate_output        | v95.0   |
| 171 | rs_ddm_sync_norm      | v96.0   |
| 172 | rs_wrt_sync_norm      | v96.0   |
| 173 | ddm_wrt_sync_norm     | v96.0   |
| 174 | triple_rdw_quality    | v96.0   |
| 175 | d3_gate_output        | v96.0   |
