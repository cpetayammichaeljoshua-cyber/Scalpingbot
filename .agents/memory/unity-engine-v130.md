---
name: Unity Engine v130.0 kelly_ceil silent-clamp bug + walk-forward edge re-check
description: the self._kelly_ceil never-assigned bug class, and which trade-data edges survive walk-forward (and which do not) — read before adding RR/confidence gates or "re-activating" Kelly steps
---

# v130.0 — self._kelly_ceil was a phantom attribute (51 silent no-op clamps)

## The bug class (recurring in this codebase)
- Kelly fine-tune Steps 88-105 clamp via `min(self._kelly_ceil, frac×mult)`, each wrapped in its own `try/except: pass`. `self._kelly_ceil` was NEVER assigned — the ceiling existed only as a LOCAL `_kelly_ceil` inside `_update_kelly()`. Every read raised AttributeError, was swallowed, and the step became a SILENT no-op (51 clamp sites dead).
- **Fix:** init `self._kelly_ceil = KELLY_MAX_FRACTION` in `__init__`, and mirror `self._kelly_ceil = _kelly_ceil` once per cycle in `_update_kelly` AFTER the Omega ceiling-lift and BEFORE the first reader.
- **Why it matters / how to apply:** identical failure mode to the many "silent dead-gate" entries. Any `self.X` read inside a bare `try/except: pass` gate/Kelly step is a silent no-op if `X` is never assigned in `__init__`. py_compile will NOT catch it; only a (swallowed) runtime AttributeError reveals it. When hardening, grep every `self._*` read inside try/except clamps and confirm a real `__init__` assignment exists.
- **Safety note (architect-corrected):** re-activated steps are NOT purely de-sizing — boost branches (×≤1.05) can RAISE frac, but always `min(.., self._kelly_ceil)` so frac can never exceed the Kelly ceiling. In crisis the de-size/sentinel branches dominate.

# Walk-forward edge re-check (bot source, 5 chronological folds, v130.0 session)
- **R:R<2.0 "edge" is NOT walk-forward-validatable.** Within `bot`, RR<2.0 showed +0.53%/trade (48% WR) vs RR≥3.0 −0.137% — but RR<2.0 trades exist ONLY in the earliest fold; once MinRR was raised the engine stopped producing them. In-sample-only. DO NOT lower MinRR on the strength of this pocket.
- **vol_ratio 2.0-3.5 penalty is the ONLY temporally-stable edge** (negative in 4/5 folds; vol 1.5-2.0 positive in 4/5). Already implemented as Kelly Step 107 (`VOL_SPIKE_RATIO_THRESH=2.0` → ×0.70 de-size, reads `self._last_vol_ratio`).
- **Confidence is anti-calibrated but unstable** — conf≥96 (58% of bot trades) has the worst EV, but the sign flips fold-to-fold. Directional ("don't trust high confidence") only; not a clean gate lever.
- **Session ASIAN/EU/TRANSITION negative but fold-noisy** — already de-sized by Kelly Step 106 (`SESSION_KELLY_DESIZE` 0.55× via `_current_kelly_session()`, which mirrors `get_current_market_session()` — resolves the old "session labels not in Kelly path" blocker).
- **insidertactics source logs CONSTANT placeholder conf/rsi/vol/session** (every row in one bucket); only its RR column varies. Any insidertactics univariate "edge" in a pooled query is an artifact — split by `source` AND ignore its non-RR features.
- **Bottom line:** both stable edges (vol-spike + session de-size) are ALREADY shipped (v129.0 Steps 106/107). No large untapped edge remains in the recorded features; the `bot` strategy is structurally ~breakeven-to-negative. More gates/threshold-cranks will not manufacture alpha — confirmed again.
