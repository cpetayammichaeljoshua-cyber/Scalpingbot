---
name: Unity Engine v154.0 upgrades
description: GDCR hard-block gate, G8.5W2 ultra-extreme tier, G8.5B4 WR<30% threshold, G8.5H3 new tiers
---

# Unity Engine v154.0

## Changes

### GDCR — Triple-Crisis DrawdownCrisisRate Hard-Block (Phase 1.98)
- Inserted after GCLH gate (Phase 1.98)
- Fires when ALL THREE: DD>47.5% AND WR<30% AND SR<-4.0
- Hard-block (NEUTRAL return), NOT a scoring penalty
- env `UNITY_GDCR=0` to disable
- gate_stats["gate_gdcr"] initialized; _GATE_DISPLAY_LABELS["gate_gdcr"]="GDCR"
- At live WR=29%, DD=49.37%, SR=-4.87 → fires immediately at boot (intentional)

### G8.5W2 — DrawdownMomentum-Sentinel new ultra-extreme tier [v154.0]
- New top tier inserted BEFORE existing ultra-ruin check:
  `if _w2_dd > 48.0 and _w2_sr < -4.0: → -4.0pts`
- Previous top tier (45%+SR<-3.0 → -3.0pts) preserved as second tier
- Banner updated: `(-4.0/-3.0/-2.0/-1.5/+1.5pts)[v89.0/v154.0]`

### G8.5B4 — RollingWR-Momentum-Sentinel threshold tighten [v154.0]
- `elif _b4_wr < 0.27:` → `elif _b4_wr < 0.30:` for -2.0pts tier
- Closes gap at live WR=29% (was falling between tiers)
- Banner updated: `[v115.0/v154.0]`
- Docstring updated: "< 27%" → "< 30% [v154.0: 27%→30%]"

### G8.5H3 — RecentWR-EmergencyBrake new tiers [v153.0, carried into v154.0]
- WR<25% → -1.5pts (mild-crisis, v153.0)
- WR<28% → -1.0pts (warning, v153.0)

## KEY PRINCIPLE CONFIRMED
Only HARD-BLOCKS (not Kelly de-size or scoring penalties) structurally move WR/Sharpe/maxDD.
GDCR is a hard-block → expected to reduce maxDD when active.

## Boot Status
- UNITY_VERSION = "154.0"
- 21/21 layers online
- Clean boot confirmed 2026-06-26
- GDCR fires at boot given live state (DD=49.37%>47.5, WR=29%<30%, SR=-4.87<-4.0)

## Version Bump
- UNITY_VERSION 153 → 154
