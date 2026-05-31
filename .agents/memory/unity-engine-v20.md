---
name: Unity Engine v20.0 upgrades
description: Key decisions, fixes, and lessons from the v19.8→v20.0 upgrade of start_unity_engine.py
---

## Torch/PyTorch
- Install: `pip install --index-url https://download.pytorch.org/whl/cpu torch==2.3.1+cpu`
- After torch: `pip install transformers==4.44.2 tokenizers safetensors accelerate`
- `_HAS_TORCH` guard already in neural_signal_trainer.py — engine degrades gracefully without torch

## Stale/Zombie Restart Fix
- Root cause: heartbeat was 30s; upgraded to 15s so scan_cycles increments 120× per 1800s watchdog window
- `UnityCycleHeartbeat` is in `_NEVER_CANCEL` frozenset — protects it from zombie detection
- `WATCHDOG_STALL_SECONDS = 1800` — genuine deadlock threshold (not false positive with 15s heartbeat)

**Why:** The 30s heartbeat gave only 60 ticks per 1800s window. Under Railway load with slow Binance REST, the real scanner could miss increments and the watchdog would fire. Halving the interval doubles the safety margin.

## OpenRouter Key Pool
- `LLMKeyRotator` supports OPENROUTER_API_KEY + BACKUP_1..7 (8 total) after v20.0 fix
- Both `_SANITIZE_KEYS` (line ~459) and `_load_keys()` candidate_vars (line ~1554) must be kept in sync
- `_free_tier_mode = True` by default (v19.6) — avoids 3-failure paid-model burn-in on Replit

## 4-Step Strategy Validation Framework
- Implemented in `SignalMaestro/backtest_overfitting_analyzer.py` v2.0
- Step 1: In-Sample Excellence (IS Sharpe>0, WR≥35%, PF≥1.2, EV>0)
- Step 2: IS Permutation Test (p-value < 0.05 → genuine IS edge)
- Step 3: Walk-Forward Test (WFR ≥ 0.30 → OOS transfers)
- Step 4: WF Permutation Test (OOS p-value < 0.10 → genuine OOS edge)
- `validate_strategy(r_returns)` returns `StrategyValidationResult` (new API)
- `assess_overfitting(r_returns)` still returns `OverfitAssessment` (backwards compat)
- Penalty: 4/4=CLEAN(0), 3/4=SUSPECT(-3), 2/4=SUSPECT(-5), ≤1/4=OVERFIT(-7)

## DynamicBacktester Integration
- `aegis_gex/dynamic_backtester.py` v10.0 now calls `validate_strategy()` for 4-step
- Falls back to original 3-metric `BacktestOverfittingAnalyzer.assess()` on import error
- `_HAS_4STEP` flag guards the new path

## Redis
- Replit has no Redis by default → falls back to local file persistence (expected warning, non-fatal)

## Boot Verification
- Engine logs show "ALL SYSTEMS ONLINE" with 21/21 layers, 15-gate filter, 1800s watchdog
- Heartbeat confirmed: "💓 [v20.0] ... 15s interval, watchdog guardian"
- Key rotator confirmed: "8 key(s) loaded (PRIMARY + 7 backup(s))"
- DynBacktest sweep #1 completes in ~2s on boot

**How to apply:** When making future changes to start_unity_engine.py, keep WATCHDOG_STALL_SECONDS ≥ 30× heartbeat interval to avoid false stalls.
