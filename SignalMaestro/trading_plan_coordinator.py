#!/usr/bin/env python3
"""
Trading Plan Coordinator - Unified Strategy Management System
Coordinates all trading strategies to work together harmoniously
- Manages signal generation across multiple strategies
- Prevents strategy conflicts and overlapping trades
- Provides unified risk management across all plans
- Coordinates execution timing and position sizing
- Ensures optimal strategy selection based on market conditions
"""

import asyncio
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, asdict
from collections import deque
import json

# Import all trading strategies
from .ultimate_scalping_strategy import UltimateScalpingStrategy, UltimateSignal
from .advanced_time_fibonacci_strategy import AdvancedTimeFibonacciStrategy, AdvancedScalpingSignal
from .momentum_scalping_strategy import MomentumScalpingStrategy, MomentumScalpingSignal
from .volume_breakout_scalping_strategy import VolumeBreakoutScalpingStrategy, VolumeBreakoutSignal
from .lightning_scalping_strategy import LightningScalpingStrategy, LightningScalpingSignal
from .ml_trade_analyzer import MLTradeAnalyzer

@dataclass
class UnifiedTradingSignal:
    """Unified signal combining outputs from multiple strategies"""
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    leverage: int
    signal_strength: float
    risk_reward_ratio: float
    
    # Strategy attribution
    primary_strategy: str
    contributing_strategies: List[str]
    strategy_consensus_score: float
    
    # Unified attributes
    confidence_score: float
    execution_priority: str  # 'critical', 'high', 'normal', 'low'
    expected_duration_minutes: int
    market_conditions: Dict[str, Any]
    
    # Risk management
    position_size_multiplier: float
    max_risk_percentage: float
    
    timestamp: datetime

class TradingPlanCoordinator:
    """Coordinates all trading strategies for optimal performance"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Initialize MACD ANTI strategy - replaces all traditional strategies
        from .macd_anti_strategy import MACDAntiStrategy
        self.strategies = {
            'macd_anti_primary': MACDAntiStrategy(),
            'macd_anti_secondary': MACDAntiStrategy(),
            'macd_anti_tertiary': MACDAntiStrategy()
        }
        
        # Initialize ML analyzer for enhanced decision making
        self.ml_analyzer = MLTradeAnalyzer()
        
        # Coordination parameters
        self.max_concurrent_signals = 3  # Maximum simultaneous signals
        self.min_signal_spacing_minutes = 5  # Minimum time between signals for same symbol
        self.strategy_weights = {
            'macd_anti_primary': 0.50,    # Primary MACD ANTI with highest weight
            'macd_anti_secondary': 0.30,  # Secondary for confirmation
            'macd_anti_tertiary': 0.20    # Tertiary for additional validation
        }
        
        # Active signal tracking
        self.active_signals = {}
        self.signal_history = deque(maxlen=100)
        self.last_signal_times = {}
        
        # Performance tracking
        self.strategy_performance = {
            strategy: {
                'signals_generated': 0, 
                'avg_strength': 0, 
                'success_rate': 0,
                'macd_anti_accuracy': 0,
                'ai_confidence_score': 0,
                'anti_trend_success': 0
            }
            for strategy in self.strategies.keys()
        }
        
        # Market condition assessment
        self.market_conditions = {
            'volatility': 'normal',
            'trend': 'neutral',
            'volume': 'normal',
            'session': 'unknown'
        }
        
        self.logger.info("🎯 Trading Plan Coordinator initialized with 5 strategies")
    
    async def analyze_symbol(self, symbol: str, ohlcv_data: Dict[str, List], 
                           market_conditions: Optional[Dict[str, Any]] = None) -> Optional[UnifiedTradingSignal]:
        """Coordinate analysis across all strategies for a unified signal"""
        try:
            # Check if we can generate a new signal for this symbol
            if not self._can_generate_signal(symbol):
                return None
            
            # Update market conditions if provided
            if market_conditions:
                self.market_conditions.update(market_conditions)
            
            # Run all strategies in parallel for efficiency
            strategy_results = await self._run_all_strategies(symbol, ohlcv_data)
            
            # Filter valid signals
            valid_signals = {name: signal for name, signal in strategy_results.items() 
                           if signal is not None}
            
            if not valid_signals:
                return None
            
            # Select optimal strategy combination
            unified_signal = await self._create_unified_signal(symbol, valid_signals, ohlcv_data)
            
            if unified_signal:
                # Record the signal
                self._record_signal(unified_signal)
                
                # Update performance tracking
                self._update_performance_tracking(unified_signal, valid_signals)
                
                self.logger.info(f"🎯 Unified Signal Generated: {symbol} | "
                               f"Primary: {unified_signal.primary_strategy} | "
                               f"Consensus: {len(unified_signal.contributing_strategies)} strategies | "
                               f"Strength: {unified_signal.signal_strength:.1f}% | "
                               f"Confidence: {unified_signal.confidence_score:.1f}%")
                
                return unified_signal
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error in coordinated analysis for {symbol}: {e}")
            return None
    
    def _can_generate_signal(self, symbol: str) -> bool:
        """Check if we can generate a new signal for this symbol"""
        try:
            # Check concurrent signal limit
            if len(self.active_signals) >= self.max_concurrent_signals:
                return False
            
            # Check symbol-specific timing
            if symbol in self.last_signal_times:
                time_diff = (datetime.now() - self.last_signal_times[symbol]).total_seconds()
                if time_diff < (self.min_signal_spacing_minutes * 60):
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking signal generation eligibility: {e}")
            return False
    
    async def _run_all_strategies(self, symbol: str, ohlcv_data: Dict[str, List]) -> Dict[str, Any]:
        """Run all strategies concurrently for maximum efficiency"""
        try:
            # Create analysis tasks for all strategies
            tasks = {}
            
            # Ultimate Scalping Strategy
            tasks['ultimate_scalping'] = asyncio.create_task(
                self.strategies['ultimate_scalping'].analyze_symbol(symbol, ohlcv_data)
            )
            
            # Advanced Time Fibonacci Strategy (with ML analyzer)
            try:
                # Check if strategy accepts ML analyzer parameter
                import inspect
                sig = inspect.signature(self.strategies['fibonacci_time'].analyze_symbol)
                if len(sig.parameters) >= 3:
                    tasks['fibonacci_time'] = asyncio.create_task(
                        self.strategies['fibonacci_time'].analyze_symbol(symbol, ohlcv_data, self.ml_analyzer)
                    )
                else:
                    tasks['fibonacci_time'] = asyncio.create_task(
                        self.strategies['fibonacci_time'].analyze_symbol(symbol, ohlcv_data)
                    )
            except Exception:
                # Fallback to standard signature
                tasks['fibonacci_time'] = asyncio.create_task(
                    self.strategies['fibonacci_time'].analyze_symbol(symbol, ohlcv_data)
                )
            
            # Momentum Scalping Strategy
            tasks['momentum_scalping'] = asyncio.create_task(
                self.strategies['momentum_scalping'].analyze_symbol(symbol, ohlcv_data)
            )
            
            # Volume Breakout Strategy
            tasks['volume_breakout'] = asyncio.create_task(
                self.strategies['volume_breakout'].analyze_symbol(symbol, ohlcv_data)
            )
            
            # Lightning Scalping Strategy
            tasks['lightning_scalping'] = asyncio.create_task(
                self.strategies['lightning_scalping'].analyze_symbol(symbol, ohlcv_data)
            )
            
            # Wait for all tasks to complete
            results = {}
            for strategy_name, task in tasks.items():
                try:
                    results[strategy_name] = await task
                except Exception as e:
                    self.logger.error(f"Error in {strategy_name} strategy: {e}")
                    results[strategy_name] = None
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error running strategies: {e}")
            return {}
    
    async def _create_unified_signal(self, symbol: str, valid_signals: Dict[str, Any], 
                                   ohlcv_data: Dict[str, List]) -> Optional[UnifiedTradingSignal]:
        """Create unified signal from multiple strategy outputs"""
        try:
            # Analyze signal consensus
            consensus_analysis = self._analyze_signal_consensus(valid_signals)
            
            if consensus_analysis['consensus_score'] < 0.6:  # Minimum consensus threshold
                return None
            
            # Select primary strategy based on conditions and performance
            primary_strategy = self._select_primary_strategy(valid_signals, consensus_analysis)
            primary_signal = valid_signals[primary_strategy]
            
            # Get ML confidence assessment
            ml_assessment = await self._get_ml_assessment(symbol, primary_signal, ohlcv_data)
            
            # Calculate unified parameters
            unified_params = self._calculate_unified_parameters(valid_signals, primary_signal, ml_assessment)
            
            # Determine execution priority
            execution_priority = self._determine_execution_priority(
                unified_params['signal_strength'], 
                consensus_analysis['consensus_score'],
                ml_assessment.get('confidence', 50)
            )
            
            return UnifiedTradingSignal(
                symbol=symbol,
                direction=consensus_analysis['consensus_direction'],
                entry_price=unified_params['entry_price'],
                stop_loss=unified_params['stop_loss'],
                tp1=unified_params['tp1'],
                tp2=unified_params['tp2'],
                tp3=unified_params['tp3'],
                leverage=unified_params['leverage'],
                signal_strength=unified_params['signal_strength'],
                risk_reward_ratio=unified_params['risk_reward_ratio'],
                primary_strategy=primary_strategy,
                contributing_strategies=list(valid_signals.keys()),
                strategy_consensus_score=consensus_analysis['consensus_score'],
                confidence_score=ml_assessment.get('confidence', 75),
                execution_priority=execution_priority,
                expected_duration_minutes=unified_params['expected_duration'],
                market_conditions=dict(self.market_conditions),
                position_size_multiplier=ml_assessment.get('position_multiplier', 1.0),
                max_risk_percentage=unified_params['max_risk_percentage'],
                timestamp=datetime.now()
            )
            
        except Exception as e:
            self.logger.error(f"Error creating unified signal: {e}")
            return None
    
    def _analyze_signal_consensus(self, valid_signals: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze consensus across multiple strategy signals"""
        try:
            if not valid_signals:
                return {'consensus_score': 0, 'consensus_direction': 'neutral'}
            
            # Normalize and validate signals first
            normalized_signals = self._normalize_signals(valid_signals)
            
            # Direction analysis
            directions = []
            strengths = []
            
            for strategy_name, signal in normalized_signals.items():
                directions.append(signal.get('direction', 'BUY'))
                strengths.append(signal.get('signal_strength', 50))
            
            # Count direction votes
            buy_votes = directions.count('BUY')
            sell_votes = directions.count('SELL')
            total_votes = len(directions)
            
            # Determine consensus direction
            if buy_votes > sell_votes:
                consensus_direction = 'BUY'
                direction_consensus = buy_votes / total_votes
            elif sell_votes > buy_votes:
                consensus_direction = 'SELL'
                direction_consensus = sell_votes / total_votes
            else:
                consensus_direction = 'neutral'
                direction_consensus = 0.5
            
            # Calculate overall consensus score
            avg_strength = np.mean(strengths)
            strength_consistency = 1 - (np.std(strengths) / 100)  # Penalize inconsistent strengths
            
            consensus_score = (direction_consensus * 0.6 + 
                             (avg_strength / 100) * 0.3 + 
                             strength_consistency * 0.1)
            
            return {
                'consensus_score': min(1.0, consensus_score),
                'consensus_direction': consensus_direction,
                'avg_strength': avg_strength,
                'direction_agreement': direction_consensus,
                'strength_consistency': strength_consistency
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing signal consensus: {e}")
            return {'consensus_score': 0, 'consensus_direction': 'neutral'}
    
    def _select_primary_strategy(self, valid_signals: Dict[str, Any], 
                               consensus_analysis: Dict[str, Any]) -> str:
        """Select the primary strategy based on conditions and performance"""
        try:
            # Score each strategy
            strategy_scores = {}
            
            for strategy_name, signal in valid_signals.items():
                score = 0
                
                # Base signal strength (40%)
                score += (signal.signal_strength / 100) * 0.4
                
                # Strategy weight (20%)
                score += self.strategy_weights.get(strategy_name, 0.2) * 0.2
                
                # Historical performance (20%)
                perf = self.strategy_performance.get(strategy_name, {})
                success_rate = perf.get('success_rate', 0.5)
                score += success_rate * 0.2
                
                # Market condition suitability (20%)
                suitability = self._assess_strategy_suitability(strategy_name)
                score += suitability * 0.2
                
                strategy_scores[strategy_name] = score
            
            # Return strategy with highest score
            return max(strategy_scores, key=strategy_scores.get)
            
        except Exception as e:
            self.logger.error(f"Error selecting primary strategy: {e}")
            return list(valid_signals.keys())[0]  # Fallback to first strategy
    
    def _assess_strategy_suitability(self, strategy_name: str) -> float:
        """Assess how suitable a strategy is for current market conditions"""
        try:
            volatility = self.market_conditions.get('volatility', 'normal')
            trend = self.market_conditions.get('trend', 'neutral')
            volume = self.market_conditions.get('volume', 'normal')
            
            # Strategy-specific suitability scoring
            if strategy_name == 'lightning_scalping':
                # Best in high volatility, high volume
                score = 0.6
                if volatility == 'high': score += 0.3
                if volume == 'high': score += 0.1
                
            elif strategy_name == 'volume_breakout':
                # Best with volume surges
                score = 0.7
                if volume == 'high': score += 0.3
                
            elif strategy_name == 'momentum_scalping':
                # Best in trending markets
                score = 0.6
                if trend in ['bullish', 'bearish']: score += 0.3
                if volatility == 'high': score += 0.1
                
            elif strategy_name == 'fibonacci_time':
                # Best in normal conditions with clear trends
                score = 0.8
                if trend != 'neutral': score += 0.1
                if volatility == 'normal': score += 0.1
                
            elif strategy_name == 'ultimate_scalping':
                # Adaptive to most conditions
                score = 0.75
                if volatility != 'low': score += 0.15
                if volume != 'low': score += 0.1
                
            else:
                score = 0.5  # Default
            
            return min(1.0, max(0.0, score))
            
        except Exception as e:
            self.logger.error(f"Error assessing strategy suitability: {e}")
            return 0.5
    
    async def _get_ml_assessment(self, symbol: str, primary_signal: Any, 
                               ohlcv_data: Dict[str, List]) -> Dict[str, Any]:
        """Get ML assessment of the signal"""
        try:
            # Prepare trade data for ML analysis
            trade_data = {
                'symbol': symbol,
                'direction': primary_signal.direction,
                'signal_strength': primary_signal.signal_strength,
                'leverage': primary_signal.leverage,
                'entry_price': primary_signal.entry_price,
                'stop_loss': primary_signal.stop_loss,
                'volatility': self._calculate_current_volatility(ohlcv_data),
                'volume_ratio': self._calculate_volume_ratio(ohlcv_data),
            }
            
            # Get ML confidence
            ml_confidence = self.ml_analyzer.get_ml_confidence(symbol, trade_data)
            
            # Get position size recommendation
            position_multiplier = self.ml_analyzer.get_optimal_position_size(symbol, trade_data)
            
            # Check if we should trade this symbol
            should_trade = self.ml_analyzer.should_trade_symbol(symbol, trade_data)
            
            return {
                'confidence': ml_confidence,
                'position_multiplier': position_multiplier,
                'should_trade': should_trade,
                'ml_recommendation': 'favorable' if ml_confidence > 70 else 'neutral' if ml_confidence > 50 else 'unfavorable'
            }
            
        except Exception as e:
            self.logger.error(f"Error getting ML assessment: {e}")
            return {'confidence': 50, 'position_multiplier': 1.0, 'should_trade': True}
    
    def _calculate_unified_parameters(self, valid_signals: Dict[str, Any], 
                                    primary_signal: Any, ml_assessment: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate unified trading parameters from multiple signals"""
        try:
            # Use primary signal as base
            entry_price = primary_signal.entry_price
            
            # Average key parameters across signals with weighting
            weighted_params = {
                'stop_loss': 0,
                'tp1': 0,
                'tp2': 0,
                'tp3': 0,
                'leverage': 0,
                'signal_strength': 0
            }
            
            total_weight = 0
            
            for strategy_name, signal in valid_signals.items():
                weight = self.strategy_weights.get(strategy_name, 0.2)
                weighted_params['stop_loss'] += signal.stop_loss * weight
                weighted_params['tp1'] += signal.tp1 * weight
                weighted_params['tp2'] += signal.tp2 * weight
                weighted_params['tp3'] += signal.tp3 * weight
                weighted_params['leverage'] += signal.leverage * weight
                weighted_params['signal_strength'] += signal.signal_strength * weight
                total_weight += weight
            
            # Normalize by total weight
            for param in weighted_params:
                weighted_params[param] /= total_weight
            
            # Apply ML adjustments
            ml_confidence_factor = ml_assessment.get('confidence', 75) / 100
            
            # Adjust leverage based on ML confidence
            final_leverage = int(weighted_params['leverage'] * ml_confidence_factor)
            final_leverage = max(5, min(50, final_leverage))  # Bounds checking
            
            # Calculate expected duration (weighted average)
            durations = []
            for signal in valid_signals.values():
                if hasattr(signal, 'expected_hold_seconds'):
                    durations.append(signal.expected_hold_seconds / 60)  # Convert to minutes
                elif hasattr(signal, 'expected_duration_minutes'):
                    durations.append(signal.expected_duration_minutes)
                else:
                    durations.append(5)  # Default 5 minutes
            
            expected_duration = int(np.mean(durations)) if durations else 5
            
            # Risk percentage calculation
            risk_distance = abs(entry_price - weighted_params['stop_loss']) / entry_price
            max_risk_percentage = min(2.0, risk_distance * 100 * final_leverage / 10)
            
            # Risk/reward ratio
            risk_amount = abs(entry_price - weighted_params['stop_loss'])
            reward_amount = abs(weighted_params['tp2'] - entry_price)
            risk_reward_ratio = reward_amount / risk_amount if risk_amount > 0 else 1.5
            
            return {
                'entry_price': entry_price,
                'stop_loss': weighted_params['stop_loss'],
                'tp1': weighted_params['tp1'],
                'tp2': weighted_params['tp2'],
                'tp3': weighted_params['tp3'],
                'leverage': final_leverage,
                'signal_strength': weighted_params['signal_strength'],
                'risk_reward_ratio': risk_reward_ratio,
                'expected_duration': expected_duration,
                'max_risk_percentage': max_risk_percentage
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating unified parameters: {e}")
            # Return primary signal parameters as fallback
            return {
                'entry_price': primary_signal.entry_price,
                'stop_loss': primary_signal.stop_loss,
                'tp1': primary_signal.tp1,
                'tp2': primary_signal.tp2,
                'tp3': primary_signal.tp3,
                'leverage': primary_signal.leverage,
                'signal_strength': primary_signal.signal_strength,
                'risk_reward_ratio': getattr(primary_signal, 'risk_reward_ratio', 2.0),
                'expected_duration': 5,
                'max_risk_percentage': 1.5
            }
    
    def _determine_execution_priority(self, signal_strength: float, 
                                    consensus_score: float, ml_confidence: float) -> str:
        """Determine execution priority based on signal quality"""
        try:
            # Combined score
            combined_score = (signal_strength * 0.4 + 
                            consensus_score * 100 * 0.35 + 
                            ml_confidence * 0.25)
            
            if combined_score >= 85:
                return 'critical'
            elif combined_score >= 75:
                return 'high'
            elif combined_score >= 65:
                return 'normal'
            else:
                return 'low'
                
        except Exception as e:
            self.logger.error(f"Error determining execution priority: {e}")
            return 'normal'
    
    def _calculate_current_volatility(self, ohlcv_data: Dict[str, List]) -> float:
        """Calculate current volatility from OHLCV data"""
        try:
            # Use 1h timeframe if available
            timeframe_data = ohlcv_data.get('1h', ohlcv_data.get('15m', ohlcv_data.get('5m', [])))
            
            if len(timeframe_data) < 20:
                return 0.02  # Default volatility
            
            df = pd.DataFrame(timeframe_data[-20:], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['close'] = pd.to_numeric(df['close'])
            
            # Calculate ATR-based volatility
            df['hl'] = pd.to_numeric(df['high']) - pd.to_numeric(df['low'])
            atr = df['hl'].rolling(window=14).mean().iloc[-1]
            current_price = df['close'].iloc[-1]
            
            return atr / current_price if current_price > 0 else 0.02
            
        except Exception as e:
            self.logger.error(f"Error calculating volatility: {e}")
            return 0.02
    
    def _calculate_volume_ratio(self, ohlcv_data: Dict[str, List]) -> float:
        """Calculate current volume ratio"""
        try:
            # Use 1h timeframe if available
            timeframe_data = ohlcv_data.get('1h', ohlcv_data.get('15m', ohlcv_data.get('5m', [])))
            
            if len(timeframe_data) < 20:
                return 1.0  # Default ratio
            
            df = pd.DataFrame(timeframe_data[-20:], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['volume'] = pd.to_numeric(df['volume'])
            
            current_volume = df['volume'].iloc[-1]
            avg_volume = df['volume'].rolling(window=10).mean().iloc[-1]
            
            return current_volume / avg_volume if avg_volume > 0 else 1.0
            
        except Exception as e:
            self.logger.error(f"Error calculating volume ratio: {e}")
            return 1.0
    
    def _record_signal(self, signal: UnifiedTradingSignal):
        """Record unified signal for tracking"""
        try:
            # Add to active signals
            self.active_signals[signal.symbol] = signal
            
            # Add to history
            self.signal_history.append({
                'timestamp': signal.timestamp,
                'symbol': signal.symbol,
                'direction': signal.direction,
                'primary_strategy': signal.primary_strategy,
                'signal_strength': signal.signal_strength,
                'confidence_score': signal.confidence_score,
                'consensus_score': signal.strategy_consensus_score
            })
            
            # Update last signal time
            self.last_signal_times[signal.symbol] = signal.timestamp
            
        except Exception as e:
            self.logger.error(f"Error recording signal: {e}")
    
    def _update_performance_tracking(self, unified_signal: UnifiedTradingSignal, valid_signals: Dict[str, Any]):
        """Update performance tracking for strategies"""
        try:
            for strategy_name in valid_signals.keys():
                if strategy_name in self.strategy_performance:
                    perf = self.strategy_performance[strategy_name]
                    perf['signals_generated'] = perf.get('signals_generated', 0) + 1
                    
                    # Update running average of signal strength
                    current_avg = perf.get('avg_strength', 0)
                    count = perf['signals_generated']
                    signal_strength = valid_signals[strategy_name].signal_strength
                    perf['avg_strength'] = ((current_avg * (count - 1)) + signal_strength) / count
                    
        except Exception as e:
            self.logger.error(f"Error updating performance tracking: {e}")
    
    def get_coordinator_status(self) -> Dict[str, Any]:
        """Get comprehensive coordinator status"""
        try:
            return {
                'active_strategies': len(self.strategies),
                'active_signals': len(self.active_signals),
                'total_signals_generated': len(self.signal_history),
                'strategy_performance': dict(self.strategy_performance),
                'current_market_conditions': dict(self.market_conditions),
                'coordination_settings': {
                    'max_concurrent_signals': self.max_concurrent_signals,
                    'min_signal_spacing_minutes': self.min_signal_spacing_minutes,
                    'strategy_weights': dict(self.strategy_weights)
                },
                'ml_analyzer_status': self.ml_analyzer.get_model_status(),
                'last_activity': max(self.last_signal_times.values()) if self.last_signal_times else None
            }
            
        except Exception as e:
            self.logger.error(f"Error getting coordinator status: {e}")
            return {'error': str(e)}
    
    async def close_signal(self, symbol: str, outcome: str, profit_loss: float):
        """Close a signal and record the outcome for ML learning"""
        try:
            if symbol in self.active_signals:
                signal = self.active_signals[symbol]
                
                # Prepare trade data for ML learning
                trade_data = {
                    'symbol': symbol,
                    'direction': signal.direction,
                    'entry_price': signal.entry_price,
                    'stop_loss': signal.stop_loss,
                    'take_profit_1': signal.tp1,
                    'take_profit_2': signal.tp2,
                    'take_profit_3': signal.tp3,
                    'signal_strength': signal.signal_strength,
                    'leverage': signal.leverage,
                    'trade_result': outcome,
                    'profit_loss': profit_loss,
                    'entry_time': signal.timestamp,
                    'exit_time': datetime.now(),
                    'duration_minutes': (datetime.now() - signal.timestamp).total_seconds() / 60,
                    'primary_strategy': signal.primary_strategy,
                    'market_conditions': signal.market_conditions,
                    'confidence_score': signal.confidence_score
                }
                
                # Record for ML learning
                await self.ml_analyzer.record_trade(trade_data)
                
                # Update strategy performance
                self._update_strategy_success_rates(signal, outcome)
                
                # Remove from active signals
                del self.active_signals[symbol]
                
                self.logger.info(f"✅ Signal closed: {symbol} | Outcome: {outcome} | P/L: {profit_loss:.2f}%")
                
        except Exception as e:
            self.logger.error(f"Error closing signal for {symbol}: {e}")
    
    def _update_strategy_success_rates(self, signal: UnifiedTradingSignal, outcome: str):
        """Update success rates for strategies involved in the signal"""
        try:
            success = outcome in ['PROFIT', 'TP1', 'TP2', 'TP3']
            
            for strategy_name in signal.contributing_strategies:
                if strategy_name in self.strategy_performance:
                    perf = self.strategy_performance[strategy_name]
                    
                    # Simple running average of success rate
                    current_rate = perf.get('success_rate', 0.5)
                    trades_count = perf.get('trades_completed', 0) + 1
                    
                    new_rate = ((current_rate * (trades_count - 1)) + (1 if success else 0)) / trades_count
                    perf['success_rate'] = new_rate
                    perf['trades_completed'] = trades_count
                    
        except Exception as e:
            self.logger.error(f"Error updating strategy success rates: {e}")
    
    def _normalize_signals(self, signals: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Normalize signals from different strategies to a common format"""
        try:
            normalized = {}
            
            for strategy_name, signal in signals.items():
                try:
                    # Create normalized signal dictionary
                    normalized_signal = {
                        'strategy_name': strategy_name,
                        'direction': getattr(signal, 'direction', 'BUY'),
                        'entry_price': getattr(signal, 'entry_price', 0),
                        'stop_loss': getattr(signal, 'stop_loss', 0),
                        'tp1': getattr(signal, 'tp1', 0),
                        'tp2': getattr(signal, 'tp2', 0),
                        'tp3': getattr(signal, 'tp3', 0),
                        'signal_strength': getattr(signal, 'signal_strength', 50),
                        'leverage': getattr(signal, 'leverage', 10),
                        'risk_reward_ratio': getattr(signal, 'risk_reward_ratio', 2.0),
                        'timestamp': getattr(signal, 'timestamp', datetime.now())
                    }
                    
                    # Validation checks
                    if normalized_signal['entry_price'] <= 0:
                        self.logger.warning(f"Invalid entry price for {strategy_name}: {normalized_signal['entry_price']}")
                        continue
                        
                    if normalized_signal['signal_strength'] <= 0 or normalized_signal['signal_strength'] > 100:
                        self.logger.warning(f"Invalid signal strength for {strategy_name}: {normalized_signal['signal_strength']}")
                        normalized_signal['signal_strength'] = max(1, min(100, normalized_signal['signal_strength']))
                    
                    if normalized_signal['leverage'] <= 0 or normalized_signal['leverage'] > 100:
                        self.logger.warning(f"Invalid leverage for {strategy_name}: {normalized_signal['leverage']}")
                        normalized_signal['leverage'] = max(5, min(50, normalized_signal['leverage']))
                    
                    normalized[strategy_name] = normalized_signal
                    
                except Exception as e:
                    self.logger.error(f"Error normalizing signal from {strategy_name}: {e}")
                    continue
            
            return normalized
            
        except Exception as e:
            self.logger.error(f"Error normalizing signals: {e}")
            return {}
    
    def _validate_strategy_compatibility(self) -> Dict[str, bool]:
        """Validate that all strategies are compatible and functional"""
        try:
            compatibility = {}
            
            for strategy_name, strategy in self.strategies.items():
                try:
                    # Check if strategy has required analyze_symbol method
                    if not hasattr(strategy, 'analyze_symbol'):
                        compatibility[strategy_name] = False
                        self.logger.error(f"Strategy {strategy_name} missing analyze_symbol method")
                        continue
                    
                    # Check method signature
                    import inspect
                    sig = inspect.signature(strategy.analyze_symbol)
                    params = list(sig.parameters.keys())
                    
                    # Must have at least 'self', 'symbol', 'ohlcv_data'
                    if len(params) < 3:
                        compatibility[strategy_name] = False
                        self.logger.error(f"Strategy {strategy_name} has invalid analyze_symbol signature")
                        continue
                    
                    compatibility[strategy_name] = True
                    self.logger.debug(f"Strategy {strategy_name} validated successfully")
                    
                except Exception as e:
                    compatibility[strategy_name] = False
                    self.logger.error(f"Error validating strategy {strategy_name}: {e}")
            
            # Log overall compatibility status
            compatible_count = sum(compatibility.values())
            total_count = len(compatibility)
            self.logger.info(f"Strategy compatibility: {compatible_count}/{total_count} strategies compatible")
            
            return compatibility
            
        except Exception as e:
            self.logger.error(f"Error validating strategy compatibility: {e}")
            return {}
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get comprehensive system health check"""
        try:
            # Validate strategy compatibility
            compatibility = self._validate_strategy_compatibility()
            
            # Check ML analyzer status
            ml_status = self.ml_analyzer.get_model_status() if self.ml_analyzer else {'error': 'No ML analyzer'}
            
            # Count active components
            active_strategies = sum(compatibility.values()) if compatibility else 0
            
            return {
                'coordinator_status': 'healthy' if active_strategies >= 3 else 'degraded',
                'active_strategies': active_strategies,
                'total_strategies': len(self.strategies),
                'strategy_compatibility': compatibility,
                'ml_analyzer_ready': ml_status.get('learning_ready', False),
                'active_signals_count': len(self.active_signals),
                'performance_tracking_active': len(self.strategy_performance) > 0,
                'last_health_check': datetime.now(),
                'recommendations': self._get_health_recommendations(active_strategies, ml_status)
            }
            
        except Exception as e:
            self.logger.error(f"Error getting system health: {e}")
            return {
                'coordinator_status': 'error',
                'error': str(e),
                'timestamp': datetime.now()
            }
    
    def _get_health_recommendations(self, active_strategies: int, ml_status: Dict) -> List[str]:
        """Get health recommendations based on system status"""
        recommendations = []
        
        if active_strategies < 3:
            recommendations.append("Warning: Less than 3 strategies active - system reliability may be reduced")
        
        if active_strategies == 0:
            recommendations.append("Critical: No strategies are functional - coordinator cannot generate signals")
        
        if not ml_status.get('learning_ready', False):
            recommendations.append("Info: ML analyzer needs more trade data to improve predictions")
        
        if len(self.signal_history) == 0:
            recommendations.append("Info: No trading history yet - performance tracking will improve over time")
        
        if active_strategies == len(self.strategies):
            recommendations.append("Excellent: All strategies are functional and working together")
        
        return recommendations