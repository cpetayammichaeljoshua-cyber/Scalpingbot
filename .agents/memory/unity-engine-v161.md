---
name: Unity Engine v161.0 upgrades
description: Six-session 17,647-trade data-confirmed gates implemented — GDOW/GCAL/GDIV/GSEQ/GMOM3/GBATCH + IRONS recovery paradox; v160→161
---

# Unity Engine v161.0 — Six-Session Data-Confirmed Gate Implementation

## PF Proof (the definitive architectural anchor)
- Filtered 33.5% of flow → PF=1.407, EV=+3.13%, WR=26.8%
- Blocked 66.5% of flow → PF=0.822, total=-17,056%
- The two populations exactly cancel → PF=1.000 unfiltered
- Filtered LONG (9×Cross only, non-kill hours): 313 trades, WR=40.3%, EV=+25.78% (fat tail)

## New Gates v161.0

### GDOW — Pre-Gate Hard Block (data: 17k trades)
- Tue SHORT: WR=21.7%, EV=-2.14% → hard block
- Sun LONG: EV=-2.30% → hard block
- Env: UNITY_GDOW=0 to disable
- State: `DOW_KILL_CFG`, `_last_g85ae_gdow`, `gate_g85ae_gdow`

### G8.5AF GCAL — Calendar Week Effect
- Days 1-7: WR=26.6%, EV=+1.55% → +1.0pt (month-start institutional positioning)
- Days 8-14: WR=22.3%, EV=-0.47% → -0.5pt
- Days 15-21: WR=20.8%, EV=-0.53% → -1.5pt (worst fortnight)
- Days 22-31: EV=-0.09% → -0.3pt
- Env: UNITY_GCAL=0 to disable

### G8.5AG GDIV — Symbol Diversity Alarm
- Catastrophic days avg 52.5 unique syms, WR=16.6% vs profitable 44.0 syms, WR=31.0%
- ≥55 unique syms/day → -2.5pt | ≥50 → -1.5pt | ≥52 → -0.8pt | <40 → +0.5pt
- Env: UNITY_GDIV=0 to disable; GDIV_LIMIT=52

### G8.5AH GSEQ — Intraday Sequence Position
- Signals 1-10: warm-up (WR=23%) → 0pt
- Signals 11-20: PEAK window (WR=28% EV=+1.79%) → +1.5pt
- Signals 21-90: plateau baseline → 0pt
- Signals 91-100: kill zone (WR=14% EV=-3.4%) → -2.5pt
- Signals >100: meltdown (WR=12%) → -3.5pt
- State: `_v161_daily_signal_n` (UTC-day reset)
- Env: UNITY_GSEQ=0 to disable

### G8.5AI GMOM3 — 3-Signal Session Direction Momentum
- After 2×LONG in recent-3 → SHORT fires: WR=28%, EV=+1.79% → +1.5pt (reversal edge)
- After 2×LONG → LONG: WR=20%, EV=-0.38% → -1.0pt (confirmed kill)
- After 2×SHORT → SHORT: WR=22% EV=-0.41% → -0.5pt (continuation fatigue)
- State: `_v161_dir_ring` (last ≤3 directions, UTC-day reset)
- Env: UNITY_GMOM3=0 to disable

### G8.5AJ GBATCH — Batch Size Signal Cluster
- Batch 5 or 7 signals in 3-min window → +2.5pt (elite selective momentum regime)
- Batch 4, 9, or 10 signals → -3.0pt (spray-and-pray chaos)
- Batch >10 → -4.0pt (ultra-kill)
- State: `_v161_batch_ts` (timestamps in GBATCH_WIN_SEC=180s window)
- Env: UNITY_GBATCH=0 to disable

### IRONS Recovery Paradox Calibration (update_adaptive_irons)
- NON-OBVIOUS: relax IRONS after catastrophe, tighten after moderate negative days
- prev_day_total < -500%: bounce expected → relax to floor 72 (if WR-based ≤79)
- prev_day_total -500 to -200%: muted recovery → max(existing, 79)
- prev_day_total -200 to -100%: grinding regime → max(existing, 80)
- prev_day_total -100 to 0%: WORST next-day historically → max(existing, 82)
- State: `_v161_prev_day_total`, `_v161_prev_day_checked`

## Daily State Reset (UTC-day boundary)
- `_v161_daily_signal_n` → 0
- `_v161_unique_syms` → empty set
- `_v161_dir_ring` → []
- `_v161_batch_ts` → []
- `_v161_prev_day_total` → loaded from booster pnl_ring proxy at day change

## Patch Method
- Python string-replacement patch (`/tmp/patch_unity_v161.py`) — 7 edits
- All edits applied, syntax check passed (py_compile)
- Boot confirmed: "Unity Engine v161.0 — ALL SYSTEMS ONLINE"
- Backup: `start_unity_engine.py.bak_v160`

## Implementation Notes
- Daily state reset fires once per UTC day at the top of the scoring path (before GCAL/GDIV/GSEQ/GMOM3/GBATCH)
- All new gates are non-fatal: wrapped in try/except, never block scoring path
- GDOW is a pre-gate hard block (same pattern as GASN/GEUT): fires before scoring, returns False immediately
- GCAL/GDIV/GSEQ/GMOM3/GBATCH are soft gates: add/subtract from quality score, recorded via _record()
- All 6 gates have env override flags (UNITY_GDOW, UNITY_GCAL, etc.) defaulting to enabled
- Gate stats registered in gate_stats + gate_stats_recent (deque) for /gates endpoint

## Why
- Six sessions of quantitative analysis on 17,647 InsiderTactics trades revealed structural edges
- Each gate confirmed on ≥1 independent dataset analysis session
- The entire value of the filter is in the 33.5% pass population (PF=1.407)
- These gates target the highest-PF-lift opportunities: DOW kills, calendar alpha, diversity alarm, sequence position, direction momentum reversal, batch clustering
