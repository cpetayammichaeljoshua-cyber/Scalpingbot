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
- The RR "paradox" (RR 1.5–2 looks great) is a SOURCE CONFOUND — those wins are insidertactics, not the bot. The bot's own RR band (2.5–3.5) is weak/negative. (v130.0 re-check: WITHIN `bot`, RR<2.0 DID show +0.53%/trade / 48% WR vs RR≥3.0 −0.137% — BUT RR<2.0 trades exist ONLY in the earliest chronological fold; the engine stopped producing them once MinRR was raised, so it is NOT walk-forward-validatable. Do NOT lower MinRR on an in-sample-only pocket.)
- insidertactics logs CONSTANT placeholder values for confidence/rsi/volume_ratio/session (every row lands in one bucket) — only its RR column varies. So any insidertactics univariate "edge" in a pooled query is an artifact; split by source AND ignore its non-RR features.

## Walk-forward VALIDATION (SignalMaestro/walk_forward_backtest.py)
Purged/embargoed expanding-window walk-forward on `bot` source (1588 trades, 6 folds), filters LEARNED on train + applied to unseen test. Architect-reviewed PASS. Results are "walk-forward-supported on this May-31 snapshot", NOT production-proof.
- OOS baseline (no filter): avgPnL **−0.212%/trade**, maxDD **418%** → the live bot is genuinely negative out-of-sample (worse than full-sample −0.04%; recent folds degrade).
- `session` (learn neg-expectancy sessions on train → drop them; consistently learns EU+ASIAN+TRANSITION, keeps US): avgPnL −0.093%, **maxDD 205% (halved)**.
- `vol_spike` (volume_ratio>2 block, learned True folds 2-5): avgPnL −0.130%, maxDD 372%. Modest but real.
- `session+vol` (the validated combo): avgPnL **+0.001% (flips losing→breakeven)**, maxDD **213%**. Drops ~51% of signals.
- `rsi_overbought` (RSI>70): no-op (bot rarely takes them, only 4 filtered). `confidence_high` (>=80) control: negligible Δ → confidence score is NOT predictive.
- **Caveats:** maxDD is cumulative trade-PnL-points (not account DD under Kelly sizing); ~5 OOS folds; thresholds had mild exploratory selection bias; embargo is trade-count not holding-horizon. Even best case is only ~breakeven — filtering cuts losers/drawdown, it does NOT create a strong positive edge.
- **Live rollout — SHIPPED v129.0:** the validated combo is now LIVE in `_update_kelly` — Kelly Step 106 de-sizes EU/ASIAN/TRANSITION to 0.55× (`SESSION_KELLY_DESIZE`) using `_current_kelly_session()` (mirrors `get_current_market_session()`, NOT the old binary UTC windows → resolves the prior "labels not in Kelly path" blocker); Kelly Step 107 de-sizes vol_ratio>2.0 to 0.70× (`VOL_SPIKE_RATIO_THRESH`/`VOL_SPIKE_KELLY_DESIZE`). De-size only (never hard-block) so signal flow is preserved. REMAINING CAVEATS: mirofish_swarm_strategy.py session_multipliers may still BOOST EU upstream — verify it doesn't re-inflate what Step 106 de-sizes; and thresholds came from the May-31 snapshot, so re-validate on fresh data periodically.

## Fresh-data confirmation (3 NEW signal-channel CSV exports, Jun-2026)
Three Telegram copy-trade channel exports analyzed (leverage-inclusive "Signal Gained Profit %"; de-leveraged = pnl% / leverage). Outcome-WR = TP/partial→win, "Stopped Out"→loss, Cancelled excluded.
- **InsiderTactics** (16.4k rows, 15,092 resolved, Mar–Jun 2026 — the channel the bot's `insidertactics` source mirrors, and the largest/freshest set): **33.9% WR, mean leveraged P&L ≈ −0.005% (breakeven), de-lev −0.008%.** WR is **strikingly stable** month-to-month (33.5/34.8/34.2/33.8%). This is the true edge profile: ~34% WR, ~zero expectancy — matches the engine's live WR. Shorts mildly > longs (35.2% vs 32.6% WR; +0.187 vs −0.214) but not strong/clean enough to hardcode a directional bias.
- **SignalTactics** (12.2k rows, 9,227 resolved): aggregate looks great (55.9% WR, +3.83% mean) **but it's a stale in-sample artifact** — Sept-2025 fold carried it (64.8% WR), recent months **collapsed to ~37% WR** (2026-03/04). Classic regime decay; NOT reliable forward.
- **PnLTactics** (1.08k rows, 1,073 resolved): 42.8% WR, positive both months — but only 2 months and the +29% lev[9-12) bucket is 25-trade outlier noise. Too small/short to walk-forward-validate.
- **Verdict (same as all prior analyses):** every channel that looks profitable does so only in an EARLY in-sample window; all converge to ~34–43% WR / ~breakeven in recent months. There is no hidden forward edge to gate your way into. Confirms — on fresh, large data — that the strategy family is structurally breakeven-to-negative.

## Direction × time-of-day (long vs short) — cross-validated Jun-2026
Ran long/short × hour-UTC × session on BOTH the InsiderTactics CSV (15,092 resolved, upstream mirror) and the bot's OWN trades (trade_history.db `bot`, 1,596). Only trust what REPLICATES across both sources:
- **REPLICATES — US session (~16–23 UTC) is the best, most reliable pocket for BOTH directions** (bot: Long US +0.30%/WR49%, Short US +0.18%/WR45%; insider: both US positive). Exactly what live Kelly Step 106 already does (keep US, de-size rest) → no new code needed.
- **REPLICATES — Long ASIAN is negative** (bot −0.40%, insider −0.13%); **TRANSITION is worst for longs** (bot −1.44%).
- **CONTRADICTS — do NOT build a direction×session rule:** EU-longs are the WORST pocket in insider (−0.22%, n=2309) but the BEST in the bot (+0.44%, n=106); Asian-shorts are insider's best (+0.13%) but negative in the bot (−0.11%). Opposite signs across sources = noise; hardcoding either overfits one dataset.
- **The real bot problem is realized-R:R collapse, not WR.** Bot targets MinRR 2.65 but REALIZED R:R = 1.46 long / 1.19 short (avgWin≈+4.4%, avgLoss≈−3.0%). At that R:R, breakeven WR = 40.6% (long)/45.7% (short); bot sits at 40.0%/44.8% → −0.6 to −0.9pp (breakeven-negative). Losers run near full SL while winners are diluted by EXPIRED-small-positive + TP1-only partial exits. Highest-leverage lever = close the target-vs-realized R:R gap (honor/tighten SL, cut EXPIRED bleeders, or let winners run past TP1); lifting realized R:R to 2.0 drops breakeven WR to ~33%. This is a TP/SL/time-stop behavioral change that itself needs walk-forward validation — do NOT ship blind.

## Strategic lesson
- Adding gates / cranking thresholds has never moved outcome-WR off ~24–29% across 100+ versions = overfitting churn.
- The data says the real levers are **session/regime selection + RR-target calibration + dropping miscalibrated signals (confidence, swarm_consensus)**, NOT a 114th gate.
- Any genuine winrate improvement needs a **walk-forward backtest on fresh data**, which cannot be run inside this Replit env. The engine's EXISTING adaptive losing-regime Kelly de-sizing (halves size when rolling-20 WR < ~29%) responds to LIVE data and is more robust than hardcoding stale-data filters.
