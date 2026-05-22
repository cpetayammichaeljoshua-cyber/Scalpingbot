"""
Binance Data Fetcher for ETH/USDT

Fetches real-time and historical OHLCV data from Binance.
Supports both REST API and WebSocket for real-time updates.
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Callable, Any, Union
import pandas as pd
from pandas import DataFrame
import numpy as np

BINANCE_AVAILABLE = False
BinanceAPIException: Any = Exception

try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
    BINANCE_AVAILABLE = True
except ImportError:
    Client = None

CCXT_AVAILABLE = False

try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    ccxt = None

logger = logging.getLogger(__name__)


class BinanceDataFetcher:
    """
    Fetches OHLCV data from Binance for ETH/USDT
    
    Supports:
    - Historical data fetching
    - Real-time candle updates
    - Heikin Ashi transformation
    - Rate limiting and error handling
    """
    
    INTERVAL_MAP = {
        '1m': '1m',
        '3m': '3m',
        '5m': '5m',
        '15m': '15m',
        '30m': '30m',
        '1h': '1h',
        '4h': '4h',
        '1d': '1d'
    }
    
    INTERVAL_MINUTES = {
        '1m': 1,
        '3m': 3,
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '1h': 60,
        '4h': 240,
        '1d': 1440
    }
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None,
                 symbol: str = 'ETHUSDT', interval: str = '5m'):
        """
        Initialize Binance Data Fetcher
        
        Args:
            api_key: Binance API key (optional for public data)
            api_secret: Binance API secret (optional for public data)
            symbol: Trading pair symbol (default 'ETHUSDT')
            interval: Timeframe interval (default '5m')
        """
        self.api_key = api_key or os.getenv('BINANCE_API_KEY', '')
        self.api_secret = api_secret or os.getenv('BINANCE_API_SECRET', '')
        self.symbol = symbol
        self.interval = interval
        self.client = None
        self.ccxt_client = None
        self._last_fetch_time = None
        self._cache: Optional[pd.DataFrame] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = 60
        
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize the Binance client"""
        if BINANCE_AVAILABLE and self.api_key and self.api_secret and Client:
            try:
                self.client = Client(self.api_key, self.api_secret)
                logger.info("Binance client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Binance client: {e}")
                self.client = None
        
        if CCXT_AVAILABLE and ccxt:
            try:
                self.ccxt_client = ccxt.binance({
                    'apiKey': self.api_key,
                    'secret': self.api_secret,
                    'enableRateLimit': True,
                    'options': {'defaultType': 'spot'}
                })
                logger.info("CCXT Binance client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize CCXT client: {e}")
                self.ccxt_client = None
    
    def fetch_historical_data(self, limit: int = 500, start_time: Optional[datetime] = None) -> Optional[DataFrame]:
        """
        Fetch historical OHLCV data
        
        Args:
            limit: Number of candles to fetch (max 1000)
            start_time: Optional start time for historical data
            
        Returns:
            DataFrame with OHLCV data or None
        """
        try:
            if self.ccxt_client:
                return self._fetch_with_ccxt(limit, start_time)
            elif self.client:
                return self._fetch_with_binance_python(limit, start_time)
            else:
                raise Exception("No Binance client available")
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            raise
    
    def _fetch_with_ccxt(self, limit: int, start_time: Optional[datetime] = None) -> Optional[DataFrame]:
        """Fetch data using CCXT library"""
        try:
            since = None
            if start_time:
                since = int(start_time.timestamp() * 1000)
            
            ohlcv = self.ccxt_client.fetch_ohlcv(
                symbol=self.symbol.replace('USDT', '/USDT'),
                timeframe=self.interval,
                since=since,
                limit=limit
            )
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            
            self._cache = df
            self._cache_time = datetime.now()
            
            logger.info(f"Fetched {len(df)} candles via CCXT")
            return df
            
        except Exception as e:
            logger.error(f"CCXT fetch error: {e}")
            raise
    
    def _fetch_with_binance_python(self, limit: int, start_time: Optional[datetime] = None) -> Optional[DataFrame]:
        """Fetch data using python-binance library"""
        try:
            klines = self.client.get_klines(
                symbol=self.symbol,
                interval=self.interval,
                limit=limit
            )
            
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            df = df[['open', 'high', 'low', 'close', 'volume']]
            for col in df.columns:
                df[col] = df[col].astype(float)
            
            self._cache = df
            self._cache_time = datetime.now()
            
            logger.info(f"Fetched {len(df)} candles via python-binance")
            return df
            
        except BinanceAPIException as e:
            logger.error(f"Binance API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Binance fetch error: {e}")
            raise
    
    def get_latest_candle(self) -> Optional[Dict]:
        """
        Get the latest completed candle
        
        Returns:
            Dictionary with latest candle data
        """
        try:
            df = self.fetch_historical_data(limit=2)
            if len(df) >= 2:
                latest = df.iloc[-2]
                return {
                    'timestamp': df.index[-2],
                    'open': latest['open'],
                    'high': latest['high'],
                    'low': latest['low'],
                    'close': latest['close'],
                    'volume': latest['volume']
                }
            return None
        except Exception as e:
            logger.error(f"Error getting latest candle: {e}")
            return None
    
    def get_current_price(self) -> Optional[float]:
        """Get current market price"""
        try:
            if self.ccxt_client:
                ticker = self.ccxt_client.fetch_ticker(self.symbol.replace('USDT', '/USDT'))
                return float(ticker['last'])
            elif self.client:
                ticker = self.client.get_symbol_ticker(symbol=self.symbol)
                return float(ticker['price'])
            return None
        except Exception as e:
            logger.error(f"Error getting current price: {e}")
            return None
    
    def calculate_heikin_ashi(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform OHLCV data to Heikin Ashi candles
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with Heikin Ashi values
        """
        ha_df = df.copy()
        
        ha_close = (df['open'] + df['high'] + df['low'] + df['close']) / 4
        
        ha_open = pd.Series(index=df.index, dtype=float)
        ha_open.iloc[0] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2
        
        for i in range(1, len(df)):
            ha_open.iloc[i] = (ha_open.iloc[i-1] + ha_close.iloc[i-1]) / 2
        
        ha_high = pd.concat([df['high'], ha_open, ha_close], axis=1).max(axis=1)
        ha_low = pd.concat([df['low'], ha_open, ha_close], axis=1).min(axis=1)
        
        ha_df['ha_open'] = ha_open
        ha_df['ha_high'] = ha_high
        ha_df['ha_low'] = ha_low
        ha_df['ha_close'] = ha_close
        
        return ha_df
    
    def get_cached_or_fresh_data(self, limit: int = 500, force_refresh: bool = False) -> pd.DataFrame:
        """
        Get data from cache if valid, otherwise fetch fresh data
        
        Args:
            limit: Number of candles to fetch
            force_refresh: Force fresh data fetch
            
        Returns:
            DataFrame with OHLCV data
        """
        now = datetime.now()
        
        if (not force_refresh and 
            self._cache is not None and 
            self._cache_time is not None and
            (now - self._cache_time).total_seconds() < self._cache_ttl):
            logger.debug("Returning cached data")
            return self._cache.copy()
        
        return self.fetch_historical_data(limit=limit)
    
    def get_interval_minutes(self) -> int:
        """Get the interval in minutes"""
        return self.INTERVAL_MINUTES.get(self.interval, 5)
    
    def time_until_next_candle(self) -> float:
        """
        Calculate seconds until next candle close
        
        Returns:
            Seconds until next candle closes
        """
        now = datetime.utcnow()
        interval_minutes = self.get_interval_minutes()
        
        current_minute = now.minute
        minutes_into_interval = current_minute % interval_minutes
        minutes_until_close = interval_minutes - minutes_into_interval
        
        next_close = now.replace(second=0, microsecond=0) + timedelta(minutes=minutes_until_close)
        seconds_until = (next_close - now).total_seconds()
        
        return max(0, seconds_until)
    
    async def close(self) -> None:
        """Close all clients and release resources"""
        try:
            if self.ccxt_client:
                try:
                    if hasattr(self.ccxt_client, 'close'):
                        result = self.ccxt_client.close()
                        if hasattr(result, '__await__'):
                            await result
                    logger.info("CCXT client closed successfully")
                except Exception as e:
                    logger.warning(f"Error closing CCXT client: {e}")
        finally:
            self.ccxt_client = None
            self.client = None
            logger.info("BinanceDataFetcher closed")
