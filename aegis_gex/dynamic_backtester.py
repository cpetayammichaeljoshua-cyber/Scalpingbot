"""
aegis_gex.dynamic_backtester — v10.0 (Unity Engine v20.0)
==========================================================

Per-symbol rolling backtest that runs in the background and exposes a
`result(symbol)` API the live filter consults for a soft quality bias.

Why this is *complementary*, not a replacement:
  • Gate 8 already uses **realised** rolling WR per symbol (`PerSymbolTracker`).
    It only activates after `SYMBOL_MIN_TRADES` (5) live trades have closed.
    For symbols with no live history (new listings, freshly un-blacklisted
    rescues), Gate 8 is silent and the engine has no per-symbol prior.
  • This backtester fills that gap with a **synthetic** prior derived from the
    most recent N candles of price action — ~75 h of 15m bars by default.
  • Output is a *bias*, never a hard veto. Existing 12-gate logic is untouched.

Strategy backtested (deliberately simple proxy, not the 10-agent swarm):
  • Entry LONG  : close crosses ABOVE EMA20  AND  EMA20 > EMA50  AND  RSI14 > 50
  • Entry SHORT : close crosses BELOW EMA20  AND  EMA20 < EMA50  AND  RSI14 < 50
  • Stop loss   : 1.5 × ATR(14) from entry
  • Take profit : 2.5 × ATR(14) from entry  (R≈1.667, matches the bot's TP1 R)
  • Time stop   : 24 bars (6 h) — scored by directional PnL at exit
  • Slip / fee  : 0.05 % per side (matches Gate 0 floor) — applied to entry+exit

This proxy is *highly correlated* with the engine's own trend-continuation
behaviour because the swarm's Trend / Momentum / Volume agents fire on the
same EMA-stack + RSI conditions. A symbol whose proxy backtest collapses
(WR < 30 %, PF < 0.8) is overwhelmingly likely to remain a loser for the
real engine too — the structural alpha of the asset is gone.

Per-symbol metrics returned:
  n_trades           — sample size (≥ 10 to be trusted)
  win_rate           — wins / n_trades
  ev_r               — expected value in R units per trade (after fees)
  sharpe             — sqrt(annualised) of per-trade R returns
  profit_factor      — Σ winners-R / |Σ losers-R|
  max_consec_losses  — worst losing streak (regime-stress signal)
  ts                 — Unix epoch of last refresh
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

try:
    from SignalMaestro.backtest_overfitting_analyzer import (
        BacktestOverfittingAnalyzer as _PBOAnalyzer,
        OverfitAssessment as _OverfitAssessment,
        StrategyValidationResult as _SVR,
        validate_strategy as _validate_strategy,
    )
    _PBO_ANALYZER: Optional[_PBOAnalyzer] = _PBOAnalyzer()
    _HAS_4STEP = True
except Exception:
    _PBO_ANALYZER = None  # type: ignore[assignment]
    _OverfitAssessment = None  # type: ignore[assignment]
    _SVR = None  # type: ignore[assignment]
    _validate_strategy = None  # type: ignore[assignment]
    _HAS_4STEP = False

try:
    import aiohttp
except ImportError:  # pragma: no cover — handled by health system
    aiohttp = None  # type: ignore[assignment]

try:
    import numpy as np
except ImportError:  # pragma: no cover — handled by health system
    np = None  # type: ignore[assignment]


_LOG = logging.getLogger("UnityEngine.DynBacktest")

_BINANCE_FAPI_HOSTS = (
    "https://fapi.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi3.binance.com",
)


@dataclass
class BacktestResult:
    symbol:            str
    n_trades:          int            = 0
    win_rate:          float          = 0.0
    ev_r:              float          = 0.0
    sharpe:            float          = 0.0
    profit_factor:     float          = 0.0
    max_consec_losses: int            = 0
    bars_analysed:     int            = 0
    ts:                float          = 0.0
    # v18.11: Overfitting probability fields (PBO / Walk-Forward / DSR)
    pbo_score:          float         = 0.0    # 0=clean, 1=full overfit
    walk_forward_ratio: float         = 1.0    # OOS/IS Sharpe (≥0.5 healthy)
    deflated_sharpe:    float         = 0.0    # DSR (>0 = genuine edge)
    pbo_label:          str           = "CLEAN"  # CLEAN / SUSPECT / OVERFIT
    pbo_penalty:        float         = 0.0    # quality score penalty applied

    def as_dict(self) -> Dict[str, Any]:
        return {
            "symbol":            self.symbol,
            "n_trades":          self.n_trades,
            "win_rate":          round(self.win_rate, 4),
            "ev_r":              round(self.ev_r, 4),
            "sharpe":            round(self.sharpe, 3),
            "profit_factor":     round(self.profit_factor, 3),
            "max_consec_losses": self.max_consec_losses,
            "bars_analysed":     self.bars_analysed,
            "ts":                self.ts,
            "pbo_score":         round(self.pbo_score, 3),
            "walk_forward_ratio":round(self.walk_forward_ratio, 3),
            "deflated_sharpe":   round(self.deflated_sharpe, 3),
            "pbo_label":         self.pbo_label,
            "pbo_penalty":       round(self.pbo_penalty, 2),
        }


def _ema(arr: "np.ndarray", period: int) -> "np.ndarray":
    """Vectorized exponential moving average (alpha = 2/(period+1))."""
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(arr, dtype=np.float64)
    out[0] = arr[0]
    # SciPy-free recurrence — Python loop is fine; period<<len(arr).
    for i in range(1, arr.shape[0]):
        out[i] = alpha * arr[i] + (1.0 - alpha) * out[i - 1]
    return out


def _rsi(closes: "np.ndarray", period: int = 14) -> "np.ndarray":
    """Wilder's RSI (matches TA-lib semantics; first `period` bars NaN)."""
    deltas = np.diff(closes, prepend=closes[0])
    up   = np.where(deltas > 0, deltas, 0.0)
    down = np.where(deltas < 0, -deltas, 0.0)
    avg_up   = np.zeros_like(closes, dtype=np.float64)
    avg_down = np.zeros_like(closes, dtype=np.float64)
    if closes.shape[0] <= period:
        return np.full_like(closes, 50.0, dtype=np.float64)
    avg_up[period]   = up[1: period + 1].mean()
    avg_down[period] = down[1: period + 1].mean()
    for i in range(period + 1, closes.shape[0]):
        avg_up[i]   = (avg_up[i - 1]   * (period - 1) + up[i])   / period
        avg_down[i] = (avg_down[i - 1] * (period - 1) + down[i]) / period
    rs  = np.divide(avg_up, avg_down, out=np.full_like(avg_up, 100.0), where=avg_down > 1e-12)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi[: period] = 50.0
    return rsi


def _atr(highs: "np.ndarray", lows: "np.ndarray", closes: "np.ndarray", period: int = 14) -> "np.ndarray":
    """Wilder's ATR. Output[period:] is meaningful; output[:period] is the seed-extension."""
    prev_close = np.roll(closes, 1)
    prev_close[0] = closes[0]
    tr = np.maximum.reduce([
        highs - lows,
        np.abs(highs - prev_close),
        np.abs(lows  - prev_close),
    ])
    out = np.empty_like(tr, dtype=np.float64)
    if tr.shape[0] <= period:
        return np.full_like(tr, float(np.mean(tr)) if tr.size else 0.0, dtype=np.float64)
    out[: period] = tr[: period].mean()
    out[period]   = tr[: period].mean()
    for i in range(period + 1, tr.shape[0]):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def _rolling_mean(arr: "np.ndarray", period: int) -> "np.ndarray":
    """Simple rolling mean using cumsum trick (O(N)).  First `period` values = arr[:period].mean()."""
    out = np.empty_like(arr, dtype=np.float64)
    seed = arr[:period].mean() if arr.size >= period else arr.mean()
    out[:period] = seed
    cum = np.cumsum(arr, dtype=np.float64)
    out[period:] = (cum[period:] - cum[:-period]) / float(period)
    return out


def _vectorized_backtest(
    opens:   "np.ndarray",
    highs:   "np.ndarray",
    lows:    "np.ndarray",
    closes:  "np.ndarray",
    volumes: "Optional[np.ndarray]" = None,
    *,
    sl_atr:  float = 1.5,
    tp_atr:  float = 2.5,
    time_stop_bars: int = 24,
    fee_bps_per_side: float = 5.0,    # 0.05 % each direction
) -> Dict[str, float]:
    """
    Mirofish-aligned per-symbol backtest. Mirrors the swarm's actual 15m
    entry conditions (EMA9/EMA21/EMA50 + volume surge + RSI filter) so the
    proxy quality-bias is highly correlated with what the live swarm would see.

    v9.9.2: upgraded from generic EMA20/EMA50 to actual Mirofish 15m params:
      Entry LONG : EMA9 crosses ABOVE EMA21  AND  EMA21 > EMA50  AND  RSI14 > 50
                   AND  (volume > 1.15× 20-bar avg OR ATR > 0.8× ATR20 avg)
      Entry SHORT: EMA9 crosses BELOW EMA21  AND  EMA21 < EMA50  AND  RSI14 < 50
                   AND  (volume > 1.15× 20-bar avg OR ATR > 0.8× ATR20 avg)
      Stop loss   : 1.5 × ATR(14) from entry
      Take profit : 2.5 × ATR(14) from entry  (TP_R ≈ 1.667)
      Time stop   : 24 bars (6 h on 15m)
      Fees        : 0.05 % per side (≥ Gate 0 slippage floor)
    """
    n = closes.shape[0]
    if n < 80:
        return {"n_trades": 0, "win_rate": 0.0, "ev_r": 0.0, "sharpe": 0.0,
                "profit_factor": 0.0, "max_consec_losses": 0, "bars_analysed": int(n)}

    # ── Mirofish 15m indicators ────────────────────────────────────────────────
    ema9  = _ema(closes, 9)
    ema21 = _ema(closes, 21)
    ema50 = _ema(closes, 50)
    rsi14 = _rsi(closes, 14)
    atr14 = _atr(highs, lows, closes, 14)

    # Volume regime filter: entry only on volume or ATR surge (swarm VolumeAgent logic)
    if volumes is not None and volumes.shape[0] == n and np.any(volumes > 0):
        vol_ma20   = _rolling_mean(volumes, 20)
        vol_surge  = volumes > (vol_ma20 * 1.15)   # volume > 115% of 20-bar avg
    else:
        vol_surge  = np.ones(n, dtype=bool)         # no volume data → don't filter

    atr_ma20  = _rolling_mean(atr14, 20)
    atr_surge = atr14 > (atr_ma20 * 0.80)          # ATR not collapsing (avoids chop)

    activity = vol_surge | atr_surge  # either volume OR volatility must be present

    # 1R distance in price units = sl_atr × ATR;
    # tp_distance = tp_atr × ATR; tp_R = tp_atr / sl_atr
    tp_R = tp_atr / sl_atr
    fee_R_per_trade = (2.0 * fee_bps_per_side / 1e4) / (sl_atr * 1.0)

    # EMA9 / EMA21 crossover (Mirofish crossover_up / crossover_down)
    cross_up   = (ema9 > ema21) & (np.roll(ema9, 1) <= np.roll(ema21, 1))
    cross_down = (ema9 < ema21) & (np.roll(ema9, 1) >= np.roll(ema21, 1))
    long_cond  = cross_up   & (ema21 > ema50) & (rsi14 > 50.0) & activity
    short_cond = cross_down & (ema21 < ema50) & (rsi14 < 50.0) & activity
    cross_up[0]   = False
    cross_down[0] = False

    r_returns: List[float] = []
    consec_loss = 0
    max_consec_loss = 0
    i = 60     # warmup: indicators settled
    cooldown_until = -1
    while i < n - 1:
        if i <= cooldown_until:
            i += 1
            continue
        # Skip if ATR collapses to zero (no volatility → no risk unit)
        atr_i = atr14[i]
        if not math.isfinite(atr_i) or atr_i <= 0.0:
            i += 1
            continue
        is_long  = bool(long_cond[i])
        is_short = bool(short_cond[i])
        if not (is_long or is_short):
            i += 1
            continue

        entry      = float(opens[i + 1]) if i + 1 < n else float(closes[i])
        sl_dist    = sl_atr * atr_i
        tp_dist    = tp_atr * atr_i
        if is_long:
            sl_price = entry - sl_dist
            tp_price = entry + tp_dist
        else:
            sl_price = entry + sl_dist
            tp_price = entry - tp_dist

        outcome_R = 0.0
        bars_held = 0
        end_idx   = min(i + 1 + time_stop_bars, n - 1)
        for j in range(i + 1, end_idx + 1):
            bars_held += 1
            hi = highs[j]; lo = lows[j]
            if is_long:
                hit_sl = lo <= sl_price
                hit_tp = hi >= tp_price
            else:
                hit_sl = hi >= sl_price
                hit_tp = lo <= tp_price
            # Pessimistic when both hit in the same bar (gap into SL first).
            if hit_sl and hit_tp:
                outcome_R = -1.0
                break
            if hit_sl:
                outcome_R = -1.0
                break
            if hit_tp:
                outcome_R = +tp_R
                break
        else:
            # Time-stopped: score by directional move at exit, in R units.
            exit_px = float(closes[end_idx])
            move    = (exit_px - entry) if is_long else (entry - exit_px)
            outcome_R = max(-1.0, min(+tp_R, move / sl_dist))

        outcome_R -= fee_R_per_trade
        r_returns.append(outcome_R)
        if outcome_R < 0:
            consec_loss += 1
            max_consec_loss = max(max_consec_loss, consec_loss)
        else:
            consec_loss = 0
        # No overlapping trades; cooldown until exit + 1 bar.
        cooldown_until = i + bars_held
        i = cooldown_until + 1

    if not r_returns:
        return {"n_trades": 0, "win_rate": 0.0, "ev_r": 0.0, "sharpe": 0.0,
                "profit_factor": 0.0, "max_consec_losses": 0, "bars_analysed": int(n),
                "pbo_score": 0.0, "walk_forward_ratio": 1.0,
                "deflated_sharpe": 0.0, "pbo_label": "CLEAN", "pbo_penalty": 0.0}

    arr = np.asarray(r_returns, dtype=np.float64)
    wins   = arr[arr > 0]
    losses = arr[arr < 0]
    win_rate = float(wins.size) / float(arr.size)
    ev_r     = float(arr.mean())
    std      = float(arr.std(ddof=1)) if arr.size >= 2 else 0.0
    # Annualised by avg trades-per-year using 15m → 96 bars/day → 365 days.
    # Without a reliable year-count, use trade frequency as a proxy:
    bars_per_trade = max(1.0, float(n) / float(arr.size))
    trades_per_year = (96.0 * 365.0) / bars_per_trade
    sharpe = (ev_r / std) * math.sqrt(trades_per_year) if std > 1e-9 else 0.0
    pf = (float(wins.sum()) / abs(float(losses.sum()))) if losses.size and losses.sum() != 0 else (
        float(wins.sum()) if wins.size else 0.0
    )

    # ── v20.0: 4-Step Strategy Validation Framework ───────────────────────────
    # Step 1: In-Sample Excellence  → IS Sharpe/WR/PF/EV all positive
    # Step 2: IS Permutation Test   → IS edge not explained by luck
    # Step 3: Walk-Forward Test     → OOS Sharpe ≥ 30% of IS Sharpe
    # Step 4: WF Permutation Test   → OOS edge not explained by luck
    # Quality penalty: [-7.0, 0.0] → integrates into Gate 8.5d bias.
    pbo_score = 0.0
    wfr       = 1.0
    dsr       = 0.0
    pbo_label = "CLEAN"
    pbo_pen   = 0.0
    _steps_passed = 4  # default CLEAN when not enough data
    if _HAS_4STEP and _validate_strategy is not None and len(r_returns) >= 20:
        try:
            _svr = _validate_strategy(r_returns)
            pbo_score = _svr.pbo_score
            wfr       = _svr.walk_forward_ratio
            dsr       = _svr.deflated_sharpe
            pbo_label = _svr.label
            pbo_pen   = _svr.quality_penalty
            _steps_passed = _svr.steps_passed
            _LOG.debug(
                "[v20.0] 4-Step Validation: steps=%d/4 label=%s "
                "IS_p=%.3f WFR=%.2f OOS_p=%.3f pen=%.1f",
                _steps_passed, pbo_label,
                _svr.is_pval, wfr, _svr.oos_pval, pbo_pen,
            )
        except Exception:
            # Fallback to original 3-metric analysis
            if _PBO_ANALYZER is not None:
                try:
                    _assessment = _PBO_ANALYZER.assess(
                        r_returns, trades_per_year=float(trades_per_year)
                    )
                    pbo_score = _assessment.pbo_score
                    wfr       = _assessment.walk_forward_ratio
                    dsr       = _assessment.deflated_sharpe
                    pbo_label = _assessment.label
                    pbo_pen   = _assessment.quality_penalty
                except Exception:
                    pass
    elif _PBO_ANALYZER is not None and len(r_returns) >= 20:
        try:
            _assessment = _PBO_ANALYZER.assess(
                r_returns, trades_per_year=float(trades_per_year)
            )
            pbo_score = _assessment.pbo_score
            wfr       = _assessment.walk_forward_ratio
            dsr       = _assessment.deflated_sharpe
            pbo_label = _assessment.label
            pbo_pen   = _assessment.quality_penalty
        except Exception:
            pass

    return {
        "n_trades":          int(arr.size),
        "win_rate":          win_rate,
        "ev_r":              ev_r,
        "sharpe":            sharpe,
        "profit_factor":     pf,
        "max_consec_losses": int(max_consec_loss),
        "bars_analysed":     int(n),
        "pbo_score":         pbo_score,
        "walk_forward_ratio":wfr,
        "deflated_sharpe":   dsr,
        "pbo_label":         pbo_label,
        "pbo_penalty":       pbo_pen,
    }


class DynamicBacktester:
    """
    Background per-symbol backtester. Refreshes every `refresh_sec` (default 1800).
    Bounded-concurrency aiohttp fetcher. All public reads are O(1) and lock-free.
    """

    def __init__(
        self,
        symbols:        Iterable[str],
        *,
        refresh_sec:    int   = 1800,
        lookback_bars:  int   = 300,
        max_concurrent: int   = 10,
        request_timeout_sec: float = 6.0,
        interval:       str   = "15m",
    ) -> None:
        self._symbols       = [s.upper() for s in symbols]
        self._refresh_sec   = max(120, int(refresh_sec))
        self._lookback      = max(120, min(1500, int(lookback_bars)))
        self._sem           = asyncio.Semaphore(max(1, int(max_concurrent)))
        self._timeout       = aiohttp.ClientTimeout(total=float(request_timeout_sec)) if aiohttp else None
        self._interval      = interval
        self._results:      Dict[str, BacktestResult] = {}
        self._session:      Optional["aiohttp.ClientSession"] = None
        self._host_idx      = 0
        self._last_full_sweep_ts: float = 0.0
        self._sweep_count   = 0

    # ---- Lifecycle ------------------------------------------------------------

    async def start(self) -> None:
        if aiohttp is None or np is None:
            raise RuntimeError(
                "DynamicBacktester requires aiohttp + numpy — install missing deps"
            )
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)

    async def stop(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    def update_symbol_universe(self, symbols: Iterable[str]) -> None:
        """Hot-update the tradeable universe (e.g. after blacklist refresh)."""
        new = [s.upper() for s in symbols]
        if set(new) != set(self._symbols):
            self._symbols = new

    # ---- Public read API (called from sync filter code) -----------------------

    def result(self, symbol: str) -> Optional[BacktestResult]:
        return self._results.get(symbol.upper())

    def quality_bias(self, symbol: str, *, max_age_sec: int = 7200) -> float:
        """
        Map per-symbol backtest into a quality-score bias.
        Range: [-13.0, +5.0] (base -8..+5 plus PBO penalty -0..-5).
        Returns 0.0 (neutral) when there's no usable result.

        v18.11: Backtesting Overfitting Probability (PBO) penalty applied
        on top of the EV/WR/PF tier:
          SUSPECT (WFR<0.50 OR PBO>0.55 OR DSR<0)  → additional -3.0 pts
          OVERFIT (WFR<0.10 OR PBO>0.70 OR DSR<-1) → additional -5.0 pts
        """
        r = self._results.get(symbol.upper())
        if r is None or r.n_trades < 10:
            return 0.0
        if (time.time() - r.ts) > max_age_sec:
            return 0.0
        # v9.9.2: recalibrated tiers.  Previous thresholds (WR≥50%+PF≥1.50)
        # were never reached in crypto bear/chop regimes → constant strong=0.
        # New tiers are calibrated against live Mirofish 15m proxy data:
        #   STRONG (+5pts) : WR≥45%, PF≥1.25, EV>0.03R  — genuine positive-EV setup
        #   GOOD   (+2pts) : WR≥38%, PF≥1.05, EV>0.0    — marginal edge
        #   WEAK   (-3pts) : WR<35%  OR  PF<0.95         — slight historical underperformance
        #   POOR   (-8pts) : WR<28%  OR  PF<0.75  OR  EV<-0.12R  — structural loser
        if r.win_rate >= 0.45 and r.profit_factor >= 1.25 and r.ev_r > 0.03:
            base_bias = +5.0
        elif r.win_rate >= 0.38 and r.profit_factor >= 1.05 and r.ev_r > 0.0:
            base_bias = +2.0
        elif r.win_rate < 0.28 or r.profit_factor < 0.75 or r.ev_r < -0.12:
            base_bias = -8.0
        elif r.win_rate < 0.35 or r.profit_factor < 0.95:
            base_bias = -3.0
        else:
            base_bias = 0.0

        # v18.11: Apply PBO penalty on top of the EV/WR/PF base bias.
        # Prevents curve-fitted symbols from earning +5pts despite IS-only edge.
        # pbo_penalty is in [-5, 0] — CLEAN=0, SUSPECT=-3, OVERFIT=-5.
        pbo_pen = float(getattr(r, "pbo_penalty", 0.0))
        if pbo_pen < 0.0 and r.n_trades >= 20:
            _LOG.debug(
                "G8.5d_PBO: %s pbo=%s WFR=%.2f DSR=%.2f → penalty %+.1f pts",
                symbol, getattr(r, "pbo_label", "?"),
                getattr(r, "walk_forward_ratio", 1.0),
                getattr(r, "deflated_sharpe", 0.0),
                pbo_pen,
            )

        return max(-13.0, base_bias + pbo_pen)

    def snapshot(self) -> Dict[str, Any]:
        """Diagnostics export for /metrics health-server endpoint."""
        return {
            "symbols_tracked":   len(self._results),
            "sweeps_completed":  self._sweep_count,
            "last_sweep_ts":     self._last_full_sweep_ts,
            "refresh_sec":       self._refresh_sec,
            "lookback_bars":     self._lookback,
            "results":           {k: v.as_dict() for k, v in self._results.items()},
        }

    # ---- Internals ------------------------------------------------------------

    async def _fetch_klines(self, symbol: str) -> Optional["np.ndarray"]:
        """Returns ndarray shape (N, 4) -> [open, high, low, close] or None."""
        if self._session is None or self._session.closed:
            return None
        # Round-robin host failover (4 FAPI mirrors).
        for offset in range(len(_BINANCE_FAPI_HOSTS)):
            host = _BINANCE_FAPI_HOSTS[(self._host_idx + offset) % len(_BINANCE_FAPI_HOSTS)]
            url = f"{host}/fapi/v1/klines"
            params = {"symbol": symbol, "interval": self._interval, "limit": str(self._lookback)}
            try:
                async with self._session.get(url, params=params) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    if not isinstance(data, list) or len(data) < 80:
                        return None
                    # Binance kline: [openTime, open, high, low, close, volume, ...]
                    # v9.9.2: capture volume (k[5]) so Mirofish volume condition works.
                    arr = np.asarray(
                        [[float(k[1]), float(k[2]), float(k[3]), float(k[4]),
                          float(k[5]) if len(k) > 5 else 0.0] for k in data],
                        dtype=np.float64,
                    )
                    self._host_idx = (self._host_idx + offset) % len(_BINANCE_FAPI_HOSTS)
                    return arr
            except (asyncio.TimeoutError, aiohttp.ClientError):
                continue
            except Exception as e:    # pragma: no cover
                _LOG.debug("klines %s host=%s err=%s", symbol, host, e)
                continue
        return None

    async def _backtest_one(self, symbol: str) -> None:
        async with self._sem:
            arr = await self._fetch_klines(symbol)
            if arr is None:
                return
            try:
                # v9.9.2: pass volume column (col 4) when available so the
                # Mirofish volume-surge condition can fire in the proxy strategy.
                vols = arr[:, 4] if arr.shape[1] >= 5 else None
                metrics = _vectorized_backtest(
                    opens=arr[:, 0], highs=arr[:, 1], lows=arr[:, 2], closes=arr[:, 3],
                    volumes=vols,
                )
            except Exception as e:    # pragma: no cover — algorithm bug shouldn't kill loop
                _LOG.warning("backtest %s failed: %s", symbol, e)
                return
            self._results[symbol] = BacktestResult(
                symbol=symbol, ts=time.time(), **metrics
            )

    async def rest_loop(self) -> None:
        """Long-running task — refresh the entire universe every `refresh_sec`."""
        if self._session is None:
            await self.start()
        while True:
            t0 = time.time()
            try:
                await asyncio.gather(
                    *[self._backtest_one(s) for s in self._symbols],
                    return_exceptions=True,
                )
                self._sweep_count += 1
                self._last_full_sweep_ts = time.time()
                ok = sum(1 for r in self._results.values() if r.n_trades >= 10)
                # v9.9.2: updated thresholds to match recalibrated quality_bias()
                bad    = sum(1 for r in self._results.values()
                             if r.n_trades >= 10 and (r.win_rate < 0.28 or r.profit_factor < 0.75 or r.ev_r < -0.12))
                good   = sum(1 for r in self._results.values()
                             if r.n_trades >= 10 and r.win_rate >= 0.38 and r.profit_factor >= 1.05 and r.ev_r > 0.0)
                strong = sum(1 for r in self._results.values()
                             if r.n_trades >= 10 and r.win_rate >= 0.45 and r.profit_factor >= 1.25 and r.ev_r > 0.03)
                top3   = sorted(
                    [r for r in self._results.values() if r.n_trades >= 10],
                    key=lambda r: r.ev_r, reverse=True
                )[:3]
                top3_str = " ".join(
                    f"{r.symbol}(WR={r.win_rate:.0%} EV={r.ev_r:+.2f}R)" for r in top3
                ) or "n/a"
                # v18.11: PBO summary stats
                pbo_overfit = sum(1 for r in self._results.values()
                                  if r.n_trades >= 20 and getattr(r, "pbo_label", "CLEAN") == "OVERFIT")
                pbo_suspect = sum(1 for r in self._results.values()
                                  if r.n_trades >= 20 and getattr(r, "pbo_label", "CLEAN") == "SUSPECT")
                pbo_str = f"overfit={pbo_overfit} suspect={pbo_suspect}"
                _LOG.info(
                    "✅ DynBacktest sweep #%d done in %.1fs | "
                    "tracked=%d | usable=%d | strong=%d(+5) good=%d(+2) weak=%d(-3..8) | "
                    "PBO[%s] | top3_EV: %s",
                    self._sweep_count, time.time() - t0,
                    len(self._results), ok, strong, good, bad, pbo_str, top3_str,
                )
            except Exception as e:    # pragma: no cover
                _LOG.error("DynBacktest sweep failed: %s", e)
            try:
                await asyncio.sleep(self._refresh_sec)
            except asyncio.CancelledError:
                raise
