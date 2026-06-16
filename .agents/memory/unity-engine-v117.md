---
name: Unity Engine v117.0 upgrades
description: G8.5D4 TimesFM-ForecastConfluence + G8.5E4 TimesFM-RegimeSync gates, NN v48 255feat, IRONS WR<0.5% tier
---

## Changes in v117.0

**G8.5D4 TimesFM-ForecastConfluence (90th gate, ±2.0/+1.5/−1.5pts)**
- Pure-numpy 8-patch (each 4 bars) polyfit slope computation on `_quant_layer_close_buf`
- Confidence = fraction of patches agreeing with aggregate direction
- Stores `_last_g85d4_tfc` (+1/−1/0) and `_last_g85d4_conf` for Kelly Step 82
- Needs ≥8 bars in close buffer; cold-start sentinel `_last_g85d4_tfc = 0`

**G8.5E4 TimesFM-RegimeSync (91st gate, ±2.0/+1.5/−1.5pts)**
- 3-vote consensus: TimesFM (D4) + HMM + OFI; requires ≥2 non-zero votes
- Stores `_last_g85e4_trs` (+1/−1/0) for Kelly Step 83

**Kelly Steps 82 + 83**
- Step 82 TFC: strongly-aligned+high-conf ×1.04, aligned ×1.02, strongly-opposed ×0.84, opposed ×0.90
- Step 83 TRS: aligned ×1.03, opposed ×0.87

**NN v48 (INPUT_DIM 250→255, _TORCH_N_TOKENS 50→51)**
- F251: timesfm_dir_norm (direction {-1,0,+1})
- F252: timesfm_conf_norm (confidence [0,1])
- F253: timesfm_slope_avg (ATR-normalized slope, clipped ±1)
- F254: timesfm_confluence_gate (G8.5D4 output)
- F255: timesfm_regime_sync (G8.5E4 output)
- Feature injection via `signal_data` dict keys stamped in G8.5D4/E4 gate blocks

**IRONS WR<0.5% ultra-supreme tier = 88.5**
- Added before WR<1%=87.5 tier
- Addresses gap where near-zero-edge symbols could still pass with WR<0.5%

**Architecture strings all updated**
- 91-gate filter, Kelly Steps 1-83, NN-v48-255feat, ScanParallel148
- Dockerfile LABEL v117.0, nixpacks verify string v117.0, requirements.txt header v117.0
- Remaining banner at line ~20250 fixed: 89-gate → 91-gate, D4/E4 appended

**How to apply:**
- TimesFM gates read `_quant_layer_close_buf[symbol]` (module global, not self._) — confirmed working pattern from v75.0 fix
- Kelly Steps use `self._last_g85d4_tfc` / `self._last_g85d4_conf` / `self._last_g85e4_trs` sentinel attrs
- NN features stamped in `signal_data` dict before IRONS scoring, same pattern as all other v40+ gates
