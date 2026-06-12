---
name: Unity Engine v86.0 live-recovery fixes
description: Critical production fixes from Railway live log analysis — perm-disable storm, G4 static cap deadlock, and 3 storm-prone GODMODE models replaced.
---

# Unity Engine v86.0 — Live-Recovery Fixes

## Root cause (Railway live log, WR=29.4%, EV=−0.314R, Sharpe=−4.870, MaxDD=49.37%)

### Problem 1: OpenRouter backbone perm-disabled too fast
- `_GENERIC_ERR_THRESHOLD = 5` caused qwen3-72b + qwen3-235b to be perm_disabled after only 5 errors during a single storm cycle
- Gut the CONSORTIUM from 8 healthy to 3/8 healthy in one session
- **Fix**: 5→8 (still fast for true 404s, survives transient bursts)
- `_GENERIC_ERR_DISABLE_S = 7200` (2h) kept backbone models out for entire trading sessions
- **Fix**: 7200→3600 (1h matches OpenRouter free-tier refresh cadence)

### Problem 2: G4 static hard cap permanently blocked all signals at WR=29.4%
- `_g4_hard_cap = 0.52` was static regardless of session WR
- NN trained on 29% WR data physically cannot produce outputs >0.44 for genuine winners at that WR regime
- Static 0.52 cap → G4 was #1 gate bottleneck, 0% pass rate → dead-zone deadlock
- **Fix**: WR-adaptive cap in `start_unity_engine.py` G4 hard-cap block:
  - WR < 25%: cap = 0.44 (ultra-crisis, NN max ≈ 0.35–0.40)
  - WR < 28%: cap = 0.46 (deep-crisis, NN max ≈ 0.40–0.44)
  - WR ≥ 28%: cap = 0.52 (standard institutional cap, unchanged from v67.0)
  - untrained sentinel: cap = 0.50 (unchanged — crisis tightening on sentinel is nonsense)
- Session WR read from `self._booster._win_ring` (min 20 samples required, else defaults to 0.50)

### Problem 3: 3 GODMODE models stuck in permanent storm/unavailable cycle
- `nvidia/nemotron-3-super-120b-a12b:free` → storm=10 rate_limit EVERY cycle (240s disable recurring)
- `z-ai/glm-4.5-air:free` → 7+ consecutive "unavailable" (model offline/restricted, not rate_limit)
- `google/gemma-4-31b-it:free` → storm=10 rate_limit EVERY cycle

**Replacements (all confirmed stable):**
- GODMODE_GLM45_CONTRARIAN (glm-4.5-air) → **GODMODE_GPT20B_CONTRARIAN** (`openai/gpt-oss-20b:free`)
  - Contrarian personality preserved in system prompt (3-step reversal framework)
- GODMODE_NEMOTRON_MACRO (nemotron) → **GODMODE_GPT120B_MACRO** (`openai/gpt-oss-120b:free`)
  - 3-layer macro regime framework (REGIME+FLOW+ALIGNMENT) in system prompt
- GODMODE_OPENBB_MACRO (gemma-4-31b) → model changed to `meta-llama/llama-3.3-70b-instruct:free`
  - OpenBB 6-layer macro system prompt preserved; distinct from GODMODE_LLAMA_QUANT (trend/momentum)

**Removed from ALL tier dicts** (TIER2, TIER3, workhorse, smart, power):
- `nvidia/nemotron-3-super-120b-a12b:free`
- `z-ai/glm-4.5-air:free`
- `google/gemma-4-31b-it:free`

**Promoted to TIER2** (from TIER3, to fill the gap):
- `cognitivecomputations/dolphin-mistral-24b-venice-edition:free`
- `google/gemma-4-26b-a4b-it:free`

## Banner fixes
- Two stale "48-gate" banners → "54-gate" (lines ~15825 and ~15864 in start_unity_engine.py)
- Gate 10 boot banner: "48-GATE SIGNAL FILTER" → "54-GATE SIGNAL FILTER"

## Why: durable lessons
- **Static G4 hard cap at 0.52 is unreachable when WR < 28%.** Always make the cap WR-adaptive or signals will permanently deadlock when the NN calibrates to a crisis regime.
- **5 generic errors is too tight for free-tier perm-disable.** Storm bursts routinely produce 5+ generic errors in one scan cycle. 8 is the correct balance.
- **1h perm-disable TTL** matches free-tier recovery window. 2h loses backbone models for entire sessions after a single storm.
- **nemotron and gemma-4-31b are storm-prone.** Confirmed storm=10 (max backoff) every cycle. Remove them permanently.
- **z-ai/glm-4.5-air:free is intermittently unavailable.** "Unavailable" errors (not rate_limit) mean the model is offline — distinct from storm. Remove permanently.
