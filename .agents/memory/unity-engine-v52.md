---
name: Unity Engine v52.0 Railway + OpenRouter fixes
description: .dockerignore DB glob gap (32MB slipping through); OpenRouter storm/generic-err thresholds raised; G3 F&G relief expanded.
---

## 1. .dockerignore root-level patterns do NOT match subdirectories

Docker's `.dockerignore` treats bare patterns (e.g. `advanced_ml_trading.db`) as root-relative only — they do NOT match `SignalMaestro/advanced_ml_trading.db` (32MB).

**Fix:** Added `**/*.db`, `**/*.db-shm`, `**/*.db-wal` glob patterns.

**How to apply:** Any time a large file (>1MB) is excluded in `.dockerignore` by a root-level pattern, also add a `**/<filename>` or `**/*.<ext>` glob to cover subdirectories.

## 2. _STORM_BLACKLIST_THRESHOLD in godmod3_strategy.py

- Location: `SignalMaestro/godmod3_strategy.py`, module-level constant (around line 608)
- **Changed:** 21 → 30
- **Why:** A 45-min Railway 429 storm with 10 active GODMODE combos can accumulate 21+ lifetime 429 errors per model in a single session, permanently disabling good models. 30 requires 6 full exponential-backoff escalation cycles before permanent exclusion.

## 3. _GENERIC_ERR_THRESHOLD in godmod3_strategy.py

- Location: `SignalMaestro/godmod3_strategy.py`, class-level constant in `GodmodeStrategy` (around line 1091)
- **Changed:** 8 → 12
- **Why:** Brief Railway infra events can cause 8 consecutive 503/timeout errors from healthy OpenRouter models, triggering the 2h GenericErrGuard disable unfairly. 12 requires a systematic failure pattern.

## 4. G3 F&G regime relief expansion

- Location: `start_unity_engine.py`, `UnitySignalFilter.apply()` Gate 3 block (around line 6173)
- **Changed:** `_g3_fg < 30.0` → `_g3_fg < 35.0`; `_g3_fg > 70.0` → `_g3_fg > 65.0`
- **Why:** F&G 31-35 (moderate fear) and 65-69 (moderate greed) still carry directional momentum bias. The 88-89% AI confidence band retains positive EV when regime-aligned in these zones.
- **Effect:** ~+4-6% more regime-aligned signals pass G3. Counter-regime signals unchanged.

## 5. GODMODE slot 4 and 12 status (v52.0)

Both slots remain EMPTY. All 10 confirmed-working free-tier OpenRouter models are already in the active GODMODE_COMBOS. Adding unverified models caused a 13-error rate_limit storm (qwen3-next incident). Do NOT fill slots without confirmed live-session validation.

**Why:** The pattern of "add model → 404 boot → 13-error storm → 960s disabled" has happened multiple times. Conservation over diversity.
