---
name: Unity Engine v182.0 analytics wiring fix
description: 12 gates (G8.5AM–AX, v165.0–v170.0) were missing from _gate_stats boot-time init, _GATE_DISPLAY_LABELS, and _SOFT_GATE_KEYS since their introduction.
---

## The Bug

Gates G8.5AM/AN/AO/AP/AQ/AR/AS/AT/AU/AV/AW/AX (v165.0–v170.0, `gate_g85am_ghtf` through `gate_g85ax_galp`) were introduced but the v165–v170 gate-stats block was never inserted — the init jumped from the v163.0 block (`gate_g85ak/al`) directly to the v171.0 block (`gate_g85ay/az`).

## Effects

- `gate_stats_summary()` showed raw dict keys ("gate_g85am_ghtf") instead of short labels ("G8.5AM") because `_GATE_DISPLAY_LABELS` had no entry.
- `gate_bottleneck_str()` classified all 12 as hard gates (not in `_SOFT_GATE_KEYS`) — they appeared as #1–#3 fake bottlenecks at every evaluation, masking real tunable bottlenecks (G0/G4/G0.5).
- Boot-time `gate_stats_summary()` was incomplete (12 entries missing until the first signal fired `_record()`'s `setdefault` fallback).
- Gates were NOT dead (they scored `quality_score` correctly and `_record()`'s `setdefault` guard created entries on first call), but analytics were corrupted.

## Fix (v182.0)

1. Added 12 `_gate_stats` + `_gate_stats_recent` entries in the correct ordered position (after v163 block, before v171 block).
2. Added 10 `_GATE_DISPLAY_LABELS` entries (gate_g85am–gate_g85av; AW/AX were already present).
3. Added 10 `_SOFT_GATE_KEYS` entries (gate_g85am–gate_g85av; AW/AX were already present).

## Root Cause Pattern

When adding gates in consecutive version batches, the gate-stats init block must be updated in the same PR. The symptom to watch for: `gate_stats_summary()` shows a raw key name (e.g. "gate_g85am_ghtf") instead of a short code ("G8.5AM") — that is the definitive indicator that `_GATE_DISPLAY_LABELS` is missing an entry.

**Why:** `_gate_stats` init ordering determines boot-time display order. `_SOFT_GATE_KEYS` determines whether a gate is excluded from the bottleneck HUD. Missing either causes misleading analytics that can mask real performance bottlenecks.

**How to apply:** After adding any new gate: (1) add to `_gate_stats`+`_gate_stats_recent` init in the correct version-ordered block, (2) add to `_GATE_DISPLAY_LABELS` with its short code, (3) add to `_SOFT_GATE_KEYS` if it's a score-adjuster (cannot hard-veto a signal). Run the analytics-completeness check script to verify all three.

## Verification Script

```python
import re
with open('start_unity_engine.py') as f:
    lines = f.readlines()
display_labels, gate_stats_keys, record_calls = set(), set(), set()
for line in lines:
    m = re.search(r'"(gate_g85[a-z0-9_]+)"\s*:\s*"G8', line)
    if m: display_labels.add(m.group(1))
    m = re.search(r'self\._gate_stats\["(gate_g85[a-z0-9_]+)"\]\s*=\s*\{', line)
    if m: gate_stats_keys.add(m.group(1))
    m = re.search(r'self\._record\("(gate_g85[a-z0-9_]+)"', line)
    if m: record_calls.add(m.group(1))
assert not (record_calls - gate_stats_keys), f"Missing _gate_stats: {record_calls - gate_stats_keys}"
assert not (record_calls - display_labels), f"Missing labels: {record_calls - display_labels}"
```
