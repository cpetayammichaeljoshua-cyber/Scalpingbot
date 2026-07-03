---
name: Unity Engine v192.0 dead-gate fix + overconsensus dampener extension
description: 6 dead-recording gate fixes (v190 sweep missed the v142-v179 soft-gate block) + overconsensus _wr_dampen extended to 20+ triple-consensus meta-gate positive paths
---

## Six dead-recording fixes (v190 mass-fix missed these gates)

v190.0 automated sweep covered gate families up to G8.5A4 (v87–v114 range) plus AA–AL (v157–v163). It did NOT cover:
- G8.5W5/X5 (v142.0) — Winsorization-Guard and ADF Stationarity-Proxy  
- G8.5Y5/Z5 (v143.0) — PCO FLOAM Orthogonality and ICS FLOAM IR Gate  
- G8.5CORR FamilyCorrDampener (v179.0)
- G8.5B4 RollingWR-Momentum-Sentinel (v115.0) — cold-start else branch AND except handler both lacked `_record`

**Pattern:** All five soft-gate gates had `_record()` inside `try: ... except Exception: pass`. Gate B4 additionally had an `else` branch (ring < 8 samples) with no `_record` at all — truly invisible on cold-start.

**Fix applied:** Changed `except Exception: pass` → `except Exception: self._record("gate_...", True)`. For B4 also added `_record("gate_g85b4_rws", True)` to the else/cold-start branch.

**Why True on exception:** neutral/error = no data = pass, consistent with all other non-fatal soft-gate exception semantics across the engine.

**How to apply (audit rule, reusable):** When checking for dead-recording bugs, do NOT just look for `_record` inside `except: pass` blocks — also check:
1. `else` branches (cold-start guards) that set sentinel to 0 but forget `_record`  
2. Cross-check the gate VERSION against the v190 sweep range (v87–v114 + v157–v163); gates outside that range may have been missed

## Overconsensus dampener extension

`_wr_dampen()` (defined v191.0) extended to 20+ positive bonus paths across the triple-consensus meta-gate families:
- G8.5A3–G8.5S3 triple families (VPC / HOS / VOE / RDW / EFO / MLC / etc.)
- G8.5K4/L4/M4 OFI micro-triple family

Negative veto paths kept at full strength — confirmed edge. Only positive "N-of-M agree" bonuses are WR-scaled.

**Why:** Correlated technical signals agreeing is not calibrated evidence of edge in a WR-suppressed regime. Only the negative side (all oppose = something is structurally wrong) has empirical validation. 

**Pattern:** Any gate whose scoring is "count how many sub-signals agree → award bonus pts" needs `_wr_dampen()` on the positive branch before shipping. Check this for every new consensus gate.
