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

## Strategic lesson
- Adding gates / cranking thresholds has never moved outcome-WR off ~24–29% across 100+ versions = overfitting churn.
- The data says the real levers are **session/regime selection + RR-target calibration + dropping miscalibrated signals (confidence, swarm_consensus)**, NOT a 114th gate.
- Any genuine winrate improvement needs a **walk-forward backtest on fresh data**, which cannot be run inside this Replit env. The engine's EXISTING adaptive losing-regime Kelly de-sizing (halves size when rolling-20 WR < ~29%) responds to LIVE data and is more robust than hardcoding stale-data filters.
