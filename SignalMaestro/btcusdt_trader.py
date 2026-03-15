#!/usr/bin/env python3
"""
Universal USDM Futures Trader
Binance USDM Futures — full API wrapper supporting ALL perpetual markets.
Multi-market edition: scans all active USDM perpetual symbols.
Uses a single persistent aiohttp.ClientSession (shared connector) for all
public market-data calls, eliminating per-request session creation overhead.
"""

import asyncio
import logging
import aiohttp
import os
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import hmac
import hashlib
import time


class BTCUSDTTrader:
    """
    Binance USDM Futures trader — supports ALL USDM perpetual markets.
    Backward-compatible: default symbol is BTCUSDT.
    """

    SYMBOL = "BTCUSDT"
    MAINNET_URL = "https://fapi.binance.com"
    TESTNET_URL = "https://testnet.binancefuture.com"
    REQUEST_TIMEOUT = 15  # seconds

    MIN_VOLUME_USDT = 50_000_000   # min 24h USDT volume to qualify for scanning
    MAX_SYMBOLS     = 80           # cap on simultaneously scanned symbols

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        self.api_key    = os.getenv("BINANCE_API_KEY")
        self.api_secret = os.getenv("BINANCE_API_SECRET")
        self.testnet    = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

        self.base_url = self.TESTNET_URL if self.testnet else self.MAINNET_URL
        self.symbol   = self.SYMBOL
        self.timeframe = "15m"

        if not self.api_key or not self.api_secret:
            raise ValueError("Missing BINANCE_API_KEY or BINANCE_API_SECRET in environment secrets")

        # Persistent shared HTTP session (created lazily on first async call)
        self._session:   Optional[aiohttp.ClientSession]  = None
        self._connector: Optional[aiohttp.TCPConnector]   = None

        # Short-lived klines cache — keyed by (symbol, interval, limit).
        # TTL of 90 s avoids duplicate Binance fetches when process_signals
        # re-requests the same klines that the strategy just fetched.
        self._klines_cache: Dict[Tuple, Tuple[list, float]] = {}
        self._klines_cache_ttl = 90.0  # seconds

        # Perpetual-symbol whitelist — refreshed every 60 minutes via exchangeInfo.
        # Prevents SETTLING / BREAK symbols leaking into the scan universe.
        self._perpetual_trading_symbols: Optional[frozenset] = None
        self._perpetual_cache_time: float = 0.0
        self._perpetual_cache_ttl: float = 3600.0  # 1 hour

        self.logger.info(
            f"✅ BTCUSDTTrader initialized — {'Testnet' if self.testnet else 'Mainnet'} | "
            f"Multi-market mode enabled | Persistent HTTP session pooling active"
        )

    # ─────────────────────────────────────────
    # Persistent Session Management
    # ─────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Return the shared persistent HTTP session, creating it on first call.
        Uses a TCPConnector with generous limits for parallel scanning of 80 symbols.
        """
        if self._session is None or self._session.closed:
            self._connector = aiohttp.TCPConnector(
                limit=60,           # max 60 total concurrent connections
                limit_per_host=30,  # max 30 to fapi.binance.com
                ttl_dns_cache=300,  # cache DNS for 5 minutes
                enable_cleanup_closed=True,
            )
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT),
            )
            self.logger.debug("🔗 Shared aiohttp session created (connector pooling active)")
        return self._session

    async def aclose(self):
        """Gracefully close the shared session and connector."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session   = None
        self._connector = None
        self.logger.debug("🔗 Shared aiohttp session closed")

    # ─────────────────────────────────────────
    # Auth Helpers
    # ─────────────────────────────────────────

    def _sign(self, query_string: str) -> str:
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _auth_headers(self) -> dict:
        return {"X-MBX-APIKEY": self.api_key}

    def _signed_params(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        params["signature"] = self._sign(query)
        return params

    # ─────────────────────────────────────────
    # Market Data — Public (no auth)
    # ─────────────────────────────────────────

    async def get_current_price(self) -> Optional[float]:
        """Get current BTCUSDT mark price"""
        try:
            url = f"{self.base_url}/fapi/v1/ticker/price"
            s = await self._get_session()
            async with s.get(url, params={"symbol": self.symbol}) as r:
                if r.status == 200:
                    data = await r.json()
                    price = float(data["price"])
                    self.logger.debug(f"💰 BTCUSDT price: ${price:,.2f}")
                    return price
                self.logger.error(f"Price fetch error: HTTP {r.status}")
        except asyncio.TimeoutError:
            self.logger.warning("⏱ Timeout fetching BTC price")
        except Exception as e:
            self.logger.error(f"get_current_price error: {e}")
        return None

    async def get_market_data(self, symbol: str, timeframe: str, limit: int = 500) -> Optional[List]:
        """Fetch klines / candlestick data (served from cache when fresh)"""
        return await self.get_klines(timeframe, limit=limit, symbol=symbol)

    async def get_klines(self, interval: str, limit: int = 500,
                         symbol: Optional[str] = None) -> Optional[List]:
        """
        Fetch klines from Binance USDM Futures (uses shared session).
        Results are cached for _klines_cache_ttl seconds to prevent duplicate
        API calls when process_signals re-fetches klines the strategy already pulled.
        """
        sym = symbol or self.symbol
        limit = min(limit, 1500)
        now = time.time()

        # Return cached result if still fresh — also accept a larger cached fetch
        # so strategy (250 bars) and boost analysis (200 bars) share one API call.
        cache_key = (sym, interval, limit)
        cached = self._klines_cache.get(cache_key)
        if cached is not None:
            data, fetched_at = cached
            if now - fetched_at < self._klines_cache_ttl:
                return data

        # Check if a larger cached result can satisfy this request
        for (c_sym, c_interval, c_limit), (c_data, c_time) in self._klines_cache.items():
            if (c_sym == sym and c_interval == interval and
                    c_limit >= limit and now - c_time < self._klines_cache_ttl):
                return c_data[-limit:] if len(c_data) >= limit else c_data

        try:
            url = f"{self.base_url}/fapi/v1/klines"
            params = {"symbol": sym, "interval": interval, "limit": limit}
            s = await self._get_session()
            async with s.get(url, params=params) as r:
                if r.status == 200:
                    data = await r.json()
                    # Evict cache entries beyond a reasonable size (max 200 symbols)
                    if len(self._klines_cache) > 200:
                        oldest_key = min(self._klines_cache, key=lambda k: self._klines_cache[k][1])
                        self._klines_cache.pop(oldest_key, None)
                    self._klines_cache[cache_key] = (data, now)
                    return data
                body = await r.text()
                self.logger.error(f"Klines error {r.status}: {body[:200]}")
        except asyncio.TimeoutError:
            self.logger.warning(f"⏱ Timeout fetching klines {interval}")
        except Exception as e:
            self.logger.error(f"get_klines error: {e}")
        return None

    async def get_24hr_ticker_stats(self, symbol: Optional[str] = None) -> Optional[Dict]:
        """24h rolling window ticker statistics"""
        sym = symbol or self.symbol
        try:
            url = f"{self.base_url}/fapi/v1/ticker/24hr"
            s = await self._get_session()
            async with s.get(url, params={"symbol": sym}) as r:
                if r.status == 200:
                    return await r.json()
        except Exception as e:
            self.logger.error(f"24hr ticker error: {e}")
        return None

    async def get_order_book(self, symbol: Optional[str] = None, limit: int = 20) -> Optional[Dict]:
        """Fetch order book depth"""
        sym = symbol or self.symbol
        limit = min(limit, 1000)
        try:
            url = f"{self.base_url}/fapi/v1/depth"
            s = await self._get_session()
            async with s.get(url, params={"symbol": sym, "limit": limit}) as r:
                if r.status == 200:
                    return await r.json()
        except Exception as e:
            self.logger.error(f"Order book error: {e}")
        return None

    async def get_funding_rate(self, symbol: Optional[str] = None) -> Optional[Dict]:
        """Get current funding rate — returns dict with 'fundingRate' key (str)"""
        sym = symbol or self.symbol
        try:
            url = f"{self.base_url}/fapi/v1/premiumIndex"
            s = await self._get_session()
            async with s.get(url, params={"symbol": sym}) as r:
                if r.status == 200:
                    data = await r.json()
                    return {
                        "fundingRate": data.get("lastFundingRate", "0"),
                        "fundingTime": data.get("nextFundingTime", 0),
                        "markPrice":   data.get("markPrice", "0"),
                        "indexPrice":  data.get("indexPrice", "0"),
                    }
        except Exception as e:
            self.logger.error(f"Funding rate error: {e}")
        return None

    async def get_open_interest(self, symbol: Optional[str] = None) -> Optional[Dict]:
        """Get current open interest"""
        sym = symbol or self.symbol
        try:
            url = f"{self.base_url}/fapi/v1/openInterest"
            s = await self._get_session()
            async with s.get(url, params={"symbol": sym}) as r:
                if r.status == 200:
                    return await r.json()
        except Exception as e:
            self.logger.error(f"Open interest error: {e}")
        return None

    async def get_exchange_info(self, symbol: Optional[str] = None) -> Dict:
        """Get exchange info for the symbol"""
        sym = symbol or self.symbol
        try:
            url = f"{self.base_url}/fapi/v1/exchangeInfo"
            s = await self._get_session()
            async with s.get(url) as r:
                if r.status == 200:
                    info = await r.json()
                    for s_info in info.get("symbols", []):
                        if s_info.get("symbol") == sym:
                            return s_info
        except Exception as e:
            self.logger.error(f"Exchange info error: {e}")
        return {}

    async def get_market_status(self) -> Dict[str, Any]:
        """Check if BTCUSDT is actively tradable"""
        try:
            info       = await self.get_exchange_info(self.symbol)
            status     = info.get("status", "UNKNOWN")
            ticker     = await self.get_24hr_ticker_stats(self.symbol)
            volume_24h = float(ticker.get("volume", 0))   if ticker else 0
            last_price = float(ticker.get("lastPrice", 0)) if ticker else 0
            quote_vol  = float(ticker.get("quoteVolume", 0)) if ticker else 0
            trade_cnt  = int(ticker.get("count", 0))       if ticker else 0
            is_trading = status == "TRADING"
            return {
                "status": status,
                "contract_type": info.get("contractType", "PERPETUAL"),
                "is_trading": is_trading,
                "is_settling": status == "SETTLING",
                "active": is_trading and volume_24h > 0,
                "volume_24h": volume_24h,
                "quote_vol_24h": quote_vol,
                "last_price": last_price,
                "trade_count": trade_cnt,
            }
        except Exception as e:
            self.logger.error(f"Market status error: {e}")
            return {"status": "UNKNOWN", "active": False, "is_trading": False}

    # ─────────────────────────────────────────
    # Account & Position Data — Authenticated
    # All signed calls reuse the shared TCPConnector session. Auth is provided
    # per-request via X-MBX-APIKEY header; the session carries no stored credentials.
    # ─────────────────────────────────────────

    async def get_account_balance(self) -> Optional[Dict]:
        """Retrieve USDT futures wallet balance"""
        try:
            url    = f"{self.base_url}/fapi/v2/balance"
            params = self._signed_params({})
            s = await self._get_session()
            async with s.get(url, params=params, headers=self._auth_headers()) as r:
                if r.status == 200:
                    balances = await r.json()
                    usdt = next(
                        (b for b in balances if b.get("asset") == "USDT"),
                        None
                    )
                    if usdt:
                        return {
                            "total_wallet_balance": float(usdt.get("balance", 0)),
                            "available_balance": float(usdt.get("availableBalance", 0)),
                            "cross_wallet_balance": float(usdt.get("crossWalletBalance", 0)),
                            "total_unrealized_pnl": float(usdt.get("crossUnPnl", 0)),
                            "asset": "USDT",
                        }
                body = await r.text()
                self.logger.error(f"Balance fetch error {r.status}: {body[:200]}")
        except Exception as e:
            self.logger.error(f"get_account_balance error: {e}")
        return None

    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get open positions for BTCUSDT (or specified symbol)"""
        sym = symbol or self.symbol
        try:
            url    = f"{self.base_url}/fapi/v2/positionRisk"
            params = self._signed_params({"symbol": sym})
            s = await self._get_session()
            async with s.get(url, params=params, headers=self._auth_headers()) as r:
                if r.status == 200:
                    positions = await r.json()
                    return [
                        p for p in positions
                        if float(p.get("positionAmt", 0)) != 0
                    ]
        except Exception as e:
            self.logger.error(f"get_positions error: {e}")
        return []

    async def get_trade_history(self, symbol: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """Get recent trade history"""
        sym = symbol or self.symbol
        limit = min(limit, 1000)
        try:
            url    = f"{self.base_url}/fapi/v1/userTrades"
            params = self._signed_params({"symbol": sym, "limit": limit})
            s = await self._get_session()
            async with s.get(url, params=params, headers=self._auth_headers()) as r:
                if r.status == 200:
                    return await r.json()
        except Exception as e:
            self.logger.error(f"get_trade_history error: {e}")
        return []

    async def get_leverage(self, symbol: Optional[str] = None) -> Optional[int]:
        """Get current leverage setting"""
        sym = symbol or self.symbol
        try:
            url    = f"{self.base_url}/fapi/v2/positionRisk"
            params = self._signed_params({"symbol": sym})
            s = await self._get_session()
            async with s.get(url, params=params, headers=self._auth_headers()) as r:
                if r.status == 200:
                    data = await r.json()
                    if data:
                        return int(data[0].get("leverage", 10))
        except Exception as e:
            self.logger.error(f"get_leverage error: {e}")
        return None

    async def change_leverage(self, symbol: str, leverage: int) -> bool:
        """Change futures leverage for symbol"""
        leverage = max(1, min(leverage, 125))  # BTCUSDT max is 125x
        try:
            url    = f"{self.base_url}/fapi/v1/leverage"
            params = self._signed_params({"symbol": symbol, "leverage": leverage})
            s = await self._get_session()
            async with s.post(url, data=params, headers=self._auth_headers()) as r:
                if r.status == 200:
                    self.logger.info(f"✅ Leverage changed to {leverage}x for {symbol}")
                    return True
                body = await r.text()
                self.logger.error(f"Leverage change error {r.status}: {body[:200]}")
        except Exception as e:
            self.logger.error(f"change_leverage error: {e}")
        return False

    # ─────────────────────────────────────────
    # Multi-Market Discovery
    # ─────────────────────────────────────────

    async def _fetch_all_tickers(self) -> Optional[List[Dict]]:
        """Fetch all /fapi/v1/ticker/24hr entries (no-symbol form)."""
        try:
            url = f"{self.base_url}/fapi/v1/ticker/24hr"
            s = await self._get_session()
            async with s.get(url) as r:
                if r.status != 200:
                    self.logger.error(f"24hr ticker (all) HTTP {r.status}")
                    return None
                return await r.json()
        except asyncio.TimeoutError:
            self.logger.warning("⏱ Timeout fetching 24hr ticker list")
        except Exception as e:
            self.logger.error(f"_fetch_all_tickers error: {e}")
        return None

    async def _get_perpetual_trading_set(self) -> frozenset:
        """
        Return a frozenset of symbols that are both PERPETUAL contract type AND
        have TRADING status on Binance USDM. Cached for _perpetual_cache_ttl seconds
        (default 1 hour) to avoid hammering the exchangeInfo endpoint.
        """
        now = time.time()
        if (self._perpetual_trading_symbols is not None and
                now - self._perpetual_cache_time < self._perpetual_cache_ttl):
            return self._perpetual_trading_symbols

        try:
            url = f"{self.base_url}/fapi/v1/exchangeInfo"
            s   = await self._get_session()
            async with s.get(url) as r:
                if r.status != 200:
                    self.logger.warning(f"exchangeInfo HTTP {r.status} — perpetual filter disabled")
                    return frozenset()
                info = await r.json()

            valid = frozenset(
                sym_info["symbol"]
                for sym_info in info.get("symbols", [])
                if sym_info.get("contractType") == "PERPETUAL"
                and sym_info.get("status") == "TRADING"
            )
            self._perpetual_trading_symbols = valid
            self._perpetual_cache_time      = now
            self.logger.debug(f"🗂️  Perpetual-trading whitelist refreshed: {len(valid)} symbols")
            return valid

        except Exception as e:
            self.logger.warning(f"_get_perpetual_trading_set error: {e} — filter disabled")
            return frozenset()

    async def get_all_usdm_symbols(
        self,
        min_volume_usdt: float = None,
        max_symbols: int = None,
    ) -> List[str]:
        """
        Fetch all active USDM PERPETUAL futures symbols sorted by 24h quote volume
        (highest liquidity first). Filters by minimum 24h USDT volume to exclude
        illiquid micro-caps. Only PERPETUAL contracts with TRADING status are included
        (SETTLING / BREAK / delivery symbols are excluded). BTCUSDT is always first.

        Args:
            min_volume_usdt: Minimum 24h USDT volume (default: self.MIN_VOLUME_USDT)
            max_symbols:     Cap on returned symbols (default: self.MAX_SYMBOLS)

        Returns:
            List of symbol strings e.g. ["BTCUSDT", "ETHUSDT", ...]
        """
        min_vol = min_volume_usdt if min_volume_usdt is not None else self.MIN_VOLUME_USDT
        cap     = max_symbols     if max_symbols     is not None else self.MAX_SYMBOLS

        # Fetch the PERPETUAL+TRADING whitelist and 24 h tickers concurrently
        perpetual_set, tickers = await asyncio.gather(
            self._get_perpetual_trading_set(),
            self._fetch_all_tickers(),
        )
        if tickers is None:
            return ["BTCUSDT"]

        qualifying: List[Tuple[float, str]] = []
        for t in tickers:
            sym = t.get("symbol", "")
            # Primary guard: must be in the PERPETUAL+TRADING whitelist.
            # When the whitelist is empty (exchangeInfo fetch failed) we fall
            # back to the name-based heuristic (endswith USDT, no underscore).
            if perpetual_set:
                if sym not in perpetual_set:
                    continue
            else:
                if not sym.endswith("USDT") or "_" in sym:
                    continue
            try:
                quote_vol = float(t.get("quoteVolume", 0))
            except (ValueError, TypeError):
                continue
            if quote_vol >= min_vol:
                qualifying.append((quote_vol, sym))

        qualifying.sort(reverse=True)
        symbols = [sym for _, sym in qualifying[:cap]]

        if "BTCUSDT" not in symbols:
            symbols.insert(0, "BTCUSDT")
        else:
            symbols.remove("BTCUSDT")
            symbols.insert(0, "BTCUSDT")

        self.logger.info(
            f"🌐 Discovered {len(symbols)} USDM symbols "
            f"(min_vol=${min_vol/1e6:.0f}M, cap={cap}) — "
            f"top 5: {symbols[:5]}"
        )
        return symbols

    async def get_price_for_symbol(self, symbol: str) -> Optional[float]:
        """Fetch mark/last price for any single USDM symbol."""
        try:
            url = f"{self.base_url}/fapi/v1/ticker/price"
            s = await self._get_session()
            async with s.get(url, params={"symbol": symbol}) as r:
                if r.status == 200:
                    data = await r.json()
                    return float(data["price"])
                self.logger.debug(f"Price fetch {symbol}: HTTP {r.status}")
        except asyncio.TimeoutError:
            self.logger.warning(f"⏱ Timeout fetching price {symbol}")
        except Exception as e:
            self.logger.debug(f"get_price_for_symbol({symbol}) error: {e}")
        return None

    async def get_prices_for_symbols(self, symbols: List[str]) -> Dict[str, float]:
        """
        Batch-fetch prices for multiple symbols in a single API call
        (uses the no-symbol form of /fapi/v1/ticker/price which returns all).
        Falls back to individual calls if the batch call fails.
        """
        try:
            url = f"{self.base_url}/fapi/v1/ticker/price"
            s = await self._get_session()
            async with s.get(url) as r:
                if r.status == 200:
                    all_tickers = await r.json()
                    price_map: Dict[str, float] = {}
                    sym_set = set(symbols)
                    for t in all_tickers:
                        sym = t.get("symbol", "")
                        if sym in sym_set:
                            try:
                                price_map[sym] = float(t["price"])
                            except (KeyError, ValueError):
                                pass
                    return price_map
        except Exception as e:
            self.logger.warning(f"Batch price fetch failed: {e} — falling back to individual")

        results: Dict[str, float] = {}
        tasks = [self.get_price_for_symbol(sym) for sym in symbols]
        prices = await asyncio.gather(*tasks, return_exceptions=True)
        for sym, price in zip(symbols, prices):
            if isinstance(price, float):
                results[sym] = price
        return results

    # ─────────────────────────────────────────
    # Convenience wrappers (backwards compat)
    # ─────────────────────────────────────────

    async def get_30m_klines(self, limit: int = 500) -> Optional[List]:
        return await self.get_klines("30m", limit=limit)

    async def get_1m_klines(self, limit: int = 500) -> Optional[List]:
        return await self.get_klines("1m", limit=limit)
