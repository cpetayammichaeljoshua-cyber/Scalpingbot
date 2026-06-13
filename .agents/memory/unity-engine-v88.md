---
name: Unity Engine v88.0 upgrades
description: G8.5V2 OBPressure-Imbalance 56th gate, Kelly Step 48, NN v24 135feat, F131-F135, ScanParallel 94→96
---

## v88.0 Changes (2026-06-13)

### G8.5V2 — OBPressure-Imbalance (56th gate, ±2.0/+1.5pts)
- Reads `_ws_state[symbol]["depth_imbalance"]` (already-cached WS orderbook state — zero API calls)
- depth_imbalance > 0 → bids dominate (buy pressure); < 0 → asks dominate (sell pressure)
- |imb| < 0.06 → 0.0pts (neutral dead-zone)
- aligned + |imb| ≥ 0.15 → +2.0pts; aligned + |imb| < 0.15 → +1.5pts
- opposing + |imb| ≥ 0.15 → -2.0pts; weak opposing → 0.0pts
- Stores `_last_g85v2_obp` (+1/-1/0) for Kelly Step 48
- Uses `getattr(self, "_ws_state", None) or {}` pattern (v75.0 fix)
- Key: `gate_g85v2_obp` in `_SOFT_GATE_KEYS` and `_GATE_DISPLAY_LABELS`

### Kelly Step 48 — OBPressure Sizing
- `_last_g85v2_obp == +1` → Kelly ×1.04 (aligned institutional OB depth)
- `_last_g85v2_obp == -1` → Kelly ×0.85 (contra-institutional depth wall)
- 0 → no change

### NN v24 — INPUT_DIM 130→135, _TORCH_N_TOKENS 26→27
- F131: `ob_pressure_imbalance` — G8.5V2 gate output [-1,+1] (from `_last_g85v2_obp`)
- F132: `ob_bid_dominance` — mapped from depth_imbalance [0,1]; 0.5+imb×2.5
- F133: `ob_ask_dominance` — inverse of bid dominance; 0.5-imb×2.5
- F134: `spread_vol_norm` — spread_pct stability normalized [-1,+1]; 1.0-spread_pct×50
- F135: `trade_flow_intensity` — aggressor proxy from depth_imbalance [-1,+1]; imb×4.0
- Injected in G4 F131-F135 stamping block (after F126-F130 block)

### SCAN_PARALLEL_LIMIT 94→96 (+2.1% throughput)

### Files changed
- `start_unity_engine.py` — all gate init, implementation, labels, keys, Kelly48, F131-F135 inject, banners
- `SignalMaestro/neural_signal_trainer.py` — INPUT_DIM, _TORCH_N_TOKENS, F131-F135 build_features
- `requirements.txt`, `Dockerfile`, `nixpacks.toml` — v88.0 headers

**Why:** OB depth imbalance is already available in the WS state cache (zero API overhead). Strong institutional accumulation walls (+|imb|≥0.15 aligned) historically precede breakout continuation; opposing walls (contra-dir) signal resistance/reversal risk.
