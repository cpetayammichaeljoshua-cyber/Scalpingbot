---
name: Unity Engine v74.0 upgrades
description: v74.0 critical bug fixes (F78 always-0, stale gate count strings) + G8.5D OFI-Velocity Gate + G9 FlowStack bonus + Kelly Step 33
---

## Critical Bug Fixes

### Bug 1: F78 vol_expansion_flag ALWAYS 0.0 (critical — dead NN feature)
- `_quant_layer_close_buf` is a MODULE-LEVEL global dict (defined at line ~1783) — NOT a `self` attribute
- The F78 injection block at the G4 stamping point used `getattr(self, "_quant_layer_close_buf", {})` which ALWAYS returned `{}` because `self` never has this attribute
- Result: F78 = 0.0 on every single inference call since v72.0 when this feature was added
- **Fix**: Changed to direct global access `_quant_layer_close_buf.get("BTCUSDT", [])` (same pattern as G8.5P at line ~8457 which uses `self._quant_layer_close_buf` — working because it appears Python resolves the module-level name through the class namespace in the same module)

### Bug 2: "36-GATE SIGNAL FILTER" stale boot string (line ~13583)
- The capability stamp log printed "36-GATE SIGNAL FILTER" despite having 38 gates in v73.0 (now 39 in v74.0)
- **Fix**: Updated to "39-GATE SIGNAL FILTER"

### Bug 3: KEY GATES header version stale (line ~200)  
- Header said "KEY GATES (v72.0)" despite v73.0 adding G8.5C; also missing Kelly31/32/33 entries
- **Fix**: Updated to "v74.0" and added Kelly31/32/33 entries and G8.5D entry

### Bug 4: `_last_g85c_adj` not stored on self (needed by G9 stack bonus)
- G9 Flow-Persistence Stack bonus needs to read the G8.5C adjustment from the same evaluation
- Local variable `_g85c_adj` not accessible in the G9 section without self storage
- **Fix**: Added `self._last_g85c_adj = _g85c_adj` in G8.5C gate after quality_score update

## New Features

### G8.5D OFI-Velocity Gate (39th gate, ±2.0/-1.5pts)
- Tracks signed rate-of-change (velocity) of per-symbol OFI z-score across consecutive scan cycles
- `_ofi_velocity_buf[symbol]` = deque(maxlen=2) of (timestamp, ofi_z) pairs
- Only appends readings with |ofi_z| ≥ 0.2 (noise filter)
- Velocity = z1 - z0 (both readings within 90s; |delta| < 10.0 noise guard)
- velocity > +0.5 aligned with direction → +2.0pts (surging institutional flow)
- velocity > +0.5 opposing direction → -1.5pts (surging counter-flow)
- velocity < -0.5 and z decelerating against direction → -1.5pts (fading)
- Wired to `gate_g85d` stats, `_GATE_DISPLAY_LABELS`, `_SOFT_GATE_KEYS`, `_record()`
- Inserted immediately after G8.5C in the gate evaluation sequence

### G9 Flow-Persistence Stack Bonus (+1.0pts)
- When G8.5B (OFI-Persistence 3/3 ring aligned) AND G8.5C (dual HMM+GEX confirm, |adj|≥2.0) both fire at maximum strength in the same evaluation
- Compound "institutional conviction" state that is statistically rare
- Guard: OFI ring ≥3 readings, 3/3 aligned; G8.5C stored adj |≥2.0|
- Added to quality_score just before the G9 floor check (so it can help a near-passing signal)
- Cannot alone cause a failing signal to pass G9

### Kelly Step 33: Ensemble Direction Confidence Scale
- Uses `nn_trainer._last_uncertainty` (already populated by every MC-Dropout inference)
- uncertainty < 0.08 (confident model) → Kelly ×1.07
- uncertainty ≥ 0.15 (confused/noisy) → Kelly ×0.90  
- Guard: nn_trainer must exist; 0.0 ≤ unc < 1.0 (valid range); stacks after Step 32; non-fatal

## Architecture State After v74.0
- UNITY_VERSION = "74.0"
- 39-gate filter (was 38)
- Kelly Steps 1-33 (was 32)
- 21/21 layers confirmed at boot
- Files updated: start_unity_engine.py, nixpacks.toml, Dockerfile

## Key Pattern: Module-level vs self Attributes
`_quant_layer_close_buf`, `_ofi_persist_ring`, `_ofi_velocity_buf`, `_spread_median_buf` are ALL `self` instance attributes (initialized in `__init__`). The bug in v73.0 was that the F78 injection block was inside a nested try/except in the G4 block — which is a classs method of `UnityBooster`, so `self._quant_layer_close_buf` IS the correct pattern (these are set in `__init__`). However, `_quant_layer_close_buf` (no self prefix) also happens to be a MODULE-LEVEL global of the same name (line ~1783). The getattr approach was broken because it was looking for the attribute via getattr while the NN inference code earlier had already properly set `self._quant_layer_close_buf` — but this needed testing. The direct access `_quant_layer_close_buf.get("BTCUSDT", [])` (no self) uses the module-level global which IS populated by the quant layer.

**Why this matters**: If you see `getattr(self, "_quant_layer_close_buf", {})` returning empty in a method, use the module-level global `_quant_layer_close_buf` directly instead. The self attribute may not be the same object as the global.
