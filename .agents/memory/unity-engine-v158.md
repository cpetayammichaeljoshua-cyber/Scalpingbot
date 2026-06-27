---
name: Unity Engine v158.0 upgrades
description: GDCR-RQG relief quality guard (preserve window when anti-signal conf≥92+WR<30%) + G8.5AB XRSI RSI Extreme Direction Penalty (139th gate, -2.5/-1.5pts chase at WR<35%); v157→v158
---

## Changes in v158.0

### GDCR-RQG — Relief Quality Guard (Phase 1.98c)

**Loop Engineering: Checker evaluates Maker's candidate before spending the recovery slot**

- **Problem**: GDCR-AR (v156) allows one recovery signal per 2-3h interval. If that signal has conf≥92 (G8.5AA CWD fires → -1.5pts), it likely fails IRONS anyway. The relief window was burned on a doomed candidate.
- **Fix**: At GDCR relief "fall-through" point — BEFORE updating `self._gdcr_last_relief` — check:
  - `_gdcr_rqg_conf >= 92.0 and _gdcr_wr < 0.30` → block this signal AND preserve the window (don't update `_gdcr_last_relief`, don't increment `_gdcr_relief_count`)
  - Next signal through the scanner checks the same elapsed-time condition → gets the preserved window
- **Key**: Window is preserved, not burned. This is qualitatively different from GDCR-AR which defers the interval; RQG defers the specific candidate while keeping the slot open.
- **Env**: `UNITY_GDCR_RQG=0` to disable quality guard (reverts to burn-on-any-signal)
- **Log**: "GDCR-RQG: relief window PRESERVED — anti-signal candidate conf=XX%+WR=XX% → deferring to next candidate"
- **Position in code**: inside GDCR `if (_gdcr_release_ok and elapsed > 14400 and since_relief > interval):` block, before `self._gdcr_last_relief = _now_gdcr`

### G8.5AB — XRSI: RSI Extreme Direction Penalty (Phase 2.03, 139th scoring gate)

**Source: confirmed negative pocket from live trade data**

- Trade data: "RSI>70 neg" — RSI extreme signals at WR<35% have negative expectancy
- Direction-aware (chasing direction at RSI extreme = anti-signal; reversal at RSI extreme is handled by GCEF and G8.5T4 CapitulationReversal):
  - LONG at RSI>78 + WR<35% → **-2.5pts** (extreme overbought chase)
  - LONG at RSI>72 + WR<35% → **-1.5pts** (overbought chase)
  - SHORT at RSI<22 + WR<35% → **-2.5pts** (extreme oversold chase)
  - SHORT at RSI<28 + WR<35% → **-1.5pts** (oversold chase)
- WR guard: WR≥35% → skip penalty (momentum continuation valid in strong trending markets)
- Cold-start safe: skips when `len(booster._pnl_ring) < 20`
- RSI key: `signal_data.get("rsi", 50)` (confirmed from scanner at line 7938)
- `direction` variable already in scope in `filter_signal` (LONG/SHORT string)

**Wiring:**
- `gate_g85ab_xrsi` in gate_stats init + gate_stats_recent init
- `_last_g85ab_xrsi: int = 0` sentinel attr after _last_g85aa_cwd
- `"gate_g85ab_xrsi": "G8.5AB"` in _GATE_DISPLAY_LABELS
- `"gate_g85ab_xrsi"` in _SOFT_GATE_KEYS frozenset
- Gate code after G8.5AA pass line, before Gate 8.5m (BTC Macro GEX)
- Uses `score +=` and `_record()` pattern (consistent)

### Infrastructure
- UNITY_VERSION 157 → 158
- Gate count: 138-gate → 139-gate (all banners updated)
- KEY GATES banner updated with GDCR-RQG + G8.5AB entries

## Live State at v158.0 Build
- WR=29.0%, W=812, L=1986, Sharpe=-4.87, MaxDD=49.37%
- GDCR fires at boot; GDCR-RQG and G8.5AB both active
- RSI not visible at build time but at WR=29%, G8.5AB fires whenever RSI>72 (LONG) or RSI<28 (SHORT)

## Boot validation
- SYNTAX OK (ast.parse clean)
- All 6 insertion points confirmed: version, gate count, GDCR-RQG (3 lines), gate_stats, sentinel, DISPLAY_LABELS, SOFT_GATE_KEYS, gate code

## KEY PRINCIPLE ADDED
- GDCR-RQG introduces **relief slot preservation** — a concept distinct from all prior GDCR logic. Previous GDCR: every elapsed-time check either gives relief or extends. RQG adds: elapsed-time check passes but signal is anti-signal → preserve slot, block candidate, next signal gets the slot. This prevents wasting the recovery window on G8.5AA-doomed signals.
