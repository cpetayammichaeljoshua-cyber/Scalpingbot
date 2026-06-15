---
name: Unity Engine v107.0 upgrades
description: Storm model replacement (6 models), G8.5P3/Q3 gates 76th/77th, Kelly68+69, NN v39 210feat, IRONS WR<6%=80.5, ScanParallel130
---

## Key changes

**OpenRouter storm fix (primary crisis)**
- 6 GODMODE models replaced (all were storm-disabled every cycle):
  - GODMODE_DOLPHIN: dolphin-mistral-24b → nvidia/nemotron-3-super-120b-a12b:free
  - GODMODE_LLAMA_QUANT: llama-3.3-70b → google/gemma-4-31b-it:free
  - GODMODE_QWEN_SYSTEMATIC: qwen3-72b → nvidia/nemotron-3-super-120b-a12b:free
  - GODMODE_FABLE5: qwen3-235b → openai/gpt-oss-120b:free
  - GODMODE_MYTHOS5: llama-3.3-70b → openai/gpt-oss-20b:free
  - GODMODE_GEMMA26B_VIBE: gemma-4-26b → google/gemma-4-31b-it:free
- _MAX_AI_CALLS_PER_60S 8→16 (14 combos now fit within window)
- _MODEL_MAX_CALLS_PER_MIN 3→6 (up to 4× reuse of same model in combos)

**Why:** llama-3.3-70b, qwen3-72b, dolphin-mistral-24b, gemma-4-26b, qwen3-235b all in constant rate_limit/generic-error storm (storm=5+ every cycle → 120s disable) → CONSORTIUM always failing → ULTRAPLINIAN fallback only → Quality=0.0/100 display, signals/hr=2.

**Stable confirmed free-tier models as of v107.0:** gpt-oss-20b, gpt-oss-120b, nemotron-3-super-120b, gemma-4-31b.

**G8.5P3 FundMom-OFI-WRCrisis Triple-Resonance (76th gate, ±2.0/±1.5pts)**
- Reads: _last_g85n2_fmp_signal + _last_g85d_ofi_vel + _last_g85s2_crisis
- 3-vote: ±2.0pts; 2-vote majority: ±1.5pts
- Stores _last_g85p3_fos ∈ {+1,-1,0}; Kelly Step 68 (aligned×1.03/opposed×0.87)

**G8.5Q3 RegimeSent-WREV-EFO Triple-Coherence (77th gate, ±2.0/±1.5pts)**
- Reads: _last_g85r2_regimesent + _last_g85o2_ev_signal + _last_g85e3_efo
- 3-vote: ±2.0pts; 2-vote: ±1.5pts
- Stores _last_g85q3_rke ∈ {+1,-1,0}; Kelly Step 69 (aligned×1.03/opposed×0.87)

**NN v39 — INPUT_DIM 205→210, _TORCH_N_TOKENS 41→42**
- F206: fmp_ofi_wrc_norm (G8.5P3 output)
- F207: rsc_wrev_efo_norm (G8.5Q3 output)
- F208: p3_q3_consensus (P3+Q3 avg)
- F209: regime_crisis_meta (WRC+EFO+RSC)/3
- F210: multi_triple_sync (P3+Q3+N3)/3

**IRONS WR<6% = 80.5** — closes blind spot where WR<6% = WR<8% = 79.0

**ScanParallel 128→130**

**Boot confirmed:** 21/21 layers, 77-gate filter, Kelly(Steps1-69), GODMODE 14 combos 6 distinct models, Rate limit 6/min/model.
