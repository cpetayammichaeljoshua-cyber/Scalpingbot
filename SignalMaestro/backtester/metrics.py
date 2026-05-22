#!/usr/bin/env python3
"""
MetricsReporter - Comprehensive backtest results analysis and reporting
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging

class MetricsReporter:
    """Comprehensive metrics calculation and reporting for backtest results"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def calculate_comprehensive_metrics(self, completed_trades: List[Dict[str, Any]],
                                      initial_capital: float, final_capital: float,
                                      backtest_hours: float, risk_metrics: Dict[str, Any],
                                      leverage_metrics: Dict[str, Any],
                                      execution_stats: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate all comprehensive backtest metrics
        
        Returns:
            Complete metrics dictionary with all KPIs
        """
        
        try:
            if not completed_trades:
                return self._get_empty_metrics(initial_capital, final_capital)
            
            # Basic trade metrics
            basic_metrics = self._calculate_basic_metrics(completed_trades, initial_capital, final_capital)
            
            # Performance metrics
            performance_metrics = self._calculate_performance_metrics(completed_trades, initial_capital, final_capital)
            
            # Risk metrics
            risk_analysis = self._calculate_risk_metrics(completed_trades, initial_capital, final_capital, risk_metrics)
            
            # Timing metrics
            timing_metrics = self._calculate_timing_metrics(completed_trades, backtest_hours)
            
            # Consecutive metrics
            consecutive_metrics = self._calculate_consecutive_metrics(completed_trades)
            
            # Advanced analytics
            advanced_metrics = self._calculate_advanced_metrics(completed_trades)
            
            # Combine all metrics
            comprehensive_metrics = {
                **basic_metrics,
                **performance_metrics,
                **risk_analysis,
                **timing_metrics,
                **consecutive_metrics,
                **advanced_metrics,
                'leverage_analysis': leverage_metrics,
                'execution_analysis': execution_stats,
                'backtest_summary': {
                    'backtest_duration_hours': backtest_hours,
                    'backtest_duration_days': backtest_hours / 24,
                    'total_signals_processed': len(completed_trades) * 3,  # Estimate
                    'signal_success_rate': basic_metrics['win_rate'],
                    'capital_efficiency': ((final_capital - initial_capital) / initial_capital) * 100,
                    'risk_adjusted_return': performance_metrics.get('sharpe_ratio', 0) * performance_metrics.get('return_percentage', 0),
                }
            }
            
            return comprehensive_metrics
            
        except Exception as e:
            self.logger.error(f"Error calculating comprehensive metrics: {e}")
            return self._get_empty_metrics(initial_capital, final_capital)
    
    def _calculate_basic_metrics(self, trades: List[Dict[str, Any]], 
                                initial_capital: float, final_capital: float) -> Dict[str, Any]:
        """Calculate basic trading metrics"""
        
        try:
            total_trades = len(trades)
            winning_trades = len([t for t in trades if t.get('is_winner', False)])
            losing_trades = total_trades - winning_trades
            
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # PnL calculations
            total_pnl = sum(t.get('net_pnl', 0) for t in trades)
            return_percentage = (total_pnl / initial_capital * 100) if initial_capital > 0 else 0
            
            gross_profit = sum(t.get('net_pnl', 0) for t in trades if t.get('net_pnl', 0) > 0)
            gross_loss = abs(sum(t.get('net_pnl', 0) for t in trades if t.get('net_pnl', 0) < 0))
            
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
            
            # Average trade metrics
            avg_win = np.mean([t.get('net_pnl', 0) for t in trades if t.get('is_winner', False)]) if winning_trades > 0 else 0
            avg_loss = np.mean([t.get('net_pnl', 0) for t in trades if not t.get('is_winner', True)]) if losing_trades > 0 else 0
            
            # Largest trades
            largest_win = max([t.get('net_pnl', 0) for t in trades], default=0)
            largest_loss = min([t.get('net_pnl', 0) for t in trades], default=0)
            
            return {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': win_rate,
                'total_pnl': total_pnl,
                'return_percentage': return_percentage,
                'final_capital': final_capital,
                'gross_profit': gross_profit,
                'gross_loss': gross_loss,
                'profit_factor': profit_factor,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'largest_win': largest_win,
                'largest_loss': largest_loss,
                'win_loss_ratio': abs(avg_win / avg_loss) if avg_loss != 0 else float('inf') if avg_win > 0 else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating basic metrics: {e}")
            return {}
    
    def _calculate_performance_metrics(self, trades: List[Dict[str, Any]], 
                                     initial_capital: float, final_capital: float) -> Dict[str, Any]:
        """Calculate performance and risk-adjusted metrics"""
        
        try:
            # Return calculations
            total_return = final_capital - initial_capital
            return_pct = (total_return / initial_capital * 100) if initial_capital > 0 else 0
            
            # Daily returns (approximate)
            trade_returns = [t.get('pnl_percentage', 0) for t in trades if 'pnl_percentage' in t]
            
            if len(trade_returns) > 1:
                avg_return = np.mean(trade_returns)
                return_std = np.std(trade_returns)
                sharpe_ratio = avg_return / return_std if return_std > 0 else 0
                
                # Sortino ratio (downside deviation)
                negative_returns = [r for r in trade_returns if r < 0]
                downside_std = np.std(negative_returns) if negative_returns else return_std
                sortino_ratio = avg_return / downside_std if downside_std > 0 else 0
            else:
                sharpe_ratio = 0
                sortino_ratio = 0
                avg_return = 0
                return_std = 0
            
            # Calmar ratio (return / max drawdown)
            max_dd = max([abs(t.get('max_adverse_pnl', 0)) for t in trades], default=1)
            calmar_ratio = return_pct / max_dd if max_dd > 0 else 0
            
            return {
                'total_return': total_return,
                'return_percentage': return_pct,
                'sharpe_ratio': sharpe_ratio,
                'sortino_ratio': sortino_ratio,
                'calmar_ratio': calmar_ratio,
                'avg_trade_return_pct': avg_return,
                'trade_return_volatility': return_std,
                'risk_adjusted_return': sharpe_ratio * return_pct
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating performance metrics: {e}")
            return {}
    
    def _calculate_risk_metrics(self, trades: List[Dict[str, Any]], 
                              initial_capital: float, final_capital: float,
                              risk_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate risk and drawdown metrics"""
        
        try:
            # Drawdown calculations
            max_drawdown = risk_metrics.get('max_drawdown_pct', 0)
            current_drawdown = risk_metrics.get('current_drawdown_pct', 0)
            peak_capital = risk_metrics.get('peak_capital', final_capital)
            
            # Value at Risk (VaR) estimation
            trade_returns = [t.get('pnl_percentage', 0) for t in trades if 'pnl_percentage' in t]
            if trade_returns:
                var_95 = np.percentile(trade_returns, 5)  # 5th percentile
                var_99 = np.percentile(trade_returns, 1)  # 1st percentile
            else:
                var_95 = 0
                var_99 = 0
            
            # Maximum adverse excursion
            max_adverse_excursions = [abs(t.get('max_adverse_pnl', 0)) for t in trades]
            avg_mae = np.mean(max_adverse_excursions) if max_adverse_excursions else 0
            max_mae = max(max_adverse_excursions) if max_adverse_excursions else 0
            
            # Maximum favorable excursion
            max_favorable_excursions = [t.get('max_favorable_pnl', 0) for t in trades]
            avg_mfe = np.mean(max_favorable_excursions) if max_favorable_excursions else 0
            max_mfe = max(max_favorable_excursions) if max_favorable_excursions else 0
            
            # Risk metrics
            total_risk_taken = sum(t.get('risk_amount', 0) for t in trades)
            avg_risk_per_trade = total_risk_taken / len(trades) if trades else 0
            max_risk_per_trade = max([t.get('risk_amount', 0) for t in trades], default=0)
            
            return {
                'max_drawdown_pct': max_drawdown,
                'current_drawdown_pct': current_drawdown,
                'peak_capital': peak_capital,
                'var_95_pct': var_95,
                'var_99_pct': var_99,
                'avg_max_adverse_excursion': avg_mae,
                'max_max_adverse_excursion': max_mae,
                'avg_max_favorable_excursion': avg_mfe,
                'max_max_favorable_excursion': max_mfe,
                'total_risk_taken': total_risk_taken,
                'avg_risk_per_trade': avg_risk_per_trade,
                'max_risk_per_trade': max_risk_per_trade,
                'risk_utilization_pct': (total_risk_taken / initial_capital * 100) if initial_capital > 0 else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating risk metrics: {e}")
            return {}
    
    def _calculate_timing_metrics(self, trades: List[Dict[str, Any]], backtest_hours: float) -> Dict[str, Any]:
        """Calculate timing and frequency metrics"""
        
        try:
            total_trades = len(trades)
            
            # Frequency metrics
            trades_per_hour = total_trades / backtest_hours if backtest_hours > 0 else 0
            trades_per_day = trades_per_hour * 24
            
            # Duration metrics
            durations = [t.get('duration_minutes', 0) for t in trades if 'duration_minutes' in t]
            
            if durations:
                avg_duration = np.mean(durations)
                median_duration = np.median(durations)
                min_duration = min(durations)
                max_duration = max(durations)
                
                # Duration by outcome
                win_durations = [t.get('duration_minutes', 0) for t in trades if t.get('is_winner', False)]
                lose_durations = [t.get('duration_minutes', 0) for t in trades if not t.get('is_winner', True)]
                
                avg_win_duration = np.mean(win_durations) if win_durations else 0
                avg_lose_duration = np.mean(lose_durations) if lose_durations else 0
            else:
                avg_duration = 0
                median_duration = 0
                min_duration = 0
                max_duration = 0
                avg_win_duration = 0
                avg_lose_duration = 0
            
            # Trading intensity analysis
            if backtest_hours > 24:
                days = backtest_hours / 24
                trading_intensity = "HIGH" if trades_per_day > 5 else "MEDIUM" if trades_per_day > 2 else "LOW"
            else:
                trading_intensity = "INSUFFICIENT_DATA"
            
            return {
                'trades_per_hour': trades_per_hour,
                'trades_per_day': trades_per_day,
                'avg_trade_duration_minutes': avg_duration,
                'median_trade_duration_minutes': median_duration,
                'min_trade_duration_minutes': min_duration,
                'max_trade_duration_minutes': max_duration,
                'avg_winning_trade_duration': avg_win_duration,
                'avg_losing_trade_duration': avg_lose_duration,
                'trading_intensity': trading_intensity,
                'duration_efficiency': avg_win_duration / avg_lose_duration if avg_lose_duration > 0 else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating timing metrics: {e}")
            return {}
    
    def _calculate_consecutive_metrics(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate consecutive wins/losses metrics"""
        
        try:
            if not trades:
                return {
                    'max_consecutive_wins': 0,
                    'max_consecutive_losses': 0,
                    'current_consecutive_wins': 0,
                    'current_consecutive_losses': 0,
                    'avg_consecutive_wins': 0,
                    'avg_consecutive_losses': 0
                }
            
            # Sort trades by time
            sorted_trades = sorted(trades, key=lambda t: t.get('entry_time', datetime.now()))
            
            # Calculate consecutive sequences
            consecutive_wins = []
            consecutive_losses = []
            current_win_streak = 0
            current_loss_streak = 0
            
            for trade in sorted_trades:
                is_winner = trade.get('is_winner', False)
                
                if is_winner:
                    current_win_streak += 1
                    if current_loss_streak > 0:
                        consecutive_losses.append(current_loss_streak)
                        current_loss_streak = 0
                else:
                    current_loss_streak += 1
                    if current_win_streak > 0:
                        consecutive_wins.append(current_win_streak)
                        current_win_streak = 0
            
            # Add final streak
            if current_win_streak > 0:
                consecutive_wins.append(current_win_streak)
            if current_loss_streak > 0:
                consecutive_losses.append(current_loss_streak)
            
            # Calculate metrics
            max_consecutive_wins = max(consecutive_wins) if consecutive_wins else 0
            max_consecutive_losses = max(consecutive_losses) if consecutive_losses else 0
            avg_consecutive_wins = np.mean(consecutive_wins) if consecutive_wins else 0
            avg_consecutive_losses = np.mean(consecutive_losses) if consecutive_losses else 0
            
            # Current streaks (last trade)
            last_trade = sorted_trades[-1]
            if last_trade.get('is_winner', False):
                current_consecutive_wins = current_win_streak
                current_consecutive_losses = 0
            else:
                current_consecutive_wins = 0
                current_consecutive_losses = current_loss_streak
            
            return {
                'max_consecutive_wins': max_consecutive_wins,
                'max_consecutive_losses': max_consecutive_losses,
                'current_consecutive_wins': current_consecutive_wins,
                'current_consecutive_losses': current_consecutive_losses,
                'avg_consecutive_wins': avg_consecutive_wins,
                'avg_consecutive_losses': avg_consecutive_losses,
                'total_win_streaks': len(consecutive_wins),
                'total_loss_streaks': len(consecutive_losses)
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating consecutive metrics: {e}")
            return {}
    
    def _calculate_advanced_metrics(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate advanced analytics and trading insights"""
        
        try:
            if not trades:
                return {}
            
            # Symbol performance analysis
            symbol_performance = {}
            for trade in trades:
                symbol = trade.get('symbol', 'UNKNOWN')
                if symbol not in symbol_performance:
                    symbol_performance[symbol] = {'trades': 0, 'wins': 0, 'total_pnl': 0}
                
                symbol_performance[symbol]['trades'] += 1
                if trade.get('is_winner', False):
                    symbol_performance[symbol]['wins'] += 1
                symbol_performance[symbol]['total_pnl'] += trade.get('net_pnl', 0)
            
            # Calculate win rates per symbol
            for symbol, stats in symbol_performance.items():
                stats['win_rate'] = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
                stats['avg_pnl'] = stats['total_pnl'] / stats['trades'] if stats['trades'] > 0 else 0
            
            # Direction performance
            long_trades = [t for t in trades if t.get('direction') == 'LONG']
            short_trades = [t for t in trades if t.get('direction') == 'SHORT']
            
            long_win_rate = len([t for t in long_trades if t.get('is_winner', False)]) / len(long_trades) * 100 if long_trades else 0
            short_win_rate = len([t for t in short_trades if t.get('is_winner', False)]) / len(short_trades) * 100 if short_trades else 0
            
            long_pnl = sum(t.get('net_pnl', 0) for t in long_trades)
            short_pnl = sum(t.get('net_pnl', 0) for t in short_trades)
            
            # Commission analysis
            total_commission = sum(t.get('total_commission', 0) for t in trades)
            avg_commission = total_commission / len(trades) if trades else 0
            commission_to_pnl_ratio = abs(total_commission / sum(t.get('net_pnl', 0) for t in trades)) if sum(t.get('net_pnl', 0) for t in trades) != 0 else 0
            
            # Volatility performance analysis
            volatility_performance = {}
            for trade in trades:
                vol_cat = trade.get('volatility_category', 'UNKNOWN')
                if vol_cat not in volatility_performance:
                    volatility_performance[vol_cat] = {'trades': 0, 'wins': 0, 'total_pnl': 0}
                
                volatility_performance[vol_cat]['trades'] += 1
                if trade.get('is_winner', False):
                    volatility_performance[vol_cat]['wins'] += 1
                volatility_performance[vol_cat]['total_pnl'] += trade.get('net_pnl', 0)
            
            # Calculate performance per volatility
            for vol_cat, stats in volatility_performance.items():
                stats['win_rate'] = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
                stats['avg_pnl'] = stats['total_pnl'] / stats['trades'] if stats['trades'] > 0 else 0
            
            return {
                'symbol_performance': symbol_performance,
                'direction_analysis': {
                    'long_trades': len(long_trades),
                    'short_trades': len(short_trades),
                    'long_win_rate': long_win_rate,
                    'short_win_rate': short_win_rate,
                    'long_total_pnl': long_pnl,
                    'short_total_pnl': short_pnl,
                    'direction_bias': 'LONG' if long_pnl > short_pnl else 'SHORT'
                },
                'commission_analysis': {
                    'total_commission': total_commission,
                    'avg_commission_per_trade': avg_commission,
                    'commission_to_pnl_ratio': commission_to_pnl_ratio,
                    'commission_impact_pct': commission_to_pnl_ratio * 100
                },
                'volatility_performance': volatility_performance,
                'best_performing_symbol': max(symbol_performance.keys(), key=lambda k: symbol_performance[k]['avg_pnl']) if symbol_performance else None,
                'worst_performing_symbol': min(symbol_performance.keys(), key=lambda k: symbol_performance[k]['avg_pnl']) if symbol_performance else None
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating advanced metrics: {e}")
            return {}
    
    def _get_empty_metrics(self, initial_capital: float, final_capital: float) -> Dict[str, Any]:
        """Return empty/zero metrics when no trades available"""
        
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'total_pnl': 0.0,
            'return_percentage': 0.0,
            'final_capital': final_capital,
            'gross_profit': 0.0,
            'gross_loss': 0.0,
            'profit_factor': 0.0,
            'max_drawdown_pct': 0.0,
            'sharpe_ratio': 0.0,
            'trades_per_hour': 0.0,
            'trades_per_day': 0.0,
            'max_consecutive_wins': 0,
            'max_consecutive_losses': 0,
            'current_consecutive_wins': 0,
            'current_consecutive_losses': 0
        }
    
    def generate_performance_report(self, metrics: Dict[str, Any]) -> str:
        """Generate a formatted performance report"""
        
        try:
            report = f"""
🚀 COMPREHENSIVE BACKTEST PERFORMANCE REPORT
{"="*80}

📊 BASIC PERFORMANCE METRICS
Total Trades: {metrics.get('total_trades', 0)}
Winning Trades: {metrics.get('winning_trades', 0)}
Losing Trades: {metrics.get('losing_trades', 0)}
Win Rate: {metrics.get('win_rate', 0):.1f}%

💰 FINANCIAL PERFORMANCE
Total P&L: ${metrics.get('total_pnl', 0):.2f}
Return: {metrics.get('return_percentage', 0):.1f}%
Final Capital: ${metrics.get('final_capital', 0):.2f}
Gross Profit: ${metrics.get('gross_profit', 0):.2f}
Gross Loss: ${metrics.get('gross_loss', 0):.2f}
Profit Factor: {metrics.get('profit_factor', 0):.2f}

🔥 CONSECUTIVE PERFORMANCE
Max Consecutive Wins: {metrics.get('max_consecutive_wins', 0)}
Max Consecutive Losses: {metrics.get('max_consecutive_losses', 0)}
Current Consecutive Wins: {metrics.get('current_consecutive_wins', 0)}
Current Consecutive Losses: {metrics.get('current_consecutive_losses', 0)}

⏰ TIMING METRICS
Trades per Hour: {metrics.get('trades_per_hour', 0):.3f}
Trades per Day: {metrics.get('trades_per_day', 0):.2f}
Avg Trade Duration: {metrics.get('avg_trade_duration_minutes', 0):.1f} minutes

📉 RISK METRICS
Max Drawdown: {metrics.get('max_drawdown_pct', 0):.1f}%
Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}
Peak Capital: ${metrics.get('peak_capital', 0):.2f}

⚡ LEVERAGE ANALYSIS
{self._format_leverage_section(metrics.get('leverage_analysis', {}))}

📈 ADVANCED ANALYTICS
{self._format_advanced_section(metrics)}

{"="*80}
            """
            
            return report.strip()
            
        except Exception as e:
            self.logger.error(f"Error generating performance report: {e}")
            return "Error generating performance report"
    
    def _format_leverage_section(self, leverage_metrics: Dict[str, Any]) -> str:
        """Format leverage analysis section"""
        
        if not leverage_metrics:
            return "No leverage data available"
        
        avg_leverage = leverage_metrics.get('average_leverage_used', 0)
        efficiency = (avg_leverage / 75) * 100  # Assuming 75x max
        
        return f"""Avg Leverage Used: {avg_leverage:.1f}x
Leverage Efficiency: {efficiency:.1f}%
Performance by Leverage: {len(leverage_metrics.get('performance_by_leverage', {}))} levels analyzed"""
    
    def _format_advanced_section(self, metrics: Dict[str, Any]) -> str:
        """Format advanced analytics section"""
        
        direction_analysis = metrics.get('direction_analysis', {})
        commission_analysis = metrics.get('commission_analysis', {})
        
        return f"""Direction Performance:
  Long Trades: {direction_analysis.get('long_trades', 0)} (Win Rate: {direction_analysis.get('long_win_rate', 0):.1f}%)
  Short Trades: {direction_analysis.get('short_trades', 0)} (Win Rate: {direction_analysis.get('short_win_rate', 0):.1f}%)
  Best Direction: {direction_analysis.get('direction_bias', 'N/A')}

Commission Impact:
  Total Commission: ${commission_analysis.get('total_commission', 0):.2f}
  Avg per Trade: ${commission_analysis.get('avg_commission_per_trade', 0):.3f}
  Impact on Returns: {commission_analysis.get('commission_impact_pct', 0):.2f}%"""