---
name: Unity Engine v97.0 upgrades
description: v97.0 changes — G8.5E3 EV-FundMom-OFI Triple-Pressure 65th gate, Kelly Step 57, NN v33 180feat (F176-F180), ScanParallel114
---

# Unity Engine v97.0 Upgrades

## Key Changes
- **G8.5E3 EV-FundMom-OFI Triple-Pressure Gate** (65th gate, ±2.0/±1.5pts)
  - Source 1: EV quality tier from signal_data["ev"] (≥0.8R=+1, <0.4R=-1, else 0)
  - Source 2: FundMom Persistence gate `_last_g85n2_fmp_signal` (+1/-1/0)
  - Source 3: OFI Persistence gate `_last_g85b_ofi` (+1/-1/0)
  - +2.0pts: triple-aligned (all 3 agree direction); +1.5pts: dual-aligned
  - -2.0pts: triple-opposed; -1.5pts: dual-opposed
  - Stores `_last_g85e3_efo`; gate stat key `gate_g85e3_efo`
- **Kelly Step 57 EFOTriplePressure** — PRESSURE-ON×1.03 / PRESSURE-OFF×0.87
- **NN v33 INPUT_DIM 175→180** — F176-F180 EV-FundMom-OFI Triple-Pressure features
  - F176: ev_fmp_sync_norm, F177: ev_ofi_sync_norm, F178: fmp_ofi_sync_norm
  - F179: triple_efo_quality, F180: e3_gate_output
- **SCAN_PARALLEL_LIMIT 112→114**
- **All banners**: 65-gate filter, Steps1-57, NN-v33-180feat, ScanParallel114

## Files Modified
- `start_unity_engine.py` — gate stats init, G8.5E3 gate code, Kelly Step 57, F176-F180 injection block, _GATE_DISPLAY_LABELS, _SOFT_GATE_KEYS, all 5 banners, UNITY_VERSION="97.0", SCAN_PARALLEL_LIMIT=114
- `SignalMaestro/neural_signal_trainer.py` — INPUT_DIM 175→180, _TORCH_N_TOKENS 35→36, F176-F180 in build_features()

## F176-F180 Key Map
| F   | Key                   | Source gates used                   |
|-----|-----------------------|-------------------------------------|
| 176 | ev_fmp_sync_norm      | EV tier × FundMom-Persist agreement |
| 177 | ev_ofi_sync_norm      | EV tier × OFI-Persist agreement     |
| 178 | fmp_ofi_sync_norm     | FundMom-Persist × OFI-Persist       |
| 179 | triple_efo_quality    | 3-way EFO alignment quality [0,1]   |
| 180 | e3_gate_output        | G8.5E3 gate output +1/-1/0          |

## Gate Attribute Names Confirmed
- FundMom Persistence: `_last_g85n2_fmp_signal` (set by G8.5N2, Kelly Step 40)
- OFI Persistence: `_last_g85b_ofi` (set by G8.5B, Kelly Step 32)
- EV: read from `signal_data["ev"]` at gate evaluation time
