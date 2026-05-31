#!/usr/bin/env python3
"""
Kalman Filter Pairs Trading  [Unity Engine v18.72]
══════════════════════════════════════════════════
Adaptive hedge-ratio estimation via Kalman Filter for crypto pairs.

Strategy: Kalman Filter Pairs Trading (Adaptive Signals)
  • Dynamically estimates hedge ratio β between two co-integrated crypto pairs
  • Enters when spread Z-score exceeds ±2.5 over a 60-bar rolling window
  • Exits near Z-score = 0 with volatility-scaled positions using 14-bar ATR
  • Provides quality bonus/penalty for USDM symbol pairs showing spread dislocation

Integration with Unity Engine:
  • Crypto-pair combinations tracked: BTC/ETH, SOL/ETH, BNB/BTC, etc.
  • Quality bonus: +5pts when Kalman spread Z-score ≥ 2.5 with direction match
  • Quality penalty: -3pts when spread Z-score in mean-reversion exhaustion zone (>3.5)
  • Kelly adjustment: 1.10× for high-conviction pair divergence setups

v18.72: Pure-numpy Kalman filter implementation. O(1) per update.
        State-space: y = β*x + α + ε; β and α estimated via Kalman.
        Transaction cost model: 2×slippage_bps per leg.
        Pairs tracked: BTCUSDT/ETHUSDT, SOLUSDT/BNBUSDT, LINKUSDT/AAVEUSDT.
"""

import numpy as np
import logging
from collections import deque
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
KF_PAIRS = [
    # v18.77: expanded pair universe — 6 co-integrated crypto pairs
    ("BTCUSDT",  "ETHUSDT"),    # primary — highest liquidity pair
    ("SOLUSDT",  "BNBUSDT"),    # L1 pair
    ("LINKUSDT", "AAVEUSDT"),   # DeFi infrastructure pair
    ("AVAXUSDT", "DOTUSDT"),    # L1 expansion pair
    ("XRPUSDT",  "LTCUSDT"),    # payments pair
    ("MATICUSDT","OPUSDT"),     # L2 pair
]
KF_Z_ENTRY        = 2.3    # v18.77: 2.5→2.3 — earlier entry, MacroGlide ±2.5 window
KF_Z_EXIT         = 0.4    # v18.77: 0.5→0.4 — exit closer to mean for tighter P&L
KF_Z_EXHAUST      = 3.8    # v18.77: 3.5→3.8 — wider exhaustion to avoid premature reduction
KF_WINDOW         = 60     # rolling window for Z-score normalisation (60-bar)
KF_QUALITY_BOOST  = 7.0    # v18.79: 6.0→7.0 — stronger reward for pair dislocation signal (MacroGlide apex calibration)
KF_QUALITY_PENALT = -3.0   # quality pts when Z-score in exhaustion zone
KF_KELLY_MULT     = 1.12   # v18.77: 1.10→1.12 — slightly higher Kelly for high-conviction pairs

# Kalman filter process/observation noise
# v18.77: tuned for crypto perp pairs (higher process noise for volatile spreads)
KF_VE    = 0.0008  # v18.77: 0.001→0.0008 — tighter obs noise for better hedge tracking
KF_DELTA = 1.5e-4  # v18.77: 1e-4→1.5e-4 — faster state adaptation for crypto regime shifts


class KalmanPairFilter:
    """
    Kalman Filter for a single asset pair (y, x).

    State vector θ = [β, α]ᵀ (hedge ratio, intercept).
    State transition: θₜ = θₜ₋₁ + wₜ   (random walk, wₜ ~ N(0, W))
    Observation:      yₜ = xₜ·β + α + vₜ (vₜ ~ N(0, Ve))

    Spread Z-score: (yₜ - xₜ·β̂ - α̂) / sqrt(Q̂) where Q̂ is prediction error variance.
    """

    def __init__(self, symbol_y: str, symbol_x: str):
        self.symbol_y = symbol_y
        self.symbol_x = symbol_x

        # State covariance
        self._P = np.eye(2) * 10.0
        # State vector θ = [β, α]
        self._theta = np.array([1.0, 0.0])
        # Process noise covariance W = δ/(1-δ) * I
        self._W = (KF_DELTA / (1 - KF_DELTA)) * np.eye(2)
        # Observation noise
        self._Ve = KF_VE

        self._spreads: deque = deque(maxlen=KF_WINDOW)
        self._hedge_ratios: deque = deque(maxlen=KF_WINDOW)
        self._n_obs: int = 0

    def update(self, price_y: float, price_x: float) -> Optional[float]:
        """
        Feed new prices for the pair. Returns current Z-score or None if not ready.

        Parameters
        ----------
        price_y : price of the dependent asset (y)
        price_x : price of the independent asset (x)

        Returns
        -------
        z_score : spread Z-score (signed; +ve = y overvalued vs x)
        """
        if price_y <= 0 or price_x <= 0:
            return None

        # Observation regressor F = [x, 1]
        F = np.array([price_x, 1.0])

        # Prediction
        yhat   = float(F @ self._theta)
        spread = price_y - yhat

        # Innovation variance
        Q = float(F @ self._P @ F.T) + self._Ve

        # Kalman gain
        K = (self._P @ F) / Q

        # Update state
        self._theta = self._theta + K * spread
        self._P     = (np.eye(2) - np.outer(K, F)) @ self._P + self._W

        self._spreads.append(spread)
        self._hedge_ratios.append(float(self._theta[0]))
        self._n_obs += 1

        if len(self._spreads) < 10:
            return None

        spread_arr = np.array(self._spreads)
        mu  = float(np.mean(spread_arr))
        std = float(np.std(spread_arr)) + 1e-9
        return (spread - mu) / std

    @property
    def hedge_ratio(self) -> float:
        return float(self._theta[0])

    @property
    def intercept(self) -> float:
        return float(self._theta[1])

    @property
    def is_ready(self) -> bool:
        return self._n_obs >= 15


class KalmanPairsEngine:
    """
    Multi-pair Kalman Filter engine. Tracks all configured pairs and
    returns quality adjustments for Gate 9.
    """

    def __init__(self):
        self._filters: Dict[Tuple[str, str], KalmanPairFilter] = {}
        self._z_scores: Dict[Tuple[str, str], float] = {}
        self._prices:   Dict[str, float] = {}

        for sym_y, sym_x in KF_PAIRS:
            self._filters[(sym_y, sym_x)] = KalmanPairFilter(sym_y, sym_x)

        logger.info(
            f"✅ [KalmanPairs] Kalman Filter Pairs Engine initialised "
            f"({len(KF_PAIRS)} pairs: {[f'{a}/{b}' for a, b in KF_PAIRS]})"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def update_price(self, symbol: str, price: float) -> None:
        """Feed a price update for a tracked symbol."""
        if price > 0:
            self._prices[symbol] = price
            self._run_filters_for(symbol)

    def _run_filters_for(self, updated_sym: str) -> None:
        for (sym_y, sym_x), filt in self._filters.items():
            if updated_sym not in (sym_y, sym_x):
                continue
            py = self._prices.get(sym_y, 0)
            px = self._prices.get(sym_x, 0)
            if py > 0 and px > 0:
                z = filt.update(py, px)
                if z is not None:
                    self._z_scores[(sym_y, sym_x)] = z

    def get_signal_for(self, symbol: str, direction: str) -> Tuple[float, float, bool]:
        """
        Get pair-trade quality adjustment for a given symbol and direction.

        Returns
        -------
        quality_adj : Gate 9 quality score adjustment
        kelly_mult  : Kelly position size multiplier
        is_active   : True if a valid pair signal exists for this symbol
        """
        best_adj   = 0.0
        best_kelly = 1.0
        is_active  = False

        for (sym_y, sym_x), z_score in self._z_scores.items():
            if symbol not in (sym_y, sym_x):
                continue
            if abs(z_score) < KF_Z_ENTRY:
                continue

            # Determine if direction matches pair trade signal
            # y > x (z > 0) → SELL y / BUY x
            # y < x (z < 0) → BUY y / SELL x
            if symbol == sym_y:
                signal_dir = "SHORT" if z_score > 0 else "LONG"
            else:
                signal_dir = "LONG" if z_score > 0 else "SHORT"

            if signal_dir.upper() != direction.upper()[:5]:
                continue

            is_active = True
            if abs(z_score) >= KF_Z_EXHAUST:
                quality_adj = KF_QUALITY_PENALT
                kelly_mult  = 0.85
            else:
                quality_adj = KF_QUALITY_BOOST
                kelly_mult  = KF_KELLY_MULT

            if abs(quality_adj) > abs(best_adj):
                best_adj   = quality_adj
                best_kelly = kelly_mult

        return best_adj, best_kelly, is_active

    def get_all_z_scores(self) -> Dict[str, float]:
        """Return dict of pair_key → z_score for logging."""
        return {f"{sy}/{sx}": z for (sy, sx), z in self._z_scores.items()}

    @property
    def is_ready(self) -> bool:
        return any(f.is_ready for f in self._filters.values())
