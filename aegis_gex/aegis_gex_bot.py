#!/usr/bin/env python3
"""
AEGIS GEX v1.0 — Production Telegram Signal Bot  (v3 — Full Dashboard)
========================================================================
Standalone — zero shared state with any other strategy.
Primary TF: 5m  |  Confirmation TF: 15m  |  Scan: 30s

Signal Logic:
  Entry  : Mark price CROSSES a GEX flip level in real-time
  TP     : Next GEX flip level in trade direction (dynamic updates each cycle)
  SL     : ATR buffer + Call/Put Wall beyond entry flip

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
    MIN_VOLUME_USDT = 30_000_000   # Lowered for 5m TF (more symbols qualify)
    MAX_SYMBOLS     = 80

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession]   = None
        self._connector: Optional[aiohttp.TCPConnector]  = None
        self._geo_blocked: Dict[str, float]              = {}
        self._geo_ttl     = 3600.0
        self._ip_ban_until= 0.0
        self._cache: Dict[tuple, Tuple[float, object]]   = {}
        self._cache_ttl   = 25.0   # 25s for 5m TF
        self.logger = logging.getLogger(f"{__name__}.BinanceClient")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._connector = aiohttp.TCPConnector(
                limit=150, limit_per_host=50,
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
        if self._connector:
            await self._connector.close()

    def _live_eps(self) -> List[str]:
        now = time.time()
        av  = [ep for ep in _FAPI_ENDPOINTS if now >= self._geo_blocked.get(ep, 0)]
        if not av:
            oldest = min(self._geo_blocked, key=self._geo_blocked.get)
            del self._geo_blocked[oldest]
            av = [oldest]
        return av

    async def _get(self, path: str, params: dict = None,
                   ck: tuple = None) -> Optional[object]:
        now = time.time()
        if now < self._ip_ban_until:
            await asyncio.sleep(min(self._ip_ban_until - now, 30))
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
                            if len(self._cache) > 1200:
                                old = min(self._cache, key=lambda k: self._cache[k][0])
                                del self._cache[old]
                        return data
                    if r.status == 451:
                        self._geo_blocked[ep] = time.time() + self._geo_ttl
                        break
                    if r.status == 418:
                        self._ip_ban_until = time.time() + 120
                        return None
                    if r.status == 429:
                        ra = int(r.headers.get("Retry-After", "5"))
                        await asyncio.sleep(min(ra, 60))
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
                               {"symbol": symbol, "interval": interval, "limit": limit},
                               ck=ck)
        if data:
            return data
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
        if "BTCUSDT" in syms:
            syms.remove("BTCUSDT")
        syms.insert(0, "BTCUSDT")
        return syms or list(_FALLBACK_SYMBOLS)


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limiter
# ─────────────────────────────────────────────────────────────────────────────

class _RateLimiter:
    def __init__(self):
        self._sym_last: Dict[str, float]            = {}
        self._sym_dir:  Dict[str, Tuple[str, float]]= {}
        self._global_ts: deque                      = deque(maxlen=100)

        self.SYM_GAP    = int(os.getenv("GEX_SYMBOL_GAP_SEC",  "180"))  # 3min for 5m TF
        self.GLOBAL_GAP = int(os.getenv("GEX_GLOBAL_GAP_SEC",  "30"))   # 30s for 5m TF
        self.MAX_HR     = int(os.getenv("GEX_MAX_PER_HOUR",    "20"))   # 20/hr for 5m TF
        self.DEDUP_MIN  = int(os.getenv("GEX_DEDUP_MINUTES",   "15"))   # 15min dedup for 5m

    def can_send(self, symbol: str, action: str) -> Tuple[bool, str]:
        now_ts = time.time()
        now_dt = datetime.now()

        gap = now_ts - self._sym_last.get(symbol, 0)
        if gap < self.SYM_GAP:
            return False, f"sym-gap {self.SYM_GAP-gap:.0f}s"

        if symbol in self._sym_dir:
            d, ts = self._sym_dir[symbol]
            if d == action and now_ts - ts < self.DEDUP_MIN * 60:
                return False, f"dedup/{action}"

        cutoff = now_dt - timedelta(hours=1)
        if sum(1 for t in self._global_ts if t > cutoff) >= self.MAX_HR:
            return False, f"cap {self.MAX_HR}/hr"

        if self._global_ts:
            g = (now_dt - self._global_ts[-1]).total_seconds()
            if g < self.GLOBAL_GAP:
                return False, f"global-gap {self.GLOBAL_GAP-g:.0f}s"

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
    if v >= 10000: return f"{v:.2f}"
    if v >= 1000:  return f"{v:.3f}"
    if v >= 100:   return f"{v:.4f}"
    if v >= 10:    return f"{v:.5f}"
    return f"{v:.6f}"

def _pct(a: float, b: float) -> float:
    return abs(a - b) / b * 100.0 if b else 0.0

def _sig_label(st: str) -> str:
    return {"GEX_FLIP": "GEX Flip", "VANNA_ENTRY": "Vanna Entry",
            "COMPRESSION_BREAK": "Compression Break"}.get(st, st)

def format_aegis_signal(sig: GEXSignal) -> str:
    """
    Cornix-compatible signal + full AEGIS GEX Dashboard Table.

    Dashboard matches the TradingView AEGIS GEX v1.0 indicator exactly:
      Regime | DGRP | Candle | RV Ratio | IV Proxy Z
      Compression | Vanna | Charm Decay | Delta Bias | Exp Move
      Dealer Flow | GEX Regime | GEX Flip ± | Signal
    """
    snap = sig.snapshot
    d_e  = "🟢" if sig.action == "BUY" else "🔴"
    e, tp1, tp2, tp3, sl = (sig.entry_price, sig.tp1, sig.tp2, sig.tp3, sig.sl)
    lev  = sig.leverage

    tp1p = _pct(tp1, e); tp2p = _pct(tp2, e)
    tp3p = _pct(tp3, e); slp  = _pct(sl, e)

    ts   = datetime.utcnow().strftime("%H:%M")
    date = datetime.utcnow().strftime("%b %d")

    # ── Dashboard Table ───────────────────────────────────────────────────────
    fund_str = f"{sig.funding_rate*100:+.4f}%"
    oi_str   = f"{sig.oi_delta_pct:+.1f}%"

    # Format dealer flow: +.1M, -.2M etc.
    df_abs = abs(snap.dealer_flow_m)
    df_sign= "+" if snap.dealer_flow_m >= 0 else "-"
    if df_abs >= 1000:
        df_str = f"{df_sign}{df_abs/1000:.1f}B"
    elif df_abs >= 1:
        df_str = f"{df_sign}{df_abs:.1f}M"
    else:
        df_str = f"{df_sign}{df_abs*1000:.0f}K"

    # Format exp_move: ± value
    em_str = f"± {_fmt(snap.exp_move)}"

    # Format GEX flip with band: $price ± band
    gf_str = f"{_fmt(snap.gex_flip)} ± {_fmt(snap.gex_flip_band)}"

    # Regime color indicator
    regime_icon = {
        "FLIP ZONE": "🟡", "POSITIVE": "🟢",
        "NEGATIVE":  "🔴", "NEUTRAL":  "⚪",
    }.get(snap.regime, "⚪")

    gex_reg_icon = "🟢" if snap.gex_regime == "LONG GAMMA" else "🔴"

    bias_e = "🐂" if sig.bias == "BULLISH" else ("🐻" if sig.bias == "BEARISH" else "⚖️")

    # ── Signal label ──────────────────────────────────────────────────────────
    st_label = _sig_label(sig.signal_type)
    zone_arrow = "↑" if sig.action == "BUY" else "↓"
    gex_zone   = f"GEX {sig.gex_zone_from[:3]}{zone_arrow}{sig.gex_zone_to[:3]}"

    # ── Chart levels ─────────────────────────────────────────────────────────
    cw_str = _fmt(snap.call_wall) if snap.call_wall else "—"
    pw_str = _fmt(snap.put_wall)  if snap.put_wall  else "—"
    vt_up  = _fmt(snap.vol_trigger_up)
    vt_dn  = _fmt(snap.vol_trigger_dn)

    # VWAP bands
    vwap_pos = "above" if e > snap.vwap else "below"
    vwap_b1  = f"[{_fmt(snap.vwap_minus1_atr)} – {_fmt(snap.vwap_plus1_atr)}]"
    vwap_b2  = f"[{_fmt(snap.vwap_minus2_atr)} – {_fmt(snap.vwap_plus2_atr)}]"

    # EMA
    ema_str = ""
    if sig.ema50:
        ema_str = f"EMA50: {'>' if e > sig.ema50 else '<'} {_fmt(sig.ema50)}\n"

    # Nearest flip levels
    nf_up = _fmt(snap.nearest_flip_up)  if snap.nearest_flip_up  else "—"
    nf_dn = _fmt(snap.nearest_flip_down) if snap.nearest_flip_down else "—"
    all_fl = sorted(set(_fmt(fl.price) for fl in snap.all_flip_levels[:6]))

    # Compression / Vanna info
    extra = ""
    if snap.compression_zones:
        cz = snap.compression_zones[0]
        extra += f"Compression: [{_fmt(cz.price_low)} – {_fmt(cz.price_high)}] → {_fmt(cz.target) if cz.target else '?'}\n"
    if sig.vanna_entry:
        extra += f"Vanna Entry Line: {_fmt(sig.vanna_entry)}\n"

    opex_str = "\n⚠️ OPEX WEEK — reduced confidence\n" if snap.is_opex_week else ""
    sess_str = f"Session+{snap.session_open_minute}min"

    msg = (
        f"{d_e} #{sig.symbol} {sig.direction}\n"
        f"Exchange: Binance Futures\n"
        f"Leverage: Cross {lev}x\n\n"
        f"Entry Targets:\n1) {_fmt(e)}\n\n"
        f"Take-Profit Targets:\n"
        f"1) {_fmt(tp1)}\n"
        f"2) {_fmt(tp2)}\n"
        f"3) {_fmt(tp3)}\n\n"
        f"Stop Targets:\n1) {_fmt(sl)}\n\n"
        f"━━ AEGIS GEX v1.0 Dashboard ━━━━━━━━━\n"
        f"Regime:       {regime_icon} {snap.regime}\n"
        f"DGRP Score:   {snap.dgrp_score:.0f} / 100\n"
        f"Candle:       {snap.candle_state}\n"
        f"RV Ratio:     {snap.rv_ratio:.2f}\n"
        f"IV Proxy Z:   {snap.iv_proxy_z:+.2f}\n"
        f"Compression:  {snap.compression_state}\n"
        f"Vanna:        {snap.vanna_state}\n"
        f"Charm Decay:  {snap.charm_state}\n"
        f"Delta Bias:   {snap.delta_bias}\n"
        f"Exp Move:     {em_str}\n"
        f"Dealer Flow:  {df_str}\n"
        f"GEX Regime:   {gex_reg_icon} {snap.gex_regime}\n"
        f"GEX Flip:     ${gf_str}\n"
        f"Signal:       {st_label} {gex_zone}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Chart Levels:\n"
        f"GEX Flip Proxy:    {_fmt(snap.gamma_flip_proxy)}\n"
        f"Call Wall:         {cw_str}\n"
        f"Put Wall:          {pw_str}\n"
        f"VOL Trigger UP:    {vt_up}\n"
        f"VOL Trigger DN:    {vt_dn}\n"
        f"GEX Flip ↑: {nf_up}  |  ↓: {nf_dn}\n"
        f"All GEX Flips:     {', '.join(all_fl)}\n"
        f"\n"
        f"VWAP ({_fmt(snap.vwap)}):  {vwap_pos}\n"
        f"VWAP ±1 ATR:  {vwap_b1}\n"
        f"VWAP ±2 ATR:  {vwap_b2}\n"
        f"Exp Move Bands: [{_fmt(snap.expected_move_lower)} – {_fmt(snap.expected_move_upper)}]\n"
    )

    if ema_str:
        msg += ema_str
    if extra:
        msg += extra

    msg += (
        f"\n"
        f"Confidence: {sig.confidence:.0f}%  |  R:R 1:{sig.rr_ratio:.1f}  |  Lev: {lev}x\n"
        f"TP: +{tp1p:.1f}%/+{tp2p:.1f}%/+{tp3p:.1f}%  |  SL: -{slp:.1f}%\n"
        f"Funding: {fund_str}  |  OI∆: {oi_str}\n"
        f"ATR: {_fmt(snap.atr)}  |  {sess_str}  |  {sig.timeframe} TF\n"
        f"{date} {ts} UTC  |  {bias_e} {sig.bias}"
        f"{opex_str}\n"
        f"📡 @ichimokutradingsignal | AEGIS GEX v1.0"
    )
    return msg


# ─────────────────────────────────────────────────────────────────────────────
# Main Bot
# ─────────────────────────────────────────────────────────────────────────────

class AEGISGEXBot:
    """
    AEGIS GEX v1.0 — Production Signal Bot

    Primary TF: 5m | Confirmation TF: 15m | Scan: 30s
    All 80 USDM symbols in true parallel (asyncio.gather + Semaphore).
    """

    SCAN_INTERVAL   = int(os.getenv("GEX_SCAN_INTERVAL_SEC",  "30"))   # 30s for 5m TF
    PARALLEL_LIMIT  = int(os.getenv("GEX_PARALLEL_LIMIT",     "25"))   # 25 concurrent
    SYM_REFRESH_SEC = int(os.getenv("GEX_SYMBOL_REFRESH_SEC", "3600"))
    MIN_CONF        = float(os.getenv("GEX_MIN_CONFIDENCE",   "60.0"))
    PRIMARY_TF      = os.getenv("GEX_PRIMARY_TF",  "5m")    # 5m primary
    CONFIRM_TF      = os.getenv("GEX_CONFIRM_TF",  "15m")   # 15m confirm
    TG_SEND_GAP     = 1.5

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
            f"TF:{self.PRIMARY_TF}+{self.CONFIRM_TF} | Scan:{self.SCAN_INTERVAL}s | "
            f"MinConf:{self.MIN_CONF:.0f}%"
        )

    # ── Telegram ──────────────────────────────────────────────────────────────

    async def _tg_sess_get(self) -> aiohttp.ClientSession:
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
                s = await self._tg_sess_get()
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
                                return (await r2.json()).get("ok", False)
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
                self.logger.error(f"send_message attempt {attempt+1}: {e}")
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
        GEX flip scan for one symbol.
        1. Compute 5m + 15m GEX snapshots (parallel)
        2. 15m confirmation filter (zone + bias alignment)
        3. Compare mark prices → detect crossover
        4. 13-layer confidence gate → rate limit → broadcast
        """
        try:
            primary, confirm = await asyncio.gather(
                self.engine.compute_gex_snapshot(self.client, symbol, self.PRIMARY_TF),
                self.engine.compute_gex_snapshot(self.client, symbol, self.CONFIRM_TF),
                return_exceptions=True,
            )

            if isinstance(primary, Exception) or primary is None:
                return False

            prev = self._prev.get(symbol)
            self._prev[symbol] = primary

            if prev is None:
                return False  # Need 2 cycles for crossover detection

            # ── 15m Confirmation filter ───────────────────────────────────────
            if not isinstance(confirm, Exception) and confirm is not None:
                # Direction must not contradict 15m bias
                if confirm.bias != "NEUTRAL":
                    if confirm.bias == "BULLISH" and primary.bias == "BEARISH":
                        return False
                    if confirm.bias == "BEARISH" and primary.bias == "BULLISH":
                        return False
                # 15m GEX regime must not actively oppose signal direction
                # (SHORT GAMMA on 15m = trending → allow any direction)
                # (LONG GAMMA on 15m = pinned → need extra confidence)
                if confirm.gex_regime == "LONG GAMMA" and primary.confidence < self.MIN_CONF + 8:
                    return False

            # ── Detect signal ─────────────────────────────────────────────────
            sig = self.engine.detect_signal(prev, primary, self.MIN_CONF)
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
                    f"DGRP:{sig.snapshot.dgrp_score:.0f} | Regime:{sig.snapshot.regime} | "
                    f"Entry:{sig.entry_price:.6g} TP1:{sig.tp1:.6g} SL:{sig.sl:.6g} | "
                    f"Conf:{sig.confidence:.0f}% RR:{sig.rr_ratio:.1f}"
                )
                if self.admin_chat and str(self.admin_chat) != str(self.channel_id):
                    d_e = "🟢" if sig.action == "BUY" else "🔴"
                    snap = sig.snapshot
                    await self.send_message(
                        self.admin_chat,
                        f"{d_e} AEGIS GEX: {symbol} {sig.direction} ({sig.signal_type})\n"
                        f"Regime: {snap.regime} | DGRP: {snap.dgrp_score:.0f} | GEX: {snap.gex_regime}\n"
                        f"Entry: {sig.entry_price:.6g} → TP1: {sig.tp1:.6g} | SL: {sig.sl:.6g}\n"
                        f"Conf: {sig.confidence:.0f}% | R:R 1:{sig.rr_ratio:.1f} | Lev: {sig.leverage}x",
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

        results = await asyncio.gather(*[_gate(s) for s in self._syms],
                                       return_exceptions=True)
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
            f"Syms: {len(self._syms)} | TF: {self.PRIMARY_TF}+{self.CONFIRM_TF}",
        )

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run(self):
        self.logger.info("🚀 AEGIS GEX v1.0 starting main loop...")
        await self._send_startup()
        await self._refresh_syms()

        last_hb = time.time()
        HB_SEC  = 3600

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
                self.logger.info("🛑 Shutdown")
                break
            except Exception as e:
                self.logger.error(f"Main loop: {e}", exc_info=True)
                await asyncio.sleep(15)

            sleep = max(0.0, self.SCAN_INTERVAL - (time.time() - t0))
            if sleep > 0:
                await asyncio.sleep(sleep)

        await self.client.close()
        if self._tg_sess and not self._tg_sess.closed:
            await self._tg_sess.close()
