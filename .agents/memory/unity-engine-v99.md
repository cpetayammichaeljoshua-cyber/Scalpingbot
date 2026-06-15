---
name: Unity Engine v99.0 upgrades
description: v99.0 critical bug fixes — direction key bug in 8 sites, SOFT_GATE_KEYS missing X2/Y2/Z2, CONSORTIUM timeout 16→22s
---

## Critical direction-key bug (8 sites fixed)

**Rule:** Gates that check signal direction MUST use `signal_data.get("action", signal_data.get("direction", ""))` — the engine stores direction under `"action"` key (e.g., "BUY"/"SELL"), NOT `"direction"`.

**Why:** Every gate from v90.0–v95.0 (G8.5Y2, Z2, A3, B3, C3) AND their corresponding NN feature injection blocks (F151, F156, F161) used `signal_data.get("direction", "")` → always returned "" → `_is_long`/`_is_short` both False → gates could never give direction-aligned scores. Confirmed by G8.5Z2=0% bottleneck in logs.

**Affected sites fixed in v99.0:**
- Gate logic: G8.5Y2 (line ~11600), G8.5Z2 (~11696), G8.5A3 (~11773), G8.5B3 (~11856), G8.5C3 (~11928)
- NN feature injection: F151-F155 block (~8074), F156-F160 block (~8133), F161-F165 block (~8163)

**Pattern to apply for all future direction-reading gates:**
```python
_sig_dir = signal_data.get("action", signal_data.get("direction", "")) if isinstance(signal_data, dict) else ""
```

**How to apply:** Whenever a new gate or NN feature block reads signal direction, use the fallback pattern. The `"action"` key is primary; `"direction"` is the legacy fallback.

---

## SOFT_GATE_KEYS missing entries (v90–v92)

**Rule:** Every soft-gate (quality-adjuster, ±pts, cannot hard-block) must be in `_SOFT_GATE_KEYS` or it shows as a false bottleneck in the HUD.

**v99.0 additions:**
- `gate_g85x2_wrt` — WinRateTrajectory (v90.0), was missing → showed as bottleneck
- `gate_g85y2_hvc` — HMM-VPIN-Coherence (v91.0), was missing
- `gate_g85z2_rms` — RegimeMomentumSync (v92.0), was missing → G8.5Z2=0% bottleneck was this

**How to apply:** After adding any new G8.5*2 or G8.5*3 quality-adjuster gate, immediately add its record key to `_SOFT_GATE_KEYS`.

---

## CONSORTIUM timeout raised (v99.0)

- `_CONSORTIUM_TIMEOUT` 16.0 → 22.0s (`godmod3_strategy.py`)
- Dynamic timeout floor `max(6.0, ...)` → `max(10.0, ...)`

**Why:** gpt-oss-20b and gpt-oss-120b respond at 12-16s in Railway. With healthy_frac=0.67, dynamic timeout = max(6.0, 16.0×0.67) = 10.7s → models time out before responding → CONSORTIUM fails → forced ULTRAPLINIAN. With 22.0s base: max(10.0, 22.0×0.67) = 14.7s, sufficient for most gpt-oss responses.
