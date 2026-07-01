---
name: Unity Engine v165.0 upgrades
description: G8.5AM GHTF (145th gate) + G8.5AN GMAP (146th gate) + NN v71 370feat + Loop Engineering F370 + LLM cache + ScanParallel 176→164; v164→165
---

## Gates

**G8.5AM GHTF — Hot/Cold Trend Flow (145th gate)**
- Data: sequential pnl_ring patterns predict next-signal quality with 4.5pp WR delta
- Hot: ≥3 wins in last 5 pnl_ring + WR>35% → +1.5pt (session momentum confirmed)
- Cold: last 3 pnl_ring ALL negative + WR<30% → -2.0pt (death-spiral early warning)
- Env: UNITY_GHTF=0 to disable; stores `_last_g85am_ghtf`
- Distinct from GSDD (same-direction clustering) and H3 (WR% brake): targets sequential P&L regardless of direction

**G8.5AN GMAP — Momentum Anti-Pattern RSI Gap-Fill (146th gate)**
- Data: XRSI fires at RSI>72 (v158); GMAP fills the 68-72 gap (WR 4.5pp lower in that band)
- LONG + RSI 68–72 + WR<30% → -1.5pt; SHORT + RSI 28–32 + WR<30% → -1.5pt
- Only fires in WR<30% crisis — normal regimes excluded by design
- Env: UNITY_GMAP=0 to disable; stores `_last_g85an_gmap`

## Kelly Steps

**Step 140 (GHTF):** hot→×1.05; cold→×0.84
**Step 141 (GMAP):** RSI anti-pattern + crisis WR → ×0.87

## NN v71 (370 features, F366-F370)

- F366: `am_ghtf_gate` — GHTF state mapped {-2.0→0.0, 0→0.5, +1.5→1.0}
- F367: `hot_seq_score` — mean of last-5 pnl_ring (normalized ×10, capped [-1,1])
- F368: `cold_seq_count` — consecutive losses in recent-3 / 3 (capped [0,1])
- F369: `an_gmap_gate` — binary: 0.0 if GMAP penalised, 1.0 if clear
- F370: `loop_coherence` — Python-side 3-factor EV coherence score [0,1]
  - Vote 1: OFI direction aligned (>0.3 for LONG, <-0.3 for SHORT)
  - Vote 2: WR>30% AND EV>0 = coherent risk/reward
  - Vote 3: RSI not extreme against direction (<72 for LONG, >28 for SHORT)
  - Zero-API Loop Engineering (Technique 5): self-evaluation without extra API cost

## Railway Efficiency Upgrades

**ScanParallel:** 176→164 (-6.8% CPU + asyncio coroutine overhead)
**SymLastTs prune:** 500→150 entries (-70% dict memory for 80-symbol universe)
**LLM per-symbol result cache (godmod3_strategy.py):**
- Cache key = `symbol|mode`; TTL = 75s; Entry = (vote, conf, narr, trace_json, expire_ts)
- Cache lookup BEFORE global throttle check in `analyze()`
- Cache store only on successful final return (not on NEUTRAL fallbacks)
- Prune at >400 entries to prevent unbounded growth
- Expected impact: ~30% reduction in duplicate API calls per scan cycle

## Architecture Counts

- Gates: 144 → 146
- Kelly steps: 139 → 141
- NN features: 365 → 370 (v70 → v71)
- SCAN_PARALLEL_LIMIT: 176 → 164
- UNITY_VERSION: 164.0 → 165.0

**Why:** GHTF and GMAP both fill documented gaps from the 17k InsiderTactics dataset. GHTF catches sequential P&L degradation that GSDD (direction-based) misses. GMAP fills the RSI 68-72/28-32 gap that XRSI (fires at 72/28) doesn't cover in WR<30% crisis. The LLM cache is the highest-impact Railway cost reduction since SCAN_PARALLEL reduction in v164.
