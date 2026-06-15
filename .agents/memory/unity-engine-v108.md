---
name: Unity Engine v108.0 upgrades
description: v108.0 changes — G8.5R3/S3 gates (78th/79th), Kelly 70+71, NN v40 215feat, IRONS WR<5%=82.0, ScanParallel132, all display strings synced. Clean 21/21 boot confirmed.
---

## v108.0 Summary (2026-06-15)

### New Gates
- **G8.5R3 BWOTripleMomentum** (78th gate, ±2.0/±1.5pts):
  - Triple: `_last_g85x2_wrt` + `_last_g85d_ofi_vel` + `_last_g85p3_fos` (BTC-WRTraj+OFI-Vel+FOS)
  - Sentinel: `_last_g85r3_bwo`; registered as `gate_g85r3_bwo`
  - +2.0pts triple-aligned, +1.5pts dual-aligned, -1.5pts dual-opposed, -2.0pts triple-opposed
- **G8.5S3 QSCCompositeHealth** (79th gate, ±2.0/±1.5pts):
  - Triple: `_last_g85o3_wnq` + `_last_g85q3_rke` + `_last_g85f3_mlc` (WNQ+RKE+MLC quality triad)
  - Sentinel: `_last_g85s3_qsc`; registered as `gate_g85s3_qsc`
  - +2.0pts triple-quality-green, +1.5pts dual-green, -1.5pts dual-red, -2.0pts triple-red

### Kelly Sizing
- **Step 70 BWOTripleMomentum**: `_last_g85r3_bwo==+1 → ×1.03`; `==-1 → ×0.87`
- **Step 71 QSCCompositeHealth**: `_last_g85s3_qsc==+1 → ×1.03`; `==-1 → ×0.87`

### Neural Network v40
- INPUT_DIM: 210 → 215 (`_TORCH_N_TOKENS` 42 → 43, 43×5=215)
- F211: `bwo_triple_norm` (G8.5R3 output ±1)
- F212: `qsc_composite_norm` (G8.5S3 output ±1)
- F213: `r3_s3_consensus` = (BWO+QSC)/2 [-1,+1]
- F214: `meta_quality_health` = (WNQ+MLC+QSC)/3 [-1,+1]
- F215: `momentum_stack_norm` = (BWO+FOS+RKE)/3 [-1,+1]
- Injection block after F210 block; pad-on-mismatch inherited

### IRONS Tier
- WR<5% → `IRONS_MIN_WR_BELOW30 + 12.0 = 82.0` [absolute-catastrophe tier]

### ScanParallel
- `SCAN_PARALLEL_LIMIT` 130 → 132 (+1.5%)

### Display Strings — All Synced to v108.0
- ARCHITECTURE header: `79-gate filter · Kelly 71-steps`
- KEY GATES header: IRONS stamp + `82.0(WR<5%)[v108.0]`
- Wired components stamp: `79-gate filter`, `Kelly(Steps1-71·...BWOTripleMomentum[v108.0]·QSCCompositeHealth[v108.0])`
- `79-GATE SIGNAL FILTER` boot log stamp
- Scanner startup line: `79-gate filter | ...G8.5R3:BWO-TripleMomentum[v108.0] · G8.5S3:QSC-CompositeHealth[v108.0]`
- Launcher `79-gate filter` stamp
- Architecture changelog: v108.0 items appended (G8.5R3/S3, Kelly70/71, NN-v40, F211-F215, IRONS-WR5%-82.0, ScanParallel132, BlacklistLogFix)
- IRONS-tiers: `82.0/80.5/...`; NNv40-215feat; ScanParallel132 in architecture stamp

### Boot Verification
- Clean 21/21 boot confirmed
- Log shows: `Unity Engine v108.0`, `21/21 layers online`, `79-gate filter`, G8.5R3/S3 in gate list
