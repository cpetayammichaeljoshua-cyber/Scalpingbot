#!/usr/bin/env python3
"""
Comprehensive Backtesting CLI - Main orchestration and execution
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

# Import backtester modules
from .data import get_market_data, SyntheticDataProvider
from .signals import generate_trading_signals, MLSignalFilter
from .leverage import DynamicLeverageEngine
from .risk import RiskManager
from .exec import ExecutionSimulator
from .metrics import MetricsReporter

class ComprehensiveBacktester:
    """Main backtesting orchestrator"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = self._setup_logging()
        
        # Initialize components
        self.data_provider = SyntheticDataProvider(seed=config.get('seed', 42))
        self.leverage_engine = DynamicLeverageEngine(
            min_leverage=config.get('min_leverage', 10),
            max_leverage=config.get('max_leverage', 75)
        )
        self.risk_manager = RiskManager(
            initial_capital=config.get('initial_capital', 10.0),
            risk_percentage=config.get('risk_percentage', 3.0),  # Reduced from 10% to 3%
            max_concurrent_trades=config.get('max_concurrent_trades', 3),
            max_daily_loss=config.get('max_daily_loss', 2.0),
            portfolio_risk_cap=config.get('portfolio_risk_cap', 8.0),  # Max 8% total portfolio risk
            use_fixed_risk=config.get('use_fixed_risk', True),  # Use fixed risk to prevent compounding
            # NEXT-1: bot uses create_market_*_order everywhere → taker, not maker.
            # Prior backtests ran on RiskManager's default 0.02% (maker), under-
            # counting fees by 0.03%/side × leverage × 2 sides. At the backtester's
            # 10x default that understated cost by 0.6%/trade; at 75x cap by 4.5%/trade.
            # 0.05% = Binance Futures USDT-M default taker (BTCUSDT/ETHUSDT/altcoins).
            commission_rate=config.get('commission_rate', 0.0005),
            funding_rate=config.get('funding_rate', 0.0001),
        )
        self.execution_simulator = ExecutionSimulator()
        self.metrics_reporter = MetricsReporter()
        
        # Tracking
        self.completed_trades = []
        self.signals_generated = 0
        self.signals_taken = 0
        
    def _setup_logging(self) -> logging.Logger:
        """Setup comprehensive logging"""
        logger = logging.getLogger('ComprehensiveBacktester')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            # File handler
            file_handler = logging.FileHandler('backtest_output.log')
            file_handler.setLevel(logging.DEBUG)
            
            # Formatter
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(formatter)
            file_handler.setFormatter(formatter)
            
            logger.addHandler(console_handler)
            logger.addHandler(file_handler)
        
        return logger
    
    async def run_comprehensive_backtest(self) -> Dict[str, Any]:
        """Run the complete backtesting process"""
        
        self.logger.info("🚀 Starting Comprehensive Binance Futures USDM Backtest")
        self.logger.info("=" * 80)
        
        # Display configuration
        self._log_configuration()
        
        start_time = time.time()
        
        try:
            # Get crypto symbols for testing
            crypto_symbols = [
                'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'SOLUSDT',
                'XRPUSDT', 'DOTUSDT', 'MATICUSDT', 'UNIUSDT', 'LINKUSDT'
            ]
            
            self.logger.info(f"📊 Processing {len(crypto_symbols)} cryptocurrency pairs")
            self.logger.info("🔄 Fetching market data and generating signals...")
            
            # Process each symbol
            for i, symbol in enumerate(crypto_symbols, 1):
                self.logger.info(f"[{i}/{len(crypto_symbols)}] Processing {symbol}...")
                
                # Get market data (7 days of 5-minute candles)
                df = await get_market_data(symbol, timeframe='5m', limit=2016, use_real_data=False)
                
                if df.empty:
                    self.logger.warning(f"No data available for {symbol}")
                    continue
                
                # Generate trading signals
                signals = await generate_trading_signals(df, symbol, use_ml_filter=True)
                self.signals_generated += len(signals)
                
                if not signals:
                    self.logger.debug(f"No signals generated for {symbol}")
                    continue
                
                self.logger.info(f"📈 Generated {len(signals)} signals for {symbol}")
                
                # Process signals chronologically
                for signal in sorted(signals, key=lambda x: x['timestamp']):
                    await self._process_signal(signal, df)
                
                # Update any remaining active trades
                if self.risk_manager.active_trades:
                    await self._update_active_trades(df.iloc[-1], df.index[-1])
            
            # Close any remaining trades
            await self._close_remaining_trades()
            
            # Calculate comprehensive results
            results = await self._calculate_final_results()
            
            # Display results
            self._display_results(results)
            
            # Generate report
            await self._generate_report(results)
            
            execution_time = time.time() - start_time
            self.logger.info(f"⏱️ Backtest completed in {execution_time:.2f} seconds")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Backtest error: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _log_configuration(self):
        """Log backtest configuration"""
        self.logger.info(f"💰 Initial Capital: ${self.config.get('initial_capital', 10.0)}")
        self.logger.info(f"📊 Risk per Trade: {self.config.get('risk_percentage', 3.0)}%")  # NEXT-BUG3 FIX: was 10.0
        self.logger.info(f"📈 Max Concurrent Trades: {self.config.get('max_concurrent_trades', 3)}")
        self.logger.info(f"⚡ Dynamic Leverage: {self.config.get('min_leverage', 10)}x - {self.config.get('max_leverage', 75)}x")
        self.logger.info(f"📅 Backtest Period: 7 days")
        self.logger.info(f"🎯 Stop Loss: 1.5%")
        self.logger.info(f"💎 Take Profit: 4.5% (1:3 R/R)")
        self.logger.info("=" * 80)
    
    async def _process_signal(self, signal: Dict[str, Any], df) -> bool:
        """Process a single trading signal with candle-by-candle outcome simulation"""
        
        try:
            # Check if signal should be taken
            can_trade, reason = self.risk_manager.can_open_trade(signal)
            if not can_trade:
                self.logger.debug(f"Signal rejected: {reason}")
                return False
            
            # Calculate dynamic leverage
            market_data = {
                'atr_percentage': signal.get('atr_percentage', 1.0),
                'volume_ratio': signal.get('volume_ratio', 1.0),
                'trend_strength': signal.get('trend_strength', 0.5)
            }
            
            leverage, vol_category, efficiency = self.leverage_engine.calculate_optimal_leverage(market_data)
            
            # Calculate position size
            position_info = self.risk_manager.calculate_position_size(signal, leverage)
            if not position_info:
                return False
            
            # Open trade
            trade = self.risk_manager.open_trade(signal, leverage, position_info)
            if not trade:
                return False
            
            self.signals_taken += 1
            
            # Simulate trade execution at signal timestamp
            signal_time = signal['timestamp']
            entry_candle_idx = df.index.get_indexer([signal_time], method='nearest')[0]
            
            # Execute entry at the candle after signal (or signal candle if no next)
            if entry_candle_idx + 1 < len(df):
                entry_candle = df.iloc[entry_candle_idx + 1]
            else:
                entry_candle = df.iloc[entry_candle_idx]
            
            order = {
                'direction': signal['direction'],
                'size': trade['position_size'],
                'symbol': signal['symbol'],
                'timestamp': entry_candle.name
            }
            
            entry_execution = self.execution_simulator.simulate_market_order(order, entry_candle)
            
            # Update entry price to the actual fill price (not signal price)
            if entry_execution and 'fill_price' in entry_execution:
                trade['entry_price'] = entry_execution['fill_price']
                # Dynamic ATR-based SL/TP — BUG10 FIX: was hardcoded 1.5%/4.5%
                # overriding risk_manager's computed stop_loss_price. Use the
                # signal's atr_percentage (or fall back to 1.5%) so volatility
                # scales the stop. R/R stays 1:3 (TP = 3 × SL).
                # BUG13 FIX: SL = 1×ATR was too tight — median candle range is ~1.1%
                # of price (same as median ATR), so intrabar wicks triggered SL
                # before TP could clear. Now SL = 1.5×ATR (industry-standard buffer)
                # and TP = 3×SL (= 4.5×ATR), preserving the 1:3 R/R while giving
                # trades room to breathe through normal volatility.
                _atr_pct = float(signal.get('atr_percentage', 1.5) or 1.5)
                # Clamp ATR to a safe band so synth outliers don't blow risk
                _atr_pct = max(0.5, min(_atr_pct, 3.0))
                _sl_dist = trade['entry_price'] * (_atr_pct * 1.5 / 100.0)
                if trade['direction'] == 'LONG':
                    trade['stop_loss_price'] = trade['entry_price'] - _sl_dist
                    trade['take_profit_price'] = trade['entry_price'] + (_sl_dist * 3)
                else:
                    trade['stop_loss_price'] = trade['entry_price'] + _sl_dist
                    trade['take_profit_price'] = trade['entry_price'] - (_sl_dist * 3)
            
            # Process candle-by-candle from entry to find SL/TP exit
            outcome = self._process_candle_by_candle(trade, df, entry_candle_idx + 1)
            
            # Close trade with actual market outcome
            completed_trade = self.risk_manager.close_trade(
                trade, outcome['exit_price'], 
                outcome['exit_time'], outcome['exit_reason']
            )
            
            # Track performance
            self.leverage_engine.track_leverage_performance(leverage, completed_trade['net_pnl'])
            self.completed_trades.append(completed_trade)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error processing signal: {e}")
            return False
    
    def _process_candle_by_candle(self, trade: Dict[str, Any], df, start_idx: int) -> Dict[str, Any]:
        """
        Process trade candle-by-candle from entry to determine SL/TP exit.
        Replaces the fabricated random-outcome simulation with real market data.
        """
        max_candles = 48  # 4 hours at 5m candles
        
        for i in range(start_idx, min(start_idx + max_candles, len(df))):
            candle = df.iloc[i]
            
            # Update trade PnL with current candle
            current_prices = {trade['symbol']: candle['close']}
            self.risk_manager.update_trades(current_prices, candle.name)
            
            # Check SL/TP using intrabar highs/lows (via ExecutionSimulator)
            triggers = self.execution_simulator.process_stop_loss_take_profit(
                [trade], candle
            )
            
            if triggers:
                trigger_trade, exit_price, exit_reason = triggers[0]
                return {
                    'exit_price': exit_price,
                    'exit_time': candle.name,
                    'exit_reason': exit_reason
                }
        
        # No SL/TP hit within max hold time — close at last candle close
        last_candle = df.iloc[min(start_idx + max_candles - 1, len(df) - 1)]
        return {
            'exit_price': last_candle['close'],
            'exit_time': last_candle.name,
            'exit_reason': 'Time Exit'
        }
    
    async def _update_active_trades(self, current_candle, current_time):
        """Update active trades with current market data using intrabar SL/TP"""
        
        if not self.risk_manager.active_trades:
            return
        
        # Create price dictionary
        current_prices = {}
        for trade in self.risk_manager.active_trades:
            current_prices[trade['symbol']] = current_candle['close']
        
        # Update trades with close-price PnL
        self.risk_manager.update_trades(current_prices, current_time)
        
        # NEXT-BUG8 FIX: Use ExecutionSimulator for intrabar SL/TP detection
        # (high/low range) instead of risk_manager.check_stop_loss_take_profit
        # which only uses close price — close-price checks miss intrabar stops.
        triggers = self.execution_simulator.process_stop_loss_take_profit(
            self.risk_manager.active_trades, current_candle
        )
        
        for trade, exit_price, exit_reason in triggers:
            completed_trade = self.risk_manager.close_trade(trade, exit_price, current_time, exit_reason)
            self.completed_trades.append(completed_trade)
    
    async def _close_remaining_trades(self):
        """Close any remaining active trades at market price"""
        
        while self.risk_manager.active_trades:
            trade = self.risk_manager.active_trades[0]
            
            # Use entry price as closing price (neutral outcome)
            exit_price = trade['entry_price']
            exit_time = datetime.now()
            
            completed_trade = self.risk_manager.close_trade(trade, exit_price, exit_time, "End of Backtest")
            self.completed_trades.append(completed_trade)
    
    async def _calculate_final_results(self) -> Dict[str, Any]:
        """Calculate comprehensive final results"""
        
        try:
            # Get component metrics
            risk_metrics = self.risk_manager.get_risk_metrics()
            leverage_metrics = self.leverage_engine.get_leverage_performance_report()
            execution_stats = self.execution_simulator.get_execution_statistics()
            
            # Calculate comprehensive metrics
            backtest_hours = 7 * 24  # 7 days
            
            comprehensive_metrics = self.metrics_reporter.calculate_comprehensive_metrics(
                completed_trades=self.completed_trades,
                initial_capital=self.config.get('initial_capital', 10.0),
                final_capital=self.risk_manager.current_capital,
                backtest_hours=backtest_hours,
                risk_metrics=risk_metrics,
                leverage_metrics=leverage_metrics,
                execution_stats=execution_stats
            )
            
            # Add signal processing metrics
            comprehensive_metrics.update({
                'signals_generated': self.signals_generated,
                'signals_taken': self.signals_taken,
                'signal_selection_rate': (self.signals_taken / self.signals_generated * 100) if self.signals_generated > 0 else 0
            })
            
            return comprehensive_metrics
            
        except Exception as e:
            self.logger.error(f"Error calculating final results: {e}")
            return {}
    
    def _display_results(self, results: Dict[str, Any]):
        """Display comprehensive results"""
        
        self.logger.info("\n" + "=" * 80)
        self.logger.info("📊 COMPREHENSIVE BACKTEST RESULTS")
        self.logger.info("=" * 80)
        
        # Signal processing
        self.logger.info(f"📈 Total Signals Generated: {results.get('signals_generated', 0)}")
        self.logger.info(f"✅ Signals Taken: {results.get('signals_taken', 0)}")
        self.logger.info(f"📊 Signal Selection Rate: {results.get('signal_selection_rate', 0):.1f}%")
        self.logger.info("")
        
        # Basic performance
        self.logger.info(f"🎯 Total Trades: {results.get('total_trades', 0)}")
        self.logger.info(f"✅ Winning Trades: {results.get('winning_trades', 0)}")
        self.logger.info(f"❌ Losing Trades: {results.get('losing_trades', 0)}")
        self.logger.info(f"🏆 Win Rate: {results.get('win_rate', 0):.1f}%")
        self.logger.info("")
        
        # Financial performance
        self.logger.info(f"💰 Total PnL: ${results.get('total_pnl', 0):.2f}")
        self.logger.info(f"📊 Return: {results.get('return_percentage', 0):.1f}%")
        self.logger.info(f"💎 Final Capital: ${results.get('final_capital', 0):.2f}")
        self.logger.info(f"📈 Gross Profit: ${results.get('gross_profit', 0):.2f}")
        self.logger.info(f"📉 Gross Loss: ${results.get('gross_loss', 0):.2f}")
        self.logger.info(f"⚖️ Profit Factor: {results.get('profit_factor', 0):.2f}")
        self.logger.info("")
        
        # Consecutive performance
        self.logger.info(f"🔥 Max Consecutive Wins: {results.get('max_consecutive_wins', 0)}")
        self.logger.info(f"❄️ Max Consecutive Losses: {results.get('max_consecutive_losses', 0)}")
        self.logger.info(f"🔥 Current Consecutive Wins: {results.get('current_consecutive_wins', 0)}")
        self.logger.info(f"❄️ Current Consecutive Losses: {results.get('current_consecutive_losses', 0)}")
        self.logger.info("")
        
        # Timing metrics
        self.logger.info(f"⏰ Trades per Hour: {results.get('trades_per_hour', 0):.3f}")
        self.logger.info(f"📅 Trades per Day: {results.get('trades_per_day', 0):.2f}")
        self.logger.info(f"⌚ Avg Trade Duration: {results.get('avg_trade_duration_minutes', 0):.1f} minutes")
        self.logger.info("")
        
        # Risk metrics
        self.logger.info(f"📉 Max Drawdown: {results.get('max_drawdown_pct', 0):.1f}%")
        self.logger.info(f"🏔️ Peak Capital: ${results.get('peak_capital', 0):.2f}")
        self.logger.info(f"📈 Sharpe Ratio: {results.get('sharpe_ratio', 0):.2f}")
        self.logger.info("")
        
        # Leverage analysis
        leverage_analysis = results.get('leverage_analysis', {})
        avg_leverage = leverage_analysis.get('average_leverage_used', 0)
        self.logger.info(f"⚡ Avg Leverage Used: {avg_leverage:.1f}x")
        
        # Find max/min leverage from performance data
        performance_by_leverage = leverage_analysis.get('performance_by_leverage', {})
        if performance_by_leverage:
            max_leverage = max(performance_by_leverage.keys())
            min_leverage = min(performance_by_leverage.keys())
            efficiency = (avg_leverage / self.config.get('max_leverage', 75)) * 100
            
            self.logger.info(f"⚡ Max Leverage Used: {max_leverage}x")
            self.logger.info(f"⚡ Min Leverage Used: {min_leverage}x")
            self.logger.info(f"📊 Leverage Efficiency: {efficiency:.1f}%")
        
        self.logger.info("=" * 80)
    
    async def _generate_report(self, results: Dict[str, Any]):
        """Generate detailed report file"""
        
        try:
            # Generate formatted report
            report = self.metrics_reporter.generate_performance_report(results)
            
            # Write to file
            report_file = Path("COMPREHENSIVE_BACKTEST_REPORT.md")
            with open(report_file, 'w') as f:
                f.write(report)
            
            self.logger.info(f"📄 Detailed report saved to {report_file}")
            
        except Exception as e:
            self.logger.error(f"Error generating report: {e}")

async def run_comprehensive_backtest():
    """Main entry point for comprehensive backtesting"""
    
    # Configuration — NEXT-BUG2 FIX: risk_percentage was 10.0 here but
    # __init__ defaults to 3.0. _log_configuration showed 10.0 misleadingly.
    # Standardized to 3.0 (institutional-grade risk per trade).
    config = {
        'initial_capital': 10.0,
        'risk_percentage': 3.0,  # NEXT-BUG2 FIX: was 10.0, inconsistent with __init__
        'max_concurrent_trades': 3,
        'min_leverage': 10,
        'max_leverage': 75,
        'max_daily_loss': 2.0,
        'seed': 42
    }
    
    # Run backtest
    backtester = ComprehensiveBacktester(config)
    results = await backtester.run_comprehensive_backtest()
    
    return results

if __name__ == "__main__":
    asyncio.run(run_comprehensive_backtest())