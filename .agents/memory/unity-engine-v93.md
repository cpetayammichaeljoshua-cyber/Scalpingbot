---
name: Unity Engine v93.0 upgrades
description: v93.0 additions — G8.5A3 VPIN-OFI-Funding Triple-Confluence Gate (61st gate), Kelly Step 53, NN v29 160feat, SCAN_PARALLEL 104→106
---

## Changes
- **G8.5A3 VPC-TripleConf** (61st gate, ±2.0/±1.5pts): zero-API cross-validation combining VPIN toxicity pct + OFI z-score direction + funding rate trend direction vs signal direction. Triple align → +2.0pts, dual align → +1.5pts, triple oppose → -2.0pts, dual oppose → -1.5pts. Needs ≥2 active sources.
- **Kelly Step 53**: VPCTripleConf sizing (aligned → ×1.03, toxic-opposed → ×0.87).
- **NN v29**: INPUT_DIM 155→160; F156-F160: vpin_ofi_conf_norm, vpin_fund_conf_norm, ofi_fund_conf_norm, triple_conf_quality, vpc_gate_output.
- **SCAN_PARALLEL_LIMIT**: 104→106 (v93.0 increment; prior stale fix raised 100→106 in same session).
- **_SOFT_GATE_KEYS**: gate_g85a3_vpc added (cannot block a signal, quality adjuster only).
- **_GATE_DISPLAY_LABELS**: "gate_g85a3_vpc" → "G8.5A3" added.

## Banner strings updated
- Docstring header: v92.0→v93.0, 60-gate→61-gate, Kelly 52-steps→53-steps
- KEY GATES line: 60-gate→61-gate, G8.5A3 entry appended
- wired-layers banner: 61-gate, Steps1-53, G8.5Z2+G8.5A3 added
- architecture banner: 61-gate, Steps1-53, v92+v93 entries added; NN-v29-160feat; ScanParallel106
- all-systems-online banner: 61-gate, G8.5Z2+G8.5A3 entries added
- Telegram/scan banner (line ~21439): 58-gate→61-gate, v88-v93 gate entries added

**Why:**
VPIN is already computed by _vpin_model; OFI z-score and funding rate trend are already in signal_data. This gate costs zero API calls and cross-validates three independent flow/toxicity signals, catching cases where a single source looks clean but two others oppose.

**How to apply:**
Next version is v94.0: gate G8.5B3 or similar, Kelly Step 54, NN v30 INPUT_DIM 160→165 (F161-F165), SCAN_PARALLEL_LIMIT 106→108. Follow the same 8-step pattern: gate_stats init → NN injection block → gate code block → Kelly step → _GATE_DISPLAY_LABELS → _SOFT_GATE_KEYS → all banners → UNITY_VERSION bump.
