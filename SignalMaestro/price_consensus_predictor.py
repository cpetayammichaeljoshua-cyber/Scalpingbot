"""
Price Consensus Predictor — multi-model ensemble (v1)
=====================================================

Production-grade, dependency-free price-direction predictor that fuses
ALL the major price-prediction model TYPES into a single normalised
consensus tilt ∈ [-1, +1].  Designed to run in <5 ms per symbol so it
fits inside the 12-25 s parallel scan loop without adding measurable
latency, and to be consumed as feature 52 of the Unity Engine NN.

Model families covered (one representative each — institutional best-in-class):
  1. Trend-following / Momentum     → EMA(8) vs EMA(21) crossover
  2. Linear / Statistical regression → Least-squares slope (last 20 closes)
  3. Mean-reversion (statistical)   → Z-score of close vs SMA-20 / σ-20
  4. Breakout / Range               → Donchian-20 channel position
  5. Volume-weighted (VWAP)         → Close deviation from rolling VWAP
  6. Time-series smoothing          → Holt double-exponential next-bar forecast
  7. Volatility-normalised momentum → ATR-scaled rate of change (5-bar)

Each sub-predictor returns a score in [-1, +1] (tanh-bounded).  The final
consensus is the equal-weight average — explainable and free of
hyper-parameter overfitting.  Per-component breakdown is returned so the
console / logger can show which models are voting bullish vs bearish.

The module has zero external dependencies beyond Python stdlib + numpy
(already in the env).  No sklearn, no statsmodels — keeping it surgical.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

try:
    import numpy as np
    _HAS_NUMPY = True
except Exception:
    _HAS_NUMPY = False


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_tanh(x: float) -> float:
    """Bounded tanh that never overflows on extreme inputs."""
    if x >  20.0: return  1.0
    if x < -20.0: return -1.0
    return math.tanh(x)


def _ema(values: Sequence[float], period: int) -> Optional[float]:
    """Classic EMA — last value only.  Returns None if too few points."""
    if not values or len(values) < period:
        return None
    k = 2.0 / (period + 1)
    ema = float(values[0])
    for v in values[1:]:
        ema = float(v) * k + ema * (1.0 - k)
    return ema


def _to_float_list(seq) -> List[float]:
    """Coerce any iterable into a clean list of floats, dropping bad entries."""
    out: List[float] = []
    if not seq:
        return out
    for v in seq:
        try:
            f = float(v)
            if math.isfinite(f) and f > 0:
                out.append(f)
        except (TypeError, ValueError):
            continue
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Sub-predictors (each → [-1, +1])
# ─────────────────────────────────────────────────────────────────────────────

def ema_crossover_signal(closes: Sequence[float]) -> float:
    """EMA(8) − EMA(21) trend tilt.  Positive → bullish."""
    cs = _to_float_list(closes)
    if len(cs) < 21:
        return 0.0
    e8  = _ema(cs[-30:], 8)
    e21 = _ema(cs[-30:], 21)
    if e8 is None or e21 is None or e21 == 0.0:
        return 0.0
    diff_pct = (e8 - e21) / e21
    # 2% spread → tanh(1.0) ≈ 0.76
    return _safe_tanh(diff_pct * 50.0)


def linreg_slope_signal(closes: Sequence[float]) -> float:
    """Least-squares slope of last 20 closes, normalised by mean price."""
    cs = _to_float_list(closes)
    if len(cs) < 20:
        return 0.0
    if not _HAS_NUMPY:
        # Fallback: simple first/last differential
        return _safe_tanh(((cs[-1] - cs[-20]) / cs[-20]) * 50.0)
    y = np.asarray(cs[-20:], dtype=np.float64)
    x = np.arange(y.shape[0], dtype=np.float64)
    # slope per bar via closed-form OLS
    x_mean = x.mean(); y_mean = y.mean()
    denom  = float(((x - x_mean) ** 2).sum())
    if denom == 0.0 or y_mean == 0.0:
        return 0.0
    slope = float(((x - x_mean) * (y - y_mean)).sum() / denom)
    norm  = slope / y_mean   # bars⁻¹ in price-fraction
    # 0.1% per bar → tanh(1.0)
    return _safe_tanh(norm * 1000.0)


def zscore_meanrev_signal(closes: Sequence[float]) -> float:
    """Mean-reversion tilt: high z (price stretched up) → bearish."""
    cs = _to_float_list(closes)
    if len(cs) < 20:
        return 0.0
    if _HAS_NUMPY:
        arr  = np.asarray(cs[-20:], dtype=np.float64)
        mu   = float(arr.mean())
        sig  = float(arr.std(ddof=0))
    else:
        window = cs[-20:]
        mu  = sum(window) / len(window)
        var = sum((v - mu) ** 2 for v in window) / len(window)
        sig = math.sqrt(var)
    if sig <= 0.0:
        return 0.0
    z = (cs[-1] - mu) / sig
    # +2σ → tanh(1.0) → -0.76 (bearish reversion expected)
    return -_safe_tanh(z / 2.0)


def donchian_position_signal(highs: Sequence[float],
                             lows:  Sequence[float],
                             closes: Sequence[float]) -> float:
    """Position within the 20-bar Donchian channel ∈ [-1, +1]."""
    hs = _to_float_list(highs)
    ls = _to_float_list(lows)
    cs = _to_float_list(closes)
    if len(hs) < 20 or len(ls) < 20 or not cs:
        return 0.0
    hi = max(hs[-20:])
    lo = min(ls[-20:])
    rng = hi - lo
    if rng <= 0.0:
        return 0.0
    pos = (cs[-1] - lo) / rng       # [0, 1]
    return float(max(-1.0, min(1.0, (pos - 0.5) * 2.0)))


def vwap_dev_signal(highs:  Sequence[float],
                    lows:   Sequence[float],
                    closes: Sequence[float],
                    volumes: Sequence[float]) -> float:
    """Deviation of close from rolling VWAP (last 20 bars)."""
    hs = _to_float_list(highs)
    ls = _to_float_list(lows)
    cs = _to_float_list(closes)
    vs: List[float] = []
    if volumes:
        for v in volumes:
            try:
                f = float(v)
                if math.isfinite(f) and f >= 0.0:
                    vs.append(f)
            except (TypeError, ValueError):
                continue
    n = min(len(hs), len(ls), len(cs), len(vs))
    if n < 20:
        return 0.0
    hs = hs[-n:]; ls = ls[-n:]; cs = cs[-n:]; vs = vs[-n:]
    typical = [(hs[i] + ls[i] + cs[i]) / 3.0 for i in range(-20, 0)]
    vol     = vs[-20:]
    sum_v   = sum(vol)
    if sum_v <= 0.0:
        return 0.0
    vwap = sum(typical[i] * vol[i] for i in range(20)) / sum_v
    if vwap <= 0.0:
        return 0.0
    dev_pct = (cs[-1] - vwap) / vwap
    # +1% above VWAP → tanh(1.0) → +0.76 (trend-continuation bullish)
    return _safe_tanh(dev_pct * 100.0)


def holt_forecast_signal(closes: Sequence[float],
                         alpha: float = 0.3,
                         beta:  float = 0.10) -> float:
    """Holt double-exponential smoothing one-bar-ahead forecast tilt."""
    cs = _to_float_list(closes)
    if len(cs) < 6:
        return 0.0
    level = cs[0]
    trend = 0.0
    for v in cs[1:]:
        prev_level = level
        level      = alpha * v + (1.0 - alpha) * (level + trend)
        trend      = beta  * (level - prev_level) + (1.0 - beta) * trend
    forecast = level + trend
    last = cs[-1]
    if last <= 0.0:
        return 0.0
    pct = (forecast - last) / last
    # +1% predicted move → tanh(1.0)
    return _safe_tanh(pct * 100.0)


def momentum_atr_signal(closes: Sequence[float],
                        atr: float,
                        lookback: int = 5) -> float:
    """5-bar rate-of-change normalised by ATR (vol-aware momentum)."""
    cs = _to_float_list(closes)
    if len(cs) < lookback + 1 or atr is None or atr <= 0.0:
        return 0.0
    last = cs[-1]
    if last <= 0.0:
        return 0.0
    roc      = (cs[-1] - cs[-(lookback + 1)]) / cs[-(lookback + 1)]
    atr_pct  = atr / last
    denom    = max(atr_pct * lookback, 1e-9)
    return _safe_tanh(roc / denom)


# ─────────────────────────────────────────────────────────────────────────────
# Top-level consensus
# ─────────────────────────────────────────────────────────────────────────────

# Component weights — equal for v1 to avoid overfitting; production can
# tune these from realised PnL.  Sum = 1.0 keeps consensus in [-1, +1].
_COMPONENT_WEIGHTS: Dict[str, float] = {
    "ema_cross":   1.0 / 7.0,
    "linreg":      1.0 / 7.0,
    "zscore_mr":   1.0 / 7.0,
    "donchian":    1.0 / 7.0,
    "vwap_dev":    1.0 / 7.0,
    "holt_fc":     1.0 / 7.0,
    "mom_atr":     1.0 / 7.0,
}


def compute_price_consensus(closes:  Optional[Sequence[float]] = None,
                            highs:   Optional[Sequence[float]] = None,
                            lows:    Optional[Sequence[float]] = None,
                            volumes: Optional[Sequence[float]] = None,
                            atr:     float = 0.0,
                            ) -> Tuple[float, Dict[str, float]]:
    """
    Run all sub-predictors, return (consensus_score, breakdown_dict).

    consensus_score ∈ [-1, +1]   negative = bearish, positive = bullish
    breakdown_dict  → {"ema_cross": ..., "linreg": ..., ...} for logging.

    All input lists may be None / empty / undersized — each sub-predictor
    fails-soft to 0.0, and the consensus naturally degrades to a partial
    average rather than crashing.
    """
    closes  = closes  or []
    highs   = highs   or []
    lows    = lows    or []
    volumes = volumes or []

    breakdown: Dict[str, float] = {
        "ema_cross": ema_crossover_signal(closes),
        "linreg":    linreg_slope_signal(closes),
        "zscore_mr": zscore_meanrev_signal(closes),
        "donchian":  donchian_position_signal(highs, lows, closes),
        "vwap_dev":  vwap_dev_signal(highs, lows, closes, volumes),
        "holt_fc":   holt_forecast_signal(closes),
        "mom_atr":   momentum_atr_signal(closes, float(atr or 0.0)),
    }
    consensus = sum(breakdown[k] * _COMPONENT_WEIGHTS[k] for k in _COMPONENT_WEIGHTS)
    # Clamp defensively (numerical drift can produce 1.0001-style values)
    if consensus >  1.0: consensus =  1.0
    if consensus < -1.0: consensus = -1.0
    return float(consensus), breakdown


def consensus_from_klines(klines: Sequence[Sequence],
                          atr: float = 0.0,
                          ) -> Tuple[float, Dict[str, float]]:
    """
    Convenience: extract OHLCV columns from raw Binance kline rows
    [open_time, open, high, low, close, volume, ...] and run consensus.
    """
    if not klines:
        return 0.0, {}
    try:
        highs   = [float(k[2]) for k in klines]
        lows    = [float(k[3]) for k in klines]
        closes  = [float(k[4]) for k in klines]
        volumes = [float(k[5]) for k in klines]
    except (IndexError, TypeError, ValueError):
        return 0.0, {}
    return compute_price_consensus(closes=closes, highs=highs,
                                   lows=lows, volumes=volumes, atr=atr)


# ───────────────────────────────────────────────────────────────────────────
# v6 — Hurst Exponent Regime Detector  (Rescaled-Range / R-S analysis)
# ───────────────────────────────────────────────────────────────────────────
# H ∈ [0, 1] estimated from log-return sub-windows is the canonical
# institutional regime classifier (Mandelbrot 1972, Peters 1991):
#
#     H > 0.55  →  persistent / TRENDING        (momentum & breakout favored)
#     H ≈ 0.50  →  random walk                  (no edge — reduce size)
#     H < 0.45  →  anti-persistent / MEAN-REVERTING  (fade strategies favored)
#
# Method: for each lag n ∈ {4, 8, 12, 16}:
#   1. split log-return series into ⌊N/n⌋ contiguous chunks
#   2. per chunk: cum_dev = Σ (x − mean(x));  R = max(cum_dev) − min(cum_dev)
#                 S       = σ(x);             rs = R / S
#   3. average rs across chunks
# Hurst H = OLS slope of  log(mean_rs)  vs  log(n).
#
# We then map to a [-1, +1] signal:  hurst_signal = clip(2·(H − 0.5), −1, +1)
# so positive = trending, negative = reverting, zero = random walk.
# ───────────────────────────────────────────────────────────────────────────

def hurst_exponent(closes: Sequence[float]) -> float:
    """
    Estimate Hurst exponent via Rescaled-Range (R/S) analysis on log returns.
    Returns H ∈ [0.0, 1.0]; on failure / insufficient data returns 0.5
    (random-walk neutral so the downstream signal collapses to 0).
    """
    if not closes or len(closes) < 20:
        return 0.5
    try:
        arr = np.asarray(closes, dtype=np.float64)
    except (TypeError, ValueError):
        return 0.5
    arr = np.where(arr > 1e-12, arr, 1e-12)
    rets = np.diff(np.log(arr))
    n_total = rets.size
    if n_total < 16:
        return 0.5

    # Choose lags that give ≥ 3 chunks each — guarantees stable R/S
    lags: List[int] = []
    for lag in (4, 8, 12, 16, 24, 32):
        if n_total // lag >= 3:
            lags.append(lag)
    if len(lags) < 2:
        return 0.5

    rs_values: List[Tuple[int, float]] = []
    for lag in lags:
        num_chunks = n_total // lag
        chunk_rs: List[float] = []
        for i in range(num_chunks):
            seg = rets[i * lag:(i + 1) * lag]
            if seg.size < 2:
                continue
            mean = float(seg.mean())
            cum_dev = np.cumsum(seg - mean)
            R = float(cum_dev.max() - cum_dev.min())
            S = float(seg.std(ddof=0))
            if S > 1e-12 and R > 0.0:
                chunk_rs.append(R / S)
        if chunk_rs:
            rs_values.append((lag, float(np.mean(chunk_rs))))

    if len(rs_values) < 2:
        return 0.5

    # OLS slope of log(R/S) vs log(lag) — closed-form least squares
    log_lags = np.log(np.array([x[0] for x in rs_values], dtype=np.float64))
    log_rs   = np.log(np.array([x[1] for x in rs_values], dtype=np.float64))
    n_pts    = log_lags.size
    sum_x    = float(log_lags.sum())
    sum_y    = float(log_rs.sum())
    sum_xy   = float((log_lags * log_rs).sum())
    sum_xx   = float((log_lags ** 2).sum())
    denom    = n_pts * sum_xx - sum_x * sum_x
    if abs(denom) < 1e-12:
        return 0.5
    slope = (n_pts * sum_xy - sum_x * sum_y) / denom
    H = float(slope)
    # Constrain to theoretical range [0, 1]; small-sample bias can briefly
    # push H above 1 or below 0 — clamp without altering the interpretation.
    if H < 0.0: H = 0.0
    if H > 1.0: H = 1.0
    return H


def hurst_regime_signal(closes: Sequence[float]) -> Tuple[float, float]:
    """
    Compute Hurst-derived regime signal in [-1, +1] alongside raw H ∈ [0, 1].

    Returns (signal, H) where:
        signal = clip(2·(H − 0.5), −1, +1)
        signal > 0  → trending  (favor momentum / breakout)
        signal < 0  → reverting (favor mean-reversion / fade)
        signal ≈ 0  → random walk (no regime edge)
    """
    H = hurst_exponent(closes)
    sig = 2.0 * (H - 0.5)
    if sig >  1.0: sig =  1.0
    if sig < -1.0: sig = -1.0
    return float(sig), H


def hurst_from_klines(klines: Sequence[Sequence]) -> Tuple[float, float]:
    """
    Convenience: extract close column from raw Binance kline rows
    [open_time, open, high, low, close, volume, ...] and compute Hurst regime.
    Returns (signal, H).
    """
    if not klines:
        return 0.0, 0.5
    try:
        closes = [float(k[4]) for k in klines]
    except (IndexError, TypeError, ValueError):
        return 0.0, 0.5
    return hurst_regime_signal(closes)


# ───────────────────────────────────────────────────────────────────────────
# v7 — EWMA Conditional Volatility Forecast  (RiskMetrics 1994, λ = 0.94)
# ───────────────────────────────────────────────────────────────────────────
# σ²_t = λ · σ²_{t-1} + (1 − λ) · r²_{t-1}
#
# The canonical institutional volatility model used by every major desk for
# VaR, vol-targeting position sizing, and adaptive stop placement.  λ = 0.94
# is the RiskMetrics standard (≈ 75-bar half-life) — it weights recent shocks
# heavily while still smoothing across the lookback.  For 15-min futures bars
# this gives ~19h of effective memory, which captures session-level vol
# regimes without contaminating across multi-day shifts.
#
# We expose two outputs:
#   1. ewma_vol  — raw √σ²_t (per-bar log-return std-dev forecast)
#   2. signal    — tanh(σ_ewma / σ_realized − 1)  ∈ [-1, +1]
#                  > 0 → VOL EXPANSION  (forecast > realized: caution, widen SL)
#                  < 0 → VOL CONTRACTION (forecast < realized: compression, breakout setup)
# ───────────────────────────────────────────────────────────────────────────

def ewma_volatility(closes: Sequence[float], lam: float = 0.94) -> float:
    """
    EWMA conditional volatility forecast on log returns.
    σ²_t = λ · σ²_{t-1} + (1 − λ) · r²_{t-1}

    Returns √σ²_t (per-bar std-dev) ∈ [0, ∞).  Returns 0.0 on insufficient data.
    Warm-started with 5-bar realized variance to avoid first-shock bias.
    """
    if not closes or len(closes) < 6:
        return 0.0
    try:
        arr = np.asarray(closes, dtype=np.float64)
    except (TypeError, ValueError):
        return 0.0
    arr = np.where(arr > 1e-12, arr, 1e-12)
    rets = np.diff(np.log(arr))
    n = rets.size
    if n < 5:
        return 0.0
    # Warm start: 5-bar realized variance smooths the recursion's first values
    var = float((rets[:5] ** 2).mean())
    for r in rets[5:]:
        var = lam * var + (1.0 - lam) * float(r) ** 2
    if var < 0.0 or not math.isfinite(var):
        return 0.0
    return math.sqrt(var)


def ewma_vol_signal(closes: Sequence[float],
                    lam: float = 0.94,
                    lookback: int = 20,
                    ) -> Tuple[float, float]:
    """
    Vol-regime signal in [-1, +1] derived from realized vs EWMA forecast:
        signal = tanh(realized_vol / ewma_vol − 1)

    Interpretation (sign follows recent vol direction relative to smoothed
    forecast — institutional convention used by RiskMetrics, MSCI Barra):
      ratio  ≈ 1.0 → balanced regime             (signal ≈ 0)
      ratio  > 1.0 → vol EXPANDING               (signal > 0, widen SL)
                     realised vol > smoothed forecast: actual vol rising
                     faster than EWMA can absorb — regime destabilising.
      ratio  < 1.0 → vol CONTRACTING             (signal < 0, compression)
                     realised vol < smoothed forecast: vol cooling off,
                     classic pre-breakout compression / squeeze setup.

    Returns (signal, ewma_vol) — second value useful for vol-targeted sizing.
    Returns (0.0, 0.0) on insufficient data so the slot is benign.
    """
    if not closes or len(closes) < lookback + 6:
        return 0.0, 0.0
    try:
        arr = np.asarray(closes, dtype=np.float64)
    except (TypeError, ValueError):
        return 0.0, 0.0
    arr = np.where(arr > 1e-12, arr, 1e-12)
    rets = np.diff(np.log(arr))
    if rets.size < lookback + 5:
        return 0.0, 0.0

    # EWMA forecast (warm-started with 5-bar realised variance)
    var = float((rets[:5] ** 2).mean())
    for r in rets[5:]:
        var = lam * var + (1.0 - lam) * float(r) ** 2
    if var < 0.0 or not math.isfinite(var):
        return 0.0, 0.0
    ewma_v = math.sqrt(var)
    if ewma_v < 1e-9:
        return 0.0, ewma_v

    # Realized baseline over lookback window (last N returns)
    realized = float(np.std(rets[-lookback:], ddof=0))

    # Sign convention: positive ⇒ vol EXPANDING (recent realised > smoothed)
    # so the v7.1 overlay's "sig > 0.10 → expansion penalty" reads naturally.
    ratio = realized / ewma_v
    sig = math.tanh(ratio - 1.0)
    if sig >  1.0: sig =  1.0
    if sig < -1.0: sig = -1.0
    return float(sig), ewma_v


def ewma_vol_from_klines(klines: Sequence[Sequence]) -> Tuple[float, float]:
    """
    Convenience: extract close column from raw Binance kline rows
    [open_time, open, high, low, close, volume, ...] and compute EWMA vol regime.
    Returns (signal, ewma_vol).
    """
    if not klines:
        return 0.0, 0.0
    try:
        closes = [float(k[4]) for k in klines]
    except (IndexError, TypeError, ValueError):
        return 0.0, 0.0
    return ewma_vol_signal(closes)


# ─────────────────────────────────────────────────────────────────────────────
# v8: Realized Skewness — third-moment companion to Hurst (1st) and EWMA (2nd)
# ─────────────────────────────────────────────────────────────────────────────
# Crypto futures exhibits the most pronounced asymmetric skew of any asset
# class (Bakshi-Kapadia-Madan 2003, Neuberger 2012, Kozhan-Neuberger-Schneider
# 2013).  Realized skewness predicts directional risk premia:
#
#   RS << 0 → CRASH-RISK regime    (long tails on the downside)
#                                   → LONG win-rate degrades, SHORT favoured
#   RS ≈  0 → symmetric regime     (no directional skew premium)
#   RS >> 0 → SQUEEZE-RISK regime  (long tails on the upside, short-squeeze)
#                                   → SHORT win-rate degrades, LONG favoured
#
# We use the model-free Neuberger 2012 estimator computed from log-returns:
#     RS_n = √n · Σrᵢ³ / (Σrᵢ²)^1.5
# which is unitless, scale-invariant, and bounded under reasonable distros.
# Output is squashed into [-1, +1] by tanh(RS / k) with k = 2.0 so values
# beyond ±2 saturate the slot — matches Hurst/EWMA convention exactly.
# ─────────────────────────────────────────────────────────────────────────────
def realized_skewness(closes: Sequence[float],
                      lookback: int = 30,
                      ) -> float:
    """
    Model-free Neuberger 2012 realized skewness from a close window.
    Returns 0.0 on insufficient data so the slot is benign.
    """
    if not closes or len(closes) < lookback + 2:
        return 0.0
    try:
        arr = np.asarray(closes[-(lookback + 1):], dtype=np.float64)
    except (TypeError, ValueError):
        return 0.0
    arr = np.where(arr > 1e-12, arr, 1e-12)
    rets = np.diff(np.log(arr))
    if rets.size < 5:
        return 0.0
    # Mean-centre to isolate the third central moment (otherwise drift biases RS)
    rets = rets - rets.mean()
    m2 = float(np.sum(rets ** 2))
    if m2 < 1e-18:
        return 0.0
    m3 = float(np.sum(rets ** 3))
    n  = float(rets.size)
    rs = math.sqrt(n) * m3 / (m2 ** 1.5)
    if not math.isfinite(rs):
        return 0.0
    return rs


def realized_skew_signal(closes: Sequence[float],
                         lookback: int = 30,
                         scale: float = 2.0,
                         ) -> Tuple[float, float]:
    """
    Realized-skewness regime signal in [-1, +1]:
        signal = tanh(RS / scale)

    Interpretation (sign mirrors return-distribution asymmetry):
      signal > +0.10 → SQUEEZE-RISK regime (upside fat tails — favour LONG)
      signal ≈   0.0 → symmetric returns   (no directional skew premium)
      signal < -0.10 → CRASH-RISK regime   (downside fat tails — favour SHORT)

    Returns (signal, raw_RS) — raw value useful for thresholding/diagnostics.
    Returns (0.0, 0.0) on insufficient data so the slot is benign.
    """
    rs = realized_skewness(closes, lookback=lookback)
    if rs == 0.0:
        return 0.0, 0.0
    sig = math.tanh(rs / max(scale, 1e-6))
    if sig >  1.0: sig =  1.0
    if sig < -1.0: sig = -1.0
    return float(sig), float(rs)


def realized_skew_from_klines(klines: Sequence[Sequence]) -> Tuple[float, float]:
    """
    Convenience: extract close column from raw Binance kline rows
    [open_time, open, high, low, close, volume, ...] and compute realized skew regime.
    Returns (signal, raw_RS).
    """
    if not klines:
        return 0.0, 0.0
    try:
        closes = [float(k[4]) for k in klines]
    except (IndexError, TypeError, ValueError):
        return 0.0, 0.0
    return realized_skew_signal(closes)
