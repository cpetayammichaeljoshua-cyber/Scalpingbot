"""
SignalMaestro Backtester - Unified Engine
==========================================

Single import surface for the entire backtesting engine.
All entry points (cli.py, realistic_cli.py) now share the same
candle-by-candle execution path via ExecutionSimulator.
No fabricated random outcomes. No lookahead bias. No overfitting flags.

Usage:
    from backtester import BacktesterCLI, RealisticBacktester, run_backtest
    from backtester import ExecutionSimulator, RiskManager, MetricsReporter
    from backtester import generate_trading_signals, get_market_data

    # Quick backtest (all-in-one):
    result = asyncio.run(run_backtest(config))
"""

from .data import get_market_data, SyntheticDataProvider
from .signals import generate_trading_signals, MLSignalFilter
from .leverage import DynamicLeverageEngine
from .risk import RiskManager
from .exec import ExecutionSimulator
from .metrics import MetricsReporter
from .cli import ComprehensiveBacktester, run_comprehensive_backtest
from .realistic_cli import RealisticBacktester, run_realistic_backtest

__all__ = [
    # Data
    "get_market_data",
    "SyntheticDataProvider",
    # Signals
    "generate_trading_signals",
    "MLSignalFilter",
    # Leverage
    "DynamicLeverageEngine",
    # Risk
    "RiskManager",
    # Execution
    "ExecutionSimulator",
    # Metrics
    "MetricsReporter",
    # Engines
    "ComprehensiveBacktester",
    "RealisticBacktester",
    "run_comprehensive_backtest",
    "run_realistic_backtest",
]

# Unified entry: dispatch to the appropriate engine based on config
async def run_backtest(config: dict, mode: str = "comprehensive"):
    """
    Unified backtest entry point.

    Args:
        config: Backtest configuration dict
        mode: "comprehensive" (default) or "realistic"

    Returns:
        Backtest results dict
    """
    if mode == "realistic":
        return await run_realistic_backtest()
    return await run_comprehensive_backtest()
