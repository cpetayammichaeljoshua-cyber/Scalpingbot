---
name: Unity Engine duplicate-log fix
description: How and why the duplicate log line problem was solved in v21.5 — root cause, fix location, and what NOT to try
---

## The Problem
Every log line appeared twice in `logs/unity_engine.log`. Affected all v21.x sessions.

## Root Cause
A background-task module imported during `UnityEngine.__init__` (specifically `SignalMaestro/logger.py`'s `setup_logging()` called from some background task) adds a second `RotatingFileHandler` for the same log path to the root logger. This happens AFTER the module-level dedup guard (which only checks at module load time) and AFTER the `run()` cleanup code (which runs before background tasks start).

The second handler was added ~40 seconds into the session, coinciding with the first background-task init wave. From that point every log line was written twice.

## What Did NOT Fix It
1. **Module-level dedup guard** (check before `addHandler(_fh)` at startup): Only prevents duplicates at import time; background tasks add the handler later.
2. **`run()` cleanup** (scan root handlers at start of `run()`, remove duplicates): Runs too early — before background tasks have added the second handler.

## The Fix (v21.5)
Monkey-patch the **root logger instance's** `addHandler` method (not the class — instance override only affects root, not child loggers):

```python
_rl_instance = logging.getLogger()
_rl_orig_add = _rl_instance.addHandler  # bound method

def _rl_dedup_add(hdlr, _root=_rl_instance, _orig=_rl_orig_add):
    if isinstance(hdlr, logging.FileHandler):
        _new_path = getattr(hdlr, "baseFilename", None)
        if _new_path and any(
            isinstance(h, logging.FileHandler) and
            getattr(h, "baseFilename", None) == _new_path
            for h in _root.handlers
        ):
            return  # duplicate — drop silently
    _orig(hdlr)

_rl_instance.addHandler = _rl_dedup_add
del _rl_instance, _rl_orig_add
```

**Location**: `start_unity_engine.py`, immediately after the RFH setup block (~line 1369). Must come BEFORE any SignalMaestro imports.

**Why:** Instance-level method override intercepts all future `root_logger.addHandler()` calls from any module, permanently rejecting duplicates for the same file path.

## How to Apply
- If duplicate lines return in a future version: check that the monkey-patch block is still present after the RFH setup in start_unity_engine.py.
- Do NOT move it after the SignalMaestro imports — must be module-level before any background task can run.
- If a legitimate second FileHandler is needed (e.g., error-only RFH for a different path), the guard allows it because it checks `baseFilename` equality.
