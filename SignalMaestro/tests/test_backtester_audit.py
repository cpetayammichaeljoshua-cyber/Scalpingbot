"""
Explicit test suite for the SignalMaestro backtester bug fixes and unification.

Covers all 9 bug fixes from commit c6aa4f7 + the realistic_cli fabrication fix
+ the unified __init__.py entry point + dead-code stub verification.

Run:  pytest tests/ -v
"""

import sys
import os
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Add SignalMaestro to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def synthetic_df():
    """Build a deterministic 200-bar OHLCV DataFrame with a trend."""
    np.random.seed(42)
    n = 200
    dates = pd.date_range("2026-01-01", periods=n, freq="5min")
    base = 50000.0
    trend = np.linspace(0, 500, n)
    noise = np.random.randn(n) * 50
    close = base + trend + noise
    open_ = close + np.random.randn(n) * 10
    high = np.maximum(open_, close) + np.abs(np.random.randn(n)) * 15
    low = np.minimum(open_, close) - np.abs(np.random.randn(n)) * 15
    volume = 100000 + np.random.randn(n) * 5000
    df = pd.DataFrame({
        "open": open_, "high": high, "low": low,
        "close": close, "volume": volume
    }, index=dates)
    return df


@pytest.fixture
def long_signal():
    """A sample LONG signal dict matching what signals.py produces."""
    return {
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "price": 50000.0,
        "timestamp": datetime(2026, 1, 1, 12, 0),
        "signal_strength": 75.0,
        "atr_percentage": 1.0,
        "volume_ratio": 1.2,
        "trend_strength": 0.6,
        "volatility_category": "MEDIUM",
    }


@pytest.fixture
def short_signal():
    """A sample SHORT signal dict."""
    return {
        "symbol": "BTCUSDT",
        "direction": "SHORT",
        "price": 51000.0,
        "timestamp": datetime(2026, 1, 1, 12, 0),
        "signal_strength": 70.0,
        "atr_percentage": 1.0,
        "volume_ratio": 1.1,
        "trend_strength": 0.5,
        "volatility_category": "MEDIUM",
    }


@pytest.fixture
def risk_manager():
    from backtester.risk import RiskManager
    return RiskManager(
        initial_capital=100.0,
        risk_percentage=2.0,
        max_concurrent_trades=3,
        max_daily_loss=5.0,
        portfolio_risk_cap=10.0,
        use_fixed_risk=True,
        commission_rate=0.0005,
        funding_rate=0.0001,
    )


@pytest.fixture
def leverage_engine():
    from backtester.leverage import DynamicLeverageEngine
    return DynamicLeverageEngine(min_leverage=10, max_leverage=75)


@pytest.fixture
def exec_simulator():
    from backtester.exec import ExecutionSimulator
    return ExecutionSimulator()


# ── Bug 1: Lookahead bias in signal entry price ─────────────────────────────

class TestBug1LookaheadBias:
    """signals.py must use next bar's open for entry, not current close."""

    def test_entry_price_uses_next_open(self, synthetic_df, long_signal):
        """Verify the signal's price field is NOT the current bar's close."""
        from backtester.signals import generate_trading_signals
        import inspect

        src = inspect.getsource(generate_trading_signals) if hasattr(generate_trading_signals, '__wrapped__') else ""
        # Directly check signals.py source for the lookahead fix
        sig_path = Path(__file__).resolve().parent.parent / "backtester" / "signals.py"
        source = sig_path.read_text()

        assert "next_open = df['open'].iloc[index + 1]" in source, \
            "Lookahead fix not found: entry price should use next bar's open"

    def test_no_shift_negative(self):
        """No .shift(-1) in signals.py (that would be future-leak)."""
        sig_path = Path(__file__).resolve().parent.parent / "backtester" / "signals.py"
        source = sig_path.read_text()
        # shift(-1) is a lookahead pattern — scanning for it in signal generation
        lines = [l for l in source.split("\n") if "shift(-" in l and "ATR" not in l.upper()]
        # True ATR uses .shift() (positive) for true-range previous close; that's fine.
        # We flag shift(-1) that isn't in ATR true-range context.
        assert len(lines) == 0, f"Lookahead pattern shift(-1) found: {lines}"


# ── Bug 2: Fabricated random outcomes replaced with candle-by-candle ───────

class TestBug2FabricatedOutcomes:
    """cli.py and realistic_cli.py must NOT use random.random() for trade outcomes."""

    def test_cli_no_simulate_trade_outcome(self):
        cli_path = Path(__file__).resolve().parent.parent / "backtester" / "cli.py"
        source = cli_path.read_text()
        assert "_simulate_trade_outcome" not in source, \
            "cli.py still contains the fabricated _simulate_trade_outcome method"
        assert "_process_candle_by_candle" in source, \
            "cli.py missing candle-by-candle replacement"

    def test_realistic_cli_no_plan_trade_exit_fabrication(self):
        rcli_path = Path(__file__).resolve().parent.parent / "backtester" / "realistic_cli.py"
        source = rcli_path.read_text()
        assert "is_winner = random.random()" not in source, \
            "realistic_cli.py still fabricates is_winner via random.random()"
        assert "_process_candle_by_candle" in source, \
            "realistic_cli.py missing candle-by-candle replacement"
        # The fabricated _plan_trade_exit should be gone
        assert "win_prob = 0.68" not in source, \
            "realistic_cli.py still has fabricated win probability logic"

    def test_no_random_outcome_in_either_cli(self):
        """Neither CLI should use random.random() to decide trade direction (fabrication)."""
        for fname in ["cli.py", "realistic_cli.py"]:
            fpath = Path(__file__).resolve().parent.parent / "backtester" / fname
            source = fpath.read_text()
            # random.random() was the fabrication mechanism
            assert "random.random()" not in source, \
                f"{fname} still uses random.random() — fabrication not removed"


# ── Bug 3: Overfitting config flags disabled ───────────────────────────────

class TestBug3OverfittingConfig:
    """backtest_optimization_config.json must have all dangerous flags = false."""

    def test_all_dangerous_flags_false(self):
        cfg_path = Path(__file__).resolve().parent.parent / "backtest_optimization_config.json"
        with open(cfg_path) as f:
            cfg = json.load(f)

        dangerous_keys = [
            "synthetic_trade_generation",
            "relaxed_signal_generation",
            "enable_simulated_trades",
            "fallback_parameters",
            "enhanced_signal_frequency",
        ]
        for key in dangerous_keys:
            assert key in cfg, f"Missing config key: {key}"
            assert cfg[key] is False, f"Overfitting flag {key} should be false, got {cfg[key]}"

        # Nested confidence_adjustment
        assert "confidence_adjustment" in cfg, "Missing confidence_adjustment section"
        assert cfg["confidence_adjustment"].get("enabled") is False, \
            "confidence_adjustment.enabled should be false"


# ── Bug 4: StrategyValidator has logger in __init__ ────────────────────────

class TestBug4StrategyValidatorLogger:
    """StrategyValidator must have __init__ that sets self.logger."""

    def test_strategy_validator_init(self):
        from backtest_overfitting_analyzer import StrategyValidator
        sv = StrategyValidator()
        assert hasattr(sv, "logger"), "StrategyValidator missing self.logger"
        assert isinstance(sv.logger, logging.Logger), \
            "self.logger should be a logging.Logger instance"

    def test_strategy_validator_validate_works(self):
        """validate() should not crash due to missing logger."""
        from backtest_overfitting_analyzer import StrategyValidator
        sv = StrategyValidator()
        # Build a minimal trade list
        trades = [
            {"net_pnl": 1.0, "is_winner": True, "direction": "LONG", "duration_minutes": 30},
            {"net_pnl": -0.5, "is_winner": False, "direction": "SHORT", "duration_minutes": 20},
        ]
        # Should not raise AttributeError about logger
        try:
            result = sv.validate(trades)
            assert result is not None
        except AttributeError as e:
            if "logger" in str(e).lower():
                pytest.fail(f"StrategyValidator still missing logger: {e}")


# ── Bug 5: Dead elif in risk.py account_health fixed ──────────────────────

class TestBug5DeadElifAccountHealth:
    """risk.py account_health must check >25 DANGER before >15 AT_RISK."""

    def test_danger_before_at_risk(self):
        risk_path = Path(__file__).resolve().parent.parent / "backtester" / "risk.py"
        source = risk_path.read_text()

        # Find account_health block
        danger_idx = source.find('account_health = "DANGER"')
        at_risk_idx = source.find('account_health = "AT_RISK"')
        assert danger_idx > 0 and at_risk_idx > 0, \
            "Could not find DANGER/AT_RISK in risk.py"
        assert danger_idx < at_risk_idx, \
            "DANGER (>25) must appear before AT_RISK (>15) — dead elif bug"

    def test_25pct_loss_is_danger(self, risk_manager):
        """25% drawdown should be DANGER, not AT_RISK."""
        risk_manager.initial_capital = 100.0
        risk_manager.current_capital = 74.0  # 26% drawdown
        metrics = risk_manager.get_risk_metrics()
        assert metrics["account_health"] == "DANGER", \
            f"26% drawdown should be DANGER, got {metrics['account_health']}"

    def test_16pct_loss_is_at_risk(self, risk_manager):
        """16% drawdown should be AT_RISK, not CRITICAL or DANGER."""
        risk_manager.initial_capital = 100.0
        risk_manager.current_capital = 84.0  # 16% drawdown
        metrics = risk_manager.get_risk_metrics()
        assert metrics["account_health"] == "AT_RISK", \
            f"16% drawdown should be AT_RISK, got {metrics['account_health']}"


# ── Bug 6: RNG noise removed from signal strength ──────────────────────────

class TestBug6RNGNoiseRemoved:
    """signals.py must NOT use np.random.uniform for signal strength."""

    def test_no_np_random_in_signal_strength(self):
        sig_path = Path(__file__).resolve().parent.parent / "backtester" / "signals.py"
        source = sig_path.read_text()
        # The old code used np.random.uniform(-5, 5) in signal_strength
        assert "np.random.uniform" not in source, \
            "signals.py still uses np.random.uniform — nondeterminism not removed"
        # The fix uses min(95.0, float(score))
        assert "min(95.0, float(long_score))" in source or \
               "min(95.0, float(short_score))" in source, \
            "signal_strength should be deterministic min(95.0, float(score))"


# ── Bug 7: Adaptive threshold overfitting disabled ──────────────────────────

class TestBug7AdaptiveThresholdDisabled:
    """signals.py adaptive threshold relaxation must be disabled for production."""

    def test_adaptive_threshold_disabled(self):
        sig_path = Path(__file__).resolve().parent.parent / "backtester" / "signals.py"
        source = sig_path.read_text()
        # The fix adds `and False` to the if condition
        assert "and False" in source, \
            "Adaptive threshold relaxation not disabled (missing 'and False')"


# ── Bug 8: is_winner default False in metrics.py ────────────────────────────

class TestBug8IsWinnerDefault:
    """metrics.py must default is_winner to False, not True."""

    def test_is_winner_default_false(self):
        metrics_path = Path(__file__).resolve().parent.parent / "backtester" / "metrics.py"
        source = metrics_path.read_text()
        # The bug was is_winner defaulting to True; fix changed to False
        # Check that no line has is_winner=True as default (the old bug)
        bad_lines = [l.strip() for l in source.split("\n")
                     if "is_winner" in l and "True" in l and "get(" in l]
        assert len(bad_lines) == 0, \
            f"is_winner still defaults to True somewhere: {bad_lines}"

    def test_losing_trade_not_counted_as_winner(self):
        """A trade with net_pnl < 0 must not be classified as a winner."""
        from backtester.metrics import MetricsReporter
        mr = MetricsReporter()
        trades = [
            {"net_pnl": -1.0, "is_winner": False, "direction": "LONG",
             "duration_minutes": 30, "pnl_percentage": -10.0, "leverage": 20},
            {"net_pnl": 2.0, "is_winner": True, "direction": "LONG",
             "duration_minutes": 40, "pnl_percentage": 20.0, "leverage": 20},
        ]
        # is_winner should respect the explicit value, not default True
        # Build a minimal kwargs set
        metrics = mr.calculate_comprehensive_metrics(
            completed_trades=trades,
            initial_capital=100.0,
            final_capital=101.0,
            backtest_hours=24,
            risk_metrics={},
            leverage_metrics={},
            execution_stats={},
        )
        # With 1 winner, 1 loser, win_rate should be 50%, not 100%
        wr = metrics.get("win_rate", metrics.get("winrate", 0))
        assert wr <= 60.0, f"Win rate should be ~50%, got {wr}"


# ── Bug 9: ExecutionSimulator SL/TP uses intrabar high/low ─────────────────

class TestBug9ExecutionSimulatorIntrabar:
    """ExecutionSimulator must check intrabar high/low, not just close."""

    def test_long_stop_loss_hit_by_low(self, exec_simulator, risk_manager, leverage_engine, long_signal):
        """LONG stop loss should trigger when candle low <= SL price."""
        leverage, _, _ = leverage_engine.calculate_optimal_leverage({
            "atr_percentage": 1.0, "volume_ratio": 1.0, "trend_strength": 0.5
        })
        pos_info = risk_manager.calculate_position_size(long_signal, leverage)
        trade = risk_manager.open_trade(long_signal, leverage, pos_info)
        assert trade is not None

        # Build a candle where low pierces SL
        sl = trade["stop_loss_price"]
        candle = pd.Series({
            "open": long_signal["price"], "high": long_signal["price"] + 100,
            "low": sl - 10,  # Low goes below SL
            "close": long_signal["price"] - 50, "volume": 100000
        }, name=long_signal["timestamp"])

        triggers = exec_simulator.process_stop_loss_take_profit([trade], candle)
        assert len(triggers) > 0, "SL should trigger when low <= SL price"
        _t, exit_price, reason = triggers[0]
        assert "Stop Loss" in reason or "SL" in reason

    def test_long_take_profit_hit_by_high(self, exec_simulator, risk_manager, leverage_engine, long_signal):
        """LONG take profit should trigger when candle high >= TP price."""
        leverage, _, _ = leverage_engine.calculate_optimal_leverage({
            "atr_percentage": 1.0, "volume_ratio": 1.0, "trend_strength": 0.5
        })
        pos_info = risk_manager.calculate_position_size(long_signal, leverage)
        trade = risk_manager.open_trade(long_signal, leverage, pos_info)
        assert trade is not None

        tp = trade["take_profit_price"]
        candle = pd.Series({
            "open": long_signal["price"], "high": tp + 100,
            "low": long_signal["price"] - 10,
            "close": long_signal["price"] + 50, "volume": 100000
        }, name=long_signal["timestamp"])

        triggers = exec_simulator.process_stop_loss_take_profit([trade], candle)
        assert len(triggers) > 0, "TP should trigger when high >= TP price"
        _t, exit_price, reason = triggers[0]
        assert "Take Profit" in reason or "TP" in reason


# ── Unification: backtester __init__.py exposes one entry point ────────────

class TestUnification:
    """Verify the unified backtester package exports everything from one place."""

    def test_package_imports(self):
        import backtester
        for name in backtester.__all__:
            assert hasattr(backtester, name), f"backtester missing export: {name}"

    def test_run_backtest_dispatches(self):
        """run_backtest should be callable with mode kwarg."""
        import backtester
        assert callable(backtester.run_backtest)
        # It's async, so check it returns a coroutine
        coro = backtester.run_backtest({}, mode="comprehensive")
        assert hasattr(coro, "__await__"), "run_backtest should be async"
        coro.close()  # Don't actually run it

    def test_unified_import_surface(self):
        """All core components should be importable from backtester."""
        from backtester import (
            get_market_data,
            SyntheticDataProvider,
            generate_trading_signals,
            MLSignalFilter,
            DynamicLeverageEngine,
            RiskManager,
            ExecutionSimulator,
            MetricsReporter,
            ComprehensiveBacktester,
            RealisticBacktester,
        )
        # All must be non-None
        assert get_market_data is not None
        assert SyntheticDataProvider is not None
        assert ComprehensiveBacktester is not None
        assert RealisticBacktester is not None


# ── Dead code stubs verify deprecation ─────────────────────────────────────

class TestDeadCodeStubs:
    """Former phantom-import files must now be deprecation stubs, not crash on import."""

    def test_comprehensive_backtest_analysis_is_stub(self):
        """Importing comprehensive_backtest_analysis should not crash."""
        import comprehensive_backtest_analysis
        assert hasattr(comprehensive_backtest_analysis, "main")

    def test_test_backtest_is_stub(self):
        """Importing test_backtest should not crash."""
        import test_backtest
        assert hasattr(test_backtest, "main")

    def test_no_phantom_backtesting_engine_import(self):
        """Neither stub file should import from backtesting_engine."""
        for fname in ["comprehensive_backtest_analysis.py", "test_backtest.py"]:
            fpath = Path(__file__).resolve().parent.parent / fname
            source = fpath.read_text()
            assert "from backtesting_engine import" not in source, \
                f"{fname} still imports from phantom backtesting_engine"


# ── Integration: real candle-by-candle trade lifecycle ────────────────────

class TestIntegrationTradeLifecycle:
    """End-to-end: open a trade, process candles, close via SL/TP, verify PnL."""

    def test_long_trade_hits_sl(self, risk_manager, leverage_engine, exec_simulator, long_signal):
        """Open LONG, then feed a candle that hits stop loss, verify loss."""
        leverage, _, _ = leverage_engine.calculate_optimal_leverage({
            "atr_percentage": 1.0, "volume_ratio": 1.0, "trend_strength": 0.5
        })
        pos_info = risk_manager.calculate_position_size(long_signal, leverage)
        trade = risk_manager.open_trade(long_signal, leverage, pos_info)
        assert trade is not None, "Trade should open"

        # Feed candle that hits SL
        sl = trade["stop_loss_price"]
        candle = pd.Series({
            "open": long_signal["price"], "high": long_signal["price"] + 100,
            "low": sl - 10, "close": long_signal["price"] - 200,
            "volume": 100000
        }, name=long_signal["timestamp"] + timedelta(minutes=30))

        triggers = exec_simulator.process_stop_loss_take_profit([trade], candle)
        assert len(triggers) > 0

        _t, exit_price, reason = triggers[0]
        completed = risk_manager.close_trade(trade, exit_price, candle.name, reason)

        assert completed["is_winner"] is False, "SL hit should be is_winner=False"
        assert completed["net_pnl"] < 0, "SL hit should have negative PnL"
        assert completed["exit_reason"] == "Stop Loss"

    def test_short_trade_hits_tp(self, risk_manager, leverage_engine, exec_simulator, short_signal):
        """Open SHORT, feed a candle that hits take profit, verify gain."""
        leverage, _, _ = leverage_engine.calculate_optimal_leverage({
            "atr_percentage": 1.0, "volume_ratio": 1.0, "trend_strength": 0.5
        })
        pos_info = risk_manager.calculate_position_size(short_signal, leverage)
        trade = risk_manager.open_trade(short_signal, leverage, pos_info)
        assert trade is not None

        tp = trade["take_profit_price"]
        candle = pd.Series({
            "open": short_signal["price"], "high": short_signal["price"] + 50,
            "low": tp - 10, "close": short_signal["price"] - 200,
            "volume": 100000
        }, name=short_signal["timestamp"] + timedelta(minutes=30))

        triggers = exec_simulator.process_stop_loss_take_profit([trade], candle)
        assert len(triggers) > 0

        _t, exit_price, reason = triggers[0]
        completed = risk_manager.close_trade(trade, exit_price, candle.name, reason)

        assert completed["is_winner"] is True, "TP hit should be is_winner=True"
        assert completed["net_pnl"] > 0, "TP hit should have positive PnL"
        assert completed["exit_reason"] == "Take Profit"

    def test_trade_pnl_includes_commission(self, risk_manager, leverage_engine, exec_simulator, long_signal):
        """PnL should include commission costs (not just price difference)."""
        leverage, _, _ = leverage_engine.calculate_optimal_leverage({
            "atr_percentage": 1.0, "volume_ratio": 1.0, "trend_strength": 0.5
        })
        pos_info = risk_manager.calculate_position_size(long_signal, leverage)
        trade = risk_manager.open_trade(long_signal, leverage, pos_info)
        assert trade is not None

        # Close at same entry price (zero price diff) — PnL should be negative due to commission
        exit_time = long_signal["timestamp"] + timedelta(minutes=30)
        completed = risk_manager.close_trade(trade, long_signal["price"], exit_time, "Manual")

        assert completed["gross_pnl"] == 0, "Zero price diff should be zero gross PnL"
        assert completed["net_pnl"] < 0, "Zero price diff + commission = negative net PnL"
        assert completed["total_commission"] > 0, "Commission should be non-zero"
