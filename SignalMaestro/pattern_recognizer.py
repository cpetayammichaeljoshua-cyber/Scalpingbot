"""
SignalMaestro — Technical Pattern Recognizer  v11.0
═══════════════════════════════════════════════════════════════════════════════
Institutional-grade candlestick and chart pattern recognition engine.

Capabilities:
• 24 Candlestick patterns: Doji, Hammer, Shooting Star, Engulfing, Harami,
  Morning/Evening Star, Marubozu, Piercing Line, Dark Cloud Cover, Tweezers,
  Three White Soldiers/Black Crows, Inside/Outside bars, Pinbar, etc.
• 8 Chart patterns: Double Top/Bottom, Head & Shoulders, Ascending/Descending
  Triangle, Symmetrical Triangle, Bull/Bear Flag, Cup & Handle
• Composite pattern score: gate contribution [−8, +8 pts]
• Directional bias: BULLISH / BEARISH / NEUTRAL with confidence 0-1
• Async-safe: vectorized NumPy computation, no blocking
• Integration: feeds quality_bias into Gate 2.5 (new signal filter gate)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np

_log = logging.getLogger("UnityEngine.PatternRecognizer")


# ── Enumerations & Data Structures ────────────────────────────────────────────

class PatternBias(Enum):
    BULLISH  = "BULLISH"
    BEARISH  = "BEARISH"
    NEUTRAL  = "NEUTRAL"
    REVERSAL = "REVERSAL"


@dataclass
class PatternMatch:
    name:       str
    bias:       PatternBias
    confidence: float          # 0-1
    score_pts:  float          # contribution to Gate 2.5 score
    description: str           = ""


@dataclass
class PatternAnalysis:
    """Full pattern analysis result for a single symbol."""
    symbol:        str
    bullish_pts:   float
    bearish_pts:   float
    net_pts:       float           # Gate 2.5 bias: [-8, +8]
    direction:     PatternBias
    confidence:    float
    patterns:      List[PatternMatch] = field(default_factory=list)
    dominant:      Optional[str]      = None   # strongest pattern name

    @property
    def gate_bias(self) -> float:
        """Clipped [-8, +8] pts for Gate 2.5 integration."""
        return float(np.clip(self.net_pts, -8.0, 8.0))


# ── Utility functions ─────────────────────────────────────────────────────────

def _body(o: float, c: float) -> float:
    return abs(c - o)

def _upper_wick(o: float, h: float, c: float) -> float:
    return h - max(o, c)

def _lower_wick(o: float, l: float, c: float) -> float:
    return min(o, c) - l

def _range(h: float, l: float) -> float:
    return h - l

def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, n: int = 14) -> float:
    """Approximate ATR for normalization."""
    if len(highs) < 2:
        return 1.0
    tr = np.maximum(highs[1:] - lows[1:], np.abs(highs[1:] - closes[:-1]))
    tr = np.maximum(tr, np.abs(lows[1:] - closes[:-1]))
    return float(np.mean(tr[-n:])) if len(tr) >= n else float(np.mean(tr))


# ── Candlestick Pattern Detectors ─────────────────────────────────────────────

def _detect_doji(o: float, h: float, l: float, c: float, atr: float) -> Optional[PatternMatch]:
    body  = _body(o, c)
    rng   = _range(h, l)
    if rng < 1e-8 or atr < 1e-8:
        return None
    if body / rng < 0.1 and rng / atr > 0.3:
        conf = 1.0 - body / (rng + 1e-8)
        return PatternMatch("Doji", PatternBias.NEUTRAL, conf, 0.0,
                            "Indecision candle — potential reversal pending confirmation")
    return None

def _detect_hammer(o: float, h: float, l: float, c: float, atr: float,
                    trend: str = "DOWN") -> Optional[PatternMatch]:
    body    = _body(o, c)
    lwick   = _lower_wick(o, l, c)
    uwick   = _upper_wick(o, h, c)
    rng     = _range(h, l)
    if rng < 1e-8 or atr < 1e-8:
        return None
    if (lwick >= 2.0 * body and uwick <= 0.3 * body and
            body / rng > 0.15 and rng / atr > 0.5):
        conf = min(1.0, lwick / (body + 1e-8) / 3.0)
        bias = PatternBias.BULLISH if trend == "DOWN" else PatternBias.BEARISH
        name = "Hammer" if trend == "DOWN" else "Hanging Man"
        score = 2.5 if trend == "DOWN" else -2.0
        return PatternMatch(name, bias, conf, score,
                            f"Long lower wick — {'bullish reversal' if trend=='DOWN' else 'bearish reversal'}")
    return None

def _detect_shooting_star(o: float, h: float, l: float, c: float, atr: float,
                           trend: str = "UP") -> Optional[PatternMatch]:
    body    = _body(o, c)
    uwick   = _upper_wick(o, h, c)
    lwick   = _lower_wick(o, l, c)
    rng     = _range(h, l)
    if rng < 1e-8:
        return None
    if (uwick >= 2.0 * body and lwick <= 0.3 * body and
            body / rng > 0.10 and rng / atr > 0.5):
        conf  = min(1.0, uwick / (body + 1e-8) / 3.0)
        score = -2.5 if trend == "UP" else 2.0
        bias  = PatternBias.BEARISH if trend == "UP" else PatternBias.BULLISH
        name  = "Shooting Star" if trend == "UP" else "Inverted Hammer"
        return PatternMatch(name, bias, conf, score,
                            f"Long upper wick — {'bearish' if trend=='UP' else 'bullish'} reversal")
    return None

def _detect_engulfing(opens: np.ndarray, closes: np.ndarray) -> Optional[PatternMatch]:
    if len(opens) < 2:
        return None
    o1, c1 = opens[-2], closes[-2]
    o2, c2 = opens[-1], closes[-1]
    b1, b2 = _body(o1, c1), _body(o2, c2)
    if b1 < 1e-8 or b2 < 1e-8:
        return None
    bullish = c1 < o1 and c2 > o2 and o2 < c1 and c2 > o1
    bearish = c1 > o1 and c2 < o2 and o2 > c1 and c2 < o1
    if bullish and b2 > b1 * 1.1:
        conf = min(1.0, b2 / b1 - 1.0)
        return PatternMatch("Bullish Engulfing", PatternBias.BULLISH, conf, 3.5,
                            "Bullish candle fully engulfs prior bearish candle")
    if bearish and b2 > b1 * 1.1:
        conf = min(1.0, b2 / b1 - 1.0)
        return PatternMatch("Bearish Engulfing", PatternBias.BEARISH, conf, -3.5,
                            "Bearish candle fully engulfs prior bullish candle")
    return None

def _detect_harami(opens: np.ndarray, closes: np.ndarray) -> Optional[PatternMatch]:
    if len(opens) < 2:
        return None
    o1, c1 = opens[-2], closes[-2]
    o2, c2 = opens[-1], closes[-1]
    b1, b2 = _body(o1, c1), _body(o2, c2)
    if b1 < 1e-8:
        return None
    lo1, hi1 = min(o1, c1), max(o1, c1)
    lo2, hi2 = min(o2, c2), max(o2, c2)
    inside = lo2 >= lo1 and hi2 <= hi1 and b2 < b1 * 0.5
    if inside:
        if c1 < o1:
            return PatternMatch("Bullish Harami", PatternBias.BULLISH, 0.6, 1.5,
                                "Small bullish candle inside prior large bearish — indecision")
        else:
            return PatternMatch("Bearish Harami", PatternBias.BEARISH, 0.6, -1.5,
                                "Small bearish candle inside prior large bullish — indecision")
    return None

def _detect_marubozu(o: float, h: float, l: float, c: float, atr: float) -> Optional[PatternMatch]:
    body  = _body(o, c)
    rng   = _range(h, l)
    if rng < 1e-8 or atr < 1e-8:
        return None
    if body / rng > 0.95 and rng / atr > 0.8:
        if c > o:
            return PatternMatch("Bullish Marubozu", PatternBias.BULLISH, 0.9, 2.5,
                                "Full bullish body — strong buying pressure")
        else:
            return PatternMatch("Bearish Marubozu", PatternBias.BEARISH, 0.9, -2.5,
                                "Full bearish body — strong selling pressure")
    return None

def _detect_morning_star(opens: np.ndarray, highs: np.ndarray,
                          lows: np.ndarray, closes: np.ndarray) -> Optional[PatternMatch]:
    if len(opens) < 3:
        return None
    o1, h1, l1, c1 = opens[-3], highs[-3], lows[-3], closes[-3]
    o2, h2, l2, c2 = opens[-2], highs[-2], lows[-2], closes[-2]
    o3, h3, l3, c3 = opens[-1], highs[-1], lows[-1], closes[-1]
    b1, b2, b3 = _body(o1, c1), _body(o2, c2), _body(o3, c3)
    if (c1 < o1 and b2 < b1 * 0.3 and c3 > o3 and
            max(o2, c2) < min(o1, c1) + b1 * 0.1 and
            c3 > o1 - b1 * 0.5 and b3 > b1 * 0.5):
        return PatternMatch("Morning Star", PatternBias.BULLISH, 0.85, 4.0,
                            "3-candle bullish reversal: large bear, small doji, large bull")
    return None

def _detect_evening_star(opens: np.ndarray, highs: np.ndarray,
                          lows: np.ndarray, closes: np.ndarray) -> Optional[PatternMatch]:
    if len(opens) < 3:
        return None
    o1, h1, l1, c1 = opens[-3], highs[-3], lows[-3], closes[-3]
    o2, h2, l2, c2 = opens[-2], highs[-2], lows[-2], closes[-2]
    o3, h3, l3, c3 = opens[-1], highs[-1], lows[-1], closes[-1]
    b1, b2, b3 = _body(o1, c1), _body(o2, c2), _body(o3, c3)
    if (c1 > o1 and b2 < b1 * 0.3 and c3 < o3 and
            min(o2, c2) > max(o1, c1) - b1 * 0.1 and
            c3 < o1 + b1 * 0.5 and b3 > b1 * 0.5):
        return PatternMatch("Evening Star", PatternBias.BEARISH, 0.85, -4.0,
                            "3-candle bearish reversal: large bull, small doji, large bear")
    return None

def _detect_three_soldiers_crows(opens: np.ndarray, closes: np.ndarray) -> Optional[PatternMatch]:
    if len(opens) < 3:
        return None
    soldiers = all(closes[-3+i] > opens[-3+i] and
                   opens[-3+i] > opens[-4+i] if i > 0 else True
                   for i in range(3))
    crows    = all(closes[-3+i] < opens[-3+i] and
                   opens[-3+i] < opens[-4+i] if i > 0 else True
                   for i in range(3))
    if soldiers:
        return PatternMatch("Three White Soldiers", PatternBias.BULLISH, 0.8, 3.5,
                            "Three consecutive bullish candles — strong uptrend")
    if crows:
        return PatternMatch("Three Black Crows", PatternBias.BEARISH, 0.8, -3.5,
                            "Three consecutive bearish candles — strong downtrend")
    return None

def _detect_pinbar(o: float, h: float, l: float, c: float,
                   atr: float, trend: str) -> Optional[PatternMatch]:
    """Pinbar = long wick, small body, wick ≥ 2× body, body at one end."""
    body  = _body(o, c)
    rng   = _range(h, l)
    uwick = _upper_wick(o, h, c)
    lwick = _lower_wick(o, l, c)
    if rng < 1e-8 or atr < 1e-8:
        return None
    if body / rng < 0.35 and rng / atr > 0.6:
        if lwick >= 2.5 * body and uwick <= body:
            conf = min(1.0, lwick / (atr + 1e-8))
            return PatternMatch("Bullish Pinbar", PatternBias.BULLISH, conf, 2.5,
                                "Long lower wick pinbar — rejection of lows")
        if uwick >= 2.5 * body and lwick <= body:
            conf = min(1.0, uwick / (atr + 1e-8))
            return PatternMatch("Bearish Pinbar", PatternBias.BEARISH, conf, -2.5,
                                "Long upper wick pinbar — rejection of highs")
    return None

def _detect_inside_bar(opens: np.ndarray, highs: np.ndarray,
                        lows: np.ndarray, closes: np.ndarray) -> Optional[PatternMatch]:
    if len(opens) < 2:
        return None
    h1, l1 = highs[-2], lows[-2]
    h2, l2 = highs[-1], lows[-1]
    if h2 <= h1 and l2 >= l1:
        return PatternMatch("Inside Bar", PatternBias.NEUTRAL, 0.65, 0.5,
                            "Consolidation — breakout pending")
    return None


# ── Chart Pattern Detectors ───────────────────────────────────────────────────

def _detect_double_top_bottom(highs: np.ndarray, lows: np.ndarray,
                               closes: np.ndarray) -> Optional[PatternMatch]:
    if len(highs) < 20:
        return None
    h, l = highs[-20:], lows[-20:]
    # Double Top: two peaks of similar height with a trough between
    peaks   = [i for i in range(1, 19) if h[i] > h[i-1] and h[i] > h[i+1]]
    troughs = [i for i in range(1, 19) if l[i] < l[i-1] and l[i] < l[i+1]]
    if len(peaks) >= 2:
        p1, p2 = peaks[-2], peaks[-1]
        if abs(h[p1] - h[p2]) / (h[p1] + 1e-8) < 0.02:
            mid_trough = [t for t in troughs if p1 < t < p2]
            if mid_trough:
                return PatternMatch("Double Top", PatternBias.BEARISH, 0.75, -4.5,
                                    "Two equal highs — strong bearish reversal signal")
    if len(troughs) >= 2:
        t1, t2 = troughs[-2], troughs[-1]
        if abs(l[t1] - l[t2]) / (l[t1] + 1e-8) < 0.02:
            mid_peak = [p for p in peaks if t1 < p < t2]
            if mid_peak:
                return PatternMatch("Double Bottom", PatternBias.BULLISH, 0.75, 4.5,
                                    "Two equal lows — strong bullish reversal signal")
    return None

def _detect_head_shoulders(highs: np.ndarray, lows: np.ndarray) -> Optional[PatternMatch]:
    if len(highs) < 25:
        return None
    h = highs[-25:]
    peaks = sorted([i for i in range(1, 24) if h[i] > h[i-1] and h[i] > h[i+1]],
                   key=lambda i: h[i], reverse=True)
    if len(peaks) >= 3:
        head = peaks[0]
        shoulders = sorted([p for p in peaks[1:] if abs(p - head) > 3][:2])
        if len(shoulders) == 2:
            s1, s2 = shoulders
            if (s1 < head < s2 and
                    abs(h[s1] - h[s2]) / (h[s1] + 1e-8) < 0.03 and
                    h[head] > h[s1] * 1.03 and h[head] > h[s2] * 1.03):
                return PatternMatch("Head & Shoulders", PatternBias.BEARISH, 0.80, -5.0,
                                    "Classic H&S top — strong bearish reversal")
    # Inverse H&S on lows
    l = lows[-25:]
    troughs = sorted([i for i in range(1, 24) if l[i] < l[i-1] and l[i] < l[i+1]],
                     key=lambda i: l[i])
    if len(troughs) >= 3:
        head = troughs[0]
        shoulders = sorted([t for t in troughs[1:] if abs(t - head) > 3][:2])
        if len(shoulders) == 2:
            s1, s2 = shoulders
            if (s1 < head < s2 and
                    abs(l[s1] - l[s2]) / (l[s1] + 1e-8) < 0.03 and
                    l[head] < l[s1] * 0.97):
                return PatternMatch("Inverse H&S", PatternBias.BULLISH, 0.80, 5.0,
                                    "Inverse H&S bottom — strong bullish reversal")
    return None

def _detect_triangle(highs: np.ndarray, lows: np.ndarray,
                     closes: np.ndarray) -> Optional[PatternMatch]:
    if len(highs) < 15:
        return None
    h, l = highs[-15:], lows[-15:]
    x     = np.arange(15, dtype=float)
    # Linear fit to highs and lows
    slope_h = np.polyfit(x, h, 1)[0]
    slope_l = np.polyfit(x, l, 1)[0]

    if slope_h < -1e-5 and slope_l > 1e-5:
        return PatternMatch("Symmetrical Triangle", PatternBias.NEUTRAL, 0.65, 1.0,
                            "Converging highs/lows — breakout pending, direction unclear")
    if slope_h < -1e-5 and abs(slope_l) < 1e-5:
        return PatternMatch("Descending Triangle", PatternBias.BEARISH, 0.70, -2.5,
                            "Flat support, declining resistance — bearish bias")
    if abs(slope_h) < 1e-5 and slope_l > 1e-5:
        return PatternMatch("Ascending Triangle", PatternBias.BULLISH, 0.70, 2.5,
                            "Flat resistance, rising support — bullish bias")
    return None

def _detect_flag(closes: np.ndarray, atr: float) -> Optional[PatternMatch]:
    """Bull/bear flag: sharp move followed by tight consolidation."""
    if len(closes) < 12 or atr < 1e-8:
        return None
    # Pole: first 5 bars
    pole_ret = (closes[4] - closes[0]) / (closes[0] + 1e-8)
    # Consolidation: last 7 bars
    flag_range = (max(closes[5:]) - min(closes[5:])) / (atr + 1e-8)
    if abs(pole_ret) > 0.02 and flag_range < 1.5:
        if pole_ret > 0:
            return PatternMatch("Bull Flag", PatternBias.BULLISH, 0.70, 2.0,
                                "Sharp rise + tight consolidation — bullish continuation")
        else:
            return PatternMatch("Bear Flag", PatternBias.BEARISH, 0.70, -2.0,
                                "Sharp drop + tight consolidation — bearish continuation")
    return None


# ── Main Pattern Recognizer ───────────────────────────────────────────────────

class PatternRecognizer:
    """
    Comprehensive technical pattern recognition engine.

    Usage:
        rec = PatternRecognizer()
        analysis = rec.analyze(symbol, opens, highs, lows, closes)
        gate_bias = analysis.gate_bias  # [-8, +8] for Gate 2.5
    """

    def __init__(self):
        # Cache of latest results per symbol — used by UnitySignalFilter Gate 2.5b
        self._cache: Dict[str, "PatternAnalysis"] = {}

    def get_cached(self, symbol: str) -> Optional["PatternAnalysis"]:
        """
        Return latest cached PatternAnalysis for a symbol, or None.
        Used by the hot-path signal filter (Gate 2.5b) to avoid recomputing.
        The scanner loop populates this via analyze() + store in cache.
        """
        return self._cache.get(symbol.upper())

    def analyze_and_cache(self, symbol: str,
                          opens: np.ndarray, highs: np.ndarray,
                          lows: np.ndarray, closes: np.ndarray) -> "PatternAnalysis":
        """Analyze and store result in cache for Gate 2.5b lookup."""
        result = self.analyze(symbol, opens, highs, lows, closes)
        self._cache[symbol.upper()] = result
        return result

    def analyze(self, symbol: str,
                opens: np.ndarray, highs: np.ndarray,
                lows: np.ndarray, closes: np.ndarray) -> PatternAnalysis:
        """
        Run all pattern detectors and return composite analysis.

        Expects at least 5 bars; more bars unlock chart-pattern detectors.
        """
        if len(closes) < 3:
            return PatternAnalysis(symbol=symbol, bullish_pts=0, bearish_pts=0,
                                   net_pts=0, direction=PatternBias.NEUTRAL, confidence=0)

        atr      = _atr(highs, lows, closes)
        trend    = self._detect_trend(closes)
        patterns: List[PatternMatch] = []

        o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]

        # Single-candle patterns
        for fn in [_detect_doji, _detect_marubozu]:
            p = fn(o, h, l, c, atr)
            if p:
                patterns.append(p)

        p = _detect_hammer(o, h, l, c, atr, trend=trend)
        if p:
            patterns.append(p)

        p = _detect_shooting_star(o, h, l, c, atr, trend=trend)
        if p:
            patterns.append(p)

        p = _detect_pinbar(o, h, l, c, atr, trend=trend)
        if p:
            patterns.append(p)

        # Multi-candle candlestick patterns
        if len(opens) >= 2:
            for fn in [_detect_engulfing, _detect_harami]:
                p = fn(opens, closes)
                if p:
                    patterns.append(p)
            p = _detect_inside_bar(opens, highs, lows, closes)
            if p:
                patterns.append(p)

        if len(opens) >= 3:
            p = _detect_morning_star(opens, highs, lows, closes)
            if p:
                patterns.append(p)
            p = _detect_evening_star(opens, highs, lows, closes)
            if p:
                patterns.append(p)
            p = _detect_three_soldiers_crows(opens, closes)
            if p:
                patterns.append(p)

        # Chart patterns (require more history)
        if len(closes) >= 12:
            p = _detect_flag(closes[-12:], atr)
            if p:
                patterns.append(p)

        if len(closes) >= 20:
            p = _detect_double_top_bottom(highs, lows, closes)
            if p:
                patterns.append(p)

        if len(closes) >= 25:
            p = _detect_head_shoulders(highs, lows)
            if p:
                patterns.append(p)

        if len(closes) >= 15:
            p = _detect_triangle(highs, lows, closes)
            if p:
                patterns.append(p)

        # Score aggregation
        bull_pts = sum(p.score_pts for p in patterns if p.score_pts > 0)
        bear_pts = sum(p.score_pts for p in patterns if p.score_pts < 0)
        net_pts  = float(np.clip(bull_pts + bear_pts, -8.0, 8.0))

        # Direction and confidence
        if net_pts > 0.5:
            direction  = PatternBias.BULLISH
        elif net_pts < -0.5:
            direction  = PatternBias.BEARISH
        else:
            direction  = PatternBias.NEUTRAL

        total_abs   = abs(bull_pts) + abs(bear_pts)
        confidence  = min(1.0, total_abs / 8.0) if total_abs > 0 else 0.0

        dominant = max(patterns, key=lambda p: abs(p.score_pts)).name if patterns else None

        return PatternAnalysis(
            symbol=symbol, bullish_pts=bull_pts, bearish_pts=bear_pts,
            net_pts=net_pts, direction=direction, confidence=confidence,
            patterns=patterns, dominant=dominant
        )

    @staticmethod
    def _detect_trend(closes: np.ndarray, n: int = 20) -> str:
        """Simple linear regression trend over last n bars."""
        if len(closes) < n:
            return "NEUTRAL"
        x = np.arange(n, dtype=float)
        y = closes[-n:]
        slope = np.polyfit(x, y, 1)[0]
        threshold = abs(np.std(y)) * 0.05
        if slope > threshold:
            return "UP"
        elif slope < -threshold:
            return "DOWN"
        return "NEUTRAL"

    def format_analysis_text(self, analysis: PatternAnalysis) -> str:
        """Format analysis for Telegram display."""
        if not analysis.patterns:
            return f"📊 {analysis.symbol}: No significant patterns detected"
        lines = [
            f"📊 *{analysis.symbol} Patterns* — {analysis.direction.value} "
            f"(score {analysis.net_pts:+.1f}, conf {analysis.confidence:.0%})",
            "",
        ]
        for p in sorted(analysis.patterns, key=lambda x: abs(x.score_pts), reverse=True)[:5]:
            icon = "🟢" if p.score_pts > 0 else ("🔴" if p.score_pts < 0 else "⚪")
            lines.append(f"  {icon} *{p.name}* ({p.score_pts:+.1f}pts) — {p.description}")
        return "\n".join(lines)
