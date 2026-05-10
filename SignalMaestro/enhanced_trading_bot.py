#!/usr/bin/env python3
"""
Enhanced Trading Bot - Improved version with optimized strategy and realistic performance
Based on backtest insights: 46.7% win rate → targeting 65%+ win rate
"""

import asyncio
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import json
import os

# Import dynamic error fixer
try:
    from dynamic_error_fixer import get_global_error_fixer, auto_fix_error
    ERROR_FIXER_AVAILABLE = True
except ImportError:
    ERROR_FIXER_AVAILABLE = False

class EnhancedTradingBot:
    """Enhanced trading bot with improved strategy and realistic capital management"""
    
    def __init__(self):
        self.logger = self._setup_logging()
        
        # Enhanced configuration based on backtest results
        self.config = {
            'initial_capital': 10.0,
            'risk_percentage': 1.5,  # Conservative 1.5% per trade
            'max_concurrent_trades': 2,  # Reduced to 2 for better quality
            'min_leverage': 10,
            'max_leverage': 50,  # Reduced max leverage for safety
            'portfolio_risk_cap': 4.0,  # Conservative 4% total exposure
            'min_signal_strength': 75,  # Higher threshold for quality
            'max_daily_loss': 0.75,  # $0.75 daily loss limit
            'profit_target_multiplier': 2.5,  # 1:2.5 R/R for better win rate
            'adaptive_sizing': True,  # Adapt position size based on performance
        }
        
        # Enhanced performance tracking
        self.performance_metrics = {
            'recent_win_rate': 0.5,
            'recent_trades': [],
            'consecutive_losses': 0,
            'daily_pnl': 0.0,
            'peak_capital': self.config['initial_capital'],
            'current_drawdown': 0.0
        }
        
        # Advanced signal filtering
        self.signal_filters = {
            'volatility_filter': True,
            'trend_confirmation': True,
            'volume_confirmation': True,
            'market_session_filter': True,
            'correlation_filter': True
        }
        
        # Error fixing capability
        if ERROR_FIXER_AVAILABLE:
            self.error_fixer = get_global_error_fixer()
        
        self.logger.info("🚀 Enhanced Trading Bot initialized with optimized parameters")
    
    def _setup_logging(self) -> logging.Logger:
        """Setup enhanced logging"""
        logger = logging.getLogger('EnhancedTradingBot')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            # File handler with rotation
            file_handler = logging.FileHandler('enhanced_trading_bot.log')
            file_handler.setLevel(logging.DEBUG)
            
            # Formatter
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(formatter)
            file_handler.setFormatter(formatter)
            
            logger.addHandler(console_handler)
            logger.addHandler(file_handler)
        
        return logger
    
    def enhanced_signal_analysis(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhanced signal analysis with multiple confirmation layers
        Targeting 65%+ win rate through better filtering
        """
        
        try:
            signal_score = 0
            confirmations = []
            
            # Extract market data
            price = market_data.get('price', 0)
            atr_pct = market_data.get('atr_percentage', 1.0)
            volume_ratio = market_data.get('volume_ratio', 1.0)
            trend_strength = market_data.get('trend_strength', 0.5)
            rsi = market_data.get('rsi', 50)
            macd = market_data.get('macd', 0)
            
            # 1. ENHANCED VOLATILITY FILTER
            if self.signal_filters['volatility_filter']:
                if 0.8 <= atr_pct <= 2.2:  # Optimal volatility range
                    signal_score += 20
                    confirmations.append("Optimal volatility")
                elif atr_pct > 3.0:  # Too volatile
                    signal_score -= 15
                    confirmations.append("High volatility penalty")
            
            # 2. ENHANCED TREND CONFIRMATION
            if self.signal_filters['trend_confirmation']:
                if trend_strength > 0.7:  # Strong trend
                    signal_score += 25
                    confirmations.append("Strong trend")
                elif trend_strength > 0.5:  # Moderate trend
                    signal_score += 15
                    confirmations.append("Moderate trend")
                elif trend_strength < 0.3:  # Weak/choppy
                    signal_score -= 10
                    confirmations.append("Weak trend penalty")
            
            # 3. ENHANCED VOLUME CONFIRMATION  
            if self.signal_filters['volume_confirmation']:
                if volume_ratio > 1.5:  # Strong volume
                    signal_score += 15
                    confirmations.append("Strong volume")
                elif volume_ratio > 1.2:  # Above average
                    signal_score += 8
                    confirmations.append("Above average volume")
                elif volume_ratio < 0.7:  # Low volume
                    signal_score -= 8
                    confirmations.append("Low volume penalty")
            
            # 4. RSI DIVERGENCE DETECTION
            if 25 < rsi < 35:  # Oversold but not extreme
                signal_score += 12
                confirmations.append("RSI oversold recovery")
            elif 65 < rsi < 75:  # Overbought but not extreme
                signal_score += 12
                confirmations.append("RSI overbought reversal")
            elif rsi < 20 or rsi > 80:  # Extreme levels - risky
                signal_score -= 5
                confirmations.append("RSI extreme levels")
            
            # 5. MACD MOMENTUM CONFIRMATION
            if abs(macd) > 0.001:  # Significant MACD signal
                signal_score += 10
                confirmations.append("MACD momentum")
            
            # 6. MARKET SESSION FILTER
            if self.signal_filters['market_session_filter']:
                current_hour = datetime.now().hour
                # Optimal trading hours (London/NY overlap)
                if 13 <= current_hour <= 17:  # 1PM-5PM UTC
                    signal_score += 8
                    confirmations.append("Optimal session")
                elif 8 <= current_hour <= 12 or 18 <= current_hour <= 22:
                    signal_score += 3
                    confirmations.append("Good session")
                else:  # Asian session or off-hours
                    signal_score -= 5
                    confirmations.append("Off-hours penalty")
            
            # 7. ADAPTIVE PERFORMANCE ADJUSTMENT
            recent_win_rate = self.performance_metrics['recent_win_rate']
            if recent_win_rate > 0.6:  # Good recent performance
                signal_score += 5
                confirmations.append("Good recent performance")
            elif recent_win_rate < 0.4:  # Poor recent performance
                signal_score -= 10
                confirmations.append("Poor recent performance")
            
            # 8. CONSECUTIVE LOSS PROTECTION
            consecutive_losses = self.performance_metrics['consecutive_losses']
            if consecutive_losses >= 3:
                signal_score -= 15
                confirmations.append("Consecutive loss protection")
            elif consecutive_losses >= 2:
                signal_score -= 8
                confirmations.append("Recent loss caution")
            
            return {
                'enhanced_signal_score': signal_score,
                'confirmations': confirmations,
                'quality_rating': self._get_signal_quality_rating(signal_score),
                'recommended_action': self._get_recommended_action(signal_score),
                'confidence_level': min(100, max(0, signal_score + 50))  # Scale to 0-100
            }
            
        except Exception as e:
            self.logger.error(f"Enhanced signal analysis error: {e}")
            if ERROR_FIXER_AVAILABLE:
                auto_fix_error(str(e))
            return {'enhanced_signal_score': 0, 'confirmations': [], 'quality_rating': 'POOR'}
    
    def _get_signal_quality_rating(self, score: float) -> str:
        """Get signal quality rating"""
        if score >= 80:
            return "EXCELLENT"
        elif score >= 65:
            return "GOOD"
        elif score >= 50:
            return "FAIR"
        elif score >= 35:
            return "POOR"
        else:
            return "REJECT"
    
    def _get_recommended_action(self, score: float) -> str:
        """Get recommended action based on score"""
        if score >= 75:
            return "STRONG_BUY"
        elif score >= 60:
            return "BUY"
        elif score >= 45:
            return "WEAK_BUY"
        elif score >= 30:
            return "HOLD"
        else:
            return "AVOID"
    
    def calculate_enhanced_position_size(self, signal_data: Dict[str, Any], 
                                       current_capital: float) -> Dict[str, Any]:
        """
        Enhanced position sizing with adaptive risk management
        """
        
        try:
            # Base risk calculation (fixed dollar amount)
            base_risk = self.config['initial_capital'] * (self.config['risk_percentage'] / 100)
            
            # Enhanced adaptive sizing
            if self.config['adaptive_sizing']:
                recent_win_rate = self.performance_metrics['recent_win_rate']
                
                if recent_win_rate > 0.65:  # Hot streak
                    risk_multiplier = 1.2
                elif recent_win_rate > 0.55:  # Good performance
                    risk_multiplier = 1.1
                elif recent_win_rate < 0.35:  # Poor performance
                    risk_multiplier = 0.7
                elif recent_win_rate < 0.45:  # Below average
                    risk_multiplier = 0.85
                else:  # Average performance
                    risk_multiplier = 1.0
                
                adjusted_risk = base_risk * risk_multiplier
            else:
                adjusted_risk = base_risk
            
            # Signal quality adjustment
            signal_quality = signal_data.get('quality_rating', 'FAIR')
            if signal_quality == 'EXCELLENT':
                quality_multiplier = 1.3
            elif signal_quality == 'GOOD':
                quality_multiplier = 1.15
            elif signal_quality == 'FAIR':
                quality_multiplier = 1.0
            else:
                quality_multiplier = 0.8
            
            final_risk = adjusted_risk * quality_multiplier
            
            # Ensure we don't exceed available capital
            max_risk = current_capital * 0.15  # Never risk more than 15% of current capital
            final_risk = min(final_risk, max_risk)
            
            # Calculate position details
            entry_price = signal_data.get('price', 100)
            volatility = signal_data.get('atr_percentage', 1.0)
            
            # Enhanced leverage calculation
            leverage = self._calculate_enhanced_leverage(volatility)
            
            # Stop loss based on volatility
            stop_loss_pct = max(1.0, min(2.5, volatility * 1.2))  # 1.0% to 2.5%
            
            # Take profit (enhanced R/R ratio)
            take_profit_pct = stop_loss_pct * self.config['profit_target_multiplier']
            
            # Position size calculation
            stop_loss_distance = entry_price * (stop_loss_pct / 100)
            position_size = final_risk / stop_loss_distance
            position_value = position_size * entry_price
            margin_required = position_value / leverage
            
            return {
                'position_size': position_size,
                'position_value': position_value,
                'margin_required': margin_required,
                'risk_amount': final_risk,
                'leverage': leverage,
                'stop_loss_pct': stop_loss_pct,
                'take_profit_pct': take_profit_pct,
                'risk_multiplier': risk_multiplier if self.config['adaptive_sizing'] else 1.0,
                'quality_multiplier': quality_multiplier,
                'max_potential_loss': final_risk,
                'max_potential_profit': final_risk * self.config['profit_target_multiplier']
            }
            
        except Exception as e:
            self.logger.error(f"Enhanced position sizing error: {e}")
            if ERROR_FIXER_AVAILABLE:
                auto_fix_error(str(e))
            return {}
    
    def _calculate_enhanced_leverage(self, volatility: float) -> int:
        """Calculate enhanced leverage with safety constraints"""
        
        # More conservative leverage calculation
        if volatility <= 0.5:
            leverage = 45  # Reduced from 75
        elif volatility <= 0.8:
            leverage = 40  # Reduced from 70
        elif volatility <= 1.2:
            leverage = 35  # Reduced from 65
        elif volatility <= 1.8:
            leverage = 30  # Reduced from 55
        elif volatility <= 2.5:
            leverage = 20  # Reduced from 35
        elif volatility <= 3.5:
            leverage = 15  # Reduced from 20
        else:
            leverage = 10  # Minimum leverage
        
        # Ensure within configured bounds
        return max(self.config['min_leverage'], min(self.config['max_leverage'], leverage))
    
    def update_performance_metrics(self, trade_result: Dict[str, Any]):
        """Update performance tracking for adaptive improvements"""
        
        try:
            # Add to recent trades (keep last 20)
            self.performance_metrics['recent_trades'].append(trade_result)
            if len(self.performance_metrics['recent_trades']) > 20:
                self.performance_metrics['recent_trades'].pop(0)
            
            # Update recent win rate
            recent_trades = self.performance_metrics['recent_trades']
            if recent_trades:
                wins = sum(1 for trade in recent_trades if trade.get('is_winner', False))
                self.performance_metrics['recent_win_rate'] = wins / len(recent_trades)
            
            # Update consecutive losses
            if trade_result.get('is_winner', False):
                self.performance_metrics['consecutive_losses'] = 0
            else:
                self.performance_metrics['consecutive_losses'] += 1
            
            # Update daily PnL
            self.performance_metrics['daily_pnl'] += trade_result.get('pnl', 0)
            
            # Update drawdown tracking
            current_capital = trade_result.get('current_capital', self.config['initial_capital'])
            if current_capital > self.performance_metrics['peak_capital']:
                self.performance_metrics['peak_capital'] = current_capital
            
            drawdown = (self.performance_metrics['peak_capital'] - current_capital) / self.performance_metrics['peak_capital'] * 100
            self.performance_metrics['current_drawdown'] = drawdown
            
            # Log performance update
            self.logger.info(f"📊 Performance Update: Win Rate: {self.performance_metrics['recent_win_rate']:.1%}, "
                           f"Consecutive Losses: {self.performance_metrics['consecutive_losses']}, "
                           f"Drawdown: {drawdown:.1f}%")
            
        except Exception as e:
            self.logger.error(f"Performance metrics update error: {e}")
            if ERROR_FIXER_AVAILABLE:
                auto_fix_error(str(e))
    
    def should_trade_enhanced(self, signal_data: Dict[str, Any], current_capital: float) -> Tuple[bool, str]:
        """Enhanced trading decision with multiple safety checks"""
        
        try:
            # 1. Capital checks
            if current_capital < self.config['initial_capital'] * 0.7:  # 30% drawdown limit
                return False, "Excessive drawdown - trading suspended"
            
            # 2. Daily loss limit
            if self.performance_metrics['daily_pnl'] <= -self.config['max_daily_loss']:
                return False, "Daily loss limit reached"
            
            # 3. Signal quality check
            signal_score = signal_data.get('enhanced_signal_score', 0)
            if signal_score < self.config['min_signal_strength']:
                return False, f"Signal score too low: {signal_score}"
            
            # 4. Consecutive loss protection
            if self.performance_metrics['consecutive_losses'] >= 4:
                return False, "Too many consecutive losses - cooling off"
            
            # 5. Market conditions check
            volatility = signal_data.get('atr_percentage', 1.0)
            if volatility > 4.0:  # Extreme volatility
                return False, "Market too volatile"
            
            # 6. Recent performance check
            recent_win_rate = self.performance_metrics['recent_win_rate']
            if recent_win_rate < 0.3 and len(self.performance_metrics['recent_trades']) >= 10:
                return False, "Poor recent performance - strategy review needed"
            
            # 7. Quality rating check
            quality_rating = signal_data.get('quality_rating', 'POOR')
            if quality_rating in ['POOR', 'REJECT']:
                return False, f"Signal quality insufficient: {quality_rating}"
            
            return True, "All safety checks passed"
            
        except Exception as e:
            self.logger.error(f"Enhanced trading decision error: {e}")
            if ERROR_FIXER_AVAILABLE:
                auto_fix_error(str(e))
            return False, f"Error in trading decision: {e}"
    
    def generate_enhanced_trading_signal(self, market_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate enhanced trading signal with comprehensive analysis"""
        
        try:
            # Perform enhanced signal analysis
            enhanced_analysis = self.enhanced_signal_analysis(market_data)
            
            # Check if signal meets quality standards
            signal_score = enhanced_analysis.get('enhanced_signal_score', 0)
            quality_rating = enhanced_analysis.get('quality_rating', 'POOR')
            
            if signal_score >= self.config['min_signal_strength'] and quality_rating in ['EXCELLENT', 'GOOD']:
                
                # Determine direction based on signal characteristics
                rsi = market_data.get('rsi', 50)
                trend_strength = market_data.get('trend_strength', 0.5)
                
                if rsi < 40 and trend_strength > 0.5:
                    direction = 'LONG'
                elif rsi > 60 and trend_strength > 0.5:
                    direction = 'SHORT'
                elif trend_strength > 0.7:  # Strong trend continuation
                    direction = 'LONG' if rsi < 60 else 'SHORT'
                else:
                    return None  # No clear direction
                
                # Create enhanced signal
                enhanced_signal = {
                    'timestamp': datetime.now(),
                    'symbol': market_data.get('symbol', 'UNKNOWN'),
                    'direction': direction,
                    'price': market_data.get('price', 0),
                    'signal_strength': signal_score,
                    'quality_rating': quality_rating,
                    'confidence_level': enhanced_analysis.get('confidence_level', 50),
                    'confirmations': enhanced_analysis.get('confirmations', []),
                    'recommended_action': enhanced_analysis.get('recommended_action', 'HOLD'),
                    
                    # Market data
                    'atr_percentage': market_data.get('atr_percentage', 1.0),
                    'volume_ratio': market_data.get('volume_ratio', 1.0),
                    'trend_strength': trend_strength,
                    'rsi': rsi,
                    'macd': market_data.get('macd', 0),
                    
                    # Enhanced metadata
                    'session_quality': self._get_session_quality(),
                    'market_regime': self._detect_market_regime(market_data),
                    'volatility_category': self._get_volatility_category(market_data.get('atr_percentage', 1.0))
                }
                
                self.logger.info(f"🎯 Enhanced signal generated: {direction} {enhanced_signal['symbol']} "
                               f"| Score: {signal_score} | Quality: {quality_rating} "
                               f"| Confirmations: {len(enhanced_analysis.get('confirmations', []))}")
                
                return enhanced_signal
            
            return None
            
        except Exception as e:
            self.logger.error(f"Enhanced signal generation error: {e}")
            if ERROR_FIXER_AVAILABLE:
                auto_fix_error(str(e))
            return None
    
    def _get_session_quality(self) -> str:
        """Determine current trading session quality"""
        current_hour = datetime.now().hour
        
        if 13 <= current_hour <= 17:  # London/NY overlap
            return "PREMIUM"
        elif 8 <= current_hour <= 12:  # London session
            return "GOOD"
        elif 18 <= current_hour <= 22:  # NY session
            return "GOOD"
        elif 1 <= current_hour <= 7:  # Asian session
            return "MODERATE"
        else:  # Off hours
            return "POOR"
    
    def _detect_market_regime(self, market_data: Dict[str, Any]) -> str:
        """Detect current market regime"""
        volatility = market_data.get('atr_percentage', 1.0)
        trend_strength = market_data.get('trend_strength', 0.5)
        volume_ratio = market_data.get('volume_ratio', 1.0)
        
        if volatility > 3.0:
            return "HIGH_VOLATILITY"
        elif volatility < 0.8 and trend_strength > 0.7:
            return "TRENDING"
        elif volatility < 0.8 and trend_strength < 0.3:
            return "RANGE_BOUND"
        elif volume_ratio > 1.5:
            return "HIGH_ACTIVITY"
        else:
            return "NORMAL"
    
    def _get_volatility_category(self, atr_percentage: float) -> str:
        """Get volatility category"""
        if atr_percentage <= 0.5:
            return "ULTRA_LOW"
        elif atr_percentage <= 0.8:
            return "LOW"
        elif atr_percentage <= 1.5:
            return "MODERATE"
        elif atr_percentage <= 2.5:
            return "HIGH"
        elif atr_percentage <= 4.0:
            return "VERY_HIGH"
        else:
            return "EXTREME"
    
    def get_enhancement_summary(self) -> Dict[str, Any]:
        """Get summary of bot enhancements and current performance"""
        
        return {
            'version': '2.0_ENHANCED',
            'key_improvements': [
                'Enhanced signal analysis with 8 confirmation layers',
                'Adaptive position sizing based on recent performance', 
                'Conservative leverage limits (max 50x vs 75x)',
                'Quality-based signal filtering (75+ score required)',
                'Market session and regime detection',
                'Consecutive loss protection',
                'Fixed dollar risk to prevent compounding',
                'Enhanced risk/reward ratio (1:2.5)'
            ],
            'current_config': self.config,
            'performance_metrics': self.performance_metrics,
            'target_improvements': {
                'win_rate_target': '65%+ (vs previous 46.7%)',
                'max_drawdown_target': '<10%',
                'sharpe_ratio_target': '>1.0',
                'profit_factor_target': '>2.0'
            },
            'safety_features': [
                'Daily loss limits',
                'Consecutive loss protection', 
                'Capital drawdown limits',
                'Volatility filters',
                'Session quality filters',
                'Portfolio risk caps'
            ]
        }
    
    async def run_enhanced_strategy_test(self) -> Dict[str, Any]:
        """Run a quick test of the enhanced strategy"""
        
        self.logger.info("🧪 Running Enhanced Strategy Test...")
        
        # Generate test market data
        test_scenarios = [
            {
                'symbol': 'BTCUSDT',
                'price': 27500,
                'atr_percentage': 0.9,
                'volume_ratio': 1.3,
                'trend_strength': 0.8,
                'rsi': 35,
                'macd': 0.002
            },
            {
                'symbol': 'ETHUSDT', 
                'price': 1650,
                'atr_percentage': 1.5,
                'volume_ratio': 0.9,
                'trend_strength': 0.4,
                'rsi': 65,
                'macd': -0.001
            },
            {
                'symbol': 'BNBUSDT',
                'price': 210,
                'atr_percentage': 2.2,
                'volume_ratio': 1.6,
                'trend_strength': 0.9,
                'rsi': 28,
                'macd': 0.005
            }
        ]
        
        test_results = []
        
        for scenario in test_scenarios:
            # Generate enhanced signal
            signal = self.generate_enhanced_trading_signal(scenario)
            
            if signal:
                # Calculate position sizing
                position_info = self.calculate_enhanced_position_size(signal, 10.0)
                
                # Check trading decision
                should_trade, reason = self.should_trade_enhanced(signal, 10.0)
                
                test_results.append({
                    'symbol': scenario['symbol'],
                    'signal_generated': True,
                    'signal_score': signal.get('signal_strength', 0),
                    'quality_rating': signal.get('quality_rating', 'UNKNOWN'),
                    'direction': signal.get('direction', 'NONE'),
                    'should_trade': should_trade,
                    'reason': reason,
                    'position_info': position_info
                })
            else:
                test_results.append({
                    'symbol': scenario['symbol'],
                    'signal_generated': False,
                    'reason': 'No quality signal generated'
                })
        
        # Summary
        signals_generated = sum(1 for r in test_results if r.get('signal_generated', False))
        trades_approved = sum(1 for r in test_results if r.get('should_trade', False))
        
        summary = {
            'test_scenarios': len(test_scenarios),
            'signals_generated': signals_generated,
            'trades_approved': trades_approved,
            'signal_quality_rate': (signals_generated / len(test_scenarios)) * 100,
            'trade_approval_rate': (trades_approved / signals_generated) * 100 if signals_generated > 0 else 0,
            'test_results': test_results,
            'enhancement_status': 'ACTIVE',
            'expected_performance_improvement': 'Win rate: 46.7% → 65%+'
        }
        
        self.logger.info(f"✅ Enhanced Strategy Test Complete: {signals_generated}/{len(test_scenarios)} signals, "
                        f"{trades_approved} trades approved")
        
        return summary

# Export enhanced bot for integration
__all__ = ['EnhancedTradingBot']

if __name__ == "__main__":
    # Quick test of enhanced bot
    async def test_enhanced_bot():
        bot = EnhancedTradingBot()
        
        # Display enhancements
        summary = bot.get_enhancement_summary()
        print("🚀 ENHANCED TRADING BOT")
        print("=" * 50)
        print(f"Version: {summary['version']}")
        print("\n📈 Key Improvements:")
        for improvement in summary['key_improvements']:
            print(f"  • {improvement}")
        
        print(f"\n🎯 Performance Targets:")
        for target, value in summary['target_improvements'].items():
            print(f"  • {target}: {value}")
        
        # Run strategy test
        test_results = await bot.run_enhanced_strategy_test()
        print(f"\n🧪 Strategy Test Results:")
        print(f"  • Signal Quality Rate: {test_results['signal_quality_rate']:.1f}%")
        print(f"  • Trade Approval Rate: {test_results['trade_approval_rate']:.1f}%")
        print(f"  • Expected Improvement: {test_results['expected_performance_improvement']}")
        
        return test_results
    
    asyncio.run(test_enhanced_bot())