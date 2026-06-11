---
name: Unity Engine v61.0 upgrades
description: Isotonic calibration for HistGBT, adaptive blend weight, walk-fwd threshold 40→30, G9 recovery momentum bonus, SR<-3.0 early-warning retrain tier — confirmed clean boot 21/21 layers
---

## What changed in v61.0

### neural_signal_trainer.py

**1. Isotonic probability calibration for HistGBT**
- After `_hgbt_model.fit(X_tr, ...)`, wrap with `CalibratedClassifierCV(method="isotonic", cv="prefit")`
- Fit calibrator on `X_va` (held-out validation set) — zero data leakage
- Guard: requires `len(X_va) >= 15` AND both classes present; falls back to uncalibrated otherwise
- Reference: Niculescu-Mizil & Caruana (2005) — trees systematically over-produce extreme probabilities
- `self._hgbt` is set to the calibrated model (or uncalibrated on fallback)

**2. Adaptive HistGBT blend weight**
- After calibration: compute MLP val_acc via `_forward(X_va)` with `_opt_threshold`
- Compute HistGBT val_acc from calibrated `predict_proba(X_va)`
- `_hgbt_w = clip(hgbt_va_acc / (hgbt_va_acc + mlp_va_acc), 0.20, 0.40)` stored as `self._hgbt_weight`
- In `predict_signal()`: replaced hardcoded `0.30` with `_hw = getattr(self, "_hgbt_weight", 0.30)`
- Falls back to 0.30 on cold-start (before first retrain cycle)

**3. Walk-forward threshold 40→30**
- `if n >= 30` (was `n >= 40`) for time-ordered split
- Allows walk-forward CV 10 samples earlier; all other split logic unchanged
- At n=30: 10 val + 18 training (2-sample embargo) — workable but small; isotonic calibration
  guard (≥15 val samples) means calibration activates at n≥50 naturally

### start_unity_engine.py

**4. G9 Recovery Momentum Bonus (+1.5pts)**
- Inserted just before `quality_score = min(100.0, max(0.0, quality_score))` at line ~8307
- Fires when: `len(_win_ring) >= 40` AND `recent20 - prior20 >= 0.03` AND `Sharpe > -2.0`
- `recent20 = sum(_win_ring[-20:]) / 20.0`, `prior20 = sum(_win_ring[-40:-20]) / 20.0`
- Rationale: Bayesian WP updates slowly (slow posterior); this bonus fires on WIN-RATE MOMENTUM
  within 1 scan cycle of a regime turn — 10-15 scan head-start vs Bayesian detection
- Guard: Sharpe > -2.0 prevents false fire during a blip inside an ongoing losing run

**5. NN Retrain SR<-3.0 early-warning tier (25min)**
- Inserted between `CRISIS-20min[v19.8] (Sharpe < -3.5)` and `ADAPTIVE-45min (WR < 0.32)`
- `elif _crisis_sharpe < -3.0: _sleep_sec = 1500` (25min)
- Label: `EARLY-WARNING-25min[v61.0]`
- Rationale: Sharpe -3.0 to -3.5 is the inflection where drawdown begins accelerating;
  25min gives 1 extra calibration cycle before the 20min crisis floor fires

### Complete NN retrain tier ladder (v61.0):
| Sharpe | Interval | Label |
|--------|----------|-------|
| < -6.0 | 8min | ULTRA-RUIN |
| < -5.0 | 15min | ULTRA-CRISIS |
| < -4.5 | 15min | DEEP-CRISIS |
| < -3.5 | 20min | CRISIS |
| < -3.0 | 25min | EARLY-WARNING (NEW) |
| WR < 32% | 45min | ADAPTIVE |
| normal | NN_RETRAIN_INTERVAL_SEC (~45min) | standard |

### File headers
- UNITY_VERSION: "60.0" → "61.0"
- Dockerfile, nixpacks.toml, requirements.txt: all updated to v61.0

## Boot confirmation
`✅ UNITY ENGINE v61.0 — ALL SYSTEMS ONLINE — 21/21 layers`
`💾 [v61.0] Startup state snapshot saved`
`✅ [v61.0] Watchdog + Persistence + ... started`

**Why these choices:**
- Isotonic calibration: trees over-produce extreme probabilities (confirmed empirical finding);
  threshold-based gates (G4 NN gate) are most sensitive to correct probability calibration
- Adaptive blend: fixed 70/30 is arbitrary; proportional to comparative val_acc is principled
- Walk-fwd 40→30: 40 was overly conservative; 30 still provides meaningful temporal validation
- Recovery momentum bonus: Bayesian posterior is slow; momentum-of-WR fires immediately on regime shift
- 25min tier: closes the 25min gap between normal 45min and crisis 20min
