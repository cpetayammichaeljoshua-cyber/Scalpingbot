---
name: Unity Engine v98.0 critical LLM gate fix
description: Root cause and fix for AI Signal Gate blocking 100% of signals in v97.0 due to has_available_models() rate-limiter false negative
---

# v98.0 Critical LLM Gate Fix

## Root Cause
`has_available_models()` in `godmod3_strategy.py` checked per-minute rate-limiter bucket usage:
```python
active = sum(1 for t in times if (mono_now - t) <= 60.0)
if active < _MODEL_MAX_CALLS_PER_MIN:  # _MODEL_MAX_CALLS_PER_MIN was 1
    return True
```
With `_MODEL_MAX_CALLS_PER_MIN=1` and 80 parallel symbol scans, every model accumulated ≥1 call within the first 60 seconds → `has_available_models()` returned False for ALL models → AI Signal Gate blocked 100% of signals even though OpenRouter was responding normally.

"Model unavailable" (storm/perm-disabled/cooldown) ≠ "rate limited this call" — these were conflated.

## Fixes Applied

### 1. `has_available_models()` — only checks genuine disable status (not rate limits)
```python
for model in ALL_FREE_MODELS:
    if model in self._session_perm_disabled:
        if now < self._disabled_models.get(model, 0.0):
            continue   # still in 2h disable
    elif now < self._disabled_models.get(model, 0.0):
        continue       # in storm cooldown
    return True        # at least one non-disabled model
return False
```

### 2. `_MODEL_MAX_CALLS_PER_MIN` 1→3
- 1/min filled immediately in parallel scan
- 3/min × 9 models = 27 slots/min; within free-tier cap

### 3. `_MAX_AI_CALLS_PER_60S` 4→8
- 4/min throttled 94% of signals in 80-symbol scan
- 8/min gives meaningful coverage

### 4. `was_recently_available()` — 120s boot-grace
Added `self._init_monotonic = time.monotonic()` in `__init__`. Within 120s of boot, treats engine as available (prevents blocking during GODMODE warm-up before first success is recorded).

## Files Changed
- `SignalMaestro/godmod3_strategy.py` — has_available_models(), was_recently_available(), _init_monotonic, rate limit constants
- `start_unity_engine.py` — UNITY_VERSION 97.0→98.0
- `nixpacks.toml` — header v92.0→v98.0, verify strings v86.0→v98.0
- `Dockerfile` — header/label/verify v83.0/v92.0→v98.0

## Verification
v98.0 boot log shows:
- `UNITY ENGINE v98.0` in console
- Zero "AI Signal Gate BLOCKED" messages (was blocking every cycle in v97.0)
- `Signal sent: ZECUSDT BUY` on first scan cycle
- `G0DM0D3+OpenRouter calls=40 sr=100%`

## Why
Rate-limiting is a per-call flow-control concern (handled by `can_call()`). The AI gate availability check should only reflect whether models are genuinely offline (storm-blacklisted, perm-disabled, or in 2h cooldown). Conflating these two concepts caused the gate to falsely see "no AI" during normal operation.
