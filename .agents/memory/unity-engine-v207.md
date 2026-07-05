---
name: Unity Engine v207.0
description: _wr_dampen ramp tightening — floor now kicks in at WR≤30% (was WR≤25%), reducing all 230 positive bonus sites by ~8% at the live WR=29% operating point
---

# Unity Engine v207.0 — _wr_dampen Ramp Tightening

## Change
`_wr_dampen()` ramp start shifted from WR=25% to WR=30%; full-scale shifted from WR=40% to WR=45% (15pp ramp preserved).

**Old formula:** `_mult = max(0.70, min(1.0, 0.70 + ((_wr - 0.25) / 0.15) * 0.30))`
- WR=25%: 0.70 (floor)
- WR=29%: 0.78
- WR=40%: 1.00

**New formula:** `_mult = max(0.70, min(1.0, 0.70 + ((_wr - 0.30) / 0.15) * 0.30))`
- WR≤30%: 0.70 (floor) — now includes live operating point of 29%
- WR=35%: 0.80
- WR=45%: 1.00

## Impact at Live WR=29%
- All 230 positive bonus sites: reduced from ×0.78 to ×0.70 (8% tighter)
- Example: ISB +5.0pt → +3.5pt (was +3.9pt)
- Example: GEX max +12pt → +8.4pt (was +9.4pt)
- Negative penalties: unchanged (no-op for pts≤0, same as before)

## Why
At WR=29% (live operating point), the old formula still gave 78% of raw bonus value. This is too generous for a regime where 71% of signals fail. Moving the ramp start to 30% means the floor applies across the entire sub-30% WR regime (the current live regime), requiring signals to have higher BASE quality to pass G9 rather than relying on compounding positive bonuses.

**How to apply:** This changes `_wr_dampen()` only. All individual gate thresholds, G9 floor, IRONS tiers, and Kelly steps are unchanged. Effect: marginally-qualifying signals that relied on stacked bonuses will now fail G9; genuine high-quality signals (strong G1-G8 base) will still pass.

## Boot Confirmation
- v207.0: 21/21 layers online, Semaphore(110) ✅
- Clean boot, no errors

## Comprehensive Scan Results (v206→v207)
All of the following confirmed clean during the v207.0 session scan:
- `_wr_dampen` WR source: `self._booster.win_rate` (correct) ✅
- ISB: dual-SOV `(_mk_sov_flag AND _vibe_sov_flag)` OR `(Markov-SOV + cons≥95% + Sharpe≥-4.0)` ✅
- GSLK: early-exit win-reset (`consecutive_losses==0`) ✅
- GCAL: 4 day-ranges correct, all WR-dampened, UTC-correct ✅
- Daily resets: `_v161_daily_signal_n`, `_v161_unique_syms`, `_v161_batch_ts` all reset at UTC day boundary ✅
- Kelly chain: `_kelly_ceil` init line 24098, published to `self._kelly_ceil` line 24260 ✅
- NN INPUT_DIM=420 with v202.0 fix confirmed at trainer line 96 ✅
- No new double-record bugs (gate_ofi lines 1866-1867 = docstring false positive) ✅
- No new dead gates found ✅
- No new overscoring paths found (all 230 sites remain WR-dampened) ✅
