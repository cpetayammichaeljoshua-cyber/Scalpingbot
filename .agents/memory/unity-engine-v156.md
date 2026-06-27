---
name: Unity Engine v156.0 upgrades
description: GDCR-AR adaptive relief (WR-progress gated, 2h improving / 3h flat) + GXPR EXPIRED-proxy rate hard-block (≥65% near-zero pnl in last 20 → 45min block); v155→v156
---

## Changes in v156.0

### GDCR-AR — Adaptive Relief with WR-Progress Tracking (Phase 1.98b)
- **Problem**: GDCR time-release (v155) fires one relief signal per 2h regardless of whether previous relief signals are working. If relief signals keep losing, WR worsens and next 2h window burns on another losing attempt.
- **Fix**: Track `_gdcr_wr_at_block` (WR when GDCR first fired) and `_gdcr_wr_at_relief` (WR at last relief). After ≥1 relief given, if `wr_delta < 0.005` (WR not improved ≥0.5pp since last relief) → extend next interval to 10800s (3h). If WR improving → keep 7200s (2h).
- **New attrs**: `self._gdcr_wr_at_block: float`, `self._gdcr_wr_at_relief: float`, `self._gdcr_relief_count: int`
- **Reset**: All GDCR-AR attrs reset to 0 when GDCR condition clears (else branch)
- **Env**: `UNITY_GDCR_ADAPTIVE=0` to disable adaptive interval (reverts to fixed 2h)
- **Log**: Each relief logs `WR Δblock=` and `WR Δlast=` and `interval=Xh` so recovery trajectory is visible
- **Principle**: Positive feedback loop — recovering engine gets relief sooner, stagnant engine waits longer

### GXPR — EXPIRED-Proxy Rate Hard-Block (Phase 2.01)
- **Problem**: #1 confirmed realized R:R bottleneck from trade-data: 855/3298 trades (26%) expire at near-zero P&L, diluting realized R:R from theoretical 2.75 to actual 1.19–1.46 (long/short). Engine was firing into EXPIRED-dominant choppy regimes.
- **Proxy**: `booster._pnl_ring` stores per-trade P&L as decimal fraction. EXPIRED trades have |pnl| < 0.005 (0.5%) — below MIN_TP1=0.65%, time-out before SL.
- **Threshold**: ≥13/20 recent trades near-zero (65%+ rate) → 2700s (45min) hard-block
- **Cold-start safe**: Only fires when `len(_pnl_ring) >= 20`
- **Position in chain**: After GMDR, before CB (hard cutoff) — Phase 2.01
- **Gate stats**: `gate_gxpr` registered in gate_stats init and `_GATE_DISPLAY_LABELS`
- **Env**: `UNITY_GXPR=0` to disable

### Infrastructure
- `gate_gxpr: {"pass": 0, "fail": 0}` added to gate_stats init after gate_gmdr
- `"gate_gxpr": "GXPR"` added to `_GATE_DISPLAY_LABELS` after gate_gmdr
- Gate count: 136-gate → 137-gate (all banners updated)
- UNITY_VERSION 155 → 156

## KEY PRINCIPLES (reaffirmed from trade-data analysis)
- Gate-adding has NEVER moved outcome-WR off 24-29% across 155 versions
- GXPR is novel: targets EXPIRED bleed specifically (no prior gate addressed near-zero pnl rate)
- GDCR-AR is novel: makes relief windows conditional on actual WR recovery (loop engineering applied)
- Both changes are structural (hard-block), not scoring — consistent with v144+ lesson that only hard-blocks move WR/Sharpe/maxDD

## Live State at v156.0 Build
- WR=29.0%, W=812, L=1986, Sharpe=-4.87, MaxDD=49.37%
- GDCR fires at boot (all 3 conditions met); GDCR-AR relief_count=0 on fresh start
- Engine not live (missing TELEGRAM_BOT_TOKEN / BINANCE keys)

## Boot validation
- SYNTAX OK (ast.parse clean, 30,746 lines)
- All grep checks: gate_gxpr wired in 5 places, _gdcr_wr_at_block in 4 places
- 137-gate confirmed in ARCHITECTURE banner and launcher string
