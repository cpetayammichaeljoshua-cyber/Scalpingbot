---
name: Unity Engine v126.0 upgrades
description: G8.5X4 SVR + G8.5Y4 OWS gates (110th-111th), Kelly102-103, NN v56 295feat, aiofiles dep fix, ScanParallel164
---

## Gates

### G8.5X4 SVR — Quality-Score-Velocity-Recovery (110th gate, soft)
- Reads `self._quality_score_ring` (deque maxlen=8); requires ≥5 entries
- LinReg slope over the ring: slope>2.0→+2.0pts/sentinel=+2; slope>0.5→+1.0pts/+1; slope<-2.0→-2.0pts/-1; else 0
- Sentinel: `_last_g85x4_svr` (int: +2/+1/-1/0)
- Gate key: `gate_g85x4_svr`; GATE_DISPLAY_LABEL: "G8.5X4"

### G8.5Y4 OWS — OFI-WR-Trajectory-Sync (111th gate, soft)
- Reads `self._booster._ofi_ring` (last 3 entries, mean sign for direction) + `self._last_g85w4_wac`
- ofi_aligned+wac≥1 → +2.0pts/+2; ofi_aligned alone → +1.0pts/+1; ofi_opposed+wac≤-1 → -2.0pts/-1; else 0
- Sentinel: `_last_g85y4_ows` (int: +2/+1/-1/0)
- Gate key: `gate_g85y4_ows`; GATE_DISPLAY_LABEL: "G8.5Y4"

## Kelly Steps

### Step 102 SVR
- `_last_g85x4_svr=+2` → ×1.03 (fast quality recovery)
- `_last_g85x4_svr=+1` → ×1.01 (moderate recovery)
- `_last_g85x4_svr=-1` → ×0.87 (deteriorating)

### Step 103 OWS
- `_last_g85y4_ows=+2` → ×1.02 (OFI+WR dual-align)
- `_last_g85y4_ows=+1` → ×1.01 (OFI directional align)
- `_last_g85y4_ows=-1` → ×0.88 (OFI-opposed + WR-decel)

## NN v56
- INPUT_DIM: 290 → 295
- _TORCH_N_TOKENS: 58 → 59 (295 = 59×5)
- F291: quality_slope_norm
- F292: ofi_vol_sync
- F293: ev_ring_percentile
- F294: pnl_stability
- F295: wr_momentum_tier

## Dependency fix
- `aiofiles==24.1.0` added to nixpacks.toml pip install line

## Other changes
- SCAN_PARALLEL_LIMIT: 162 → 164
- UNITY_VERSION: 125.0 → 126.0
- All banner strings updated: docstring, IRONS prompt, startup banner, Kelly steps, wire_components, ALL SYSTEMS ONLINE, launcher stamp
- nixpacks.toml + Dockerfile: v123.0 → v126.0 verify strings; NN v53/280feat → v56/295feat
- neural_signal_trainer.py: INPUT_DIM=295, _TORCH_N_TOKENS=59

## Boot result
Clean 21/21 layers, 111-gate filter confirmed in ALL SYSTEMS ONLINE banner [v126.0]

**Why:** Ongoing upgrade cycle — each version adds 2 soft gates + 2 Kelly steps + 5 NN features.
