#!/usr/bin/env python3
"""
AEGIS GEX v1.0 — Dealer Flow Engine
=====================================
Pure-Python, zero-dependency GEX flip calculator for Binance USDM perpetuals.

Based on the AEGIS GEX DEALER FLOW ENGINE (TradingView: T1zYSBd7).

Core Concept (Gamma Exposure proxy for crypto perpetuals):
  - Real options markets: GEX = Σ(OI × Gamma × Contract_Size) at each strike
  - Crypto perpetuals proxy: GEX computed from OI distribution + funding rate polarity
    across a Gaussian-weighted strike grid built from ATR-spaced price levels.

  Positive GEX zone: Dealers are long gamma → they BUY dips and SELL rallies.
                     Price is PINNED — mean-reverting, stable.
  Negative GEX zone: Dealers are short gamma → they AMPLIFY moves.
                     Price TRENDS away — momentum-driven.

GEX Flip Level: The price where net dealer gamma crosses ZERO.
  → Above the flip: positive GEX (pin zone)
  → Below the flip: negative GEX (momentum zone)

Signal Logic:
  LONG  entry: Price crosses UP through a GEX flip (negative→positive = pinned rally)
  SHORT entry: Price crosses DOWN through a GEX flip (positive→negative = momentum dump)
  Entry  = current GEX flip level (the crossing price)
  TP     = the NEXT GEX flip level in the direction of trade (updated dynamically)
  SL     = ATR-based buffer beyond the entry flip level (invalidation zone)
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GEXLevel:
    """A single Gamma Exposure flip level."""
    price: float
    gex_value: float       # Net GEX proxy at this level (+ = positive, - = negative)
    is_flip: bool          # True if this level is a sign-change (flip point)
    strength: float        # 0-100 strength score based on OI concentration
    level_type: str        # "FLIP_UP" | "FLIP_DOWN" | "WALL_BULL" | "WALL_BEAR"
    timeframe: str         # "15m" | "1h" | "4h"


@dataclass
class GEXSnapshot:
    """Complete GEX picture for a symbol at a moment in time."""
    symbol: str
    timestamp: float
    current_price: float
    current_gex_zone: str          # "POSITIVE" | "NEGATIVE" | "NEUTRAL"
    net_gex: float                 # Net GEX at current price (proxy)
    nearest_flip_up: Optional[float]    # Nearest flip above price
    nearest_flip_down: Optional[float]  # Nearest flip below price
    all_flip_levels: List[GEXLevel]     # All detected flips (sorted by price)
    atr: float                          # ATR(14) used for level spacing
    funding_rate: float                 # Current funding rate
    open_interest: float                # Current OI (in contracts or USDT)
    oi_delta_pct: float                 # OI change % in last period
    volume_24h: float
    bias: str                           # "BULLISH" | "BEARISH" | "NEUTRAL"
    confidence: float                   # 0-100 overall signal confidence


@dataclass
class GEXSignal:
    """A trading signal derived from a GEX flip crossover."""
    symbol: str
    action: str             # "BUY" | "SELL"
    direction: str          # "LONG" | "SHORT"
    entry_price: float      # The GEX flip level being crossed
    entry_flip_level: float # Same as entry — the flipped GEX level
    tp1: float              # Next GEX flip level in direction (primary TP)
    tp2: float              # Second next flip level (extended TP)
    tp3: float              # Third flip level (runner TP)
    sl: float               # Stop loss (ATR buffer beyond entry flip)
    confidence: float       # 0–100
    timeframe: str          # Trigger timeframe
    gex_zone_from: str      # Zone BEFORE crossing
    gex_zone_to: str        # Zone AFTER crossing
    leverage: int           # Recommended leverage
    rr_ratio: float         # Risk:Reward ratio
    bias: str               # "BULLISH" | "BEARISH"
    atr: float
    funding_rate: float
    open_interest: float
    oi_delta_pct: float
    snapshot: GEXSnapshot
    timestamp: float = field(default_factory=time.time)
    signal_id: str = ""

    def __post_init__(self):
        if not self.signal_id:
            self.signal_id = f"GEX_{self.symbol}_{self.action}_{int(self.timestamp)}"


# ─────────────────────────────────────────────────────────────────────────────
# Pure-Python Indicator Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ema(data: List[float], period: int) -> Optional[float]:
    if len(data) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(data[:period]) / period
    for v in data[period:]:
        ema = v * k + ema * (1 - k)
    return ema

def _atr(closes: List[float], highs: List[float], lows: List[float],
         period: int = 14) -> float:
    """Wilder's ATR — true range with prev-close."""
    n = min(len(closes), len(highs), len(lows))
    if n < 2:
        return abs(closes[-1] * 0.01) if closes else 1.0
    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return sum(trs) / len(trs)
    wilder = sum(trs[:period]) / period
    for tr in trs[period:]:
        wilder = (wilder * (period - 1) + tr) / period
    return wilder

def _sma(data: List[float], period: int) -> Optional[float]:
    if len(data) < period:
        return None
    return sum(data[-period:]) / period

def _vwap(closes: List[float], highs: List[float], lows: List[float],
          volumes: List[float]) -> Optional[float]:
    n = min(len(closes), len(highs), len(lows), len(volumes))
    if n == 0:
        return None
    typicals = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(n)]
    cum_tv = sum(t * v for t, v in zip(typicals, volumes))
    cum_v  = sum(volumes)
    return cum_tv / cum_v if cum_v > 0 else None

def _rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100 - 100 / (1 + rs)

def _gaussian_weight(distance: float, sigma: float) -> float:
    """Gaussian kernel weight — higher weight = closer to current price."""
    if sigma <= 0:
        return 0.0
    return math.exp(-0.5 * (distance / sigma) ** 2)


# ─────────────────────────────────────────────────────────────────────────────
# GEX Engine
# ─────────────────────────────────────────────────────────────────────────────

class AEGISGEXEngine:
    """
    AEGIS GEX Dealer Flow Engine v1.0

    Computes GEX flip levels from Binance USDM perpetuals data using:
      - ATR-spaced strike grid (21 strikes, ±10 ATR from current price)
      - Gaussian-weighted OI distribution across the grid
      - Funding rate polarity to bias dealer gamma direction
      - OI velocity (delta) to weight active hedging levels
      - Volume profile VPOC for high-concentration "strike equivalents"
      - Multi-timeframe consensus (15m + 1h + 4h)
    """

    STRIKE_COUNT  = 21         # Number of synthetic strike levels in the grid
    ATR_PERIOD    = 14
    ATR_MULTIPLIER = 1.0       # Strike spacing = 1 ATR between levels
    SIGMA_MULTIPLIER = 3.0     # Gaussian sigma = 3 ATR (wider distribution)
    FLIP_MIN_STRENGTH = 15.0   # Minimum GEX strength to qualify as a flip level
    LOOKBACK_PERIODS = {
        "15m": 200,
        "1h":  200,
        "4h":  200,
    }
    OI_HIST_INTERVAL = {
        "15m": "5m",    # Use 5m OI history for 15m GEX
        "1h":  "1h",
        "4h":  "4h",
    }

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.GEXEngine")
        self._cache: Dict[str, Tuple[float, GEXSnapshot]] = {}
        self._cache_ttl = 60.0   # 60s cache per symbol

    async def compute_gex_snapshot(
        self,
        trader,
        symbol: str,
        timeframe: str = "1h",
    ) -> Optional[GEXSnapshot]:
        """
        Compute a complete GEX snapshot for a symbol.
        Returns cached result if fresher than 60 seconds.
        """
        cache_key = f"{symbol}_{timeframe}"
        cached = self._cache.get(cache_key)
        if cached:
            ts, snap = cached
            if time.time() - ts < self._cache_ttl:
                return snap

        try:
            limit = self.LOOKBACK_PERIODS.get(timeframe, 200)
            klines, funding_data, oi_data, ticker = await asyncio.gather(
                trader.get_klines(symbol, timeframe, limit),
                trader.get_funding_rate(symbol),
                trader.get_open_interest(symbol),
                trader.get_24hr_ticker_stats(symbol),
                return_exceptions=True,
            )

            if isinstance(klines, Exception) or not klines or len(klines) < 30:
                self.logger.debug(f"[{symbol}] Insufficient klines for GEX")
                return None

            closes  = [float(k[4]) for k in klines]
            highs   = [float(k[2]) for k in klines]
            lows    = [float(k[3]) for k in klines]
            volumes = [float(k[5]) for k in klines]

            current_price = closes[-1]

            atr_val = _atr(closes, highs, lows, self.ATR_PERIOD)
            if atr_val <= 0:
                atr_val = current_price * 0.005

            funding_rate = 0.0
            if isinstance(funding_data, dict) and "fundingRate" in funding_data:
                try:
                    funding_rate = float(funding_data["fundingRate"])
                except (ValueError, TypeError):
                    pass

            open_interest = 0.0
            if isinstance(oi_data, dict) and "openInterest" in oi_data:
                try:
                    open_interest = float(oi_data["openInterest"])
                except (ValueError, TypeError):
                    pass

            volume_24h = 0.0
            if isinstance(ticker, dict):
                try:
                    volume_24h = float(ticker.get("quoteVolume", 0))
                except (ValueError, TypeError):
                    pass

            oi_delta_pct = await self._compute_oi_delta(trader, symbol, timeframe, open_interest)

            snap = self._build_snapshot(
                symbol, current_price, closes, highs, lows, volumes,
                atr_val, funding_rate, open_interest, oi_delta_pct, volume_24h, timeframe,
            )

            self._cache[cache_key] = (time.time(), snap)
            return snap

        except Exception as e:
            self.logger.error(f"[{symbol}/{timeframe}] GEX snapshot error: {e}")
            return None

    async def _compute_oi_delta(
        self, trader, symbol: str, timeframe: str, current_oi: float
    ) -> float:
        """Compute OI % change over last period (proxy for dealer hedging activity)."""
        try:
            interval = self.OI_HIST_INTERVAL.get(timeframe, "1h")
            oi_hist  = await trader._get_fapi(
                "/futures/data/openInterestHist",
                {"symbol": symbol, "period": interval, "limit": 5},
            )
            if oi_hist and isinstance(oi_hist, list) and len(oi_hist) >= 2:
                oldest = float(oi_hist[0].get("sumOpenInterest", current_oi) or current_oi)
                latest = float(oi_hist[-1].get("sumOpenInterest", current_oi) or current_oi)
                if oldest > 0:
                    return (latest - oldest) / oldest * 100.0
        except Exception:
            pass
        return 0.0

    def _build_snapshot(
        self,
        symbol: str,
        price: float,
        closes: List[float],
        highs: List[float],
        lows: List[float],
        volumes: List[float],
        atr: float,
        funding_rate: float,
        open_interest: float,
        oi_delta_pct: float,
        volume_24h: float,
        timeframe: str,
    ) -> GEXSnapshot:
        """
        Build the full GEX snapshot:
         1. Construct ATR-spaced strike grid (21 levels)
         2. Assign Gaussian-weighted GEX proxy to each strike
         3. Identify sign changes (flip levels)
         4. Compute current zone, bias, and confidence
        """
        half = self.STRIKE_COUNT // 2
        sigma = atr * self.SIGMA_MULTIPLIER

        # ── Build strike grid ────────────────────────────────────────────────
        strikes = [price + (i - half) * atr * self.ATR_MULTIPLIER
                   for i in range(self.STRIKE_COUNT)]

        # ── Volume profile: identify VPOC (highest-volume price cluster) ──────
        vpoc = self._compute_vpoc(closes, highs, lows, volumes)

        # ── Compute GEX proxy at each strike ─────────────────────────────────
        # Core formula (AEGIS GEX proxy):
        #   GEX(S) = OI_weight(S) × Gamma_sign(S) × Funding_factor × OI_delta_factor
        # Where:
        #   OI_weight(S)       = Gaussian kernel centered at current price
        #   Gamma_sign(S)      = +1 above price (call-side), -1 below price (put-side)
        #   Funding_factor     = 1 + (funding_rate × 100) clamped to [0.5, 2.0]
        #   OI_delta_factor    = 1 + (oi_delta_pct/100) clamped to [0.5, 2.0]
        #   VPOC_boost         = 1.5× weight boost for strikes within 0.5 ATR of VPOC

        oi_reference = max(open_interest, 1.0)
        funding_factor = max(0.5, min(2.0, 1.0 + funding_rate * 100))
        oi_delta_factor = max(0.5, min(2.0, 1.0 + oi_delta_pct / 100.0))

        gex_values: List[float] = []
        for s in strikes:
            dist   = abs(price - s)
            weight = _gaussian_weight(dist, sigma)

            vpoc_boost = 1.5 if vpoc and abs(s - vpoc) < atr * 0.5 else 1.0

            gamma_sign = 1.0 if s >= price else -1.0

            raw_gex = oi_reference * weight * gamma_sign * funding_factor * oi_delta_factor * vpoc_boost
            gex_values.append(raw_gex)

        # ── Identify GEX flip levels ──────────────────────────────────────────
        max_abs_gex = max(abs(g) for g in gex_values) or 1.0
        flip_levels: List[GEXLevel] = []

        for i in range(1, len(strikes)):
            g_prev = gex_values[i - 1]
            g_curr = gex_values[i]
            if g_prev * g_curr < 0:   # Sign change = flip
                interp_price = self._interpolate_zero_crossing(
                    strikes[i - 1], strikes[i], g_prev, g_curr
                )
                strength = (abs(g_prev) + abs(g_curr)) / (2 * max_abs_gex) * 100.0
                if strength >= self.FLIP_MIN_STRENGTH:
                    if g_prev < 0 and g_curr >= 0:
                        level_type = "FLIP_UP"
                    else:
                        level_type = "FLIP_DOWN"
                    flip_levels.append(GEXLevel(
                        price=interp_price,
                        gex_value=(g_prev + g_curr) / 2,
                        is_flip=True,
                        strength=min(strength, 100.0),
                        level_type=level_type,
                        timeframe=timeframe,
                    ))

        if not flip_levels:
            for i in range(1, len(strikes)):
                g_prev = gex_values[i - 1]
                g_curr = gex_values[i]
                if abs(g_curr - g_prev) > max_abs_gex * 0.05:
                    strength = abs(g_curr) / max_abs_gex * 100.0
                    flip_levels.append(GEXLevel(
                        price=strikes[i],
                        gex_value=g_curr,
                        is_flip=False,
                        strength=strength,
                        level_type="WALL_BULL" if g_curr > 0 else "WALL_BEAR",
                        timeframe=timeframe,
                    ))

        flip_levels.sort(key=lambda x: x.price)

        # ── Current GEX zone at price ─────────────────────────────────────────
        price_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - price))
        current_gex = gex_values[price_idx]

        if current_gex > max_abs_gex * 0.1:
            zone = "POSITIVE"
        elif current_gex < -max_abs_gex * 0.1:
            zone = "NEGATIVE"
        else:
            zone = "NEUTRAL"

        # ── Nearest flips above and below ────────────────────────────────────
        nearest_flip_up   = next((fl.price for fl in flip_levels if fl.price > price), None)
        nearest_flip_down = next((fl.price for fl in reversed(flip_levels) if fl.price < price), None)

        # ── Bias: funding + OI delta + VWAP relative to price ────────────────
        vwap = _vwap(closes, highs, lows, volumes)
        rsi  = _rsi(closes, 14) or 50.0

        bullish_score = 0
        bearish_score = 0

        if funding_rate < 0:
            bullish_score += 1  # Shorts paying longs → bullish
        else:
            bearish_score += 1

        if oi_delta_pct > 0:
            if funding_rate >= 0:
                bearish_score += 1  # Growing OI with positive funding = short pressure
            else:
                bullish_score += 1
        elif oi_delta_pct < 0:
            if funding_rate < 0:
                bullish_score += 1  # Shrinking shorts = bullish cover
            else:
                bearish_score += 1

        if vwap and price > vwap:
            bullish_score += 1
        elif vwap and price < vwap:
            bearish_score += 1

        if rsi > 55:
            bullish_score += 1
        elif rsi < 45:
            bearish_score += 1

        if nearest_flip_up and nearest_flip_down:
            up_dist   = nearest_flip_up   - price
            down_dist = price - nearest_flip_down
            if up_dist < down_dist * 0.5:
                bearish_score += 1
            elif down_dist < up_dist * 0.5:
                bullish_score += 1

        if bullish_score > bearish_score:
            bias = "BULLISH"
        elif bearish_score > bullish_score:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        total = bullish_score + bearish_score
        if total > 0:
            score = max(bullish_score, bearish_score) / total
            confidence = 50.0 + score * 50.0
        else:
            confidence = 50.0

        if len(flip_levels) >= 3:
            confidence = min(confidence + 10.0, 95.0)

        return GEXSnapshot(
            symbol=symbol,
            timestamp=time.time(),
            current_price=price,
            current_gex_zone=zone,
            net_gex=current_gex,
            nearest_flip_up=nearest_flip_up,
            nearest_flip_down=nearest_flip_down,
            all_flip_levels=flip_levels,
            atr=atr,
            funding_rate=funding_rate,
            open_interest=open_interest,
            oi_delta_pct=oi_delta_pct,
            volume_24h=volume_24h,
            bias=bias,
            confidence=confidence,
        )

    def _interpolate_zero_crossing(
        self, x1: float, x2: float, y1: float, y2: float
    ) -> float:
        """Linear interpolation to find the exact zero-crossing price."""
        if y1 == y2:
            return (x1 + x2) / 2
        return x1 + (x2 - x1) * (-y1 / (y2 - y1))

    def _compute_vpoc(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float],
        volumes: List[float],
        bins: int = 50,
    ) -> Optional[float]:
        """Volume Profile Point of Control — highest-volume price level."""
        n = min(len(closes), len(highs), len(lows), len(volumes))
        if n < 10:
            return None
        price_min = min(lows[-n:])
        price_max = max(highs[-n:])
        if price_max <= price_min:
            return None
        bin_size  = (price_max - price_min) / bins
        vol_bins  = [0.0] * bins
        for i in range(n):
            mid     = (highs[i] + lows[i] + closes[i]) / 3.0
            bin_idx = min(int((mid - price_min) / bin_size), bins - 1)
            vol_bins[bin_idx] += volumes[i]
        peak_bin = vol_bins.index(max(vol_bins))
        return price_min + (peak_bin + 0.5) * bin_size

    def detect_gex_flip_signal(
        self,
        snap_prev: GEXSnapshot,
        snap_curr: GEXSnapshot,
        min_confidence: float = 60.0,
    ) -> Optional[GEXSignal]:
        """
        Compare two consecutive snapshots to detect a GEX flip crossover.

        A GEX flip occurs when price has CROSSED through one of the flip levels
        between the previous and current snapshot.

        Entry  = the flip level that was crossed (current GEX flip price)
        TP1    = next flip level in the direction of trade
        TP2    = second next flip level
        TP3    = third next flip level (or TP1 × 1.5× extension)
        SL     = ATR-based buffer on the wrong side of the entry flip
        """
        if snap_curr.confidence < min_confidence:
            return None

        price_prev = snap_prev.current_price
        price_curr = snap_curr.current_price
        flips      = snap_curr.all_flip_levels

        if not flips:
            return None

        crossed_flip: Optional[GEXLevel] = None
        action: str = ""

        for fl in flips:
            fp = fl.price
            if price_prev <= fp < price_curr:
                crossed_flip = fl
                action = "BUY"
                break
            elif price_curr < fp <= price_prev:
                crossed_flip = fl
                action = "SELL"
                break

        if not crossed_flip or not action:
            return None

        entry = crossed_flip.price
        atr   = snap_curr.atr

        if action == "BUY":
            flips_above = sorted([fl for fl in flips if fl.price > entry], key=lambda x: x.price)
            tp1 = flips_above[0].price if len(flips_above) > 0 else entry + atr * 2.0
            tp2 = flips_above[1].price if len(flips_above) > 1 else tp1 + atr * 2.0
            tp3 = flips_above[2].price if len(flips_above) > 2 else tp2 + atr * 2.0
            sl  = entry - atr * 1.5

            gex_from = snap_prev.current_gex_zone
            gex_to   = "POSITIVE"

        else:
            flips_below = sorted([fl for fl in flips if fl.price < entry], key=lambda x: x.price, reverse=True)
            tp1 = flips_below[0].price if len(flips_below) > 0 else entry - atr * 2.0
            tp2 = flips_below[1].price if len(flips_below) > 1 else tp1 - atr * 2.0
            tp3 = flips_below[2].price if len(flips_below) > 2 else tp2 - atr * 2.0
            sl  = entry + atr * 1.5

            gex_from = snap_prev.current_gex_zone
            gex_to   = "NEGATIVE"

        risk   = abs(entry - sl)
        reward = abs(tp1 - entry)
        rr     = reward / risk if risk > 0 else 1.0

        if rr < 1.0:
            return None

        confidence = snap_curr.confidence
        if crossed_flip.strength > 60:
            confidence = min(confidence + 10.0, 98.0)
        if snap_curr.bias == ("BULLISH" if action == "BUY" else "BEARISH"):
            confidence = min(confidence + 8.0, 98.0)
        if abs(snap_curr.funding_rate) > 0.001:
            if (action == "BUY" and snap_curr.funding_rate < 0) or \
               (action == "SELL" and snap_curr.funding_rate > 0):
                confidence = min(confidence + 5.0, 98.0)

        lev = 10 if rr >= 3.0 else (8 if rr >= 2.0 else 5)
        lev = max(3, min(lev, 10))

        return GEXSignal(
            symbol=snap_curr.symbol,
            action=action,
            direction="LONG" if action == "BUY" else "SHORT",
            entry_price=entry,
            entry_flip_level=crossed_flip.price,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            sl=sl,
            confidence=confidence,
            timeframe=snap_curr.all_flip_levels[0].timeframe if snap_curr.all_flip_levels else "1h",
            gex_zone_from=gex_from,
            gex_zone_to=gex_to,
            leverage=lev,
            rr_ratio=rr,
            bias=snap_curr.bias,
            atr=atr,
            funding_rate=snap_curr.funding_rate,
            open_interest=snap_curr.open_interest,
            oi_delta_pct=snap_curr.oi_delta_pct,
            snapshot=snap_curr,
        )

    def get_current_tp_target(
        self,
        entry_price: float,
        direction: str,
        snapshot: GEXSnapshot,
    ) -> Optional[float]:
        """
        Dynamically return the CURRENT best TP target given live GEX state.
        Used by the bot to update TP as new GEX flips appear while in a trade.

        Rule: TP = nearest GEX flip level in the direction of the trade
               that is BETTER than the entry price.
        """
        flips = snapshot.all_flip_levels
        if not flips:
            return None

        if direction == "LONG":
            targets = sorted([fl.price for fl in flips if fl.price > entry_price])
            return targets[0] if targets else None
        else:
            targets = sorted([fl.price for fl in flips if fl.price < entry_price], reverse=True)
            return targets[0] if targets else None
