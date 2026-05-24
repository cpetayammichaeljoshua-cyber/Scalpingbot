#!/usr/bin/env python3
"""
Public API Market Intelligence — Free Data Feeds for Trading Signals
====================================================================
Integrates curated free public APIs from github.com/public-apis/public-apis
to provide REAL market intelligence data that enhances signal quality.

Data sources (all free, no API key required):
  1. Fear & Greed Index   — alternative.me/crypto/fear-and-greed/
  2. CoinGecko Global     — api.coingecko.com/api/v3/global
  3. CoinGecko Trending   — api.coingecko.com/api/v3/search/trending
  4. CoinCap Assets       — api.coincap.io/v2/assets

All data is cached with configurable TTLs and refreshed in the background.
Thread-safe reads via simple attribute access.  The async refresh loop
runs as an asyncio task alongside the main scanner.
"""

import asyncio
import logging
import time
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class PublicAPIIntelligence:
    """
    Aggregates free public API data into a unified market intelligence feed.
    Background refresh loop runs as an asyncio.Task alongside the main scanner.
    """

    FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1&format=json"
    COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
    COINGECKO_TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"
    COINCAP_BTC_URL = "https://api.coincap.io/v2/assets/bitcoin"

    FEAR_GREED_TTL = 600
    GLOBAL_DATA_TTL = 300
    TRENDING_TTL = 900
    COINCAP_TTL = 120

    REFRESH_INTERVAL = 120
    REQUEST_TIMEOUT = 10

    def __init__(self):
        self._fear_greed_value: int = 50
        self._fear_greed_label: str = "Neutral"
        self._fear_greed_ts: float = 0.0

        self._btc_dominance: float = 0.0
        self._total_market_cap_change_24h: float = 0.0
        self._active_cryptocurrencies: int = 0
        self._global_data_ts: float = 0.0

        self._trending_coins: list = []
        self._trending_ts: float = 0.0

        self._btc_change_24h: float = 0.0
        self._coincap_ts: float = 0.0

        self._session = None
        self._initialized = False
        self._consecutive_failures = 0
        self._max_consecutive_failures = 10

        logger.info(
            "📡 PublicAPIIntelligence initialized — "
            "Fear&Greed + CoinGecko + CoinCap feeds active"
        )

    @property
    def fear_greed_index(self) -> int:
        return self._fear_greed_value

    @property
    def fear_greed_label(self) -> str:
        return self._fear_greed_label

    @property
    def btc_dominance(self) -> float:
        return self._btc_dominance

    @property
    def market_cap_change_24h(self) -> float:
        return self._total_market_cap_change_24h

    @property
    def btc_change_24h(self) -> float:
        return self._btc_change_24h

    @property
    def trending_coins(self) -> list:
        return self._trending_coins

    @property
    def is_fresh(self) -> bool:
        return self._fear_greed_ts > 0 and (time.time() - self._fear_greed_ts) < self.FEAR_GREED_TTL * 3

    def get_sentiment_adjustment(self) -> float:
        if not self.is_fresh:
            return 0.0

        fg = self._fear_greed_value

        if fg <= 15:
            return -6.0
        elif fg <= 25:
            return -3.0
        elif fg >= 85:
            return -5.0
        elif fg >= 75:
            return -2.0
        elif 40 <= fg <= 60:
            return 0.0
        elif fg > 60:
            return 1.0
        else:
            return -1.0

    def get_directional_bias(self) -> Dict[str, float]:
        if not self.is_fresh:
            return {"buy_adj": 0.0, "sell_adj": 0.0}

        fg = self._fear_greed_value
        mkt_chg = self._total_market_cap_change_24h

        buy_adj = 0.0
        sell_adj = 0.0

        if fg <= 20:
            buy_adj += 2.0
            sell_adj -= 1.0
        elif fg <= 30:
            buy_adj += 1.0
        elif fg >= 80:
            sell_adj += 2.0
            buy_adj -= 1.0
        elif fg >= 70:
            sell_adj += 1.0

        if mkt_chg > 3.0:
            sell_adj += 1.5
            buy_adj -= 0.5
        elif mkt_chg > 1.5:
            buy_adj += 0.5
        elif mkt_chg < -3.0:
            buy_adj += 1.5
            sell_adj -= 0.5
        elif mkt_chg < -1.5:
            sell_adj += 0.5

        return {"buy_adj": buy_adj, "sell_adj": sell_adj}

    def get_market_summary(self) -> Dict[str, Any]:
        return {
            "fear_greed": self._fear_greed_value,
            "fear_greed_label": self._fear_greed_label,
            "btc_dominance": round(self._btc_dominance, 2),
            "market_cap_change_24h": round(self._total_market_cap_change_24h, 2),
            "btc_change_24h": round(self._btc_change_24h, 2),
            "trending": [c.get("name", "?") for c in self._trending_coins[:5]],
            "is_fresh": self.is_fresh,
        }

    async def start(self):
        try:
            import aiohttp
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT),
                headers={"Accept": "application/json"},
            )
        except Exception as e:
            logger.warning(f"📡 PublicAPI: Failed to create session: {e}")
            return

        await self._refresh_all()
        self._initialized = True
        logger.info(
            f"📡 PublicAPI initial fetch complete — "
            f"Fear&Greed={self._fear_greed_value} ({self._fear_greed_label}) | "
            f"BTC dom={self._btc_dominance:.1f}% | "
            f"Mkt cap Δ24h={self._total_market_cap_change_24h:+.1f}%"
        )

    async def run(self):
        if not self._initialized:
            await self.start()

        while True:
            try:
                await asyncio.sleep(self.REFRESH_INTERVAL)
                await self._refresh_all()
                self._consecutive_failures = 0
            except asyncio.CancelledError:
                logger.info("📡 PublicAPIIntelligence cancelled")
                break
            except Exception as e:
                self._consecutive_failures += 1
                logger.warning(
                    f"📡 PublicAPI refresh error ({self._consecutive_failures}/"
                    f"{self._max_consecutive_failures}): {e}"
                )
                if self._consecutive_failures >= self._max_consecutive_failures:
                    logger.error("📡 PublicAPI: too many failures, pausing 10min")
                    await asyncio.sleep(600)
                    self._consecutive_failures = 0
                else:
                    await asyncio.sleep(30)

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _refresh_all(self):
        now = time.time()
        tasks = []

        if now - self._fear_greed_ts >= self.FEAR_GREED_TTL:
            tasks.append(self._fetch_fear_greed())

        if now - self._global_data_ts >= self.GLOBAL_DATA_TTL:
            tasks.append(self._fetch_coingecko_global())

        if now - self._trending_ts >= self.TRENDING_TTL:
            tasks.append(self._fetch_coingecko_trending())

        if now - self._coincap_ts >= self.COINCAP_TTL:
            tasks.append(self._fetch_coincap_btc())

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_get(self, url: str) -> Optional[Dict]:
        if not self._session or self._session.closed:
            return None
        try:
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 429:
                    logger.debug(f"📡 Rate limited: {url}")
                else:
                    logger.debug(f"📡 HTTP {resp.status}: {url}")
        except asyncio.TimeoutError:
            logger.debug(f"📡 Timeout: {url}")
        except Exception as e:
            logger.debug(f"📡 Fetch error {url}: {e}")
        return None

    async def _fetch_fear_greed(self):
        data = await self._safe_get(self.FEAR_GREED_URL)
        if data and "data" in data and data["data"]:
            entry = data["data"][0]
            self._fear_greed_value = int(entry.get("value", 50))
            self._fear_greed_label = entry.get("value_classification", "Neutral")
            self._fear_greed_ts = time.time()

    async def _fetch_coingecko_global(self):
        data = await self._safe_get(self.COINGECKO_GLOBAL_URL)
        if data and "data" in data:
            try:
                gd = data["data"]
                mcp = gd.get("market_cap_percentage")
                self._btc_dominance = float(mcp.get("btc", 0)) if isinstance(mcp, dict) else 0.0
                chg = gd.get("market_cap_change_percentage_24h_usd", 0)
                self._total_market_cap_change_24h = float(chg) if chg else 0.0
                self._active_cryptocurrencies = int(gd.get("active_cryptocurrencies", 0))
                self._global_data_ts = time.time()
            except (KeyError, TypeError, ValueError) as e:
                logger.debug(f"📡 CoinGecko global parse error: {e}")

    async def _fetch_coingecko_trending(self):
        data = await self._safe_get(self.COINGECKO_TRENDING_URL)
        if data and "coins" in data:
            self._trending_coins = [
                {
                    "name": c.get("item", {}).get("name", "?"),
                    "symbol": c.get("item", {}).get("symbol", "?"),
                    "market_cap_rank": c.get("item", {}).get("market_cap_rank", 0),
                }
                for c in data["coins"][:10]
            ]
            self._trending_ts = time.time()

    async def _fetch_coincap_btc(self):
        data = await self._safe_get(self.COINCAP_BTC_URL)
        if data and "data" in data:
            btc = data["data"]
            chg = btc.get("changePercent24Hr", "0")
            self._btc_change_24h = float(chg) if chg else 0.0
            self._coincap_ts = time.time()
