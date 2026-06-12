---
name: Unity Engine v75.0 upgrades
description: v75.0 — two critical silent dead-gate fixes + G8.5E CrossCoherence 40th gate + Kelly Step 34; engine boots cleanly 40-gate/Steps1-34
---

## Critical Bug Fixes (silent dead gates since prior versions)

### G8.5P BTC-CrossPair (dead since v60.0)
- `self._quant_layer_close_buf` → `_quant_layer_close_buf` (module-level global)
- Gate was silently returning `{}` on every eval due to AttributeError caught by bare `except`
- Pattern: ANY gate reading `_quant_layer_close_buf` MUST use the bare name (module global), never `self.` or `getattr(self, ...)`

### G8.5Y ATR-VolCompress (dead since v65.0)
- `getattr(self, "_quant_layer_close_buf", {})` → `_quant_layer_close_buf` (module-level global)
- Same silent-failure pattern as G8.5P

**Why:** `_quant_layer_close_buf` is declared at module level (~line 1817), not as an instance attribute. Using `self.` raises AttributeError which is swallowed by the bare `except` in each gate block. Gates G8.5Z, G8.5T, G8.5w all correctly use the bare module-level name — match that pattern.

## New: G8.5E Quant Cross-Signal Coherence (40th gate)

- 3-vote meta-gate: OFI z-score direction + HMM regime direction + BTC GEX net direction
- Requires ≥2 of 3 data sources live to fire; uses `self._last_g85e_votes` to pass vote count to Kelly Step 34
- Scoring: 3/3→+2.0pts, 2/3→+0.8pts, 1/3→0pts, 0/3→−1.5pts
- Wired to `_gate_stats["gate_g85e"]`, `_GATE_DISPLAY_LABELS`, `_SOFT_GATE_KEYS`, `_record()`
- `self._last_g85e_votes` initialized as `-1` in `__init__`; set to vote count during gate eval; −1 means gate did not fire

## New: Kelly Step 34 Cross-Signal Coherence Sizing

- Reads `self._last_g85e_votes` (set by G8.5E in apply())
- 3/3 votes → Kelly ×1.06 (ultra-conviction institutional coherence)
- 0/3 votes → Kelly ×0.87 (three-way institutional headwind)
- 1/3 or 2/3 → no change (neutral)
- Guard: `_last_g85e_votes >= 0` (was gate evaluated this cycle)

## gate_g85dv Explicit Init

- `gate_g85dv` (G8.5X DGRP-Velocity) was relying on `_record()` setdefault; now explicitly initialized in `__init__` alongside all other gates for clean boot analytics

## Architecture Stamp

- 40-gate filter, Kelly Steps1-34
- File: 18457 lines
- All stamps updated: KEY GATES docstring, wire_all() banner, startup banner, console HUD (line ~17402), Telegram capability stamp (line ~18329)
- nixpacks.toml: header + verify string → v75.0, 40-gate
- Dockerfile: header → v75.0
- Boot confirmed: v75.0 Launcher, 21/21 layers online, 40-gate filter in console
