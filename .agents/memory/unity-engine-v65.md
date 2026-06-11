---
name: Unity Engine v65.0 upgrades
description: v65.0 changes — G8.5Y ATR-VolCompress 34th gate, Kelly Step 27 Sortino-Scale, G8.5S FLIP-zone double, G9 Sortino floor, NN ensemble coherence
---

## v65.0 Upgrade Summary (2026-06-11)

### Files changed
- `start_unity_engine.py` — all core changes
- `SignalMaestro/neural_signal_trainer.py` — ensemble coherence
- `nixpacks.toml`, `Dockerfile`, `requirements.txt` — version bumps

### Changes

**1. G8.5Y ATR Volatility Compression / Expansion Gate (34th gate)**
- Uses `_quant_layer_close_buf` (same source as G8.5Z); bar-to-bar abs-return as ATR proxy
- 5-bar smoothed ATR vs 60-bar rolling window (min 15 obs, min 20 bars in close buf)
- ATR ≤ 25th pct (compressed, pre-breakout): +2.0pts
- ATR ≥ 80th pct (expanded, noisy): −1.5pts
- 25–80th pct range: gate silent
- Wired to `_gate_stats`, `_gate_stats_recent`, `_GATE_DISPLAY_LABELS`, `_SOFT_GATE_KEYS`, `_record()`
- Non-fatal, soft-gate

**2. Kelly Step 27 — Sortino Downside Protection Scale**
- Inserted after Kelly Step 26 (dual-regime HMM-GEX upscale)
- Sortino < -2.5: Kelly × 0.85 (extreme downside vol de-risk)
- Sortino > 2.0 + ring WR > 35%: Kelly × 1.05 (confirmed downside-controlled edge)
- Reads `self._booster.sortino_ratio` and `self._booster._win_ring`
- Non-fatal, capped at `_kelly_ceil`

**3. G8.5S SpreadStress FLIP-Zone Double Penalty**
- In GEX FLIP ZONE (gex_btc_regime contains "FLIP"): penalties doubled
- FLIP + spread > 3× mean: −4pts (was −2pts)
- FLIP + spread > 2× mean: −2pts (was −1pt)
- Reads `signal_data.get("gex_btc_regime", "")`
- Normal (non-FLIP) penalties unchanged

**4. G9 Sortino Ultra-Crisis Floor**
- When Sortino < −4.0 AND ≥15 ring samples: G9 floor raised +1pt
- Cap: `SIGNAL_MIN_QUALITY_GATE + 4` (same as WR<15% tier)
- Inserted between compound-hostile gate and SOVEREIGN_RECOVERY block
- Non-fatal

**5. NN Ensemble Coherence Boost/Penalty (neural_signal_trainer.py)**
- Applied AFTER unified 3-way tree consensus blend, before `return base_prob`
- Collects all available model outputs: neural base_prob, HistGBT, ExtraTrees
- Range ≤ 0.03: high consensus → base_prob × 1.02 (cap 0.95)
- Range ≥ 0.15: high ambiguity → base_prob × 0.99 (floor 0.05)
- Non-fatal; ≥2 active models required to fire

### Banner / version strings
- UNITY_VERSION = "65.0"
- All "33-gate" → "34-gate" in live log strings (6 locations)
- All "33-GATE SIGNAL FILTER" → "34-GATE SIGNAL FILTER"
- All "Steps1-26" → "Steps1-27" in banner strings
- nixpacks.toml: header, verify string, hmmlearn string, intelligence tier, all updated to v65.0
- Dockerfile: header and build tag updated to v65.0
- requirements.txt: header and last-verified comment updated to v65.0

### AST verification
Both `start_unity_engine.py` and `SignalMaestro/neural_signal_trainer.py` pass `ast.parse()` after all edits.

**Why:**
- G8.5Y addresses the vol-regime blind spot: existing gates ignored whether market was coiling vs. chaotic
- Kelly Step 27 closes the gap between Sharpe-based CB (Step 24) and Sortino-specific downside protection
- G8.5S FLIP-zone double: FLIP regime is already the worst dealer-hedging environment; spread widening there is uniquely dangerous
- G9 Sortino floor: catches high-loss-magnitude regimes that Sharpe misses (both sides inflated)
- NN coherence: Krogh & Vedelsby 1995 — ensemble error bounded by member ambiguity; high agreement = genuine edge
