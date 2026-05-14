#!/usr/bin/env python3
"""
Kraken trading integration using ccxt library
Alternative API for market data when Binance is unavailable
"""

import asyncio
import logging
import ccxt.async_support as ccxt
from typing import Dict, Any, List, Optional
import time

from config import Config

class KrakenTrader:
    """Kraken trading interface using ccxt as alternative to Binance"""

    def __init__(self):
        self.config = Config()
        self.logger = logging.getLogger(__name__)
        self.exchange = None

        # Map common symbols to Kraken format
        self.symbol_mapping = {
            'BTCUSDT': 'BTC/USDT',
            'ETHUSDT': 'ETH/USDT',
            'ADAUSDT': 'ADA/USDT',
            'SOLUSDT': 'SOL/USDT',
            'MATICUSDT': 'MATIC/USDT',
            'LINKUSDT': 'LINK/USDT',
            'BNBUSDT': 'BNB/USDT',
            'XRPUSDT': 'XRP/USDT',
            'DOTUSDT': 'DOT/USDT',
            'AVAXUSDT': 'AVAX/USDT'
        }

    async def initialize(self):
        """Initialize Kraken exchange connection"""
        try:
            self.exchange = ccxt.kraken({
                'timeout': 30000,
                'rateLimit': 3000,
                'enableRateLimit': True,
                'sandbox': False,
                'options': {
                    'defaultType': 'spot',
                }
            })

            # Test connection
            await self.exchange.load_markets()
            self.logger.info("Kraken exchange initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize Kraken exchange: {e}")
            raise

    async def close(self):
        """Close exchange connection"""
        if self.exchange:
            await self.exchange.close()

    async def test_connection(self) -> bool:
        """Test exchange connectivity"""
        try:
            await self.exchange.fetch_status()
            return True
        except Exception as e:
            self.logger.warning(f"Kraken connection test failed: {e}")
            return False

    def _convert_symbol(self, symbol: str) -> str:
        """Convert Binance symbol format to Kraken format"""
        return self.symbol_mapping.get(symbol, symbol)

    async def get_current_price(self, symbol: str) -> float:
        """Get current market price for symbol"""
        try:
            kraken_symbol = self._convert_symbol(symbol)
            ticker = await self.exchange.fetch_ticker(kraken_symbol)
            price = ticker.get('last') or ticker.get('close') or ticker.get('price')

            if price is None:
                self.logger.warning(f"No price data available for {symbol}")
                return 0.0

            return float(price)

        except Exception as e:
            self.logger.error(f"Error getting price for {symbol} from Kraken: {e}")
            return 0.0

    async def get_market_data(self, symbol: str, timeframe: str = '1h', limit: int = 100) -> List[List]:
        """Get OHLCV market data"""
        try:
            kraken_symbol = self._convert_symbol(symbol)
            ohlcv = await self.exchange.fetch_ohlcv(kraken_symbol, timeframe, limit=limit)

            # Validate the data
            if not ohlcv or len(ohlcv) == 0:
                self.logger.warning(f"No OHLCV data returned for {symbol} {timeframe}")
                return []

            # Check if data contains valid values
            valid_data = []
            for candle in ohlcv:
                if len(candle) >= 6 and all(x is not None for x in candle[:6]):
                    valid_data.append(candle)

            if len(valid_data) == 0:
                self.logger.warning(f"No valid OHLCV data for {symbol} {timeframe}")
                return []

            return valid_data

        except Exception as e:
            self.logger.error(f"Error getting market data for {symbol} {timeframe}: {e}")
            return []

    async def get_technical_analysis(self, symbol: str) -> Dict[str, Any]:
        """Get technical analysis for symbol"""
        try:
            kraken_symbol = self._convert_symbol(symbol)

            # Get market data
            ohlcv_1h = await self.get_market_data(symbol, '1h', 100)
            ohlcv_4h = await self.get_market_data(symbol, '4h', 100)
            ohlcv_1d = await self.get_market_data(symbol, '1d', 50)

            # Get 24h price change
            ticker = await self.exchange.fetch_ticker(kraken_symbol)
            price_change_24h = ticker['percentage']

            analysis = {
                'symbol': symbol,
                'price_change_24h': price_change_24h,
                'volume': ticker['baseVolume'],
                'high_24h': ticker['high'],
                'low_24h': ticker['low'],
                'current_price': ticker['last']
            }

            return analysis

        except Exception as e:
            self.logger.error(f"Error getting technical analysis for {symbol} from Kraken: {e}")
            return {}

    async def get_market_summary(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get market summary for multiple symbols"""
        try:
            summaries = {}

            for symbol in symbols:
                try:
                    kraken_symbol = self._convert_symbol(symbol)
                    ticker = await self.exchange.fetch_ticker(kraken_symbol)
                    summaries[symbol] = {
                        'price': ticker['last'],
                        'change_24h': ticker['percentage'],
                        'volume': ticker['baseVolume'],
                        'high_24h': ticker['high'],
                        'low_24h': ticker['low']
                    }
                except Exception:
                    continue

                # Rate limiting
                await asyncio.sleep(0.1)

            return summaries

        except Exception as e:
            self.logger.error(f"Error getting market summary from Kraken: {e}")
            return {}