---
name: Unity Engine v76.0 upgrades
description: G8.5F VWAP-Extension + G8.5G CUSUM-Breakout gates; Kelly Step 35; NN v14 INPUT_DIM 80→85; all stale 40-gate strings patched
---

## v76.0 Changes

### Gates Added
- **G8.5F VWAP-Extension** (41st gate, `gate_g85f`): Uses `avwap_dist_bps` from signal_data (injected in F81-F85 block by reading `_timing_state.avwap_distance_bps()`). Signed distance: positive = price above VWAP, negative = below. BUY: above VWAP = in-direction; SELL: below VWAP = in-direction.
  - >80bps against dir → -2.0pts; 40-80bps against → -1.0pts
  - >80bps in dir → +1.5pts; 40-80bps in dir → +0.8pts
  - |dist| < 40bps or abs < 1.0 (cold-start) → silent
  - Stores `_last_g85f_avwap_dist` for Kelly Step 35.
- **G8.5G CUSUM-Breakout** (42nd gate, `gate_g85g`): Uses `_timing_state.cusum_event_active()` + `ofi_zscore()` to detect live statistical breakouts. OFI |z| < 0.3 → silent (direction ambiguous).
  - CUSUM active + aligned with OFI → +1.5pts
  - CUSUM active + opposed to OFI → -1.5pts
  - Stores `_last_g85g_cusum_active` for Kelly Step 35.

### Kelly Step 35 — AVWAP-Extension Sizing
Uses `_last_g85f_avwap_dist` + `_last_g85g_cusum_active`. Guard: `abs(avwap) >= 1.0` (timing state warm).
- |avwap| > 150bps against direction → Kelly ×0.82
- |avwap| > 150bps in direction AND CUSUM active → Kelly ×1.04

### NN v14 — INPUT_DIM 80→85
Files: `SignalMaestro/neural_signal_trainer.py`
- `_TORCH_N_TOKENS = 17` (was 16); `_TORCH_TOKEN_DIM = 5` (unchanged)
- `INPUT_DIM = 85` (was 80)
- F81: `avwap_dist_norm` = avwap_dist_bps / 100 clipped ±1
- F82: `cusum_flag` = 1.0 if cusum active, 0.0 otherwise (reads `cusum_flag` or `cusum_active` key, handles bool/float)
- F83: `depth_slip_norm` = depth_slip_rt / 0.003 clipped [0,1]; fallback computes from raw `depth_slip_rt`
- F84: `mark_div_norm` = mark_divergence_bps / 50 clipped ±1; fallback from raw `mark_divergence_bps`
- F85: `ob_imbalance_norm` = (ob_imbalance - 0.5) × 2 clipped ±1; fallback from raw `ob_imbalance`
- Weight reset on mismatch 80→85 → retrain in 2min from boot

### F81-F85 Injection (G4 stamping block)
Located after F76-F80 block (`signal_data.setdefault("spread_regime_flag", ...)`). Same pattern as v73 F76-F80 injection. F81 reads `avwap_dist_bps` from signal_data first, falls back to `_timing_state.avwap_distance_bps()`. F82 reads `cusum_active` from signal_data, falls back to `_timing_state.cusum_event_active()`. F83-F85 read from `_ws_state_ref` per-symbol dict.

**Critical**: F81-F85 block is INSIDE the same outer try/except as F76-F80. The `except Exception: pass` at the end covers BOTH blocks as non-fatal.

### Gate Wiring Checklist (all 4 required locations)
- `_gate_stats[gate_g85f/g]` + `_gate_stats_recent` — initialized in `__init__` after gate_g85e init
- `_GATE_DISPLAY_LABELS["gate_g85f/g"]` — entries added after gate_g85e
- `_SOFT_GATE_KEYS` frozenset — gate_g85f + gate_g85g added after gate_g85e
- `self._record("gate_g85f/g", fired)` — called at end of each gate's try/except block

### Stale String Fixes
All "40-gate" → "42-gate" patched (6+ display locations):
- docstring header, KEY GATES, wire_all() log, startup banner (ARCHITECTURE, 🔒 SIGNAL FILTER), ALL SYSTEMS ONLINE "Signal gates", headless scanner capability stamp
- Kelly Steps 1-34 → Steps 1-35 in all banner strings
- NN "80-feat NN v13 MLP (60%)+Transformer 4-head 16×5" → "85-feat NN v14 MLP (60%)+Transformer 4-head 17×5"
- nixpacks.toml: v75.0→v76.0, "80-feature NN v13"→"85-feature NN v14", "40-gate"→"42-gate"

**Why:** avwap_dist_bps and cusum_active are already computed every cycle by the timing layer (L9) — zero new API calls needed. G8.5F uses mean-reversion theory (AVWAP as magnetic anchor) and G8.5G uses de Prado's CUSUM for statistical breakout confirmation — both complementary to existing OFI/HMM/GEX gate stack.
