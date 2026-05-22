
#!/usr/bin/env python3
"""
Enhanced Binance Futures Signal Bot
Dynamically perfectly advanced flexible adaptable comprehensive
Fetches all Binance Futures markets and sends optimized signals to channel
"""

import asyncio
import logging
import aiohttp
import os
import json
import hmac
import hashlib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import traceback
import time
import signal
import sys
import atexit
from pathlib import Path

# Technical Analysis
try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    CHART_AVAILABLE = True
except ImportError:
    CHART_AVAILABLE = False

from io import BytesIO
import base64

class EnhancedBinanceFuturesSignalBot:
    """Enhanced Binance Futures Signal Bot with comprehensive market scanning"""

    def __init__(self):
        self.logger = self._setup_logging()
        
        # Process management
        self.pid_file = Path("enhanced_futures_bot.pid")
        self.shutdown_requested = False
        
        # Setup signal handlers
        self._setup_signal_handlers()
        atexit.register(self._cleanup_on_exit)
        
        # Telegram configuration
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        
        # Target configuration
        self.admin_chat_id = None
        self.target_channel = "@SignalTactics"
        
        # Binance Futures API endpoints
        self.futures_base_url = "https://fapi.binance.com"
        self.api_key = os.getenv('BINANCE_API_KEY', '')
        self.api_secret = os.getenv('BINANCE_API_SECRET', '')
        
        # All available futures symbols (will be fetched dynamically)
        self.futures_symbols = []
        self.active_symbols = []  # Filtered symbols with good volume
        
        # Trading parameters optimized for futures
        self.timeframes = ['1m', '3m', '5m', '15m', '1h', '4h']
        self.min_volume_usdt = 1000000  # Minimum 1M USDT 24h volume
        self.min_signal_strength = 75  # Higher threshold for futures
        self.max_signals_per_hour = 8  # Increased for futures markets
        self.leverage_range = (10, 50)  # Leverage range for futures
        
        # Signal tracking
        self.signal_counter = 0
        self.last_signal_time = {}
        self.min_signal_interval = 300  # 5 minutes between signals for same symbol
        
        # Performance tracking
        self.performance_stats = {
            'total_signals': 0,
            'profitable_signals': 0,
            'win_rate': 0.0,
            'total_profit': 0.0,
            'average_rrr': 0.0
        }
        
        # Bot status
        self.running = True
        self.last_heartbeat = datetime.now()
        
        self.logger.info("Enhanced Binance Futures Signal Bot initialized")
        self._write_pid_file()

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.info(f"🛑 Received signal {signum}, shutting down...")
            self.shutdown_requested = True
            self.running = False

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    def _write_pid_file(self):
        """Write process ID to file"""
        try:
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))
            self.logger.info(f"📝 PID file written: {self.pid_file}")
        except Exception as e:
            self.logger.warning(f"Could not write PID file: {e}")

    def _cleanup_on_exit(self):
        """Cleanup resources on exit"""
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
                self.logger.info("🧹 PID file cleaned up")
        except Exception as e:
            self.logger.warning(f"Cleanup error: {e}")

    def _setup_logging(self):
        """Setup logging system"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - FUTURES_BOT - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_dir / "enhanced_futures_bot.log"),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger(__name__)

    async def send_telegram_message(self, chat_id: str, text: str, parse_mode='Markdown') -> bool:
        """Send message to Telegram with enhanced error handling"""
        max_retries = 5
        
        for attempt in range(max_retries):
            try:
                url = f"{self.base_url}/sendMessage"
                data = {
                    'chat_id': chat_id,
                    'text': text,
                    'parse_mode': parse_mode,
                    'disable_web_page_preview': True
                }
                
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                    async with session.post(url, json=data) as response:
                        if response.status == 200:
                            result = await response.json()
                            if result.get('ok'):
                                self.logger.info(f"✅ Message sent to {chat_id}")
                                return True
                        
                        error_data = await response.json()
                        self.logger.error(f"❌ Send failed (attempt {attempt + 1}): {error_data}")
                        
            except Exception as e:
                self.logger.error(f"❌ Send error (attempt {attempt + 1}): {e}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        
        return False

    async def fetch_all_futures_symbols(self) -> List[str]:
        """Fetch all available Binance Futures symbols"""
        try:
            url = f"{self.futures_base_url}/fapi/v1/exchangeInfo"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        symbols = []
                        
                        for symbol_info in data.get('symbols', []):
                            if (symbol_info.get('status') == 'TRADING' and 
                                symbol_info.get('contractType') == 'PERPETUAL' and
                                symbol_info.get('quoteAsset') == 'USDT'):
                                symbols.append(symbol_info['symbol'])
                        
                        self.logger.info(f"📊 Fetched {len(symbols)} USDT perpetual futures symbols")
                        return symbols
                        
            return []
            
        except Exception as e:
            self.logger.error(f"Error fetching futures symbols: {e}")
            return []

    async def filter_active_symbols(self, symbols: List[str]) -> List[str]:
        """Filter symbols by volume and activity"""
        try:
            url = f"{self.futures_base_url}/fapi/v1/ticker/24hr"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        tickers = await response.json()
                        active_symbols = []
                        
                        for ticker in tickers:
                            symbol = ticker['symbol']
                            if symbol in symbols:
                                volume_usdt = float(ticker.get('quoteVolume', 0))
                                price_change = abs(float(ticker.get('priceChangePercent', 0)))
                                
                                # Filter by volume and volatility
                                if (volume_usdt >= self.min_volume_usdt and 
                                    price_change >= 0.5):  # At least 0.5% daily movement
                                    active_symbols.append({
                                        'symbol': symbol,
                                        'volume': volume_usdt,
                                        'change': price_change,
                                        'price': float(ticker.get('lastPrice', 0))
                                    })
                        
                        # Sort by volume
                        active_symbols.sort(key=lambda x: x['volume'], reverse=True)
                        
                        # Take top 100 most active symbols
                        filtered_symbols = [s['symbol'] for s in active_symbols[:100]]
                        
                        self.logger.info(f"📈 Filtered to {len(filtered_symbols)} active symbols")
                        return filtered_symbols
                        
            return symbols[:50]  # Fallback to first 50 symbols
            
        except Exception as e:
            self.logger.error(f"Error filtering symbols: {e}")
            return symbols[:50]

    async def get_futures_klines(self, symbol: str, interval: str, limit: int = 100) -> Optional[pd.DataFrame]:
        """Get futures klines data"""
        try:
            url = f"{self.futures_base_url}/fapi/v1/klines"
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        df = pd.DataFrame(data, columns=[
                            'timestamp', 'open', 'high', 'low', 'close', 'volume',
                            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                            'taker_buy_quote', 'ignore'
                        ])
                        
                        # Convert to proper types
                        for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume']:
                            df[col] = pd.to_numeric(df[col])
                        
                        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                        df.set_index('timestamp', inplace=True)
                        
                        return df
                        
            return None
            
        except Exception as e:
            self.logger.error(f"Error fetching klines for {symbol}: {e}")
            return None

    def calculate_futures_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate advanced futures trading indicators"""
        try:
            if df.empty or len(df) < 50:
                return {}
            
            indicators = {}
            
            # Price data
            high = df['high'].values
            low = df['low'].values
            close = df['close'].values
            volume = df['volume'].values
            
            # 1. Enhanced SuperTrend for futures
            hl2 = (high + low) / 2
            atr = self._calculate_atr(high, low, close, 10)
            
            # Dynamic multiplier based on volatility
            volatility = np.std(close[-20:]) / np.mean(close[-20:])
            multiplier = 2.0 + (volatility * 8)  # Adjusted for futures
            
            upper_band = hl2 + (multiplier * atr)
            lower_band = hl2 - (multiplier * atr)
            
            # SuperTrend calculation
            supertrend = np.zeros(len(close))
            supertrend_direction = np.zeros(len(close))
            
            for i in range(1, len(close)):
                if close[i] <= lower_band[i]:
                    supertrend[i] = upper_band[i]
                    supertrend_direction[i] = -1
                elif close[i] >= upper_band[i]:
                    supertrend[i] = lower_band[i]
                    supertrend_direction[i] = 1
                else:
                    supertrend[i] = supertrend[i-1]
                    supertrend_direction[i] = supertrend_direction[i-1]
            
            indicators['supertrend'] = supertrend[-1]
            indicators['supertrend_direction'] = supertrend_direction[-1]
            
            # 2. EMA Cross System (optimized for futures)
            ema_12 = self._calculate_ema(close, 12)
            ema_26 = self._calculate_ema(close, 26)
            ema_50 = self._calculate_ema(close, 50)
            
            indicators['ema_12'] = ema_12[-1]
            indicators['ema_26'] = ema_26[-1]
            indicators['ema_50'] = ema_50[-1]
            indicators['ema_bullish'] = ema_12[-1] > ema_26[-1] > ema_50[-1]
            indicators['ema_bearish'] = ema_12[-1] < ema_26[-1] < ema_50[-1]
            
            # 3. RSI with futures-optimized settings
            rsi = self._calculate_rsi(close, 14)
            indicators['rsi'] = rsi[-1]
            indicators['rsi_oversold'] = rsi[-1] < 25  # More extreme for futures
            indicators['rsi_overbought'] = rsi[-1] > 75
            
            # 4. MACD with histogram
            macd_line, macd_signal, macd_hist = self._calculate_macd(close, 12, 26, 9)
            indicators['macd'] = macd_line[-1]
            indicators['macd_signal'] = macd_signal[-1]
            indicators['macd_histogram'] = macd_hist[-1]
            indicators['macd_bullish'] = macd_line[-1] > macd_signal[-1] and macd_hist[-1] > 0
            
            # 5. Volume analysis for futures
            avg_volume = np.mean(volume[-20:])
            if avg_volume > 0:
                indicators['volume_ratio'] = volume[-1] / avg_volume
                indicators['volume_surge'] = volume[-1] > avg_volume * 2.0  # Higher threshold
            else:
                indicators['volume_ratio'] = 1.0
                indicators['volume_surge'] = False
            
            # 6. Bollinger Bands
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(close, 20, 2)
            indicators['bb_upper'] = bb_upper[-1]
            indicators['bb_middle'] = bb_middle[-1]
            indicators['bb_lower'] = bb_lower[-1]
            indicators['bb_squeeze'] = (bb_upper[-1] - bb_lower[-1]) < (bb_upper[-5] - bb_lower[-5])
            
            # 7. Support and Resistance for futures
            swing_highs = self._find_swing_points(high, 'high')
            swing_lows = self._find_swing_points(low, 'low')
            indicators['resistance_level'] = swing_highs[-1] if len(swing_highs) > 0 else high[-1]
            indicators['support_level'] = swing_lows[-1] if len(swing_lows) > 0 else low[-1]
            
            # 8. Momentum indicators
            indicators['momentum'] = (close[-1] - close[-10]) / close[-10] * 100
            indicators['price_velocity'] = (close[-1] - close[-3]) / close[-3] * 100
            
            # 9. Current price info
            indicators['current_price'] = close[-1]
            indicators['price_change'] = (close[-1] - close[-2]) / close[-2] * 100
            
            return indicators
            
        except Exception as e:
            self.logger.error(f"Error calculating indicators: {e}")
            return {}

    def _calculate_atr(self, high, low, close, period):
        """Calculate Average True Range"""
        try:
            if TALIB_AVAILABLE:
                return talib.ATR(high, low, close, timeperiod=period)
            else:
                # Manual ATR calculation
                tr1 = high - low
                tr2 = np.abs(high - np.roll(close, 1))
                tr3 = np.abs(low - np.roll(close, 1))
                tr = np.maximum(tr1, np.maximum(tr2, tr3))
                tr[0] = tr1[0]  # First value
                return pd.Series(tr).rolling(window=period).mean().values
        except:
            return np.ones(len(high)) * 0.01

    def _calculate_ema(self, prices, period):
        """Calculate Exponential Moving Average"""
        try:
            if TALIB_AVAILABLE:
                return talib.EMA(prices, timeperiod=period)
            else:
                return pd.Series(prices).ewm(span=period).mean().values
        except:
            return np.ones(len(prices)) * prices[-1]

    def _calculate_rsi(self, prices, period):
        """Calculate RSI"""
        try:
            if TALIB_AVAILABLE:
                return talib.RSI(prices, timeperiod=period)
            else:
                delta = np.diff(prices)
                gain = np.where(delta > 0, delta, 0)
                loss = np.where(delta < 0, -delta, 0)
                avg_gain = pd.Series(gain).rolling(window=period).mean()
                avg_loss = pd.Series(loss).rolling(window=period).mean()
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
                return np.concatenate([[50], rsi.values])  # Prepend initial value
        except:
            return np.ones(len(prices)) * 50

    def _calculate_macd(self, prices, fast=12, slow=26, signal=9):
        """Calculate MACD"""
        try:
            if TALIB_AVAILABLE:
                macd, signal_line, histogram = talib.MACD(prices, fastperiod=fast, slowperiod=slow, signalperiod=signal)
                return macd, signal_line, histogram
            else:
                ema_fast = pd.Series(prices).ewm(span=fast).mean()
                ema_slow = pd.Series(prices).ewm(span=slow).mean()
                macd_line = ema_fast - ema_slow
                signal_line = macd_line.ewm(span=signal).mean()
                histogram = macd_line - signal_line
                return macd_line.values, signal_line.values, histogram.values
        except:
            length = len(prices)
            return np.zeros(length), np.zeros(length), np.zeros(length)

    def _calculate_bollinger_bands(self, prices, period, std_dev):
        """Calculate Bollinger Bands"""
        try:
            if TALIB_AVAILABLE:
                upper, middle, lower = talib.BBANDS(prices, timeperiod=period, nbdevup=std_dev, nbdevdn=std_dev)
                return upper, middle, lower
            else:
                sma = pd.Series(prices).rolling(window=period).mean()
                std = pd.Series(prices).rolling(window=period).std()
                upper = sma + (std * std_dev)
                lower = sma - (std * std_dev)
                return upper.values, sma.values, lower.values
        except:
            length = len(prices)
            return np.ones(length) * prices[-1], np.ones(length) * prices[-1], np.ones(length) * prices[-1]

    def _find_swing_points(self, data, point_type, window=5):
        """Find swing highs/lows"""
        try:
            swing_points = []
            for i in range(window, len(data) - window):
                if point_type == 'high':
                    if data[i] == max(data[i-window:i+window+1]):
                        swing_points.append(data[i])
                else:
                    if data[i] == min(data[i-window:i+window+1]):
                        swing_points.append(data[i])
            return swing_points if swing_points else [data[-1]]
        except:
            return [data[-1]]

    def generate_futures_signal(self, symbol: str, indicators: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate futures trading signal"""
        try:
            if not indicators:
                return None
            
            signal_strength = 0
            direction = None
            reasons = []
            
            # SuperTrend signal
            if indicators.get('supertrend_direction') == 1:
                signal_strength += 25
                reasons.append("SuperTrend bullish")
                direction = 'LONG'
            elif indicators.get('supertrend_direction') == -1:
                signal_strength += 25
                reasons.append("SuperTrend bearish")
                direction = 'SHORT'
            
            # EMA alignment
            if indicators.get('ema_bullish'):
                signal_strength += 20
                reasons.append("EMA alignment bullish")
                if direction != 'SHORT':
                    direction = 'LONG'
            elif indicators.get('ema_bearish'):
                signal_strength += 20
                reasons.append("EMA alignment bearish")
                if direction != 'LONG':
                    direction = 'SHORT'
            
            # RSI confirmation
            if direction == 'LONG' and indicators.get('rsi_oversold'):
                signal_strength += 15
                reasons.append("RSI oversold")
            elif direction == 'SHORT' and indicators.get('rsi_overbought'):
                signal_strength += 15
                reasons.append("RSI overbought")
            
            # MACD confirmation
            if direction == 'LONG' and indicators.get('macd_bullish'):
                signal_strength += 15
                reasons.append("MACD bullish")
            elif direction == 'SHORT' and not indicators.get('macd_bullish'):
                signal_strength += 15
                reasons.append("MACD bearish")
            
            # Volume confirmation
            if indicators.get('volume_surge'):
                signal_strength += 10
                reasons.append("Volume surge")
            
            # Bollinger Bands
            current_price = indicators.get('current_price', 0)
            bb_upper = indicators.get('bb_upper', 0)
            bb_lower = indicators.get('bb_lower', 0)
            
            if direction == 'LONG' and current_price < bb_lower:
                signal_strength += 10
                reasons.append("Below BB lower")
            elif direction == 'SHORT' and current_price > bb_upper:
                signal_strength += 10
                reasons.append("Above BB upper")
            
            # Check minimum signal strength
            if signal_strength < self.min_signal_strength or not direction:
                return None
            
            # Calculate dynamic leverage based on volatility
            volatility = abs(indicators.get('price_velocity', 1))
            if volatility > 3:
                leverage = self.leverage_range[0]  # Lower leverage for high volatility
            elif volatility < 1:
                leverage = self.leverage_range[1]  # Higher leverage for low volatility
            else:
                leverage = int(self.leverage_range[0] + (self.leverage_range[1] - self.leverage_range[0]) * (2 - volatility) / 2)
            
            # Calculate stop loss and take profit
            entry_price = current_price
            atr_estimate = abs(indicators.get('momentum', 1)) * 0.01 * entry_price
            
            if direction == 'LONG':
                stop_loss = entry_price - (atr_estimate * 2)
                take_profit_1 = entry_price + (atr_estimate * 3)
                take_profit_2 = entry_price + (atr_estimate * 5)
                take_profit_3 = entry_price + (atr_estimate * 8)
            else:
                stop_loss = entry_price + (atr_estimate * 2)
                take_profit_1 = entry_price - (atr_estimate * 3)
                take_profit_2 = entry_price - (atr_estimate * 5)
                take_profit_3 = entry_price - (atr_estimate * 8)
            
            # Calculate risk/reward ratio
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit_1 - entry_price)
            rrr = reward / risk if risk > 0 else 3.0
            
            signal = {
                'symbol': symbol,
                'direction': direction,
                'signal_strength': signal_strength,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit_1': take_profit_1,
                'take_profit_2': take_profit_2,
                'take_profit_3': take_profit_3,
                'leverage': leverage,
                'risk_reward_ratio': rrr,
                'reasons': reasons,
                'timestamp': datetime.now().isoformat(),
                'timeframe': '5m',
                'market_type': 'futures'
            }
            
            return signal
            
        except Exception as e:
            self.logger.error(f"Error generating signal for {symbol}: {e}")
            return None

    def format_futures_signal(self, signal: Dict[str, Any]) -> str:
        """Format futures signal for Telegram"""
        try:
            symbol = signal['symbol']
            direction = signal['direction']
            entry_price = signal['entry_price']
            stop_loss = signal['stop_loss']
            tp1 = signal['take_profit_1']
            tp2 = signal['take_profit_2']
            tp3 = signal['take_profit_3']
            leverage = signal['leverage']
            strength = signal['signal_strength']
            rrr = signal['risk_reward_ratio']
            reasons = ', '.join(signal['reasons'][:3])
            
            # Direction styling
            if direction == 'LONG':
                emoji = "🟢"
                direction_emoji = "🚀"
                action_text = "💎 FUTURES LONG SIGNAL"
                color_bar = "🟢🟢🟢🟢🟢"
            else:
                emoji = "🔴"
                direction_emoji = "📉"
                action_text = "💎 FUTURES SHORT SIGNAL"
                color_bar = "🔴🔴🔴🔴🔴"
            
            # Calculate percentages
            risk_percent = abs((entry_price - stop_loss) / entry_price * 100)
            profit_percent_1 = abs((tp1 - entry_price) / entry_price * 100)
            
            timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S UTC')
            
            formatted_signal = f"""
{color_bar}
{emoji} **{action_text}** {direction_emoji}

🏷️ **Pair:** `{symbol}`
💰 **Entry:** `${entry_price:.4f}`
⚡ **Leverage:** `{leverage}x`

🛑 **Stop Loss:** `${stop_loss:.4f}` (-{risk_percent:.1f}%)
🎯 **TP1:** `${tp1:.4f}` (+{profit_percent_1:.1f}%) - 50%
🎯 **TP2:** `${tp2:.4f}` - 30%
🎯 **TP3:** `${tp3:.4f}` - 20%

📊 **ANALYSIS:**
💪 **Signal Strength:** `{strength:.0f}%`
⚖️ **Risk/Reward:** `1:{rrr:.1f}`
🧠 **Strategy:** `Futures Multi-Strategy`
📈 **Confluence:** `{reasons}`

💰 **MAX PROFIT:** `+{profit_percent_1 * 2:.1f}%`
🛡️ **MAX RISK:** `-{risk_percent:.1f}%`

⏰ **Generated:** `{timestamp}`
🔢 **Signal #{self.signal_counter + 1}`

{color_bar}
*🤖 AI-Powered Futures Analysis*
*📢 @SignalTactics - Premium Futures Signals*
*⚡ Real-Time Market Scanning*
            """
            
            return formatted_signal.strip()
            
        except Exception as e:
            self.logger.error(f"Error formatting signal: {e}")
            return "Error formatting signal"

    async def scan_futures_markets(self) -> Optional[Dict[str, Any]]:
        """Scan all futures markets for signals"""
        try:
            if not self.active_symbols:
                # Fetch symbols if not already done
                all_symbols = await self.fetch_all_futures_symbols()
                self.active_symbols = await self.filter_active_symbols(all_symbols)
            
            best_signals = []
            
            # Scan top symbols
            scan_limit = min(50, len(self.active_symbols))  # Scan top 50 symbols
            
            for symbol in self.active_symbols[:scan_limit]:
                try:
                    # Check rate limiting
                    now = datetime.now()
                    if symbol in self.last_signal_time:
                        time_diff = (now - self.last_signal_time[symbol]).total_seconds()
                        if time_diff < self.min_signal_interval:
                            continue
                    
                    # Get market data
                    df = await self.get_futures_klines(symbol, '5m', 100)
                    if df is None or len(df) < 50:
                        continue
                    
                    # Calculate indicators
                    indicators = self.calculate_futures_indicators(df)
                    if not indicators:
                        continue
                    
                    # Generate signal
                    signal = self.generate_futures_signal(symbol, indicators)
                    if signal and signal['signal_strength'] >= self.min_signal_strength:
                        best_signals.append(signal)
                        self.last_signal_time[symbol] = now
                    
                    # Small delay to avoid rate limits
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    self.logger.error(f"Error scanning {symbol}: {e}")
                    continue
            
            # Sort by signal strength and return best signal
            if best_signals:
                best_signals.sort(key=lambda x: x['signal_strength'], reverse=True)
                return best_signals[0]
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error scanning futures markets: {e}")
            return None

    async def send_futures_signal(self, signal: Dict[str, Any]) -> bool:
        """Send futures signal to channel"""
        try:
            formatted_signal = self.format_futures_signal(signal)
            success = await self.send_telegram_message(self.target_channel, formatted_signal)
            
            if success:
                self.signal_counter += 1
                self.performance_stats['total_signals'] += 1
                
                # Log signal
                self.logger.info(f"🚀 Futures signal #{self.signal_counter} sent: {signal['symbol']} {signal['direction']}")
                
                # Send admin notification
                if self.admin_chat_id:
                    admin_msg = f"✅ **Futures Signal #{self.signal_counter} Sent**\n\nSymbol: {signal['symbol']}\nDirection: {signal['direction']}\nStrength: {signal['signal_strength']:.0f}%"
                    await self.send_telegram_message(self.admin_chat_id, admin_msg)
                
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error sending futures signal: {e}")
            return False

    async def main_futures_loop(self):
        """Main futures scanning and signal generation loop"""
        self.logger.info("🚀 Starting Enhanced Binance Futures Signal Bot...")
        
        # Send startup message
        startup_msg = "🚀 **Enhanced Binance Futures Signal Bot ONLINE**\n\n✅ Scanning all USDT perpetual futures\n⚡ Advanced multi-strategy analysis\n🎯 Dynamic leverage optimization\n📊 Real-time market monitoring"
        await self.send_telegram_message(self.target_channel, startup_msg)
        
        # Initial symbol fetch
        try:
            all_symbols = await self.fetch_all_futures_symbols()
            self.active_symbols = await self.filter_active_symbols(all_symbols)
            self.logger.info(f"📊 Monitoring {len(self.active_symbols)} active futures symbols")
        except Exception as e:
            self.logger.error(f"Error fetching initial symbols: {e}")
        
        # Main loop
        signals_this_hour = []
        last_hour = datetime.now().hour
        
        while self.running and not self.shutdown_requested:
            try:
                current_hour = datetime.now().hour
                
                # Reset hourly counter
                if current_hour != last_hour:
                    signals_this_hour = []
                    last_hour = current_hour
                    
                    # Refresh symbols every hour
                    try:
                        all_symbols = await self.fetch_all_futures_symbols()
                        self.active_symbols = await self.filter_active_symbols(all_symbols)
                        self.logger.info(f"🔄 Refreshed symbols: {len(self.active_symbols)} active")
                    except Exception as e:
                        self.logger.error(f"Error refreshing symbols: {e}")
                
                # Check signal limit
                if len(signals_this_hour) >= self.max_signals_per_hour:
                    self.logger.info("⏳ Hourly signal limit reached, waiting...")
                    await asyncio.sleep(300)  # Wait 5 minutes
                    continue
                
                # Scan markets for signals
                signal = await self.scan_futures_markets()
                
                if signal:
                    success = await self.send_futures_signal(signal)
                    if success:
                        signals_this_hour.append(datetime.now())
                        
                        # Wait after sending signal
                        await asyncio.sleep(300)  # 5 minutes between signals
                    else:
                        await asyncio.sleep(60)  # 1 minute on send failure
                else:
                    # No signal found, wait shorter time
                    await asyncio.sleep(120)  # 2 minutes
                
                # Heartbeat
                self.last_heartbeat = datetime.now()
                
                # Status log every 30 minutes
                if self.signal_counter % 6 == 0 and self.signal_counter > 0:
                    self.logger.info(f"📊 Status: {self.signal_counter} signals sent, monitoring {len(self.active_symbols)} symbols")
                
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(60)  # Recovery delay

    async def start_bot(self):
        """Start the futures signal bot"""
        try:
            await self.main_futures_loop()
        except KeyboardInterrupt:
            self.logger.info("🛑 Bot stopped by user")
        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            traceback.print_exc()
        finally:
            self.running = False
            self.logger.info("🏁 Enhanced Binance Futures Signal Bot stopped")

async def main():
    """Main function"""
    bot = EnhancedBinanceFuturesSignalBot()
    await bot.start_bot()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Enhanced Binance Futures Signal Bot stopped")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        traceback.print_exc()
