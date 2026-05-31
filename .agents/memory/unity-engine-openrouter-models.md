---
name: Unity Engine OpenRouter model roster
description: Confirmed working/dead OpenRouter free-tier models for Unity Engine — GODMODE combos, TIER lists, known 404 slugs
---

## Confirmed WORKING (v21.5 — 2026-05-31)

| Model | Tier | GODMODE | Notes |
|-------|------|---------|-------|
| openai/gpt-oss-20b:free | fast/std/power | — | PRIMARY_MODEL v21.2b; score=93.5/100; fastest + most reliable |
| openai/gpt-oss-120b:free | smart/power | #8 GODMODE_FINROBOT_CHAIN | live winner score=88-90/100, latency=7-16s |
| meta-llama/llama-3.3-70b-instruct:free | std/smart/power | #2 GODMODE_LLAMA_QUANT | periodic auth on some keys |
| qwen/qwen3-next-80b-a3b-instruct:free | std/smart/power | #7 GODMODE_KIMI_RESEARCH | 80B MoE; v21.2b swap from kimi-k2 |
| google/gemma-4-31b-it:free | smart/power | #9 GODMODE_OPENBB_MACRO | v21.2 GODMODE; v21.5 confirmed |
| cognitivecomputations/dolphin-mistral-24b-venice-edition:free | std/smart/power | #1 GODMODE_DOLPHIN_ULTRAPLINIAN | periodic rate limits |
| z-ai/glm-4.5-air:free | std/smart/power | #5 GODMODE_GLM45_CONTRARIAN | 131K ctx |
| google/gemma-4-26b-a4b-it:free | std/smart/power | — | replaces gemma-3-27b; v21.5 smart-tier replacement for dead deepseek-r1-0528 |
| nvidia/nemotron-3-super-120b-a12b:free | smart/power | #6 GODMODE_NEMOTRON_MACRO | 120B, 1M ctx |
| deepseek/deepseek-v4-flash:free | fast/std/power | #4 GODMODE_MOMENTUM_DEEPSEEK | 1M ctx |

## GODMODE_COMBOS (9 total as of v21.2b — unchanged in v21.5)
1. GODMODE_DOLPHIN_ULTRAPLINIAN — dolphin-mistral-24b-venice-edition:free
2. GODMODE_LLAMA_QUANT — llama-3.3-70b-instruct:free
3. GODMODE_QWEN_SYSTEMATIC — qwen3-next-80b-a3b-instruct:free
4. GODMODE_MOMENTUM_DEEPSEEK — deepseek-v4-flash:free
5. GODMODE_GLM45_CONTRARIAN — z-ai/glm-4.5-air:free
6. GODMODE_NEMOTRON_MACRO — nvidia/nemotron-3-super-120b-a12b:free
7. GODMODE_KIMI_RESEARCH — qwen3-next-80b:free (v21.2b: swapped from kimi-k2 which got 404)
8. GODMODE_FINROBOT_CHAIN — openai/gpt-oss-120b:free (v21.2 NEW — FinRobot 5-analyst pipeline)
9. GODMODE_OPENBB_MACRO — google/gemma-4-31b-it:free (v21.2 NEW — OpenBB macro synthesis)

## ULTRAPLINIAN Tiers (v21.5)
- fast: gpt-oss-20b (PRIMARY), deepseek-v4-flash
- std: llama-3.3-70b, qwen3-next-80b, dolphin, glm-4.5-air, gemma-4-26b, gpt-oss-20b, deepseek-v4-flash (qwen3-235b REMOVED v21.4 — non-429 errors)
- smart: llama-3.3-70b, qwen3-next-80b, dolphin, glm-4.5-air, gemma-4-26b (v21.5 replaces dead deepseek-r1-0528), nemotron-120b, gpt-oss-120b, gemma-4-31b
- power: llama-3.3-70b, qwen3-next-80b, dolphin, glm-4.5-air, gemma-4-26b, gpt-oss-20b, gpt-oss-120b, deepseek-v4-flash, gemma-4-31b, nemotron-120b
- ultra: ALL_FREE_MODELS (auto-deduplicated)

## PRIMARY_MODEL history
- v18.x–v21.1: llama-3.3-70b-instruct:free (periodic auth errors but functional)
- v21.2 (initial): moonshotai/kimi-k2:free — **immediately 404 on boot 2026-05-31**
- v21.2b (corrected): openai/gpt-oss-20b:free — best performer, no auth issues

**Rule:** Treat any "newly confirmed" free model as provisional until it survives 2+ consecutive live boots without 404.

## Confirmed DEAD / 404 (never use)
- moonshotai/kimi-k2:free → **404 confirmed v21.2 boot 2026-05-31** (provider revoked free tier same day it was "confirmed")
- deepseek/deepseek-r1-0528:free → **404 confirmed live log 2026-05-31** (worked briefly, then died)
- tngtech/deepseek-r1t-chimera:free → 404 confirmed (documented in godmod3_strategy.py comments)
- qwen/qwen3-235b-a22b-instruct:free → persistent non-429 generic errors, demoted to ultra-only
- qwen/qwen3-coder:free → 404 confirmed v20.5 boot
- arcee-ai/trinity-large-thinking:free → 404 confirmed v20.4 boot
- arcee-ai/trinity-large-preview:free → 404 confirmed 2026-05-03
- meta-llama/llama-4-maverick:free → 404 confirmed 2026-05-09
- meta-llama/llama-4-scout:free → 404 confirmed 2026-05-08
- google/gemma-3-27b-it:free → 404 confirmed 2026-05-25
- google/gemma-3-12b-it:free → 404 confirmed 2026-05-08
- microsoft/phi-4-reasoning:free → 404 confirmed 2026-05-25
- mistralai/devstral-small:free → 404 confirmed 2026-05-25
- deepseek/deepseek-r1:free → 404 confirmed 2026-05-08
- meta-llama/llama-3.1-8b-instruct:free → 404
- qwen/qwen3-14b:free → 404 April 2026
- qwen/qwen3-30b-a3b:free → 404 confirmed twice
- qwen/qwen3-235b-a22b:free → 404 (WRONG SLUG — correct is `qwen3-235b-a22b-instruct:free`)
- nvidia/llama-3.1-nemotron-70b-instruct:free → 404
- deepseek/deepseek-chat:free → 404
