"""
Risk management system for trading signals
Handles position sizing, risk calculation, and trade validation
"""

import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal, ROUND_DOWN
import asyncio

from config import Config

class RiskManager:
    """Risk management and position sizing calculator"""
    
    def __init__(self):
        self.config = Config()
        self.logger = logging.getLogger(__name__)
        
    async def validate_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate trading signal from risk management perspective
        
        Args:
            signal: Parsed trading signal
            
        Returns:
            Validation result with risk assessment
        """
        try:
            validation_result = {
                'valid': True,
                'warnings': [],
                'errors': [],
                'risk_level': 'medium',
                'position_size': 0,
                'risk_reward_ratio': 0,
                'max_loss': 0,
                'expected_profit': 0
            }
            
            # Basic signal structure validation
            if not self._validate_signal_structure(signal, validation_result):
                return validation_result
            
            # Calculate risk metrics
            await self._calculate_risk_metrics(signal, validation_result)
            
            # Validate position size limits
            self._validate_position_limits(signal, validation_result)
            
            # Validate risk-reward ratio
            self._validate_risk_reward_ratio(signal, validation_result)
            
            # Check market conditions (if needed)
            await self._check_market_conditions(signal, validation_result)
            
            # Determine overall risk level
            self._determine_risk_level(validation_result)
            
            # Final validation status
            validation_result['valid'] = len(validation_result['errors']) == 0
            
            return validation_result
            
        except Exception as e:
            self.logger.error(f"Error validating signal: {e}")
            return {
                'valid': False,
                'errors': [f"Validation error: {str(e)}"],
                'warnings': [],
                'risk_level': 'high'
            }
    
    def _validate_signal_structure(self, signal: Dict[str, Any], result: Dict[str, Any]) -> bool:
        """Validate basic signal structure"""
        try:
            # Check required fields
            required_fields = ['action', 'symbol']
            for field in required_fields:
                if field not in signal:
                    result['errors'].append(f"Missing required field: {field}")
            
            # Validate action
            valid_actions = ['BUY', 'SELL', 'LONG', 'SHORT']
            if signal.get('action', '').upper() not in valid_actions:
                result['errors'].append(f"Invalid action: {signal.get('action')}")
            
            # Validate symbol
            symbol = signal.get('symbol', '')
            if symbol not in self.config.SUPPORTED_PAIRS:
                result['warnings'].append(f"Unsupported trading pair: {symbol}")
            
            # Validate numeric fields
            numeric_fields = ['price', 'stop_loss', 'take_profit', 'quantity', 'leverage']
            for field in numeric_fields:
                if field in signal:
                    try:
                        value = float(signal[field])
                        if value <= 0:
                            result['errors'].append(f"{field} must be positive")
                    except (ValueError, TypeError):
                        result['errors'].append(f"Invalid {field} format")
            
            return len(result['errors']) == 0
            
        except Exception as e:
            result['errors'].append(f"Structure validation error: {str(e)}")
            return False
    
    async def _calculate_risk_metrics(self, signal: Dict[str, Any], result: Dict[str, Any]):
        """Calculate risk metrics for the signal"""
        try:
            action = signal.get('action', '').upper()
            entry_price = signal.get('price', 0)
            stop_loss = signal.get('stop_loss', 0)
            take_profit = signal.get('take_profit', 0)
            
            if not entry_price:
                # If no entry price specified, we can't calculate accurate risk
                result['warnings'].append("No entry price specified - risk calculation limited")
                return
            
            # Calculate risk per unit
            if stop_loss:
                if action in ['BUY', 'LONG']:
                    risk_per_unit = abs(entry_price - stop_loss)
                    if stop_loss >= entry_price:
                        result['warnings'].append("Stop loss should be below entry price for long positions")
                else:  # SELL, SHORT
                    risk_per_unit = abs(stop_loss - entry_price)
                    if stop_loss <= entry_price:
                        result['warnings'].append("Stop loss should be above entry price for short positions")
                
                # Calculate potential profit per unit
                profit_per_unit = 0
                if take_profit:
                    if action in ['BUY', 'LONG']:
                        profit_per_unit = abs(take_profit - entry_price)
                        if take_profit <= entry_price:
                            result['warnings'].append("Take profit should be above entry price for long positions")
                    else:  # SELL, SHORT
                        profit_per_unit = abs(entry_price - take_profit)
                        if take_profit >= entry_price:
                            result['warnings'].append("Take profit should be below entry price for short positions")
                
                # Calculate risk-reward ratio
                if risk_per_unit > 0 and profit_per_unit > 0:
                    result['risk_reward_ratio'] = profit_per_unit / risk_per_unit
                
                # Calculate position size based on risk
                result['position_size'] = await self._calculate_optimal_position_size(
                    signal, risk_per_unit
                )
                
                # Calculate maximum loss and expected profit
                result['max_loss'] = result['position_size'] * risk_per_unit
                result['expected_profit'] = result['position_size'] * profit_per_unit
            
        except Exception as e:
            self.logger.error(f"Error calculating risk metrics: {e}")
            result['warnings'].append(f"Risk calculation error: {str(e)}")
    
    async def _calculate_optimal_position_size(self, signal: Dict[str, Any], risk_per_unit: float) -> float:
        """Calculate optimal position size based on risk management rules"""
        try:
            # This is a simplified calculation - in a real implementation,
            # you would fetch actual account balance from the exchange
            
            # Use configurable capital base
            account_balance = self.config.CAPITAL_BASE  # USD - Configurable capital base
            
            # Default risk percentage
            risk_percentage = self.config.DEFAULT_RISK_PERCENTAGE / 100
            
            # Maximum risk amount
            max_risk_amount = account_balance * risk_percentage
            
            # Calculate position size
            if risk_per_unit > 0:
                position_size = max_risk_amount / risk_per_unit
            else:
                # If no stop loss, use a conservative approach
                entry_price = signal.get('price', 1)
                position_size = max_risk_amount / entry_price
            
            # Apply position size limits
            max_position_value = self.config.MAX_POSITION_SIZE
            min_position_value = self.config.MIN_POSITION_SIZE
            
            entry_price = signal.get('price', 1)
            position_value = position_size * entry_price
            
            if position_value > max_position_value:
                position_size = max_position_value / entry_price
            elif position_value < min_position_value:
                position_size = min_position_value / entry_price
            
            return position_size
            
        except Exception as e:
            self.logger.error(f"Error calculating position size: {e}")
            return 0
    
    def _validate_position_limits(self, signal: Dict[str, Any], result: Dict[str, Any]):
        """Validate position size limits"""
        try:
            position_size = result.get('position_size', 0)
            entry_price = signal.get('price', 1)
            position_value = position_size * entry_price
            
            max_position = self.config.MAX_POSITION_SIZE
            min_position = self.config.MIN_POSITION_SIZE
            
            if position_value > max_position:
                result['warnings'].append(f"Position size ${position_value:.2f} exceeds maximum ${max_position}")
            
            if position_value < min_position:
                result['warnings'].append(f"Position size ${position_value:.2f} below minimum ${min_position}")
            
            # Check if specific quantity is provided and validate it
            if 'quantity' in signal:
                specified_value = float(signal['quantity']) * entry_price
                if specified_value > max_position:
                    result['errors'].append(f"Specified quantity value ${specified_value:.2f} exceeds maximum position size")
                
        except Exception as e:
            result['warnings'].append(f"Position limit validation error: {str(e)}")
    
    def _validate_risk_reward_ratio(self, signal: Dict[str, Any], result: Dict[str, Any]):
        """Validate risk-reward ratio"""
        try:
            risk_reward_ratio = result.get('risk_reward_ratio', 0)
            
            if risk_reward_ratio > 0:
                if risk_reward_ratio < 1.5:
                    result['warnings'].append(f"Low risk-reward ratio: {risk_reward_ratio:.2f} (recommended > 1.5)")
                elif risk_reward_ratio >= 3.0:
                    result['warnings'].append(f"High risk-reward ratio: {risk_reward_ratio:.2f} - verify take profit level")
            
            # Check stop loss percentage
            entry_price = signal.get('price', 0)
            stop_loss = signal.get('stop_loss', 0)
            
            if entry_price and stop_loss:
                stop_loss_percentage = abs(entry_price - stop_loss) / entry_price * 100
                
                if stop_loss_percentage > 10:
                    result['warnings'].append(f"Large stop loss: {stop_loss_percentage:.1f}% (recommended < 10%)")
                elif stop_loss_percentage < 1:
                    result['warnings'].append(f"Very tight stop loss: {stop_loss_percentage:.1f}% (risk of premature exit)")
            
        except Exception as e:
            result['warnings'].append(f"Risk-reward validation error: {str(e)}")
    
    async def _check_market_conditions(self, signal: Dict[str, Any], result: Dict[str, Any]):
        """Check current market conditions for additional risk assessment"""
        try:
            # This is where you would check:
            # - Market volatility
            # - Recent price movements
            # - Volume patterns
            # - Overall market sentiment
            
            # Placeholder for market condition checks
            symbol = signal.get('symbol', '')
            
            # Example checks (would be implemented with real market data)
            market_conditions = {
                'volatility': 'medium',  # Would calculate from recent price data
                'trend': 'neutral',      # Would determine from technical analysis
                'volume': 'normal'       # Would check against average volume
            }
            
            # Add warnings based on market conditions
            if market_conditions['volatility'] == 'high':
                result['warnings'].append("High market volatility detected - consider reducing position size")
            
            if market_conditions['volume'] == 'low':
                result['warnings'].append("Low trading volume - potential liquidity issues")
            
        except Exception as e:
            result['warnings'].append(f"Market condition check error: {str(e)}")
    
    def _determine_risk_level(self, result: Dict[str, Any]):
        """Determine overall risk level based on validation results"""
        try:
            risk_score = 0
            
            # Count errors and warnings
            error_count = len(result.get('errors', []))
            warning_count = len(result.get('warnings', []))
            
            # Add to risk score
            risk_score += error_count * 10  # Errors are serious
            risk_score += warning_count * 3  # Warnings are moderate
            
            # Check risk-reward ratio
            risk_reward_ratio = result.get('risk_reward_ratio', 0)
            if risk_reward_ratio < 1.0:
                risk_score += 5
            elif risk_reward_ratio > 5.0:
                risk_score += 3
            
            # Check position size
            max_loss = result.get('max_loss', 0)
            if max_loss > 500:  # Arbitrary threshold
                risk_score += 3
            
            # Determine risk level
            if risk_score >= 15:
                result['risk_level'] = 'high'
            elif risk_score >= 8:
                result['risk_level'] = 'medium'
            else:
                result['risk_level'] = 'low'
            
        except Exception as e:
            self.logger.error(f"Error determining risk level: {e}")
            result['risk_level'] = 'high'  # Default to high risk on error
    
    def calculate_kelly_criterion(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """
        Calculate optimal position size using Kelly Criterion
        
        Args:
            win_rate: Historical win rate (0-1)
            avg_win: Average winning trade amount
            avg_loss: Average losing trade amount
            
        Returns:
            Recommended position size as fraction of capital
        """
        try:
            if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
                return 0
            
            # Kelly formula: f = (bp - q) / b
            # where:
            # f = fraction of capital to bet
            # b = odds received on the wager (avg_win / avg_loss)
            # p = probability of winning (win_rate)
            # q = probability of losing (1 - win_rate)
            
            b = avg_win / avg_loss
            p = win_rate
            q = 1 - win_rate
            
            kelly_fraction = (b * p - q) / b
            
            # Apply safety factor (typically 25-50% of Kelly)
            safety_factor = 0.25
            recommended_fraction = kelly_fraction * safety_factor
            
            # Ensure result is between 0 and reasonable maximum
            return max(0, min(recommended_fraction, 0.1))  # Max 10% of capital
            
        except Exception as e:
            self.logger.error(f"Error calculating Kelly criterion: {e}")
            return 0.01  # Default to 1% of capital
    
    def assess_drawdown_risk(self, recent_trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Assess drawdown risk based on recent trading performance
        
        Args:
            recent_trades: List of recent trade results
            
        Returns:
            Drawdown risk assessment
        """
        try:
            if not recent_trades:
                return {
                    'current_drawdown': 0,
                    'max_drawdown': 0,
                    'consecutive_losses': 0,
                    'risk_level': 'low'
                }
            
            # Calculate running PnL
            running_pnl = 0
            max_pnl = 0
            max_drawdown = 0
            consecutive_losses = 0
            current_consecutive_losses = 0
            
            for trade in recent_trades:
                pnl = trade.get('pnl', 0)
                running_pnl += pnl
                
                # Track maximum PnL
                if running_pnl > max_pnl:
                    max_pnl = running_pnl
                
                # Calculate drawdown
                drawdown = max_pnl - running_pnl
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                
                # Track consecutive losses
                if pnl < 0:
                    current_consecutive_losses += 1
                    consecutive_losses = max(consecutive_losses, current_consecutive_losses)
                else:
                    current_consecutive_losses = 0
            
            # Current drawdown
            current_drawdown = max_pnl - running_pnl
            
            # Assess risk level
            risk_level = 'low'
            if current_drawdown > 1000 or consecutive_losses >= 5:
                risk_level = 'high'
            elif current_drawdown > 500 or consecutive_losses >= 3:
                risk_level = 'medium'
            
            return {
                'current_drawdown': current_drawdown,
                'max_drawdown': max_drawdown,
                'consecutive_losses': consecutive_losses,
                'current_consecutive_losses': current_consecutive_losses,
                'risk_level': risk_level,
                'recommendation': self._get_drawdown_recommendation(risk_level, current_drawdown)
            }
            
        except Exception as e:
            self.logger.error(f"Error assessing drawdown risk: {e}")
            return {
                'current_drawdown': 0,
                'max_drawdown': 0,
                'consecutive_losses': 0,
                'risk_level': 'high',
                'error': str(e)
            }
    
    def _get_drawdown_recommendation(self, risk_level: str, drawdown: float) -> str:
        """Get recommendation based on drawdown risk level"""
        if risk_level == 'high':
            return f"High drawdown risk (${drawdown:.2f}) - Consider reducing position sizes or taking a break"
        elif risk_level == 'medium':
            return f"Moderate drawdown (${drawdown:.2f}) - Exercise caution with new trades"
        else:
            return "Drawdown within acceptable limits - Continue normal trading"
    
    async def get_risk_summary(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Get overall risk summary for user or system"""
        try:
            # This would typically fetch data from database
            # For now, return a placeholder summary
            
            return {
                'overall_risk_level': 'medium',
                'active_positions': 0,
                'total_exposure': 0,
                'available_margin': 10000,
                'risk_utilization': 0.0,
                'recommendations': [
                    "Risk management system active",
                    "Position sizing within limits",
                    "Monitor market conditions"
                ]
            }
            
        except Exception as e:
            self.logger.error(f"Error getting risk summary: {e}")
            return {
                'overall_risk_level': 'high',
                'error': str(e)
            }
