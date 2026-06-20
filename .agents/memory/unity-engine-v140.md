---
name: Unity Engine v140.0 upgrades
description: G8.5S5 LSQ + G8.5T5 MFR 129th/130th gates, Kelly124/125, NN v66 345feat, GODMODE tighter risk thresholds
---

## v140.0 Upgrade Summary

### New Gates
- **G8.5S5 LSQ** — Liquidity-Sharpe-Quality TripleConvergence (129th gate)
  - EMERGENCY -3.5pts when all 3 crisis; +2.0/+1.0/-1.0/-2.0 tiers
  - Uses: spread_liq_signal (SpreadLiq percentile), sharpe_velocity_norm, quality_score_ring
  - Sentinel: `_last_g85s5_lsq`; stats key: `gate_g85s5_lsq`
- **G8.5T5 MFR** — MomentumFlow-Regime TripleResonance (130th gate)
  - EMERGENCY -3.5pts when all 3 crisis; +2.0/+1.0/-1.0/-2.0 tiers
  - Uses: direction-aware OFI z-score (action key), _last_g85s5_lsq, vol_ratio
  - Sentinel: `_last_g85t5_mfr`; stats key: `gate_g85t5_mfr`

### Kelly Steps
- **Step 124 LSQ** — ×0.75 emergency / ×0.85 crisis / ×0.95 caution / ×1.02 healthy / ×1.04 strong
- **Step 125 MFR** — same multiplier profile as Step 124
- Both use `self._kelly_ceil if hasattr(self, "_kelly_ceil") else self.last_kelly_fraction * 2.0` (safe fallback)

### NN v66
- INPUT_DIM: 340→345 features, F341-F345
  - F341: s5_lsq_gate, F342: s5_spl_signal, F343: s5_svq_signal, F344: t5_mfr_gate, F345: t5_ofi_vel_signal
- Layer 5 banner: "345-feature NN v66 (MLP+Transformer 69×5 tokens)"

### GODMODE system_prompt improvements (godmod3_strategy.py)
- MaxDD hard NEUTRAL lowered: 50%→46% (survival mode trigger earlier)
- OFI opposition threshold tightened: >3.5→>2.0 z-score
- VPIN toxic threshold lowered: 0.65→0.60; added 0.50-0.60 intermediate (-8pp)
- Volume exhaustion trigger lowered: >3.0→>2.5 vol_ratio
- P_win floor lowered: ≥40%→≥38% (crisis calibration for WR≈29%)
- WR crisis cap: WR<29%→hard cap confidence at 63
- Spread illiquid threshold: >0.1%→>0.08%
- Confidence cap: 95→90; misalignment penalty: -20pp→-25pp
- Candle bonus: +8pp→+6pp (capped 88 not 95)
- IRONS floor cap: 72→70
- Added condition (i): VPIN>0.60 AND spread>0.08% = toxic ambush NEUTRAL
- Architecture banner tags: GODMODE-VPINToxic0.60, GODMODE-OFIOppose2.0, GODMODE-WR29Crisis, GODMODE-MaxDD46NEUTRAL

### Version counters
- UNITY_VERSION: "139.0"→"140.0"
- SCAN_PARALLEL_LIMIT: 184→186 (ScanParallel186)
- All banners: 128-gate→130-gate filter, Kelly Steps1-123→Steps1-125, NN v65→v66

### Boot verification
- Clean boot confirmed: "Unity Engine v140.0 Launcher", "130-gate filter", "345-feature NN v66", "ScanParallel(186)", "Kelly Steps 1-125"
- Zero errors or Tracebacks in boot log
- No remaining 128-gate stale strings in any banner
