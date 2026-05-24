#!/usr/bin/env python3
"""
Momentum Scalping Strategy - Ultra-Fast RSI Divergence & MACD Crossover System
Specialized for rapid momentum capture with ultra-tight risk management
- Timeframes: 1m, 3m, 5m for lightning-fast scalping
- RSI divergence detection with peak/trough analysis
- MACD crossover momentum with histogram analysis
- Multi-EMA momentum confirmation (5,13,21)
- 6-10 trades/hour capability with 30-180 second holds
- Dynamic leverage 15-40x based on momentum strength
- Target 0.5-2% moves with 1:1.5 to 1:3 risk/reward
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

try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False

@dataclass
class MomentumScalpingSignal:
    """Momentum scalping signal with ultra-fast execution parameters"""
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    signal_strength: float
    leverage: int = 25
    margin_type: str = "cross"
    risk_reward_ratio: float = 2.0
    timeframe: str = "Multi-TF"
    
    # Momentum-specific attributes
    rsi_divergence_type: str = "none"
    rsi_divergence_strength: float = 0.0
    macd_crossover_type: str = "none" 
    macd_momentum_score: float = 0.0
    ema_alignment_strength: float = 0.0
    price_velocity: float = 0.0
    momentum_confluence: int = 0
    volume_confirmation: bool = False
    
    # Scalping-specific attributes
    expected_hold_seconds: int = 90
    momentum_phase: str = "building"
    divergence_bars_back: int = 0
    crossover_bars_back: int = 0
    velocity_percentile: float = 0.0
    
    timestamp: Optional[datetime] = None

class MomentumScalpingStrategy:
    """Ultra-fast momentum scalping strategy with RSI divergence and MACD crossovers"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Ultra-fast scalping parameters
        self.timeframes = ['1m', '3m', '5m']  # Lightning-fast timeframes
        self.max_leverage = 40  # Maximum leverage for strongest momentum
        self.min_leverage = 15  # Conservative leverage for weak momentum
        self.margin_type = "cross"
        self.risk_percentage = 0.8  # Ultra-tight risk for fast scalping
        
        # High-frequency momentum trading limits
        self.max_trades_per_hour = 10  # Peak momentum frequency
        self.min_trade_interval = 30   # 30 second minimum cooldown
        self.last_trade_times = {}
        self.hourly_trade_counts = {}
        
        # RSI divergence parameters
        self.rsi_period = 14
        self.rsi_divergence_lookback = 25  # Bars to analyze for divergence
        self.min_divergence_strength = 65  # Minimum divergence confidence
        self.rsi_overbought = 70
        self.rsi_oversold = 30
        
        # MACD parameters optimized for scalping
        self.macd_fast = 8   # Faster for scalping (vs standard 12)
        self.macd_slow = 21  # Faster for scalping (vs standard 26)
        self.macd_signal = 6 # Faster for scalping (vs standard 9)
        
        # EMA periods for momentum analysis
        self.ema_periods = [5, 13, 21]  # Fast momentum EMAs
        self.momentum_ema_weight = 0.3  # Weight for EMA alignment
        
        # Signal strength weighting optimized for momentum
        self.momentum_weights = {
            'rsi_divergence': 0.30,        # Primary momentum signal
            'macd_crossover': 0.25,        # Trend change confirmation
            'ema_momentum': 0.20,          # Multi-timeframe momentum
            'price_velocity': 0.15,        # Speed of price movement
            'volume_confirmation': 0.10    # Volume backing
        }
        
        # Minimum signal strength for ultra-fast entry
        self.min_signal_strength = 72  # Balanced for speed vs quality
        
        # Scalping-specific risk management
        self.tight_stop_loss_pct = [0.5, 0.8, 1.2]  # Ultra-tight stops
        self.quick_target_ratios = [1.5, 2.0, 2.5]  # Fast profit ratios
        
        # Price velocity parameters
        self.velocity_periods = [3, 5, 8]  # Short-term velocity calculation
        self.min_velocity_percentile = 60  # Minimum velocity strength
        
        # Volume confirmation parameters
        self.volume_ma_period = 10
        self.min_volume_ratio = 1.2  # 120% of average volume
        
    async def analyze_symbol(self, symbol: str, ohlcv_data: Dict[str, List]) -> Optional[MomentumScalpingSignal]:
        """Analyze symbol for momentum scalping opportunities"""
        try:
            # Check ultra-fast trading limits
            if not self._can_trade_symbol(symbol):
                return None
            
            # Prepare ultra-fast timeframe data
            tf_data = {}
            for tf in self.timeframes:
                if tf in ohlcv_data and len(ohlcv_data[tf]) >= 50:
                    tf_data[tf] = self._prepare_dataframe(ohlcv_data[tf])
            
            if len(tf_data) < 2:  # Need at least 2 timeframes
                return None
            
            # Primary analysis on 3m timeframe for balance of speed and stability
            primary_tf = '3m' if '3m' in tf_data else '1m' if '1m' in tf_data else '5m'
            primary_df = tf_data[primary_tf]
            
            # Core momentum analysis
            momentum_analysis = await self._calculate_momentum_indicators(primary_df, tf_data)
            
            if not momentum_analysis:
                return None
            
            # RSI divergence detection
            rsi_analysis = await self._detect_rsi_divergence(primary_df)
            
            # MACD crossover analysis 
            macd_analysis = await self._analyze_macd_crossovers(primary_df)
            
            # Multi-EMA momentum alignment
            ema_analysis = await self._calculate_ema_momentum(primary_df, tf_data)
            
            # Price velocity calculation
            velocity_analysis = await self._calculate_price_velocity(primary_df)
            
            # Volume confirmation
            volume_analysis = await self._validate_volume_momentum(primary_df)
            
            # Generate momentum scalping signal
            signal = await self._generate_momentum_signal(
                symbol, primary_df, rsi_analysis, macd_analysis, 
                ema_analysis, velocity_analysis, volume_analysis
            )
            
            if signal and signal.signal_strength >= self.min_signal_strength:
                # Record ultra-fast trade timing
                current_time = datetime.now()
                self.last_trade_times[symbol] = current_time
                
                # Update high-frequency counter
                if symbol not in self.hourly_trade_counts:
                    self.hourly_trade_counts[symbol] = deque()
                self.hourly_trade_counts[symbol].append(current_time)
                
                # Log momentum signal details
                self.logger.info(f"⚡ Momentum Scalping Signal: {symbol} | "
                               f"RSI Div: {signal.rsi_divergence_type} ({signal.rsi_divergence_strength:.1f}%) | "
                               f"MACD: {signal.macd_crossover_type} | "
                               f"EMA: {signal.ema_alignment_strength:.1f}% | "
                               f"Velocity: {signal.velocity_percentile:.1f}% | "
                               f"Strength: {signal.signal_strength:.1f}%")
                
                return signal
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error analyzing {symbol} for momentum scalping: {e}")
            return None
    
    def _can_trade_symbol(self, symbol: str) -> bool:
        """Check ultra-fast trading limits (10/hour, 30s cooldown)"""
        current_time = datetime.now()
        
        # Check 30-second ultra-fast cooldown
        if symbol in self.last_trade_times:
            time_diff = (current_time - self.last_trade_times[symbol]).total_seconds()
            if time_diff < self.min_trade_interval:
                remaining = int(self.min_trade_interval - time_diff)
                self.logger.debug(f"⚡ {symbol}: 30s cooldown active, {remaining}s remaining")
                return False
        
        # Initialize high-frequency tracking
        if symbol not in self.hourly_trade_counts:
            self.hourly_trade_counts[symbol] = deque()
        
        # Clean old timestamps (older than 1 hour)
        cutoff_time = current_time - timedelta(hours=1)
        trade_times = self.hourly_trade_counts[symbol]
        while trade_times and trade_times[0] < cutoff_time:
            trade_times.popleft()
        
        # Check high-frequency limit
        if len(trade_times) >= self.max_trades_per_hour:
            oldest_trade = trade_times[0]
            wait_time = int((oldest_trade + timedelta(hours=1) - current_time).total_seconds())
            self.logger.debug(f"⚡ {symbol}: Max 10 momentum trades/hour reached, next in {wait_time}s")
            return False
        
        return True
    
    def _prepare_dataframe(self, ohlcv: List[List]) -> pd.DataFrame:
        """Prepare OHLCV dataframe for ultra-fast analysis"""
        df = pd.DataFrame(ohlcv)
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df.dropna()
    
    async def _calculate_momentum_indicators(self, df: pd.DataFrame, tf_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Calculate core momentum indicators for all timeframes"""
        try:
            momentum_data = {}
            
            # Calculate for each timeframe
            for tf, tf_df in tf_data.items():
                if len(tf_df) < max(self.ema_periods):
                    continue
                    
                close = np.array(tf_df['close'].values, dtype=np.float64)
                high = np.array(tf_df['high'].values, dtype=np.float64)
                low = np.array(tf_df['low'].values, dtype=np.float64)
                volume = np.array(tf_df['volume'].values, dtype=np.float64)
                
                # RSI calculation
                if TALIB_AVAILABLE:
                    import talib
                    rsi = talib.RSI(close, timeperiod=self.rsi_period)
                else:
                    rsi = self._calculate_rsi_fallback(close, self.rsi_period)
                
                # MACD calculation
                if TALIB_AVAILABLE:
                    import talib
                    macd, macdsignal, macdhist = talib.MACD(close, 
                                                           fastperiod=self.macd_fast,
                                                           slowperiod=self.macd_slow, 
                                                           signalperiod=self.macd_signal)
                else:
                    macd, macdsignal, macdhist = self._calculate_macd_fallback(close)
                
                # EMAs calculation
                emas = {}
                for period in self.ema_periods:
                    if TALIB_AVAILABLE:
                        import talib
                        emas[f'ema_{period}'] = talib.EMA(close, timeperiod=period)
                    else:
                        emas[f'ema_{period}'] = self._calculate_ema_fallback(close, period)
                
                momentum_data[tf] = {
                    'rsi': rsi,
                    'macd': macd,
                    'macd_signal': macdsignal,
                    'macd_histogram': macdhist,
                    'emas': emas,
                    'close': close,
                    'high': high,
                    'low': low,
                    'volume': volume
                }
            
            return momentum_data
            
        except Exception as e:
            self.logger.error(f"Error calculating momentum indicators: {e}")
            return {}
    
    async def _detect_rsi_divergence(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Detect RSI divergence patterns with enhanced precision"""
        try:
            close = np.array(df['close'].values, dtype=np.float64)
            high = np.array(df['high'].values, dtype=np.float64)
            low = np.array(df['low'].values, dtype=np.float64)
            
            if TALIB_AVAILABLE:
                import talib
                rsi = talib.RSI(close, timeperiod=self.rsi_period)
            else:
                rsi = self._calculate_rsi_fallback(close, self.rsi_period)
            
            if len(rsi) < self.rsi_divergence_lookback:
                return {'type': 'none', 'strength': 0, 'bars_back': 0}
            
            # Find recent swing points in price and RSI
            price_peaks, price_troughs = self._find_swing_points(close, high, low)
            rsi_peaks, rsi_troughs = self._find_swing_points(rsi, rsi, rsi)
            
            # Bullish divergence detection
            bullish_div = self._detect_bullish_divergence(
                close, rsi, price_troughs, rsi_troughs
            )
            
            # Bearish divergence detection  
            bearish_div = self._detect_bearish_divergence(
                close, rsi, price_peaks, rsi_peaks
            )
            
            # Determine strongest divergence
            if bullish_div['strength'] > bearish_div['strength']:
                return {
                    'type': 'bullish',
                    'strength': bullish_div['strength'],
                    'bars_back': bullish_div['bars_back'],
                    'rsi_level': rsi[-1] if len(rsi) > 0 else 50
                }
            elif bearish_div['strength'] > 0:
                return {
                    'type': 'bearish', 
                    'strength': bearish_div['strength'],
                    'bars_back': bearish_div['bars_back'],
                    'rsi_level': rsi[-1] if len(rsi) > 0 else 50
                }
            else:
                return {
                    'type': 'none',
                    'strength': 0,
                    'bars_back': 0,
                    'rsi_level': rsi[-1] if len(rsi) > 0 else 50
                }
                
        except Exception as e:
            self.logger.error(f"Error detecting RSI divergence: {e}")
            return {'type': 'none', 'strength': 0, 'bars_back': 0}
    
    def _find_swing_points(self, close: np.ndarray, high: np.ndarray, low: np.ndarray) -> Tuple[List, List]:
        """Find swing high and low points for divergence analysis"""
        try:
            peaks = []
            troughs = []
            lookback = 3  # Minimum bars each side for swing point
            
            for i in range(lookback, len(close) - lookback):
                # Peak detection (highest high in window)
                is_peak = True
                for j in range(i - lookback, i + lookback + 1):
                    if j != i and high[j] >= high[i]:
                        is_peak = False
                        break
                if is_peak:
                    peaks.append({'index': i, 'value': high[i]})
                
                # Trough detection (lowest low in window)
                is_trough = True  
                for j in range(i - lookback, i + lookback + 1):
                    if j != i and low[j] <= low[i]:
                        is_trough = False
                        break
                if is_trough:
                    troughs.append({'index': i, 'value': low[i]})
            
            return peaks[-10:], troughs[-10:]  # Keep last 10 of each
            
        except Exception as e:
            self.logger.error(f"Error finding swing points: {e}")
            return [], []
    
    def _detect_bullish_divergence(self, close: np.ndarray, rsi: np.ndarray, 
                                   price_troughs: List, rsi_troughs: List) -> Dict[str, Any]:
        """Detect bullish divergence between price and RSI"""
        try:
            if len(price_troughs) < 2 or len(rsi_troughs) < 2:
                return {'strength': 0, 'bars_back': 0}
            
            # Get two most recent troughs
            recent_price_trough = price_troughs[-1]
            prev_price_trough = price_troughs[-2]
            
            recent_rsi_trough = min(rsi_troughs, key=lambda x: abs(x['index'] - recent_price_trough['index']))
            prev_rsi_trough = min(rsi_troughs, key=lambda x: abs(x['index'] - prev_price_trough['index']))
            
            # Check for bullish divergence pattern
            price_lower = recent_price_trough['value'] < prev_price_trough['value']
            rsi_higher = recent_rsi_trough['value'] > prev_rsi_trough['value']
            
            if price_lower and rsi_higher:
                # Calculate divergence strength
                price_diff = abs(recent_price_trough['value'] - prev_price_trough['value'])
                price_pct_diff = (price_diff / prev_price_trough['value']) * 100
                
                rsi_diff = abs(recent_rsi_trough['value'] - prev_rsi_trough['value'])
                
                # Strength based on magnitude of divergence
                strength = min(90, (price_pct_diff * 20) + (rsi_diff * 2))
                
                # Additional strength if RSI is oversold
                if recent_rsi_trough['value'] < self.rsi_oversold:
                    strength += 15
                
                bars_back = len(close) - recent_price_trough['index']
                
                return {'strength': strength, 'bars_back': bars_back}
            
            return {'strength': 0, 'bars_back': 0}
            
        except Exception as e:
            self.logger.error(f"Error detecting bullish divergence: {e}")
            return {'strength': 0, 'bars_back': 0}
    
    def _detect_bearish_divergence(self, close: np.ndarray, rsi: np.ndarray,
                                   price_peaks: List, rsi_peaks: List) -> Dict[str, Any]:
        """Detect bearish divergence between price and RSI"""
        try:
            if len(price_peaks) < 2 or len(rsi_peaks) < 2:
                return {'strength': 0, 'bars_back': 0}
            
            # Get two most recent peaks
            recent_price_peak = price_peaks[-1]
            prev_price_peak = price_peaks[-2]
            
            recent_rsi_peak = min(rsi_peaks, key=lambda x: abs(x['index'] - recent_price_peak['index']))
            prev_rsi_peak = min(rsi_peaks, key=lambda x: abs(x['index'] - prev_price_peak['index']))
            
            # Check for bearish divergence pattern
            price_higher = recent_price_peak['value'] > prev_price_peak['value']
            rsi_lower = recent_rsi_peak['value'] < prev_rsi_peak['value']
            
            if price_higher and rsi_lower:
                # Calculate divergence strength
                price_diff = abs(recent_price_peak['value'] - prev_price_peak['value'])
                price_pct_diff = (price_diff / prev_price_peak['value']) * 100
                
                rsi_diff = abs(recent_rsi_peak['value'] - prev_rsi_peak['value'])
                
                # Strength based on magnitude of divergence
                strength = min(90, (price_pct_diff * 20) + (rsi_diff * 2))
                
                # Additional strength if RSI is overbought
                if recent_rsi_peak['value'] > self.rsi_overbought:
                    strength += 15
                
                bars_back = len(close) - recent_price_peak['index']
                
                return {'strength': strength, 'bars_back': bars_back}
            
            return {'strength': 0, 'bars_back': 0}
            
        except Exception as e:
            self.logger.error(f"Error detecting bearish divergence: {e}")
            return {'strength': 0, 'bars_back': 0}
    
    async def _analyze_macd_crossovers(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze MACD crossovers and momentum for scalping signals"""
        try:
            close = np.array(df['close'].values, dtype=np.float64)
            
            if TALIB_AVAILABLE:
                import talib
                macd, macd_signal, macd_hist = talib.MACD(close,
                                                         fastperiod=self.macd_fast,
                                                         slowperiod=self.macd_slow,
                                                         signalperiod=self.macd_signal)
            else:
                macd, macd_signal, macd_hist = self._calculate_macd_fallback(close)
            
            if len(macd) < 10:
                return {'type': 'none', 'momentum_score': 0, 'bars_back': 0}
            
            # Recent crossover detection
            crossover_type = 'none'
            bars_back = 0
            momentum_score = 0
            
            # Check for recent crossovers (within last 5 bars)
            for i in range(1, min(6, len(macd))):
                idx = -i
                prev_idx = -(i+1)
                
                if len(macd) > abs(prev_idx) and not np.isnan(macd[idx]) and not np.isnan(macd_signal[idx]):
                    # Bullish crossover: MACD crosses above signal
                    if macd[prev_idx] <= macd_signal[prev_idx] and macd[idx] > macd_signal[idx]:
                        crossover_type = 'bullish'
                        bars_back = i
                        break
                    # Bearish crossover: MACD crosses below signal  
                    elif macd[prev_idx] >= macd_signal[prev_idx] and macd[idx] < macd_signal[idx]:
                        crossover_type = 'bearish'
                        bars_back = i
                        break
            
            # Calculate momentum score
            if crossover_type != 'none':
                # Histogram momentum (acceleration/deceleration)
                hist_momentum = 0
                if len(macd_hist) >= 3:
                    recent_hist = macd_hist[-3:]
                    hist_trend = np.polyfit(range(len(recent_hist)), recent_hist, 1)[0]
                    hist_momentum = abs(hist_trend) * 100
                
                # Distance from zero line (strength indicator)
                macd_distance = abs(macd[-1]) / (close[-1] * 0.01)  # Normalize to price
                
                # Signal line separation (momentum strength)
                signal_separation = abs(macd[-1] - macd_signal[-1]) / (close[-1] * 0.01)
                
                # Combined momentum score
                momentum_score = min(95, hist_momentum * 0.4 + macd_distance * 0.3 + signal_separation * 0.3)
                
                # Bonus for fresh crossover
                if bars_back <= 2:
                    momentum_score += 10
                    
                # Bonus for zero line position
                if crossover_type == 'bullish' and macd[-1] > 0:
                    momentum_score += 5
                elif crossover_type == 'bearish' and macd[-1] < 0:
                    momentum_score += 5
            
            return {
                'type': crossover_type,
                'momentum_score': momentum_score,
                'bars_back': bars_back,
                'macd_value': macd[-1] if len(macd) > 0 else 0,
                'signal_value': macd_signal[-1] if len(macd_signal) > 0 else 0,
                'histogram_value': macd_hist[-1] if len(macd_hist) > 0 else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing MACD crossovers: {e}")
            return {'type': 'none', 'momentum_score': 0, 'bars_back': 0}
    
    async def _calculate_ema_momentum(self, df: pd.DataFrame, tf_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Calculate multi-EMA momentum alignment across timeframes"""
        try:
            ema_analysis = {}
            
            for tf, tf_df in tf_data.items():
                if len(tf_df) < max(self.ema_periods):
                    continue
                    
                close = tf_df['close'].values
                emas = {}
                
                # Calculate EMAs
                for period in self.ema_periods:
                    if TALIB_AVAILABLE:
                        import talib
                        emas[period] = talib.EMA(np.array(close, dtype=np.float64), timeperiod=period)
                    else:
                        emas[period] = self._calculate_ema_fallback(np.array(close, dtype=np.float64), period)
                
                # Check alignment
                current_price = close[-1]
                ema_values = [emas[period][-1] for period in self.ema_periods if len(emas[period]) > 0]
                
                if len(ema_values) >= 3:
                    # Bullish alignment: price > EMA5 > EMA13 > EMA21
                    bullish_alignment = (current_price > ema_values[0] > ema_values[1] > ema_values[2])
                    # Bearish alignment: price < EMA5 < EMA13 < EMA21
                    bearish_alignment = (current_price < ema_values[0] < ema_values[1] < ema_values[2])
                    
                    # Calculate alignment strength
                    if bullish_alignment:
                        # Distance between EMAs (tighter = stronger trend)
                        spacing = [(ema_values[i] - ema_values[i+1]) / current_price * 100 
                                  for i in range(len(ema_values)-1)]
                        alignment_strength = max(0, 100 - sum(spacing) * 50)
                        bias = 'bullish'
                    elif bearish_alignment:
                        spacing = [(ema_values[i+1] - ema_values[i]) / current_price * 100 
                                  for i in range(len(ema_values)-1)]
                        alignment_strength = max(0, 100 - sum(spacing) * 50)
                        bias = 'bearish'
                    else:
                        alignment_strength = 0
                        bias = 'neutral'
                    
                    ema_analysis[tf] = {
                        'bias': bias,
                        'strength': alignment_strength,
                        'ema_values': ema_values,
                        'current_price': current_price
                    }
            
            # Aggregate multi-timeframe EMA momentum
            if not ema_analysis:
                return {'alignment_strength': 0, 'bias': 'neutral', 'confluence': 0}
            
            # Calculate confluence (how many timeframes agree)
            bullish_count = sum(1 for tf in ema_analysis.values() if tf['bias'] == 'bullish')
            bearish_count = sum(1 for tf in ema_analysis.values() if tf['bias'] == 'bearish')
            total_tfs = len(ema_analysis)
            
            if bullish_count > bearish_count:
                overall_bias = 'bullish'
                confluence = bullish_count / total_tfs * 100
                avg_strength = np.mean([tf['strength'] for tf in ema_analysis.values() 
                                      if tf['bias'] == 'bullish'])
            elif bearish_count > bullish_count:
                overall_bias = 'bearish' 
                confluence = bearish_count / total_tfs * 100
                avg_strength = np.mean([tf['strength'] for tf in ema_analysis.values()
                                      if tf['bias'] == 'bearish'])
            else:
                overall_bias = 'neutral'
                confluence = 0
                avg_strength = 0
            
            return {
                'alignment_strength': avg_strength,
                'bias': overall_bias,
                'confluence': confluence,
                'timeframe_details': ema_analysis
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating EMA momentum: {e}")
            return {'alignment_strength': 0, 'bias': 'neutral', 'confluence': 0}
    
    async def _calculate_price_velocity(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate price velocity and momentum strength"""
        try:
            close = np.array(df['close'].values, dtype=np.float64)
            
            if len(close) < max(self.velocity_periods):
                return {'velocity': 0, 'percentile': 0, 'acceleration': 0}
            
            # Calculate velocity over different periods
            velocities = []
            for period in self.velocity_periods:
                if len(close) >= period + 1:
                    price_change = (close[-1] - close[-period-1]) / close[-period-1]
                    velocity = price_change / period  # Price change per bar
                    velocities.append(abs(velocity))
            
            if not velocities:
                return {'velocity': 0, 'percentile': 0, 'acceleration': 0}
            
            # Average velocity
            avg_velocity = np.mean(velocities)
            
            # Calculate percentile rank of current velocity vs historical
            historical_velocities = []
            for i in range(max(self.velocity_periods), len(close)):
                for period in self.velocity_periods:
                    price_change = (close[i] - close[i-period]) / close[i-period]
                    historical_velocities.append(abs(price_change / period))
            
            if historical_velocities:
                percentile = (np.sum(np.array(historical_velocities) <= avg_velocity) / 
                             len(historical_velocities)) * 100
            else:
                percentile = 50
            
            # Calculate acceleration (change in velocity)
            acceleration = 0
            if len(close) >= 10:
                recent_velocity = (close[-1] - close[-4]) / close[-4] / 3  # 3-bar velocity
                prev_velocity = (close[-4] - close[-7]) / close[-7] / 3    # Previous 3-bar velocity
                acceleration = recent_velocity - prev_velocity
            
            return {
                'velocity': avg_velocity * 100,  # Convert to percentage
                'percentile': percentile,
                'acceleration': acceleration * 100
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating price velocity: {e}")
            return {'velocity': 0, 'percentile': 0, 'acceleration': 0}
    
    async def _validate_volume_momentum(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate volume backing for momentum signals"""
        try:
            volume = np.array(df['volume'].values, dtype=np.float64)
            
            if len(volume) < self.volume_ma_period:
                return {'confirmed': False, 'ratio': 1.0, 'trend': 'neutral'}
            
            # Calculate volume moving average
            volume_ma = float(np.mean(volume[-self.volume_ma_period:]))
            current_volume = float(volume[-1])
            volume_ratio = current_volume / volume_ma if volume_ma > 0 else 1.0
            
            # Volume trend over last few bars
            if len(volume) >= 5:
                volume_trend = float(np.polyfit(range(5), volume[-5:], 1)[0])
                if volume_trend > 0:
                    trend = 'increasing'
                elif volume_trend < 0:
                    trend = 'decreasing'
                else:
                    trend = 'neutral'
            else:
                trend = 'neutral'
            
            # Volume confirmation
            confirmed = (volume_ratio >= self.min_volume_ratio and 
                        trend in ['increasing', 'neutral'])
            
            return {
                'confirmed': confirmed,
                'ratio': volume_ratio,
                'trend': trend,
                'current_volume': current_volume,
                'average_volume': volume_ma
            }
            
        except Exception as e:
            self.logger.error(f"Error validating volume momentum: {e}")
            return {'confirmed': False, 'ratio': 1.0, 'trend': 'neutral'}
    
    async def _generate_momentum_signal(self, symbol: str, df: pd.DataFrame, 
                                       rsi_analysis: Dict, macd_analysis: Dict,
                                       ema_analysis: Dict, velocity_analysis: Dict,
                                       volume_analysis: Dict) -> Optional[MomentumScalpingSignal]:
        """Generate momentum scalping signal with all confluence factors"""
        try:
            close = np.array(df['close'].values, dtype=np.float64)
            current_price = close[-1]
            
            # Determine signal direction
            signal_direction = None
            
            # Primary signals: RSI divergence and MACD crossover
            rsi_bullish = rsi_analysis.get('type') == 'bullish'
            rsi_bearish = rsi_analysis.get('type') == 'bearish'
            macd_bullish = macd_analysis.get('type') == 'bullish'
            macd_bearish = macd_analysis.get('type') == 'bearish'
            
            # EMA momentum confirmation
            ema_bullish = ema_analysis.get('bias') == 'bullish'
            ema_bearish = ema_analysis.get('bias') == 'bearish'
            
            # Signal direction logic
            if (rsi_bullish and macd_bullish) or (rsi_bullish and ema_bullish) or (macd_bullish and ema_bullish):
                signal_direction = 'BUY'
            elif (rsi_bearish and macd_bearish) or (rsi_bearish and ema_bearish) or (macd_bearish and ema_bearish):
                signal_direction = 'SELL'
            
            if not signal_direction:
                return None
            
            # Calculate signal strength
            signal_strength = 0
            
            # RSI divergence weight
            if rsi_analysis.get('type') != 'none':
                signal_strength += (rsi_analysis.get('strength', 0) * 
                                   self.momentum_weights['rsi_divergence'])
            
            # MACD crossover weight
            if macd_analysis.get('type') != 'none':
                signal_strength += (macd_analysis.get('momentum_score', 0) * 
                                   self.momentum_weights['macd_crossover'])
            
            # EMA momentum weight
            signal_strength += (ema_analysis.get('alignment_strength', 0) * 
                               self.momentum_weights['ema_momentum'])
            
            # Price velocity weight
            velocity_score = min(100, velocity_analysis.get('percentile', 0))
            signal_strength += (velocity_score * self.momentum_weights['price_velocity'])
            
            # Volume confirmation weight
            if volume_analysis.get('confirmed', False):
                volume_score = min(100, (volume_analysis.get('ratio', 1) - 1) * 100)
                signal_strength += (volume_score * self.momentum_weights['volume_confirmation'])
            
            if signal_strength < self.min_signal_strength:
                return None
            
            # Calculate dynamic leverage based on signal strength
            leverage_ratio = (signal_strength - self.min_signal_strength) / (95 - self.min_signal_strength)
            dynamic_leverage = int(self.min_leverage + 
                                 (self.max_leverage - self.min_leverage) * leverage_ratio)
            
            # Calculate ultra-tight risk management
            atr = self._calculate_simple_atr(np.array(df['high'].values, dtype=np.float64), 
                                           np.array(df['low'].values, dtype=np.float64), close)
            atr_pct = (atr / current_price) * 100
            
            # Select stop loss based on volatility
            if atr_pct < 0.5:
                sl_pct = self.tight_stop_loss_pct[0]  # 0.5%
            elif atr_pct < 1.0:
                sl_pct = self.tight_stop_loss_pct[1]  # 0.8%
            else:
                sl_pct = self.tight_stop_loss_pct[2]  # 1.2%
            
            # Calculate prices
            if signal_direction == 'BUY':
                stop_loss = current_price * (1 - sl_pct / 100)
                tp1 = current_price * (1 + sl_pct * self.quick_target_ratios[0] / 100)
                tp2 = current_price * (1 + sl_pct * self.quick_target_ratios[1] / 100)
                tp3 = current_price * (1 + sl_pct * self.quick_target_ratios[2] / 100)
            else:  # SELL
                stop_loss = current_price * (1 + sl_pct / 100)
                tp1 = current_price * (1 - sl_pct * self.quick_target_ratios[0] / 100)
                tp2 = current_price * (1 - sl_pct * self.quick_target_ratios[1] / 100)
                tp3 = current_price * (1 - sl_pct * self.quick_target_ratios[2] / 100)
            
            # Calculate expected hold time
            velocity_percentile = velocity_analysis.get('percentile', 50)
            if velocity_percentile > 80:
                expected_hold = 60  # 1 minute for very fast moves
            elif velocity_percentile > 60:
                expected_hold = 90  # 1.5 minutes for fast moves
            else:
                expected_hold = 120  # 2 minutes for normal moves
            
            # Count momentum confluence
            confluence_count = sum([
                1 if rsi_analysis.get('type') != 'none' else 0,
                1 if macd_analysis.get('type') != 'none' else 0,
                1 if ema_analysis.get('bias') != 'neutral' else 0,
                1 if velocity_analysis.get('percentile', 0) > self.min_velocity_percentile else 0,
                1 if volume_analysis.get('confirmed', False) else 0
            ])
            
            return MomentumScalpingSignal(
                symbol=symbol,
                direction=signal_direction,
                entry_price=current_price,
                stop_loss=stop_loss,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                signal_strength=signal_strength,
                leverage=dynamic_leverage,
                margin_type=self.margin_type,
                risk_reward_ratio=self.quick_target_ratios[1],
                timeframe="Multi-TF",
                
                # Momentum-specific attributes
                rsi_divergence_type=rsi_analysis.get('type', 'none'),
                rsi_divergence_strength=rsi_analysis.get('strength', 0),
                macd_crossover_type=macd_analysis.get('type', 'none'),
                macd_momentum_score=macd_analysis.get('momentum_score', 0),
                ema_alignment_strength=ema_analysis.get('alignment_strength', 0),
                price_velocity=velocity_analysis.get('velocity', 0),
                momentum_confluence=confluence_count,
                volume_confirmation=volume_analysis.get('confirmed', False),
                
                # Scalping-specific attributes
                expected_hold_seconds=expected_hold,
                momentum_phase='building' if signal_strength < 80 else 'strong',
                divergence_bars_back=rsi_analysis.get('bars_back', 0),
                crossover_bars_back=macd_analysis.get('bars_back', 0),
                velocity_percentile=velocity_analysis.get('percentile', 0),
                
                timestamp=datetime.now()
            )
            
        except Exception as e:
            self.logger.error(f"Error generating momentum signal: {e}")
            return None
    
    def _calculate_simple_atr(self, high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
        """Calculate simple Average True Range"""
        try:
            if len(high) < period + 1:
                return (high[-1] - low[-1])
            
            true_ranges = []
            for i in range(1, len(high)):
                tr1 = high[i] - low[i]
                tr2 = abs(high[i] - close[i-1])
                tr3 = abs(low[i] - close[i-1])
                true_ranges.append(max(tr1, tr2, tr3))
            
            return float(np.mean(true_ranges[-period:]))
            
        except Exception as e:
            self.logger.error(f"Error calculating ATR: {e}")
            return high[-1] - low[-1] if len(high) > 0 else 0
    
    def _calculate_rsi_fallback(self, close: np.ndarray, period: int = 14) -> np.ndarray:
        """Fallback RSI calculation when talib is not available"""
        try:
            deltas = np.diff(close)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            
            avg_gains = np.convolve(gains, np.ones(period)/period, mode='valid')
            avg_losses = np.convolve(losses, np.ones(period)/period, mode='valid')
            
            rs = avg_gains / (avg_losses + 1e-10)
            rsi = 100 - (100 / (1 + rs))
            
            # Pad to match original length
            return np.concatenate([np.full(period, 50), rsi])
            
        except Exception as e:
            self.logger.error(f"Error calculating RSI fallback: {e}")
            return np.full(len(close), 50)
    
    def _calculate_macd_fallback(self, close: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Fallback MACD calculation when talib is not available"""
        try:
            # Calculate EMAs
            ema_fast = self._calculate_ema_fallback(close, self.macd_fast)
            ema_slow = self._calculate_ema_fallback(close, self.macd_slow)
            
            # MACD line
            macd = ema_fast - ema_slow
            
            # Signal line
            macd_signal = self._calculate_ema_fallback(macd, self.macd_signal)
            
            # Histogram
            macd_histogram = macd - macd_signal
            
            return macd, macd_signal, macd_histogram
            
        except Exception as e:
            self.logger.error(f"Error calculating MACD fallback: {e}")
            return np.zeros(len(close)), np.zeros(len(close)), np.zeros(len(close))
    
    def _calculate_ema_fallback(self, data: np.ndarray, period: int) -> np.ndarray:
        """Fallback EMA calculation when talib is not available"""
        try:
            alpha = 2 / (period + 1)
            ema = [data[0]]
            
            for price in data[1:]:
                ema.append(alpha * price + (1 - alpha) * ema[-1])
            
            return np.array(ema)
            
        except Exception as e:
            self.logger.error(f"Error calculating EMA fallback: {e}")
            return np.copy(data)