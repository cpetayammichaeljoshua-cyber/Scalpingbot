---
name: Unity Engine v216.0 — G8.5CORR sentinel gap v161 era
description: GCAL/GSEQ/GMOM3/GBATCH (G8.5AF/AH/AI/AJ) had positive score paths excluded from CORR overconsensus dampener since v161.0 introduction.
---

## Rule
After any CORR expansion pass, always check the immediately-preceding AND immediately-following version blocks — the gap is always between two passes that covered adjacent versions. The v186 pass covered v163-v168 but skipped v161 (the block immediately before). Same pattern as every prior CORR gap.

## What changed
Four v161.0-era gates added to `_corr_sentinels` tuple:
- `_last_g85af_gcal`  — GCAL  +1.0pt month-start alpha   → int=+1 → vote=+1
- `_last_g85ah_gseq`  — GSEQ  +1.5pt peak-window signal  → int=+1 → vote=+1
- `_last_g85ai_gmom3` — GMOM3 +1.5pt reversal momentum   → int=+1 → vote=+1
- `_last_g85aj_gbatch`— GBATCH +2.5pt elite batch size    → int=+2 → vote=+1

GDIV (AG, +0.5pt → int=0 → no vote) and GDOW (AE, hard-block) correctly omitted.
Sentinel count: 105→109.

**Why:** When all four fire simultaneously in active markets (e.g. day 1-7 + signal #11-20 + reversal momentum + batch size 5), the combined quality_score boost is up to 6.5pt without any CORR clawback — direct overconsensus inflation.

**How to apply:** After each CORR sentinel expansion pass:
1. List the version range covered.
2. Check v(start-2) through v(start-1) — the immediately-preceding un-audited window.
3. For each gate in that window, check: (a) does it contribute to quality_score? (b) does it have a positive path? (c) is `int(positive_value) != 0`?
4. Add all positive-contribution gates to `_corr_sentinels`.

## CORR vote normalization
The CORR loop normalizes all votes to ±1 regardless of int magnitude:
```python
_corr_votes.append(1 if _v > 0 else -1)  # int(2.5)=2 → +1, not +2
```
So `int(+2.5)=+2` and `int(+1.5)=+1` both contribute exactly ONE positive vote.
Only `int(+0.5)=0` is filtered out by `if _v != 0:`. This is why GDIV (+0.5) is correctly omitted.
