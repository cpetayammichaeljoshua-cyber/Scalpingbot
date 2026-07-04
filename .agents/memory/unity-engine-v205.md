---
name: Unity Engine v205.0
description: 3 fixes — gate_g85m/n missing from _SOFT_GATE_KEYS; swarm +10 no-swarm-data path not WR-dampened; stale banners (166-gate/Steps1-149)
---

# Unity Engine v205.0 — SOFT_GATE_KEYS gap + swarm no-data dampener + banner fixes

## Fixes Applied

### 1. gate_g85m + gate_g85n missing from `_SOFT_GATE_KEYS`
- Both gates (BTC Macro GEX, Multi-Asset FLIP ZONE) are quality score adjusters, NOT hard blockers
- They were in `_GATE_DISPLAY_LABELS` (lines 22585-22586) but NOT in `_SOFT_GATE_KEYS`
- Without being in `_SOFT_GATE_KEYS`, `gate_bottleneck_str()` treated them as hard gates → they appeared as top fake blockers in analytics
- Fix: added both to `_SOFT_GATE_KEYS` before `gate_g85bi_gsev` entry (line ~22931)
- **Pattern**: Any time a gate is wired with `self._record()` but only applies quality_score adjustments (never returns False to block), it MUST be in `_SOFT_GATE_KEYS`

### 2. Swarm +10 no-swarm-data path not WR-dampened
- G2 gate: `quality_score += 10.0 if _no_swarm_data else self._wr_dampen(min(20.0, consensus * 20.0))`
- The consensus path was WR-dampened (v194.0) but the no-data +10.0 baseline was raw
- At WR=25%, every symbol without swarm data got +10.0pts regardless of regime → overscoring
- Fix: `quality_score += self._wr_dampen(10.0) if _no_swarm_data else ...`
- **Why**: v194.0 sweep caught the consensus*20 path but left the else branch raw — always check both sides of a ternary when one side is dampened

### 3. Stale banner strings
- Architecture banner: "166-gate filter" → "167-gate filter" (v201.0 added G8.5BI GSEV as 167th)
- Architecture banner: "Kelly(Steps1-149·" → "Kelly(Steps1-162·" (Kelly Step 162 added v201.0)
- Signal filter banner: "166-GATE SIGNAL FILTER" → "167-GATE SIGNAL FILTER"

## False Alarms Cleared This Session
- "46 dead-recording gates" (gate_g85a5_svc through gate_g85z4_arc) — these use DIRECT dict access `_gate_stats["key"]["pass"/"fail"] += 1` instead of `self._record()`. Both approaches are valid. The direct approach skips `_record()` but still updates `_gate_stats` and `_gate_stats_recent` identically. NOT a bug.
- ISB `_isb_pts` already WR-dampened: `_isb_pts = self._wr_dampen(5.0)` at line 21870 ✅
- Vibe `_vibe_applied` already WR-dampened: `_vibe_applied = self._wr_dampen(_vibe_delta)` at line 21832 ✅
- GEX bonuses already WR-dampened via `_gex_wr_mult` multiplier (floor 0.70 post-v203.0) ✅

## Boot Confirmation
- v205.0 clean boot: 21/21 layers, Semaphore(110), all WS connected
