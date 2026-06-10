---
name: Unity Engine v56.0 upgrades
description: Claude Fable 5 + Mythos 5 integration; 10→12 GODMODE combos; TurboVec 3-TF momentum in Mythos5 prompt; version sync across all deployment files.
---

## Key changes — v56.0 (2026-06-10)

### Models added
- `anthropic/claude-fable-5` — OpenRouter slug (404-guarded; auto-disabled if not live)
- `anthropic/claude-mythos-5` — OpenRouter slug (404-guarded)
- Both prepended as position-0 to SIMPLE/MEDIUM/COMPLEX/REASONING in `smart_llm_router.py` TIER_MODELS
- Both added to MODEL_PRICING: Fable5=$6/$30, Mythos5=$10/$50 (input/output per Mtok)
- Duplicate dict key bug fixed: removed the second "alias" block (Python dict silently overwrites duplicates)

### GODMODE combos: 10 → 12
- `GODMODE_CLAUDE_FABLE5` — 4-step narrative chain (STRUCTURAL→MOMENTUM→RISK-ASYMMETRY→SYNTHESIS). emoji=📖
- `GODMODE_CLAUDE_MYTHOS5` — 5-layer TurboVec cross-asset macro (MACRO REGIME→FUNDING→INSTITUTIONAL FLOW→VECTORIZED MOMENTUM→SYNTHESIS). emoji=🏛️
- Both 404-guarded: GenericErrGuard auto-disables on 404/503; free-tier pool unaffected

### TurboVec integration
- TurboVec-style vectorized 3-timeframe momentum gate embedded in GODMODE_CLAUDE_MYTHOS5 system prompt:
  all-3-aligned → conviction 1.0×; 2/3 → 0.75×; split → mandatory NEUTRAL
- No new Python package deps (TurboVec concepts embedded in LLM prompt, not code)

### Version sync
- `start_unity_engine.py`: UNITY_VERSION "55.0"→"56.0", module docstring v55.0→v56.0, architecture stamp GODMODE-10combo→GODMODE-12combo[v56.0], CONSORTIUM-14s→CONSORTIUM-16s (was already 16s since v53.0, stamp was stale)
- `Dockerfile`: LABEL version "49.0"→"56.0", description updated, verify print v55.0→v56.0
- `nixpacks.toml`: header v55.0→v56.0
- `requirements.txt`: header v55.0→v56.0

**Why 404-guard for Claude 5 models:**
OpenRouter slugs for brand-new Anthropic models may not be immediately available or may change naming.
The existing GenericErrGuard + model-disable system (12 consecutive generic errors → 2h disable) handles
this automatically — no crash, no stuck state. Free-tier ensemble continues unaffected.
