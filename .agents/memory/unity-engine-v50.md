---
name: Unity Engine v50.0 gate data-pipeline fix
description: G8.5w and G8.5x were silent no-ops since v49.0 launch; root cause and fix for both gates; display string audit.
---

## Root cause: G8.5w MTF-Momentum was a silent no-op
Gate 8.5w read `signal_data.get("price_returns", [])` but `price_returns` is NEVER stamped into `signal_data` before `apply()` runs — the field simply doesn't exist in the dict. Gate silently fell through on every single signal since v49.0.

**Fix:** Added fallback to `_quant_layer_close_buf[symbol]` (module-level per-symbol rolling deque of closes, written by `_feed_quant_layers_kline()` on every kline tick for all 76 scanned symbols). Derives returns as `(c[i+1]-c[i])/c[i]` from last 9 closes → 8 returns.

```python
if not (isinstance(_g85w_rets, (list, tuple)) and len(_g85w_rets) >= 4):
    _g85w_buf = _quant_layer_close_buf.get(symbol, [])
    if len(_g85w_buf) >= 5:
        _g85w_cls = list(_g85w_buf)[-9:]
        _g85w_rets = [(_g85w_cls[i+1]-_g85w_cls[i])/_g85w_cls[i]
                      for i in range(len(_g85w_cls)-1) if _g85w_cls[i] > 0]
```

## Root cause: G8.5x LiqCascade-Direction was a silent no-op
Gate 8.5x read `signal_data.get("liq_net_side", "")` and `signal_data.get("liq_magnitude", 0.0)` but these fields are NEVER stamped into `signal_data` — the signal construction code does not include liquidation direction. Gate fired 0 times since v49.0.

**Fix:** Added fallback to `_live_liq_data[symbol]` (module-level dict populated in real-time by `_liq_ws_task()` from Binance `!forceOrder@arr` WebSocket). Staleness guard: `ts < 90s`. Logic: `long_usd >= short_usd → "LONG"` (bearish cascade), else `"SHORT"` (bullish squeeze). Magnitude normalised to 0–1 (cap at $1M).

**Why:** The existing GLIQ gate (`gate_liq_cascade`, around line 5822) already reads `_live_liq_data` directly — G8.5x should follow the same pattern rather than relying on signal_data population.

## Display string audit (all corrected in v50.0)
- Module docstring line 3: `v48.0` → `v50.0`
- ARCHITECTURE docstring line 5: `25-gate filter` → `27-gate filter`
- Wiring log (~11574): `25-gate filter` → `27-gate filter` + added `G8.5w:MTF-Momentum[v50.0]` and `G8.5x:LiqCascade-Dir[v50.0]`
- Architecture banner (~11593): `25-gate filter` → `27-gate filter`; `NN-v10-65feat[v43.0]` → `NN-v11-70feat[v49.0]`; added `G8.5w-MTF-Momentum[v50.0]` + `G8.5x-LiqCascadeDir[v50.0]`
- Gate filter header (~11597): `25-GATE SIGNAL FILTER` → `27-GATE SIGNAL FILTER` + G8.5w/G8.5x in the description
- ALL SYSTEMS ONLINE banner (~15092): `15-gate filter` → `27-gate filter` + G8.5w/G8.5x named
- Launcher log (~16019): `15-gate filter` → `27-gate filter` + G8.5w/G8.5x named
- Layer 5 description (~11587): `55-feature MLP (42+8...)` → `70-feature NN v11 (MLP+Transformer 14×5 tokens...)`
- UNITY_VERSION: `49.0` → `50.0`
- Dockerfile/nixpacks.toml/requirements.txt: all updated to v50.0

## How to apply in future versions
When adding a new gate that uses data NOT part of the standard `signal_data` dict, always wire a fallback to the relevant module-level global state dict (`_live_liq_data`, `_quant_layer_close_buf`, `_live_kline_data`, `_live_funding_rates`, etc.). Never assume signal_data carries the field — check if it's actually stamped by inspecting `fxsusdt_telegram_bot.py::process_signals` and `mirofish_swarm_strategy.py::_analyze_timeframe` before relying on it.
