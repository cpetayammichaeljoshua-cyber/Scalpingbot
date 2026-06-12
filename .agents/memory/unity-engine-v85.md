---
name: Unity Engine v85.0 upgrades
description: G8.5S2 WRCrisisRegime + G8.5T2 ExtremeFearRegime 53rd/54th gates; Kelly 45+46; NN v22 125feat; GODMODE FABLE-5+MYTHOS-5; CPCV floor 50%→45%
---

## v85.0 (2026-06-12) — 54-gate, Kelly 1-46, NN v22 125feat, GODMODE 14combo

### G8.5S2 — WinRate-CrisisRegime (53rd gate, ±2.0/+1.5pts)
- Zero-API-call: reads `self._booster.wr_bayes` directly (already computed)
- Decision: WR>55% → +2.0; WR>45% → +1.5; WR<28% → -2.0; WR<35% → -1.5; else 0
- Stores `_last_g85s2_crisis` (+1/-1/0) for Kelly Step 45
- Key gates: `gate_g85s2_wrcrisis` in `_gate_stats`, `_GATE_DISPLAY_LABELS`, `_SOFT_GATE_KEYS`

### G8.5T2 — ExtremeFearRegime (54th gate, ±1.5/+0.5pts)
- Zero-API-call: reads `signal_data.get("fear_greed_index", 50)` + direction
- F&G<20 SELL→+1.5; F&G<20 BUY→-1.5; F&G<35 SELL→+0.5; F&G<35 BUY→-0.5
- F&G>80 BUY→+1.5; F&G>80 SELL→-1.5; F&G>65 BUY→+0.5; F&G>65 SELL→-0.5
- Stores `_last_g85t2_fearreg` (+1/-1/0) for Kelly Step 46

### Kelly Step 45 — WRCrisisRegime Sizing
- G8.5S2=+1 (healthy) → ×1.03; G8.5S2=-1 (ultra-crisis) → ×0.86

### Kelly Step 46 — ExtremeFearRegime Sizing
- G8.5T2=+1 (aligned) → ×1.02; G8.5T2=-1 (contra-regime) → ×0.88

### NN v22 — 125 features (25×5 tokens)
- F121: wr_crisis_score = (wr_bayes - 0.35) / 0.20 clipped [-1,+1]
- F122: fear_greed_regime = (fg - 50) / 50 clipped [-1,+1]
- F123: g85s2_crisis (+1/0/-1 from G8.5S2)
- F124: g85t2_fearreg (+1/0/-1 from G8.5T2)
- F125: crisis_regime_composite = (1.5×F123 + 1.0×F124 + 0.5×F121) / 3.0
- neural_signal_trainer.py: INPUT_DIM 120→125, _TORCH_N_TOKENS 24→25

### GODMODE 14 combos (12→14)
- GODMODE_FABLE5: qwen3-235b-a22b-instruct:free — 3-arc narrative synthesis (ACCUMULATION/DISTRIBUTION/CONFUSION)
- GODMODE_MYTHOS5: meta-llama/llama-3.3-70b-instruct:free — temporal pattern resonance (momentum/reversal/neutral)
- Both models confirmed working free tier (qwen3 from v27.0, llama-3.3-70b confirmed stable)

### CPCV floor fix (neural_signal_trainer.py)
- `_cpcv_avg > 0.50` → `_cpcv_avg > 0.45`
- **Why:** live logs showed avg≈47.2% chronically excluded by 50% boundary, suppressing all overfit protection
- **How to apply:** any CPCV floor bump should account for realistic avg range at WR=35% (≈45-50%)

### ScanParallel 90→92, 54-gate filter, all banners updated [v85.0]
