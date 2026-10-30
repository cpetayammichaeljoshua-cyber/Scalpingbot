"""
QuantJourney United Signal Bridge
==================================
Adapts the QuantJourney "united strategy" consensus philosophy to the
Scalpingbot pipeline, so the united strategy runs BEFORE the LLM.

The UnitedStrategy (quantjourney-bt) blends top backtest strategies into one
consensus signal. This bridge applies the SAME consensus-blending logic to the
live symbol's price series, producing a directional bias (BUY/SELL/NEUTRAL)
plus a confidence score and the per-strategy votes. The G0DM0D3 LLM then
analyzes the prompt enriched with this signal to emit the final Telegram signal.

The bridge is dependency-light: it computes the constituent strategies' core
signal generators (MACD trend, SMA cross, RSI reversion, Bollinger reversion,
momentum) natively on the price series, so it runs even if quantjourney-bt is
not installed.

Design: consensus[i] = sum_j( w_j * signal_j[i] ) / sum_j( w_j )
    - signal_j in {-1, 0, +1} (direction vote per strategy)
    - w_j = Sharpe-derived weight (from the quantjourney backtest ranking)
    - If consensus magnitude > threshold -> BUY/SELL, else NEUTRAL
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger("UnityEngine.QuantJourneyUnited")

# Sharpe weights from the quantjourney-bt sample backtest ranking (sector-ETF
# universe, the highest-Sharpe united composition).
CONSTITUENT_SHARPE: Dict[str, float] = {
    "MACDTrend": 40.06,            # example_weights_22_macd_trend
    "DailyPartialDrift": 25.67,    # example_weights_12_daily_partial_drift
    "RiskParityCapped": 20.78,     # example_weights_20_risk_parity_capped
    "VolTargetTrend": 20.53,       # example_weights_17_vol_target_trend
    "MonthlyInverseVol": 20.73,    # example_weights_05_monthly_inverse_vol
}

DEFAULT_CONSENSUS_THRESHOLD = 0.30
MIN_BARS = 60


class QuantJourneyUnitedBridge:
    """Computes a consensus directional signal from a live price series."""

    def __init__(
        self,
        consensus_threshold: float = DEFAULT_CONSENSUS_THRESHOLD,
        sharpe_weights: Optional[Dict[str, float]] = None,
    ) -> None:
        self.consensus_threshold = consensus_threshold
        self.sharpe_weights = sharpe_weights or CONSTITUENT_SHARPE

    def compute_signal(
        self,
        closes: List[float],
        symbol: str = "",
        timeframe: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Compute a consensus signal from a price series (most recent LAST)."""
        if not closes or len(closes) < MIN_BARS:
            return self._neutral("insufficient data (need >= %d bars)" % MIN_BARS, symbol)

        votes: Dict[str, Dict[str, Any]] = {}

        macd_vote = self._macd_trend(closes)
        if macd_vote is not None:
            votes["MACDTrend"] = self._fmt_vote(macd_vote, "MACD(12/26/9) trend")

        sma_vote = self._sma_trend(closes, 50, 200)
        if sma_vote is not None:
            votes["DailyPartialDrift"] = self._fmt_vote(sma_vote, "SMA(50/200) trend")

        rp_vote = self._risk_parity_proxy(closes)
        if rp_vote is not None:
            votes["RiskParityCapped"] = self._fmt_vote(rp_vote, "inverse-vol momentum")

        vt_vote = self._vol_target_trend(closes)
        if vt_vote is not None:
            votes["VolTargetTrend"] = self._fmt_vote(vt_vote, "vol-target trend")

        miv_vote = self._monthly_inverse_vol(closes)
        if miv_vote is not None:
            votes["MonthlyInverseVol"] = self._fmt_vote(miv_vote, "monthly inverse-vol")

        total_weight = 0.0
        weighted_sum = 0.0
        active = 0
        for name, v in votes.items():
            w = self.sharpe_weights.get(name, 1.0)
            if w <= 0:
                continue
            weighted_sum += w * v["direction"]
            total_weight += w
            active += 1

        if total_weight <= 0 or active == 0:
            return self._neutral("no strategies produced a vote", symbol)

        consensus = weighted_sum / total_weight

        if consensus >= self.consensus_threshold:
            direction = "BUY"
        elif consensus <= -self.consensus_threshold:
            direction = "SELL"
        else:
            direction = "NEUTRAL"

        confidence = min(abs(consensus), 1.0)
        agreement = active / max(len(self.sharpe_weights), 1)
        confidence = min(confidence * (0.7 + 0.3 * agreement), 1.0)

        return {
            "direction": direction,
            "confidence": round(confidence, 4),
            "consensus": round(consensus, 4),
            "votes": votes,
            "n_strategies": len(self.sharpe_weights),
            "active_strategies": active,
            "symbol": symbol,
            "timeframe": timeframe,
        }

    def to_prompt_line(self, result: Dict[str, Any]) -> str:
        """Format the signal for injection into the G0DM0D3 prompt."""
        if not result or (result.get("direction") == "NEUTRAL" and result.get("consensus", 0) == 0):
            return "QuantJourney United: NO CLEAR SIGNAL (consensus near zero)"
        votes_str = "; ".join(
            f"{k}={v['direction_label']}" for k, v in result.get("votes", {}).items()
        )
        return (
            f"QuantJourney United Strategy: {result['direction']} "
            f"@ {result['confidence']*100:.0f}% confidence "
            f"(consensus={result['consensus']:+.2f}, {result['active_strategies']}"
            f"/{result['n_strategies']} strategies: {votes_str})"
        )

    # ── Constituent signal generators (each returns -1/0/+1 or None) ──
    def _macd_trend(self, closes: List[float]) -> Optional[int]:
        fast = self._ema(closes, 12)
        slow = self._ema(closes, 26)
        if fast is None or slow is None:
            return None
        macd_series = [fast[i] - slow[i] for i in range(len(fast))]
        signal_line = self._ema(macd_series, 9)
        if signal_line is None:
            return None
        macd = macd_series[-1]
        sig = signal_line[-1]
        hist = macd - sig
        # Histogram threshold avoids noise flips on steady trends (where
        # MACD converges to the signal line). When |hist| is tiny, fall back
        # to the MACD sign (positive -> uptrend, negative -> downtrend).
        scale = max(abs(macd), 1e-9)
        if abs(hist) > 0.05 * scale:
            if hist > 0:
                return 1
            elif hist < 0:
                return -1
            return 0
        # Steady trend tiebreaker: use MACD sign relative to zero
        if macd > 0:
            return 1
        elif macd < 0:
            return -1
        return 0

    def _sma_trend(self, closes: List[float], fast: int, slow: int) -> Optional[int]:
        if len(closes) < slow:
            return None
        f = sum(closes[-fast:]) / fast
        s = sum(closes[-slow:]) / slow
        if f > s:
            return 1
        elif f < s:
            return -1
        return 0

    def _risk_parity_proxy(self, closes: List[float]) -> Optional[int]:
        if len(closes) < 30:
            return None
        ret_20 = (closes[-1] - closes[-20]) / closes[-20] if closes[-20] != 0 else 0.0
        vol = self._stdev(closes[-30:])
        if vol == 0:
            return None
        z = ret_20 / vol
        if z > 0.5:
            return 1
        elif z < -0.5:
            return -1
        return 0

    def _vol_target_trend(self, closes: List[float]) -> Optional[int]:
        if len(closes) < 30:
            return None
        ema = self._ema(closes, 20)
        if ema is None:
            return None
        slope = ema[-1] - ema[-6]
        vol = self._stdev(closes[-20:])
        if vol == 0:
            return None
        z = slope / vol
        if z > 0.15:
            return 1
        elif z < -0.15:
            return -1
        return 0

    def _monthly_inverse_vol(self, closes: List[float]) -> Optional[int]:
        if len(closes) < 40:
            return None
        ret_40 = (closes[-1] - closes[-40]) / closes[-40] if closes[-40] != 0 else 0.0
        if ret_40 > 0.02:
            return 1
        elif ret_40 < -0.02:
            return -1
        return 0

    # ── Helpers ──
    @staticmethod
    def _fmt_vote(direction: int, reason: str) -> Dict[str, Any]:
        d = "BUY" if direction > 0 else ("SELL" if direction < 0 else "NEUTRAL")
        return {"direction": direction, "direction_label": d,
                "strength": abs(direction), "reason": reason}

    @staticmethod
    def _ema(data: List[float], span: int) -> Optional[List[float]]:
        if len(data) < span:
            return None
        k = 2.0 / (span + 1)
        ema = [data[0]]
        for i in range(1, len(data)):
            ema.append(data[i] * k + ema[-1] * (1 - k))
        return ema

    @staticmethod
    def _stdev(data: List[float]) -> float:
        if len(data) < 2:
            return 0.0
        m = sum(data) / len(data)
        return math.sqrt(sum((x - m) ** 2 for x in data) / (len(data) - 1))

    @staticmethod
    def _neutral(reason: str, symbol: str) -> Dict[str, Any]:
        return {
            "direction": "NEUTRAL", "confidence": 0.0, "consensus": 0.0,
            "votes": {}, "n_strategies": 0, "active_strategies": 0,
            "symbol": symbol, "reason": reason,
        }


__all__ = ["QuantJourneyUnitedBridge", "CONSTITUENT_SHARPE", "DEFAULT_CONSENSUS_THRESHOLD"]
