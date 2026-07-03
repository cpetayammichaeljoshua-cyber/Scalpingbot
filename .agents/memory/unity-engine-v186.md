---
name: Unity Engine v186.0 precision bug-fix
description: Four bugs fixed — Torch embargo, CORR avg_pt, CORR missing sentinels v163-v168, SCAN_PARALLEL
---

## Rule
Four precision bugs fixed in v186.0 (no new gates, pure bug-fix release).

**Bug 1 — Torch train/val no embargo (neural_signal_trainer.py ~line 2248)**
GBT/ET walk-forward CV correctly applies `_embargo = min(3, train_end//10)` at ~line 3393.
Torch primary split `X_norm[:-n_val]` had NO embargo → autocorrelated features (OFI ring,
VPIN, EMA, HMM state) spanning the boundary leaked look-ahead bias into training labels.
Fix: `_emb_n = min(5, max(1, n_val // 4))` purge samples removed from end of train set;
`X_tr = X_norm[:-(n_val + _emb_n)]`, `y_tr = y[:-(n_val + _emb_n)]`, `sample_weight` slice
also updated to match. Edge-case safe: N=20 guard already exits before; at min valid N=20,
n_val=4, _emb_n=1 → 15 train samples remain.

**Bug 2 — G8.5CORR _corr_avg_pt over-estimated (start_unity_engine.py ~line 19606)**
`_corr_avg_pt = 1.75` was computed from early symmetric ±1.5/±2.0pt gates.
Newer gates (v163-v175) use asymmetric ±2.0/-1.0 or ±2.0/-1.5 patterns — true weighted avg
absolute contribution is ~1.55-1.65. 1.75 inflated naive_total → understated clawback →
overconsensus under-clipped. Fix: 1.75 → 1.60.

**Bug 3 — G8.5CORR missing sentinels v163-v168 (start_unity_engine.py ~line 19574)**
Same version-block gap pattern as v182.0 analytics wiring bug. v181.0 expansion added
v169-v175 batch but SKIPPED the preceding v163-v168 batch (10 gates):
`_last_g85ak_gsdd`, `_last_g85al_grex` (v163),
`_last_g85am_ghtf`, `_last_g85an_gmap` (v165),
`_last_g85ao_gcal2`, `_last_g85ap_glen` (v166),
`_last_g85aq_grsl`,  `_last_g85ar_gevap` (v167),
`_last_g85as_gfrd`,  `_last_g85at_gord` (v168).
All are loop-engineering/quality-regime score-adjusters firing on WR<30%+quality-degradation
(same family as v169-v175 already in CORR). All _last_ attrs initialized in __init__ at
lines 6452-6461. Sentinel count: 80 → 90.
Note: like v169-v175, these run AFTER CORR in eval sequence → clawback uses prev-eval values
(consistent with existing design).

**Bug 4 — SCAN_PARALLEL_LIMIT 114 → 110**
v178.0 activated 36 previously dead gates that now fully compute each evaluation (was
NameError→silent-skip before v178). CPU per-evaluation materially increased since v178;
reduction justified. No new gates were added in v176-v185 so SCAN_PARALLEL had stayed at 114.

**Why:** All four bugs found via comprehensive multi-parallel codebase scan (version-block gap
pattern recognition + CORR calibration analysis + walk-forward validation audit).

**How to apply:**
- Parity check pattern: whenever a batch of gates is added to CORR, verify the batch
  immediately preceding it wasn't skipped (check version timestamps).
- Torch split embargo must stay in sync with GBT embargo pattern.
- When new gates added with ±asymmetric patterns, re-evaluate _corr_avg_pt calibration.
