#!/usr/bin/env python3
"""
Cross-Sectional Mean Reversion Engine  [Unity Engine v18.72]
═════════════════════════════════════════════════════════════
Relative Extremes Strategy — exploit beta/sector-adjusted abnormal returns.

Strategy: Cross-Sectional Mean Reversion (Relative Extremes)
  • Ranks symbols by 5-bar abnormal returns adjusted for beta and volatility
  • Identifies symbols that have moved ±2 standard deviations from their
    expected cross-sectional return distribution
  • LONG the weakest (most oversold) 3% of the universe when below -2σ
  • SHORT the strongest (most overbought) 3% when above +2σ
  • Mean-reversion entry with position size scaled by ATR-normalised deviation

Integration with Unity Engine:
  • Symbol in extreme oversold zone (z < -2.0) → LONG signal gets +5pts
  • Symbol in extreme overbought zone (z > +2.0) → SHORT signal gets +5pts
  • Signals in the middle (|z| < 1.0) → -2pts quality penalty (no edge)
  • Provides beta-adjusted Z-score for each symbol in the scan universe

v18.72: Pure-numpy implementation. 5-bar abnormal return = actual return minus
        (beta × BTC return). Beta estimated via 20-bar rolling OLS. Z-score
        computed cross-sectionally at each scan cycle. Universe = all 80 USDM
        symbols in the scan pool. Recompute every 5 price updates.
"""

import numpy as np
import logging
from collections import deque
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
CSM_BETA_WINDOW   = 20      # bars for beta estimation via OLS
CSM_RETURN_WINDOW = 5       # lookback bars for abnormal return calculation
CSM_Z_EXTREME     = 2.2     # v18.77: 2.0→2.2 — stricter extreme threshold (only true outliers)
CSM_Z_WEAK        = 0.8     # v18.77: 1.0→0.8 — tighter neutral zone = more signals rewarded
CSM_TOP_PCT       = 0.04    # v18.77: 3%→4% — slightly wider overbought candidate pool
CSM_BOT_PCT       = 0.04    # v18.77: 3%→4% — slightly wider oversold candidate pool
CSM_QUALITY_BOOST = 7.0     # v18.79: 6.0→7.0 — stronger signal for ±2σ cross-sectional moves (MacroGlide apex calibration)
CSM_NEUTRAL_PENALT = -1.5   # v18.77: -2.0→-1.5 — softer neutral penalty (less signal rejection)
CSM_RECOMPUTE_N   = 4       # v18.77: 5→4 — faster recalculation (1 update sooner)
CSM_MIN_SYMBOLS   = 12      # v18.77: 15→12 — accept smaller universe during low-volume sessions


class CrossSectionMeanRevEngine:
    """
    Cross-Sectional Mean Reversion signal generator.

    For each symbol i at time t:
      abnormal_return[i] = sum(log_ret[i, t-4:t]) - beta[i] × sum(btc_ret[t-4:t])
    Cross-sectional Z-score:
      z[i] = (abnormal_return[i] - mu) / sigma

    Signal trigger:
      z[i] ≤ -2.0  AND direction=LONG  → strong mean-reversion BUY
      z[i] ≥ +2.0  AND direction=SHORT → strong mean-reversion SELL
    """

    def __init__(self):
        # Price history per symbol
        self._prices:  Dict[str, deque] = {}
        self._returns: Dict[str, deque] = {}

        # BTC anchor for beta estimation
        self._btc_returns: deque = deque(maxlen=CSM_BETA_WINDOW + CSM_RETURN_WINDOW)

        # Computed per-symbol metrics
        self._betas:    Dict[str, float] = {}
        self._abn_rets: Dict[str, float] = {}
        self._z_scores: Dict[str, float] = {}

        # Percentile thresholds
        self._top_threshold: float = 2.0
        self._bot_threshold: float = -2.0

        self._n_updates: int = 0

        logger.info(
            f"✅ [CSM] Cross-Sectional Mean Reversion engine initialised "
            f"(beta_window={CSM_BETA_WINDOW}, return_window={CSM_RETURN_WINDOW}, "
            f"z_extreme=±{CSM_Z_EXTREME})"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def update_price(self, symbol: str, price: float) -> None:
        """Feed a new price for any symbol in the scan universe."""
        if price <= 0:
            return
        if symbol not in self._prices:
            self._prices[symbol]  = deque(maxlen=CSM_BETA_WINDOW + CSM_RETURN_WINDOW + 2)
            self._returns[symbol] = deque(maxlen=CSM_BETA_WINDOW + CSM_RETURN_WINDOW)

        prev_prices = list(self._prices[symbol])
        self._prices[symbol].append(price)

        if prev_prices:
            log_ret = float(np.log(price / prev_prices[-1]))
            self._returns[symbol].append(log_ret)
            if symbol == "BTCUSDT":
                self._btc_returns.append(log_ret)

        self._n_updates += 1
        if self._n_updates % CSM_RECOMPUTE_N == 0:
            self._recompute()

    def get_signal(self, symbol: str, direction: str) -> Tuple[float, float, bool]:
        """
        Get cross-sectional mean reversion quality adjustment for Gate 9.

        Returns
        -------
        quality_adj  : Gate 9 quality score adjustment
        z_score      : cross-sectional Z-score for this symbol
        is_active    : True if CSM engine has computed a score for this symbol
        """
        if symbol not in self._z_scores or len(self._z_scores) < CSM_MIN_SYMBOLS:
            return 0.0, 0.0, False

        z = self._z_scores[symbol]
        is_long  = direction.upper() in ("BUY",  "LONG")
        is_short = direction.upper() in ("SELL", "SHORT")

        if is_long and z <= self._bot_threshold:
            return CSM_QUALITY_BOOST, z, True
        elif is_short and z >= self._top_threshold:
            return CSM_QUALITY_BOOST, z, True
        elif abs(z) < CSM_Z_WEAK:
            return CSM_NEUTRAL_PENALT, z, True
        else:
            return 0.0, z, True

    def get_extreme_symbols(self) -> Tuple[List[str], List[str]]:
        """
        Return (oversold_symbols, overbought_symbols) — top/bottom 3%.
        """
        if not self._z_scores:
            return [], []
        ranked = sorted(self._z_scores.items(), key=lambda x: x[1])
        n_extreme = max(1, int(len(ranked) * CSM_BOT_PCT))
        oversold   = [s for s, _ in ranked[:n_extreme]]
        overbought = [s for s, _ in ranked[-n_extreme:]]
        return oversold, overbought

    @property
    def is_ready(self) -> bool:
        return len(self._z_scores) >= CSM_MIN_SYMBOLS

    # ─────────────────────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────────────────────

    def _estimate_beta(self, symbol: str) -> float:
        """OLS beta of symbol vs BTC over beta window."""
        if symbol not in self._returns:
            return 1.0
        sym_rets = list(self._returns[symbol])[-CSM_BETA_WINDOW:]
        btc_rets = list(self._btc_returns)[-CSM_BETA_WINDOW:]
        n = min(len(sym_rets), len(btc_rets))
        if n < 5:
            return 1.0
        y = np.array(sym_rets[-n:])
        x = np.array(btc_rets[-n:])
        x_var = float(np.var(x))
        if x_var < 1e-12:
            return 1.0
        return float(np.cov(y, x)[0, 1] / x_var)

    def _recompute(self) -> None:
        """Recompute betas, abnormal returns, and cross-sectional Z-scores."""
        btc_rets_window = list(self._btc_returns)[-CSM_RETURN_WINDOW:]
        if len(btc_rets_window) < CSM_RETURN_WINDOW:
            return

        btc_cum = float(sum(btc_rets_window))

        abn_rets: Dict[str, float] = {}
        for sym, ret_buf in self._returns.items():
            sym_rets_window = list(ret_buf)[-CSM_RETURN_WINDOW:]
            if len(sym_rets_window) < CSM_RETURN_WINDOW:
                continue
            sym_cum = float(sum(sym_rets_window))
            beta = self._estimate_beta(sym)
            abnormal = sym_cum - beta * btc_cum
            abn_rets[sym] = abnormal

        if len(abn_rets) < CSM_MIN_SYMBOLS:
            return

        # Cross-sectional Z-scores
        vals = np.array(list(abn_rets.values()))
        mu   = float(np.mean(vals))
        std  = float(np.std(vals)) + 1e-9
        for sym, ar in abn_rets.items():
            self._z_scores[sym] = (ar - mu) / std
            self._betas[sym]    = self._estimate_beta(sym)
        self._abn_rets = abn_rets

        # Dynamic thresholds
        z_arr = np.array(list(self._z_scores.values()))
        self._top_threshold = float(np.percentile(z_arr, (1 - CSM_TOP_PCT) * 100))
        self._bot_threshold = float(np.percentile(z_arr, CSM_BOT_PCT * 100))
        # Enforce minimum ±2σ requirement
        self._top_threshold = max(self._top_threshold, CSM_Z_EXTREME)
        self._bot_threshold = min(self._bot_threshold, -CSM_Z_EXTREME)
