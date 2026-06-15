---
name: Unity Engine v100.0 upgrades
description: v100.0 comprehensive fixes — IRONS health semantic, RL WR-adaptive cap 89%, NN regularization improvements
---

## IRONS_AIScorer sr=0% — semantic health recording fix

**Rule:** `_health.record_call("IRONS_AIScorer", success=...)` must use `success=True` when the scorer computed a valid score. Reserve `success=False` for exceptions only.

**Why:** The old code used `success=passed_g10` — when a signal fails Gate 10 (IRONS score below threshold), it recorded `success=False`, showing ❌ in the HUD. This confused "scorer is broken" with "signal was rejected". The health probe measures layer availability, not gate pass rate. Gate pass rate is tracked separately via `_record("gate10", passed_g10)`.

**Fix location:** `start_unity_engine.py` — Gate 10 scoring block, after `passed_g10 = irons_score >= _irons_min`. Changed `success=passed_g10` → `success=True`.

**How to apply:** Any new layer health recording must distinguish "did the layer RUN successfully" (health) from "did the signal PASS this gate" (gate stats).

---

## RL WR-adaptive threshold cap — prevents death spiral

**Rule:** After computing `rl_threshold`, cap it based on current WR:
```python
_rl_wr_cap = (
    87.0 if recent_wr < 0.25 else
    89.0 if recent_wr < 0.30 else
    91.0 if recent_wr < 0.35 else
    93.0 if recent_wr < 0.40 else 95.0
)
rl_threshold = min(rl_threshold, _rl_wr_cap)
```

**Why:** Without the cap, the RL climbs to 91-95% during sustained losing streaks. This starves the NN retrainer (fewer signals → less training data → poor CPCV → more losses → higher threshold). The cap breaks the death spiral by ensuring borderline signals (85-88% confidence) still enter the live pool, providing data for learning even during adverse regimes.

**Confirmed effect:** At WR=29.3%, the cap reduced threshold 91% → 89% on first boot after v100.0.

**How to apply:** This cap fires after the existing `consec_loss_raised` branch. The log tag `[v100.0] RL WR-cap applied` in DEBUG shows when it fires.

---

## NN Transformer regularization improvements

**Context:** CPCV gap = 17.6% (val 68.6% vs CPCV avg 51.0%) indicates severe overfitting with 2974 training samples at 37% WR.

**Changes in `SignalMaestro/neural_signal_trainer.py`:**
- `dropout` in `_TransformerSignalModule`: 0.10 → 0.15 (stronger attention-layer regularization)
- `weight_decay` in AdamW: 1e-4 → 2e-4 (stronger L2 regularization)
- `epochs` default: 150 → 120 (prevents gradient from memorizing noise)
- `patience` for early stopping: 25 → 20 (tighter stopping criterion)

**Why:** At WR<35% with only ~2974 samples, a 150-epoch Transformer with 1e-4 L2 memorizes training patterns that don't generalize. The CPCV gap (17.6%) directly measures this: a 17%+ gap means the model is essentially fitting noise in the last 30% of training epochs. Reducing epochs + tightening early stopping + stronger L2 brings CPCV closer to val accuracy.

**How to apply:** These are constructor/call-site defaults. If you call `fit()` explicitly with different params, the explicit params take precedence.

---

## SCAN_PARALLEL_LIMIT bump

- 114 → 116 (+1.8% throughput) [v100.0]
- Stays within Binance rate envelope via 0.5s stagger
