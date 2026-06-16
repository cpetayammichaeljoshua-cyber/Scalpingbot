---
name: Unity Engine v118.0 upgrades
description: G8.5F4 TimesFM-PatchMomentum + G8.5G4 SharpeVelocity-TimesFM Composite gates; Kelly84-85; NN v49 260feat; IRONS WR<0.1%=90.5/WR<0.2%=90.0; EV43bps; 93-gate; ScanParallel150
---

## v118.0 Changes

**Gate G8.5F4 — TimesFM-PatchMomentum (92nd gate, ±2.0/-1.5/+1.5pts):**
- 3-scale multi-resolution patch approach: 16/32/64-bar windows, 4 patches each
- Uses `_quant_layer_close_buf` (global, not self.*); reads "action" key for direction_int
- ATR-normalized slope threshold=0.08; votes across scales; +2.0 if ≥2 scales agree dir, +1.5 if all 3 agree but ATR-weak, -1.5 if 2 oppose, -2.0 if all 3 oppose
- Kelly Step 84: ×1.04 (3-scale full agree) / ×1.02 (2-scale agree) / ×0.89 (2-scale oppose) / ×0.84 (3-scale full oppose)

**Gate G8.5G4 — SharpeVelocity-TimesFM Composite (93rd gate, ±2.0/-1.5/+1.5pts):**
- Uses `_pnl_ring` (≥10 entries required); recent-5 vs prior-5 Sharpe delta
- Sums D4+E4+F4 votes as composite; +2.0 if Sharpe-improving+votes≥2, +1.5 if flat+votes≥2, -1.5 if Sharpe-declining, -2.0 if Sharpe-declining+votes≤-2
- Kelly Step 85: ×1.03 (aligned) / ×0.87 (opposed)

**NN v49:**
- INPUT_DIM 255→260; _TORCH_N_TOKENS 51→52; F256-F260 in neural_signal_trainer.py
- F256: timesfm_pm_dir, F257: timesfm_pm_strength, F258: timesfm_pm_votes, F259: sharpe_velocity_norm, F260: svtfc_composite

**Other constants:**
- IRONS WR<0.2%→90.0, WR<0.1%→90.5 (2 new ultra-extreme tiers)
- EV_MIN_THRESHOLD 40→43bps
- SCAN_PARALLEL_LIMIT 148→150

**Banner strings updated (all 5 locations):**
- "91-gate" → "93-gate filter" in KEY GATES, f-string wired, capability stamp, Signal gates line, G0:EV filter string
- "Kelly(Steps1-83" → "Kelly(Steps1-85" in all relevant banner lines
- "NN-v48-255feat" → "NN-v49-260feat" in architecture stamps
- "ScanParallel148" → "ScanParallel150"
- IRONS tiers prefix updated: "90.5/90.0/88.5/..."

**Build files:**
- Dockerfile: version label 117.0→118.0, verify print updated
- nixpacks.toml: verify prints updated (no LABEL block in nixpacks — only Dockerfile has LABEL)
- requirements.txt: header comment updated

**Boot result:** 21/21 clean, 93-gate filter confirmed in startup banner [v118.0]
