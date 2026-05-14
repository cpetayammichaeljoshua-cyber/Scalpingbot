#!/usr/bin/env python3
"""
VPIN Order-Flow Toxicity Model  [Unity Engine v18.72]
══════════════════════════════════════════════════════
Volume-synchronized Probability of Informed Trading (VPIN).

Strategy: Order Flow Toxicity Model — Liquidity Stress
  • Uses 1-minute trade volume data with buy/sell imbalance
  • Partitions total volume into equal-size volume buckets (V_bucket)
  • Estimates VPIN = |buy_volume - sell_volume| / total_volume per bucket
  • Tracks rolling VPIN over last 50 buckets
  • Reduces position size / blocks new entries when VPIN > 90th-percentile
    of historical distribution (liquidity stress indicator)

Integration:
  • Feeds Gate 9 quality penalty: -6 pts when VPIN > 90th pct
  • Kelly multiplier: 0.75× when VPIN > 90th pct
  • Fully operational in pure-Python (no external deps beyond numpy)

v18.72: Initial integration. Volume-bucket VPIN with rolling 50-bucket window.
        Aggressive buy/sell classification via tick rule (trade vs prev price).
        VPIN percentile tracked over 200-bucket history. Gate 9 penalty -6pts
        when VPIN > 90th pct (historically unstable liquidity).
"""

import numpy as np
import logging
from collections import deque
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
VPIN_BUCKET_SIZE    = 5_000     # volume per bucket (scaled for crypto; adjustable)
VPIN_WINDOW         = 50        # number of buckets in rolling VPIN estimate
VPIN_HISTORY        = 200       # historical buckets for percentile computation
VPIN_TOXIC_PCT      = 0.90      # VPIN > 90th percentile → toxic / reduce exposure
VPIN_GATE_PENALTY   = -6.0      # quality pts removed when VPIN is toxic
VPIN_KELLY_MULT     = 0.75      # Kelly multiplier when VPIN is toxic
VPIN_MILD_PCT       = 0.75      # VPIN > 75th pct → mild caution
VPIN_MILD_PENALTY   = -2.0      # mild quality penalty


class VPINModel:
    """
    VPIN (Volume-synchronized Probability of Informed Trading) estimator.

    Algorithm (Easley, Lopez de Prado & O'Hara 2012):
      1. Accumulate aggressively-classified buy/sell volumes.
      2. When accumulated volume ≥ V_bucket, record |BuyVol - SellVol| / V_bucket as VPIN.
      3. Rolling VPIN = average of last VPIN_WINDOW buckets.
      4. VPIN percentile relative to VPIN_HISTORY buckets → risk signal.

    Tick-rule classification:
      trade_price > prev_price → BUY
      trade_price < prev_price → SELL
      trade_price = prev_price → inherit last direction
    """

    def __init__(self):
        self._bucket_buy_vol:  float = 0.0
        self._bucket_sell_vol: float = 0.0
        self._bucket_total:    float = 0.0
        self._last_price:      float = 0.0
        self._last_dir:        int   = 0     # +1 buy, -1 sell

        self._recent_vpins: deque = deque(maxlen=VPIN_WINDOW)
        self._all_vpins:    deque = deque(maxlen=VPIN_HISTORY)

        self._current_vpin: float = 0.0
        self._vpin_pct:     float = 0.0
        self._toxic:        bool  = False

        self._buckets_filled: int = 0

        logger.info("✅ [VPIN] VPIN Order-Flow Toxicity Model initialised "
                    f"(bucket={VPIN_BUCKET_SIZE:,}, window={VPIN_WINDOW}, toxic_pct={VPIN_TOXIC_PCT:.0%})")

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def on_trade(self, price: float, volume: float) -> None:
        """
        Process a single trade tick.

        Parameters
        ----------
        price  : trade execution price
        volume : trade volume in base asset
        """
        if price <= 0 or volume <= 0:
            return

        # Tick-rule classification
        if price > self._last_price and self._last_price > 0:
            direction = 1
        elif price < self._last_price:
            direction = -1
        else:
            direction = self._last_dir or 1

        self._last_price = price
        self._last_dir   = direction

        if direction > 0:
            self._bucket_buy_vol  += volume
        else:
            self._bucket_sell_vol += volume
        self._bucket_total += volume

        # Check if bucket is full
        if self._bucket_total >= VPIN_BUCKET_SIZE:
            vpin_val = abs(self._bucket_buy_vol - self._bucket_sell_vol) / max(self._bucket_total, 1e-9)
            self._recent_vpins.append(vpin_val)
            self._all_vpins.append(vpin_val)
            self._buckets_filled += 1

            # Update rolling VPIN
            self._current_vpin = float(np.mean(self._recent_vpins))

            # Update percentile
            if len(self._all_vpins) >= 10:
                arr = np.array(self._all_vpins)
                pct_90 = float(np.percentile(arr, VPIN_TOXIC_PCT * 100))
                pct_75 = float(np.percentile(arr, VPIN_MILD_PCT * 100))
                # Percentile rank of current VPIN
                self._vpin_pct = float(np.searchsorted(np.sort(arr), self._current_vpin) / len(arr))
                self._toxic = self._current_vpin >= pct_90

            # Reset bucket
            self._bucket_buy_vol  = 0.0
            self._bucket_sell_vol = 0.0
            self._bucket_total    = 0.0

    def on_kline(self, close: float, volume: float, is_green: bool) -> None:
        """
        Simplified ingestor from OHLCV kline data (when tick data unavailable).
        Approximates buy/sell split using bar direction and volume.

        Parameters
        ----------
        close    : close price
        volume   : bar volume in base asset
        is_green : True if close > open (buy bar)
        """
        if volume <= 0:
            return
        # Conservative bulk-volume classification: 60/40 split in bar direction
        if is_green:
            buy_vol  = volume * 0.60
            sell_vol = volume * 0.40
        else:
            buy_vol  = volume * 0.40
            sell_vol = volume * 0.60

        for _ in range(max(1, int(volume / (VPIN_BUCKET_SIZE * 0.1)))):
            self.on_trade(close, min(VPIN_BUCKET_SIZE * 0.1, buy_vol))
            self.on_trade(close - 0.001, min(VPIN_BUCKET_SIZE * 0.1, sell_vol))

    def get_signal(self) -> Tuple[float, float, float, bool]:
        """
        Return VPIN signal for Gate 9 integration.

        Returns
        -------
        vpin      : current rolling VPIN value (0–1)
        vpin_pct  : percentile rank in historical distribution (0–1)
        quality_adj : Gate 9 quality score adjustment (negative = penalty)
        is_toxic  : True when VPIN > 90th percentile
        """
        if self._buckets_filled < VPIN_WINDOW:
            return self._current_vpin, self._vpin_pct, 0.0, False

        if self._vpin_pct >= VPIN_TOXIC_PCT:
            quality_adj = VPIN_GATE_PENALTY
        elif self._vpin_pct >= VPIN_MILD_PCT:
            quality_adj = VPIN_MILD_PENALTY
        else:
            quality_adj = 0.0

        return self._current_vpin, self._vpin_pct, quality_adj, self._toxic

    def get_kelly_multiplier(self) -> float:
        """Return Kelly multiplier based on VPIN toxicity."""
        if self._buckets_filled < VPIN_WINDOW:
            return 1.0
        if self._vpin_pct >= VPIN_TOXIC_PCT:
            return VPIN_KELLY_MULT
        elif self._vpin_pct >= VPIN_MILD_PCT:
            return 0.90
        return 1.0

    @property
    def is_ready(self) -> bool:
        return self._buckets_filled >= VPIN_WINDOW

    @property
    def current_vpin(self) -> float:
        return self._current_vpin

    @property
    def is_toxic(self) -> bool:
        return self._toxic
