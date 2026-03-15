#!/usr/bin/env python3
"""
ATAS Integrated Analyzer
Comprehensive technical indicator analysis compatible with ATAS platform
Analyzes all major trading indicators for signal generation
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

def _normalize_ohlcv(data):
    """Normalize OHLCV data (handle 5 or 6 columns)"""
    if isinstance(data, list):
        if not data or len(data) == 0:
            return None
        first = data[0] if isinstance(data[0], (list, tuple)) else None
        col_count = len(first) if first else 5
        
        if col_count == 6:
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df = df.drop('timestamp', axis=1)
        else:
            df = pd.DataFrame(data, columns=['open', 'high', 'low', 'close', 'volume'])
        return df
    elif isinstance(data, pd.DataFrame):
        if 'timestamp' in data.columns:
            data = data.drop('timestamp', axis=1)
        return data
    return None

@dataclass
class ATASIndicatorSignal:
    """ATAS indicator signal"""
    timestamp: str
    indicator_name: str
    value: float
    signal: str
    strength: float
    confidence: float
    description: str

class ATASIntegratedAnalyzer:
    """Comprehensive technical indicator analysis using ATAS methodology"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.min_bars = 100
    
    async def analyze_all_indicators(self, ohlcv_data) -> Dict[str, Any]:
        """Analyze all ATAS indicators in parallel"""
        try:
            df = _normalize_ohlcv(ohlcv_data)
            if df is None or len(df) < self.min_bars:
                return {'error': 'Insufficient data'}
            
            results = {
                'timestamp': pd.Timestamp.now().isoformat(),
                'indicators': {}
            }
            
            # Analyze all indicators
            results['indicators']['moving_averages'] = await self.analyze_moving_averages(df)
            results['indicators']['rsi'] = await self.analyze_rsi(df)
            results['indicators']['macd'] = await self.analyze_macd(df)
            results['indicators']['bollinger_bands'] = await self.analyze_bollinger_bands(df)
            results['indicators']['stochastic'] = await self.analyze_stochastic(df)
            results['indicators']['atr'] = await self.analyze_atr(df)
            results['indicators']['adx'] = await self.analyze_adx(df)
            results['indicators']['vpt'] = await self.analyze_volume_price_trend(df)
            results['indicators']['obv'] = await self.analyze_obv(df)
            results['indicators']['accumulation_distribution'] = await self.analyze_accumulation_distribution(df)
            results['indicators']['keltner_channel'] = await self.analyze_keltner_channel(df)
            results['indicators']['pivot_points'] = await self.analyze_pivot_points(df)
            results['indicators']['supertrend'] = await self.analyze_supertrend(df)
            results['indicators']['vwap'] = await self.analyze_vwap(df)
            results['indicators']['ichimoku'] = await self.analyze_ichimoku_extended(df)
            
            # Calculate composite signal
            results['composite_signal'] = self._calculate_composite_signal(results['indicators'])
            results['overall_strength'] = self._calculate_overall_strength(results['indicators'])
            
            return results
        except Exception as e:
            self.logger.error(f"ATAS analysis error: {e}")
            return {'error': str(e)}
    
    async def analyze_moving_averages(self, df: pd.DataFrame) -> Dict[str, Any]:
        """SMA, EMA, WMA analysis"""
        try:
            close = df['close'].values
            sma_20 = float(np.mean(close[-20:]))
            sma_50 = float(np.mean(close[-50:]))
            sma_200 = float(np.mean(close[-200:])) if len(close) >= 200 else float(np.mean(close))
            current = float(close[-1])
            signal = 'BUY' if current > sma_20 > sma_50 > sma_200 else ('SELL' if current < sma_20 < sma_50 < sma_200 else 'NEUTRAL')
            return {'sma_20': sma_20, 'sma_50': sma_50, 'sma_200': sma_200, 'current_price': current, 'signal': signal, 'strength': 75.0 if signal != 'NEUTRAL' else 50.0}
        except Exception as e:
            self.logger.debug(f"MA error: {e}")
            return {'signal': 'NEUTRAL', 'strength': 0}
    
    async def analyze_rsi(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Relative Strength Index"""
        try:
            close = df['close'].values[-50:]
            deltas = np.diff(close)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = float(np.mean(gains))
            avg_loss = float(np.mean(losses))
            rs = avg_gain / avg_loss if avg_loss > 0 else 0
            rsi = 100 - (100 / (1 + rs)) if rs >= 0 else 0
            signal = 'BUY' if rsi < 30 else ('SELL' if rsi > 70 else 'NEUTRAL')
            return {'rsi': float(rsi), 'signal': signal, 'strength': float(abs(rsi - 50) / 50 * 100)}
        except Exception as e:
            self.logger.debug(f"RSI error: {e}")
            return {'signal': 'NEUTRAL', 'strength': 0}
    
    async def analyze_macd(self, df: pd.DataFrame) -> Dict[str, Any]:
        """MACD Analysis"""
        try:
            close = df['close'].values
            exp1 = pd.Series(close).ewm(span=12).mean().values
            exp2 = pd.Series(close).ewm(span=26).mean().values
            macd = exp1 - exp2
            signal_line = pd.Series(macd).ewm(span=9).mean().values
            histogram = macd - signal_line
            current_macd = float(macd[-1])
            current_signal = float(signal_line[-1])
            current_hist = float(histogram[-1])
            signal = 'BUY' if current_hist > 0 and macd[-2] <= signal_line[-2] else ('SELL' if current_hist < 0 and macd[-2] >= signal_line[-2] else 'NEUTRAL')
            return {'macd': current_macd, 'signal_line': current_signal, 'histogram': current_hist, 'signal': signal, 'strength': float(abs(current_hist) * 100)}
        except Exception as e:
            self.logger.debug(f"MACD error: {e}")
            return {'signal': 'NEUTRAL', 'strength': 0}
    
    async def analyze_bollinger_bands(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Bollinger Bands Analysis"""
        try:
            close = df['close'].values[-50:]
            sma = np.mean(close)
            std = np.std(close)
            upper = float(sma + 2 * std)
            lower = float(sma - 2 * std)
            current = float(close[-1])
            signal = 'BUY' if current < lower else ('SELL' if current > upper else 'NEUTRAL')
            return {'upper': upper, 'middle': float(sma), 'lower': lower, 'signal': signal, 'strength': 70.0 if signal != 'NEUTRAL' else 40.0}
        except Exception as e:
            self.logger.debug(f"BB error: {e}")
            return {'signal': 'NEUTRAL', 'strength': 0}
    
    async def analyze_stochastic(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Stochastic Oscillator"""
        try:
            close = df['close'].values[-14:]
            high14 = np.max(close)
            low14 = np.min(close)
            current = float(close[-1])
            k_percent = float(((current - low14) / (high14 - low14)) * 100) if high14 != low14 else 50.0
            signal = 'BUY' if k_percent < 20 else ('SELL' if k_percent > 80 else 'NEUTRAL')
            return {'k_percent': k_percent, 'signal': signal, 'strength': float(abs(k_percent - 50) / 50 * 100)}
        except Exception as e:
            self.logger.debug(f"Stochastic error: {e}")
            return {'signal': 'NEUTRAL', 'strength': 0}
    
    async def analyze_atr(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Average True Range"""
        try:
            high = df['high'].values[-14:]
            low = df['low'].values[-14:]
            close = df['close'].values[-14:]
            tr = np.maximum(high[1:] - low[1:], np.maximum(abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])))
            atr = float(np.mean(tr))
            return {'atr': atr, 'signal': 'NEUTRAL', 'strength': 60.0}
        except Exception as e:
            self.logger.debug(f"ATR error: {e}")
            return {'signal': 'NEUTRAL', 'strength': 0}
    
    async def analyze_adx(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Average Directional Index"""
        try:
            high = df['high'].values
            low = df['low'].values
            up_moves = high[1:] - high[:-1]
            down_moves = low[:-1] - low[1:]
            plus_dm = np.where((up_moves > down_moves) & (up_moves > 0), up_moves, 0)
            minus_dm = np.where((down_moves > up_moves) & (down_moves > 0), down_moves, 0)
            tr = np.maximum(high[1:] - low[1:], np.maximum(abs(high[1:] - df['close'].values[:-1]), abs(low[1:] - df['close'].values[:-1])))
            atr = np.mean(tr[-14:])
            di_plus = float(np.mean(plus_dm[-14:]) / atr * 100) if atr > 0 else 0
            di_minus = float(np.mean(minus_dm[-14:]) / atr * 100) if atr > 0 else 0
            adx = float(abs(di_plus - di_minus) / (di_plus + di_minus) * 100) if (di_plus + di_minus) > 0 else 0
            signal = 'BUY' if di_plus > di_minus and adx > 25 else ('SELL' if di_minus > di_plus and adx > 25 else 'NEUTRAL')
            return {'adx': adx, 'di_plus': di_plus, 'di_minus': di_minus, 'signal': signal, 'strength': float(adx)}
        except Exception as e:
            self.logger.debug(f"ADX error: {e}")
            return {'signal': 'NEUTRAL', 'strength': 0}
    
    async def analyze_volume_price_trend(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Volume Price Trend"""
        try:
            close = df['close'].values
            volume = df['volume'].values
            returns = np.diff(close) / close[:-1]
            vpt = np.sum(returns * volume[:-1])
            signal = 'BUY' if vpt > 0 else ('SELL' if vpt < 0 else 'NEUTRAL')
            return {'vpt': float(vpt), 'signal': signal, 'strength': 65.0}
        except Exception as e:
            self.logger.debug(f"VPT error: {e}")
            return {'signal': 'NEUTRAL', 'strength': 0}
    
    async def analyze_obv(self, df: pd.DataFrame) -> Dict[str, Any]:
        """On Balance Volume"""
        try:
            close = df['close'].values
            volume = df['volume'].values
            obv = np.zeros_like(close)
            obv[0] = volume[0]
            for i in range(1, len(close)):
                if close[i] > close[i-1]:
                    obv[i] = obv[i-1] + volume[i]
                elif close[i] < close[i-1]:
                    obv[i] = obv[i-1] - volume[i]
                else:
                    obv[i] = obv[i-1]
            current_obv = float(obv[-1])
            prev_obv = float(obv[-20])
            signal = 'BUY' if current_obv > prev_obv else ('SELL' if current_obv < prev_obv else 'NEUTRAL')
            return {'obv': current_obv, 'signal': signal, 'strength': 60.0 if signal != 'NEUTRAL' else 30.0}
        except Exception as e:
            self.logger.debug(f"OBV error: {e}")
            return {'signal': 'NEUTRAL', 'strength': 0}
    
    async def analyze_accumulation_distribution(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Accumulation/Distribution Line"""
        try:
            high = df['high'].values
            low = df['low'].values
            close = df['close'].values
            volume = df['volume'].values
            ad_line = np.zeros_like(close)
            for i in range(len(close)):
                hl_range = high[i] - low[i]
                clv = ((close[i] - low[i]) - (high[i] - close[i])) / hl_range if hl_range > 0 else 0
                ad_line[i] = ad_line[i-1] + clv * volume[i] if i > 0 else clv * volume[i]
            current_ad = float(ad_line[-1])
            prev_ad = float(ad_line[-20])
            signal = 'BUY' if current_ad > prev_ad else ('SELL' if current_ad < prev_ad else 'NEUTRAL')
            return {'ad_line': current_ad, 'signal': signal, 'strength': 60.0 if signal != 'NEUTRAL' else 30.0}
        except Exception as e:
            self.logger.debug(f"A/D error: {e}")
            return {'signal': 'NEUTRAL', 'strength': 0}
    
    async def analyze_keltner_channel(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Keltner Channel"""
        try:
            close = df['close'].values[-20:]
            atr_vals = np.zeros(len(close)-1)
            for i in range(1, len(close)):
                tr = max(df['high'].values[-(len(close)-i)] - df['low'].values[-(len(close)-i)], 
                        abs(df['high'].values[-(len(close)-i)] - close[i-1]), 
                        abs(df['low'].values[-(len(close)-i)] - close[i-1]))
                atr_vals[i-1] = tr
            atr = float(np.mean(atr_vals))
            mid = float(np.mean(close))
            upper = float(mid + 2 * atr)
            lower = float(mid - 2 * atr)
            current = float(close[-1])
            signal = 'BUY' if current < lower else ('SELL' if current > upper else 'NEUTRAL')
            return {'upper': upper, 'middle': mid, 'lower': lower, 'signal': signal, 'strength': 65.0 if signal != 'NEUTRAL' else 40.0}
        except Exception as e:
            self.logger.debug(f"Keltner error: {e}")
            return {'signal': 'NEUTRAL', 'strength': 0}
    
    async def analyze_pivot_points(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Pivot Points"""
        try:
            high = float(df['high'].iloc[-1])
            low = float(df['low'].iloc[-1])
            close = float(df['close'].iloc[-1])
            pivot = (high + low + close) / 3
            r1 = 2 * pivot - low
            s1 = 2 * pivot - high
            signal = 'BUY' if close < pivot else ('SELL' if close > pivot else 'NEUTRAL')
            return {'pivot': pivot, 'r1': r1, 's1': s1, 'signal': signal, 'strength': 60.0}
        except Exception as e:
            self.logger.debug(f"Pivot error: {e}")
            return {'signal': 'NEUTRAL', 'strength': 0}
    
    async def analyze_supertrend(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Supertrend Indicator"""
        try:
            high = df['high'].values[-20:]
            low = df['low'].values[-20:]
            close = df['close'].values[-20:]
            hl2 = (high + low) / 2
            atr = np.mean(np.maximum(high[1:] - low[1:], np.maximum(abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1]))))
            basic_ub = hl2 + 3 * atr
            basic_lb = hl2 - 3 * atr
            current = float(close[-1])
            signal = 'BUY' if current > np.mean(basic_ub[-5:]) else ('SELL' if current < np.mean(basic_lb[-5:]) else 'NEUTRAL')
            return {'signal': signal, 'strength': 70.0 if signal != 'NEUTRAL' else 50.0}
        except Exception as e:
            self.logger.debug(f"Supertrend error: {e}")
            return {'signal': 'NEUTRAL', 'strength': 0}
    
    async def analyze_vwap(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Volume Weighted Average Price"""
        try:
            close = df['close'].values
            volume = df['volume'].values
            total_volume = np.sum(volume)
            if total_volume == 0:
                return {'vwap': float(close[-1]), 'current': float(close[-1]),
                        'signal': 'NEUTRAL', 'strength': 50.0}
            vwap = float(np.sum(close * volume) / total_volume)
            current = float(close[-1])
            signal = 'BUY' if current < vwap else ('SELL' if current > vwap else 'NEUTRAL')
            return {'vwap': vwap, 'current': current, 'signal': signal, 'strength': 65.0}
        except Exception as e:
            self.logger.debug(f"VWAP error: {e}")
            return {'signal': 'NEUTRAL', 'strength': 0}
    
    async def analyze_ichimoku_extended(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Ichimoku Cloud Extended"""
        try:
            high = df['high'].values[-52:]
            low = df['low'].values[-52:]
            close = df['close'].values[-9:]
            tenkan_hi = np.max(high[-9:])
            tenkan_lo = np.min(low[-9:])
            tenkan = (tenkan_hi + tenkan_lo) / 2
            kijun_hi = np.max(high[-26:])
            kijun_lo = np.min(low[-26:])
            kijun = (kijun_hi + kijun_lo) / 2
            signal = 'BUY' if tenkan > kijun else ('SELL' if tenkan < kijun else 'NEUTRAL')
            return {'tenkan': float(tenkan), 'kijun': float(kijun), 'signal': signal, 'strength': 75.0 if signal != 'NEUTRAL' else 50.0}
        except Exception as e:
            self.logger.debug(f"Ichimoku error: {e}")
            return {'signal': 'NEUTRAL', 'strength': 0}
    
    def _calculate_composite_signal(self, indicators: Dict[str, Any]) -> str:
        """
        Calculate composite signal from all indicators using strength-weighted scoring.

        BUG FIX: Old implementation divided by buy+sell only (ignoring NEUTRAL),
        so 5 BUY / 1 SELL / 8 NEUTRAL gave buy_ratio=5/6=83% → STRONG_BUY.
        Correct approach: weight by all indicators so NETURALs reduce conviction.
        STRONG signal requires >55% of ALL indicators aligned (not just non-neutral).
        """
        try:
            all_inds = [ind for ind in indicators.values() if isinstance(ind, dict)]
            total_count = len(all_inds)
            if total_count == 0:
                return 'NEUTRAL'

            # Use strength-weighted scoring
            buy_score  = sum(
                ind.get('strength', 50.0) / 100.0
                for ind in all_inds if ind.get('signal') == 'BUY'
            )
            sell_score = sum(
                ind.get('strength', 50.0) / 100.0
                for ind in all_inds if ind.get('signal') == 'SELL'
            )

            # Counts for ratio calculation (denominator = ALL indicators)
            buy_count  = sum(1 for ind in all_inds if ind.get('signal') == 'BUY')
            sell_count = sum(1 for ind in all_inds if ind.get('signal') == 'SELL')

            # Ratio out of ALL indicators (including NEUTRAL)
            buy_ratio  = buy_count  / total_count
            sell_ratio = sell_count / total_count

            # Require >55% of ALL indicators aligned for STRONG, >40% for normal
            if buy_ratio > 0.55 and buy_score > sell_score * 1.5:
                return 'STRONG_BUY'
            elif buy_ratio > 0.40 and buy_score > sell_score:
                return 'BUY'
            elif sell_ratio > 0.55 and sell_score > buy_score * 1.5:
                return 'STRONG_SELL'
            elif sell_ratio > 0.40 and sell_score > buy_score:
                return 'SELL'
            return 'NEUTRAL'
        except Exception as e:
            self.logger.debug(f"Composite signal error: {e}")
            return 'NEUTRAL'
    
    def _calculate_overall_strength(self, indicators: Dict[str, Any]) -> float:
        """Calculate overall signal strength"""
        try:
            strengths = []
            for ind in indicators.values():
                if isinstance(ind, dict) and 'strength' in ind:
                    strengths.append(float(ind['strength']))
            return float(np.mean(strengths)) if strengths else 50.0
        except Exception as e:
            self.logger.debug(f"Overall strength error: {e}")
            return 50.0

# Global instance
atas_analyzer = ATASIntegratedAnalyzer()
