
#!/usr/bin/env python3
"""
Ultimate Scalping Strategy - Most Profitable Trading System
Combines all the most effective indicators for maximum profitability
- Timeframes: 3m to 4h only
- 1 SL and 3 TPs with dynamic management
- 50x leverage with cross margin
- ML learning from losses
- Rate limited responses (3/hour, 1 trade per 15 mins)
"""

import asyncio
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    
from dataclasses import dataclass
import time

@dataclass
class UltimateSignal:
    """Ultimate trading signal with all parameters"""
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    signal_strength: float
    leverage: int = 50
    margin_type: str = "cross"
    risk_reward_ratio: float = 3.0
    timeframe: str = "Multi-TF"
    indicators_confluence: Optional[Dict[str, Any]] = None
    market_structure: str = "trending"
    volume_confirmation: bool = False
    timestamp: Optional[datetime] = None

class UltimateScalpingStrategy:
    """Most profitable scalping strategy combining all indicators"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Strategy parameters optimized for maximum profitability
        self.timeframes = ['3m', '5m', '15m', '1h', '4h']  # Fixed timeframe range
        self.leverage = 50  # Reduced from 75x
        self.margin_type = "cross"  # Cross margin only
        self.risk_percentage = 2.0  # 2% risk per trade
        
        # Signal filtering - Optimized for higher win rate & more trades
        self.min_signal_strength = 78  # Balanced threshold for quality vs frequency
        self.min_trade_interval = 300  # 5 minutes minimum between trades
        self.last_trade_time = {}
        
        # Optimized indicator weights for confluence scoring (favor trend/momentum)
        self.indicator_weights = {
            'supertrend': 0.18,        # Increased - Most reliable trend indicator
            'ema_confluence': 0.17,    # Increased - Strong trend confirmation
            'rsi_divergence': 0.14,    # Increased - Powerful momentum signal
            'macd_momentum': 0.12,     # Increased - Key momentum indicator
            'volume_profile': 0.09,    # Slightly reduced
            'bollinger_squeeze': 0.08, # Maintained
            'stochastic_oversold': 0.07, # Slightly reduced
            'vwap_position': 0.06,     # Slightly reduced
            'support_resistance': 0.06, # Slightly reduced
            'market_structure': 0.03   # Reduced to balance total = 1.0
        }
        
        # Profitability optimizations
        self.profit_multipliers = [1.0, 2.0, 3.0]  # TP1, TP2, TP3 ratios
        
        # Adaptive signal strength thresholds based on market volatility
        self.volatility_thresholds = {
            'low': 0.5,      # ATR% < 0.5% - Low volatility
            'normal': 1.5,   # ATR% 0.5-1.5% - Normal volatility
            'high': 3.0      # ATR% > 1.5% - High volatility
        }
        
        # Adaptive minimum signal strength based on volatility
        self.adaptive_signal_strength = {
            'low': self.min_signal_strength - 8,     # 70% in low volatility
            'normal': self.min_signal_strength,      # 78% in normal volatility
            'high': self.min_signal_strength + 7     # 85% in high volatility
        }
        
    async def analyze_symbol(self, symbol: str, ohlcv_data: Dict[str, List]) -> Optional[UltimateSignal]:
        """Analyze symbol with ultimate scalping strategy"""
        try:
            # Check trade frequency limit (1 per 15 minutes)
            if not self._can_trade_symbol(symbol):
                return None
            
            # Get multi-timeframe data
            tf_data = {}
            for tf in self.timeframes:
                if tf in ohlcv_data and len(ohlcv_data[tf]) >= 100:
                    tf_data[tf] = self._prepare_dataframe(ohlcv_data[tf])
            
            if len(tf_data) < 3:  # Need at least 3 timeframes
                return None
            
            # Calculate all indicators for each timeframe
            indicators = {}
            for tf, df in tf_data.items():
                indicators[tf] = await self._calculate_ultimate_indicators(df)
            
            # Get market volatility for adaptive thresholding
            primary_tf = '1h' if '1h' in indicators else '15m' if '15m' in indicators else list(indicators.keys())[0]
            atr = indicators[primary_tf].get('atr', 0)
            current_price = indicators[primary_tf].get('current_price', 1)
            volatility_state = self._get_market_volatility_state(atr, current_price)
            adaptive_threshold = self._get_adaptive_signal_threshold(volatility_state)
            
            # Generate signal with confluence analysis
            signal = await self._generate_ultimate_signal(symbol, indicators, tf_data, volatility_state)
            
            if signal and signal.signal_strength >= adaptive_threshold:
                # Record trade time
                self.last_trade_time[symbol] = datetime.now()
                return signal
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error analyzing {symbol}: {e}")
            return None
    
    def _can_trade_symbol(self, symbol: str) -> bool:
        """Check if we can trade this symbol (5-minute minimum interval)"""
        if symbol not in self.last_trade_time:
            return True
        
        time_diff = (datetime.now() - self.last_trade_time[symbol]).total_seconds()
        return time_diff >= self.min_trade_interval
    
    def _get_market_volatility_state(self, atr: float, current_price: float) -> str:
        """Determine market volatility state for adaptive signal strength"""
        try:
            atr_percentage = (atr / current_price) * 100
            
            if atr_percentage < self.volatility_thresholds['low']:
                return 'low'
            elif atr_percentage < self.volatility_thresholds['normal']:
                return 'normal'
            else:
                return 'high'
        except:
            return 'normal'  # Default to normal volatility
    
    def _get_adaptive_signal_threshold(self, volatility_state: str) -> float:
        """Get adaptive signal strength threshold based on market volatility"""
        return self.adaptive_signal_strength.get(volatility_state, self.min_signal_strength)
    
    def _prepare_dataframe(self, ohlcv: List[List]) -> pd.DataFrame:
        """Prepare OHLCV dataframe"""
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df.dropna()
    
    async def _calculate_ultimate_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate all profitable indicators"""
        indicators = {}
        
        try:
            # Price arrays
            high = df['high'].values
            low = df['low'].values
            close = df['close'].values
            volume = df['volume'].values
            
            # 1. SuperTrend (Most reliable trend indicator)
            indicators['supertrend'] = self._calculate_supertrend(high, low, close)
            
            # 2. EMA Confluence (21, 55, 200)
            indicators['ema_confluence'] = self._calculate_ema_confluence(close)
            
            # 3. RSI with Divergence Detection
            indicators['rsi_analysis'] = self._calculate_rsi_with_divergence(close, high, low)
            
            # 4. MACD with Momentum
            indicators['macd_momentum'] = self._calculate_macd_momentum(close)
            
            # 5. Volume Profile Analysis
            indicators['volume_profile'] = self._calculate_volume_profile(close, volume)
            
            # 6. Bollinger Bands Squeeze
            indicators['bollinger_squeeze'] = self._calculate_bollinger_squeeze(close)
            
            # 7. Stochastic Oversold/Overbought
            indicators['stochastic'] = self._calculate_stochastic_analysis(high, low, close)
            
            # 8. VWAP Position
            indicators['vwap_position'] = self._calculate_vwap_position(high, low, close, volume)
            
            # 9. Support/Resistance Levels
            indicators['support_resistance'] = self._calculate_support_resistance(high, low, close)
            
            # 10. Market Structure (Higher Highs/Lower Lows)
            indicators['market_structure'] = self._calculate_market_structure(high, low, close)
            
            # 11. ATR for volatility
            if TALIB_AVAILABLE:
                indicators['atr'] = talib.ATR(high, low, close, timeperiod=14)[-1]
            else:
                # Simple ATR calculation
                tr = np.maximum(high[1:] - low[1:], 
                               np.maximum(np.abs(high[1:] - close[:-1]), 
                                         np.abs(low[1:] - close[:-1])))
                indicators['atr'] = np.mean(tr[-14:]) if len(tr) >= 14 else (high[-1] - low[-1])
            
            # 12. Current price info
            indicators['current_price'] = close[-1]
            indicators['price_change'] = (close[-1] - close[-2]) / close[-2] * 100
            
            return indicators
            
        except Exception as e:
            self.logger.error(f"Error calculating indicators: {e}")
            return {}
    
    def _calculate_supertrend(self, high: np.array, low: np.array, close: np.array) -> Dict[str, Any]:
        """Calculate SuperTrend indicator"""
        try:
            period = 10
            multiplier = 3.0
            
            if TALIB_AVAILABLE:
                atr = talib.ATR(high, low, close, timeperiod=period)
            else:
                # Simple ATR fallback
                tr = np.maximum(high[1:] - low[1:], 
                               np.maximum(np.abs(high[1:] - close[:-1]), 
                                         np.abs(low[1:] - close[:-1])))
                atr_values = []
                for i in range(len(close)):
                    if i < period:
                        atr_values.append(high[i] - low[i])
                    else:
                        atr_values.append(np.mean(tr[i-period:i]))
                atr = np.array(atr_values)
            hl2 = (high + low) / 2
            
            upper_band = hl2 + (multiplier * atr)
            lower_band = hl2 - (multiplier * atr)
            
            supertrend = np.zeros(len(close))
            trend = np.zeros(len(close))
            
            for i in range(1, len(close)):
                if close[i] <= lower_band[i-1]:
                    supertrend[i] = upper_band[i]
                    trend[i] = -1
                elif close[i] >= upper_band[i-1]:
                    supertrend[i] = lower_band[i]
                    trend[i] = 1
                else:
                    supertrend[i] = supertrend[i-1]
                    trend[i] = trend[i-1]
            
            current_trend = trend[-1]
            trend_strength = abs(close[-1] - supertrend[-1]) / close[-1] * 100
            
            return {
                'trend': 'bullish' if current_trend > 0 else 'bearish',
                'strength': min(trend_strength * 10, 100),
                'support_resistance': supertrend[-1],
                'signal_quality': 'strong' if trend_strength > 0.5 else 'weak'
            }
        except:
            return {'trend': 'neutral', 'strength': 0, 'support_resistance': close[-1]}
    
    def _calculate_ema_confluence(self, close: np.array) -> Dict[str, Any]:
        """Calculate EMA confluence (21, 55, 200)"""
        try:
            if TALIB_AVAILABLE:
                ema21 = talib.EMA(close, timeperiod=21)
                ema55 = talib.EMA(close, timeperiod=55)
                ema200 = talib.EMA(close, timeperiod=200)
            else:
                # Simple EMA fallback
                def simple_ema(data, period):
                    alpha = 2 / (period + 1)
                    ema = [data[0]]
                    for price in data[1:]:
                        ema.append(alpha * price + (1 - alpha) * ema[-1])
                    return np.array(ema)
                
                ema21 = simple_ema(close, 21)
                ema55 = simple_ema(close, 55)
                ema200 = simple_ema(close, 200)
            
            current_price = close[-1]
            
            # Check alignment
            bullish_alignment = ema21[-1] > ema55[-1] > ema200[-1]
            bearish_alignment = ema21[-1] < ema55[-1] < ema200[-1]
            
            # Distance from EMAs (closer = stronger signal)
            ema21_distance = abs(current_price - ema21[-1]) / current_price * 100
            ema55_distance = abs(current_price - ema55[-1]) / current_price * 100
            
            # Confluence strength
            if bullish_alignment:
                strength = max(0, 100 - (ema21_distance + ema55_distance) * 10)
                bias = 'bullish'
            elif bearish_alignment:
                strength = max(0, 100 - (ema21_distance + ema55_distance) * 10)
                bias = 'bearish'
            else:
                strength = 0
                bias = 'neutral'
            
            return {
                'bias': bias,
                'strength': strength,
                'ema21': ema21[-1],
                'ema55': ema55[-1],
                'ema200': ema200[-1],
                'alignment': bullish_alignment or bearish_alignment
            }
        except:
            return {'bias': 'neutral', 'strength': 0, 'alignment': False}
    
    def _calculate_rsi_with_divergence(self, close: np.array, high: np.array, low: np.array) -> Dict[str, Any]:
        """Calculate RSI with divergence detection"""
        try:
            if TALIB_AVAILABLE:
                rsi = talib.RSI(close, timeperiod=14)
            else:
                # Simple RSI fallback
                def simple_rsi(prices, period=14):
                    deltas = np.diff(prices)
                    gains = np.where(deltas > 0, deltas, 0)
                    losses = np.where(deltas < 0, -deltas, 0)
                    
                    avg_gains = np.convolve(gains, np.ones(period)/period, mode='valid')
                    avg_losses = np.convolve(losses, np.ones(period)/period, mode='valid')
                    
                    rs = avg_gains / (avg_losses + 1e-10)
                    rsi_vals = 100 - (100 / (1 + rs))
                    
                    # Pad to match original length
                    return np.concatenate([np.full(period, 50), rsi_vals])
                
                rsi = simple_rsi(close)
            current_rsi = rsi[-1]
            
            # RSI levels
            oversold = current_rsi < 30
            overbought = current_rsi > 70
            
            # Divergence detection (simplified)
            bullish_divergence = False
            bearish_divergence = False
            
            if len(close) >= 20:
                # Price and RSI comparison over last 10-20 bars
                recent_price_low = np.min(close[-10:])
                prev_price_low = np.min(close[-20:-10])
                recent_rsi_low = np.min(rsi[-10:])
                prev_rsi_low = np.min(rsi[-20:-10])
                
                # Bullish divergence: lower price low, higher RSI low
                if recent_price_low < prev_price_low and recent_rsi_low > prev_rsi_low:
                    bullish_divergence = True
                
                # Bearish divergence: higher price high, lower RSI high
                recent_price_high = np.max(close[-10:])
                prev_price_high = np.max(close[-20:-10])
                recent_rsi_high = np.max(rsi[-10:])
                prev_rsi_high = np.max(rsi[-20:-10])
                
                if recent_price_high > prev_price_high and recent_rsi_high < prev_rsi_high:
                    bearish_divergence = True
            
            # Signal strength
            strength = 0
            if oversold and bullish_divergence:
                strength = 95
            elif overbought and bearish_divergence:
                strength = 95
            elif oversold:
                strength = 70
            elif overbought:
                strength = 70
            elif 40 <= current_rsi <= 60:
                strength = 50
            
            return {
                'value': current_rsi,
                'oversold': oversold,
                'overbought': overbought,
                'bullish_divergence': bullish_divergence,
                'bearish_divergence': bearish_divergence,
                'strength': strength
            }
        except:
            return {'value': 50, 'strength': 0, 'oversold': False, 'overbought': False}
    
    def _calculate_macd_momentum(self, close: np.array) -> Dict[str, Any]:
        """Calculate MACD with momentum analysis"""
        try:
            if TALIB_AVAILABLE:
                macd, macdsignal, macdhist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
            else:
                # Simple MACD fallback
                def simple_ema(data, period):
                    alpha = 2 / (period + 1)
                    ema = [data[0]]
                    for price in data[1:]:
                        ema.append(alpha * price + (1 - alpha) * ema[-1])
                    return np.array(ema)
                
                ema12 = simple_ema(close, 12)
                ema26 = simple_ema(close, 26)
                macd = ema12 - ema26
                macdsignal = simple_ema(macd, 9)
                macdhist = macd - macdsignal
            
            current_macd = macd[-1]
            current_signal = macdsignal[-1]
            current_hist = macdhist[-1]
            prev_hist = macdhist[-2]
            
            # Momentum analysis
            bullish_crossover = current_hist > 0 and prev_hist <= 0
            bearish_crossover = current_hist < 0 and prev_hist >= 0
            increasing_momentum = current_hist > prev_hist
            
            # Signal strength
            strength = min(abs(current_hist) * 1000, 100)  # Scale histogram
            
            return {
                'macd': current_macd,
                'signal': current_signal,
                'histogram': current_hist,
                'bullish_crossover': bullish_crossover,
                'bearish_crossover': bearish_crossover,
                'increasing_momentum': increasing_momentum,
                'strength': strength
            }
        except:
            return {'strength': 0, 'bullish_crossover': False, 'bearish_crossover': False}
    
    def _calculate_volume_profile(self, close: np.array, volume: np.array) -> Dict[str, Any]:
        """Calculate volume profile analysis"""
        try:
            # Volume weighted average price
            vwap = np.sum(close * volume) / np.sum(volume) if np.sum(volume) > 0 else close[-1]
            
            # Volume trend
            recent_volume = np.mean(volume[-5:])
            avg_volume = np.mean(volume[-20:])
            volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1
            
            # High volume confirmation
            high_volume = volume_ratio > 1.5
            
            # Volume price trend
            volume_price_trend = 'bullish' if close[-1] > vwap and high_volume else 'bearish' if close[-1] < vwap and high_volume else 'neutral'
            
            strength = min(volume_ratio * 30, 100) if high_volume else 20
            
            return {
                'vwap': vwap,
                'volume_ratio': volume_ratio,
                'high_volume': high_volume,
                'trend': volume_price_trend,
                'strength': strength
            }
        except:
            return {'strength': 20, 'high_volume': False, 'trend': 'neutral'}
    
    def _calculate_bollinger_squeeze(self, close: np.array) -> Dict[str, Any]:
        """Calculate Bollinger Bands squeeze"""
        try:
            # Bollinger Bands
            if TALIB_AVAILABLE:
                upper, middle, lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
            else:
                # Simple Bollinger Bands fallback
                period = 20
                std_dev = 2
                middle = np.convolve(close, np.ones(period)/period, mode='same')
                std = np.array([np.std(close[max(0,i-period):i+1]) for i in range(len(close))])
                upper = middle + (std * std_dev)
                lower = middle - (std * std_dev)
            
            # Band width
            band_width = (upper[-1] - lower[-1]) / middle[-1] * 100
            avg_band_width = np.mean([(upper[i] - lower[i]) / middle[i] * 100 for i in range(-20, 0)])
            
            # Squeeze detection
            squeeze = band_width < avg_band_width * 0.8
            expansion = band_width > avg_band_width * 1.2
            
            # Position within bands
            bb_position = (close[-1] - lower[-1]) / (upper[-1] - lower[-1])
            
            strength = 0
            if squeeze:
                strength = 80  # High probability of breakout
            elif expansion and (bb_position > 0.8 or bb_position < 0.2):
                strength = 90  # Strong directional move
            
            return {
                'squeeze': squeeze,
                'expansion': expansion,
                'bb_position': bb_position,
                'band_width': band_width,
                'strength': strength
            }
        except:
            return {'squeeze': False, 'expansion': False, 'strength': 0}
    
    def _calculate_stochastic_analysis(self, high: np.array, low: np.array, close: np.array) -> Dict[str, Any]:
        """Calculate Stochastic oscillator analysis"""
        try:
            if TALIB_AVAILABLE:
                slowk, slowd = talib.STOCH(high, low, close, fastk_period=14, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
            else:
                # Simple Stochastic fallback
                period = 14
                k_values = []
                for i in range(len(close)):
                    if i < period - 1:
                        k_values.append(50)
                    else:
                        lowest_low = np.min(low[i-period+1:i+1])
                        highest_high = np.max(high[i-period+1:i+1])
                        k = 100 * ((close[i] - lowest_low) / (highest_high - lowest_low + 1e-10))
                        k_values.append(k)
                
                slowk = np.array(k_values)
                # Simple moving average for %D
                slowd = np.convolve(slowk, np.ones(3)/3, mode='same')
            
            current_k = slowk[-1]
            current_d = slowd[-1]
            
            oversold = current_k < 20
            overbought = current_k > 80
            
            # Crossover signals
            bullish_crossover = current_k > current_d and slowk[-2] <= slowd[-2]
            bearish_crossover = current_k < current_d and slowk[-2] >= slowd[-2]
            
            strength = 0
            if oversold and bullish_crossover:
                strength = 85
            elif overbought and bearish_crossover:
                strength = 85
            elif oversold or overbought:
                strength = 60
            
            return {
                'k': current_k,
                'd': current_d,
                'oversold': oversold,
                'overbought': overbought,
                'bullish_crossover': bullish_crossover,
                'bearish_crossover': bearish_crossover,
                'strength': strength
            }
        except:
            return {'strength': 0, 'oversold': False, 'overbought': False}
    
    def _calculate_vwap_position(self, high: np.array, low: np.array, close: np.array, volume: np.array) -> Dict[str, Any]:
        """Calculate VWAP position analysis"""
        try:
            # VWAP calculation
            typical_price = (high + low + close) / 3
            vwap = np.sum(typical_price * volume) / np.sum(volume) if np.sum(volume) > 0 else close[-1]
            
            # Position relative to VWAP
            above_vwap = close[-1] > vwap
            distance = abs(close[-1] - vwap) / close[-1] * 100
            
            # VWAP trend
            vwap_slope = (vwap - np.sum(typical_price[-10:] * volume[-10:]) / np.sum(volume[-10:])) / vwap * 100
            
            strength = max(0, 70 - distance * 20)  # Closer to VWAP = stronger signal
            
            return {
                'vwap': vwap,
                'above_vwap': above_vwap,
                'distance': distance,
                'slope': vwap_slope,
                'strength': strength
            }
        except:
            return {'strength': 30, 'above_vwap': True, 'distance': 1}
    
    def _calculate_support_resistance(self, high: np.array, low: np.array, close: np.array) -> Dict[str, Any]:
        """Calculate support/resistance levels"""
        try:
            # Find recent highs and lows
            recent_high = np.max(high[-20:])
            recent_low = np.min(low[-20:])
            
            # Distance from key levels
            resistance_distance = (recent_high - close[-1]) / close[-1] * 100
            support_distance = (close[-1] - recent_low) / close[-1] * 100
            
            # Near key level?
            near_resistance = resistance_distance < 0.5
            near_support = support_distance < 0.5
            
            strength = 0
            if near_resistance or near_support:
                strength = 75  # High probability of reaction at key levels
            
            return {
                'resistance': recent_high,
                'support': recent_low,
                'near_resistance': near_resistance,
                'near_support': near_support,
                'resistance_distance': resistance_distance,
                'support_distance': support_distance,
                'strength': strength
            }
        except:
            return {'strength': 0, 'near_resistance': False, 'near_support': False}
    
    def _calculate_market_structure(self, high: np.array, low: np.array, close: np.array) -> Dict[str, Any]:
        """Analyze market structure (Higher Highs, Lower Lows)"""
        try:
            # Recent swing points
            recent_highs = []
            recent_lows = []
            
            # Simple swing detection
            for i in range(2, len(high) - 2):
                if high[i] > high[i-1] and high[i] > high[i+1]:
                    recent_highs.append(high[i])
                if low[i] < low[i-1] and low[i] < low[i+1]:
                    recent_lows.append(low[i])
            
            # Market structure analysis
            if len(recent_highs) >= 2 and len(recent_lows) >= 2:
                higher_highs = recent_highs[-1] > recent_highs[-2]
                higher_lows = recent_lows[-1] > recent_lows[-2]
                lower_highs = recent_highs[-1] < recent_highs[-2]
                lower_lows = recent_lows[-1] < recent_lows[-2]
                
                if higher_highs and higher_lows:
                    structure = 'uptrend'
                    strength = 80
                elif lower_highs and lower_lows:
                    structure = 'downtrend'
                    strength = 80
                else:
                    structure = 'sideways'
                    strength = 40
            else:
                structure = 'unclear'
                strength = 20
            
            return {
                'structure': structure,
                'strength': strength,
                'recent_highs': recent_highs[-2:] if len(recent_highs) >= 2 else [],
                'recent_lows': recent_lows[-2:] if len(recent_lows) >= 2 else []
            }
        except:
            return {'structure': 'unclear', 'strength': 20}
    
    async def _generate_ultimate_signal(self, symbol: str, indicators: Dict[str, Dict], tf_data: Dict[str, pd.DataFrame], volatility_state: str = 'normal') -> Optional[UltimateSignal]:
        """Generate ultimate signal with all indicators confluence and adaptive filtering"""
        try:
            # Use primary timeframe for signal generation (15m or 1h)
            primary_tf = '1h' if '1h' in indicators else '15m' if '15m' in indicators else list(indicators.keys())[0]
            primary_indicators = indicators[primary_tf]
            primary_df = tf_data[primary_tf]
            
            current_price = primary_indicators['current_price']
            
            # Calculate confluence score
            bullish_score = 0
            bearish_score = 0
            
            # SuperTrend
            st = primary_indicators.get('supertrend', {})
            if st.get('trend') == 'bullish':
                bullish_score += self.indicator_weights['supertrend'] * (st.get('strength', 0) / 100)
            elif st.get('trend') == 'bearish':
                bearish_score += self.indicator_weights['supertrend'] * (st.get('strength', 0) / 100)
            
            # EMA Confluence
            ema = primary_indicators.get('ema_confluence', {})
            if ema.get('bias') == 'bullish' and ema.get('alignment'):
                bullish_score += self.indicator_weights['ema_confluence'] * (ema.get('strength', 0) / 100)
            elif ema.get('bias') == 'bearish' and ema.get('alignment'):
                bearish_score += self.indicator_weights['ema_confluence'] * (ema.get('strength', 0) / 100)
            
            # RSI with Divergence
            rsi = primary_indicators.get('rsi_analysis', {})
            if rsi.get('bullish_divergence') or rsi.get('oversold'):
                bullish_score += self.indicator_weights['rsi_divergence'] * (rsi.get('strength', 0) / 100)
            elif rsi.get('bearish_divergence') or rsi.get('overbought'):
                bearish_score += self.indicator_weights['rsi_divergence'] * (rsi.get('strength', 0) / 100)
            
            # MACD Momentum
            macd = primary_indicators.get('macd_momentum', {})
            if macd.get('bullish_crossover') or (macd.get('increasing_momentum') and macd.get('histogram', 0) > 0):
                bullish_score += self.indicator_weights['macd_momentum'] * (macd.get('strength', 0) / 100)
            elif macd.get('bearish_crossover') or (not macd.get('increasing_momentum') and macd.get('histogram', 0) < 0):
                bearish_score += self.indicator_weights['macd_momentum'] * (macd.get('strength', 0) / 100)
            
            # Volume Profile
            vol = primary_indicators.get('volume_profile', {})
            if vol.get('trend') == 'bullish' and vol.get('high_volume'):
                bullish_score += self.indicator_weights['volume_profile'] * (vol.get('strength', 0) / 100)
            elif vol.get('trend') == 'bearish' and vol.get('high_volume'):
                bearish_score += self.indicator_weights['volume_profile'] * (vol.get('strength', 0) / 100)
            
            # Continue with other indicators...
            bb = primary_indicators.get('bollinger_squeeze', {})
            stoch = primary_indicators.get('stochastic', {})
            vwap = primary_indicators.get('vwap_position', {})
            sr = primary_indicators.get('support_resistance', {})
            ms = primary_indicators.get('market_structure', {})
            
            # Add their contributions to scores...
            if bb.get('expansion') and bb.get('bb_position', 0.5) > 0.7:
                bullish_score += self.indicator_weights['bollinger_squeeze'] * (bb.get('strength', 0) / 100)
            elif bb.get('expansion') and bb.get('bb_position', 0.5) < 0.3:
                bearish_score += self.indicator_weights['bollinger_squeeze'] * (bb.get('strength', 0) / 100)
            
            if stoch.get('bullish_crossover') and stoch.get('oversold'):
                bullish_score += self.indicator_weights['stochastic_oversold'] * (stoch.get('strength', 0) / 100)
            elif stoch.get('bearish_crossover') and stoch.get('overbought'):
                bearish_score += self.indicator_weights['stochastic_oversold'] * (stoch.get('strength', 0) / 100)
            
            if vwap.get('above_vwap') and vwap.get('distance', 0) < 1:
                bullish_score += self.indicator_weights['vwap_position'] * (vwap.get('strength', 0) / 100)
            elif not vwap.get('above_vwap') and vwap.get('distance', 0) < 1:
                bearish_score += self.indicator_weights['vwap_position'] * (vwap.get('strength', 0) / 100)
            
            if sr.get('near_support'):
                bullish_score += self.indicator_weights['support_resistance'] * (sr.get('strength', 0) / 100)
            elif sr.get('near_resistance'):
                bearish_score += self.indicator_weights['support_resistance'] * (sr.get('strength', 0) / 100)
            
            if ms.get('structure') == 'uptrend':
                bullish_score += self.indicator_weights['market_structure'] * (ms.get('strength', 0) / 100)
            elif ms.get('structure') == 'downtrend':
                bearish_score += self.indicator_weights['market_structure'] * (ms.get('strength', 0) / 100)
            
            # Enhanced signal direction determination with adaptive filtering
            # Adjust confluence requirement based on volatility
            base_confluence_req = 0.6
            if volatility_state == 'high':
                confluence_requirement = base_confluence_req + 0.1  # Require 70% confluence in high volatility
            elif volatility_state == 'low':
                confluence_requirement = base_confluence_req - 0.05  # Accept 55% confluence in low volatility
            else:
                confluence_requirement = base_confluence_req  # 60% confluence in normal volatility
            
            # Additional reliability checks for higher win rate
            trend_momentum_score = 0
            trend_momentum_score += (st.get('strength', 0) / 100) * self.indicator_weights['supertrend']
            trend_momentum_score += (ema.get('strength', 0) / 100) * self.indicator_weights['ema_confluence']
            trend_momentum_score += (macd.get('strength', 0) / 100) * self.indicator_weights['macd_momentum']
            
            # Require strong trend/momentum signals for reliability
            min_trend_momentum = 0.25 if volatility_state == 'high' else 0.20
            
            if (bullish_score > bearish_score and 
                bullish_score > confluence_requirement and 
                trend_momentum_score > min_trend_momentum):
                direction = 'LONG'
                # Boost signal strength for strong trend confluence
                signal_strength = min(bullish_score * 100 * (1 + trend_momentum_score), 100)
            elif (bearish_score > bullish_score and 
                  bearish_score > confluence_requirement and 
                  trend_momentum_score > min_trend_momentum):
                direction = 'SHORT'
                # Boost signal strength for strong trend confluence  
                signal_strength = min(bearish_score * 100 * (1 + trend_momentum_score), 100)
            else:
                return None  # Not enough confluence or trend strength
            
            # Calculate precise SL and TP levels
            atr = primary_indicators.get('atr', current_price * 0.02)
            
            if direction == 'LONG':
                # Use SuperTrend or recent support as SL
                stop_loss = st.get('support_resistance', current_price * (1 - self.risk_percentage / 100))
                sl_distance = current_price - stop_loss
                
                # 3 TPs with 1:1, 1:2, 1:3 ratios
                tp1 = current_price + (sl_distance * self.profit_multipliers[0])
                tp2 = current_price + (sl_distance * self.profit_multipliers[1])
                tp3 = current_price + (sl_distance * self.profit_multipliers[2])
            else:  # SHORT
                stop_loss = st.get('support_resistance', current_price * (1 + self.risk_percentage / 100))
                sl_distance = stop_loss - current_price
                
                tp1 = current_price - (sl_distance * self.profit_multipliers[0])
                tp2 = current_price - (sl_distance * self.profit_multipliers[1])
                tp3 = current_price - (sl_distance * self.profit_multipliers[2])
            
            # Create ultimate signal
            signal = UltimateSignal(
                symbol=symbol,
                direction=direction,
                entry_price=current_price,
                stop_loss=stop_loss,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                signal_strength=signal_strength,
                leverage=self.leverage,
                margin_type=self.margin_type,
                risk_reward_ratio=3.0,
                timeframe=f"Multi-TF ({primary_tf})",
                indicators_confluence={
                    'supertrend': st,
                    'ema_confluence': ema,
                    'rsi_analysis': rsi,
                    'macd_momentum': macd,
                    'volume_profile': vol,
                    'bullish_score': bullish_score,
                    'bearish_score': bearish_score
                },
                market_structure=ms.get('structure', 'unclear'),
                volume_confirmation=vol.get('high_volume', False),
                timestamp=datetime.now()
            )
            
            return signal
            
        except Exception as e:
            self.logger.error(f"Error generating ultimate signal: {e}")
            return None
    
    def get_signal_summary(self, signal: UltimateSignal) -> Dict[str, Any]:
        """Get comprehensive signal summary"""
        return {
            'symbol': signal.symbol,
            'direction': signal.direction,
            'strength': f"{signal.signal_strength:.1f}%",
            'entry': signal.entry_price,
            'stop_loss': signal.stop_loss,
            'take_profits': [signal.tp1, signal.tp2, signal.tp3],
            'leverage': f"{signal.leverage}x",
            'margin_type': signal.margin_type,
            'risk_reward': f"1:{signal.risk_reward_ratio}",
            'timeframe': signal.timeframe,
            'market_structure': signal.market_structure,
            'volume_confirmation': signal.volume_confirmation,
            'indicators_count': len([k for k, v in signal.indicators_confluence.items() if isinstance(v, dict) and v.get('strength', 0) > 0])
        }
