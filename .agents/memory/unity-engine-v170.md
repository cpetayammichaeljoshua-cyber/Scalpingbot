---
name: Unity Engine v170.0 upgrades
description: v170.0 data-confirmed session-structure gates, alpha/avoid expansion, NN v76 — key decisions worth preserving
---

## v170.0 Upgrades (v169→v170)

### G8.5AW — GHRZ Hour Regime Zero (155th gate)
- **Data source**: 12,231 SignalTactics USDM futures signals (Apr–Jul 2026)
- **Dead zones**: 00h UTC=52% WR, 19h UTC=52% WR vs 71% peak at 08h
- **Logic**: hour ∈ {0,19} + WR<30% → -2.0pt; structural alone → -1.5pt
- **Guard**: ≥20 lifetime trades before firing
- **Kelly Step 150**: crisis→×0.83, structural→×0.88

### G8.5AX — GALP Alpha Session Convergence Plus (156th gate)
- **Data**: 06-09h UTC = 67-71% WR peak in 12k-signal dataset
- **Logic**: hour ∈ {6,7,8,9} + WR≥32% → +1.5pt; + WR<32% → +1.0pt
- **Guard**: ≥20 trades + IRONS ≥ max(60, irons_floor)
- **Kelly Step 151**: strong→×1.04, recovery→×1.02

### Alpha/Avoid List Expansion
- **New alpha** (cross-source 12k validation): CAKEUSDT(84%WR n=97), OPUSDT(80% n=71), TRXUSDT(78% n=113), ENJUSDT(74% n=65)
- **New avoids**: ZKJUSDT(0%), PLAYUSDT(0%), FLOCKUSDT(11%), VVVUSDT(18%), HBARUSDT(avg -27.6%), SKYAIUSDT(17%)
- **Borderline additions**: CTSIUSDT(70% n=10), IOPUSDT(80% n=5)

### NN v76
- INPUT_DIM 390→395 (+5 features F391-F395)
- _TORCH_N_TOKENS 73→79 (73×5=365 was stale; 79×5=395 correct)
- Features: aw_ghrz_gate, hour_dead_zone, ax_galp_gate, peak_hour_score, session_edge_delta
- Wired in both engine (injection + setdefault fallbacks) and neural_signal_trainer.py build_features()
- Gate display labels + soft gate keys added for both new gates

### Infrastructure
- SCAN_PARALLEL_LIMIT 138→134 (-2.9% Railway CPU)
- UNITY_VERSION 169.0→170.0, 154-gate→156-gate, Kelly 149→151 steps

**Why**: Live WR=29% vs 60% in 12k signal dataset. Dead-zone hours (00h/19h=52% WR) and zero-WR symbols are structural bleed sources not covered by prior gates. GALP bonus rewards entering during the peak structural window (67-71% WR) to upsize quality positions.
