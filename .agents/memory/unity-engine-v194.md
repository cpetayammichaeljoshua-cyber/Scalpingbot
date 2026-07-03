---
name: Unity Engine v194.0 overscoring sweep — foundational bonus paths
description: 7 large unchecked positive-bonus paths (G2/G2.5/G2.5b/G2.5c/G5/ISB) now WR-dampened; banner gate count corrected to 176
---

## Overscoring sweep: foundational early-path bonuses now WR-dampened

Prior dampener sweeps (v179/v189/v191/v192) targeted specific gate families but missed the foundational quality bonuses that fire on *every* signal — these were structurally identical overscoring risks.

### 7 paths fixed with _wr_dampen():

1. **G2 swarm consensus**: `min(20.0, consensus * 20.0)` → `_wr_dampen(min(20.0, consensus * 20.0))`. Max +20pts raw → +14pts at WR=25%. No-swarm neutral baseline (10pts) explicitly preserved — it is not a consensus signal.
2. **G2.5 bookmap aligned flow**: `+5.0/+2.0` → `_wr_dampen(5.0 or 2.0)`. Pure confluence bonus, not an independent edge.
3. **G2.5b pattern recognition positive**: `quality_score += _g25b_adj` → `quality_score += self._wr_dampen(_g25b_adj)`. Was up to +8.0pts raw.
4. **G2.5c volume confirmation ×4 tiers**: all +5.0/+3.0/+2.0/+1.0 wrapped with `_wr_dampen()`. Volume ratio correlates with swarm/bookmap signals.
5. **G5 ATAS+Bookmap dual alignment**: `+10.0` → `_wr_dampen(10.0)`; `+5.0` → `_wr_dampen(5.0)`. Highest unchecked raw bonus in engine was +10pts.
6. **ISB Intelligence Singularity Bonus**: `+5.0` → `_wr_dampen(5.0)`. Dual-SOVEREIGN still fires in low-WR regimes when SOVEREIGN thresholds themselves may be miscalibrated.
7. **_wr_dampen** total call count: 7 → 46 across engine (previous sweeps: 39 calls from v192 triple-consensus families).

## Banner gate count corrected

- **Before**: "168-gate filter" (stale since v191/v192 additions)  
- **After**: "176-gate filter" (actual `_GATE_DISPLAY_LABELS` count, Python-verified: 176 entries at lines 22242–22430)  
- Both architecture header banner AND runtime launcher banner (line ~34600) updated.

**Why:** `_GATE_DISPLAY_LABELS` is the ground truth — it is what `/gates` endpoint renders. The `_gate_stats_recent` has 189 keys (includes internal tracking not exposed in display). The `_SOFT_GATE_KEYS` has 161 entries (subset). Always count `_GATE_DISPLAY_LABELS` for the user-facing gate count.

## Rule: complete coverage of all quality_score += paths

When auditing for overscoring, prior sweeps only targeted gate-family classes. The correct audit scope is **every** `quality_score +=` or `quality_score -=` path in the engine, not just consensus-class gates. The foundational G2/G5 bonuses were missed for 193 versions because they predated the dampener concept and were considered "structural."

**How to apply:** grep `quality_score +=` and check every positive path ≥ +1.0 against whether it has `_wr_dampen()` or a documented reason why not (e.g., IRONS final-range bonus is post-gate and intentional; no-swarm-data neutral baseline is not a bonus).
