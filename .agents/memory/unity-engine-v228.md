---
name: Unity Engine v228.0 — Kelly Steps 27/32/33/34/35 missing _kGSEV guard
description: 5 Kelly boost steps (27 Sortino, 32 OFI-Persist, 33 EnsembleConf, 34 CrossCoherence, 35 AVWAP) had WR guards but no GSEV crisis guard — boost could fire while GSEV ×0.84 de-size also fires.
---

# Root cause
`_kGSEV` (shared GSEV bool, `_last_g85bi_gsev > -1.5`) was only defined **after** Step 35 (line ~25487, v225.0), so Steps 27/32/33/34/35 were outside its scope. These steps got per-step WR guards in v221.0 but the GSEV guard pattern from v220.0 (Steps 19/20/21/26) was never extended to them.

**Why:** Steps 32–35 are early steps with own local `_kXX_wr` re-computations; the shared `_kW`/`_kGSEV` block was designed for Steps 36–162 ternary pattern. Steps 32–35 and 27 used a different coding pattern and were not audited for GSEV coverage.

# Fix
- Moved `_kGSEV` computation block from after Step 35 → **before Step 27** (now covers Steps 27–162)
- Added `and _kGSEV` to boost-path condition in all 5 steps:
  - Step 27 (Sortino ×1.05): `_k27_srt > 2.0 and _k27_wr > 0.35 and _kGSEV`
  - Step 32 (OFI-Persist ×1.08): `_k32_aligned == 3 and _k32_wr >= 0.32 and _kGSEV`
  - Step 33 (EnsembleConf ×1.07): `_k33_unc < 0.08 and _k33_wr >= 0.32 and _kGSEV`
  - Step 34 (CrossCoherence ×1.06): `_k34_votes == 3 and _k34_wr >= 0.32 and _kGSEV`
  - Step 35 (AVWAP ×1.04): full condition + `and _kGSEV`
- De-size paths in all 5 steps are **unmodified** (crisis de-sizing always fires)

# Guard architecture map (complete after v228)
| Steps | WR guard | GSEV guard | Fixed in |
|-------|----------|------------|----------|
| 1–18, 22–26 | N/A or Sharpe | Per-step inline | v220.0 |
| 19/20/21 | Sharpe | `_gsev19/20/21 > -1.5` inline | v220.0 |
| 26 | N/A | `_gsev26 > -1.5` inline | v220.0 |
| **27/32/33/34/35** | per-step `_kXX_wr` | **`_kGSEV` (shared)** | **v228.0** |
| 36–162 | `_kW >= 0.30` (shared) | `_kGSEV` (shared) | v225.0/v226.0 |

**How to apply:** Any new Kelly boost step added between 27 and 35 must also add `and _kGSEV` to its boost condition. Any step at 36+ uses the ternary pattern `if _kW >= 0.30 and _kGSEV else self.last_kelly_fraction`.
