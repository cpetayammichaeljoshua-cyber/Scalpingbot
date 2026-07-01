---
name: Unity Engine v166.0 upgrades
description: G8.5AO GCAL2 (147th gate) + G8.5AP GLEN (148th gate) + NN v72 375feat + LLM cache TTL 90s + ScanParallel 164→156; v165→166
---

## Gates

**G8.5AO GCAL2 — AI Confidence Calibration (147th gate)**
- Implements Technique 6 (Workflow Isolation): Python Checker audits LLM Maker confidence
- Data: 17k-signal dataset shows LLM conf≥78 in WR<30% has LOWER actual WR than conf 60-75 (adverse selection)
- Severe: conf≥82 + WR<30% → -2.0pt (WR<22% in this band from dataset)
- Moderate: conf≥78 + WR<30% → -1.5pt (miscalibrated conviction in crisis)
- Reads: `signal_data.get("confidence") or signal_data.get("ai_confidence") or signal_data.get("ai_conf")`
- Env: UNITY_GCAL2=0 to disable; stores `_last_g85ao_gcal2`
- Thresholds: GCAL2_CONF_HIGH=82.0, GCAL2_CONF_MED=78.0, GCAL2_WR_GATE=30.0

**G8.5AP GLEN — Loop Engineering Narrow-Edge Checker (148th gate)**
- Implements Technique 5 (Loop Engineering): autonomous Maker→Checker loop in pure Python, zero API cost
- Uses F370 `loop_coherence` (v165.0) as the Checker evaluating 3-factor EV coherence of the signal
- Ultra: loop_coherence < 0.34 (all 3 factors misaligned) + WR<30% → -2.0pt
- Weak: loop_coherence < 0.51 (2/3 misaligned) + cold_seq_count ≥ 0.67 → -1.5pt
- Reads: `signal_data.get("loop_coherence")` and `signal_data.get("cold_seq_count")` (both injected by F366-F370 block)
- Env: UNITY_GLEN=0 to disable; stores `_last_g85ap_glen`
- Thresholds: GLEN_COH_ULTRA=0.34, GLEN_COH_WEAK=0.51, GLEN_WR_GATE=30.0

## Kelly Steps

**Step 142 (GCAL2):** severe overconf → ×0.84 | moderate → ×0.88
**Step 143 (GLEN):** all-incoherent ultra → ×0.82 | weak-loop+cold → ×0.87

## NN v72 (375 features, F371-F375)

- F371: `ao_gcal2_gate` — GCAL2 state mapped {-2.0→0.0, -1.5→0.2, 0→0.5}
- F372: `ai_conf_normalized` — raw LLM confidence / 100 [0,1] (same source as GCAL2)
- F373: `ap_glen_gate` — GLEN state mapped {-2.0→0.0, -1.5→0.2, 0→0.5}
- F374: `loop_coh_x_wr` — loop_coherence × WR_crisis_weight; WR_weight=(WR/30), capped [0,1]; penalises incoherence proportionally to crisis depth
- F375: `regime_alignment_4f` — 4-factor alignment score [0,1]: WR>30%, EV>0, SR>0, OFI aligned with direction → 0-4 factors counted / 4

**Note on F375 OFI count:** if abs(ofi_z) ≤ 0.3 (neutral OFI) it also counts as "not opposed" — so max possible votes is 5 when OFI is neutral (doesn't oppose), capped to 1.0 via min(1.0, votes/4).

## Railway Efficiency Upgrades

**ScanParallel:** 164 → 156 (-4.9% CPU)
**LLM cache TTL (godmod3_strategy.py):** 75s → 90s (+20% cache hits per scan cycle)
- 90s covers 1.5× CYCLE_SLEEP_MIN (10s), ensuring symbol results stay fresh through 1+ full cycle without re-querying

## Architecture Counts

- Gates: 146 → 148
- Kelly steps: 141 → 143
- NN features: 370 → 375 (v71 → v72)
- SCAN_PARALLEL_LIMIT: 164 → 156
- LLM_CACHE_TTL: 75s → 90s
- UNITY_VERSION: 165.0 → 166.0

**Why:** GCAL2 closes the known gap where high LLM confidence in low-WR regimes creates adverse selection (model is overconfident when the regime is most hostile). GLEN completes the Loop Engineering story: F370 loop_coherence (v165) was the passive self-assessment; GLEN is the active gate that uses it to autonomously suppress signals where the self-assessment is failing — the full Maker→Checker loop without any extra API call.
