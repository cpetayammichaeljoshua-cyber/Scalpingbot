#!/usr/bin/env python3
"""
RiskManager - Handles position sizing, capital management, and concurrent trade limits
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import logging

class RiskManager:
    """Risk management system for backtesting"""
    
    def __init__(self, initial_capital: float = 10.0, risk_percentage: float = 10.0,
                 max_concurrent_trades: int = 3, max_daily_loss: float = 2.0,
                 commission_rate: float = 0.0002, funding_rate: float = 0.0001,
                 portfolio_risk_cap: float = 15.0, use_fixed_risk: bool = True):
        
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.risk_percentage = risk_percentage
        self.max_concurrent_trades = max_concurrent_trades
        self.max_daily_loss = max_daily_loss
        self.commission_rate = commission_rate
        self.funding_rate = funding_rate  # 8-hour funding rate
        self.portfolio_risk_cap = portfolio_risk_cap  # Max total portfolio risk %
        self.use_fixed_risk = use_fixed_risk  # Use fixed dollar risk to prevent compounding
        
        # Tracking
        self.active_trades: List[Dict[str, Any]] = []
        self.daily_pnl = 0.0
        self.total_commission_paid = 0.0
        self.total_funding_paid = 0.0
        self.peak_capital = initial_capital
        self.max_drawdown = 0.0
        
        self.logger = logging.getLogger(__name__)
    
    def can_open_trade(self, signal: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if a new trade can be opened based on risk rules
        
        Returns:
            (can_open, reason)
        """
        
        try:
            # Check concurrent trades limit
            if len(self.active_trades) >= self.max_concurrent_trades:
                return False, f"Max concurrent trades reached ({self.max_concurrent_trades})"
            
            # Check daily loss limit
            if self.daily_pnl <= -self.max_daily_loss:
                return False, f"Daily loss limit reached (${self.daily_pnl:.2f})"
            
            # Check minimum capital requirement
            if self.current_capital < 1.0:
                return False, f"Insufficient capital (${self.current_capital:.2f})"
            
            # Check if signal quality meets minimum threshold
            signal_strength = signal.get('signal_strength', 0)
            if signal_strength < 50:  # Minimum signal strength
                return False, f"Signal strength too low ({signal_strength:.1f})"
            
            # Check risk amount
            risk_amount = self.current_capital * (self.risk_percentage / 100)
            if risk_amount < 0.05:  # Minimum $0.05 risk
                return False, f"Risk amount too small (${risk_amount:.3f})"
            
            return True, "Trade allowed"
            
        except Exception as e:
            self.logger.error(f"Error checking trade eligibility: {e}")
            return False, f"Error: {e}"
    
    def calculate_position_size(self, signal: Dict[str, Any], leverage: int,
                              stop_loss_percentage: float = 1.5) -> Dict[str, Any]:
        """
        Calculate position size, margin, and risk metrics using realistic risk management
        
        Args:
            signal: Trading signal with price and direction
            leverage: Leverage to use
            stop_loss_percentage: Stop loss distance as percentage
        
        Returns:
            Dict with position_size, margin_required, risk_amount, etc.
        """
        
        try:
            entry_price = signal['price']
            direction = signal['direction']
            
            # Calculate free equity (available capital minus reserved margin)
            reserved_margin = sum(trade['margin_used'] for trade in self.active_trades)
            free_equity = max(0, self.current_capital - reserved_margin)
            
            # Calculate risk amount with realistic constraints
            if self.use_fixed_risk:
                # Fixed dollar risk based on initial capital to prevent compounding
                base_risk = self.initial_capital * (self.risk_percentage / 100)
                # Scale down if we don't have enough free equity
                risk_amount = min(base_risk, free_equity * 0.8)  # Max 80% of free equity
            else:
                # Percent of free equity (more conservative)
                risk_amount = free_equity * (self.risk_percentage / 100)
            
            # Check portfolio risk cap
            current_portfolio_risk = sum(trade.get('risk_amount', 0) for trade in self.active_trades)
            max_portfolio_risk = self.initial_capital * (self.portfolio_risk_cap / 100)
            
            if current_portfolio_risk + risk_amount > max_portfolio_risk:
                # Reduce risk to stay within portfolio cap
                risk_amount = max(0, max_portfolio_risk - current_portfolio_risk)
            
            # Minimum risk check
            if risk_amount < 0.05:  # Minimum $0.05 risk
                return {}
            
            # Calculate position value based on risk and stop loss
            # Risk = Position_Size * Stop_Loss_Distance
            # Position_Size = Risk / Stop_Loss_Distance
            stop_loss_distance = entry_price * (stop_loss_percentage / 100)
            position_size = risk_amount / stop_loss_distance
            
            # Position value (notional)
            position_value = position_size * entry_price
            
            # Margin required
            margin_required = position_value / leverage
            
            # Ensure we have enough free equity for margin
            if margin_required > free_equity:
                # Scale down position to fit available margin
                scale_factor = free_equity / margin_required * 0.95  # 5% buffer
                margin_required *= scale_factor
                position_size *= scale_factor
                position_value *= scale_factor
                risk_amount *= scale_factor
            
            # Commission calculation (entry + estimated exit)
            entry_commission = position_value * self.commission_rate
            exit_commission = position_value * self.commission_rate  # Estimate
            total_commission = entry_commission + exit_commission
            
            # Funding cost estimate (for 2-hour average hold)
            funding_periods = 2 / 8  # 2 hours / 8 hour funding periods
            estimated_funding = position_value * self.funding_rate * funding_periods
            
            # Calculate stop loss and take profit prices
            if direction == 'LONG':
                stop_loss_price = entry_price * (1 - stop_loss_percentage / 100)
                take_profit_price = entry_price * (1 + (stop_loss_percentage * 3) / 100)  # 1:3 R/R
            else:  # SHORT
                stop_loss_price = entry_price * (1 + stop_loss_percentage / 100)
                take_profit_price = entry_price * (1 - (stop_loss_percentage * 3) / 100)  # 1:3 R/R
            
            return {
                'position_size': position_size,
                'position_value': position_value,
                'margin_required': margin_required,
                'risk_amount': risk_amount,
                'entry_commission': entry_commission,
                'total_commission': total_commission,
                'estimated_funding': estimated_funding,
                'stop_loss_price': stop_loss_price,
                'take_profit_price': take_profit_price,
                'risk_reward_ratio': 3.0,  # 1:3 risk/reward
                'max_loss': risk_amount + total_commission + estimated_funding,
                'max_profit': risk_amount * 3 - total_commission - estimated_funding
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating position size: {e}")
            return {}
    
    def open_trade(self, signal: Dict[str, Any], leverage: int,
                   position_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Open a new trade and update capital
        
        Returns:
            Trade record or None if failed
        """
        
        try:
            margin_required = position_info['margin_required']
            
            # Check if we have enough capital for margin
            if margin_required > self.current_capital:
                self.logger.warning(f"Insufficient capital for margin: need ${margin_required:.2f}, "
                                  f"have ${self.current_capital:.2f}")
                return None
            
            # Create trade record
            trade = {
                'trade_id': len(self.active_trades) + 1,
                'symbol': signal['symbol'],
                'direction': signal['direction'],
                'entry_price': signal['price'],
                'entry_time': signal['timestamp'],
                'position_size': position_info['position_size'],
                'leverage': leverage,
                'margin_used': margin_required,
                'stop_loss_price': position_info['stop_loss_price'],
                'take_profit_price': position_info['take_profit_price'],
                'risk_amount': position_info['risk_amount'],
                'entry_commission': position_info['entry_commission'],
                'signal_strength': signal.get('signal_strength', 0),
                'volatility_category': signal.get('volatility_category', 'UNKNOWN'),
                
                # Track status
                'is_open': True,
                'current_pnl': 0.0,
                'max_favorable_pnl': 0.0,
                'max_adverse_pnl': 0.0,
                'funding_paid': 0.0
            }
            
            # Reserve margin
            self.current_capital -= margin_required
            
            # Track commission
            self.total_commission_paid += position_info['entry_commission']
            
            # Add to active trades
            self.active_trades.append(trade)
            
            self.logger.info(f"Opened {trade['direction']} {trade['symbol']}: "
                           f"{trade['position_size']:.4f} @ {leverage}x | "
                           f"Margin: ${margin_required:.2f}")
            
            return trade
            
        except Exception as e:
            self.logger.error(f"Error opening trade: {e}")
            return None
    
    def update_trades(self, current_prices: Dict[str, float], current_time: datetime):
        """Update PnL for all active trades"""
        
        try:
            for trade in self.active_trades:
                symbol = trade['symbol']
                if symbol in current_prices:
                    current_price = current_prices[symbol]
                    
                    # Calculate current PnL
                    if trade['direction'] == 'LONG':
                        price_diff = current_price - trade['entry_price']
                    else:  # SHORT
                        price_diff = trade['entry_price'] - current_price
                    
                    unrealized_pnl = price_diff * trade['position_size']
                    trade['current_pnl'] = unrealized_pnl
                    
                    # Track maximum favorable/adverse excursions
                    if unrealized_pnl > trade['max_favorable_pnl']:
                        trade['max_favorable_pnl'] = unrealized_pnl
                    if unrealized_pnl < trade['max_adverse_pnl']:
                        trade['max_adverse_pnl'] = unrealized_pnl
                    
                    # Update funding costs (simplified - every 8 hours)
                    hours_open = (current_time - trade['entry_time']).total_seconds() / 3600
                    funding_periods = int(hours_open / 8)
                    position_value = trade['position_size'] * trade['entry_price']
                    trade['funding_paid'] = funding_periods * position_value * self.funding_rate
                    
        except Exception as e:
            self.logger.error(f"Error updating trades: {e}")
    
    def close_trade(self, trade: Dict[str, Any], exit_price: float, exit_time: datetime,
                   exit_reason: str = "Manual") -> Dict[str, Any]:
        """
        Close a trade and update capital
        
        Returns:
            Updated trade record with final results
        """
        
        try:
            # Calculate final PnL
            if trade['direction'] == 'LONG':
                price_diff = exit_price - trade['entry_price']
            else:  # SHORT
                price_diff = trade['entry_price'] - exit_price
            
            gross_pnl = price_diff * trade['position_size']
            
            # Calculate exit commission
            position_value = trade['position_size'] * exit_price
            exit_commission = position_value * self.commission_rate
            
            # Total costs
            total_commission = trade['entry_commission'] + exit_commission
            total_funding = trade.get('funding_paid', 0.0)
            total_costs = total_commission + total_funding
            
            # Net PnL
            net_pnl = gross_pnl - total_costs
            
            # Update trade record
            trade.update({
                'exit_price': exit_price,
                'exit_time': exit_time,
                'exit_reason': exit_reason,
                'gross_pnl': gross_pnl,
                'exit_commission': exit_commission,
                'total_commission': total_commission,
                'total_funding': total_funding,
                'net_pnl': net_pnl,
                'pnl_percentage': (net_pnl / trade['margin_used']) * 100,
                'duration_minutes': (exit_time - trade['entry_time']).total_seconds() / 60,
                'is_open': False,
                'is_winner': net_pnl > 0
            })
            
            # Return margin and add/subtract PnL
            self.current_capital += trade['margin_used'] + net_pnl
            
            # Update daily PnL
            self.daily_pnl += net_pnl
            
            # Track commission and funding
            self.total_commission_paid += exit_commission
            self.total_funding_paid += total_funding
            
            # Update drawdown tracking
            if self.current_capital > self.peak_capital:
                self.peak_capital = self.current_capital
            
            current_drawdown = (self.peak_capital - self.current_capital) / self.peak_capital * 100
            self.max_drawdown = max(self.max_drawdown, current_drawdown)
            
            # Remove from active trades
            if trade in self.active_trades:
                self.active_trades.remove(trade)
            
            status = "WIN" if trade['is_winner'] else "LOSS"
            self.logger.info(f"Closed {status} {trade['symbol']}: ${net_pnl:.2f} "
                           f"({trade['pnl_percentage']:.1f}%) | {exit_reason}")
            
            return trade
            
        except Exception as e:
            self.logger.error(f"Error closing trade: {e}")
            return trade
    
    def check_stop_loss_take_profit(self, current_prices: Dict[str, float], 
                                   current_time: datetime) -> List[Dict[str, Any]]:
        """
        Check for stop loss and take profit triggers
        
        Returns:
            List of trades to close
        """
        
        trades_to_close = []
        
        try:
            for trade in list(self.active_trades):  # Copy list to avoid modification during iteration
                symbol = trade['symbol']
                if symbol not in current_prices:
                    continue
                
                current_price = current_prices[symbol]
                
                # Check stop loss
                if trade['direction'] == 'LONG':
                    if current_price <= trade['stop_loss_price']:
                        trades_to_close.append((trade, current_price, "Stop Loss"))
                    elif current_price >= trade['take_profit_price']:
                        trades_to_close.append((trade, current_price, "Take Profit"))
                else:  # SHORT
                    if current_price >= trade['stop_loss_price']:
                        trades_to_close.append((trade, current_price, "Stop Loss"))
                    elif current_price <= trade['take_profit_price']:
                        trades_to_close.append((trade, current_price, "Take Profit"))
                
                # Check time-based exit (maximum 4 hours)
                hours_open = (current_time - trade['entry_time']).total_seconds() / 3600
                if hours_open >= 4:
                    trades_to_close.append((trade, current_price, "Time Exit"))
            
            return trades_to_close
            
        except Exception as e:
            self.logger.error(f"Error checking SL/TP: {e}")
            return []
    
    def reset_daily_pnl(self):
        """Reset daily PnL counter (call at start of each day)"""
        self.daily_pnl = 0.0
    
    def get_risk_metrics(self) -> Dict[str, Any]:
        """Get current risk metrics and statistics"""
        
        try:
            # Calculate current exposure
            total_margin_used = sum(trade['margin_used'] for trade in self.active_trades)
            total_position_value = sum(
                trade['position_size'] * trade['entry_price'] 
                for trade in self.active_trades
            )
            
            # Current drawdown
            current_drawdown = 0.0
            if self.peak_capital > 0:
                current_drawdown = (self.peak_capital - self.current_capital) / self.peak_capital * 100
            
            # Account health
            account_health = "HEALTHY"
            if current_drawdown > 15:
                account_health = "AT_RISK"
            elif current_drawdown > 25:
                account_health = "DANGER"
            elif self.current_capital < self.initial_capital * 0.5:
                account_health = "CRITICAL"
            
            return {
                'current_capital': self.current_capital,
                'initial_capital': self.initial_capital,
                'peak_capital': self.peak_capital,
                'total_return_pct': ((self.current_capital - self.initial_capital) / self.initial_capital) * 100,
                'current_drawdown_pct': current_drawdown,
                'max_drawdown_pct': self.max_drawdown,
                'daily_pnl': self.daily_pnl,
                'active_trades_count': len(self.active_trades),
                'total_margin_used': total_margin_used,
                'total_position_value': total_position_value,
                'margin_utilization_pct': (total_margin_used / self.current_capital) * 100 if self.current_capital > 0 else 0,
                'total_commission_paid': self.total_commission_paid,
                'total_funding_paid': self.total_funding_paid,
                'account_health': account_health,
                'risk_capacity_remaining': max(0, self.max_concurrent_trades - len(self.active_trades))
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating risk metrics: {e}")
            return {}
    
    def suggest_risk_improvements(self) -> List[str]:
        """Analyze risk metrics and suggest improvements"""
        
        recommendations = []
        metrics = self.get_risk_metrics()
        
        try:
            # Drawdown analysis
            if metrics.get('max_drawdown_pct', 0) > 20:
                recommendations.append("Consider reducing position sizes - max drawdown exceeded 20%")
            
            # Capital utilization
            margin_util = metrics.get('margin_utilization_pct', 0)
            if margin_util > 80:
                recommendations.append("High margin utilization - consider reducing concurrent trades")
            elif margin_util < 20:
                recommendations.append("Low margin utilization - consider slightly larger position sizes")
            
            # Commission analysis
            total_return = metrics.get('total_return_pct', 0)
            commission_pct = (metrics.get('total_commission_paid', 0) / self.initial_capital) * 100
            
            if commission_pct > abs(total_return) * 0.3:
                recommendations.append("Commission costs are high relative to returns - consider longer hold times")
            
            # Account health
            if metrics.get('account_health') == 'AT_RISK':
                recommendations.append("Account at risk - implement stricter loss limits and position sizing")
            elif metrics.get('account_health') == 'DANGER':
                recommendations.append("URGENT: Account in danger - stop trading and review strategy")
            
            if not recommendations:
                recommendations.append("Risk management appears appropriate for current market conditions")
            
        except Exception as e:
            self.logger.error(f"Error generating risk recommendations: {e}")
            recommendations.append("Unable to analyze risk metrics due to error")
        
        return recommendations