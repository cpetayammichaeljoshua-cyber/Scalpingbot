---
name: Unity Engine v101.0 upgrades
description: GBLK blacklist adaptive fix (6 symbols vs ~80% block rate), GBT/ET blend cap expansion, G8.5F3 MultiLayer-Coherence 66th gate, ScanParallel118
---

## Key Changes

**GBLK Bottleneck Fix (most impactful):**
- Blacklist SQL: `total >= 10 AND WR < 30%` → `total >= 20 AND WR < 25%`
- Root cause: at engine WR=29.3% almost every traded symbol hit WR<30%/≥10 → 80% of signals auto-blocked (GBLK was #1 bottleneck at ~20-23% pass rate)
- Result: blacklist dropped to 6 symbols (1000PEPEUSDT, ARBUSDT, BTCUSDC, HYPEUSDT, TAOUSDT, TRUMPUSDT)
- Safety nets kept: zero-win (≥5 or ≥7 trades) + severe underperformer (WR<15%/≥8 trades)

**Why:** When engine WR ≈ 29.3%, WR<30% threshold blacklists symbols that are merely average performers in a bear session. Raising to WR<25%/≥20 trades requires meaningful evidence of persistent underperformance before blocking.

**GBT Ensemble Blend Cap (neural_signal_trainer.py):**
- `np.clip(_hgbt_va_acc / _combined_acc, 0.20, 0.40)` → `np.clip(..., 0.20, 0.55)`
- ExtraTrees cap: `np.clip(..., 0.10, 0.25)` → `np.clip(..., 0.10, 0.30)`
- Total tree cap in predict_signal: `min(_tree_sum, 0.40)` → `min(_tree_sum, 0.55)`
- **Why:** GBT=79.2% vs MLP=62.5% val_acc → computed weight=55.9% was capped at 40%, leaving 16pp of ensemble accuracy on the table

**New G8.5F3 MultiLayer-Coherence Gate (66th gate, ±2.0/+1.0pts):**
- Key: `gate_g85f3_mlc`
- Reads: `confidence` (AI, 0-100), `consensus` (swarm, 0-1), `nn_win_prob` (NN, 0-1) from signal_data
- +2.0pts: AI≥89% + Swarm≥96% + NN≥54% (all 3 model layers aligned)
- +1.0pts: 2/3 layers above threshold (dual-layer agreement)
- -2.0pts: AI≥90% + NN<50% (LLM-NN dangerous divergence)
- Neutral otherwise
- Uses `quality_score +=` (same as other G8.5*3 gates at that location)
- Placed AFTER G8.5E3, BEFORE Gate 8.5m in evaluate_signal()

**ScanParallel:** 116→118

**All display strings updated:**
- `65-gate filter` → `66-gate filter` (4 locations: Launcher, Signal gates boot, all-components banner, ARCHITECTURE banner)
- Architecture banner stamps: `G8.5F3-MLCCoherence[v101.0]·GBTBlend55%[v101.0]·BlacklistAdaptive25%[v101.0]·ScanParallel118[v101.0]`

## Boot Confirmation
- v101.0: 21/21 layers ✅, 66-gate filter ✅, Semaphore(118) ✅, ALL SYSTEMS ONLINE ✅
- No Python errors on boot
- Blacklist: 6 symbols confirmed (dramatically reduced from prior session)
