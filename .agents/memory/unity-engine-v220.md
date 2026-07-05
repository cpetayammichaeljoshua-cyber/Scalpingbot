---
name: Unity Engine v220.0 — Kelly boost anti-compounding + Step 20 Sharpe tightening
description: Kelly Steps 19/20/21/26 GSEV guard + Step 20 Sharpe guard -4.0→-2.0 to prevent boost compounding against active GSEV optimism-trap
---

## Rule
Kelly boost steps (19/20/21/26) must be skipped when GSEV optimism-trap is active (≤-1.5).

## Root Cause
G8.5BI GSEV (Kelly Step 162) is the LAST step — it de-sizes by ×0.84 (GSEV≤-1.5) or ×0.78 (GSEV≤-2.0).
But Steps 19 (×1.08), 20 (×1.18), 21 (×1.25) and 26 (×1.10) are applied at steps 19-26 (far before Step 162).
When all three early boosts fire simultaneously before GSEV de-size: ×1.08 × ×1.18 × ×1.25 × ×0.84 ≈ ×1.337 net.
The GSEV optimism-trap intent (reduce sizing when system is overconfident) was being substantially offset.

## Fix
All four boost steps now check `_gsevXX = float(getattr(self, "_last_g85bi_gsev", 0.0) or 0.0)` and
gate the boost on `_gsevXX > -1.5`. When GSEV is active (≤-1.5), boosts are skipped entirely.
- Step 19 (line ~24665): `if _sr_prime_19 >= -1.0 and _gsev19 > -1.5`
- Step 20 (line ~24700): `if _sr20 >= -2.0 and _gsev20 > -1.5`  ← also Sharpe guard tightened
- Step 21 EXPANSION (line ~24726): `... and _gsev21 > -1.5`  (CONTRACTION path unaffected)
- Step 26 (line ~24969): `if _k26_scale > 1.0 and _gsev26 > -1.5`

## Step 20 Sharpe Guard Fix
Previous: `if _sr20 >= -4.0` — fires in virtually every drawdown (at live WR 29%, Sharpe ~-0.5 to -2.5).
Fixed: `if _sr20 >= -2.0` — blocks ×1.18 Markov boost in severe drawdown (Sharpe < -2.0).
Markov SOVEREIGN for a specific direction does not validate overall edge health at WR 29%.

**Why:** GSEV guard default (getattr 0.0) correctly evaluates to `0.0 > -1.5 = True` (boost allowed) when
GSEV has not fired this signal. Step 21 CONTRACTION de-size path is a separate `elif` and is unaffected.

**How to apply:** When adding new Kelly boost steps in the future, always add `_gsevNN > -1.5` guard.
