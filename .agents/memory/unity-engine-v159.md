---
name: Unity Engine v159.0 upgrades
description: G8.5AC GDLB Direction Long Bias Penalty (140th gate, data-confirmed from 16,305 terminal signals) + Kelly Step 133 LONG de-size; v158→v159; full CSV analysis findings documented
---

## Data Analysis: 17,647-Signal InsiderTactics CSV (June 2026)

### Headline Findings (16,305 terminal signals)

| Metric | Value | Implication |
|---|---|---|
| Overall WR (strict, All Targets only) | 15.3% | Engine 29% = strong selection alpha |
| Long WR | 14.1% | Structural loser |
| Short WR | 16.4% | Structural winner |
| Long avgP | −0.28% | Confirmed negative |
| Short avgP | +0.26% | Confirmed positive |
| Max consecutive loss run | 44 | Validates GDCR necessity |
| Post-3-SL bounce WR | 41.5% | Channel self-corrects (vs 15.3% base) |

### Direction × Leverage Cross (critical)

| Bucket | WR | avgP | Verdict |
|---|---|---|---|
| Long 5-7X | 12.4% | −1.26% | WORST |
| Long 8-10X | 13.9% | −0.73% | BAD |
| Long 11-13X | 16.8% | +0.92% | OK |
| Short 5-7X | 16.3% | +0.45% | GOOD |
| Short 8-10X | 17.0% | +1.54% | BEST |
| Short 11-13X | 11.5% | −1.15% | BAD |

### Duration is Strongest Single Predictor

| Duration | WR | avgP |
|---|---|---|
| <15min | 1.3% | −11.74% |
| 15-30min | 2.1% | −11.14% |
| 30-60min | 3.2% | −9.42% |
| 1-2h | 7.4% | −5.74% |
| 2-4h | 14.9% | +0.31% |
| 4-8h | 24.0% | +7.57% |
| >8h | 37.1% | +16.59% |

**Why:** Short-duration trades are structural losers. The engine cannot predict trade duration at signal time, but GXPR (near-zero EXPIRED tracking) is the existing proxy for fast-stop regimes. This analysis validates GXPR.

### Worst Symbols (by WR)
- DOT: 9.3% | LINK: 10.3% | XRP/SOL: 12.8% | AVAX: 12.4%
- GBLK adaptive per-symbol block already handles these adaptively

---

## Changes in v159.0

### G8.5AC — GDLB: Direction Long Bias Penalty (140th scoring gate)

**Source: 16,305 terminal signals, LONG avgP=−0.28% vs SHORT avgP=+0.26%**

- At crisis WR (<32%), LONG signals face 0.54pp avgP structural headwind vs SHORT
- Direction-aware penalty-only gate (no reward for SHORT — that's already baked into signal selection):
  - `direction == "LONG"` AND WR < 28% → **−1.5pts** (deep-crisis LONG)
  - `direction == "LONG"` AND WR < 32% → **−1.0pt** (crisis LONG)
  - `direction == "SHORT"` → 0pts (structural edge inherent; no boost needed)
- WR guard: WR ≥ 35% → skip (momentum continuation can override structural bias)
- Cold-start: requires `len(booster._pnl_ring) >= 30`
- Cross-validation: G8.5AB XRSI + G8.5AC GDLB both fire simultaneously on LONG+RSI>72 = −2.5pts compound penalty

### Kelly Step 133 — GDLB Long De-size

Mirrors G8.5AC at the sizing level:
- LONG + WR < 32% → `_kelly_ceil × 0.90`
- LONG + WR < 28% → `_kelly_ceil × 0.85`
- Uses `self._last_direction` (dispatch path, consistent with Steps 20/23/26 pattern)
- Min floor: 0.05% (from `max(_kelly_ceil * mult, 0.05)`)

### Compound Anti-signal Stack at Current State (WR=29%)

A LONG signal at WR=29% with conf≥92 and RSI>72 now faces:
- G8.5AA CWD: −1.5pts (conf≥92+WR<30%)
- G8.5AB XRSI: −1.5pts (LONG RSI>72+WR<35%)
- G8.5AC GDLB: −1.0pt (LONG WR<32%)
- **Total: −4.0pts compound penalty** → very likely IRONS fail at IRONS_MIN=77

### Infrastructure
- UNITY_VERSION 158 → 159
- Gate count: 139-gate → 140-gate
- KEY GATES banner updated with G8.5AC + Kelly133 entries

## Post-3-SL Finding (Important for Future)
Post-3-consecutive-SL channel WR = 41.5% vs 15.3% base. This means:
- The channel self-corrects after loss streaks
- GCLH blocks the ENGINE after engine's own loss streaks (separate distribution)
- Engine's 29% WR vs channel's 15.3% proves engine selection adds significant alpha
- GCLH remains valid as long as engine's consecutive losses track channel's loss clusters
- Future consideration: reduce GCLH block duration if data shows engine-level post-3-loss bounce

## Syntax
- SYNTAX OK (ast.parse clean, v159.0)
- All 8 insertion points confirmed: version, gate count, gate_stats, sentinel, DISPLAY_LABELS, SOFT_GATE_KEYS, gate code, Kelly Step 133
