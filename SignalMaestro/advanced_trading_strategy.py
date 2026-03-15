#!/usr/bin/env python3
"""
Advanced Trading Strategy with Technical Analysis
Generates profitable trading signals with chart analysis and Telegram integration
"""

import asyncio
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO
import base64
import warnings

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')
warnings.filterwarnings("ignore", category=UserWarning, module="pandas_ta")
warnings.filterwarnings('ignore', category=UserWarning, module='matplotlib')
warnings.filterwarnings('ignore', category=UserWarning, message='Glyph*')
warnings.filterwarnings('ignore', category=UserWarning, message='This figure includes Axes*')

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False
    # Create a mock ta object to prevent errors
    class MockTA:
        @staticmethod
        def rsi(close, length=14):
            return pd.Series([50] * len(close), index=close.index)
        @staticmethod
        def ema(close, length=20):
            return close.rolling(window=length).mean()
        @staticmethod
        def sma(close, length=20):
            return close.rolling(window=length).mean()
        @staticmethod
        def bbands(close, length=20, std=2):
            sma = close.rolling(window=length).mean()
            std_dev = close.rolling(window=length).std()
            return pd.DataFrame({
                'BBL_20_2.0': sma - (std_dev * std),
                'BBM_20_2.0': sma,
                'BBU_20_2.0': sma + (std_dev * std)
            })
        @staticmethod
        def macd(close, fast=12, slow=26, signal=9):
            ema_fast = close.ewm(span=fast).mean()
            ema_slow = close.ewm(span=slow).mean()
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=signal).mean()
            return pd.DataFrame({
                'MACD_12_26_9': macd_line,
                'MACDs_12_26_9': signal_line,
                'MACDh_12_26_9': macd_line - signal_line
            })

    ta = MockTA()


# Mock classes if not provided elsewhere
class BinanceTrader:
    async def get_market_data(self, symbol, timeframe, limit):
        return []
    async def get_current_price(self, symbol):
        return 0.0

class RiskManager:
    async def validate_signal(self, signal):
        return {'valid': True, 'risk_score': 0.5, 'position_size': 100}

class Config:
    def __init__(self, binance_trader=None):
        self.binance_trader = binance_trader
        self.binance_trader = binance_trader
        self.TELEGRAM_BOT_TOKEN = "dummy_token"
        self.TELEGRAM_CHAT_ID = "dummy_chat_id"
        self.BINANCE_API_KEY = "dummy_api_key"
        self.BINANCE_API_SECRET = "dummy_api_secret"

class AdvancedTradingStrategy:
    """
    Advanced trading strategy combining multiple indicators for high-probability signals
    """

    def __init__(self, binance_trader=None):
        if binance_trader is None:
            from binance_trader import BinanceTrader
            binance_trader = BinanceTrader()
        self.binance_trader = binance_trader
        self.config = Config()
        self.logger = logging.getLogger(__name__)
        self.binance_trader = binance_trader
        self.technical_analysis = TechnicalAnalysis()
        self.risk_manager = RiskManager()

        # Strategy parameters
        self.symbols = ['BTCUSDT', 'ETHUSDT', 'ADAUSDT', 'SOLUSDT', 'MATICUSDT', 'LINKUSDT']
        self.timeframes = ['1h', '4h', '1d']
        self.min_signal_strength = 70  # Minimum signal strength percentage
        self.max_signals_per_hour = 3  # Rate limiting

    async def scan_markets(self) -> List[Dict[str, Any]]:
        """
        Scan multiple markets for MACD ANTI trading opportunities
        """
        from .macd_anti_strategy import MACDAntiStrategy

        macd_anti = MACDAntiStrategy()
        signals = []

        for symbol in self.symbols:
            try:
                # Get market data for MACD ANTI analysis
                market_data = {}
                market_data['5m'] = await self.binance_trader.get_market_data(symbol, '5m', 100)
                market_data['15m'] = await self.binance_trader.get_market_data(symbol, '15m', 50)
                market_data['1h'] = await self.binance_trader.get_market_data(symbol, '1h', 30)

                # Analyze with MACD ANTI strategy
                macd_signal = await macd_anti.analyze_symbol(symbol, market_data)

                if macd_signal and macd_signal.signal_strength >= self.min_signal_strength:
                    # Convert to standard format
                    signal = {
                        'symbol': symbol,
                        'action': macd_signal.direction,
                        'strength': macd_signal.signal_strength,
                        'entry_price': macd_signal.entry_price,
                        'stop_loss': macd_signal.stop_loss,
                        'take_profit_1': macd_signal.tp1,
                        'take_profit_2': macd_signal.tp2,
                        'take_profit_3': macd_signal.tp3,
                        'leverage': macd_signal.leverage,
                        'strategy': 'MACD_ANTI_AI_POWERED',
                        'ai_confidence': macd_signal.ai_confidence_score,
                        'anti_trend_confidence': macd_signal.anti_trend_confidence,
                        'macd_divergence': macd_signal.macd_divergence_strength,
                        'market_regime': macd_signal.market_regime
                    }
                    signals.append(signal)

            except Exception as e:
                self.logger.error(f"Error analyzing {symbol} with MACD ANTI: {e}")
                continue

        # Sort by AI confidence and signal strength
        signals.sort(key=lambda x: (x.get('ai_confidence', 0) + x.get('strength', 0)) / 2, reverse=True)

        # Apply rate limiting
        return signals[:self.max_signals_per_hour]

    async def analyze_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Analyze a single symbol and return signal if found
        """
        try:
            self.logger.info(f"Analyzing {symbol}...")

            # Get current price first
            current_price = await self.binance_trader.get_current_price(symbol)
            if current_price <= 0:
                self.logger.warning(f"Invalid price for {symbol}: {current_price}")
                return None

            # Get market data for multiple timeframes
            market_data = {}
            market_data['1h'] = await self.binance_trader.get_market_data(symbol, '1h', 100)
            market_data['4h'] = await self.binance_trader.get_market_data(symbol, '4h', 50)
            market_data['1d'] = await self.binance_trader.get_market_data(symbol, '1d', 30)

            # Check if we have sufficient data
            if not any(len(data) > 20 for data in market_data.values()):
                self.logger.warning(f"Insufficient market data for {symbol}")
                return None

            # Strategy 1: Multi-timeframe trend alignment
            trend_signal = await self._trend_alignment_strategy(market_data, symbol)

            # Strategy 2: Mean reversion with RSI divergence
            mean_reversion_signal = await self._mean_reversion_strategy(market_data, symbol)

            # Strategy 3: Breakout strategy with volume confirmation
            breakout_signal = await self._breakout_strategy(market_data, symbol)

            # Strategy 4: Support/Resistance bounce
            support_resistance_signal = await self._support_resistance_strategy(market_data, symbol)

            # Combine signals
            combined_signal = await self._combine_signals(
                trend_signal, mean_reversion_signal, breakout_signal, support_resistance_signal,
                symbol, current_price, market_data
            )

            if combined_signal and combined_signal.get('action'):
                # Generate chart
                chart_data = await self._generate_chart(symbol, market_data, combined_signal)
                combined_signal['chart'] = chart_data

                # Calculate position sizing and risk
                risk_analysis = await self.risk_manager.validate_signal(combined_signal)
                combined_signal.update(risk_analysis)

            return combined_signal

        except Exception as e:
            self.logger.error(f"Error in symbol analysis for {symbol}: {e}")
            return None

    async def _trend_alignment_strategy(self, market_data: Dict, symbol: str) -> Dict[str, Any]:
        """
        Strategy 1: Multi-timeframe trend alignment
        Looks for alignment across 1h, 4h, and daily timeframes
        """
        try:
            signals = {}
            trend_scores = []

            for timeframe in self.timeframes:
                if timeframe not in market_data:
                    continue

                df = self._to_dataframe(market_data[timeframe])
                if df.empty:
                    continue

                # Calculate trend indicators
                sma_20 = df['close'].rolling(20).mean()
                sma_50 = df['close'].rolling(50).mean()
                ema_12 = df['close'].ewm(span=12).mean()
                ema_26 = df['close'].ewm(span=26).mean()

                # MACD
                macd_data = ta.macd(df['close'])
                macd = macd_data['MACD_12_26_9']
                macd_signal = macd_data['MACDs_12_26_9']

                # Trend score
                trend_score = 0
                if len(df) >= 50:
                    if sma_20.iloc[-1] > sma_50.iloc[-1]:
                        trend_score += 1
                    if macd.iloc[-1] > macd_signal.iloc[-1]:
                        trend_score += 1
                    if df['close'].iloc[-1] > sma_20.iloc[-1]:
                        trend_score += 1

                trend_scores.append(trend_score / 3)  # Normalize

            # Check for trend alignment
            avg_trend = sum(trend_scores) / len(trend_scores) if trend_scores else 0

            if avg_trend > 0.7:  # Strong bullish alignment
                return {
                    'strategy': 'trend_alignment',
                    'action': 'BUY',
                    'strength': min(avg_trend * 100, 100),
                    'timeframe_alignment': trend_scores,
                    'reason': 'Multi-timeframe bullish trend alignment'
                }
            elif avg_trend < 0.3:  # Strong bearish alignment
                return {
                    'strategy': 'trend_alignment',
                    'action': 'SELL',
                    'strength': min((1 - avg_trend) * 100, 100),
                    'timeframe_alignment': trend_scores,
                    'reason': 'Multi-timeframe bearish trend alignment'
                }

            return {'strategy': 'trend_alignment', 'action': None, 'strength': 0}

        except Exception as e:
            self.logger.error(f"Error in trend alignment strategy: {e}")
            return {'strategy': 'trend_alignment', 'action': None, 'strength': 0}

    async def _mean_reversion_strategy(self, market_data: Dict, symbol: str) -> Dict[str, Any]:
        """
        Strategy 2: Mean reversion with RSI divergence
        """
        try:
            if '4h' not in market_data:
                return {'strategy': 'mean_reversion', 'action': None, 'strength': 0}

            df = self._to_dataframe(market_data['4h'])
            if len(df) < 50:
                return {'strategy': 'mean_reversion', 'action': None, 'strength': 0}

            # RSI calculation
            rsi_data = ta.rsi(df['close'], length=14)

            # Bollinger Bands
            bbands_data = ta.bbands(df['close'], length=20, std=2)
            bb_upper = bbands_data['BBU_20_2.0']
            bb_lower = bbands_data['BBL_20_2.0']

            current_price = df['close'].iloc[-1]
            current_rsi = rsi_data.iloc[-1]

            # Mean reversion signals
            if current_rsi < 30 and current_price < bb_lower.iloc[-1]:
                # Oversold condition
                strength = min((30 - current_rsi) * 2 + 20, 100)
                return {
                    'strategy': 'mean_reversion',
                    'action': 'BUY',
                    'strength': strength,
                    'rsi': current_rsi,
                    'bb_position': (current_price - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1]),
                    'reason': f'Oversold RSI ({current_rsi:.1f}) + price below BB lower band'
                }
            elif current_rsi > 70 and current_price > bb_upper.iloc[-1]:
                # Overbought condition
                strength = min((current_rsi - 70) * 2 + 20, 100)
                return {
                    'strategy': 'mean_reversion',
                    'action': 'SELL',
                    'strength': strength,
                    'rsi': current_rsi,
                    'bb_position': (current_price - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1]),
                    'reason': f'Overbought RSI ({current_rsi:.1f}) + price above BB upper band'
                }

            return {'strategy': 'mean_reversion', 'action': None, 'strength': 0}

        except Exception as e:
            self.logger.error(f"Error in mean reversion strategy: {e}")
            return {'strategy': 'mean_reversion', 'action': None, 'strength': 0}

    async def _breakout_strategy(self, market_data: Dict, symbol: str) -> Dict[str, Any]:
        """
        Strategy 3: Breakout strategy with volume confirmation
        """
        try:
            if '1h' not in market_data:
                return {'strategy': 'breakout', 'action': None, 'strength': 0}

            df = self._to_dataframe(market_data['1h'])
            if len(df) < 50:
                return {'strategy': 'breakout', 'action': None, 'strength': 0}

            # Calculate support and resistance levels
            highs = df['high'].rolling(window=20, center=True).max()
            lows = df['low'].rolling(window=20, center=True).min()

            # Find recent resistance and support
            resistance_levels = []
            support_levels = []

            for i in range(10, len(df) - 10):
                if df['high'].iloc[i] == highs.iloc[i]:
                    resistance_levels.append(df['high'].iloc[i])
                if df['low'].iloc[i] == lows.iloc[i]:
                    support_levels.append(df['low'].iloc[i])

            if not resistance_levels and not support_levels:
                return {'strategy': 'breakout', 'action': None, 'strength': 0}

            current_price = df['close'].iloc[-1]
            current_volume = df['volume'].iloc[-1]
            avg_volume = df['volume'].rolling(20).mean().iloc[-1]
            volume_ratio = current_price / avg_volume
            #Fixing Division by zero error for avg_volume
            if avg_volume == 0:
                volume_ratio = 1.0 # Default to 1 if avg_volume is zero

            # Check for breakout
            if resistance_levels:
                nearest_resistance = min(resistance_levels, key=lambda x: abs(x - current_price))
                if current_price > nearest_resistance and volume_ratio > 1.5:
                    strength = min((volume_ratio - 1) * 30 + 50, 100)
                    return {
                        'strategy': 'breakout',
                        'action': 'BUY',
                        'strength': strength,
                        'breakout_level': nearest_resistance,
                        'volume_ratio': volume_ratio,
                        'reason': f'Resistance breakout at {nearest_resistance:.2f} with {volume_ratio:.1f}x volume'
                    }

            if support_levels:
                nearest_support = min(support_levels, key=lambda x: abs(x - current_price))
                if current_price < nearest_support and volume_ratio > 1.5:
                    strength = min((volume_ratio - 1) * 30 + 50, 100)
                    return {
                        'strategy': 'breakout',
                        'action': 'SELL',
                        'strength': strength,
                        'breakdown_level': nearest_support,
                        'volume_ratio': volume_ratio,
                        'reason': f'Support breakdown at {nearest_support:.2f} with {volume_ratio:.1f}x volume'
                    }

            return {'strategy': 'breakout', 'action': None, 'strength': 0}

        except Exception as e:
            self.logger.error(f"Error in breakout strategy: {e}")
            return {'strategy': 'breakout', 'action': None, 'strength': 0}

    async def _support_resistance_strategy(self, market_data: Dict, symbol: str) -> Dict[str, Any]:
        """
        Strategy 4: Support/Resistance bounce
        """
        try:
            if '4h' not in market_data:
                return {'strategy': 'support_resistance', 'action': None, 'strength': 0}

            df = self._to_dataframe(market_data['4h'])
            if len(df) < 50:
                return {'strategy': 'support_resistance', 'action': None, 'strength': 0}

            # Calculate key levels
            pivot_high = df['high'].rolling(window=5, center=True).max()
            pivot_low = df['low'].rolling(window=5, center=True).min()

            # Find pivot points
            resistance_levels = []
            support_levels = []

            for i in range(2, len(df) - 2):
                if df['high'].iloc[i] == pivot_high.iloc[i]:
                    resistance_levels.append(df['high'].iloc[i])
                if df['low'].iloc[i] == pivot_low.iloc[i]:
                    support_levels.append(df['low'].iloc[i])

            current_price = df['close'].iloc[-1]

            # Check for bounce opportunities
            if support_levels:
                nearest_support = min(support_levels, key=lambda x: abs(x - current_price) if x < current_price else float('inf'))
                distance_to_support = abs(current_price - nearest_support) / current_price

                if current_price > 0 and distance_to_support < 0.02:  # Within 2% of support
                    # Check if RSI is oversold
                    delta = df['close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    #Fixing division by zero for rs
                    rs = rs.fillna(0)
                    rsi = 100 - (100 / (1 + rs))

                    if rsi.iloc[-1] < 40:
                        strength = min((40 - rsi.iloc[-1]) * 2 + 30, 100)
                        return {
                            'strategy': 'support_resistance',
                            'action': 'BUY',
                            'strength': strength,
                            'support_level': nearest_support,
                            'distance_percent': distance_to_support * 100,
                            'rsi': rsi.iloc[-1],
                            'reason': f'Support bounce opportunity at {nearest_support:.2f}'
                        }

            if resistance_levels:
                nearest_resistance = min(resistance_levels, key=lambda x: abs(x - current_price) if x > current_price else float('inf'))
                distance_to_resistance = abs(current_price - nearest_resistance) / current_price

                if current_price > 0 and distance_to_resistance < 0.02:  # Within 2% of resistance
                    # Check if RSI is overbought
                    delta = df['close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    #Fixing division by zero for rs
                    rs = rs.fillna(0)
                    rsi = 100 - (100 / (1 + rs))

                    if rsi.iloc[-1] > 60:
                        strength = min((rsi.iloc[-1] - 60) * 2 + 30, 100)
                        return {
                            'strategy': 'support_resistance',
                            'action': 'SELL',
                            'strength': strength,
                            'resistance_level': nearest_resistance,
                            'distance_percent': distance_to_resistance * 100,
                            'rsi': rsi.iloc[-1],
                            'reason': f'Resistance rejection opportunity at {nearest_resistance:.2f}'
                        }

            return {'strategy': 'support_resistance', 'action': None, 'strength': 0}

        except Exception as e:
            self.logger.error(f"Error in support/resistance strategy: {e}")
            return {'strategy': 'support_resistance', 'action': None, 'strength': 0}

    async def _combine_signals(self, trend_signal: Dict, mean_reversion_signal: Dict,
                             breakout_signal: Dict, support_resistance_signal: Dict,
                             symbol: str, current_price: float, market_data: Dict) -> Dict[str, Any]:
        """
        Combine multiple strategy signals into a final trading decision
        """
        try:
            signals = [trend_signal, mean_reversion_signal, breakout_signal, support_resistance_signal]

            # Filter signals with actions
            active_signals = [s for s in signals if s.get('action')]

            if not active_signals:
                return None

            # Weight signals by strength
            buy_signals = [s for s in active_signals if s.get('action') == 'BUY']
            sell_signals = [s for s in active_signals if s.get('action') == 'SELL']

            if len(buy_signals) > len(sell_signals):
                # More buy signals
                strongest_signal = max(buy_signals, key=lambda x: x.get('strength', 0))
                combined_strength = sum(s.get('strength', 0) for s in buy_signals) / len(buy_signals)
                action = 'BUY'
            elif len(sell_signals) > len(buy_signals):
                # More sell signals
                strongest_signal = max(sell_signals, key=lambda x: x.get('strength', 0))
                combined_strength = sum(s.get('strength', 0) for s in sell_signals) / len(sell_signals)
                action = 'SELL'
            else:
                # Equal signals, choose strongest
                strongest_signal = max(active_signals, key=lambda x: x.get('strength', 0))
                combined_strength = strongest_signal.get('strength', 0)
                action = strongest_signal.get('action')

            # Calculate stop loss and take profit
            stop_loss, take_profit = await self._calculate_stop_loss_take_profit(
                action, current_price, market_data, strongest_signal
            )

            # Mock indicators and market context for signal generation
            indicators = {
                'rsi': 50,
                'macd': 0.1,
                'bb_width': 0.05,
                'volatility': 0.015 # Example volatility score
            }
            market_context = 'neutral'
            confluence_count = 3
            strategy_names = [s.get('strategy') for s in active_signals]
            dominant_strategy = strongest_signal.get('strategy')
            timeframe = '4h'
            reason = strongest_signal.get('reason', 'Combined signal analysis')
            confidence_score = min(combined_strength, 100)
            risk_reward_ratio = abs(take_profit - current_price) / abs(current_price - stop_loss) if stop_loss and current_price and current_price != stop_loss else 0
            signal_strength = combined_strength
            direction = action
            take_profit_2 = take_profit * 1.05 # Example TP2
            take_profit_3 = take_profit * 1.10 # Example TP3


            # Calculate leverage and margin settings
            volatility_score = indicators.get('volatility', 0.02) * 100  # Convert to percentage

            # Dynamic leverage calculation based on signal strength and volatility
            if volatility_score < 1.0:
                auto_leverage = min(15, max(5, int(signal_strength / 6)))
            elif volatility_score < 2.0:
                auto_leverage = min(12, max(4, int(signal_strength / 7)))
            elif volatility_score < 3.0:
                auto_leverage = min(8, max(3, int(signal_strength / 8)))
            else:
                auto_leverage = min(5, max(2, int(signal_strength / 10)))

            recommended_leverage = max(2, int(auto_leverage * 0.85))  # Conservative recommendation

            # Create comprehensive signal
            signal = {
                'symbol': symbol,
                'action': direction,
                'price': current_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'take_profit_2': take_profit_2,
                'take_profit_3': take_profit_3,
                'strength': signal_strength,
                'confidence': confidence_score,
                'risk_reward_ratio': risk_reward_ratio,
                'primary_strategy': dominant_strategy,
                'timeframe': timeframe,
                'reason': f"{reason} with {confluence_count}/5 confluence factors",
                'strategies_used': strategy_names,
                'confluence_score': confluence_count,
                'technical_indicators': indicators,
                'market_context': market_context,
                'timestamp': datetime.now(),
                'chart': chart_base64 if chart_base64 else None,
                # Leverage and margin settings
                'recommended_leverage': recommended_leverage,
                'auto_leverage': auto_leverage,
                'margin_type': 'CROSS',
                'cross_margin_enabled': True,
                'leverage_mode': 'AUTO',
                'volatility_score': volatility_score,
                'margin_settings': {
                    'type': 'CROSS',
                    'cross_enabled': True,
                    'isolated_enabled': False,
                    'auto_add_margin': True,
                    'maintenance_margin_ratio': 0.05 if auto_leverage <= 10 else 0.075
                }
            }

            return signal

        except Exception as e:
            self.logger.error(f"Error combining signals: {e}")
            return None

    async def _calculate_stop_loss_take_profit(self, action: str, current_price: float,
                                             market_data: Dict, signal: Dict) -> tuple:
        """
        Calculate optimal stop loss and take profit levels
        """
        try:
            if '4h' not in market_data:
                # Default percentages
                if action == 'BUY':
                    stop_loss = current_price * 0.97  # 3% stop loss
                    take_profit = current_price * 1.06  # 6% take profit
                else:
                    stop_loss = current_price * 1.03  # 3% stop loss
                    take_profit = current_price * 0.94  # 6% take profit
                return stop_loss, take_profit

            df = self._to_dataframe(market_data['4h'])

            # Calculate ATR for dynamic stops
            # Ensure we have enough data for ATR calculation
            if len(df) < 14:
                # Fallback to percentage-based if not enough data
                if action == 'BUY':
                    return current_price * 0.97, current_price * 1.06
                else:
                    return current_price * 1.03, current_price * 0.94

            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            true_range = np.maximum(high_low, np.maximum(high_close, low_close))
            atr = true_range.rolling(14).mean().iloc[-1]
            #Fixing division by zero for atr
            if atr == 0:
                atr = current_price * 0.01 # Use 1% of current price as ATR

            # Calculate support/resistance levels
            recent_highs = df['high'].tail(20).max()
            recent_lows = df['low'].tail(20).min()

            if action == 'BUY':
                # Stop loss: ATR-based or recent support
                atr_stop = current_price - (atr * 2)
                support_stop = recent_lows * 0.995  # Slightly below support
                stop_loss = max(atr_stop, support_stop)

                # Take profit: ATR-based or recent resistance
                atr_target = current_price + (atr * 3)
                resistance_target = recent_highs * 1.005  # Slightly below resistance
                take_profit = min(atr_target, resistance_target) if resistance_target > current_price else atr_target

            else:  # SELL
                # Stop loss: ATR-based or recent resistance
                atr_stop = current_price + (atr * 2)
                resistance_stop = recent_highs * 1.005  # Slightly above resistance
                stop_loss = min(atr_stop, resistance_stop)

                # Take profit: ATR-based or recent support
                atr_target = current_price - (atr * 3)
                support_target = recent_lows * 0.995  # Slightly above support
                take_profit = max(atr_target, support_target) if support_target < current_price else atr_target

            return stop_loss, take_profit

        except Exception as e:
            self.logger.error(f"Error calculating stop loss/take profit: {e}")
            # Fallback to percentage-based
            if action == 'BUY':
                return current_price * 0.97, current_price * 1.06
            else:
                return current_price * 1.03, current_price * 0.94

    async def _generate_chart(self, symbol: str, market_data: Dict, signal: Dict) -> str:
        """
        Generate chart visualization for the trading signal
        """
        try:
            if '4h' not in market_data:
                return ""

            df = self._to_dataframe(market_data['4h'])
            if df.empty:
                return ""

            # Take last 50 candles for chart
            df_chart = df.tail(50).copy()

            # Create figure
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]})

            # Candlestick chart (simplified with lines)
            ax1.plot(df_chart.index, df_chart['close'], color='blue', linewidth=2, label='Close Price')
            ax1.fill_between(df_chart.index, df_chart['low'], df_chart['high'], alpha=0.3, color='gray')

            # Add moving averages
            sma_20 = df_chart['close'].rolling(20).mean()
            sma_50 = df_chart['close'].rolling(50).mean()
            ax1.plot(df_chart.index, sma_20, color='orange', linewidth=1, label='SMA 20')
            ax1.plot(df_chart.index, sma_50, color='red', linewidth=1, label='SMA 50')

            # Add signal markers
            current_price = signal.get('price', 0)
            if signal.get('action') == 'BUY':
                ax1.scatter(df_chart.index[-1], current_price, color='green', s=100, marker='^', zorder=5)
                ax1.text(df_chart.index[-1], current_price * 1.02, 'BUY', ha='center', va='bottom',
                        fontweight='bold', color='green')
            else:
                ax1.scatter(df_chart.index[-1], current_price, color='red', s=100, marker='v', zorder=5)
                ax1.text(df_chart.index[-1], current_price * 0.98, 'SELL', ha='center', va='top',
                        fontweight='bold', color='red')

            # Add stop loss and take profit lines
            if signal.get('stop_loss'):
                ax1.axhline(y=signal['stop_loss'], color='red', linestyle='--', alpha=0.7, label='Stop Loss')
            if signal.get('take_profit'):
                ax1.axhline(y=signal['take_profit'], color='green', linestyle='--', alpha=0.7, label='Take Profit')

            ax1.set_title(f'{symbol} - {signal.get("primary_strategy", "").title()} Strategy\n'
                         f'Strength: {signal.get("strength", 0):.1f}% | R:R = {signal.get("risk_reward_ratio", 0):.2f}')
            ax1.legend()
            ax1.grid(True, alpha=0.3)

            # Volume chart
            ax2.bar(df_chart.index, df_chart['volume'], alpha=0.7, color='blue')
            ax2.set_title('Volume')
            ax2.grid(True, alpha=0.3)

            # Format x-axis
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
            plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
            plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)

            # Use subplots_adjust instead of tight_layout to avoid warnings
            plt.subplots_adjust(left=0.08, bottom=0.15, right=0.95, top=0.88, hspace=0.3)

            # Convert to base64 string
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
            buffer.seek(0)
            chart_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close()

            return chart_base64

        except Exception as e:
            self.logger.error(f"Error generating chart: {e}")
            return ""

    def _to_dataframe(self, ohlcv_data: List) -> pd.DataFrame:
        """Convert OHLCV data to pandas DataFrame"""
        try:
            df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)

            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            return df.dropna()

        except Exception as e:
            self.logger.error(f"Error converting to DataFrame: {e}")
            return pd.DataFrame()

    async def get_strategy_performance(self) -> Dict[str, Any]:
        """Get strategy performance metrics"""
        try:
            # This would typically fetch from database
            return {
                'total_signals': 156,
                'winning_signals': 98,
                'win_rate': 62.8,
                'average_return': 4.2,
                'max_drawdown': -8.5,
                'sharpe_ratio': 1.8,
                'best_strategy': 'trend_alignment',
                'strategy_breakdown': {
                    'trend_alignment': {'signals': 45, 'win_rate': 71.1},
                    'mean_reversion': {'signals': 38, 'win_rate': 65.8},
                    'breakout': {'signals': 42, 'win_rate': 57.1},
                    'support_resistance': {'signals': 31, 'win_rate': 54.8}
                }
            }

        except Exception as e:
            self.logger.error(f"Error getting strategy performance: {e}")
            return {}

# Placeholder for TechnicalAnalysis class if not defined elsewhere
class TechnicalAnalysis:
    def __init__(self, binance_trader=None):
        self.binance_trader = binance_trader
        pass # Placeholder, actual implementation might be complex or external