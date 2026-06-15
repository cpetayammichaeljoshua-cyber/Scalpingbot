---
name: Unity Engine v106.0 upgrades
description: G8.5N3/O3 gates, Kelly66/67, NN v38 205feat F201-F205, IRONS WR<8%=79.0, ScanParallel128, 75-gate filter
---

## Changes

- **G8.5N3 OFI-HMM-MicroTrend TripleSync** (74th gate): reads `_last_g85d_ofi_vel` + `_last_g85y2_hvc` + `_last_g85i_microtrend`; 3-vote majority → ±2.0/±1.5pts; sentinel `_last_g85n3_irc`
- **G8.5O3 WinRate-CPCV-NNQuality Coherence** (75th gate): WR-trajectory vote + CPCV-gap vote + NN-quality vote; 3-vote majority → ±2.0/±1.5pts; sentinel `_last_g85o3_wnq`
- **Kelly Step 66** (IRCTripleSync): G8.5N3 aligned → ×1.03, opposed → ×0.87
- **Kelly Step 67** (WNQCoherence): G8.5O3 aligned → ×1.03, opposed → ×0.87
- **NN v38**: INPUT_DIM 200→205, _TORCH_N_TOKENS 40→41; F201-F205 in both `start_unity_engine.py` (injection) and `SignalMaestro/neural_signal_trainer.py` (build_features)
  - F201: `ofi_vel_gate_norm` — G8.5D direction output
  - F202: `hmm_vpin_coh_norm` — G8.5Y2 direction output
  - F203: `irc_triple_gate` — G8.5N3 output ±1
  - F204: `wnq_coherence_gate` — G8.5O3 output ±1
  - F205: `quality_persistence_score` — (N3+O3+M3)/3 composite
- **F196-F200** (v37/v105): also added to neural_signal_trainer.py build_features (were missing from trainer despite INPUT_DIM=200 being set in v105)
  - F196: `crisis_consensus_gate`, F197: `trend_quality_gate`, F198: `sharpe_norm`, F199: `dd_sharpe_composite`, F200: `wr_trajectory_norm`
- **IRONS WR<8% = 79.0** tier: new hyper-extreme tier closes blind spot where WR<8% was treated same as WR<10%=78.0
- **SCAN_PARALLEL_LIMIT** 126→128
- **SOFT_GATE_KEYS** includes gate_g85n3_irc + gate_g85o3_wnq
- **gate_stats**: gate_g85n3_irc + gate_g85o3_wnq initialized in _gate_stats and _GATE_DISPLAY_LABELS
- **UNITY_VERSION** = "106.0"
- All banner strings updated: "75-gate filter", "Kelly(Steps1-67)", "75-GATE SIGNAL FILTER"

## How to apply
Gate sentinels follow the `_last_g85XX_YY` naming pattern. For new triple-sync gates, read 3 pre-existing gate sentinels (no new data sources). G8.5O3 quality vote reads `self._neural_engine.is_trained` / `win_class_accuracy`.

**Why:** Each gate pair adds 2 Kelly steps and 5 NN features (5×5 token block pattern) per version increment.
