#!/usr/bin/env python3
"""
Comprehensive Backtest Analysis Report
Provides detailed analysis of the enhanced trading bot performance
Including all requested metrics and breakdowns
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
import pandas as pd
import numpy as np
from dataclasses import asdict

# Import the backtesting engine and related components
from backtesting_engine import (
    BacktestingEngine, BacktestConfig, BacktestMetrics, 
    TradeResult, Position, DynamicLeverageCalculator
)

class ComprehensiveAnalyzer:
    """Provides detailed analysis of backtest results"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def run_enhanced_backtest(self) -> Dict[str, Any]:
        """Run enhanced backtest with comprehensive analysis"""
        
        # Configure backtest with exact specifications
        config = BacktestConfig(
            initial_capital=10.0,           # $10 USD
            risk_percentage=10.0,           # 10% risk per trade
            max_concurrent_trades=3,        # 3 concurrent trades
            commission_rate=0.0004,         # 0.04% futures commission
            min_leverage=10,                # Min leverage 10x
            max_leverage=75,                # Max leverage 75x
            sl1_percent=1.5,               # SL1 at 1.5%
            sl2_percent=4.0,               # SL2 at 4.0%
            sl3_percent=7.5,               # SL3 at 7.5%
            tp1_percent=2.0,               # TP1 at 2.0%
            tp2_percent=4.0,               # TP2 at 4.0%
            tp3_percent=6.0,               # TP3 at 6.0%
            start_date=datetime.now() - timedelta(days=30),  # Last 30 days
            end_date=datetime.now() - timedelta(days=1)
        )
        
        # Initialize engine
        engine = BacktestingEngine(config)
        
        # Define comprehensive symbol list
        symbols = [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'SOLUSDT',
            'XRPUSDT', 'AVAXUSDT', 'DOTUSDT', 'MATICUSDT', 'LTCUSDT',
            'BCHUSDT', 'LINKUSDT', 'ATOMUSDT', 'ALGOUSDT', 'VETUSDT'
        ]
        
        print("🚀 Starting Comprehensive Backtest Analysis")
        print("="*60)
        print(f"📊 Configuration:")
        print(f"   • Initial Capital: ${config.initial_capital:.2f}")
        print(f"   • Risk per Trade: {config.risk_percentage}%")
        print(f"   • Max Concurrent Trades: {config.max_concurrent_trades}")
        print(f"   • Dynamic Leverage: {config.min_leverage}x - {config.max_leverage}x")
        print(f"   • Stop Loss Levels: {config.sl1_percent}%, {config.sl2_percent}%, {config.sl3_percent}%")
        print(f"   • Take Profit Levels: {config.tp1_percent}%, {config.tp2_percent}%, {config.tp3_percent}%")
        print(f"   • Period: {config.start_date.strftime('%Y-%m-%d')} to {config.end_date.strftime('%Y-%m-%d')}")
        print(f"   • Symbols: {len(symbols)} pairs")
        print("="*60)
        
        # Run backtest
        try:
            metrics = await engine.run_backtest(symbols)
            
            # Generate comprehensive analysis
            analysis = self.generate_comprehensive_analysis(
                config, metrics, engine.trade_history, engine.position_history
            )
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"Error running enhanced backtest: {e}")
            return {"error": str(e)}
    
    def generate_comprehensive_analysis(self, config: BacktestConfig, 
                                      metrics: BacktestMetrics, 
                                      trade_history: List[TradeResult],
                                      position_history: List[Position]) -> Dict[str, Any]:
        """Generate comprehensive analysis of backtest results"""
        
        analysis = {
            "configuration": asdict(config),
            "basic_metrics": asdict(metrics),
            "detailed_analysis": {},
            "performance_breakdowns": {},
            "trading_statistics": {},
            "risk_analysis": {},
            "leverage_analysis": {},
            "stop_loss_analysis": {},
            "symbol_performance": {},
            "time_analysis": {},
            "recommendations": []
        }
        
        # 1. Detailed Performance Analysis
        analysis["detailed_analysis"] = {
            "win_rate": metrics.win_rate,
            "total_pnl_usd": metrics.total_pnl,
            "total_pnl_percentage": metrics.total_pnl_percentage,
            "profit_factor": metrics.profit_factor,
            "sharpe_ratio": metrics.sharpe_ratio,
            "sortino_ratio": metrics.sortino_ratio,
            "max_drawdown": metrics.max_drawdown,
            "max_drawdown_percentage": metrics.max_drawdown_percentage,
            "consecutive_wins": metrics.max_consecutive_wins,
            "consecutive_losses": metrics.max_consecutive_losses,
            "avg_trade_duration_hours": metrics.avg_trade_duration / 60,
            "trades_per_hour": metrics.trades_per_hour,
            "trades_per_day": metrics.trades_per_day,
            "total_commission": metrics.total_commission,
            "net_profit": metrics.total_pnl - metrics.total_commission,
            "roi_percentage": ((metrics.final_capital - config.initial_capital) / config.initial_capital) * 100
        }
        
        # 2. Leverage Analysis
        leverage_stats = self.analyze_leverage_performance(trade_history)
        analysis["leverage_analysis"] = leverage_stats
        
        # 3. Stop Loss Effectiveness
        sl_stats = self.analyze_stop_loss_effectiveness(trade_history)
        analysis["stop_loss_analysis"] = sl_stats
        
        # 4. Symbol Performance Breakdown
        symbol_stats = self.analyze_symbol_performance(trade_history)
        analysis["symbol_performance"] = symbol_stats
        
        # 5. Risk Analysis
        risk_stats = self.analyze_risk_metrics(trade_history, config)
        analysis["risk_analysis"] = risk_stats
        
        # 6. Trading Frequency Analysis
        freq_stats = self.analyze_trading_frequency(trade_history)
        analysis["time_analysis"] = freq_stats
        
        # 7. Generate Recommendations
        recommendations = self.generate_recommendations(analysis)
        analysis["recommendations"] = recommendations
        
        return analysis
    
    def analyze_leverage_performance(self, trades: List[TradeResult]) -> Dict[str, Any]:
        """Analyze performance by leverage levels"""
        leverage_groups = {
            "10x": [], "20x": [], "35x": [], "55x": [], "65x": [], "70x": [], "75x": []
        }
        
        for trade in trades:
            leverage = trade.leverage
            if leverage <= 15:
                leverage_groups["10x"].append(trade)
            elif leverage <= 25:
                leverage_groups["20x"].append(trade)
            elif leverage <= 45:
                leverage_groups["35x"].append(trade)
            elif leverage <= 60:
                leverage_groups["55x"].append(trade)
            elif leverage <= 67:
                leverage_groups["65x"].append(trade)
            elif leverage <= 72:
                leverage_groups["70x"].append(trade)
            else:
                leverage_groups["75x"].append(trade)
        
        analysis = {}
        for level, level_trades in leverage_groups.items():
            if level_trades:
                wins = sum(1 for t in level_trades if t.pnl > 0)
                total_pnl = sum(t.pnl for t in level_trades)
                avg_pnl = total_pnl / len(level_trades)
                
                analysis[level] = {
                    "trades": len(level_trades),
                    "win_rate": (wins / len(level_trades)) * 100,
                    "total_pnl": total_pnl,
                    "avg_pnl": avg_pnl,
                    "avg_duration": np.mean([t.duration_minutes for t in level_trades])
                }
        
        return analysis
    
    def analyze_stop_loss_effectiveness(self, trades: List[TradeResult]) -> Dict[str, Any]:
        """Analyze stop loss level effectiveness"""
        sl_stats = {
            "sl1_hits": 0, "sl2_hits": 0, "sl3_hits": 0,
            "tp1_hits": 0, "tp2_hits": 0, "tp3_hits": 0,
            "natural_closes": 0
        }
        
        for trade in trades:
            if "SL1" in trade.sl_levels_hit:
                sl_stats["sl1_hits"] += 1
            if "SL2" in trade.sl_levels_hit:
                sl_stats["sl2_hits"] += 1
            if "SL3" in trade.sl_levels_hit:
                sl_stats["sl3_hits"] += 1
            if "TP1" in trade.tp_levels_hit:
                sl_stats["tp1_hits"] += 1
            if "TP2" in trade.tp_levels_hit:
                sl_stats["tp2_hits"] += 1
            if "TP3" in trade.tp_levels_hit:
                sl_stats["tp3_hits"] += 1
            if not trade.sl_levels_hit and not trade.tp_levels_hit:
                sl_stats["natural_closes"] += 1
        
        total_trades = len(trades)
        if total_trades > 0:
            for key in sl_stats:
                sl_stats[f"{key}_percentage"] = (sl_stats[key] / total_trades) * 100
        
        return sl_stats
    
    def analyze_symbol_performance(self, trades: List[TradeResult]) -> Dict[str, Any]:
        """Analyze performance by trading symbol"""
        symbol_stats = {}
        
        for trade in trades:
            symbol = trade.symbol
            if symbol not in symbol_stats:
                symbol_stats[symbol] = {
                    "trades": 0, "wins": 0, "losses": 0,
                    "total_pnl": 0, "avg_duration": 0
                }
            
            symbol_stats[symbol]["trades"] += 1
            if trade.pnl > 0:
                symbol_stats[symbol]["wins"] += 1
            else:
                symbol_stats[symbol]["losses"] += 1
            symbol_stats[symbol]["total_pnl"] += trade.pnl
        
        # Calculate derived metrics
        for symbol, stats in symbol_stats.items():
            if stats["trades"] > 0:
                stats["win_rate"] = (stats["wins"] / stats["trades"]) * 100
                stats["avg_pnl"] = stats["total_pnl"] / stats["trades"]
        
        return symbol_stats
    
    def analyze_risk_metrics(self, trades: List[TradeResult], config: BacktestConfig) -> Dict[str, Any]:
        """Analyze risk-related metrics"""
        if not trades:
            return {}
        
        pnls = [trade.pnl for trade in trades]
        returns = [trade.pnl_percentage for trade in trades]
        
        risk_metrics = {
            "value_at_risk_95": np.percentile(pnls, 5),  # 95% VaR
            "value_at_risk_99": np.percentile(pnls, 1),  # 99% VaR
            "expected_shortfall": np.mean([p for p in pnls if p <= np.percentile(pnls, 5)]),
            "volatility": np.std(returns),
            "skewness": float(pd.Series(returns).skew()),
            "kurtosis": float(pd.Series(returns).kurtosis()),
            "max_risk_per_trade": config.initial_capital * (config.risk_percentage / 100),
            "actual_max_loss": min(pnls) if pnls else 0,
            "risk_utilization": (abs(min(pnls)) / (config.initial_capital * config.risk_percentage / 100)) * 100 if pnls else 0
        }
        
        return risk_metrics
    
    def analyze_trading_frequency(self, trades: List[TradeResult]) -> Dict[str, Any]:
        """Analyze trading frequency and timing"""
        if not trades:
            return {}
        
        # Group trades by hour of day
        hourly_distribution = {}
        daily_distribution = {}
        
        for trade in trades:
            hour = trade.entry_time.hour
            day = trade.entry_time.strftime('%A')
            
            hourly_distribution[hour] = hourly_distribution.get(hour, 0) + 1
            daily_distribution[day] = daily_distribution.get(day, 0) + 1
        
        # Calculate trading session performance
        sessions = {
            "Asian": list(range(0, 8)),      # 00:00 - 08:00 UTC
            "London": list(range(8, 16)),    # 08:00 - 16:00 UTC
            "New York": list(range(16, 24))  # 16:00 - 24:00 UTC
        }
        
        session_stats = {}
        for session, hours in sessions.items():
            session_trades = [t for t in trades if t.entry_time.hour in hours]
            if session_trades:
                session_stats[session] = {
                    "trades": len(session_trades),
                    "win_rate": (sum(1 for t in session_trades if t.pnl > 0) / len(session_trades)) * 100,
                    "avg_pnl": np.mean([t.pnl for t in session_trades])
                }
        
        return {
            "hourly_distribution": hourly_distribution,
            "daily_distribution": daily_distribution,
            "session_performance": session_stats,
            "avg_trades_per_day": len(trades) / 30,  # Assuming 30-day period
            "peak_trading_hour": max(hourly_distribution, key=hourly_distribution.get) if hourly_distribution else None
        }
    
    def generate_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate trading recommendations based on analysis"""
        recommendations = []
        
        basic_metrics = analysis["basic_metrics"]
        
        # Win rate recommendations
        if basic_metrics["win_rate"] < 40:
            recommendations.append("🔴 LOW WIN RATE: Consider tightening entry criteria and improving signal quality")
        elif basic_metrics["win_rate"] > 60:
            recommendations.append("🟢 EXCELLENT WIN RATE: Current strategy is performing well")
        
        # Profit factor recommendations
        if basic_metrics["profit_factor"] < 1.5:
            recommendations.append("🔴 LOW PROFIT FACTOR: Reduce position sizes or improve stop loss management")
        elif basic_metrics["profit_factor"] > 2.0:
            recommendations.append("🟢 STRONG PROFIT FACTOR: Consider increasing position sizes slightly")
        
        # Drawdown recommendations
        if basic_metrics["max_drawdown_percentage"] > 10:
            recommendations.append("🔴 HIGH DRAWDOWN: Implement stricter risk management and reduce concurrent trades")
        
        # Leverage recommendations
        leverage_analysis = analysis.get("leverage_analysis", {})
        best_leverage = None
        best_performance = -float('inf')
        
        for level, stats in leverage_analysis.items():
            if stats.get("win_rate", 0) > 50 and stats.get("avg_pnl", 0) > best_performance:
                best_performance = stats["avg_pnl"]
                best_leverage = level
        
        if best_leverage:
            recommendations.append(f"🎯 OPTIMAL LEVERAGE: {best_leverage} shows best risk-adjusted returns")
        
        # Trading frequency recommendations
        if basic_metrics["trades_per_day"] < 1:
            recommendations.append("📈 INCREASE FREQUENCY: Consider loosening entry criteria for more opportunities")
        elif basic_metrics["trades_per_day"] > 10:
            recommendations.append("📉 REDUCE FREQUENCY: High frequency may lead to overtrading")
        
        return recommendations

def format_comprehensive_report(analysis: Dict[str, Any]) -> str:
    """Format the comprehensive analysis into a readable report"""
    
    config = analysis["configuration"]
    metrics = analysis["basic_metrics"]
    detailed = analysis["detailed_analysis"]
    
    report = f"""
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                    🚀 COMPREHENSIVE TRADING BOT BACKTEST REPORT 🚀                   ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

📊 CONFIGURATION SUMMARY
{'='*90}
• Initial Capital: ${config['initial_capital']:.2f} USD
• Risk per Trade: {config['risk_percentage']}%
• Max Concurrent Trades: {config['max_concurrent_trades']}
• Dynamic Leverage Range: {config['min_leverage']}x - {config['max_leverage']}x
• Stop Loss Levels: SL1({config['sl1_percent']}%), SL2({config['sl2_percent']}%), SL3({config['sl3_percent']}%)
• Take Profit Levels: TP1({config['tp1_percent']}%), TP2({config['tp2_percent']}%), TP3({config['tp3_percent']}%)
• Commission Rate: {config['commission_rate']*100:.2f}%
• Testing Period: 30 Days (Recent Market Data)

💰 CORE PERFORMANCE METRICS
{'='*90}
• Final Capital: ${metrics['final_capital']:.2f}
• Total PnL: ${detailed['total_pnl_usd']:.4f} ({detailed['total_pnl_percentage']:.2f}%)
• Net Profit (After Fees): ${detailed['net_profit']:.4f}
• ROI: {detailed['roi_percentage']:.2f}%
• Total Trades: {metrics['total_trades']}
• Win Rate: {detailed['win_rate']:.1f}%
• Winning Trades: {metrics['winning_trades']}
• Losing Trades: {metrics['losing_trades']}

📈 ADVANCED PERFORMANCE METRICS
{'='*90}
• Profit Factor: {detailed['profit_factor']:.2f}
• Sharpe Ratio: {detailed['sharpe_ratio']:.2f}
• Sortino Ratio: {detailed['sortino_ratio']:.2f}
• Maximum Drawdown: {detailed['max_drawdown']:.2f}% (${detailed['max_drawdown']:.4f})
• Peak Capital: ${metrics['peak_capital']:.2f}

🎯 STREAK ANALYSIS
{'='*90}
• Maximum Consecutive Wins: {detailed['consecutive_wins']}
• Maximum Consecutive Losses: {detailed['consecutive_losses']}
• Current Win Streak: {metrics['current_win_streak']}
• Current Loss Streak: {metrics['current_loss_streak']}

⏰ TRADING FREQUENCY ANALYSIS
{'='*90}
• Average Trade Duration: {detailed['avg_trade_duration_hours']:.1f} hours
• Trades per Hour: {detailed['trades_per_hour']:.3f}
• Trades per Day: {detailed['trades_per_day']:.1f}
• Average Leverage Used: {metrics['avg_leverage_used']:.1f}x
• Leverage Efficiency: {metrics['leverage_efficiency']:.1f}%

💸 COST ANALYSIS
{'='*90}
• Total Commission Paid: ${detailed['total_commission']:.4f}
• Commission as % of Capital: {(detailed['total_commission']/config['initial_capital'])*100:.3f}%
• Average Commission per Trade: ${detailed['total_commission']/max(metrics['total_trades'],1):.4f}

"""

    # Add leverage analysis if available
    if "leverage_analysis" in analysis and analysis["leverage_analysis"]:
        report += f"""
⚡ DYNAMIC LEVERAGE PERFORMANCE BREAKDOWN
{'='*90}
"""
        for level, stats in analysis["leverage_analysis"].items():
            report += f"• {level} Leverage: {stats['trades']} trades, {stats['win_rate']:.1f}% win rate, ${stats['avg_pnl']:.4f} avg PnL\n"

    # Add stop loss analysis if available
    if "stop_loss_analysis" in analysis and analysis["stop_loss_analysis"]:
        sl_stats = analysis["stop_loss_analysis"]
        report += f"""
🛑 3-LEVEL STOP LOSS SYSTEM EFFECTIVENESS
{'='*90}
• SL1 (1.5%) Triggers: {sl_stats.get('sl1_hits', 0)} ({sl_stats.get('sl1_hits_percentage', 0):.1f}%)
• SL2 (4.0%) Triggers: {sl_stats.get('sl2_hits', 0)} ({sl_stats.get('sl2_hits_percentage', 0):.1f}%)
• SL3 (7.5%) Triggers: {sl_stats.get('sl3_hits', 0)} ({sl_stats.get('sl3_hits_percentage', 0):.1f}%)
• TP1 (2.0%) Hits: {sl_stats.get('tp1_hits', 0)} ({sl_stats.get('tp1_hits_percentage', 0):.1f}%)
• TP2 (4.0%) Hits: {sl_stats.get('tp2_hits', 0)} ({sl_stats.get('tp2_hits_percentage', 0):.1f}%)
• TP3 (6.0%) Hits: {sl_stats.get('tp3_hits', 0)} ({sl_stats.get('tp3_hits_percentage', 0):.1f}%)
• Natural Closes: {sl_stats.get('natural_closes', 0)} ({sl_stats.get('natural_closes_percentage', 0):.1f}%)
"""

    # Add risk analysis if available
    if "risk_analysis" in analysis and analysis["risk_analysis"]:
        risk = analysis["risk_analysis"]
        report += f"""
⚠️ RISK ANALYSIS
{'='*90}
• 95% Value at Risk: ${risk.get('value_at_risk_95', 0):.4f}
• 99% Value at Risk: ${risk.get('value_at_risk_99', 0):.4f}
• Expected Shortfall: ${risk.get('expected_shortfall', 0):.4f}
• Return Volatility: {risk.get('volatility', 0):.3f}%
• Max Risk per Trade: ${risk.get('max_risk_per_trade', 0):.2f}
• Actual Max Loss: ${risk.get('actual_max_loss', 0):.4f}
• Risk Utilization: {risk.get('risk_utilization', 0):.1f}%
"""

    # Add symbol performance if available
    if "symbol_performance" in analysis and analysis["symbol_performance"]:
        report += f"""
📊 TOP PERFORMING SYMBOLS
{'='*90}
"""
        symbol_performance = analysis["symbol_performance"]
        # Sort by total PnL
        sorted_symbols = sorted(symbol_performance.items(), key=lambda x: x[1].get("total_pnl", 0), reverse=True)
        for symbol, stats in sorted_symbols[:5]:  # Top 5
            report += f"• {symbol}: {stats['trades']} trades, {stats.get('win_rate', 0):.1f}% win rate, ${stats.get('total_pnl', 0):.4f} total PnL\n"

    # Add recommendations
    if "recommendations" in analysis and analysis["recommendations"]:
        report += f"""
💡 STRATEGIC RECOMMENDATIONS
{'='*90}
"""
        for i, rec in enumerate(analysis["recommendations"], 1):
            report += f"{i}. {rec}\n"

    report += f"""
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                               📈 SUMMARY CONCLUSION 📈                               ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

The Enhanced Trading Bot achieved a {detailed['roi_percentage']:.2f}% ROI over the 30-day testing period
with a {detailed['win_rate']:.1f}% win rate and {detailed['profit_factor']:.2f} profit factor.

✅ Capital Growth: ${config['initial_capital']:.2f} → ${metrics['final_capital']:.2f} (+${detailed['total_pnl_usd']:.4f})
✅ Risk Management: Max drawdown of {detailed['max_drawdown_percentage']:.2f}% kept losses controlled
✅ Efficiency: {detailed['trades_per_day']:.1f} trades/day with {detailed['avg_trade_duration_hours']:.1f}h avg duration
✅ Dynamic Leverage: Average {metrics['avg_leverage_used']:.1f}x leverage with {metrics['leverage_efficiency']:.1f}% efficiency

The bot demonstrates {'PROFITABLE' if detailed['total_pnl_usd'] > 0 else 'UNPROFITABLE'} performance with {'CONSERVATIVE' if detailed['max_drawdown_percentage'] < 5 else 'MODERATE' if detailed['max_drawdown_percentage'] < 10 else 'AGGRESSIVE'} risk characteristics.

{'🟢 RECOMMENDED FOR LIVE TRADING' if detailed['roi_percentage'] > 5 and detailed['win_rate'] > 45 and detailed['max_drawdown_percentage'] < 15 else '🟡 REQUIRES OPTIMIZATION' if detailed['roi_percentage'] > 0 else '🔴 NOT RECOMMENDED - NEEDS MAJOR IMPROVEMENTS'}

"""

    return report

async def main():
    """Execute comprehensive backtest analysis"""
    analyzer = ComprehensiveAnalyzer()
    
    print("🚀 Initializing Comprehensive Backtest Analysis...")
    print("This may take a few minutes to complete...")
    
    analysis = await analyzer.run_enhanced_backtest()
    
    if "error" in analysis:
        print(f"❌ Error: {analysis['error']}")
        return
    
    # Generate and display comprehensive report
    report = format_comprehensive_report(analysis)
    print(report)
    
    # Save detailed analysis to file
    with open("comprehensive_backtest_results.json", "w") as f:
        json.dump(analysis, f, indent=2, default=str)
    
    print("✅ Detailed analysis saved to 'comprehensive_backtest_results.json'")

if __name__ == "__main__":
    asyncio.run(main())