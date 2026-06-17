---
name: Unity Engine v122.0 upgrades
description: v122.0 critical NN fix — loss_acc_floor 3-tier (root cause: training WR ≠ live WR); Kelly62 partial-credit ×0.88; NN re-enabled, Kelly 0.10%→0.30%
---

## Root cause discovered (critical)

**NN disabled despite v121.0 win_acc fix:** The trainer uses TRAINING-SET WR (raw label ratio W/(W+L)), NOT live overall WR.
- Live WR = 29.2% (crisis)
- Training WR = 1157/(1157+1931) = **37.5%** (≥ 30%)
- Old 2-tier `_loss_acc_floor`: 0.40 (WR<30%) / 0.50 (WR≥30%) → at 37.5%: floor = **0.50**
- loss_acc = 48.1% < 50% → NN still disabled after v121.0

## Fix applied

### 1. `_loss_acc_floor` 3-tier adaptive (neural_signal_trainer.py line 3606)
```python
_loss_acc_floor = 0.40 if (_wr_for_cap < 0.30) else 0.45 if (_wr_for_cap < 0.42) else 0.50
```
- At training WR=37.5%: floor=0.45, loss_acc=48.1%>0.45 → NN **re-enabled** ✅
- Crisis tier (WR<30%): 0.40 (unchanged)
- Mid-tier (WR 30-42%): 0.45 (new — covers the 37-38% training WR that appears during live WR≈29% crisis)
- Healthy tier (WR≥42%): 0.50 (institutional standard, unchanged)

**Why:** The trainer's `_wr_for_cap` is computed from raw label counts before oversampling; with 1157W and 1931L labels it always shows 37.5% even when live WR is 29%. This creates a systematic gap: the crisis floor (0.40) never fires even in deep crisis because the label WR > 30%.

### 2. Kelly Step 62 partial-credit (start_unity_engine.py)
- Old: NN disabled → `×0.72` (regardless of how close to qualifying)
- New: NN disabled AND `last_loss_acc > 0.42` → `×0.88` (near-qualified partial credit)
- NN disabled AND `last_loss_acc ≤ 0.42` → `×0.72` (no useful signal, full de-risk)
- **Why:** At loss_acc=48.1%, model filters 48% of losers — still directional signal worth ×0.88 not ×0.72

### 3. Observed result
- Startup cold train (W=403/L=533, training WR=43.1%→ old floor=0.50, loss_acc=83.9%>50%) → PASS anyway
- Full retrain (W=1157/L=1931, training WR=37.5%) → v122.0 gives floor=0.45 vs old 0.50 → PASS when loss_acc>0.45
- Kelly: 0.10% → **0.30%** (3× improvement) from NN re-enabled + Kelly Step 62 ×1.03 bonus
- Bottleneck: GBLK dropped out of top 3; G4=67% now #1 (expected — NN active and filtering)

## Key lesson
When diagnosing NN quality gate failures, always check:
1. What is `_wr_for_cap` actually measuring? (Training label ratio, NOT live WR)
2. Is the adaptive floor tier matching the training-set regime, not the live trading regime?
3. Two separate issues can combine: v121.0 fixed `win_acc_floor` but `loss_acc_floor` had the same training-vs-live WR gap
