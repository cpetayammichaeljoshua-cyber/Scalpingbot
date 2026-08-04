#!/usr/bin/env python3
"""
SignalProvider Interface - Generates trading signals with adaptive thresholds
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Protocol
from abc import ABC, abstractmethod
import logging

# Import advanced price action analyzer
try:
    from advanced_price_action_analyzer import AdvancedPriceActionAnalyzer
    ADVANCED_PRICE_ACTION_AVAILABLE = True
except ImportError:
    ADVANCED_PRICE_ACTION_AVAILABLE = False

class SignalProvider(Protocol):
    """Signal provider interface"""
    
    @abstractmethod
    def generate_signals(self, df: pd.DataFrame, symbol: str) -> List[Dict[str, Any]]:
        """Generate trading signals from OHLCV data"""
        pass

class TechnicalSignalProvider:
    """Technical analysis signal generator with adaptive thresholds and advanced price action"""
    
    def __init__(self, min_signal_strength: float = 60.0, adaptive_threshold: bool = True):
        self.logger = logging.getLogger(__name__)
        self.min_signal_strength = min_signal_strength
        self.adaptive_threshold = adaptive_threshold
        self.signals_generated = 0
        self.target_signals_per_week = 20  # Minimum to avoid 0-trade runs
        
        # Initialize advanced price action analyzer
        if ADVANCED_PRICE_ACTION_AVAILABLE:
            self.price_action_analyzer = AdvancedPriceActionAnalyzer()
            self.logger.info("✅ Advanced Price Action Analyzer initialized")
        else:
            self.price_action_analyzer = None
            self.logger.warning("⚠️ Advanced Price Action Analyzer not available")
    
    async def generate_signals(self, df: pd.DataFrame, symbol: str) -> List[Dict[str, Any]]:
        """Generate technical analysis signals with adaptive filtering and advanced price action"""
        
        try:
            if len(df) < 50:
                return []
            
            signals = []
            
            # Calculate additional technical indicators
            df = self._add_signal_indicators(df.copy())
            
            # Generate advanced price action signals if available
            if self.price_action_analyzer:
                try:
                    advanced_signal = await self.price_action_analyzer.generate_trading_signal(df, symbol)
                    if advanced_signal and advanced_signal.confidence >= 0.6:
                        # Convert to standard signal format
                        pa_signal = {
                            'timestamp': advanced_signal.timestamp,
                            'symbol': symbol,
                            'direction': advanced_signal.direction,
                            'signal_strength': advanced_signal.strength,
                            'price': advanced_signal.entry_price,
                            'atr_percentage': self._calculate_atr_percentage(df),
                            'volume_ratio': df.get('volume_ratio', pd.Series([1.0] * len(df))).iloc[-1],
                            'trend_strength': advanced_signal.timing_score,
                            'rsi': df.get('rsi', pd.Series([50] * len(df))).iloc[-1],
                            'reasons': ['Advanced Price Action Analysis'],
                            'volatility_category': self._get_volatility_category(self._calculate_atr_percentage(df)),
                            'liquidity_analysis': advanced_signal.liquidity_analysis,
                            'schelling_points': advanced_signal.schelling_points,
                            'order_flow_analysis': advanced_signal.order_flow_analysis,
                            'strategic_positioning': advanced_signal.strategic_positioning,
                            'risk_reward_ratio': advanced_signal.risk_reward_ratio,
                            'advanced_stop_losses': {
                                'primary_sl': advanced_signal.stop_loss,
                                'take_profits': advanced_signal.take_profit
                            }
                        }
                        signals.append(pa_signal)
                        self.logger.info(f"✅ Generated advanced price action signal for {symbol}")
                except Exception as e:
                    self.logger.warning(f"Advanced price action analysis failed: {e}")
            
            # Generate traditional technical signals
            start_idx = int(len(df) * 0.8)  # Start from 80% through the data
            
            for i in range(start_idx, len(df) - 1):
                current_row = df.iloc[i]
                prev_row = df.iloc[i - 1] if i > 0 else current_row
                
                signal = self._evaluate_signal_conditions(current_row, prev_row, symbol, i)
                if signal:
                    signals.append(signal)
            
            # Apply adaptive threshold if needed (disabled for production backtests
            # to prevent overfitting via threshold relaxation)
            if self.adaptive_threshold and len(signals) < 5 and False:  # NEXT-OVERFIT: disabled adaptive threshold lowering
                self.logger.info(f"Only {len(signals)} signals generated, applying adaptive threshold")
                # Lower threshold and regenerate
                original_threshold = self.min_signal_strength
                self.min_signal_strength = max(50.0, self.min_signal_strength - 10.0)
                
                additional_signals = []
                for i in range(start_idx, len(df) - 1):
                    current_row = df.iloc[i]
                    prev_row = df.iloc[i - 1] if i > 0 else current_row
                    
                    signal = self._evaluate_signal_conditions(current_row, prev_row, symbol, i)
                    if signal:
                        additional_signals.append(signal)
                
                signals.extend(additional_signals)
                self.min_signal_strength = original_threshold  # Reset
            
            self.signals_generated += len(signals)
            self.logger.info(f"Generated {len(signals)} total signals for {symbol} (including advanced price action)")
            
            return signals
            
        except Exception as e:
            self.logger.error(f"Error generating signals for {symbol}: {e}")
            return []
    
    def _add_signal_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators for signal generation
            
            NEXT-BUG4: Previously only computed RSI, MACD, BB, volume_surge, and
            price_momentum. The _evaluate_signal_conditions method reads ema_8,
            ema_21, ema_50, atr_percentage, volume_ratio, and trend_strength via
            .get() with fallback defaults — but those columns were never computed
            here. The EMA alignment check (ema_8 > ema_21 > ema_50) always used
            fallback (close == close == close → never True), so long_conditions
            stayed at 0-1, never reaching the >= 2 threshold. The strategy
            generated ZERO signals. Fixed by computing all indicators here.
        """
        
        try:
            # RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            
            # MACD
            exp1 = df['close'].ewm(span=12).mean()
            exp2 = df['close'].ewm(span=26).mean()
            df['macd'] = exp1 - exp2
            df['macd_signal'] = df['macd'].ewm(span=9).mean()
            df['macd_histogram'] = df['macd'] - df['macd_signal']
            
            # Bollinger Bands
            df['bb_middle'] = df['close'].rolling(20).mean()
            bb_std = df['close'].rolling(20).std()
            df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
            df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
            bb_range = df['bb_upper'] - df['bb_lower']
            df['bb_position'] = (df['close'] - df['bb_lower']) / bb_range.replace(0, np.nan)
            df['bb_position'] = df['bb_position'].fillna(0.5)  # Mid-band when bands collapse
            
            # Volume analysis
            df['volume_sma'] = df['volume'].rolling(20).mean()
            df['volume_surge'] = (df['volume'] / df['volume_sma'].replace(0, np.nan)).fillna(1.0)
            
            # Momentum
            df['price_momentum'] = df['close'].pct_change(5)  # 5-period momentum
            
            # NEXT-BUG4 FIX: EMAs for trend alignment detection
            df['ema_8'] = df['close'].ewm(span=8).mean()
            df['ema_21'] = df['close'].ewm(span=21).mean()
            df['ema_50'] = df['close'].ewm(span=50).mean()
            
            # NEXT-BUG4 FIX: ATR percentage for volatility-aware signals
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift(1))
            low_close = np.abs(df['low'] - df['close'].shift(1))
            true_range = np.maximum(high_low, np.maximum(high_close, low_close))
            atr = true_range.rolling(window=14).mean()
            df['atr'] = atr
            df['atr_percentage'] = (atr / df['close']) * 100
            
            # NEXT-BUG4 FIX: volume_ratio (current vs 20-period average)
            vol_avg = df['volume'].rolling(20).mean()
            df['volume_ratio'] = (df['volume'] / vol_avg.replace(0, np.nan)).fillna(1.0)
            
            # NEXT-BUG4 FIX: trend_strength (0-1 scale) based on EMA spread
            ema_spread = np.abs(df['ema_8'] - df['ema_50']) / df['close']
            df['trend_strength'] = np.clip(ema_spread * 50, 0, 1)
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error adding signal indicators: {e}")
            return df
    
    def _evaluate_signal_conditions(self, current: pd.Series, previous: pd.Series, 
                                   symbol: str, index: int) -> Optional[Dict[str, Any]]:
        """Evaluate current market conditions for signals"""
        
        try:
            signal_strength = 0.0
            direction = None
            reasons = []
            
            # Get values safely
            rsi = current.get('rsi', 50)
            macd = current.get('macd', 0)
            macd_signal = current.get('macd_signal', 0)
            macd_hist = current.get('macd_histogram', 0)
            prev_macd_hist = previous.get('macd_histogram', 0)
            
            bb_position = current.get('bb_position', 0.5)
            volume_surge = current.get('volume_surge', 1.0)
            price_momentum = current.get('price_momentum', 0)
            
            ema_8 = current.get('ema_8', current['close'])
            ema_21 = current.get('ema_21', current['close'])
            ema_50 = current.get('ema_50', current['close'])
            
            atr_pct = current.get('atr_percentage', 1.0)
            trend_strength = current.get('trend_strength', 0.5)
            
            # LONG signal conditions
            long_conditions = 0
            long_score = 0
            
            # EMA alignment (bullish)
            if ema_8 > ema_21 > ema_50:
                long_conditions += 1
                long_score += 25
                reasons.append("EMA bullish alignment")
            
            # RSI oversold but recovering
            if 25 < rsi < 45:
                long_conditions += 1
                long_score += 20
                reasons.append("RSI oversold recovery")
            
            # MACD bullish crossover
            if macd > macd_signal and prev_macd_hist <= 0 and macd_hist > 0:
                long_conditions += 1
                long_score += 30
                reasons.append("MACD bullish crossover")
            
            # Bollinger Band bounce from lower band
            if bb_position < 0.2:
                long_conditions += 1
                long_score += 15
                reasons.append("BB lower band bounce")
            
            # Volume confirmation
            if volume_surge > 1.2:
                long_score += 10
                reasons.append("Volume surge")
            
            # Positive momentum
            if price_momentum > 0.005:  # > 0.5% momentum
                long_score += 10
                reasons.append("Positive momentum")
            
            # Check for LONG signal
            if long_conditions >= 2 and long_score >= self.min_signal_strength:
                direction = 'LONG'
                signal_strength = min(95.0, float(long_score))  # NEXT-RNG: removed np.random noise for reproducible backtests
            
            # SHORT signal conditions
            short_conditions = 0
            short_score = 0
            short_reasons = []
            
            # EMA alignment (bearish)
            if ema_8 < ema_21 < ema_50:
                short_conditions += 1
                short_score += 25
                short_reasons.append("EMA bearish alignment")
            
            # RSI overbought
            if 55 < rsi < 75:
                short_conditions += 1
                short_score += 20
                short_reasons.append("RSI overbought")
            
            # MACD bearish crossover
            if macd < macd_signal and prev_macd_hist >= 0 and macd_hist < 0:
                short_conditions += 1
                short_score += 30
                short_reasons.append("MACD bearish crossover")
            
            # Bollinger Band rejection from upper band
            if bb_position > 0.8:
                short_conditions += 1
                short_score += 15
                short_reasons.append("BB upper band rejection")
            
            # Volume confirmation
            if volume_surge > 1.2:
                short_score += 10
                short_reasons.append("Volume surge")
            
            # Negative momentum
            if price_momentum < -0.005:  # < -0.5% momentum
                short_score += 10
                short_reasons.append("Negative momentum")
            
            # Check for SHORT signal (only if no LONG signal)
            if direction != 'LONG' and short_conditions >= 2 and short_score >= self.min_signal_strength:
                direction = 'SHORT'
                signal_strength = min(95.0, float(short_score))  # NEXT-RNG: removed np.random noise for reproducible backtests
                reasons = short_reasons
            
            # Return signal if valid
            if direction and signal_strength >= self.min_signal_strength:
                # Entry price is the bar CLOSE where the signal was generated.
                # BUG12 FIX: previous NEXT-LOOKAHEAD patch referenced `df['open'].iloc[index+1]`
                # but `df` is NOT in scope in this method (only `current`/`previous` Series are),
                # so it raised NameError, was silently swallowed by the bare except below,
                # and produced ZERO signals — the strategy never fired. Real lookahead
                # protection lives at the trade-execution layer (cli.py advances entry to
                # df.iloc[entry_idx + 1], so the signal bar's close is the decision price,
                # not the fill price). Keep the signal price as `current['close']` here.
                return {
                    'timestamp': current.name,
                    'symbol': symbol,
                    'direction': direction,
                    'signal_strength': signal_strength,
                    'price': current['close'],
                    'atr_percentage': atr_pct,
                    'volume_ratio': current.get('volume_ratio', 1.0),
                    'trend_strength': trend_strength,
                    'rsi': rsi,
                    'macd_signal_type': 'bullish' if direction == 'LONG' else 'bearish',
                    'reasons': reasons,
                    'volatility_category': self._get_volatility_category(atr_pct)
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error evaluating signal conditions: {e}")
            return None
    
    def _calculate_atr_percentage(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate ATR as percentage of price"""
        try:
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            
            true_range = np.maximum(high_low, np.maximum(high_close, low_close))
            atr = true_range.rolling(window=period).mean().iloc[-1]
            atr_percentage = (atr / df['close'].iloc[-1]) * 100
            
            return atr_percentage if not np.isnan(atr_percentage) else 1.0
        except Exception:
            return 1.0

    def _get_volatility_category(self, atr_percentage: float) -> str:
        """Get volatility category string"""
        if atr_percentage <= 0.5:
            return "ULTRA LOW"
        elif atr_percentage <= 0.8:
            return "VERY LOW"
        elif atr_percentage <= 1.2:
            return "LOW"
        elif atr_percentage <= 1.8:
            return "MEDIUM"
        elif atr_percentage <= 2.5:
            return "HIGH"
        elif atr_percentage <= 3.5:
            return "VERY HIGH"
        else:
            return "EXTREME"

class MLSignalFilter:
    """Machine Learning signal filter with adaptive confidence thresholds"""
    
    def __init__(self, base_confidence: float = 0.6):
        self.logger = logging.getLogger(__name__)
        self.base_confidence = base_confidence
        self.adaptive_confidence = base_confidence
        self.signals_processed = 0
    
    def filter_signal(self, signal: Dict[str, Any]) -> bool:
        """Filter signal using ML-based confidence scoring"""
        
        try:
            # Extract features for ML scoring
            features = {
                'signal_strength': signal.get('signal_strength', 50),
                'atr_percentage': signal.get('atr_percentage', 1.0),
                'volume_ratio': signal.get('volume_ratio', 1.0),
                'trend_strength': signal.get('trend_strength', 0.5),
                'rsi': signal.get('rsi', 50)
            }
            
            # Calculate ML confidence score (simplified model)
            confidence = self._calculate_ml_confidence(features)
            
            # Adaptive threshold adjustment
            if self.signals_processed > 0 and self.signals_processed % 10 == 0:
                self._adjust_adaptive_threshold()
            
            self.signals_processed += 1
            
            # Apply threshold
            should_take = confidence >= self.adaptive_confidence
            
            if should_take:
                self.logger.debug(f"ML filter PASSED: confidence {confidence:.3f} >= {self.adaptive_confidence:.3f}")
            else:
                self.logger.debug(f"ML filter REJECTED: confidence {confidence:.3f} < {self.adaptive_confidence:.3f}")
            
            return should_take
            
        except Exception as e:
            self.logger.error(f"ML filter error: {e}")
            return True  # Default to accepting signal if ML fails
    
    def _calculate_ml_confidence(self, features: Dict[str, float]) -> float:
        """Calculate ML confidence score (simplified model)"""
        
        try:
            # Simplified ML confidence calculation
            signal_strength = features['signal_strength']
            atr_pct = features['atr_percentage']
            volume_ratio = features['volume_ratio']
            trend_strength = features['trend_strength']
            rsi = features['rsi']
            
            # Base confidence from signal strength
            confidence = signal_strength / 100.0
            
            # Volatility adjustment (lower vol = higher confidence)
            if atr_pct <= 1.0:
                confidence *= 1.1  # Boost for low volatility
            elif atr_pct >= 3.0:
                confidence *= 0.9  # Reduce for high volatility
            
            # Volume confirmation
            if volume_ratio > 1.2:
                confidence *= 1.05
            elif volume_ratio < 0.8:
                confidence *= 0.95
            
            # Trend strength adjustment
            confidence *= (0.9 + trend_strength * 0.2)  # 0.9 to 1.1 multiplier
            
            # RSI extreme levels (good for reversal signals)
            if rsi < 30 or rsi > 70:
                confidence *= 1.05
            
            # Cap confidence between 0 and 1
            return max(0.0, min(1.0, confidence))
            
        except Exception as e:
            self.logger.error(f"ML confidence calculation error: {e}")
            return 0.5  # Default confidence
    
    def _adjust_adaptive_threshold(self):
        """Adjust adaptive confidence threshold based on recent performance"""
        
        # Simple adaptive logic - could be enhanced with actual performance tracking
        if self.signals_processed < 5:  # Too few signals, lower threshold
            self.adaptive_confidence = max(0.5, self.adaptive_confidence - 0.05)
        elif self.signals_processed > 20:  # Too many signals, raise threshold
            self.adaptive_confidence = min(0.8, self.adaptive_confidence + 0.02)
        
        self.logger.debug(f"Adaptive confidence threshold adjusted to {self.adaptive_confidence:.3f}")

async def generate_trading_signals(df: pd.DataFrame, symbol: str, 
                           use_ml_filter: bool = True) -> List[Dict[str, Any]]:
    """
    Generate filtered trading signals for backtesting
    
    Args:
        df: OHLCV DataFrame with technical indicators
        symbol: Trading pair symbol
        use_ml_filter: Apply ML-based signal filtering
    
    Returns:
        List of trading signals with confidence scores
    """
    
    # Generate technical signals
    signal_provider = TechnicalSignalProvider()
    signals = await signal_provider.generate_signals(df, symbol)
    
    if not signals:
        return []
    
    # Apply ML filter if enabled
    if use_ml_filter:
        ml_filter = MLSignalFilter()
        filtered_signals = []
        
        for signal in signals:
            if ml_filter.filter_signal(signal):
                signal['ml_confidence'] = ml_filter._calculate_ml_confidence({
                    'signal_strength': signal.get('signal_strength', 50),
                    'atr_percentage': signal.get('atr_percentage', 1.0),
                    'volume_ratio': signal.get('volume_ratio', 1.0),
                    'trend_strength': signal.get('trend_strength', 0.5),
                    'rsi': signal.get('rsi', 50)
                })
                filtered_signals.append(signal)
        
        return filtered_signals
    
    return signals