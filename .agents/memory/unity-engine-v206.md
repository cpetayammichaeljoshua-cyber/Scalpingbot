---
name: Unity Engine v206.0
description: G9 FlowStack bonus abs() overscoring bug — fired when G8.5C was maximally NEGATIVE (both HMM+GEX oppose direction), creating conflict-as-confluence error
---

# Unity Engine v206.0 — G9 FlowStack abs() overscoring bug fix

## Bug Fixed

### G9 FlowStack bonus `abs()` direction error
- **Location**: `_evaluate_gate()` → G9 FlowStack block, was line ~22366
- **Condition**: `if abs(getattr(self, "_last_g85c_adj", 0.0)) >= 2.0:`
- **Bug**: `abs()` means the bonus fires when G8.5C = **-2.0** (both HMM+GEX OPPOSE direction = maximum conflict), not just when G8.5C = +2.0 (both HMM+GEX confirm direction = true confluence).
- **Scenario**: OFI ring 3/3 aligned with trade direction BUT HMM and GEX both strongly oppose → this is a **conflict**, not confluence → was still awarding +1.0pt stack bonus (after _wr_dampen)
- **Fix**: `if getattr(self, "_last_g85c_adj", 0.0) >= 2.0:` — positive-only check
- **Impact**: Stack bonus now strictly requires positive dual-confirm. In low-WR regimes where G8.5C frequently fires -2.0 (regime against direction), this eliminates a spurious +0.7-1.0pt bonus that was silently helping bad signals pass G9.

## Full Scan Results (v206.0 session — confirmed clean)
- **Overscoring**: 230 WR-dampened `quality_score +=` sites — sweep confirmed comprehensive (v198.0)
- **GALP/GVLR/GRLB/GCAL/GSEQ/GMOM3/GBATCH/GDSA/GEVL/GRDC/GXWI**: all `# v198.0: WR-dampened` ✅
- **gate_g85m BTC GEX +1.5pt**: `_wr_dampen(1.5) # v197.0` ✅
- **GHTF +1.5pt**: `_wr_dampen(_ghtf_adj) # v198.0` ✅
- **GDIV n<40 +0.5pt**: `_wr_dampen(0.5) # v198.0` ✅
- **G9 exp bonus +1.5pt**: `_wr_dampen(1.5) # v197.0` ✅
- **G9 stack bonus +1.0pt**: `_wr_dampen(_g9_stack_bonus) # v199.0` ✅ (condition bug fixed v206.0)
- **Kelly chain**: self._kelly_ceil properly initialized at line 23074 ✅
- **CPCV**: K=3, purge=min(5,//8), result stored to _last_cpcv_avg ✅
- **GSEV (G8.5BI)**: penalties-only gate (-1.5/-2.0) ✅
- **G8.5CORR sentinel**: 93 gates (post-v204.0) ✅
- **GBATCH variable**: named `_gbat_adj` not `_gbatch_adj` — grep false negative pattern documented

## Boot Confirmation
- v206.0 clean boot: 21/21 layers, Semaphore(110), all WS connected, NN retraining on 1000 trades
