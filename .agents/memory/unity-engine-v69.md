---
name: Unity Engine v69.0 upgrades
description: v69.0 signal-flow recovery — G6 fear gate, fear penalty recalibration, OpenRouter recovery, Kelly Step 30
---

# Unity Engine v69.0 — Signal Flow Recovery

## Root causes fixed (from live console analysis)
- WR=29.3%, EV=-0.314R, MaxDD=49.37%, Sharpe=-4.870, IRONS calls=0, CONSORTIUM always failing

## Changes

### 1. G6 Fear Gate hard-block 20→10 (start_unity_engine.py ~line 7020)
- **Was**: `if fg <= 20 and direction == "BUY": return False` — blocked ALL BUY at F&G=12
- **Now**: `if fg <= 10 → hard block`; F&G 10-20 BUY → `-3.0 quality_score pts` (soft penalty)
- **Why**: F&G=12 in live operation was blocking every BUY candidate before IRONS/NN/GEX could evaluate. IRONS_AIScorer calls=0 was a consequence — no signals survived to reach Gate 10.
- Symmetric: hard block SELL moved from F&G≥85 to F&G≥90; F&G 80-90 SELL → -3pt soft penalty

### 2. Fear penalty reduction (SignalMaestro/fxsusdt_telegram_bot.py ~line 1934)
- **Was**: F&G<13→-15pt, F&G 13-15→-10pt, F&G 15-20→-5pt
- **Now**: F&G<13→-8pt, F&G 13-15→-5pt, F&G 15-20→-3pt
- **Why**: -15pt at F&G=12 dropped conf to 64%; pre-skip check (64+15max_boost=79 < 89% threshold) suppressed the signal before NN/IRONS could evaluate. -8pt lands at ~71% → max_boost 15pt → ~86% (closer to clearing).

### 3. OpenRouter session_perm_disabled recovery (SignalMaestro/godmod3_strategy.py ~line 1440)
- **Was**: `if model in _session_perm_disabled: return True` — permanent for entire session
- **Now**: check if `_disabled_models[model]` timer has also expired; if yes → discard from set + log ♻️
- **Why**: v66.0 added permanent session disable after 12 generic errors. With F&G=12+market stress, all free-tier models (qwen3-72b, qwen3-235b, claude-fable-5, claude-mythos-5, glm-4.5) hit generic errors simultaneously → all permanently disabled → CONSORTIUM always fails → only ULTRAPLINIAN single-model. The fix re-enables models after the 2h timer expires naturally.

### 4. _ERR_GENERIC cooldown 30→90s (SignalMaestro/godmod3_strategy.py line ~636)
- **Was**: `_ERR_GENERIC: 30.0` — fast retry storm
- **Now**: `_ERR_GENERIC: 90.0` — 3× longer breathing room between retries
- **Why**: 30s meant models were re-enabled every 30s, failing again immediately, accumulating toward the 12-error permanent disable threshold very quickly.

### 5. Kelly Step 30 — MaxDD Ultra-Ruin Intermediate Brake (start_unity_engine.py after Step 29)
- **Triggers**: MaxDD > 48.0%
- **DD 48-50%**: hard cap 0.15% (was 0.4% at Step 28 47.5%+)
- **DD > 50%**: hard cap 0.05% (micro-sizing preservation mode)
- **Why**: Live MaxDD=49.37% was in the critical band where Step 28 (47.5%→×0.25) fires but the absolute cap was still ~0.4%, allowing meaningful compounding. Step 30 catches the 48-50% band explicitly.
- Stacks multiplicatively after Steps 28+29.

## Files changed
- `start_unity_engine.py`: UNITY_VERSION 68→69, G6 gate, Kelly Step 30, all banners/KEY GATES
- `SignalMaestro/fxsusdt_telegram_bot.py`: fear penalty 15/10/5→8/5/3
- `SignalMaestro/godmod3_strategy.py`: _ERR_GENERIC 30→90s, _is_model_disabled() recovery
- `Dockerfile`, `nixpacks.toml`, `requirements.txt`: version stamps → v69.0
