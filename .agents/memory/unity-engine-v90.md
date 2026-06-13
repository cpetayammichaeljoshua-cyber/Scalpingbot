---
name: Unity Engine v90.0 upgrades
description: G8.5X2 WinRateTrajectory gate, Kelly Step 50, NN v26 145-feat, IRONS WR<22% tier, ScanParallel 100
---

## G8.5X2 WinRateTrajectory Gate (58th gate) [v90.0]
- Zero-API-call soft-gate comparing recent booster RL-ring WR vs all-time session WR
- Uses `self._booster._rl_wins / _rl_ring_size` (ring last ~20) vs `self._metrics.win_count / total`
- Tiers: delta < -0.08 → -2.0pts (strongly deteriorating); delta < -0.05 → -1.0pts (mild warn); delta > +0.08 → +2.0pts (recovering)
- Requires ≥20 total resolved trades AND booster ring ≥10 to fire
- Stores `self._last_g85x2_wrt` (+1=recovering, -1=deteriorating, 0=neutral) for Kelly Step 50
- Gate key: `gate_g85x2_wrt`; in _SOFT_GATE_KEYS (cannot block, only adjusts score)

## Kelly Step 50: WinRateTrajectory Sizing [v90.0]
- `_last_g85x2_wrt == +1` (recovering) → Kelly × 1.02
- `_last_g85x2_wrt == -1` (deteriorating) → Kelly × 0.86
- `_last_g85x2_wrt == 0` (neutral/insufficient data) → no change
- Non-fatal; runs after Step 49 DrawdownMomentum

## NN v26: INPUT_DIM 140 → 145, _TORCH_N_TOKENS 28 → 29 [v90.0]
- F141: `rolling_5wr_norm` — recent booster-ring WR normalized [-1,+1] (0.5 → 0.0)
- F142: `rolling_20wr_norm` — all-time session WR normalized [-1,+1]
- F143: `wr_trajectory_norm` — delta(recent - alltime) × 5.0, clamped [-1,+1]
- F144: `recent_loss_streak_norm` — _last_g85x2_wrt × -0.5 (+0.5=deteriorating, -0.5=recovering)
- F145: `recent_win_streak_norm` — recent booster-ring WR raw [0,1]
- Injection block placed after F136-F140 in signal_data; build_features in neural_signal_trainer.py
- Architecture confirmed: 145→128→64→32→1 (BitNet ternary)

## IRONS WR<22% Ultra-Crisis Tier [v90.0]
- New tier: `current_wr < 0.22` → `_adaptive_irons_min = IRONS_MIN_WR_BELOW30 + 2.0` (= 72)
- Same floor as WR<20% tier — closes the 20-22% gap where false recovery signals can slip through
- Inserted between WR<20% (=72) and WR<25% (=71.5) in `update_adaptive_irons()`

## SCAN_PARALLEL_LIMIT 98 → 100 [v90.0]

## Banner / stamp update notes [v90.0]
- Long ARCHITECTURE banner (line ~16446) and wired components stamp (line ~16430) both required sed line-targeted edits — Python byte-string replacements failed (UTF-8 middle-dot ·  U+00B7 = 0xC2B7 didn't match at runtime)
- Use `sed -i '<line>s/old/new/'` for targeted single-line edits when Python `c.replace()` returns 0
- Confirmed: G8.5X2 appears in wired components stamp, Steps1-50 in both banners, NN-v26-145feat in ARCHITECTURE

## Boot confirmation
- Engine started v90.0 cleanly: all 30 layers online in 6258ms
- NN architecture upgraded log: `input_dim 140→145` — discarding old weights, starting fresh
- No Python errors on boot; Redis warning suppressed (expected, Railway env)
