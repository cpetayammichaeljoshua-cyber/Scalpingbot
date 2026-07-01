---
name: Unity Engine v169.0 upgrades
description: G8.5AU GWFV (153rd gate) + G8.5AV GDDV (154th gate) + NN v75 390feat + ScanParallel 144→138; v168→169
---

## Gates

**G8.5AU GWFV — Walk-Forward Validation Gap (153rd gate)**
- Technique 4 (Prompt Refinement): system permanently encodes the lesson that live outcomes must match walk-forward CV prediction
- Source A: `self._cpcv_avg_chance` (fraction; -1.0=unset, 0.47=chance floor, 0.50=validated) — confirmed at line 15582
- Source B: `win_rate` (0-100 scale at gate call site)
- Guard: only fires when `_cpcv_avg_chance >= 0.0` (has been computed at least once)
- Case 1: cpcv_avg < 0.47 (model NOT WFV-validated) + WR<30% → -2.0pt
- Case 2: cpcv_avg >= 0.50 (model IS validated) + WR<25% → -1.5pt (regime shift = model edge evaporated)
- Thresholds: GWFV_CPCV_BAD=0.47, GWFV_CPCV_VALID=0.50, GWFV_WR_CRISIS=30.0, GWFV_WR_SHIFT=25.0
- Env: UNITY_GWFV=0 to disable; stores `_last_g85au_gwfv`

**G8.5AV GDDV — Drawdown Velocity via Quality Slope (154th gate)**
- Technique 3 (Extended Thinking): multi-step trajectory analysis — catches pre-DD acceleration before absolute MaxDD thresholds fire
- Source: `self._quality_score_ring` (deque maxlen=8, confirmed at line 6137) — pure-Python linreg slope, zero API
- Requires ≥3 ring entries to compute slope; moderate tier requires ≥5 entries
- Severe: slope < -0.05 + WR<30% → quality collapsing rapidly → -2.0pt
- Moderate: slope < -0.02 + WR<30% + n≥5 entries → declining quality + crisis regime → -1.5pt
- Thresholds: GDDV_SLOPE_SEVERE=-0.05, GDDV_SLOPE_MODERATE=-0.02, GDDV_MIN_ENTRIES=5, GDDV_WR_GATE=30.0
- Env: UNITY_GDDV=0 to disable; stores `_last_g85av_gddv`

## Kelly Steps

**Step 148 (GWFV):** CPCV-invalid+crisis → ×0.82 | regime-shift → ×0.86
**Step 149 (GDDV):** severe quality collapse → ×0.81 | moderate decline → ×0.87

## NN v75 (390 features, F386-F390)

- F386: `au_gwfv_gate` — GWFV state {-2.0→0.0, -1.5→0.2, 0→0.5}
- F387: `cpcv_wfv_gap` — (cpcv_avg − win_rate/100) × 5, capped [-1,+1]; positive = model overpredicts live (regime shift); 0.0 when cpcv_avg unset
- F388: `av_gddv_gate` — GDDV state {-2.0→0.0, -1.5→0.2, 0→0.5}
- F389: `quality_slope_norm` — linreg slope of quality_score_ring / 0.1, capped [-1,+1]; negative = quality declining
- F390: `wfv_regime_score` — composite [0,1]: CPCV valid (0/0.5/1.0) + quality improving (0.5/1.0) + GWFV clear (0/1.0), normalized /3.0

## Railway Efficiency

**ScanParallel:** 144 → 138 (-4.2% CPU)
- Cumulative v163→v169: 192 → 138 (−28.1% Railway asyncio load)

## Architecture Counts

- Gates: 152 → 154
- Kelly steps: 147 → 149
- NN features: 385 → 390 (v74 → v75)
- SCAN_PARALLEL_LIMIT: 144 → 138
- UNITY_VERSION: 168.0 → 169.0

**Why:** GWFV directly addresses "walk forward validation" — when CPCV says the model has no validated edge (< chance floor), the bot has been given explicit permission by the data to reduce sizing. GDDV catches the inflection point of quality degradation before the MaxDD threshold gates fire — trading the slope trend, not the level. Both are zero-API, pure-Python, no Railway cost increase.
