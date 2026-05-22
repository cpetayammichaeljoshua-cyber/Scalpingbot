#!/usr/bin/env python3
"""
ExecutionSimulator - Handles trade execution, SL/TP processing, and market simulation
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import logging

class ExecutionSimulator:
    """Realistic trade execution simulator with candle-by-candle processing"""
    
    def __init__(self, slippage_bps: float = 1.0, latency_ms: float = 50.0):
        """
        Initialize execution simulator
        
        Args:
            slippage_bps: Slippage in basis points (0.01% = 1bp)
            latency_ms: Execution latency in milliseconds
        """
        self.slippage_bps = slippage_bps
        self.latency_ms = latency_ms
        self.logger = logging.getLogger(__name__)
        
        # Execution tracking
        self.executions = []
        self.total_slippage_cost = 0.0
        
    def simulate_market_order(self, order: Dict[str, Any], market_data: pd.Series) -> Dict[str, Any]:
        """
        Simulate market order execution with realistic slippage
        
        Args:
            order: Order details (direction, size, symbol, timestamp)
            market_data: Current market candle data (OHLCV)
        
        Returns:
            Execution result with fill price and costs
        """
        
        try:
            direction = order['direction']
            size = order['size']
            symbol = order['symbol']
            order_time = order['timestamp']
            
            # Base price from market data
            open_price = market_data['open']
            high_price = market_data['high']
            low_price = market_data['low']
            close_price = market_data['close']
            volume = market_data['volume']
            
            # Calculate realistic fill price with slippage
            fill_price = self._calculate_fill_price(
                direction, open_price, high_price, low_price, close_price, volume, size
            )
            
            # Calculate slippage cost
            reference_price = (open_price + close_price) / 2  # Mid-price reference
            slippage_cost = self._calculate_slippage_cost(direction, reference_price, fill_price, size)
            
            execution = {
                'order_id': len(self.executions) + 1,
                'symbol': symbol,
                'direction': direction,
                'size': size,
                'fill_price': fill_price,
                'fill_time': order_time,
                'slippage_cost': slippage_cost,
                'reference_price': reference_price,
                'market_impact': abs(fill_price - reference_price) / reference_price * 10000,  # bps
                'execution_quality': self._assess_execution_quality(direction, reference_price, fill_price)
            }
            
            self.executions.append(execution)
            self.total_slippage_cost += slippage_cost
            
            self.logger.debug(f"Executed {direction} {symbol}: {size:.4f} @ {fill_price:.6f} "
                            f"(slippage: ${slippage_cost:.4f})")
            
            return execution
            
        except Exception as e:
            self.logger.error(f"Error simulating market order: {e}")
            return {}
    
    def _calculate_fill_price(self, direction: str, open_price: float, high_price: float,
                             low_price: float, close_price: float, volume: float, size: float) -> float:
        """Calculate realistic fill price considering market conditions"""
        
        try:
            # Base price (slightly worse than open for market orders)
            if direction == 'LONG':
                base_price = open_price * 1.0002  # Slightly above open
            else:  # SHORT
                base_price = open_price * 0.9998  # Slightly below open
            
            # Volume-based slippage
            avg_candle_volume = volume
            size_impact = min(0.001, (size / avg_candle_volume) * 0.01)  # Max 0.1% impact
            
            if direction == 'LONG':
                volume_impact = base_price * size_impact
            else:
                volume_impact = -base_price * size_impact
            
            # Volatility-based slippage
            volatility = (high_price - low_price) / open_price
            volatility_impact = volatility * 0.1  # 10% of volatility as slippage
            
            if direction == 'LONG':
                volatility_slippage = base_price * volatility_impact
            else:
                volatility_slippage = -base_price * volatility_impact
            
            # Base slippage
            base_slippage_factor = self.slippage_bps / 10000
            if direction == 'LONG':
                base_slippage = base_price * base_slippage_factor
            else:
                base_slippage = -base_price * base_slippage_factor
            
            # Total fill price
            fill_price = base_price + volume_impact + volatility_slippage + base_slippage
            
            # Ensure fill price is within candle range
            fill_price = max(low_price, min(high_price, fill_price))
            
            return fill_price
            
        except Exception as e:
            self.logger.error(f"Error calculating fill price: {e}")
            return open_price  # Fallback to open price
    
    def _calculate_slippage_cost(self, direction: str, reference_price: float, 
                                fill_price: float, size: float) -> float:
        """Calculate slippage cost in USD"""
        
        try:
            if direction == 'LONG':
                slippage_per_unit = max(0, fill_price - reference_price)
            else:  # SHORT
                slippage_per_unit = max(0, reference_price - fill_price)
            
            return slippage_per_unit * size
            
        except Exception as e:
            self.logger.error(f"Error calculating slippage cost: {e}")
            return 0.0
    
    def _assess_execution_quality(self, direction: str, reference_price: float, fill_price: float) -> str:
        """Assess execution quality based on price improvement/degradation"""
        
        try:
            if direction == 'LONG':
                improvement = reference_price - fill_price  # Negative = worse execution
            else:  # SHORT
                improvement = fill_price - reference_price  # Negative = worse execution
            
            improvement_bps = (improvement / reference_price) * 10000
            
            if improvement_bps > 2:
                return "EXCELLENT"
            elif improvement_bps > 0:
                return "GOOD"
            elif improvement_bps > -2:
                return "FAIR"
            elif improvement_bps > -5:
                return "POOR"
            else:
                return "VERY_POOR"
                
        except Exception as e:
            self.logger.error(f"Error assessing execution quality: {e}")
            return "UNKNOWN"
    
    def process_stop_loss_take_profit(self, trades: List[Dict[str, Any]], 
                                     market_data: pd.Series) -> List[Tuple[Dict[str, Any], float, str]]:
        """
        Process stop loss and take profit triggers using intrabar analysis
        
        Args:
            trades: List of active trades
            market_data: Current candle OHLCV data
        
        Returns:
            List of (trade, exit_price, exit_reason) tuples for trades to close
        """
        
        triggers = []
        
        try:
            high_price = market_data['high']
            low_price = market_data['low']
            close_price = market_data['close']
            
            for trade in trades:
                direction = trade['direction']
                sl_price = trade['stop_loss_price']
                tp_price = trade['take_profit_price']
                
                # Check stop loss trigger
                if direction == 'LONG':
                    if low_price <= sl_price:
                        # Stop loss triggered
                        exit_price = self._get_realistic_exit_price(sl_price, low_price, high_price, 'STOP_LOSS', direction)
                        triggers.append((trade, exit_price, "Stop Loss"))
                        continue
                else:  # SHORT
                    if high_price >= sl_price:
                        # Stop loss triggered
                        exit_price = self._get_realistic_exit_price(sl_price, low_price, high_price, 'STOP_LOSS', direction)
                        triggers.append((trade, exit_price, "Stop Loss"))
                        continue
                
                # Check take profit trigger (only if stop loss not triggered)
                if direction == 'LONG':
                    if high_price >= tp_price:
                        # Take profit triggered
                        exit_price = self._get_realistic_exit_price(tp_price, low_price, high_price, 'TAKE_PROFIT', direction)
                        triggers.append((trade, exit_price, "Take Profit"))
                else:  # SHORT
                    if low_price <= tp_price:
                        # Take profit triggered
                        exit_price = self._get_realistic_exit_price(tp_price, low_price, high_price, 'TAKE_PROFIT', direction)
                        triggers.append((trade, exit_price, "Take Profit"))
            
            return triggers
            
        except Exception as e:
            self.logger.error(f"Error processing SL/TP: {e}")
            return []
    
    def _get_realistic_exit_price(self, target_price: float, low_price: float, 
                                 high_price: float, exit_type: str, direction: str) -> float:
        """Get realistic exit price considering slippage and market impact"""
        
        try:
            # Add slippage for stop losses (worse fills) and limit slippage for take profits
            if exit_type == 'STOP_LOSS':
                # Stop losses get worse fills due to market pressure
                slippage_factor = self.slippage_bps * 2 / 10000  # Double slippage for stops
                if direction == 'LONG':
                    # Long stop loss - sell at worse price (lower)
                    exit_price = target_price * (1 - slippage_factor)
                else:
                    # Short stop loss - buy at worse price (higher)
                    exit_price = target_price * (1 + slippage_factor)
            else:  # TAKE_PROFIT
                # Take profits get better execution
                slippage_factor = self.slippage_bps * 0.5 / 10000  # Half slippage for TPs
                if direction == 'LONG':
                    # Long take profit - sell at slightly worse price
                    exit_price = target_price * (1 - slippage_factor)
                else:
                    # Short take profit - buy at slightly worse price
                    exit_price = target_price * (1 + slippage_factor)
            
            # Ensure exit price is within candle range
            exit_price = max(low_price, min(high_price, exit_price))
            
            return exit_price
            
        except Exception as e:
            self.logger.error(f"Error calculating realistic exit price: {e}")
            return target_price  # Fallback to target price
    
    def simulate_partial_fills(self, trade: Dict[str, Any], market_data: pd.Series, 
                              partial_ratio: float = 0.3) -> Optional[Dict[str, Any]]:
        """
        Simulate partial position closures (e.g., taking 1/3 at first TP level)
        
        Args:
            trade: Trade to partially close
            market_data: Current market data
            partial_ratio: Ratio of position to close (0.3 = 30%)
        
        Returns:
            Partial closure execution details
        """
        
        try:
            if not trade.get('is_open', False):
                return None
            
            # Check if trade is in profit enough for partial closure
            current_price = market_data['close']
            entry_price = trade['entry_price']
            direction = trade['direction']
            
            # Calculate current profit
            if direction == 'LONG':
                profit_pct = (current_price - entry_price) / entry_price * 100
            else:
                profit_pct = (entry_price - current_price) / entry_price * 100
            
            # Only take partials if in significant profit (>2%)
            if profit_pct < 2.0:
                return None
            
            # Simulate partial fill
            partial_size = trade['position_size'] * partial_ratio
            
            order = {
                'direction': 'SELL' if direction == 'LONG' else 'BUY',
                'size': partial_size,
                'symbol': trade['symbol'],
                'timestamp': market_data.name
            }
            
            execution = self.simulate_market_order(order, market_data)
            
            if execution:
                # Update trade position size
                trade['position_size'] -= partial_size
                
                # Track partial closure
                execution['partial_closure'] = True
                execution['partial_ratio'] = partial_ratio
                execution['remaining_size'] = trade['position_size']
                
                self.logger.info(f"Partial close: {partial_ratio*100:.0f}% of {trade['symbol']} "
                               f"at {execution['fill_price']:.6f}")
            
            return execution
            
        except Exception as e:
            self.logger.error(f"Error simulating partial fills: {e}")
            return None
    
    def get_execution_statistics(self) -> Dict[str, Any]:
        """Get execution quality statistics"""
        
        try:
            if not self.executions:
                return {}
            
            # Quality distribution
            quality_counts = {}
            market_impacts = []
            slippage_costs = []
            
            for exec in self.executions:
                quality = exec.get('execution_quality', 'UNKNOWN')
                quality_counts[quality] = quality_counts.get(quality, 0) + 1
                
                market_impacts.append(exec.get('market_impact', 0))
                slippage_costs.append(exec.get('slippage_cost', 0))
            
            return {
                'total_executions': len(self.executions),
                'total_slippage_cost': self.total_slippage_cost,
                'avg_slippage_cost': np.mean(slippage_costs),
                'avg_market_impact_bps': np.mean(market_impacts),
                'max_market_impact_bps': max(market_impacts) if market_impacts else 0,
                'execution_quality_distribution': quality_counts,
                'excellent_execution_rate': quality_counts.get('EXCELLENT', 0) / len(self.executions) * 100,
                'poor_execution_rate': (quality_counts.get('POOR', 0) + quality_counts.get('VERY_POOR', 0)) / len(self.executions) * 100
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating execution statistics: {e}")
            return {}
    
    def suggest_execution_improvements(self) -> List[str]:
        """Analyze execution performance and suggest improvements"""
        
        recommendations = []
        stats = self.get_execution_statistics()
        
        try:
            if not stats:
                return ["No execution data available for analysis"]
            
            # Analyze slippage costs
            avg_slippage = stats.get('avg_slippage_cost', 0)
            if avg_slippage > 0.005:  # $0.005 per execution
                recommendations.append("High average slippage - consider using limit orders or trading during higher liquidity periods")
            
            # Analyze market impact
            avg_impact = stats.get('avg_market_impact_bps', 0)
            if avg_impact > 5:  # > 5 basis points
                recommendations.append("High market impact - consider reducing position sizes or splitting large orders")
            
            # Analyze execution quality
            poor_rate = stats.get('poor_execution_rate', 0)
            if poor_rate > 30:  # > 30% poor executions
                recommendations.append("High rate of poor executions - review order timing and market conditions")
            
            excellent_rate = stats.get('excellent_execution_rate', 0)
            if excellent_rate > 20:
                recommendations.append("Good execution quality achieved - current approach is working well")
            
            # Total cost analysis
            total_slippage = stats.get('total_slippage_cost', 0)
            if total_slippage > 0.1:  # > $0.10 total
                recommendations.append(f"Total slippage costs: ${total_slippage:.3f} - consider execution optimization")
            
            if not recommendations:
                recommendations.append("Execution performance appears optimal for current trading conditions")
            
        except Exception as e:
            self.logger.error(f"Error generating execution recommendations: {e}")
            recommendations.append("Unable to analyze execution performance due to error")
        
        return recommendations