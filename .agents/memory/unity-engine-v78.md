---
name: Unity Engine v78.0 upgrades
description: G8.5J HMM Volatility Regime Transition gate (45th), Kelly Step 37, boot drought suppression fix, SCAN_PARALLEL 76→78, all display strings updated
---

## Changes

**G8.5J HMM Volatility Regime Transition gate** (45th gate, `gate_g85j_hmm`):
- ±2.0pts adverse / +1.5pts aligned based on `_last_hmm_regime_transition_signal`
- Uses 5-bar EWMA of vol-transition probability from `_hmm_layer_volatility_probs`
- Stored in `self._last_g85j_regime_signal` for Kelly Step 37 to consume
- `_g85j_hmm_ewma: Dict[str, float]` initialized in booster gate_stats block
- Inserted after G8.5I block (MicroTrend gate), keyed `gate_g85j_hmm` in _SOFT_GATE_KEYS

**Kelly Step 37 — HMM Regime Transition Dampener**:
- Adverse transition (signal < -0.3): ×0.87
- Aligned transition (signal > 0.3): ×1.04
- Uses `self._last_g85j_regime_signal` stored by G8.5J

**Boot drought suppression fix**:
- `_drought_boot_grace` check in `_update_threshold_rl()` drought block
- Suppresses drought base-cuts for first 300s after boot
- Uses `self._session_start_time` (already existed from v5.7, no new variable)
- Prevents false drought penalties during the warm-up window

**SCAN_PARALLEL_LIMIT**: 76 → 78

## Display strings updated (all locations)
- `44-gate` → `45-gate` in: KEY GATES block, wired_all() banner, _print_startup_banner() ARCHITECTURE + 45-GATE FILTER lines, ✅ UNITY ENGINE online banner, and main() 45-gate filter line
- `Steps1-36` → `Steps1-37` in wired_all() Kelly string + _print_startup_banner() ARCHITECTURE string  
- `ScanParallel76` → `ScanParallel78` in ARCHITECTURE string
- Kelly36+37 entries added to KEY GATES comment block at line ~396
- nixpacks.toml: header v77.0→v78.0, verify string updated (v77.0→v78.0, 44-gate→45-gate, SCAN_PARALLEL 77→78)

## Boot verification
Engine boots cleanly: `🚀 Unity Engine v78.0 Launcher`, `📦 RUNTIME DEPENDENCY MANIFEST (v78.0)`, `💾 [v78.0] Startup state snapshot saved` all confirmed in logs.
