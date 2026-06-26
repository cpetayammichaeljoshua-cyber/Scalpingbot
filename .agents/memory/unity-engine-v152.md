---
name: Unity Engine v151.0/v152.0 upgrades
description: v151: GCLH 28.5%→30% + G8.5U4 advanced-crisis tier; v152: G8.5Q4 ultra/advanced tiers + quality floor tighten
---

## v151.0 Changes (GCLH + G8.5U4 blind-spot)

**GCLH threshold: 28.5% → 30%**
- All 4 code locations updated: arm trigger, release check, 3 log strings, 3 inline comments
- GCLH now arms at WR=29% (WR<30% trigger) — was missing at current live WR

**G8.5U4 TripleUltimateCrisis — advanced-crisis tier added:**
- OLD: WR<25%+SR<-4.0+DD>47% → -4.0pts; WR<28%+SR<-3.0+DD>42% → -3.0pts
- NEW: Added WR<30%+SR<-4.0+DD>47% → -2.5pts (fires at WR=29%+SR=-4.87+DD=49.37%)
- Blind-spot: WR<28% ultra-tier missed WR=29%; new tier closes the gap
- Banner: `(-4.0/-2.5/-3.0/+1.5pts)[v124.0/v151.0]`

---

## v152.0 Changes (G8.5Q4 + quality floors)

**G8.5Q4 MaxDD-EV-Compound — identical blind-spot found and fixed:**
- WR=29%+DD=49.37% only triggered -2.0pts (deep tier, DD>42%+WR<32%)
- Extreme tier requires WR<28% — MISSES WR=29%
- NEW tier 1: DD>47%+WR<28% → -4.0pts (raised from -3.0)
- NEW tier 2: DD>48%+WR<30% → -3.5pts (fires NOW at WR=29%+DD=49.37%)
- Banner: `(-4.0/-3.5/-2.0/+1.5pts)[v121.0/v152.0]`

**SIGNAL_MIN_QUALITY_GATE: 72 → 73**
- G9 floor +1pt; 72-73 band confirmed net-negative at sustained WR=29%+SR=-4.87
- Markov-SOVEREIGN fast-path: 73+16=89≥73 (unaffected)

**IRONS_MIN_WR_BELOW30: 75 → 77**
- G10 crisis floor +2pt; eliminates bottom 15-20% of IRONS-passing signals in WR<30% crisis
- Auto-scale: WR<25%→78.5, WR<20%→80
- Three-tier coherence: G9=73 + G10/SOVEREIGN=77 + WR<20%=80

**IRONS_MIN_WR_30_45: 71 → 72**
- Co-equal with G9 raise to 73; dual-floor coherence in WR 30-45% recovery

**KEY LESSON — Recurring blind-spot pattern:**
Multiple gates (G8.5U4, G8.5Q4) had extreme-crisis tiers gated on WR<28%, which MISSES the live WR=29%. When adding crisis tiers, ALWAYS check the exact live WR against each tier's WR threshold. The correct pattern is: existing extreme tier catches WR<28%, add a NEW tier at WR<30% to catch the 28-30% gap at current live state.
