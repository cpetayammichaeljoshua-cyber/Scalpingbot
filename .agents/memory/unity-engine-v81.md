---
name: Unity Engine v81.0 upgrades
description: G8.5N2 FundingMomentum-Persistence gate, Kelly Step 40, NN v18 105-feature, ScanParallel 84, all banners synced
---

## Gate G8.5N2 — FundingMomentum-Persistence (48th gate)
- Threshold: `|funding_rate_trend| > 0.0002` (two σ of typical 0.01%/8h cycle)
- Logic: `cross = funding_rate_trend × dir_sign`
  - `cross > 0` (trend OPPOSED to direction): `−2.0pts`, `_last_g85n2_fmp_signal = -1`
  - `cross < 0` (trend ALIGNED with direction): `+1.5pts`, `_last_g85n2_fmp_signal = +1`
  - `|trend| ≤ 0.0002`: neutral, 0pts
- Source: `signal_data["funding_rate_trend"]` (injected at F71 / G8.5A block — zero extra API calls)
- All 6 wiring points present: `_gate_stats`, `_gate_stats_recent` deque, `_last_g85n2_fmp_signal` sentinel, `_GATE_DISPLAY_LABELS`, `_SOFT_GATE_KEYS`, `_record()` call
- Inserted after G8.5L2 block, before `# ── Gate 8.5m — BTC Macro GEX Alignment`

## Kelly Step 40 — FundingMomentum-Persistence Sizing
- `_k40_sig = getattr(self, "_last_g85n2_fmp_signal", 0)`
- `-1` (opposed): Kelly × 0.86 (crowd funded against direction)
- `+1` (aligned): Kelly × 1.03 (crowd funded with direction)
- Non-fatal try/except; inserted after Kelly Step 39 block

## NN v18 — INPUT_DIM 100→105, _TORCH_N_TOKENS 20→21
- `_TORCH_N_TOKENS = 21`, `INPUT_DIM = 105` (21×5 tokens)
- F101: `funding_momentum_norm` — fr_trend × dir_sign × (−1) / 0.0004, clamped [-1,+1]
- F102: `vol_surge_persist` — (vol_ratio - 1.5) / 1.5, clamped [-1,+1]
- F103: `liq_cascade_intensity` — liq_intensity_norm × liq_net_side × dir_sign, clamped [-1,+1]
- F104: `ofi_fund_cross` — 50% ofi_z×dir_sign + 50% (-fr_trend×dir_sign/0.0004), clamped [-1,+1]
- F105: `meta_8gate_vote` — 8-gate aggregate (HMM+OFI+spread+G8.5J+G8.5L2+G8.5N2+liq+funding) / 8
- All 5 keys set via `signal_data.setdefault(...)` in the F101-F105 injection block (non-fatal try/except)
- `neural_signal_trainer.py` build_features: F101-F105 appended after F100 block; shape guard validates 105

## SCAN_PARALLEL_LIMIT 82→84

## Infrastructure sync
- Dockerfile: header v80.0→v81.0, build tag 80.0→81.0, verify print v80.0→v81.0, LABEL version/description updated
- nixpacks.toml: header v80.0→v81.0, verify string v80.0→v81.0, sklearn line "100-feature NN v17"→"105-feature NN v18", SCAN_PARALLEL 82→84, gate count 47→48
- requirements.txt: header v80.0→v81.0, last-verified line updated

## Syntax
Both `start_unity_engine.py` and `SignalMaestro/neural_signal_trainer.py` pass `ast.parse()` clean (verified 2026-06-12).

**Why:** Funding rate trend is already computed (F71 / G8.5A) so G8.5N2 is zero-cost. Crowding-risk signal: when longs pay more than usual (positive funding) AND signal is BUY, the crowd is against the expected move — a known drawdown precursor in perp markets.
