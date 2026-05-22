
#!/usr/bin/env python3
"""
Comprehensive Backtest Runner
Runs advanced backtesting with the specified configuration and generates detailed reports
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

# Add SignalMaestro to path
sys.path.append(str(Path(__file__).parent / "SignalMaestro"))

from backtester.cli import run_comprehensive_backtest
from backtester.realistic_cli import RealisticBacktester

async def main():
    """Run comprehensive backtest with specified configuration"""
    
    print("🚀 COMPREHENSIVE BINANCE FUTURES USDM BACKTEST")
    print("=" * 60)
    
    # Configuration as requested
    config = {
        'initial_capital': 10.0,           # $10 USD capital
        'risk_percentage': 10.0,           # 10% risk per trade
        'max_concurrent_trades': 3,        # Maximum 3 trades
        'min_leverage': 10,                # Dynamic leverage 10x-75x
        'max_leverage': 75,
        'commission_rate': 0.0004,         # 0.04% Binance futures commission
        'sl1_percent': 1.5,               # Dynamic 3-level stop losses
        'sl2_percent': 4.0,
        'sl3_percent': 7.5,
        'tp1_percent': 2.0,               # Take profit levels
        'tp2_percent': 4.0,
        'tp3_percent': 6.0,
        'max_daily_loss': 2.0,            # $2 max daily loss
        'portfolio_risk_cap': 8.0,        # 8% portfolio risk cap
        'use_fixed_risk': True,            # Fixed risk to prevent compounding
        'seed': 42                         # Reproducible results
    }
    
    print(f"💰 Capital: ${config['initial_capital']}")
    print(f"📊 Risk per Trade: {config['risk_percentage']}%")
    print(f"🔄 Max Concurrent Trades: {config['max_concurrent_trades']}")
    print(f"⚡ Dynamic Leverage: {config['min_leverage']}x - {config['max_leverage']}x")
    print(f"🛑 Dynamic 3-Level Stop Losses: {config['sl1_percent']}%, {config['sl2_percent']}%, {config['sl3_percent']}%")
    print(f"🎯 Take Profit Levels: {config['tp1_percent']}%, {config['tp2_percent']}%, {config['tp3_percent']}%")
    print("=" * 60)
    
    try:
        # Run comprehensive backtest
        print("\n🔄 Starting Comprehensive Backtest...")
        results = await run_comprehensive_backtest()
        
        if results:
            print("\n✅ BACKTEST COMPLETED SUCCESSFULLY!")
            print("=" * 60)
            
            # Display key metrics
            print(f"📊 PERFORMANCE SUMMARY:")
            print(f"   • Total Trades: {results.get('total_trades', 0)}")
            print(f"   • Win Rate: {results.get('win_rate', 0):.1f}%")
            print(f"   • Total P&L: ${results.get('total_pnl', 0):.2f}")
            print(f"   • Return: {results.get('return_percentage', 0):.1f}%")
            print(f"   • Final Capital: ${results.get('final_capital', 0):.2f}")
            print(f"   • Max Consecutive Wins: {results.get('max_consecutive_wins', 0)}")
            print(f"   • Max Consecutive Losses: {results.get('max_consecutive_losses', 0)}")
            print(f"   • Trades per Hour: {results.get('trades_per_hour', 0):.3f}")
            print(f"   • Trades per Day: {results.get('trades_per_day', 0):.2f}")
            print(f"   • Max Drawdown: {results.get('max_drawdown_pct', 0):.1f}%")
            print(f"   • Profit Factor: {results.get('profit_factor', 0):.2f}")
            print(f"   • Sharpe Ratio: {results.get('sharpe_ratio', 0):.2f}")
            
            # Dynamic leverage analysis
            leverage_analysis = results.get('leverage_analysis', {})
            if leverage_analysis:
                avg_leverage = leverage_analysis.get('average_leverage_used', 0)
                print(f"   • Average Leverage Used: {avg_leverage:.1f}x")
                
                performance_by_leverage = leverage_analysis.get('performance_by_leverage', {})
                if performance_by_leverage:
                    print(f"   • Leverage Levels Tested: {len(performance_by_leverage)}")
            
            # Stop loss effectiveness
            print(f"\n🛑 DYNAMIC STOP LOSS ANALYSIS:")
            sl_analysis = results.get('stop_loss_analysis', {})
            if sl_analysis:
                print(f"   • SL1 Triggers: {sl_analysis.get('sl1_hits', 0)} ({sl_analysis.get('sl1_hits_percentage', 0):.1f}%)")
                print(f"   • SL2 Triggers: {sl_analysis.get('sl2_hits', 0)} ({sl_analysis.get('sl2_hits_percentage', 0):.1f}%)")
                print(f"   • SL3 Triggers: {sl_analysis.get('sl3_hits', 0)} ({sl_analysis.get('sl3_hits_percentage', 0):.1f}%)")
            
            print("\n📄 Detailed report saved to: COMPREHENSIVE_BACKTEST_REPORT.md")
            print("🔄 Now run: python enhance_bot_from_backtest.py")
            
        else:
            print("❌ Backtest failed to generate results")
            return 1
            
    except Exception as e:
        print(f"❌ Error running backtest: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
