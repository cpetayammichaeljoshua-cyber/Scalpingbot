---
name: Unity Engine v219.0 — dual "141-gate filter" stale banner fix
description: Two _logger.info banner sites were frozen at "141-gate filter" since ~v141.0; both fixed to "177-gate filter" in v219.0.
---

## Rule
Any gate-count banner fix must sweep ALL four distinct runtime banner sites:
1. `_wire_all_components` 🔗 info log (`f"177-gate filter (G2.5b:Pattern…"`)
2. `_print_startup_banner` 📐 ARCHITECTURE logger line (`logger.info(f"📐 ARCHITECTURE (30 layers, 177-gate filter…"`)
3. `_print_startup_banner` 🔒 GATE SIGNAL FILTER stamp (`logger.info(f"🔒 177-GATE SIGNAL FILTER…"`)
4. `start_continuous_scanner` 📋 ALL SYSTEMS ONLINE signal-gates line (`f"   Signal gates   : 177-gate filter…"`)

**Why:** Banners 1 and 4 are in separate methods from banners 2 and 3. Every prior sweep (v214, v215, v218) fixed banners 2+3 but missed 1 and 4. Banner 4's gate count is on an f-string continuation line — a plain `logger.*141-gate` regex misses it.

**How to apply:** Run this Python after any gate-count change:
```python
import re
text = open('start_unity_engine.py').read()
lines = text.split('\n')
for i, line in enumerate(lines, 1):
    if re.search(r'\b[0-9]{2,3}-gate', line):
        m = re.search(r'\b([0-9]{2,3})-gate', line)
        if m.group(1) != '177' and i > 100:  # skip changelog
            print(f'STALE L{i}: {line.strip()[:80]}')
```
The canonical gate count is 177 (post-v201.0 GSEV as 177th gate).
