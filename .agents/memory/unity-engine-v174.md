---
name: Unity Engine v174.0 upgrades
description: G8.5BE GRDC (163rd gate, role-defined drawdown coherence) + G8.5BF GXWI (164th gate, XML-workflow isolation divergence); Kelly158+159; NN v80 415feat F411-F415; ScanParallel 122->118
---

## What shipped
- **G8.5BE GRDC** (163rd gate, "Role-Defined Drawdown Coherence" — Technique 1 Role Definition + Technique 3 Extended Thinking): cross-validates recent-10 WR trajectory (`_win_ring`) against `quality_score_ring` linreg slope. Coherent dual-source decay → -2.0pt; single-source lean → -1.0pt; coherent dual-recovery → +1.0pt.
- **G8.5BF GXWI** (164th gate, "XML-Workflow Isolation Divergence" — Technique 2 XML Delimiters + Technique 6 Workflow Isolation): separates "Maker" (live running score) from "Checker" (isolated `quality_score_ring` historical baseline). Large positive Maker-overconfidence divergence + WR<30-35% → -1.5/-1.0pt; aligned → +0.5pt trust bonus.
- Kelly Step 158 (GRDC ×0.80/×0.90/×1.04) + Step 159 (GXWI ×0.83/×0.91/×1.03).
- NN v80: INPUT_DIM 410→415, F411-F415 (be_grdc_gate, wr_qs_coherence, bf_gxwi_gate, maker_checker_div, role_workflow_composite), tokens 82×5→83×5.
- SCAN_PARALLEL_LIMIT 122→118 (Railway CPU headroom for 2 new gates).

## Reusable pattern confirmed this cycle
Both new gates reused existing state (`_win_ring`, `_quality_score_ring`) rather than adding new tracking structures — cheapest gate-addition path when the needed signal already exists somewhere in the engine.

## Infra sync checklist (the parts that are easy to miss)
When adding a paired-gate version bump, in addition to the gate logic + Kelly step + NN feature block, all of the following must be touched or the version is "half-shipped":
1. File header/docstring version + gate-count + Kelly-step-count line, plus full changelog entry.
2. `SCAN_PARALLEL_LIMIT` constant itself (not just the header comment documenting it).
3. `self._gate_stats[...]` init entries (pass/fail dict) for each new gate key.
4. `self._gate_stats_recent[...]` deque init entries for each new gate key.
5. `_GATE_DISPLAY_LABELS` dict entries mapping internal key → "G8.5xx" label.
6. `_SOFT_GATE_KEYS` list entries (marks the gate as a non-blocking adjuster for bottleneck HUD exclusion).
7. Two long banner strings: the `🔒 NNN-GATE SIGNAL FILTER` f-string (boot Gate-10 banner) AND the separate `"NNN-gate filter (...)"` f-string used in the startup summary log — both need the gate count digit bumped AND a new `G8.5xx:Description(pts)[vNNN.0]` segment appended.
8. Boot logger "Layer 5 : Neural Network" message — feature count, NN version, token count, and the full F-list must all be updated together or the boot banner silently drifts from the real feature count.
9. `SignalMaestro/neural_signal_trainer.py`: `INPUT_DIM`, `_TORCH_N_TOKENS`, and the tokenisation comment on the line above it, plus a new zero-padded backward-compat `build_features` block for the new F-numbers.
10. `ast.parse()` syntax-check both files, then restart the workflow and grep the fresh boot log for the new gate labels + feature list to confirm the banner actually reflects the new state (don't just trust the source edit — the boot banner is a separate hardcoded string, easy to update in one place and miss the other).

`INPUT_DIM` / `_TORCH_N_TOKENS` constants live ONLY in `neural_signal_trainer.py` — `start_unity_engine.py` only carries them as comment-string documentation in the header/banners, never as real constants.
