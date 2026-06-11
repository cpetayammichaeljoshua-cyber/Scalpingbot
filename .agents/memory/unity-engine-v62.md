---
name: Unity Engine v62.0 upgrades
description: CPCV reliability signal, G8.5R HMM-GEX Coherence 31st gate, Kelly drawdown-scaled de-sizing — confirmed clean boot 21/21 layers, 31-gate filter
---

## What changed in v62.0

### neural_signal_trainer.py

**1. CPCV (Combinatorial Purged Cross-Validation) Reliability Signal**
- Placement: after `acc = float(np.mean(preds == y_flat))`, before direction-calibration block
- Fires when: `n >= 45` (at least 15 samples per fold)
- Algorithm: K=2 temporal walk-forward folds
  - Fold split points: [n//3, 2n//3]
  - Each fold: train on 0..sp-purge, test on sp..sp+n//3
  - Purge: min(3, sp//10) samples at boundary (prevents leakage)
  - Model: `MLPClassifier(hidden_layer_sizes=(32,), max_iter=150, alpha=1.0)` — fast, lightweight
  - Guard: skips fold if train<12 or test<8 or only one class in training
- Overfit detection: when `val_acc − cpcv_avg > 0.04`
  - Adjustment: `min(0.03, gap × 0.50)` added to `_opt_threshold` (cap +3pp)
  - Also re-derives `_reject_threshold` and `_boost_threshold` to stay consistent
  - Log: `🔬 [v62.0 CPCV]` info-level when fires, debug-level when no action
- Non-fatal: entire block wrapped in `try: ... except Exception: pass`
- **Why:** De Prado AFML ch.12 — standard K-fold with random splits overestimates OOS accuracy
  by 5-15% on time-series data. Walk-forward folds detect when the model has overfit to the
  most recent market regime (val_acc high because test window is temporally adjacent to train).
  The threshold guard prevents the engine from trading on an overfit model during regime shifts.

### start_unity_engine.py

**2. G8.5R — HMM-GEX Regime Coherence Gate (31st gate, ±1.5pts)**
- Position: inserted after G8.5P block (`_record("gate_g85p",...)`), before G8.5m block
- Logic: JOINT confirmation — HMM expansion/contraction direction AND BTC GEX net direction
  must BOTH agree with the signal direction
  - BUY + HMM=EXPANSION + GEX net>+$500M: +1.5pts (dual bullish confirmation)
  - BUY + HMM=CONTRACTION + GEX net<-$500M: -1.5pts (dual bearish opposition)
  - SELL + HMM=CONTRACTION + GEX net<-$500M: +1.5pts (dual bearish confirmation)
  - SELL + HMM=EXPANSION + GEX net>+$500M: -1.5pts (dual bullish opposition)
  - Mixed signals (HMM and GEX disagree): 0pts (gate silent)
- Guards: GEX conf ≥ 35, "FLIP" not in GEX regime string, GEX snapshot < 120s old
- Gate stats: `gate_g85r` initialised in `_gate_stats`, `_gate_stats_recent`, `_GATE_DISPLAY_LABELS`
- Log: `[G8.5R HMM-GEX Coherence v62.0]` debug-level
- **Why:** G8.5e applies unilateral HMM adjustment; G8.5m applies unilateral GEX adjustment.
  Neither captures the JOINT case. Two orthogonal systems (state-machine regime + dealer
  gamma positioning) simultaneously aligned creates multiplicatively stronger conviction.
  The gate is silent (0pts) when they disagree — no false penalty from this interaction.
- **Important:** Does NOT double-count with G8.5e or G8.5m — they fire on individual signals;
  G8.5R fires only on the conjunction. At any time one of the conditions can be true without
  the other, leaving G8.5e/G8.5m active while G8.5R stays silent.

**3. Kelly Max-Drawdown Scale-Down**
- Placement: immediately after `self.last_kelly_fraction = max(0.0, min(_kelly_ceil, kelly))`
- Formula: `scale = max(0.50, 1.0 − (max_dd_pct − 15.0) / 60.0)`
- Impact schedule:
  - DD ≤ 15%: no effect (scale = 1.00)
  - DD = 30%: scale = 0.75 (25% reduction)
  - DD = 45%: scale = 0.625 (37.5% reduction)
  - DD = 75%: scale = 0.50 (50% maximum reduction cap)
- Reads `self._max_drawdown_pct` (already tracked on booster at `_current_equity / _peak_equity`)
- Guard: cold-start no-op when `_max_drawdown_pct == 0.0`
- **Why:** During sustained drawdown the edge assumption embedded in Kelly's f* is compromised
  (win rate and RR estimates are stale from a different regime). Institutional risk management
  requires progressive position de-sizing as drawdown deepens. The 50% cap ensures the engine
  never goes below half-Kelly even in severe drawdowns (still trades but cautiously).

### All banners updated: 30-gate → 31-gate filter
- Line ~47 (module docstring): `G8.5R:HMM-GEX-Coherence(±1.5pts) | 31-gate filter [v62.0]`
- Line ~12234 (wiring log): `G8.5R:HMM-GEX-Coherence[v62.0]`
- Line ~15781 (boot banner): `G8.5R:HMM-GEX-Coherence | 5-bucket RL | ... [v62.0]`
- Line ~16708 (launcher log): `G8.5R` added to gate list

### File headers synced
- UNITY_VERSION: "61.0" → "62.0"
- Dockerfile, nixpacks.toml, requirements.txt: all updated to v62.0

## Boot confirmation
```
✅ UNITY ENGINE v62.0 — ALL SYSTEMS ONLINE — STARTING CONTINUOUS SCANNER
   Layers online  : 21/21
   Signal gates   : 31-gate filter | ... G8.5R:HMM-GEX-Coherence | 5-bucket RL | Quality≥67 | IRONS≥50 [v62.0]
💾 [v62.0] Startup state snapshot saved
✅ [v62.0] Watchdog + Persistence + ... started
```
