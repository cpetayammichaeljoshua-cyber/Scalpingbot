---
name: Unity Engine v147.0 power-mode upgrades
description: GCLH pre-gate (Phase 1.97) + 9 threshold tightens for WR/Sharpe/maxDD improvement at WR=29% baseline
---

## v147.0 Changes

### 9 Parameter Tightens (power-mode)
| Parameter | Before | After | Rationale |
|---|---|---|---|
| AI_THRESHOLD_PERCENT | 92 | 93 | Top-7th-percentile LLM conviction only |
| NN_WIN_PROB_GATE | 0.56 | 0.58 | P_win≥58% → EV=+1.175R at RR=2.75 |
| MIN_RR_RATIO | 2.65 | 2.75 | +49.6% EV improvement per trade; break-even WR=26.7% |
| EV_MIN_THRESHOLD | 65bps | 70bps | 70bps requires P_win≥50.5% at RR=2.75 |
| SIGNAL_MIN_QUALITY_GATE (G9) | 70 | 72 | Top ~68th percentile composite quality |
| IRONS_MIN_WR_BELOW30 | 73 | 75 | Three-tier: G9=72 + G10/SOVEREIGN=75 + WR<20%=78 |
| IRONS_MIN_WR_30_45 | 69 | 71 | Co-equal with G9=72 dual-floor |
| CONSEC_LOSS_HARD_CUTOFF | 5 | 4 | P(4 losses)=25.4%; fires 1 trade earlier per CB trigger |
| SOVEREIGN_RECOVERY_GATE | 73 | 75 | Co-equal with IRONS_MIN_WR_BELOW30=75 |

### New Gate: GCLH (Phase 1.97) — Pre-Gate A5
- **Position**: After GVSP (Pre-Gate A4), before Pre-Gate B (consec hard cutoff)
- **Trigger**: `win_rate < 28.5% AND consec_losses ≥ 3 AND consec_losses < CONSEC_LOSS_HARD_CUTOFF`
- **Duration**: 3600s (1h) hard block
- **Early exit**: Cancelled if WR recovers ≥ 28.5% during cooldown
- **State**: `self._gclh_until` float timestamp in `UnitySignalFilter.__init__`
- **Stats key**: `"gate_gclh"` in `_gate_stats`
- **Env override**: `UNITY_GCLH=0` to disable
- **Two-tier design**: GCLH(3 losses + crisis) → 1h / Pre-Gate B(4 losses) → 3h

### Critical Implementation Detail: win_rate Scale
- `BoosterState.win_rate` returns **0–100 scale** (e.g., 29.0 = 29%), NOT 0–1
- GCLH gate normalises: `_gclh_wr_pct = raw / 100.0 if raw > 1.0 else raw`
- Then compares against 0.285 (fraction) — same pattern as line ~7722 in engine
- **Why:** `booster.win_rate` is accessed via `getattr` which hits `BoosterState.win_rate`
  returning `win_count / total * 100`; must normalise before fractional comparison

### Architecture Principle (inherited from v145)
For a SIGNAL bot, only HARD-BLOCK (not Kelly de-size) moves WR/Sharpe/maxDD —
de-sized bad signals still fire and pollute the WR distribution.

### UNITY_VERSION
146.0 → 147.0
