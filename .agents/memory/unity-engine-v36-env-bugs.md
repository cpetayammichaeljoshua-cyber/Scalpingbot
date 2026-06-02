---
name: Unity Engine v36.0 critical env-override bugs
description: Two .replit userenv vars were silently overriding designed gate constants, destroying win rate. Fixed in v36.0.
---

# Unity Engine v36.0 — Critical env-override gate bugs

## The bugs

### Bug 1: UNITY_NN_GATE = "0.35" (design = 0.48)
- **Where**: `.replit` `[userenv.shared]` section
- **Effect**: G4 Neural Network win-prob gate ran at **35%** not the designed **48%**. A 13pp gap meant signals with only 35% win probability passed G4, far below the EV-positive floor.
- **Code that reads it**: `NN_WIN_PROB_GATE = float(os.getenv("UNITY_NN_GATE", "0.48") or 0.48)` (start_unity_engine.py ~line 743)
- **Fix**: Set `UNITY_NN_GATE = "0.48"` in shared env via `setEnvVars()`

### Bug 2: IRONS_MIN_SCORE = "62" (design base = 50)
- **Where**: `.replit` `[userenv.shared]` section
- **Effect**: The IRONS base floor was 62 not 50. The adaptive WR-tier effective_min formula is `max(IRONS_MIN_SCORE, adaptive_tier - relax)`. With base=62:
  - WR 45-55% tier: adaptive=53 → `max(62, 48)=62` — tier never relaxed
  - WR >55% tier: adaptive=48 → `max(62, 43)=62` — capitalise-form mode disabled
  - Only WR<30% (adaptive=68) and WR 30-45% (adaptive=65) worked correctly (their adaptive > 62)
- **Fix**: Set `IRONS_MIN_SCORE = "50"` in shared env via `setEnvVars()`

## How to fix env overrides
Use code_execution with `setEnvVars()` — direct `.replit` edits are blocked:
```javascript
await setEnvVars({ values: { UNITY_NN_GATE: "0.48", IRONS_MIN_SCORE: "50" }, environment: "shared" });
```

## Key lesson
**Why:** The `.replit` `[userenv.shared]` section silently overrides runtime constants set in Python code. Any `os.getenv()` call with a matching env key will use the `.replit` value, not the code default. When gate constants are changed in code (e.g. NN_WIN_PROB_GATE raised 0.35→0.48 in v9.8), old env overrides persist and keep the gate at the old value.

**How to apply:** Before any gate calibration session, run `viewEnvVars({type: "env", environment: "shared"})` and check that none of the gate-controlling env keys (`UNITY_NN_GATE`, `IRONS_MIN_SCORE`, `SIGNAL_MIN_QUALITY_GATE`, `MIN_RR_RATIO`) have stale values that contradict the current code design constants.
