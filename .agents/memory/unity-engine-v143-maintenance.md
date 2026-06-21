---
name: Unity Engine v143 maintenance quirks
description: Tooling + banner-drift hazards when editing the giant start_unity_engine.py, plus the architect-confirmed truth that WR≠more gates.
---

# start_unity_engine.py maintenance hazards (confirmed v143.0)

## `read` tool mis-reports this file's length
- The `read` tool reports the file as ~14,668 lines; the real length is ~30,148 (per `wc -l` / `grep -n`).
  Using `read` with `offset`/`limit` beyond ~14.6k silently returns the wrong region ("exceeds file length").
- **How to apply:** for precise line access in this file use `sed -n 'A,Bp'` / `grep -n` / `rg`, NOT the read tool's offsets.

## Banner literals carry MULTIPLE independent hardcoded counts that drift every version
- There are ~5 live `logger.info` banner literals (around lines 25531/25550/25570 + launcher ~29090/30017) plus
  a giant `📐 ARCHITECTURE` line. Each independently hardcodes: the **gate count** ("NNN-gate filter" / "NNN-GATE
  SIGNAL FILTER") AND the **Kelly step count** ("Kelly(Steps1-NNN)"). They routinely fall out of sync with the
  real counts and with each other (e.g. found 115/122-gate and Kelly Steps1-116 while canonical was 136 / 131).
- Canonical truth = the file header/docstring + `UNITY_VERSION`; the highest real Kelly step ≈ the largest
  `Kelly Step NNN` comment. Docstring/changelog lines (e.g. ~lines 492, 600-960, 1687) hold HISTORICAL counts —
  leave those; only fix the live runtime banners (grep line >25000).
- **Why:** these are display-only; wrong counts confuse the user but never affect trade logic. Fixing them is the
  safe, in-scope part of "clean up the console". Verify with a fresh boot + `grep -oE "[0-9]{3}-gate"` on the new log.
- `Unity 12-gate REJECTED/PASSED` in `SignalMaestro/fxsusdt_telegram_bot.py` is NOT stale — it is that module's
  own core G0–G10 hard-gate fast-path, a deliberately different count from the 136-gate full filter. Do not "fix" it.

## WR problem is overfitting, not a missing gate (architect-confirmed)
- Live v143: WR≈28.9%, Sharpe≈-4.9, MaxDD≈49%, EV≈-0.31R, pnl≈-730%, NN win_acc≈2.8% (quality-gate self-disables).
- The historical per-version pattern (+2 gates / +2 Kelly steps / +5 NN feats each version, v124→v143) has NOT
  recovered edge. Architect agreed: adding more gates/steps/features is overfit symptom-chasing.
- **How to apply:** for real WR work, do walk-forward / CPCV edge validation + regime/session/symbol calibration +
  hard-block the documented negative pockets (ASIAN session, RSI>70, vol_ratio>2, miscalibrated confidence) —
  do NOT ship a "v144 with +2 gates". Propose a separate validation/backtest task instead.
