---
name: Unity Engine v95.0 upgrades
description: v95.0 additions — G8.5C3 VolumeFlow-OFI-EV Triple-Convergence Gate (63rd gate), Kelly Step 55, NN v31 170feat, SCAN_PARALLEL 108→110
---

## Changes
- **G8.5C3 VOE-TripleConv** (63rd gate, ±2.0/±1.5pts): zero-API soft-gate cross-validating three independently-sourced signals:
  - Source 1: VolPressure-Regime gate output (_last_g85l2_vpr: +1/-1/0) — G8.5L2 fires when vol_ratio≥1.5× cross-confirmed with OFI direction
  - Source 2: OFI-Persistence gate output (_last_g85b_ofi: +1/-1/0) — G8.5B 3-cycle OFI ring alignment
  - Source 3: EV quality tier — EV≥0.8R → +1, EV<0.4R → -1, else 0
  - Scoring: triple-align → +2.0pts, dual-align → +1.5pts, triple-oppose → -2.0pts, dual-oppose → -1.5pts (≥2 active sources)
- **Kelly Step 55**: VOETripleConv sizing (aligned → ×1.03, hostile → ×0.87).
- **NN v31**: INPUT_DIM 165→170; F166-F170: ofi_vpr_sync_norm, ofi_ev_sync_norm, vpr_ev_sync_norm, triple_voe_quality, c3_gate_output.
- **SCAN_PARALLEL_LIMIT**: 108→110 (+1.9%).
- **_SOFT_GATE_KEYS**: gate_g85c3_voe added.
- **_GATE_DISPLAY_LABELS**: "gate_g85c3_voe" → "G8.5C3" added.

## Gate design notes
- Source 1 (VPR): uses _last_g85l2_vpr × dir_sign (volume pressure regime already directional)
- Source 2 (OFI): uses _last_g85b_ofi × dir_sign (OFI persistence ring already directional)
- Source 3 (EV): EV threshold 0.8R (high quality) / 0.4R (low quality); direction-agnostic — low EV is always hostile regardless of direction

## Banner strings updated
- KEY GATES line: 62-gate→63-gate, G8.5C3 entry appended
- wired-layers banner: 63-gate, Steps1-55, G8.5C3+VOETripleConv added
- architecture banner: 63-gate, Steps1-55, v95 entries added; NN-v31-170feat; ScanParallel110
- all-systems-online banner: 63-gate, G8.5C3:VOETripleConv added
- Telegram/scan launcher banner: 62-gate→63-gate, G8.5C3 added

**Why:**
OFI persistence, volume pressure regime, and EV quality are independently computed from different data pipelines (orderbook ring, vol/OFI cross, risk model). G8.5C3 cross-validates all three. When all agree a trade is high-quality, size up; when all flag it as low-quality, de-size and reduce score.

**How to apply:**
Next version is v96.0: gate G8.5D3 or similar, Kelly Step 56, NN v32 INPUT_DIM 170→175 (F171-F175), SCAN_PARALLEL_LIMIT 110→112.
