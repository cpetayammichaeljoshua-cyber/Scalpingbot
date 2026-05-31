---
name: Unity Engine gate calibration history
description: Key gate thresholds and their calibration history across versions — IRONS floor, quality gate, session bonus, RL thresholds
---

## v21.2 Gate State (2026-05-31 — CURRENT)

| Gate | Constant | Value | Notes |
|------|----------|-------|-------|
| G0 EV floor | EV_MIN_THRESHOLD | 22bps | v20.0: 20→22bps |
| G0.5 Session dead zone | DEAD_ZONE_UTC_START/END | 00:00-02:00 UTC | v18.78: 03h→02h |
| G0.5 Session prime bonus | SESSION_QUALITY_BONUS | 7.0pts | v21.1: 6.0→7.0 |
| G0.5 Prime hours | SESSION_BONUS_UTC_START/END | 15:00-21:00 UTC | v18.78 |
| G3 AI threshold | AI_THRESHOLD_PERCENT | 87% | v20.0: 85→87% |
| G4 NN gate | NN_WIN_PROB_GATE | 0.48 | v19.8: 0.50→0.48 |
| G8.5q QuantDinger | vol_ratio × RSI | ±3pts cap | v21.2 NEW: MomVol coherence |
| G9 Quality floor | SIGNAL_MIN_QUALITY_GATE | 63 | v21.1: 62→63 |
| G10 IRONS WR<30% | IRONS_MIN_WR_BELOW30 | 67 | v21.1: 65→67 |
| G10 IRONS WR<20% | IRONS_MIN_WR_BELOW30+3 | 70 | v21.1: 68→70 |
| G10 IRONS WR 30-45% | IRONS_MIN_WR_30_45 | 63 | v21.1: 62→63 |
| G10 IRONS WR 45-55% | IRONS_MIN_WR_45_55 | 53 | unchanged |
| G10 IRONS WR>55% | IRONS_MIN_WR_ABOVE55 | 48 | unchanged |
| SOVEREIGN_RECOVERY | SOVEREIGN_RECOVERY_GATE | 67 | v21.1: 65→67 |
| MIN_RR | MIN_RR_RATIO | 2.35 | v18.91: 2.20→2.35 |

## v21.2 Operational Parameters

- UNITY_VERSION: "21.2"
- PRIMARY_MODEL: openai/gpt-oss-20b:free (v21.2b: kimi-k2 got 404 on boot)
- NN_RETRAIN_INTERVAL_SEC: 1800 (30min base); 20min crisis; 15min ultra-crisis
- BGHealthProbe initial wait: 10s (v21.1: 45s→10s)
- GODMODE combos: 9 (v21.2: +GODMODE_FINROBOT_CHAIN[gpt-oss-120b], +GODMODE_OPENBB_MACRO[gemma-4-31b])
- IRONS_MIN_SCORE (base/env): 50 (adaptive overrides at runtime based on WR)
- Gate count: 26 (25 existing + G8.5q QuantDinger)

## G8.5q QuantDinger Momentum-Volume Coherence (v21.2 NEW)
- +2.5pts: vol_ratio≥1.3 AND RSI aligned (BUY≥55 | SELL≤45)
- +1.0pts: vol_ratio≥1.3, RSI neutral (45-55)
- +0.5pts: normal volume (0.7-1.3), RSI aligned
- -1.5pts: vol_ratio≤0.7 AND RSI aligned (momentum without volume)
- -1.5pts: RSI counter-directional with vol expansion (fighting momentum)
- -2.5pts: vol_ratio≤0.7 AND RSI counter-directional (false breakout)
- -1.5pts: RSI counter-directional, any volume
- Cap: ±3pts | fires when vol_ratio > 0.05
- signal_data keys: volume_ratio|vol_ratio, rsi|rsi_14, direction

## Why These Thresholds

**EV=22bps**: At WR=29.6%, RR=2.35, break-even EV=0. 22bps requires demonstrated positive EV after 5bps slip+3bps spread.

**AI=87%**: At WR=30% need AI conf>85% to have positive Bayesian EV. 87% adds safety margin.

**IRONS=67(WR<30%)**: v21.1 ruthless WR fix. At WR=29.6%, Sharpe=-4.87, EV=-0.008R. The 65 floor was insufficient. 67 removes bottom 15% of marginal signals → projected WR improvement +3-5pts → EV positive at RR=2.35 (break-even WR=29.85%).

**SIGNAL_QUALITY=63**: 1pt tighten from 62. At negative EV, signals scoring 62-63 are statistically marginal. Creates proper G9/G10 separation: G9=63, G10=67 at WR<30%.

**SESSION_BONUS=7.0**: At IRONS_MIN=67, the +7pt prime bonus lifts borderline 65→72 during 15-21h UTC. Concentrates trading in optimal liquidity hours.

**G8.5q (v21.2)**: QuantDinger research shows momentum without volume confirmation has 20-30% lower follow-through rate. The ±3pt adjustment acts as a quality multiplier — strong signals get boosted further, marginal divergence signals get penalised before reaching IRONS gate.

## v20.5 Gate State (for reference)
- EV=22bps, AI=87%, IRONS_MIN=65(WR<30%), SIGNAL_QUALITY=62, SESSION_BONUS=6.0, NN_RETRAIN=45min
- BGHealthProbe fires at 45s (showed calls=0 at 30s dashboard — expected)
- BGHealthProbe liveness: gex_engine, deribit_gex._snapshots, okx_gex, binance_aggtrade, depth_slip, dyn_backtester, mirofish_sim, sovereign_rm (no underscore)
