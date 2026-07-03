---
name: Unity Engine v190.0 dead-gate mass fix
description: 95 gates had self._record() inside try/except — exact v178 pattern. Mass fix + 3 secondary bugs.
---

## Rule
Any `self._record()` call that is the LAST statement inside a `try` block (immediately before `except Exception: pass`) is silently skipped if ANY prior statement in that try raises. The gate then produces NO analytics entry for that cycle. This is the v178/v190 dead-gate pattern.

**Why:** Python's `except` swallows the exception before `_record()` can run. The gate appears "alive" in `_gate_stats` (because that dict update runs before the crash point) but its `_record()` is never called.

**How to apply:** After every gate try/except refactor, verify `self._record()` is at the EXCEPT indentation level (outside the try), NOT the try body's indentation level (+4 spaces deeper). Run the detection script:
```python
for i, line in enumerate(lines):
    if 'self._record(' in line:
        for j in range(i+1, min(i+5, len(lines))):
            ns = lines[j].strip()
            if ns:
                if ns.startswith('except Exception'):
                    ri = len(line) - len(line.lstrip())
                    ei = len(lines[j]) - len(lines[j].lstrip())
                    if ri > ei:
                        print(f"BUG: Line {i+1}")
                break
```

## v190.0 Fix Summary
- **95 gates fixed** via surgical Python transformation: all `self._record()` calls moved from INSIDE try to AFTER except/pass block (at except indentation level)
- **Markov gate** special fix: added `_mk_record_val = True` sentinel before try; `_mk_record_val = _mk_delta > 0` inside try; single `self._record("gate_markov", _mk_record_val)` after except. Eliminated empty `else:` syntax error and double-recording.
- **G8.5AA–AD** (4 gates): added `_aa_pass/_ab_pass/_ac_pass/_ad_pass = True` sentinel before each try block — pass/fail vars were only assigned late in the try body, causing `UnboundLocalError` if exception before assignment.
- **GDOW** (gate_g85ae_gdow): removed duplicate `_record(True)` from inside except (kept only the post-except call). Exception path was double-recording.
- Transformation script: `python3` detecting `_record` before `except Exception` with indent > except_indent → move after pass line at except_indent.
- AST-verified clean before and after.
- Engine boots cleanly on v190.0.

## Checklist for new gates
1. Initialize `_fired = False` and any pass/fail sentinels BEFORE the try block
2. Place `self._record(...)` AFTER the except/pass block, NOT inside the try
3. Add gate to `_gate_stats`, `_gate_stats_recent`, `_GATE_DISPLAY_LABELS`, `_SOFT_GATE_KEYS`
4. Run the detection script above to verify 0 remaining patterns
