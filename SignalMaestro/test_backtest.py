#!/usr/bin/env python3
"""
Test script to run backtesting engine and verify functionality
"""

import asyncio
import logging
from datetime import datetime, timedelta
from backtesting_engine import BacktestingEngine, BacktestConfig

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def run_quick_backtest():
    """Run a quick backtest to verify system functionality"""
    
    # Create backtest configuration for a short test period
    config = BacktestConfig(
        initial_capital=10.0,  # $10 USD
        risk_percentage=10.0,  # 10% risk per trade
        max_concurrent_trades=3,
        start_date=datetime.now() - timedelta(days=7),  # Last 7 days
        end_date=datetime.now() - timedelta(days=1),  # Until yesterday
        timeframes=['5m', '15m', '1h']  # Focus on shorter timeframes for testing
    )
    
    print(f"🚀 Starting backtest with ${config.initial_capital} capital...")
    print(f"📅 Period: {config.start_date.strftime('%Y-%m-%d')} to {config.end_date.strftime('%Y-%m-%d')}")
    
    # Initialize backtesting engine
    engine = BacktestingEngine(config)
    
    try:
        # Initialize exchange connection
        await engine.initialize_exchange()
        
        # Test with a few popular trading pairs
        test_symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT']
        
        for symbol in test_symbols:
            print(f"\n📊 Testing data fetch for {symbol}...")
            
            # Test data fetching
            data = await engine.fetch_historical_data(symbol, '5m', limit=100)
            
            if data and len(data) > 0:
                print(f"✅ Successfully fetched {len(data)} candles for {symbol}")
                
                # Create test signal
                test_signal = {
                    'symbol': symbol,
                    'direction': 'BUY',
                    'entry_price': data[-1][4],  # Close price of last candle
                    'signal_strength': 85,
                    'volatility': 0.015,  # 1.5% volatility
                    'volume_ratio': 1.2,
                    'trend_strength': 0.7,
                    'rsi': 45
                }
                
                print(f"🎯 Testing signal processing for {symbol}...")
                
                # Test signal processing
                current_time = datetime.now()
                result = await engine.process_signal(test_signal, current_time)
                
                if result:
                    print(f"✅ Signal processed successfully - position opened")
                else:
                    print(f"❌ Signal filtered out or couldn't open position")
                
            else:
                print(f"❌ No data available for {symbol}")
        
        # Display current system status
        print(f"\n📈 System Status:")
        print(f"💰 Current Capital: ${engine.capital:.2f}")
        print(f"📊 Active Positions: {len(engine.active_positions)}")
        print(f"📋 Trade History: {len(engine.trade_history)}")
        
        # Test metrics calculation if we have any trades
        if engine.trade_history:
            metrics = await engine.calculate_metrics()
            print(f"\n📊 Sample Metrics:")
            print(f"Win Rate: {metrics.win_rate:.1f}%")
            print(f"Total PnL: ${metrics.total_pnl:.2f}")
            print(f"Max Drawdown: {metrics.max_drawdown_percentage:.2f}%")
        
        print(f"\n✅ Backtesting engine test completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during backtest: {e}")
        raise
    
    finally:
        # Close exchange connection
        if engine.exchange:
            await engine.exchange.close()

if __name__ == "__main__":
    asyncio.run(run_quick_backtest())