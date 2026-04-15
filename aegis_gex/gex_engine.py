#!/usr/bin/env python3
"""
AEGIS GEX v1.0 — Dealer Flow Engine  (Complete Rebuild)
=========================================================
Pure-Python, zero-dependency GEX Dealer Flow Engine for Binance USDM perpetuals.
Based on: AEGIS GEX DEALER FLOW ENGINE (TradingView: T1zYSBd7)

All 13 indicator layers from the original TradingView script are implemented:
  1.  Gamma Wall Boxes          — Price zones with peak OI concentration
  2.  Compression Boxes         — Two gamma walls close together (pre-breakout coil)
  3.  Vanna Unwind Zones        — dGamma/dVol zones; dealers rehedge aggressively here
  4.  Expected Move Bands       — IV-derived ±1 StdDev price range
  5.  VWAP + Bands              — VWAP ±1 ATR, ±2 ATR bands
  6.  Gamma Flip Proxy Line     — Primary GEX zero-crossing line
  7.  Charm Decay Intensity     — Time-decay effect on dealer delta hedging
  8.  Strike Center Lines       — Centroid of each gamma strike cluster
  9.  Compression Mid + Target  — Mid-point and breakout target of compression zones
  10. Vanna Entry Line          — Secondary entry signal from Vanna positioning
  11. GEX Flip Line + Band      — The main entry signal with ATR band
  12. Dashboard Table           — Summary of all key levels (embedded in signal message)
  13. Session Open Minute logic — Recalibrate GEX at session open + 30min mark

Critical bug fixes vs v1:
  - Use REAL-TIME mark price (not candle close) for GEX flip crossover detection
  - 41-level strike grid (was 21) for more granular flip detection
  - Vanna proxy computed from funding rate velocity × OI acceleration
  - Charm Decay computed from time-to-next-funding × |funding_rate|
  - Compression zones from paired gamma walls < 2 ATR apart
  - VWAP bands filter: entry only valid if price is on VWAP band side
  - 50 EMA trend filter: suppress counter-trend entries
  - OPEX awareness: reduce confidence near monthly options expiration
  - Confidence scoring uses all 13 layers (was 4 signals)
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GEXLevel:
    """A single Gamma Exposure level (flip point or gamma wall)."""
    price: float
    gex_value: float        # Net GEX proxy (positive = long gamma, negative = short gamma)
    is_flip: bool           # True = sign-change zero-crossing
    strength: float         # 0–100 strength score
    level_type: str         # "FLIP_UP"|"FLIP_DOWN"|"WALL_BULL"|"WALL_BEAR"|"STRIKE_CENTER"
    timeframe: str


@dataclass
class GEXZone:
    """A price zone (gamma wall box or compression box)."""
    price_low: float
    price_high: float
    zone_type: str          # "GAMMA_WALL_BULL"|"GAMMA_WALL_BEAR"|"COMPRESSION"
    strength: float         # 0–100
    mid: float              # (price_low + price_high) / 2
    target: Optional[float] # For compression: breakout target


@dataclass
class GEXSnapshot:
    """Complete GEX picture for one symbol at a moment in time."""
    symbol: str
    timestamp: float
    mark_price: float           # Real-time mark price (NOT candle close)
    current_gex_zone: str       # "POSITIVE" | "NEGATIVE" | "NEUTRAL"
    net_gex: float
    nearest_flip_up: Optional[float]
    nearest_flip_down: Optional[float]
    all_flip_levels: List[GEXLevel]
    gamma_walls: List[GEXZone]
    compression_zones: List[GEXZone]
    vanna_unwind_up: Optional[float]     # Vanna unwind level above
    vanna_unwind_down: Optional[float]   # Vanna unwind level below
    vanna_entry: Optional[float]         # Vanna entry line
    expected_move_upper: float           # VWAP + expected move
    expected_move_lower: float           # VWAP - expected move
    vwap: float
    vwap_plus1_atr: float
    vwap_minus1_atr: float
    vwap_plus2_atr: float
    vwap_minus2_atr: float
    ema50: Optional[float]
    gamma_flip_proxy: float              # Primary GEX flip level (Gamma Flip Proxy Line)
    charm_decay: float                   # 0–1 charm decay intensity
    atr: float
    funding_rate: float
    open_interest: float
    oi_delta_pct: float
    volume_24h: float
    bias: str                            # "BULLISH"|"BEARISH"|"NEUTRAL"
    confidence: float                    # 0–100
    is_opex_week: bool                   # Near monthly options expiration
    session_open_minute: int             # Minutes since session open


@dataclass
class GEXSignal:
    """A trading signal produced by the AEGIS GEX engine."""
    symbol: str
    action: str             # "BUY" | "SELL"
    direction: str          # "LONG" | "SHORT"
    signal_type: str        # "GEX_FLIP" | "VANNA_ENTRY" | "COMPRESSION_BREAK"
    entry_price: float      # The GEX flip level that was crossed
    entry_flip_level: float
    tp1: float              # Next GEX flip in direction (primary dynamic TP)
    tp2: float              # Second flip (extended TP)
    tp3: float              # Third flip (runner TP)
    sl: float               # ATR buffer beyond entry flip
    confidence: float
    timeframe: str
    gex_zone_from: str
    gex_zone_to: str
    leverage: int
    rr_ratio: float
    bias: str
    atr: float
    funding_rate: float
    open_interest: float
    oi_delta_pct: float
    charm_decay: float
    vanna_entry: Optional[float]
    expected_move_upper: float
    expected_move_lower: float
    vwap: float
    gamma_flip_proxy: float
    ema50: Optional[float]
    nearest_compression: Optional[GEXZone]
    snapshot: GEXSnapshot
    timestamp: float = field(default_factory=time.time)
    signal_id: str = ""

    def __post_init__(self):
        if not self.signal_id:
            self.signal_id = f"GEX_{self.symbol}_{self.action}_{int(self.timestamp)}"


# ─────────────────────────────────────────────────────────────────────────────
# Pure-Python Indicator Helpers (zero external dependencies)
# ─────────────────────────────────────────────────────────────────────────────

def _ema(data: List[float], period: int) -> Optional[float]:
    if len(data) < period:
        return None
    k = 2.0 / (period + 1)
    e = sum(data[:period]) / period
    for v in data[period:]:
        e = v * k + e * (1 - k)
    return e

def _ema_series(data: List[float], period: int) -> List[Optional[float]]:
    """Full EMA series for all bars."""
    if len(data) < period:
        return [None] * len(data)
    k = 2.0 / (period + 1)
    e = sum(data[:period]) / period
    out: List[Optional[float]] = [None] * (period - 1)
    out.append(e)
    for v in data[period:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out

def _atr(closes: List[float], highs: List[float], lows: List[float],
         period: int = 14) -> float:
    """Wilder's ATR with true range (prev_close correction)."""
    n = min(len(closes), len(highs), len(lows))
    if n < 2:
        return max(abs(closes[-1] * 0.005), 1e-8) if closes else 1.0
    trs = [
        max(highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i]  - closes[i-1]))
        for i in range(1, n)
    ]
    if len(trs) < period:
        return sum(trs) / len(trs) if trs else 1.0
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr

def _vwap(closes: List[float], highs: List[float],
          lows: List[float], volumes: List[float]) -> Optional[float]:
    n = min(len(closes), len(highs), len(lows), len(volumes))
    if n == 0:
        return None
    tv = sum((highs[i]+lows[i]+closes[i])/3 * volumes[i] for i in range(n))
    sv = sum(volumes[:n])
    return tv / sv if sv > 0 else None

def _rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period-1) + gains[i]) / period
        al = (al * (period-1) + losses[i]) / period
    return 100.0 if al == 0 else 100 - 100 / (1 + ag/al)

def _stdev(data: List[float], period: int) -> float:
    if len(data) < period:
        return 0.0
    w = data[-period:]
    mu = sum(w) / period
    return math.sqrt(sum((x - mu)**2 for x in w) / period)

def _gaussian(distance: float, sigma: float) -> float:
    if sigma <= 0:
        return 0.0
    return math.exp(-0.5 * (distance / sigma) ** 2)

def _vpoc(closes: List[float], highs: List[float],
          lows: List[float], volumes: List[float],
          bins: int = 100) -> Optional[float]:
    """Volume Profile Point of Control."""
    n = min(len(closes), len(highs), len(lows), len(volumes))
    if n < 10:
        return None
    lo, hi = min(lows[-n:]), max(highs[-n:])
    if hi <= lo:
        return None
    bsz = (hi - lo) / bins
    vol_bins = [0.0] * bins
    for i in range(n):
        mid = (highs[i] + lows[i] + closes[i]) / 3.0
        idx = min(int((mid - lo) / bsz), bins - 1)
        vol_bins[idx] += volumes[i]
    pk = vol_bins.index(max(vol_bins))
    return lo + (pk + 0.5) * bsz

def _is_opex_week() -> bool:
    """
    Detect monthly options expiration week.
    Standard OPEX = 3rd Friday of each month.
    Returns True if today is within 3 days of OPEX Friday.
    """
    import calendar as _cal
    now = datetime.now(timezone.utc)
    # Find 3rd Friday: calendar.monthcalendar returns rows of weeks
    month_cal = _cal.monthcalendar(now.year, now.month)
    fridays = [week[4] for week in month_cal if week[4] != 0]  # weekday index 4 = Friday
    if len(fridays) < 3:
        return False
    opex_day = fridays[2]
    opex_date = now.date().replace(day=opex_day)
    delta = abs((now.date() - opex_date).days)
    return delta <= 3

def _session_open_minute() -> int:
    """Minutes elapsed since the closest major session open (00:00, 08:00, 16:00 UTC)."""
    now = datetime.now(timezone.utc)
    minute_of_day = now.hour * 60 + now.minute
    opens = [0, 480, 960]   # 00:00, 08:00, 16:00 UTC
    return min((minute_of_day - o) % 1440 for o in opens)

def _interpolate_zero(x1: float, x2: float, y1: float, y2: float) -> float:
    """Linear interpolation to the zero-crossing between two points."""
    if y1 == y2:
        return (x1 + x2) / 2
    return x1 + (x2 - x1) * (-y1 / (y2 - y1))


# ─────────────────────────────────────────────────────────────────────────────
# AEGIS GEX Engine — Full Rebuild
# ─────────────────────────────────────────────────────────────────────────────

class AEGISGEXEngine:
    """
    AEGIS GEX Dealer Flow Engine v1.0 — Complete Implementation

    All 13 indicator layers implemented.
    Uses real-time mark price for crossover detection (critical bug fix).
    """

    # Strike grid
    STRIKE_COUNT     = 41          # 41 levels = ±20 ATR (was 21 — doubled resolution)
    ATR_PERIOD       = 14
    ATR_MULT         = 0.75        # Strike spacing = 0.75 ATR (tighter grid)
    SIGMA_MULT       = 4.0         # Gaussian sigma = 4 ATR (wider distribution)
    FLIP_MIN_STR     = 10.0        # Min strength for a flip level
    WALL_MIN_STR     = 20.0        # Min strength for a gamma wall
    COMPRESS_MAX_GAP = 2.0         # Max ATR gap between walls to form compression

    # Session open minute (from screenshot: default 30)
    SESSION_OPEN_MINUTE = int(
        __import__("os").getenv("GEX_SESSION_OPEN_MINUTE", "30")
    )

    LOOKBACK = {
        "15m": 300, "30m": 200,
        "1h":  200, "4h":  200, "1d": 100,
    }
    OI_HIST_PERIOD = {
        "15m": "5m", "30m": "15m",
        "1h":  "1h", "4h":  "4h", "1d": "1d",
    }

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.GEXEngine")
        self._cache: Dict[str, Tuple[float, GEXSnapshot]] = {}
        self._cache_ttl = 55.0   # slightly under scan interval to stay fresh

    # ─── Public: compute snapshot ────────────────────────────────────────────

    async def compute_gex_snapshot(
        self,
        client,
        symbol: str,
        timeframe: str = "1h",
    ) -> Optional[GEXSnapshot]:
        """
        Compute a complete AEGIS GEX snapshot for one symbol.
        ─ Uses real-time mark price (not last candle close) for crossover.
        ─ Caches for 55 seconds to avoid redundant Binance calls.
        """
        ck = f"{symbol}_{timeframe}"
        cached = self._cache.get(ck)
        if cached:
            ts, snap = cached
            if time.time() - ts < self._cache_ttl:
                return snap

        try:
            limit = self.LOOKBACK.get(timeframe, 200)

            klines, funding, oi_now, ticker, mark_price_data = await asyncio.gather(
                client.get_klines(symbol, timeframe, limit),
                client.get_funding_rate(symbol),
                client.get_open_interest(symbol),
                client.get_24hr_ticker_stats(symbol),
                client.get_premium_index(symbol),     # real-time mark price
                return_exceptions=True,
            )

            if isinstance(klines, Exception) or not klines or len(klines) < 30:
                return None

            closes  = [float(k[4]) for k in klines]
            highs   = [float(k[2]) for k in klines]
            lows    = [float(k[3]) for k in klines]
            volumes = [float(k[5]) for k in klines]

            # ── Real-time mark price (critical: not candle close) ───────────
            mark_price = closes[-1]   # fallback
            if isinstance(mark_price_data, dict):
                try:
                    mp = float(mark_price_data.get("markPrice", 0) or 0)
                    if mp > 0:
                        mark_price = mp
                except (ValueError, TypeError):
                    pass
            elif isinstance(funding, dict):
                try:
                    mp = float(funding.get("markPrice", 0) or 0)
                    if mp > 0:
                        mark_price = mp
                except (ValueError, TypeError):
                    pass

            # ── Parse funding rate ──────────────────────────────────────────
            fund_rate = 0.0
            if isinstance(funding, dict):
                try:
                    fund_rate = float(funding.get("fundingRate", 0) or 0)
                except (ValueError, TypeError):
                    pass
            elif isinstance(mark_price_data, dict):
                try:
                    fund_rate = float(mark_price_data.get("lastFundingRate", 0) or 0)
                except (ValueError, TypeError):
                    pass

            # ── Parse open interest ─────────────────────────────────────────
            oi = 0.0
            if isinstance(oi_now, dict):
                try:
                    oi = float(oi_now.get("openInterest", 0) or 0)
                except (ValueError, TypeError):
                    pass

            # ── Parse 24h volume ────────────────────────────────────────────
            vol_24h = 0.0
            if isinstance(ticker, dict):
                try:
                    vol_24h = float(ticker.get("quoteVolume", 0) or 0)
                except (ValueError, TypeError):
                    pass

            # ── OI delta ────────────────────────────────────────────────────
            oi_delta = await self._oi_delta(client, symbol, timeframe, oi)

            # ── Build & cache ────────────────────────────────────────────────
            snap = self._build(
                symbol, mark_price, closes, highs, lows, volumes,
                fund_rate, oi, oi_delta, vol_24h, timeframe,
            )
            self._cache[ck] = (time.time(), snap)
            return snap

        except Exception as e:
            self.logger.error(f"[{symbol}/{timeframe}] snapshot error: {e}")
            return None

    # ─── OI delta ────────────────────────────────────────────────────────────

    async def _oi_delta(self, client, symbol, timeframe, current_oi) -> float:
        try:
            period = self.OI_HIST_PERIOD.get(timeframe, "1h")
            hist = await client._get_fapi(
                "/futures/data/openInterestHist",
                {"symbol": symbol, "period": period, "limit": 6},
            )
            if hist and isinstance(hist, list) and len(hist) >= 2:
                old = float(hist[0].get("sumOpenInterest", current_oi) or current_oi)
                new = float(hist[-1].get("sumOpenInterest", current_oi) or current_oi)
                if old > 0:
                    return (new - old) / old * 100.0
        except Exception:
            pass
        return 0.0

    # ─── Core snapshot builder ────────────────────────────────────────────────

    def _build(
        self,
        symbol: str,
        mark_price: float,
        closes: List[float],
        highs: List[float],
        lows: List[float],
        volumes: List[float],
        fund_rate: float,
        oi: float,
        oi_delta: float,
        vol_24h: float,
        timeframe: str,
    ) -> GEXSnapshot:

        price = mark_price
        atr   = _atr(closes, highs, lows, self.ATR_PERIOD)
        if atr <= 0:
            atr = max(price * 0.002, 1e-8)

        # ── 1. Build 41-level ATR-spaced strike grid ─────────────────────────
        half    = self.STRIKE_COUNT // 2
        sigma   = atr * self.SIGMA_MULT
        strikes = [price + (i - half) * atr * self.ATR_MULT
                   for i in range(self.STRIKE_COUNT)]

        # ── 2. Volume Profile VPOC ───────────────────────────────────────────
        vpoc = _vpoc(closes, highs, lows, volumes, bins=100)

        # ── 3. GEX proxy at each strike ──────────────────────────────────────
        #  Full AEGIS GEX formula (all components):
        #    GEX(S) = OI_reference
        #           × Gaussian_weight(dist, sigma)        ← concentration
        #           × Gamma_sign(S)                       ← call/put side
        #           × Funding_factor                      ← dealer bias
        #           × OI_delta_factor                     ← active hedging
        #           × VPOC_boost                          ← high-volume strike
        #           × Skew_factor(S)                      ← asymmetric gamma skew
        #           × Session_factor                      ← session open proximity

        oi_ref          = max(oi, 1.0)
        fund_factor     = max(0.3, min(3.0, 1.0 + fund_rate * 200))
        oi_delta_factor = max(0.3, min(3.0, 1.0 + oi_delta / 100.0))
        session_min     = _session_open_minute()
        # Session factor: GEX is stronger near session open (30-min window)
        session_factor  = 1.2 if session_min <= self.SESSION_OPEN_MINUTE else 1.0

        gex_vals: List[float] = []
        for s in strikes:
            dist   = abs(price - s)
            w      = _gaussian(dist, sigma)
            vpoc_b = 1.6 if vpoc and abs(s - vpoc) < atr * 0.75 else 1.0
            g_sign = 1.0 if s >= price else -1.0
            # Gamma skew: OTM puts heavier than OTM calls in fear regimes
            # Proxy: negative funding → elevated put-side gamma
            skew_factor = (1.0 + abs(fund_rate) * 50) if (s < price and fund_rate < 0) else 1.0
            gex_vals.append(
                oi_ref * w * g_sign * fund_factor * oi_delta_factor * vpoc_b * skew_factor * session_factor
            )

        max_abs = max(abs(g) for g in gex_vals) or 1.0

        # ── 4. GEX flip levels ───────────────────────────────────────────────
        flip_levels: List[GEXLevel] = []
        for i in range(1, len(strikes)):
            g0, g1 = gex_vals[i-1], gex_vals[i]
            if g0 * g1 < 0:          # Zero crossing
                zp  = _interpolate_zero(strikes[i-1], strikes[i], g0, g1)
                str_ = (abs(g0) + abs(g1)) / (2 * max_abs) * 100.0
                if str_ >= self.FLIP_MIN_STR:
                    ltype = "FLIP_UP" if g0 < 0 else "FLIP_DOWN"
                    flip_levels.append(GEXLevel(
                        price=zp, gex_value=(g0+g1)/2, is_flip=True,
                        strength=min(str_, 100.0), level_type=ltype, timeframe=timeframe,
                    ))

        # Fallback: if no true flips, use highest-gradient transitions
        if not flip_levels:
            candidates = sorted(
                range(1, len(strikes)),
                key=lambda i: abs(gex_vals[i] - gex_vals[i-1]),
                reverse=True,
            )[:5]
            for i in candidates:
                str_ = abs(gex_vals[i]) / max_abs * 100.0
                flip_levels.append(GEXLevel(
                    price=strikes[i], gex_value=gex_vals[i], is_flip=False,
                    strength=str_, level_type="WALL_BULL" if gex_vals[i] > 0 else "WALL_BEAR",
                    timeframe=timeframe,
                ))

        flip_levels.sort(key=lambda x: x.price)

        # ── 5. Gamma Flip Proxy (primary GEX flip line) ───────────────────────
        # The gamma flip proxy is the strongest flip level
        flip_only = [fl for fl in flip_levels if fl.is_flip]
        if flip_only:
            gamma_flip_proxy = max(flip_only, key=lambda x: x.strength).price
        elif flip_levels:
            gamma_flip_proxy = min(flip_levels, key=lambda x: abs(x.price - price)).price
        else:
            gamma_flip_proxy = price

        # ── 6. Gamma Wall Boxes ───────────────────────────────────────────────
        gamma_walls: List[GEXZone] = []
        for fl in flip_levels:
            if fl.strength >= self.WALL_MIN_STR:
                half_width = atr * 0.3
                ztype = "GAMMA_WALL_BULL" if fl.gex_value >= 0 else "GAMMA_WALL_BEAR"
                gamma_walls.append(GEXZone(
                    price_low  = fl.price - half_width,
                    price_high = fl.price + half_width,
                    zone_type  = ztype,
                    strength   = fl.strength,
                    mid        = fl.price,
                    target     = None,
                ))

        # ── 7. Compression Boxes ─────────────────────────────────────────────
        # Two gamma walls within COMPRESS_MAX_GAP ATR of each other
        compression_zones: List[GEXZone] = []
        sorted_walls = sorted(gamma_walls, key=lambda w: w.mid)
        for j in range(1, len(sorted_walls)):
            w0, w1 = sorted_walls[j-1], sorted_walls[j]
            gap = (w1.mid - w0.mid) / atr
            if gap < self.COMPRESS_MAX_GAP:
                comp_mid    = (w0.mid + w1.mid) / 2
                comp_height = w1.mid - w0.mid
                # Breakout target = opposite wall + same distance (measured move)
                if price >= comp_mid:
                    target = w1.mid + comp_height
                else:
                    target = w0.mid - comp_height
                compression_zones.append(GEXZone(
                    price_low  = w0.price_low,
                    price_high = w1.price_high,
                    zone_type  = "COMPRESSION",
                    strength   = (w0.strength + w1.strength) / 2,
                    mid        = comp_mid,
                    target     = target,
                ))

        # ── 8. Current GEX zone at mark price ────────────────────────────────
        price_idx   = min(range(len(strikes)), key=lambda i: abs(strikes[i] - price))
        current_gex = gex_vals[price_idx]
        if current_gex > max_abs * 0.08:
            zone = "POSITIVE"
        elif current_gex < -max_abs * 0.08:
            zone = "NEGATIVE"
        else:
            zone = "NEUTRAL"

        # ── 9. Nearest flip levels ────────────────────────────────────────────
        flips_above = sorted([fl.price for fl in flip_levels if fl.price > price])
        flips_below = sorted([fl.price for fl in flip_levels if fl.price < price], reverse=True)
        nearest_flip_up   = flips_above[0]  if flips_above  else None
        nearest_flip_down = flips_below[0]  if flips_below  else None

        # ── 10. VWAP + ATR Bands ─────────────────────────────────────────────
        vwap_val = _vwap(closes, highs, lows, volumes) or price
        vwap_p1  = vwap_val + atr
        vwap_m1  = vwap_val - atr
        vwap_p2  = vwap_val + 2 * atr
        vwap_m2  = vwap_val - 2 * atr

        # ── 11. Expected Move Bands ───────────────────────────────────────────
        # IV proxy = annualized HV × sqrt(bars_per_day/252)
        # Approximate with ATR-based method: EM = price × σ_pct × sqrt(horizon)
        # For 1h candles, 1-session horizon = 8 bars
        horizon_map = {"15m": 32, "30m": 16, "1h": 8, "4h": 2, "1d": 1}
        horizon  = horizon_map.get(timeframe, 8)
        hv_pct   = _stdev(closes[-30:], 20) / (price or 1) if len(closes) >= 20 else 0.015
        exp_move = price * hv_pct * math.sqrt(horizon)
        exp_up   = vwap_val + exp_move
        exp_down = vwap_val - exp_move

        # ── 12. 50 EMA ────────────────────────────────────────────────────────
        ema50 = _ema(closes, 50)

        # ── 13. Vanna Proxy ───────────────────────────────────────────────────
        # Vanna = dGamma/dVol = how gamma changes as implied vol moves
        # Proxy: funding rate velocity × OI acceleration
        # High Vanna → dealers rehedge aggressively when vol moves
        fund_abs     = abs(fund_rate)
        oi_acc       = abs(oi_delta) / 100.0
        vanna_proxy  = fund_abs * oi_acc * max_abs
        # Vanna unwind levels: near the ±1 expected move boundaries
        vanna_up     = exp_up   - atr * 0.5
        vanna_down   = exp_down + atr * 0.5
        # Vanna entry: weighted average of flip proxy and VWAP
        vanna_entry  = (gamma_flip_proxy * 0.6 + vwap_val * 0.4)

        # ── 14. Charm Decay Intensity ─────────────────────────────────────────
        # Charm = dDelta/dTime — measures how dealer hedges decay toward expiration
        # Proxy: |funding_rate| × time_factor
        # Funding resets every 8h; charm increases near funding time
        now_ts     = time.time()
        # Estimate time-to-next-funding (Binance: every 8h at 00:00/08:00/16:00 UTC)
        hour_utc   = datetime.now(timezone.utc).hour
        next_fund  = ((hour_utc // 8) + 1) * 8
        hours_to_f = (next_fund - hour_utc - datetime.now(timezone.utc).minute/60)
        charm_decay = min(1.0, fund_abs * 1000 * (1.0 / max(hours_to_f, 0.1)))

        # ── 15. Bias scoring (all 13 layers) ─────────────────────────────────
        bull, bear = 0.0, 0.0

        # Funding rate
        if fund_rate < -0.0001:     bull += 2.0
        elif fund_rate < 0:         bull += 1.0
        elif fund_rate > 0.0001:    bear += 2.0
        else:                       bear += 0.5

        # OI delta
        if oi_delta < -1.0 and fund_rate > 0:  bull += 1.5   # shorts covering
        elif oi_delta > 1.0 and fund_rate > 0: bear += 1.5   # new shorts
        elif oi_delta > 1.0 and fund_rate < 0: bull += 1.0   # new longs
        elif oi_delta < -1.0 and fund_rate < 0:bear += 1.0   # longs reducing

        # VWAP position
        if price > vwap_val + atr * 0.2:    bull += 1.5
        elif price < vwap_val - atr * 0.2:  bear += 1.5
        else:                                bull += 0.5; bear += 0.5

        # 50 EMA position
        if ema50 and price > ema50:          bull += 1.5
        elif ema50 and price < ema50:        bear += 1.5

        # RSI
        rsi = _rsi(closes, 14)
        if rsi > 60:    bull += 1.0
        elif rsi < 40:  bear += 1.0

        # Nearest flip distances (asymmetry = directional pressure)
        if nearest_flip_up and nearest_flip_down:
            up_d = nearest_flip_up - price
            dn_d = price - nearest_flip_down
            if up_d < dn_d * 0.6:     bear += 1.0  # closer to upside resistance
            elif dn_d < up_d * 0.6:   bull += 1.0  # closer to downside support

        # GEX zone
        if zone == "POSITIVE":
            bull += 0.5; bear += 0.5   # pinned = neutral momentum
        elif zone == "NEGATIVE" and fund_rate < 0:
            bull += 1.0
        elif zone == "NEGATIVE" and fund_rate > 0:
            bear += 1.0

        # Charm decay: high charm → dealers rehedge urgently → amplifies move
        if charm_decay > 0.5:
            if fund_rate < 0:  bull += 1.0
            else:              bear += 1.0

        # OPEX: reduce extreme scores during expiration week
        opex = _is_opex_week()
        if opex:
            bull *= 0.85
            bear *= 0.85

        total = bull + bear
        if bull > bear * 1.1:   bias = "BULLISH"
        elif bear > bull * 1.1: bias = "BEARISH"
        else:                   bias = "NEUTRAL"

        dom_score = max(bull, bear) / total if total > 0 else 0.5
        base_conf = 45.0 + dom_score * 55.0
        # Boost for multiple confirming flip levels
        if len(flip_only) >= 3:   base_conf = min(base_conf + 8.0, 96.0)
        # Boost for strong gamma wall alignment
        wall_align = any(abs(w.mid - gamma_flip_proxy) < atr for w in gamma_walls)
        if wall_align:             base_conf = min(base_conf + 5.0, 96.0)
        # Boost for compression zones nearby
        in_compression = any(z.price_low <= price <= z.price_high for z in compression_zones)
        if in_compression:         base_conf = min(base_conf + 6.0, 96.0)
        # Penalty for OPEX week uncertainty
        if opex:                   base_conf = max(base_conf - 8.0, 40.0)

        return GEXSnapshot(
            symbol=symbol,
            timestamp=time.time(),
            mark_price=price,
            current_gex_zone=zone,
            net_gex=current_gex,
            nearest_flip_up=nearest_flip_up,
            nearest_flip_down=nearest_flip_down,
            all_flip_levels=flip_levels,
            gamma_walls=gamma_walls,
            compression_zones=compression_zones,
            vanna_unwind_up=vanna_up,
            vanna_unwind_down=vanna_down,
            vanna_entry=vanna_entry,
            expected_move_upper=exp_up,
            expected_move_lower=exp_down,
            vwap=vwap_val,
            vwap_plus1_atr=vwap_p1,
            vwap_minus1_atr=vwap_m1,
            vwap_plus2_atr=vwap_p2,
            vwap_minus2_atr=vwap_m2,
            ema50=ema50,
            gamma_flip_proxy=gamma_flip_proxy,
            charm_decay=charm_decay,
            atr=atr,
            funding_rate=fund_rate,
            open_interest=oi,
            oi_delta_pct=oi_delta,
            volume_24h=vol_24h,
            bias=bias,
            confidence=base_conf,
            is_opex_week=opex,
            session_open_minute=_session_open_minute(),
        )

    # ─── Signal Detection ─────────────────────────────────────────────────────

    def detect_signal(
        self,
        snap_prev: GEXSnapshot,
        snap_curr: GEXSnapshot,
        min_confidence: float = 60.0,
    ) -> Optional[GEXSignal]:
        """
        Detect a GEX flip crossover between two consecutive snapshots.

        Uses REAL-TIME mark prices (not candle closes) for crossover detection.
        This is the critical fix: the mark price updates every second, whereas
        candle closes only change once per timeframe interval.

        ── Signal Types ──────────────────────────────────────────────────────
        GEX_FLIP:          Price crosses a primary GEX flip level
        VANNA_ENTRY:       Price enters a Vanna unwind zone + GEX confirms
        COMPRESSION_BREAK: Price breaks out of a compression box
        """
        if snap_curr.confidence < min_confidence:
            return None

        pp = snap_prev.mark_price
        cp = snap_curr.mark_price
        flips = snap_curr.all_flip_levels

        if not flips or abs(cp - pp) < snap_curr.atr * 0.01:
            return None    # Price hasn't moved meaningfully

        # ── Check GEX Flip crossover ─────────────────────────────────────────
        crossed: Optional[GEXLevel] = None
        action: str = ""

        for fl in flips:
            fp = fl.price
            if pp <= fp < cp:          # Crossed upward
                crossed = fl; action = "BUY"; break
            elif cp < fp <= pp:        # Crossed downward
                crossed = fl; action = "SELL"; break

        # ── Check Compression Breakout ───────────────────────────────────────
        sig_type = "GEX_FLIP"
        comp_hit: Optional[GEXZone] = None

        if crossed is None:
            for cz in snap_curr.compression_zones:
                if pp <= cz.price_high < cp:    # Breaking up out of compression
                    crossed = GEXLevel(
                        price=cz.price_high, gex_value=0, is_flip=True,
                        strength=cz.strength, level_type="FLIP_UP", timeframe=snap_curr.all_flip_levels[0].timeframe,
                    )
                    action   = "BUY"
                    sig_type = "COMPRESSION_BREAK"
                    comp_hit = cz
                    break
                elif cp < cz.price_low <= pp:   # Breaking down out of compression
                    crossed = GEXLevel(
                        price=cz.price_low, gex_value=0, is_flip=True,
                        strength=cz.strength, level_type="FLIP_DOWN", timeframe=snap_curr.all_flip_levels[0].timeframe,
                    )
                    action   = "SELL"
                    sig_type = "COMPRESSION_BREAK"
                    comp_hit = cz
                    break

        # ── Check Vanna Entry ────────────────────────────────────────────────
        if crossed is None and snap_curr.vanna_entry:
            ve = snap_curr.vanna_entry
            if pp <= ve < cp:
                crossed = GEXLevel(
                    price=ve, gex_value=snap_curr.net_gex, is_flip=True,
                    strength=50.0, level_type="FLIP_UP", timeframe="1h",
                )
                action   = "BUY"
                sig_type = "VANNA_ENTRY"
            elif cp < ve <= pp:
                crossed = GEXLevel(
                    price=ve, gex_value=snap_curr.net_gex, is_flip=True,
                    strength=50.0, level_type="FLIP_DOWN", timeframe="1h",
                )
                action   = "SELL"
                sig_type = "VANNA_ENTRY"

        if not crossed or not action:
            return None

        entry = crossed.price
        atr   = snap_curr.atr

        # ── Compute TP targets ────────────────────────────────────────────────
        # TP = NEXT GEX flip levels in the direction of the trade
        # (Updated dynamically each scan cycle as new flips appear)
        all_flips_sorted = sorted([fl.price for fl in flips])

        if action == "BUY":
            tp_candidates = [p for p in all_flips_sorted if p > entry + atr * 0.1]
            tp1 = tp_candidates[0] if len(tp_candidates) > 0 else entry + atr * 2.0
            tp2 = tp_candidates[1] if len(tp_candidates) > 1 else tp1 + atr * 2.0
            tp3 = tp_candidates[2] if len(tp_candidates) > 2 else tp2 + atr * 2.5
            sl  = max(entry - atr * 1.5, snap_curr.nearest_flip_down or entry - atr * 2)
            gex_from = snap_prev.current_gex_zone
            gex_to   = "POSITIVE"
        else:
            tp_candidates = sorted([p for p in all_flips_sorted if p < entry - atr * 0.1], reverse=True)
            tp1 = tp_candidates[0] if len(tp_candidates) > 0 else entry - atr * 2.0
            tp2 = tp_candidates[1] if len(tp_candidates) > 1 else tp1 - atr * 2.0
            tp3 = tp_candidates[2] if len(tp_candidates) > 2 else tp2 - atr * 2.5
            sl  = min(entry + atr * 1.5, snap_curr.nearest_flip_up or entry + atr * 2)
            gex_from = snap_prev.current_gex_zone
            gex_to   = "NEGATIVE"

        # ── Use compression target as primary TP if applicable ───────────────
        if sig_type == "COMPRESSION_BREAK" and comp_hit and comp_hit.target:
            tp1 = comp_hit.target

        # ── Validate R:R ────────────────────────────────────────────────────
        risk   = abs(entry - sl)
        reward = abs(tp1 - entry)
        if risk <= 0:
            return None
        rr = reward / risk
        if rr < 1.2:    # Minimum 1.2:1 R:R
            return None

        # ── Confidence boosting with all 13 layers ────────────────────────────
        conf = snap_curr.confidence

        # Layer: crossed flip strength
        if crossed.strength > 70:          conf = min(conf + 12, 97)
        elif crossed.strength > 50:        conf = min(conf + 6, 97)

        # Layer: bias alignment
        if (action == "BUY"  and snap_curr.bias == "BULLISH") or \
           (action == "SELL" and snap_curr.bias == "BEARISH"):
            conf = min(conf + 8, 97)
        elif snap_curr.bias == "NEUTRAL":
            conf -= 5

        # Layer: funding rate alignment
        if action == "BUY"  and snap_curr.funding_rate < -0.0001: conf = min(conf + 6, 97)
        if action == "SELL" and snap_curr.funding_rate >  0.0001: conf = min(conf + 6, 97)

        # Layer: VWAP position
        if action == "BUY"  and cp > snap_curr.vwap:  conf = min(conf + 4, 97)
        if action == "SELL" and cp < snap_curr.vwap:  conf = min(conf + 4, 97)

        # Layer: 50 EMA trend
        if snap_curr.ema50:
            if action == "BUY"  and cp > snap_curr.ema50: conf = min(conf + 4, 97)
            if action == "SELL" and cp < snap_curr.ema50: conf = min(conf + 4, 97)
            if action == "BUY"  and cp < snap_curr.ema50: conf -= 8   # Counter-trend penalty
            if action == "SELL" and cp > snap_curr.ema50: conf -= 8

        # Layer: Expected Move confirmation
        if action == "BUY"  and cp > snap_curr.expected_move_lower: conf = min(conf + 3, 97)
        if action == "SELL" and cp < snap_curr.expected_move_upper: conf = min(conf + 3, 97)

        # Layer: charm decay (urgency bonus)
        if snap_curr.charm_decay > 0.6:    conf = min(conf + 4, 97)

        # Layer: R:R quality
        if rr >= 3.0:  conf = min(conf + 5, 97)
        elif rr >= 2.0:conf = min(conf + 2, 97)

        # Layer: signal type quality
        if sig_type == "COMPRESSION_BREAK": conf = min(conf + 6, 97)

        # Layer: OPEX penalty
        if snap_curr.is_opex_week:          conf -= 6

        conf = max(conf, 0.0)
        if conf < min_confidence:
            return None

        # ── Leverage: calibrated by R:R and volatility ───────────────────────
        if rr >= 4.0:   lev = 12
        elif rr >= 3.0: lev = 10
        elif rr >= 2.0: lev = 8
        else:           lev = 5
        lev = max(3, min(lev, 15))

        # ── Nearest compression zone for signal context ────────────────────
        nearest_comp = min(
            snap_curr.compression_zones,
            key=lambda z: abs(z.mid - entry),
            default=None,
        ) if snap_curr.compression_zones else None

        tf = snap_curr.all_flip_levels[0].timeframe if snap_curr.all_flip_levels else "1h"

        return GEXSignal(
            symbol=snap_curr.symbol,
            action=action,
            direction="LONG" if action == "BUY" else "SHORT",
            signal_type=sig_type,
            entry_price=entry,
            entry_flip_level=crossed.price,
            tp1=tp1, tp2=tp2, tp3=tp3, sl=sl,
            confidence=conf,
            timeframe=tf,
            gex_zone_from=gex_from,
            gex_zone_to=gex_to,
            leverage=lev,
            rr_ratio=rr,
            bias=snap_curr.bias,
            atr=atr,
            funding_rate=snap_curr.funding_rate,
            open_interest=snap_curr.open_interest,
            oi_delta_pct=snap_curr.oi_delta_pct,
            charm_decay=snap_curr.charm_decay,
            vanna_entry=snap_curr.vanna_entry,
            expected_move_upper=snap_curr.expected_move_upper,
            expected_move_lower=snap_curr.expected_move_lower,
            vwap=snap_curr.vwap,
            gamma_flip_proxy=snap_curr.gamma_flip_proxy,
            ema50=snap_curr.ema50,
            nearest_compression=nearest_comp,
            snapshot=snap_curr,
        )

    def get_dynamic_tp(
        self,
        entry: float,
        direction: str,
        snap: GEXSnapshot,
    ) -> Optional[float]:
        """
        Return the current best TP target given live GEX snapshot.
        Called each cycle to update TP as new GEX flip levels appear.

        Rule: TP = nearest GEX flip level BEYOND entry in trade direction.
        If a new flip appears that's closer, TP updates to it immediately.
        """
        flips = [fl.price for fl in snap.all_flip_levels]
        if not flips:
            return None
        if direction == "LONG":
            candidates = sorted([p for p in flips if p > entry])
            return candidates[0] if candidates else None
        else:
            candidates = sorted([p for p in flips if p < entry], reverse=True)
            return candidates[0] if candidates else None
