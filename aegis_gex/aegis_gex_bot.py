#!/usr/bin/env python3
"""
AEGIS GEX v1.0 — Production Telegram Signal Bot  (Complete Rebuild)
=====================================================================
Standalone — zero shared state with any other strategy.

Signal Logic (strict, from AEGIS GEX DEALER FLOW ENGINE):
  Entry  : Price CROSSES a GEX flip level in real-time (uses mark price, not candle close)
  TP     : The NEXT GEX flip level in the direction of trade
           Dynamically updated each cycle as new flip levels appear
  SL     : ATR-based buffer beyond the entry flip level (invalidation zone)

All 13 AEGIS indicator layers are integrated into:
  - Signal generation (GEX_FLIP / VANNA_ENTRY / COMPRESSION_BREAK)
  - Confidence scoring (all 13 layers weighted)
  - Signal message (Dashboard Table embedded in Telegram format)

Architecture:
  Symbol Universe (≤80 USDM perps)
    ↓ asyncio.gather + Semaphore(20) — true parallel scan
  GEX Engine (1h primary + 4h confirmation, mark price)
    ↓ snapshot delta → flip crossover detection
  13-layer confidence gate (≥60%)
    ↓ rate limiter (12/hr, 60s global, 5min/symbol, 30min dedup)
  Telegram Broadcaster (Cornix-compatible + GEX Dashboard)
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
    GEXZone,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Fallback symbol universe
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_SYMBOLS: List[str] = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "SUIUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "INJUSDT",
    "NEARUSDT", "MATICUSDT", "LTCUSDT", "SEIUSDT", "TIAUSDT",
    "ATOMUSDT", "AAVEUSDT", "UNIUSDT", "LDOUSDT", "WLDUSDT",
    "ORDIUSDT", "RUNEUSDT", "STXUSDT", "MKRUSDT", "FETUSDT",
    "GMXUSDT", "DYDXUSDT", "GALAUSDT", "SANDUSDT", "AXSUSDT",
    "ICPUSDT", "FILUSDT", "TRXUSDT", "ETCUSDT", "BCHUSDT",
    "XLMUSDT", "VETUSDT", "ALGOUSDT", "GRTUSDT", "SNXUSDT",
    "CRVUSDT", "HBARUSDT", "MNTUSDT", "ARKMUSDT", "KASUSDT",
    "PENDLEUSDT", "PYTHUSDT", "PEPEUSDT", "WIFUSDT", "BOMEUSDT",
    "ENAUSDT", "JUPUSDT", "APEUSDT", "CHZUSDT", "MANAUSDT",
    "QNTUSDT", "IMXUSDT", "AGIXUSDT", "RNDRUSDT", "FLOWUSDT",
    "TIAUSDT", "FTMUSDT", "EGLDUSDT", "COMPUSDT", "XMRUSDT",
    "SUSHIUSDT", "CAKEUSDT", "ENJUSDT", "ZILUSDT", "THETAUSDT",
    "BANDUSDT", "STORJUSDT", "KNCUSDT", "CTKUSDT", "BLURUSDT",
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
# Binance Client — public market data, multi-endpoint failover
# ─────────────────────────────────────────────────────────────────────────────

class _BinanceClient:
    """
    Minimal async Binance FAPI client.
    Public market data only — no auth, no trading.
    Multi-endpoint geo-block failover identical to main btcusdt_trader.py.
    """
    MIN_VOLUME_USDT = 50_000_000
    MAX_SYMBOLS     = 80

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
        self._geo_blocked: Dict[str, float] = {}
        self._geo_ttl     = 3600.0
        self._ip_ban_until= 0.0
        self._cache: Dict[tuple, Tuple[float, object]] = {}
        self._cache_ttl   = 55.0    # slightly under scan interval
        self.logger = logging.getLogger(f"{__name__}.BinanceClient")

    async def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._connector = aiohttp.TCPConnector(
                limit=120, limit_per_host=40,
                ttl_dns_cache=300, ssl=False,
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

    def _live_endpoints(self) -> List[str]:
        now = time.time()
        av  = [ep for ep in _FAPI_ENDPOINTS if now >= self._geo_blocked.get(ep, 0)]
        if not av:
            oldest = min(self._geo_blocked, key=self._geo_blocked.get)
            del self._geo_blocked[oldest]
            av = [oldest]
        return av

    async def _get(self, path: str, params: dict = None,
                   cache_key: tuple = None) -> Optional[object]:
        # Check IP ban
        now = time.time()
        if now < self._ip_ban_until:
            w = self._ip_ban_until - now
            await asyncio.sleep(min(w, 30))
            return None

        # Check cache
        if cache_key:
            hit = self._cache.get(cache_key)
            if hit:
                ts, data = hit
                if now - ts < self._cache_ttl:
                    return data

        params = params or {}
        for ep in self._live_endpoints():
            url = f"{ep}{path}"
            try:
                s = await self._session_get()
                async with s.get(url, params=params) as r:
                    if r.status == 200:
                        self._geo_blocked.pop(ep, None)
                        data = await r.json()
                        if cache_key:
                            self._cache[cache_key] = (time.time(), data)
                            # LRU eviction
                            if len(self._cache) > 1000:
                                oldest_k = min(self._cache, key=lambda k: self._cache[k][0])
                                del self._cache[oldest_k]
                        return data
                    if r.status == 451:
                        self._geo_blocked[ep] = time.time() + self._geo_ttl
                        self.logger.debug(f"Geo-blocked: {ep}")
                        break   # Try next endpoint
                    if r.status == 418:
                        self._ip_ban_until = time.time() + 120
                        return None
                    if r.status == 429:
                        retry = int(r.headers.get("Retry-After", "5"))
                        await asyncio.sleep(min(retry, 60))
                        continue
                    if 400 <= r.status < 500:
                        return None
            except asyncio.TimeoutError:
                self.logger.debug(f"Timeout: {ep}{path}")
                continue
            except Exception as e:
                self.logger.debug(f"_get({path}) [{ep}]: {e}")
                continue
        return None

    async def get_klines(self, symbol: str, interval: str,
                         limit: int = 200) -> Optional[list]:
        ck = ("klines", symbol, interval, limit)
        data = await self._get(
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
            cache_key=ck,
        )
        if data:
            return data
        # Spot klines fallback
        try:
            s = await self._session_get()
            async with s.get(_SPOT_KLINES,
                             params={"symbol": symbol, "interval": interval, "limit": limit}) as r:
                if r.status == 200:
                    spot = await r.json()
                    self._cache[ck] = (time.time(), spot)
                    return spot
        except Exception:
            pass
        return None

    async def get_funding_rate(self, symbol: str) -> Optional[dict]:
        data = await self._get(
            "/fapi/v1/premiumIndex", {"symbol": symbol},
            cache_key=("funding", symbol),
        )
        if data:
            return {
                "fundingRate": data.get("lastFundingRate", "0"),
                "markPrice":   data.get("markPrice", "0"),
                "indexPrice":  data.get("indexPrice", "0"),
                "nextFundingTime": data.get("nextFundingTime", 0),
            }
        return None

    async def get_premium_index(self, symbol: str) -> Optional[dict]:
        """Real-time mark price + funding via premiumIndex (separate from cached funding)."""
        data = await self._get("/fapi/v1/premiumIndex", {"symbol": symbol})
        return data   # no cache — we want real-time mark price

    async def get_open_interest(self, symbol: str) -> Optional[dict]:
        return await self._get(
            "/fapi/v1/openInterest", {"symbol": symbol},
            cache_key=("oi", symbol),
        )

    async def get_24hr_ticker_stats(self, symbol: str) -> Optional[dict]:
        return await self._get(
            "/fapi/v1/ticker/24hr", {"symbol": symbol},
            cache_key=("ticker24h", symbol),
        )

    async def _get_fapi(self, path: str, params: dict = None) -> Optional[object]:
        """Alias for GEX engine OI history calls."""
        return await self._get(path, params)

    def is_ip_banned(self) -> bool:
        return time.time() < self._ip_ban_until

    async def get_all_usdm_symbols(self) -> List[str]:
        tickers, info = await asyncio.gather(
            self._get("/fapi/v1/ticker/24hr"),
            self._get("/fapi/v1/exchangeInfo"),
            return_exceptions=True,
        )

        if isinstance(tickers, Exception) or not tickers or not isinstance(tickers, list):
            self.logger.warning("Symbol fetch failed — using fallback list")
            return list(_FALLBACK_SYMBOLS)

        perp_set: set = set()
        if not isinstance(info, Exception) and info and "symbols" in info:
            for s in info["symbols"]:
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
                v = float(t.get("quoteVolume", 0))
                if v >= self.MIN_VOLUME_USDT:
                    qualifying.append((v, sym))
            except (ValueError, TypeError):
                pass

        qualifying.sort(reverse=True)
        syms = [s for _, s in qualifying[:self.MAX_SYMBOLS]]
        if "BTCUSDT" in syms:
            syms.remove("BTCUSDT")
        syms.insert(0, "BTCUSDT")
        return syms or list(_FALLBACK_SYMBOLS)


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limiter
# ─────────────────────────────────────────────────────────────────────────────

class _RateLimiter:
    def __init__(self):
        self._sym_last:   Dict[str, float]         = {}
        self._sym_dir:    Dict[str, Tuple[str, float]] = {}
        self._global_ts:  deque                    = deque(maxlen=100)
        self._lock = asyncio.Lock()

        self.SYM_GAP_SEC   = int(os.getenv("GEX_SYMBOL_GAP_SEC", "300"))
        self.GLOBAL_GAP_SEC= int(os.getenv("GEX_GLOBAL_GAP_SEC", "60"))
        self.MAX_PER_HOUR  = int(os.getenv("GEX_MAX_PER_HOUR", "12"))
        self.DEDUP_MIN     = int(os.getenv("GEX_DEDUP_MINUTES", "30"))

    def can_send(self, symbol: str, action: str) -> Tuple[bool, str]:
        now_ts = time.time()
        now_dt = datetime.now()

        # Per-symbol gap
        gap = now_ts - self._sym_last.get(symbol, 0)
        if gap < self.SYM_GAP_SEC:
            return False, f"sym-gap {self.SYM_GAP_SEC-gap:.0f}s"

        # Same-direction dedup
        if symbol in self._sym_dir:
            d, ts = self._sym_dir[symbol]
            if d == action and now_ts - ts < self.DEDUP_MIN * 60:
                return False, f"dedup/{action}"

        # Hourly cap
        cutoff = now_dt - timedelta(hours=1)
        recent = sum(1 for t in self._global_ts if t > cutoff)
        if recent >= self.MAX_PER_HOUR:
            return False, f"cap {self.MAX_PER_HOUR}/hr"

        # Global gap
        if self._global_ts:
            g = (now_dt - self._global_ts[-1]).total_seconds()
            if g < self.GLOBAL_GAP_SEC:
                return False, f"global-gap {self.GLOBAL_GAP_SEC-g:.0f}s"

        return True, "ok"

    def record(self, symbol: str, action: str):
        ts = time.time()
        self._sym_last[symbol] = ts
        self._sym_dir[symbol]  = (action, ts)
        self._global_ts.append(datetime.now())


# ─────────────────────────────────────────────────────────────────────────────
# Signal Formatter — Cornix-compatible + GEX Dashboard
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(v: float) -> str:
    """Auto-precision formatter."""
    if v >= 10000:  return f"{v:.2f}"
    if v >= 1000:   return f"{v:.3f}"
    if v >= 100:    return f"{v:.4f}"
    if v >= 10:     return f"{v:.5f}"
    return f"{v:.6f}"

def _pct(a: float, b: float) -> float:
    return abs(a - b) / b * 100.0 if b else 0.0

def _sig_type_label(st: str) -> str:
    return {
        "GEX_FLIP":          "GEX Flip",
        "VANNA_ENTRY":       "Vanna Entry",
        "COMPRESSION_BREAK": "Compression Break",
    }.get(st, st)

def format_aegis_signal(sig: GEXSignal) -> str:
    """
    Full Cornix-compatible signal message with embedded AEGIS GEX Dashboard.

    Layout:
      [Direction header — Cornix parses this]
      [Entry / TP targets / Stop — Cornix format]
      [GEX Dashboard Table — all 13 indicator layers summarized]
    """
    d_emoji  = "🟢" if sig.action == "BUY" else "🔴"
    sym_tag  = f"#{sig.symbol}"

    e   = sig.entry_price
    tp1 = sig.tp1
    tp2 = sig.tp2
    tp3 = sig.tp3
    sl  = sig.sl
    lev = sig.leverage

    tp1p = _pct(tp1, e)
    tp2p = _pct(tp2, e)
    tp3p = _pct(tp3, e)
    slp  = _pct(sl, e)

    ts   = datetime.utcnow().strftime("%H:%M")
    date = datetime.utcnow().strftime("%b %d")

    zone_arrow = "↑" if sig.action == "BUY" else "↓"
    gex_zone   = f"GEX {sig.gex_zone_from[:3]}{zone_arrow}{sig.gex_zone_to[:3]}"
    st_label   = _sig_type_label(sig.signal_type)
    bias_emoji = "🐂" if sig.bias == "BULLISH" else ("🐻" if sig.bias == "BEARISH" else "⚖️")

    # ── GEX Dashboard (13 layers) ─────────────────────────────────────────────
    snap = sig.snapshot
    fund_str  = f"{sig.funding_rate*100:+.4f}%"
    oi_str    = f"{sig.oi_delta_pct:+.1f}%"
    charm_str = f"{sig.charm_decay:.2f}"

    ema_pos = ""
    if sig.ema50:
        ema_pos = f"{'>' if e > sig.ema50 else '<'} EMA50({_fmt(sig.ema50)})"

    vwap_pos = f"{'above' if e > sig.vwap else 'below'} VWAP({_fmt(sig.vwap)})"
    vwap_b1  = f"±1ATR [{_fmt(snap.vwap_minus1_atr)}–{_fmt(snap.vwap_plus1_atr)}]"
    vwap_b2  = f"±2ATR [{_fmt(snap.vwap_minus2_atr)}–{_fmt(snap.vwap_plus2_atr)}]"

    exp_up   = _fmt(sig.expected_move_upper)
    exp_dn   = _fmt(sig.expected_move_lower)

    flip_up_str  = _fmt(snap.nearest_flip_up)   if snap.nearest_flip_up   else "—"
    flip_dn_str  = _fmt(snap.nearest_flip_down) if snap.nearest_flip_down else "—"
    gfp_str      = _fmt(sig.gamma_flip_proxy)

    opex_str  = "⚠️OPEX WEEK" if snap.is_opex_week else ""
    sess_str  = f"Session+{snap.session_open_minute}min"

    walls_str = ""
    if snap.gamma_walls:
        top3 = sorted(snap.gamma_walls, key=lambda w: w.strength, reverse=True)[:3]
        walls_str = " | ".join(f"{'BULL' if 'BULL' in w.zone_type else 'BEAR'}@{_fmt(w.mid)}" for w in top3)

    comp_str = ""
    if snap.compression_zones:
        cz = snap.compression_zones[0]
        comp_str = f"COIL [{_fmt(cz.price_low)}–{_fmt(cz.price_high)}] → {_fmt(cz.target) if cz.target else '?'}"

    vanna_str = ""
    if sig.vanna_entry:
        vanna_str = f"Vanna Line @ {_fmt(sig.vanna_entry)}"

    flip_levels_all = sorted(
        set([_fmt(fl.price) for fl in snap.all_flip_levels[:6]])
    )

    msg = (
        f"{d_emoji} {sym_tag} {sig.direction}\n"
        f"Exchange: Binance Futures\n"
        f"Leverage: Cross {lev}x\n\n"
        f"Entry Targets:\n1) {_fmt(e)}\n\n"
        f"Take-Profit Targets:\n"
        f"1) {_fmt(tp1)}\n"
        f"2) {_fmt(tp2)}\n"
        f"3) {_fmt(tp3)}\n\n"
        f"Stop Targets:\n1) {_fmt(sl)}\n\n"
        f"── AEGIS GEX Dashboard ─────────────\n"
        f"Signal: {st_label} | {gex_zone} | {bias_emoji}{sig.bias}\n"
        f"Conf: {sig.confidence:.0f}% | R:R 1:{sig.rr_ratio:.1f} | Lev: {lev}x\n"
        f"TP: +{tp1p:.1f}%/+{tp2p:.1f}%/+{tp3p:.1f}% | SL: -{slp:.1f}%\n\n"
        f"GEX Flip Proxy: {gfp_str}\n"
        f"GEX Flip ↑: {flip_up_str} | ↓: {flip_dn_str}\n"
        f"All Flips: {', '.join(flip_levels_all)}\n"
    )

    if walls_str:
        msg += f"Gamma Walls: {walls_str}\n"
    if comp_str:
        msg += f"Compression: {comp_str}\n"
    if vanna_str:
        msg += f"{vanna_str}\n"

    msg += (
        f"\n"
        f"VWAP: {vwap_pos}\n"
        f"{vwap_b1} | {vwap_b2}\n"
        f"Exp Move: [{exp_dn} – {exp_up}]\n"
    )

    if ema_pos:
        msg += f"EMA50: {ema_pos}\n"

    msg += (
        f"\n"
        f"Funding: {fund_str} | OI∆: {oi_str}\n"
        f"Charm Decay: {charm_str} | ATR: {_fmt(sig.atr)}\n"
        f"{sess_str} | {sig.timeframe} TF | {date} {ts} UTC\n"
    )
    if opex_str:
        msg += f"{opex_str}\n"

    msg += f"📡 @ichimokutradingsignal | AEGIS GEX v1.0"
    return msg


# ─────────────────────────────────────────────────────────────────────────────
# Main Bot
# ─────────────────────────────────────────────────────────────────────────────

class AEGISGEXBot:
    """
    AEGIS GEX v1.0 — Production Signal Bot

    Scan every 60s (configurable).
    All 80 symbols in parallel via asyncio.gather + Semaphore.
    Uses real-time mark price for GEX flip crossover detection.
    """

    SCAN_INTERVAL   = int(os.getenv("GEX_SCAN_INTERVAL_SEC", "60"))
    PARALLEL_LIMIT  = int(os.getenv("GEX_PARALLEL_LIMIT",    "20"))
    SYM_REFRESH_SEC = int(os.getenv("GEX_SYMBOL_REFRESH_SEC","3600"))
    MIN_CONF        = float(os.getenv("GEX_MIN_CONFIDENCE",  "60.0"))
    PRIMARY_TF      = os.getenv("GEX_PRIMARY_TF",  "1h")
    CONFIRM_TF      = os.getenv("GEX_CONFIRM_TF",  "4h")
    TG_SEND_GAP     = 2.0

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN missing")

        _ch = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
        _ct = (os.getenv("TELEGRAM_CHAT_ID", "") or "").strip()
        self.channel_id   = _ch if _ch else (_ct if _ct.startswith("-") else "-1002453842816")
        self.admin_chat   = os.getenv("ADMIN_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
        self.base_url     = f"https://api.telegram.org/bot{self.bot_token}"

        self._tg_sess: Optional[aiohttp.ClientSession] = None
        self._tg_lock = asyncio.Lock()
        self._tg_last = 0.0

        self.client  = _BinanceClient()
        self.engine  = AEGISGEXEngine()
        self.limiter = _RateLimiter()

        self._sem          = asyncio.Semaphore(self.PARALLEL_LIMIT)
        self._prev: Dict[str, GEXSnapshot] = {}
        self._syms:        List[str]  = []
        self._syms_ts:     float      = 0.0
        self._start        = datetime.now()
        self._signals_sent = 0
        self._cycles       = 0

        self.logger.info(
            f"🛡️ AEGIS GEX v1.0 ready | CH:{self.channel_id} | "
            f"TF:{self.PRIMARY_TF}+{self.CONFIRM_TF} | MinConf:{self.MIN_CONF:.0f}%"
        )

    # ── Telegram ──────────────────────────────────────────────────────────────

    async def _tg_session(self) -> aiohttp.ClientSession:
        if self._tg_sess is None or self._tg_sess.closed:
            self._tg_sess = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False),
                timeout=aiohttp.ClientTimeout(total=12),
            )
        return self._tg_sess

    async def send_message(self, chat_id: str, text: str, retries: int = 3) -> bool:
        if not chat_id:
            return False
        chat_id = str(chat_id)

        async with self._tg_lock:
            gap = time.time() - self._tg_last
            if gap < self.TG_SEND_GAP:
                await asyncio.sleep(self.TG_SEND_GAP - gap)
            self._tg_last = time.time()

        url  = f"{self.base_url}/sendMessage"
        body = {"chat_id": chat_id, "text": text,
                "link_preview_options": {"is_disabled": True}}

        for attempt in range(retries):
            try:
                s = await self._tg_session()
                async with s.post(url, json=body) as r:
                    if r.status == 200:
                        res = await r.json()
                        if res.get("ok"):
                            return True
                        desc = res.get("description", "")
                        if "chat not found" in desc.lower():
                            return False
                        if "can't parse" in desc.lower():
                            plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', text)
                            pb = {"chat_id": chat_id, "text": plain,
                                  "link_preview_options": {"is_disabled": True}}
                            async with s.post(url, json=pb) as r2:
                                r2j = await r2.json()
                                return r2j.get("ok", False)
                    elif r.status == 400:
                        try:
                            bd = await r.json()
                            self.logger.warning(f"TG 400: {bd.get('description','?')}")
                        except Exception:
                            pass
                        return False
                    elif r.status == 429:
                        ra = int(r.headers.get("Retry-After", "5"))
                        await asyncio.sleep(min(ra, 60))
                        continue
                    await asyncio.sleep(2 ** attempt)
            except asyncio.TimeoutError:
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                self.logger.error(f"send_message (attempt {attempt+1}): {e}")
                await asyncio.sleep(2 ** attempt)
        return False

    # ── Symbol management ─────────────────────────────────────────────────────

    async def _refresh_syms(self):
        now = time.time()
        if now - self._syms_ts < self.SYM_REFRESH_SEC and self._syms:
            return
        try:
            syms = await self.client.get_all_usdm_symbols()
            if syms:
                self._syms    = syms
                self._syms_ts = now
                self.logger.info(f"🌐 {len(syms)} symbols active")
        except Exception as e:
            self.logger.warning(f"Symbol refresh error: {e}")
            if not self._syms:
                self._syms = list(_FALLBACK_SYMBOLS)

    # ── Single symbol scan ────────────────────────────────────────────────────

    async def _scan(self, symbol: str) -> bool:
        """
        Scan one symbol for GEX flip signals.
        Uses real-time mark price (via premiumIndex) for crossover detection.
        Returns True if a signal was sent.
        """
        try:
            # Fetch primary (1h) and confirmation (4h) snapshots in parallel
            primary, confirm = await asyncio.gather(
                self.engine.compute_gex_snapshot(self.client, symbol, self.PRIMARY_TF),
                self.engine.compute_gex_snapshot(self.client, symbol, self.CONFIRM_TF),
                return_exceptions=True,
            )

            if isinstance(primary, Exception) or primary is None:
                return False

            prev = self._prev.get(symbol)
            self._prev[symbol] = primary      # Store current as next cycle's prev

            if prev is None:
                return False  # Need 2 cycles to detect crossover

            # ── 4h Confirmation filter ────────────────────────────────────────
            # Suppress signals that contradict the 4h GEX bias
            if not isinstance(confirm, Exception) and confirm is not None:
                if confirm.bias != "NEUTRAL":
                    if confirm.bias == "BULLISH" and primary.bias == "BEARISH":
                        return False  # 4h and 1h bias conflict
                    if confirm.bias == "BEARISH" and primary.bias == "BULLISH":
                        return False

                # 4h GEX zone must support the trade direction
                # (don't go long in 4h NEGATIVE zone unless strong signal)
                conf_zone_ok = True
                if confirm.current_gex_zone == "NEGATIVE" and primary.bias == "BULLISH":
                    # Only allow if primary confidence is very high
                    if primary.confidence < self.MIN_CONF + 10:
                        conf_zone_ok = False
                if not conf_zone_ok:
                    return False

            # ── Detect GEX flip crossover ─────────────────────────────────────
            sig = self.engine.detect_signal(prev, primary, self.MIN_CONF)
            if sig is None:
                return False

            # ── Rate limiting gate ────────────────────────────────────────────
            ok, reason = self.limiter.can_send(symbol, sig.action)
            if not ok:
                self.logger.debug(f"[{symbol}] Rate-limited: {reason}")
                return False

            # ── Format & broadcast ────────────────────────────────────────────
            msg = format_aegis_signal(sig)
            sent = await self.send_message(self.channel_id, msg)

            if sent:
                self.limiter.record(symbol, sig.action)
                self._signals_sent += 1
                self.logger.info(
                    f"📡 {symbol} {sig.direction} | {sig.signal_type} | "
                    f"Entry:{sig.entry_price:.6g} | TP1:{sig.tp1:.6g} | "
                    f"SL:{sig.sl:.6g} | Conf:{sig.confidence:.0f}% | R:R 1:{sig.rr_ratio:.1f}"
                )
                # Admin ping (concise)
                if self.admin_chat and str(self.admin_chat) != str(self.channel_id):
                    d_e = "🟢" if sig.action == "BUY" else "🔴"
                    await self.send_message(
                        self.admin_chat,
                        f"{d_e} AEGIS GEX: {symbol} {sig.direction}\n"
                        f"Type: {sig.signal_type} | Conf: {sig.confidence:.0f}%\n"
                        f"Entry: {sig.entry_price:.6g} → TP1: {sig.tp1:.6g} | SL: {sig.sl:.6g}",
                    )
                return True

        except Exception as e:
            self.logger.error(f"[{symbol}] scan error: {e}", exc_info=False)
        return False

    # ── Parallel scan cycle ───────────────────────────────────────────────────

    async def scan_all(self) -> int:
        """Scan all symbols in true parallel. Returns signals sent count."""
        if not self._syms:
            return 0

        async def _gate(sym: str) -> bool:
            if self.client.is_ip_banned():
                return False
            async with self._sem:
                if self.client.is_ip_banned():
                    return False
                try:
                    return await asyncio.wait_for(self._scan(sym), timeout=50.0)
                except asyncio.TimeoutError:
                    self.logger.debug(f"[{sym}] scan timeout (50s)")
                    return False
                except Exception as exc:
                    self.logger.debug(f"[{sym}] scan exc: {exc}")
                    return False

        results = await asyncio.gather(
            *[_gate(s) for s in self._syms],
            return_exceptions=True,
        )
        sent   = sum(1 for r in results if r is True)
        errors = sum(1 for r in results if isinstance(r, Exception))
        self.logger.info(
            f"⚡ Cycle #{self._cycles}: {len(self._syms)} syms | "
            f"{sent} signals | {errors} errs"
        )
        return sent

    # ── Startup message ───────────────────────────────────────────────────────

    async def _send_startup(self):
        msg = (
            f"🛡️ AEGIS GEX v1.0 — Started\n\n"
            f"Engine: GEX Dealer Flow (13 layers)\n"
            f"Entry: GEX Flip | TP: Next GEX Flip | SL: ATR Buffer\n"
            f"Signal Types: GEX Flip / Vanna Entry / Compression Break\n"
            f"Universe: ≤{_BinanceClient.MAX_SYMBOLS} USDM Perpetuals\n"
            f"TF: {self.PRIMARY_TF} primary + {self.CONFIRM_TF} confirm\n"
            f"Min Confidence: {self.MIN_CONF:.0f}%\n"
            f"Scan: every {self.SCAN_INTERVAL}s | Max: {self.limiter.MAX_PER_HOUR}/hr\n\n"
            f"Layers: Gamma Walls | Compression | Vanna Unwind\n"
            f"        Exp Move | VWAP ±ATR | GEX Flip | Charm Decay\n"
            f"        Strike Centers | Vanna Entry | Dashboard\n"
            f"        Session Open | OPEX Detection | 50 EMA\n\n"
            f"📡 @ichimokutradingsignal | AEGIS GEX v1.0"
        )
        await self.send_message(self.channel_id, msg)
        if self.admin_chat and str(self.admin_chat) != str(self.channel_id):
            await self.send_message(self.admin_chat, msg)

    async def _send_heartbeat(self):
        if not self.admin_chat:
            return
        up  = datetime.now() - self._start
        hrs = int(up.total_seconds() // 3600)
        mns = int((up.total_seconds() % 3600) // 60)
        await self.send_message(
            self.admin_chat,
            f"💓 AEGIS GEX v1.0 Heartbeat\n"
            f"Uptime: {hrs}h {mns}m | Cycles: {self._cycles}\n"
            f"Symbols: {len(self._syms)} | Signals: {self._signals_sent}\n"
            f"Limits: {self.limiter.MAX_PER_HOUR}/hr | {self.limiter.GLOBAL_GAP_SEC}s gap",
        )

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run(self):
        self.logger.info("🚀 AEGIS GEX v1.0 starting main loop...")
        await self._send_startup()
        await self._refresh_syms()

        last_hb = time.time()
        HB_INTERVAL = 3600

        while True:
            t0 = time.time()
            try:
                await self._refresh_syms()
                self._cycles += 1
                await self.scan_all()

                if time.time() - last_hb >= HB_INTERVAL:
                    await self._send_heartbeat()
                    last_hb = time.time()

            except asyncio.CancelledError:
                self.logger.info("🛑 AEGIS GEX shutdown")
                break
            except Exception as e:
                self.logger.error(f"Main loop error: {e}", exc_info=True)
                await asyncio.sleep(15)

            sleep = max(0.0, self.SCAN_INTERVAL - (time.time() - t0))
            if sleep > 0:
                await asyncio.sleep(sleep)

        await self.client.close()
        if self._tg_sess and not self._tg_sess.closed:
            await self._tg_sess.close()
        self.logger.info("✅ AEGIS GEX v1.0 stopped")
