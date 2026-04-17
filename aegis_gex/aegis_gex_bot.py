#!/usr/bin/env python3
"""
AEGIS GEX v1.0 — Production Telegram Signal Bot  (v4 — Enhanced)
========================================================================
Standalone — zero shared state with any other strategy.
Primary TF: 5m  |  Confirmation TF: 15m  |  Scan: 30s

Signal Logic (AEGIS GEX v1.0 spec):
  Entry  : Mark price CROSSES a GEX flip level in real-time
  TP1    : Entry × 1.0054  (0.54% — FIXED)
  TP2    : Entry × 1.0108  (1.08% — FIXED)
  TP3    : Entry × 1.0162  (1.62% base) or nearest GEX wall / compression target
  SL     : ATR-adaptive dynamic anchor — nearest technical level within
           [max(0.05%, 0.4×ATR), min(0.18%, 1.2×ATR)] budget.
           Levels (priority): nearest flip → GEX proxy → VWAP → VPOC →
           gamma wall → VWAP±0.5ATR → VWAP±1ATR.
           Hard cap: 0.18% from entry. Fallback: full ATR-scaled budget.

Quality Gates (ALL 20 must pass):
  Confidence ≥ 68% | DGRP ≥ 40 | Vol spike or DGRP ≥ 58 | Bias aligned
  ATR-adaptive min price move | FLIP ZONE or strength ≥ 65
  15m DGRP ≥ 25 | OPEX: conf ≥ 73% | 15m bias aligned
  VWAP side (0.3 ATR exception) | Momentum direction | EMA50 trend
  Funding not crowded | OI delta aligned | IV Z ≤ 3.0
  ATR not overextended | StochRSI not extreme | Stoch K/D cross | R:R ≥ 2.8

Dashboard (exact match to TradingView AEGIS GEX v1.0):
  Regime | DGRP Score | Candle | RV Ratio | IV Proxy Z
  Compression | Vanna | Charm Decay | Delta Bias | Exp Move
  Dealer Flow | GEX Regime | GEX Flip | Signal

Chart Levels in signal:
  GEX Flip Proxy | Call Wall | Put Wall
  VOL TRIGGER UP | VOL TRIGGER DN
  VWAP ±1/±2 ATR | Expected Move Bands | 50 EMA
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
    _fmt_price,
    SL_PCT,
    TP1_PCT,
    TP2_PCT,
    TP3_PCT,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Fallback symbol universe (top 80 USDM perpetuals by volume)
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_SYMBOLS: List[str] = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "SUIUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "INJUSDT",
    "NEARUSDT", "LTCUSDT", "SEIUSDT", "ATOMUSDT", "AAVEUSDT",
    "UNIUSDT", "LDOUSDT", "WLDUSDT", "ORDIUSDT", "RUNEUSDT",
    "STXUSDT", "MKRUSDT", "FETUSDT", "GMXUSDT", "DYDXUSDT",
    "GALAUSDT", "SANDUSDT", "AXSUSDT", "ICPUSDT", "FILUSDT",
    "TRXUSDT", "ETCUSDT", "BCHUSDT", "XLMUSDT", "VETUSDT",
    "ALGOUSDT", "GRTUSDT", "SNXUSDT", "CRVUSDT", "HBARUSDT",
    "MNTUSDT", "ARKMUSDT", "KASUSDT", "PENDLEUSDT", "PYTHUSDT",
    "PEPEUSDT", "WIFUSDT", "BOMEUSDT", "ENAUSDT", "JUPUSDT",
    "APEUSDT", "CHZUSDT", "MANAUSDT", "QNTUSDT", "IMXUSDT",
    "AGIXUSDT", "RNDRUSDT", "FLOWUSDT", "FTMUSDT", "EGLDUSDT",
    "COMPUSDT", "SUSHIUSDT", "CAKEUSDT", "ENJUSDT", "ZILUSDT",
    "THETAUSDT", "BANDUSDT", "STORJUSDT", "KNCUSDT", "BLURUSDT",
    "MATICUSDT", "TIAUSDT", "XMRUSDT", "CTKUSDT", "YGGUSDT",
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
# Binance Client
# ─────────────────────────────────────────────────────────────────────────────

class _BinanceClient:
    MIN_VOLUME_USDT = 25_000_000   # Lowered slightly for 5m TF
    MAX_SYMBOLS     = 80

    def __init__(self):
        self._session:    Optional[aiohttp.ClientSession]  = None
        self._connector:  Optional[aiohttp.TCPConnector]   = None
        self._geo_blocked: Dict[str, float]                = {}
        self._geo_ttl     = 3600.0
        self._ip_ban_until= 0.0
        self._cache: Dict[tuple, Tuple[float, object]]     = {}
        self._cache_ttl   = 22.0   # 22s — slightly under scan interval
        self.logger = logging.getLogger(f"{__name__}.BinanceClient")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._connector = aiohttp.TCPConnector(
                limit=200, limit_per_host=60,
                ttl_dns_cache=300, ssl=False,
            )
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=aiohttp.ClientTimeout(total=12),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
        if self._connector and not self._connector.closed:
            await self._connector.close()

    def _live_eps(self) -> List[str]:
        now = time.time()
        av  = [ep for ep in _FAPI_ENDPOINTS if now >= self._geo_blocked.get(ep, 0)]
        if not av:
            # Unblock the least-recently-blocked endpoint
            oldest = min(self._geo_blocked, key=self._geo_blocked.get)
            del self._geo_blocked[oldest]
            av = [oldest]
        return av

    async def _get(self, path: str, params: dict = None,
                   ck: tuple = None) -> Optional[object]:
        now = time.time()
        if now < self._ip_ban_until:
            wait = min(self._ip_ban_until - now, 30)
            await asyncio.sleep(wait)
            return None

        if ck:
            hit = self._cache.get(ck)
            if hit and now - hit[0] < self._cache_ttl:
                return hit[1]

        params = params or {}
        for ep in self._live_eps():
            try:
                s = await self._get_session()
                async with s.get(f"{ep}{path}", params=params) as r:
                    if r.status == 200:
                        self._geo_blocked.pop(ep, None)
                        data = await r.json()
                        if ck:
                            self._cache[ck] = (time.time(), data)
                            # Prune cache if too large
                            if len(self._cache) > 1500:
                                oldest_key = min(self._cache, key=lambda k: self._cache[k][0])
                                del self._cache[oldest_key]
                        return data
                    if r.status == 451:
                        self._geo_blocked[ep] = time.time() + self._geo_ttl
                        break
                    if r.status == 418:
                        self._ip_ban_until = time.time() + 120
                        return None
                    if r.status == 429:
                        retry_after = int(r.headers.get("Retry-After", "5"))
                        await asyncio.sleep(min(retry_after, 60))
                        continue
                    if 400 <= r.status < 500:
                        return None
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.debug(f"_get {path}: {e}")
                continue
        return None

    async def get_klines(self, symbol: str, interval: str,
                         limit: int = 500) -> Optional[list]:
        ck   = ("klines", symbol, interval, limit)
        data = await self._get("/fapi/v1/klines",
                               {"symbol": symbol, "interval": interval,
                                "limit": limit}, ck=ck)
        if data:
            return data
        # Fallback to spot klines
        try:
            s = await self._get_session()
            async with s.get(_SPOT_KLINES,
                             params={"symbol": symbol, "interval": interval,
                                     "limit": limit}) as r:
                if r.status == 200:
                    spot = await r.json()
                    self._cache[ck] = (time.time(), spot)
                    return spot
        except Exception:
            pass
        return None

    async def get_funding_rate(self, symbol: str) -> Optional[dict]:
        data = await self._get("/fapi/v1/premiumIndex", {"symbol": symbol},
                               ck=("funding", symbol))
        if data:
            return {"fundingRate": data.get("lastFundingRate", "0"),
                    "markPrice":   data.get("markPrice", "0")}
        return None

    async def get_premium_index(self, symbol: str) -> Optional[dict]:
        """Real-time mark price — no cache."""
        return await self._get("/fapi/v1/premiumIndex", {"symbol": symbol})

    async def get_open_interest(self, symbol: str) -> Optional[dict]:
        return await self._get("/fapi/v1/openInterest", {"symbol": symbol},
                               ck=("oi", symbol))

    async def get_24hr_ticker_stats(self, symbol: str) -> Optional[dict]:
        return await self._get("/fapi/v1/ticker/24hr", {"symbol": symbol},
                               ck=("ticker24", symbol))

    async def _get_fapi(self, path: str, params: dict = None) -> Optional[object]:
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
            return list(_FALLBACK_SYMBOLS)

        perp_set: set = set()
        if not isinstance(info, Exception) and info and "symbols" in info:
            for s in info["symbols"]:
                if s.get("contractType") == "PERPETUAL" and s.get("status") == "TRADING":
                    perp_set.add(s["symbol"])

        q = []
        for t in tickers:
            sym = t.get("symbol", "")
            if not sym.endswith("USDT") or "_" in sym:
                continue
            if perp_set and sym not in perp_set:
                continue
            try:
                v = float(t.get("quoteVolume", 0))
                if v >= self.MIN_VOLUME_USDT:
                    q.append((v, sym))
            except (ValueError, TypeError):
                pass

        q.sort(reverse=True)
        syms = [s for _, s in q[:self.MAX_SYMBOLS]]
        # Always keep BTCUSDT at index 0
        if "BTCUSDT" in syms:
            syms.remove("BTCUSDT")
        syms.insert(0, "BTCUSDT")
        return syms or list(_FALLBACK_SYMBOLS)


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limiter
# ─────────────────────────────────────────────────────────────────────────────

class _RateLimiter:
    def __init__(self):
        self._sym_last: Dict[str, float]             = {}
        self._sym_dir:  Dict[str, Tuple[str, float]] = {}
        self._global_ts: deque                       = deque(maxlen=100)

        # Tighter defaults for higher signal quality (5m TF)
        self.SYM_GAP    = int(os.getenv("GEX_SYMBOL_GAP_SEC", "300"))   # 5min per symbol
        self.GLOBAL_GAP = int(os.getenv("GEX_GLOBAL_GAP_SEC", "45"))    # 45s between signals
        self.MAX_HR     = int(os.getenv("GEX_MAX_PER_HOUR",   "15"))    # 15/hr max
        self.DEDUP_MIN  = int(os.getenv("GEX_DEDUP_MINUTES",  "20"))    # 20min dedup

    def can_send(self, symbol: str, action: str) -> Tuple[bool, str]:
        now_ts = time.time()
        now_dt = datetime.now()

        gap = now_ts - self._sym_last.get(symbol, 0)
        if gap < self.SYM_GAP:
            return False, f"sym-gap {self.SYM_GAP - gap:.0f}s"

        if symbol in self._sym_dir:
            d, ts = self._sym_dir[symbol]
            if d == action and now_ts - ts < self.DEDUP_MIN * 60:
                return False, f"dedup/{action}"

        cutoff = now_dt - timedelta(hours=1)
        recent = sum(1 for t in self._global_ts if t > cutoff)
        if recent >= self.MAX_HR:
            return False, f"cap {self.MAX_HR}/hr"

        if self._global_ts:
            g = (now_dt - self._global_ts[-1]).total_seconds()
            if g < self.GLOBAL_GAP:
                return False, f"global-gap {self.GLOBAL_GAP - g:.0f}s"

        return True, "ok"

    def record(self, symbol: str, action: str):
        ts = time.time()
        self._sym_last[symbol] = ts
        self._sym_dir[symbol]  = (action, ts)
        self._global_ts.append(datetime.now())


# ─────────────────────────────────────────────────────────────────────────────
# Signal Formatter — Cornix-compatible + AEGIS GEX Dashboard Table
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(v: float) -> str:
    """Delegate to engine formatter for consistent precision."""
    return _fmt_price(v)


def _pct(a: float, b: float) -> float:
    return abs(a - b) / b * 100.0 if b else 0.0


def _sig_label(st: str) -> str:
    return {
        "GEX_FLIP":          "GEX Flip",
        "VANNA_ENTRY":       "Vanna Entry",
        "COMPRESSION_BREAK": "Compression Break",
    }.get(st, st)


def format_aegis_signal(sig: GEXSignal) -> str:
    """
    STRICT Cornix-compatible trading signal.

    Format (exactly as required for Cornix auto-execution):
      🟢/🔴 #SYMBOL LONG/SHORT
      Exchange: Binance Futures
      Leverage: Cross Xx

      Entry Targets:
      1) <price>

      Take-Profit Targets:
      1) <price>
      2) <price>
      3) <price>

      Stop Targets:
      1) <price>

    Rules:
      • Pure decimal prices ONLY on every target line — no text, no % after price
      • Emoji prefix on header line is recognised and displayed by Telegram/Cornix
      • Blank line between every section (required by Cornix parser)
      • Nothing after Stop Targets — Cornix signal is self-contained

    SL / TP (strictly fixed from entry — 5m scalp R:R 1:3):
      SL  = 0.18%   TP1 = 0.54%   TP2 = 1.08%   TP3 = 1.62% (or GEX wall)
    """
    d_e = "🟢" if sig.action == "BUY" else "🔴"
    e, tp1, tp2, tp3, sl = sig.entry_price, sig.tp1, sig.tp2, sig.tp3, sig.sl
    lev = sig.leverage

    return (
        f"{d_e} #{sig.symbol} {sig.direction}\n"
        f"Exchange: Binance Futures\n"
        f"Leverage: Cross {lev}x\n"
        f"\n"
        f"Entry Targets:\n"
        f"1) {_fmt(e)}\n"
        f"\n"
        f"Take-Profit Targets:\n"
        f"1) {_fmt(tp1)}\n"
        f"2) {_fmt(tp2)}\n"
        f"3) {_fmt(tp3)}\n"
        f"\n"
        f"Stop Targets:\n"
        f"1) {_fmt(sl)}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main Bot
# ─────────────────────────────────────────────────────────────────────────────

class AEGISGEXBot:
    """
    AEGIS GEX v1.0 — Production Signal Bot

    Primary TF: 5m | Confirmation TF: 15m | Scan: 30s
    All 80 USDM symbols in true parallel (asyncio.gather + Semaphore).
    SL: ATR-adaptive (0.4–1.2×ATR, hard cap 0.18%) | TP1: 0.54% FIXED | TP2: 1.08% FIXED.
    """

    SCAN_INTERVAL   = int(os.getenv("GEX_SCAN_INTERVAL_SEC",  "30"))
    PARALLEL_LIMIT  = int(os.getenv("GEX_PARALLEL_LIMIT",     "30"))  # 30 concurrent
    SYM_REFRESH_SEC = int(os.getenv("GEX_SYMBOL_REFRESH_SEC", "3600"))
    MIN_CONF        = float(os.getenv("GEX_MIN_CONFIDENCE",   "68.0"))
    PRIMARY_TF      = os.getenv("GEX_PRIMARY_TF",  "5m")
    CONFIRM_TF      = os.getenv("GEX_CONFIRM_TF",  "15m")
    TG_SEND_GAP     = 1.5   # Seconds between Telegram sends

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN missing")

        _ch = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
        _ct = (os.getenv("TELEGRAM_CHAT_ID", "") or "").strip()
        self.channel_id = _ch if _ch else (_ct if _ct.startswith("-") else "-1002453842816")
        self.admin_chat = os.getenv("ADMIN_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
        self.base_url   = f"https://api.telegram.org/bot{self.bot_token}"

        self._tg_sess: Optional[aiohttp.ClientSession] = None
        self._tg_lock = asyncio.Lock()
        self._tg_last = 0.0

        self.client  = _BinanceClient()
        self.engine  = AEGISGEXEngine()
        self.limiter = _RateLimiter()

        self._sem         = asyncio.Semaphore(self.PARALLEL_LIMIT)
        self._prev: Dict[str, GEXSnapshot] = {}
        self._syms: List[str] = []
        self._syms_ts = 0.0
        self._start   = datetime.now()
        self._signals = 0
        self._cycles  = 0

        self.logger.info(
            f"🛡️ AEGIS GEX v1.0 | CH:{self.channel_id} | "
            f"TF:{self.PRIMARY_TF}+{self.CONFIRM_TF} | "
            f"Scan:{self.SCAN_INTERVAL}s | MinConf:{self.MIN_CONF:.0f}% | "
            f"SL:{SL_PCT*100:.2f}% TP:{TP1_PCT*100:.2f}%"
        )

    # ── Telegram ──────────────────────────────────────────────────────────────

    async def _tg_sess_get(self) -> aiohttp.ClientSession:
        if self._tg_sess is None or self._tg_sess.closed:
            self._tg_sess = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False),
                timeout=aiohttp.ClientTimeout(total=15),
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
        body = {
            "chat_id": chat_id,
            "text": text,
            "link_preview_options": {"is_disabled": True},
        }

        for attempt in range(retries):
            try:
                s = await self._tg_sess_get()
                async with s.post(url, json=body) as r:
                    if r.status == 200:
                        res = await r.json()
                        if res.get("ok"):
                            return True
                        desc = res.get("description", "")
                        if "chat not found" in desc.lower():
                            return False
                        # Markdown parse error — retry with plain text
                        if "can't parse" in desc.lower() or "parse" in desc.lower():
                            plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', text)
                            pb    = {"chat_id": chat_id, "text": plain,
                                     "link_preview_options": {"is_disabled": True}}
                            async with s.post(url, json=pb) as r2:
                                return (await r2.json()).get("ok", False)
                    elif r.status == 400:
                        try:
                            bd = await r.json()
                            self.logger.warning(f"TG 400: {bd.get('description', '?')}")
                        except Exception:
                            pass
                        return False
                    elif r.status == 429:
                        retry_after = int(r.headers.get("Retry-After", "5"))
                        await asyncio.sleep(min(retry_after, 60))
                        continue
                    await asyncio.sleep(2 ** attempt)
            except asyncio.TimeoutError:
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                self.logger.error(f"send_message attempt {attempt + 1}: {e}")
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
            self.logger.warning(f"Symbol refresh: {e}")
            if not self._syms:
                self._syms = list(_FALLBACK_SYMBOLS)

    # ── Single symbol scan ────────────────────────────────────────────────────

    async def _scan(self, symbol: str) -> bool:
        """
        Full GEX scan for one symbol.
        1. Compute 5m + 15m GEX snapshots in parallel
        2. Multi-gate quality check (confidence, DGRP, bias, vol)
        3. 15m confirmation filter
        4. Crossover detection
        5. Rate limit → broadcast
        """
        try:
            primary_res, confirm_res = await asyncio.gather(
                self.engine.compute_gex_snapshot(self.client, symbol, self.PRIMARY_TF),
                self.engine.compute_gex_snapshot(self.client, symbol, self.CONFIRM_TF),
                return_exceptions=True,
            )

            # Unwrap exceptions from gather
            primary = None if isinstance(primary_res, Exception) else primary_res
            confirm = None if isinstance(confirm_res, Exception) else confirm_res

            if primary is None:
                return False

            prev = self._prev.get(symbol)
            self._prev[symbol] = primary

            if prev is None:
                return False   # Need ≥2 cycles for crossover

            # ── Detect signal (passes confirm_snap for 15m check) ─────────────
            sig = self.engine.detect_signal(
                prev, primary,
                min_confidence=self.MIN_CONF,
                confirm_snap=confirm,
            )
            if sig is None:
                return False

            # ── Rate limiter ──────────────────────────────────────────────────
            ok, reason = self.limiter.can_send(symbol, sig.action)
            if not ok:
                self.logger.debug(f"[{symbol}] rate: {reason}")
                return False

            # ── Broadcast ─────────────────────────────────────────────────────
            msg  = format_aegis_signal(sig)
            sent = await self.send_message(self.channel_id, msg)

            if sent:
                self.limiter.record(symbol, sig.action)
                self._signals += 1
                self.logger.info(
                    f"📡 {symbol} {sig.direction} | {sig.signal_type} | "
                    f"DGRP:{sig.snapshot.dgrp_score:.0f} | "
                    f"Regime:{sig.snapshot.regime} | "
                    f"Vol spike:{sig.snapshot.vol_spike} | "
                    f"RSI:{sig.snapshot.rsi:.1f} | Stoch:{sig.snapshot.stoch_k:.1f} | "
                    f"Entry:{sig.entry_price:.6g} TP1:{sig.tp1:.6g} SL:{sig.sl:.6g} | "
                    f"Conf:{sig.confidence:.0f}% RR:{sig.rr_ratio:.1f}"
                )
                # Admin summary
                if self.admin_chat and str(self.admin_chat) != str(self.channel_id):
                    d_e  = "🟢" if sig.action == "BUY" else "🔴"
                    snap = sig.snapshot
                    await self.send_message(
                        self.admin_chat,
                        f"{d_e} AEGIS GEX: {symbol} {sig.direction} ({sig.signal_type})\n"
                        f"Regime: {snap.regime} | DGRP: {snap.dgrp_score:.0f} | "
                        f"GEX: {snap.gex_regime}\n"
                        f"Entry: {sig.entry_price:.6g} → "
                        f"TP1: {sig.tp1:.6g} | SL: {sig.sl:.6g}\n"
                        f"SL: {SL_PCT*100:.2f}% | TP1: {TP1_PCT*100:.2f}% "
                        f"(R:R 1:{sig.rr_ratio:.1f})\n"
                        f"Conf: {sig.confidence:.0f}% | Lev: {sig.leverage}x | "
                        f"Vol↑: {snap.vol_spike}",
                    )
                return True

        except Exception as e:
            self.logger.error(f"[{symbol}] scan error: {e}", exc_info=False)
        return False

    # ── Parallel scan ─────────────────────────────────────────────────────────

    async def scan_all(self) -> int:
        if not self._syms:
            return 0

        async def _gate(sym: str) -> bool:
            if self.client.is_ip_banned():
                return False
            async with self._sem:
                try:
                    return await asyncio.wait_for(self._scan(sym), timeout=28.0)
                except asyncio.TimeoutError:
                    return False
                except Exception:
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

    # ── Startup ───────────────────────────────────────────────────────────────

    async def _send_startup(self):
        msg = (
            f"🛡️ AEGIS GEX v1.0 — Live\n\n"
            f"Timeframe: {self.PRIMARY_TF} primary + {self.CONFIRM_TF} confirm\n"
            f"Scan interval: {self.SCAN_INTERVAL}s\n"
            f"Signal types: GEX Flip | Vanna Entry | Compression Break\n"
            f"Universe: ≤{_BinanceClient.MAX_SYMBOLS} USDM Perpetuals\n"
            f"Min Confidence: {self.MIN_CONF:.0f}%\n"
            f"Max signals: {self.limiter.MAX_HR}/hr\n\n"
            f"SL: ATR-adaptive (0.4–1.2×ATR, hard cap {SL_PCT*100:.2f}%)\n"
            f"  Priority: nearest flip → VWAP → VPOC → γ wall → VWAP±ATR\n"
            f"  TP1: {TP1_PCT*100:.2f}% FIXED | TP2: {TP2_PCT*100:.2f}% FIXED\n"
            f"  TP3: {TP3_PCT*100:.2f}% base → GEX wall / compression target\n\n"
            f"Quality Gates (20 layers):\n"
            f"  Conf ≥ {self.MIN_CONF:.0f}% | DGRP ≥ 40 | Vol spike OR DGRP ≥ 58\n"
            f"  ATR-adaptive move | FLIP ZONE or flip ≥ 65 str | 15m DGRP ≥ 25\n"
            f"  OPEX conf +5% | VWAP side | Momentum | EMA50 | Funding | OI\n"
            f"  IV Z ≤ 3.0 | ATR overext | StochRSI | Stoch K/D | R:R ≥ 2.8\n\n"
            f"Dashboard: Regime | DGRP | Candle | RV Ratio | IV Proxy Z\n"
            f"           Compression | Vanna | Charm | Delta Bias | Exp Move\n"
            f"           Dealer Flow | GEX Regime | GEX Flip ± Band\n\n"
            f"Chart: GEX Flip | Call Wall | Put Wall\n"
            f"       VOL Triggers | VWAP ±ATR | EMA50 | Expected Move\n\n"
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
            f"Up: {hrs}h {mns}m | Cycles: {self._cycles} | Signals: {self._signals}\n"
            f"Syms: {len(self._syms)} | TF: {self.PRIMARY_TF}+{self.CONFIRM_TF}\n"
            f"Rate/hr cap: {self.limiter.MAX_HR} | "
            f"SL: {SL_PCT*100:.2f}% | TP1: {TP1_PCT*100:.2f}%",
        )

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run(self):
        self.logger.info("🚀 AEGIS GEX v1.0 starting main loop...")
        await self._send_startup()
        await self._refresh_syms()

        last_hb = time.time()
        HB_SEC  = 3600  # Heartbeat every hour

        while True:
            t0 = time.time()
            try:
                await self._refresh_syms()
                self._cycles += 1
                await self.scan_all()

                if time.time() - last_hb >= HB_SEC:
                    await self._send_heartbeat()
                    last_hb = time.time()

            except asyncio.CancelledError:
                self.logger.info("🛑 Shutdown signal received")
                break
            except Exception as e:
                self.logger.error(f"Main loop error: {e}", exc_info=True)
                await asyncio.sleep(15)

            elapsed = time.time() - t0
            sleep   = max(0.0, self.SCAN_INTERVAL - elapsed)
            if sleep > 0:
                await asyncio.sleep(sleep)

        # Graceful cleanup
        await self.client.close()
        if self._tg_sess and not self._tg_sess.closed:
            await self._tg_sess.close()
        self.logger.info(
            f"🛑 AEGIS GEX v1.0 stopped | "
            f"Cycles: {self._cycles} | Signals: {self._signals}"
        )
