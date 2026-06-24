#!/usr/bin/env python3
"""
FXSUSDT.P Futures Trader — v2.0 (June 2026)
Specialized for forex futures trading with API secrets management.

v2.0 improvements (engine v45.0):
  • Instance-level TTL cache for all per-symbol market data calls (60s TTL):
    get_symbol_ticker, get_funding_rate, get_open_interest, get_24hr_ticker_stats
    Prevents redundant calls within same scan cycle even for a single symbol.

Bug fixes applied:
- get_market_data() now passes the `symbol` argument to get_klines()
  (previously always fetched self.symbol regardless of what was requested)
- Shared persistent aiohttp.ClientSession added (eliminates per-call session
  creation that caused TCP/TLS overhead on every request)
- Added aclose() for graceful cleanup on shutdown
- _generate_signature: standardized to hmac.new() consistent with btcusdt_trader
"""

import asyncio
import logging
import aiohttp
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
import hmac
import hashlib
import time


class FXSUSDTTrader:
    """Binance Futures trader specifically for FXSUSDT.P"""

    MAINNET_URL = "https://fapi.binance.com"
    TESTNET_URL = "https://testnet.binancefuture.com"
    REQUEST_TIMEOUT = 15

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        self.api_key    = os.getenv('BINANCE_API_KEY')
        self.api_secret = os.getenv('BINANCE_API_SECRET')
        self.testnet    = os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'

        self.base_url = self.TESTNET_URL if self.testnet else self.MAINNET_URL
        self.symbol   = "FXSUSDT"
        self.timeframe = "30m"

        if not self.api_key or not self.api_secret:
            self.logger.warning("⚠️ API credentials not found in secrets")
            raise ValueError("Missing BINANCE_API_KEY or BINANCE_API_SECRET in Replit secrets")

        # Shared persistent HTTP session — avoids per-call TCP/TLS overhead.
        # BUG FIX: all previous methods created `aiohttp.ClientSession()` inside
        # each call, which meant a full TLS handshake on every Binance request.
        self._session:   Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector]  = None

        # ── v2.0 instance-level market data cache (engine v45.0) ─────────────
        # Prevents duplicate REST calls within the same scan cycle for FXSUSDT.
        # TTL 60s — covers 4-6 scan cycles (CYCLE_SLEEP_MIN=10, MAX=25).
        _mc: Dict = {}
        self._mkt_cache: Dict[str, Any]   = _mc    # endpoint_key → response data
        self._mkt_cache_ts: Dict[str, float] = {}  # endpoint_key → fetch timestamp
        self._CACHE_TTL: float = 60.0              # seconds

        self.logger.info(f"✅ FXSUSDT Trader v2.0 initialized ({'Testnet' if self.testnet else 'Mainnet'}) | cache_ttl={self._CACHE_TTL}s")

    # ─────────────────────────────────────────
    # Persistent Session Management
    # ─────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return (or lazily create) the shared persistent HTTP session."""
        if self._session is None or self._session.closed:
            self._connector = aiohttp.TCPConnector(
                limit=20,
                limit_per_host=10,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT),
            )
        return self._session

    async def aclose(self):
        """Gracefully close the shared session (call on shutdown)."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session   = None
        self._connector = None
        self.logger.debug("🔗 FXSUSDT shared aiohttp session closed")

    # ─────────────────────────────────────────
    # Auth Helpers
    # ─────────────────────────────────────────

    def _generate_signature(self, query_string: str) -> str:
        """Generate HMAC SHA256 signature for authenticated requests"""
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def _auth_headers(self) -> dict:
        return {'X-MBX-APIKEY': self.api_key}

    # ─────────────────────────────────────────
    # Market Data
    # ─────────────────────────────────────────

    async def get_market_status(self) -> Dict[str, Any]:
        """Check if FXSUSDT is actively tradeable"""
        try:
            info   = await self.get_exchange_info(self.symbol)
            status = info.get('status', 'UNKNOWN')
            ticker = await self.get_24hr_ticker_stats(self.symbol)
            volume_24h    = float(ticker.get('volume', 0))       if ticker else 0
            last_price    = float(ticker.get('lastPrice', 0))    if ticker else 0
            quote_vol_24h = float(ticker.get('quoteVolume', 0))  if ticker else 0
            trade_count   = int(ticker.get('count', 0))          if ticker else 0
            is_trading    = (status == 'TRADING')
            is_settling   = (status == 'SETTLING')
            return {
                'status':        status,
                'contract_type': info.get('contractType', 'UNKNOWN'),
                'is_trading':    is_trading,
                'is_settling':   is_settling,
                'active':        is_trading and volume_24h > 0,
                'volume_24h':    volume_24h,
                'quote_vol_24h': quote_vol_24h,
                'last_price':    last_price,
                'trade_count':   trade_count,
            }
        except Exception as e:
            self.logger.error(f"Market status check failed: {e}")
            return {'status': 'UNKNOWN', 'active': False, 'is_trading': False, 'is_settling': False}

    async def get_current_price(self) -> Optional[float]:
        """Get current FXSUSDT price"""
        try:
            url = f"{self.base_url}/fapi/v1/ticker/price"
            s = await self._get_session()
            async with s.get(url, params={"symbol": self.symbol}) as response:
                if response.status == 200:
                    data = await response.json()
                    price = float(data['price'])
                    self.logger.debug(f"💰 {self.symbol} current price: {price:.5f}")
                    return price
                self.logger.error(f"Failed to get price: {response.status}")
        except Exception as e:
            self.logger.error(f"Error getting current price: {e}")
        return None

    async def get_klines(self, interval: str, limit: int = 100,
                         symbol: Optional[str] = None) -> List[List]:
        """
        Get kline data for any timeframe and symbol.
        v28.0: Added 429 retry with exponential backoff — previously silently
        failed on rate-limit, returning empty list without retrying.
        """
        sym = symbol or self.symbol
        url    = f"{self.base_url}/fapi/v1/klines"
        params = {"symbol": sym, "interval": interval, "limit": min(limit, 1500)}
        _max_attempts = 3
        for _attempt in range(_max_attempts):
            try:
                s = await self._get_session()
                async with s.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        ohlcv_data = [
                            [int(k[0]), float(k[1]), float(k[2]),
                             float(k[3]), float(k[4]), float(k[5])]
                            for k in data
                        ]
                        self.logger.debug(
                            f"📊 Retrieved {len(ohlcv_data)} {interval} candles for {sym}"
                        )
                        return ohlcv_data
                    # v28.0: 429 rate-limit — exponential backoff before retry
                    if response.status == 429:
                        _retry_base = int(response.headers.get("Retry-After", "5"))
                        _retry = min(60, _retry_base * (2 ** _attempt) + _attempt)
                        self.logger.warning(
                            f"⏳ FXSUSDT 429 klines [{sym}|{interval}] "
                            f"(attempt {_attempt+1}/{_max_attempts}) — backing off {_retry}s [v28.0]"
                        )
                        await asyncio.sleep(_retry)
                        continue
                    # v24.0: tiered severity — 202=debug(soft-skip), 5xx=warning, 4xx=warning
                    if response.status == 202:
                        self.logger.debug(
                            f"Klines skip [{sym}|{interval}] HTTP 202 "
                            f"(pre-delivery/maintenance) — soft-skip [v24.0]"
                        )
                    elif response.status >= 500:
                        self.logger.warning(
                            f"Klines server error [{sym}|{interval}] HTTP {response.status} (transient) [v24.0]"
                        )
                    else:
                        self.logger.warning(
                            f"Failed to get {interval} klines [{sym}]: HTTP {response.status} [v24.0]"
                        )
                    break  # Non-retryable status
            except Exception as e:
                self.logger.error(f"Error getting {interval} kline data: {e}")
                break
        return []

    async def get_30m_klines(self, limit: int = 100) -> List[List]:
        """Get 30-minute kline data for FXSUSDT"""
        return await self.get_klines(self.timeframe, limit)

    async def get_market_data(self, symbol: str, timeframe: str,
                              limit: int = 500) -> List[List]:
        """
        Get market data for the given symbol and timeframe.

        BUG FIX: The previous implementation always called
        `get_klines(timeframe, limit)` which internally used `self.symbol`
        (FXSUSDT) regardless of the `symbol` argument passed in.  Every
        multi-market scan was silently returning FXSUSDT candle data for
        every symbol.  Now passes `symbol` explicitly to `get_klines`.
        """
        return await self.get_klines(timeframe, limit=limit, symbol=symbol)

    async def get_account_balance(self) -> Dict[str, Any]:
        """Get futures account balance"""
        try:
            endpoint     = "/fapi/v2/account"
            timestamp    = int(time.time() * 1000)
            query_string = f"timestamp={timestamp}"
            signature    = self._generate_signature(query_string)
            url          = f"{self.base_url}{endpoint}?{query_string}&signature={signature}"
            s = await self._get_session()
            async with s.get(url, headers=self._auth_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    usdt_balance = 0.0
                    for asset in data.get('assets', []):
                        if asset['asset'] == 'USDT':
                            usdt_balance = float(asset['availableBalance'])
                            break
                    return {
                        'total_wallet_balance':  float(data.get('totalWalletBalance', 0)),
                        'available_balance':      usdt_balance,
                        'total_unrealized_pnl':  float(data.get('totalUnrealizedProfit', 0)),
                        'cross_wallet_balance':  float(data.get('totalCrossWalletBalance', 0)),
                    }
                self.logger.error(f"Failed to get account: {response.status}")
        except Exception as e:
            self.logger.error(f"Error getting account balance: {e}")
        return {}

    async def get_position_info(self) -> Dict[str, Any]:
        """Get current FXSUSDT position information"""
        try:
            endpoint     = "/fapi/v2/positionRisk"
            timestamp    = int(time.time() * 1000)
            query_string = f"symbol={self.symbol}&timestamp={timestamp}"
            signature    = self._generate_signature(query_string)
            url          = f"{self.base_url}{endpoint}?{query_string}&signature={signature}"
            s = await self._get_session()
            async with s.get(url, headers=self._auth_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    if data:
                        position = data[0]
                        return {
                            'symbol':           position.get('symbol'),
                            'position_amount':  float(position.get('positionAmt', 0)),
                            'entry_price':      float(position.get('entryPrice', 0)),
                            'mark_price':       float(position.get('markPrice', 0)),
                            'unrealized_pnl':   float(position.get('unRealizedProfit', 0)),
                            'leverage':         float(position.get('leverage', 1)),
                        }
                    return {'position_amount': 0}
                self.logger.error(f"Failed to get position: {response.status}")
        except Exception as e:
            self.logger.error(f"Error getting position info: {e}")
        return {}

    def _cache_get(self, key: str) -> Optional[Any]:
        """Return cached value if within TTL, else None."""
        ts = self._mkt_cache_ts.get(key, 0.0)
        if time.time() - ts < self._CACHE_TTL:
            return self._mkt_cache.get(key)
        return None

    def _cache_set(self, key: str, value: Any) -> None:
        """Store value in cache with current timestamp."""
        self._mkt_cache[key] = value
        self._mkt_cache_ts[key] = time.time()

    async def get_symbol_ticker(self, symbol: str = None) -> Optional[Dict[str, Any]]:
        """Get symbol ticker information — TTL-cached 60s (v2.0)"""
        sym = symbol or self.symbol
        cache_key = f"ticker:{sym}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            url = f"{self.base_url}/fapi/v1/ticker/24hr"
            s = await self._get_session()
            async with s.get(url, params={"symbol": sym}) as response:
                if response.status == 200:
                    data = await response.json()
                    self.logger.debug(f"📊 Retrieved ticker for {sym}")
                    self._cache_set(cache_key, data)
                    return data
                self.logger.error(f"Failed to get ticker: {response.status}")
        except Exception as e:
            self.logger.error(f"Error getting ticker: {e}")
        return None

    async def get_funding_rate(self, symbol: str = None) -> Optional[Dict[str, Any]]:
        """Get current funding rate — TTL-cached 60s (v2.0)"""
        sym = symbol or self.symbol
        cache_key = f"funding:{sym}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            url = f"{self.base_url}/fapi/v1/premiumIndex"
            s = await self._get_session()
            async with s.get(url, params={"symbol": sym}) as response:
                if response.status == 200:
                    data = await response.json()
                    self.logger.debug(f"📊 Retrieved funding rate for {sym}")
                    result = {
                        "fundingRate": data.get("lastFundingRate", "0"),
                        "fundingTime": data.get("nextFundingTime", 0),
                        "markPrice":   data.get("markPrice", "0"),
                    }
                    self._cache_set(cache_key, result)
                    return result
                self.logger.error(f"Failed to get funding rate: {response.status}")
        except Exception as e:
            self.logger.error(f"Error getting funding rate: {e}")
        return None

    async def get_open_interest(self, symbol: str = None) -> Optional[Dict[str, Any]]:
        """Get open interest — TTL-cached 120s (v2.0)"""
        sym = symbol or self.symbol
        cache_key = f"oi:{sym}"
        ts = self._mkt_cache_ts.get(cache_key, 0.0)
        if time.time() - ts < 120.0:   # OI cache: 120s (same as btcusdt_trader)
            cached = self._mkt_cache.get(cache_key)
            if cached is not None:
                return cached
        try:
            url = f"{self.base_url}/fapi/v1/openInterest"
            s = await self._get_session()
            async with s.get(url, params={"symbol": sym}) as response:
                if response.status == 200:
                    data = await response.json()
                    self.logger.debug(f"📊 Retrieved open interest for {sym}")
                    self._mkt_cache[cache_key] = data
                    self._mkt_cache_ts[cache_key] = time.time()
                    return data
                self.logger.error(f"Failed to get open interest: {response.status}")
        except Exception as e:
            self.logger.error(f"Error getting open interest: {e}")
        return None

    async def get_positions(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Get current positions for symbol"""
        try:
            sym       = symbol or self.symbol
            timestamp = int(time.time() * 1000)
            qs        = f"symbol={sym}&timestamp={timestamp}"
            sig       = self._generate_signature(qs)
            url       = f"{self.base_url}/fapi/v2/positionRisk?{qs}&signature={sig}"
            s = await self._get_session()
            async with s.get(url, headers=self._auth_headers()) as response:
                if response.status == 200:
                    data             = await response.json()
                    active_positions = [
                        pos for pos in data if float(pos.get('positionAmt', 0)) != 0
                    ]
                    self.logger.debug(
                        f"📊 Retrieved {len(active_positions)} active positions"
                    )
                    return active_positions
                self.logger.error(f"Failed to get positions: {response.status}")
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
        return []

    async def get_account_info(self) -> Dict[str, Any]:
        """Get detailed account information"""
        try:
            timestamp    = int(time.time() * 1000)
            query_string = f"timestamp={timestamp}"
            signature    = self._generate_signature(query_string)
            url          = f"{self.base_url}/fapi/v2/account?{query_string}&signature={signature}"
            s = await self._get_session()
            async with s.get(url, headers=self._auth_headers()) as response:
                if response.status == 200:
                    self.logger.debug("📊 Retrieved account info")
                    return await response.json()
                self.logger.error(f"Failed to get account info: {response.status}")
        except Exception as e:
            self.logger.error(f"Error getting account info: {e}")
        return {}

    async def get_exchange_info(self, symbol: str = None) -> Dict[str, Any]:
        """Get exchange information for symbol"""
        try:
            sym = symbol or self.symbol
            url = f"{self.base_url}/fapi/v1/exchangeInfo"
            s = await self._get_session()
            async with s.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    for sym_info in data.get('symbols', []):
                        if sym_info.get('symbol') == sym:
                            return sym_info
                    return {}
                self.logger.error(f"Failed to get exchange info: {response.status}")
        except Exception as e:
            self.logger.error(f"Error getting exchange info: {e}")
        return {}

    async def get_24hr_ticker_stats(self, symbol: str = None) -> Dict[str, Any]:
        """Get 24hr ticker statistics — TTL-cached 60s (v2.0)"""
        sym = symbol or self.symbol
        cache_key = f"ticker24:{sym}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            url = f"{self.base_url}/fapi/v1/ticker/24hr"
            s = await self._get_session()
            async with s.get(url, params={"symbol": sym}) as response:
                if response.status == 200:
                    self.logger.debug(f"📊 Retrieved 24hr stats for {sym}")
                    data = await response.json()
                    self._cache_set(cache_key, data)
                    return data
                self.logger.error(f"Failed to get 24hr stats: {response.status}")
        except Exception as e:
            self.logger.error(f"Error getting 24hr stats: {e}")
        return {}

    async def change_leverage(self, symbol: str, leverage: int) -> bool:
        """Change leverage for symbol"""
        leverage = max(1, min(leverage, 125))
        try:
            timestamp    = int(time.time() * 1000)
            query_string = f"symbol={symbol}&leverage={leverage}&timestamp={timestamp}"
            signature    = self._generate_signature(query_string)
            url          = f"{self.base_url}/fapi/v1/leverage"
            data         = {
                'symbol': symbol, 'leverage': leverage,
                'timestamp': timestamp, 'signature': signature,
            }
            s = await self._get_session()
            async with s.post(url, headers=self._auth_headers(), data=data) as response:
                if response.status == 200:
                    self.logger.info(f"✅ Leverage changed to {leverage}x for {symbol}")
                    return True
                self.logger.error(f"Failed to change leverage: {response.status}")
        except Exception as e:
            self.logger.error(f"Error changing leverage: {e}")
        return False

    async def get_leverage(self, symbol: str = None) -> Optional[int]:
        """Get current leverage for symbol"""
        try:
            position_info = await self.get_position_info()
            if position_info and 'leverage' in position_info:
                return int(float(position_info['leverage']))
            account_info = await self.get_account_info()
            for position in account_info.get('positions', []):
                if position.get('symbol') == (symbol or self.symbol):
                    return int(float(position.get('leverage', 1)))
            return 1
        except Exception as e:
            self.logger.error(f"Error getting leverage: {e}")
        return None

    async def get_trade_history(self, symbol: str = None,
                                limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent trade history for symbol"""
        try:
            sym       = symbol or self.symbol
            timestamp = int(time.time() * 1000)
            qs        = f"symbol={sym}&limit={min(limit, 1000)}&timestamp={timestamp}"
            sig       = self._generate_signature(qs)
            url       = f"{self.base_url}/fapi/v1/userTrades?{qs}&signature={sig}"
            s = await self._get_session()
            async with s.get(url, headers=self._auth_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    self.logger.debug(f"📊 Retrieved {len(data)} trades for {sym}")
                    return data
                self.logger.error(f"Failed to get trade history: {response.status}")
        except Exception as e:
            self.logger.error(f"Error getting trade history: {e}")
        return []

    async def get_order_book(self, symbol: str = None,
                             limit: int = 20) -> Optional[Dict[str, Any]]:
        """Get order book (depth) data"""
        try:
            sym = symbol or self.symbol
            url = f"{self.base_url}/fapi/v1/depth"
            s = await self._get_session()
            async with s.get(url, params={"symbol": sym, "limit": min(limit, 1000)}) as response:
                if response.status == 200:
                    self.logger.debug(f"📊 Order book retrieved for {sym}")
                    return await response.json()
                self.logger.error(f"Failed to get order book: {response.status}")
        except Exception as e:
            self.logger.error(f"Error getting order book: {e}")
        return None

    async def get_recent_trades(self, symbol: str = None,
                                limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent market trades for time & sales tape analysis"""
        try:
            sym = symbol or self.symbol
            url = f"{self.base_url}/fapi/v1/trades"
            s = await self._get_session()
            async with s.get(url, params={"symbol": sym, "limit": min(limit, 1000)}) as response:
                if response.status == 200:
                    data = await response.json()
                    self.logger.debug(f"📈 Retrieved {len(data)} recent trades for {sym}")
                    return data
                self.logger.error(f"Failed to get recent trades: {response.status}")
        except Exception as e:
            self.logger.error(f"Error getting recent trades: {e}")
        return []

    async def test_connection(self) -> bool:
        """Test API connection and credentials"""
        try:
            price = await self.get_current_price()
            if price is None:
                return False
            account = await self.get_account_balance()
            if not account:
                return False
            self.logger.info("✅ API connection test successful")
            return True
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # MEXC USDM Perpetual Futures — public market data helpers [v146.0]
    # Base URL: https://contract.mexc.com (public endpoints, no auth required)
    # Symbol format: BTC_USDT (underscore separator, vs Binance's BTCUSDT)
    # ─────────────────────────────────────────────────────────────────────────

    MEXC_FUTURES_URL = "https://contract.mexc.com"

    @staticmethod
    def binance_to_mexc_symbol(binance_symbol: str) -> str:
        """Convert Binance USDM symbol to MEXC perpetual format.

        Examples:
            BTCUSDT  → BTC_USDT
            ETHUSDT  → ETH_USDT
            SOLUSDT  → SOL_USDT
        """
        sym = binance_symbol.upper().strip()
        if sym.endswith("USDT"):
            base = sym[:-4]
            return f"{base}_USDT"
        return sym  # fallback: return unchanged if unexpected format

    async def get_mexc_klines(
        self,
        symbol: str,
        interval: str = "Min15",
        limit: int = 25,
    ) -> Optional[Dict[str, Any]]:
        """Fetch MEXC USDM perpetual klines (candlestick data).

        Args:
            symbol:   MEXC symbol format, e.g. ``BTC_USDT``.
            interval: Candle interval. Supported values:
                      Min1, Min5, Min15, Min30, Min60,
                      Hour4, Hour8, Day1, Week1, Month1.
            limit:    Number of candles to fetch (max 2000).

        Returns:
            Raw MEXC kline data dict with keys:
                ``time``, ``open``, ``close``, ``high``, ``low``,
                ``vol``, ``amount`` — all as lists of floats.
            Returns ``None`` on network error or non-200 response.
        """
        try:
            session = await self._get_session()
            url = f"{self.MEXC_FUTURES_URL}/api/v1/contract/kline/{symbol}"
            async with session.get(
                url,
                params={"interval": interval, "limit": str(limit)},
                timeout=aiohttp.ClientTimeout(total=8.0),
            ) as resp:
                if resp.status != 200:
                    self.logger.debug(f"MEXC klines {symbol}: HTTP {resp.status}")
                    return None
                data = await resp.json()
                if (isinstance(data, dict) and
                        (data.get("success") or data.get("code") == 0) and
                        isinstance(data.get("data"), dict)):
                    return data["data"]
                return None
        except Exception as e:
            self.logger.debug(f"MEXC klines {symbol} error: {e}")
            return None

    async def get_mexc_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch MEXC USDM perpetual ticker for a single symbol.

        Args:
            symbol: MEXC symbol format, e.g. ``BTC_USDT``.

        Returns:
            Ticker dict with keys including ``lastPrice``, ``bid1``,
            ``ask1``, ``volume24``, ``amount24``, ``riseFallRate``,
            ``indexPrice``, ``fairPrice``.  Returns ``None`` on error.
        """
        try:
            session = await self._get_session()
            url = f"{self.MEXC_FUTURES_URL}/api/v1/contract/ticker"
            async with session.get(
                url,
                params={"symbol": symbol},
                timeout=aiohttp.ClientTimeout(total=8.0),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if (isinstance(data, dict) and
                        (data.get("success") or data.get("code") == 0)):
                    raw = data.get("data", {})
                    if isinstance(raw, list) and raw:
                        return raw[0]
                    if isinstance(raw, dict):
                        return raw
                return None
        except Exception as e:
            self.logger.debug(f"MEXC ticker {symbol} error: {e}")
            return None

    async def get_mexc_symbols(self) -> List[str]:
        """Fetch all active MEXC USDM perpetual contract symbols.

        Returns:
            List of MEXC-format symbols (e.g. ``['BTC_USDT', 'ETH_USDT', ...]``).
            Empty list on error.
        """
        try:
            session = await self._get_session()
            url = f"{self.MEXC_FUTURES_URL}/api/v1/contract/detail"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10.0)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                if (isinstance(data, dict) and
                        (data.get("success") or data.get("code") == 0) and
                        isinstance(data.get("data"), list)):
                    return [
                        c["symbol"]
                        for c in data["data"]
                        if isinstance(c, dict)
                        and c.get("symbol", "").endswith("_USDT")
                        and c.get("state") in (0, 1, "0", "1", None)
                    ]
                return []
        except Exception as e:
            self.logger.debug(f"MEXC symbols error: {e}")
            return []
