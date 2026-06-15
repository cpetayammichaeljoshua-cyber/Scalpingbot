---
name: Unity Engine v110.0 upgrades
description: G8.5T3/U3 critical bug fixes, G8.5V3 82nd gate, Kelly Step 74, NN v42 225feat, IRONS WR<3%=85.0, banner sync
---

## Critical Bug Fixes (v110.0)
- **G8.5T3/U3 `_direction_int` bug**: Both gates were computing `direction` param incorrectly — fixed to proper `direction` local variable derivation.
- **G8.5T3/U3 `quality_score` bug**: 8 occurrences used `self._irons_score` (attribute never exists at gate call time) — replaced with `quality_score` (the gate param). Both gates were silently passing/failing incorrectly.

## G8.5V3 TripleEV-Confidence-Persistence Gate (82nd gate)
- **Sources**: `_last_g85x2_wrt` (WinRateTrajectory, v90.0) + `_last_g85y2_hvc` (HMM-VPIN-Coherence, v91.0) + `_last_g85o3_wnq` (WinRate-CPCV-NNQuality, v106.0)
- **Scoring**: +2.0 (3-way positive), +1.5 (2-way positive), -1.5 (2-way negative), -2.0 (3-way negative)
- **Sentinel**: `_last_g85v3_tec: int = 0` initialized in `__init__`
- **Soft gate key**: `gate_g85v3_tec` added to `_SOFT_GATE_KEYS`
- **F feature**: `v3_tec_gate` injected via `signal_data.setdefault()`

## Kelly Step 74 — TECTripleConf
- `_last_g85v3_tec == 1` → ×1.04 (triple/dual EV-confidence-persistence aligned)
- `_last_g85v3_tec == -1` → ×0.85 (triple/dual EV-confidence-persistence opposed)

## NN v42 — 225 features
- `INPUT_DIM`: 220 → 225
- `_TORCH_N_TOKENS`: 44 → 45 (45×5 token layout)
- F221-F225 injection block added in `start_unity_engine.py` (build_features section)
- `neural_signal_trainer.py`: INPUT_DIM=225, N_TOKENS=45, F221-F225 feature block after F220

## IRONS WR<3% = 85.0
- New ultra-terminal tier added before the WR<4% check
- `self._adaptive_irons_min = IRONS_MIN_WR_BELOW30 + 15.0` (= 85.0)

## Version / Infrastructure
- `UNITY_VERSION`: "109.0" → "110.0"
- `SCAN_PARALLEL_LIMIT`: 134 → 136
- nixpacks.toml header + verify string updated to v110.0, 82-gate, ScanParallel136, 225feat NN v42
- All banners updated: 81-gate→82-gate, Steps1-73→Steps1-74, G8.5V3 added to all gate lists

## Clean Boot Confirmed
- 21/21 layers online, 82-gate filter in banner, G8.5V3:TEC-TripleEVConfPersist[v110.0] listed, Semaphore(136)
