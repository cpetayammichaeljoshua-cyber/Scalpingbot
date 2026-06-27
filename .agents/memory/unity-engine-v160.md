---
name: Unity Engine v160.0 GTOD gate
description: G8.5AD Time-of-Day Direction Penalty (141st gate) + Kelly Step 134 — US-session worst Direction×Hour pockets from 17,647-signal CSV analysis
---

# Unity Engine v160.0 — G8.5AD GTOD + Kelly Step 134

## Changes
- **G8.5AD — GTOD: Time-of-Day Direction Penalty** (141st scoring gate)
- **Kelly Step 134 — GTOD De-size** (matches scoring penalty at position-sizing level)
- UNITY_VERSION 159→160; 140-gate→141-gate

## Data Basis — Direction × Hour (17,647 signals, US session = 13-22h UTC)
Full cross-analysis confirmed worst pockets:
```
LONG  13h UTC: avgP=−4.12%  WR=11.7%  ← worst LONG hour, NY open chaos
LONG  14h UTC: avgP=−3.01%  WR=12.1%  ← both dirs weak, pre-NY overlap
SHORT 14h UTC: avgP=−2.80%  WR=12.9%  ← dual-direction dead zone
LONG  15h UTC: avgP=−3.06%  WR=13.1%  ← early US continuation
SHORT 22h UTC: avgP=−4.39%  WR=12.0%  ← worst SHORT hour, late-day reversal
```

Best US session hours (17-21h UTC): LONG 17.3-17.9% WR, SHORT 16-19.4% WR

## G8.5AD Gate Logic
- Cold-start: ≥20 trades in _pnl_ring
- WR guard: WR≥35% → skip all (trending market overrides microstructure bias)
- LONG  @13h or 14h UTC + WR<35% → -1.5pts (NY open / pre-NY overlap)
- LONG  @15h     UTC + WR<35% → -1.0pt  (early US continuation)
- SHORT @14h     UTC + WR<35% → -1.0pt  (dual-direction dead zone)
- SHORT @22h     UTC + WR<35% → -2.0pts (US session close short-covering)
- Penalty-only; cannot block; compounds with G8.5AC GDLB for LONG in worst pockets

## Kelly Step 134 De-size
- LONG @13-14h UTC + WR<35% → ×0.82
- LONG @15h    UTC + WR<35% → ×0.88
- SHORT@22h    UTC + WR<35% → ×0.78 (strongest de-size, worst pocket)

## Microstructure Rationale
- LONG 13-15h: NY market open (9am ET) = high volatility + directional instability → LONG gets chopped
- SHORT 22h: US session close (5pm ET) = late-day short-covering / buy-the-close programs wipe SHORT
- Both directions at 14h: Pre-NY overlap is a dead zone for signal fidelity

## Direction × Hour Complete Table (US Session 13-22h UTC)
```
Hour  LONG WR  LONG avgP   SHORT WR  SHORT avgP
13h   11.7%    -4.12%      15.2%     -0.44%
14h   12.1%    -3.01%      12.9%     -2.80%  ← dual bad
15h   13.1%    -3.06%      17.1%     +0.88%
16h   14.7%    -0.91%      14.0%     -0.26%
17h   17.9%    -0.28%      16.0%     +2.50%  ← best LONG WR
18h   16.0%    +1.57%      18.5%     +2.88%  ← best SHORT WR
19h   16.1%    -0.14%      14.6%     +0.70%
20h   17.3%    -0.47%      19.4%     +1.23%
21h   17.5%    +0.19%      17.9%     +0.81%
22h   15.5%    -0.83%      12.0%     -4.39%  ← SHORT catastrophic
```

**Why:** NY open and US close are confirmed worst microstructure periods for directional futures signals. LONG gets chopped at open by volatility; SHORT gets reversed at close by buy programs.
