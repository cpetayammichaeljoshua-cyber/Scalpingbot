---
name: Unity Engine v128.1 hardening (deps + zero-bypass)
description: Why timesfm was removed, why the IRONS cold-start floor was safe to delete, how to audit zero-call gates, and which artifacts must never be git-reverted.
---

# Unity Engine v128.1 — hardening pass (deps, bypass removal, zero-call audit)

## timesfm was the Railway build-error cause — safe to remove
- `timesfm==2.0.1` was pinned in requirements.txt + nixpacks.toml but **never imported** (0 `import timesfm`). The TimesFM-named gates (G8.5D4/E4/F4/G4/H4/I4/J4) and features ("timesfm_*" dict keys) are computed with **pure-numpy polyfit**.
- It pulled unlisted transitive deps `huggingface_hub[cli]>=0.23.0` + `safetensors>=0.5.3` that risk colliding with the `transformers==4.44.2` pin (`huggingface_hub>=0.23.2,<1.0`) on a fresh Railway build → prime dependency-error cause.
- **Confirmed safe:** timesfm is NOT installed in Replit, yet the engine boots clean (21/21) and all TimesFM gates work. torch 2.3.1+cpu and transformers 4.44.2 are KEPT.

## IRONS Gate-10 cold-start floor was the LAST active bypass — safe to delete
- It forced `_irons_min = 38.0` whenever the IRONS score ring held `<5` entries (ring is in-memory deque, NOT persisted → fired on every fresh deploy).
- **Why deletion is dead-loop-safe:** `_irons_score_ring.append(irons_score)` happens UNCONDITIONALLY on BOTH the precomp and re-score paths, BEFORE the `passed_g10 = irons_score >= _irons_min` check. So failed evaluations still warm the ring → strict-adaptive floor from signal #1, no starvation deadlock (only a possible brief signal drought on cold start, which is desirable noise reduction).
- Other "bypasses" were already dead before this session: `IRONS_QUALITY_OVERRIDE_THRESHOLD/RELAX` (never applied since v37.0) and `_g3_softpass_flag`/`_g4_bypass_flag` (write-only locals, Gate-9 penalty hook removed in v37.0). All deleted in v128.1.

## How to audit "zero-call" gates correctly (result: 0 dead)
- A gate records pass/fail two ways: `self._record("key", cond)` OR direct/ternary increment `self._gate_stats["key"]["pass" if cond else "fail"] += 1`. A naive regex for only `_record(` false-positives ~22 gates as dead.
- Correct audit: `registered = keys from self._gate_stats["k"] = {"pass":...}` ; `covered = (keys with _record) ∪ (keys with self._gate_stats["k"][ increment)` ; `dead = registered - covered`.
- v128.1 result: **92 registered, 92 covered (65 via _record, 27 via direct increment), 0 dead.** There are NO zero-call gates.

## Structural performance reality (do NOT fix by adding gates)
- Live: WR≈29%, payoff +1.85R(TP1)/-1.0R(SL) → EV ≈ -0.17R/trade; break-even needs WR ≥ ~35%. System is structurally negative-EV.
- Across v20→v128 (~100 versions) gates grew to 113 but WR stayed ~29% → gate-proliferation is overfitting, not edge. Architect (twice) advised: adding a 114th gate or cranking thresholds won't help; the safe drawdown levers are risk-sizing / send-suppression, and those already exist (Kelly DD-brakes, crisis gates). No backtest is possible in this env.

## Runtime artifacts must NOT be git-reverted
- Running the engine (required to verify boots) modifies `trade_history.db`, `unity_metrics_v5.json`, `swarm_memory.db`, `nn_weights.json`, `torch_transformer_weights.pt`, `unity_*_v5/v6.json`. These hold REAL accumulated trade outcomes + NN training progress.
- **Why:** reverting them to a pre-session snapshot destroys live data — strictly worse than the reproducibility concern an architect may raise. They are the repo's normal operational diff on every run; leave them in the auto-commit.

## Cosmetic debt left intentionally
- Internal banner strings disagree on gate count (one says "113-gate filter", another "115-GATE SIGNAL FILTER" after v128.0 added B5/C5). Display-only; does not affect behavior. Not worth chasing every hardcoded banner.
