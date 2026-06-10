---
name: Unity Engine v53.0 gate analytics fixes
description: Four fixes found from live Railway log analysis — soft-gate false bottleneck, GOFI zero-call, G8.5w direction-guard, consortium timeout.
---

## 1. Soft gates dominate bottleneck HUD (gate_bottleneck_str)

**Problem:** G8.5w=0%(#1) G8.5x=0%(#2) appeared every session, hiding real bottleneck G0.5=61%.

**Root cause:** Quality-adjuster gates (G8.5w, G8.5x, G8.5V, GMK/Markov) record "fail" when no kline buffer data is available at cold start. Since they CANNOT hard-veto a signal, a 0% pass rate = "no data", not a true bottleneck.

**Fix:** Added `_SOFT_GATE_KEYS = frozenset({gate_g85w, gate_g85x, gate_vibe, gate_markov})` exclusion inside `gate_bottleneck_str()`. These soft gates still appear in `gate_stats_summary()` and `/gates` — just excluded from the worst-3 bottleneck HUD.

**How to apply:** Any future quality-adjuster gate (no hard-veto) should be added to `_SOFT_GATE_KEYS` inside `gate_bottleneck_str()`.

## 2. GOFI zero-call bug — three missing _record() paths

**Problem:** GOFI only called `_record("gate_ofi", True)` inside `if _aligned and _ofi_bonus > 0`. Three paths never recorded:
- (a) `abs(_ofi_z) < 0.5` — noise envelope (most evaluations)
- (b) `_aligned` but `_ofi_bonus == 0` — weak alignment, no bonus
- (c) `not _aligned and _z_mag < VETO_SIGMA` — opposed but below veto threshold

**Fix:** Moved `self._record("gate_ofi", True)` outside the bonus-if (covers cases b+c), added `else: self._record("gate_ofi", True)` for the noise-envelope case (a). False only on hard veto (OFI_OPPOSED).

**Pattern:** Any gate where `_record()` is nested inside multiple conditionals is at risk of zero-call. Always ensure `_record()` is called for every signal evaluation path through the gate block.

## 3. G8.5w direction-guard position bug

**Problem:** `_g85w_fired = False` and `self._record("gate_g85w", _g85w_fired)` were BOTH inside `if _g85w_dir in ("BUY","LONG","SELL","SHORT")`. If direction was empty/None/malformed, `_record()` was never called → G8.5w showed 0% evaluations as false bottleneck #1.

**Fix:** Moved `_g85w_fired = False` BEFORE the direction guard, moved `self._record(...)` AFTER (outside) the direction guard. Now always records every evaluation.

**Pattern:** `_record()` for any gate must be reachable regardless of guard conditions. Place the flag init and record call OUTSIDE any guard that might skip the entire block.

## 4. CONSORTIUM timeout 14.0 → 16.0

**Evidence:** Live Railway log showed `gpt-oss-120b:free` responding at 12195ms (12.2s) — only 1.8s below the 14s cutoff. Only 1/8 models responded → CONSORTIUM fell back to ULTRAPLINIAN every call (requires ≥2 responses for ensemble).

**Fix:** `_CONSORTIUM_TIMEOUT = 16.0` (effective 16+3=19s with outer guard). Gives 2+ additional models a chance to respond and form a valid ensemble.

**Why not higher:** 18s+ was the previous value and was dropped to 14s for speed. 16s is the measured middle point — covers the 12-16s latency range seen in Railway without regressing to the 21s old effective timeout.

## 5. Identifying zero-call gates from live logs

**Process:** Run `grep -n "_record\|gate_stats\|gate_bottleneck" start_unity_engine.py` to find all gate recording sites. For each gate, check:
1. Is `_record()` inside a conditional that might not execute? → Bug (move outside)
2. Is `_record()` only in the "bonus/fail" branch but not the "pass-through" branch? → Bug (add else)
3. Is the gate a quality-adjuster (no hard veto)? → Should be in `_SOFT_GATE_KEYS` for bottleneck exclusion

GOFI, GCUS, GLIQ, G8.5w have historically had this pattern. GCUS still only records when ≥30 samples — cold-start safe by design.
