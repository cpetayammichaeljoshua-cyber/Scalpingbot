---
name: Unity Engine v155.0 upgrades
description: GDCR death-spiral fix (time-release valve), GMDR hard-block Phase 1.99, GCLH ultra-crisis tier, G8.5U4 sub-GDCR tier; version 154→155
---

## Changes in v155.0

### GDCR Time-Release Valve (CRITICAL death-spiral fix)
- **Problem**: GDCR (DD>47.5%+WR<30%+SR<-4.0) permanently blocked all signals because no new wins could improve WR/SR while blocked — true death spiral
- **Fix**: After 4h continuous GDCR block (`self._gdcr_block_start`), allow ONE signal per 2h (`self._gdcr_last_relief`) to let engine accumulate wins and lift condition
- **New attrs**: `self._gdcr_block_start: float = 0.0` and `self._gdcr_last_relief: float = 0.0` (added after `self._gclh_until` ~line 5518)
- **Condition resets**: `self._gdcr_block_start = 0.0` when GDCR condition clears (else branch)
- **Env**: `UNITY_GDCR_RELEASE=0` to disable (reverts to v154 permanent-block behaviour)
- **Thresholds**: 14400s (4h) elapsed + 7200s (2h) since last relief → allow 1 signal through

### GMDR Pre-Gate (Phase 1.99) — New HARD-BLOCK
- **Purpose**: Closes structural gap between GCLH (3 losses, no DD awareness) and GDCR (DD>47.5% triple-crisis)
- **Condition**: MaxDD > 43.0% AND WR < 28% AND consec_losses ≥ 2 → 1800s (30min) block
- **New attr**: `self._gmdr_until: float = 0.0` (added after `self._gdcr_last_relief`)
- **gate_stats**: `"gate_gmdr": {"pass": 0, "fail": 0}` added after gate_gdcr entry
- **_GATE_DISPLAY_LABELS**: `"gate_gmdr": "GMDR"` added after gate_gdcr
- **Env**: `UNITY_GMDR=0` to disable
- **Ordering**: After GDCR gate, before CB (hard cutoff) — Phase 1.99

### GCLH Ultra-Crisis Tier (Phase 1.97b)
- **New tier**: WR < 26% AND consec_losses ≥ 2 → 1800s (30min) block
- **Fires BEFORE** existing standard tier (WR<28.5% + 3 losses → 1h)
- **Rationale**: At WR<26% (deep crisis below 28.5% floor), 2 consecutive losses are statistically sufficient evidence of adverse selection. Fires 1 loss earlier than standard tier.
- **Message**: "GCLH: Phase 1.97b ultra-crisis WR<26%..."

### G8.5U4 Sub-GDCR Tier (v155.0 new scoring tier)
- **New tier**: WR<30% AND SR<-3.0 AND DD>44.0 → -2.0pts
- **Fills gap**: At DD=44-47.5% (below GDCR threshold), WR=29%, SR=-3.5 the prior code gave 0 pts; now gives -2.0pts
- **Tier order** (elif chain): -4.0 → -3.0 → -2.5 → -2.0 (new) → +1.5 (healthy)
- Also confirmed v151.0 tier (WR<30%+SR<-4.0+DD>47% → -2.5pts) in same elif chain

## Boot validation
- 21/21 layers online ✓
- v155.0 confirmed in launcher and capability stamp ✓
- GMDR gate_stats registered, _GATE_DISPLAY_LABELS registered ✓

## Key principles confirmed
- HARD-BLOCKS only move WR/Sharpe/maxDD (scoring gates don't)
- GDCR death spiral: permanent block → no new wins → metrics can't improve → CONFIRMED REAL
- Time-release valve breaks the spiral while maintaining structural protection
- Phase ordering: GASN→GEUT→GVSP→GSLK→GCLH→GDCR→GMDR→CB
