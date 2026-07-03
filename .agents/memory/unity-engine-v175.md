---
name: Unity Engine v175.0 upgrades
description: G8.5BG GPEL (165th gate, prompt-edge-lock streak) + G8.5BH GLCV (166th gate, loop-convergence-velocity); Kelly160+161; NN v81 420feat F416-F420; ScanParallel 118->114
---

## What shipped
- **G8.5BG GPEL** (165th gate, "Prompt-Edge-Lock Streak" — Technique 4 Prompt Refinement/The Loop): detects a RECURRING low/high streak in `quality_score_ring` (not just a single bad reading) and escalates the penalty/bonus the longer the pattern persists. Locked-low-streak(≥3) → -2.0pt; lean-low(≥2) → -1.0pt; locked-high-streak(≥3) → +1.0pt.
- **G8.5BH GLCV** (166th gate, "Loop-Convergence-Velocity" — Technique 5 Loop Engineering): treats recent `quality_score_ring` cycles as an evaluate-iterate loop and measures whether variance is shrinking (converging) or growing (diverging/thrashing). Diverging-crisis+WR<30% → -2.0pt; diverging-mild+WR<35% → -1.0pt; converging+WR≥30% → +1.0pt.
- Kelly Step 160 (GPEL ×0.78/×0.90/×1.04) + Step 161 (GLCV ×0.80/×0.90/×1.03).
- NN v81: INPUT_DIM 415→420, F416-F420 (bg_gpel_gate, gpel_streak_norm, bh_glcv_gate, glcv_var_delta_norm, loop_prompt_composite), tokens 83×5→84×5.
- SCAN_PARALLEL_LIMIT 118→114 (Railway CPU headroom for 2 new gates).

## Notable this cycle
The GPEL/GLCV gate logic, constants, and sentinel init (`_last_g85bg_gpel`/`_last_g85bh_glcv`) were found ALREADY implemented in the source before this session started (half-shipped from a prior session) — only the 10-point infra sync checklist (from v174 memory) was missing and had to be completed: gate_stats/gate_stats_recent init, display labels, soft-gate keys, Kelly steps, NN feature block, both banner strings, header/changelog, SCAN_PARALLEL_LIMIT, and the trainer file INPUT_DIM/_TORCH_N_TOKENS/build_features block. Always check for this "gate logic exists but infra is unsynced" half-shipped state before assuming a gate pair needs to be built from scratch — grep for `_last_g85` sentinels and the gate eval block first.

This completes the full "6 Anthropic prompting techniques" gate-mapping arc started in v174.0: Technique 1 (Role Definition) + 3 (Extended Thinking) → GRDC; Technique 2 (XML Delimiters) + 6 (Workflow Isolation) → GXWI; Technique 4 (Prompt Refinement/Loop) → GPEL; Technique 5 (Loop Engineering) → GLCV.

## Infra sync checklist (unchanged from v174, reconfirmed accurate)
See `.agents/memory/unity-engine-v174.md` for the full 10-point checklist — it held exactly as documented for this version too.
