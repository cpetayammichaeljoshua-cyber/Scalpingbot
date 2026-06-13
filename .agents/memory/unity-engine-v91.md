---
name: Unity Engine v91.0 upgrades
description: v91.0 — G8.5Y2 HMM-VPIN-Coherence (59th gate), Kelly Step 51, NN v27 150-feat, IRONS WR<17%→74.5, ScanParallel102
---

## Changes in v91.0

### G8.5Y2 HMM-VPIN-Coherence Gate (59th gate)
- Dual-source: self._hmm_regime.get_regime() + self._vpin_model.get_signal()
- EXPANSION + clean VPIN (pct<0.20) + aligned → +2.0pts (full coherence)
- EXPANSION OR clean VPIN (one source only) → +1.5pts (partial)
- CONTRACTION + toxic VPIN (pct>0.80) + opposed → -2.0pts (full divergence)
- CONTRACTION OR toxic VPIN (one source) → -1.5pts (partial)
- Stores _last_g85y2_hvc (+1/-1/0) for Kelly Step 51

### Kelly Step 51: HMM-VPIN-Coherence Sizing
- +1 (coherent) → Kelly ×1.03
- -1 (divergent) → Kelly ×0.87

### NN v27: INPUT_DIM 145→150, _TORCH_N_TOKENS 29→30
- F146: hmm_expansion_prob_norm [0,1]
- F147: vpin_pct_norm [0,1]  
- F148: hmm_vpin_coherence_norm [-1,+1]
- F149: hmm_regime_norm [-1,+1]
- F150: vpin_toxic_norm [0,1]
- Injection block reads self._hmm_regime + self._vpin_model in signal stamping path

### IRONS WR<17% Extreme-Ultra Tier
- WR<17% → IRONS≥74.5 [v91.0 extreme-ultra; was sharing WR<18%=73]
- Now 7 IRONS tiers: WR<17%→74.5 | WR<18%→73 | WR<20%→72 | WR<22%→72 | WR<25%→71.5 | WR<30%→70 | WR30-45%→67

### Other
- SCAN_PARALLEL_LIMIT 100→102
- All banners: 58→59-gate, Steps1-50→Steps1-51, NN-v26-145→NN-v27-150, ScanParallel100→102
- IRONS capability stamp updated to v91.0 (added WR<17%→74.5 + WR<22%→72[v90.0])
- Gate 10 boot display updated with 6-tier IRONS breakdown

**Why:** Incremental institutional-grade addition — HMM+VPIN dual-source coherence detects informed-trader flow regime alignment, directly improves signal quality by filtering adverse-selection entries.

**How to apply:** Next version is v92.0; insert G8.5Z2 or similar after G8.5Y2 pass statement; Kelly Step 52 after Step 51; F151-F155 after F150 block; NN v28 INPUT_DIM 150→155, _TORCH_N_TOKENS 30→31; ScanParallel102→104.
