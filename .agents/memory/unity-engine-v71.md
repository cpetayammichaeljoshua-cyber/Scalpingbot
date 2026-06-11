---
name: Unity Engine v71.0 upgrades
description: v71.0 stale-display fixes, anthropic noise reduction, NN fast-boot 2min, CONSORTIUM dynamic timeout — all confirmed live 2026-06-11
---

## Changes

### 1. Stale IRONS/G9 Display Strings Fixed
v70.0 introduced a WR<18% tier split (73 ultra-severe / WR<20% 72 crisis-relief) but 4 display strings still showed the pre-split v38.0 values:

- **Gate 10 boot label** (`start_unity_engine.py` line ~13104): was `[v38.0: WR<30%→70 | WR<25%→71.5 | WR<20%→73 | WR30-45%→67]` → fixed to `[v70.0: WR<30%→70 | WR<25%→71.5 | WR<20%→72 | WR<18%→73 | WR30-45%→67]`
- **KEY GATES G9_WR-tiers comment** (line ~135): `WR<20%→72` → `WR<20%→70` (v70.0 changed G9 floor at WR<20% from 72→70)
- **IRONS-sync capability stamp** (`ai_capability_checker.py` line ~187): was `v40.0 ... WR<20%→73/...` → fixed to `v70.0 ... WR<18%→73/WR<20%→72/WR<25%→71.5/WR<30%→70/WR30-45%→67`
- **G9 WR-tier inline comments** (line ~8964-8969): updated to reflect v70.0 floors

**Why:** Stale display strings cause confusion when diagnosing live signal filtering. Boot logs are the primary diagnostic tool — they must exactly reflect the running configuration.

### 2. Anthropic INFO Log Noise → DEBUG
`AIOrchestrationAgent._init_claude()` was logging at INFO level on every boot:
- `"No ANTHROPIC_API_KEY — Claude disabled"`
- `"anthropic package not found — Claude disabled"`

Both changed to `self.logger.debug(...)` in `mirofish_swarm_strategy.py`.

**Why:** The engine uses OpenRouter exclusively (via godmod3_strategy.py). Anthropic direct-API is never used in production. The INFO logs appeared as unexplained warnings on every boot, with no action possible.

### 3. NN First-Retrain 5min → 2min
`start_unity_engine.py` `_nn_retrain_loop()` initial `await asyncio.sleep(300)` changed to `await asyncio.sleep(120)`.

**Why:** At WR=18-26%, the NN adaptive quality gate (v70.0: 20% floor at WR<25%) must be active ASAP. 5min was designed for healthy WR. 2min allows 2 full scan cycles to populate the retrain queue before first NN evaluation.

### 4. CONSORTIUM Dynamic Timeout
In `godmod3_strategy.py` `_run_consortium_mode()`, after computing `n_available`:

```python
_healthy_frac = n_available / max(1, n_total)
_dyn_timeout  = max(6.0, self._CONSORTIUM_TIMEOUT * _healthy_frac)
```

The staggered-call inner function uses `_dyn_timeout + 3.0` (was hardcoded `CONSORTIUM_TIMEOUT + 3.0`).

**Why:** When free-tier model storms perm-disable several models (leaving e.g. 4/12), the old code still waited 16s per available model slot — burning clock on slots that were never going to respond. Dynamic timeout scales proportionally; full pool gets full 16s, half pool gets 8s (clamped to 6s floor). This speeds CONSORTIUM→ULTRAPLINIAN fallback during storm conditions.

## Infra Version Bumps (all 70.0→71.0)
- `start_unity_engine.py`: UNITY_VERSION, docstring, KEY GATES header, architecture banner
- `Dockerfile`: header comment, verify print, LABEL version/description
- `nixpacks.toml`: header comment, all verify-print strings
- `requirements.txt`: header comment, last-verified line

## Boot Verification (2026-06-11 14:27)
- `Unity Engine v71.0 Launcher` ✅
- Gate 10 display: `[v70.0: WR<30%→70 | WR<25%→71.5 | WR<20%→72 | WR<18%→73 | WR30-45%→67]` ✅
- IRONS-sync stamp: `v70.0 ... WR<18%→73/WR<20%→72/WR<25%→71.5/WR<30%→70/WR30-45%→67` ✅
- NN fast-boot: `first run in 2min [v71.0 fast-boot: 5min→2min crisis-boot]` ✅
- No anthropic INFO noise ✅
- Architecture banner: `CONSORTIUM-DynTimeout[v71.0]·NNFastBoot2min[v71.0]·IROnSDisplayFix[v71.0]·G9WR-tiers-70[v71.0]` ✅
- SOVEREIGN [1.00] · 30 layers · 36-gate filter ✅
