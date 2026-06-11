---
name: Unity Engine v70.0 upgrades
description: v70.0 changes — NN adaptive quality gate, CPCV chance-floor guard, G9/IRONS WR<20% dual-floor relief, GODMOD3 model heartbeat
---

## v70.0 Changes (2026-06-11)

### 1. NN Quality Gate Adaptive (neural_signal_trainer.py)
- `_win_acc_floor = 0.20 if (_wr_for_cap < 0.25) else 0.28`
- At training WR<25%: gate drops to 20% (was always 28%)
- **Why:** At WR=18-25%, win_acc=24.2% + loss_acc=93.7% still filters 93.7% of losses. Disabling NN completely (static 28% gate) leaves G4 with zero probability filter — strictly worse than an imperfect model.
- **How to apply:** Adaptive gate only; at WR≥25% standard 0.28 floor remains.

### 2. CPCV Chance-Floor Guard (neural_signal_trainer.py)
- Condition changed: `if _cpcv_gap > 0.07 and _cpcv_avg > 0.47:`
- Added `elif _cpcv_gap > 0.07:` branch to log suppression reason
- **Why:** At CPCV avg=45.4% (near-chance), the gap signal is noise. Previously, this was pushing `_opt_threshold` up from 0.540→0.560, creating additional G4 blockage with no informational basis.
- **How to apply:** Any future CPCV threshold push path must check meaningful signal level first.

### 3. G9 WR<20% Floor Relief (start_unity_engine.py Gate 9)
- `max(SIGNAL_MIN_QUALITY_GATE, 70.0)` (was `72.0`) for `_g9_wr < 0.20` tier
- WR<15% floor stays at 74 (unchanged — extreme ruin tier)
- **Why:** G9=72 + IRONS=73 dual-floor at WR=18-20% produced near-zero throughput. At 70pt, co-equal with IRONS_MIN_WR_BELOW30+2=72 crisis-relief tier (v70.0).

### 4. IRONS WR<18% Tier Split (start_unity_engine.py Gate 10 adaptive_irons_min)
- Split `current_wr < 0.20` into two tiers:
  - `current_wr < 0.18` → `IRONS_MIN_WR_BELOW30 + 3.0` = **73** (ultra-severe, unchanged)
  - `current_wr < 0.20` → `IRONS_MIN_WR_BELOW30 + 2.0` = **72** (crisis relief, was 73 for whole WR<20% band)
- KEY GATES string: `IRONS_MIN=70(WR<30%)+72(WR<20%)+73(WR<18%)`
- **Why:** WR 18-20% is crisis but not statistical ruin (that's WR<18%). The blanket 73 floor at 18-20% combined with G9=72 was excessive — blocking genuine SOVEREIGN signals in a recoverable crisis zone.

### 5. GODMOD3 Model Status Heartbeat (godmod3_strategy.py _is_model_disabled)
- `self._last_model_heartbeat: float = 0.0` added in `__init__`
- Every 300s: logs `healthy/soft_disabled/perm_disabled` counts + perm_disabled model names
- Placed at top of `_is_model_disabled()` inside `try/except` (non-fatal)
- **Why:** During F&G=12 market stress all free-tier models were simultaneously disabled; no visibility into this state existed before v70.0.

## Boot verification
- Engine logged `✅ UNITY ENGINE v70.0 — ALL SYSTEMS ONLINE` on clean boot
- `[v70.0] Startup state snapshot saved` in Persistence log
- No errors in boot sequence
