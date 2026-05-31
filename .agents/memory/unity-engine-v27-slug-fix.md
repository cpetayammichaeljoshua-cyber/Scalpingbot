---
name: Unity Engine v27.0 slug fix
description: qwen3-next-80b-a3b-instruct:free is a nonexistent model causing rate-limit storms; fix and replacement for future reference
---

## The Rule
Never use `qwen/qwen3-next-80b-a3b-instruct:free` — it is not a real Qwen3 model and causes rate-limit storms.

## Why
Railway log 2026-04-21 15:09:11 confirmed 13 consecutive rate_limit errors → model disabled 960s, storm=28 accumulated errors. The Qwen3 model lineup (QwenLM/Qwen3) has NO "80B-a3b" variant. Official sizes: 0.6B/1.7B/4B/8B/14B/32B dense + 30B-a3b MoE + 235B-a22b MoE. The "next-80b-a3b-instruct" slug was a speculative/placeholder name that never shipped.

## How to apply
Replacement is `qwen/qwen3-72b:free` (72B dense, confirmed valid free-tier slug, already in MODEL_COSTS since v19.3). Applied in: `godmod3_strategy.py` (GODMODE_COMBOS GODMODE_QWEN_SYSTEMATIC + TIER1 + ULTRAPLINIAN_TIERS standard/smart/power), `smart_llm_router.py` (MODEL_COSTS entry removed — qwen3-72b already present; _FREE_SIMPLE and _FREE_REASONING slot removed). Version bumped to 27.0 in `start_unity_engine.py`, `Dockerfile` LABEL, and `requirements.txt`.
