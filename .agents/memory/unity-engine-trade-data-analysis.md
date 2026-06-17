---
name: Unity Engine trade-data analysis (SignalMaestro/trade_history.db)
description: What 3,296 real resolved trades actually say about the engine's edge — use BEFORE blindly cranking thresholds or adding gates to "improve winrate"
---

# Unity Engine trade-data reality (from SignalMaestro/trade_history.db)

Analysis run on the `trades` table (3,298 rows, 3,296 resolved w/ pnl_pct). Data snapshot ~May-31; older engine versions, so directional not definitive — but it is REAL outcome data and far better than guessing.

## Two sources are mixed — never analyze them together
- `bot` (the live Unity Engine signals): n=1588, **avgPnL ≈ −0.04%/trade (breakeven/slightly negative)**, pnl-sign WR 42.3%.
- `insidertactics` (a SEPARATE strategy): n=1708, **+0.85%/trade**. This is the ONLY thing making the blended number look positive.
- **Lesson:** any "the bot is profitable" claim from a blended query is wrong. Split by `source` first.

## WR definition matters
- **Outcome-WR (TP*=win, SL/EXPIRED=loss) = 24.2%** → this is what the engine reports as live WR (~24–29%).
- pnl-sign WR = 37.8% only because it counts tiny-positive EXPIRED trades as "wins". Don't quote 37.8% as the real WR.
- Outcome mix: SL=1644 (50%), EXPIRED=855, TP1=395, TP3=337, TP2=65.

## Real, large-sample weak pockets (drawdown/noise levers)
- **ASIAN session = negative expectancy**: −0.27% avgPnL over 726 trades (in the dominant RR 2.5–3.5 band: −0.31 over 683). US session is best (~+0.08 to +0.25). EU/TRANSITION ~flat/negative.
- **RSI > 70 (overbought) = bad**: WR 24.5%, avgPnL −1.40% (small n=49 but consistent with "don't chase overbought").
- **volume_ratio > 2 = bad**: −0.6% to −1.1% avgPnL.
- **Confidence is miscalibrated/non-predictive**: confidence 90+ has WORSE avgPnL (−0.08%) than 70–80 (+0.84%). Higher "confidence" does not mean better outcome.
- **`swarm_consensus` is a DEAD column**: all 3,296 rows fall in the <50 bucket → carries zero information; any gate keying off it is a no-op.
- The RR "paradox" (RR 1.5–2 looks great) is a SOURCE CONFOUND — those wins are insidertactics, not the bot. The bot's own RR band (2.5–3.5) is weak/negative.

## Walk-forward VALIDATION (SignalMaestro/walk_forward_backtest.py)
Purged/embargoed expanding-window walk-forward on `bot` source (1588 trades, 6 folds), filters LEARNED on train + applied to unseen test. Architect-reviewed PASS. Results are "walk-forward-supported on this May-31 snapshot", NOT production-proof.
- OOS baseline (no filter): avgPnL **−0.212%/trade**, maxDD **418%** → the live bot is genuinely negative out-of-sample (worse than full-sample −0.04%; recent folds degrade).
- `session` (learn neg-expectancy sessions on train → drop them; consistently learns EU+ASIAN+TRANSITION, keeps US): avgPnL −0.093%, **maxDD 205% (halved)**.
- `vol_spike` (volume_ratio>2 block, learned True folds 2-5): avgPnL −0.130%, maxDD 372%. Modest but real.
- `session+vol` (the validated combo): avgPnL **+0.001% (flips losing→breakeven)**, maxDD **213%**. Drops ~51% of signals.
- `rsi_overbought` (RSI>70): no-op (bot rarely takes them, only 4 filtered). `confidence_high` (>=80) control: negligible Δ → confidence score is NOT predictive.
- **Caveats:** maxDD is cumulative trade-PnL-points (not account DD under Kelly sizing); ~5 OOS folds; thresholds had mild exploratory selection bias; embargo is trade-count not holding-horizon. Even best case is only ~breakeven — filtering cuts losers/drawdown, it does NOT create a strong positive edge.
- **Live rollout blocker:** the live engine does NOT compute US/ASIAN/EU/TRANSITION labels in its Kelly path (only binary UTC prime/morning windows at SESSION_BONUS_UTC_*); labels come from the SignalMaestro bot module. mirofish_swarm_strategy.py session_multipliers even BOOST EU (1.05-1.15×) — contradicts validated EU-negative. Any live de-size must use the exact live session classifier + be re-validated on fresh data first.

## Strategic lesson
- Adding gates / cranking thresholds has never moved outcome-WR off ~24–29% across 100+ versions = overfitting churn.
- The data says the real levers are **session/regime selection + RR-target calibration + dropping miscalibrated signals (confidence, swarm_consensus)**, NOT a 114th gate.
- Any genuine winrate improvement needs a **walk-forward backtest on fresh data**, which cannot be run inside this Replit env. The engine's EXISTING adaptive losing-regime Kelly de-sizing (halves size when rolling-20 WR < ~29%) responds to LIVE data and is more robust than hardcoding stale-data filters.
