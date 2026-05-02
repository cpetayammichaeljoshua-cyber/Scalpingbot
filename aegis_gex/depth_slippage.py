"""
Order-Book Depth-Weighted Slippage Estimator  (v9.9 / Apex-#2)
==============================================================

Replaces the static SLIPPAGE_PCT × 2 fallback in Gate 0 with a real
depth-walked VWAP slippage number derived from the live Binance USDM
order book.

Method
------
Given (symbol, side, notional_usd), the estimator:

  1. Fetches /fapi/v1/depth?symbol=X&limit=20 (cached `cache_ttl_sec`s).
  2. Walks the relevant side of the book accumulating {price × qty}
     until the cumulative notional ≥ requested notional.
  3. Returns:
        avg_fill_price = sum(p_i * q_i) / sum(q_i)
        slippage_pct   = abs(avg_fill_price - mid) / mid
        cleared_pct    = % of requested notional that was actually fillable
                         within the top 20 levels (1.0 if book is deep enough)

For BUY side we walk the asks (lifting offers); for SELL we walk the bids.
Round-trip slippage = slippage_pct × 2 (entry + exit).

Why it's better than `SLIPPAGE_PCT × 2`
---------------------------------------
The static 0.10% round-trip assumption is optimistic for thin-book alts
(NEIROUSDT, ARCUSDT, etc.) and pessimistic for top-tier pairs (BTCUSDT,
ETHUSDT).  At signal-time the EV gate now sees the **actual cost to fill
the planned notional**, so it correctly:
  • Blocks "looks profitable on mid-price" trades that bleed on real fills.
  • Approves tight-book trades that the static assumption was rejecting.

Cache strategy
--------------
Per-symbol depth snapshot is cached for `cache_ttl_sec` (default 1.5s).
This keeps Binance REST QPS low (~13 req/s for 20 symbols × 0.66 polls/s)
and is well below the 2400 weight/min budget for /fapi/v1/depth at limit=20
(weight=2 per call → 1200 calls/min ceiling).

Failure modes
-------------
  • REST 451 / network error → returns `None`; caller falls back to
    static slippage.  No exception bubbles up.
  • Empty book / malformed payload → `None`.
  • Notional larger than top-20 cumulative → returns the partial VWAP
    plus `cleared_pct < 1.0` so caller can apply a stricter EV penalty.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Optional, Tuple

import aiohttp

try:
    import orjson as _orjson  # type: ignore
    def _loads(b):
        return _orjson.loads(b)
except Exception:
    import json
    def _loads(b):
        if isinstance(b, (bytes, bytearray)):
            b = b.decode("utf-8", errors="replace")
        return json.loads(b)

_log = logging.getLogger("UnityEngine.DepthSlippage")

# Multi-endpoint fallback for geo-blocked Binance regions (mirrors btcusdt_trader)
_FAPI_ENDPOINTS = [
    "https://fapi.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi3.binance.com",
]


class DepthSlippageEstimator:
    """
    Public API:

        est = DepthSlippageEstimator(cache_ttl_sec=1.5)
        await est.start()                                    # creates aiohttp session
        result = await est.estimate("BTCUSDT", "BUY", 10_000.0)
        # result = {
        #     "avg_fill_price": 76512.34,
        #     "mid":            76500.00,
        #     "slip_pct":       0.000161,    # one-leg
        #     "round_trip":     0.000322,    # one-leg × 2
        #     "cleared_pct":    1.0,
        #     "depth_levels":   3,
        #     "age_ms":         420,
        # }
        await est.close()
    """

    def __init__(
        self,
        *,
        cache_ttl_sec: float = 1.5,
        depth_limit: int = 20,
        request_timeout: float = 2.0,
    ) -> None:
        self._cache_ttl = max(0.25, float(cache_ttl_sec))
        self._depth_limit = int(depth_limit)
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        # Per-symbol cache: {symbol: (ts, {"bids": [(p,q)...], "asks": [...]})}
        self._depth_cache: Dict[str, Tuple[float, Dict]] = {}
        # Per-symbol asyncio.Lock to dedupe concurrent fetches for the same symbol
        self._sym_locks: Dict[str, asyncio.Lock] = {}
        # Endpoint-failure tracker (round-robin on 451)
        self._endpoint_idx: int = 0
        # Rolling stats for /metrics
        self._fetches: int = 0
        self._cache_hits: int = 0
        self._errors: int = 0
        self._last_err: str = ""
        # Lazy aiohttp session (created on first use to avoid event-loop binding issues)
        self._session: Optional[aiohttp.ClientSession] = None
        self._closed = False

    # ─── Lifecycle ───────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._session is None and not self._closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
            _log.info(
                f"⚡ [v9.9] DepthSlippageEstimator started "
                f"(cache_ttl={self._cache_ttl:.2f}s, limit={self._depth_limit})"
            )

    async def close(self) -> None:
        self._closed = True
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None

    # ─── Public read API ─────────────────────────────────────────────────

    async def estimate(
        self,
        symbol: str,
        side: str,
        notional_usd: float,
    ) -> Optional[Dict[str, float]]:
        """
        Compute depth-weighted slippage to fill `notional_usd` on `side`.

        Returns None on any error so caller falls back to static estimate.
        """
        if not symbol or notional_usd <= 0:
            return None
        sym = symbol.upper()
        side_up = (side or "").upper()
        if side_up not in ("BUY", "LONG", "SELL", "SHORT"):
            return None
        is_buy = side_up in ("BUY", "LONG")

        snap = await self._get_depth(sym)
        if snap is None:
            return None
        ts, book = snap
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        if not bids or not asks:
            return None
        try:
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
        except (TypeError, ValueError, IndexError):
            return None
        if best_bid <= 0 or best_ask <= 0 or best_ask < best_bid:
            return None
        mid = (best_bid + best_ask) / 2.0

        # Walk the relevant side
        levels = asks if is_buy else bids
        cum_notional = 0.0
        cum_qty = 0.0
        weighted_px = 0.0
        levels_used = 0
        for lvl in levels:
            try:
                p = float(lvl[0])
                q = float(lvl[1])
            except (TypeError, ValueError, IndexError):
                continue
            if p <= 0 or q <= 0:
                continue
            level_notional = p * q
            remaining = notional_usd - cum_notional
            if remaining <= 0:
                break
            take_notional = min(remaining, level_notional)
            take_qty = take_notional / p
            cum_qty += take_qty
            weighted_px += p * take_qty
            cum_notional += take_notional
            levels_used += 1
            if cum_notional >= notional_usd:
                break

        if cum_qty <= 0:
            return None
        avg_fill_price = weighted_px / cum_qty
        slip_pct = abs(avg_fill_price - mid) / mid if mid > 0 else 0.0
        cleared_pct = min(1.0, cum_notional / notional_usd) if notional_usd > 0 else 1.0
        return {
            "avg_fill_price": avg_fill_price,
            "mid":            mid,
            "slip_pct":       slip_pct,         # one-leg
            "round_trip":     slip_pct * 2.0,   # entry + exit
            "cleared_pct":    cleared_pct,
            "depth_levels":   levels_used,
            "age_ms":         int(max(0.0, (time.time() - ts) * 1000.0)),
        }

    def status_summary(self) -> Dict[str, int]:
        return {
            "cached_symbols": len(self._depth_cache),
            "fetches":        self._fetches,
            "cache_hits":     self._cache_hits,
            "errors":         self._errors,
            "last_err":       (self._last_err or "")[:80],
        }

    # ─── Internal: REST fetch w/ cache + per-symbol lock ─────────────────

    async def _get_depth(self, symbol: str) -> Optional[Tuple[float, Dict]]:
        """Return (cache_ts, book_dict) for `symbol`, fetching if cache is cold."""
        now = time.time()
        cached = self._depth_cache.get(symbol)
        if cached is not None and (now - cached[0]) < self._cache_ttl:
            self._cache_hits += 1
            return cached

        # Acquire per-symbol lock to dedupe concurrent fetches
        lock = self._sym_locks.setdefault(symbol, asyncio.Lock())
        async with lock:
            # Re-check cache after acquiring lock (another caller may have populated)
            cached = self._depth_cache.get(symbol)
            if cached is not None and (time.time() - cached[0]) < self._cache_ttl:
                self._cache_hits += 1
                return cached

            book = await self._fetch_depth_rest(symbol)
            if book is None:
                return None
            ts = time.time()
            self._depth_cache[symbol] = (ts, book)
            return (ts, book)

    async def _fetch_depth_rest(self, symbol: str) -> Optional[Dict]:
        """Try each endpoint in round-robin; return the first successful book."""
        if self._session is None:
            await self.start()
        if self._session is None:
            return None

        params = {"symbol": symbol, "limit": str(self._depth_limit)}
        n_endpoints = len(_FAPI_ENDPOINTS)
        for attempt in range(n_endpoints):
            idx = (self._endpoint_idx + attempt) % n_endpoints
            url = f"{_FAPI_ENDPOINTS[idx]}/fapi/v1/depth"
            try:
                async with self._session.get(url, params=params) as r:
                    if r.status == 200:
                        body = await r.read()
                        try:
                            data = _loads(body)
                        except Exception as e:
                            self._last_err = f"parse: {e}"
                            continue
                        if not isinstance(data, dict):
                            continue
                        bids = data.get("bids") or []
                        asks = data.get("asks") or []
                        if not bids or not asks:
                            continue
                        # Success — pin this endpoint as primary for next call
                        self._endpoint_idx = idx
                        self._fetches += 1
                        return {"bids": bids, "asks": asks}
                    elif r.status in (451, 418, 403, 429):
                        # Geo-block / rate-limit → try next endpoint
                        self._last_err = f"HTTP {r.status} on {url}"
                        continue
                    else:
                        self._last_err = f"HTTP {r.status}"
                        continue
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._last_err = f"{type(e).__name__}: {e}"
                continue

        self._errors += 1
        return None
