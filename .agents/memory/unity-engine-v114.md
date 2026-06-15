---
name: Unity Engine v114.0 upgrades
description: G8.5Z3+G8.5A4 gates, Kelly78+79, NN v45 240feat, Sharpe/IRONS/win_acc tightening, SCAN_PARALLEL 144
---

## Key changes
- **G8.5Z3 RegimeCrisisQuality-TripleSync** (86th gate, ±2.0/±1.5pts): aggregates RegimeSentiment (G8.5R2) + WRCrisisRegime (G8.5S2) + RegimeMomentumSync (G8.5Z2). Stores `_last_g85z3_rqt`.
- **G8.5A4 FlowVolumeRegime-TripleSync** (87th gate, ±2.0/±1.5pts): aggregates VoV-Stability (G8.5U2) + OBPressure (G8.5V2) + HMM-VPIN-Coherence (G8.5Y2). Stores `_last_g85a4_fvr`.
- **Kelly Step 78** (RQTRegimeCrisisSafety): aligned×1.03/opposed×0.87
- **Kelly Step 79** (FVRFlowVolumeSafety): aligned×1.03/opposed×0.87
- **NN v45**: INPUT_DIM 235→240, _TORCH_N_TOKENS 47→48; F236=z3_rqt_gate, F237=z3_reg_norm, F238=z3_wrc_norm, F239=a4_fvr_gate, F240=a4_vov_cross
- **Sharpe floor**: 0.15→0.22 (both code paths)
- **win_acc floors**: 0.28→0.25 (normal WR≥25%), 0.20→0.18 (WR<25% crisis)
- **IRONS WR<1% tier**: 87.5 added (absolute-maximum extinction tier)
- **SCAN_PARALLEL_LIMIT**: 142→144
- **UNITY_VERSION**: "114.0" (note: variable has extra spaces `UNITY_VERSION                = "114.0"` — use Python replace, not sed)

## Pitfall — version string spacing
`UNITY_VERSION` has many extra spaces before `=`. The sed pattern `UNITY_VERSION = "113.0"` does NOT match. Use Python `content.replace('UNITY_VERSION                = "113.0"', ...)` with the exact spacing.

## Boot verified
- 21/21 layers clean on first restart
- `G8.5Z3:RQT-TripleSync[v114.0]` and `G8.5A4:FVR-TripleSync[v114.0]` visible in boot signal gates banner
- `Semaphore(144)` confirmed in scanner startup log
