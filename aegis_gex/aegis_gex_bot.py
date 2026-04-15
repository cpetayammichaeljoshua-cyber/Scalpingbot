#!/usr/bin/env python3
"""
AEGIS GEX v1.0 — Standalone Telegram Signal Bot
=================================================
Fully isolated from all other strategies.
Uses ONLY the GEX flip engine for signal generation.

Signal Logic (strict):
  - Entry  : when price crosses a GEX flip level right now
  - TP     : the NEXT GEX flip level in the direction of trade
             (updated dynamically as new flips appear during the trade)
  - SL     : ATR buffer beyond the entry flip level

Telegram format: Cornix-compatible (same channel as main bot)
Workflow: completely separate — does not share state with main bot.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import aiohttp

from aegis_gex.gex_engine import (
    AEGISGEXEngine,
    GEXSignal,
    GEXSnapshot,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Hard-coded fallback symbol universe (top 80 USDM perps by volume)
# ─────────────────────────────────────────────────────────────────────────────
_FALLBACK_SYMBOLS: List[str] = [
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
    "QNTUSDT", "HBARUSDT", "MNTUSDT", "ARKMUSDT", "KASUSDT",
    "PENDLEUSDT", "PYTHUSDT", "BOMEUSDT", "WIFUSDT", "PEPEUSDT",
    "ENAUSDT", "JUPUSDT", "STRKUSDT", "ALTUSDT", "ACEUSDT",
    "BLURUSDT", "UMAUSDT", "YGGUSDT", "SUSHIUSDT", "CAKEUSDT",
    "APEUSDT", "CHZUSDT", "MANAUSDT", "ENJUSDT", "ZILUSDT",
]

_FAPI_ENDPOINTS: List[str] = [
    "https://fapi.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi3.binance.com",
    "https://fapi4.binance.com",
    "https://fapi5.binance.com",
]
_SPOT_KLINES = "https://data.binance.com/api/v3/klines"


# ─────────────────────────────────────────────────────────────────────────────
# Lightweight Binance client (no auth required for market data)
# ─────────────────────────────────────────────────────────────────────────────

class _BinanceClient:
    """
    Minimal Binance FAPI client for AEGIS GEX.
    Only fetches public market data — no trading or auth required.
    Multi-endpoint failover identical to the main btcusdt_trader.py pattern.
    """

    MIN_VOLUME_USDT = 50_000_000   # 50M USDT / 24h minimum
    MAX_SYMBOLS     = 80

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
        self._geo_blocked: Dict[str, float] = {}
        self._geo_block_ttl = 3600.0
        self._ip_banned_until = 0.0
        self._klines_cache: Dict[tuple, Tuple[float, list]] = {}
        self._cache_ttl = 60.0
        self.logger = logging.getLogger(f"{__name__}.BinanceClient")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._connector = aiohttp.TCPConnector(
                limit=100, ttl_dns_cache=300, ssl=False,
            )
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
        if self._connector:
            await self._connector.close()

    def _endpoints(self) -> List[str]:
        now = time.time()
        av = [ep for ep in _FAPI_ENDPOINTS if now >= self._geo_blocked.get(ep, 0)]
        if not av:
            oldest = min(self._geo_blocked, key=self._geo_blocked.get)
            self._geo_blocked.pop(oldest)
            av = [oldest]
        return av

    async def _get(self, path: str, params: dict = None) -> Optional[object]:
        if time.time() < self._ip_banned_until:
            wait = self._ip_banned_until - time.time()
            self.logger.warning(f"IP ban active — sleeping {wait:.0f}s")
            await asyncio.sleep(min(wait, 30))
            return None

        params = params or {}
        for ep in self._endpoints():
            url = f"{ep}{path}"
            try:
                s = await self._get_session()
                async with s.get(url, params=params) as r:
                    if r.status == 200:
                        self._geo_blocked.pop(ep, None)
                        return await r.json()
                    if r.status == 451:
                        self._geo_blocked[ep] = time.time() + self._geo_block_ttl
                        break
                    if r.status == 418:
                        self._ip_banned_until = time.time() + 120
                        return None
                    if r.status == 429:
                        retry = int(r.headers.get("Retry-After", "5"))
                        await asyncio.sleep(min(retry, 60))
                        continue
                    if 400 <= r.status < 500:
                        return None
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.debug(f"_get({path}) [{ep}]: {e}")
        return None

    async def get_klines(self, symbol: str, interval: str, limit: int = 200) -> Optional[list]:
        cache_key = (symbol, interval, limit)
        cached = self._klines_cache.get(cache_key)
        if cached:
            ts, data = cached
            if time.time() - ts < self._cache_ttl:
                return data

        data = await self._get("/fapi/v1/klines",
                               {"symbol": symbol, "interval": interval, "limit": limit})
        if data:
            self._klines_cache[cache_key] = (time.time(), data)
            if len(self._klines_cache) > 500:
                oldest = min(self._klines_cache, key=lambda k: self._klines_cache[k][0])
                self._klines_cache.pop(oldest, None)
            return data

        try:
            s = await self._get_session()
            async with s.get(_SPOT_KLINES,
                             params={"symbol": symbol, "interval": interval, "limit": limit}) as r:
                if r.status == 200:
                    spot = await r.json()
                    self._klines_cache[cache_key] = (time.time(), spot)
                    return spot
        except Exception:
            pass
        return None

    async def get_funding_rate(self, symbol: str) -> Optional[Dict]:
        data = await self._get("/fapi/v1/premiumIndex", {"symbol": symbol})
        if data:
            return {
                "fundingRate": data.get("lastFundingRate", "0"),
                "markPrice":   data.get("markPrice", "0"),
            }
        return None

    async def get_open_interest(self, symbol: str) -> Optional[Dict]:
        return await self._get("/fapi/v1/openInterest", {"symbol": symbol})

    async def get_24hr_ticker_stats(self, symbol: str) -> Optional[Dict]:
        return await self._get("/fapi/v1/ticker/24hr", {"symbol": symbol})

    async def get_current_price(self, symbol: str) -> Optional[float]:
        d = await self._get("/fapi/v1/ticker/price", {"symbol": symbol})
        if d and "price" in d:
            return float(d["price"])
        return None

    async def _get_fapi(self, path: str, params: dict = None) -> Optional[object]:
        return await self._get(path, params)

    async def is_ip_banned(self) -> bool:
        return time.time() < self._ip_banned_until

    async def get_all_usdm_symbols(self) -> List[str]:
        tickers = await self._get("/fapi/v1/ticker/24hr")
        if not tickers or not isinstance(tickers, list):
            return list(_FALLBACK_SYMBOLS)

        perpetual_info = await self._get("/fapi/v1/exchangeInfo")
        perp_set = set()
        if perpetual_info and "symbols" in perpetual_info:
            for s in perpetual_info["symbols"]:
                if s.get("contractType") == "PERPETUAL" and s.get("status") == "TRADING":
                    perp_set.add(s["symbol"])

        qualifying = []
        for t in tickers:
            sym = t.get("symbol", "")
            if not sym.endswith("USDT") or "_" in sym:
                continue
            if perp_set and sym not in perp_set:
                continue
            try:
                vol = float(t.get("quoteVolume", 0))
                if vol >= self.MIN_VOLUME_USDT:
                    qualifying.append((vol, sym))
            except (ValueError, TypeError):
                pass

        qualifying.sort(reverse=True)
        symbols = [sym for _, sym in qualifying[:self.MAX_SYMBOLS]]
        if "BTCUSDT" in symbols:
            symbols.remove("BTCUSDT")
        symbols.insert(0, "BTCUSDT")
        return symbols or list(_FALLBACK_SYMBOLS)


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limit Configuration
# ─────────────────────────────────────────────────────────────────────────────

class _RateLimiter:
    """Thread-safe rate limiter for GEX signal broadcasting."""

    def __init__(self):
        self._symbol_last: Dict[str, float] = {}
        self._symbol_dir: Dict[str, Tuple[str, float]] = {}
        self._global_timestamps: deque = deque(maxlen=50)
        self._last_send = 0.0
        self._lock = asyncio.Lock()

        self.MIN_SYMBOL_GAP_SEC   = int(os.getenv("GEX_SYMBOL_GAP_SEC", "300"))    # 5 min per symbol
        self.GLOBAL_MIN_GAP_SEC   = int(os.getenv("GEX_GLOBAL_GAP_SEC", "60"))     # 60s between any signals
        self.MAX_PER_HOUR         = int(os.getenv("GEX_MAX_PER_HOUR", "12"))       # max 12/hr
        self.SAME_DIR_DEDUP_MIN   = int(os.getenv("GEX_DEDUP_MINUTES", "30"))      # 30min same-dir lock
        self.TG_MIN_SEND_GAP      = 2.0                                             # Telegram flood throttle

    def can_send(self, symbol: str, action: str) -> Tuple[bool, str]:
        now = datetime.now()

        # Per-symbol cooldown
        sym_gap = time.time() - self._symbol_last.get(symbol, 0)
        if sym_gap < self.MIN_SYMBOL_GAP_SEC:
            return False, f"symbol cooldown ({self.MIN_SYMBOL_GAP_SEC-sym_gap:.0f}s left)"

        # Same-direction dedup
        if symbol in self._symbol_dir:
            prev_dir, prev_ts = self._symbol_dir[symbol]
            if prev_dir == action and (time.time() - prev_ts) < self.SAME_DIR_DEDUP_MIN * 60:
                return False, f"same-dir dedup ({action})"

        # Hourly cap
        cutoff = now - timedelta(hours=1)
        recent = sum(1 for t in self._global_timestamps if t > cutoff)
        if recent >= self.MAX_PER_HOUR:
            return False, f"hourly cap ({self.MAX_PER_HOUR}/hr)"

        # Global gap
        if self._global_timestamps:
            gap = (now - self._global_timestamps[-1]).total_seconds()
            if gap < self.GLOBAL_MIN_GAP_SEC:
                return False, f"global gap ({self.GLOBAL_MIN_GAP_SEC-gap:.0f}s)"

        return True, "ok"

    def record_sent(self, symbol: str, action: str):
        now = datetime.now()
        ts  = time.time()
        self._symbol_last[symbol] = ts
        self._symbol_dir[symbol]  = (action, ts)
        self._global_timestamps.append(now)
        self._last_send = ts


# ─────────────────────────────────────────────────────────────────────────────
# Signal Formatter — Cornix-compatible
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(v: float, decimals: int = None) -> str:
    if decimals is not None:
        return f"{v:.{decimals}f}"
    if v >= 10000:
        return f"{v:.2f}"
    if v >= 1000:
        return f"{v:.3f}"
    if v >= 100:
        return f"{v:.4f}"
    if v >= 10:
        return f"{v:.5f}"
    return f"{v:.6f}"

def _pct(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return abs(a - b) / b * 100.0

def format_aegis_signal(sig: GEXSignal) -> str:
    """Format a GEXSignal into a Cornix-compatible Telegram message."""
    d_emoji = "🟢" if sig.action == "BUY" else "🔴"
    sym_tag = f"#{sig.symbol}"

    entry  = sig.entry_price
    tp1    = sig.tp1
    tp2    = sig.tp2
    tp3    = sig.tp3
    sl     = sig.sl
    lev    = sig.leverage

    tp1_pct = _pct(tp1, entry)
    tp2_pct = _pct(tp2, entry)
    tp3_pct = _pct(tp3, entry)
    sl_pct  = _pct(sl, entry)

    ts = datetime.utcnow().strftime("%H:%M")

    funding_str = f"{sig.funding_rate*100:+.4f}%"
    oi_str      = f"{sig.oi_delta_pct:+.1f}%"

    zone_arrow = "↑" if sig.action == "BUY" else "↓"
    flip_from  = sig.gex_zone_from[:3]
    flip_to    = sig.gex_zone_to[:3]

    gex_zone_str = f"GEX {flip_from}{zone_arrow}{flip_to}"

    msg = (
        f"{d_emoji} {sym_tag} {sig.direction}\n"
        f"Exchange: Binance Futures\n"
        f"Leverage: Cross {lev}x\n\n"
        f"Entry Targets:\n1) {_fmt(entry)}\n\n"
        f"Take-Profit Targets:\n"
        f"1) {_fmt(tp1)}\n"
        f"2) {_fmt(tp2)}\n"
        f"3) {_fmt(tp3)}\n\n"
        f"Stop Targets:\n1) {_fmt(sl)}\n\n"
        f"⚡GEX Flip · {gex_zone_str} · {sig.confidence:.0f}%Conf\n"
        f"TP +{tp1_pct:.1f}%/+{tp2_pct:.1f}%/+{tp3_pct:.1f}% · SL -{sl_pct:.1f}%\n"
        f"R:R 1:{sig.rr_ratio:.1f} · ATR {_fmt(sig.atr)} · {sig.timeframe}\n"
        f"Fund: {funding_str} · OI∆: {oi_str} · {ts} UTC\n"
        f"📡 @ichimokutradingsignal | AEGIS GEX v1.0"
    )
    return msg


# ─────────────────────────────────────────────────────────────────────────────
# Main AEGIS GEX Bot
# ─────────────────────────────────────────────────────────────────────────────

class AEGISGEXBot:
    """
    AEGIS GEX v1.0 — Production Telegram Signal Bot

    Architecture:
      ┌─────────────────────────────────────────────────────┐
      │  Symbol Universe (up to 80 USDM perps)              │
      │  ↓ parallel asyncio.gather with semaphore           │
      │  GEX Engine (per symbol, multi-timeframe: 1h + 4h)  │
      │  ↓ snapshot comparison (prev vs curr)               │
      │  GEX Flip Detection                                 │
      │  ↓ rate limiter gate                                │
      │  Telegram Broadcaster (Cornix-compatible format)    │
      └─────────────────────────────────────────────────────┘

    Scan cycle: every SCAN_INTERVAL_SECONDS (default 60s)
    Parallel limit: SCAN_PARALLEL_LIMIT concurrent Binance fetches (default 20)
    """

    SCAN_INTERVAL_SEC     = int(os.getenv("GEX_SCAN_INTERVAL_SEC", "60"))
    SCAN_PARALLEL_LIMIT   = int(os.getenv("GEX_PARALLEL_LIMIT", "20"))
    SYMBOL_REFRESH_SEC    = int(os.getenv("GEX_SYMBOL_REFRESH_SEC", "3600"))
    MIN_CONFIDENCE        = float(os.getenv("GEX_MIN_CONFIDENCE", "60.0"))
    PRIMARY_TF            = os.getenv("GEX_PRIMARY_TF", "1h")      # Primary signal timeframe
    CONFIRM_TF            = os.getenv("GEX_CONFIRM_TF",  "4h")     # Confirmation timeframe
    TG_SEND_MIN_GAP       = 2.0

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set in environment")

        _ch = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
        _ct = (os.getenv("TELEGRAM_CHAT_ID", "") or "").strip()
        if _ch:
            self.channel_id = _ch
        elif _ct.startswith("-"):
            self.channel_id = _ct
        else:
            self.channel_id = "-1002453842816"

        self.admin_chat_id = os.getenv("ADMIN_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
        self.base_url      = f"https://api.telegram.org/bot{self.bot_token}"

        self._tg_session: Optional[aiohttp.ClientSession] = None
        self._tg_lock     = asyncio.Lock()
        self._tg_last     = 0.0

        self.client  = _BinanceClient()
        self.engine  = AEGISGEXEngine()
        self.limiter = _RateLimiter()

        self._scan_sem      = asyncio.Semaphore(self.SCAN_PARALLEL_LIMIT)
        self._prev_snaps: Dict[str, GEXSnapshot]  = {}
        self._active_syms: List[str]              = []
        self._syms_refresh_ts: float              = 0.0
        self._start_time     = datetime.now()
        self._signal_count   = 0
        self._scan_count     = 0

        self.logger.info(
            f"🛡️  AEGIS GEX v1.0 initialized | "
            f"Channel: {self.channel_id} | "
            f"Primary TF: {self.PRIMARY_TF} | "
            f"Confirm TF: {self.CONFIRM_TF} | "
            f"Min Confidence: {self.MIN_CONFIDENCE:.0f}%"
        )

    # ── Telegram ──────────────────────────────────────────────────────────────

    async def _get_tg_session(self) -> aiohttp.ClientSession:
        if self._tg_session is None or self._tg_session.closed:
            self._tg_session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False),
                timeout=aiohttp.ClientTimeout(total=12),
            )
        return self._tg_session

    async def send_message(self, chat_id: str, text: str, retries: int = 3) -> bool:
        """Send Telegram message with throttle, retry, and plain-text fallback."""
        if not chat_id:
            return False
        chat_id = str(chat_id)

        async with self._tg_lock:
            gap = time.time() - self._tg_last
            if gap < self.TG_SEND_MIN_GAP:
                await asyncio.sleep(self.TG_SEND_MIN_GAP - gap)
            self._tg_last = time.time()

        url  = f"{self.base_url}/sendMessage"
        data = {"chat_id": chat_id, "text": text,
                "link_preview_options": {"is_disabled": True}}

        for attempt in range(retries):
            try:
                session = await self._get_tg_session()
                async with session.post(url, json=data) as r:
                    if r.status == 200:
                        result = await r.json()
                        if result.get("ok"):
                            return True
                        desc = result.get("description", "")
                        if "chat not found" in desc.lower():
                            return False
                        if "can't parse" in desc.lower():
                            plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', text)
                            pdata = {"chat_id": chat_id, "text": plain,
                                     "link_preview_options": {"is_disabled": True}}
                            async with session.post(url, json=pdata) as r2:
                                r2j = await r2.json()
                                return r2j.get("ok", False)
                    elif r.status == 400:
                        body = await r.json()
                        self.logger.warning(f"TG 400: {body.get('description','bad request')}")
                        return False
                    elif r.status == 429:
                        retry_after = int(r.headers.get("Retry-After", "5"))
                        await asyncio.sleep(min(retry_after, 60))
                        continue
                    await asyncio.sleep(2 ** attempt)
            except asyncio.TimeoutError:
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                self.logger.error(f"send_message error (attempt {attempt+1}): {e}")
                await asyncio.sleep(2 ** attempt)
        return False

    # ── Symbol Management ─────────────────────────────────────────────────────

    async def _refresh_symbols(self):
        now = time.time()
        if now - self._syms_refresh_ts < self.SYMBOL_REFRESH_SEC and self._active_syms:
            return
        try:
            syms = await self.client.get_all_usdm_symbols()
            if syms:
                self._active_syms    = syms
                self._syms_refresh_ts = now
                self.logger.info(f"🌐 Symbol universe refreshed: {len(syms)} symbols")
        except Exception as e:
            self.logger.warning(f"Symbol refresh failed: {e}")
            if not self._active_syms:
                self._active_syms = list(_FALLBACK_SYMBOLS)

    # ── Core GEX Scan (single symbol) ────────────────────────────────────────

    async def _scan_symbol(self, symbol: str) -> bool:
        """
        Run GEX flip detection for one symbol.
        1. Fetch GEX snapshot for primary timeframe (1h)
        2. Fetch GEX snapshot for confirmation timeframe (4h)
        3. Compare with previous snapshot → detect flip crossover
        4. If confirmed flip → rate-check → format → broadcast

        Returns True if a signal was sent.
        """
        try:
            primary_snap, confirm_snap = await asyncio.gather(
                self.engine.compute_gex_snapshot(self.client, symbol, self.PRIMARY_TF),
                self.engine.compute_gex_snapshot(self.client, symbol, self.CONFIRM_TF),
                return_exceptions=True,
            )

            if isinstance(primary_snap, Exception) or primary_snap is None:
                return False

            if isinstance(confirm_snap, Exception):
                confirm_snap = None

            prev_snap = self._prev_snaps.get(symbol)
            self._prev_snaps[symbol] = primary_snap

            if prev_snap is None:
                return False

            sig = self.engine.detect_gex_flip_signal(
                prev_snap, primary_snap,
                min_confidence=self.MIN_CONFIDENCE,
            )

            if sig is None:
                return False

            if confirm_snap and not isinstance(confirm_snap, Exception):
                if confirm_snap.bias != "NEUTRAL":
                    if confirm_snap.bias == "BULLISH" and sig.action == "SELL":
                        self.logger.debug(
                            f"[{symbol}] 4h GEX bias BULLISH contradicts SHORT → skip"
                        )
                        return False
                    if confirm_snap.bias == "BEARISH" and sig.action == "BUY":
                        self.logger.debug(
                            f"[{symbol}] 4h GEX bias BEARISH contradicts LONG → skip"
                        )
                        return False
                if sig.action == "BUY" and confirm_snap.current_gex_zone == "NEGATIVE":
                    sig.confidence = max(sig.confidence - 10.0, self.MIN_CONFIDENCE)
                if sig.action == "SELL" and confirm_snap.current_gex_zone == "POSITIVE":
                    sig.confidence = max(sig.confidence - 10.0, self.MIN_CONFIDENCE)

            if sig.confidence < self.MIN_CONFIDENCE:
                return False

            can, reason = self.limiter.can_send(symbol, sig.action)
            if not can:
                self.logger.debug(f"[{symbol}] Rate-limited: {reason}")
                return False

            formatted = format_aegis_signal(sig)
            ok = await self.send_message(self.channel_id, formatted)

            if ok:
                self.limiter.record_sent(symbol, sig.action)
                self._signal_count += 1
                self.logger.info(
                    f"📡 [{symbol}] GEX FLIP {sig.direction} @ {sig.entry_price:.6g} | "
                    f"TP1: {sig.tp1:.6g} | SL: {sig.sl:.6g} | "
                    f"Conf: {sig.confidence:.0f}% | R:R 1:{sig.rr_ratio:.1f}"
                )
                if self.admin_chat_id and str(self.admin_chat_id) != str(self.channel_id):
                    d_e = "🟢" if sig.action == "BUY" else "🔴"
                    await self.send_message(
                        self.admin_chat_id,
                        f"{d_e} AEGIS GEX FLIP — {symbol} {sig.direction}\n"
                        f"Entry: {sig.entry_price:.6g} | TP1: {sig.tp1:.6g} | "
                        f"SL: {sig.sl:.6g} | Conf: {sig.confidence:.0f}%",
                    )
                return True

        except Exception as e:
            self.logger.error(f"[{symbol}] scan error: {e}")
        return False

    # ── Parallel Scan Cycle ───────────────────────────────────────────────────

    async def scan_all(self) -> int:
        """
        Scan ALL active symbols in parallel using asyncio.gather + Semaphore.
        Returns number of signals sent.
        """
        symbols = self._active_syms
        if not symbols:
            return 0

        async def _gate(sym: str) -> bool:
            if await self.client.is_ip_banned():
                return False
            async with self._scan_sem:
                if await self.client.is_ip_banned():
                    return False
                try:
                    return await asyncio.wait_for(
                        self._scan_symbol(sym), timeout=45.0,
                    )
                except asyncio.TimeoutError:
                    self.logger.debug(f"[{sym}] scan timed out (45s)")
                    return False
                except Exception as exc:
                    self.logger.debug(f"[{sym}] scan exception: {exc}")
                    return False

        results = await asyncio.gather(
            *[_gate(sym) for sym in symbols],
            return_exceptions=True,
        )
        sent   = sum(1 for r in results if r is True)
        errors = sum(1 for r in results if isinstance(r, Exception))
        self.logger.info(
            f"⚡ Scan cycle #{self._scan_count}: {len(symbols)} symbols | "
            f"{sent} GEX signals sent | {errors} errors"
        )
        return sent

    # ── Startup ───────────────────────────────────────────────────────────────

    async def _send_startup_message(self):
        """Broadcast startup notification to channel."""
        msg = (
            f"🛡️ AEGIS GEX v1.0 — Online\n\n"
            f"Strategy: GEX Dealer Flow Engine\n"
            f"Mode: GEX Flip Entry & Dynamic TP\n"
            f"Universe: Up to {_BinanceClient.MAX_SYMBOLS} USDM Perpetuals\n"
            f"Primary TF: {self.PRIMARY_TF} | Confirm TF: {self.CONFIRM_TF}\n"
            f"Min Confidence: {self.MIN_CONFIDENCE:.0f}%\n"
            f"Started: {self._start_time.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"Entry = GEX Flip Level | TP = Next GEX Flip | SL = ATR Buffer\n"
            f"📡 @ichimokutradingsignal | AEGIS GEX v1.0"
        )
        await self.send_message(self.channel_id, msg)
        if self.admin_chat_id and str(self.admin_chat_id) != str(self.channel_id):
            await self.send_message(self.admin_chat_id, msg)

    # ── Heartbeat ─────────────────────────────────────────────────────────────

    async def _send_heartbeat(self):
        """Send periodic status update to admin chat."""
        if not self.admin_chat_id:
            return
        uptime = datetime.now() - self._start_time
        hrs    = int(uptime.total_seconds() // 3600)
        mins   = int((uptime.total_seconds() % 3600) // 60)
        msg = (
            f"💓 AEGIS GEX v1.0 Heartbeat\n"
            f"Uptime: {hrs}h {mins}m\n"
            f"Symbols scanned: {len(self._active_syms)}\n"
            f"Scan cycles: {self._scan_count}\n"
            f"GEX signals sent: {self._signal_count}\n"
            f"Rate limit: {self.limiter.MAX_PER_HOUR}/hr | "
            f"Gap: {self.limiter.GLOBAL_MIN_GAP_SEC}s"
        )
        await self.send_message(self.admin_chat_id, msg)

    # ── Main Loop ─────────────────────────────────────────────────────────────

    async def run(self):
        """
        Main production event loop.
        Runs forever with SCAN_INTERVAL_SEC between cycles.
        Handles graceful shutdown on KeyboardInterrupt.
        """
        self.logger.info("🚀 AEGIS GEX v1.0 starting...")

        await self._send_startup_message()
        await self._refresh_symbols()

        heartbeat_interval = 3600  # 1 hour
        last_heartbeat     = time.time()

        while True:
            loop_start = time.time()
            try:
                await self._refresh_symbols()
                self._scan_count += 1
                await self.scan_all()

                if time.time() - last_heartbeat >= heartbeat_interval:
                    await self._send_heartbeat()
                    last_heartbeat = time.time()

            except asyncio.CancelledError:
                self.logger.info("🛑 AEGIS GEX shutdown signal received")
                break
            except Exception as e:
                self.logger.error(f"Main loop error: {e}", exc_info=True)
                await asyncio.sleep(10)

            elapsed = time.time() - loop_start
            sleep   = max(0, self.SCAN_INTERVAL_SEC - elapsed)
            if sleep > 0:
                self.logger.debug(f"Sleeping {sleep:.1f}s until next cycle")
                await asyncio.sleep(sleep)

        await self.client.close()
        if self._tg_session and not self._tg_session.closed:
            await self._tg_session.close()
        self.logger.info("✅ AEGIS GEX v1.0 shut down cleanly")
