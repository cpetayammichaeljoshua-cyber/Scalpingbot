---
name: Unity Engine v82.0 upgrades
description: v82.0 changes — OpenRouter model storm fix, G8.5O2 gate, Kelly Step 41, NN v19 F106-F110, key constants fixed
---

## Summary
v82.0 (2026-06-12) — Primary focus: fix persistent OpenRouter model storm causing CONSORTIUM failure and ULTRAPLINIAN fallback every cycle.

## Root Cause Fixed
`anthropic/claude-fable-5` and `anthropic/claude-mythos-5` return 404 generic errors on every free-tier OpenRouter call.
- `_GENERIC_ERR_THRESHOLD=12` → required 12×90s = ~18 min of burn before session_perm_disable fired
- `_CONSORTIUM_MIN_MODELS=2` → when only gpt-oss-20b or 120b responded (all others rate-limited), CONSORTIUM failed → ULTRAPLINIAN fallback

## Constants Fixed (godmod3_strategy.py)
- `_GENERIC_ERR_THRESHOLD`: 12 → **5** (fast perm-disable for genuinely dead routes)
- `_CONSORTIUM_MIN_MODELS`: 2 → **1** (accept 1-model CONSORTIUM result over ULTRAPLINIAN fallback)

## GODMODE Combos Replaced (godmod3_strategy.py)
- `GODMODE_CLAUDE_FABLE5` (anthropic/claude-fable-5 → 404) → **GODMODE_STRUCTURAL_VORTEX** (openai/gpt-oss-120b:free, 4-lens structural inflection system)
- `GODMODE_CLAUDE_MYTHOS5` (anthropic/claude-mythos-5 → 404) → **GODMODE_MACRO_NEXUS** (openai/gpt-oss-20b:free, 5-layer orthogonal scoring system)
- Cognitive diversity preserved: same base model + distinct reasoning framework = different analytical outputs

**Why:** gpt-oss-120b and gpt-oss-20b are the only consistently working free-tier models per live logs. Using them with structurally different system prompts preserves ensemble diversity without wasting the error budget on dead routes.

## New Gate: G8.5O2 WinRate-EV Coherence (49th gate)
- Location: `start_unity_engine.py`, after G8.5N2 FundingMomentum block
- Init key: `gate_g85o2_evcoherence`, signal: `_last_g85o2_ev_signal` (+1/-1/0)
- Logic: reads `self._metrics.win_count/loss_count` + `self._consec_losses`
  - WR < 28% AND consec ≥ 4 → −2.0pts (losing regime)
  - WR > 42% AND consec = 0 → +1.5pts (winning regime)
  - consec ≥ 3 (no regime flag) → −1.0pts (streak penalty)
  - Requires ≥ 10 resolved trades (sample guard)
- Added to `_GATE_DISPLAY_LABELS` and `_SOFT_GATE_KEYS`

## Kelly Step 41: WinRate-EV Coherence Sizing
- Losing regime (`_last_g85o2_ev_signal == -1`) → Kelly ×0.82
- Winning regime (`_last_g85o2_ev_signal == 1`) → Kelly ×1.03
- consec_losses ≥ 3 (neutral signal) → Kelly ×0.90

## NN v19: INPUT_DIM 105→110
- `_TORCH_N_TOKENS`: 21 → 22 (22×5=110)
- `INPUT_DIM`: 105 → 110
- F106: `wr_regime_norm` — session WR normalized (50%=0.0, ±25%=±1.0)
- F107: `consec_loss_norm` — consecutive losses normalized (0→0.0, 5+→-1.0)
- F108: `ev_coherence_gate` — G8.5O2 output (−1/0/+1)
- F109: `sharpe_norm` — Sharpe ratio / 3.0, clipped [-1,+1]
- F110: `meta_regime_composite` — combined average of F106-F109

## SCAN_PARALLEL_LIMIT: 84 → 86

## Files Changed
- `SignalMaestro/godmod3_strategy.py` — constants, GODMODE combos
- `start_unity_engine.py` — version, scan_parallel, gate init/impl/labels/softkeys, Kelly Step 41, NN injection, docstring, KEY GATES, banner
- `SignalMaestro/neural_signal_trainer.py` — INPUT_DIM 105→110, _TORCH_N_TOKENS 21→22
- `Dockerfile` / `nixpacks.toml` — version strings synced to v82.0
