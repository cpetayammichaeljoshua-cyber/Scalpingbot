---
name: Unity Engine v210.0 — CORR sentinel gap v121-v127 era
description: 10 gates from v121.0-v127.0 era missing from G8.5CORR clawback sentinel list since introduction; same gap pattern as v186.0/v204.0/v180.0
---

## Rule
G8.5CORR sentinel count: 95 → 105. Any gate added to the engine that stores a ±/0 sentinel variable must also be added to the `_corr_sentinels` tuple in `_score_signal()`.

## What Was Fixed
Gates O4/P4/Q4 (v121.0), R4/S4 (v123.0), V4/W4 (v125.0), X4/Y4 (v126.0), Z4 (v127.0) were fixed for WR-dampening in v209.0 but their sentinel attribute names were never inserted into `_corr_sentinels`. When these 10 gates all fired positive votes simultaneously (trending regime), CORR `_corr_pos` was undercounted → naive_total less clipped → overscoring slipped through in exactly low-WR high-consensus regimes where CORR is most needed.

Sentinel names added:
- `_last_g85o4_ev_vel` (O4), `_last_g85p4_wra` (P4), `_last_g85q4_mec` (Q4)
- `_last_g85r4_sow` (R4), `_last_g85s4_sqc` (S4)
- `_last_g85v4_erv` (V4), `_last_g85w4_wac` (W4)
- `_last_g85x4_svr` (X4), `_last_g85y4_ows` (Y4)
- `_last_g85z4_arc` (Z4)

Also fixed: stale docstring header "v204.0" → "v210.0"; UNITY_VERSION "209.0" → "210.0".

**Why:** CORR sentinel tuple gaps consistently reappear at era boundaries (v119-v120, v163-v168, v169-v175, v204 m/n, now v121-v127). Every version bump that adds new gates to `_last_g85*` sentinels must verify CORR inclusion.

**How to apply:** After adding any new `_last_g85XX_YYY` sentinel, grep `_corr_sentinels` and confirm the new attribute appears. If missing, add it to the appropriate era comment block.
