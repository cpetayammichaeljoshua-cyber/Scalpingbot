---
name: Unity Engine v73.0 upgrades
description: v73.0 critical bug fixes and new features — ofi_z injection, F76-F80 feature injection, G8.5C gate, Kelly Step 32, CPCV floor tightening
---

## Critical Bug Fixes

### Bug 1: G8.5B `ofi_z` always 0.0 (gate was completely dead)
- G8.5B reads `signal_data.get("ofi_z")` at line ~8848 to record directional OFI readings into `_ofi_persist_ring`
- This key was NEVER set in `signal_data` before v73.0 → gate always got 0.0 → |0.0| < 0.3 threshold → ring was never populated → gate was a complete no-op
- **Fix**: Inject `signal_data.setdefault("ofi_z", _v73_ofi_z)` at the G4 stamping block (before G8.5B in the gate eval flow), computed from `self._timing_state.ofi_zscore(symbol)`

### Bug 2: F76-F80 NN features all 0.0 defaults
- v72.0 added INPUT_DIM 75→80 with 5 new features but never injected the values into `signal_data` before `predict_from_dict()` call
- Features affected: `ofi_persistence_score`, `regime_coherence_score`, `vol_expansion_flag`, `hmm_expansion_prob`, `spread_regime_flag`
- **Fix**: Added F76-F80 injection block at the same G4 stamping block (lines ~6860-6940), computing each feature from live engine state

### Bug 3: CPCV threshold push too aggressive  
- At CPCV avg=47.5% (near chance), gap=18.8% was triggering threshold push to 0.560
- Old floor `_cpcv_avg > 0.47` allowed push despite the CPCV signal being near-chance level
- **Fix** (neural_signal_trainer.py line 2527): floor raised `0.47 → 0.50` (hard chance boundary); push multiplier reduced `0.30 → 0.25`

## New Features

### G8.5C Regime-Coherence Gate (38th gate, ±2.0pts)
- Dual HMM + BTC GEX net direction confirmation
- Both EXPANSION+GEX>$200M+BUY or CONTRACTION+GEX<-$200M+SELL → +2.0pts
- Both opposed → -2.0pts; single source aligned → ±1.0pts weak
- HMM threshold: P≥0.60 for EXPANSION, P≥0.55 for CONTRACTION
- GEX guard: |net_gex| > $200M and snapshot age < 120s
- Soft-gate (cannot block); wired to `gate_g85c` stats, `_GATE_DISPLAY_LABELS`, `_SOFT_GATE_KEYS`, `_record()`

### Kelly Step 32: OFI-Persist Sizing Scale
- Reuses `_ofi_persist_ring[symbol]` populated by G8.5B gate
- 3/3 readings aligned with direction → Kelly ×1.08
- 0/3 readings aligned → Kelly ×0.88  
- Guard: ring must have ≥3 readings; stacks AFTER Step 31; non-fatal

### `_spread_median_buf` tracker
- Per-symbol `deque(maxlen=20)` rolling spread median
- Populated at G4 stamping block for F80 spread_regime_flag
- `spread_pct > 2× median` → F80 = 1.0 (elevated spread regime)

## Architecture State After v73.0
- UNITY_VERSION = "73.0"
- 38-gate filter (was 37)
- Kelly Steps 1-32 (was 31)
- 21/21 layers confirmed at boot
- Files updated: start_unity_engine.py, SignalMaestro/neural_signal_trainer.py, nixpacks.toml, Dockerfile

## Key Pattern: Feature Injection at G4 Stamping Block
The G4 NN inference block (around the GEX stamp code at `signal_data.setdefault("gex_flip_count", ...)`) is the canonical place to inject live features into signal_data that downstream gates need. Gate evaluation order: G0→G4→G8.5*→G9. Any feature injected at G4 is available to all G8.5* gates that come after.

**Why**: `predict_from_dict()` reads from the signal_data dict. Gates like G8.5B also read from it. The injection must happen before the NN call AND before those gates run. The G4 block is the only place that executes in this order with access to `self` (engine instance) and `signal_data`.
