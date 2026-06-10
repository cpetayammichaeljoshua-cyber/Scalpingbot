---
name: Unity Engine v54.0 signal flow recovery
description: Three evidence-driven fixes from live Railway logs at 01:46 UTC — dead zone recovery, G1 extreme regime relief, pre-skip tolerance.
---

## Evidence: What the live logs showed (v53.0 session, 01:46 UTC)

- 0 signals sent in 8+ minutes despite bot fully operational
- G0.5=0%(#1) in bottleneck display — dead zone hard veto at UTC hour=1 (range 0-2h)
- XAUTUSDT SELL: Markov p_ij=1.00, conf=91%, F&G=9 → G1_FAIL: R:R=2.79 < 2.80 (0.01 margin)
- PAXGUSDT SELL: F&G=9, Swarm=96% → pre-skip at 73.2%+15=88.2% < 89% (0.8pt margin)
- IRONS_AIScorer calls=0 = NOT a bug (Gate 10 only reached after Gates 0-9 pass)

## Fix 1: Dead zone 2→1h

**Location:** `start_unity_engine.py` line ~1174: `DEAD_ZONE_UTC_END = int(os.getenv("DEAD_ZONE_UTC_END", "1") or 1)`

**Rationale:** 00-01h UTC WR=22-23% (hard veto warranted). 01-02h UTC WR=24-26% (same logic that removed 02-03h in v18.78). Tokyo equities correlation window opens at 01h UTC.

**How to apply:** If live logs show 0 signals being blocked during a known-active market session (01-04h UTC crypto volume picks up), check `DEAD_ZONE_UTC_END` first.

## Fix 2: G1 R:R floor Extreme Fear/Greed regime-aligned relief

**Location:** `start_unity_engine.py`, Gate 1 block, after the GEX macro overlay (line ~6086)

**Code added:** After GEX overlay (`_adaptive_rr += 0.15`):
```python
_g1_fg = float(signal_data.get("fear_greed_index", 50) or 50)
_g1_is_long = direction in ("BUY", "LONG")
if (_g1_fg < 15.0 and not _g1_is_long) or (_g1_fg > 85.0 and _g1_is_long):
    _adaptive_rr = max(MIN_RR_RATIO, _adaptive_rr - 0.10)
```

**Why:** GEX macro overlay (+0.15 for 3/3 FLIP ZONE) creates a COUNTER-PRODUCTIVE penalty for regime-aligned extreme-regime signals. In Extreme Fear + SELL, dealer net-short gamma = SELL signals are dealer-aligned. The overlay's "adverse-fill risk" argument is reversed in this regime.

**Effect:** WR<25% + 3/3 FLIP + Extreme Fear SELL: 2.65+0.15−0.10=2.70 effective floor (was 2.80).

## Fix 3: Pre-skip +2pt tolerance

**Location:** `SignalMaestro/fxsusdt_telegram_bot.py` line ~2007: 
`_PRE_SKIP_TOLERANCE = 2.0`
`if _pre_boost_conf + _MAX_BOOST < confidence_threshold - _PRE_SKIP_TOLERANCE:`

**Why:** Signals within 2pt of threshold with max boost (e.g. 88.2% vs 89% threshold) are being pre-skipped before GODMODE can evaluate them. The 2pt tolerance only affects the [threshold-17, threshold-15) range — genuinely weak signals (threshold-17+) are still correctly pre-skipped.

**How to apply:** If live logs show many pre-skip suppressions at <1pt margin, tolerance was 0. It was set to 2pt in v54.0.

## v55.0 additions

### CONSORTIUM MIN_MODELS 3→2 (godmod3_strategy.py)
Storm disables (qwen3-72b 30s, glm-4.5-air 45s, llama-3.3-70b 240s, nemotron 240s, dolphin 240s, gemma-4-31b 240s) regularly drop available pool below MIN_MODELS=3. Result: CONSORTIUM bailed to ULTRAPLINIAN 100% of calls — no ensemble voting at all. Fix: `_CONSORTIUM_MIN_MODELS = 2`. Already aligned with `_CONSORTIUM_MIN_VOTES=2`.

### IRONS cold-start bypass 45→38 (Gate 10, start_unity_engine.py)
First signal to reach Gate 10 (IRONS calls=1 sr=0%) failed cold-start bypass. OHLCV stub data (fallback re-scoring path) produces scores in 30-42 range, below old 45 floor. Ring populates unconditionally (from both pass AND fail paths), so dead-loop concern from v11.2 is already resolved. Bypass now 38 > random baseline (~30-35). After 5 ring entries, adaptive WR-tier logic (70+ at WR<30%) takes over.

### G4 NN adaptive threshold diagnosis
G4_FAIL: NN win-prob=0.50 < 0.55 at Sharpe=-4.870 is CORRECT behavior:
- Base NN_WIN_PROB_GATE=0.50, _raw_opt=0.514, nn_threshold=0.514
- Sharpe<-3.5: nn_threshold = max(0.514, min(0.54, 0.50+0.08)) = 0.54
- v52 cap was 0.55 (not 0.54 as in v54+)
- v37.0-STRICT removed ALL G4 bypass paths for good reason — DO NOT re-add

## Pattern: Dead zone is the #1 signal suppressor

During any UTC hour inside DEAD_ZONE (00-01h), G0.5 hard-vetos 100% of signals. All other gates (IRONS, NN, NeuralNetwork, etc.) will show 0 calls because they're downstream of G0.5.

If IRONS_AIScorer shows calls=0 → check if dead zone hard veto is active first.
