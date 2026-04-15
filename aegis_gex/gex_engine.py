#!/usr/bin/env python3
"""
AEGIS GEX v1.0 — Dealer Flow Engine  (v3 — Full Dashboard Implementation)
===========================================================================
Based on: AEGIS GEX DEALER FLOW ENGINE (TradingView: T1zYSBd7)

Dashboard Table (exact match to TradingView indicator):
  Regime        — FLIP ZONE | POSITIVE | NEGATIVE | NEUTRAL
  DGRP Score    — 0-100 composite Dealer GEX Regime Proxy score
  Candle        — Flip Zone | Compression | Vanna Active | Normal
  RV Ratio      — ATR(14)/ATR(28) — current vs historical realized vol
  IV Proxy Z    — Z-score of ATR% vs 50-period mean (normalized IV proxy)
  Compression   — Free | Compressed | Extreme
  Vanna         — Stable | Unstable | Active
  Charm Decay   — ACTIVE | Moderate | Low
  Delta Bias    — Net Bullish | Net Bearish | Neutral
  Exp Move      — ± value in price units (±1 std dev move)
  Dealer Flow   — Net dealer hedging flow in $M (+ = long, - = short)
  GEX Regime    — LONG GAMMA | SHORT GAMMA
  GEX Flip      — $price ± band_width

Chart Levels:
  GEX Flip Proxy Line  — primary zero-crossing entry level
  Call Wall            — strongest gamma wall ABOVE price
  Put Wall             — strongest gamma wall BELOW price
  VOL TRIGGER UP       — upper volatility expansion trigger
  VOL TRIGGER DN       — lower volatility expansion trigger
  VWAP ±1/±2 ATR bands
  Expected Move Bands
  50 EMA
  Compression Boxes
  Vanna Unwind Zones

Timeframe: 5m primary (per user specification), 15m confirmation
"""

from __future__ import annotations

import asyncio
import calendar as _cal
import logging
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GEXLevel:
    """Single Gamma Exposure level — flip, wall, or strike center."""
    price: float
    gex_value: float
    is_flip: bool
    strength: float         # 0–100
    level_type: str         # "FLIP_UP"|"FLIP_DOWN"|"WALL_BULL"|"WALL_BEAR"
    timeframe: str


@dataclass
class GEXZone:
    """Price zone — Gamma Wall Box, Compression Box, or Vanna Zone."""
    price_low: float
    price_high: float
    zone_type: str          # "GAMMA_WALL_BULL"|"GAMMA_WALL_BEAR"|"COMPRESSION"|"VANNA_UNWIND"
    strength: float
    mid: float
    target: Optional[float]


@dataclass
class GEXSnapshot:
    """Complete AEGIS GEX picture — all dashboard fields + chart levels."""
    symbol: str
    timestamp: float
    mark_price: float

    # ── Dashboard Table fields (exact match to TradingView AEGIS GEX v1.0) ──
    regime: str                  # "FLIP ZONE" | "POSITIVE" | "NEGATIVE" | "NEUTRAL"
    dgrp_score: float            # 0–100 DGRP score
    candle_state: str            # "Flip Zone" | "Compression" | "Vanna Active" | "Normal"
    rv_ratio: float              # ATR(14) / ATR(28) — current/historical vol
    iv_proxy_z: float            # Z-score of ATR% from mean
    compression_state: str       # "Free" | "Compressed" | "Extreme"
    vanna_state: str             # "Stable" | "Unstable" | "Active"
    charm_state: str             # "ACTIVE" | "Moderate" | "Low"
    delta_bias: str              # "Net Bullish" | "Net Bearish" | "Neutral"
    exp_move: float              # Expected move in price units (±)
    dealer_flow_m: float         # Dealer flow in $M (+ = long, - = short)
    gex_regime: str              # "LONG GAMMA" | "SHORT GAMMA"
    gex_flip: float              # Primary GEX flip price
    gex_flip_band: float         # ± band width around the flip
    signal_state: str            # "Signal" | "No Signal"

    # ── GEX core ──────────────────────────────────────────────────────────────
    current_gex_zone: str        # "POSITIVE" | "NEGATIVE" | "NEUTRAL"
    net_gex: float
    nearest_flip_up: Optional[float]
    nearest_flip_down: Optional[float]
    all_flip_levels: List[GEXLevel]

    # ── Chart zones ───────────────────────────────────────────────────────────
    gamma_walls: List[GEXZone]
    compression_zones: List[GEXZone]
    call_wall: Optional[float]      # Strongest gamma wall ABOVE price
    put_wall: Optional[float]       # Strongest gamma wall BELOW price
    vol_trigger_up: float           # Upper volatility expansion trigger
    vol_trigger_dn: float           # Lower volatility expansion trigger

    # ── Greek layers ──────────────────────────────────────────────────────────
    vanna_unwind_up: Optional[float]
    vanna_unwind_down: Optional[float]
    vanna_entry: Optional[float]
    charm_decay: float              # 0–1 raw intensity

    # ── Indicator levels ──────────────────────────────────────────────────────
    expected_move_upper: float
    expected_move_lower: float
    vwap: float
    vwap_plus1_atr: float
    vwap_minus1_atr: float
    vwap_plus2_atr: float
    vwap_minus2_atr: float
    ema50: Optional[float]
    gamma_flip_proxy: float

    # ── Market data ───────────────────────────────────────────────────────────
    atr: float
    atr_slow: float                 # ATR(28) for RV Ratio
    funding_rate: float
    open_interest: float
    oi_delta_pct: float
    volume_24h: float
    bias: str                       # "BULLISH" | "BEARISH" | "NEUTRAL"
    confidence: float               # 0–100
    is_opex_week: bool
    session_open_minute: int


@dataclass
class GEXSignal:
    """Trading signal from the AEGIS GEX engine."""
    symbol: str
    action: str             # "BUY" | "SELL"
    direction: str          # "LONG" | "SHORT"
    signal_type: str        # "GEX_FLIP" | "VANNA_ENTRY" | "COMPRESSION_BREAK"
    entry_price: float
    entry_flip_level: float
    tp1: float
    tp2: float
    tp3: float
    sl: float
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
# Pure-Python Indicator Math (zero external deps)
# ─────────────────────────────────────────────────────────────────────────────

def _ema(data: List[float], period: int) -> Optional[float]:
    if len(data) < period:
        return None
    k = 2.0 / (period + 1)
    e = sum(data[:period]) / period
    for v in data[period:]:
        e = v * k + e * (1 - k)
    return e

def _atr(closes: List[float], highs: List[float], lows: List[float],
         period: int = 14) -> float:
    n = min(len(closes), len(highs), len(lows))
    if n < 2:
        return max(abs(closes[-1] * 0.005), 1e-8) if closes else 1.0
    trs = [
        max(highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i]  - closes[i-1]))
        for i in range(1, n)
    ]
    if not trs:
        return 1.0
    if len(trs) < period:
        return sum(trs) / len(trs)
    a = sum(trs[:period]) / period
    for tr in trs[period:]:
        a = (a * (period - 1) + tr) / period
    return a

def _vwap(closes: List[float], highs: List[float],
          lows: List[float], volumes: List[float]) -> Optional[float]:
    n = min(len(closes), len(highs), len(lows), len(volumes))
    if n == 0:
        return None
    tv = sum((highs[i] + lows[i] + closes[i]) / 3 * volumes[i] for i in range(n))
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
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)

def _stdev(data: List[float], period: int) -> float:
    if len(data) < period:
        return 0.0
    w = data[-period:]
    mu = sum(w) / period
    v  = sum((x - mu) ** 2 for x in w) / period
    return math.sqrt(v) if v > 0 else 0.0

def _sma(data: List[float], period: int) -> Optional[float]:
    if len(data) < period:
        return None
    return sum(data[-period:]) / period

def _gaussian(distance: float, sigma: float) -> float:
    if sigma <= 0:
        return 0.0
    return math.exp(-0.5 * (distance / sigma) ** 2)

def _vpoc(closes: List[float], highs: List[float],
          lows: List[float], volumes: List[float],
          bins: int = 100) -> Optional[float]:
    n = min(len(closes), len(highs), len(lows), len(volumes))
    if n < 10:
        return None
    lo, hi = min(lows[-n:]), max(highs[-n:])
    if hi <= lo:
        return None
    bsz = (hi - lo) / bins
    vb  = [0.0] * bins
    for i in range(n):
        mid = (highs[i] + lows[i] + closes[i]) / 3.0
        idx = min(int((mid - lo) / bsz), bins - 1)
        vb[idx] += volumes[i]
    pk = vb.index(max(vb))
    return lo + (pk + 0.5) * bsz

def _is_opex_week() -> bool:
    """True if within 3 calendar days of the 3rd Friday (standard OPEX)."""
    now = datetime.now(timezone.utc)
    mc  = _cal.monthcalendar(now.year, now.month)
    frs = [week[4] for week in mc if week[4] != 0]
    if len(frs) < 3:
        return False
    opex = now.date().replace(day=frs[2])
    return abs((now.date() - opex).days) <= 3

def _session_open_minute() -> int:
    """Minutes since most recent major session open (00:00 / 08:00 / 16:00 UTC)."""
    now = datetime.now(timezone.utc)
    m   = now.hour * 60 + now.minute
    return min((m - o) % 1440 for o in [0, 480, 960])

def _interpolate_zero(x1: float, x2: float, y1: float, y2: float) -> float:
    if y1 == y2:
        return (x1 + x2) / 2
    return x1 + (x2 - x1) * (-y1 / (y2 - y1))


# ─────────────────────────────────────────────────────────────────────────────
# AEGIS GEX Engine v3
# ─────────────────────────────────────────────────────────────────────────────

class AEGISGEXEngine:
    """
    AEGIS GEX Dealer Flow Engine v1.0 — Complete Dashboard Implementation

    Primary TF: 5m (per user specification, configurable via GEX_PRIMARY_TF)
    Confirmation TF: 15m (configurable via GEX_CONFIRM_TF)
    """

    # Strike grid parameters
    STRIKE_COUNT      = 41          # 41 strikes = ±20 levels @ 0.75 ATR each
    ATR_PERIOD        = 14
    ATR_SLOW_PERIOD   = 28          # For RV Ratio calculation
    ATR_MULT          = 0.75        # Strike spacing
    SIGMA_MULT        = 4.0         # Gaussian distribution width
    FLIP_MIN_STR      = 10.0
    WALL_MIN_STR      = 18.0
    COMPRESS_MAX_GAP  = 2.0         # ATR gap for compression detection

    SESSION_OPEN_MIN  = int(os.getenv("GEX_SESSION_OPEN_MINUTE", "30"))

    LOOKBACK = {
        "1m": 500, "3m": 500, "5m": 500, "15m": 400,
        "30m": 300, "1h": 200, "4h": 200, "1d": 100,
    }
    OI_HIST_PERIOD = {
        "1m": "5m", "3m": "5m", "5m": "5m", "15m": "15m",
        "30m": "30m", "1h": "1h", "4h": "4h", "1d": "1d",
    }
    # Expected move horizon (bars per trading session)
    HORIZON = {
        "1m": 480, "3m": 160, "5m": 96, "15m": 32,
        "30m": 16, "1h": 8, "4h": 2, "1d": 1,
    }

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.GEXEngine")
        self._cache: Dict[str, Tuple[float, GEXSnapshot]] = {}
        self._cache_ttl = 25.0   # 25s for 5m TF (under scan interval)

    # ─── Public API ──────────────────────────────────────────────────────────

    async def compute_gex_snapshot(
        self,
        client,
        symbol: str,
        timeframe: str = "5m",
    ) -> Optional[GEXSnapshot]:
        """Compute full AEGIS GEX snapshot. Uses real-time mark price."""
        ck = f"{symbol}_{timeframe}"
        hit = self._cache.get(ck)
        if hit:
            ts, snap = hit
            if time.time() - ts < self._cache_ttl:
                return snap

        try:
            limit = self.LOOKBACK.get(timeframe, 500)

            klines, funding, oi_now, ticker, mark_data = await asyncio.gather(
                client.get_klines(symbol, timeframe, limit),
                client.get_funding_rate(symbol),
                client.get_open_interest(symbol),
                client.get_24hr_ticker_stats(symbol),
                client.get_premium_index(symbol),
                return_exceptions=True,
            )

            if isinstance(klines, Exception) or not klines or len(klines) < 50:
                return None

            closes  = [float(k[4]) for k in klines]
            highs   = [float(k[2]) for k in klines]
            lows    = [float(k[3]) for k in klines]
            volumes = [float(k[5]) for k in klines]

            # ── Real-time mark price ─────────────────────────────────────────
            mark_price = closes[-1]
            for src in (mark_data, funding):
                if isinstance(src, dict):
                    try:
                        mp = float(src.get("markPrice", 0) or 0)
                        if mp > 0:
                            mark_price = mp
                            break
                    except (ValueError, TypeError):
                        pass

            # ── Funding rate ─────────────────────────────────────────────────
            fund_rate = 0.0
            for src in (funding, mark_data):
                if isinstance(src, dict):
                    for key in ("fundingRate", "lastFundingRate"):
                        try:
                            v = float(src.get(key, 0) or 0)
                            if v != 0:
                                fund_rate = v
                                break
                        except (ValueError, TypeError):
                            pass
                    if fund_rate != 0:
                        break

            # ── OI ───────────────────────────────────────────────────────────
            oi = 0.0
            if isinstance(oi_now, dict):
                try:
                    oi = float(oi_now.get("openInterest", 0) or 0)
                except (ValueError, TypeError):
                    pass

            # ── 24h volume ───────────────────────────────────────────────────
            vol_24h = 0.0
            if isinstance(ticker, dict):
                try:
                    vol_24h = float(ticker.get("quoteVolume", 0) or 0)
                except (ValueError, TypeError):
                    pass

            # ── OI delta ────────────────────────────────────────────────────
            oi_delta = await self._oi_delta(client, symbol, timeframe, oi)

            snap = self._build(
                symbol, mark_price, closes, highs, lows, volumes,
                fund_rate, oi, oi_delta, vol_24h, timeframe,
            )
            self._cache[ck] = (time.time(), snap)
            return snap

        except Exception as e:
            self.logger.error(f"[{symbol}/{timeframe}] snapshot: {e}")
            return None

    async def _oi_delta(self, client, symbol, tf, cur_oi) -> float:
        try:
            period = self.OI_HIST_PERIOD.get(tf, "5m")
            hist = await client._get_fapi(
                "/futures/data/openInterestHist",
                {"symbol": symbol, "period": period, "limit": 8},
            )
            if hist and isinstance(hist, list) and len(hist) >= 2:
                old = float(hist[0].get("sumOpenInterest", cur_oi) or cur_oi)
                new = float(hist[-1].get("sumOpenInterest", cur_oi) or cur_oi)
                if old > 0:
                    return (new - old) / old * 100.0
        except Exception:
            pass
        return 0.0

    # ─── Core Snapshot Builder ────────────────────────────────────────────────

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
        n     = len(closes)

        # ── ATR (fast + slow for RV Ratio) ────────────────────────────────────
        atr14 = _atr(closes, highs, lows, self.ATR_PERIOD)
        atr28 = _atr(closes, highs, lows, self.ATR_SLOW_PERIOD)
        if atr14 <= 0: atr14 = max(price * 0.002, 1e-8)
        if atr28 <= 0: atr28 = atr14

        # ── RV Ratio: ATR(14) / ATR(28) ───────────────────────────────────────
        rv_ratio = atr14 / atr28 if atr28 > 0 else 1.0

        # ── IV Proxy Z-score ──────────────────────────────────────────────────
        # atr_pct series over last 50 bars, then z-score the current value
        atr_pct_series = []
        for i in range(max(15, n - 50), n):
            sub_c = closes[max(0, i-15):i+1]
            sub_h = highs [max(0, i-15):i+1]
            sub_l = lows  [max(0, i-15):i+1]
            if len(sub_c) >= 2 and closes[i] > 0:
                a = _atr(sub_c, sub_h, sub_l, min(14, len(sub_c)-1))
                atr_pct_series.append(a / closes[i])

        iv_proxy_z = 0.0
        if len(atr_pct_series) >= 10:
            cur_iv = atr14 / price if price > 0 else 0
            mu  = sum(atr_pct_series) / len(atr_pct_series)
            sd  = _stdev(atr_pct_series, min(20, len(atr_pct_series)))
            iv_proxy_z = (cur_iv - mu) / sd if sd > 0 else 0.0
            iv_proxy_z = max(-3.0, min(3.0, iv_proxy_z))

        # ── VPOC ──────────────────────────────────────────────────────────────
        vpoc = _vpoc(closes, highs, lows, volumes, bins=100)

        # ── Session / Funding factors ─────────────────────────────────────────
        session_min    = _session_open_minute()
        session_factor = 1.25 if session_min <= self.SESSION_OPEN_MIN else 1.0
        fund_factor    = max(0.25, min(4.0, 1.0 + fund_rate * 300))
        oi_delta_f     = max(0.25, min(4.0, 1.0 + oi_delta / 100.0))

        # ── Strike grid + GEX proxy ───────────────────────────────────────────
        half    = self.STRIKE_COUNT // 2
        sigma   = atr14 * self.SIGMA_MULT
        strikes = [price + (i - half) * atr14 * self.ATR_MULT
                   for i in range(self.STRIKE_COUNT)]

        oi_ref = max(oi, 1.0)
        gex_vals: List[float] = []
        for s in strikes:
            dist    = abs(price - s)
            w       = _gaussian(dist, sigma)
            vpoc_b  = 1.7 if vpoc and abs(s - vpoc) < atr14 * 0.8 else 1.0
            g_sign  = 1.0 if s >= price else -1.0
            # Fear-regime skew: elevated put-side gamma when funding negative
            skew    = (1.0 + abs(fund_rate) * 80) if (s < price and fund_rate < -0.0001) else 1.0
            # Vol expansion: high IV proxy Z → stronger gamma
            vol_amp = 1.0 + max(0.0, iv_proxy_z * 0.1)
            gex_vals.append(
                oi_ref * w * g_sign
                * fund_factor * oi_delta_f
                * vpoc_b * skew * session_factor * vol_amp
            )

        max_abs = max(abs(g) for g in gex_vals) or 1.0

        # ── GEX flip levels ───────────────────────────────────────────────────
        flip_levels: List[GEXLevel] = []
        for i in range(1, len(strikes)):
            g0, g1 = gex_vals[i-1], gex_vals[i]
            if g0 * g1 < 0:
                zp   = _interpolate_zero(strikes[i-1], strikes[i], g0, g1)
                str_ = (abs(g0) + abs(g1)) / (2 * max_abs) * 100.0
                if str_ >= self.FLIP_MIN_STR:
                    lt = "FLIP_UP" if g0 < 0 else "FLIP_DOWN"
                    flip_levels.append(GEXLevel(
                        price=zp, gex_value=(g0+g1)/2, is_flip=True,
                        strength=min(str_, 100.0), level_type=lt, timeframe=timeframe,
                    ))

        # Fallback: gradient-based pseudo-flips if no zero crossings
        if not flip_levels:
            cands = sorted(range(1, len(strikes)),
                           key=lambda i: abs(gex_vals[i] - gex_vals[i-1]),
                           reverse=True)[:5]
            for i in cands:
                str_ = abs(gex_vals[i]) / max_abs * 100.0
                flip_levels.append(GEXLevel(
                    price=strikes[i], gex_value=gex_vals[i], is_flip=False,
                    strength=str_, timeframe=timeframe,
                    level_type="WALL_BULL" if gex_vals[i] > 0 else "WALL_BEAR",
                ))

        flip_levels.sort(key=lambda x: x.price)

        # ── Primary GEX Flip Proxy (strongest true flip) ──────────────────────
        true_flips = [fl for fl in flip_levels if fl.is_flip]
        if true_flips:
            gfp = max(true_flips, key=lambda x: x.strength).price
        elif flip_levels:
            gfp = min(flip_levels, key=lambda x: abs(x.price - price)).price
        else:
            gfp = price

        # GEX flip band = half the average gap between flip levels (or ATR * 0.3)
        if len(flip_levels) >= 2:
            gaps = [flip_levels[i+1].price - flip_levels[i].price
                    for i in range(len(flip_levels)-1)]
            gfp_band = min(sum(gaps)/len(gaps)/2, atr14 * 0.5)
        else:
            gfp_band = atr14 * 0.3

        # ── Gamma Wall Boxes ──────────────────────────────────────────────────
        gamma_walls: List[GEXZone] = []
        for fl in flip_levels:
            if fl.strength >= self.WALL_MIN_STR:
                hw  = atr14 * 0.35
                zt  = "GAMMA_WALL_BULL" if fl.gex_value >= 0 else "GAMMA_WALL_BEAR"
                gamma_walls.append(GEXZone(
                    price_low=fl.price - hw,
                    price_high=fl.price + hw,
                    zone_type=zt,
                    strength=fl.strength,
                    mid=fl.price,
                    target=None,
                ))

        # ── Call Wall / Put Wall ──────────────────────────────────────────────
        # Call Wall = strongest BULL gamma wall ABOVE current price
        walls_above = [w for w in gamma_walls if w.mid > price]
        walls_below = [w for w in gamma_walls if w.mid < price]
        call_wall = max(walls_above, key=lambda w: w.strength).mid if walls_above else None
        put_wall  = max(walls_below, key=lambda w: w.strength).mid if walls_below else None

        # ── Compression Boxes ─────────────────────────────────────────────────
        compression_zones: List[GEXZone] = []
        sorted_walls = sorted(gamma_walls, key=lambda w: w.mid)
        for j in range(1, len(sorted_walls)):
            w0, w1 = sorted_walls[j-1], sorted_walls[j]
            gap = (w1.mid - w0.mid) / atr14
            if gap < self.COMPRESS_MAX_GAP:
                comp_mid = (w0.mid + w1.mid) / 2
                comp_h   = w1.mid - w0.mid
                tgt      = (w1.mid + comp_h) if price >= comp_mid else (w0.mid - comp_h)
                compression_zones.append(GEXZone(
                    price_low=w0.price_low,
                    price_high=w1.price_high,
                    zone_type="COMPRESSION",
                    strength=(w0.strength + w1.strength) / 2,
                    mid=comp_mid,
                    target=tgt,
                ))

        # ── GEX zone at mark price ─────────────────────────────────────────────
        pi  = min(range(len(strikes)), key=lambda i: abs(strikes[i] - price))
        cgx = gex_vals[pi]
        if cgx > max_abs * 0.08:   zone = "POSITIVE"
        elif cgx < -max_abs * 0.08: zone = "NEGATIVE"
        else:                       zone = "NEUTRAL"

        # ── Nearest flips ─────────────────────────────────────────────────────
        fa = sorted([fl.price for fl in flip_levels if fl.price > price])
        fb = sorted([fl.price for fl in flip_levels if fl.price < price], reverse=True)
        nf_up = fa[0] if fa else None
        nf_dn = fb[0] if fb else None

        # ── VWAP + ATR bands ──────────────────────────────────────────────────
        vwap_val = _vwap(closes, highs, lows, volumes) or price
        vwap_p1  = vwap_val + atr14
        vwap_m1  = vwap_val - atr14
        vwap_p2  = vwap_val + 2 * atr14
        vwap_m2  = vwap_val - 2 * atr14

        # ── Expected Move ─────────────────────────────────────────────────────
        horizon  = self.HORIZON.get(timeframe, 96)
        # Use stdev-based vol for more accuracy
        if n >= 20:
            ret_series = [abs(closes[i] - closes[i-1]) / closes[i-1]
                          for i in range(max(1, n-30), n) if closes[i-1] > 0]
            hv_pct = sum(ret_series) / len(ret_series) if ret_series else atr14 / price
        else:
            hv_pct = atr14 / price if price > 0 else 0.01
        exp_move = price * hv_pct * math.sqrt(horizon)
        exp_up   = vwap_val + exp_move
        exp_dn   = vwap_val - exp_move

        # ── VOL TRIGGERS ─────────────────────────────────────────────────────
        # VOL TRIGGER UP = higher of (Call Wall, VWAP+2ATR, GFP+1.5×exp_move)
        vol_up_candidates = [vwap_p2, gfp + exp_move * 1.5]
        if call_wall:
            vol_up_candidates.append(call_wall + atr14)
        vol_trigger_up = max(vol_up_candidates)

        # VOL TRIGGER DN = lower of (Put Wall, VWAP-2ATR, GFP-1.5×exp_move)
        vol_dn_candidates = [vwap_m2, gfp - exp_move * 1.5]
        if put_wall:
            vol_dn_candidates.append(put_wall - atr14)
        vol_trigger_dn = min(vol_dn_candidates)

        # ── 50 EMA ────────────────────────────────────────────────────────────
        ema50 = _ema(closes, min(50, n - 1)) if n >= 10 else None

        # ── Vanna proxy ───────────────────────────────────────────────────────
        fund_abs   = abs(fund_rate)
        oi_acc     = abs(oi_delta) / 100.0
        vanna_raw  = fund_abs * oi_acc
        vanna_norm = min(1.0, vanna_raw * 5000)   # normalize 0–1
        vanna_up   = exp_up  - atr14 * 0.4
        vanna_dn   = exp_dn  + atr14 * 0.4
        vanna_line = gfp * 0.55 + vwap_val * 0.45

        if   vanna_norm > 0.6:  vanna_state = "Active"
        elif vanna_norm > 0.3:  vanna_state = "Unstable"
        else:                   vanna_state = "Stable"

        # ── Charm Decay ───────────────────────────────────────────────────────
        now_utc    = datetime.now(timezone.utc)
        h_utc      = now_utc.hour + now_utc.minute / 60
        next_fund  = ((int(h_utc) // 8) + 1) * 8
        hrs_to_f   = max(next_fund - h_utc, 0.1)
        charm_raw  = min(1.0, fund_abs * 1200 * (1.0 / hrs_to_f))

        if   charm_raw > 0.5:  charm_state = "ACTIVE"
        elif charm_raw > 0.2:  charm_state = "Moderate"
        else:                  charm_state = "Low"

        # ── Dealer Flow in $M ─────────────────────────────────────────────────
        # Estimated net dealer hedging flow: fund_rate × OI × price → USD
        # Positive = dealers net long (bullish hedging flow)
        # Negative = dealers net short (bearish hedging flow)
        dealer_flow_usd = fund_rate * oi * price
        dealer_flow_m   = dealer_flow_usd / 1_000_000  # In $M

        # ── Delta Bias ────────────────────────────────────────────────────────
        # Net directional bias from all dealer Greek signals
        delta_bull = 0.0
        delta_bear = 0.0
        if fund_rate < -0.0001:  delta_bull += 2.0
        elif fund_rate > 0.0001: delta_bear += 2.0
        if oi_delta > 1.0 and fund_rate < 0:  delta_bull += 1.5
        if oi_delta > 1.0 and fund_rate > 0:  delta_bear += 1.5
        if oi_delta < -1.0 and fund_rate > 0: delta_bull += 1.0
        if price > vwap_val:                   delta_bull += 1.0
        else:                                  delta_bear += 1.0
        if ema50 and price > ema50:            delta_bull += 1.0
        elif ema50 and price < ema50:          delta_bear += 1.0

        if   delta_bull > delta_bear * 1.2:  delta_bias = "Net Bullish"
        elif delta_bear > delta_bull * 1.2:  delta_bias = "Net Bearish"
        else:                                 delta_bias = "Neutral"

        # ── GEX Regime: LONG GAMMA / SHORT GAMMA ─────────────────────────────
        gex_regime = "LONG GAMMA" if zone == "POSITIVE" else (
                     "SHORT GAMMA" if zone == "NEGATIVE" else "FLIP ZONE")

        # ── Regime: FLIP ZONE / POSITIVE / NEGATIVE / NEUTRAL ────────────────
        dist_to_flip = abs(price - gfp)
        if dist_to_flip < atr14 * 1.2:
            regime = "FLIP ZONE"
        elif zone == "POSITIVE":
            regime = "POSITIVE"
        elif zone == "NEGATIVE":
            regime = "NEGATIVE"
        else:
            regime = "NEUTRAL"

        # ── Compression state ─────────────────────────────────────────────────
        in_comp = any(z.price_low <= price <= z.price_high for z in compression_zones)
        if in_comp and len(compression_zones) > 1:
            comp_state = "Extreme"
        elif in_comp:
            comp_state = "Compressed"
        else:
            comp_state = "Free"

        # ── Candle state ──────────────────────────────────────────────────────
        if regime == "FLIP ZONE":
            candle_state = "Flip Zone"
        elif comp_state in ("Compressed", "Extreme"):
            candle_state = "Compression"
        elif vanna_state == "Active":
            candle_state = "Vanna Active"
        else:
            candle_state = "Normal"

        # ── DGRP Score (0-100): Dealer GEX Regime Proxy ───────────────────────
        # Composite of: flip proximity, GEX strength, RV ratio, funding intensity,
        # OI delta, vanna, charm, delta alignment, vol trigger proximity
        score = 0.0
        # 1. Flip proximity (0–20): higher when price closer to GEX flip
        flip_dist_norm = max(0.0, 1.0 - dist_to_flip / (atr14 * 3))
        score += flip_dist_norm * 20

        # 2. GEX strength at flip (0–15): stronger flip = higher DGRP
        if true_flips:
            best_str = max(fl.strength for fl in true_flips)
            score += (best_str / 100.0) * 15

        # 3. RV Ratio (0–15): extreme RV (high or low) = higher DGRP
        rv_dev = abs(rv_ratio - 1.0)
        score += min(rv_dev * 30, 15)

        # 4. Funding intensity (0–15)
        score += min(fund_abs * 30000, 15)

        # 5. OI delta (0–10)
        score += min(abs(oi_delta) * 2, 10)

        # 6. Vanna activation (0–10)
        score += vanna_norm * 10

        # 7. Charm decay (0–10)
        score += charm_raw * 10

        # 8. Vol trigger proximity (0–5): near vol trigger = higher
        dist_vol_up = abs(price - vol_trigger_up) / atr14
        dist_vol_dn = abs(price - vol_trigger_dn) / atr14
        vol_prox = max(0.0, 1.0 - min(dist_vol_up, dist_vol_dn) / 5)
        score += vol_prox * 5

        dgrp_score = min(100.0, max(0.0, score))

        # ── Bias scoring (comprehensive, 13 layers) ───────────────────────────
        bull, bear = 0.0, 0.0

        if fund_rate < -0.0001:    bull += 2.5
        elif fund_rate < 0:         bull += 1.0
        elif fund_rate > 0.0001:    bear += 2.5
        else:                       bear += 0.5

        if oi_delta < -1.0 and fund_rate > 0:  bull += 2.0
        elif oi_delta > 1.0 and fund_rate > 0: bear += 2.0
        elif oi_delta > 1.0 and fund_rate < 0: bull += 1.5
        elif oi_delta < -1.0 and fund_rate < 0:bear += 1.5

        if price > vwap_val + atr14 * 0.15:  bull += 2.0
        elif price < vwap_val - atr14 * 0.15:bear += 2.0
        else:                                  bull += 0.5; bear += 0.5

        if ema50:
            if price > ema50:  bull += 2.0
            else:              bear += 2.0

        rsi = _rsi(closes, 14)
        if rsi > 62:   bull += 1.5
        elif rsi < 38: bear += 1.5

        # Nearest flip asymmetry
        if nf_up and nf_dn:
            ud = nf_up - price
            dd = price - nf_dn
            if ud < dd * 0.5:   bear += 1.5
            elif dd < ud * 0.5: bull += 1.5

        # GEX zone
        if zone == "NEGATIVE":
            if fund_rate < 0: bull += 1.0
            else:             bear += 1.5
        elif zone == "POSITIVE":
            pass   # Pinned — no directional bias

        # Charm
        if charm_raw > 0.5:
            if fund_rate < 0: bull += 1.0
            else:             bear += 1.0

        # OPEX week penalty
        opex = _is_opex_week()
        if opex:
            bull *= 0.85; bear *= 0.85

        tot = bull + bear
        if   bull > bear * 1.1:  bias = "BULLISH"
        elif bear > bull * 1.1:  bias = "BEARISH"
        else:                     bias = "NEUTRAL"

        dom = max(bull, bear) / tot if tot > 0 else 0.5
        base_conf = 45.0 + dom * 55.0
        if len(true_flips) >= 3:  base_conf = min(base_conf + 8, 96)
        if in_comp:               base_conf = min(base_conf + 6, 96)
        if regime == "FLIP ZONE": base_conf = min(base_conf + 4, 96)
        if opex:                  base_conf = max(base_conf - 8, 40)
        # DGRP score boost: high-scoring regime = more confident
        if dgrp_score > 60:       base_conf = min(base_conf + 5, 96)
        elif dgrp_score < 30:     base_conf -= 5

        return GEXSnapshot(
            symbol=symbol,
            timestamp=time.time(),
            mark_price=price,
            # ── Dashboard fields ──────────────────────────────────────────────
            regime=regime,
            dgrp_score=dgrp_score,
            candle_state=candle_state,
            rv_ratio=rv_ratio,
            iv_proxy_z=iv_proxy_z,
            compression_state=comp_state,
            vanna_state=vanna_state,
            charm_state=charm_state,
            delta_bias=delta_bias,
            exp_move=exp_move,
            dealer_flow_m=dealer_flow_m,
            gex_regime=gex_regime,
            gex_flip=gfp,
            gex_flip_band=gfp_band,
            signal_state="No Signal",  # updated in detect_signal when a signal fires
            # ── Core ─────────────────────────────────────────────────────────
            current_gex_zone=zone,
            net_gex=cgx,
            nearest_flip_up=nf_up,
            nearest_flip_down=nf_dn,
            all_flip_levels=flip_levels,
            gamma_walls=gamma_walls,
            compression_zones=compression_zones,
            call_wall=call_wall,
            put_wall=put_wall,
            vol_trigger_up=vol_trigger_up,
            vol_trigger_dn=vol_trigger_dn,
            vanna_unwind_up=vanna_up,
            vanna_unwind_down=vanna_dn,
            vanna_entry=vanna_line,
            charm_decay=charm_raw,
            expected_move_upper=exp_up,
            expected_move_lower=exp_dn,
            vwap=vwap_val,
            vwap_plus1_atr=vwap_p1,
            vwap_minus1_atr=vwap_m1,
            vwap_plus2_atr=vwap_p2,
            vwap_minus2_atr=vwap_m2,
            ema50=ema50,
            gamma_flip_proxy=gfp,
            atr=atr14,
            atr_slow=atr28,
            funding_rate=fund_rate,
            open_interest=oi,
            oi_delta_pct=oi_delta,
            volume_24h=vol_24h,
            bias=bias,
            confidence=base_conf,
            is_opex_week=opex,
            session_open_minute=session_min,
        )

    # ─── Signal Detection ─────────────────────────────────────────────────────

    def detect_signal(
        self,
        snap_prev: GEXSnapshot,
        snap_curr: GEXSnapshot,
        min_confidence: float = 60.0,
    ) -> Optional[GEXSignal]:
        """
        Detect GEX flip crossover between two consecutive real-time snapshots.

        Signal logic:
          GEX_FLIP:          mark_price crosses a GEX flip level
          COMPRESSION_BREAK: mark_price exits a compression box (measured move entry)
          VANNA_ENTRY:       mark_price crosses the Vanna entry line
        """
        if snap_curr.confidence < min_confidence:
            return None

        pp = snap_prev.mark_price
        cp = snap_curr.mark_price
        price_move = abs(cp - pp)

        # Must have moved at least 0.3% to avoid noise
        if price_move < cp * 0.001:
            return None

        flips = snap_curr.all_flip_levels
        if not flips:
            return None

        crossed: Optional[GEXLevel] = None
        action  = ""
        sig_type = "GEX_FLIP"
        comp_hit: Optional[GEXZone] = None

        # ── 1. GEX Flip ────────────────────────────────────────────────────────
        for fl in sorted(flips, key=lambda x: x.strength, reverse=True):
            fp = fl.price
            if pp <= fp < cp:
                crossed = fl; action = "BUY"; break
            elif cp < fp <= pp:
                crossed = fl; action = "SELL"; break

        # ── 2. Compression Breakout ────────────────────────────────────────────
        if crossed is None:
            for cz in snap_curr.compression_zones:
                if pp <= cz.price_high < cp:
                    crossed = GEXLevel(
                        price=cz.price_high, gex_value=0, is_flip=True,
                        strength=cz.strength,
                        level_type="FLIP_UP",
                        timeframe=flips[0].timeframe if flips else "5m",
                    )
                    action = "BUY"; sig_type = "COMPRESSION_BREAK"; comp_hit = cz; break
                elif cp < cz.price_low <= pp:
                    crossed = GEXLevel(
                        price=cz.price_low, gex_value=0, is_flip=True,
                        strength=cz.strength,
                        level_type="FLIP_DOWN",
                        timeframe=flips[0].timeframe if flips else "5m",
                    )
                    action = "SELL"; sig_type = "COMPRESSION_BREAK"; comp_hit = cz; break

        # ── 3. Vanna Entry ─────────────────────────────────────────────────────
        if crossed is None and snap_curr.vanna_entry:
            ve = snap_curr.vanna_entry
            if pp <= ve < cp:
                crossed = GEXLevel(price=ve, gex_value=snap_curr.net_gex,
                                   is_flip=True, strength=50.0,
                                   level_type="FLIP_UP",
                                   timeframe=flips[0].timeframe if flips else "5m")
                action = "BUY"; sig_type = "VANNA_ENTRY"
            elif cp < ve <= pp:
                crossed = GEXLevel(price=ve, gex_value=snap_curr.net_gex,
                                   is_flip=True, strength=50.0,
                                   level_type="FLIP_DOWN",
                                   timeframe=flips[0].timeframe if flips else "5m")
                action = "SELL"; sig_type = "VANNA_ENTRY"

        if not crossed or not action:
            return None

        entry = crossed.price
        atr   = snap_curr.atr

        # ── TP: next GEX flip levels in trade direction ───────────────────────
        all_fp = sorted(fl.price for fl in flips)

        if action == "BUY":
            tps = sorted([p for p in all_fp if p > entry + atr * 0.05])
            tp1 = tps[0] if len(tps) > 0 else entry + atr * 2.0
            tp2 = tps[1] if len(tps) > 1 else tp1 + atr * 2.0
            tp3 = tps[2] if len(tps) > 2 else tp2 + atr * 2.5
            # Use Call Wall as ceiling TP if it's above tp1
            if snap_curr.call_wall and snap_curr.call_wall > tp1:
                tp3 = max(tp3, snap_curr.call_wall)
            sl = max(
                entry - atr * 1.5,
                snap_curr.nearest_flip_down or entry - atr * 2.0,
                snap_curr.put_wall - atr * 0.3 if snap_curr.put_wall else entry - atr * 2.0,
            )
            gex_to = "POSITIVE"
            gex_from = snap_prev.current_gex_zone
        else:
            tps = sorted([p for p in all_fp if p < entry - atr * 0.05], reverse=True)
            tp1 = tps[0] if len(tps) > 0 else entry - atr * 2.0
            tp2 = tps[1] if len(tps) > 1 else tp1 - atr * 2.0
            tp3 = tps[2] if len(tps) > 2 else tp2 - atr * 2.5
            # Use Put Wall as floor TP if below tp1
            if snap_curr.put_wall and snap_curr.put_wall < tp1:
                tp3 = min(tp3, snap_curr.put_wall)
            sl = min(
                entry + atr * 1.5,
                snap_curr.nearest_flip_up or entry + atr * 2.0,
                snap_curr.call_wall + atr * 0.3 if snap_curr.call_wall else entry + atr * 2.0,
            )
            gex_to = "NEGATIVE"
            gex_from = snap_prev.current_gex_zone

        # Use compression measured-move target as TP1
        if sig_type == "COMPRESSION_BREAK" and comp_hit and comp_hit.target:
            tp1 = comp_hit.target

        # ── R:R check ─────────────────────────────────────────────────────────
        risk   = abs(entry - sl)
        reward = abs(tp1 - entry)
        if risk <= 0:
            return None
        rr = reward / risk
        if rr < 1.2:
            return None

        # ── Confidence refinement with all layers ────────────────────────────
        conf = snap_curr.confidence

        # Crossed flip quality
        if crossed.strength > 75:  conf = min(conf + 12, 97)
        elif crossed.strength > 50:conf = min(conf + 6, 97)

        # Bias alignment
        if (action == "BUY" and snap_curr.bias == "BULLISH") or \
           (action == "SELL" and snap_curr.bias == "BEARISH"):
            conf = min(conf + 8, 97)
        elif snap_curr.bias == "NEUTRAL":
            conf -= 4

        # Delta bias alignment
        if (action == "BUY" and "Bullish" in snap_curr.delta_bias) or \
           (action == "SELL" and "Bearish" in snap_curr.delta_bias):
            conf = min(conf + 5, 97)

        # Funding
        if action == "BUY"  and snap_curr.funding_rate < -0.0001: conf = min(conf + 5, 97)
        if action == "SELL" and snap_curr.funding_rate >  0.0001: conf = min(conf + 5, 97)

        # VWAP
        if action == "BUY"  and cp > snap_curr.vwap: conf = min(conf + 4, 97)
        if action == "SELL" and cp < snap_curr.vwap: conf = min(conf + 4, 97)

        # 50 EMA
        if snap_curr.ema50:
            if action == "BUY"  and cp > snap_curr.ema50: conf = min(conf + 4, 97)
            if action == "SELL" and cp < snap_curr.ema50: conf = min(conf + 4, 97)
            if action == "BUY"  and cp < snap_curr.ema50: conf -= 8  # counter-trend
            if action == "SELL" and cp > snap_curr.ema50: conf -= 8

        # DGRP score
        if snap_curr.dgrp_score > 60:  conf = min(conf + 5, 97)
        elif snap_curr.dgrp_score < 30:conf -= 5

        # Regime match
        if snap_curr.regime == "FLIP ZONE":  conf = min(conf + 6, 97)

        # GEX regime match
        if action == "BUY"  and snap_curr.gex_regime == "SHORT GAMMA": conf = min(conf + 4, 97)
        if action == "SELL" and snap_curr.gex_regime == "LONG GAMMA":  conf = min(conf + 4, 97)

        # Charm active
        if snap_curr.charm_state == "ACTIVE":  conf = min(conf + 3, 97)

        # Compression break bonus
        if sig_type == "COMPRESSION_BREAK":  conf = min(conf + 7, 97)

        # R:R quality
        if rr >= 3.0:  conf = min(conf + 5, 97)
        elif rr >= 2.0:conf = min(conf + 2, 97)

        # OPEX penalty
        if snap_curr.is_opex_week:  conf -= 6

        conf = max(conf, 0.0)
        if conf < min_confidence:
            return None

        # ── Leverage: calibrated by R:R and DGRP ─────────────────────────────
        base_lev = 5
        if rr >= 4.0:  base_lev = 12
        elif rr >= 3.0:base_lev = 10
        elif rr >= 2.0:base_lev = 8
        if snap_curr.dgrp_score > 70: base_lev = min(base_lev + 2, 15)
        lev = max(3, min(base_lev, 15))

        tf = flips[0].timeframe if flips else timeframe

        nearest_comp = min(
            snap_curr.compression_zones,
            key=lambda z: abs(z.mid - entry),
            default=None,
        ) if snap_curr.compression_zones else None

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

    def get_dynamic_tp(self, entry: float, direction: str,
                       snap: GEXSnapshot) -> Optional[float]:
        """Return updated TP from current flip levels (called each scan cycle)."""
        fps = [fl.price for fl in snap.all_flip_levels]
        if not fps:
            return None
        if direction == "LONG":
            c = sorted([p for p in fps if p > entry])
            return c[0] if c else None
        else:
            c = sorted([p for p in fps if p < entry], reverse=True)
            return c[0] if c else None
