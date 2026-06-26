---
name: Unity Engine v153.0 upgrades
description: SOVEREIGN_RECOVERY_GATE 75→77 coherence fix + G8.5H3 EWB crisis tier extension (WR<25%→-1.5pts / WR<28%→-1.0pts) + KEY GATES banner update + CB constant disambiguation
---

## Changes Shipped

**SOVEREIGN_RECOVERY_GATE 75→77** (line 3165)
- Env default `"75.0"` → `"77.0"`. Three-tier coherence: G9=73 + G10/SOVEREIGN=77 + WR<20%=80.
- CRITICAL FIX: IRONS=75-76 signals were passing the SOVEREIGN path while failing the IRONS crisis floor — incoherent gate. Signals need to fail BOTH walls consistently.
- Ultra-crisis WR<23% → SOVEREIGN_RECOVERY_GATE+2 = 79 (auto-scaled by existing code at line 18758).

**G8.5H3 RecentWR-EmergencyBrake extended (v103.0/v153.0)**
- Added 2 new tiers to fill the 20-40% neutral dead zone at live WR=29%:
  - WR<25% → **-1.5pts** (mild-crisis; `_last_g85h3_ewb` stays 0, no Kelly Step 60 trigger)
  - WR<28% → **-1.0pts** (warning; `_last_g85h3_ewb` stays 0, scoring only)
- Full tier stack: WR<15%→-3.0 / WR<20%→-2.0 / WR<25%→-1.5 / WR<28%→-1.0 / [28-40% neutral] / WR>40%→+1.5
- KEY INSIGHT: at G9 floor=73, a -1.5pt penalty pushes borderline composite scores (73-74.5) below the floor → becomes effective hard-block for marginal signals.
- `_last_g85h3_ewb` value semantics unchanged (-2/-1/0/+1); new tiers map to 0.

**KEY GATES banner** (line 1177-1179)
- Version: v150.0 → v153.0
- IRONS_MIN: 75→77 (base), 76.5→78.5 (WR<25%), 78→80 (WR<20%/WR<18%)
- SIGNAL_QUALITY: 72→73
- SOVEREIGN_RECOVERY: 75→77
- Added: G8.5Q4/G8.5H3 explicit tier descriptions

**Architecture banner** (line 25974)
- `CB5[v59.0]` (soft threshold, still correct) restored with `CBHard4[v147.0]` tag added to document the hard cutoff separately.

**Gate 10 boot log** (line 26005)
- Updated to v153.0 with SOVEREIGN=77 added to the label.

## CB Constant Disambiguation (CRITICAL LESSON)

Two separate CONSEC_LOSS constants exist — do NOT confuse them:
- `CONSEC_LOSS_THRESHOLD = 5` — SOFT CB: raises dynamic threshold by 3% for 30min after 5 consecutive losses (set v59.0, unchanged). The boot banner `Consec-Loss CB(5)` correctly shows this.
- `CONSEC_LOSS_HARD_CUTOFF = 4` — HARD CB (GCLH): blocks ALL signals when streak ≥ 4 (set v147.0). Separate gate, separate constant.
- The architecture banner tag `CB5[v59.0]` was NOT stale — it refers to the soft threshold. Changing it to `CB4` would be incorrect.

**Why:** The session scratchpad incorrectly flagged CB5 as stale based on CONSEC_LOSS_HARD_CUTOFF=4. The two constants serve different purposes; the boot banner dynamically pulls CONSEC_LOSS_THRESHOLD which is correctly 5.

## Live State at v153.0 Boot
- WR=29.0%, W=812, L=1986, Sharpe=-4.87, MaxDD=49.37%, F&G=13 Extreme Fear
- IRONS MinReq=77(adapt) confirmed in console
- 21/21 layers online, 136-gate filter active
- Quality≥73 confirmed in gates banner
