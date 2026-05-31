#!/usr/bin/env python3
"""
Universal USDM Futures Trader — v8.0 (April 2026)
Binance USDM Futures — full API wrapper supporting ALL perpetual markets.
Multi-market edition: scans all active USDM perpetual symbols.

KEY IMPROVEMENTS v8.0:
  • Multi-endpoint failover: fapi.binance.com → fapi1-fapi5.binance.com
    Resolves HTTP 451 geo-block on Replit/cloud environments
  • SPOT klines fallback (data.binance.com/api/v3) when all FAPI blocked
  • Hardcoded fallback symbol list (top 80 USDM perps by volume, April 2026)
    — ensures bot continues scanning when ticker endpoint is geo-blocked
  • Endpoint health tracking — blocks confirmed-451 endpoints automatically
  • All network methods use endpoint rotation: get_klines, get_current_price,
    _fetch_all_tickers, _get_perpetual_trading_set, get_funding_rate
  • Persistent shared aiohttp.ClientSession with generous limits
"""

import asyncio
import logging
import re
import aiohttp
import os
from collections import OrderedDict
from typing import Dict, Any, Optional, List, Tuple, Set
from datetime import datetime
import hmac
import hashlib
import time


# ─────────────────────────────────────────────────────────────────────────────
# Global klines rate-limiter — v28.0
# 76 symbols × multiple timeframes all fire get_klines() concurrently via
# asyncio.gather(), hammering Binance's klines endpoint → HTTP 429 storms.
# Semaphore(8): max 8 concurrent klines fetches — remaining callers queue behind.
# Lazy creation: bound to the running event loop on first acquisition, safe to
# define at module level without a running loop (Python 3.10+ asyncio primitives).
# ─────────────────────────────────────────────────────────────────────────────
_KLINES_SEMAPHORE: Optional["asyncio.Semaphore"] = None


def _get_klines_semaphore() -> "asyncio.Semaphore":
    """Return the module-level klines semaphore, creating it lazily on first call."""
    global _KLINES_SEMAPHORE
    if _KLINES_SEMAPHORE is None:
        _KLINES_SEMAPHORE = asyncio.Semaphore(8)
    return _KLINES_SEMAPHORE


# ─────────────────────────────────────────────────────────────────────────────
# Alternative Binance FAPI Endpoints — rotated on HTTP 451 geo-block
# Binance operates CDN mirrors on fapi1-fapi5 with different IP allocations
# that may bypass region-based restrictions on the primary fapi.binance.com
# ─────────────────────────────────────────────────────────────────────────────
_FAPI_ENDPOINTS: List[str] = [
    "https://fapi.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi3.binance.com",
    "https://fapi4.binance.com",
    "https://fapi5.binance.com",
]

# Spot klines fallback — used when ALL FAPI endpoints fail with 451/geo-block.
# USDM perpetual prices track spot extremely closely; close prices are valid
# as input for technical indicators even if the instrument is a futures contract.
_SPOT_KLINES_ENDPOINT = "https://data.binance.com/api/v3/klines"

# ─────────────────────────────────────────────────────────────────────────────
# Hardcoded Fallback Symbol List — top 80 USDM perpetuals by 24h volume
# April 2026 — used when the Binance 24hr ticker endpoint returns 451/error.
# Refreshed periodically from Binance market data.
# ─────────────────────────────────────────────────────────────────────────────
_FALLBACK_USDM_SYMBOLS: List[str] = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "SUIUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "INJUSDT",
    "NEARUSDT", "MATICUSDT", "LTCUSDT", "SEIUSDT", "TIAUSDT",
    "ATOMUSDT", "FTMUSDT", "AAVEUSDT", "UNIUSDT", "LDOUSDT",
    "WLDUSDT", "ORDIUSDT", "RUNEUSDT", "STXUSDT", "IMXUSDT",
    "MKRUSDT", "FETUSDT", "AGIXUSDT", "RNDRUSDT", "GMXUSDT",
    "DYDXUSDT", "GALAUSDT", "SANDUSDT", "AXSUSDT", "FLOWUSDT",
    "ICPUSDT", "FILUSDT", "TRXUSDT", "ETCUSDT", "BCHUSDT",
    "XLMUSDT", "VETUSDT", "THETAUSDT", "ALGOUSDT", "GRTUSDT",
    "SNXUSDT", "CRVUSDT", "COMPUSDT", "EGLDUSDT", "XMRUSDT",
    "BATUSDT", "ZRXUSDT", "BANDUSDT", "STORJUSDT", "RLCUSDT",
    "CFXUSDT", "WOOUSDT", "KNCUSDT", "MASKUSDT", "CELOUSDT",
    "PERPUSDT", "BLZUSDT", "REEFUSDT", "CTKUSDT", "FLMUSDT",
    "STMXUSDT", "OGUSDT", "ENJUSDT", "ZILUSDT", "XTZUSDT",
    "QNTUSDT", "HBARUSDT", "MNTUSDT", "ARKMUSDT", "KASUSDT",
    "JOEUSDT", "PENDLEUSDT", "PYTHUSDT", "SATSUSDT", "BOMEUSDT",
]


class BTCUSDTTrader:
    """
    Binance USDM Futures trader — supports ALL USDM perpetual markets.
    Backward-compatible: default symbol is BTCUSDT.

    v8.0: Multi-endpoint failover resolves HTTP 451 geo-restriction.
    """

    SYMBOL = "BTCUSDT"
    MAINNET_URL = "https://fapi.binance.com"
    TESTNET_URL = "https://testnet.binancefuture.com"
    REQUEST_TIMEOUT = 15  # seconds

    MIN_VOLUME_USDT = 10_000_000   # min 24h USDT volume to qualify for scanning
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

        # ── Multi-endpoint failover state ─────────────────────────────────────
        # Tracks which FAPI endpoints have returned HTTP 451 (geo-blocked).
        # Once blocked, an endpoint is skipped for _endpoint_block_ttl seconds
        # before being retried (in case the block is temporary).
        self._geo_blocked_endpoints: Dict[str, float] = {}  # url → blocked_until ts
        self._endpoint_block_ttl = 3600.0  # 1 hour before retrying a blocked endpoint
        self._current_fapi_idx = 0  # Index into _FAPI_ENDPOINTS for round-robin rotation

        # Track whether we've fallen back to spot klines (informational)
        self._using_spot_fallback = False

        # Short-lived klines cache — keyed by (symbol, interval, limit).
        # TTL of 120s avoids duplicate Binance fetches when process_signals
        # re-requests the same klines that the strategy just fetched.
        # OrderedDict enables O(1) LRU eviction.
        self._klines_cache: OrderedDict = OrderedDict()
        self._klines_cache_ttl = 180.0   # v28.0: 120→180s — 50% more cache reuse per cycle, reduces API calls
        self._klines_cache_max = 500

        # Perpetual-symbol whitelist — refreshed every 60 minutes via exchangeInfo.
        self._perpetual_trading_symbols: Optional[frozenset] = None
        self._perpetual_cache_time: float = 0.0
        self._perpetual_cache_ttl: float = 3600.0  # 1 hour

        # IP ban tracking — Binance returns HTTP 418 when an IP is banned.
        self._ip_banned_until: float = 0.0
        self._ip_ban_last_logged: float = 0.0

        self.logger.info(
            f"✅ BTCUSDTTrader v8.0 — {'Testnet' if self.testnet else 'Mainnet'} | "
            f"Multi-endpoint failover: {len(_FAPI_ENDPOINTS)} FAPI endpoints | "
            f"Fallback: {len(_FALLBACK_USDM_SYMBOLS)} hardcoded symbols | "
            f"Spot klines fallback: {_SPOT_KLINES_ENDPOINT}"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Multi-Endpoint Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _get_fapi_endpoints(self) -> List[str]:
        """
        Return the list of FAPI endpoints to try, with currently-blocked ones
        filtered out (unless the block has expired).
        Always includes at least one endpoint.
        """
        now = time.time()
        available = [
            ep for ep in _FAPI_ENDPOINTS
            if now >= self._geo_blocked_endpoints.get(ep, 0.0)
        ]
        if not available:
            # All endpoints blocked — reset oldest one to retry
            self.logger.warning("⚠️ All FAPI endpoints geo-blocked — resetting oldest block")
            oldest = min(self._geo_blocked_endpoints, key=self._geo_blocked_endpoints.get)
            self._geo_blocked_endpoints.pop(oldest)
            available = [oldest]
        return available

    def _record_geo_block(self, endpoint: str) -> None:
        """Mark an endpoint as geo-blocked (HTTP 451) for _endpoint_block_ttl seconds."""
        self._geo_blocked_endpoints[endpoint] = time.time() + self._endpoint_block_ttl
        self.logger.warning(
            f"🌐 HTTP 451 geo-block on {endpoint} — rotating to next FAPI endpoint "
            f"(will retry in {self._endpoint_block_ttl/60:.0f}min)"
        )

    def _record_endpoint_success(self, endpoint: str) -> None:
        """Clear geo-block status for a successfully-responding endpoint."""
        self._geo_blocked_endpoints.pop(endpoint, None)
        if self.base_url != endpoint:
            self.logger.info(f"✅ Active FAPI endpoint switched to: {endpoint}")
            self.base_url = endpoint

    # ─────────────────────────────────────────────────────────────────────────
    # Persistent Session Management
    # ─────────────────────────────────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Return the shared persistent HTTP session, creating it on first call.
        Uses a TCPConnector with generous limits for parallel scanning of 80 symbols
        across multiple alternative FAPI endpoints.
        """
        if self._session is None or self._session.closed:
            self._connector = aiohttp.TCPConnector(
                limit=80,           # max 80 total concurrent connections
                limit_per_host=30,  # max 30 per host (multi-endpoint routing)
                ttl_dns_cache=300,  # cache DNS for 5 minutes
                enable_cleanup_closed=True,
            )
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT),
            )
            self.logger.debug("🔗 Shared aiohttp session created (multi-endpoint connector active)")
        return self._session

    async def aclose(self):
        """Gracefully close the shared session and connector."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session   = None
        self._connector = None
        self.logger.debug("🔗 Shared aiohttp session closed")

    # ─────────────────────────────────────────────────────────────────────────
    # IP Ban Handling (Binance HTTP 418)
    # ─────────────────────────────────────────────────────────────────────────

    def _record_ip_ban(self, body: str) -> float:
        """Parse Binance HTTP 418 ban, record expiry, return wait seconds."""
        ban_until_secs: float = 0.0
        m = re.search(r'banned until (\d{10,13})', body)
        if m:
            raw_ts = int(m.group(1))
            ban_until_secs = raw_ts / 1000.0 if raw_ts > 1e12 else float(raw_ts)
        if ban_until_secs < time.time():
            ban_until_secs = time.time() + 300.0
        self._ip_banned_until = ban_until_secs
        wait_secs = max(0.0, ban_until_secs - time.time())
        self.logger.error(
            f"🚫 BINANCE IP BAN (HTTP 418) — banned until "
            f"{datetime.utcfromtimestamp(ban_until_secs).strftime('%H:%M:%S UTC')} "
            f"({wait_secs / 60:.1f} min). All API calls paused."
        )
        return wait_secs

    def is_ip_banned(self) -> bool:
        """Return True if a Binance IP ban is currently active."""
        return self._ip_banned_until > time.time()

    def ip_ban_wait_seconds(self) -> float:
        """Return remaining ban wait seconds (0 if not banned)."""
        return max(0.0, self._ip_banned_until - time.time())

    async def _wait_ip_ban_if_needed(self) -> None:
        """Sleep if IP is currently banned. Deduplicates log messages."""
        now = time.time()
        if self._ip_banned_until > now:
            wait = self._ip_banned_until - now
            if now - self._ip_ban_last_logged >= 60.0:
                self._ip_ban_last_logged = now
                self.logger.warning(
                    f"⏸ IP ban active — waiting {wait:.1f}s "
                    f"(expires {datetime.utcfromtimestamp(self._ip_banned_until).strftime('%H:%M:%S UTC')})"
                )
            await asyncio.sleep(min(wait, 30.0))

    # ─────────────────────────────────────────────────────────────────────────
    # Auth Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _sign(self, query_string: str) -> str:
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _auth_headers(self) -> dict:
        return {"X-MBX-APIKEY": self.api_key}

    def _signed_params(self, params: dict) -> dict:
        """Return a NEW dict with timestamp + HMAC-SHA256 signature appended."""
        p = dict(params)
        p["timestamp"] = int(time.time() * 1000)
        query = "&".join(f"{k}={v}" for k, v in p.items())
        p["signature"] = self._sign(query)
        return p

    # ─────────────────────────────────────────────────────────────────────────
    # Core HTTP helper — multi-endpoint GET with 451 rotation
    # ─────────────────────────────────────────────────────────────────────────

    async def _get_fapi(self, path: str, params: dict = None,
                        retries: int = 2) -> Optional[Any]:
        """
        Perform a GET request to the Binance FAPI, automatically rotating to
        alternative endpoints when the primary returns HTTP 451 (geo-block).

        Tries all available endpoints before giving up.
        Returns parsed JSON or None on failure.
        """
        await self._wait_ip_ban_if_needed()
        if params is None:
            params = {}

        endpoints = self._get_fapi_endpoints()

        for endpoint in endpoints:
            url = f"{endpoint}{path}"
            for attempt in range(retries):
                try:
                    s = await self._get_session()
                    async with s.get(url, params=params) as r:
                        if r.status == 200:
                            self._record_endpoint_success(endpoint)
                            return await r.json()

                        if r.status == 451:
                            self._record_geo_block(endpoint)
                            break  # Try next endpoint immediately

                        if r.status == 418:
                            body = await r.text()
                            self._record_ip_ban(body)
                            return None

                        if r.status == 429:
                            _retry = int(r.headers.get("Retry-After", "5"))
                            _retry = max(1, min(_retry, 60))
                            self.logger.warning(
                                f"⏳ Binance 429 {path} (attempt {attempt+1}) — backing off {_retry}s"
                            )
                            await asyncio.sleep(_retry)
                            continue

                        body = await r.text()
                        self.logger.debug(f"FAPI {path} HTTP {r.status}: {body[:200]}")
                        if 400 <= r.status < 500:
                            return None  # Permanent client error

                except asyncio.TimeoutError:
                    if attempt < retries - 1:
                        await asyncio.sleep(2 ** attempt)
                except Exception as e:
                    self.logger.debug(f"_get_fapi({path}) error [{endpoint}]: {e}")
                    break

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Market Data — Public (no auth)
    # ─────────────────────────────────────────────────────────────────────────

    async def get_current_price(self, symbol: Optional[str] = None) -> Optional[float]:
        """
        Get current mark price for any USDM symbol.
        Rotates through alternative FAPI endpoints on 451 geo-block.
        """
        sym = symbol or self.symbol
        data = await self._get_fapi("/fapi/v1/ticker/price", {"symbol": sym})
        if data and "price" in data:
            price = float(data["price"])
            self.logger.debug(f"💰 {sym} price: ${price:,.4g}")
            return price
        return None

    async def get_market_data(self, symbol: str, timeframe: str, limit: int = 500) -> Optional[List]:
        """Fetch klines / candlestick data (served from cache when fresh)"""
        return await self.get_klines(timeframe, limit=limit, symbol=symbol)

    async def get_klines(self, interval: str, limit: int = 500,
                         symbol: Optional[str] = None) -> Optional[List]:
        """
        Fetch klines from Binance USDM Futures with multi-endpoint failover.

        Failover chain on HTTP 451:
          1. Try fapi.binance.com (primary)
          2. Try fapi1-fapi5.binance.com (CDN mirrors, different IPs)
          3. Fall back to data.binance.com SPOT klines (close prices ~identical)

        Results are cached for _klines_cache_ttl seconds to prevent duplicate
        API calls when process_signals re-fetches klines the strategy already pulled.
        """
        sym = symbol or self.symbol
        limit = min(limit, 1500)
        now = time.time()

        # Check exact cache hit
        cache_key = (sym, interval, limit)
        cached = self._klines_cache.get(cache_key)
        if cached is not None:
            data, fetched_at = cached
            if now - fetched_at < self._klines_cache_ttl:
                self._klines_cache.move_to_end(cache_key)
                return data

        # Check if a larger cached result can satisfy this request
        for (c_sym, c_interval, c_limit), (c_data, c_time) in list(self._klines_cache.items()):
            if (c_sym == sym and c_interval == interval and
                    c_limit >= limit and now - c_time < self._klines_cache_ttl):
                self._klines_cache.move_to_end((c_sym, c_interval, c_limit))
                return c_data[-limit:] if len(c_data) >= limit else c_data

        # v28.0: Acquire the global rate-limiter slot before any network I/O.
        # Caps concurrent klines fetches at 8 — eliminates Binance HTTP 429
        # storms caused by 76+ symbols all firing get_klines() simultaneously
        # via asyncio.gather(). Cache hits (above) bypass the semaphore entirely.
        async with _get_klines_semaphore():
            return await self._do_fetch_klines(sym, interval, limit, cache_key, now)

    async def _do_fetch_klines(self, sym: str, interval: str, limit: int,
                                cache_key: tuple, now: float) -> Optional[List]:
        """
        Network-fetch implementation for get_klines — always called inside
        _get_klines_semaphore() to prevent concurrent Binance 429 storms.
        Tries all FAPI endpoints then falls back to SPOT klines on geo-block.
        [v28.0: extracted from get_klines for semaphore gating]
        """
        await self._wait_ip_ban_if_needed()

        params = {"symbol": sym, "interval": interval, "limit": limit}

        # ── Phase 1: Try all FAPI endpoints ──────────────────────────────────
        endpoints = self._get_fapi_endpoints()
        for endpoint in endpoints:
            url = f"{endpoint}/fapi/v1/klines"
            _max_attempts = 3
            for _attempt in range(_max_attempts):
                try:
                    s = await self._get_session()
                    async with s.get(url, params=params) as r:
                        if r.status == 200:
                            data = await r.json()
                            self._record_endpoint_success(endpoint)
                            self._using_spot_fallback = False
                            # Cache the result
                            if cache_key in self._klines_cache:
                                self._klines_cache.move_to_end(cache_key)
                            self._klines_cache[cache_key] = (data, now)
                            while len(self._klines_cache) > self._klines_cache_max:
                                self._klines_cache.popitem(last=False)
                            return data

                        if r.status == 451:
                            self._record_geo_block(endpoint)
                            break  # Next endpoint

                        if r.status == 429:
                            # v28.0: exponential backoff — prevents thundering-herd re-retry
                            _retry_base = int(r.headers.get("Retry-After", "5"))
                            _retry = min(60, _retry_base * (2 ** _attempt) + _attempt)
                            self.logger.warning(
                                f"⏳ Binance 429 klines [{sym}|{interval}] "
                                f"(attempt {_attempt+1}/{_max_attempts}) — backing off {_retry}s [v28.0]"
                            )
                            await asyncio.sleep(_retry)
                            continue

                        body = await r.text()
                        if r.status == 418:
                            self._record_ip_ban(body)
                            return None

                        # v24.0: HTTP 202 = "Accepted" — Binance returns this for symbols
                        # in pre-delivery, maintenance, or pending-delist state.  It is NOT
                        # an error; the symbol simply has no kline data available yet.
                        # Treat as a soft-skip (return None) so the scanner moves on without
                        # flooding Railway logs with spurious ERROR lines every scan cycle.
                        if r.status == 202:
                            self.logger.debug(
                                f"Klines skip [{sym}|{interval}] HTTP 202 "
                                f"(pre-delivery/maintenance symbol) — soft-skip [v24.0]"
                            )
                            return None

                        # 5xx server errors → warning (transient); 4xx client errors → error
                        if r.status >= 500:
                            self.logger.warning(
                                f"Klines server error [{sym}|{interval}] HTTP {r.status} "
                                f"(transient) — will retry next cycle [v24.0]"
                            )
                        else:
                            self.logger.warning(
                                f"Klines error [{sym}|{interval}] HTTP {r.status}: {body[:200]} [v24.0]"
                            )
                        break  # Other errors — no retry

                except asyncio.TimeoutError:
                    if _attempt < _max_attempts - 1:
                        await asyncio.sleep(2 ** _attempt)
                except Exception as e:
                    self.logger.error(f"get_klines error [{endpoint}]: {e}")
                    break

        # ── Phase 2: SPOT klines fallback (data.binance.com) ─────────────────
        # Used only when all FAPI endpoints are geo-blocked. SPOT close prices
        # are virtually identical to USDM perpetual prices for TA purposes.
        try:
            spot_params = {"symbol": sym, "interval": interval, "limit": limit}
            s = await self._get_session()
            async with s.get(_SPOT_KLINES_ENDPOINT, params=spot_params) as r:
                if r.status == 200:
                    data = await r.json()
                    if not self._using_spot_fallback:
                        self.logger.warning(
                            f"📡 [{sym}] All FAPI endpoints geo-blocked — "
                            f"using SPOT klines fallback (data.binance.com)"
                        )
                        self._using_spot_fallback = True
                    # Cache spot result with same key (transparent to callers)
                    self._klines_cache[cache_key] = (data, now)
                    while len(self._klines_cache) > self._klines_cache_max:
                        self._klines_cache.popitem(last=False)
                    return data
                self.logger.debug(f"SPOT klines fallback HTTP {r.status} for {sym}")
        except Exception as e:
            self.logger.debug(f"SPOT klines fallback error [{sym}]: {e}")

        return None

    async def get_24hr_ticker_stats(self, symbol: Optional[str] = None) -> Optional[Dict]:
        """24h rolling window ticker statistics"""
        sym = symbol or self.symbol
        return await self._get_fapi("/fapi/v1/ticker/24hr", {"symbol": sym})

    async def get_order_book(self, symbol: Optional[str] = None, limit: int = 20) -> Optional[Dict]:
        """Fetch order book depth"""
        sym = symbol or self.symbol
        limit = min(limit, 1000)
        return await self._get_fapi("/fapi/v1/depth", {"symbol": sym, "limit": limit})

    async def get_funding_rate(self, symbol: Optional[str] = None) -> Optional[Dict]:
        """Get current funding rate — returns dict with 'fundingRate' key (str)"""
        sym = symbol or self.symbol
        data = await self._get_fapi("/fapi/v1/premiumIndex", {"symbol": sym})
        if data:
            return {
                "fundingRate": data.get("lastFundingRate", "0"),
                "fundingTime": data.get("nextFundingTime", 0),
                "markPrice":   data.get("markPrice", "0"),
                "indexPrice":  data.get("indexPrice", "0"),
            }
        return None

    async def get_open_interest(self, symbol: Optional[str] = None) -> Optional[Dict]:
        """Get current open interest"""
        sym = symbol or self.symbol
        return await self._get_fapi("/fapi/v1/openInterest", {"symbol": sym})

    async def get_exchange_info(self, symbol: Optional[str] = None) -> Dict:
        """Get exchange info for the symbol"""
        sym = symbol or self.symbol
        try:
            data = await self._get_fapi("/fapi/v1/exchangeInfo")
            if data:
                for s_info in data.get("symbols", []):
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

    # ─────────────────────────────────────────────────────────────────────────
    # Account & Position Data — Authenticated
    # ─────────────────────────────────────────────────────────────────────────

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
        """Get open positions for symbol"""
        sym = symbol or self.symbol
        try:
            url    = f"{self.base_url}/fapi/v2/positionRisk"
            params = self._signed_params({"symbol": sym})
            s = await self._get_session()
            async with s.get(url, params=params, headers=self._auth_headers()) as r:
                if r.status == 200:
                    positions = await r.json()
                    return [p for p in positions if float(p.get("positionAmt", 0)) != 0]
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
        leverage = max(1, min(leverage, 125))
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

    # ─────────────────────────────────────────────────────────────────────────
    # Multi-Market Discovery
    # ─────────────────────────────────────────────────────────────────────────

    async def _fetch_all_tickers(self, retries: int = 3) -> Optional[List[Dict]]:
        """
        Fetch all /fapi/v1/ticker/24hr entries (no-symbol form).

        Multi-endpoint failover: if the primary endpoint returns 451,
        automatically tries fapi1-fapi5.binance.com before giving up.
        If ALL endpoints are geo-blocked, returns None (caller uses fallback list).
        """
        await self._wait_ip_ban_if_needed()
        endpoints = self._get_fapi_endpoints()

        for endpoint in endpoints:
            url = f"{endpoint}/fapi/v1/ticker/24hr"
            for attempt in range(retries):
                try:
                    s = await self._get_session()
                    async with s.get(url) as r:
                        if r.status == 200:
                            self._record_endpoint_success(endpoint)
                            return await r.json()

                        if r.status == 451:
                            self._record_geo_block(endpoint)
                            break  # Next endpoint

                        if r.status == 429:
                            _retry_after = int(r.headers.get("Retry-After", "5"))
                            _retry_after = max(1, min(_retry_after, 60))
                            self.logger.warning(
                                f"⏳ Binance 429 24hr ticker "
                                f"(attempt {attempt+1}/{retries}) — backing off {_retry_after}s"
                            )
                            await asyncio.sleep(_retry_after)
                            continue

                        body = await r.text()
                        if r.status == 418:
                            self._record_ip_ban(body)
                            return None

                        self.logger.error(
                            f"24hr ticker HTTP {r.status} "
                            f"(attempt {attempt+1}/{retries}): {body[:200]}"
                        )
                        if 400 <= r.status < 500:
                            return None

                except asyncio.TimeoutError:
                    if attempt < retries - 1:
                        await asyncio.sleep(2 ** attempt)
                except Exception as e:
                    self.logger.error(f"_fetch_all_tickers error [{endpoint}] (attempt {attempt+1}): {e}")
                    break

        # All endpoints exhausted — return None; caller will use fallback symbols
        self.logger.warning(
            "🌐 All FAPI endpoints blocked/failed for 24hr ticker — "
            "will use hardcoded fallback symbol list"
        )
        return None

    async def _get_perpetual_trading_set(self) -> frozenset:
        """
        Return frozenset of PERPETUAL+TRADING symbols from exchangeInfo.
        Cached for 1 hour. Uses multi-endpoint failover on 451.
        Falls back to cached value on any failure.
        """
        now = time.time()
        if (self._perpetual_trading_symbols is not None and
                now - self._perpetual_cache_time < self._perpetual_cache_ttl):
            return self._perpetual_trading_symbols

        if self.is_ip_banned():
            return self._perpetual_trading_symbols or frozenset()

        data = await self._get_fapi("/fapi/v1/exchangeInfo", retries=2)
        if data is not None:
            valid = frozenset(
                sym_info["symbol"]
                for sym_info in data.get("symbols", [])
                if sym_info.get("contractType") == "PERPETUAL"
                and sym_info.get("status") == "TRADING"
            )
            self._perpetual_trading_symbols = valid
            self._perpetual_cache_time      = now
            self.logger.debug(f"🗂️  Perpetual-trading whitelist refreshed: {len(valid)} symbols")
            return valid

        # Failed — return stale cache or empty frozenset
        if self._perpetual_trading_symbols is not None:
            self.logger.debug("exchangeInfo failed — using stale perpetual cache")
            return self._perpetual_trading_symbols
        self.logger.warning("exchangeInfo failed and no cache — perpetual filter disabled")
        return frozenset()

    async def get_all_usdm_symbols(
        self,
        min_volume_usdt: float = None,
        max_symbols: int = None,
    ) -> List[str]:
        """
        Fetch all active USDM PERPETUAL futures symbols sorted by 24h quote volume.

        v8.0: When Binance 24hr ticker returns 451 (geo-block) and ALL alternative
        endpoints are also blocked, automatically falls back to a hardcoded list of
        top 80 USDM perpetuals rather than returning ["BTCUSDT"] only.
        This ensures the bot scans a full universe even under geo-restriction.

        Args:
            min_volume_usdt: Minimum 24h USDT volume
            max_symbols:     Cap on returned symbols

        Returns:
            List of symbol strings e.g. ["BTCUSDT", "ETHUSDT", ...]
        """
        min_vol = min_volume_usdt if min_volume_usdt is not None else self.MIN_VOLUME_USDT
        cap     = max_symbols     if max_symbols     is not None else self.MAX_SYMBOLS

        perpetual_set, tickers = await asyncio.gather(
            self._get_perpetual_trading_set(),
            self._fetch_all_tickers(),
        )

        # ── Fallback: use hardcoded symbol list when API is geo-blocked ──────
        if tickers is None:
            symbols = list(_FALLBACK_USDM_SYMBOLS[:cap])
            if "BTCUSDT" not in symbols:
                symbols.insert(0, "BTCUSDT")
            self.logger.warning(
                f"🌐 Using hardcoded fallback symbol list ({len(symbols)} symbols) — "
                f"Binance ticker API unreachable (geo-block or network error)"
            )
            return symbols

        qualifying: List[Tuple[float, str]] = []
        for t in tickers:
            sym = t.get("symbol", "")
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

        # USDC deduplication: prefer USDT when both XYZUSDT and XYZUSDC qualify
        all_qualifying_syms = {sym for _, sym in qualifying}
        deduplicated: List[str] = []
        n_usdc_dropped = 0
        for _, sym in qualifying:
            if sym.endswith("USDC"):
                usdt_sibling = sym[:-4] + "USDT"
                if usdt_sibling in all_qualifying_syms:
                    n_usdc_dropped += 1
                    continue
            deduplicated.append(sym)
            if len(deduplicated) >= cap:
                break

        symbols = deduplicated

        if "BTCUSDT" not in symbols:
            symbols.insert(0, "BTCUSDT")
        else:
            symbols.remove("BTCUSDT")
            symbols.insert(0, "BTCUSDT")

        dedup_note = f", dropped {n_usdc_dropped} USDC dupes" if n_usdc_dropped else ""
        self.logger.info(
            f"🌐 Discovered {len(symbols)} USDM symbols "
            f"(min_vol=${min_vol/1e6:.0f}M, cap={cap}{dedup_note}) — "
            f"top 5: {symbols[:5]}"
        )
        return symbols

    async def get_price_for_symbol(self, symbol: str) -> Optional[float]:
        """Fetch mark/last price for any single USDM symbol."""
        return await self.get_current_price(symbol)

    async def get_prices_for_symbols(self, symbols: List[str]) -> Dict[str, float]:
        """
        Batch-fetch prices for multiple symbols in a single API call.
        Falls back to individual calls if the batch call fails.
        """
        try:
            data = await self._get_fapi("/fapi/v1/ticker/price")
            if data and isinstance(data, list):
                price_map: Dict[str, float] = {}
                sym_set = set(symbols)
                for t in data:
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
        tasks = [self.get_current_price(sym) for sym in symbols]
        prices = await asyncio.gather(*tasks, return_exceptions=True)
        for sym, price in zip(symbols, prices):
            if isinstance(price, float):
                results[sym] = price
        return results

    # ─────────────────────────────────────────────────────────────────────────
    # Convenience wrappers (backwards compat)
    # ─────────────────────────────────────────────────────────────────────────

    async def get_30m_klines(self, limit: int = 500) -> Optional[List]:
        return await self.get_klines("30m", limit=limit)

    async def get_1m_klines(self, limit: int = 500) -> Optional[List]:
        return await self.get_klines("1m", limit=limit)
