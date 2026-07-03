---
name: Unity Engine v195.0 overscoring sweep round 4
description: 7 highest-weight positive-bonus paths WR-dampened (Gates 1/3/4/6/7b/GLTB/GCMS); total self._wr_dampen() call sites 40→47
---

## What changed
Power-mode scan round 4 — overscoring sweep continued from v194. Four-way parallel scan identified 7 remaining unguarded `quality_score +=` paths with raw bonuses ≥ +2.0 pts that were not wrapped in `_wr_dampen()`.

## 7 paths fixed

| Path | Gate | Raw max | Fix |
|---|---|---|---|
| G1 R:R margin bonus | Adaptive R:R | +20.0 pts | `_wr_dampen(min(20.0, rr_margin/range*20))` |
| G3 AI confidence | AI Confidence | +20.0 pts | `_wr_dampen(min(20.0, conf/100*20))` |
| G4 NN probability | Neural Network | +15.0 pts | `_wr_dampen(min(15.0, nn_prob*15))` |
| G6 F&G quality | Fear & Greed | +11.25 pts | `_wr_dampen(fg_quality*7.5*_fg_dir_mult)` |
| G7b BS Greeks IV skew ×2 | IV Skew | +2.0 pts | `_wr_dampen(2.0)` both branches |
| G8.5BA-GLTB positive tiers | Loop-Eng DirBias | +1.5/+1.0 | conditional `_wr_dampen(_gltb_adj) if _gltb_adj > 0` |
| G8.5BB-GCMS positive tiers | Checker MetaScore | +2.0/+1.5 | conditional `_wr_dampen(_gcms_adj) if _gcms_adj > 0` |

## Key architectural notes

**Why G1/G3/G4/G6 needed dampening:**
- These are "structural quality gates" — they feel like objective signal metrics, but at WR=25-29%, they are ALL miscalibrated. A 95% AI confidence or 90% NN probability when strategy WR is 25% means the model is overfit/wrong in the current regime.
- Prior sweeps (v179/v189/v191/v192/v194) targeted consensus-class and confluence-class bonuses. v195 targets the core signal-metric bonuses.

**Why GLTB/GCMS use conditional dampening:**
- These gates have positive AND negative branches (`_gltb_adj` can be +1.5/+1.0/-1.5/-2.0).
- Only positive branch is dampened; negative penalty stays at full raw value.
- Outer guard `if _gltb_adj != 0.0` means zero case never hits the ternary — correct.
- GLTB/GCMS have INTERNAL WR gates (GLTB_WR_STRONG=32%, GCMS_WR_ULTRA=32%) that protect the positive branch locally. The global `_wr_dampen` adds cross-scope protection when global engine WR differs from local ring WR.

## Scan findings — still unguarded (future v196+ scope)
Code review identified these pre-existing unguarded paths not addressed in v195:
- Line ~8773: EV bonus (`min(10.0, ev/0.005*10)`)
- Line ~9249: Liq bonus
- Line ~9274: TP1 proximity bonus
- Lines ~13847, ~14335, ~14962, ~16788, ~17126, ~17224, ~17337, ~17408, ~21455: various G8.5 meta-gate +2/+2.5 paths

**Policy recommendation:** Classify as "expected-value signal bonus" (should dampen) vs "gate-pass credit" (borderline). EV bonus at line ~8773 is especially large (+10pts) and should be priority for v196.

## State
- UNITY_VERSION: 195.0
- Total `self._wr_dampen(` call sites: 47 (grep-verified)
- Syntax: clean (ast.parse OK)
- Boot: ✅ UNITY ENGINE v195.0 — ALL SYSTEMS ONLINE
- CPCV/WF: clean (v193 fix confirmed intact)
- Dead gates: clean (v190/v192 fixes intact, all v165-v176 gates verified wired)
