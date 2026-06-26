---
name: Unity Engine v150.0
description: GCEF short-penalty gate extension + IRONS conservative tier selection fix at both call sites + stale Gate 10 banner fix
---

## GCEF — G8.5T4 Extreme Fear SHORT Penalty (v150.0)

**Conviction:** When F&G≤20 AND BTC GEX=FLIP ZONE AND direction=SHORT → **-2.5pts quality penalty**.

In capitulation (F&G=13, ALL 3 assets at FLIP ZONE), short positions are maximally crowded. Dealers are in neutral GEX territory — no structural support for further downside. Squeeze risk is highest. This is the mirror of the existing LONG +2.5pts reversal bonus (same F&G<15+FLIP condition).

**Implementation:** Added `elif _t4_fg < 20.0 and _t4_btc_regime == "FLIP ZONE":` branch to the SHORT direction block inside G8.5T4. Sets `_t4_adj = -2.5, _t4_cap = -1`. Kelly Step 98 already sizes DOWN on `_last_g85t4_cap = -1`.

**Live context when shipped:** F&G=13, BTC/ETH/SOL all FLIP ZONE simultaneously.

## IRONS Conservative Tier Selection — Two Call Sites Fixed

**The bug:** Bayesian WR (α=813/β=1980 = 29.1%) is below 30% but ring×0.15 pushes blend to 31.5%, causing:
- `update_adaptive_irons(31.5%)` → WR30-45% tier → IRONS_MIN=71 (wrong)
- Should be: WR<30% tier → IRONS_MIN=75

**TWO call sites required the fix:**
1. **Bug O path (v19.5, line ~28982):** `_rn_tier_wr = min(_rn_blend_wr, _rn_bayes_wr) if _rn_bayes_wr < 0.30 else _rn_blend_wr`
2. **Boot pre-set (v7.3, line ~29090):** Changed `_irons_wr = blend` → `_irons_wr = min(blend, bayes) if bayes < 0.30 else blend` INSIDE the try block

**Log sequence confirmation:**
```
[v19.5 Bug O] blend_wr=31.5% tier_wr=29.1% → min=75  ✅
[v7.3]        tier_wr=29.1% → min=75                   ✅
```

**Why:** The v7.3 boot pre-set runs AFTER Bug O and previously overrode the correct min=75 back to 71. Both paths now use the conservative (lower of Bayes vs blend) for tier selection. Rule: whenever IRONS tier selection is near a WR boundary, the Bayesian posterior (N≥2793) is authoritative over the short ring.

## Stale Gate 10 Boot Banner Fix

Old: `[v70.0: WR<30%→70 | WR<25%→71.5 | WR<20%→72 | WR<18%→73 | WR30-45%→67]`
New: `[v147.0: WR<30%→75 | WR<25%→76.5 | WR<20%→78 | WR<18%→78 | WR30-45%→71]`

Also: KEY GATES (v150.0) banner updated to include `GCEF:FLIP+F&G≤20+SHORT→-2.5pts`.

## UNITY_VERSION: 149.0 → 150.0
