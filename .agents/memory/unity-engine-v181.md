---
name: Unity Engine v181.0 upgrades
description: G8.5CORR +15 sentinels (v127+v169-v175 families) + G8.5V/G8.5sq/G8.5q dead-recording fixes + IRONS docstring/banner corrections
---

## Rules

### G8.5CORR dampener now covers 80 sentinels (was 65)
Missing families added in v181.0:
- `_last_g85a5_svc` (v127.0 SVC Sharpe-Velocity-Confluence) — was missing since v179.0 introduction
- v169-v175 float-sentinel gates: `_last_g85au_gwfv`, `_last_g85av_gddv`, `_last_g85aw_ghrz`, `_last_g85ax_galp`, `_last_g85ay_gvlr`, `_last_g85az_grlb`, `_last_g85ba_gltb`, `_last_g85bb_gcms`, `_last_g85bc_gdsa`, `_last_g85bd_gevl`, `_last_g85be_grdc`, `_last_g85bf_gxwi`, `_last_g85bg_gpel`, `_last_g85bh_glcv`

**Why:** The dampener's int() cast correctly handles float sentinels (e.g., -2.0 → -2, +1.5 → +1, 0.0 excluded). Any new float-sentinel gate from v169+ should be added here.

**How to apply:** When adding a new score-adjuster gate that stores a float sentinel (e.g., `_last_g85XX_yyy: float`), add it to `_corr_sentinels` in G8.5CORR simultaneously.

### G8.5V vibe gate _record fix
`_vibe_delta = 0.0` initialized OUTSIDE the `if symbol and direction and self._vibe_pool is not None:` block. `self._record("gate_vibe", _vibe_delta >= 0)` called OUTSIDE the try/except. Exception path defaults to _vibe_delta=0.0 → records as pass (neutral).

### G8.5sq (StochasticQuant) wiring — fully dead before v181.0
Gate existed since v19.0 but had NO `self._record()`, NO `_gate_stats` init, NO `_GATE_DISPLAY_LABELS`, NO `_SOFT_GATE_KEYS`. Fixed via `_sq_adj_outer = 0.0` before the if-block; `_sq_adj_outer = _sq_adj` inside inner try; `self._record("gate_g85sq", _sq_adj_outer >= 0.0)` after except.

### G8.5q (QuantDinger) wiring — fully dead before v181.0
Same issue as G8.5sq. Gate key is `"gate_g85q"` (distinct from `"gate_g85q_trendmom"` which is the v84.0 TrendMomentum gate). Fixed via `_q_adj = 0.0` before try; `self._record("gate_g85q", _q_adj >= 0.0)` after except. NOTE: there is a separate `_q_adj` variable used in the G8 DYN gate block (~line 12401) — no collision because it's in a different scope (earlier in the function, not in same block).

### IRONS docstring + Gate 10 banner stale values (v181.0 fix)
- `update_adaptive_irons` docstring was showing v147.0 values (base=75). Corrected to v152.0+ values: WR<18%=80, WR18-20%=79, WR<25%=78.5, WR<30%=77, WR30-45%=72.
- Gate 10 banner showed `WR<20%→80` (wrong — that's WR<18%). Fixed to `WR18-20%→79 | WR<18%→80`.

**Why:** Two separate tiers were collapsed in the banner (WR<18% and WR18-20% both showed "80"). The docstring had never been updated since v147.0 despite IRONS_MIN_WR_BELOW30 bumping from 75→77 in v152.0.

### Scan findings confirmed clean (no action needed)
- Swarm 0.99 threshold: NOT a dead branch. 10/10 unanimous MiroFish agents produce consensus=1.0 ≥ 0.99. Reachable.
- gate_g85d/e/f/g/h/i already in `_SOFT_GATE_KEYS` (scan agent was wrong).
- gate_g85j_hmm and gate_g85k_spread (not gate_g85j/k bare) are in SOFT_GATE_KEYS correctly.
- walk-forward backtest: 6-fold purged+embargoed CPCV confirmed anti-overfitting intact.
