#!/usr/bin/env python3
"""
DEPRECATED — Legacy Backtest Test Script
=========================================

This script previously imported from a phantom `backtesting_engine` module
that never existed in the repository. It was dead code that crashed on import.

Use the unified pytest suite instead:

    pytest tests/ -v

Or test the unified engine directly:

    python3 -c "from backtester import run_backtest; import asyncio; print(asyncio.run(run_backtest({})))"
"""

import sys

def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║  DEPRECATED: test_backtest.py                                ║
║                                                              ║
║  This module imported from `backtesting_engine` which never  ║
║  existed. It was dead code that crashed on import.           ║
║                                                              ║
║  Use the unified pytest suite instead:                       ║
║                                                              ║
║    pytest tests/ -v                                          ║
║                                                              ║
║  Or test the backtester package:                             ║
║    python3 -c "from backtester import run_backtest"          ║
╚══════════════════════════════════════════════════════════════╝
""", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    main()
