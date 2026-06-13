---
name: Unity Engine v94.0 upgrades
description: v94.0 additions — G8.5B3 HMM-OFI-Spread Triple-Sync Gate (62nd gate), Kelly Step 54, NN v30 165feat, SCAN_PARALLEL 106→108
---

## Changes
- **G8.5B3 HOS-TripleSync** (62nd gate, ±2.0/±1.5pts): zero-API soft-gate cross-validating HMM regime state + OFI z-score direction + SpreadLiquidity gate output (_last_g85k_slq) vs signal direction. Triple align → +2.0pts, dual align → +1.5pts, triple oppose → -2.0pts, dual oppose → -1.5pts. Needs ≥2 active sources.
- **Kelly Step 54**: HOSTripleSync sizing (aligned → ×1.03, hostile → ×0.87).
- **NN v30**: INPUT_DIM 160→165; F161-F165: hmm_ofi_sync_norm, hmm_spread_sync_norm, ofi_spread_sync_norm, triple_hmm_quality, b3_gate_output.
- **SCAN_PARALLEL_LIMIT**: 106→108 (+1.9%).
- **_SOFT_GATE_KEYS**: gate_g85b3_hos added.
- **_GATE_DISPLAY_LABELS**: "gate_g85b3_hos" → "G8.5B3" added.

## Gate design notes
- Source 1 (HMM): BULL/BULLISH/TRENDING → +1 (favours LONG); BEAR/BEARISH → -1; RANGING/TRANSITIONING → 0 (neutral)
- Source 2 (OFI): z-score > 0.3 → +1×dir_sign; z < -0.3 → -1×dir_sign; else 0
- Source 3 (SpreadLiq): reuses _last_g85k_slq (+1=liquid, -1=illiquid). Liquid spread aligns with ANY direction; illiquid is universally hostile.

## Banner strings updated
- KEY GATES line: 61-gate→62-gate, G8.5B3 entry appended
- wired-layers banner: 62-gate, Steps1-54, G8.5B3+HOSTripleSync added
- architecture banner: 62-gate, Steps1-54, v94 entries added; NN-v30-165feat; ScanParallel108
- all-systems-online banner: 62-gate, G8.5B3:HOSTripleSync added
- Telegram/scan launcher banner: 61-gate→62-gate, G8.5B3 added

**Why:**
HMM regime, OFI order flow, and spread liquidity are three entirely independent microstructure channels. G8.5A3 covers VPIN+OFI+Funding; G8.5B3 covers HMM+OFI+Spread. Together they provide 6-source comprehensive microstructure validation.

**How to apply:**
Next version is v95.0: gate G8.5C3 or similar, Kelly Step 55, NN v31 INPUT_DIM 165→170 (F166-F170), SCAN_PARALLEL_LIMIT 108→110. Follow the same 8-step pattern.
