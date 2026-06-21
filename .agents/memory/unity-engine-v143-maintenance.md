---
name: Unity Engine v143 maintenance quirks
description: Tooling + banner-drift hazards on the giant start_unity_engine.py; /gates count-offset reading; godmod3 system-prompt vs swarm user-prompt data gap; and the architect-confirmed truth that WR≠more gates.
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

# Gate per-call counts have a fixed warmup-burst offset — compare DELTAS, not absolutes

The `/gates` endpoint (localhost:8080/gates → `{gate_key:{pass,fail,total,pass_rate}}`)
shows large *absolute* gaps between gates (e.g. early gates a3/g4/i4 ~259 vs later gates h4 ~3).
This is NOT a broken/zero-call gate.
- **Why:** during an early post-boot warmup burst (~256 apply() calls) the older gates recorded but the newer
  gate cohort didn't yet (cold-start / pre-fix window). That gap is a *frozen historical offset*. Take two
  `/gates` reads a few apply() calls apart: every gate increments by the same +N in lockstep per apply(). A gate
  "stuck at 1" is almost always just an idle window (signals/hr=0), not a dead gate.
- **How to apply:** to decide if a gate is truly dead, read /gates twice and diff `total` per gate — never compare
  a new gate's absolute total against an old gate's. Real health metric = "0 gates with total==0" (verified live
  129/129 recording, 0 zero-call).

## Soft-gate except clauses use bare `pass`, by house style
- The 11 newer soft-gates' except clauses were reverted from temporary GATE_DIAG instrumentation back to
  `pass  # G8.5XX is a non-fatal soft-gate` to match the existing a3/g4/i4 pattern. Tradeoff: a future exception
  silently stops a gate from recording. Acceptable ONLY while /gates delta-monitoring stays in place to catch a
  zero-call regression. Soft gates only add ±pts — fixing them is correctness, not a win-rate lever.

# godmod3 system_prompt references data the swarm user-prompt never feeds

The godmod3 system_prompt (`SignalMaestro/godmod3_strategy.py`, ~line 2563) is exhaustive — it tells models to
force NEUTRAL on hour_utc 1-7, volume_ratio>3.0, VPIN>0.60, funding pressure, rolling WR<X, MaxDD, OFI z-score,
HMM state, etc. But the user prompt is built by `_build_prompt()` in `SignalMaestro/mirofish_swarm_strategy.py`
(~line 1798), called from `analyze()` (~line 2254), and that method only has access to price `closes` — it feeds
symbol/price/RSI/MACD/BB%/Stoch/ATR% + swarm votes + graph memory.
- **Consequence:** most system-prompt hard-NEUTRAL rules were dead — the model was told to reason about
  VPIN/OFI/funding/MaxDD/WR it never received. Those fields live in the engine's UnitySignalFilter
  (start_unity_engine.py), NOT in the swarm. Feeding them needs `analyze()`'s signature changed to accept a
  market_context dict + plumbing from the engine call site — a multi-file, cross-module change.
- **What was done (minimal, correct):** added `hour_utc` (free via `datetime.now(timezone.utc).hour`) — the single
  most important and cheaply-available override field. Asian low-liquidity window (1-7 UTC) is a *confirmed*
  negative-EV pocket (see trade-data-analysis: "ASIAN session neg", live WR<24%). Prompt header now shows
  `hour_utc: NN` + a "force NEUTRAL" warning flag when 1<=hour<=7. Correctness/alignment fix, NOT a WR lever.
- **Why not feed the rest:** over-engineering risk in a 30k-line losing system; the swarm genuinely lacks that data
  in scope. Full microstructure plumbing = a deliberate larger follow-up, not an incidental edit.

# WR problem is overfitting, not a missing gate (architect-confirmed)
- Live v143: WR≈28.9%, Sharpe≈-4.9, MaxDD≈49%, EV≈-0.31R, pnl≈-730%, NN win_acc≈2.8% (quality-gate self-disables).
- The historical per-version pattern (+2 gates / +2 Kelly steps / +5 NN feats each version, v124→v143) has NOT
  recovered edge. Architect agreed: adding more gates/steps/features is overfit symptom-chasing.
- **How to apply:** for real WR work, do walk-forward / CPCV edge validation + regime/session/symbol calibration +
  hard-block the documented negative pockets (ASIAN session, RSI>70, vol_ratio>2, miscalibrated confidence) —
  do NOT ship a "v144 with +2 gates". Propose a separate validation/backtest task instead.
- Free OpenRouter models (gpt-oss-20b etc.) have limited context — do not bloat prompts. Never git-revert runtime
  *.db / *.json / weights (real trade + NN data) even when a code-review flags them as "artifacts in the diff".
