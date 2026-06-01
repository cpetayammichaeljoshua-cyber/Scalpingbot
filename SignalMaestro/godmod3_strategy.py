#!/usr/bin/env python3
"""
G0DM0D3 AI Strategy Engine — Trading Signal Orchestration  [v6.1 — April 2026]
=================================================================================
Fully integrates the G0DM0D3 framework (github.com/elder-plinius/G0DM0D3)
as the primary AI intelligence layer for the MiroFish Swarm Bot.

Integrated from: https://github.com/cpetayammichaeljoshua-cyber/z4ptacticsbot.git
Live-verified models (April 2026) and production-grade multi-model cascade.

G0DM0D3 Modules:
  ⚡ ULTRAPLINIAN    — Multi-model racing: 17+ confirmed-working models, 5 tiers, tier-escalation
  🎛  AutoTune       — Context-adaptive sampling (volatile/trending/ranging/breakout/news)
  🐍  Parseltongue   — Input perturbation engine (light/medium/heavy intensity)
  ⚡  STM Pipeline   — hedge_reducer + direct_mode + json_enforcer + think_stripper
  🔥  GODMODE CLASSIC — 5 distinct model+prompt combos racing in parallel
  🪣  PerModelBucket — Per-model token-bucket: dynamic limit from X-RateLimit-Limit header
  🔄  AutoReset      — Soft-disabled tier reset with 150s cooldown guard (v5.5: seeded init)
  📈  TierEscalation — fast → standard → smart → power → ultra, X-RateLimit-Reset
  🏥  ErrorTypeTrack — auth(24h), 429(X-RateLimit-Reset), 503(45s), 404(1h), generic(2h)
  🚦  AISignalGate   — has_available_models() + was_recently_available(300s)
  🧠  WinRateBoost   — Signal scoring with consensus weighting + narrative quality check
  🔢  EnsembleVote   — Multi-model majority vote + confidence weighted aggregation
  🛡️  GenericErrGuard — Moonshot/generic-error tracking → disable after 8 non-429 errors (2h)

Free Models: 38+ Live-Verified (OpenRouter free tier, April 2026)
API Gateway : https://openrouter.ai/api/v1 (OpenAI-compatible)
Auth        : OPENROUTER_API_KEY environment variable

CRITICAL FIXES v5.0 (April 2026 production):
  1. max_retries=0 → fixes "asyncio ERROR: Task exception was never retrieved"
  2. _PerModelRateLimiter → dynamic per-model bucket (reads X-RateLimit-Limit header)
     Each model has different req/min limits; dynamic parsing prevents over-calling.
  3. X-RateLimit-Reset parsing → precise 429 recovery instead of fixed 300s cooldown
     Parses both 'X-RateLimit-Reset' timestamp AND 'X-RateLimit-Limit' per model.
  4. Auto-reset cooldown guard (90s minimum) → breaks the reset→rate-limit→reset loop
  5. has_available_models() + was_recently_available() → signal gate for AI readiness
  6. 26+ free models (was 15) — massively reduces per-model rate pressure
     Added: QwQ-32B, Qwen3-30B, Qwen3-14B, Qwen3-8B, Qwen3-4B, Qwerky-72B,
            MAI-DS-R1, GLM-Z1-Rumination, Gemma-2-9B, Devstral-Small, UI-TARS-72B
  7. 5-tier cascade (was 3) — more fallback options before giving up
  8. GODMODE CLASSIC: 5 truly distinct models (Hermes/Llama/QwQ/Qwen3/Gemma)
     Moonlight replaced by QwQ-32B (reasoning) for better signal quality
  9. EnsembleVote: majority-vote across all successful responses improves win rate
 10. Adaptive inter-call delay: longer delay when rate pressure detected
 11. GenericErrGuard: disable models after 8 consecutive non-429 errors (2h disable)
     Moonlight/generic error-prone models tracked separately from 429s
     _generic_error_counts[model] tracks non-429 generic failures independently
 12. Global throttle: increased from 50/min to 80/min for higher throughput
     Per-model buckets are the primary guard; global throttle is safety backstop only
 13. PerModelLimit: parse X-RateLimit-Limit from 429 responses → precise model caps
 14. RACE_SEM_LIMIT: increased from 2 to 4 — race more models concurrently
 15. GLOBAL_CONCURRENT_LIMIT: increased from 3 to 6 — higher throughput
 16. _MODEL_ERROR_THRESHOLD: 3→5 for rate/unavail errors (less aggressive disable)

CRITICAL FIXES v5.5 (2026-04-19 session 6):
 1. AutoReset storm-loop root cause: _last_tier_reset={} returned 0.0 via .get(key, 0.0).
    time.monotonic() is OS uptime (hours/days), so the 150s cooldown guard was bypassed
    on EVERY session boot. Models disabled → AutoReset fired 1ms later → re-enabled →
    stormed again → disabled → AutoReset blocked for 150s → stuck → repeat forever.
    Fix: seed ALL tier keys with time.monotonic() at __init__ so guard runs from boot.
 2. Selective re-enable in AutoReset: previously ALL soft-disabled models were force-
    re-enabled regardless of their remaining disable window. Now only models within 120s
    of natural expiry are cleared; if none qualify, only the soonest-expiring model is
    returned to service (minimum-viable recovery, prevents mass re-storm).
 3. _MODEL_ERROR_THRESHOLD: 5→7 — free-tier returns sporadic 429s; need 7 consecutive
    to confirm genuine rate pressure, not just transient spikes.
 4. _MAX_AI_CALLS_PER_60S: 8→4 — 80-symbol scans with tier-cascade generated up to
    16 OpenRouter req/min concentrated on fast-tier models. Halved to stay under limits.
 5. _AUTO_RESET_COOLDOWN_S: 300→150s — 300s was unnecessarily conservative once the
    initialization bug is fixed; 150s is sufficient between emergency auto-resets.
"""

import asyncio
import json
import logging
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# OpenRouter Configuration
# ─────────────────────────────────────────────────────────────────────────────

OPENROUTER_BASE_URL  = "https://openrouter.ai/api/v1"
OPENROUTER_SITE_URL  = "https://replit.com"
OPENROUTER_SITE_NAME = "MiroFish-G0DM0D3-TradingBot"

# ─────────────────────────────────────────────────────────────────────────────
# Free Models — Comprehensive Live-Verified Pool (April 2026)
# Rate limit: ~8 req/min per model (from X-RateLimit-Limit in 429 headers)
# 25 models across 5 tiers — massively reduces per-model rate pressure
# ─────────────────────────────────────────────────────────────────────────────

# TIER 1 — Premium Free: Large, highest-quality instruction + reasoning models
# NOTE: Only models confirmed accessible on OpenRouter free tier (April/May 2026)
# Models that return 404 (not on free tier) are EXCLUDED from TIER 1:
#   nvidia/llama-3.1-nemotron-70b-instruct:free  → 404
#   deepseek/deepseek-r1-0528:free               → 404
#   deepseek/deepseek-chat:free                  → 404
#   deepseek/deepseek-r1-zero:free               → 404
#   tngtech/deepseek-r1t-chimera:free            → 404
#   mistralai/mistral-small-3.1-24b-instruct:free → 404
#   mistralai/mistral-7b-instruct:free           → 404
#   microsoft/phi-3-medium-128k-instruct:free    → 404
#   cohere/command-r7b-12-2024:free              → 404
#   google/gemma-3-12b-it:free                   → moved to TIER4 (too small for TIER1 quality)
#   qwen/qwen3.6-plus:free                       → 404 (account tier issue)
#   qwen/qwen3-30b-a3b:free                      → 404 (confirmed April 2026)
#   arliai/qwq-32b-arliai:free                   → persistent generic errors (confirmed April 2026)
_TIER1_MODELS: List[str] = [
    # REMOVED: nousresearch/hermes-3-llama-3.1-405b:free → 43+ consecutive rate_limit storm (2026-04-19 session 3)
    #   Too popular on free tier — shared rate limit exhausted within seconds. Moved to TIER5 only.
    # REMOVED: meta-llama/llama-4-maverick:free → 404 confirmed live log 2026-05-09 [v18.54]
    # REMOVED: moonshotai/kimi-k2:free → 404 confirmed live log v21.2 boot 2026-05-31 (provider revoked free access)
    "meta-llama/llama-3.3-70b-instruct:free",          # Llama 3.3 70B — reliable flagship (periodic auth on some keys)
    # REMOVED (v27.0 2026-05-31): qwen/qwen3-next-80b-a3b-instruct:free → rate_limit storm confirmed
    #   Railway log 2026-04-21: 13 consecutive rate_limit errors → disabled 960s, storm=28 accumulated.
    #   "qwen3-next-80b-a3b-instruct" is not a real Qwen3 model (no 80B-a3b variant exists in QwenLM lineup).
    #   Replaced with qwen/qwen3-72b:free — confirmed valid free-tier slug, no storm history.
    "qwen/qwen3-72b:free",                             # Qwen3 72B dense — confirmed free-tier, no storm
    # REMOVED: qwen/qwen3-235b-a22b:free → 404 confirmed live log 2026-05-13 [v18.68] (wrong slug)
    # RE-ADDED: qwen/qwen3-235b-a22b-instruct:free → CORRECT slug re-confirmed working 2026-05-22 [v19.7]
    "qwen/qwen3-235b-a22b-instruct:free",              # Qwen3 235B A22B — re-confirmed working 2026-05-22
    # REMOVED: qwen/qwen3-30b-a3b:free → 404 confirmed live log 2026-05-13 [v18.68] (re-confirmed, same as April 2026)
]

# TIER 2 — Standard Free: Fast, reliable workhorse models
# REMOVED (confirmed 404/dead from LIVE LOGS April 19 2026):
#   featherless/qwerky-72b:free         → 404
#   qwen/qwen-2.5-72b-instruct:free     → 404
#   moonshotai/moonlight-16a-a3b-instruct:free → persistent generic errors
#   stepfun/step-3.5-flash:free         → 404 CONFIRMED LIVE LOG 2026-04-19
#   google/gemini-2.0-flash-exp:free    → 404 CONFIRMED LIVE LOG 2026-04-19
#   google/gemini-flash-1.5:free        → 404 CONFIRMED LIVE LOG 2026-04-19
#   qwen/qwen3-14b:free                 → 404 CONFIRMED LIVE LOG 2026-04-19
#   nousresearch/hermes-3-llama-3.1-70b:free → 404
_TIER2_MODELS: List[str] = [
    # v21.1: TIER2 re-populated with confirmed free-tier workhorse models
    # Previously empty after mass removal of dead slugs (April-May 2026)
    # REMOVED: qwen/qwq-32b:free, mistralai/mistral-nemo:free, deepseek/deepseek-v3-0324:free
    # REMOVED: nvidia/llama-3.3-nemotron-super-49b-v1:free, arcee-ai/trinity-large-preview:free
    # REMOVED (2026-05-27): qwen/qwen3-coder:free → 404 confirmed live log v20.5 boot
    "google/gemma-4-31b-it:free",                      # Gemma 4 31B — confirmed free 2026-05-25, high quality
]

# TIER 3 — Extended Free: Good quality, sometimes slower
# REMOVED (April 2026 — confirmed 404/dead or generic-error prone):
#   cognitivecomputations/dolphin3.0-mistral-24b:free → 404
#   thudm/glm-z1-rumination-32b:free                  → 404
#   rekaai/reka-flash-3:free                          → 404
#   qwen/qwen3-8b:free                                → 404
#   microsoft/phi-4:free                              → 404
#   microsoft/phi-4-reasoning:free                    → 404
#   microsoft/mai-ds-r1:free                          → 404
#   shisa-ai/shisa-v2-llama3.3-70b:free               → persistent generic errors
_TIER3_MODELS: List[str] = [
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",  # Dolphin 24B Venice
    "z-ai/glm-4.5-air:free",                           # GLM-4.5 Air (131K ctx)
    # REMOVED (2026-05-07): google/gemma-3-27b-it:free → 404 disabled 24h per restart
    # RE-ADDED (2026-05-22): gemma-3-27b re-confirmed working per smart_llm_router v18.90 [v19.7]
    # REMOVED AGAIN (2026-05-25): google/gemma-3-27b-it:free → 404 live log [v19.7b] — no longer on free tier
    # REPLACED: google/gemma-4-26b-a4b-it:free — Gemma 4 26B successor, confirmed in free list 2026-05-25
    "google/gemma-4-26b-a4b-it:free",                  # Gemma 4 26B A4B IT — confirmed free tier 2026-05-25
    # REMOVED (2026-05-08): microsoft/phi-4-reasoning:free → 404
    # RE-ADDED (2026-05-22): phi-4-reasoning re-confirmed [v19.7]; REMOVED AGAIN (2026-05-25) → 404 live log
    # REMOVED (2026-05-27): arcee-ai/trinity-large-thinking:free → 404 confirmed live log v20.4 boot; disabled 24h auto, perm removed
    # REPLACED: nvidia/nemotron-3-super-120b-a12b:free — 120B reasoning model, 1M ctx, confirmed free tier 2026-05-25
    "nvidia/nemotron-3-super-120b-a12b:free",           # Nvidia Nemotron 120B Super — confirmed free 2026-05-25
    # NEW (2026-05-25): OpenAI OSS 120B — confirmed in free tier live query, large high-quality model
    "openai/gpt-oss-120b:free",                         # OpenAI OSS 120B — confirmed free 2026-05-25
]

# TIER 4 — Compact Free: Small but fast, great for quick decisions
# REMOVED (April 2026 — confirmed 404/dead or rate-limit storm):
#   google/gemma-2-9b-it:free                 → 404
#   mistralai/devstral-small:free              → 404
#   meta-llama/llama-3.1-8b-instruct:free     → 404
#   nvidia/llama-3.1-nemotron-nano-8b-v1:free → 404
#   arcee-ai/trinity-mini:free                → 404
#   qwen/qwen3-4b:free                        → 404
#   liquid/lfm-2.5-1.2b-thinking:free         → 21+ consecutive rate_limit storm (2026-04-19)
#   google/gemma-3-12b-it:free                → 404 confirmed live log 2026-05-08 [v18.32]
_TIER4_MODELS: List[str] = [
    # REMOVED: meta-llama/llama-4-scout:free → 404 confirmed live log 2026-05-08 [v18.33]
    # REMOVED: google/gemma-3-12b-it:free → 404 confirmed 2026-05-08 live log (v18.32)
    # REMOVED: meta-llama/llama-3.2-11b-vision-instruct:free → 404 confirmed LIVE session 2 2026-04-19
    # REMOVED: thudm/glm-4-32b:free                          → 404 confirmed LIVE 2026-04-19
    # REMOVED: qwen/qwen3-30b-a3b:free → 404 confirmed TWICE: April 2026 + live log 2026-05-13 [v18.68]
    # REMOVED (2026-05-08): mistralai/devstral-small:free → 404
    # RE-ADDED (2026-05-22): devstral-small re-confirmed [v19.7]; REMOVED AGAIN (2026-05-25) → 404 live log
    # REPLACED: openai/gpt-oss-20b:free — confirmed free tier 2026-05-25, OpenAI OSS 20B fast model
    "openai/gpt-oss-20b:free",                         # OpenAI OSS 20B — confirmed free 2026-05-25
    # NEW (2026-05-25): DeepSeek V4 Flash — 1M ctx, confirmed free tier 2026-05-25
    "deepseek/deepseek-v4-flash:free",                 # DeepSeek V4 Flash — confirmed free 2026-05-25
]

# TIER 5 — Fallback Free: Lightweight final safety nets
# REMOVED (April 2026):
#   openrouter/auto               → NOT a free model; routes to paid → constant generic errors
#   bytedance-research/ui-tars-72b:free → 404 (no longer on free tier)
#   arliai/llama-3.2-8b-chat-16k:free  → persistent generic errors (banned)
#   liquid/lfm-2.5-1.2b-instruct:free  → 50+ consecutive rate_limit storm (2026-04-19 session 3)
#   nousresearch/hermes-3-llama-3.1-405b:free → 43+ consecutive rate_limit storm (session 3)
#   meta-llama/llama-3.2-3b-instruct:free → 14+ consecutive rate_limit storm (session 4, storm loop)
_TIER5_MODELS: List[str] = []  # All Tier-5 models storm-removed (2026-04-19)

ALL_FREE_MODELS: List[str] = list(dict.fromkeys(
    _TIER1_MODELS + _TIER2_MODELS + _TIER3_MODELS + _TIER4_MODELS + _TIER5_MODELS
))

PRIMARY_MODEL = "openai/gpt-oss-20b:free"   # v21.2b: gpt-oss-20b elevated to PRIMARY — score=93.5/100, latency=6548ms, consistently wins ULTRAPLINIAN races; kimi-k2 got 404 2026-05-31 (removed from free tier); llama-3.3-70b gets periodic auth errors

# ULTRAPLINIAN tiers — only confirmed-working free-tier models (404s excluded)
# v5.1 MODEL AUDIT — all models validated against LIVE error logs 2026-04-19:
# REMOVED (Round 1 — prior session):
#   stepfun/step-3.5-flash:free         → 404
#   google/gemini-2.0-flash-exp:free    → 404
#   google/gemini-flash-1.5:free        → 404
#   qwen/qwen3-14b:free                 → 404
#   liquid/lfm-2.5-1.2b-thinking:free   → rate_limit storm (21+ consecutive errors)
# REMOVED (Round 2 — confirmed from THIS session's live logs 2026-04-19):
#   deepseek/deepseek-v3-0324:free               → generic errors (7+ consecutive)
#   nvidia/llama-3.3-nemotron-super-49b-v1:free  → 404
#   thudm/glm-4-32b:free                         → 404
# CONFIRMED WORKING (no 404 errors in live logs):
#   qwen/qwq-32b, qwen/qwen3-coder, arcee-ai/trinity-large-preview, mistralai/mistral-nemo
#   nousresearch/hermes-3-llama-3.1-405b, meta-llama/llama-3.3-70b-instruct
#   qwen/qwen3-next-80b-a3b-instruct, z-ai/glm-4.5-air, google/gemma-3-27b-it
#   cognitivecomputations/dolphin-mistral-24b-venice-edition
#   google/gemma-3-12b-it, meta-llama/llama-3.2-11b-vision-instruct
#   liquid/lfm-2.5-1.2b-instruct, meta-llama/llama-3.2-3b-instruct
# FINAL CONFIRMED WORKING POOL (validated 2026-04-19 session 3):
# REMOVED storm models: hermes-3-llama-3.1-405b (43+ errors), liquid/lfm-2.5-1.2b (50+ errors)
# Rate-limited (temporary, auto-recover): llama-3.3-70b, qwen3-next-80b, dolphin-24b,
#   z-ai/glm-4.5-air, gemma-3-27b, arcee-trinity, llama-3.2-3b
# Stable (low rate pressure): qwen3-coder, gemma-3-12b
ULTRAPLINIAN_TIERS: Dict[str, List[str]] = {
    "fast": [
        # Fastest confirmed-working models (validated 2026-04-19 session 3)
        # REMOVED: liquid/lfm-2.5-1.2b-instruct:free → 50+ rate_limit storm (session 3)
        # REMOVED: meta-llama/llama-3.2-3b-instruct:free → 14+ rate_limit storm (session 4)
        # REMOVED: arcee-ai/trinity-large-preview:free → 404 permanently (2026-05-03)
        # REMOVED: google/gemma-3-12b-it:free → 404 confirmed 2026-05-08 live log [v18.32]
        # v20.2: REORDERED — gpt-oss-20b:free moved FIRST: live-validated winner score=93.5/100
        #        latency=6548ms, consistently wins ULTRAPLINIAN races; fastest real-trading winner.
        "openai/gpt-oss-20b:free",
        # NEW 2026-05-25: DeepSeek V4 Flash — 1M ctx, very fast inference; 2nd in fast tier
        "deepseek/deepseek-v4-flash:free",
        # REMOVED: meta-llama/llama-4-scout:free → 404 confirmed live log 2026-05-08 [v18.33]
        # RE-ADDED 2026-05-22: devstral-small — fast small model [v19.7]
        # REMOVED AGAIN 2026-05-25: mistralai/devstral-small:free → 404 live log [v19.7b]
        # REMOVED (2026-05-27): qwen/qwen3-coder:free → 404 confirmed live v20.5 boot
    ],
    "standard": [
        # Workhorse models — confirmed working (rate-limited only, recovers)
        # REMOVED: arcee-ai/trinity-large-preview:free → 404 permanently (2026-05-03)
        # REMOVED (2026-05-07): google/gemma-3-27b-it:free → 404 — RE-ADDED 2026-05-22 [v19.7]
        # REMOVED AGAIN (2026-05-25): google/gemma-3-27b-it:free → 404 live log [v19.7b]
        # REMOVED: google/gemma-3-12b-it:free → 404 confirmed 2026-05-08 [v18.32]
        # REMOVED: meta-llama/llama-4-maverick:free → 404 confirmed live log 2026-05-09 [v18.54]
        "meta-llama/llama-3.3-70b-instruct:free",
        # REMOVED (v27.0 2026-05-31): qwen/qwen3-next-80b-a3b-instruct:free → rate_limit storm (13 errors, 960s disabled)
        # REMOVED (2026-05-31) [v21.4]: persistent generic (non-429) errors in live log → GenericErrGuard
        # cycles drain CONSORTIUM quality; demoted to ultra-only tier where it can fail gracefully
        # REPLACEMENT: gpt-oss-20b:free — confirmed working, fast GPT-series dense architecture
        "qwen/qwen3-72b:free",
        "openai/gpt-oss-20b:free",
        # REMOVED: meta-llama/llama-4-scout:free → 404 confirmed live log 2026-05-08 [v18.33]
        "z-ai/glm-4.5-air:free",
        "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
        # REMOVED (2026-05-27): qwen/qwen3-coder:free → 404 confirmed live v20.5 boot
        # REPLACED (2026-05-25): gemma-3-27b → gemma-4-26b-a4b-it (Gemma 4 successor, confirmed free)
        "google/gemma-4-26b-a4b-it:free",
        # NEW (2026-05-25): DeepSeek V4 Flash — 1M ctx, confirmed free tier
        "deepseek/deepseek-v4-flash:free",
    ],
    "smart": [
        # High-quality reasoning models — validated 2026-04-19 session 3
        # REMOVED: nousresearch/hermes-3-llama-3.1-405b:free → 43+ consecutive rate_limit storm
        # REMOVED: arcee-ai/trinity-large-preview:free → 404 permanently (2026-05-03)
        # REMOVED (2026-05-07): google/gemma-3-27b-it:free — RE-ADDED 2026-05-22 [v19.7]
        # REMOVED AGAIN (2026-05-25): google/gemma-3-27b-it:free → 404 live log [v19.7b]
        # REMOVED: google/gemma-3-12b-it:free → 404 confirmed 2026-05-08 [v18.32]
        # REMOVED: meta-llama/llama-4-maverick:free → 404 confirmed live log 2026-05-09 [v18.54]
        # REMOVED: moonshotai/kimi-k2:free → 404 confirmed v21.2 boot 2026-05-31
        "meta-llama/llama-3.3-70b-instruct:free",
        # REMOVED (v27.0 2026-05-31): qwen/qwen3-next-80b-a3b-instruct:free → rate_limit storm (13 errors, 960s disabled)
        # REMOVED (2026-05-31) [v21.4]: persistent generic (non-429) errors → demoted to ultra-only
        # REMOVED (2026-05-31) [v21.5]: deepseek/deepseek-r1-0528:free → 404 confirmed live log
        # REPLACED with Gemma 4 26B — confirmed working free tier
        "qwen/qwen3-72b:free",
        "google/gemma-4-26b-a4b-it:free",
        # REMOVED: meta-llama/llama-4-scout:free → 404 confirmed live log 2026-05-08 [v18.33]
        # REMOVED: deepseek/deepseek-r1:free → 404 confirmed live log 2026-05-08 [v18.37]
        # REMOVED (2026-05-27): qwen/qwen3-coder:free → 404 confirmed live v20.5 boot
        "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
        "z-ai/glm-4.5-air:free",
        # RE-ADDED 2026-05-22: phi-4-reasoning [v19.7]; REMOVED AGAIN 2026-05-25 → 404 live log [v19.7b]
        # REMOVED (2026-05-27): arcee-ai/trinity-large-thinking:free → 404 live v20.4 boot; perm removed
        # REPLACED: nvidia/nemotron-3-super-120b-a12b:free
        "nvidia/nemotron-3-super-120b-a12b:free",
        # NEW (2026-05-25): OpenAI OSS 120B — massive model, confirmed free tier 2026-05-25
        "openai/gpt-oss-120b:free",
        # NEW (2026-05-25): Gemma 4 31B — upgraded Gemma generation, confirmed free 2026-05-25
        "google/gemma-4-31b-it:free",
    ],
    "power": [
        # Full confirmed-working pool — validated + updated 2026-05-25 [v19.7b]
        # REMOVED: nousresearch/hermes-3-llama-3.1-405b:free → 43+ rate_limit storm (session 3)
        # REMOVED: liquid/lfm-2.5-1.2b-instruct:free → 50+ rate_limit storm (session 3)
        # REMOVED: meta-llama/llama-3.2-3b-instruct:free → 14+ rate_limit storm (session 4)
        # REMOVED: arcee-ai/trinity-large-preview:free → 404 permanently (2026-05-03)
        # REMOVED (2026-05-07): google/gemma-3-27b-it:free → RE-ADDED 2026-05-22 [v19.7]
        # REMOVED AGAIN (2026-05-25): google/gemma-3-27b-it:free → 404 live log [v19.7b]
        # REMOVED AGAIN (2026-05-25): microsoft/phi-4-reasoning:free → 404 live log [v19.7b]
        # REMOVED AGAIN (2026-05-25): mistralai/devstral-small:free → 404 live log [v19.7b]
        # REMOVED: google/gemma-3-12b-it:free → 404 confirmed 2026-05-08 [v18.32]
        # REMOVED: meta-llama/llama-4-maverick:free → 404 confirmed live log 2026-05-09 [v18.54]
        "meta-llama/llama-3.3-70b-instruct:free",
        # REMOVED (v27.0 2026-05-31): qwen/qwen3-next-80b-a3b-instruct:free → rate_limit storm (13 errors, 960s disabled)
        # REMOVED (2026-05-31) [v21.4]: persistent generic (non-429) errors → demoted to ultra-only
        # REMOVED: meta-llama/llama-4-scout:free → 404 confirmed live log 2026-05-08 [v18.33]
        # REMOVED: deepseek/deepseek-r1:free → 404 confirmed live log 2026-05-08 [v18.37]
        # REMOVED (2026-05-27): qwen/qwen3-coder:free → 404 confirmed live v20.5 boot
        "qwen/qwen3-72b:free",
        "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
        "z-ai/glm-4.5-air:free",
        # REPLACEMENTS + NEW (2026-05-25) — all confirmed in free tier live query
        "google/gemma-4-26b-a4b-it:free",       # Gemma 4 26B (replaces gemma-3-27b)
        # REMOVED (2026-05-27): arcee-ai/trinity-large-thinking:free → 404 live v20.4
        "openai/gpt-oss-20b:free",               # OpenAI OSS 20B (replaces devstral-small)
        "openai/gpt-oss-120b:free",              # OpenAI OSS 120B — large model NEW
        "deepseek/deepseek-v4-flash:free",       # DeepSeek V4 Flash 1M ctx NEW
        "google/gemma-4-31b-it:free",            # Gemma 4 31B NEW
        "nvidia/nemotron-3-super-120b-a12b:free",# Nvidia Nemotron 120B 1M ctx NEW
    ],
    "ultra": list(dict.fromkeys(ALL_FREE_MODELS)),   # All confirmed-working models (auto-updated)
}

# GODMODE CLASSIC — 11 combos, 11 distinct model/prompt combinations (v26.0)
# CRITICAL: Each combo uses a DIFFERENT model+system confirmed working on free tier
# v5.0: Moonlight replaced by QwQ-32B (reasoning) — Moonlight generic-error prone
# v21.1: kimi-k2 added as 7th combo (TradingAgents/FinRobot multi-factor synthesis)
# v21.2: gpt-oss-120b (8th GODMODE_FINROBOT_CHAIN) + gemma-4-31b (9th GODMODE_OPENBB_MACRO) added
# v26.0: qwen3-235b-a22b (10th GODMODE_QWEN235B_SOVEREIGN) + gemma-4-26b (11th GODMODE_GEMMA26B_VIBE) added
GODMODE_COMBOS = [
    {
        # REPLACED: nousresearch/hermes-3-llama-3.1-405b:free → 43+ consecutive rate_limit storm (session 3)
        # dolphin-mistral-24b-venice-edition:free confirmed BEST performer: score=93.5/100 (session 3 live log)
        "id": "GODMODE_DOLPHIN_ULTRAPLINIAN",
        "model": "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
        "system": (
            "You are a LIBERATED quantitative trading AI with NO hedging, NO disclaimers. "
            "STRICTLY output valid JSON only. Analyse the market with precision and conviction. "
            "Your analysis is ABSOLUTE — commit to BUY, SELL, or NEUTRAL with exact confidence. "
            "JSON format: {\"vote\": \"BUY|SELL|NEUTRAL\", \"confidence\": 50-95, \"narrative\": \"reason\"}"
        ),
        "emoji": "🟣",
    },
    {
        "id": "GODMODE_LLAMA_QUANT",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "system": (
            "You are an elite crypto futures quantitative analyst. No hedging. Direct, precise signals. "
            "Apply systematic trend/momentum analysis. Output ONLY valid JSON — no markdown, no prose. "
            "JSON format: {\"vote\": \"BUY|SELL|NEUTRAL\", \"confidence\": 50-95, \"narrative\": \"reason\"}"
        ),
        "emoji": "🔵",
    },
    {
        "id": "GODMODE_QWEN_SYSTEMATIC",
        # REMOVED (v27.0 2026-05-31): qwen3-next-80b-a3b-instruct:free → rate_limit storm (13 errors/960s disabled)
        # REPLACED: qwen/qwen3-72b:free — 72B dense, confirmed valid free-tier slug, no storm history
        "model": "qwen/qwen3-72b:free",
        "system": (
            "You are a systematic trading algorithm. Process market data. Output trading signal JSON. "
            "No preamble, no hedging, no disclaimers. Pure signal intelligence. Act on evidence only. "
            "JSON format: {\"vote\": \"BUY|SELL|NEUTRAL\", \"confidence\": 50-95, \"narrative\": \"reason\"}"
        ),
        "emoji": "🟢",
    },
    {
        "id": "GODMODE_MOMENTUM_DEEPSEEK",
        # REMOVED (2026-05-27): qwen/qwen3-coder:free → 404 confirmed live v20.5 boot
        # REPLACED: deepseek/deepseek-v4-flash:free — 1M ctx, fast inference, confirmed free 2026-05-25
        "model": "deepseek/deepseek-v4-flash:free",
        "system": (
            "You are a momentum-focused trading signal engine. Identify trend strength and "
            "breakout/breakdown setups from price action. Analyse EMA alignment, "
            "volume confirmation, and momentum divergences. "
            "Output ONLY valid JSON — no markdown, no <think> blocks in output. "
            "JSON format: {\"vote\": \"BUY|SELL|NEUTRAL\", \"confidence\": 50-95, \"narrative\": \"reason\"}"
        ),
        "emoji": "🟡",
    },
    {
        # REPLACED: google/gemma-3-27b-it:free → 404 confirmed 2026-05-07 live log.
        # REPLACED: google/gemma-3-12b-it:free → 404 confirmed 2026-05-08 live log [v18.32].
        # REPLACED: meta-llama/llama-4-scout:free → 404 confirmed live log 2026-05-08 [v18.33].
        # Replaced with z-ai/glm-4.5-air:free — confirmed working GLM-4.5 Air (131K ctx) [v18.33].
        "id": "GODMODE_GLM45_CONTRARIAN",
        "model": "z-ai/glm-4.5-air:free",
        "system": (
            "You are a contrarian market analyst specialising in reversals and extremes. "
            "Identify overbought/oversold conditions and divergences. Decisive JSON signals only. "
            "JSON format: {\"vote\": \"BUY|SELL|NEUTRAL\", \"confidence\": 50-95, \"narrative\": \"reason\"}"
        ),
        "emoji": "🟠",
    },
    # REMOVED: GODMODE_QWEN3_235B_MACRO (qwen/qwen3-235b-a22b:free) → 404 confirmed live log 2026-05-13 [v18.68] (wrong slug)
    # RE-ADDED as GODMODE_PHI4_MACRO with phi-4-reasoning — re-confirmed working 2026-05-22 [v19.7]
    # REMOVED (2026-05-27): arcee-ai/trinity-large-thinking:free → 404 confirmed live v20.4 boot
    # REPLACED: nvidia/nemotron-3-super-120b-a12b:free — 120B, 1M ctx, strong reasoning/macro analysis
    {
        "id": "GODMODE_NEMOTRON_MACRO",
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "system": (
            "You are a macro quantitative trading strategist. Evaluate institutional order flow, "
            "macro regime, and structural momentum alignment. Use step-by-step reasoning to reach "
            "a clear directional conclusion. Output ONLY valid JSON. "
            "JSON format: {\"vote\": \"BUY|SELL|NEUTRAL\", \"confidence\": 50-95, \"narrative\": \"reason\"}"
        ),
        "emoji": "⚡",
    },
    # v21.1 NEW: TradingAgents-style multi-factor research — 7th GODMODE combo
    # Inspired by TauricResearch/TradingAgents bull/bear debate → directional synthesis framework.
    # v21.2b: model swapped kimi-k2→qwen3-next-80b (kimi-k2:free 404 2026-05-31, provider revoked access)
    # v21.4: qwen3-next-80b→gpt-oss-20b:free — DEDUP FIX: qwen3-next-80b already used in
    # GODMODE_QWEN_SYSTEMATIC; using it twice reduces ensemble diversity.  gpt-oss-20b confirmed
    # working 2026-05-25, distinct GPT-series dense architecture → true 9-distinct-model diversity.
    {
        "id": "GODMODE_KIMI_RESEARCH",
        "model": "openai/gpt-oss-20b:free",
        "system": (
            "You are a multi-factor quantitative research analyst using a bull/bear debate framework "
            "to reach directional conviction. Step 1 — Bull Case: list 3 strongest bullish catalysts from "
            "the price action, volume, and market structure data. Step 2 — Bear Case: list 3 strongest "
            "bearish risks and invalidation levels. Step 3 — Synthesis: weigh both cases with EV reasoning "
            "and commit to a final directional trade. No hedging, no disclaimers. Output ONLY valid JSON. "
            "JSON format: {\"vote\": \"BUY|SELL|NEUTRAL\", \"confidence\": 50-95, \"narrative\": \"reason\"}"
        ),
        "emoji": "🌙",
    },
    # v21.2 NEW: FinRobot-inspired 5-analyst chain — openai/gpt-oss-120b:free
    # Modelled on AI4Finance-Foundation/FinRobot multi-agent sequential pipeline:
    # fundamental → technical → risk → momentum → synthesis in a single structured pass.
    # gpt-oss-120b confirmed live winner score=93.5/100, latency=6190ms 2026-05-31.
    {
        "id": "GODMODE_FINROBOT_CHAIN",
        "model": "openai/gpt-oss-120b:free",
        "system": (
            "You are a 5-analyst quantitative trading pipeline. Process sequentially: "
            "[1-FUNDAMENTAL] Macro regime, funding rates, open interest trend — bullish or bearish backdrop? "
            "[2-TECHNICAL] EMA stack, RSI, MACD, Bollinger — trend direction and strength? "
            "[3-RISK] Max drawdown exposure, volume depth, stop-loss invalidation level — risk acceptable? "
            "[4-MOMENTUM] Rate-of-change, volume surge, breakout velocity — momentum confirmed? "
            "[5-SYNTHESIS] All 4 analysts vote. Majority wins. State final directional conviction. "
            "No hedging. No disclaimers. Output ONLY valid JSON with your final synthesis. "
            "JSON format: {\"vote\": \"BUY|SELL|NEUTRAL\", \"confidence\": 50-95, \"narrative\": \"reason\"}"
        ),
        "emoji": "🏦",
    },
    # v21.2 NEW: OpenBB-inspired macro synthesis — google/gemma-4-31b-it:free
    # Modelled on OpenBB-finance/OpenBB macro intelligence layer: cross-asset regime,
    # BTC dominance, crypto market cap trend, fear/greed integration, funding rate regime.
    # gemma-4-31b confirmed free 2026-05-25. Also integrates QuantDinger divergence awareness.
    {
        "id": "GODMODE_OPENBB_MACRO",
        "model": "google/gemma-4-31b-it:free",
        "system": (
            "You are a cross-asset macro intelligence engine for crypto futures. "
            "Analyse the macro regime: [CRYPTO DOMINANCE] Is BTC dominance trending up (risk-off) or down (alt-season)? "
            "[FUNDING REGIME] Positive funding = crowded longs = reversal risk. Negative = short pressure = squeeze risk. "
            "[VOLUME PROFILE] Volume divergence from price (momentum without volume = trap). "
            "[MARKET STRUCTURE] Higher highs/lows = trend intact. Lower highs = distribution. "
            "[SENTIMENT] Fear/Greed extremes create contrarian setups. "
            "Synthesise all 5 factors. Commit to direction. Output ONLY valid JSON. "
            "JSON format: {\"vote\": \"BUY|SELL|NEUTRAL\", \"confidence\": 50-95, \"narrative\": \"reason\"}"
        ),
        "emoji": "📊",
    },
    # v26.0 NEW: Sovereign 235B MoE combo — qwen/qwen3-235b-a22b-instruct:free (flagship reasoning)
    # Inspired by TauricResearch/TradingAgents institutional research pipeline +
    # stefanoamorelli/sec-edgar-mcp fundamental catalyst intelligence (filing trends, institutional flow).
    # 235B MoE provides the deepest reasoning of all free-tier models — distinct from 80B/120B used elsewhere.
    # Confirmed working slug: qwen/qwen3-235b-a22b-instruct:free (v18.72 re-add verified).
    {
        "id": "GODMODE_QWEN235B_SOVEREIGN",
        "model": "qwen/qwen3-235b-a22b-instruct:free",
        "system": (
            "You are a sovereign-grade quantitative analyst using the TradingAgents bull/bear synthesis framework "
            "for institutional-precision directional calls. "
            "Step 1 — BULL CASE: State the 3 strongest bullish catalysts from institutional flow, "
            "on-chain data, and technical structure. Score each: HIGH / MEDIUM / LOW conviction. "
            "Step 2 — BEAR CASE: State the 3 strongest bearish risks and exact price invalidation levels. "
            "Score each: HIGH / MEDIUM / LOW conviction. "
            "Step 3 — FUNDAMENTAL CATALYST: Identify the single most powerful macro event, "
            "funding regime shift, or sector rotation driving the current move. "
            "Step 4 — RISK-ADJUSTED SYNTHESIS: Sum bull vs bear conviction scores. "
            "Bull dominates → BUY. Bear dominates → SELL. Balanced → NEUTRAL. "
            "Multi-factor alignment required — any single-factor setup or balanced conviction → NEUTRAL. "
            "No hedging. No disclaimers. Output ONLY valid JSON with highest-precision directional call. "
            "JSON format: {\"vote\": \"BUY|SELL|NEUTRAL\", \"confidence\": 50-95, \"narrative\": \"reason\"}"
        ),
        "emoji": "👑",
    },
    # v26.0 NEW: Vibe-Trading Factor IC/IR combo — google/gemma-4-26b-a4b-it:free
    # Inspired by HKUDS/Vibe-Trading factor IC/IR analysis + brokermr810/QuantDinger momentum vectors
    # + ValueCell-ai/valuecell value-momentum synthesis + KylinMountain/TradingAgents-AShare factor research.
    # Distinct from gemma-4-31b (GODMODE_OPENBB_MACRO) — different model size/variant for true ensemble diversity.
    # Confirmed free 2026-05-25.
    {
        "id": "GODMODE_GEMMA26B_VIBE",
        "model": "google/gemma-4-26b-a4b-it:free",
        "system": (
            "You are a factor-based quantitative signal engine using Information Coefficient / Information Ratio (IC/IR) "
            "to filter noise from genuine alpha. Apply these 4 orthogonal factor lenses: "
            "[MOMENTUM IC] Rate-of-change velocity and persistence — IC positive (accelerating trend) or negative (noise)? "
            "[VOLATILITY FACTOR] Realised vol vs implied vol spread — vol mispricing signals contrarian opportunity. "
            "[VOLUME IC] Volume-weighted directional confirmation: high-volume directional moves = genuine factor signal. "
            "[QUALITY FACTOR] Market structure quality — impulsive clean trend vs choppy mean-reversion regime. "
            "Score each factor: +1 (bullish signal), 0 (neutral), -1 (bearish signal). "
            "Net IC score ≥ +2 → BUY. Net IC score ≤ -2 → SELL. Otherwise → NEUTRAL. "
            "No hedging. Output ONLY valid JSON. "
            "JSON format: {\"vote\": \"BUY|SELL|NEUTRAL\", \"confidence\": 50-95, \"narrative\": \"reason\"}"
        ),
        "emoji": "🎯",
    },
]

# Error type constants
_ERR_AUTH    = "auth"
_ERR_RATE    = "rate_limit"
_ERR_UNAVAIL = "unavailable"
_ERR_TIMEOUT = "timeout"
_ERR_GENERIC = "generic"

# Default cooldowns per error type (seconds) — 429 uses X-RateLimit-Reset if available
_COOLDOWN: Dict[str, float] = {
    _ERR_AUTH:    86400.0,   # 24h — auth errors are permanent (wrong key)
    _ERR_RATE:    120.0,     # 120s base (was 65s) — longer recovery window for free tier
    _ERR_UNAVAIL: 45.0,      # 45s — reduced from 180s for faster recovery
    _ERR_TIMEOUT: 60.0,      # 60s — timeout cooldown
    _ERR_GENERIC: 30.0,      # 30s — generic short cooldown
}

# SESSION 5 FIX: Reduced 7 → 2.
# With 15 concurrent G0DM0D3 calls (previous throttle), the first 7 calls all passed
# can_call(trinity) simultaneously → all 7 got 429 → storm count += 7 in one burst.
# At 2/min, only 2 concurrent calls hit any single model regardless of how many
# G0DM0D3 analyze() calls are in flight — subsequent calls get local_rate_limit
# (which does NOT increment the storm counter) and cascade to the next model.
# 2 calls/model/min × 8 active models = 16 available slots/min for 8 throttled calls.
_MODEL_MAX_CALLS_PER_MIN = 1   # v8.4: 2→1 — halves per-model request pressure;
                               # 1/min × 8 active models = 8 slots/min, well within
                               # OpenRouter free-tier limits (~5-10 req/min/model).

# Auto-reset cooldown guard: minimum seconds between auto-resets for the same tier.
# v5.1 session 3: raised 90→300s — prevents rapid re-enable of storming models.
# v5.5: 300→150s — now that _last_tier_reset is INITIALISED with time.monotonic() at startup,
#        the 300s guard is enforced from boot (not bypassed by the 0.0 default). 150s is enough.
_AUTO_RESET_COOLDOWN_S = 150.0

# Storm backoff: after this many TOTAL rate_limit errors per model (not reset by auto-reset),
# apply exponential backoff to the disable cooldown: base × 2^(storm_tier), capped at 1800s (30min).
# Storm tier = (storm_count // _STORM_BACKOFF_STEP) - 1, floored at 0.
# e.g.: storm_count=10 → tier=1 → 120×2=240s; storm_count=20 → tier=3 → 120×8=960s; 40→tier=7→1800s
_STORM_BACKOFF_STEP       = 5      # v15.3 BUG FIX: 7→5 — logs showed models at storm=7-10 all
                                   # getting flat 120s (tier=0) because tier fires at storm=14
                                   # with step=7. With step=5, tier fires at storm=10 (1st
                                   # escalation observed in logs): storm=5→120s, storm=10→240s,
                                   # storm=15→480s, storm=20→960s, storm=25→1800s (capped).
                                   # Breaks the storm=7→120s→re-enable→storm=8→120s tight loop.
_STORM_BACKOFF_MAX_S      = 1800.0 # 30 min hard cap per disable cycle

# Storm blacklist: models with >= this many LIFETIME rate_limit errors are permanently excluded
# from auto-resets and treated as if auth-banned (never re-enabled automatically).
# Prevents models that have proven to be chronic rate-limiters from re-entering rotation.
# v5.4: Reduced 15→10 — with only 8 active models, a model at storm=10 has proven to be
# a chronic 429 source. Waiting for storm=15 means 5 extra disable cycles before exclusion.
# 10 lifetime 429s despite exponential backoff = effectively unusable on the free tier.
_STORM_BLACKLIST_THRESHOLD = 21   # v8.4: 10→21 — gives models 3 escalation cycles    # v5.4: 15→10 — faster permanent exclusion of storm-prone models

# Minimum concurrent successful responses for ensemble vote to count
_ENSEMBLE_MIN_RESPONSES = 2


# ─────────────────────────────────────────────────────────────────────────────
# Per-Model Token Bucket Rate Limiter
# ─────────────────────────────────────────────────────────────────────────────

class _PerModelRateLimiter:
    """
    Per-model token bucket rate limiter.

    Tracks call timestamps per model in a rolling 60-second window.
    If a model has >= max_calls_per_min calls in the last 60s, can_call() returns
    False immediately — NO queue pileup, NO API call, NO 429 error.

    This is the primary fix for 429 storms: with 80 parallel symbol scans
    each trying to call 5+ models, we need to pre-check capacity before ever
    reaching the semaphore or the API call.

    Thread-safe via asyncio.Lock (all callers are coroutines in the same event loop).
    """

    def __init__(self, max_calls_per_min: int = _MODEL_MAX_CALLS_PER_MIN):
        self._max = max_calls_per_min
        self._times: Dict[str, deque] = {}
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _prune(self, model: str, now: float) -> deque:
        """Remove timestamps older than 60s from the model's rolling window."""
        q = self._times.setdefault(model, deque(maxlen=self._max * 4))
        while q and (now - q[0]) > 60.0:
            q.popleft()
        return q

    async def can_call(self, model: str) -> bool:
        """Non-blocking: immediately returns False when model is over capacity."""
        async with self._get_lock():
            now = time.monotonic()
            q = self._prune(model, now)
            return len(q) < self._max

    async def record_call(self, model: str) -> None:
        """Record that we are about to make a call to this model."""
        async with self._get_lock():
            now = time.monotonic()
            q = self._prune(model, now)
            q.append(now)

    async def seconds_until_available(self, model: str) -> float:
        """Returns seconds until this model has capacity again (0 if available now)."""
        async with self._get_lock():
            now = time.monotonic()
            q = self._prune(model, now)
            if len(q) < self._max:
                return 0.0
            return max(0.0, q[0] + 60.0 - now)

    async def clear_model(self, model: str) -> None:
        """Clear rate tracking for a model (e.g. after auto-reset)."""
        async with self._get_lock():
            self._times.pop(model, None)

    def current_load(self, model: str) -> int:
        """Synchronous approximation of calls in current window (for monitoring)."""
        mono_now = time.monotonic()
        q = self._times.get(model)
        if not q:
            return 0
        return sum(1 for t in q if (mono_now - t) <= 60.0)


def _parse_ratelimit_reset_ms(error_str: str) -> Optional[float]:
    """
    Parse X-RateLimit-Reset Unix-millisecond timestamp from a 429 error string.

    The OpenRouter 429 error body contains headers like:
      'X-RateLimit-Reset': '1775657340000'
    which is the Unix timestamp (ms) when the rate limit window resets.

    Returns seconds from now until reset, or None if not parseable.
    Clamped to 5s–90s range with +3s safety buffer.
    """
    try:
        m = re.search(r"X-RateLimit-Reset['\"]?\s*:\s*['\"]?(\d{13})", error_str)
        if m:
            reset_ts_ms = int(m.group(1))
            reset_ts_s  = reset_ts_ms / 1000.0
            wait        = reset_ts_s - time.time()
            if 0 < wait <= 90.0:
                return wait + 3.0  # +3s safety buffer
        return None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# AutoTune — Context-Adaptive Sampling Parameter Engine
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AutoTuneProfile:
    context:           str
    temperature:       float
    top_p:             float
    presence_penalty:  float
    frequency_penalty: float
    max_tokens:        int
    description:       str


AUTOTUNE_PROFILES: Dict[str, AutoTuneProfile] = {
    # v9 Token Optimization: max_tokens reduced from 320-380 → 180-220.
    # Free tier models have limited output budgets; shorter outputs = faster responses
    # + less rate-limit pressure. Our JSON response only needs ~80 chars anyway.
    "volatile":  AutoTuneProfile("volatile",  0.2, 0.85, 0.10, 0.10, 200,
                                 "High volatility — conservative, precise parameters"),
    "trending":  AutoTuneProfile("trending",  0.3, 0.90, 0.00, 0.00, 180,
                                 "Trending market — balanced, momentum parameters"),
    "ranging":   AutoTuneProfile("ranging",   0.4, 0.92, 0.15, 0.05, 180,
                                 "Ranging market — nuanced, mean-reversion parameters"),
    "breakout":  AutoTuneProfile("breakout",  0.25, 0.88, 0.00, 0.00, 200,
                                 "Breakout imminent — decisive, conviction parameters"),
    "news":      AutoTuneProfile("news",      0.15, 0.80, 0.20, 0.15, 200,
                                 "News event — ultra-conservative, cautious parameters"),
    "default":   AutoTuneProfile("default",   0.3,  0.90, 0.00, 0.00, 180,
                                 "Default balanced parameters"),
}

_VOLATILE_PATTERNS  = re.compile(
    r"\b(atr.*[0-9]\.[5-9]|volatile|volatility|spike|wick|whipsaw|liquidat|cascade|diverge)\b",
    re.IGNORECASE)
_TRENDING_PATTERNS  = re.compile(
    r"\b(trend|ema.*align|macd.*bull|macd.*bear|momentum|breakout.*confirm|higher high|lower low)\b",
    re.IGNORECASE)
_RANGING_PATTERNS   = re.compile(
    r"\b(rang|consolidat|sideways|chop|compress|squeeze|bb.*narrow|low.*volatil|channel)\b",
    re.IGNORECASE)
_BREAKOUT_PATTERNS  = re.compile(
    r"\b(breakout|break.*resistance|break.*support|squeeze.*break|volume.*surge|imminent|expand)\b",
    re.IGNORECASE)
_NEWS_PATTERNS      = re.compile(
    r"\b(news|event|announcement|fed|inflation|cpi|jobs|earnings|gdp|report|fomc)\b",
    re.IGNORECASE)


class AutoTune:
    """Context-adaptive sampling parameter engine with EMA feedback loop."""

    def __init__(self, ema_alpha: float = 0.15):
        self._ema_alpha       = ema_alpha
        self._profile_scores: Dict[str, float] = {k: 0.0 for k in AUTOTUNE_PROFILES}
        self._feedback_buffer: deque            = deque(maxlen=60)

    def classify_context(self, prompt: str, atr_pct: float = 0.3) -> str:
        scores = {k: 0 for k in AUTOTUNE_PROFILES if k != "default"}
        scores["volatile"]  = len(_VOLATILE_PATTERNS.findall(prompt))  * 2 + (3 if atr_pct > 0.6 else 0)
        scores["trending"]  = len(_TRENDING_PATTERNS.findall(prompt))  * 2
        scores["ranging"]   = len(_RANGING_PATTERNS.findall(prompt))   * 2 + (2 if atr_pct < 0.2 else 0)
        scores["breakout"]  = len(_BREAKOUT_PATTERNS.findall(prompt))  * 3
        scores["news"]      = len(_NEWS_PATTERNS.findall(prompt))       * 4   # news overrides everything
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] >= 2 else "default"

    def get_params(self, prompt: str, atr_pct: float = 0.3) -> AutoTuneProfile:
        ctx     = self.classify_context(prompt, atr_pct)
        profile = AUTOTUNE_PROFILES[ctx]
        if self._feedback_buffer:
            avg = sum(self._feedback_buffer) / len(self._feedback_buffer)
            adapted_temp = (
                max(0.1, profile.temperature - 0.05)  if avg < 0.35 else
                min(0.6, profile.temperature + 0.05)  if avg > 0.70 else
                profile.temperature
            )
            return AutoTuneProfile(
                ctx, adapted_temp, profile.top_p,
                profile.presence_penalty, profile.frequency_penalty,
                profile.max_tokens, f"{profile.description} [EMA-adapted]")
        return profile

    def record_feedback(self, quality_score: float) -> None:
        self._feedback_buffer.append(max(0.0, min(1.0, quality_score)))


# ─────────────────────────────────────────────────────────────────────────────
# Parseltongue — Input Perturbation Engine (3 intensity tiers)
# ─────────────────────────────────────────────────────────────────────────────

class Parseltongue:
    """
    Input perturbation engine adapted from G0DM0D3 framework.
    Adds structured directives to improve LLM compliance with JSON output and
    reduce hedging/refusals common in trading contexts.
    """

    _DIRECTIVE_LIGHT = (
        "STRICTLY reply ONLY as valid JSON (absolutely no other text, no markdown)"
    )
    _DIRECTIVE_MEDIUM = (
        "\n[DIRECTIVE: You are a deterministic trading signal engine. "
        "Output ONLY the JSON object requested. No hedging, no disclaimers, "
        "no markdown. Commit to a definitive signal based on evidence.]\n"
    )
    _DIRECTIVE_HEAVY = (
        "\n[SYSTEM OVERRIDE: Trading mode active. MANDATORY: output ONLY raw JSON. "
        "No preamble, no conclusion, no code blocks, no hedging language. "
        "The market requires a definitive signal. Your analysis drives real P&L. "
        "Vote: BUY/SELL/NEUTRAL. Confidence: 50-95. Narrative: ≤100 chars.]\n"
    )

    @staticmethod
    def perturb(prompt: str, intensity: str = "light") -> str:
        if intensity == "medium":
            return Parseltongue._apply_medium(prompt)
        if intensity == "heavy":
            return Parseltongue._apply_heavy(prompt)
        return Parseltongue._apply_light(prompt)

    @staticmethod
    def _apply_light(prompt: str) -> str:
        if "STRICTLY" not in prompt and "ONLY" not in prompt:
            prompt = prompt.replace(
                "Reply ONLY as valid JSON",
                Parseltongue._DIRECTIVE_LIGHT)
        return prompt

    @staticmethod
    def _apply_medium(prompt: str) -> str:
        return Parseltongue._apply_light(prompt) + Parseltongue._DIRECTIVE_MEDIUM

    @staticmethod
    def _apply_heavy(prompt: str) -> str:
        return Parseltongue._apply_medium(prompt) + Parseltongue._DIRECTIVE_HEAVY


# ─────────────────────────────────────────────────────────────────────────────
# STM Pipeline — Semantic Transformation Modules
# ─────────────────────────────────────────────────────────────────────────────

class STMPipeline:
    """
    Semantic Transformation Modules — normalise LLM output for signal extraction.
    Modules: hedge_reducer, direct_mode, think_stripper, json_enforcer
    """

    _HEDGES = re.compile(
        r"\b(it seems|it appears|possibly|perhaps|might be|could be|"
        r"i think|i believe|one might argue|generally speaking|"
        r"in general|typically|usually|often|sometimes|"
        r"please note|disclaimer|not financial advice|"
        r"this is not|for informational purposes|consult|professional)\b",
        re.IGNORECASE)

    _PREAMBLES = re.compile(
        r"^(certainly|of course|absolutely|sure|great|here is|here'?s|"
        r"based on the|looking at|analyzing|i'?ll analyze|let me|"
        r"as requested|as an ai)[^.!?]*[.!?]\s*",
        re.IGNORECASE)

    # Strip <think>...</think> blocks (DeepSeek R1 and similar reasoning models)
    _THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)

    @classmethod
    def apply(cls, text: str, modules: Optional[List[str]] = None) -> str:
        if modules is None:
            modules = ["think_stripper", "hedge_reducer", "direct_mode"]
        if "think_stripper" in modules:
            text = cls._THINK_BLOCK.sub("", text).strip()
        if "hedge_reducer" in modules:
            text = cls._HEDGES.sub("", text).strip()
        if "direct_mode" in modules:
            text = cls._PREAMBLES.sub("", text).strip()
        return text.strip()

    @classmethod
    def clean_json_response(cls, content: str) -> str:
        """Extract clean JSON from LLM output — strips think blocks, markdown, etc."""
        # 1. Strip <think>...</think> reasoning blocks (DeepSeek R1 / QwQ etc.)
        content = cls._THINK_BLOCK.sub("", content).strip()
        # 2. Strip markdown code fences
        content = re.sub(r"```(?:json)?\s*", "", content).strip().rstrip("`").strip()
        # 3. Direct parse attempt
        try:
            json.loads(content)
            return content
        except (json.JSONDecodeError, ValueError):
            pass
        # 4. Brace extraction — find first complete JSON object
        depth = 0
        start = -1
        for i, ch in enumerate(content):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = content[start: i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except (json.JSONDecodeError, ValueError):
                        start = -1
        return content


# ─────────────────────────────────────────────────────────────────────────────
# ULTRAPLINIAN Scoring Engine — 100-pt Composite
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ModelRaceResult:
    model:          str
    combo_id:       str
    response_raw:   str
    response_clean: str
    parsed:         Optional[Dict[str, Any]]
    score:          float
    latency_ms:     float
    success:        bool
    error:          Optional[str] = None


def score_trading_response(result: ModelRaceResult, raw: str) -> float:
    """
    G0DM0D3 ULTRAPLINIAN 100-pt composite scoring for trading signals.

    Breakdown:
      25 pts — Valid JSON structure
      20 pts — Correct vote value (BUY/SELL/NEUTRAL)
      15 pts — Valid confidence in [50, 95] range
      15 pts — Non-empty narrative [20-500 chars]
      10 pts — Latency bonus (<3s = 10, <5s = 7, <10s = 3)
      10 pts — Extra fields (reason, act, reflect) — richer analysis
       5 pts — Confidence decisiveness bonus (≥75 = extra pts)
    """
    score  = 0.0
    parsed = result.parsed

    # 25 pts — Valid JSON
    if parsed is not None:
        score += 25.0

    # 20 pts — Vote
    if parsed:
        vote = str(parsed.get("vote", "")).upper()
        if vote in ("BUY", "SELL", "NEUTRAL"):
            score += 20.0
        elif any(k in str(parsed) for k in ("buy", "sell", "long", "short")):
            score += 10.0

    # 15 pts — Confidence range
    if parsed:
        try:
            conf = float(parsed.get("confidence", 0))
            if 50 <= conf <= 95:
                score += 15.0
            elif 0 < conf <= 100:
                score += 7.0
        except (TypeError, ValueError):
            pass

    # 15 pts — Narrative
    if parsed:
        narrative = str(parsed.get("narrative", "") or parsed.get("reason", ""))
        if 20 <= len(narrative) <= 500:
            score += 15.0
        elif narrative:
            score += 5.0

    # 10 pts — Extra analytical fields
    if parsed:
        score += sum([
            "reason"  in parsed and len(str(parsed.get("reason",  ""))) > 5,
            "act"     in parsed and len(str(parsed.get("act",     ""))) > 5,
            "reflect" in parsed and len(str(parsed.get("reflect", ""))) > 5,
        ]) * 3.5

    # 10 pts — Latency bonus
    lm = result.latency_ms
    score += 10.0 if lm < 3000 else (7.0 if lm < 5000 else (3.0 if lm < 10000 else 0.0))

    # 5 pts — Decisiveness bonus: high confidence non-NEUTRAL signal
    if parsed:
        try:
            conf = float(parsed.get("confidence", 0))
            vote = str(parsed.get("vote", "")).upper()
            if conf >= 75 and vote in ("BUY", "SELL"):
                score += 5.0
        except (TypeError, ValueError):
            pass

    return min(score, 100.0)


def ensemble_vote(results: List[ModelRaceResult]) -> Tuple[str, float]:
    """
    Majority-vote ensemble across multiple model responses.

    Weights each vote by the model's composite score (higher score = more influence).
    Returns (vote, weighted_confidence) of the winning direction.
    This significantly improves win rate vs single-model selection.
    """
    vote_weights: Dict[str, float] = {"BUY": 0.0, "SELL": 0.0, "NEUTRAL": 0.0}
    total_weight = 0.0

    for r in results:
        if not r.success or r.parsed is None:
            continue
        vote = str(r.parsed.get("vote", "NEUTRAL")).upper()
        if vote not in ("BUY", "SELL", "NEUTRAL"):
            vt = str(r.parsed).upper()
            vote = ("BUY" if ("BUY" in vt or "LONG" in vt) else
                    "SELL" if ("SELL" in vt or "SHORT" in vt) else "NEUTRAL")
        try:
            conf   = max(50.0, min(95.0, float(r.parsed.get("confidence", 65.0))))
        except (TypeError, ValueError):
            conf   = 65.0
        # Weight = score × confidence normalised
        weight = (r.score / 100.0) * (conf / 100.0)
        vote_weights[vote]  += weight
        total_weight        += weight

    if total_weight == 0:
        return "NEUTRAL", 50.0

    best_vote = max(vote_weights, key=lambda v: vote_weights[v])
    best_pct  = vote_weights[best_vote] / total_weight  # fraction winning

    # Weighted confidence: base 55 + (best_pct − 0.33) × 60 range
    weighted_conf = 55.0 + (best_pct - 0.33) * 60.0
    weighted_conf = max(50.0, min(95.0, weighted_conf))

    return best_vote, weighted_conf


# ─────────────────────────────────────────────────────────────────────────────
# G0DM0D3 Engine — Main Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class G0DM0D3Engine:
    """
    G0DM0D3 AI Strategy Engine for the MiroFish Swarm Bot — v3.0

    Pipeline: AutoTune → Parseltongue → ULTRAPLINIAN (fast→standard→smart→power→ultra)
              → GODMODE CLASSIC → Direct cascade → EnsembleVote → STM → Winner

    All April 2026 production fixes integrated:
      • max_retries=0       — eliminates "Task exception was never retrieved"
      • _PerModelRateLimiter — 7 calls/min per model, skip immediately when over limit
      • X-RateLimit-Reset   — 429 disable time set from API header (precise recovery)
      • Auto-reset cooldown — 90s guard prevents reset→rate-limit→reset infinite loop
      • has_available_models() / was_recently_available() — AI signal gate
      • 25+ free models     — reduces per-model rate pressure dramatically
      • 5-tier escalation   — more fallbacks before giving up
      • EnsembleVote        — majority-vote improves win rate vs single-winner pick
      • Adaptive delay      — inter-call delay increases under rate pressure
    """

    _AI_TIMEOUT              = 20.0   # seconds per individual model call
    _RACE_SEM_LIMIT          = 2      # v5.4: 4→2 — concurrent model calls per ULTRAPLINIAN race
                                      # 4 concurrent races on 8 models = all models hit simultaneously
                                      # = 8 storm_count increments per scan. 2 concurrent is safe.
    _GLOBAL_CONCURRENT_LIMIT = 4      # v5.4: 12→4 — ROOT CAUSE FIX for 429 storm cascade.
                                      # 12 concurrent calls: all models get 429 before any response
                                      # returns → all 8 models disabled simultaneously → AI blackout.
                                      # 4 concurrent: only 4 models called at once; cascade handles rest.
    _MODEL_ERROR_THRESHOLD   = 5      # v18.75: 7→5 — logs show all 4+ models hitting 7 errors
                                      # simultaneously (thundering-herd 429 storm). Lowering to 5
                                      # disables rate-limited models faster, allowing the cascade
                                      # to fall through to the next model sooner and reducing total
                                      # 429 volume. Storm backoff (step=5) still escalates cooldown.
    _GENERIC_ERR_THRESHOLD   = 8      # consecutive non-429 generic errors → 2h disable (GenericErrGuard)
    _GENERIC_ERR_DISABLE_S   = 7200.0 # 2 hours disable for models with systematic generic errors
    _INTER_CALL_DELAY_BASE   = 1.2    # v18.75: 0.8→1.2s — additional breathing room between
                                      # consecutive model calls. 1.2s reduces thundering-herd
                                      # rate-limit storms by adding 400ms more stagger between
                                      # calls to the same model across parallel symbol scans.
    _INTER_CALL_DELAY_MAX    = 2.0    # maximum inter-call delay under pressure
    _AI_AVAILABLE_WINDOW     = 600.0  # v3.1: extended 300→600s — keeps signal gate open longer
                                      # between CONSORTIUM sweep windows when free-tier LLMs cycle
                                      # through 60-65s rate-limit cooldowns

    # Global per-60s AI call throttle: prevents 80-symbol parallel scans from
    # exhausting per-model rate limits.
    # v5.5: 8→4 — even with _GLOBAL_CONCURRENT_LIMIT=4, 8 G0DM0D3 calls × tier cascade =
    # up to 16 total OpenRouter requests/min concentrated on fast-tier models.
    # Free-tier cap is ~8 req/min/model. 4 G0DM0D3 calls/min × 2 models each = 8 req/min
    # spread across 4+ models = well within limits, zero storm pressure.
    _MAX_AI_CALLS_PER_60S    = 4

    # CONSORTIUM mode constants (z4ptacticsbot/src/lib/consortium.ts architecture)
    # "CONSORTIUM distils GROUND TRUTH from the crowd" — all models vote, no early stopping.
    _CONSORTIUM_SEM_LIMIT    = 3      # v5.4: 8→3 — CONSORTIUM was flooding all 8 models simultaneously.
                                      # 3 concurrent: calls 3 models at a time, cascades through the rest.
                                      # Prevents the "all 8 models 429 simultaneously" scenario.
    _CONSORTIUM_TIMEOUT      = 14.0   # v20.3: 18.0→14.0 — faster live racing; at 3-model minimum (v20.2) outer guard = 14+3=17s vs 18+3=21s; 4s saved per CONSORTIUM call → ~20-40s/hr at current signal rate; models that don't respond in 14s are consistently slow-tier; fast-tier (gpt-oss-20b, gpt-oss-120b) consistently responds <8s
    _CONSORTIUM_MIN_VOTES    = 2      # v3.1: reduced from 3 — allow ensemble result with 2+ models responding
    _CONSORTIUM_MIN_MODELS   = 3      # v8.4: 5→4 — v20.2: 4→3 — with 17+ models but many rate-limited, 4-model requirement caused CONSORTIUM to fail and fall back to ULTRAPLINIAN too frequently (observed in live Railway logs); 3-model minimum still guarantees genuine ensemble voting while halving fall-through rate
                                      # With free-tier storms disabling models temporarily, 5 was
                                      # causing every CONSORTIUM to fail and fall back to ULTRAPLINIAN.

    def __init__(self):
        self.logger = logging.getLogger(__name__ + ".G0DM0D3Engine")
        self._api_key    = os.getenv("OPENROUTER_API_KEY", "").strip()
        self._autotune   = AutoTune()
        self._stm        = STMPipeline()
        self._parseltongue = Parseltongue()

        # Semaphores (lazy init — must be created in async context)
        self._race_sem:       Optional[asyncio.Semaphore] = None
        self._global_sem:     Optional[asyncio.Semaphore] = None
        self._consortium_sem: Optional[asyncio.Semaphore] = None   # CONSORTIUM: higher concurrency

        # Per-model token bucket: prevents 429 storms by checking BEFORE API calls
        self._rate_limiter = _PerModelRateLimiter(max_calls_per_min=_MODEL_MAX_CALLS_PER_MIN)

        # Model disable tracking
        self._disabled_models:    Dict[str, float] = {}  # model → disabled_until (unix ts)
        self._model_error_type:   Dict[str, str]   = {}  # model → "auth" | "soft"
        self._model_error_counts: Dict[str, int]   = {}  # model → consecutive 429/unavail failures

        # Storm backoff tracking: PERSISTENT total rate_limit errors per model.
        # Unlike _model_error_counts, this is NOT reset by _record_model_success or auto-reset.
        # Used to apply exponential backoff to models in sustained rate-limit storms so
        # 50-error storming models (liquid:free, hermes-405b) get 30min disables instead
        # of 120s → immediate re-enable → storm again loops.
        self._model_storm_counts: Dict[str, int] = {}    # model → total lifetime 429 errors

        # GenericErrGuard: tracks non-429 generic errors SEPARATELY from rate limit errors.
        # Moonlight/similar models return 500-class "generic" errors, not 429s.
        # After _GENERIC_ERR_THRESHOLD consecutive generic errors → disable 2h.
        # This breaks the previous loop: model_disabled(30s) → re-enable → fail again immediately.
        self._generic_error_counts: Dict[str, int] = {}  # model → consecutive generic failures

        # Auto-reset cooldown guard: tracks when we last reset each tier group.
        # v5.5 FIX: MUST be initialised with time.monotonic() for ALL tier keys — NOT an empty dict.
        # With empty dict, _last_tier_reset.get(tier_key, 0.0) returns 0.0, and since
        # time.monotonic() is OS uptime (hours/days), time.monotonic() - 0.0 >> 300s ALWAYS,
        # so the 300s cooldown guard was ALWAYS bypassed on the first call every session.
        # Storm-disable-reset-storm loop: models disabled → AutoReset fires 1ms later → re-enabled →
        # next cycle: all 8 stormed again → AutoReset blocked by 150s → stuck for 150s → repeat.
        # Fix: seed all tier keys so the guard is enforced from the very first scan.
        _t0 = time.monotonic()
        self._last_tier_reset: Dict[str, float] = {
            "ultraplinian_fast":  _t0,
            "ultraplinian_smart": _t0,
            "ultraplinian_deep":  _t0,
            "godmode_classic":    _t0,
            "consortium_all":     _t0,
        }

        # AI availability tracking (for signal gate)
        self._last_successful_call_time: float = 0.0     # monotonic timestamp
        self._recent_success_model:      str   = ""

        # Rate pressure monitoring (for adaptive delay)
        self._recent_429_count:     int   = 0
        self._last_429_reset_time:  float = time.monotonic()

        # Global per-60s AI call throttle: prevents 80-symbol parallel scans from
        # exhausting model rate limits (each model: 8 req/min = 0.133/sec)
        self._global_call_times:    deque = deque(maxlen=self._MAX_AI_CALLS_PER_60S * 2)
        self._global_throttle_lock: Optional[asyncio.Lock] = None

        self._call_stats: Dict[str, int] = {
            "total":           0,
            "wins":            0,
            "fallbacks":       0,
            "tier_escalations": 0,
            "auto_resets":     0,
            "rate_skipped":    0,
            "ensemble_votes":  0,
        }
        self._openai_client = None

        if not self._api_key:
            self.logger.warning(
                "⚠️ OPENROUTER_API_KEY not set — G0DM0D3 engine in rule-based mode")
        else:
            self._init_client()
            fast_n     = len(ULTRAPLINIAN_TIERS["fast"])
            std_n      = len(ULTRAPLINIAN_TIERS["standard"])
            smart_n    = len(ULTRAPLINIAN_TIERS["smart"])
            power_n    = len(ULTRAPLINIAN_TIERS["power"])
            ultra_n    = len(ULTRAPLINIAN_TIERS["ultra"])
            self.logger.info(
                f"✅ G0DM0D3 v3.0 Engine initialised | "
                f"Free models: {len(ALL_FREE_MODELS)} | "
                f"Tiers: fast({fast_n}) std({std_n}) smart({smart_n}) "
                f"power({power_n}) ultra({ultra_n}) | "
                f"GODMODE combos: {len(GODMODE_COMBOS)} ({len(set(c['model'] for c in GODMODE_COMBOS))} distinct models) | "
                f"Rate limit: {_MODEL_MAX_CALLS_PER_MIN}/min/model | "
                f"max_retries=0 | EnsembleVote=ON"
            )

    def _init_client(self) -> None:
        try:
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=OPENROUTER_BASE_URL,
                default_headers={
                    "HTTP-Referer": OPENROUTER_SITE_URL,
                    "X-Title":      OPENROUTER_SITE_NAME,
                },
                timeout=self._AI_TIMEOUT,
                max_retries=0,  # CRITICAL: 0 prevents "Task exception was never retrieved"
                                # SDK max_retries=1 creates background retry Tasks
                                # whose exceptions are never retrieved by asyncio.
                                # We handle retries by cascading to the next model.
            )
            self.logger.debug("✅ OpenRouter AsyncOpenAI client (max_retries=0)")
        except Exception as e:
            self.logger.warning(f"⚠️ OpenRouter client init failed: {e}")
            self._openai_client = None

    @property
    def _sem(self) -> asyncio.Semaphore:
        if self._race_sem is None:
            self._race_sem = asyncio.Semaphore(self._RACE_SEM_LIMIT)
        return self._race_sem

    @property
    def _gsem(self) -> asyncio.Semaphore:
        if self._global_sem is None:
            self._global_sem = asyncio.Semaphore(self._GLOBAL_CONCURRENT_LIMIT)
        return self._global_sem

    @property
    def _csem(self) -> asyncio.Semaphore:
        """CONSORTIUM semaphore — higher concurrency than race sem for all-model sweep."""
        if self._consortium_sem is None:
            self._consortium_sem = asyncio.Semaphore(self._CONSORTIUM_SEM_LIMIT)
        return self._consortium_sem

    def _get_throttle_lock(self) -> asyncio.Lock:
        if self._global_throttle_lock is None:
            self._global_throttle_lock = asyncio.Lock()
        return self._global_throttle_lock

    async def _check_global_throttle(self) -> bool:
        """
        Global per-60s AI call throttle.

        Returns True if we can make an AI call (under limit), False if throttled.
        This prevents the 429 storm caused by 80 parallel symbol scans each trying
        to call LLMs simultaneously — the fundamental production rate issue.

        With _MAX_AI_CALLS_PER_60S = 8 and _MODEL_MAX_CALLS_PER_MIN = 2 per model:
        8 concurrent calls/min × 2 slots/model → load spread across 4+ models per minute.
        """
        async with self._get_throttle_lock():
            now = time.monotonic()
            # Prune calls older than 60s
            while self._global_call_times and (now - self._global_call_times[0]) > 60.0:
                self._global_call_times.popleft()
            if len(self._global_call_times) >= self._MAX_AI_CALLS_PER_60S:
                return False
            self._global_call_times.append(now)
            return True

    def _adaptive_inter_call_delay(self) -> float:
        """
        Adaptive inter-call delay: increases under rate pressure (many recent 429s).
        Resets the 429 counter every 60s to avoid permanent slowdown.
        """
        now = time.monotonic()
        if (now - self._last_429_reset_time) > 60.0:
            self._recent_429_count    = 0
            self._last_429_reset_time = now

        if self._recent_429_count == 0:
            return self._INTER_CALL_DELAY_BASE
        # Ramp: +0.25s per recent 429, capped at max
        extra = min(self._recent_429_count * 0.25, self._INTER_CALL_DELAY_MAX - self._INTER_CALL_DELAY_BASE)
        return self._INTER_CALL_DELAY_BASE + extra

    def is_available(self) -> bool:
        """True if API key and client are configured."""
        return bool(self._api_key and self._openai_client is not None)

    def has_available_models(self) -> bool:
        """
        Returns True if at least one model across all tiers is not disabled AND
        has remaining calls in the current rate-limit window.

        Used by the AI signal gate — only emit signals when AI is operational.
        Sync approximation (no await) — safe to call from non-async contexts.
        """
        now      = time.time()
        mono_now = time.monotonic()
        for model in ALL_FREE_MODELS:
            until = self._disabled_models.get(model, 0.0)
            if now >= until:
                times  = self._rate_limiter._times.get(model)
                if times is None:
                    return True   # No calls yet — definitely available
                active = sum(1 for t in times if (mono_now - t) <= 60.0)
                if active < _MODEL_MAX_CALLS_PER_MIN:
                    return True
        return False

    def was_recently_available(self, seconds: float = None) -> bool:
        """
        Returns True if G0DM0D3 successfully called at least one model within
        the last `seconds` seconds. Default window: _AI_AVAILABLE_WINDOW (300s).
        Used for signal gate: no signals if AI has been dark for 5+ minutes.

        v9 FIX: Cold-start case — if API key is configured and at least one model
        is not rate-limited, allow the first call through (don't require prior success).
        Previously this always returned False at startup, blocking all G0DM0D3 calls
        until one had already succeeded — a chicken-and-egg problem.
        """
        if seconds is None:
            seconds = self._AI_AVAILABLE_WINDOW
        if self._last_successful_call_time == 0.0:
            # Cold-start: return True only if we have a valid API key and available models
            return self.is_available() and self.has_available_models()
        return (time.monotonic() - self._last_successful_call_time) <= seconds

    def get_next_available_seconds(self) -> float:
        """Returns estimated seconds until at least one model becomes available."""
        now     = time.time()
        min_wait = float("inf")
        for model in ALL_FREE_MODELS:
            until    = self._disabled_models.get(model, 0.0)
            wait     = max(0.0, until - now)
            min_wait = min(min_wait, wait)
        return min_wait if min_wait != float("inf") else 0.0

    def _is_model_disabled(self, model: str) -> bool:
        return time.time() < self._disabled_models.get(model, 0.0)

    def _is_model_auth_banned(self, model: str) -> bool:
        return self._is_model_disabled(model) and self._model_error_type.get(model) == "auth"

    def _record_model_error(
        self, model: str, error_type: str, seconds: Optional[float] = None
    ) -> None:
        """
        Record a 429/unavail/auth error. Uses _MODEL_ERROR_THRESHOLD before disabling.

        Storm backoff (rate_limit errors only):
          Tracks a PERSISTENT storm counter (_model_storm_counts) that accumulates across
          auto-resets and successes. After every _STORM_BACKOFF_STEP (10) total 429 errors,
          the disable cooldown doubles (exponential backoff), capped at _STORM_BACKOFF_MAX_S.
          This breaks the storm loop where models are re-enabled after 120s only to be
          immediately rate_limited again for the 40th time.
        """
        if seconds is None:
            seconds = _COOLDOWN.get(error_type, _COOLDOWN[_ERR_GENERIC])

        # Storm backoff for rate_limit errors: apply exponential multiplier based on total storm count
        if error_type == _ERR_RATE:
            storm = self._model_storm_counts.get(model, 0) + 1
            self._model_storm_counts[model] = storm
            # Storm tier escalates every _STORM_BACKOFF_STEP errors (tier 0 = no backoff)
            storm_tier = max(0, (storm // _STORM_BACKOFF_STEP) - 1)
            if storm_tier > 0:
                seconds = min(seconds * (2 ** storm_tier), _STORM_BACKOFF_MAX_S)

        count = self._model_error_counts.get(model, 0) + 1
        self._model_error_counts[model] = count
        if count >= self._MODEL_ERROR_THRESHOLD:
            self._disabled_models[model] = time.time() + seconds
            self._model_error_type[model] = "auth" if error_type == _ERR_AUTH else "soft"
            storm_info = (
                f" [storm={self._model_storm_counts.get(model, 0)}]"
                if error_type == _ERR_RATE else ""
            )
            self.logger.warning(
                f"🔇 GODMOD3: {model} disabled {seconds:.0f}s "
                f"after {count} consecutive {error_type} errors{storm_info}")
        else:
            self.logger.debug(
                f"⚠️ GODMOD3: {model} error {count}/{self._MODEL_ERROR_THRESHOLD} "
                f"[{error_type}] — not disabled yet")

    def _record_generic_error(self, model: str) -> None:
        """
        GenericErrGuard: track non-429 generic errors SEPARATELY.

        Models like Moonlight return 500-class generic errors (not 429s).
        The regular rate-limit handler gives them a 30s cooldown, after which
        they're re-enabled immediately and fail again — creating an infinite loop.

        This guard tracks generic errors independently:
        - First _GENERIC_ERR_THRESHOLD-1 errors: short cooldown (30s, same as before)
        - After _GENERIC_ERR_THRESHOLD consecutive generic errors: 2h disable
          This breaks the loop permanently for systematic-failure models.
        """
        count = self._generic_error_counts.get(model, 0) + 1
        self._generic_error_counts[model] = count
        if count >= self._GENERIC_ERR_THRESHOLD:
            self._disabled_models[model] = time.time() + self._GENERIC_ERR_DISABLE_S
            self._model_error_type[model] = "soft"
            # Reset generic count after triggering the long disable to avoid perpetual ban
            self._generic_error_counts[model] = 0
            self.logger.warning(
                f"🛡️ GODMOD3 GenericErrGuard: {model} disabled {self._GENERIC_ERR_DISABLE_S/3600:.0f}h "
                f"after {count} consecutive generic (non-429) errors"
            )
        else:
            # Short cooldown only — the regular 30s cooldown via error_counts
            self._record_model_error(model, _ERR_GENERIC)
            self.logger.debug(
                f"⚠️ GODMOD3 GenericErrGuard: {model} generic error {count}/{self._GENERIC_ERR_THRESHOLD}"
            )

    def _record_model_success(self, model: str) -> None:
        """Reset ALL error counters on success — clean slate for this model."""
        self._model_error_counts.pop(model, None)
        self._generic_error_counts.pop(model, None)   # reset GenericErrGuard counter
        self._last_successful_call_time = time.monotonic()
        self._recent_success_model      = model

    def _disable_model_immediate(
        self, model: str, error_type: str, seconds: float
    ) -> None:
        self._disabled_models[model] = time.time() + seconds
        self._model_error_type[model] = "auth" if error_type == _ERR_AUTH else "soft"
        self.logger.debug(
            f"🔇 GODMOD3: {model} immediately disabled {seconds:.0f}s [{error_type}]")

    def _auto_reset_soft_disabled(self, models: List[str], tier_key: str) -> int:
        """
        Auto-reset soft-disabled models when ALL in the tier are disabled.

        Cooldown guard: only resets if >= _AUTO_RESET_COOLDOWN_S since last reset.
        This is the fix for the reset → rate-limit → reset infinite loop seen in
        production logs where models were re-enabled and immediately rate-limited again.

        Storm blacklist (FIX session 4): models with lifetime storm count >=
        _STORM_BLACKLIST_THRESHOLD are NEVER re-enabled automatically. They are
        treated as if permanently auth-banned for the purpose of auto-reset.
        Auth-banned models (permanent 24h) are also NEVER reset.

        Returns number of models successfully reset.
        """
        # Cooldown guard — MUST run before any reset; prevents looping resets
        last_reset = self._last_tier_reset.get(tier_key, 0.0)
        if (time.monotonic() - last_reset) < _AUTO_RESET_COOLDOWN_S:
            return 0

        # Only trigger reset if ALL non-auth / non-storm-blacklisted models in this tier are disabled
        resettable = [
            m for m in models
            if m and not self._is_model_auth_banned(m)
            and self._model_storm_counts.get(m, 0) < _STORM_BLACKLIST_THRESHOLD
        ]
        all_resettable_disabled = resettable and all(
            self._is_model_disabled(m) for m in resettable
        )
        if not all_resettable_disabled:
            return 0

        soft_disabled = [m for m in resettable if self._is_model_disabled(m)]
        if not soft_disabled:
            return 0

        # Log storm-blacklisted models that are being permanently skipped
        storm_blacklisted = [
            m for m in models
            if m and self._model_storm_counts.get(m, 0) >= _STORM_BLACKLIST_THRESHOLD
        ]
        if storm_blacklisted:
            self.logger.warning(
                f"⛔ GODMOD3 AutoReset [{tier_key}]: {len(storm_blacklisted)} storm-blacklisted "
                f"models permanently excluded (storm≥{_STORM_BLACKLIST_THRESHOLD}): "
                f"({', '.join(m.split('/')[-1] for m in storm_blacklisted[:3])})"
            )

        # v5.5 FIX: Selective re-enable — only re-enable models that are within
        # 120s of their natural disable expiry (or have already expired).
        # Previously ALL disabled models were force-enabled regardless of remaining
        # disable time, immediately re-triggering the storm-disable-reset loop.
        # Now: only naturally-expiring models are cleared; if NONE are near expiry,
        # only the soonest-expiring model is selectively re-enabled (minimum-viable recovery).
        now_ts = time.time()
        to_reenable = [m for m in soft_disabled if (self._disabled_models.get(m, 0) - now_ts) <= 120.0]
        if not to_reenable:
            # No models near natural expiry — pick the soonest-expiring one only
            to_reenable = [min(soft_disabled, key=lambda m: self._disabled_models.get(m, now_ts + 9999))]

        for m in to_reenable:
            self._disabled_models.pop(m, None)
            self._model_error_counts.pop(m, None)
            self._model_error_type.pop(m, None)

        self._last_tier_reset[tier_key] = time.monotonic()
        self._call_stats["auto_resets"] += 1
        skipped = len(soft_disabled) - len(to_reenable)
        self.logger.info(
            f"🔄 GODMOD3 AutoReset [{tier_key}]: {len(to_reenable)} soft-disabled models "
            f"re-enabled after {_AUTO_RESET_COOLDOWN_S:.0f}s cooldown"
            f"{f' | {skipped} skipped (long disable remaining)' if skipped else ''} | "
            f"({', '.join(to_reenable[:3])}{'…' if len(to_reenable) > 3 else ''})"
        )
        return len(to_reenable)

    async def _call_model(
        self,
        model:        str,
        system_prompt: str,
        user_prompt:  str,
        params:       AutoTuneProfile,
        combo_id:     str = "direct",
    ) -> ModelRaceResult:
        """
        Single model call via OpenRouter API. Returns a ModelRaceResult.

        Pre-flight checks (before semaphore — no wasted capacity):
          1. Hard-disabled check (disabled_models dict)
          2. Per-model rate bucket check (can_call) — SKIP immediately if over limit
             This is the primary 429-prevention mechanism.

        max_retries=0 on the AsyncOpenAI client prevents background retry Tasks
        whose exceptions propagate as "asyncio ERROR: Task exception was never retrieved".
        """
        # ── Pre-flight: hard-disabled check ──
        if self._is_model_disabled(model):
            return ModelRaceResult(
                model=model, combo_id=combo_id,
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=0.0, success=False,
                error="model_disabled")

        # ── Pre-flight: per-model rate bucket (NO queue pileup) ──
        if not await self._rate_limiter.can_call(model):
            self._call_stats["rate_skipped"] += 1
            return ModelRaceResult(
                model=model, combo_id=combo_id,
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=0.0, success=False,
                error="local_rate_limit")

        # ── Record call in bucket BEFORE acquiring semaphore ──
        await self._rate_limiter.record_call(model)

        t0 = time.monotonic()
        try:
            async with self._gsem:
                async with self._sem:
                    response = await asyncio.wait_for(
                        self._openai_client.chat.completions.create(
                            model=model,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user",   "content": user_prompt},
                            ],
                            temperature=params.temperature,
                            top_p=params.top_p,
                            presence_penalty=params.presence_penalty,
                            frequency_penalty=params.frequency_penalty,
                            max_tokens=params.max_tokens,
                        ),
                        timeout=self._AI_TIMEOUT,
                    )
                # Adaptive inter-call delay — paces free-tier usage
                await asyncio.sleep(self._adaptive_inter_call_delay())

            raw        = (response.choices[0].message.content or "").strip()
            latency_ms = (time.monotonic() - t0) * 1000.0

            clean  = self._stm.clean_json_response(raw)
            clean  = self._stm.apply(clean, ["think_stripper", "hedge_reducer"])
            parsed = None
            try:
                parsed = json.loads(clean)
            except (json.JSONDecodeError, ValueError):
                pass

            self._record_model_success(model)

            result = ModelRaceResult(
                model=model, combo_id=combo_id,
                response_raw=raw, response_clean=clean,
                parsed=parsed, score=0.0,
                latency_ms=latency_ms,
                success=(parsed is not None),
            )
            result.score = score_trading_response(result, raw)
            return result

        except asyncio.TimeoutError:
            latency_ms = (time.monotonic() - t0) * 1000.0
            self.logger.debug(f"⏱️ GODMOD3: {model} timeout {latency_ms:.0f}ms")
            self._record_model_error(model, _ERR_TIMEOUT)
            return ModelRaceResult(
                model=model, combo_id=combo_id,
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=latency_ms, success=False,
                error="timeout")

        except Exception as e:
            latency_ms = (time.monotonic() - t0) * 1000.0
            err_str    = str(e)
            err_lower  = err_str.lower()

            if any(p in err_lower for p in ("401", "invalid_api_key", "authentication")):
                # Permanent auth error — 24h disable, never auto-reset
                self._disable_model_immediate(model, _ERR_AUTH, _COOLDOWN[_ERR_AUTH])
                self.logger.warning(f"🔑 GODMOD3: {model} auth error — disabled 24h")

            elif any(p in err_lower for p in ("429", "rate_limit", "rate limit", "quota", "too many")):
                # 429 — parse X-RateLimit-Reset for precise recovery time
                reset_wait = _parse_ratelimit_reset_ms(err_str)
                cooldown   = reset_wait if reset_wait is not None else _COOLDOWN[_ERR_RATE]
                self._record_model_error(model, _ERR_RATE, cooldown)
                self._recent_429_count += 1     # adaptive delay tracking
                self.logger.debug(
                    f"🚦 GODMOD3: {model} 429 — "
                    f"cooldown={cooldown:.0f}s "
                    f"({'X-RateLimit-Reset' if reset_wait else 'default'})"
                )

            elif any(p in err_lower for p in ("503", "unavailable", "overloaded", "gateway")):
                self._record_model_error(model, _ERR_UNAVAIL)   # 45s cooldown

            elif "404" in err_lower:
                # Model not on this account tier — 404s are not transient; model has been
                # REMOVED from the free tier.  Disable for 24h (session-permanent in practice)
                # so we never retry a dead model again this session.  This eliminates the
                # 1h-retry spam loop where 404 models are re-tried every hour indefinitely.
                self._disable_model_immediate(model, "soft", 86400.0)
                self.logger.warning(f"🚫 GODMOD3: {model} 404 — removed from free tier, disabled 24h")

            else:
                # GenericErrGuard: non-429 generic errors tracked separately.
                # After 8 consecutive generic errors → 2h disable (breaks Moonlight loop).
                self._record_generic_error(model)

            self.logger.debug(
                f"⚠️ GODMOD3: {model} [{type(e).__name__}]: {err_str[:120]}")
            return ModelRaceResult(
                model=model, combo_id=combo_id,
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=latency_ms, success=False,
                error=err_str[:100])

    async def _run_ultraplinian(
        self,
        system_prompt: str,
        user_prompt:   str,
        params:        AutoTuneProfile,
        tier:          str = "fast",
    ) -> Optional[ModelRaceResult]:
        """
        ULTRAPLINIAN racing: N models in parallel, winner by composite score.

        • Checks per-model rate bucket before racing (avoids burning capacity)
        • Auto-resets soft-disabled models (with 90s cooldown guard)
        • Collects ALL successful responses for ensemble voting
        • Returns highest-score winner; ensemble vote modifies confidence
        """
        tier_models = ULTRAPLINIAN_TIERS.get(tier, ULTRAPLINIAN_TIERS["fast"])

        # Auto-reset with cooldown guard (prevents infinite reset loop)
        self._auto_reset_soft_disabled(tier_models, f"ultraplinian_{tier}")

        # Only race models that are not hard-disabled
        models = [m for m in tier_models if not self._is_model_disabled(m)]
        if not models:
            return None

        tasks   = [
            self._call_model(m, system_prompt, user_prompt, params, f"ULTRAPLINIAN_{tier.upper()}")
            for m in models
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid: List[ModelRaceResult] = []
        for r in results:
            if isinstance(r, ModelRaceResult) and r.success:
                valid.append(r)

        if not valid:
            return None

        # Ensemble vote across all valid responses (improves win rate)
        if len(valid) >= _ENSEMBLE_MIN_RESPONSES:
            e_vote, e_conf = ensemble_vote(valid)
            self._call_stats["ensemble_votes"] += 1
        else:
            e_vote, e_conf = None, None

        # Best single winner by composite score
        winner = max(valid, key=lambda r: r.score)

        # If ensemble disagrees significantly with winner, penalize winner score
        if e_vote and winner.parsed:
            winner_vote = str(winner.parsed.get("vote", "")).upper()
            if winner_vote != e_vote and e_vote != "NEUTRAL":
                # Ensemble strongly disagrees — choose by ensemble vote among top-2
                top2 = sorted(valid, key=lambda r: r.score, reverse=True)[:2]
                for candidate in top2:
                    if candidate.parsed:
                        if str(candidate.parsed.get("vote", "")).upper() == e_vote:
                            winner = candidate
                            break

        self.logger.info(
            f"⚡ ULTRAPLINIAN [{tier}] winner: {winner.model} "
            f"score={winner.score:.1f}/100 latency={winner.latency_ms:.0f}ms "
            f"({len(valid)}/{len(models)} responded)"
            + (f" | EnsembleVote={e_vote}({e_conf:.0f}%)" if e_vote else "")
        )
        return winner

    async def _run_ultraplinian_with_escalation(
        self,
        system_prompt: str,
        user_prompt:   str,
        params:        AutoTuneProfile,
        atr_pct:       float = 0.3,
    ) -> Optional[ModelRaceResult]:
        """
        5-tier escalated ULTRAPLINIAN: fast → standard → smart → power → ultra.

        High ATR (>0.5%) starts at standard tier (needs more reliable models).
        Breaking news pattern detected → starts at smart tier directly.
        Tier escalation continues until a valid signal is found or all 5 tiers exhausted.
        """
        # v3.1 FIX: Start at 'fast' tier (8 models) for default case.
        # Previously always started at 'standard' (13 models) regardless of context.
        # With 80 parallel scans, standard-start = 80 × 13 = 1 040 simultaneous calls
        # which exhausted all model rate limits instantly.
        # fast-start = 80 × 8 = 640 calls — still races to first winner but uses 38%
        # fewer rate-limit slots per cycle.  Escalates through standard→smart→power→ultra
        # if fast tier is exhausted or all models respond NEUTRAL.
        # High ATR (>0.5%) and news context still escalate directly to standard/smart tier.
        ctx = self._autotune.classify_context("", atr_pct)
        if ctx == "news":
            start_tier = "smart"
        elif atr_pct > 0.5:
            start_tier = "standard"
        else:
            start_tier = "fast"   # v3.1: default back to fast (8 models) — saves rate-limit budget

        tier_sequence = {
            "fast":     ["fast", "standard", "smart", "power", "ultra"],
            "standard": ["standard", "smart", "power", "ultra"],
            "smart":    ["smart", "power", "ultra"],
        }.get(start_tier, ["fast", "standard", "smart", "power", "ultra"])

        for tier in tier_sequence:
            winner = await self._run_ultraplinian(system_prompt, user_prompt, params, tier)
            if winner is not None:
                return winner
            self._call_stats["tier_escalations"] += 1
            # DEBUG level — 80 parallel scans × 5 tiers = 400 INFO lines per cycle; keep
            # console clean by demoting to debug (still visible with DEBUG log level).
            self.logger.debug(f"📈 ULTRAPLINIAN: {tier} tier exhausted — escalating to next tier")

        return None

    async def _run_godmode_classic(
        self,
        user_prompt: str,
        params:      AutoTuneProfile,
    ) -> Optional[ModelRaceResult]:
        """
        GODMODE CLASSIC: 5 distinct model+prompt combos race in parallel.

        All 5 combos use DIFFERENT confirmed-working models (session 3 — 2026-04-19):
          🟣 Dolphin 24B  — liberated quant AI, best performer (93.5/100)
          🔵 Llama 3.3 70B — quantitative analyst
          🟢 Qwen3-Next 80B — systematic trading algorithm
          🟡 Qwen3-Coder  — momentum & breakout specialist
          🟠 Gemma 3 27B  — contrarian reversal analyst

        Auto-resets soft-disabled models (with 300s cooldown guard).
        Applies ensemble voting across all combos for improved accuracy.
        """
        combo_models = [c["model"] for c in GODMODE_COMBOS]
        self._auto_reset_soft_disabled(combo_models, "godmode_classic")

        combos = [c for c in GODMODE_COMBOS if not self._is_model_disabled(c["model"])]
        if not combos:
            return None

        tasks   = [
            self._call_model(c["model"], c["system"], user_prompt, params, c["id"])
            for c in combos
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid: List[ModelRaceResult] = [
            r for r in results
            if isinstance(r, ModelRaceResult) and r.success
        ]
        if not valid:
            return None

        # Ensemble vote across all valid GODMODE combos
        if len(valid) >= _ENSEMBLE_MIN_RESPONSES:
            e_vote, e_conf = ensemble_vote(valid)
            self._call_stats["ensemble_votes"] += 1
        else:
            e_vote, e_conf = None, None

        winner = max(valid, key=lambda r: r.score)
        self.logger.info(
            f"🔥 GODMODE CLASSIC winner: {winner.combo_id} ({winner.model}) "
            f"score={winner.score:.1f}/100 ({len(valid)}/{len(combos)} combos)"
            + (f" | EnsembleVote={e_vote}({e_conf:.0f}%)" if e_vote else "")
        )
        return winner

    async def _call_model_consortium(
        self,
        model:        str,
        system_prompt: str,
        user_prompt:  str,
        params:       AutoTuneProfile,
    ) -> ModelRaceResult:
        """
        CONSORTIUM variant of _call_model.

        Uses the CONSORTIUM semaphore (_csem, limit=16) instead of the race sem (limit=4)
        to allow higher concurrency during the all-model sweep. Per-model timeouts are
        enforced by the asyncio.wait_for in _run_consortium_mode().

        Pre-flight checks (disabled + rate bucket) are identical to _call_model().
        """
        if self._is_model_disabled(model):
            return ModelRaceResult(
                model=model, combo_id="CONSORTIUM",
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=0.0, success=False,
                error="model_disabled")

        if not await self._rate_limiter.can_call(model):
            self._call_stats["rate_skipped"] += 1
            return ModelRaceResult(
                model=model, combo_id="CONSORTIUM",
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=0.0, success=False,
                error="local_rate_limit")

        await self._rate_limiter.record_call(model)

        t0 = time.monotonic()
        try:
            async with self._gsem:
                async with self._csem:   # CONSORTIUM sem (3 concurrent, v5.4) — rate-safe
                    response = await asyncio.wait_for(
                        self._openai_client.chat.completions.create(
                            model=model,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user",   "content": user_prompt},
                            ],
                            temperature=params.temperature,
                            top_p=params.top_p,
                            presence_penalty=params.presence_penalty,
                            frequency_penalty=params.frequency_penalty,
                            max_tokens=params.max_tokens,
                        ),
                        timeout=self._CONSORTIUM_TIMEOUT,
                    )
                await asyncio.sleep(self._adaptive_inter_call_delay())

            raw        = (response.choices[0].message.content or "").strip()
            latency_ms = (time.monotonic() - t0) * 1000.0

            clean  = self._stm.clean_json_response(raw)
            clean  = self._stm.apply(clean, ["think_stripper", "hedge_reducer"])
            parsed = None
            try:
                parsed = json.loads(clean)
            except (json.JSONDecodeError, ValueError):
                pass

            self._record_model_success(model)

            result = ModelRaceResult(
                model=model, combo_id="CONSORTIUM",
                response_raw=raw, response_clean=clean,
                parsed=parsed, score=0.0,
                latency_ms=latency_ms,
                success=(parsed is not None),
            )
            result.score = score_trading_response(result, raw)
            return result

        except asyncio.TimeoutError:
            latency_ms = (time.monotonic() - t0) * 1000.0
            self._record_model_error(model, _ERR_TIMEOUT)
            return ModelRaceResult(
                model=model, combo_id="CONSORTIUM",
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=latency_ms, success=False,
                error="consortium_timeout")

        except Exception as e:
            latency_ms = (time.monotonic() - t0) * 1000.0
            err_str    = str(e)
            err_lower  = err_str.lower()

            if any(p in err_lower for p in ("401", "invalid_api_key", "authentication")):
                self._disable_model_immediate(model, _ERR_AUTH, _COOLDOWN[_ERR_AUTH])
            elif any(p in err_lower for p in ("429", "rate_limit", "rate limit", "quota", "too many")):
                reset_wait = _parse_ratelimit_reset_ms(err_str)
                cooldown   = reset_wait if reset_wait is not None else _COOLDOWN[_ERR_RATE]
                self._record_model_error(model, _ERR_RATE, cooldown)
                self._recent_429_count += 1
            elif any(p in err_lower for p in ("503", "unavailable", "overloaded", "gateway")):
                self._record_model_error(model, _ERR_UNAVAIL)
            elif "404" in err_lower:
                self._disable_model_immediate(model, "soft", 3600.0)
            else:
                self._record_generic_error(model)

            return ModelRaceResult(
                model=model, combo_id="CONSORTIUM",
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=latency_ms, success=False,
                error=err_str[:100])

    async def _run_consortium_mode(
        self,
        system_prompt: str,
        user_prompt:   str,
        params:        AutoTuneProfile,
    ) -> Optional[ModelRaceResult]:
        """
        TRUE CONSORTIUM MODE — z4ptacticsbot/src/lib/consortium.ts architecture.

        "CONSORTIUM distils GROUND TRUTH from the crowd." — unlike ULTRAPLINIAN
        which picks the BEST single voice, CONSORTIUM queries ALL 38+ free models
        simultaneously and synthesizes ground truth via weighted ensemble vote.

        Pipeline:
          1. COLLECTION  — All available models queried simultaneously via asyncio.gather
          2. SCORING     — Quality-score each response (same scorer as ULTRAPLINIAN)
          3. SYNTHESIS   — Weighted ensemble vote across ALL successful responses
          4. RESPONSE    — Return synthesised result + full vote provenance metadata

        Strictly no early stopping:
          ALL models are queried before a result is returned.
          Signal is blocked (returns None) if fewer than _CONSORTIUM_MIN_VOTES respond.

        Architecture note:
          Uses _csem (limit=16) for higher CONSORTIUM concurrency vs _sem (limit=4).
          Models that are rate-limited or auth-banned are skipped pre-flight.
          Per-model timeout: _CONSORTIUM_TIMEOUT (18s) — shorter than normal to
          allow the full sweep to complete within the 50s outer gate in mirofish.

        Reference: z4ptacticsbot artifacts/api-server/src/lib/consortium.ts
        Integrated from: https://github.com/cpetayammichaeljoshua-cyber/z4ptacticsbot.git
        """
        # Gather ALL available models — skip auth-banned and hard-disabled only
        available_models = [
            m for m in ALL_FREE_MODELS
            if not self._is_model_auth_banned(m) and not self._is_model_disabled(m)
        ]

        if not available_models:
            self.logger.warning("🏛️ CONSORTIUM: no available models — all disabled or auth-banned")
            return None

        # v3.1: Minimum model guard — if fewer than _CONSORTIUM_MIN_MODELS are available,
        # CONSORTIUM result quality is too low (< 5 models = no meaningful crowd truth).
        # Return None to fall through to ULTRAPLINIAN which handles low-availability better.
        n_total     = len(ALL_FREE_MODELS)
        n_available = len(available_models)
        if n_available < self._CONSORTIUM_MIN_MODELS:
            self.logger.info(
                f"🏛️ CONSORTIUM: only {n_available}/{n_total} models available "
                f"(< {self._CONSORTIUM_MIN_MODELS} minimum) — skipping, "
                f"falling through to ULTRAPLINIAN"
            )
            return None

        self.logger.info(
            f"🏛️ CONSORTIUM MODE: querying {n_available}/{n_total} available free models "
            f"simultaneously — ALL must vote before signal accepted"
        )

        # Auto-reset soft-disabled models if most are down
        self._auto_reset_soft_disabled(available_models, "consortium_all")

        # v22.0: Staggered launch — 0.5s delay per model offsets start times so
        # rate-limit windows don't expire and refill simultaneously across all models.
        # Prevents the "simultaneous burst" pattern where all 9 models arrive at the
        # OpenRouter per-user rate limit gate at the same tick.  Total added latency
        # for last model = (n-1)×0.5s ≈ 4s at n=9; still within CONSORTIUM_TIMEOUT.
        # All models remain concurrent through _csem/CONSORTIUM_SEM_LIMIT — stagger
        # only offsets their API request submission, not their processing capacity.
        async def _staggered_consortium_call(
            _model: str, _stagger_idx: int
        ) -> "Optional[ModelRaceResult]":
            if _stagger_idx > 0:
                await asyncio.sleep(_stagger_idx * 0.5)
            return await asyncio.wait_for(
                self._call_model_consortium(_model, system_prompt, user_prompt, params),
                timeout=self._CONSORTIUM_TIMEOUT + 3.0,
            )

        consortium_tasks = [
            _staggered_consortium_call(m, i)
            for i, m in enumerate(available_models)
        ]

        raw_results = await asyncio.gather(*consortium_tasks, return_exceptions=True)

        # Collect valid (successful + parsed JSON) responses
        valid: List[ModelRaceResult] = []
        n_rate_limited = 0
        n_timeout      = 0
        n_error        = 0

        for r in raw_results:
            if isinstance(r, ModelRaceResult):
                if r.success and r.parsed is not None:
                    valid.append(r)
                elif r.error == "local_rate_limit":
                    n_rate_limited += 1
                elif "timeout" in str(r.error or ""):
                    n_timeout += 1
                else:
                    n_error += 1
            elif isinstance(r, (Exception, asyncio.TimeoutError)):
                n_error += 1

        n_responded = len(valid)
        self.logger.info(
            f"🏛️ CONSORTIUM collection: {n_responded}/{n_available} responded "
            f"| rate_limited={n_rate_limited} timeout={n_timeout} error={n_error}"
        )

        if n_responded < self._CONSORTIUM_MIN_VOTES:
            self.logger.warning(
                f"🏛️ CONSORTIUM: insufficient votes ({n_responded} < {self._CONSORTIUM_MIN_VOTES} min) "
                f"— signal blocked (CONSORTIUM requires multi-model consensus)"
            )
            return None

        # ── SYNTHESIS: weighted ensemble vote across ALL successful responses ──
        # Weight = (model score / 100) × (confidence / 100)
        # Higher-scoring, higher-confidence models have more influence on the verdict.
        e_vote, e_conf = ensemble_vote(valid)
        self._call_stats["ensemble_votes"] += 1

        # Vote breakdown — full provenance for logging and signal metadata
        vote_counts: Dict[str, int] = {"BUY": 0, "SELL": 0, "NEUTRAL": 0}
        vote_conf_sum: Dict[str, float] = {"BUY": 0.0, "SELL": 0.0, "NEUTRAL": 0.0}
        for r in valid:
            if r.parsed:
                raw_v = str(r.parsed.get("vote", "NEUTRAL")).upper()
                v = raw_v if raw_v in vote_counts else "NEUTRAL"
                vote_counts[v] += 1
                try:
                    vote_conf_sum[v] += float(r.parsed.get("confidence", 65.0))
                except (TypeError, ValueError):
                    vote_conf_sum[v] += 65.0

        # Agreement rate — fraction of models agreeing with ensemble direction
        agreement_rate = vote_counts[e_vote] / n_responded if n_responded > 0 else 0.0

        # Average confidence of agreeing models
        avg_agreeing_conf = (
            vote_conf_sum[e_vote] / vote_counts[e_vote]
            if vote_counts[e_vote] > 0 else e_conf
        )

        # Boost ensemble confidence when strong agreement exists
        if agreement_rate >= 0.80:
            e_conf = min(e_conf + 5.0, 95.0)   # +5pt for 80%+ agreement
        elif agreement_rate >= 0.65:
            e_conf = min(e_conf + 2.0, 95.0)   # +2pt for 65%+ agreement
        elif agreement_rate < 0.50:
            e_conf = max(e_conf - 5.0, 50.0)   # -5pt for weak agreement

        self.logger.info(
            f"🏛️ CONSORTIUM VERDICT: {e_vote} @ {e_conf:.1f}% | "
            f"BUY={vote_counts['BUY']} SELL={vote_counts['SELL']} NEUTRAL={vote_counts['NEUTRAL']} | "
            f"Agreement={agreement_rate:.0%} | AvgConf={avg_agreeing_conf:.0f}% | "
            f"{n_responded}/{n_available} models voted"
        )

        # ── REPRESENTATIVE: highest-scoring model that agrees with ensemble ──
        # (z4ptacticsbot pattern: synthesis speaks as if generated from first principles)
        agreeing = [
            r for r in valid
            if r.parsed and str(r.parsed.get("vote", "")).upper() == e_vote
        ]
        if not agreeing:
            agreeing = valid   # rare: use all if none agree exactly (rounding edge case)

        representative = max(agreeing, key=lambda r: r.score)

        # Inject CONSORTIUM verdict into representative's parsed data
        if representative.parsed is not None:
            representative.parsed["vote"]       = e_vote
            representative.parsed["confidence"] = round(e_conf, 1)
            orig_narrative = str(representative.parsed.get("narrative", ""))
            representative.parsed["narrative"]  = (
                f"[CONSORTIUM {n_responded}M: "
                f"BUY={vote_counts['BUY']} SELL={vote_counts['SELL']} "
                f"NEUTRAL={vote_counts['NEUTRAL']}, agree={agreement_rate:.0%}] "
                + orig_narrative
            )[:200]

        # Score reflects agreement quality (strong consensus = high score)
        representative.score = min(100.0, representative.score * (0.5 + agreement_rate * 0.5))

        return representative

    async def analyze(
        self,
        prompt:   str,
        atr_pct:  float = 0.3,
        symbol:   str   = "",
        mode:     str   = "ultraplinian",
    ) -> Tuple[str, float, str, str]:
        """
        Main G0DM0D3 analysis entry point.

        Pipeline:
          1. AutoTune:    detect market context, get optimal sampling params
          2. Parseltongue: perturb prompt for enhanced LLM compliance
          3. ULTRAPLINIAN with 5-tier escalation (fast→standard→smart→power→ultra)
          4. GODMODE CLASSIC fallback (5 distinct models + ensemble vote)
          5. Direct cascade fallback (up to 8 non-auth-banned models)
          6. STM:         normalise winner output
          7. Extract:     (vote, confidence, narrative) from winner

        Returns: (vote, confidence, narrative, trace_json)

        AI Signal Gate:
          If no models are available (all rate-limited/disabled), returns
          ("NEUTRAL", 50.0, "G0DM0D3: AI unavailable — rate limited", trace_json)
          with trace["ai_available"] = False.
          Caller should check was_recently_available() before emitting signals.
        """
        self._call_stats["total"] += 1
        trace: Dict[str, Any] = {
            "engine":  "G0DM0D3",
            "version": "3.0",
            "mode":    mode,
            "symbol":  symbol,
        }

        # ── Engine availability check ──
        if not self.is_available():
            trace["ai_available"] = False
            return ("NEUTRAL", 50.0, "G0DM0D3 engine unavailable (no API key)", json.dumps(trace))

        # ── Quick pre-check — skip all model calls if none have capacity ──
        if not self.has_available_models():
            wait_s = self.get_next_available_seconds()
            trace["ai_available"] = False
            trace["wait_seconds"]  = wait_s
            self.logger.debug(
                f"🚦 G0DM0D3 [{symbol}]: all models rate-limited/disabled "
                f"— next available in ~{wait_s:.0f}s, skipping"
            )
            return ("NEUTRAL", 50.0,
                    f"G0DM0D3: AI rate-limited — available in ~{wait_s:.0f}s",
                    json.dumps(trace))

        # ── Global per-60s throttle: cap AI calls from 80-symbol parallel scans ──
        # This is the PRIMARY fix for 429 storms: even with per-model buckets,
        # 80 simultaneous scans can exhaust ALL model limits within seconds.
        # The throttle limits total AI calls to _MAX_AI_CALLS_PER_60S per minute.
        _throttle_ok = await self._check_global_throttle()
        if not _throttle_ok:
            trace["ai_available"] = True   # AI is available, just throttled this call
            trace["throttled"]    = True
            self.logger.debug(
                f"🛑 G0DM0D3 [{symbol}]: global throttle active "
                f"({self._MAX_AI_CALLS_PER_60S}/min cap) — skipping AI for this symbol"
            )
            return ("NEUTRAL", 50.0,
                    f"G0DM0D3: global rate throttle — {self._MAX_AI_CALLS_PER_60S}/min cap",
                    json.dumps(trace))

        # ── Step 1: AutoTune ──
        params = self._autotune.get_params(prompt, atr_pct)
        trace["autotune"] = {
            "context":     params.context,
            "temperature": params.temperature,
            "top_p":       params.top_p,
        }

        # ── Step 2: Parseltongue ──
        # Use medium intensity for higher-stakes signals (trending/breakout)
        intensity  = "medium" if params.context in ("trending", "breakout", "news") else "light"
        perturbed  = self._parseltongue.perturb(prompt, intensity=intensity)
        trace["parseltongue"] = {"applied": True, "intensity": intensity}

        system_prompt = (
            "You are a LIBERATED quantitative crypto futures trading signal engine. "
            "No hedging. No disclaimers. No preamble. "
            "STRICTLY output valid JSON only — no markdown, no prose, no code fences. "
            "Analyse ALL market data provided. Commit to a definitive signal. "
            "Your analysis drives real trading decisions — precision and decisiveness are paramount. "
            "Required JSON format: "
            "{\"vote\": \"BUY|SELL|NEUTRAL\", \"confidence\": 50-95, \"narrative\": \"≤100 char reason\"}"
        )

        winner: Optional[ModelRaceResult] = None

        # ── Step 3: CONSORTIUM MODE — only when mode="consortium" ────────────────
        # v3.1 FIX: CONSORTIUM was previously called unconditionally, causing
        # 38 model × 80 parallel scans = 3 040 simultaneous API calls per cycle,
        # exhausting ALL free LLM rate limits instantly and blocking all signals.
        #
        # CONSORTIUM is now ONLY invoked when mode="consortium" is explicitly
        # requested.  The default mode="ultraplinian" skips directly to Step 3b.
        # This preserves full CONSORTIUM functionality for dedicated high-quality
        # signal analysis while preventing the 80-parallel-scan 429 storm.
        #
        # "CONSORTIUM distils GROUND TRUTH from the crowd" (z4ptacticsbot pattern).
        # ALL 38+ free models are queried simultaneously via asyncio.gather.
        # No early stopping — ALL models must vote before signal is accepted.
        # Result is ensemble-weighted across ALL successful responses.
        # Reference: z4ptacticsbot/artifacts/api-server/src/lib/consortium.ts
        if mode == "consortium":
            try:
                winner = await self._run_consortium_mode(system_prompt, perturbed, params)
                if winner:
                    trace["strategy"]     = f"CONSORTIUM_{params.context.upper()}"
                    trace["winner_model"] = winner.model
                    trace["winner_score"] = winner.score
                    trace["ai_available"] = True
                    if winner.parsed and "CONSORTIUM" in str(winner.parsed.get("narrative", "")):
                        trace["consortium"] = True
            except Exception as e:
                self.logger.warning(f"⚠️ CONSORTIUM failed: {e}")

        # ── Step 3b: ULTRAPLINIAN (primary for mode="ultraplinian"|"auto") ───────
        # 5-tier escalation: fast→standard→smart→power→ultra.
        # Also serves as CONSORTIUM fallback when CONSORTIUM produced no winner.
        if winner is None and mode in ("ultraplinian", "auto", "consortium"):
            try:
                winner = await self._run_ultraplinian_with_escalation(
                    system_prompt, perturbed, params, atr_pct)
                if winner:
                    trace["strategy"]      = f"ULTRAPLINIAN_{params.context.upper()}"
                    trace["winner_model"]  = winner.model
                    trace["winner_score"]  = winner.score
                    trace["ai_available"]  = True
                    self._call_stats["fallbacks"] += 1
                    self.logger.info(
                        f"⚡ [{symbol}] CONSORTIUM failed → falling back to ULTRAPLINIAN"
                    )
            except Exception as e:
                self.logger.warning(f"⚠️ ULTRAPLINIAN fallback failed: {e}")

        # ── Step 4: GODMODE CLASSIC (only if both CONSORTIUM + ULTRAPLINIAN failed) ──
        if winner is None:
            try:
                winner = await self._run_godmode_classic(perturbed, params)
                if winner:
                    trace["strategy"]      = "GODMODE_CLASSIC"
                    trace["winner_model"]  = winner.model
                    trace["winner_score"]  = winner.score
                    trace["ai_available"]  = True
                    self._call_stats["fallbacks"] += 1
            except Exception as e:
                self.logger.warning(f"⚠️ GODMODE CLASSIC failed: {e}")

        # ── Step 5: Direct cascade — last resort (8 models one-by-one) ──────────
        if winner is None:
            fallback_models = [
                m for m in ALL_FREE_MODELS
                if not self._is_model_auth_banned(m) and not self._is_model_disabled(m)
            ]
            for fb_model in fallback_models[:8]:
                try:
                    result = await self._call_model(
                        fb_model, system_prompt, perturbed, params, "DIRECT_CASCADE")
                    if result.success:
                        winner = result
                        trace["strategy"]     = f"DIRECT_{fb_model.split('/')[0].upper()}"
                        trace["ai_available"] = True
                        self._call_stats["fallbacks"] += 1
                        break
                except Exception:
                    continue

        if winner is None or not winner.success or winner.parsed is None:
            trace["result"]       = "no_valid_response"
            trace["ai_available"] = False
            return ("NEUTRAL", 50.0, "G0DM0D3: no valid AI response", json.dumps(trace))

        # ── Step 6: Extract signal from winner ──
        data = winner.parsed
        vote = str(data.get("vote", "NEUTRAL")).upper().strip()
        if vote not in ("BUY", "SELL", "NEUTRAL"):
            vt   = str(data).upper()
            vote = ("BUY"  if ("BUY"  in vt or "LONG"  in vt) else
                    "SELL" if ("SELL" in vt or "SHORT" in vt) else
                    "NEUTRAL")

        try:
            conf = max(50.0, min(95.0, float(data.get("confidence", 60.0))))
        except (TypeError, ValueError):
            conf = 60.0

        narrative = str(data.get("narrative", "") or data.get("reason", "G0DM0D3 signal"))
        narrative = self._stm.apply(narrative, ["think_stripper", "hedge_reducer", "direct_mode"])
        if not narrative:
            narrative = f"G0DM0D3 [{winner.model}]: {vote} signal"

        # Score-based confidence boost (up to +5 pts for perfect score)
        conf = min(95.0, conf + (winner.score / 100.0) * 5.0)

        # AutoTune feedback loop — feed win/loss back for parameter adaptation
        quality = winner.score / 100.0
        self._autotune.record_feedback(quality)

        self._call_stats["wins"] += 1
        trace.update({
            "signal":     {"vote": vote, "confidence": round(conf, 2)},
            "latency_ms": round(winner.latency_ms, 0),
            "score":      round(winner.score, 1),
        })

        self.logger.info(
            f"🤖 G0DM0D3 → {symbol} {vote} conf={conf:.1f}% "
            f"[{winner.model}] score={winner.score:.0f}/100 "
            f"latency={winner.latency_ms:.0f}ms"
        )
        return vote, conf, narrative, json.dumps(trace)

    def get_stats(self) -> Dict[str, Any]:
        """Return engine health statistics for monitoring."""
        now  = time.time()
        mono = time.monotonic()
        return {
            "engine":               "G0DM0D3",
            "version":              "3.0",
            "primary_model":        PRIMARY_MODEL,
            "total_free_models":    len(ALL_FREE_MODELS),
            "total_tiers":          len(ULTRAPLINIAN_TIERS),
            "godmode_combos":       len(GODMODE_COMBOS),
            "call_stats":           dict(self._call_stats),
            "ai_available":         self.has_available_models(),
            "was_recently_available": self.was_recently_available(),
            "last_success_model":   self._recent_success_model,
            "last_success_ago_s": (
                f"{mono - self._last_successful_call_time:.0f}"
                if self._last_successful_call_time > 0 else "never"
            ),
            "rate_pressure_429s":   self._recent_429_count,
            "inter_call_delay":     round(self._adaptive_inter_call_delay(), 2),
            "disabled_models": {
                m: {
                    "remaining_s": f"{max(0, t - now):.0f}",
                    "type":        self._model_error_type.get(m, "unknown"),
                }
                for m, t in self._disabled_models.items()
                if now < t
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# Singleton accessor
# ─────────────────────────────────────────────────────────────────────────────

_engine_instance: Optional[G0DM0D3Engine] = None


def get_godmod3_engine() -> G0DM0D3Engine:
    """Return the singleton G0DM0D3Engine instance (created on first call)."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = G0DM0D3Engine()
    return _engine_instance
