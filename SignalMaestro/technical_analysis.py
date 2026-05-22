"""
Technical analysis module for cryptocurrency trading signals
Implements various technical indicators and market analysis
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, List, Optional, Tuple
import asyncio

try:
    import pandas_ta as ta
except ImportError:
    ta = None

class TechnicalAnalysis:
    """Technical analysis calculator for trading signals"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        if ta is None:
            self.logger.warning("pandas_ta not available - some indicators may not work")
    
    async def analyze(self, ohlcv_1h: List[List], ohlcv_4h: List[List], 
                     ohlcv_1d: List[List]) -> Dict[str, Any]:
        """
        Perform comprehensive technical analysis
        
        Args:
            ohlcv_1h: 1-hour OHLCV data
            ohlcv_4h: 4-hour OHLCV data  
            ohlcv_1d: Daily OHLCV data
            
        Returns:
            Technical analysis results
        """
        try:
            # Convert to DataFrames
            df_1h = self._ohlcv_to_dataframe(ohlcv_1h)
            df_4h = self._ohlcv_to_dataframe(ohlcv_4h)
            df_1d = self._ohlcv_to_dataframe(ohlcv_1d)
            
            analysis = {}
            
            # Calculate indicators for each timeframe
            analysis['1h'] = await self._calculate_indicators(df_1h, '1h')
            analysis['4h'] = await self._calculate_indicators(df_4h, '4h')
            analysis['1d'] = await self._calculate_indicators(df_1d, '1d')
            
            # Calculate multi-timeframe signals
            analysis['signals'] = await self._generate_signals(df_1h, df_4h, df_1d)
            
            # Overall trend analysis
            analysis['trend'] = await self._analyze_trend(df_1h, df_4h, df_1d)
            
            # Support and resistance levels
            analysis['levels'] = await self._calculate_support_resistance(df_1h, df_4h)
            
            # Market strength indicators
            analysis['strength'] = await self._calculate_market_strength(df_1h, df_4h, df_1d)
            
            # Risk assessment
            analysis['risk'] = await self._assess_risk(df_1h, df_4h)
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"Error in technical analysis: {e}")
            return {'error': str(e)}
    
    def _ohlcv_to_dataframe(self, ohlcv: List[List]) -> pd.DataFrame:
        """Convert OHLCV data to pandas DataFrame"""
        try:
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # Ensure numeric types
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error converting OHLCV to DataFrame: {e}")
            return pd.DataFrame()
    
    async def _calculate_indicators(self, df: pd.DataFrame, timeframe: str) -> Dict[str, Any]:
        """Calculate technical indicators for a given timeframe"""
        try:
            if df.empty:
                return {}
            
            indicators = {}
            
            # Price-based indicators
            indicators.update(await self._calculate_moving_averages(df))
            indicators.update(await self._calculate_bollinger_bands(df))
            indicators.update(await self._calculate_rsi(df))
            indicators.update(await self._calculate_macd(df))
            indicators.update(await self._calculate_stochastic(df))
            
            # Volume-based indicators
            indicators.update(await self._calculate_volume_indicators(df))
            
            # Volatility indicators
            indicators.update(await self._calculate_volatility_indicators(df))
            
            # Current price information
            current = df.iloc[-1]
            indicators['current_price'] = float(current['close'])
            indicators['current_volume'] = float(current['volume'])
            indicators['price_change'] = float((current['close'] - df.iloc[-2]['close']) / df.iloc[-2]['close'] * 100)
            
            return indicators
            
        except Exception as e:
            self.logger.error(f"Error calculating indicators for {timeframe}: {e}")
            return {}
    
    async def _calculate_moving_averages(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate moving averages"""
        try:
            mas = {}
            
            # Simple Moving Averages
            for period in [7, 14, 20, 50, 100, 200]:
                if len(df) >= period:
                    sma = df['close'].rolling(window=period).mean()
                    mas[f'sma_{period}'] = float(sma.iloc[-1])
            
            # Exponential Moving Averages
            for period in [12, 26, 50]:
                if len(df) >= period:
                    ema = df['close'].ewm(span=period).mean()
                    mas[f'ema_{period}'] = float(ema.iloc[-1])
            
            # Moving Average Crossover Signals
            if 'sma_20' in mas and 'sma_50' in mas:
                mas['ma_signal'] = 'bullish' if mas['sma_20'] > mas['sma_50'] else 'bearish'
            
            return mas
            
        except Exception as e:
            self.logger.error(f"Error calculating moving averages: {e}")
            return {}
    
    async def _calculate_bollinger_bands(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate Bollinger Bands"""
        try:
            period = 20
            std_dev = 2
            
            if len(df) < period:
                return {}
            
            sma = df['close'].rolling(window=period).mean()
            std = df['close'].rolling(window=period).std()
            
            upper_band = sma + (std * std_dev)
            lower_band = sma - (std * std_dev)
            
            current_price = df['close'].iloc[-1]
            
            # Calculate position within bands
            bb_position = (current_price - lower_band.iloc[-1]) / (upper_band.iloc[-1] - lower_band.iloc[-1])
            
            return {
                'bb_upper': float(upper_band.iloc[-1]),
                'bb_middle': float(sma.iloc[-1]),
                'bb_lower': float(lower_band.iloc[-1]),
                'bb_position': float(bb_position),
                'bb_signal': 'overbought' if bb_position > 0.8 else 'oversold' if bb_position < 0.2 else 'neutral'
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating Bollinger Bands: {e}")
            return {}
    
    async def _calculate_rsi(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate Relative Strength Index"""
        try:
            period = 14
            
            if len(df) < period + 1:
                return {}
            
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            current_rsi = float(rsi.iloc[-1])
            
            return {
                'rsi': current_rsi,
                'rsi_signal': 'overbought' if current_rsi > 70 else 'oversold' if current_rsi < 30 else 'neutral'
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating RSI: {e}")
            return {}
    
    async def _calculate_macd(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate MACD indicator"""
        try:
            if len(df) < 26:
                return {}
            
            ema_12 = df['close'].ewm(span=12).mean()
            ema_26 = df['close'].ewm(span=26).mean()
            macd_line = ema_12 - ema_26
            signal_line = macd_line.ewm(span=9).mean()
            histogram = macd_line - signal_line
            
            current_macd = float(macd_line.iloc[-1])
            current_signal = float(signal_line.iloc[-1])
            current_histogram = float(histogram.iloc[-1])
            
            return {
                'macd': current_macd,
                'macd_signal': current_signal,
                'macd_histogram': current_histogram,
                'macd_trend': 'bullish' if current_macd > current_signal else 'bearish'
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating MACD: {e}")
            return {}
    
    async def _calculate_stochastic(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate Stochastic oscillator"""
        try:
            period = 14
            
            if len(df) < period:
                return {}
            
            low_min = df['low'].rolling(window=period).min()
            high_max = df['high'].rolling(window=period).max()
            
            k_percent = 100 * ((df['close'] - low_min) / (high_max - low_min))
            d_percent = k_percent.rolling(window=3).mean()
            
            current_k = float(k_percent.iloc[-1])
            current_d = float(d_percent.iloc[-1])
            
            return {
                'stoch_k': current_k,
                'stoch_d': current_d,
                'stoch_signal': 'overbought' if current_k > 80 else 'oversold' if current_k < 20 else 'neutral'
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating Stochastic: {e}")
            return {}
    
    async def _calculate_volume_indicators(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate volume-based indicators"""
        try:
            indicators = {}
            
            # Volume Moving Average
            if len(df) >= 20:
                vol_sma = df['volume'].rolling(window=20).mean()
                indicators['volume_sma'] = float(vol_sma.iloc[-1])
                indicators['volume_ratio'] = float(df['volume'].iloc[-1] / vol_sma.iloc[-1])
            
            # On-Balance Volume (simplified)
            if len(df) >= 2:
                obv = []
                obv_value = 0
                
                for i in range(1, len(df)):
                    if df['close'].iloc[i] > df['close'].iloc[i-1]:
                        obv_value += df['volume'].iloc[i]
                    elif df['close'].iloc[i] < df['close'].iloc[i-1]:
                        obv_value -= df['volume'].iloc[i]
                    obv.append(obv_value)
                
                if obv:
                    indicators['obv'] = float(obv[-1])
            
            return indicators
            
        except Exception as e:
            self.logger.error(f"Error calculating volume indicators: {e}")
            return {}
    
    async def _calculate_volatility_indicators(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate volatility indicators"""
        try:
            indicators = {}
            
            # Average True Range
            if len(df) >= 14:
                high_low = df['high'] - df['low']
                high_close = np.abs(df['high'] - df['close'].shift())
                low_close = np.abs(df['low'] - df['close'].shift())
                
                true_range = np.maximum(high_low, np.maximum(high_close, low_close))
                atr = true_range.rolling(window=14).mean()
                indicators['atr'] = float(atr.iloc[-1])
                indicators['atr_percent'] = float(atr.iloc[-1] / df['close'].iloc[-1] * 100)
            
            # Volatility (standard deviation of returns)
            if len(df) >= 20:
                returns = df['close'].pct_change()
                volatility = returns.rolling(window=20).std() * np.sqrt(24)  # Annualized
                indicators['volatility'] = float(volatility.iloc[-1] * 100)
            
            return indicators
            
        except Exception as e:
            self.logger.error(f"Error calculating volatility indicators: {e}")
            return {}
    
    async def _generate_signals(self, df_1h: pd.DataFrame, df_4h: pd.DataFrame, 
                               df_1d: pd.DataFrame) -> Dict[str, Any]:
        """Generate trading signals based on multiple timeframes"""
        try:
            signals = {
                'overall': 'neutral',
                'strength': 0,
                'short_term': 'neutral',
                'medium_term': 'neutral',
                'long_term': 'neutral',
                'confidence': 0
            }
            
            signal_scores = []
            
            # 1-hour signals (short-term)
            if not df_1h.empty and len(df_1h) >= 20:
                short_signals = await self._get_timeframe_signals(df_1h)
                signals['short_term'] = short_signals['direction']
                signal_scores.append(short_signals['score'])
            
            # 4-hour signals (medium-term)
            if not df_4h.empty and len(df_4h) >= 20:
                medium_signals = await self._get_timeframe_signals(df_4h)
                signals['medium_term'] = medium_signals['direction']
                signal_scores.append(medium_signals['score'] * 1.5)  # Weight medium-term more
            
            # Daily signals (long-term)
            if not df_1d.empty and len(df_1d) >= 20:
                long_signals = await self._get_timeframe_signals(df_1d)
                signals['long_term'] = long_signals['direction']
                signal_scores.append(long_signals['score'] * 2)  # Weight long-term most
            
            # Calculate overall signal
            if signal_scores:
                avg_score = sum(signal_scores) / len(signal_scores)
                signals['strength'] = avg_score
                
                if avg_score > 0.3:
                    signals['overall'] = 'bullish'
                elif avg_score < -0.3:
                    signals['overall'] = 'bearish'
                else:
                    signals['overall'] = 'neutral'
                
                signals['confidence'] = min(abs(avg_score) * 100, 100)
            
            return signals
            
        except Exception as e:
            self.logger.error(f"Error generating signals: {e}")
            return {'overall': 'neutral', 'error': str(e)}
    
    async def _get_timeframe_signals(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Get signals for a specific timeframe"""
        try:
            score = 0
            signals_count = 0
            
            # Moving average signal
            if len(df) >= 50:
                sma_20 = df['close'].rolling(window=20).mean()
                sma_50 = df['close'].rolling(window=50).mean()
                
                if sma_20.iloc[-1] > sma_50.iloc[-1]:
                    score += 1
                else:
                    score -= 1
                signals_count += 1
            
            # RSI signal
            if len(df) >= 15:
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                
                current_rsi = rsi.iloc[-1]
                if current_rsi < 30:
                    score += 1  # Oversold - bullish
                elif current_rsi > 70:
                    score -= 1  # Overbought - bearish
                signals_count += 1
            
            # MACD signal
            if len(df) >= 26:
                ema_12 = df['close'].ewm(span=12).mean()
                ema_26 = df['close'].ewm(span=26).mean()
                macd = ema_12 - ema_26
                signal_line = macd.ewm(span=9).mean()
                
                if macd.iloc[-1] > signal_line.iloc[-1]:
                    score += 1
                else:
                    score -= 1
                signals_count += 1
            
            # Price momentum signal
            if len(df) >= 10:
                price_change = (df['close'].iloc[-1] - df['close'].iloc[-10]) / df['close'].iloc[-10]
                if price_change > 0.02:  # 2% increase
                    score += 1
                elif price_change < -0.02:  # 2% decrease
                    score -= 1
                signals_count += 1
            
            # Normalize score
            if signals_count > 0:
                normalized_score = score / signals_count
            else:
                normalized_score = 0
            
            direction = 'bullish' if normalized_score > 0.2 else 'bearish' if normalized_score < -0.2 else 'neutral'
            
            return {
                'score': normalized_score,
                'direction': direction,
                'signals_count': signals_count
            }
            
        except Exception as e:
            self.logger.error(f"Error getting timeframe signals: {e}")
            return {'score': 0, 'direction': 'neutral', 'signals_count': 0}
    
    async def _analyze_trend(self, df_1h: pd.DataFrame, df_4h: pd.DataFrame, 
                            df_1d: pd.DataFrame) -> Dict[str, Any]:
        """Analyze overall trend across timeframes"""
        try:
            trend_analysis = {
                'short_term_trend': 'neutral',
                'medium_term_trend': 'neutral', 
                'long_term_trend': 'neutral',
                'trend_strength': 'weak'
            }
            
            # Analyze each timeframe
            timeframes = [
                ('short_term_trend', df_1h, 20),
                ('medium_term_trend', df_4h, 20),
                ('long_term_trend', df_1d, 20)
            ]
            
            trend_scores = []
            
            for trend_key, df, period in timeframes:
                if not df.empty and len(df) >= period:
                    # Calculate trend using linear regression slope
                    y = df['close'].tail(period).values
                    x = np.arange(len(y))
                    
                    slope = np.polyfit(x, y, 1)[0]
                    trend_score = slope / y[-1] * 100  # Normalize by current price
                    
                    if trend_score > 0.5:
                        trend_analysis[trend_key] = 'uptrend'
                    elif trend_score < -0.5:
                        trend_analysis[trend_key] = 'downtrend'
                    else:
                        trend_analysis[trend_key] = 'sideways'
                    
                    trend_scores.append(abs(trend_score))
            
            # Determine overall trend strength
            if trend_scores:
                avg_strength = sum(trend_scores) / len(trend_scores)
                if avg_strength > 2:
                    trend_analysis['trend_strength'] = 'strong'
                elif avg_strength > 1:
                    trend_analysis['trend_strength'] = 'moderate'
                else:
                    trend_analysis['trend_strength'] = 'weak'
            
            return trend_analysis
            
        except Exception as e:
            self.logger.error(f"Error analyzing trend: {e}")
            return {'error': str(e)}
    
    async def _calculate_support_resistance(self, df_1h: pd.DataFrame, 
                                           df_4h: pd.DataFrame) -> Dict[str, List[float]]:
        """Calculate support and resistance levels"""
        try:
            levels = {
                'support_levels': [],
                'resistance_levels': [],
                'key_levels': []
            }
            
            # Use 4-hour data for more significant levels
            if not df_4h.empty and len(df_4h) >= 50:
                highs = df_4h['high'].rolling(window=5, center=True).max()
                lows = df_4h['low'].rolling(window=5, center=True).min()
                
                # Find local peaks (resistance)
                for i in range(2, len(df_4h) - 2):
                    if (df_4h['high'].iloc[i] == highs.iloc[i] and 
                        df_4h['high'].iloc[i] > df_4h['high'].iloc[i-1] and
                        df_4h['high'].iloc[i] > df_4h['high'].iloc[i+1]):
                        levels['resistance_levels'].append(float(df_4h['high'].iloc[i]))
                
                # Find local troughs (support)
                for i in range(2, len(df_4h) - 2):
                    if (df_4h['low'].iloc[i] == lows.iloc[i] and 
                        df_4h['low'].iloc[i] < df_4h['low'].iloc[i-1] and
                        df_4h['low'].iloc[i] < df_4h['low'].iloc[i+1]):
                        levels['support_levels'].append(float(df_4h['low'].iloc[i]))
                
                # Remove duplicates and sort
                levels['resistance_levels'] = sorted(list(set(levels['resistance_levels'])))[-5:]  # Keep top 5
                levels['support_levels'] = sorted(list(set(levels['support_levels'])), reverse=True)[:5]  # Keep top 5
                
                # Combine key levels
                levels['key_levels'] = levels['support_levels'] + levels['resistance_levels']
            
            return levels
            
        except Exception as e:
            self.logger.error(f"Error calculating support/resistance: {e}")
            return {'support_levels': [], 'resistance_levels': [], 'key_levels': []}
    
    async def _calculate_market_strength(self, df_1h: pd.DataFrame, df_4h: pd.DataFrame, 
                                        df_1d: pd.DataFrame) -> Dict[str, Any]:
        """Calculate market strength indicators"""
        try:
            strength = {
                'volume_strength': 'normal',
                'momentum_strength': 'normal',
                'volatility_level': 'normal',
                'overall_strength': 'normal'
            }
            
            # Volume strength analysis
            if not df_1h.empty and len(df_1h) >= 20:
                current_volume = df_1h['volume'].iloc[-1]
                avg_volume = df_1h['volume'].rolling(window=20).mean().iloc[-1]
                
                volume_ratio = current_volume / avg_volume
                if volume_ratio > 2:
                    strength['volume_strength'] = 'high'
                elif volume_ratio < 0.5:
                    strength['volume_strength'] = 'low'
            
            # Momentum strength
            if not df_4h.empty and len(df_4h) >= 10:
                price_change_24h = (df_4h['close'].iloc[-1] - df_4h['close'].iloc[-6]) / df_4h['close'].iloc[-6]
                
                if abs(price_change_24h) > 0.05:  # 5% change
                    strength['momentum_strength'] = 'high'
                elif abs(price_change_24h) < 0.01:  # 1% change
                    strength['momentum_strength'] = 'low'
            
            # Volatility level
            if not df_1h.empty and len(df_1h) >= 20:
                returns = df_1h['close'].pct_change()
                volatility = returns.rolling(window=20).std().iloc[-1]
                
                if volatility > 0.03:  # 3%
                    strength['volatility_level'] = 'high'
                elif volatility < 0.01:  # 1%
                    strength['volatility_level'] = 'low'
            
            # Overall strength assessment
            high_count = sum(1 for v in strength.values() if v == 'high')
            low_count = sum(1 for v in strength.values() if v == 'low')
            
            if high_count >= 2:
                strength['overall_strength'] = 'high'
            elif low_count >= 2:
                strength['overall_strength'] = 'low'
            
            return strength
            
        except Exception as e:
            self.logger.error(f"Error calculating market strength: {e}")
            return {'error': str(e)}
    
    async def _assess_risk(self, df_1h: pd.DataFrame, df_4h: pd.DataFrame) -> Dict[str, Any]:
        """Assess trading risk based on market conditions"""
        try:
            risk_assessment = {
                'volatility_risk': 'medium',
                'trend_risk': 'medium', 
                'volume_risk': 'medium',
                'overall_risk': 'medium',
                'risk_score': 50
            }
            
            risk_factors = []
            
            # Volatility risk
            if not df_1h.empty and len(df_1h) >= 20:
                returns = df_1h['close'].pct_change()
                volatility = returns.rolling(window=20).std().iloc[-1]
                
                if volatility > 0.04:  # High volatility
                    risk_assessment['volatility_risk'] = 'high'
                    risk_factors.append(20)
                elif volatility < 0.01:  # Low volatility
                    risk_assessment['volatility_risk'] = 'low'
                    risk_factors.append(-10)
                else:
                    risk_factors.append(0)
            
            # Trend consistency risk
            if not df_4h.empty and len(df_4h) >= 20:
                # Check for trend reversals
                recent_highs = df_4h['high'].tail(10).max()
                recent_lows = df_4h['low'].tail(10).min()
                price_range = (recent_highs - recent_lows) / df_4h['close'].iloc[-1]
                
                if price_range > 0.1:  # 10% range
                    risk_assessment['trend_risk'] = 'high'
                    risk_factors.append(15)
                else:
                    risk_assessment['trend_risk'] = 'low'
                    risk_factors.append(-5)
            
            # Volume risk (low volume = higher risk)
            if not df_1h.empty and len(df_1h) >= 20:
                current_volume = df_1h['volume'].iloc[-1]
                avg_volume = df_1h['volume'].rolling(window=20).mean().iloc[-1]
                
                if current_volume < avg_volume * 0.5:  # Low volume
                    risk_assessment['volume_risk'] = 'high'
                    risk_factors.append(10)
                elif current_volume > avg_volume * 1.5:  # High volume
                    risk_assessment['volume_risk'] = 'low'
                    risk_factors.append(-5)
                else:
                    risk_factors.append(0)
            
            # Calculate overall risk score
            if risk_factors:
                base_score = 50
                risk_adjustment = sum(risk_factors)
                risk_score = max(0, min(100, base_score + risk_adjustment))
                
                risk_assessment['risk_score'] = risk_score
                
                if risk_score > 70:
                    risk_assessment['overall_risk'] = 'high'
                elif risk_score < 30:
                    risk_assessment['overall_risk'] = 'low'
                else:
                    risk_assessment['overall_risk'] = 'medium'
            
            return risk_assessment
            
        except Exception as e:
            self.logger.error(f"Error assessing risk: {e}")
            return {'error': str(e)}

    async def get_signal_recommendation(self, symbol: str, ohlcv_data: Dict[str, List]) -> Dict[str, Any]:
        """Get trading recommendation for a symbol"""
        try:
            analysis = await self.analyze(
                ohlcv_data.get('1h', []),
                ohlcv_data.get('4h', []),
                ohlcv_data.get('1d', [])
            )
            
            if 'error' in analysis:
                return {'recommendation': 'HOLD', 'confidence': 0, 'reason': 'Analysis error'}
            
            signals = analysis.get('signals', {})
            risk = analysis.get('risk', {})
            trend = analysis.get('trend', {})
            
            # Determine recommendation
            overall_signal = signals.get('overall', 'neutral')
            confidence = signals.get('confidence', 0)
            risk_level = risk.get('overall_risk', 'medium')
            
            recommendation = 'HOLD'
            reason = 'Neutral market conditions'
            
            if overall_signal == 'bullish' and confidence > 60 and risk_level != 'high':
                recommendation = 'BUY'
                reason = f'Bullish signals detected with {confidence:.0f}% confidence'
            elif overall_signal == 'bearish' and confidence > 60 and risk_level != 'high':
                recommendation = 'SELL'
                reason = f'Bearish signals detected with {confidence:.0f}% confidence'
            elif risk_level == 'high':
                recommendation = 'HOLD'
                reason = 'High risk conditions detected'
            
            # Adjust confidence based on risk
            if risk_level == 'high':
                confidence *= 0.7
            elif risk_level == 'low':
                confidence *= 1.1
            
            confidence = min(confidence, 100)
            
            return {
                'recommendation': recommendation,
                'confidence': round(confidence, 1),
                'reason': reason,
                'signals': signals,
                'risk': risk,
                'trend': trend
            }
            
        except Exception as e:
            self.logger.error(f"Error getting signal recommendation: {e}")
            return {
                'recommendation': 'HOLD',
                'confidence': 0,
                'reason': f'Error: {str(e)}'
            }
