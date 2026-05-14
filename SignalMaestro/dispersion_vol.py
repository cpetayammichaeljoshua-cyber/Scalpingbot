#!/usr/bin/env python3
"""
Dispersion Volatility Arbitrage  [Unity Engine v18.72]
═══════════════════════════════════════════════════════
Correlation Spread Strategy from Implied Volatility.

Strategy: Dispersion Volatility Arbitrage (Correlation Spread)
  • Monitors implied-correlation proxy derived from crypto market
  • When average single-asset implied correlation falls below threshold
    while realized index volatility stays above its 30-bar average →
    signals SHORT volatility / BUY directional
  • Adapted for crypto: uses cross-asset realized correlation (BTC vs ALT basket)
    as a proxy for implied correlation spread

Integration with Unity Engine:
  • Low-correlation + high-BTC-vol regime → LONG alt breakout signals boosted +4pts
  • High-correlation + low-BTC-vol regime → neutral
  • Correlation spike (ALL assets moving together) → defensive -5pts quality penalty
  • Provides regime context string for Telegram signal messages

v18.72: Pure-numpy implementation. Tracks rolling 30-bar realized correlations
        between BTC and the top 10 alt symbols. Dispersion = std(cross-asset returns).
        Correlation below 0.25 + vol above 30-bar avg → dispersion regime (+4pts).
        Correlation spike > 0.85 → systemic risk (-5pts).
"""

import numpy as np
import logging
from collections import deque
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
DISPERSION_WINDOW      = 30      # rolling bars for correlation/vol calculation
DISPERSION_LOW_CORR    = 0.25    # implied-correlation threshold for dispersion regime
DISPERSION_HIGH_CORR   = 0.85    # correlation spike → systemic risk
DISPERSION_QUALITY_BUY = 4.0    # quality boost when dispersion regime confirmed
DISPERSION_QUALITY_RISK = -5.0  # quality penalty when correlation spike detected
DISPERSION_MIN_ASSETS  = 5      # minimum assets for reliable correlation matrix

# Reference symbols (BTC anchor + top ALT basket)
DISPERSION_BASKET = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "AVAXUSDT", "DOTUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT",
]


class DispersionVolEngine:
    """
    Dispersion Volatility Arbitrage engine.

    Tracks realized correlations across a crypto basket and identifies
    dispersion regimes where individual assets diverge from index behaviour.

    Key metrics:
      avg_corr    : average pairwise realized correlation in basket
      btc_vol     : rolling BTC realized volatility
      vol_vs_avg  : BTC vol relative to its 30-bar mean
      dispersion  : std of cross-sectional returns (high = dispersion regime)
    """

    def __init__(self):
        self._returns:  Dict[str, deque] = {
            sym: deque(maxlen=DISPERSION_WINDOW + 1)
            for sym in DISPERSION_BASKET
        }
        self._prev_prices: Dict[str, float] = {}

        self._avg_corr:   float = 0.5    # running avg pairwise correlation
        self._dispersion: float = 0.0    # cross-sectional return std
        self._btc_vol:    float = 0.0    # BTC realized vol
        self._vol_hist:   deque = deque(maxlen=DISPERSION_WINDOW)
        self._vol_vs_avg: float = 1.0

        self._regime:     str = "NEUTRAL"
        self._n_updates:  int = 0

        logger.info(
            f"✅ [Dispersion] Dispersion Vol Engine initialised "
            f"(basket={len(DISPERSION_BASKET)} assets, window={DISPERSION_WINDOW})"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def update_price(self, symbol: str, price: float) -> None:
        """Feed a new price for a basket symbol."""
        if symbol not in self._returns:
            return
        if price <= 0:
            return
        prev = self._prev_prices.get(symbol, price)
        if prev > 0:
            log_ret = float(np.log(price / prev))
            self._returns[symbol].append(log_ret)
        self._prev_prices[symbol] = price
        self._n_updates += 1

        if self._n_updates % 10 == 0:
            self._recalculate()

    def get_signal(self, symbol: str) -> Tuple[str, float, float]:
        """
        Get dispersion signal for a given symbol.

        Returns
        -------
        regime      : 'DISPERSION' | 'SYSTEMIC_RISK' | 'NEUTRAL'
        quality_adj : Gate 9 quality score adjustment
        avg_corr    : current average pairwise correlation
        """
        if not self._is_ready():
            return "NEUTRAL", 0.0, self._avg_corr

        if self._regime == "DISPERSION":
            return "DISPERSION", DISPERSION_QUALITY_BUY, self._avg_corr
        elif self._regime == "SYSTEMIC_RISK":
            return "SYSTEMIC_RISK", DISPERSION_QUALITY_RISK, self._avg_corr
        else:
            return "NEUTRAL", 0.0, self._avg_corr

    def get_stats(self) -> Dict:
        return {
            "regime":     self._regime,
            "avg_corr":   round(self._avg_corr, 4),
            "dispersion": round(self._dispersion, 6),
            "btc_vol":    round(self._btc_vol, 6),
            "vol_vs_avg": round(self._vol_vs_avg, 3),
            "ready":      self._is_ready(),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────────────────────

    def _is_ready(self) -> bool:
        filled = sum(1 for r in self._returns.values() if len(r) >= DISPERSION_WINDOW)
        return filled >= DISPERSION_MIN_ASSETS

    def _recalculate(self) -> None:
        """Recompute correlations, dispersion, and determine regime."""
        # Build return matrix: shape (T, N) for assets with enough data
        asset_rets: List[np.ndarray] = []
        for sym in DISPERSION_BASKET:
            r = self._returns[sym]
            if len(r) >= DISPERSION_WINDOW:
                asset_rets.append(np.array(list(r)[-DISPERSION_WINDOW:]))

        if len(asset_rets) < DISPERSION_MIN_ASSETS:
            return

        R = np.column_stack(asset_rets)   # (T, N)
        N = R.shape[1]

        # Correlation matrix
        with np.errstate(divide='ignore', invalid='ignore'):
            corr = np.corrcoef(R.T)       # (N, N)
            corr = np.where(np.isnan(corr), 0.0, corr)

        # Average pairwise correlation (off-diagonal)
        mask = ~np.eye(N, dtype=bool)
        self._avg_corr = float(np.mean(np.abs(corr[mask])))

        # Cross-sectional dispersion = std of last bar returns across assets
        last_bar_rets = R[-1, :]
        self._dispersion = float(np.std(last_bar_rets))

        # BTC realized vol
        if "BTCUSDT" in self._returns and len(self._returns["BTCUSDT"]) >= DISPERSION_WINDOW:
            btc_r = np.array(list(self._returns["BTCUSDT"])[-DISPERSION_WINDOW:])
            self._btc_vol = float(np.std(btc_r)) * np.sqrt(1440)  # annualise to daily
            self._vol_hist.append(self._btc_vol)
            if len(self._vol_hist) >= 5:
                self._vol_vs_avg = self._btc_vol / (float(np.mean(self._vol_hist)) + 1e-9)

        # Regime classification
        if self._avg_corr >= DISPERSION_HIGH_CORR:
            self._regime = "SYSTEMIC_RISK"
        elif self._avg_corr <= DISPERSION_LOW_CORR and self._vol_vs_avg >= 1.0:
            self._regime = "DISPERSION"
        else:
            self._regime = "NEUTRAL"
