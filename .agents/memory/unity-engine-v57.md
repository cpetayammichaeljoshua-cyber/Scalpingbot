---
name: Unity Engine v57.0 upgrades
description: G8.5T TurboVec vectorized Python gate (Fib 3/8/21), 28-gate filter sync, nixpacks v44→v57 verify string fix, Dockerfile header fix.
---

## Key changes — v57.0 (2026-06-10)

### G8.5T TurboVec Vectorized 3-Timeframe Momentum Gate
- New soft-gate after G8.5x (line ~7688 in start_unity_engine.py)
- Uses real numpy vectorized computation — NOT just LLM prompt embedding
- Data source: `_quant_layer_close_buf` (per-symbol rolling close series, always populated by kline WS)
- 3 Fibonacci-period momentum returns: short=3-bar, mid=8-bar, long=21-bar
- Direction alignment count (n_aligned): 3→+2.5pts, 2→+1.0pts, 1→−1.0pts, 0→−2.5pts
- Cold-start guard: requires ≥25 bars in buffer (covers 21-bar long TF + buffer)
- Wired to gate_stats (_gate_stats["gate_g85t"]), _GATE_DISPLAY_LABELS ("G8.5T"), _SOFT_GATE_KEYS (excluded from bottleneck HUD — same pattern as G8.5w/G8.5x)
- Zero new Python dependencies — only numpy (already imported)

### 28-Gate Filter (27→28)
All occurrence sites updated:
- Module docstring ARCHITECTURE header
- Docstring gate list (G8.5T:TurboVec_3TF_Fib added)
- Wired-layers banner (11885)
- 🔒 GATE FILTER stamp (11924)
- ALL SYSTEMS ONLINE startup (15419)
- Launcher banner (16346)

### Nixpacks verify string — eliminated stale v44.0 boot stamps
The embedded Python verify script in nixpacks.toml (line 149) showed stale info on every Railway build log:
- "✅ UNITY ENGINE v44.0" → "v57.0"
- "MLP+RF 60-feature ensemble [v19.3]" → "70-feature NN v11 ensemble [v49.0]"
- "25-gate filter | v44.0-STRICT" → "28-gate filter | v57.0-STRICT"
- "[v44.0 — ZERO DEGRADED | ZERO BYPASS]" → "[v57.0 ...]"
- "Kelly24-DeepDD-CB" → "Kelly25-TurboVec-G8.5T"
- "NN_WIN_PROB_GATE=0.48" → "0.50"
- "Kelly Step 21" (HMMlearn) → "Kelly Step 25"
- torch forward-pass tag [v36.0] → [v57.0]

### Dockerfile header
- Line 2: "v44.0 — Multi-stage Production Dockerfile" → "v57.0"

**Why nixpacks verify string matters:**
Railway build logs show this Python print block verbatim during the `install` phase.
When it says "v44.0" with wrong gate count and wrong NN feature count, it creates confusion about
what version is actually deployed. Now every Railway build log shows the correct v57.0 stats.

**Why soft-gate exclusion matters for G8.5T:**
G8.5T fires only when _quant_layer_close_buf has ≥25 bars (takes ~25 kline ticks = ~25min warm-up).
During cold-start, _fired=False → _record("gate_g85t", False) → would appear as "0% pass" bottleneck
in gate_bottleneck_str(). Adding to _SOFT_GATE_KEYS prevents false bottleneck #1/#2/#3 display.
