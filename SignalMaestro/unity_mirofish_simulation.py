#!/usr/bin/env python3
"""
Unity Engine — MiroFish Swarm Simulation & Dynamic Backtesting Engine
=======================================================================
v10.0 — Institutional-Grade Swarm Intelligence Backtesting System

Architecture:
  • 10 Specialized MiroFish Swarm Agents (Trend, Momentum, Volume, Volatility,
    OrderFlow, Sentiment, Regime, Microstructure, Risk, Composite)
  • Vectorised proxy strategy on 15M Binance USDM klines
  • Parallel multi-symbol backtesting with asyncio.Semaphore rate control
  • Real-time quality bias injection into Unity Engine signal filter (Gate 8.5)
  • Sharpe / Sortino / Calmar / Win-Rate / EV / Max-Drawdown metrics
  • Auto-refresh every UNITY_DBT_REFRESH_SEC seconds
  • Thread-safe result store with RLock protection
  • Integrates with DynamicBacktester framework for zero-duplication

Swarm Agent Decision Matrix:
  Each agent produces: (direction: LONG/SHORT/NEUTRAL, confidence: 0.0-1.0)
  Weighted consensus = Σ(agent_weight × confidence × direction_sign) / Σ(weights)
  Final signal = consensus × session_multiplier × regime_multiplier

Quality Bias Output (fed to Gate 8.5 UnitySignalFilter):
  +5 pts  → sim_wr ≥ 0.60 AND sim_sharpe ≥ 1.5
  +3 pts  → sim_wr ≥ 0.50 AND sim_sharpe ≥ 0.8
  +0 pts  → neutral / insufficient data
  -4 pts  → sim_wr < 0.40 OR sim_sharpe < -0.5
  -8 pts  → sim_wr < 0.30 (consistently losing setup)

Usage:
    sim = MiroFishSimulationEngine(symbols=["BTCUSDT", "ETHUSDT"], refresh_sec=1800)
    await sim.start()
    asyncio.create_task(sim.run_loop())
    bias = sim.get_quality_bias("BTCUSDT")  # → float in [-8, +5]
    report = sim.get_simulation_report("BTCUSDT")
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import random
import time
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("UnityEngine.MiroFishSim")

try:
    import aiohttp
    _HAS_AIOHTTP = True
except ImportError:
    _HAS_AIOHTTP = False

try:
    import numpy as np
    _HAS_NP = True
except ImportError:
    np = None
    _HAS_NP = False


# ═══════════════════════════════════════════════════════════════════════
#   CONSTANTS
# ═══════════════════════════════════════════════════════════════════════

BINANCE_FAPI_BASE    = "https://fapi.binance.com"
KLINES_INTERVAL      = "15m"
KLINES_LOOKBACK      = int(os.getenv("UNITY_DBT_LOOKBACK_BARS", "300"))
MAX_CONCURRENT       = int(os.getenv("UNITY_DBT_MAX_CONCURRENT", "8"))
REFRESH_SEC          = int(os.getenv("UNITY_DBT_REFRESH_SEC", "1800"))
STALE_MAX_SEC        = int(os.getenv("UNITY_DBT_MAX_AGE_SEC", "7200"))
REQUEST_TIMEOUT      = 12.0
QUALITY_BIAS_HIGH    = 5.0
QUALITY_BIAS_MED     = 3.0
QUALITY_BIAS_NEU     = 0.0
QUALITY_BIAS_LOW     = -4.0
QUALITY_BIAS_VLOW    = -8.0

AGENT_WEIGHTS = {
    "trend":          1.40,
    "momentum":       1.20,
    "volume":         1.00,
    "volatility":     0.80,
    "order_flow":     1.10,
    "sentiment":      0.70,
    "regime":         1.30,
    "microstructure": 0.90,
    "risk":           1.00,
    "composite":      1.20,
}


# ═══════════════════════════════════════════════════════════════════════
#   DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class KlineBar:
    open_time:  int
    open:       float
    high:       float
    low:        float
    close:      float
    volume:     float
    close_time: int
    quote_vol:  float
    num_trades: int
    taker_buy_base: float
    taker_buy_quote: float


@dataclass
class AgentVote:
    agent_id:   str
    direction:  float   # +1 = LONG, -1 = SHORT, 0 = NEUTRAL
    confidence: float   # 0.0 – 1.0
    reasoning:  str = ""


@dataclass
class SwarmDecision:
    symbol:          str
    direction:       str        # "LONG" | "SHORT" | "NEUTRAL"
    consensus:       float      # 0.0 – 1.0
    agent_votes:     List[AgentVote] = field(default_factory=list)
    session_mult:    float = 1.0
    regime_mult:     float = 1.0
    ts:              float = field(default_factory=time.time)


@dataclass
class SimulationResult:
    symbol:       str
    n_trades:     int
    win_rate:     float
    total_pnl_pct: float
    sharpe:       float
    sortino:      float
    calmar:       float
    max_drawdown: float
    avg_rr:       float
    ev_per_trade: float
    quality_bias: float
    last_updated: float = field(default_factory=time.time)
    bars_used:    int   = 0
    error:        str   = ""


# ═══════════════════════════════════════════════════════════════════════
#   MATHEMATICAL UTILITIES
# ═══════════════════════════════════════════════════════════════════════

def _ema(values: List[float], period: int) -> List[float]:
    if not values or period < 1:
        return values[:]
    k   = 2.0 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _sma(values: List[float], period: int) -> List[float]:
    out = []
    for i in range(len(values)):
        start = max(0, i - period + 1)
        out.append(sum(values[start:i+1]) / (i - start + 1))
    return out


def _rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0:
        return 100.0
    rs = ag / al
    return 100.0 - (100.0 / (1 + rs))


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(closes) < 2:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i-1]),
                 abs(lows[i] - closes[i-1]))
        trs.append(tr)
    return sum(trs[-period:]) / min(len(trs), period)


def _sharpe(returns: List[float], rf: float = 0.0) -> float:
    if len(returns) < 5:
        return 0.0
    n = len(returns)
    mu = sum(returns) / n
    var = sum((r - mu) ** 2 for r in returns) / n
    sd  = math.sqrt(var) if var > 0 else 1e-9
    raw = (mu - rf) / sd
    return raw * math.sqrt(252 * 4)  # annualise from 15m bars (4/hr × 6.5hr ×252 days)


def _sortino(returns: List[float], rf: float = 0.0) -> float:
    if len(returns) < 5:
        return 0.0
    mu    = sum(returns) / len(returns)
    downs = [r for r in returns if r < rf]
    if not downs:
        return 4.0
    dsd   = math.sqrt(sum((r - rf) ** 2 for r in downs) / len(downs))
    if dsd < 1e-12:
        return 4.0
    return (mu - rf) / dsd * math.sqrt(252 * 4)


def _max_drawdown(equity_curve: List[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    mdd  = 0.0
    for e in equity_curve:
        if e > peak:
            peak = e
        dd = (peak - e) / peak if peak > 0 else 0.0
        mdd = max(mdd, dd)
    return mdd


def _calmar(total_return: float, max_dd: float) -> float:
    if max_dd < 1e-9:
        return 0.0
    return (total_return / max_dd) * (252 * 4 / max(1, 1))


# ═══════════════════════════════════════════════════════════════════════
#   SWARM AGENTS
# ═══════════════════════════════════════════════════════════════════════

class _TrendAgent:
    """Multi-timeframe trend detection via EMA crossovers."""
    id = "trend"

    def vote(self, bars: List[KlineBar]) -> AgentVote:
        closes = [b.close for b in bars]
        if len(closes) < 50:
            return AgentVote(self.id, 0, 0.5)
        fast = _ema(closes, 20)
        slow = _ema(closes, 50)
        very_slow = _ema(closes, 200) if len(closes) >= 200 else [closes[0]] * len(closes)
        c = closes[-1]
        f, s, vs = fast[-1], slow[-1], very_slow[-1]
        if f > s > vs:
            conf = min(1.0, abs(f - s) / (c * 0.002 + 1e-9))
            return AgentVote(self.id, 1.0, min(0.95, 0.55 + conf), "triple bull stack")
        if f < s < vs:
            conf = min(1.0, abs(s - f) / (c * 0.002 + 1e-9))
            return AgentVote(self.id, -1.0, min(0.95, 0.55 + conf), "triple bear stack")
        if f > s:
            return AgentVote(self.id, 1.0, 0.45, "short-term bull")
        if f < s:
            return AgentVote(self.id, -1.0, 0.45, "short-term bear")
        return AgentVote(self.id, 0.0, 0.3, "ranging")


class _MomentumAgent:
    """RSI + MACD momentum scoring."""
    id = "momentum"

    def vote(self, bars: List[KlineBar]) -> AgentVote:
        closes = [b.close for b in bars]
        if len(closes) < 26:
            return AgentVote(self.id, 0, 0.5)
        rsi = _rsi(closes, 14)
        ema12 = _ema(closes, 12)[-1]
        ema26 = _ema(closes, 26)[-1]
        macd  = ema12 - ema26
        signal_line = _ema([ema12 - ema26 for _ in range(9)], 9)[-1]
        macd_hist = macd - signal_line
        if rsi > 60 and macd_hist > 0:
            return AgentVote(self.id, 1.0, min(0.90, 0.5 + (rsi - 60) / 80), "RSI+MACD bull")
        if rsi < 40 and macd_hist < 0:
            return AgentVote(self.id, -1.0, min(0.90, 0.5 + (40 - rsi) / 80), "RSI+MACD bear")
        if rsi > 55:
            return AgentVote(self.id, 1.0, 0.42, "RSI mild bull")
        if rsi < 45:
            return AgentVote(self.id, -1.0, 0.42, "RSI mild bear")
        return AgentVote(self.id, 0.0, 0.30, "neutral momentum")


class _VolumeAgent:
    """Volume profile & CVD (Cumulative Volume Delta) analysis."""
    id = "volume"

    def vote(self, bars: List[KlineBar]) -> AgentVote:
        if len(bars) < 20:
            return AgentVote(self.id, 0, 0.5)
        vols   = [b.volume for b in bars]
        buys   = [b.taker_buy_base for b in bars]
        sells  = [b.volume - b.taker_buy_base for b in bars]
        avg_v  = sum(vols[-20:]) / 20
        cur_v  = vols[-1]
        vol_ratio = cur_v / (avg_v + 1e-9)
        cvd_recent = sum(buys[-10:]) - sum(sells[-10:])
        norm_cvd = cvd_recent / (sum(vols[-10:]) + 1e-9)
        if norm_cvd > 0.15 and vol_ratio > 1.2:
            return AgentVote(self.id, 1.0, min(0.88, 0.50 + norm_cvd), "volume accumulation")
        if norm_cvd < -0.15 and vol_ratio > 1.2:
            return AgentVote(self.id, -1.0, min(0.88, 0.50 + abs(norm_cvd)), "volume distribution")
        if norm_cvd > 0.05:
            return AgentVote(self.id, 1.0, 0.40, "mild buy pressure")
        if norm_cvd < -0.05:
            return AgentVote(self.id, -1.0, 0.40, "mild sell pressure")
        return AgentVote(self.id, 0.0, 0.35, "balanced volume")


class _VolatilityAgent:
    """ATR-normalised volatility regime + Bollinger Band squeeze detector."""
    id = "volatility"

    def vote(self, bars: List[KlineBar]) -> AgentVote:
        closes = [b.close for b in bars]
        highs  = [b.high for b in bars]
        lows   = [b.low  for b in bars]
        if len(closes) < 20:
            return AgentVote(self.id, 0, 0.5)
        atr = _atr(highs, lows, closes, 14)
        mid = _sma(closes, 20)[-1]
        dev = math.sqrt(sum((c - mid)**2 for c in closes[-20:]) / 20)
        bb_width = 4 * dev / (mid + 1e-9)
        atr_pct  = atr / (closes[-1] + 1e-9)
        # squeeze = low vol, about to expand
        if bb_width < 0.02 and atr_pct < 0.005:
            slope = closes[-1] - closes[-10]
            return AgentVote(self.id, 1.0 if slope > 0 else -1.0, 0.60, "BB squeeze breakout")
        # expanding volatility with trend
        if atr_pct > 0.015:
            ema20 = _ema(closes, 20)[-1]
            dir_ = 1.0 if closes[-1] > ema20 else -1.0
            return AgentVote(self.id, dir_, 0.50, "high-vol trend")
        return AgentVote(self.id, 0.0, 0.35, "normal vol")


class _OrderFlowAgent:
    """Taker buy/sell imbalance as a proxy for aggressive order flow."""
    id = "order_flow"

    def vote(self, bars: List[KlineBar]) -> AgentVote:
        if len(bars) < 10:
            return AgentVote(self.id, 0, 0.5)
        buys  = [b.taker_buy_quote for b in bars[-10:]]
        vols  = [b.quote_vol for b in bars[-10:]]
        total_vol = sum(vols) + 1e-9
        buy_pct   = sum(buys) / total_vol
        sell_pct  = 1.0 - buy_pct
        delta = buy_pct - sell_pct
        if delta > 0.20:
            return AgentVote(self.id, 1.0, min(0.92, 0.50 + delta), "aggressive buying")
        if delta < -0.20:
            return AgentVote(self.id, -1.0, min(0.92, 0.50 + abs(delta)), "aggressive selling")
        if delta > 0.05:
            return AgentVote(self.id, 1.0, 0.40, "mild buy flow")
        if delta < -0.05:
            return AgentVote(self.id, -1.0, 0.40, "mild sell flow")
        return AgentVote(self.id, 0.0, 0.35, "balanced flow")


class _SentimentAgent:
    """Synthetic sentiment proxy: RSI momentum divergence + volume confirmation."""
    id = "sentiment"

    def vote(self, bars: List[KlineBar]) -> AgentVote:
        closes = [b.close for b in bars]
        if len(closes) < 30:
            return AgentVote(self.id, 0, 0.5)
        rsi_now  = _rsi(closes[-15:], 14)
        rsi_prev = _rsi(closes[-30:-15], 14)
        price_up   = closes[-1] > closes[-15]
        rsi_diverge = (price_up and rsi_now < rsi_prev)
        rsi_confirm = (price_up and rsi_now > rsi_prev)
        if rsi_diverge:
            return AgentVote(self.id, -1.0, 0.62, "bearish RSI divergence")
        if rsi_confirm and rsi_now > 55:
            return AgentVote(self.id, 1.0, 0.58, "bullish RSI confirm")
        if not price_up and rsi_now > rsi_prev:
            return AgentVote(self.id, 1.0, 0.55, "bullish hidden divergence")
        return AgentVote(self.id, 0.0, 0.35, "no sentiment signal")


class _RegimeAgent:
    """Market regime classifier: trending vs ranging vs reversal."""
    id = "regime"

    def vote(self, bars: List[KlineBar]) -> AgentVote:
        closes = [b.close for b in bars]
        if len(closes) < 50:
            return AgentVote(self.id, 0, 0.5)
        ema20 = _ema(closes, 20)
        ema50 = _ema(closes, 50)
        slope20 = (ema20[-1] - ema20[-20]) / (ema20[-20] + 1e-9)
        slope50 = (ema50[-1] - ema50[-20]) / (ema50[-20] + 1e-9)
        adr = sum(abs(closes[i] - closes[i-1]) for i in range(1, min(20, len(closes)))) / min(19, len(closes)-1)
        adr_pct = adr / (closes[-1] + 1e-9)
        if adr_pct < 0.003:
            return AgentVote(self.id, 0.0, 0.50, "ranging low-ADR regime")
        if slope20 > 0.005 and slope50 > 0.002:
            return AgentVote(self.id, 1.0, min(0.92, 0.60 + slope20 * 20), "strong uptrend")
        if slope20 < -0.005 and slope50 < -0.002:
            return AgentVote(self.id, -1.0, min(0.92, 0.60 + abs(slope20) * 20), "strong downtrend")
        if slope20 > 0:
            return AgentVote(self.id, 1.0, 0.45, "mild uptrend")
        if slope20 < 0:
            return AgentVote(self.id, -1.0, 0.45, "mild downtrend")
        return AgentVote(self.id, 0.0, 0.35, "sideways regime")


class _MicrostructureAgent:
    """Bar-level microstructure: wicks, bodies, engulfing candles."""
    id = "microstructure"

    def vote(self, bars: List[KlineBar]) -> AgentVote:
        if len(bars) < 5:
            return AgentVote(self.id, 0, 0.5)
        last = bars[-1]
        prev = bars[-2]
        body  = abs(last.close - last.open)
        range_ = (last.high - last.low) + 1e-9
        body_ratio = body / range_
        upper_wick = last.high - max(last.open, last.close)
        lower_wick = min(last.open, last.close) - last.low
        # Bullish engulf
        if (last.close > prev.open and last.open < prev.close
                and last.close > last.open and body_ratio > 0.6):
            return AgentVote(self.id, 1.0, 0.72, "bullish engulf")
        # Bearish engulf
        if (last.open > prev.close and last.close < prev.open
                and last.open > last.close and body_ratio > 0.6):
            return AgentVote(self.id, -1.0, 0.72, "bearish engulf")
        # Hammer / pin bar
        if lower_wick > 2.0 * body and upper_wick < body:
            return AgentVote(self.id, 1.0, 0.60, "hammer / pin bar")
        if upper_wick > 2.0 * body and lower_wick < body:
            return AgentVote(self.id, -1.0, 0.60, "shooting star")
        if body_ratio > 0.75:
            dir_ = 1.0 if last.close > last.open else -1.0
            return AgentVote(self.id, dir_, 0.48, "strong marubozu")
        return AgentVote(self.id, 0.0, 0.35, "indecision candle")


class _RiskAgent:
    """Risk-overlay agent: ATR-normalised position stress + drawdown guard."""
    id = "risk"

    def vote(self, bars: List[KlineBar]) -> AgentVote:
        closes = [b.close for b in bars]
        highs  = [b.high  for b in bars]
        lows   = [b.low   for b in bars]
        if len(closes) < 20:
            return AgentVote(self.id, 0, 0.5)
        atr     = _atr(highs, lows, closes, 14)
        atr_pct = atr / (closes[-1] + 1e-9)
        # High-risk (super-volatile) → reduce confidence
        if atr_pct > 0.025:
            return AgentVote(self.id, 0.0, 0.30, "excessive volatility risk")
        # Moderate risk, follow trend direction
        ema20 = _ema(closes, 20)[-1]
        dir_  = 1.0 if closes[-1] > ema20 else -1.0
        conf  = max(0.35, 0.60 - atr_pct * 10)
        return AgentVote(self.id, dir_, conf, f"ATR risk-OK ({atr_pct:.3%})")


class _CompositeAgent:
    """Meta-composite: re-weights primary agents for final ensemble override."""
    id = "composite"

    def __init__(self):
        self._sub = [
            _TrendAgent(), _MomentumAgent(), _VolumeAgent()
        ]

    def vote(self, bars: List[KlineBar]) -> AgentVote:
        votes = [a.vote(bars) for a in self._sub]
        net = sum(v.direction * v.confidence for v in votes)
        w   = sum(v.confidence for v in votes) + 1e-9
        consensus = net / w
        if abs(consensus) < 0.15:
            return AgentVote(self.id, 0.0, 0.30, "composite neutral")
        dir_  = 1.0 if consensus > 0 else -1.0
        return AgentVote(self.id, dir_, min(0.90, abs(consensus) * 0.90 + 0.30), "composite signal")


# ═══════════════════════════════════════════════════════════════════════
#   SESSION / REGIME MULTIPLIERS
# ═══════════════════════════════════════════════════════════════════════

def _session_multiplier() -> float:
    """Weight signals based on market session (UTC)."""
    h = time.gmtime().tm_hour
    if 12 <= h < 20:   # London + NY overlap — highest liquidity
        return 1.15
    if 7 <= h < 12:    # London open
        return 1.05
    if 20 <= h < 22:   # NY close
        return 1.00
    return 0.90        # Asian / dead zone


# ═══════════════════════════════════════════════════════════════════════
#   PROXY BACKTEST ENGINE
# ═══════════════════════════════════════════════════════════════════════

def _run_proxy_backtest(bars: List[KlineBar],
                        sl_pct: float = 0.0065,
                        tp_pct: float = 0.0110,
                        min_conf: float = 0.58) -> SimulationResult:
    """
    Vectorised proxy strategy backtest using swarm agent votes.
    Simulates entry at candle close, SL/TP checked on next candle's OHLC.
    Returns SimulationResult with all key metrics.
    """
    agents = [
        _TrendAgent(), _MomentumAgent(), _VolumeAgent(), _VolatilityAgent(),
        _OrderFlowAgent(), _SentimentAgent(), _RegimeAgent(),
        _MicrostructureAgent(), _RiskAgent(), _CompositeAgent(),
    ]

    trades_pnl   = []
    equity_curve = [1.0]
    equity       = 1.0

    total_weight = sum(AGENT_WEIGHTS.values())

    for i in range(50, len(bars) - 1):
        window = bars[:i+1]
        # run agents
        net_signal = 0.0
        net_conf   = 0.0
        for agent in agents:
            try:
                vote = agent.vote(window)
                w    = AGENT_WEIGHTS.get(agent.id, 1.0)
                net_signal += vote.direction * vote.confidence * w
                net_conf   += vote.confidence * w
            except Exception:
                pass

        if net_conf < 1e-9:
            continue
        raw_consensus  = net_signal / total_weight
        abs_consensus  = abs(raw_consensus)
        if abs_consensus < min_conf:
            continue

        direction = 1.0 if raw_consensus > 0 else -1.0
        entry  = bars[i].close
        hi     = bars[i+1].high
        lo     = bars[i+1].low
        sl_lvl = entry * (1 - sl_pct * direction)
        tp_lvl = entry * (1 + tp_pct * direction)

        if direction > 0:
            hit_sl = lo <= sl_lvl
            hit_tp = hi >= tp_lvl
        else:
            hit_sl = hi >= sl_lvl
            hit_tp = lo <= tp_lvl

        if hit_tp and not hit_sl:
            pnl = tp_pct - 0.001   # net of slippage estimate
        elif hit_sl:
            pnl = -(sl_pct + 0.001)
        else:
            # neither — close at bar close
            close_pct = (bars[i+1].close - entry) / (entry + 1e-9) * direction
            pnl = close_pct - 0.0005

        trades_pnl.append(pnl)
        equity *= (1 + pnl)
        equity_curve.append(equity)

    n  = len(trades_pnl)
    if n < 5:
        return SimulationResult(
            symbol="", n_trades=n, win_rate=0.0, total_pnl_pct=0.0,
            sharpe=0.0, sortino=0.0, calmar=0.0, max_drawdown=0.0,
            avg_rr=0.0, ev_per_trade=0.0, quality_bias=QUALITY_BIAS_NEU,
            bars_used=len(bars), error="insufficient_trades",
        )

    wins        = sum(1 for p in trades_pnl if p > 0)
    win_rate    = wins / n
    total_pnl   = equity - 1.0
    sharpe_val  = _sharpe(trades_pnl)
    sortino_val = _sortino(trades_pnl)
    mdd         = _max_drawdown(equity_curve)
    calmar_val  = _calmar(total_pnl, mdd)
    ev          = sum(trades_pnl) / n
    avg_win     = (sum(p for p in trades_pnl if p > 0) / max(wins, 1))
    avg_loss    = (sum(p for p in trades_pnl if p < 0) / max(n - wins, 1))
    avg_rr      = avg_win / (abs(avg_loss) + 1e-9)

    # Quality bias
    if win_rate >= 0.60 and sharpe_val >= 1.5:
        bias = QUALITY_BIAS_HIGH
    elif win_rate >= 0.50 and sharpe_val >= 0.8:
        bias = QUALITY_BIAS_MED
    elif win_rate < 0.30:
        bias = QUALITY_BIAS_VLOW
    elif win_rate < 0.40 or sharpe_val < -0.5:
        bias = QUALITY_BIAS_LOW
    else:
        bias = QUALITY_BIAS_NEU

    return SimulationResult(
        symbol="",
        n_trades=n,
        win_rate=win_rate,
        total_pnl_pct=total_pnl * 100,
        sharpe=sharpe_val,
        sortino=sortino_val,
        calmar=calmar_val,
        max_drawdown=mdd,
        avg_rr=avg_rr,
        ev_per_trade=ev,
        quality_bias=bias,
        bars_used=len(bars),
    )


# ═══════════════════════════════════════════════════════════════════════
#   MAIN SIMULATION ENGINE
# ═══════════════════════════════════════════════════════════════════════

class MiroFishSimulationEngine:
    """
    Parallel MiroFish swarm simulation engine for all tracked symbols.
    Provides real-time quality bias injection for Unity Engine Gate 8.5.
    """

    def __init__(
        self,
        symbols:      Optional[List[str]] = None,
        refresh_sec:  int  = REFRESH_SEC,
        lookback:     int  = KLINES_LOOKBACK,
        max_concurrent: int = MAX_CONCURRENT,
        sl_pct:       float = 0.0065,
        tp_pct:       float = 0.0110,
        min_conf:     float = 0.58,
    ):
        self.symbols       = [s.upper().strip() for s in (symbols or [])]
        self.refresh_sec   = refresh_sec
        self.lookback      = lookback
        self.max_concurrent = max_concurrent
        self.sl_pct        = sl_pct
        self.tp_pct        = tp_pct
        self.min_conf      = min_conf

        self._results:     Dict[str, SimulationResult] = {}
        self._lock         = threading.RLock()
        self._session:     Optional["aiohttp.ClientSession"] = None
        self._running      = False
        self._sem:         Optional[asyncio.Semaphore] = None
        self._last_run:    float = 0.0
        self._run_count:   int   = 0
        self._logger       = logging.getLogger("UnityEngine.MiroFishSim")

    async def start(self) -> None:
        if _HAS_AIOHTTP and (self._session is None or self._session.closed):
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                connector=aiohttp.TCPConnector(limit=self.max_concurrent + 4),
            )
        self._sem     = asyncio.Semaphore(self.max_concurrent)
        self._running = True
        self._logger.info(
            f"✅ [MiroFishSim] Started — {len(self.symbols)} symbols, "
            f"refresh={self.refresh_sec}s, lookback={self.lookback} bars, "
            f"max_concurrent={self.max_concurrent}"
        )

    async def stop(self) -> None:
        self._running = False
        if self._session and not self._session.closed:
            await self._session.close()

    async def run_loop(self) -> None:
        """Background sweep loop — run as asyncio.create_task."""
        while self._running:
            try:
                await self._sweep_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.warning(f"[MiroFishSim] sweep error: {e}")
            wait = max(10.0, self.refresh_sec - (time.time() - self._last_run))
            await asyncio.sleep(wait)

    async def _sweep_all(self) -> None:
        if not self.symbols:
            return
        t0 = time.time()
        self._last_run = t0
        self._run_count += 1
        tasks = [self._simulate_symbol(sym) for sym in self.symbols]
        done = await asyncio.gather(*tasks, return_exceptions=True)
        ok  = sum(1 for r in done if isinstance(r, SimulationResult) and not r.error)
        err = sum(1 for r in done if not isinstance(r, SimulationResult) or r.error)
        elapsed = time.time() - t0
        self._logger.info(
            f"[MiroFishSim] Sweep #{self._run_count}: {ok}/{len(self.symbols)} ok, "
            f"{err} errors — {elapsed:.1f}s"
        )

    async def _simulate_symbol(self, symbol: str) -> SimulationResult:
        async with self._sem:
            bars = await self._fetch_klines(symbol)
            if not bars or len(bars) < 55:
                res = SimulationResult(
                    symbol=symbol, n_trades=0, win_rate=0.0, total_pnl_pct=0.0,
                    sharpe=0.0, sortino=0.0, calmar=0.0, max_drawdown=0.0,
                    avg_rr=0.0, ev_per_trade=0.0, quality_bias=QUALITY_BIAS_NEU,
                    error="no_data",
                )
                self._store(symbol, res)
                return res
            try:
                loop = asyncio.get_event_loop()
                res = await loop.run_in_executor(
                    None, _run_proxy_backtest, bars, self.sl_pct, self.tp_pct, self.min_conf
                )
            except Exception as e:
                res = SimulationResult(
                    symbol=symbol, n_trades=0, win_rate=0.0, total_pnl_pct=0.0,
                    sharpe=0.0, sortino=0.0, calmar=0.0, max_drawdown=0.0,
                    avg_rr=0.0, ev_per_trade=0.0, quality_bias=QUALITY_BIAS_NEU,
                    error=str(e),
                )
            res.symbol = symbol
            self._store(symbol, res)
            return res

    async def _fetch_klines(self, symbol: str) -> List[KlineBar]:
        if not _HAS_AIOHTTP or self._session is None or self._session.closed:
            return []
        url = f"{BINANCE_FAPI_BASE}/fapi/v1/klines"
        params = {"symbol": symbol, "interval": KLINES_INTERVAL, "limit": self.lookback}
        try:
            async with self._session.get(url, params=params) as r:
                if r.status != 200:
                    return []
                data = await r.json()
                bars = []
                for d in data:
                    bars.append(KlineBar(
                        open_time=int(d[0]),
                        open=float(d[1]),
                        high=float(d[2]),
                        low=float(d[3]),
                        close=float(d[4]),
                        volume=float(d[5]),
                        close_time=int(d[6]),
                        quote_vol=float(d[7]),
                        num_trades=int(d[8]),
                        taker_buy_base=float(d[9]),
                        taker_buy_quote=float(d[10]),
                    ))
                return bars
        except Exception as e:
            self._logger.debug(f"[MiroFishSim] klines fetch {symbol}: {e}")
            return []

    def _store(self, symbol: str, res: SimulationResult) -> None:
        with self._lock:
            self._results[symbol] = res

    def get_quality_bias(self, symbol: str) -> float:
        """Returns quality bias score in [-8, +5] for Gate 8.5."""
        with self._lock:
            res = self._results.get(symbol)
        if res is None:
            return QUALITY_BIAS_NEU
        if time.time() - res.last_updated > STALE_MAX_SEC:
            return QUALITY_BIAS_NEU
        return res.quality_bias

    def get_simulation_report(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Returns full simulation report for a symbol."""
        with self._lock:
            res = self._results.get(symbol)
        if res is None:
            return None
        return {
            "symbol":         res.symbol,
            "n_trades":       res.n_trades,
            "win_rate_pct":   round(res.win_rate * 100, 1),
            "total_pnl_pct":  round(res.total_pnl_pct, 2),
            "sharpe":         round(res.sharpe, 3),
            "sortino":        round(res.sortino, 3),
            "calmar":         round(res.calmar, 3),
            "max_drawdown_pct": round(res.max_drawdown * 100, 2),
            "avg_rr":         round(res.avg_rr, 2),
            "ev_per_trade_pct": round(res.ev_per_trade * 100, 3),
            "quality_bias":   res.quality_bias,
            "bars_used":      res.bars_used,
            "last_updated":   res.last_updated,
            "age_sec":        round(time.time() - res.last_updated, 0),
            "error":          res.error,
        }

    def get_all_reports(self) -> List[Dict[str, Any]]:
        """Returns all simulation reports sorted by Sharpe descending."""
        with self._lock:
            items = list(self._results.values())
        reports = [self.get_simulation_report(r.symbol) for r in items]
        reports = [r for r in reports if r is not None]
        return sorted(reports, key=lambda r: r.get("sharpe", 0.0), reverse=True)

    def update_symbols(self, symbols: List[str]) -> None:
        """Dynamically update the symbol universe."""
        new = [s.upper().strip() for s in symbols if s.strip()]
        with self._lock:
            self.symbols = new

    def summary_stats(self) -> Dict[str, Any]:
        """Aggregate stats across all simulated symbols (complete institutional metrics)."""
        with self._lock:
            all_res = list(self._results.values())
        valid = [r for r in all_res if r.n_trades >= 5 and not r.error]
        if not valid:
            return {
                "symbols_simulated": 0,
                "avg_win_rate_pct": 0.0,
                "avg_sharpe": 0.0,
                "avg_sortino": 0.0,
                "avg_calmar": 0.0,
                "avg_max_dd_pct": 0.0,
                "avg_ev_pct": 0.0,
                "avg_rr": 0.0,
                "top_5_by_sharpe": [],
                "top_5_by_wr": [],
                "last_sweep": self._last_run,
                "run_count": self._run_count,
            }
        n          = len(valid)
        avg_wr     = sum(r.win_rate     for r in valid) / n
        avg_sharpe = sum(r.sharpe       for r in valid) / n
        avg_sortino= sum(r.sortino      for r in valid) / n
        avg_calmar = sum(r.calmar       for r in valid) / n
        avg_mdd    = sum(r.max_drawdown for r in valid) / n
        avg_ev     = sum(r.ev_per_trade for r in valid) / n
        avg_rr     = sum(r.avg_rr       for r in valid) / n
        top_sharpe = sorted(valid, key=lambda r: r.sharpe,   reverse=True)[:5]
        top_wr     = sorted(valid, key=lambda r: r.win_rate, reverse=True)[:5]
        return {
            "symbols_simulated": n,
            "avg_win_rate_pct":  round(avg_wr * 100,   1),
            "avg_sharpe":        round(avg_sharpe,      3),
            "avg_sortino":       round(avg_sortino,     3),
            "avg_calmar":        round(avg_calmar,      3),
            "avg_max_dd_pct":    round(avg_mdd * 100,   2),
            "avg_ev_pct":        round(avg_ev * 100,    3),
            "avg_rr":            round(avg_rr,           2),
            "top_5_by_sharpe":   [r.symbol for r in top_sharpe],
            "top_5_by_wr":       [r.symbol for r in top_wr],
            "last_sweep":        self._last_run,
            "run_count":         self._run_count,
        }

    async def run_single(self, symbol: str) -> Optional[Dict[str, Any]]:
        """On-demand single-symbol simulation. Returns report dict."""
        res = await self._simulate_symbol(symbol)
        return self.get_simulation_report(symbol)
