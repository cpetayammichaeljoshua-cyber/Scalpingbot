#!/usr/bin/env python3
"""
Advanced Time-Based and Fibonacci Trading Strategy
Combines advanced time theory with Fibonacci retracements/extensions for maximum scalping profitability
- Time-based market session analysis
- Fibonacci golden ratios and extensions
- ML-enhanced trade validation
- Optimized for 3m-1h scalping
"""

import asyncio
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from collections import deque
import time

@dataclass
class AdvancedScalpingSignal:
    """Advanced scalping signal with time and Fibonacci analysis"""
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    signal_strength: float
    leverage: int = 5  # Default leverage, will be dynamically adjusted
    time_session: str = "UNKNOWN"
    fibonacci_level: float = 0.0
    time_confluence: float = 0.0
    fibonacci_confluence: float = 0.0
    ml_prediction: Optional[Dict[str, Any]] = None
    optimal_entry_time: Optional[datetime] = None
    session_volatility: float = 1.0
    fibonacci_extension: float = 0.0
    timestamp: Optional[datetime] = None
    # New fields for dynamic leverage system
    volatility_score: float = 0.0
    recommended_leverage: int = 5
    max_safe_leverage: int = 5
    risk_level: str = "medium"
    leverage_confidence: str = "medium"

class AdvancedTimeFibonacciStrategy:
    """Advanced strategy combining time theory and Fibonacci analysis"""

    def __init__(self, leverage_manager=None):
        self.logger = logging.getLogger(__name__)
        self.leverage_manager = leverage_manager
        
        # Dynamic leverage integration
        self.dynamic_leverage_enabled = leverage_manager is not None
        if self.dynamic_leverage_enabled:
            self.logger.info("🎯 Advanced strategy integrated with dynamic leverage management")

        # Time-based trading windows (UTC)
        self.trading_sessions = {
            'ASIA_EARLY': {'start': 0, 'end': 4, 'volatility': 0.7, 'strength': 0.6},
            'ASIA_MAIN': {'start': 4, 'end': 8, 'volatility': 0.8, 'strength': 0.7},
            'LONDON_OPEN': {'start': 8, 'end': 10, 'volatility': 1.3, 'strength': 0.95},
            'LONDON_MAIN': {'start': 10, 'end': 14, 'volatility': 1.1, 'strength': 0.85},
            'NY_OVERLAP': {'start': 14, 'end': 16, 'volatility': 1.4, 'strength': 1.0},
            'NY_MAIN': {'start': 16, 'end': 20, 'volatility': 1.2, 'strength': 0.9},
            'NY_CLOSE': {'start': 20, 'end': 24, 'volatility': 0.9, 'strength': 0.75}
        }

        # Fibonacci levels for retracements and extensions
        self.fibonacci_retracements = [0.236, 0.382, 0.5, 0.618, 0.786]
        self.fibonacci_extensions = [1.272, 1.414, 1.618, 2.618, 4.236]
        self.golden_ratio = 1.618

        # Time-based confluence factors
        self.time_confluence_factors = {
            'session_strength': 0.3,
            'volatility_optimal': 0.25,
            'news_avoidance': 0.2,
            'trend_continuation': 0.15,
            'volume_confirmation': 0.1
        }

        # Fibonacci confluence factors
        self.fib_confluence_factors = {
            'retracement_accuracy': 0.35,
            'extension_projection': 0.3,
            'golden_ratio_proximity': 0.2,
            'multiple_level_confluence': 0.15
        }

        # ML enhancement parameters - Optimized for balanced signal quality vs quantity
        self.ml_confidence_threshold = 0.68  # Lowered from 0.75 to increase signal frequency
        self.min_signal_strength = 80  # Balanced threshold for more opportunities
        
        # ML Confidence-based filtering bands
        self.ml_confidence_bands = {
            'conservative': {'min': 0.68, 'max': 0.72, 'leverage_multiplier': 0.85, 'signal_bonus': 0},
            'moderate': {'min': 0.72, 'max': 0.80, 'leverage_multiplier': 1.0, 'signal_bonus': 3},
            'aggressive': {'min': 0.80, 'max': 1.0, 'leverage_multiplier': 1.15, 'signal_bonus': 8}
        }
        self.max_trades_per_hour = 5   # Enhanced trade frequency
        self.last_trade_times = {}
        self.hourly_trade_counts = {}  # Track trades per hour per symbol

    def _get_ml_confidence_band(self, confidence: float) -> str:
        """Determine ML confidence band for adaptive signal processing"""
        for band_name, band_data in self.ml_confidence_bands.items():
            if band_data['min'] <= confidence <= band_data['max']:
                return band_name
        return 'conservative'  # Default to conservative for edge cases

    async def analyze_symbol(self, symbol: str, ohlcv_data: Dict[str, List], ml_analyzer=None) -> Optional[AdvancedScalpingSignal]:
        """Analyze symbol with advanced time and Fibonacci theory"""
        try:
            # Check trade throttling limits
            if not self._can_trade_symbol(symbol):
                self.logger.debug(f"⚠️ Trade throttling active for {symbol} - skipping analysis")
                return None

            # Get current time analysis
            time_analysis = self._analyze_time_confluence()

            # Skip if time conditions are poor
            if time_analysis['time_strength'] < 0.6:
                return None

            # Prepare multi-timeframe data
            timeframes = ['3m', '5m', '15m', '1h']
            tf_data = {}

            for tf in timeframes:
                if tf in ohlcv_data and len(ohlcv_data[tf]) >= 100:
                    tf_data[tf] = self._prepare_dataframe(ohlcv_data[tf])

            if len(tf_data) < 3:
                return None

            # Primary analysis on 15m timeframe
            primary_tf = '15m' if '15m' in tf_data else '5m'
            primary_df = tf_data[primary_tf]

            # Calculate Fibonacci levels
            fib_analysis = await self._calculate_fibonacci_levels(primary_df, tf_data)

            if not fib_analysis or fib_analysis['confluence_strength'] < 0.65:
                return None

            # Generate signal with time and Fibonacci confluence
            signal = await self._generate_advanced_signal(
                symbol, primary_df, fib_analysis, time_analysis, ml_analyzer, ohlcv_data
            )

            if signal and signal.signal_strength >= self.min_signal_strength:
                # Record trade time and update counters
                current_time = datetime.now()
                self.last_trade_times[symbol] = current_time
                
                # Add to hourly trade count
                if symbol not in self.hourly_trade_counts:
                    self.hourly_trade_counts[symbol] = deque()
                self.hourly_trade_counts[symbol].append(current_time)
                
                # Log throttling status
                trades_this_hour = len(self.hourly_trade_counts[symbol])
                self.logger.info(f"✅ {symbol}: Trade #{trades_this_hour}/5 this hour, next cooldown: 10min")
                return signal

            return None

        except Exception as e:
            self.logger.error(f"Error analyzing {symbol}: {e}")
            return None

    def _can_trade_symbol(self, symbol: str) -> bool:
        """Check if we can trade this symbol (600-second cooldown + 5 trades/hour limit)"""
        current_time = datetime.now()
        
        # Check 600-second (10-minute) cooldown
        if symbol in self.last_trade_times:
            time_diff = (current_time - self.last_trade_times[symbol]).total_seconds()
            if time_diff < 600:
                remaining = int(600 - time_diff)
                self.logger.info(f"🕐 {symbol}: 10-min cooldown active, {remaining}s remaining")
                return False
        
        # Initialize hourly tracking for new symbols
        if symbol not in self.hourly_trade_counts:
            self.hourly_trade_counts[symbol] = deque()
        
        # Clean old timestamps (remove entries older than 1 hour)
        cutoff_time = current_time - timedelta(hours=1)
        trade_times = self.hourly_trade_counts[symbol]
        while trade_times and trade_times[0] < cutoff_time:
            trade_times.popleft()
        
        # Check max trades per hour limit
        if len(trade_times) >= self.max_trades_per_hour:
            oldest_trade = trade_times[0]
            wait_time = int((oldest_trade + timedelta(hours=1) - current_time).total_seconds())
            self.logger.info(f"📊 {symbol}: Max 5 trades/hour reached, next available in {wait_time}s")
            return False
        
        return True

    def _prepare_dataframe(self, ohlcv: List[List]) -> pd.DataFrame:
        """Prepare OHLCV dataframe"""
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        return df.dropna()

    def _analyze_time_confluence(self) -> Dict[str, Any]:
        """Analyze current time for trading confluence"""
        now = datetime.utcnow()
        hour = now.hour
        minute = now.minute
        day_of_week = now.weekday()

        # Determine current session
        current_session = None
        session_data = None

        for session_name, session_info in self.trading_sessions.items():
            if session_info['start'] <= hour < session_info['end']:
                current_session = session_name
                session_data = session_info
                break

        if not current_session:
            return {'time_strength': 0.0, 'session': 'UNKNOWN'}

        # Calculate time-based strength
        time_strength = session_data['strength']

        # Adjust for high-impact times (market opens, closes, news times)
        if self._is_high_impact_time(hour, minute):
            time_strength *= 1.2  # Boost during high-impact times

        # Adjust for day of week (avoid Fridays after 20:00 UTC, Sundays before 22:00)
        if day_of_week == 4 and hour >= 20:  # Friday evening
            time_strength *= 0.7
        elif day_of_week == 6:  # Sunday
            time_strength *= 0.8

        # Adjust for volatility expectations
        volatility_factor = session_data['volatility']
        if 1.0 <= volatility_factor <= 1.3:  # Optimal volatility range
            time_strength *= 1.1

        return {
            'time_strength': min(time_strength, 1.0),
            'session': current_session,
            'volatility_factor': volatility_factor,
            'is_high_impact': self._is_high_impact_time(hour, minute)
        }

    def _is_high_impact_time(self, hour: int, minute: int) -> bool:
        """Check if current time is high-impact (opens, closes, news)"""
        # Major session opens/closes and common news release times
        high_impact_times = [
            (8, 30), (9, 0),   # London open
            (14, 30), (15, 0), # NY overlap
            (16, 0), (16, 30), # NY open
            (21, 0), (22, 0)   # Major closes
        ]

        return (hour, minute) in high_impact_times or minute in [0, 30]

    async def _calculate_fibonacci_levels(self, df: pd.DataFrame, tf_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Calculate advanced Fibonacci levels and confluence"""
        try:
            # Find significant swing high and low (lookback 50 periods)
            lookback = min(50, len(df))
            recent_data = df.tail(lookback)

            swing_high = recent_data['high'].max()
            swing_low = recent_data['low'].min()
            swing_range = swing_high - swing_low

            if swing_range == 0:
                return None

            current_price = df['close'].iloc[-1]

            # Calculate Fibonacci retracement levels
            fib_levels = {}
            for level in self.fibonacci_retracements:
                fib_levels[f'retracement_{level}'] = swing_high - (swing_range * level)

            # Calculate Fibonacci extension levels
            for level in self.fibonacci_extensions:
                fib_levels[f'extension_{level}'] = swing_high + (swing_range * (level - 1))

            # Find closest Fibonacci level to current price
            closest_level = None
            min_distance = float('inf')

            for level_name, level_price in fib_levels.items():
                distance = abs(current_price - level_price) / current_price
                if distance < min_distance:
                    min_distance = distance
                    closest_level = {'name': level_name, 'price': level_price, 'distance': distance}

            # Calculate Fibonacci confluence strength
            confluence_strength = 0.0

            # Proximity to key Fibonacci level (closer = stronger)
            if closest_level and closest_level['distance'] < 0.005:  # Within 0.5%
                confluence_strength += 0.4
            elif closest_level and closest_level['distance'] < 0.01:  # Within 1%
                confluence_strength += 0.25

            # Golden ratio proximity bonus
            golden_levels = [fib_levels.get('retracement_0.618'), fib_levels.get('extension_1.618')]
            for golden_level in golden_levels:
                if golden_level:
                    golden_distance = abs(current_price - golden_level) / current_price
                    if golden_distance < 0.005:
                        confluence_strength += 0.3

            # Multiple timeframe Fibonacci confluence
            mtf_confluence = await self._check_multi_timeframe_fibonacci(current_price, tf_data)
            confluence_strength += mtf_confluence * 0.3

            # Trend direction confluence with Fibonacci
            trend_direction = self._determine_trend_direction(df)
            if trend_direction != 'sideways':
                confluence_strength += 0.2

            return {
                'swing_high': swing_high,
                'swing_low': swing_low,
                'fib_levels': fib_levels,
                'closest_level': closest_level,
                'confluence_strength': min(confluence_strength, 1.0),
                'trend_direction': trend_direction,
                'current_price': current_price
            }

        except Exception as e:
            self.logger.error(f"Error calculating Fibonacci levels: {e}")
            return None

    async def _check_multi_timeframe_fibonacci(self, current_price: float, tf_data: Dict[str, pd.DataFrame]) -> float:
        """Check Fibonacci confluence across multiple timeframes"""
        confluence_score = 0.0
        timeframes_checked = 0

        for tf, df in tf_data.items():
            if len(df) < 30:
                continue

            try:
                # Calculate Fibonacci for this timeframe
                lookback = min(30, len(df))
                recent_data = df.tail(lookback)

                swing_high = recent_data['high'].max()
                swing_low = recent_data['low'].min()
                swing_range = swing_high - swing_low

                if swing_range == 0:
                    continue

                # Check if current price is near any Fibonacci level
                for level in self.fibonacci_retracements + self.fibonacci_extensions:
                    if level <= 1:  # Retracement
                        fib_price = swing_high - (swing_range * level)
                    else:  # Extension
                        fib_price = swing_high + (swing_range * (level - 1))

                    distance = abs(current_price - fib_price) / current_price
                    if distance < 0.01:  # Within 1%
                        confluence_score += 0.2
                        break

                timeframes_checked += 1

            except Exception:
                continue

        return confluence_score / max(timeframes_checked, 1)

    def _determine_trend_direction(self, df: pd.DataFrame) -> str:
        """Determine trend direction using EMAs"""
        try:
            if len(df) < 50:
                return 'sideways'

            # Calculate EMAs
            ema_9 = df['close'].ewm(span=9).mean()
            ema_21 = df['close'].ewm(span=21).mean()
            ema_50 = df['close'].ewm(span=50).mean()

            current_price = df['close'].iloc[-1]
            current_ema_9 = ema_9.iloc[-1]
            current_ema_21 = ema_21.iloc[-1]
            current_ema_50 = ema_50.iloc[-1]

            # Strong uptrend
            if (current_price > current_ema_9 > current_ema_21 > current_ema_50):
                return 'uptrend'
            # Strong downtrend
            elif (current_price < current_ema_9 < current_ema_21 < current_ema_50):
                return 'downtrend'
            else:
                return 'sideways'

        except Exception:
            return 'sideways'

    def _check_momentum_confirmation(self, df: pd.DataFrame, direction: str) -> Dict[str, Any]:
        """Check momentum confirmation using multiple EMAs and momentum indicators"""
        try:
            if len(df) < 50:
                return {'momentum_confirmed': False, 'momentum_strength': 0.0}

            # Calculate multiple EMAs for momentum analysis
            ema_5 = df['close'].ewm(span=5).mean()
            ema_9 = df['close'].ewm(span=9).mean()
            ema_13 = df['close'].ewm(span=13).mean()
            ema_21 = df['close'].ewm(span=21).mean()
            ema_34 = df['close'].ewm(span=34).mean()

            current_price = df['close'].iloc[-1]
            current_ema_5 = ema_5.iloc[-1]
            current_ema_9 = ema_9.iloc[-1]
            current_ema_13 = ema_13.iloc[-1]
            current_ema_21 = ema_21.iloc[-1]
            current_ema_34 = ema_34.iloc[-1]

            # Calculate EMA slopes (momentum direction)
            ema_5_slope = (ema_5.iloc[-1] - ema_5.iloc[-3]) / ema_5.iloc[-3] * 100
            ema_9_slope = (ema_9.iloc[-1] - ema_9.iloc[-3]) / ema_9.iloc[-3] * 100
            ema_21_slope = (ema_21.iloc[-1] - ema_21.iloc[-5]) / ema_21.iloc[-5] * 100

            momentum_strength = 0.0
            momentum_confirmed = False

            if direction == 'LONG':
                # Check for bullish momentum alignment
                price_above_emas = (current_price > current_ema_5 > current_ema_9 > 
                                  current_ema_13 > current_ema_21)
                ema_slopes_bullish = (ema_5_slope > 0 and ema_9_slope > 0 and ema_21_slope > 0)
                
                # Calculate momentum strength
                if price_above_emas:
                    momentum_strength += 0.4
                if ema_slopes_bullish:
                    momentum_strength += 0.3
                if current_price > current_ema_34:
                    momentum_strength += 0.2
                if ema_5_slope > 0.1:  # Strong recent momentum
                    momentum_strength += 0.1

                momentum_confirmed = momentum_strength >= 0.6

            elif direction == 'SHORT':
                # Check for bearish momentum alignment
                price_below_emas = (current_price < current_ema_5 < current_ema_9 < 
                                  current_ema_13 < current_ema_21)
                ema_slopes_bearish = (ema_5_slope < 0 and ema_9_slope < 0 and ema_21_slope < 0)
                
                # Calculate momentum strength
                if price_below_emas:
                    momentum_strength += 0.4
                if ema_slopes_bearish:
                    momentum_strength += 0.3
                if current_price < current_ema_34:
                    momentum_strength += 0.2
                if ema_5_slope < -0.1:  # Strong recent momentum
                    momentum_strength += 0.1

                momentum_confirmed = momentum_strength >= 0.6

            return {
                'momentum_confirmed': momentum_confirmed,
                'momentum_strength': momentum_strength,
                'ema_5_slope': ema_5_slope,
                'ema_9_slope': ema_9_slope,
                'ema_21_slope': ema_21_slope,
                'price_ema_alignment': True if momentum_confirmed else False
            }

        except Exception as e:
            self.logger.error(f"Error checking momentum confirmation: {e}")
            return {'momentum_confirmed': False, 'momentum_strength': 0.0}

    def _calculate_volume_confirmation(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate volume confirmation bonus for signal strength"""
        try:
            if len(df) < 20:
                return {'volume_confirmed': False, 'volume_strength': 0.0}

            # Calculate volume moving averages
            volume_sma_10 = df['volume'].rolling(window=10).mean()
            volume_sma_20 = df['volume'].rolling(window=20).mean()
            
            current_volume = df['volume'].iloc[-1]
            avg_volume_10 = volume_sma_10.iloc[-1]
            avg_volume_20 = volume_sma_20.iloc[-1]
            
            # Calculate volume strength
            volume_strength = 0.0
            
            # High volume vs recent average
            if current_volume > avg_volume_10 * 1.5:
                volume_strength += 0.4
            elif current_volume > avg_volume_10 * 1.2:
                volume_strength += 0.2
                
            # Volume trend (increasing volume)
            if avg_volume_10 > avg_volume_20 * 1.1:
                volume_strength += 0.3
                
            # Exceptional volume spike
            if current_volume > avg_volume_20 * 2.0:
                volume_strength += 0.3
                
            volume_confirmed = volume_strength >= 0.5
            
            return {
                'volume_confirmed': volume_confirmed,
                'volume_strength': volume_strength,
                'volume_ratio_10': current_volume / avg_volume_10 if avg_volume_10 > 0 else 1.0,
                'volume_ratio_20': current_volume / avg_volume_20 if avg_volume_20 > 0 else 1.0
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating volume confirmation: {e}")
            return {'volume_confirmed': False, 'volume_strength': 0.0}

    async def _generate_advanced_signal(self, symbol: str, df: pd.DataFrame, fib_analysis: Dict[str, Any], 
                                      time_analysis: Dict[str, Any], ml_analyzer=None, 
                                      ohlcv_data: Dict[str, List] = None) -> Optional[AdvancedScalpingSignal]:
        """Generate advanced signal combining time and Fibonacci analysis"""
        try:
            current_price = fib_analysis['current_price']
            trend_direction = fib_analysis['trend_direction']
            closest_fib = fib_analysis['closest_level']

            # Determine trade direction
            direction = None

            if trend_direction == 'uptrend' and closest_fib:
                # Look for long opportunities near Fibonacci support
                if 'retracement' in closest_fib['name'] and closest_fib['distance'] < 0.01:
                    direction = 'LONG'
            elif trend_direction == 'downtrend' and closest_fib:
                # Look for short opportunities near Fibonacci resistance
                if 'retracement' in closest_fib['name'] and closest_fib['distance'] < 0.01:
                    direction = 'SHORT'

            if not direction:
                return None

            # Enhanced momentum confirmation
            momentum_analysis = self._check_momentum_confirmation(df, direction)
            if not momentum_analysis['momentum_confirmed']:
                # Allow some signals through with reduced strength if other factors are very strong
                if (fib_analysis['confluence_strength'] < 0.8 or 
                    time_analysis['time_strength'] < 0.85):
                    return None

            # Volume confirmation analysis
            volume_analysis = self._calculate_volume_confirmation(df)

            # ML validation if available
            ml_prediction = None
            if ml_analyzer:
                signal_data = {
                    'symbol': symbol,
                    'signal_strength': 85,
                    'direction': direction,
                    'current_price': current_price,
                    'fibonacci_level': closest_fib['price'] if closest_fib else current_price,
                    'time_session': time_analysis['session'],
                    'volatility': time_analysis['volatility_factor']
                }
                ml_prediction = ml_analyzer.predict_trade_outcome(signal_data)

                # Skip if ML confidence is too low (now optimized at 68%)
                ml_confidence = ml_prediction.get('confidence', 0) / 100.0  # Convert to decimal
                if ml_confidence < self.ml_confidence_threshold:
                    self.logger.debug(f"❌ {symbol}: ML confidence {ml_confidence*100:.1f}% below threshold {self.ml_confidence_threshold*100:.1f}%")
                    return None
                    
                # Determine ML confidence band for adaptive filtering
                confidence_band = self._get_ml_confidence_band(ml_confidence)
                self.logger.info(f"🧠 {symbol}: ML confidence {ml_confidence*100:.1f}% ({confidence_band} band)")

            # Calculate stop loss and take profits using Fibonacci
            atr = self._calculate_atr(df)

            if direction == 'LONG':
                # Stop loss below closest Fibonacci support
                stop_loss = closest_fib['price'] - (atr * 1.5) if closest_fib else current_price - (atr * 2)

                # Take profits at Fibonacci extension levels
                sl_distance = current_price - stop_loss
                tp1 = current_price + (sl_distance * 1.618)  # Golden ratio
                tp2 = current_price + (sl_distance * 2.618)
                tp3 = current_price + (sl_distance * 4.236)

            else:  # SHORT
                # Stop loss above closest Fibonacci resistance
                stop_loss = closest_fib['price'] + (atr * 1.5) if closest_fib else current_price + (atr * 2)

                # Take profits at Fibonacci extension levels
                sl_distance = stop_loss - current_price
                tp1 = current_price - (sl_distance * 1.618)  # Golden ratio
                tp2 = current_price - (sl_distance * 2.618)
                tp3 = current_price - (sl_distance * 4.236)

            # Calculate signal strength with enhanced factors
            base_strength = 75

            # Enhanced time confluence bonus
            base_strength += time_analysis['time_strength'] * 18

            # Enhanced Fibonacci confluence bonus
            base_strength += fib_analysis['confluence_strength'] * 17

            # Momentum confirmation bonus
            if momentum_analysis['momentum_confirmed']:
                base_strength += momentum_analysis['momentum_strength'] * 12  # Up to 12 points
            else:
                # Penalty for weak momentum (but still allow strong confluences)
                base_strength -= 5

            # Volume confirmation bonus
            if volume_analysis['volume_confirmed']:
                base_strength += volume_analysis['volume_strength'] * 8  # Up to 8 points
                # Extra bonus for exceptional volume spikes
                if volume_analysis.get('volume_ratio_20', 1.0) > 2.0:
                    base_strength += 5
            
            # Enhanced ML prediction bonus with confidence-based weighting
            if ml_prediction and ml_prediction.get('prediction') == 'favorable':
                # Base ML bonus
                base_strength += 12
                if ml_prediction.get('telegram_enhanced'):
                    base_strength += 3  # Telegram learning bonus
                    
                # Confidence band bonus
                confidence_band_data = self.ml_confidence_bands[confidence_band]
                base_strength += confidence_band_data['signal_bonus']

            signal_strength = min(base_strength, 100)

            # Calculate leverage using dynamic leverage manager if available
            leverage_info = await self._calculate_dynamic_leverage(
                symbol, signal_strength, time_analysis, fib_analysis, 
                ml_prediction, ohlcv_data, direction
            )
            
            leverage = leverage_info['recommended_leverage']

            # Create advanced signal with enhanced data
            signal = AdvancedScalpingSignal(
                symbol=symbol,
                direction=direction,
                entry_price=current_price,
                stop_loss=stop_loss,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                signal_strength=signal_strength,
                leverage=leverage,
                volatility_score=leverage_info.get('volatility_score', 0.0),
                recommended_leverage=leverage_info['recommended_leverage'],
                max_safe_leverage=leverage_info.get('max_leverage', leverage),
                risk_level=leverage_info.get('risk_level', 'medium'),
                leverage_confidence=leverage_info.get('confidence', 'medium'),
                time_session=time_analysis['session'],
                fibonacci_level=closest_fib['price'] if closest_fib else 0.0,
                time_confluence=time_analysis['time_strength'],
                fibonacci_confluence=fib_analysis['confluence_strength'],
                ml_prediction={
                    **(ml_prediction or {}),
                    'confidence_value': ml_confidence,
                    'confidence_band': confidence_band,
                    'leverage_multiplier': confidence_band_data['leverage_multiplier'],
                    'momentum_confirmed': momentum_analysis['momentum_confirmed'],
                    'momentum_strength': momentum_analysis['momentum_strength'],
                    'volume_confirmed': volume_analysis['volume_confirmed'],
                    'volume_strength': volume_analysis['volume_strength'],
                    'ema_5_slope': momentum_analysis.get('ema_5_slope', 0),
                    'volume_ratio_20': volume_analysis.get('volume_ratio_20', 1.0)
                },
                optimal_entry_time=datetime.now(),
                session_volatility=time_analysis['volatility_factor'],
                fibonacci_extension=tp3,
                timestamp=datetime.now()
            )

            return signal

        except Exception as e:
            self.logger.error(f"Error generating advanced signal: {e}")
            return None

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range"""
        try:
            if len(df) < period + 1:
                return (df['high'].iloc[-1] - df['low'].iloc[-1])

            high = df['high'].values
            low = df['low'].values
            close = df['close'].values

            tr_list = []
            for i in range(1, len(df)):
                tr1 = high[i] - low[i]
                tr2 = abs(high[i] - close[i-1])
                tr3 = abs(low[i] - close[i-1])
                tr = max(tr1, tr2, tr3)
                tr_list.append(tr)

            if len(tr_list) >= period:
                atr = sum(tr_list[-period:]) / period
            else:
                atr = sum(tr_list) / len(tr_list)

            return atr

        except Exception as e:
            self.logger.error(f"Error calculating ATR: {e}")
            return df['high'].iloc[-1] - df['low'].iloc[-1]

    async def _calculate_dynamic_leverage(self, symbol: str, signal_strength: float,
                                        time_analysis: Dict[str, Any], fib_analysis: Dict[str, Any],
                                        ml_prediction: Optional[Dict[str, Any]], 
                                        ohlcv_data: Dict[str, List],
                                        direction: str) -> Dict[str, Any]:
        """
        Calculate dynamic leverage using the leverage manager or fallback to signal-based calculation
        
        Args:
            symbol: Trading symbol
            signal_strength: Calculated signal strength
            time_analysis: Time-based analysis results
            fib_analysis: Fibonacci analysis results
            ml_prediction: ML prediction results
            ohlcv_data: OHLCV data for volatility calculation
            direction: Trade direction ('LONG' or 'SHORT')
            
        Returns:
            Dictionary with leverage recommendation and analysis
        """
        try:
            # Use dynamic leverage manager if available
            if self.leverage_manager and ohlcv_data:
                # Calculate trade size for leverage optimization (based on $10 capital base)
                capital_base = 10.0  # $10 capital base
                risk_percentage = 5.0  # 5% risk management
                trade_size_usdt = capital_base * (risk_percentage / 100)
                
                leverage_analysis = await self.leverage_manager.get_optimal_leverage_for_trade(
                    symbol, direction, trade_size_usdt, ohlcv_data
                )
                
                # Apply signal strength adjustments to recommended leverage
                recommended_leverage = leverage_analysis['recommended_leverage']
                
                # Boost leverage for very strong signals
                if signal_strength >= 95:
                    recommended_leverage = min(10, int(recommended_leverage * 1.2))
                elif signal_strength >= 90:
                    recommended_leverage = min(9, int(recommended_leverage * 1.1))
                elif signal_strength < 80:
                    # Reduce leverage for weaker signals
                    recommended_leverage = max(2, int(recommended_leverage * 0.9))
                
                # Apply ML confidence adjustments
                if ml_prediction:
                    ml_confidence = ml_prediction.get('confidence', 0) / 100.0
                    if ml_confidence > 0.85:
                        recommended_leverage = min(10, int(recommended_leverage * 1.1))
                    elif ml_confidence < 0.70:
                        recommended_leverage = max(2, int(recommended_leverage * 0.8))
                
                # Apply time and Fibonacci confluence adjustments
                confluence_multiplier = 1.0
                if (time_analysis['time_strength'] > 0.9 and 
                    fib_analysis['confluence_strength'] > 0.85):
                    confluence_multiplier = 1.15  # Premium confluence bonus
                elif (time_analysis['time_strength'] > 0.8 and 
                      fib_analysis['confluence_strength'] > 0.75):
                    confluence_multiplier = 1.05  # Good confluence bonus
                
                recommended_leverage = min(10, max(2, int(recommended_leverage * confluence_multiplier)))
                
                return {
                    'recommended_leverage': recommended_leverage,
                    'max_leverage': leverage_analysis.get('max_leverage', recommended_leverage),
                    'volatility_score': leverage_analysis.get('volatility_score', 'N/A'),
                    'risk_level': leverage_analysis.get('risk_level', 'medium'),
                    'confidence': leverage_analysis.get('confidence', 'medium'),
                    'risk_factors': leverage_analysis.get('risk_factors', []),
                    'analysis_source': 'dynamic_volatility_manager',
                    'signal_strength_adjustment': f"Signal: {signal_strength:.1f}%",
                    'confluence_adjustment': f"Confluence: {confluence_multiplier:.2f}x"
                }
            
            # Fallback to signal-based leverage calculation
            else:
                # Legacy calculation for backward compatibility
                base_leverage = 5  # Conservative default
                
                # Signal strength adjustment
                if signal_strength >= 95:
                    base_leverage = 8
                elif signal_strength >= 90:
                    base_leverage = 7
                elif signal_strength >= 85:
                    base_leverage = 6
                elif signal_strength >= 80:
                    base_leverage = 5
                else:
                    base_leverage = 3
                
                # Time session adjustment
                session_multiplier = 1.0
                current_session = time_analysis.get('session', 'UNKNOWN')
                if current_session in ['NY_OVERLAP', 'LONDON_OPEN']:
                    session_multiplier = 1.2  # Higher leverage during peak sessions
                elif current_session in ['LONDON_MAIN', 'NY_MAIN']:
                    session_multiplier = 1.1
                
                # Fibonacci confluence adjustment
                fib_multiplier = 1.0
                fib_strength = fib_analysis.get('confluence_strength', 0)
                if fib_strength > 0.85:
                    fib_multiplier = 1.15
                elif fib_strength > 0.75:
                    fib_multiplier = 1.05
                
                # ML prediction adjustment
                ml_multiplier = 1.0
                if ml_prediction and ml_prediction.get('prediction') == 'favorable':
                    ml_confidence = ml_prediction.get('confidence', 0) / 100.0
                    if ml_confidence > 0.80:
                        ml_multiplier = 1.1
                    elif ml_confidence < 0.70:
                        ml_multiplier = 0.9
                
                # Calculate final leverage
                final_leverage = int(base_leverage * session_multiplier * fib_multiplier * ml_multiplier)
                final_leverage = max(2, min(10, final_leverage))
                
                return {
                    'recommended_leverage': final_leverage,
                    'max_leverage': final_leverage,
                    'volatility_score': 'N/A (calculated from signal)',
                    'risk_level': 'signal_based',
                    'confidence': 'medium',
                    'risk_factors': ['Using signal-based calculation'],
                    'analysis_source': 'signal_based_fallback',
                    'signal_strength_adjustment': f"Signal: {signal_strength:.1f}%",
                    'confluence_adjustment': f"Combined: {session_multiplier * fib_multiplier * ml_multiplier:.2f}x"
                }
            
        except Exception as e:
            self.logger.error(f"Error calculating dynamic leverage for {symbol}: {e}")
            # Safe fallback
            return {
                'recommended_leverage': 5,
                'max_leverage': 5,
                'volatility_score': 'Error in calculation',
                'risk_level': 'safe_fallback',
                'confidence': 'low',
                'risk_factors': [f'Error: {e}'],
                'analysis_source': 'error_fallback',
                'signal_strength_adjustment': 'Error',
                'confluence_adjustment': 'Error'
            }

    def get_signal_summary(self, signal: AdvancedScalpingSignal) -> Dict[str, Any]:
        """Get comprehensive signal summary with enhanced metrics"""
        ml_data = signal.ml_prediction or {}
        
        return {
            'symbol': signal.symbol,
            'direction': signal.direction,
            'strength': f"{signal.signal_strength:.1f}%",
            'entry': signal.entry_price,
            'stop_loss': signal.stop_loss,
            'take_profits': [signal.tp1, signal.tp2, signal.tp3],
            'leverage': f"{signal.leverage}x",
            'time_session': signal.time_session,
            'fibonacci_level': signal.fibonacci_level,
            'time_confluence': f"{signal.time_confluence:.1f}%",
            'fibonacci_confluence': f"{signal.fibonacci_confluence:.1f}%",
            'momentum_confirmed': ml_data.get('momentum_confirmed', False),
            'momentum_strength': f"{ml_data.get('momentum_strength', 0):.1f}%",
            'volume_confirmed': ml_data.get('volume_confirmed', False),
            'volume_strength': f"{ml_data.get('volume_strength', 0):.1f}%",
            'ema_5_slope': f"{ml_data.get('ema_5_slope', 0):.3f}%",
            'volume_ratio_20': f"{ml_data.get('volume_ratio_20', 1.0):.2f}x",
            'ml_confidence': ml_data.get('confidence', 0),
            'session_volatility': signal.session_volatility,
            'optimal_entry': signal.optimal_entry_time.strftime('%H:%M:%S UTC'),
            'strategy': 'Enhanced Time-Fibonacci w/ Momentum & Volume'
        }