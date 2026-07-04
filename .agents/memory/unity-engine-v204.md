---
name: Unity Engine v204.0
description: CORR overconsensus sentinel gap fix + 3 undampened positive bias paths WR-dampened
---

## Summary
v204.0 — 4 bug fixes. No new gates or Kelly steps. UNITY_VERSION 203.0→204.0. AST clean, clean boot confirmed.

## Fix 1: G8.5CORR sentinel gap — gate_g85m / gate_g85n (CORR count 91→93)
- gate_g85m (BTC Macro GEX, v18.94) and gate_g85n (Multi-Asset FLIP ZONE, v18.95) were added in v203.0 with score-delta sentinel pattern (`_g85m_q_before`/`_g85n_q_before` locals) but had **no persistent `self._last_g85m_score` / `self._last_g85n_score` attributes**.
- They could never contribute to the G8.5CORR Family Correlation Dampener vote count (which iterates `_corr_sentinels` tuple reading `getattr(self, attr, 0)`).
- gate_g85m can apply +2.0pts (flip-zone alignment) or +1.5pts (long/short GEX); gate_g85n can apply ±2.0pts. When both fire alongside GSEV + other correlated gates the clawback was under-counting by up to 2 votes.
- **Fix**: Added `self._last_g85m_score: float = 0.0` and `self._last_g85n_score: float = 0.0` to `__init__` (after `_last_g85bi_gsev`); stored `_g85m_net_score`/`_g85n_net_score` into them after each gate's `_record()` call; added both to the `_corr_sentinels` tuple with a `# v204.0` comment.

**Why:** Score-delta sentinels (using local `q_before` vars) never had a persistent class attribute to expose to the CORR dampener — the overconsensus clawback missed these two gates entirely since v203.0 introduction.

**How to apply:** Any future gate using the score-delta sentinel pattern (instead of storing a signed float like `_last_g85X`) must ALSO add a `self._last_g85X_score` class attr and store the net delta into it, then add to `_corr_sentinels`.

## Fix 2: DBT quality_bias undampened (since v9.9.1)
- G8.5 DynBacktest: `quality_score += _bias` — the primary vectorised-backtest quality bias was added raw.
- Positive _bias (up to +5pts when backtester sees clean win pattern) was awarded at full strength even at WR<30%.
- The adjacent PBO-CLEAN bonus was already WR-dampened (v200.0) but the primary `_bias` was not.
- **Fix**: `quality_score += self._wr_dampen(_bias) if _bias > 0 else _bias`

## Fix 3: MiroFish swarm simulation bias undampened (since v10.0)
- `quality_score += _sim_bias` — the 10-agent proxy-backtest bias was a raw addition.
- **Fix**: `quality_score += self._wr_dampen(_sim_bias) if _sim_bias > 0 else _sim_bias`

## Fix 4: Factor IC/IR bias undampened (since v11.0)
- `quality_score += _fac_bias` — the Factor IC/IR directional alpha signal was a raw +3.0pt addition.
- **Fix**: `quality_score += self._wr_dampen(_fac_bias) if _fac_bias > 0 else _fac_bias`

## Additional cleanup
- CORR rho comment updated: "90-sentinel pool post-v186.0" → "93-sentinel pool post-v204.0"
- Banner updated: "Unity Engine v203.0" → "Unity Engine v204.0"
- UNITY_VERSION = "204.0"

## Pattern documented
Any `quality_score += variable` that can be positive and is NOT already multiplied by `_gex_wr_mult` or wrapped in `self._wr_dampen()` is a v200.0-sweep miss. The three bias paths (DBT/_sim/_fac) were the last remaining raw-positive additions in the scoring path.
