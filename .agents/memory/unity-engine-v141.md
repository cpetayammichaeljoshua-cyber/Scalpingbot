---
name: Unity Engine v141.0 upgrades
description: G8.5U5 OUP (131st gate), G8.5V5 MFA (132nd gate), Kelly Steps 126/127, NN v67 350-feat, GODMODE OU/FLOAM prompts
---

## v141.0 Summary

### G8.5U5 OUP — Ornstein-Uhlenbeck Process Mean-Reversion (131st gate)
- **Design**: dS_t=θ(μ-S_t)dt+σdW_t → Z_t=(quality_score−μ_ring)/σ_ring (8-sample window from `_quality_score_ring`)
- **Thresholds**: EMERGENCY -3.5pts at |Z|>3.5 (structural break); -2.0 at Z<-2.5; -1.0 at Z<-1.5; +1.0 at Z>1.5; +2.0 at Z>2.5
- **Fires when**: len(ring)≥6 AND σ_ring>0.5 (meaningful quality variation exists)
- **Sentinel**: `self._last_g85u5_oup`; stats key `gate_g85u5_oup`
- **Pure Python**: no numpy import needed (uses sum/len/pow directly)

### G8.5V5 MFA — Multi-Factor Alpha FLOAM IR=IC×√BR (132nd gate)
- **Design**: Fundamental Law of Active Management — IR=IC×√BR
  - IC = quality_score/100 (signal accuracy proxy, normalised)
  - BR = count of 5 orthogonal aligned sources: FLOW(ofi_z>0.5), REGIME(regimesent>0), QUALITY(svq>0), MOMENTUM(mfr>0), MEAN-REV(oup>0)
- **Thresholds**: EMERGENCY -3.5pts at IC<-0.15+BR<3; -2.0 at IR<-0.10; -1.0 at IR<0; +1.0 at IR>0.08; +2.0 at IR>0.15
- **Sentinel**: `self._last_g85v5_mfa`; stats key `gate_g85v5_mfa`
- **CRITICAL**: G8.5V5 reads `_last_g85u5_oup` for BR Category 5 — must run AFTER G8.5U5

### Kelly Steps 126 & 127
- **Step 126 OUP**: ×0.75 EMERGENCY / ×0.85 Z<-2.5 / ×0.95 Z<-1.5 / ×1.02 Z>1.5 / ×1.04 Z>2.5
- **Step 127 MFA**: ×0.75 EMERGENCY(IC<-0.15+BR<3) / ×0.85 IR<-0.10 / ×0.95 IR<0 / ×1.02 IR>0.08 / ×1.04 IR>0.15
- **Pattern**: uses `self._kelly_ceil if hasattr(self, "_kelly_ceil") else self.last_kelly_fraction * 2.0`

### NN v67 — 350 features (F346-F350)
- **F346**: u5_oup_gate — G8.5U5 state {-3→0.0,-2→0.1,-1→0.3,0→0.5,1→0.75,2→1.0}
- **F347**: u5_zscore_signal — OU z-score from quality_score_ring, normalized [-4,+4]→[0,1]
- **F348**: u5_ou_theta — mean-reversion speed proxy: σ/|μ| (capped at 1.0)
- **F349**: v5_mfa_gate — G8.5V5 state {-3→0.0,-2→0.1,-1→0.3,0→0.5,1→0.75,2→1.0}
- **F350**: v5_ir_composite — FLOAM IR=IC×√BR normalized to [0,1]
- **INPUT_DIM**: 345→350; **_TORCH_N_TOKENS**: 69→70 (70×5=350)
- **Trainer file**: `SignalMaestro/neural_signal_trainer.py` lines 84-99
- **Weight auto-reset**: triggers on mismatch, NN retrained at boot

### GODMODE Prompt Upgrades
- Added to [4-CONVICTION] section in `SignalMaestro/godmod3_strategy.py`:
  - FLOAM multi-alpha: 3+ independent sources → +5pp; <2 sources → cap at 65
  - OU z-score: >2.0σ = peak edge (+4pp); <-2.0σ = below threshold (-12pp); |Z|>3.5σ = EMERGENCY NEUTRAL
- **Why**: improves LLM reasoning with StatArb/FLOAM quantitative framework

### Version Counters
- UNITY_VERSION: "140.0" → "141.0"
- SCAN_PARALLEL_LIMIT: 186 → 188
- All 132-gate banners synced
- Architecture banner: Steps1-127, 132-gate filter
- Layer 5 banner: 350-feature NN v67 (70×5 tokens)

### Boot Verification
- Clean 132-gate boot: 21/21 layers online
- Signal gates banner shows G8.5U5:OUP and G8.5V5:MFA correctly
- Semaphore(188) confirmed in scan log
- NN retraining triggered on INPUT_DIM 345→350 mismatch (expected behaviour)
