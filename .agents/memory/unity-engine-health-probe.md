---
name: Unity Engine background layer health probe
description: How background GEX/WS layers get record_call() invoked so they show calls>0 in the dashboard
---

# Background Layer Health Probe (v20.5)

## The Rule
Background layers (AEGIS_GEX, DERIBIT_GEX, OKX_GEX, BINANCE_AGGTRADE_WS, DEPTH_SLIPPAGE, DYN_BACKTEST, MIROFISH_SIM, SOVEREIGN_RM) run in their own asyncio tasks and NEVER call record_call() via the signal-filter path. Without the probe they permanently show calls=0/sr=N/A.

## How to Apply
`_bg_layer_health_probe()` is an async method on `UnityEngine` class. It sleeps 45s after boot then calls `self.health.record_call("LAYER_NAME", success=bool)` every 30s based on object liveness.

**Critical attribute names (not derivable without running the engine):**
- SOVEREIGN_RM → `self.sovereign_rm` (no underscore — `_sovereign_rm` is always None)
- AEGIS_GEX → `self.gex_engine`
- DERIBIT_GEX → `self.deribit_gex`
- OKX_GEX → `self.okx_gex`
- BINANCE_AGGTRADE_WS → `self.binance_aggtrade`
- DEPTH_SLIPPAGE → `self.depth_slip`
- DYN_BACKTEST → `self.dyn_backtester`
- MIROFISH_SIM → `self.mirofish_sim`

## Why
These objects are initialized during `_init_layers()` and registered in the health monitor (self.health, which is the same instance as self._health inside signal filter). The `record_call()` function silently returns if the name is not in `self.layers` — no exception. The probe task is created with `asyncio.create_task(self._bg_layer_health_probe(), name="UnityBGHealthProbe")` alongside _watchdog_task, _persistence_task, _health_server_task.

## Confirmed working (v20.5)
After 45s warmup, logs show:
- 01:49:09: AEGIS_GEX calls=1 sr=100%, DERIBIT_GEX calls=1 sr=100%, all 7 GEX/WS layers updated
- SOVEREIGN_RM showed sr=0% until attribute name fixed from `_sovereign_rm` → `sovereign_rm`
