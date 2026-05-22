"""
SignalMaestro — Exchange Executor  v11.4
═══════════════════════════════════════════════════════════════════════════════
CCXT-based async execution engine + institutional-grade quant mathematics.

Capabilities:
  • Multi-exchange support via ccxt.async_support (Binance USDM primary)
  • Market / Limit order placement with automatic SL + TP bracket
  • DCA (Dollar-Cost-Average) entry with configurable layers
  • Position queries: open positions, unrealised PnL, liquidation price
  • Balance queries: USDT equity, available margin, total equity
  • Take-profit / Stop-loss management (set / modify / cancel)
  • Trailing stop activation (after TP1 hit)
  • Leverage & margin-mode configuration per symbol
  • Position-size calculator from risk % or fixed USDT stake
  • Graceful degradation: never raises — all methods return safe defaults
  • Async-safe: one ccxt exchange instance per user×exchange pair, pooled

QuantMath module (v11.4) — integrated institutional quant mathematics:
  • Black-Scholes pricing + full Greeks (Δ, Γ, Θ, ν, ρ) for perpetual hedging
  • Factor IC / IR analysis — real-time signal validation via Spearman rank corr
  • Portfolio Optimization — Mean-Variance (MVO), Risk Parity, Black-Litterman
  • Kelly Criterion sizing — maximises geometric growth / Sharpe Ratio
  • Dynamic slippage model — spread + vol + market-impact cost estimation
  • Adaptive ATR stop-loss — volatility-normalised SL placement

Supported exchanges:
  binanceusdm / bybit / okx / bingx / bitget / kucoin / gate / mexc

Reference: CCXT documentation — https://docs.ccxt.com
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False
    _log_np = logging.getLogger("UnityEngine.ExchangeExecutor")
    _log_np.warning("numpy not installed — QuantMath math ops degraded to pure-Python fallbacks")

    class _FakeNp:  # noqa: D101
        inf    = float("inf")
        pi     = 3.141592653589793
        e      = 2.718281828459045
        float64 = float

        def array(self, x, *a, **kw):  return list(x) if hasattr(x, "__iter__") else [x]
        def cov(self, *a, **kw):       return [[1.0]]
        def sqrt(self, x):             return x ** 0.5
        def log(self, x):              return __import__("math").log(max(x, 1e-300))
        def exp(self, x):              return __import__("math").exp(min(x, 709.0))
        def dot(self, a, b):           return sum(x * y for x, y in zip(a, b))
        def diag(self, a):             return [[v if i == j else 0 for j in range(len(a))] for i, v in enumerate(a)]
        def linalg(self):              return self
        def solve(self, a, b):         return b  # degrade gracefully
        def norm(self, a, *x, **kw):   return sum(v ** 2 for v in (a if hasattr(a, "__iter__") else [a])) ** 0.5
        def maximum(self, a, b):       return max(a, b)
        def minimum(self, a, b):       return min(a, b)
        def clip(self, v, lo, hi):     return max(lo, min(hi, v))
        def zeros(self, n, *a, **kw):  return [0.0] * (n if isinstance(n, int) else n[0])
        def ones(self, n, *a, **kw):   return [1.0] * (n if isinstance(n, int) else n[0])
        def sum(self, a, *x, **kw):    return sum(a) if hasattr(a, "__iter__") else a
        def mean(self, a, *x, **kw):   return (sum(a) / len(a)) if a else 0.0

    np = _FakeNp()  # type: ignore[assignment]

_log = logging.getLogger("UnityEngine.ExchangeExecutor")

try:
    import ccxt.async_support as ccxt_async
    _HAS_CCXT = True
except ImportError:
    _HAS_CCXT = False
    _log.warning("ccxt not installed — ExchangeExecutor disabled")

try:
    from scipy.optimize import minimize
    from scipy.stats import rankdata, spearmanr
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False
    _log.warning("scipy not installed — QuantMath optimizers degraded")

# ── Constants ────────────────────────────────────────────────────────────────
_SUPPORTED_EXCHANGES = (
    "binance", "bybit", "okx", "bingx", "bitget", "kucoin", "gate", "mexc"
)
_CCXT_ID_MAP: Dict[str, str] = {
    "binance": "binanceusdm",
    "bybit":   "bybit",
    "okx":     "okx",
    "bingx":   "bingx",
    "bitget":  "bitget",
    "kucoin":  "kucoinfutures",
    "gate":    "gateio",
    "mexc":    "mexc",
}
_DEFAULT_TIMEOUT_MS = 15_000
_ORDER_BOOK_DEPTH   = 5
_MAX_RETRY_ATTEMPTS = 2
_RETRY_DELAY_SEC    = 1.0

# Kelly Criterion caps — never risk more than 25% of capital on a single trade
_KELLY_MAX_FRACTION = 0.25
# Minimum acceptable annualised Sharpe to allow full Kelly
_SHARPE_FLOOR = -1.0
_SHARPE_TARGET =  0.5


# ══════════════════════════════════════════════════════════════════════════════
#  QuantMath — Institutional Quant Mathematics Module
# ══════════════════════════════════════════════════════════════════════════════

class QuantMath:
    """
    Stateless collection of institutional-grade mathematical methods used
    throughout the Unity Engine for signal validation, position sizing,
    portfolio optimisation, and perpetual hedging.

    All methods are static / class-level — no instantiation required.
    All methods degrade gracefully: return None / 0.0 / {} on any error.

    Black-Scholes:
        Adapted for crypto perpetual futures: use mark price as S, synthetic
        strike K = entry ± expected move, T = hours-to-signal-expiry / 8760,
        r ≈ 0 (or funding rate annualised), σ = realised vol.

    MVO / Risk Parity / Black-Litterman:
        Input is a matrix of recent log-returns (T × N: T periods, N assets/
        exchanges). Output is a weight vector summing to 1.0.
        Used to distribute available margin across exchanges or signal sources.

    Kelly Criterion:
        Fractional Kelly sizing (half-Kelly by default) that maximises the
        geometric growth rate.  Capped at _KELLY_MAX_FRACTION for risk control.
        Scaled by Sharpe ratio when realised SR < target.

    Factor IC / IR:
        Information Coefficient (IC): Spearman rank correlation between a
        factor signal and forward returns.  IC > 0.05 is considered useful.
        Information Ratio (IR): IC / σ(IC) across a rolling window.
        IR > 0.5 indicates a statistically reliable factor.
    """

    # ── Black-Scholes Internals ────────────────────────────────────────────────

    @staticmethod
    def _norm_cdf(x: float) -> float:
        """Standard normal cumulative distribution via erf."""
        try:
            return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
        except Exception:
            return 0.5

    @staticmethod
    def _norm_pdf(x: float) -> float:
        """Standard normal probability density."""
        try:
            return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)
        except Exception:
            return 0.0

    @classmethod
    def bs_d1_d2(
        cls,
        S: float,      # current mark price
        K: float,      # synthetic strike (entry price)
        T: float,      # time to expiry in years (e.g. 4h = 4/8760)
        r: float,      # risk-free / funding rate (annualised)
        sigma: float,  # annualised volatility
    ) -> Tuple[float, float]:
        """Compute d1 and d2 for Black-Scholes."""
        try:
            if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
                return 0.0, 0.0
            sqrt_T = math.sqrt(T)
            d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
            d2 = d1 - sigma * sqrt_T
            return d1, d2
        except Exception:
            return 0.0, 0.0

    @classmethod
    def bs_price(
        cls,
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        option_type: str = "call",
    ) -> float:
        """
        Theoretical Black-Scholes price for a European call or put.
        Applied to perpetuals: use as a delta-neutral hedge reference price.

        Returns fair value in the same units as S (e.g. USDT).
        """
        try:
            d1, d2 = cls.bs_d1_d2(S, K, T, r, sigma)
            disc = math.exp(-r * T) if T > 0 else 1.0
            if option_type.lower() == "call":
                price = S * cls._norm_cdf(d1) - K * disc * cls._norm_cdf(d2)
            else:
                price = K * disc * cls._norm_cdf(-d2) - S * cls._norm_cdf(-d1)
            return max(0.0, round(price, 6))
        except Exception:
            return 0.0

    @classmethod
    def bs_greeks(
        cls,
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        option_type: str = "call",
    ) -> Dict[str, float]:
        """
        Full Black-Scholes Greeks for dynamic perpetual hedging.

        Returns dict with:
          delta  — price sensitivity to underlying (Δ)
          gamma  — delta sensitivity to underlying (Γ)
          theta  — time decay per day          (Θ)
          vega   — sensitivity to 1% vol move  (ν / 100)
          rho    — sensitivity to 1% rate move (ρ / 100)
          price  — theoretical BS price
          iv_proxy — annualised implied vol (same as input sigma for reference)

        Interpretation for perpetuals:
          delta → hedge ratio: short delta contracts for each long position
          gamma → convexity: how fast hedge must be rebalanced
          theta → cost of carry per day in USDT
          vega  → PnL impact of a 1pp vol expansion / compression
        """
        try:
            if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
                return {"delta": 0.0, "gamma": 0.0, "theta": 0.0,
                        "vega": 0.0, "rho": 0.0, "price": 0.0, "iv_proxy": sigma}
            d1, d2 = cls.bs_d1_d2(S, K, T, r, sigma)
            sqrt_T = math.sqrt(T)
            disc   = math.exp(-r * T)
            pdf_d1 = cls._norm_pdf(d1)
            is_call = option_type.lower() == "call"

            delta = cls._norm_cdf(d1) if is_call else cls._norm_cdf(d1) - 1.0
            gamma = pdf_d1 / (S * sigma * sqrt_T)
            theta_raw = (
                -(S * pdf_d1 * sigma) / (2.0 * sqrt_T)
                - (r * K * disc * (cls._norm_cdf(d2) if is_call else cls._norm_cdf(-d2)))
            )
            theta = theta_raw / 365.0   # per-calendar-day theta
            vega  = S * pdf_d1 * sqrt_T / 100.0   # per 1% vol move
            rho   = (
                K * T * disc * cls._norm_cdf(d2) / 100.0 if is_call
                else -K * T * disc * cls._norm_cdf(-d2) / 100.0
            )
            price = cls.bs_price(S, K, T, r, sigma, option_type)
            return {
                "delta":    round(delta,  6),
                "gamma":    round(gamma,  8),
                "theta":    round(theta,  6),
                "vega":     round(vega,   6),
                "rho":      round(rho,    6),
                "price":    round(price,  6),
                "iv_proxy": round(sigma,  4),
            }
        except Exception as e:
            _log.debug(f"bs_greeks error: {e}")
            return {"delta": 0.0, "gamma": 0.0, "theta": 0.0,
                    "vega": 0.0, "rho": 0.0, "price": 0.0, "iv_proxy": 0.0}

    # ── Factor IC / IR Analysis ────────────────────────────────────────────────

    @staticmethod
    def information_coefficient(
        factor_values:   Sequence[float],
        forward_returns: Sequence[float],
    ) -> float:
        """
        Spearman rank-correlation IC between a factor score vector and
        realised forward returns over the same period.

        IC > 0.05  → factor has economically meaningful signal
        IC > 0.10  → strong signal (institutional threshold)
        IC < 0.00  → factor is inversely predictive (consider reversing)

        Returns IC ∈ [-1, +1], or 0.0 on error / insufficient data.
        """
        try:
            fv = np.asarray(factor_values,   dtype=np.float64)
            fr = np.asarray(forward_returns, dtype=np.float64)
            mask = np.isfinite(fv) & np.isfinite(fr)
            if mask.sum() < 5:
                return 0.0
            if _HAS_SCIPY:
                corr, _ = spearmanr(fv[mask], fr[mask])
                return float(corr) if math.isfinite(corr) else 0.0
            # Fallback: manual Spearman via rank
            fv_r = rankdata(fv[mask]).astype(np.float64)
            fr_r = rankdata(fr[mask]).astype(np.float64)
            n = len(fv_r)
            cov  = np.mean((fv_r - fv_r.mean()) * (fr_r - fr_r.mean()))
            denom = fv_r.std(ddof=1) * fr_r.std(ddof=1)
            return float(cov / denom) if denom > 1e-12 else 0.0
        except Exception as e:
            _log.debug(f"IC error: {e}")
            return 0.0

    @staticmethod
    def information_ratio(ic_series: Sequence[float]) -> float:
        """
        Information Ratio = mean(IC) / std(IC).

        IR > 0.50 → reliable factor across the sample window.
        IR > 1.00 → exceptional predictive consistency.

        Returns IR, or 0.0 on error / insufficient data.
        """
        try:
            arr = np.asarray(ic_series, dtype=np.float64)
            arr = arr[np.isfinite(arr)]
            if len(arr) < 3:
                return 0.0
            std = float(np.std(arr, ddof=1))
            if std < 1e-12:
                return 0.0
            return float(np.mean(arr) / std)
        except Exception:
            return 0.0

    @classmethod
    def factor_icir(
        cls,
        factor_matrix:  np.ndarray,   # shape (T, N) — T periods, N symbols
        returns_matrix: np.ndarray,   # shape (T, N) — aligned forward returns
        lookback: int = 20,
    ) -> Dict[str, Any]:
        """
        Compute rolling IC and IR for each factor period in the window.

        Returns:
          ic_series  — list of per-period IC values
          ir         — Information Ratio over the window
          mean_ic    — mean IC
          std_ic     — IC standard deviation
          t_stat     — t-statistic: mean_ic / (std_ic / sqrt(N))
          verdict    — "STRONG" / "USEFUL" / "WEAK" / "INVERSE"
        """
        try:
            T, N = factor_matrix.shape
            lookback = min(lookback, T)
            ic_series = []
            for t in range(T - lookback, T):
                ic = cls.information_coefficient(
                    factor_matrix[t, :], returns_matrix[t, :]
                )
                ic_series.append(ic)
            ir       = cls.information_ratio(ic_series)
            mean_ic  = float(np.mean(ic_series)) if ic_series else 0.0
            std_ic   = float(np.std(ic_series, ddof=1)) if len(ic_series) > 1 else 0.0
            t_stat   = (mean_ic / (std_ic / math.sqrt(max(lookback, 1)))) if std_ic > 1e-12 else 0.0
            if mean_ic >= 0.10:
                verdict = "STRONG"
            elif mean_ic >= 0.05:
                verdict = "USEFUL"
            elif mean_ic >= -0.02:
                verdict = "WEAK"
            else:
                verdict = "INVERSE"
            return {
                "ic_series": ic_series,
                "ir":        round(ir,      4),
                "mean_ic":   round(mean_ic, 4),
                "std_ic":    round(std_ic,  4),
                "t_stat":    round(t_stat,  4),
                "verdict":   verdict,
            }
        except Exception as e:
            _log.debug(f"factor_icir error: {e}")
            return {"ic_series": [], "ir": 0.0, "mean_ic": 0.0, "std_ic": 0.0,
                    "t_stat": 0.0, "verdict": "WEAK"}

    # ── Mean-Variance Optimisation ────────────────────────────────────────────

    @staticmethod
    def mvo_weights(
        returns_matrix: np.ndarray,    # shape (T, N)
        risk_aversion:  float = 2.0,
        min_weight:     float = 0.0,
        max_weight:     float = 1.0,
    ) -> np.ndarray:
        """
        Markowitz Mean-Variance Optimisation (MVO).

        Maximises: w^T μ - (λ/2) w^T Σ w
        Subject to: Σw = 1, min_weight ≤ w_i ≤ max_weight

        Where:
          μ = mean return vector (annualised)
          Σ = covariance matrix (annualised)
          λ = risk_aversion parameter (higher = more conservative)

        Returns weight vector of length N summing to 1.0.
        Falls back to equal weights on any error or if scipy unavailable.
        """
        try:
            R = np.asarray(returns_matrix, dtype=np.float64)
            T, N = R.shape
            if T < 5 or N < 1:
                return np.ones(N) / N
            mu  = R.mean(axis=0) * 252       # annualise daily returns
            cov = np.cov(R, rowvar=False) * 252
            if N == 1:
                return np.array([1.0])
            if not _HAS_SCIPY:
                # Naive inverse-vol weighting as fallback
                vols = np.sqrt(np.diag(cov))
                vols = np.where(vols < 1e-12, 1e-12, vols)
                w    = 1.0 / vols
                return w / w.sum()
            def neg_utility(w: np.ndarray) -> float:
                port_ret = w @ mu
                port_var = w @ cov @ w
                return -(port_ret - 0.5 * risk_aversion * port_var)
            w0  = np.ones(N) / N
            constraints = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
            bounds = [(min_weight, max_weight)] * N
            result = minimize(
                neg_utility, w0,
                method="SLSQP",
                bounds=bounds,
                constraints=constraints,
                options={"maxiter": 500, "ftol": 1e-9},
            )
            if result.success:
                w = np.clip(result.x, min_weight, max_weight)
                w = w / w.sum()
                return w
            return np.ones(N) / N
        except Exception as e:
            _log.debug(f"mvo_weights error: {e}")
            N = returns_matrix.shape[1] if hasattr(returns_matrix, "shape") else 1
            return np.ones(N) / N

    @staticmethod
    def risk_parity_weights(
        returns_matrix: np.ndarray,
        target_vol:     float = 0.10,
    ) -> np.ndarray:
        """
        Risk Parity (Equal Risk Contribution) weights.

        Each asset contributes equally to total portfolio volatility.
        Particularly robust when mean estimates are noisy (as in crypto).

        Returns weight vector of length N summing to 1.0.
        """
        try:
            R   = np.asarray(returns_matrix, dtype=np.float64)
            T, N = R.shape
            if T < 5 or N < 1:
                return np.ones(N) / N
            cov = np.cov(R, rowvar=False) * 252
            if N == 1:
                return np.array([1.0])
            if not _HAS_SCIPY:
                vols = np.sqrt(np.diag(cov))
                vols = np.where(vols < 1e-12, 1e-12, vols)
                w    = 1.0 / vols
                return w / w.sum()
            def risk_parity_obj(w: np.ndarray) -> float:
                port_var = w @ cov @ w
                mrc      = cov @ w            # marginal risk contribution
                rc       = w * mrc            # risk contribution
                target   = port_var / N
                return float(np.sum((rc - target) ** 2))
            w0          = np.ones(N) / N
            constraints = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
            bounds      = [(0.01, 1.0)] * N
            result      = minimize(
                risk_parity_obj, w0,
                method="SLSQP",
                bounds=bounds,
                constraints=constraints,
                options={"maxiter": 500, "ftol": 1e-12},
            )
            if result.success:
                w = np.clip(result.x, 0.0, 1.0)
                return w / w.sum()
            return np.ones(N) / N
        except Exception as e:
            _log.debug(f"risk_parity_weights error: {e}")
            N = returns_matrix.shape[1] if hasattr(returns_matrix, "shape") else 1
            return np.ones(N) / N

    @staticmethod
    def black_litterman(
        market_weights:    np.ndarray,   # market-cap implied weights (N,)
        cov_matrix:        np.ndarray,   # annualised covariance (N, N)
        views:             np.ndarray,   # view return vector (K,) — K = number of views
        pick_matrix:       np.ndarray,   # P matrix: which assets are in each view (K, N)
        view_confidences:  np.ndarray,   # Ω diagonal — uncertainty of each view (K,)
        risk_aversion:     float = 2.5,
        tau:               float = 0.05,
    ) -> np.ndarray:
        """
        Black-Litterman portfolio allocation.

        Blends the market equilibrium expected returns (π = λ Σ w_mkt) with
        analyst/model views (P μ = q with uncertainty Ω) to produce a
        posterior expected return vector μ_BL used for MVO.

        View construction for Unity:
          • Each gate output (GEX bias, NN probability, IRONS score) can be
            expressed as a view on a set of symbols.
          • Views are blended into the equilibrium via Bayesian updating.

        Returns BL-implied weights (N,).
        """
        try:
            N = len(market_weights)
            if N < 1 or not _HAS_SCIPY:
                return market_weights
            w_mkt = np.asarray(market_weights,   dtype=np.float64)
            Sigma  = np.asarray(cov_matrix,       dtype=np.float64)
            q      = np.asarray(views,             dtype=np.float64)
            P      = np.asarray(pick_matrix,       dtype=np.float64)
            omega  = np.diag(np.asarray(view_confidences, dtype=np.float64))

            # Market equilibrium implied returns
            pi = risk_aversion * Sigma @ w_mkt

            # BL posterior expected returns
            tau_sigma = tau * Sigma
            PT         = P.T
            inner      = P @ tau_sigma @ PT + omega
            mu_bl = pi + tau_sigma @ PT @ np.linalg.solve(inner, q - P @ pi)

            # MVO with BL returns
            if not _HAS_SCIPY:
                vols = np.sqrt(np.diag(Sigma))
                vols = np.where(vols < 1e-12, 1e-12, vols)
                w    = 1.0 / vols
                return w / w.sum()

            def neg_util(w: np.ndarray) -> float:
                return -(w @ mu_bl - 0.5 * risk_aversion * w @ Sigma @ w)

            result = minimize(
                neg_util, w_mkt,
                method="SLSQP",
                bounds=[(0.0, 1.0)] * N,
                constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0}],
                options={"maxiter": 500},
            )
            if result.success:
                w = np.clip(result.x, 0.0, 1.0)
                return w / w.sum()
            return w_mkt
        except Exception as e:
            _log.debug(f"black_litterman error: {e}")
            return market_weights

    # ── Kelly Criterion + Sharpe Scaling ──────────────────────────────────────

    @staticmethod
    def kelly_fraction(
        win_rate:      float,
        avg_win_pct:   float,
        avg_loss_pct:  float,
        half_kelly:    bool  = True,
        sharpe:        float = 0.5,
    ) -> float:
        """
        Fractional Kelly Criterion — optimal bet fraction for geometric growth.

        Formula: f* = (p·b - q) / b
          where:  p = win_rate
                  q = 1 - p
                  b = avg_win / avg_loss (reward-to-risk ratio)

        Sharpe scaling: Kelly is linearly attenuated between SHARPE_FLOOR and
        SHARPE_TARGET — capital is committed only when risk-adjusted returns
        are positive. Kelly → 0 at SR ≤ SHARPE_FLOOR.

        Returns fraction ∈ [0, _KELLY_MAX_FRACTION].
        """
        try:
            p = max(0.0, min(1.0, win_rate))
            q = 1.0 - p
            b = abs(avg_win_pct) / max(abs(avg_loss_pct), 0.001)
            if b < 1e-9 or p < 1e-9:
                return 0.0
            f_star = (p * b - q) / b
            if f_star <= 0:
                return 0.0
            f_kelly = f_star * (0.5 if half_kelly else 1.0)
            # Sharpe attenuation
            sharpe_scale = max(
                0.0,
                min(1.0, (sharpe - _SHARPE_FLOOR) / (_SHARPE_TARGET - _SHARPE_FLOOR)),
            )
            f_scaled = f_kelly * sharpe_scale
            return round(min(f_scaled, _KELLY_MAX_FRACTION), 4)
        except Exception:
            return 0.0

    @staticmethod
    def sharpe_ratio(
        returns:          Sequence[float],
        risk_free_rate:   float = 0.0,
        annualise_factor: float = 252.0,
    ) -> float:
        """
        Sharpe Ratio = (E[R] - Rf) / σ(R) × √(annualise_factor).

        Annualise factor:
          252 for daily returns, 365 for crypto daily, 8760 for hourly.

        Returns annualised Sharpe, or 0.0 on insufficient data.
        """
        try:
            arr = np.asarray(returns, dtype=np.float64)
            arr = arr[np.isfinite(arr)]
            if len(arr) < 2:
                return 0.0
            excess = arr - (risk_free_rate / annualise_factor)
            std    = float(np.std(excess, ddof=1))
            if std < 1e-12:
                return 0.0
            sr = float(np.mean(excess) / std * math.sqrt(annualise_factor))
            return round(sr, 4)
        except Exception:
            return 0.0

    # ── Dynamic Slippage ──────────────────────────────────────────────────────

    @staticmethod
    def dynamic_slippage(
        spread_bps:   float,    # quoted bid-ask spread in basis points
        volatility_bps: float,  # 1σ price volatility in bps (over signal horizon)
        size_usdt:    float,    # order notional in USDT
        adv_usdt:     float,    # average daily volume in USDT
        impact_coeff: float = 0.1,
    ) -> float:
        """
        Estimated total slippage cost in basis points (bps).

        Model: slippage = (spread/2) + vol_slippage + market_impact

        Market impact (Almgren-Chriss simplified):
          impact = κ × σ × √(size / ADV)
          where κ = impact_coeff (exchange-specific constant)

        Returns expected slippage in bps; 0.0 on error.
        """
        try:
            half_spread    = spread_bps / 2.0
            vol_slippage   = volatility_bps * 0.15   # 15% of 1σ as vol cost
            participation  = size_usdt / max(adv_usdt, 1.0)
            market_impact  = impact_coeff * volatility_bps * math.sqrt(participation)
            return round(max(0.0, half_spread + vol_slippage + market_impact), 2)
        except Exception:
            return 0.0

    # ── Adaptive ATR Stop-Loss ────────────────────────────────────────────────

    @staticmethod
    def adaptive_stop_loss(
        entry:       float,
        atr:         float,
        direction:   str,
        multiplier:  float = 2.0,
        min_sl_pct:  float = 0.005,    # minimum 0.5% from entry
        max_sl_pct:  float = 0.08,     # maximum 8% from entry
    ) -> float:
        """
        ATR-based adaptive stop-loss price.

        SL distance = max(min_sl_pct, min(max_sl_pct, atr × multiplier / entry))

        Returns stop price rounded to 4 decimal places.
        """
        try:
            if entry <= 0 or atr <= 0:
                return entry * (1.0 - min_sl_pct) if direction.upper() in ("BUY", "LONG") else entry * (1.0 + min_sl_pct)
            raw_distance = atr * multiplier
            distance_pct = raw_distance / entry
            distance_pct = max(min_sl_pct, min(max_sl_pct, distance_pct))
            if direction.upper() in ("BUY", "LONG"):
                return round(entry * (1.0 - distance_pct), 4)
            else:
                return round(entry * (1.0 + distance_pct), 4)
        except Exception:
            return entry


# ── Quantile Backtesting ──────────────────────────────────────────────────────

class QuantileBacktester:
    """
    Signal validation via quantile (decile) backtesting.

    Splits factor values into N quantile buckets and measures the forward
    return of each bucket.  A monotone relationship (Q1 < Q2 < ... < QN or
    Q1 > Q2 > ... > QN) confirms that the factor has directional predictive
    power (positive IC).

    Also computes the spread return (top - bottom quantile) which is the
    tradeable alpha of the factor.
    """

    def __init__(self, n_quantiles: int = 5):
        self.n_quantiles = n_quantiles

    def run(
        self,
        factor_values:   Sequence[float],
        forward_returns: Sequence[float],
    ) -> Dict[str, Any]:
        """
        Returns:
          quantile_returns — list of mean return per quantile bucket
          spread_return    — top_q - bottom_q return
          monotone         — True if relationship is monotonically increasing or decreasing
          ic               — IC of factor over this sample
        """
        try:
            fv = np.asarray(factor_values,   dtype=np.float64)
            fr = np.asarray(forward_returns, dtype=np.float64)
            mask = np.isfinite(fv) & np.isfinite(fr)
            if mask.sum() < self.n_quantiles * 2:
                return {"quantile_returns": [], "spread_return": 0.0,
                        "monotone": False, "ic": 0.0}
            fv_m = fv[mask]
            fr_m = fr[mask]
            # Assign quantile bins
            quantile_bounds = np.percentile(fv_m, np.linspace(0, 100, self.n_quantiles + 1))
            q_returns: List[float] = []
            for i in range(self.n_quantiles):
                lo = quantile_bounds[i]
                hi = quantile_bounds[i + 1]
                in_bin = (fv_m >= lo) & (fv_m <= hi)
                if in_bin.sum() > 0:
                    q_returns.append(float(fr_m[in_bin].mean()))
                else:
                    q_returns.append(0.0)
            spread  = q_returns[-1] - q_returns[0]
            diffs   = [q_returns[i + 1] - q_returns[i] for i in range(len(q_returns) - 1)]
            mono    = all(d >= 0 for d in diffs) or all(d <= 0 for d in diffs)
            ic      = QuantMath.information_coefficient(fv_m, fr_m)
            return {
                "quantile_returns": [round(r, 6) for r in q_returns],
                "spread_return":    round(spread, 6),
                "monotone":         mono,
                "ic":               round(ic, 4),
            }
        except Exception as e:
            _log.debug(f"quantile backtest error: {e}")
            return {"quantile_returns": [], "spread_return": 0.0,
                    "monotone": False, "ic": 0.0}


# ── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class OrderResult:
    success:    bool
    order_id:   str   = ""
    exchange:   str   = ""
    symbol:     str   = ""
    side:       str   = ""
    order_type: str   = ""
    price:      float = 0.0
    amount:     float = 0.0
    filled:     float = 0.0
    avg_price:  float = 0.0
    status:     str   = ""
    timestamp:  float = field(default_factory=time.time)
    error:      str   = ""
    raw:        Optional[Dict] = field(default=None, repr=False)


@dataclass
class Position:
    symbol:            str
    side:              str   = ""
    size:              float = 0.0
    entry_price:       float = 0.0
    mark_price:        float = 0.0
    unrealised_pnl:    float = 0.0
    percentage:        float = 0.0
    liquidation_price: float = 0.0
    leverage:          int   = 1
    margin_mode:       str   = "isolated"
    notional:          float = 0.0


@dataclass
class BalanceInfo:
    exchange:       str
    usdt_free:      float = 0.0
    usdt_used:      float = 0.0
    usdt_total:     float = 0.0
    unrealised_pnl: float = 0.0
    margin_ratio:   float = 0.0
    fetched_at:     float = field(default_factory=time.time)
    error:          str   = ""    # non-empty when fetch failed


@dataclass
class ExecutionPlan:
    """Computed execution plan before placing orders."""
    symbol:         str
    direction:      str
    entry_price:    float
    sl_price:       float
    tp1_price:      float
    tp2_price:      float
    tp3_price:      float
    position_size:  float
    notional_usdt:  float
    leverage:       int
    risk_usdt:      float
    rr_ratio:       float
    order_type:     str   = "market"
    dca_layers:     int   = 1
    dca_multiplier: float = 1.5
    tp_split:       Tuple[float, float, float] = (0.33, 0.33, 0.34)
    kelly_fraction: float = 0.0
    slippage_bps:   float = 0.0
    bs_delta:       float = 0.0    # hedge delta from Black-Scholes


# ── Exchange Pool ─────────────────────────────────────────────────────────────

class _ExchangePool:
    """Manages a pool of ccxt exchange instances keyed by (user_id, exchange)."""

    def __init__(self):
        self._pool: Dict[Tuple[int, str], Any] = {}
        self._lock = asyncio.Lock()

    async def get(
        self,
        user_id:    int,
        exchange:   str,
        api_key:    str,
        api_secret: str,
        passphrase: str  = "",
        testnet:    bool = False,
    ) -> Optional[Any]:
        if not _HAS_CCXT:
            return None
        key = (user_id, exchange.lower())
        async with self._lock:
            if key in self._pool:
                return self._pool[key]
            ex = self._create(exchange, api_key, api_secret, passphrase, testnet)
            if ex is not None:
                self._pool[key] = ex
            return ex

    def _create(
        self,
        exchange:   str,
        api_key:    str,
        api_secret: str,
        passphrase: str,
        testnet:    bool,
    ) -> Optional[Any]:
        ccxt_id  = _CCXT_ID_MAP.get(exchange.lower(), exchange.lower())
        ExClass  = getattr(ccxt_async, ccxt_id, None)
        if ExClass is None:
            _log.warning(f"CCXT exchange not found: {ccxt_id}")
            return None
        params: Dict[str, Any] = {
            "apiKey":          api_key,
            "secret":          api_secret,
            "timeout":         _DEFAULT_TIMEOUT_MS,
            "enableRateLimit": True,
        }
        if passphrase:
            params["password"] = passphrase
        if testnet:
            params["sandbox"] = True
        # Exchange-specific perpetual/futures options — required so CCXT routes
        # orders to the futures markets instead of defaulting to spot.
        # binanceusdm is already the dedicated USD-M futures class (no option needed).
        _fut_opts: Dict[str, Any] = {}
        if ccxt_id in ("bybit",):
            _fut_opts["defaultType"] = "swap"        # linear perpetuals on Bybit
        elif ccxt_id in ("okx",):
            _fut_opts["defaultType"] = "swap"        # USDT perpetual contracts
        elif ccxt_id in ("bingx",):
            _fut_opts["defaultType"]              = "swap"
            _fut_opts["fetchBalance"]             = {"type": "swap"}
            _fut_opts["createOrder"]              = {"type": "swap"}
        elif ccxt_id in ("bitget",):
            _fut_opts["defaultType"] = "swap"
        elif ccxt_id in ("gateio",):
            _fut_opts["defaultType"] = "futures"
        elif ccxt_id in ("mexc",):
            _fut_opts["defaultType"] = "swap"
        if _fut_opts:
            params["options"] = _fut_opts
        try:
            ex = ExClass(params)
            if testnet and hasattr(ex, "set_sandbox_mode"):
                ex.set_sandbox_mode(True)
            return ex
        except Exception as e:
            _log.warning(f"CCXT init error ({exchange}): {e}")
            return None

    async def close_all(self) -> None:
        async with self._lock:
            for ex in self._pool.values():
                try:
                    await ex.close()
                except Exception:
                    pass
            self._pool.clear()

    async def remove(self, user_id: int, exchange: str) -> None:
        key = (user_id, exchange.lower())
        async with self._lock:
            ex = self._pool.pop(key, None)
            if ex is not None:
                try:
                    await ex.close()
                except Exception:
                    pass


_pool = _ExchangePool()


# ── Position Size Calculator ──────────────────────────────────────────────────

def calc_position_size(
    balance_usdt: float,
    risk_pct:     float,
    entry_price:  float,
    sl_price:     float,
    leverage:     int,
    stake_fixed:  float = 0.0,
    kelly_frac:   float = 0.0,
    free_usdt:    float = 0.0,   # available margin — hard cap so we never exceed it
) -> Tuple[float, float]:
    """
    Compute position size in base currency and notional USDT.

    Priority:
      1. If kelly_frac > 0  → use Kelly-sized stake (balance × kelly_frac)
      2. If stake_fixed > 0 → use fixed USDT stake directly
      3. Otherwise          → risk_pct of balance / SL distance

    Hard cap: notional is always capped so the required margin (notional / leverage)
    never exceeds 90% of free_usdt.  This prevents "Insufficient margin" rejections
    on BingX / Binance when some margin is already in use by existing positions.

    Returns (base_size, notional_usdt).
    """
    try:
        # Maximum allowable notional given the free available margin
        _max_notional = (free_usdt * leverage * 0.90) if free_usdt > 0 else float("inf")

        if kelly_frac > 0:
            risk_usdt     = balance_usdt * kelly_frac
            sl_distance   = abs(entry_price - sl_price) / max(entry_price, 1e-9)
            sl_distance   = max(sl_distance, 0.001)
            notional_usdt = min((risk_usdt / sl_distance) * leverage,
                                balance_usdt * leverage, _max_notional)
            base_size     = notional_usdt / entry_price if entry_price else 0.0
            return round(base_size, 4), round(notional_usdt, 2)
        if stake_fixed > 0:
            notional_usdt = min(stake_fixed * leverage,
                                balance_usdt * leverage, _max_notional)
            base_size     = notional_usdt / entry_price if entry_price else 0.0
            return round(base_size, 4), round(notional_usdt, 2)
        # Risk-based sizing (default)
        risk_usdt     = balance_usdt * (risk_pct / 100.0)
        sl_distance   = abs(entry_price - sl_price) / max(entry_price, 1e-9)
        sl_distance   = max(sl_distance, 0.0001)
        notional_usdt = min((risk_usdt / sl_distance) * leverage,
                            balance_usdt * leverage, _max_notional)
        base_size     = notional_usdt / entry_price if entry_price else 0.0
        return round(base_size, 4), round(notional_usdt, 2)
    except Exception:
        return 0.0, 0.0


# ── ExchangeExecutor ──────────────────────────────────────────────────────────

class ExchangeExecutor:
    """
    High-level async CCXT execution engine.

    Usage:
        executor = ExchangeExecutor()
        result = await executor.market_order(
            user_id=123, exchange="binance",
            api_key="...", api_secret="...",
            symbol="BTC/USDT:USDT", side="buy", amount=0.001,
        )
    """

    def __init__(self):
        self._pool         = _pool
        self._balance_cache: Dict[Tuple[int, str], Tuple[BalanceInfo, float]] = {}
        self._cache_ttl    = 30.0
        self.quant         = QuantMath
        # Hedge-mode cache: keyed by exchange name; True = dual-position-side confirmed.
        # BingX is pre-seeded because it ALWAYS requires positionSide in hedge mode —
        # skipping the error round-trip eliminates the 109400 failure on the first order.
        self._hedge_mode_cache: Dict[str, bool] = {
            "bingx": True,
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _get_exchange(
        self,
        user_id:    int,
        exchange:   str,
        api_key:    str,
        api_secret: str,
        passphrase: str  = "",
        testnet:    bool = False,
    ) -> Optional[Any]:
        return await self._pool.get(
            user_id, exchange, api_key, api_secret, passphrase, testnet
        )

    @staticmethod
    def _normalise_symbol(symbol: str, exchange: str) -> str:
        """Convert BTCUSDT → BTC/USDT:USDT for CCXT futures."""
        if "/" in symbol:
            return symbol
        if symbol.endswith("USDT"):
            base = symbol[:-4]
            return f"{base}/USDT:USDT"
        return symbol

    @staticmethod
    def _order_to_result(raw: Dict, exchange: str) -> OrderResult:
        return OrderResult(
            success=True,
            order_id=str(raw.get("id", "")),
            exchange=exchange,
            symbol=str(raw.get("symbol", "")),
            side=str(raw.get("side", "")),
            order_type=str(raw.get("type", "")),
            price=float(raw.get("price") or 0),
            amount=float(raw.get("amount") or 0),
            filled=float(raw.get("filled") or 0),
            avg_price=float(raw.get("average") or raw.get("price") or 0),
            status=str(raw.get("status", "open")),
            timestamp=time.time(),
            raw=raw,
        )

    # ── Hedge-Mode Support (BingX 109400 / Binance -4061) ────────────────────

    _HEDGE_ERR_SIGNALS: Tuple[str, ...] = (
        "109400", "-4061", "PositionSide", "positionSide",
        "dualSidePosition", "position side", "dual side", "position_side",
    )

    @staticmethod
    def _pos_side(direction: str) -> str:
        """Return positionSide string for hedge-mode: 'LONG' or 'SHORT' (uppercase required by BingX/Binance)."""
        return "LONG" if direction.upper() in ("BUY", "LONG") else "SHORT"

    async def _place_order_with_hedge_retry(
        self,
        ex:         Any,
        sym:        str,
        order_type: str,          # "market" | "limit" | "STOP_MARKET" | "TAKE_PROFIT_MARKET"
        side:       str,          # "buy" | "sell"
        amount:     float,
        price:      Optional[float] = None,
        params:     Optional[Dict]  = None,
        direction:  str             = "",
        exchange:   str             = "",
    ) -> Dict:
        """
        Place a CCXT order with automatic hedge-mode (dual-position-side) retry.

        On first call, tries without positionSide.  If the exchange returns any
        hedge-mode error (BingX 109400 / Binance -4061 / "positionSide required"),
        injects positionSide and retries once.  Detection is cached per exchange
        so all subsequent orders on that exchange go directly to the hedge path
        without an extra round-trip.
        """
        params = dict(params or {})
        _exc   = (exchange or "").lower()
        _hedge = self._hedge_mode_cache.get(_exc, False)

        # If hedge-mode already confirmed for this exchange, inject positionSide now.
        if _hedge and direction and "positionSide" not in params:
            params["positionSide"] = self._pos_side(direction)

        # CRITICAL: In hedge mode (dual-position-side), "reduceOnly" is FORBIDDEN on
        # conditional orders (BingX error 109400: "ReduceOnly field cannot be filled").
        # positionSide alone is sufficient to identify which leg to close.
        if _hedge and "reduceOnly" in params:
            params.pop("reduceOnly", None)

        async def _do_place() -> Dict:
            if order_type == "market":
                return await ex.create_market_order(sym, side, amount, params=params)
            if order_type == "limit":
                return await ex.create_limit_order(sym, side, amount, price, params=params)
            return await ex.create_order(
                sym, order_type, side, amount, price=price, params=params
            )

        try:
            return await _do_place()
        except Exception as e:
            err = str(e)
            is_hedge_err = any(sig in err for sig in self._HEDGE_ERR_SIGNALS)
            if is_hedge_err and direction and "positionSide" not in params:
                ps = self._pos_side(direction)
                _log.info(
                    f"🔄 Hedge-mode detected on {_exc} — injecting positionSide={ps} "
                    f"and retrying ({err[:80]})"
                )
                self._hedge_mode_cache[_exc] = True
                params["positionSide"] = ps
                return await _do_place()
            raise

    # ── Balance ───────────────────────────────────────────────────────────────

    async def get_balance(
        self,
        user_id:       int,
        exchange:      str,
        api_key:       str,
        api_secret:    str,
        passphrase:    str  = "",
        testnet:       bool = False,
        force_refresh: bool = False,
    ) -> BalanceInfo:
        cache_key = (user_id, exchange.lower())
        if not force_refresh:
            cached = self._balance_cache.get(cache_key)
            if cached and time.time() - cached[1] < self._cache_ttl:
                return cached[0]
        empty = BalanceInfo(exchange=exchange)
        if not _HAS_CCXT:
            return empty
        try:
            ex = await self._get_exchange(user_id, exchange, api_key, api_secret,
                                          passphrase, testnet)
            if ex is None:
                _log.warning(f"⚠️ get_balance: CCXT exchange init failed for {exchange}")
                return empty
            # BingX swap requires explicit type param — defaultType in options alone
            # is not always honoured by fetch_balance in CCXT 4.x.
            ccxt_id = _CCXT_ID_MAP.get(exchange.lower(), exchange.lower())
            fetch_params: Dict[str, Any] = {}
            if ccxt_id == "bingx":
                fetch_params["type"] = "swap"
            raw  = await ex.fetch_balance(params=fetch_params)
            usdt = raw.get("USDT", {}) or {}
            free_val  = float(usdt.get("free",  0) or 0)
            used_val  = float(usdt.get("used",  0) or 0)
            total_val = float(usdt.get("total", 0) or 0)
            # Many futures exchanges store actual balance in raw["info"] sub-keys
            # because the top-level CCXT-normalised "USDT" dict may be zero for
            # isolated-margin or specialised perpetual accounts.
            if total_val == 0:
                ri = raw.get("info", {}) or {}
                # ── BingX linear swap: info.data is a list of account objects ──
                # CCXT 4.x parses these into top-level USDT but the fallback
                # handles the rare case where parsing silently returned 0.
                _bingx_data = ri.get("data") if isinstance(ri.get("data"), list) else None
                if _bingx_data:
                    for _acct in _bingx_data:
                        _asset = str(_acct.get("asset", "")).upper()
                        if _asset == "USDT":
                            tb = float(_acct.get("balance",         0) or
                                       _acct.get("equity",          0) or 0)
                            ab = float(_acct.get("availableMargin", 0) or
                                       _acct.get("availableBalance", 0) or 0)
                            if tb > 0:
                                total_val = tb
                                free_val  = ab if ab > 0 else tb
                                used_val  = max(0.0, total_val - free_val)
                            break
                # ── Binance USDM: totalWalletBalance / availableBalance ────────
                if total_val == 0:
                    tb = float(ri.get("totalWalletBalance",  0) or
                               ri.get("totalMarginBalance",   0) or
                               ri.get("balance",              0) or 0)
                    ab = float(ri.get("availableBalance",    0) or
                               ri.get("availableMargin",      0) or 0)
                    if tb > 0:
                        total_val = tb
                        free_val  = ab if ab > 0 else tb
                        used_val  = max(0.0, total_val - free_val)
                # ── Bybit / OKX / Gate: assets list ───────────────────────────
                if total_val == 0:
                    assets = (
                        (ri.get("result") or {}).get("list", []) or
                        ri.get("assets", []) or
                        (ri.get("data") or {}).get("list", []) or
                        []
                    )
                    for asset in assets:
                        coin = str(asset.get("coin", asset.get("currency",
                                   asset.get("asset", "")))).upper()
                        if coin == "USDT":
                            total_val = float(asset.get("walletBalance",  0) or
                                              asset.get("equity",         0) or
                                              asset.get("balance",        0) or 0)
                            free_val  = float(asset.get("availableToWithdraw", 0) or
                                              asset.get("available",       0) or
                                              asset.get("availableBalance",0) or
                                              asset.get("availableMargin", 0) or 0)
                            used_val  = max(0.0, total_val - free_val)
                            break
            if total_val == 0:
                _log.warning(
                    f"⚠️ get_balance: {exchange.upper()} returned $0.00 — "
                    f"check API key permissions and that funds are in the "
                    f"futures/swap wallet (not spot). raw keys: {list(raw.keys())}"
                )
            info = BalanceInfo(
                exchange=exchange,
                usdt_free=free_val,
                usdt_used=used_val,
                usdt_total=total_val,
            )
            self._balance_cache[cache_key] = (info, time.time())
            return info
        except Exception as e:
            _log.warning(f"⚠️ get_balance error ({exchange}): {e}")
            return BalanceInfo(exchange=exchange, error=str(e))

    async def test_connection(
        self,
        user_id:    int,
        exchange:   str,
        api_key:    str,
        api_secret: str,
        passphrase: str  = "",
        testnet:    bool = False,
    ) -> Dict[str, Any]:
        """
        Test API credentials by fetching balance.
        Returns {"ok": bool, "balance": float, "free": float, "error": str}.
        """
        result: Dict[str, Any] = {"ok": False, "balance": 0.0, "free": 0.0, "error": ""}
        if not _HAS_CCXT:
            result["error"] = "ccxt not installed"
            return result
        try:
            bi = await asyncio.wait_for(
                self.get_balance(
                    user_id, exchange, api_key, api_secret, passphrase, testnet,
                    force_refresh=True,
                ),
                timeout=12.0,
            )
            result["balance"] = bi.usdt_total
            result["free"]    = bi.usdt_free
            result["error"]   = bi.error
            result["ok"]      = not bool(bi.error)
        except asyncio.TimeoutError:
            result["error"] = f"{exchange.upper()} API timed out (12s) — check your network."
        except Exception as e:
            result["error"] = str(e)
        return result

    # ── Market Order ──────────────────────────────────────────────────────────

    async def market_order(
        self,
        user_id:    int,
        exchange:   str,
        api_key:    str,
        api_secret: str,
        symbol:     str,
        side:       str,
        amount:     float,
        params:     Optional[Dict] = None,
        passphrase: str  = "",
        testnet:    bool = False,
        direction:  str  = "",
    ) -> OrderResult:
        if not _HAS_CCXT:
            return OrderResult(success=False, error="ccxt not installed")
        try:
            ex  = await self._get_exchange(user_id, exchange, api_key, api_secret,
                                           passphrase, testnet)
            if ex is None:
                return OrderResult(success=False, error="exchange init failed")
            sym = self._normalise_symbol(symbol, exchange)
            raw = await self._place_order_with_hedge_retry(
                ex, sym, "market", side.lower(), amount,
                params=params, direction=direction, exchange=exchange,
            )
            _log.info(f"✅ Market order: {exchange} {side} {amount} {symbol} → {raw.get('id')}")
            return self._order_to_result(raw, exchange)
        except Exception as e:
            _log.warning(f"market_order error ({exchange} {symbol}): {e}")
            return OrderResult(success=False, error=str(e), exchange=exchange, symbol=symbol)

    # ── Limit Order ───────────────────────────────────────────────────────────

    async def limit_order(
        self,
        user_id:    int,
        exchange:   str,
        api_key:    str,
        api_secret: str,
        symbol:     str,
        side:       str,
        amount:     float,
        price:      float,
        params:     Optional[Dict] = None,
        passphrase: str  = "",
        testnet:    bool = False,
        direction:  str  = "",
    ) -> OrderResult:
        if not _HAS_CCXT:
            return OrderResult(success=False, error="ccxt not installed")
        try:
            ex  = await self._get_exchange(user_id, exchange, api_key, api_secret,
                                           passphrase, testnet)
            if ex is None:
                return OrderResult(success=False, error="exchange init failed")
            sym = self._normalise_symbol(symbol, exchange)
            raw = await self._place_order_with_hedge_retry(
                ex, sym, "limit", side.lower(), amount, price=price,
                params=params, direction=direction, exchange=exchange,
            )
            _log.info(f"✅ Limit order: {exchange} {side} {amount} {symbol} @ {price} → {raw.get('id')}")
            return self._order_to_result(raw, exchange)
        except Exception as e:
            _log.warning(f"limit_order error ({exchange} {symbol}): {e}")
            return OrderResult(success=False, error=str(e), exchange=exchange, symbol=symbol)

    # ── Stop-Loss ─────────────────────────────────────────────────────────────

    async def set_stop_loss(
        self,
        user_id:    int,
        exchange:   str,
        api_key:    str,
        api_secret: str,
        symbol:     str,
        side:       str,
        amount:     float,
        stop_price: float,
        passphrase: str  = "",
        testnet:    bool = False,
        direction:  str  = "",
    ) -> OrderResult:
        if not _HAS_CCXT:
            return OrderResult(success=False, error="ccxt not installed")
        try:
            ex  = await self._get_exchange(user_id, exchange, api_key, api_secret,
                                           passphrase, testnet)
            if ex is None:
                return OrderResult(success=False, error="exchange init failed")
            sym        = self._normalise_symbol(symbol, exchange)
            _dir       = direction or side   # use explicit direction if given
            close_side = "sell" if _dir.upper() in ("BUY", "LONG") else "buy"
            _exc_sl    = exchange.lower()
            _is_hedge  = self._hedge_mode_cache.get(_exc_sl, False)
            # In hedge mode "reduceOnly" is rejected — positionSide alone is enough.
            # In one-way mode (no hedge cache), "reduceOnly" must be set.
            sl_params: Dict[str, Any] = {"stopPrice": stop_price}
            if not _is_hedge:
                sl_params["reduceOnly"] = True
            if _exc_sl == "bybit":
                sl_params["triggerBy"]        = "LastPrice"
                sl_params["triggerDirection"] = 2 if close_side == "sell" else 1
            raw = await self._place_order_with_hedge_retry(
                ex, sym, "STOP_MARKET", close_side, amount,
                price=stop_price, params=sl_params,
                direction=_dir, exchange=exchange,
            )
            _log.info(f"✅ Stop-loss set: {exchange} {symbol} @ {stop_price}")
            return self._order_to_result(raw, exchange)
        except Exception as e:
            _log.warning(f"set_stop_loss error ({exchange} {symbol}): {e}")
            return OrderResult(success=False, error=str(e))

    # ── Full Signal Execution ─────────────────────────────────────────────────

    async def execute_signal(
        self,
        user_id:    int,
        exchange:   str,
        api_key:    str,
        api_secret: str,
        plan:       ExecutionPlan,
        passphrase: str  = "",
        testnet:    bool = False,
    ) -> Dict[str, Any]:
        """
        Execute a full trading plan: entry + SL + TP1/TP2/TP3.
        Returns dict with keys: entry, sl, tp1, tp2, tp3, success, errors.
        """
        results: Dict[str, Any] = {
            "success": False,
            "entry":   None,
            "sl":      None,
            "tp1":     None,
            "tp2":     None,
            "tp3":     None,
            "errors":  [],
            "plan":    plan,
        }
        if not _HAS_CCXT:
            results["errors"].append("ccxt not installed")
            return results

        ex = await self._get_exchange(user_id, exchange, api_key, api_secret,
                                      passphrase, testnet)
        if ex is None:
            results["errors"].append("Exchange init failed")
            return results

        side = "buy" if plan.direction.upper() in ("BUY", "LONG") else "sell"

        # Guard: never submit a zero-size order — catches misconfigured risk/balance combos
        if plan.position_size <= 0:
            results["errors"].append(
                "Zero position size — check balance and risk settings "
                f"(balance=${getattr(plan, 'notional_usdt', 0):.2f}, "
                f"risk={getattr(plan, 'risk_usdt', 0):.2f} USDT)"
            )
            return results

        # Set leverage — exchange-specific params to avoid API rejection.
        # NOTE: For Binance USDM, marginMode MUST be set via a separate
        # fapiPrivatePostLeverage call, NOT inside set_leverage params.
        # Mixing marginMode into set_leverage causes error -4048.
        try:
            sym = self._normalise_symbol(plan.symbol, exchange)
            _exc_lower = exchange.lower()
            if _exc_lower == "bybit":
                # Bybit V5: requires buy_leverage + sell_leverage in params
                await ex.set_leverage(plan.leverage, sym,
                                      params={"buy_leverage": plan.leverage,
                                              "sell_leverage": plan.leverage})
            else:
                # Binance USDM, OKX, Gate, etc. — plain leverage call
                await ex.set_leverage(plan.leverage, sym)
        except Exception as _le:
            _log.debug(f"set_leverage non-fatal ({exchange}): {_le}")

        # Set margin mode (isolated) separately — required for Binance USDM
        try:
            _exc_lower2 = exchange.lower()
            if _exc_lower2 in ("binance", "binanceusdm"):
                await ex.set_margin_mode("isolated", sym)
            elif _exc_lower2 == "bybit":
                await ex.set_margin_mode("isolated", sym,
                                         params={"category": "linear"})
        except Exception as _me:
            _log.debug(f"set_margin_mode non-fatal ({exchange}): {_me}")

        # Entry order
        try:
            if plan.order_type == "market":
                entry_result = await self.market_order(
                    user_id, exchange, api_key, api_secret,
                    plan.symbol, side, plan.position_size,
                    passphrase=passphrase, testnet=testnet,
                    direction=plan.direction,
                )
            else:
                entry_result = await self.limit_order(
                    user_id, exchange, api_key, api_secret,
                    plan.symbol, side, plan.position_size, plan.entry_price,
                    passphrase=passphrase, testnet=testnet,
                    direction=plan.direction,
                )
            results["entry"] = entry_result
            if not entry_result.success:
                results["errors"].append(f"Entry failed: {entry_result.error}")
                return results
        except Exception as e:
            results["errors"].append(f"Entry exception: {e}")
            return results

        # SL order
        try:
            sl_result = await self.set_stop_loss(
                user_id, exchange, api_key, api_secret,
                plan.symbol, side, plan.position_size, plan.sl_price,
                passphrase=passphrase, testnet=testnet,
                direction=plan.direction,
            )
            results["sl"] = sl_result
            if not sl_result.success:
                results["errors"].append(f"SL failed: {sl_result.error}")
        except Exception as e:
            results["errors"].append(f"SL exception: {e}")

        # TP orders (split by tp_split fractions)
        # Determine the last non-zero TP index so only that one gets
        # closePosition=True (closes residual) while earlier TPs use
        # reduceOnly=True + explicit partial size.
        _tp_prices  = [plan.tp1_price, plan.tp2_price, plan.tp3_price]
        _last_tp_idx = max(
            (i for i, p in enumerate(_tp_prices) if p and p > 0),
            default=-1,
        )
        for i, (tp_frac, tp_price, label) in enumerate(zip(
            plan.tp_split,
            _tp_prices,
            ["tp1", "tp2", "tp3"],
        )):
            if not tp_price:
                continue
            tp_size = round(plan.position_size * tp_frac, 4)
            _is_last_tp = (i == _last_tp_idx)
            try:
                tp_result = await self.set_take_profit(
                    user_id, exchange, api_key, api_secret,
                    plan.symbol, side, tp_size, tp_price,
                    passphrase=passphrase, testnet=testnet,
                    direction=plan.direction,
                    is_last_tp=_is_last_tp,
                )
                results[label] = tp_result
            except Exception as e:
                results["errors"].append(f"{label.upper()} exception: {e}")

        results["success"] = results["entry"] is not None and results["entry"].success
        _log.info(
            f"{'✅' if results['success'] else '❌'} Signal executed: "
            f"{exchange} {plan.symbol} {plan.direction} "
            f"size={plan.position_size} notional=${plan.notional_usdt:.0f} "
            f"kelly={plan.kelly_fraction:.1%} slip={plan.slippage_bps:.1f}bps"
        )
        return results

    # ── Open Positions ────────────────────────────────────────────────────────

    async def get_positions(
        self,
        user_id:    int,
        exchange:   str,
        api_key:    str,
        api_secret: str,
        symbol:     Optional[str] = None,
        passphrase: str  = "",
        testnet:    bool = False,
    ) -> List[Position]:
        if not _HAS_CCXT:
            return []
        try:
            ex = await self._get_exchange(user_id, exchange, api_key, api_secret,
                                          passphrase, testnet)
            if ex is None:
                return []
            if symbol:
                sym      = self._normalise_symbol(symbol, exchange)
                raw_list = await ex.fetch_positions([sym])
            else:
                raw_list = await ex.fetch_positions()
            result = []
            for r in raw_list:
                size = float(
                    r.get("contracts") or
                    r.get("info", {}).get("positionAmt", 0) or 0
                )
                if abs(size) < 1e-9:
                    continue
                result.append(Position(
                    symbol=str(r.get("symbol", "")),
                    side="long" if size > 0 else "short",
                    size=abs(size),
                    entry_price=float(r.get("entryPrice") or 0),
                    mark_price=float(r.get("markPrice") or 0),
                    unrealised_pnl=float(r.get("unrealizedPnl") or 0),
                    percentage=float(r.get("percentage") or 0),
                    liquidation_price=float(r.get("liquidationPrice") or 0),
                    leverage=int(r.get("leverage") or 1),
                    margin_mode=str(r.get("marginMode") or "isolated"),
                    notional=float(r.get("notional") or 0),
                ))
            return result
        except Exception as e:
            _log.warning(f"⚠️ get_positions error ({exchange}): {e}")
            return []

    # ── Cancel Order ──────────────────────────────────────────────────────────

    async def cancel_order(
        self,
        user_id:    int,
        exchange:   str,
        api_key:    str,
        api_secret: str,
        order_id:   str,
        symbol:     str,
        passphrase: str  = "",
        testnet:    bool = False,
    ) -> bool:
        if not _HAS_CCXT:
            return False
        try:
            ex = await self._get_exchange(user_id, exchange, api_key, api_secret,
                                          passphrase, testnet)
            if ex is None:
                return False
            sym = self._normalise_symbol(symbol, exchange)
            await ex.cancel_order(order_id, sym)
            _log.info(f"✅ Order cancelled: {exchange} {symbol} #{order_id}")
            return True
        except Exception as e:
            _log.debug(f"cancel_order error: {e}")
            return False

    # ── Close All Positions ───────────────────────────────────────────────────

    async def close_all_positions(
        self,
        user_id:    int,
        exchange:   str,
        api_key:    str,
        api_secret: str,
        passphrase: str  = "",
        testnet:    bool = False,
    ) -> Dict[str, Any]:
        """
        Market-close all open positions on the given exchange.
        Returns dict with closed symbols and any errors.
        """
        results: Dict[str, Any] = {"closed": [], "errors": []}
        if not _HAS_CCXT:
            results["errors"].append("ccxt not installed")
            return results
        try:
            positions = await self.get_positions(user_id, exchange, api_key,
                                                 api_secret, passphrase=passphrase,
                                                 testnet=testnet)
            _is_hedge_close = self._hedge_mode_cache.get(exchange.lower(), False)
            for pos in positions:
                close_side = "sell" if pos.side == "long" else "buy"
                # In hedge mode reduceOnly is forbidden — positionSide handles routing
                _close_params = {} if _is_hedge_close else {"reduceOnly": True}
                try:
                    r = await self.market_order(
                        user_id, exchange, api_key, api_secret,
                        pos.symbol, close_side, pos.size,
                        params=_close_params,
                        passphrase=passphrase, testnet=testnet,
                        direction=pos.side,   # hedge-mode: pass original position side
                    )
                    if r.success:
                        results["closed"].append(pos.symbol)
                    else:
                        results["errors"].append(f"{pos.symbol}: {r.error}")
                except Exception as e:
                    results["errors"].append(f"{pos.symbol}: {e}")
        except Exception as e:
            results["errors"].append(str(e))
        return results

    # ── Close Single Position ────────────────────────────────────────────────

    async def close_position(
        self,
        user_id:    int,
        exchange:   str,
        api_key:    str,
        api_secret: str,
        symbol:     str,
        side:       str,          # "long" / "short" — position side to close
        passphrase: str  = "",
        testnet:    bool = False,
    ) -> "OrderResult":
        """
        Market-close a single open position identified by *symbol* + *side*.

        Fetches the live position first to get the current size, then places a
        reduceOnly market order on the opposite side.  Supports BingX hedge-mode
        (positionSide injection) via the existing ``_place_order_with_hedge_retry``
        path.

        Args:
            symbol : exchange symbol, e.g. "BTCUSDT"
            side   : "long" or "short" — the direction of the existing position
        """
        if not _HAS_CCXT:
            return OrderResult(success=False, error="ccxt not installed")
        try:
            positions = await self.get_positions(
                user_id, exchange, api_key, api_secret,
                passphrase=passphrase, testnet=testnet,
            )
            sym_norm = self._normalise_symbol(symbol, exchange)
            # Find the matching position (symbol + side)
            target: Optional["Position"] = None
            for pos in positions:
                if (
                    self._normalise_symbol(pos.symbol, exchange) == sym_norm
                    and pos.side.lower() == side.lower()
                    and pos.size > 0
                ):
                    target = pos
                    break
            if target is None:
                return OrderResult(
                    success=False,
                    error=f"No open {side} position found for {symbol}",
                )
            close_side    = "sell" if target.side.lower() == "long" else "buy"
            _is_hm_close  = self._hedge_mode_cache.get(exchange.lower(), False)
            _cp           = {} if _is_hm_close else {"reduceOnly": True}
            r = await self.market_order(
                user_id, exchange, api_key, api_secret,
                target.symbol, close_side, target.size,
                params=_cp,
                passphrase=passphrase, testnet=testnet,
                direction=target.side,   # hedge-mode positionSide
            )
            if r.success:
                _log.info(
                    f"✅ Position closed: {exchange} {symbol} {side} "
                    f"size={target.size} → order {r.order_id}"
                )
            else:
                _log.warning(f"⚠️  close_position failed: {exchange} {symbol}: {r.error}")
            return r
        except Exception as e:
            _log.warning(f"close_position error ({exchange} {symbol} {side}): {e}")
            return OrderResult(success=False, error=str(e))

    # ── Get Open Orders (v12.0) ───────────────────────────────────────────────

    async def get_open_orders(
        self,
        user_id:    int,
        exchange:   str,
        api_key:    str,
        api_secret: str,
        symbol:     Optional[str] = None,
        passphrase: str  = "",
        testnet:    bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Return all open/pending orders for the exchange.
        Optionally filtered to a single symbol.
        Each entry: id, symbol, side, type, price, amount, filled, status, ts.
        """
        if not _HAS_CCXT:
            return []
        try:
            ex = await self._get_exchange(user_id, exchange, api_key, api_secret,
                                          passphrase, testnet)
            if ex is None:
                return []
            sym = self._normalise_symbol(symbol, exchange) if symbol else None
            raw = await ex.fetch_open_orders(sym) if sym else await ex.fetch_open_orders()
            return [
                {
                    "id":     str(r.get("id",        "")),
                    "symbol": str(r.get("symbol",    "")),
                    "side":   str(r.get("side",      "")),
                    "type":   str(r.get("type",      "")),
                    "price":  float(r.get("price")   or 0),
                    "amount": float(r.get("amount")  or 0),
                    "filled": float(r.get("filled")  or 0),
                    "status": str(r.get("status",    "")),
                    "ts":     float(r.get("timestamp") or 0) / 1000.0,
                }
                for r in (raw or [])
            ]
        except Exception as e:
            _log.warning(f"⚠️ get_open_orders error ({exchange}): {e}")
            return []

    # ── Cancel All Orders (v12.0) ─────────────────────────────────────────────

    async def cancel_all_orders(
        self,
        user_id:    int,
        exchange:   str,
        api_key:    str,
        api_secret: str,
        symbol:     Optional[str] = None,
        passphrase: str  = "",
        testnet:    bool = False,
    ) -> Dict[str, Any]:
        """
        Cancel every open order on the exchange (optionally filtered by symbol).
        Returns: {"cancelled": [order_ids], "errors": [error_strs]}
        """
        results: Dict[str, Any] = {"cancelled": [], "errors": []}
        if not _HAS_CCXT:
            results["errors"].append("ccxt not installed")
            return results
        try:
            orders = await self.get_open_orders(
                user_id, exchange, api_key, api_secret,
                symbol=symbol, passphrase=passphrase, testnet=testnet,
            )
            for order in orders:
                oid = order.get("id",     "")
                sym = order.get("symbol", "")
                if not oid:
                    continue
                try:
                    ok = await self.cancel_order(
                        user_id, exchange, api_key, api_secret,
                        oid, sym, passphrase=passphrase, testnet=testnet,
                    )
                    if ok:
                        results["cancelled"].append(oid)
                    else:
                        results["errors"].append(f"cancel failed for #{oid}")
                except Exception as e:
                    results["errors"].append(f"#{oid}: {e}")
        except Exception as e:
            results["errors"].append(str(e))
        return results

    # ── Move SL to Breakeven (v12.0) ──────────────────────────────────────────

    async def move_sl_to_breakeven(
        self,
        user_id:         int,
        exchange:        str,
        api_key:         str,
        api_secret:      str,
        symbol:          str,
        side:            str,
        size:            float,
        breakeven_price: float,
        buffer_pct:      float = 0.001,
        passphrase:      str   = "",
        testnet:         bool  = False,
    ) -> "OrderResult":
        """
        Move stop-loss to breakeven (entry price ± small buffer) after TP1 hit.

        buffer_pct: fractional cushion from exact entry — default 0.1%.
        LONG  → SL = breakeven * (1 − buffer_pct)  (just below entry)
        SHORT → SL = breakeven * (1 + buffer_pct)  (just above entry)

        Returns an OrderResult; success=True means the new SL order was placed.
        """
        if not _HAS_CCXT:
            return OrderResult(success=False, error="ccxt not installed")
        try:
            is_long  = side.lower() in ("buy", "long")
            sl_price = (
                round(breakeven_price * (1.0 - buffer_pct), 6) if is_long
                else round(breakeven_price * (1.0 + buffer_pct), 6)
            )
            result = await self.set_stop_loss(
                user_id, exchange, api_key, api_secret,
                symbol, side, size, sl_price,
                passphrase=passphrase, testnet=testnet,
            )
            if result.success:
                _log.info(
                    f"✅ SL → breakeven: {exchange} {symbol} @ {sl_price:.6f} "
                    f"(entry≈{breakeven_price:.6f}, buf={buffer_pct:.3%})"
                )
            return result
        except Exception as e:
            _log.warning(f"move_sl_to_breakeven error ({exchange} {symbol}): {e}")
            return OrderResult(success=False, error=str(e))

    # ── Smart Entry (v13.0) ───────────────────────────────────────────────────

    async def smart_entry(
        self,
        user_id:          int,
        exchange:         str,
        api_key:          str,
        api_secret:       str,
        symbol:           str,
        side:             str,
        amount:           float,
        entry_price:      float,
        spread_pct:       float = 0.0,
        spread_threshold: float = 0.0002,
        params:           Optional[Dict] = None,
        passphrase:       str   = "",
        testnet:          bool  = False,
    ) -> "OrderResult":
        """
        Intelligent order routing based on live spread width.

        If the observed spread is tighter than spread_threshold (default 0.02%),
        place a limit order at the mid-price to capture the spread and avoid
        market-impact slippage.  Otherwise fall back to a market order for
        guaranteed fill when the book is wider / less liquid.

        spread_pct: one-way spread as a fraction (e.g. 0.0001 = 0.01%).
        Binance USDM liquid hours typically run 0.01–0.03% one-way.
        """
        if spread_pct > 0.0 and spread_pct < spread_threshold:
            _log.info(
                f"💡 smart_entry [{symbol}]: spread={spread_pct:.4%}<{spread_threshold:.4%} "
                f"→ LIMIT @ {entry_price:.6f} (saves ~{spread_pct * 0.5:.4%} slippage)"
            )
            return await self.limit_order(
                user_id, exchange, api_key, api_secret,
                symbol, side, amount, entry_price,
                params=params, passphrase=passphrase, testnet=testnet,
            )
        return await self.market_order(
            user_id, exchange, api_key, api_secret,
            symbol, side, amount,
            params=params, passphrase=passphrase, testnet=testnet,
        )

    # ── Set Take Profit (v13.0) ────────────────────────────────────────────────

    async def set_take_profit(
        self,
        user_id:    int,
        exchange:   str,
        api_key:    str,
        api_secret: str,
        symbol:     str,
        side:       str,
        size:       float,
        tp_price:   float,
        passphrase: str  = "",
        testnet:    bool = False,
        direction:  str  = "",
        is_last_tp: bool = False,
    ) -> "OrderResult":
        """
        Place a TAKE_PROFIT_MARKET order to lock in a specific TP level.

        side: original position side ('buy'/'long' or 'sell'/'short').
        The closing side is automatically computed (sell for long, buy for short).
        is_last_tp: when True and exchange is Binance USDM, uses closePosition=True
            on the final TP so any residual contracts are always closed.
            For partial TPs (is_last_tp=False) we use reduceOnly=True + explicit
            size so earlier TPs do not accidentally flatten the whole position.
        direction: when provided, enables hedge-mode positionSide injection.
        """
        if not _HAS_CCXT:
            return OrderResult(success=False, error="ccxt not installed")
        try:
            ex = await self._get_exchange(user_id, exchange, api_key, api_secret,
                                          passphrase, testnet)
            if ex is None:
                return OrderResult(success=False, error="exchange init failed")
            sym        = self._normalise_symbol(symbol, exchange)
            _dir       = direction or side
            close_side = "sell" if _dir.upper() in ("BUY", "LONG") else "buy"
            _exc_tp    = exchange.lower()
            _is_hedge_tp = self._hedge_mode_cache.get(_exc_tp, False)
            tp_params: Dict[str, Any] = {"stopPrice": tp_price}
            # Binance USDM partial-TP strategy:
            #   • TP1 / TP2 (is_last_tp=False): reduceOnly=True + explicit partial size
            #     → closes only that fraction; remaining contracts stay open.
            #   • TP3 / sole TP (is_last_tp=True):  closePosition=True + amount=0
            #     → Binance closes whatever residual contracts remain; amount=0 is
            #     required when closePosition is set (API rejects non-zero amount).
            # Hedge-mode overrides: positionSide injected by _place_order_with_hedge_retry;
            # neither reduceOnly nor closePosition is valid alongside positionSide.
            _is_binance = _exc_tp in ("binance", "binanceusdm")
            if _is_hedge_tp:
                # Hedge-mode (dual-position-side): positionSide set by retry helper
                _tp_amount = size
            elif _is_binance and is_last_tp:
                # Final Binance TP: close all remaining contracts
                tp_params["closePosition"] = True
                _tp_amount = 0.0
            else:
                # One-way mode (Binance partial TP / OKX / Bybit / BingX one-way):
                # reduceOnly prevents opening a reverse position
                tp_params["reduceOnly"] = True
                _tp_amount = size
            raw = await self._place_order_with_hedge_retry(
                ex, sym, "TAKE_PROFIT_MARKET", close_side, _tp_amount,
                price=tp_price, params=tp_params,
                direction=_dir, exchange=exchange,
            )
            _log.info(
                f"✅ TP order set: {exchange} {symbol} {close_side} @ {tp_price:.6f} "
                f"→ {raw.get('id')}"
            )
            return self._order_to_result(raw, exchange)
        except Exception as e:
            _log.warning(f"set_take_profit error ({exchange} {symbol}): {e}")
            return OrderResult(success=False, error=str(e))

    async def close(self) -> None:
        """Close all exchange connections in the pool."""
        await self._pool.close_all()


# ── TradeMonitor ──────────────────────────────────────────────────────────────

class TradeMonitor:
    """
    Background monitor for open user-executed trades.

    After `_execute_signal` / `maybe_auto_execute` succeeds, register the
    trade here.  Every 60 s the monitor polls mark prices via the exchange
    positions API and fires DM notifications when:
      • TP1 / TP2 / TP3 is hit
      • SL is hit (static or trailed)
      • Trailing SL is activated / moved

    The notify_cb must be an async callable(user_id: int, html_text: str).
    """

    CHECK_INTERVAL = 60.0

    def __init__(self, executor: "ExchangeExecutor") -> None:
        self._exec   = executor
        self._trades: Dict[str, Dict[str, Any]] = {}
        self._lock   = asyncio.Lock()
        self._task:  Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
            _log.info("✅ TradeMonitor started")

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    async def register(
        self,
        trade_id:      str,
        user_id:       int,
        exchange:      str,
        api_key:       str,
        api_secret:    str,
        symbol:        str,
        direction:     str,
        entry:         float,
        sl:            float,
        tp1:           float,
        tp2:           float,
        tp3:           float,
        trailing_mode: str  = "off",
        passphrase:    str  = "",
        testnet:       bool = False,
        notify_cb:     Any  = None,
    ) -> None:
        async with self._lock:
            self._trades[trade_id] = {
                "user_id":      user_id,
                "exchange":     exchange,
                "api_key":      api_key,
                "api_secret":   api_secret,
                "passphrase":   passphrase,
                "testnet":      testnet,
                "symbol":       symbol,
                "direction":    direction.upper(),
                "entry":        entry,
                "sl":           sl,
                "sl_current":   sl,
                "tp1":          tp1,
                "tp2":          tp2,
                "tp3":          tp3,
                "trailing_mode": trailing_mode,
                "tp1_hit":      False,
                "tp2_hit":      False,
                "notify_cb":    notify_cb,
                "registered_at": time.time(),
            }
        _log.debug(f"TradeMonitor: registered trade {trade_id} {symbol} {direction}")

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.CHECK_INTERVAL)
                await self._check_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                _log.debug(f"TradeMonitor._run error: {e}")

    async def _check_all(self) -> None:
        async with self._lock:
            trade_ids = list(self._trades.keys())
        for tid in trade_ids:
            try:
                await self._check_one(tid)
            except Exception as e:
                _log.debug(f"TradeMonitor._check_one {tid}: {e}")

    async def _check_one(self, trade_id: str) -> None:
        async with self._lock:
            t = self._trades.get(trade_id)
            if t is None:
                return
            t = dict(t)

        try:
            positions = await asyncio.wait_for(
                self._exec.get_positions(
                    t["user_id"], t["exchange"],
                    t["api_key"], t["api_secret"],
                    passphrase=t.get("passphrase", ""),
                    testnet=t.get("testnet", False),
                ), timeout=12.0
            )
        except Exception:
            return

        sym       = t["symbol"]
        is_long   = t["direction"] in ("BUY", "LONG")
        entry     = t["entry"]
        sl        = t["sl_current"]
        tp1       = t["tp1"]
        tp2       = t["tp2"]
        tp3       = t["tp3"]

        sym_key = sym.replace("/", "").replace(":USDT", "").upper()
        mark_price = 0.0
        pos_found  = False
        for pos in positions:
            pos_sym = pos.symbol.replace("/", "").replace(":USDT", "").upper()
            if pos_sym == sym_key:
                _mp = getattr(pos, "mark_price", 0.0) or getattr(pos, "avg_price", 0.0)
                if _mp:
                    mark_price = float(_mp)
                    pos_found  = True
                break

        if not mark_price:
            if not pos_found:
                async with self._lock:
                    self._trades.pop(trade_id, None)
            return

        notify_cb    = t.get("notify_cb")
        trailing_mode = t.get("trailing_mode", "off")
        sym_disp     = sym_key.replace("USDT", "") + "/USDT"

        async def _notify(msg: str) -> None:
            if notify_cb and callable(notify_cb):
                try:
                    await notify_cb(t["user_id"], msg)
                except Exception:
                    pass

        def _pct() -> float:
            return abs(mark_price - entry) / max(entry, 1e-9) * 100.0

        tp3_hit = bool(tp3) and (mark_price >= tp3 if is_long else mark_price <= tp3)
        tp2_hit = bool(tp2) and (mark_price >= tp2 if is_long else mark_price <= tp2)
        tp1_hit = bool(tp1) and (mark_price >= tp1 if is_long else mark_price <= tp1)
        sl_hit  = (mark_price <= sl if is_long else mark_price >= sl)

        dir_e = "🟢 LONG" if is_long else "🔴 SHORT"

        if tp3_hit:
            await _notify(
                f"🎯🎯🎯 <b>TP3 Hit!</b> — {sym_disp}\n"
                f"{dir_e} | Entry: <code>{entry:.4f}</code>\n"
                f"Mark: <code>{mark_price:.4f}</code>  Profit: <code>+{_pct():.2f}%</code>\n"
                f"🏆 <b>All targets achieved!</b>"
            )
            async with self._lock:
                self._trades.pop(trade_id, None)
            return

        if tp2_hit and not t["tp2_hit"]:
            await _notify(
                f"🎯🎯 <b>TP2 Hit!</b> — {sym_disp}\n"
                f"{dir_e} | Entry: <code>{entry:.4f}</code>\n"
                f"Mark: <code>{mark_price:.4f}</code>  Profit: <code>+{_pct():.2f}%</code>"
            )
            async with self._lock:
                if trade_id in self._trades:
                    self._trades[trade_id]["tp2_hit"] = True
            if trailing_mode == "trail_tp2":
                new_sl = mark_price * (0.995 if is_long else 1.005)
                async with self._lock:
                    if trade_id in self._trades:
                        self._trades[trade_id]["sl_current"] = new_sl
                await _notify(
                    f"🔁 <b>Trailing SL moved</b> — {sym_disp}\n"
                    f"New SL: <code>{new_sl:.4f}</code>  (0.5% trail after TP2)"
                )
            return

        if tp1_hit and not t["tp1_hit"]:
            await _notify(
                f"🎯 <b>TP1 Hit!</b> — {sym_disp}\n"
                f"{dir_e} | Entry: <code>{entry:.4f}</code>\n"
                f"Mark: <code>{mark_price:.4f}</code>  Profit: <code>+{_pct():.2f}%</code>"
            )
            async with self._lock:
                if trade_id in self._trades:
                    self._trades[trade_id]["tp1_hit"] = True
            if trailing_mode == "breakeven_tp1":
                async with self._lock:
                    if trade_id in self._trades:
                        self._trades[trade_id]["sl_current"] = entry
                await _notify(
                    f"🔒 <b>SL → Break Even</b> — {sym_disp}\n"
                    f"Stop loss moved to entry: <code>{entry:.4f}</code>"
                )
            elif trailing_mode == "trail_tp1":
                new_sl = mark_price * (0.997 if is_long else 1.003)
                async with self._lock:
                    if trade_id in self._trades:
                        self._trades[trade_id]["sl_current"] = new_sl
                await _notify(
                    f"🔁 <b>Trailing SL activated</b> — {sym_disp}\n"
                    f"SL: <code>{new_sl:.4f}</code>  (0.3% trail after TP1)"
                )
            return

        if sl_hit:
            pct     = _pct()
            outcome = "partial win (trailing SL)" if t["tp1_hit"] else "loss"
            await _notify(
                f"🛑 <b>Stop Loss Hit</b> — {sym_disp}\n"
                f"{dir_e} | Entry: <code>{entry:.4f}</code>\n"
                f"SL: <code>{sl:.4f}</code>  Mark: <code>{mark_price:.4f}</code>\n"
                f"Result: <b>{outcome}</b>  Loss: <code>-{pct:.2f}%</code>"
            )
            async with self._lock:
                self._trades.pop(trade_id, None)


# ── Module-level singleton ────────────────────────────────────────────────────

_executor: Optional[ExchangeExecutor] = None


def get_executor() -> ExchangeExecutor:
    global _executor
    if _executor is None:
        _executor = ExchangeExecutor()
    return _executor
