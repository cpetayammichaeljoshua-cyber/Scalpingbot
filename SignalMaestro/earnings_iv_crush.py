#!/usr/bin/env python3
"""
Earnings IV Crush / IV Rank Monitor  [Unity Engine v18.72]
═══════════════════════════════════════════════════════════
Premium Collapse Strategy — adapted for crypto perpetual futures.

Strategy: Earnings Implied Volatility Crush (Premium Collapse)
  Adapted for crypto: monitors IV Rank (IVR) and funding rate as
  premium indicators. In crypto:
    • IV Rank > 80% → implied vol elevated relative to 1-year range
    • Funding rate absolute value > 0.05% per 8h → premium collapse risk
    • These combined → SHORT vol / neutral position sizing (reduce size)
    • IV crush post-major-event → LONG directional with larger size

Integration with Unity Engine:
  • High IV Rank (>80%) + elevated funding → -4pts quality (sizing caution)
  • Low IV Rank (<20%) + flat funding → +3pts (vol expansion potential)
  • IV crush condition post-spike → Kelly ×0.80 (protect from gap fills)
  • Funding rate extreme (>0.10%) → -6pts systemic squeeze risk

v18.72: Uses Binance perpetual funding rate + rolling close-to-close vol
        as IV proxy (Parkinson estimator). IV Rank computed over 252-bar window.
        Funding rate data ingested from the scan pipeline.
"""

import numpy as np
import logging
from collections import deque
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
IVR_WINDOW          = 252      # bars for IV Rank (1-year daily or 252 4h bars)
IVR_HIGH_THRESHOLD  = 0.80     # IV Rank > 80% → elevated premium
IVR_LOW_THRESHOLD   = 0.20     # IV Rank < 20% → vol compression
FUNDING_HIGH_ABS    = 0.0005   # |funding_rate| > 0.05% per 8h → elevated carry
FUNDING_EXTREME_ABS = 0.0010   # |funding_rate| > 0.10% → extreme squeeze risk
IVR_HIGH_PENALTY    = -4.0     # quality penalty in high-IVR regime
IVR_EXTREME_PENALTY = -6.0     # quality penalty when funding extreme
IVR_LOW_BOOST       = 3.0      # quality boost in low-IVR / vol expansion
IV_CRUSH_KELLY_MULT = 0.80     # Kelly multiplier during IV crush risk


class IVCrushMonitor:
    """
    IV Rank and funding-rate monitor for crypto perpetual futures.

    Per-symbol tracking of:
      - Parkinson volatility (high-low range estimator)
      - IV Rank = (current_vol - min_vol_252) / (max_vol_252 - min_vol_252)
      - Binance perpetual funding rate
      - Combined IV/funding signal for quality adjustment
    """

    def __init__(self):
        # Per-symbol volatility history
        self._vol_history: Dict[str, deque] = {}
        self._current_vol: Dict[str, float] = {}
        self._iv_rank:     Dict[str, float] = {}
        self._funding:     Dict[str, float] = {}  # latest 8h funding rate

        logger.info(
            f"✅ [IVCrush] IV Rank + Funding Rate monitor initialised "
            f"(window={IVR_WINDOW}, high_threshold={IVR_HIGH_THRESHOLD:.0%})"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def update_bar(self, symbol: str, high: float, low: float, close: float) -> None:
        """
        Feed OHLC data for volatility estimation.

        Uses Parkinson high-low estimator:
          σ² = (1 / (4·ln2)) × ln(H/L)²
        """
        if high <= 0 or low <= 0 or low >= high:
            return
        if symbol not in self._vol_history:
            self._vol_history[symbol] = deque(maxlen=IVR_WINDOW)

        park_var = (1.0 / (4.0 * np.log(2))) * (np.log(high / low)) ** 2
        park_vol = float(np.sqrt(park_var))
        self._vol_history[symbol].append(park_vol)

        # Compute IV Rank
        if len(self._vol_history[symbol]) >= 10:
            arr = np.array(self._vol_history[symbol])
            min_v = float(np.min(arr))
            max_v = float(np.max(arr))
            if max_v > min_v:
                self._iv_rank[symbol] = (park_vol - min_v) / (max_v - min_v)
            else:
                self._iv_rank[symbol] = 0.5
            self._current_vol[symbol] = park_vol

    def update_funding(self, symbol: str, funding_rate: float) -> None:
        """Feed the latest perpetual funding rate for a symbol."""
        self._funding[symbol] = funding_rate

    def get_signal(self, symbol: str) -> Tuple[str, float, float]:
        """
        Get IV/funding quality adjustment for Gate 9.

        Returns
        -------
        regime       : 'HIGH_IV' | 'LOW_IV' | 'EXTREME_FUNDING' | 'NEUTRAL'
        quality_adj  : Gate 9 quality score adjustment
        kelly_mult   : Kelly multiplier
        """
        ivr      = self._iv_rank.get(symbol, 0.5)
        funding  = abs(self._funding.get(symbol, 0.0))

        # Extreme funding → systemic squeeze risk
        if funding >= FUNDING_EXTREME_ABS:
            return "EXTREME_FUNDING", IVR_EXTREME_PENALTY, IV_CRUSH_KELLY_MULT

        # High IV Rank + elevated funding → premium collapse risk
        if ivr >= IVR_HIGH_THRESHOLD and funding >= FUNDING_HIGH_ABS:
            return "HIGH_IV", IVR_HIGH_PENALTY, IV_CRUSH_KELLY_MULT

        # Low IV Rank → vol compression / expansion potential
        if ivr <= IVR_LOW_THRESHOLD and funding < FUNDING_HIGH_ABS:
            return "LOW_IV", IVR_LOW_BOOST, 1.0

        return "NEUTRAL", 0.0, 1.0

    def get_stats(self, symbol: str) -> Dict:
        return {
            "iv_rank":  round(self._iv_rank.get(symbol, 0.5), 4),
            "vol":      round(self._current_vol.get(symbol, 0.0), 6),
            "funding":  round(self._funding.get(symbol, 0.0), 6),
            "ready":    symbol in self._iv_rank,
        }
