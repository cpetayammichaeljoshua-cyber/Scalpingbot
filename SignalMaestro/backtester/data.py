#!/usr/bin/env python3
"""
DataProvider Interface - Handles market data with CCXT, CSV, and synthetic fallbacks
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Protocol
from abc import ABC, abstractmethod
import logging

class DataProvider(Protocol):
    """Data provider interface"""
    
    @abstractmethod
    async def get_ohlcv_data(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Get OHLCV data with ATR%, volume ratio, trend indicators"""
        pass

class SyntheticDataProvider:
    """Synthetic market data generator calibrated for crypto markets"""
    
    def __init__(self, seed: int = 42):
        self.logger = logging.getLogger(__name__)
        np.random.seed(seed)
        
        # Crypto market calibration
        self.crypto_specs = {
            'BTCUSDT': {'base_price': 27500, 'base_vol': 0.8, 'trend_bias': 0.6},
            'ETHUSDT': {'base_price': 1650, 'base_vol': 1.2, 'trend_bias': 0.5},
            'BNBUSDT': {'base_price': 210, 'base_vol': 1.5, 'trend_bias': 0.4},
            'ADAUSDT': {'base_price': 0.245, 'base_vol': 2.1, 'trend_bias': 0.3},
            'SOLUSDT': {'base_price': 23.5, 'base_vol': 2.8, 'trend_bias': 0.7},
            'XRPUSDT': {'base_price': 0.52, 'base_vol': 1.9, 'trend_bias': 0.4},
            'DOTUSDT': {'base_price': 4.2, 'base_vol': 2.3, 'trend_bias': 0.5},
            'MATICUSDT': {'base_price': 0.75, 'base_vol': 2.6, 'trend_bias': 0.6},
            'UNIUSDT': {'base_price': 10.2, 'base_vol': 1.8, 'trend_bias': 0.5},
            'LINKUSDT': {'base_price': 7.8, 'base_vol': 2.0, 'trend_bias': 0.4},
        }
    
    async def get_ohlcv_data(self, symbol: str, timeframe: str = '5m', limit: int = 2016) -> pd.DataFrame:
        """
        Generate synthetic OHLCV data with realistic crypto market characteristics
        2016 candles = 7 days of 5m data
        """
        
        try:
            if symbol not in self.crypto_specs:
                # Use BTC as default
                spec = self.crypto_specs['BTCUSDT']
            else:
                spec = self.crypto_specs[symbol]
            
            # Generate time series
            end_time = datetime.now()
            if timeframe == '5m':
                interval_minutes = 5
            elif timeframe == '15m':
                interval_minutes = 15
            elif timeframe == '1h':
                interval_minutes = 60
            else:
                interval_minutes = 5  # Default to 5m
            
            timestamps = [
                end_time - timedelta(minutes=interval_minutes * i) 
                for i in range(limit, 0, -1)
            ]
            
            # Generate realistic price movement
            base_price = spec['base_price']
            base_volatility = spec['base_vol'] / 100  # Convert to decimal
            trend_bias = spec['trend_bias']
            
            # Create price series with trend and volatility cycles
            prices = []
            current_price = base_price
            
            for i, timestamp in enumerate(timestamps):
                # Add market cycles (daily and weekly patterns)
                hour = timestamp.hour
                day_cycle = np.sin(hour * np.pi / 12) * 0.02  # Daily volatility cycle
                week_cycle = np.sin(i * np.pi / (7 * 24 * 12)) * 0.03  # Weekly trend cycle
                
                # Random walk with trend bias
                trend_factor = (trend_bias - 0.5) * 0.001  # Small trend bias
                volatility_factor = base_volatility * (1 + day_cycle)
                
                price_change = np.random.normal(trend_factor, volatility_factor)
                current_price *= (1 + price_change)
                
                # Prevent extreme price movements
                current_price = max(base_price * 0.7, min(base_price * 1.4, current_price))
                prices.append(current_price)
            
            # Generate OHLCV from price series
            ohlcv_data = []
            for i, (timestamp, price) in enumerate(zip(timestamps, prices)):
                # Generate realistic candle ranges
                volatility = base_volatility * np.random.uniform(0.5, 2.0)
                
                # Open price (previous close or current price for first candle)
                if i == 0:
                    open_price = price
                else:
                    open_price = ohlcv_data[-1]['close']
                
                # Generate high/low based on volatility
                price_range = open_price * volatility
                high = max(open_price, price) + np.random.uniform(0, price_range * 0.5)
                low = min(open_price, price) - np.random.uniform(0, price_range * 0.5)
                
                # Ensure high >= low and price is within range
                high = max(high, low + open_price * 0.001)  # Minimum spread
                low = min(low, high - open_price * 0.001)
                
                # Close price with some noise
                close = price * np.random.uniform(0.998, 1.002)
                close = max(low, min(high, close))  # Ensure close is within range
                
                # Volume (higher during volatile periods)
                base_volume = np.random.uniform(1000000, 5000000)  # Base volume
                volatility_volume_factor = 1 + (volatility / base_volatility - 1) * 2
                volume = base_volume * volatility_volume_factor * np.random.uniform(0.5, 2.0)
                
                ohlcv_data.append({
                    'timestamp': timestamp,
                    'open': open_price,
                    'high': high,
                    'low': low,
                    'close': close,
                    'volume': volume
                })
            
            # Convert to DataFrame
            df = pd.DataFrame(ohlcv_data)
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
            
            # Calculate technical indicators
            df = self._add_technical_indicators(df)
            
            self.logger.info(f"Generated {len(df)} synthetic candles for {symbol}")
            return df
            
        except Exception as e:
            self.logger.error(f"Error generating synthetic data for {symbol}: {e}")
            return pd.DataFrame()
    
    def _add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add ATR%, volume ratio, and trend indicators"""
        
        try:
            # True Range and ATR
            df['prev_close'] = df['close'].shift(1)
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = abs(df['high'] - df['prev_close'])
            df['tr3'] = abs(df['low'] - df['prev_close'])
            df['true_range'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            
            # ATR (14 periods)
            df['atr'] = df['true_range'].rolling(14).mean()
            df['atr_percentage'] = (df['atr'] / df['close']) * 100
            
            # Volume ratio (current vs 20-period average)
            df['volume_avg'] = df['volume'].rolling(20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_avg']
            
            # Trend indicators (EMAs)
            df['ema_8'] = df['close'].ewm(span=8).mean()
            df['ema_21'] = df['close'].ewm(span=21).mean()
            df['ema_50'] = df['close'].ewm(span=50).mean()
            
            # Trend strength (0-1 scale)
            df['ema_alignment'] = (
                (df['ema_8'] > df['ema_21']) & (df['ema_21'] > df['ema_50'])
            ).astype(int)
            
            # Calculate trend strength based on EMA distances
            ema_spread = abs(df['ema_8'] - df['ema_50']) / df['close']
            df['trend_strength'] = np.clip(ema_spread * 50, 0, 1)  # Scale to 0-1
            
            # Clean up intermediate columns
            cols_to_drop = ['prev_close', 'tr1', 'tr2', 'tr3', 'true_range', 'volume_avg']
            df.drop(columns=[col for col in cols_to_drop if col in df.columns], inplace=True)
            
            # Fill NaN values
            df['atr_percentage'] = df['atr_percentage'].fillna(df['atr_percentage'].mean())
            df['volume_ratio'] = df['volume_ratio'].fillna(1.0)
            df['trend_strength'] = df['trend_strength'].fillna(0.5)
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error adding technical indicators: {e}")
            return df

class CCXTDataProvider:
    """CCXT-based data provider for real market data"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.exchange = None
    
    async def get_ohlcv_data(self, symbol: str, timeframe: str = '5m', limit: int = 2016) -> pd.DataFrame:
        """Get real OHLCV data from Binance (falls back to synthetic if fails)"""
        
        try:
            import ccxt.async_support as ccxt
            
            if not self.exchange:
                self.exchange = ccxt.binance({
                    'apiKey': 'dummy',  # Public data doesn't need real keys
                    'secret': 'dummy',
                    'sandbox': False,
                    'options': {'defaultType': 'future'}
                })
                await self.exchange.load_markets()
            
            # Fetch OHLCV data
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            if not ohlcv:
                raise Exception("No data returned from exchange")
            
            # Convert to DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # Add technical indicators
            synthetic_provider = SyntheticDataProvider()
            df = synthetic_provider._add_technical_indicators(df)
            
            self.logger.info(f"Fetched {len(df)} real candles for {symbol}")
            return df
            
        except Exception as e:
            self.logger.warning(f"CCXT data fetch failed for {symbol}: {e}, falling back to synthetic")
            # Fallback to synthetic data
            synthetic_provider = SyntheticDataProvider()
            return await synthetic_provider.get_ohlcv_data(symbol, timeframe, limit)
        finally:
            if self.exchange:
                await self.exchange.close()

async def get_market_data(symbol: str, timeframe: str = '5m', limit: int = 2016, 
                         use_real_data: bool = True) -> pd.DataFrame:
    """
    Get market data with automatic fallback
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
        timeframe: Candle timeframe ('5m', '15m', '1h')
        limit: Number of candles (2016 = 7 days of 5m data)
        use_real_data: Try real data first, fallback to synthetic
    """
    
    if use_real_data:
        provider = CCXTDataProvider()
    else:
        provider = SyntheticDataProvider()
    
    return await provider.get_ohlcv_data(symbol, timeframe, limit)