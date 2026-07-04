---
name: Unity Engine v203.0 — dead gate + GEX floor + Markov dampener fixes
description: gate_g85m/gate_g85n invisible to analytics since v18.94/v18.95; GEX sub-bonus floors 0.80→0.70; Markov positive delta now WR-dampened.
---

## Dead Gates Fixed (gate_g85m + gate_g85n)

Both gates had scored `quality_score` since v18.94/v18.95 with ZERO analytics wiring:
no `_gate_stats` init, no `_gate_stats_recent`, no `_record()`, not in `_GATE_DISPLAY_LABELS`.

**gate_g85m** (BTC Macro GEX Dealer-Flow, v18.94):
- Applies ±1.5/±2.0/±3.5pts based on BTC net GEX regime vs signal direction
- Fires for non-BTC/ETH symbols only (cross-pair macro context)

**gate_g85n** (Multi-Asset FLIP ZONE, v18.95):
- Applies −2.0pts when ≥2/3 of BTC/ETH/SOL are simultaneously in FLIP ZONE
- _multiflip_count was already exposed for G9 compound floor — just missing analytics

**Fix pattern used:**
```python
_g85m_q_before = quality_score  # save before try
try:
    ... (gate logic unchanged)
except Exception:
    pass
_g85m_net_score = quality_score - _g85m_q_before  # net delta
self._record("gate_g85m", _g85m_net_score >= 0.0)  # pass=neutral/positive, fail=penalized
```
Score-delta sentinel avoids modifying gate interior (clean, minimal change).

## GEX Sub-Bonus Floor Tightened 0.80→0.70

GEX alignment bonus used `_gex_wr_mult` (floor 0.70) but 4 sub-bonus paths used `max(0.80, _gex_wr_mult)`:
- `_gz_prox_mult` (Gamma Zero proximity)
- `_vt_mult` (Vol Trigger directional alignment)
- `_gz_mr_bonus = 3.0 * max(0.80, ...)` (GZ Mean-Revert)
- `_gz_tf_bonus = 4.0 * max(0.80, ...)` (GZ Trend-Follow)

All 4 now use `_gex_wr_mult` directly → consistent 0.70 floor at WR≤25%, ~14% more dampening.

## Markov Positive Delta WR-Dampened

`quality_score += _mk_delta` was completely raw. MARKOV_BOOST_PTS = 16.0 pts.
In WR=25% regime, Markov SOVEREIGN was adding 16.0pts raw vs 11.2pts (×0.70 dampened).

**Fix:**
```python
_mk_applied = self._wr_dampen(_mk_delta) if _mk_delta > 0 else _mk_delta
quality_score += _mk_applied
```
Negatives (penalties) pass through unchanged. Positive SOVEREIGN bonus WR-dampened.

**Why:** Consistent with v194-v200 overscoring sweep. Markov SOVEREIGN in WR<30% regime
signals regime-level strength but the WIN probability is still below 30% — full 16pt bonus was overcrediting.

**How to apply:** Any NEW positive quality_score bonus must go through `self._wr_dampen()` unless
it's a penalty-only path (like GSEV) or explicitly justified as "WR-independent" structural signal.
