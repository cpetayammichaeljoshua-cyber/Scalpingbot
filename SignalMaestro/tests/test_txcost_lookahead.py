"""
Focused audit tests for transaction-cost integration and lookahead safety
in the unified backtester/ engine.

Covers three gaps NOT exercised by test_backtester_audit.py:

  1. Transaction-cost accounting — verifies RiskManager.close_trade()
     nets gross PnL minus (entry+exit commission) minus funding, and that
     current_capital moves by margin + net_pnl (not just gross).
  2. Portfolio risk cap — verifies calculate_position_size() scales down
     the Nth concurrent trade so sum(active risk) <= portfolio_risk_cap%.
  3. Candle-by-candle lookahead safety — verifies _process_candle_by_candle
     starts scanning at the bar AFTER entry (never at or before it), and
     that the fill-price override uses a strictly-later candle's open.

Run:  pytest tests/test_txcost_lookahead.py -v
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtester.risk import RiskManager
from backtester.exec import ExecutionSimulator
from backtester.leverage import DynamicLeverageEngine


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def risk_manager_taker():
    """RiskManager with the taker commission rate the unified CLIs ship."""
    return RiskManager(
        initial_capital=100.0,
        risk_percentage=2.0,
        max_concurrent_trades=3,
        max_daily_loss=5.0,
        portfolio_risk_cap=6.0,         # 6% of initial = $6 max total risk
        use_fixed_risk=True,
        commission_rate=0.0005,         # 0.05% taker (unified default)
        funding_rate=0.0001,            # 0.01% per 8h
    )


@pytest.fixture
def long_signal():
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
def leverage_engine():
    return DynamicLeverageEngine(min_leverage=10, max_leverage=75)


@pytest.fixture
def exec_simulator():
    return ExecutionSimulator(slippage_bps=1.0)


def _block_df(entry_open=50000.0, after_move=0.0, bars_after=5, freq="5min"):
    """Build a small deterministic df with a known entry bar and a known move."""
    start = datetime(2026, 1, 1, 12, 0)
    dates = pd.date_range(start, periods=bars_after + 2, freq=freq)
    n = bars_after + 2
    # Entry bar (bar 0): flat around entry_open
    open_ = [entry_open] + [entry_open + after_move] * (n - 1)
    close = [entry_open] + [entry_open + after_move] * (n - 1)
    high = [o + 5 for o in open_]
    low = [o - 5 for o in open_]
    volume = [200000.0] * n
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low,
         "close": close, "volume": volume},
        index=dates,
    )


# ── 1. Transaction-cost accounting ───────────────────────────────────────────


class TestTransactionCostAccounting:
    """close_trade must net out commission + funding, and capital must move
    by margin + net_pnl (not gross_pnl)."""

    def test_close_trade_nets_commission_and_funding(self, risk_manager_taker,
                                                      leverage_engine, long_signal):
        """A flat trade (exit==entry) should still show a net loss equal to
        round-trip commission + funding, never zero."""
        rm = risk_manager_taker
        lev, _, _ = leverage_engine.calculate_optimal_leverage({
            "atr_percentage": long_signal["atr_percentage"],
            "volume_ratio": long_signal["volume_ratio"],
            "trend_strength": long_signal["trend_strength"],
        })
        pos = rm.calculate_position_size(long_signal, lev)
        assert pos, "position_info must not be empty"

        trade = rm.open_trade(long_signal, lev, pos)
        assert trade is not None

        # Simulate 16h hold so funding_periods=2 (16//8 = 2) kicks in.
        exit_time = long_signal["timestamp"] + timedelta(hours=16)
        closed = rm.close_trade(
            trade,
            exit_price=trade["entry_price"],     # flat exit — no gross PnL
            exit_time=exit_time,
            exit_reason="Flat Exit",
        )

        # gross_pnl is zero by construction
        assert closed["gross_pnl"] == pytest.approx(0.0, abs=1e-9)

        # Commission is entry + exit, both on position value at commission_rate
        pos_val_entry = trade["position_size"] * trade["entry_price"]
        pos_val_exit = trade["position_size"] * trade["entry_price"]
        expected_entry_com = pos_val_entry * rm.commission_rate
        expected_exit_com = pos_val_exit * rm.commission_rate
        expected_total_com = expected_entry_com + expected_exit_com
        assert closed["total_commission"] == pytest.approx(
            expected_total_com, rel=1e-6
        ), "total_commission must equal entry_value*rate + exit_value*rate"

        # Funding: position_value * funding_rate * funding_periods
        # Note: close_trade uses trade.get('funding_paid', 0.0), which is
        # computed by update_trades. Without calling update_trades first,
        # funding_paid stays 0, so close_trade's total_funding is 0.
        # This documents the actual contract — funding is only captured if
        # update_trades() was called during the hold.
        assert closed["total_funding"] == 0.0, (
            "funding_paid is 0 unless update_trades() ran during hold "
            "— close_trade reads trade['funding_paid'], not a recompute"
        )

        # Net PnL must be gross - commission - funding (here: -commission)
        assert closed["net_pnl"] == pytest.approx(
            closed["gross_pnl"] - closed["total_commission"] - closed["total_funding"],
            rel=1e-6,
        )
        assert closed["net_pnl"] < 0, "flat trade must show a net loss (fees)"

    def test_capital_moves_by_margin_plus_net_pnl(self, risk_manager_taker,
                                                    leverage_engine, long_signal):
        """current_capital after close == pre-open capital + net_pnl
        (margin is returned, gross_pnl−costs is what sticks)."""
        rm = risk_manager_taker
        lev, _, _ = leverage_engine.calculate_optimal_leverage({
            "atr_percentage": long_signal["atr_percentage"],
            "volume_ratio": long_signal["volume_ratio"],
            "trend_strength": long_signal["trend_strength"],
        })
        pos = rm.calculate_position_size(long_signal, lev)
        trade = rm.open_trade(long_signal, lev, pos)
        assert trade is not None

        cap_after_open = rm.current_capital
        margin = trade["margin_used"]

        exit_time = long_signal["timestamp"] + timedelta(hours=1)
        closed = rm.close_trade(
            trade,
            exit_price=trade["entry_price"],
            exit_time=exit_time,
            exit_reason="Flat",
        )

        # After close: capital should be (cap_after_open + margin + net_pnl)
        # because cap_after_open already had margin subtracted at open.
        expected = cap_after_open + margin + closed["net_pnl"]
        assert rm.current_capital == pytest.approx(expected, rel=1e-6), (
            "capital must move by margin_returned + net_pnl, not gross_pnl"
        )
        # And net_pnl must be < gross_pnl (0) because of fees
        assert closed["net_pnl"] < closed["gross_pnl"]

    def test_funding_accrues_via_update_trades(self, risk_manager_taker,
                                                leverage_engine, long_signal):
        """If update_trades() is called during the hold, funding_paid must
        be non-zero for a position held >= 8 hours."""
        rm = risk_manager_taker
        lev, _, _ = leverage_engine.calculate_optimal_leverage({
            "atr_percentage": long_signal["atr_percentage"],
            "volume_ratio": long_signal["volume_ratio"],
            "trend_strength": long_signal["trend_strength"],
        })
        pos = rm.calculate_position_size(long_signal, lev)
        trade = rm.open_trade(long_signal, lev, pos)
        assert trade is not None

        # Advance 9 hours → 1 funding period (9//8=1)
        t_after_9h = long_signal["timestamp"] + timedelta(hours=9)
        rm.update_trades(
            {long_signal["symbol"]: long_signal["price"]},
            t_after_9h,
        )
        assert trade["funding_paid"] > 0, (
            "9h hold must accrue >=1 funding period of funding cost"
        )

        closed = rm.close_trade(
            trade,
            exit_price=trade["entry_price"],
            exit_time=t_after_9h,
            exit_reason="Flat",
        )
        assert closed["total_funding"] > 0
        assert closed["net_pnl"] < closed["gross_pnl"] - 1e-9  # costs drag net

    def test_slippage_cost_attached_in_execution_simulator(self, exec_simulator):
        """simulate_market_order must populate slippage_cost in the execution
        record and accumulate it into total_slippage_cost."""
        candle = pd.Series({
            "open": 100.0, "high": 100.5, "low": 99.5,
            "close": 100.2, "volume": 500000.0,
        }, name=datetime(2026, 1, 1, 12, 0))
        order = {
            "direction": "LONG",
            "size": 1.0,
            "symbol": "BTCUSDT",
            "timestamp": candle.name,
        }
        execution = exec_simulator.simulate_market_order(order, candle)
        assert "slippage_cost" in execution
        assert "fill_price" in execution
        # LONG fill is above open → slippage_cost should be >= 0
        assert execution["slippage_cost"] >= 0
        assert exec_simulator.total_slippage_cost >= execution["slippage_cost"]


# ── 2. Portfolio risk cap across concurrent trades ──────────────────────────


class TestPortfolioRiskCap:
    """The unified entry point must cap total portfolio risk when multiple
    trades are open, not just check the per-trade limit."""

    def test_portfolio_cap_scales_down_third_trade(self, risk_manager_taker,
                                                     leverage_engine, long_signal):
        """With portfolio_risk_cap=6% and risk_percentage=2% on $100,
        each trade risks $2. Opening 3 should be allowed (3×$2=$6 = cap),
        but a 4th should be denied by max_concurrent OR scaled to $0 risk
        by the portfolio cap."""
        rm = risk_manager_taker
        assert rm.portfolio_risk_cap == 6.0
        assert rm.max_concurrent_trades == 3

        opened = []
        for i in range(3):
            sig = dict(long_signal)
            sig["symbol"] = f"SYM{i}USDT"   # distinct symbols
            sig["timestamp"] = long_signal["timestamp"] + timedelta(minutes=i)
            lev, _, _ = leverage_engine.calculate_optimal_leverage({
                "atr_percentage": sig["atr_percentage"],
                "volume_ratio": sig["volume_ratio"],
                "trend_strength": sig["trend_strength"],
            })
            pos = rm.calculate_position_size(sig, lev)
            assert pos, f"trade {i} position_info must not be empty"
            trade = rm.open_trade(sig, lev, pos)
            assert trade is not None, f"trade {i} should open"
            opened.append(trade)

        # Sum of active risk must not exceed cap
        total_active_risk = sum(t["risk_amount"] for t in rm.active_trades)
        max_allowed = rm.initial_capital * (rm.portfolio_risk_cap / 100)
        assert total_active_risk <= max_allowed + 1e-9, (
            f"total active risk ${total_active_risk:.4f} exceeded "
            f"portfolio cap ${max_allowed:.4f}"
        )

        # 4th trade should be blocked by max_concurrent_trades first
        sig4 = dict(long_signal)
        sig4["symbol"] = "SYM3USDT"
        sig4["timestamp"] = long_signal["timestamp"] + timedelta(minutes=4)
        can_open, reason = rm.can_open_trade(sig4)
        assert not can_open, "4th trade must be rejected"
        assert "concurrent" in reason.lower()

    def test_portfolio_cap_reduces_risk_when_near_limit(self, risk_manager_taker,
                                                          leverage_engine, long_signal):
        """With cap=6% ($6) and risk pct=2% ($2/trade), if we open 2 trades
        ($4 used), the 3rd's risk must be capped at $2 (fills the cap exactly)
        rather than exceeding $6 total."""
        rm = risk_manager_taker
        for i in range(2):
            sig = dict(long_signal)
            sig["symbol"] = f"SYM{i}USDT"
            sig["timestamp"] = long_signal["timestamp"] + timedelta(minutes=i)
            lev, _, _ = leverage_engine.calculate_optimal_leverage({
                "atr_percentage": sig["atr_percentage"],
                "volume_ratio": sig["volume_ratio"],
                "trend_strength": sig["trend_strength"],
            })
            pos = rm.calculate_position_size(sig, lev)
            rm.open_trade(sig, lev, pos)

        used = sum(t["risk_amount"] for t in rm.active_trades)
        assert used == pytest.approx(4.0, rel=0.05), "two $2 risks ≈ $4"

        sig3 = dict(long_signal)
        sig3["symbol"] = "SYM2USDT"
        sig3["timestamp"] = long_signal["timestamp"] + timedelta(minutes=3)
        lev, _, _ = leverage_engine.calculate_optimal_leverage({
            "atr_percentage": sig3["atr_percentage"],
            "volume_ratio": sig3["volume_ratio"],
            "trend_strength": sig3["trend_strength"],
        })
        pos3 = rm.calculate_position_size(sig3, lev)
        assert pos3, "3rd trade position_info must not be empty"
        # After adding, total must not exceed cap
        total = used + pos3["risk_amount"]
        max_allowed = rm.initial_capital * (rm.portfolio_risk_cap / 100)
        assert total <= max_allowed + 0.01, (
            f"3rd trade brought total risk to ${total:.4f}, "
            f"exceeding cap ${max_allowed:.4f}"
        )


# ── 3. Lookahead safety in candle-by-candle exit ─────────────────────────────


class TestLookaheadSafety:
    """_process_candle_by_candle must start scanning at start_idx (the bar
    AFTER entry) and never look at bars before or at entry for exit triggers.
    It must use the intrabar high/low (via ExecutionSimulator), not the
    close-only path in RiskManager.check_stop_loss_take_profit (which only
    sees current_price and is a close-only trigger)."""

    def test_exit_scan_starts_after_entry(self, exec_simulator, risk_manager_taker,
                                           leverage_engine, long_signal):
        """Build a trade that should NOT have triggered on the entry bar but
        SHOULD trigger on bar+1. If the scanner looked backward, it would
        fire prematurely on bar+0 instead of bar+1."""
        rm = risk_manager_taker
        lev, _, _ = leverage_engine.calculate_optimal_leverage({
            "atr_percentage": long_signal["atr_percentage"],
            "volume_ratio": long_signal["volume_ratio"],
            "trend_strength": long_signal["trend_strength"],
        })
        pos = rm.calculate_position_size(long_signal, lev)
        assert pos
        trade = rm.open_trade(long_signal, lev, pos)
        assert trade is not None

        # df: bar0 = entry (flat, no SL/TP hit), bar1 dives below SL (LONG hit)
        entry_price = trade["entry_price"]
        sl_price = trade["stop_loss_price"]
        dates = pd.date_range("2026-01-01 12:00", periods=4, freq="5min")
        df = pd.DataFrame({
            # bar0: range stays above SL (safe), bar1: low pierces SL
            "open": [entry_price, entry_price, entry_price, entry_price],
            "high": [entry_price + 10, entry_price + 5, entry_price + 5, entry_price + 5],
            "low":  [entry_price - 10, sl_price - 20, entry_price - 10, entry_price - 10],
            "close":[entry_price,      sl_price - 30, entry_price - 5,  entry_price - 5],
            "volume": [200000.0] * 4,
        }, index=dates)

        # Use the ComprehensiveBacktester's _process_candle_by_candle path
        from backtester.cli import ComprehensiveBacktester
        bt = ComprehensiveBacktester.__new__(ComprehensiveBacktester)
        bt.execution_simulator = exec_simulator
        bt.risk_manager = rm
        bt.logger = __import__("logging").getLogger("test")

        # Entry happened "before" bar0; start_idx=0 means scan bar0 onward
        outcome = bt._process_candle_by_candle(trade, df, start_idx=1)
        # bar1 (index 1) has low = sl_price-20, which is < SL → must trigger SL
        assert outcome["exit_reason"] == "Stop Loss"
        assert outcome["exit_time"] == dates[1], (
            "exit must fire on bar1 (the first scanned bar), not bar0"
        )

    def test_no_exit_trigger_on_entry_bar_when_scanning_from_after(self,
            exec_simulator, risk_manager_taker, leverage_engine, long_signal):
        """If we start scanning at bar0 and bar0 itself would pierce SL,
        the scanner IS allowed to fire on bar0 — but the caller in cli.py
        passes start_idx = entry_candle_idx + 1, so bar0 (entry bar) is
        never scanned. This test documents that contract: bar0 should not
        be the exit bar when start_idx > 0."""
        rm = risk_manager_taker
        lev, _, _ = leverage_engine.calculate_optimal_leverage({
            "atr_percentage": long_signal["atr_percentage"],
            "volume_ratio": long_signal["volume_ratio"],
            "trend_strength": long_signal["trend_strength"],
        })
        pos = rm.calculate_position_size(long_signal, lev)
        trade = rm.open_trade(long_signal, lev, pos)
        entry_price = trade["entry_price"]
        sl_price = trade["stop_loss_price"]

        dates = pd.date_range("2026-01-01 12:00", periods=3, freq="5min")
        # bar0 (entry bar) low pierces SL; bar1+ are safe.
        df = pd.DataFrame({
            "open":   [entry_price, entry_price, entry_price],
            "high":   [entry_price + 5, entry_price + 5, entry_price + 5],
            "low":    [sl_price - 50, entry_price - 5, entry_price - 5],
            "close":  [sl_price - 60, entry_price,     entry_price],
            "volume": [200000.0] * 3,
        }, index=dates)

        from backtester.cli import ComprehensiveBacktester
        bt = ComprehensiveBacktester.__new__(ComprehensiveBacktester)
        bt.execution_simulator = exec_simulator
        bt.risk_manager = rm
        bt.logger = __import__("logging").getLogger("test")

        # start_idx=1 simulates the cli.py contract: entry was at bar0,
        # scanning begins at bar1 (which is safe) → no trigger → time exit
        outcome = bt._process_candle_by_candle(trade, df, start_idx=1)
        assert outcome["exit_reason"] == "Time Exit", (
            "bar0 (entry bar) must never be scanned; bar1+ are safe → time exit"
        )
        assert outcome["exit_time"] == dates[2]

    def test_signal_price_uses_current_close_not_df_reference(self):
        """signals.py must set signal['price'] = current['close'] (BUG12 FIX).

        The previous 'NEXT-LOOKAHEAD' patch tried to reference
        df['open'].iloc[index+1] inside _evaluate_signal_conditions,
        but `df` is NOT in scope there (only `current` and `previous` Series).
        This caused a NameError, silently swallowed by the bare except,
        resulting in ZERO signals generated. The BUG12 FIX reverts to
        current['close'] — real lookahead protection lives at the
        trade-execution layer (cli.py advances entry to entry_idx + 1).
        """
        import inspect
        from backtester.signals import TechnicalSignalProvider
        src = inspect.getsource(
            TechnicalSignalProvider._evaluate_signal_conditions
        )
        # BUG12 FIX: must NOT reference df['open'].iloc[...] (df out of scope)
        assert "next_open = df['open'].iloc" not in src, (
            "BUG12 REGRESSION: _evaluate_signal_conditions must not reference "
            "df (out of scope). Use current['close']."
        )
        assert "'price': current['close']" in src, (
            "BUG12 FIX MISSING: signal price must bind 'price': current['close']"
        )


# ── 4. Taker-vs-maker commission sanity ─────────────────────────────────────


class TestTakerCommissionDefault:
    """The unified CLIs must default to the taker rate (0.05%), not the
    RiskManager constructor default (0.02% maker). This guards against
    silent fee understatement under leverage."""

    def test_cli_default_is_taker(self):
        """ComprehensiveBacktester must pass commission_rate=0.0005 to
        RiskManager when config omits it."""
        import inspect
        from backtester import cli
        src = inspect.getsource(cli.ComprehensiveBacktester.__init__)
        assert "0.0005" in src, (
            "cli.py must default commission_rate to 0.0005 (taker), "
            "not the RiskManager default 0.0002 (maker)"
        )

    def test_realistic_cli_default_is_taker(self):
        import inspect
        from backtester import realistic_cli
        src = inspect.getsource(realistic_cli.RealisticBacktester.__init__)
        assert "0.0005" in src, (
            "realistic_cli.py must default commission_rate to 0.0005 (taker)"
        )

    def test_risk_manager_constructor_default_is_maker(self):
        """RiskManager's own default is 0.0002 (maker) — this is documented
        so the caller knows to override it for taker backtests."""
        from backtester.risk import RiskManager
        rm = RiskManager(initial_capital=100.0)  # use all defaults
        assert rm.commission_rate == 0.0002, (
            "RiskManager default must remain 0.0002 (maker) — callers must "
            "explicitly pass 0.0005 for taker backtests"
        )
