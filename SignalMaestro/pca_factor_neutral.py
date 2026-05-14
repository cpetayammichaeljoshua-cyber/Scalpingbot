#!/usr/bin/env python3
"""
PCA Factor Neutral Long/Short Engine  [Unity Engine v18.72]
════════════════════════════════════════════════════════════
Residual Exposure Strategy — removes market and sector beta via PCA.

Strategy: PCA Factor Neutral Long/Short (Residual Exposure)
  • Collects rolling returns for the full symbol universe (50+ USDM symbols)
  • Runs incremental PCA to extract first 2-3 principal components
    (representing crypto market beta and sector rotation)
  • Neutralises systematic factor exposure to isolate idiosyncratic alpha
  • Ranks symbols by residual (factor-neutral) return zscore
  • Symbols with high positive residual → LONG bias (+quality bonus)
  • Symbols with high negative residual → SHORT bias (+quality bonus for shorts)
  • Symbols near the residual mean (neutral) → no adjustment

Integration with Unity Engine:
  • Top residual quartile (LONG) → +4pts quality bonus
  • Bottom residual quartile (SHORT) → +4pts quality bonus for short signals
  • Factor loading too high (dominated by market beta) → -3pts penalty
  • Weekly rebalance cadence (every 2,016 bars at 1m, or 72 scan cycles)

v18.72: Incremental covariance PCA using numpy SVD. 50-bar rolling window.
        2-component factor model. Residual z-score ranked relative to universe.
        No external dependencies. O(N·T) per recompute cycle.
"""

import numpy as np
import logging
from collections import deque
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
PCA_WINDOW         = 50        # rolling bars for PCA
PCA_N_COMPONENTS   = 2        # number of principal components to neutralise
PCA_RECOMPUTE_EVERY = 72      # recompute every N price updates (across all symbols)
PCA_TOP_QUARTILE   = 0.75     # residual percentile → LONG signal boost
PCA_BOT_QUARTILE   = 0.25     # residual percentile → SHORT signal boost
PCA_QUALITY_BOOST  = 4.0      # quality pts for top/bottom residual decile
PCA_BETA_PENALTY   = -3.0     # quality pts when factor loading dominates (β>0.90)
PCA_MIN_SYMBOLS    = 10       # minimum symbols for reliable PCA


class PCAFactorEngine:
    """
    Incremental PCA factor model for cross-sectional alpha extraction.

    For each symbol, computes:
      residual[sym] = return[sym] - PC1_loading * PC1 - PC2_loading * PC2

    Symbols with extreme residuals (top/bottom quartile) have idiosyncratic
    momentum not explained by market/sector factors → higher signal quality.
    """

    def __init__(self):
        self._returns:   Dict[str, deque] = {}
        self._residuals: Dict[str, float] = {}
        self._loadings:  Dict[str, np.ndarray] = {}
        self._components: Optional[np.ndarray] = None  # shape (K, T)
        self._n_updates:  int = 0

        # Percentile thresholds
        self._top_threshold: float = 0.0
        self._bot_threshold: float = 0.0

        logger.info(
            f"✅ [PCA] PCA Factor Neutral engine initialised "
            f"(K={PCA_N_COMPONENTS} components, window={PCA_WINDOW})"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def update_price(self, symbol: str, price: float, prev_price: float) -> None:
        """Feed a log-return for a symbol."""
        if price <= 0 or prev_price <= 0:
            return
        if symbol not in self._returns:
            self._returns[symbol] = deque(maxlen=PCA_WINDOW)
        log_ret = float(np.log(price / prev_price))
        self._returns[symbol].append(log_ret)
        self._n_updates += 1

        if self._n_updates % PCA_RECOMPUTE_EVERY == 0:
            self._recompute_pca()

    def get_signal(self, symbol: str, direction: str) -> Tuple[float, float, bool]:
        """
        Get PCA residual quality adjustment for Gate 9.

        Returns
        -------
        quality_adj : Gate 9 quality score adjustment
        residual_z  : factor-neutral residual Z-score
        is_active   : True if PCA has enough data for this symbol
        """
        if symbol not in self._residuals or self._components is None:
            return 0.0, 0.0, False

        residual_z  = self._residuals.get(symbol, 0.0)
        loading     = self._loadings.get(symbol, np.zeros(PCA_N_COMPONENTS))
        max_loading = float(np.max(np.abs(loading))) if len(loading) > 0 else 0.0

        # Factor-dominated signal — penalise
        if max_loading > 0.90:
            return PCA_BETA_PENALTY, residual_z, True

        is_long = direction.upper() in ("BUY", "LONG")
        is_short = direction.upper() in ("SELL", "SHORT")

        if is_long and residual_z >= self._top_threshold:
            return PCA_QUALITY_BOOST, residual_z, True
        elif is_short and residual_z <= self._bot_threshold:
            return PCA_QUALITY_BOOST, residual_z, True
        else:
            return 0.0, residual_z, True

    def get_rankings(self) -> List[Tuple[str, float]]:
        """Return symbols ranked by residual Z-score (descending)."""
        return sorted(self._residuals.items(), key=lambda x: x[1], reverse=True)

    @property
    def is_ready(self) -> bool:
        filled = sum(1 for r in self._returns.values() if len(r) >= PCA_WINDOW)
        return filled >= PCA_MIN_SYMBOLS and self._components is not None

    # ─────────────────────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────────────────────

    def _recompute_pca(self) -> None:
        """Full PCA recompute using SVD on the return matrix."""
        # Build return matrix for symbols with enough data
        valid: Dict[str, np.ndarray] = {}
        for sym, buf in self._returns.items():
            if len(buf) >= PCA_WINDOW:
                valid[sym] = np.array(list(buf)[-PCA_WINDOW:])

        if len(valid) < PCA_MIN_SYMBOLS:
            return

        symbols = list(valid.keys())
        R = np.column_stack([valid[s] for s in symbols])  # (T, N)
        N = R.shape[1]

        # Demean
        R_mean = R.mean(axis=0, keepdims=True)
        R_centered = R - R_mean

        # SVD (economy)
        try:
            U, S, Vt = np.linalg.svd(R_centered, full_matrices=False)
        except np.linalg.LinAlgError:
            return

        # First K components (T, K) and loadings (K, N)
        K = min(PCA_N_COMPONENTS, len(S))
        factors  = U[:, :K] * S[:K]   # (T, K) — factor time series
        loadings = Vt[:K, :]           # (K, N) — symbol loadings

        # Residuals: R_centered - factors @ loadings
        residual_mat = R_centered - factors @ loadings  # (T, N)
        # Use last bar residuals and z-score across universe
        last_residuals = residual_mat[-1, :]
        mu_r  = float(np.mean(last_residuals))
        std_r = float(np.std(last_residuals)) + 1e-9
        z_scores = (last_residuals - mu_r) / std_r

        self._residuals  = {sym: float(z_scores[i]) for i, sym in enumerate(symbols)}
        self._loadings   = {sym: loadings[:, i] for i, sym in enumerate(symbols)}
        self._components = factors.T  # (K, T)

        # Percentile thresholds
        arr = np.array(list(z_scores))
        self._top_threshold = float(np.percentile(arr, PCA_TOP_QUARTILE * 100))
        self._bot_threshold = float(np.percentile(arr, PCA_BOT_QUARTILE * 100))
