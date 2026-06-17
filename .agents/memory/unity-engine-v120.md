---
name: Unity Engine v120.0 upgrades
description: 5 new gates (G8.5J4-N4, 100th total), Kelly Steps 88-92, NN v51 270feat, IRONS WR<0.02%=91.5, EV48bps, ScanParallel154, timesfm==2.0.1
---

## Key changes
- **Gates**: G8.5J4 TFMSMultiScale (7-scale TF vote) + G8.5K4 PSRRegimeAlign + G8.5L4 WSDTriple + G8.5M4 OFMicroTriple + G8.5N4 TFCConsensusMeta = 100th gate
- **Kelly Steps 88-92**: one per new gate; use `self.last_kelly_fraction` + `self._kelly_ceil` (NOT `position_size_frac` / `_kelly_hard_cap` — those don't exist)
- **NN v51**: INPUT_DIM 265→270, _TORCH_N_TOKENS 53→54; F266-F270 (tf_multiscale_dir, psr_regime, wsd_triple, ofm_micro, tfc_consensus)
- **IRONS**: WR<0.02%=91.5 tier added
- **EV floor**: 46bps→48bps
- **ScanParallel**: 152→154
- **timesfm==2.0.1**: added to requirements.txt, nixpacks.toml pip-install line, and Dockerfile

## Critical lesson
Kelly steps in the sizing function use `self.last_kelly_fraction` (instance attribute) and `self._kelly_ceil` (instance cap). Variables `position_size_frac` and `_kelly_hard_cap` do NOT exist and will silently no-op if used inside a `try/except Exception: pass` block.

**Why:** All Kelly steps from Step 1 onward (pre-existing code) use `self.last_kelly_fraction`. The mismatch caused all 5 new steps to silently fail until caught in the final variable-name grep check.
