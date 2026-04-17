#!/usr/bin/env python3
"""
AEGIS GEX v1.0 — Dealer Flow Engine  (v4 — Production Enhanced)
===========================================================================
Based on: AEGIS GEX DEALER FLOW ENGINE (TradingView: T1zYSBd7)

SL / TP (fixed from entry — 5m TF):
  SL  = 0.18 % below/above entry
  TP1 = 0.54 % (3 × SL) beyond entry   [primary target]
  TP2 = 1.08 % (6 × SL) beyond entry
  TP3 = next GEX wall / level if favourable, else 1.62 % (9 × SL)

Dashboard Table (exact match to TradingView AEGIS GEX v1.0):
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

Timeframe: 5m primary, 15m confirmation
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

# ── Fixed SL / TP percentages (5m scalp specification) ────────────────────────
SL_PCT  = float(os.getenv("GEX_SL_PCT",  "0.0018"))   # 0.18 % — hard cap / fallback
TP1_PCT = float(os.getenv("GEX_TP1_PCT", "0.0054"))   # 0.54 % (3 × SL)
TP2_PCT = float(os.getenv("GEX_TP2_PCT", "0.0108"))   # 1.08 % (6 × SL)
TP3_PCT = float(os.getenv("GEX_TP3_PCT", "0.0162"))   # 1.62 % (9 × SL)

# Minimum SL distance from entry — avoids noise stops closer than 0.05 %
_SL_MIN_PCT = 0.0005   # 0.05 %


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
    vol_avg: float                  # Average 20-bar volume (for spike detection)
    vol_last: float                 # Last bar volume
    vol_spike: bool                 # True if last bar volume > 1.3× average
    rsi: float                      # RSI(14) at current price
    stoch_k: float                  # Stochastic %K (14,3,3)
    stoch_d: float                  # Stochastic %D (signal line — SMA of %K)
    vpoc: Optional[float]           # Volume Point of Control (highest-volume price)
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
    if len(data) < period or period < 1:
        return None
    k = 2.0 / (period + 1)
    e = sum(data[:period]) / period
    for v in data[period:]:
        e = v * k + e * (1.0 - k)
    return e


def _atr(closes: List[float], highs: List[float], lows: List[float],
         period: int = 14) -> float:
    n = min(len(closes), len(highs), len(lows))
    if n < 2:
        return max(abs(closes[-1] * 0.005), 1e-10) if closes else 1.0
    trs = [
        max(highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1]))
        for i in range(1, n)
    ]
    if not trs:
        return 1.0
    period = max(1, min(period, len(trs)))
    a = sum(trs[:period]) / period
    for tr in trs[period:]:
        a = (a * (period - 1) + tr) / period
    return max(a, 1e-10)


def _vwap(closes: List[float], highs: List[float],
          lows: List[float], volumes: List[float]) -> Optional[float]:
    n = min(len(closes), len(highs), len(lows), len(volumes))
    if n == 0:
        return None
    tv = sum((highs[i] + lows[i] + closes[i]) / 3.0 * volumes[i] for i in range(n))
    sv = sum(volumes[:n])
    return tv / sv if sv > 0 else closes[-1] if closes else None


def _rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def _stochastic(closes: List[float], highs: List[float], lows: List[float],
                k_period: int = 14, d_period: int = 3, smooth: int = 3
                ) -> Tuple[float, float]:
    """Full Stochastic Oscillator %K and %D (slowed version)."""
    n = min(len(closes), len(highs), len(lows))
    if n < k_period + d_period + smooth:
        return 50.0, 50.0

    raw_k: List[float] = []
    for i in range(k_period - 1, n):
        hi = max(highs[i - k_period + 1: i + 1])
        lo = min(lows [i - k_period + 1: i + 1])
        denom = hi - lo
        raw_k.append((closes[i] - lo) / denom * 100.0 if denom > 0 else 50.0)

    if len(raw_k) < smooth:
        return 50.0, 50.0

    # Smooth %K with SMA(smooth)
    smoothed_k: List[float] = []
    for i in range(smooth - 1, len(raw_k)):
        smoothed_k.append(sum(raw_k[i - smooth + 1: i + 1]) / smooth)

    if len(smoothed_k) < d_period:
        return smoothed_k[-1] if smoothed_k else 50.0, 50.0

    # %D = SMA(d_period) of smoothed %K
    k_val = smoothed_k[-1]
    d_val = sum(smoothed_k[-d_period:]) / d_period
    return k_val, d_val


def _stdev(data: List[float], period: int) -> float:
    if len(data) < period or period < 1:
        return 0.0
    w  = data[-period:]
    mu = sum(w) / period
    v  = sum((x - mu) ** 2 for x in w) / period
    return math.sqrt(v) if v > 0 else 0.0


def _sma(data: List[float], period: int) -> Optional[float]:
    if len(data) < period or period < 1:
        return None
    return sum(data[-period:]) / period


def _gaussian(distance: float, sigma: float) -> float:
    if sigma <= 0:
        return 0.0
    return math.exp(-0.5 * (distance / sigma) ** 2)


def _vpoc(closes: List[float], highs: List[float],
          lows: List[float], volumes: List[float],
          bins: int = 120) -> Optional[float]:
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
    try:
        mc  = _cal.monthcalendar(now.year, now.month)
        frs = [week[4] for week in mc if week[4] != 0]
        if len(frs) < 3:
            return False
        opex = now.date().replace(day=frs[2])
        return abs((now.date() - opex).days) <= 3
    except Exception:
        return False


def _session_open_minute() -> int:
    """Minutes since most recent major session open (00:00 / 08:00 / 16:00 UTC).
    Always returns a non-negative value in [0, 480).
    """
    now = datetime.now(timezone.utc)
    m   = now.hour * 60 + now.minute
    candidates = []
    for o in (0, 480, 960):
        diff = (m - o) % 1440
        candidates.append(diff)
    return min(candidates)


def _interpolate_zero(x1: float, x2: float, y1: float, y2: float) -> float:
    if y1 == y2:
        return (x1 + x2) / 2.0
    return x1 + (x2 - x1) * (-y1 / (y2 - y1))


def _vol_avg(volumes: List[float], period: int = 20) -> float:
    """Simple moving average of volume over last `period` bars."""
    if not volumes:
        return 1.0
    w = volumes[-min(period, len(volumes)):]
    return sum(w) / len(w) if w else 1.0


def _fmt_price(v: float) -> str:
    """Format price with appropriate precision.
    Handles all magnitudes including sub-dollar and negative values safely.
    """
    if not math.isfinite(v):
        return "0"
    sign = "-" if v < 0 else ""
    av   = abs(v)
    if av == 0:
        return "0"
    if av >= 100_000:
        return f"{sign}{av:.2f}"
    if av >= 10_000:
        return f"{sign}{av:.2f}"
    if av >= 1_000:
        return f"{sign}{av:.3f}"
    if av >= 100:
        return f"{sign}{av:.4f}"
    if av >= 10:
        return f"{sign}{av:.5f}"
    if av >= 1:
        return f"{sign}{av:.6f}"
    # Sub-dollar (meme/nano coins) — use significant-digit precision
    try:
        sig = max(4, -int(math.floor(math.log10(av))) + 3)
    except (ValueError, OverflowError):
        sig = 8
    return f"{sign}{av:.{min(sig, 10)}f}"


def _dynamic_sl(entry: float, action: str, snap: "GEXSnapshot") -> float:
    """
    ATR-adaptive dynamic SL anchored to the tightest meaningful technical
    level within a per-symbol volatility-scaled risk budget.

    Adaptive SL boundaries (hard-capped by SL_PCT = 0.18%):
      sl_min_pct = max(_SL_MIN_PCT, ATR/entry × 0.40) — noise floor:
                   at least 0.4 ATR away so the stop survives micro-wicks.
      sl_max_pct = min(SL_PCT,      ATR/entry × 1.20) — risk ceiling:
                   no more than 1.2 ATR of risk (never exceeds 0.18%).
      If ATR/entry > SL_PCT  : use SL_PCT (very volatile symbol)
      If sl_min_pct ≥ sl_max_pct : fall back to sl_max_pct × 0.5 floor

    Level priority — tested in order; ALL qualifying levels are collected and
    the tightest (closest to entry) is returned:
      1. Nearest GEX flip below price (BUY) / above price (SELL) — the exact
         gamma boundary that invalidates the thesis if recrossed.
      2. GEX flip proxy / gamma flip proxy — primary AEGIS GEX zero-crossing.
      3. VWAP — strongest real-time institutional anchor.
      4. VPOC — Volume Point of Control; the highest-volume price node.
      5. Put wall (BUY) / Call wall (SELL) — gamma support / resistance.
      6. VWAP ± 0.5 × ATR — intermediate intraday volatility band.
      7. VWAP ± 1.0 × ATR (stored vwap_minus1_atr / vwap_plus1_atr) — wider
         band used as last-resort technical anchor before full-budget fallback.
    Fallback: full ATR-scaled SL (= sl_max) when no level qualifies.
    """
    atr_pct     = snap.atr / max(entry, 1e-10)
    # Noise floor: at least 0.4 ATR, but never below the absolute minimum
    sl_min_pct  = max(_SL_MIN_PCT, atr_pct * 0.40)
    # Risk ceiling: at most 1.2 ATR, always capped by the hard budget
    sl_max_pct  = min(SL_PCT, atr_pct * 1.20)
    # Safety: ensure min < max so the valid window is non-empty
    if sl_min_pct >= sl_max_pct:
        sl_min_pct = sl_max_pct * 0.50

    if action == "BUY":
        # SL must be BELOW entry
        # sl_floor  = furthest allowed (lowest price) = tightest risk budget
        # sl_ceil   = closest allowed (highest price below entry) = noise floor
        sl_floor  = entry * (1.0 - sl_max_pct)
        sl_ceil   = entry * (1.0 - sl_min_pct)

        def _ok_buy(p: Optional[float]) -> bool:
            return (p is not None and math.isfinite(p)
                    and p > 0 and sl_floor <= p <= sl_ceil)

        cands: List[float] = []

        # 1. Nearest flip DOWN (strongest GEX anchor just below price)
        if _ok_buy(snap.nearest_flip_down):
            cands.append(snap.nearest_flip_down)

        # 2. GEX flip proxy / gamma flip proxy
        for lvl in (snap.gex_flip, snap.gamma_flip_proxy):
            if _ok_buy(lvl):
                cands.append(lvl)

        # 3. VWAP
        if _ok_buy(snap.vwap):
            cands.append(snap.vwap)

        # 4. VPOC
        if _ok_buy(snap.vpoc):
            cands.append(snap.vpoc)

        # 5. Put wall
        if _ok_buy(snap.put_wall):
            cands.append(snap.put_wall)

        # 6. VWAP – 0.5 ATR
        if snap.vwap and snap.atr:
            if _ok_buy(snap.vwap - snap.atr * 0.5):
                cands.append(snap.vwap - snap.atr * 0.5)

        # 7. VWAP – 1.0 ATR (explicit snapshot band)
        if _ok_buy(snap.vwap_minus1_atr):
            cands.append(snap.vwap_minus1_atr)

        # Tightest valid level = closest to entry = highest qualifying price
        return max(cands) if cands else sl_floor

    else:  # SELL — SL must be ABOVE entry
        sl_floor  = entry * (1.0 + sl_min_pct)   # closest (lowest price above)
        sl_ceil   = entry * (1.0 + sl_max_pct)   # furthest (highest price)

        def _ok_sell(p: Optional[float]) -> bool:
            return (p is not None and math.isfinite(p)
                    and p > 0 and sl_floor <= p <= sl_ceil)

        cands = []

        # 1. Nearest flip UP
        if _ok_sell(snap.nearest_flip_up):
            cands.append(snap.nearest_flip_up)

        # 2. GEX flip proxy / gamma flip proxy
        for lvl in (snap.gex_flip, snap.gamma_flip_proxy):
            if _ok_sell(lvl):
                cands.append(lvl)

        # 3. VWAP
        if _ok_sell(snap.vwap):
            cands.append(snap.vwap)

        # 4. VPOC
        if _ok_sell(snap.vpoc):
            cands.append(snap.vpoc)

        # 5. Call wall
        if _ok_sell(snap.call_wall):
            cands.append(snap.call_wall)

        # 6. VWAP + 0.5 ATR
        if snap.vwap and snap.atr:
            if _ok_sell(snap.vwap + snap.atr * 0.5):
                cands.append(snap.vwap + snap.atr * 0.5)

        # 7. VWAP + 1.0 ATR (explicit snapshot band)
        if _ok_sell(snap.vwap_plus1_atr):
            cands.append(snap.vwap_plus1_atr)

        # Tightest valid level = closest to entry = lowest qualifying price
        return min(cands) if cands else sl_ceil


# ─────────────────────────────────────────────────────────────────────────────
# AEGIS GEX Engine v4 — Production Enhanced
# ─────────────────────────────────────────────────────────────────────────────

class AEGISGEXEngine:
    """
    AEGIS GEX Dealer Flow Engine v1.0 — Production Enhanced

    Primary TF  : 5m  (configurable via GEX_PRIMARY_TF)
    Confirm TF  : 15m (configurable via GEX_CONFIRM_TF)
    SL / TP     : Fixed percentages — SL 0.18 %, TP 0.54/1.08/1.62 %
    Signal gate : Confidence ≥ 68 | DGRP ≥ 40 | Vol spike or DGRP ≥ 55
                  | R:R ≥ 3.0 | Bias aligned | 15m confirmation
    """

    # Strike grid parameters
    STRIKE_COUNT      = 51          # 51 strikes = ±25 levels @ 0.65 ATR each
    ATR_PERIOD        = 14
    ATR_SLOW_PERIOD   = 28          # For RV Ratio calculation
    ATR_MULT          = 0.65        # Strike spacing (tighter for precision)
    SIGMA_MULT        = 3.5         # Gaussian distribution width
    FLIP_MIN_STR      = 8.0         # Minimum flip strength
    WALL_MIN_STR      = 16.0        # Minimum wall strength
    COMPRESS_MAX_GAP  = 1.5         # ATR gap for compression detection (tighter = higher quality)

    # Signal quality gates
    MIN_CONFIDENCE    = float(os.getenv("GEX_MIN_CONFIDENCE", "68.0"))
    MIN_DGRP          = float(os.getenv("GEX_MIN_DGRP", "40.0"))
    MIN_RR            = 3.0         # Fixed: TP1 = 3× SL
    MIN_PRICE_MOVE    = 0.00025     # 0.025% min move to avoid pure noise

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
        self._cache_ttl = 22.0   # 22s — just under 30s scan interval

    # ─── Public API ──────────────────────────────────────────────────────────

    async def compute_gex_snapshot(
        self,
        client,
        symbol: str,
        timeframe: str = "5m",
    ) -> Optional[GEXSnapshot]:
        """Compute full AEGIS GEX snapshot. Uses real-time mark price."""
        ck  = f"{symbol}_{timeframe}"
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
            opens   = [float(k[1]) for k in klines]

            # Guard against zero prices
            if not closes or closes[-1] <= 0:
                return None

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

            # ── OI (contracts) ───────────────────────────────────────────────
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
                symbol, mark_price, closes, highs, lows, volumes, opens,
                fund_rate, oi, oi_delta, vol_24h, timeframe,
            )
            self._cache[ck] = (time.time(), snap)
            return snap

        except Exception as e:
            self.logger.error(f"[{symbol}/{timeframe}] snapshot: {e}")
            return None

    async def _oi_delta(self, client, symbol: str, tf: str, cur_oi: float) -> float:
        try:
            period = self.OI_HIST_PERIOD.get(tf, "5m")
            hist   = await client._get_fapi(
                "/futures/data/openInterestHist",
                {"symbol": symbol, "period": period, "limit": 10},
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
        opens: List[float],
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
        if atr14 <= 0:
            atr14 = max(price * 0.002, 1e-10)
        if atr28 <= 0:
            atr28 = atr14

        # ── RV Ratio: ATR(14) / ATR(28) ───────────────────────────────────────
        rv_ratio = atr14 / atr28 if atr28 > 0 else 1.0

        # ── IV Proxy Z-score ──────────────────────────────────────────────────
        atr_pct_series: List[float] = []
        for i in range(max(15, n - 60), n):
            sub_c = closes[max(0, i - 15):i + 1]
            sub_h = highs [max(0, i - 15):i + 1]
            sub_l = lows  [max(0, i - 15):i + 1]
            if len(sub_c) >= 2 and closes[i] > 0:
                a = _atr(sub_c, sub_h, sub_l, min(14, len(sub_c) - 1))
                atr_pct_series.append(a / closes[i])

        iv_proxy_z = 0.0
        if len(atr_pct_series) >= 10:
            cur_iv = atr14 / price if price > 0 else 0.0
            mu  = sum(atr_pct_series) / len(atr_pct_series)
            sd  = _stdev(atr_pct_series, min(20, len(atr_pct_series)))
            iv_proxy_z = (cur_iv - mu) / sd if sd > 0 else 0.0
            iv_proxy_z = max(-3.0, min(3.0, iv_proxy_z))

        # ── Volume spike detection ─────────────────────────────────────────────
        # Use only closed candles: exclude the last (possibly open/partial) candle
        closed_vols = volumes[:-1] if len(volumes) > 1 else volumes
        vol_avg_20  = _vol_avg(closed_vols, 20)
        # Compare the last COMPLETED candle against the prior 20-bar average
        vol_last    = volumes[-2] if len(volumes) >= 2 else (volumes[-1] if volumes else 0.0)
        vol_spike   = vol_last > vol_avg_20 * 1.5 if vol_avg_20 > 0 else False

        # ── RSI(14) ───────────────────────────────────────────────────────────
        rsi14 = _rsi(closes, 14)

        # ── Stochastic (14,3,3) — both %K and %D stored ───────────────────────
        stoch_k, stoch_d = _stochastic(closes, highs, lows, 14, 3, 3)

        # ── VPOC (Volume Point of Control) ────────────────────────────────────
        vpoc = _vpoc(closes, highs, lows, volumes, bins=120)

        # ── Session / Funding factors ─────────────────────────────────────────
        session_min    = _session_open_minute()
        session_factor = 1.30 if session_min <= self.SESSION_OPEN_MIN else 1.0
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
            # VPOC boost: strikes near VPOC get higher gamma weight
            vpoc_b  = 1.8 if vpoc and abs(s - vpoc) < atr14 * 0.7 else 1.0
            g_sign  = 1.0 if s >= price else -1.0
            # Fear-regime skew: elevated put-side gamma when funding negative
            skew    = (1.0 + abs(fund_rate) * 90) if (s < price and fund_rate < -0.0001) else 1.0
            # Vol expansion: high IV proxy Z → stronger gamma
            vol_amp = 1.0 + max(0.0, iv_proxy_z * 0.12)
            # Volume spike: amplify gamma signal when vol is elevated
            vol_spk = 1.15 if vol_spike else 1.0
            gex_vals.append(
                oi_ref * w * g_sign
                * fund_factor * oi_delta_f
                * vpoc_b * skew * session_factor * vol_amp * vol_spk
            )

        max_abs = max((abs(g) for g in gex_vals), default=1.0) or 1.0

        # ── GEX flip levels ───────────────────────────────────────────────────
        flip_levels: List[GEXLevel] = []
        for i in range(1, len(strikes)):
            g0, g1 = gex_vals[i - 1], gex_vals[i]
            if g0 * g1 < 0:
                zp   = _interpolate_zero(strikes[i - 1], strikes[i], g0, g1)
                str_ = (abs(g0) + abs(g1)) / (2.0 * max_abs) * 100.0
                if str_ >= self.FLIP_MIN_STR:
                    lt = "FLIP_UP" if g0 < 0 else "FLIP_DOWN"
                    flip_levels.append(GEXLevel(
                        price=zp, gex_value=(g0 + g1) / 2.0, is_flip=True,
                        strength=min(str_, 100.0), level_type=lt,
                        timeframe=timeframe,
                    ))

        # Fallback: gradient-based pseudo-flips if no zero crossings
        if not flip_levels:
            cands = sorted(range(1, len(strikes)),
                           key=lambda i: abs(gex_vals[i] - gex_vals[i - 1]),
                           reverse=True)[:5]
            for i in cands:
                str_ = abs(gex_vals[i]) / max_abs * 100.0
                flip_levels.append(GEXLevel(
                    price=strikes[i], gex_value=gex_vals[i], is_flip=False,
                    strength=str_, timeframe=timeframe,
                    level_type="WALL_BULL" if gex_vals[i] > 0 else "WALL_BEAR",
                ))

        flip_levels.sort(key=lambda x: x.price)

        # ── Primary GEX Flip Proxy (strongest true flip nearest price) ────────
        true_flips = [fl for fl in flip_levels if fl.is_flip]
        if true_flips:
            # Prefer the strongest flip within 3 ATR of price
            nearby = [fl for fl in true_flips if abs(fl.price - price) < atr14 * 3]
            if nearby:
                gfp = max(nearby, key=lambda x: x.strength).price
            else:
                gfp = max(true_flips, key=lambda x: x.strength).price
        elif flip_levels:
            gfp = min(flip_levels, key=lambda x: abs(x.price - price)).price
        else:
            gfp = price

        # GEX flip band: bounded by [ATR*0.15, ATR*0.4]
        if len(flip_levels) >= 2:
            gaps = [flip_levels[i + 1].price - flip_levels[i].price
                    for i in range(len(flip_levels) - 1)]
            raw_band = sum(gaps) / len(gaps) / 2.0
        else:
            raw_band = atr14 * 0.3
        gfp_band = max(atr14 * 0.15, min(raw_band, atr14 * 0.4))

        # ── Gamma Wall Boxes ──────────────────────────────────────────────────
        gamma_walls: List[GEXZone] = []
        for fl in flip_levels:
            if fl.strength >= self.WALL_MIN_STR:
                hw  = atr14 * 0.30
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
        walls_above = [w for w in gamma_walls if w.mid > price]
        walls_below = [w for w in gamma_walls if w.mid < price]
        call_wall = max(walls_above, key=lambda w: w.strength).mid if walls_above else None
        put_wall  = max(walls_below, key=lambda w: w.strength).mid if walls_below else None

        # ── Compression Boxes ─────────────────────────────────────────────────
        compression_zones: List[GEXZone] = []
        sorted_walls = sorted(gamma_walls, key=lambda w: w.mid)
        for j in range(1, len(sorted_walls)):
            w0, w1 = sorted_walls[j - 1], sorted_walls[j]
            gap = (w1.mid - w0.mid) / atr14
            if 0 < gap < self.COMPRESS_MAX_GAP:
                comp_mid = (w0.mid + w1.mid) / 2.0
                comp_h   = w1.mid - w0.mid
                tgt      = (w1.mid + comp_h) if price >= comp_mid else (w0.mid - comp_h)
                compression_zones.append(GEXZone(
                    price_low=w0.price_low,
                    price_high=w1.price_high,
                    zone_type="COMPRESSION",
                    strength=(w0.strength + w1.strength) / 2.0,
                    mid=comp_mid,
                    target=tgt,
                ))

        # ── GEX zone at mark price ─────────────────────────────────────────────
        pi  = min(range(len(strikes)), key=lambda i: abs(strikes[i] - price))
        cgx = gex_vals[pi]
        if cgx > max_abs * 0.08:    zone = "POSITIVE"
        elif cgx < -max_abs * 0.08: zone = "NEGATIVE"
        else:                        zone = "NEUTRAL"

        # ── Nearest flips ─────────────────────────────────────────────────────
        fa   = sorted([fl.price for fl in flip_levels if fl.price > price])
        fb   = sorted([fl.price for fl in flip_levels if fl.price < price], reverse=True)
        nf_up = fa[0] if fa else None
        nf_dn = fb[0] if fb else None

        # ── VWAP + ATR bands ──────────────────────────────────────────────────
        vwap_val = _vwap(closes, highs, lows, volumes) or price
        vwap_p1  = vwap_val + atr14
        vwap_m1  = vwap_val - atr14
        vwap_p2  = vwap_val + 2.0 * atr14
        vwap_m2  = vwap_val - 2.0 * atr14

        # ── Expected Move ─────────────────────────────────────────────────────
        horizon = self.HORIZON.get(timeframe, 96)
        if n >= 20:
            ret_series = [
                abs(closes[i] - closes[i - 1]) / closes[i - 1]
                for i in range(max(1, n - 30), n)
                if closes[i - 1] > 0
            ]
            hv_pct = sum(ret_series) / len(ret_series) if ret_series else atr14 / max(price, 1e-10)
        else:
            hv_pct = atr14 / max(price, 1e-10)
        exp_move = price * hv_pct * math.sqrt(horizon)
        exp_up   = vwap_val + exp_move
        exp_dn   = vwap_val - exp_move

        # ── VOL TRIGGERS ─────────────────────────────────────────────────────
        # VOL TRIGGER UP — must be strictly above price
        vol_up_cands = [vwap_p2, gfp + exp_move * 1.5]
        if call_wall:
            vol_up_cands.append(call_wall + atr14 * 0.5)
        vol_trigger_up = max(vol_up_cands)
        # Safety: always above price
        vol_trigger_up = max(vol_trigger_up, price + atr14 * 2.0)

        # VOL TRIGGER DN — must be strictly below price
        vol_dn_cands = [vwap_m2, gfp - exp_move * 1.5]
        if put_wall:
            vol_dn_cands.append(put_wall - atr14 * 0.5)
        vol_trigger_dn = min(vol_dn_cands)
        # Safety: always below price
        vol_trigger_dn = min(vol_trigger_dn, price - atr14 * 2.0)

        # ── 50 EMA ────────────────────────────────────────────────────────────
        ema50 = _ema(closes, min(50, n - 1)) if n >= 10 else None

        # ── Vanna proxy ───────────────────────────────────────────────────────
        fund_abs   = abs(fund_rate)
        oi_acc     = abs(oi_delta) / 100.0
        vanna_raw  = fund_abs * oi_acc
        vanna_norm = min(1.0, vanna_raw * 5000)
        vanna_up   = exp_up  - atr14 * 0.35
        vanna_dn   = exp_dn  + atr14 * 0.35
        vanna_line = gfp * 0.55 + vwap_val * 0.45

        if   vanna_norm > 0.6: vanna_state = "Active"
        elif vanna_norm > 0.3: vanna_state = "Unstable"
        else:                  vanna_state = "Stable"

        # ── Charm Decay ───────────────────────────────────────────────────────
        now_utc   = datetime.now(timezone.utc)
        h_utc     = now_utc.hour + now_utc.minute / 60.0
        # Funding every 8h at 00:00, 08:00, 16:00 UTC
        fund_hrs  = [0.0, 8.0, 16.0, 24.0]
        hrs_to_f  = min((fh - h_utc) % 24.0 for fh in fund_hrs)
        hrs_to_f  = max(hrs_to_f, 0.1)
        charm_raw = min(1.0, fund_abs * 1200.0 * (1.0 / hrs_to_f))

        if   charm_raw > 0.5: charm_state = "ACTIVE"
        elif charm_raw > 0.2: charm_state = "Moderate"
        else:                  charm_state = "Low"

        # ── Dealer Flow in $M ─────────────────────────────────────────────────
        # OI (contracts) × price → OI in USD → × fund_rate → hedging flow estimate
        # Positive = dealers net long (call-side hedging)
        # Negative = dealers net short (put-side hedging)
        oi_usd          = oi * price             # Convert contracts → USD notional
        dealer_flow_usd = fund_rate * oi_usd     # Hedging flow proxy
        dealer_flow_m   = dealer_flow_usd / 1_000_000.0

        # ── Delta Bias ────────────────────────────────────────────────────────
        delta_bull = 0.0
        delta_bear = 0.0
        if fund_rate < -0.0001:  delta_bull += 2.0
        elif fund_rate > 0.0001: delta_bear += 2.0
        if oi_delta > 1.0 and fund_rate < 0:   delta_bull += 1.5
        if oi_delta > 1.0 and fund_rate > 0:   delta_bear += 1.5
        if oi_delta < -1.0 and fund_rate > 0:  delta_bull += 1.0
        if price > vwap_val:                    delta_bull += 1.0
        else:                                   delta_bear += 1.0
        if ema50 and price > ema50:             delta_bull += 1.0
        elif ema50 and price < ema50:           delta_bear += 1.0
        # RSI contribution
        if rsi14 > 55:  delta_bull += 0.5
        elif rsi14 < 45: delta_bear += 0.5
        # Stochastic contribution
        if stoch_k > 60: delta_bull += 0.5
        elif stoch_k < 40: delta_bear += 0.5

        if   delta_bull > delta_bear * 1.2: delta_bias = "Net Bullish"
        elif delta_bear > delta_bull * 1.2: delta_bias = "Net Bearish"
        else:                                delta_bias = "Neutral"

        # ── GEX Regime: LONG GAMMA / SHORT GAMMA ─────────────────────────────
        if zone == "POSITIVE":
            gex_regime = "LONG GAMMA"
        elif zone == "NEGATIVE":
            gex_regime = "SHORT GAMMA"
        else:
            gex_regime = "FLIP ZONE"

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
        score = 0.0

        # 1. Flip proximity (0–20)
        flip_dist_norm = max(0.0, 1.0 - dist_to_flip / (atr14 * 3.0))
        score += flip_dist_norm * 20.0

        # 2. GEX flip strength (0–15)
        if true_flips:
            best_str = max(fl.strength for fl in true_flips)
            score += (best_str / 100.0) * 15.0

        # 3. RV Ratio deviation (0–15)
        rv_dev = abs(rv_ratio - 1.0)
        score += min(rv_dev * 30.0, 15.0)

        # 4. Funding intensity (0–15)
        score += min(fund_abs * 30000.0, 15.0)

        # 5. OI delta (0–10)
        score += min(abs(oi_delta) * 2.0, 10.0)

        # 6. Vanna activation (0–10)
        score += vanna_norm * 10.0

        # 7. Charm decay (0–10)
        score += charm_raw * 10.0

        # 8. Vol trigger proximity (0–5)
        dist_vol_up = abs(price - vol_trigger_up) / atr14
        dist_vol_dn = abs(price - vol_trigger_dn) / atr14
        vol_prox    = max(0.0, 1.0 - min(dist_vol_up, dist_vol_dn) / 5.0)
        score += vol_prox * 5.0

        # 9. Volume spike bonus (0–5)
        if vol_spike:
            score += 5.0

        # 10. IV Proxy Z-score contribution — elevated IV boosts DGRP (0–8)
        # High absolute Z = large vol deviation = more regime significance
        score += min(abs(iv_proxy_z) * 2.5, 8.0)

        # 11. Stochastic alignment with delta bias (0–4)
        # Aligned stoch+delta boost signal quality
        if delta_bias == "Net Bullish" and stoch_k > 55:
            score += min((stoch_k - 55) / 5.0, 4.0)
        elif delta_bias == "Net Bearish" and stoch_k < 45:
            score += min((45 - stoch_k) / 5.0, 4.0)

        dgrp_score = min(100.0, max(0.0, score))

        # ── Bias scoring (comprehensive, 15 layers) ───────────────────────────
        bull, bear = 0.0, 0.0

        if fund_rate < -0.0001:    bull += 2.5
        elif fund_rate < 0:         bull += 1.0
        elif fund_rate > 0.0001:    bear += 2.5
        else:                        bear += 0.5

        if oi_delta < -1.0 and fund_rate > 0:   bull += 2.0
        elif oi_delta > 1.0 and fund_rate > 0:  bear += 2.0
        elif oi_delta > 1.0 and fund_rate < 0:  bull += 1.5
        elif oi_delta < -1.0 and fund_rate < 0: bear += 1.5

        if price > vwap_val + atr14 * 0.15:  bull += 2.0
        elif price < vwap_val - atr14 * 0.15: bear += 2.0
        else:                                   bull += 0.5; bear += 0.5

        if ema50:
            if price > ema50:  bull += 2.0
            else:               bear += 2.0

        if rsi14 > 62:    bull += 1.5
        elif rsi14 < 38:  bear += 1.5
        elif rsi14 > 55:  bull += 0.5
        elif rsi14 < 45:  bear += 0.5

        # Stochastic K
        if stoch_k > 70:   bull += 1.0
        elif stoch_k < 30:  bear += 1.0
        elif stoch_k > 55:  bull += 0.5
        elif stoch_k < 45:  bear += 0.5

        # Nearest flip asymmetry
        if nf_up and nf_dn:
            ud = nf_up - price
            dd = price - nf_dn
            if dd > 0 and ud < dd * 0.5:   bear += 1.5
            elif ud > 0 and dd < ud * 0.5: bull += 1.5

        # GEX zone
        if zone == "NEGATIVE":
            if fund_rate < 0: bull += 1.0
            else:              bear += 1.5
        elif zone == "POSITIVE":
            pass  # Pinned — neutral directional bias

        # Charm near funding
        if charm_raw > 0.5:
            if fund_rate < 0: bull += 1.0
            else:              bear += 1.0

        # Volume spike alignment
        if vol_spike:
            last_close = closes[-1]
            last_open  = opens[-1] if opens else last_close
            if last_close > last_open:   bull += 1.0
            elif last_close < last_open: bear += 1.0

        # OPEX week penalty
        opex = _is_opex_week()
        if opex:
            bull *= 0.85
            bear *= 0.85

        tot = bull + bear
        if   bull > bear * 1.1:  bias = "BULLISH"
        elif bear > bull * 1.1:  bias = "BEARISH"
        else:                     bias = "NEUTRAL"

        dom = max(bull, bear) / tot if tot > 0 else 0.5
        base_conf = 45.0 + dom * 55.0

        # True flip count bonus — mutually exclusive tiers (elif prevents double-add)
        if len(true_flips) >= 3:    base_conf = min(base_conf + 10.0, 96.0)
        elif len(true_flips) >= 2:  base_conf = min(base_conf + 5.0,  96.0)
        elif len(true_flips) >= 1:  base_conf = min(base_conf + 2.0,  96.0)

        if in_comp:                  base_conf = min(base_conf + 6.0, 96.0)
        if regime == "FLIP ZONE":   base_conf = min(base_conf + 4.0, 96.0)
        if opex:                     base_conf = max(base_conf - 8.0, 40.0)
        if dgrp_score > 60:          base_conf = min(base_conf + 6.0, 96.0)
        elif dgrp_score < 30:        base_conf  = max(base_conf - 6.0, 40.0)  # floored at 40
        if vol_spike:                base_conf = min(base_conf + 3.0, 96.0)
        # Stochastic overbought/oversold alignment bonus
        if stoch_k < 20 and bias == "BULLISH":  base_conf = min(base_conf + 3.0, 96.0)
        if stoch_k > 80 and bias == "BEARISH":  base_conf = min(base_conf + 3.0, 96.0)
        # Final clamp
        base_conf = max(30.0, min(96.0, base_conf))

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
            signal_state="No Signal",
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
            vol_avg=vol_avg_20,
            vol_last=vol_last,
            vol_spike=vol_spike,
            rsi=rsi14,
            stoch_k=stoch_k,
            stoch_d=stoch_d,
            vpoc=vpoc,
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
        min_confidence: float = 68.0,
        confirm_snap: Optional[GEXSnapshot] = None,
    ) -> Optional[GEXSignal]:
        """
        Detect GEX flip crossover between two consecutive real-time snapshots.

        Signal quality gates (ALL must pass):
           1. Confidence ≥ min_confidence (default 68%)
           2. DGRP Score ≥ MIN_DGRP (40)
           3. Bias not NEUTRAL (requires directional conviction)
           4. Vol spike OR DGRP ≥ 58 (raised from 55 for quality)
           5. ATR-adaptive price move ≥ max(0.025%, 0.20 × ATR/price)
           6. GEX flip crossover (≥65 strength outside FLIP ZONE)
              OR compression break OR vanna entry
           7. Bias alignment — signal direction must match snapshot bias
           8. 15m DGRP ≥ 25 (multi-TF context gate)
           9. OPEX week: confidence ≥ min_confidence + 5%
          10. 15m confirmation bias aligned (if confirm_snap provided)
          11. VWAP directional filter (within 0.3 ATR exception)
          12. Momentum direction: price delta agrees with signal
          13. EMA50 trend alignment (within 1.0 ATR exception)
          14. Funding rate alignment (crowded-trade filter)
          15. OI delta alignment (smart-money flow filter)
          16. IV Z ≤ 3.0 (explosive-vol protection)
          17. ATR overextension guard (≤ 1.5 ATR between scans)
          18. Stoch/RSI extreme filter (no deep overbought/oversold)
          19. Stochastic K/D cross alignment (momentum quality)
          20. R:R ≥ 2.8 (≥3.0 typical with ATR-adaptive dynamic SL)

        SL  : ATR-adaptive dynamic SL — tightest technical level within
              [max(0.05%, 0.4×ATR), min(0.18%, 1.2×ATR)] budget.
        TP1 : FIXED entry × TP1_PCT (0.54%)
        TP2 : FIXED entry × TP2_PCT (1.08%)
        TP3 : Base 1.62%; extended to GEX wall or compression target
        """
        if snap_curr.confidence < min_confidence:
            return None

        if snap_curr.dgrp_score < self.MIN_DGRP:
            return None

        # Require directional conviction
        if snap_curr.bias == "NEUTRAL":
            return None

        # Volume gate: need spike OR high DGRP (raised threshold for quality)
        if not snap_curr.vol_spike and snap_curr.dgrp_score < 58.0:
            return None

        pp = snap_prev.mark_price
        cp = snap_curr.mark_price

        if pp <= 0 or cp <= 0:
            return None

        price_move_pct = abs(cp - pp) / pp
        # ATR-adaptive minimum move: max(0.025%, 0.20 × ATR/price).
        # Prevents false signals on slow-moving coins where 0.025% is noise.
        atr_move_min = max(self.MIN_PRICE_MOVE,
                           snap_curr.atr / max(cp, 1e-10) * 0.20)
        if price_move_pct < atr_move_min:
            return None

        flips = snap_curr.all_flip_levels
        if not flips:
            return None

        crossed: Optional[GEXLevel] = None
        action   = ""
        sig_type = "GEX_FLIP"
        comp_hit: Optional[GEXZone] = None

        # ── 1. GEX Flip crossover (strongest first) ────────────────────────────
        # AEGIS GEX v1.0 core: GEX_FLIP signals REQUIRE the FLIP ZONE regime —
        # only fire when price is at the actual gamma boundary (high-precision entry).
        is_flip_zone = snap_curr.regime == "FLIP ZONE"
        for fl in sorted(flips, key=lambda x: x.strength, reverse=True):
            fp = fl.price
            # Outside FLIP ZONE: require high-strength flip (≥65) for precision
            if not is_flip_zone and fl.strength < 65.0:
                continue
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
                                   is_flip=True, strength=52.0,
                                   level_type="FLIP_UP",
                                   timeframe=flips[0].timeframe if flips else "5m")
                action = "BUY"; sig_type = "VANNA_ENTRY"
            elif cp < ve <= pp:
                crossed = GEXLevel(price=ve, gex_value=snap_curr.net_gex,
                                   is_flip=True, strength=52.0,
                                   level_type="FLIP_DOWN",
                                   timeframe=flips[0].timeframe if flips else "5m")
                action = "SELL"; sig_type = "VANNA_ENTRY"

        if not crossed or not action:
            return None

        # ── Bias alignment check ───────────────────────────────────────────────
        # Signal direction must align with snapshot bias
        if action == "BUY"  and snap_curr.bias == "BEARISH":
            return None
        if action == "SELL" and snap_curr.bias == "BULLISH":
            return None

        # ── Multi-timeframe DGRP quality gate ────────────────────────────────────
        # If the 15m DGRP is extremely weak, the higher-TF regime provides no
        # dealer flow context — reject to avoid low-context signals.
        if confirm_snap is not None and confirm_snap.dgrp_score < 25.0:
            return None

        # ── OPEX week hard confidence gate ────────────────────────────────────
        # During OPEX week, dealer repositioning creates unpredictable gamma
        # spikes. Require 5% extra confidence above the normal threshold.
        if snap_curr.is_opex_week and snap_curr.confidence < min_confidence + 5.0:
            return None

        # ── 15m Confirmation alignment ─────────────────────────────────────────
        confirm_boost = 0.0
        if confirm_snap is not None:
            if confirm_snap.bias != "NEUTRAL":
                if action == "BUY"  and confirm_snap.bias == "BEARISH":
                    return None
                if action == "SELL" and confirm_snap.bias == "BULLISH":
                    return None
                # Both timeframes have same non-neutral bias: quality boost
                if (action == "BUY"  and confirm_snap.bias == "BULLISH") or \
                   (action == "SELL" and confirm_snap.bias == "BEARISH"):
                    confirm_boost += 3.0
            # 15m DGRP alignment — strong 15m DGRP boosts signal confidence
            if confirm_snap.dgrp_score >= 55:
                confirm_boost += 2.0
            if confirm_snap.dgrp_score >= 70:
                confirm_boost += 2.0
            # 15m FLIP ZONE alignment = strongest confirmation
            if confirm_snap.regime == "FLIP ZONE":
                confirm_boost += 3.0
            # 15m LONG GAMMA regime = price pinned; require extra confidence
            if confirm_snap.gex_regime == "LONG GAMMA" and snap_curr.confidence < min_confidence + 8:
                return None
            # 15m vol spike additional quality signal
            if confirm_snap.vol_spike:
                confirm_boost += 2.0

        # ── VWAP directional filter ───────────────────────────────────────────────
        # Price must be on the correct side of VWAP for the signal direction.
        # Exception: tightened to 0.3 ATR — only allow VWAP-crossing entries
        # (price is right at the VWAP boundary, not far on the wrong side).
        vwap = snap_curr.vwap
        atr  = snap_curr.atr
        near_vwap = abs(cp - vwap) < atr * 0.3
        if not near_vwap:
            if action == "BUY"  and cp < vwap:
                return None   # Price below VWAP — bias against long
            if action == "SELL" and cp > vwap:
                return None   # Price above VWAP — bias against short

        # ── Momentum direction confirmation ───────────────────────────────────
        # The price move between scan intervals must agree with the action.
        # Prevents entering on counter-trend whipsaws at the flip level.
        price_delta = cp - pp
        if action == "BUY"  and price_delta < 0 and abs(price_delta) > atr * 0.05:
            return None   # Price dropping into the flip — wait for momentum
        if action == "SELL" and price_delta > 0 and abs(price_delta) > atr * 0.05:
            return None   # Price rising into the flip — wait for momentum

        # ── EMA50 trend alignment filter ─────────────────────────────────────
        # Reject signals where price is significantly on the wrong side of EMA50.
        # Allows signals within 1.0 ATR of EMA50 (crossing / testing EMA50).
        ema50_val = snap_curr.ema50
        if ema50_val and ema50_val > 0:
            if action == "BUY"  and cp < ema50_val - atr * 1.0:
                return None   # Price > 1 ATR below EMA50 — downtrend
            if action == "SELL" and cp > ema50_val + atr * 1.0:
                return None   # Price > 1 ATR above EMA50 — uptrend

        # ── Funding rate alignment filter ─────────────────────────────────────
        # Extreme funding against the signal direction = crowded trade,
        # increased risk of snap-back. Threshold: 0.08% per 8h session.
        fr = snap_curr.funding_rate
        if action == "BUY"  and fr >  0.0008:
            return None   # Crowded long — elevated squeeze risk
        if action == "SELL" and fr < -0.0008:
            return None   # Crowded short — elevated squeeze risk

        # ── OI delta alignment filter ─────────────────────────────────────────
        # Large OI drops against the signal direction indicate smart money
        # closing positions — opposing signal conviction.
        oi_d = snap_curr.oi_delta_pct
        if action == "BUY"  and oi_d < -8.0:
            return None   # Heavy long closing — bad for new long
        if action == "SELL" and oi_d >  8.0:
            return None   # Heavy open interest surge — short squeeze risk

        # ── IV overload protection ────────────────────────────────────────────
        # IV Proxy Z > 3.0 = explosive vol regime; entries are unpredictable
        if abs(snap_curr.iv_proxy_z) > 3.0:
            return None

        # ── ATR overextension filter ──────────────────────────────────────────
        # If the move between prev and curr already covers > 1.5 ATR, the
        # entry is too late — the bulk of the move has already happened.
        if price_move_pct > (atr / max(cp, 1e-10)) * 1.5:
            return None

        # ── Stochastic / RSI extreme filter ───────────────────────────────────
        # Avoid chasing overbought BUY or oversold SELL entries
        sk  = snap_curr.stoch_k
        sd  = snap_curr.stoch_d
        rsi = snap_curr.rsi
        if action == "BUY":
            if sk > 82 and rsi > 70:
                return None   # Deep overbought — wait for pullback
            if rsi < 35 and snap_curr.delta_bias != "Net Bullish":
                return None   # RSI too weak without strong bullish delta
        if action == "SELL":
            if sk < 18 and rsi < 30:
                return None   # Deep oversold — wait for bounce
            if rsi > 65 and snap_curr.delta_bias != "Net Bearish":
                return None   # RSI too strong without bearish delta

        # ── Stochastic K/D momentum cross alignment ───────────────────────────
        # %K must be consistent with signal direction relative to %D.
        # A wide adverse divergence (K vs D) signals fading momentum.
        # Tolerance of 8 points allows entries near the crossover itself.
        if action == "BUY"  and sk < sd - 8.0 and sk < 60:
            return None   # %K trending down through %D — momentum against long
        if action == "SELL" and sk > sd + 8.0 and sk > 40:
            return None   # %K trending up through %D — momentum against short

        entry = cp  # Real-time mark price as entry

        # ── SL: dynamic anchor + fixed 0.18 % hard cap ────────────────────────
        # TPs: strictly fixed from entry (never modified except TP3 extension)
        if action == "BUY":
            # SL placed at the tightest meaningful technical level ≤ 0.18 % below
            sl  = _dynamic_sl(entry, "BUY", snap_curr)
            tp1 = entry * (1.0 + TP1_PCT)  # 0.54 % — FIXED
            tp2 = entry * (1.0 + TP2_PCT)  # 1.08 % — FIXED
            tp3 = entry * (1.0 + TP3_PCT)  # 1.62 % base, may extend
            # Extend TP3 to call wall if it is above the base TP3
            if snap_curr.call_wall and snap_curr.call_wall > tp3:
                tp3 = snap_curr.call_wall
            gex_to   = "POSITIVE"
            gex_from = snap_prev.current_gex_zone
        else:
            # SL placed at the tightest meaningful technical level ≤ 0.18 % above
            sl  = _dynamic_sl(entry, "SELL", snap_curr)
            tp1 = entry * (1.0 - TP1_PCT)  # 0.54 % — FIXED
            tp2 = entry * (1.0 - TP2_PCT)  # 1.08 % — FIXED
            tp3 = entry * (1.0 - TP3_PCT)  # 1.62 % base, may extend
            # Extend TP3 to put wall if it is below the base TP3
            if snap_curr.put_wall and snap_curr.put_wall < tp3:
                tp3 = snap_curr.put_wall
            gex_to   = "NEGATIVE"
            gex_from = snap_prev.current_gex_zone

        # TP3 extension via compression measured-move target
        # TP1 and TP2 are STRICTLY FIXED at 0.54% and 1.08% — never modified
        # Only TP3 (1.62% base) can be extended if compression target is favourable
        if sig_type == "COMPRESSION_BREAK" and comp_hit and comp_hit.target:
            ct = comp_hit.target
            if action == "BUY" and ct > tp2:
                tp3 = max(tp3, ct)   # Only extend TP3 if target is beyond TP2
            elif action == "SELL" and ct < tp2:
                tp3 = min(tp3, ct)   # Only extend TP3 downward for SELL

        # ── R:R validation ───────────────────────────────────────────────────────
        # SL is dynamically placed (≤ 0.18 % from entry), so R:R ≥ 3.0.
        # Floor at 2.8 absorbs floating-point edge cases on the rare fallback path.
        risk   = abs(entry - sl)
        reward = abs(tp1 - entry)
        if risk <= 0:
            return None
        rr = reward / risk
        if rr < 2.8:
            return None

        # ── Final confidence (5m base + 15m confirmation boost) ───────────────
        final_conf = min(96.0, snap_curr.confidence + confirm_boost)

        # ── Leverage (confidence / regime based) ──────────────────────────────
        conf = final_conf
        if conf >= 88:   lev = 20
        elif conf >= 80: lev = 15
        elif conf >= 74: lev = 12
        elif conf >= 68: lev = 10
        else:            lev = 8
        # Reduce leverage in OPEX week
        if snap_curr.is_opex_week:
            lev = max(5, lev - 3)
        # Reduce leverage in FLIP ZONE (higher uncertainty)
        if snap_curr.regime == "FLIP ZONE" and lev > 12:
            lev = 12
        # Cap leverage based on IV proxy Z — high IV = more risk
        if abs(snap_curr.iv_proxy_z) > 2.0 and lev > 10:
            lev = 10

        return GEXSignal(
            symbol=snap_curr.symbol,
            action=action,
            direction="LONG" if action == "BUY" else "SHORT",
            signal_type=sig_type,
            entry_price=entry,
            entry_flip_level=crossed.price,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            sl=sl,
            confidence=final_conf,
            timeframe=flips[0].timeframe if flips else "5m",
            gex_zone_from=gex_from,
            gex_zone_to=gex_to,
            leverage=lev,
            rr_ratio=round(rr, 2),   # Actual R:R — ≥3.0, higher when SL is tightened
            bias=snap_curr.bias,
            atr=snap_curr.atr,
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
            nearest_compression=comp_hit,
            snapshot=snap_curr,
        )
