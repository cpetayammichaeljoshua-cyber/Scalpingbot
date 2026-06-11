---
name: Unity Engine v66.0 upgrades
description: v66.0 changes — G4 dead-zone relief, G8.5X DGRP-Velocity (35th gate), Kelly Step 28 MaxDD brake, OpenRouter session-perm-disable, EV crisis floor SR<-4.5
---

## v66.0 Changes

### G4 Dead-Zone Relief (`_g4_pass_ring`, `UnitySignalFilter.__init__`)
- `deque(maxlen=15)` ring tracks G4 pass/fail per evaluation
- When 15/15 fail AND `nn_threshold > 0.45`: relief = `min(0.09, threshold − 0.44)`, floor = 0.44
- Fires only in proven deadlock (not a general throughput boost); INFO-logged
- Root cause: Sharpe-tightening pushes threshold to 0.56–0.58 while NN predicts 0.30–0.42 → 0% pass

### G8.5X DGRP-Velocity Gate (35th gate, `gate_g85dv`)
- Measures velocity of GEX DGRP score over last 3–6 readings (30s update guard)
- `velocity < −8pts` → −2.0pts quality penalty (rapid deterioration)
- `velocity > +6pts` → +1.5pts quality bonus (rapid improvement)
- Added to: `gate_stats`, `_GATE_DISPLAY_LABELS` (label "G8.5X"), `_SOFT_GATE_KEYS`, `_record()` calls
- Ring: `_dgrp_velocity_ring = deque(maxlen=6)`, guard: `_dgrp_vel_last_update`

### Kelly Step 28 — MaxDD Emergency Brake
- Triggers when `_max_drawdown_pct > 47.5%`
- Applies after Step 27b DD-Scale: multiplies `last_kelly_fraction × 0.25`
- Both reductions stack multiplicatively; floor = 0 (allows recovery micro-sizing)
- At live MaxDD=49.37%: Step 27b gives ×0.54, Step 28 adds ×0.25 → ×0.135 total

### EV Crisis Floor — SR < −4.5 Tier
- New tier between existing −3.5 (1.20×) and −5.0 (1.35×) tiers
- `_sr_ev < -4.5`: `_ev_floor = min(EV_MIN_THRESHOLD * 1.28, EV_MIN_THRESHOLD + 0.0011)`
- At live Sharpe=−4.87: raises floor from 33.6bps (1.20×) to 35.8bps (1.28×)

### OpenRouter Session-Perm-Disable (`godmod3_strategy.py`)
- `_session_perm_disabled: set` — already inited in `__init__`
- `_is_model_disabled()` checks `_session_perm_disabled` first (early return)
- `_record_generic_error()`: when `GenericErrGuard` fires (≥12 consecutive errors), model added to `_session_perm_disabled` permanently for the session
- Prevents 2h-disable → re-enable → fail-again loop for dead routes (claude-fable-5, mythos-5)

**Why:** Live data showed G4=0% recent, claude-fable-5/mythos-5 burning generic errors every restart, Sharpe=−4.87, MaxDD=49.37%, EV=−0.3140R. All fixes are targeted at the specific failure mode observed.

## Version Strings Updated
- `UNITY_VERSION = "66.0"` in both `start_unity_engine.py` and `SignalMaestro/godmod3_strategy.py`
- nixpacks.toml, Dockerfile, requirements.txt headers → v66.0
- All banner strings: `34-gate filter` → `35-gate filter`, `Steps1-27` → `Steps1-28`
