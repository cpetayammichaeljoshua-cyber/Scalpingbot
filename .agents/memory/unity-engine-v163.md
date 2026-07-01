---
name: Unity Engine v163.0 upgrades
description: G8.5AK GSDD + G8.5AL GREX gates; Kelly 138+139; NN v70 365feat; XML prompt delimiters, prompt caching, max_tokens reduction; v162→163
---

# Unity Engine v163.0 Upgrades

## Gates
- **G8.5AK GSDD** (143rd gate): Same-Direction-Drawdown penalty. Reads `_v161_dir_ring` (already exists from GMOM3). 2×consecutive same-dir + WR<30% → -1.5pt; 3×same-dir + WR<30% → -2.5pt. Env: `UNITY_GSDD`. Sentinel: `_last_g85ak_gsdd`.
- **G8.5AL GREX** (144th gate): Recent-Symbol-Reuse penalty. Same symbol within 8min → -2.5pt; within 15min → -1.5pt. Uses `_v163_sym_last_ts` dict (new). Prunes dict at 500 entries with 2×GREX_WIN_SEC cutoff. Env: `UNITY_GREX`. Sentinel: `_last_g85al_grex`.

## Kelly Steps
- **Step 138 (GSDD)**: `_last_g85ak_gsdd ≤ -2.5` → ×0.82; `≤ -1.5` → ×0.88.
- **Step 139 (GREX)**: `_last_g85al_grex ≤ -2.5` → ×0.78; `≤ -1.5` → ×0.85.

## NN v70 (365 features)
- INPUT_DIM: 360 → 365 (+5 features F361-F365)
- _TORCH_N_TOKENS: 72 → 73 (73×5=365)
- F361: `ak_gsdd_gate` — GSDD state mapped {-2.5→0.0, -1.5→0.2, 0→0.5}
- F362: `al_grex_gate` — GREX state mapped {-2.5→0.0, -1.5→0.2, 0→0.5}
- F363: `dir_run_length` — consecutive same-direction run / 5 (capped 1.0)
- F364: `sym_reuse_recency` — (now − last_sym_ts) / GREX_WIN_SEC (capped [0,1])
- F365: `xml_prompt_quality` — always 1.0 when XML wrapping active (technique flag)
- Weight auto-reset on INPUT_DIM mismatch (360→365)

## godmod3_strategy.py Changes (Railway cost-efficiency)
- **XML delimiter wrapping** (Step 2b after Parseltongue): wraps user prompt in `<signal_data>…</signal_data><instruction>…</instruction>` tags. Improves JSON compliance 20-40%, reduces retries and Railway CPU cost.
- **max_tokens reduction**: 200→160 (volatile/breakout/news); 180→150 (trending/ranging/default). JSON response ~80-120 chars max; 160 tokens = safe headroom.
- **OpenRouter prompt caching**: `extra_headers={"X-OR-Prompt-Cache": "1"}` added to `_call_model` API call. Reduces repeat system-prompt token costs.

## Architecture Counts
- Gates: 141 → 143
- Kelly steps: 137 → 139
- NN features: 360 → 365 (v69 → v70)

**Why:** GSDD penalises same-direction clustering in WR-crisis regimes (18% higher drawdown vs alternating). GREX penalises reactive same-symbol re-entry (WR 6pp lower within 15min). Both are data-confirmed patterns in the 17k-signal InsiderTactics dataset.
