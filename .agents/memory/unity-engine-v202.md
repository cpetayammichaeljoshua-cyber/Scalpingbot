---
name: Unity Engine v202.0 — F281-F320 trainer feature gap fix
description: Critical bug: 40 features missing from neural_signal_trainer.py build_features(); F321-F420 at wrong array positions; F297 (top loss-predictor) always zero during training.
---

## The Bug (existed since v136.0 / ~6 months)
`neural_signal_trainer.py` `build_features()` jumped from F280 directly to F321,
leaving a 40-feature gap (F281–F320). The immediate effects:

1. **F321–F420 were at wrong array positions [280–379]** instead of correct [320–419].
   Every gate-sentinel feature fed to the wrong neuron since v136.0.
2. **F297 (`sharpe_ev_velocity`) always 0.5 in training** — the #1 ExtraTrees loss-predictor
   (importance=2.00) and the core discriminator for the v201.0 GSEV gate was invisible.
3. **Trailing positions [380–419] were always zeros** (padding), wasted capacity.

## The Fix (v202.0)
Inserted 8 five-feature blocks between F280 and F321 in `neural_signal_trainer.py`:
- F281–F285 (v124.0/v54): fg_norm, tuc_sentinel, cap_reversal, quality_velocity, triple_crisis_n
- F286–F290 (v125.0/v55): ev_recovery_rate, pnl_ring_mean, wr_10trade_recent, ev_ring_std_norm, filter_coherence
- F291–F295 (v126.0/v56): quality_slope_norm, ofi_vol_sync, ev_ring_percentile, pnl_stability, wr_momentum_tier
- F296–F300 (v127.0/v57): hmm_regime_norm, **sharpe_ev_velocity [F297★]**, arc_consensus_norm, ofi_persistence_norm, svc_confluence_norm
- F301–F305 (v132.0/v58): d5_ekc_gate, d5_evpv_svc_cross, d5_tsqc_norm, e5_msc_gate, e5_sentinel_vote
- F306–F310 (v133.0/v59): f5_irq_gate, f5_rfc_gate, f5_irons_wr_delta, f5_hmm_ofi_cross, f5_vol_ratio_norm
- F311–F315 (v134.0/v60): h5_wrs_gate, h5_ovm_gate, h5_wr_recent_delta, h5_vpin_percentile, h5_vol_momentum
- F316–F320 (v135.0/v61): j5_emc_gate, j5_ev_ring_mean, j5_maxdd_severity, k5_qfc_gate, k5_irons_floor_pct

## Verified
- `build_features({})` returns shape (420,) with no padding (was 380 real + 40 zeros)
- F297 at index 296 reads correct value when `sharpe_ev_velocity` key present
- F321 (`l5_mev_gate`) now correctly at index 320

## Side Effects
- `SignalMaestro/nn_weights.json` and `torch_transformer_weights.pt` deleted to force clean retrain
- INPUT_DIM stays 420 — architecture detection won't auto-clear, so explicit deletion was necessary
- First retrain cycle after deploy produces correctly-aligned model

**Why:** Feature positions shifted for F321–F420 (40 slots), so saved weights had fundamentally wrong feature→neuron mappings. Manual weight clearing mandatory.

**How to apply:** Any time INPUT_DIM stays constant but build_features() changes internal ordering, saved weights MUST be manually deleted.
