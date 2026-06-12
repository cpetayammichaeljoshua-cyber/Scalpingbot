---
name: Unity Engine v79.0 upgrades
description: G8.5K gate (46th), Kelly Step 38, NN v16 (INPUT_DIM 95), F91-F95 features, ScanParallel80, build_features fix
---

## What changed in v79.0

### G8.5K — Spread-Regime Liquidity gate (46th gate, ±2.0/+1.5pts)
- `gate_g85k_spread` — per-symbol `_g85k_spread_ring` deque(maxlen=30)
- Reads `spread_ratio_norm` (F89) — the existing spread-normalised feature
- Fires when spread >=75th pct AND >1.15 → −2.0pts (illiquid regime)
- Fires when spread <=25th pct AND <0.85 → +1.5pts (liquid regime)
- Requires >=10 ring samples before activating
- Added to `_gate_stats`, `_gate_stats_recent`, `_GATE_DISPLAY_LABELS`, `_SOFT_GATE_KEYS`, `_record()` calls
- Gate placed after G8.5J block in the quality-score pipeline

### Kelly Step 38 — SpreadLiquidity Sizing
- Reads `self._last_g85k_liq_signal` from booster via `getattr`
- illiquid signal → ×0.86; liquid signal → ×1.03; neutral → ×1.00
- Placed after Kelly Step 37 block

### NN v16 — INPUT_DIM 90→95, F91-F95 cross-signal coherence features
- `neural_signal_trainer.py`: `INPUT_DIM=95`, `_TORCH_N_TOKENS=19`, comment "v16 (v79.0)"
- F91: `ofi_hmm_cross` — OFI z-score × HMM regime alignment
- F92: `vwap_micro_align` — VWAP extension × microtrend slope
- F93: `funding_ofi_cross` — funding rate × OFI flow cross-product
- F94: `regime_3gate_vote` — normalized vote from G8.5C/G8.5R/G8.5U
- F95: `gex_net_norm` — net GEX normalized to [-1, +1]
- All 5 features injected at G4 stamping block via `setdefault`
- All 5 features added to `build_features()` in neural_signal_trainer.py

### Critical fix: build_features F91-F95 missing → NN training shape error
- On restart after INPUT_DIM 90→95, existing labeled trades (1000) triggered:
  `Training error: Feature shape 90 ≠ 95`
- Fix: added F91-F95 to `build_features()` in neural_signal_trainer.py
- Old trades without these fields default to 0.0 via `trade.get("field", 0.0)`
- This is the same pattern as F86-F90 in v77.0 and F76-F80 in v73.0

### Other changes
- `SCAN_PARALLEL_LIMIT` = 78→80
- All display strings updated: docstring, KEY GATES (v79.0), L5 description (95-feat NN v16), 46-gate filter, Steps1-38, ScanParallel80, wired_all banner, main() ARCHITECTURE logger, 46-GATE SIGNAL FILTER banner, online banner (2 locations), capabilities stamp, Kelly steps comment block

## Pattern: every INPUT_DIM bump requires build_features update
**Why:** `build_features` validates `arr.shape[0] == INPUT_DIM` at line ~932. If new features are not appended in `build_features`, NN training fails with shape mismatch on ALL existing labeled trades. Always add new feature blocks to `build_features()` with `trade.get("new_field", 0.0)` defaults before bumping INPUT_DIM.

## Display string locations (all updated in v79.0)
1. Docstring capabilities line 414 (gate list) and line 420 (Kelly steps)
2. KEY GATES header line ~403
3. `wired_all` banner lines ~14786-14792 (46-gate, Kelly Steps1-38, G8.5K)
4. `print_startup_banner` line ~14828 (46-GATE SIGNAL FILTER)
5. `main()` ARCHITECTURE logger line ~14808
6. Online-scanner banner line ~18336 (46-gate, G8.5K)
7. Launcher capabilities stamp line ~19263 (46-gate, G8.5K)
