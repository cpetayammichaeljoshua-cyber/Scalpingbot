#!/usr/bin/env python3
"""
DEPRECATED — Comprehensive Backtest Analysis
============================================

This module previously imported from a phantom `backtesting_engine` module
that never existed in the repository. It was 527 lines of dead code that
crashed immediately on import.

Use the unified backtester package instead:

    from backtester import run_backtest, ComprehensiveBacktester
    results = asyncio.run(run_backtest(config))

Or run directly:
    python3 -m backtester.cli
    python3 -m backtester.realistic_cli
"""

import sys
import asyncio

def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║  DEPRECATED: comprehensive_backtest_analysis.py              ║
║                                                              ║
║  This module previously imported from `backtesting_engine`  ║
║  which never existed. It was dead code that crashed on       ║
║  import.                                                     ║
║                                                              ║
║  Use the unified backtester package instead:                 ║
║                                                              ║
║    from backtester import run_backtest                       ║
║    results = asyncio.run(run_backtest(config))               ║
║                                                              ║
║  Or run the CLI:                                             ║
║    python3 -m backtester.cli                                 ║
║    python3 -m backtester.realistic_cli                       ║
╚══════════════════════════════════════════════════════════════╝
""", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    main()
