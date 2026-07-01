---
name: Unity Engine v168.0 upgrades
description: G8.5AS GFRD (151st gate) + G8.5AT GORD (152nd gate) + NN v74 385feat + ScanParallel 150→144; v167→168
---

## Gates

**G8.5AS GFRD — Funding Rate Direction Mismatch (151st gate)**
- Technique 2 (XML Delimiters): isolates raw funding level signal from funding trend signal (G8.5N2 tracks trend; GFRD tracks absolute crowding level)
- Source: `signal_data.get("funding_rate")` — raw fraction (0.00025 = 0.025%/8h) confirmed at F71/line 9608/13043
- Extreme: |funding_rate| ≥ 0.0005 (0.05%/8h) + direction aligned with crowd → -2.0pt
- Moderate: |funding_rate| ≥ 0.00025 (0.025%/8h) + direction aligned → -1.5pt
- LONG+high-positive-funding = crowded long = mean-reversion risk
- SHORT+high-negative-funding = crowded short = squeeze risk
- Thresholds: GFRD_MOD_THRESH=0.00025, GFRD_EXT_THRESH=0.00050
- Env: UNITY_GFRD=0 to disable; stores `_last_g85as_gfrd`

**G8.5AT GORD — OFI Direction Divergence (152nd gate)**
- Technique 6 (Workflow Isolation): OFI microstructure acts as Checker vs LLM/swarm Maker directional call
- Source: `signal_data.get("ofi_z")` — confirmed at F73/G8.5B/multiple gates
- Extreme: ofi_z ≤ -2.5 (LONG) or ≥ +2.5 (SHORT) → -2.0pt, ANY WR (structural flow reversal)
- Crisis: ofi_z ≤ -1.5 (LONG) or ≥ +1.5 (SHORT) + WR<30% → -1.5pt
- Thresholds: GORD_EXT_OFI=2.5, GORD_CRIS_OFI=1.5, GORD_WR_GATE=30.0
- Env: UNITY_GORD=0 to disable; stores `_last_g85at_gord`

## Kelly Steps

**Step 146 (GFRD):** extreme crowding → ×0.83 | moderate → ×0.87
**Step 147 (GORD):** extreme divergence → ×0.82 | crisis divergence → ×0.88

## NN v74 (385 features, F381-F385)

- F381: `as_gfrd_gate` — GFRD state {-2.0→0.0, -1.5→0.2, 0→0.5}
- F382: `funding_abs_norm` — |funding_rate| / 0.0005, capped [0,1]; 1.0 = extreme crowding (0.05%+/8h)
- F383: `at_gord_gate` — GORD state {-2.0→0.0, -1.5→0.2, 0→0.5}
- F384: `ofi_dir_divergence` — OFI opposition magnitude [0,1]; only nonzero when OFI opposes direction; capped at |ofi_z|/3
- F385: `flow_regime_quality` — composite microstructure quality [0,1]: OFI aligned (+1.0) + funding neutral <0.025% (+1.0) + GFRD neutral (+0.5) → normalized /2.5

## Railway Efficiency

**ScanParallel:** 150 → 144 (-4.0% CPU)
- Cumulative v163→v168: 192 → 144 (−25.0% Railway asyncio load)

## Architecture Counts

- Gates: 150 → 152
- Kelly steps: 145 → 147
- NN features: 380 → 385 (v73 → v74)
- SCAN_PARALLEL_LIMIT: 150 → 144
- UNITY_VERSION: 167.0 → 168.0

**Why:** GFRD exploits the structural crypto-futures funding crowding edge: when longs are paying 0.025%+/8h in funding, the position is already crowded and mean-reversion pressure builds. GORD is the microstructure Workflow Isolation — when OFI strongly contradicts the directional call, the real-time order flow (Checker) overrides the AI signal (Maker). Both gates use data already present in signal_data with zero extra API calls.
