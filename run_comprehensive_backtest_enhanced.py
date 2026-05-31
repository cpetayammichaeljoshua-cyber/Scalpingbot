
#!/usr/bin/env python3
"""
Enhanced Comprehensive Backtest Runner
Advanced backtesting with price action analysis, liquidity mapping, timing optimization,
Schelling points, order flow analysis, and strategic positioning
"""

import asyncio
import logging
import sys
import os
from pathlib import Path
from datetime import datetime

# Add SignalMaestro to path
sys.path.append(str(Path(__file__).parent / "SignalMaestro"))

from backtester.cli import run_comprehensive_backtest

async def run_enhanced_backtest():
    """Run enhanced comprehensive backtest with advanced analysis"""
    
    print("🚀 ENHANCED COMPREHENSIVE BINANCE FUTURES USDM BACKTEST")
    print("=" * 80)
    print("✨ Advanced Features Enabled:")
    print("   • Advanced Price Action Analysis")
    print("   • Advanced Liquidity & Engineered Liquidity Mapping")
    print("   • Advanced Timing & Sequential Move Analysis")
    print("   • Advanced Schelling Points Identification")
    print("   • Advanced Order Flow Analysis")  
    print("   • Advanced Strategic Positioning")
    print("   • Dynamic 3-Level Stop Loss System")
    print("   • Dynamic Leverage Optimization (10x-75x)")
    print("=" * 80)
    
    # Enhanced configuration with advanced features
    enhanced_config = {
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
        'seed': 42,                        # Reproducible results
        
        # Advanced features
        'advanced_price_action': True,
        'liquidity_analysis': True,
        'engineered_liquidity_detection': True,
        'sequential_move_analysis': True,
        'schelling_points_identification': True,
        'order_flow_analysis': True,
        'strategic_positioning': True,
        'dynamic_stop_loss_system': True,
        'market_session_optimization': True,
        'volatility_based_sizing': True
    }
    
    print(f"💰 Enhanced Configuration:")
    print(f"   • Capital: ${enhanced_config['initial_capital']}")
    print(f"   • Risk per Trade: {enhanced_config['risk_percentage']}%")
    print(f"   • Max Concurrent Trades: {enhanced_config['max_concurrent_trades']}")
    print(f"   • Dynamic Leverage: {enhanced_config['min_leverage']}x - {enhanced_config['max_leverage']}x")
    print(f"   • Advanced Price Action: {'✅' if enhanced_config['advanced_price_action'] else '❌'}")
    print(f"   • Liquidity Analysis: {'✅' if enhanced_config['liquidity_analysis'] else '❌'}")
    print(f"   • Order Flow Analysis: {'✅' if enhanced_config['order_flow_analysis'] else '❌'}")
    print(f"   • Strategic Positioning: {'✅' if enhanced_config['strategic_positioning'] else '❌'}")
    print("=" * 80)
    
    try:
        # Run enhanced comprehensive backtest
        print("\n🔄 Starting Enhanced Comprehensive Backtest...")
        results = await run_comprehensive_backtest()
        
        if results:
            print("\n✅ ENHANCED BACKTEST COMPLETED SUCCESSFULLY!")
            print("=" * 80)
            
            # Display enhanced metrics
            print(f"📊 ENHANCED PERFORMANCE SUMMARY:")
            print(f"   • Total Trades: {results.get('total_trades', 0)}")
            print(f"   • Win Rate: {results.get('win_rate', 0):.1f}%")
            print(f"   • Total P&L: ${results.get('total_pnl', 0):.4f}")
            print(f"   • Return: {results.get('return_percentage', 0):.1f}%")
            print(f"   • Final Capital: ${results.get('final_capital', 0):.4f}")
            print(f"   • Max Consecutive Wins: {results.get('max_consecutive_wins', 0)}")
            print(f"   • Max Consecutive Losses: {results.get('max_consecutive_losses', 0)}")
            print(f"   • Trades per Hour: {results.get('trades_per_hour', 0):.3f}")
            print(f"   • Trades per Day: {results.get('trades_per_day', 0):.2f}")
            print(f"   • Max Drawdown: {results.get('max_drawdown_pct', 0):.1f}%")
            print(f"   • Profit Factor: {results.get('profit_factor', 0):.2f}")
            print(f"   • Sharpe Ratio: {results.get('sharpe_ratio', 0):.2f}")
            
            # Enhanced analytics
            print(f"\n🚀 ADVANCED ANALYTICS:")
            
            # Dynamic leverage analysis
            leverage_analysis = results.get('leverage_analysis', {})
            if leverage_analysis:
                avg_leverage = leverage_analysis.get('average_leverage_used', 0)
                print(f"   • Average Leverage Used: {avg_leverage:.1f}x")
                print(f"   • Leverage Efficiency: {(avg_leverage/75)*100:.1f}%")
                
                performance_by_leverage = leverage_analysis.get('performance_by_leverage', {})
                if performance_by_leverage:
                    print(f"   • Leverage Levels Tested: {len(performance_by_leverage)}")
                    best_leverage = max(performance_by_leverage.keys(), 
                                      key=lambda k: performance_by_leverage[k].get('avg_pnl_per_trade', 0))
                    print(f"   • Best Performing Leverage: {best_leverage}x")
            
            # Advanced stop loss analysis
            print(f"\n🛑 DYNAMIC 3-LEVEL STOP LOSS ANALYSIS:")
            sl_analysis = results.get('stop_loss_analysis', {})
            if sl_analysis:
                print(f"   • SL1 (1.5%) Triggers: {sl_analysis.get('sl1_hits', 0)} ({sl_analysis.get('sl1_hits_percentage', 0):.1f}%)")
                print(f"   • SL2 (4.0%) Triggers: {sl_analysis.get('sl2_hits', 0)} ({sl_analysis.get('sl2_hits_percentage', 0):.1f}%)")
                print(f"   • SL3 (7.5%) Triggers: {sl_analysis.get('sl3_hits', 0)} ({sl_analysis.get('sl3_hits_percentage', 0):.1f}%)")
                print(f"   • Natural Closes: {sl_analysis.get('natural_closes', 0)} ({sl_analysis.get('natural_closes_percentage', 0):.1f}%)")
            
            # Advanced signal analysis
            advanced_signals = results.get('advanced_signal_analysis', {})
            if advanced_signals:
                print(f"\n🎯 ADVANCED SIGNAL ANALYSIS:")
                print(f"   • Price Action Signals: {advanced_signals.get('price_action_signals', 0)}")
                print(f"   • Liquidity Zone Signals: {advanced_signals.get('liquidity_signals', 0)}")
                print(f"   • Schelling Point Signals: {advanced_signals.get('schelling_signals', 0)}")
                print(f"   • Order Flow Signals: {advanced_signals.get('order_flow_signals', 0)}")
                print(f"   • Strategic Position Signals: {advanced_signals.get('strategic_signals', 0)}")
            
            # Market structure analysis
            market_structure = results.get('market_structure_analysis', {})
            if market_structure:
                print(f"\n📈 MARKET STRUCTURE INSIGHTS:")
                print(f"   • Trend Alignment Success Rate: {market_structure.get('trend_alignment_success', 0):.1f}%")
                print(f"   • Liquidity Grab Success Rate: {market_structure.get('liquidity_grab_success', 0):.1f}%")
                print(f"   • Session-Based Performance: {market_structure.get('best_session', 'Mixed')}")
                print(f"   • Volatility Adaptation Score: {market_structure.get('volatility_adaptation', 0):.2f}")
            
            print("\n📄 Enhanced detailed report saved to: ENHANCED_COMPREHENSIVE_BACKTEST_REPORT.md")
            print("🔄 Now run: python enhance_bot_from_backtest_enhanced.py")
            
        else:
            print("❌ Enhanced backtest failed to generate results")
            return 1
            
    except Exception as e:
        print(f"❌ Error running enhanced backtest: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    print("🌟 Welcome to Enhanced Comprehensive Backtesting System")
    print("🔧 Loading advanced price action, liquidity, and strategic analysis...")
    
    exit_code = asyncio.run(run_enhanced_backtest())
    
    if exit_code == 0:
        print("\n🎉 Enhanced backtest completed successfully!")
        print("📊 Check ENHANCED_COMPREHENSIVE_BACKTEST_REPORT.md for detailed analysis")
        print("🚀 Ready to run enhancement phase with: python enhance_bot_from_backtest_enhanced.py")
    
    sys.exit(exit_code)
