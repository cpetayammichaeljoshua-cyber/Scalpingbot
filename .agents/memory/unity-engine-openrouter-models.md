---
name: Unity Engine OpenRouter model roster
description: Confirmed working/dead OpenRouter free-tier models for Unity Engine — GODMODE combos, TIER lists, known 404 slugs
---

## Confirmed WORKING (v41.1 — 2026-06-02)

| Model | Tier | GODMODE | Notes |
|-------|------|---------|-------|
| openai/gpt-oss-20b:free | fast/std/power | #7 GODMODE_KIMI_RESEARCH | PRIMARY_MODEL; score=93.5/100; fastest + most reliable |
| openai/gpt-oss-120b:free | smart/power | #8 GODMODE_FINROBOT_CHAIN | live winner score=88-90/100, latency=7-19s |
| meta-llama/llama-3.3-70b-instruct:free | std/smart/power | #2 GODMODE_LLAMA_QUANT | periodic auth on some keys |
| qwen/qwen3-72b:free | std/smart/power | #3 GODMODE_QWEN_SYSTEMATIC | v27.0 swap from qwen3-next-80b |
| google/gemma-4-31b-it:free | smart/power | #9 GODMODE_OPENBB_MACRO | v21.2 confirmed |
| cognitivecomputations/dolphin-mistral-24b-venice-edition:free | std/smart/power | #1 GODMODE_DOLPHIN_ULTRAPLINIAN | periodic rate limits |
| z-ai/glm-4.5-air:free | std/smart/power | #5 GODMODE_GLM45_CONTRARIAN | 131K ctx |
| google/gemma-4-26b-a4b-it:free | std/smart/power | #11 GODMODE_GEMMA26B_VIBE | v26.0 confirmed |
| nvidia/nemotron-3-super-120b-a12b:free | smart/power | #6 GODMODE_NEMOTRON_MACRO | 120B, 1M ctx |
| qwen/qwen3-235b-a22b-instruct:free | smart/power | #10 GODMODE_QWEN235B_SOVEREIGN | v26.0 confirmed |

## GODMODE_COMBOS (10 total as of v41.1 — 2026-06-02)
1. GODMODE_DOLPHIN_ULTRAPLINIAN — dolphin-mistral-24b-venice-edition:free
2. GODMODE_LLAMA_QUANT — llama-3.3-70b-instruct:free
3. GODMODE_QWEN_SYSTEMATIC — qwen/qwen3-72b:free (v27.0: swapped from qwen3-next-80b)
4. ~~GODMODE_MOMENTUM_MISTRAL~~ — **REMOVED v41.1** mistral-small-3.2-24b:free → 404 2026-06-02
5. GODMODE_GLM45_CONTRARIAN — z-ai/glm-4.5-air:free
6. GODMODE_NEMOTRON_MACRO — nvidia/nemotron-3-super-120b-a12b:free
7. GODMODE_KIMI_RESEARCH — openai/gpt-oss-20b:free (swapped from kimi-k2 which got 404)
8. GODMODE_FINROBOT_CHAIN — openai/gpt-oss-120b:free
9. GODMODE_OPENBB_MACRO — google/gemma-4-31b-it:free
10. GODMODE_QWEN235B_SOVEREIGN — qwen/qwen3-235b-a22b-instruct:free (v26.0)
11. GODMODE_GEMMA26B_VIBE — google/gemma-4-26b-a4b-it:free (v26.0)
12. ~~GODMODE_PHI4_NOIX~~ — **REMOVED v41.1** phi-4-reasoning-plus:free → 404 2026-06-02

**Active 10: slots 1–3, 5–11 (no slots 4 or 12)**

## ULTRAPLINIAN Tiers (v41.1)
- fast: gpt-oss-20b ONLY [mistral-small-3.2-24b REMOVED v41.1 — 404; deepseek-v4-flash REMOVED v33.0]
- std: llama-3.3-70b, qwen3-72b, dolphin, glm-4.5-air, gemma-4-26b, gpt-oss-20b
- smart: llama-3.3-70b, qwen3-72b, dolphin, glm-4.5-air, gemma-4-26b, nemotron-120b, gpt-oss-120b, gemma-4-31b
- power: llama-3.3-70b, qwen3-72b, dolphin, glm-4.5-air, gemma-4-26b, gpt-oss-20b, gpt-oss-120b, gemma-4-31b, nemotron-120b
- ultra: ALL_FREE_MODELS (auto-deduplicated)

## PRIMARY_MODEL history
- v18.x–v21.1: llama-3.3-70b-instruct:free (periodic auth errors but functional)
- v21.2 (initial): moonshotai/kimi-k2:free — **immediately 404 on boot 2026-05-31**
- v21.2b+ (current): openai/gpt-oss-20b:free — best performer, no auth issues

**Rule:** Treat any "newly confirmed" free model as provisional until it survives 2+ consecutive live boots without 404. Both Microsoft phi-4 variants are permanently dead — never use them.

## Confirmed DEAD / 404 (never use)
- mistralai/mistral-small-3.2-24b-instruct:free → **404 confirmed v41.0 boot 2026-06-02** (worked <24h — added v33.0 on 2026-06-01, dead next day)
- microsoft/phi-4-reasoning-plus:free → **404 confirmed v41.0 boot 2026-06-02** (PLUS variant dead; was last surviving phi-4 slug)
- microsoft/phi-4-reasoning:free → **404 confirmed THREE TIMES: 2026-05-08, 2026-05-25, 2026-06-01** — base variant permanently dead
- deepseek/deepseek-v4-flash:free → **404 confirmed v33.0 boot 2026-06-01** (was working 2026-05-25; went dead)
- moonshotai/kimi-k2:free → **404 confirmed v21.2 boot 2026-05-31** (provider revoked free tier)
- deepseek/deepseek-r1-0528:free → **404 confirmed live log 2026-05-31**
- tngtech/deepseek-r1t-chimera:free → 404 confirmed (documented)
- qwen/qwen3-coder:free → 404 confirmed v20.5 boot
- arcee-ai/trinity-large-thinking:free → 404 confirmed v20.4 boot
- arcee-ai/trinity-large-preview:free → 404 confirmed 2026-05-03
- meta-llama/llama-4-maverick:free → 404 confirmed 2026-05-09
- meta-llama/llama-4-scout:free → 404 confirmed 2026-05-08
- google/gemma-3-27b-it:free → 404 confirmed 2026-05-25
- google/gemma-3-12b-it:free → 404 confirmed 2026-05-08
- mistralai/devstral-small:free → 404 confirmed 2026-05-25
- deepseek/deepseek-r1:free → 404 confirmed 2026-05-08
- meta-llama/llama-3.1-8b-instruct:free → 404
- qwen/qwen3-14b:free → 404 April 2026
- qwen/qwen3-30b-a3b:free → 404 confirmed twice
- qwen/qwen3-235b-a22b:free → 404 (WRONG SLUG — correct is `qwen3-235b-a22b-instruct:free`)
- nvidia/llama-3.1-nemotron-70b-instruct:free → 404
- deepseek/deepseek-chat:free → 404
- qwen/qwen3-next-80b-a3b-instruct:free → rate_limit storm (13 errors, 960s disabled v27.0) — replaced with qwen3-72b
