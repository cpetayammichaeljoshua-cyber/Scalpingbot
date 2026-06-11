---
name: Unity Engine v64.0 upgrades
description: v64.0 changes — G8.5Z gate, Kelly Step 26, 3-way tree consensus, _SOFT_GATE_KEYS bug fix, stale "29-GATE" string fix
---

## Key changes in v64.0

### G8.5Z — Return-Autocorrelation Persistence Gate (33rd gate, ±2.0pts)
- Inserted after G8.5R block in `_quant_layer_filter()` in start_unity_engine.py
- Uses lag-1 AC of bar-to-bar returns from `_quant_layer_close_buf[symbol]` (≥20 bars)
- AC > +0.15 (trending): aligned trade +2.0pts, counter-trend -1.5pts
- AC < -0.15 (mean-rev): fade trade +1.5pts, trend-chase -1.0pt
- |AC| ≤ 0.15: random walk, gate silent (0pts)
- Wired to: gate_stats init, _GATE_DISPLAY_LABELS, _SOFT_GATE_KEYS, _record()

### Kelly Step 26 — HMM-GEX Dual Regime Conviction Upscale
- Inserted in `_update_kelly()` after Step 25 exception block, before `self.last_kelly_fraction =`
- EXPANSION P≥0.75 + GEX net > +$1B + BUY signal → Kelly ×1.10 (cap: _kelly_ceil)
- CONTRACTION P≥0.65 + GEX net < -$1B + SELL signal → Kelly ×1.10 (cap: _kelly_ceil)
- Reads: self._hmm_regime_ref.get_regime()[0/1], self._gex_snaps_ref["BTCUSDT"], self._last_direction
- Guards: GEX conf ≥ 35, "FLIP" not in regime, snapshot age < 120s, kelly > 0.001; non-fatal

### Bug fix: _SOFT_GATE_KEYS missing entries (gate_g85p/r/s/z)
- Before v64.0: _SOFT_GATE_KEYS only had gate_g85w/x/t/u, vibe, markov
- gate_g85p/r/s are all quality adjusters (soft-gates) but were not in the set
  → showed as false #1/#2 bottlenecks in gate_bottleneck_str() HUD
- Fixed: added gate_g85p, gate_g85r, gate_g85s, gate_g85z to _SOFT_GATE_KEYS

### Bug fix: "29-GATE SIGNAL FILTER" stale string
- Was at line ~12332 as `🔒 29-GATE SIGNAL FILTER` (stale since v63.0 had 32 gates)
- Fixed to `🔒 33-GATE SIGNAL FILTER`

### Neural trainer: Unified 3-way tree consensus (predict_signal)
- Replaced sequential HistGBT→then→ExtraTrees blending with a unified block
- When both fitted: tree_consensus = accuracy-weighted avg(GBT, ET); total tree weight capped at 40%
- Prevents implicit double-counting of tree weight (sequential 30%+15% could compound to >40%)
- Fallback: if only one tree fitted, individual blend applies unchanged

### File headers updated
- UNITY_VERSION: "63.0" → "64.0"
- Module docstring: "v57.0" → "v64.0", "30-gate" → "33-gate"
- nixpacks.toml, Dockerfile, requirements.txt all updated to v64.0
- All banner strings: "32-gate" → "33-gate" (6 locations); Kelly "Steps1-25" → "Steps1-26"

**Why:** Gate count accuracy critical — false bottleneck display hides real hard-gate failures (G0.5/G4); AC-based regime detection adds orthogonal signal quality discrimination.
