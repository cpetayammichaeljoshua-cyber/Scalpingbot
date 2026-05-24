"""
SignalMaestro — Portfolio Optimizer  v11.0
═══════════════════════════════════════════════════════════════════════════════
Institutional-grade portfolio construction engine for the Unity Engine signal universe.

Capabilities:
• Mean-Variance Optimization (MVO / Markowitz efficient frontier)
• Risk Parity (Equal Risk Contribution — ERC)
• Black-Litterman model with LLM-generated views
• Maximum Sharpe Ratio portfolio
• Minimum Variance portfolio
• Optimal signal weighting: combines optimizer output with Kelly sizing
• Integration: feeds per-symbol weight multipliers into position sizing
• Async-safe: all heavy compute on ThreadPoolExecutor

Reference:
  Markowitz (1952), Black & Litterman (1992),
  Maillard, Roncalli & Teiletche (2010) — ERC,
  Ledoit-Wolf covariance shrinkage (2004)
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import minimize, Bounds, LinearConstraint

_log = logging.getLogger("UnityEngine.PortfolioOptimizer")

# ── Constants ──────────────────────────────────────────────────────────────────
MIN_WEIGHT        = 0.01   # minimum per-asset weight
MAX_WEIGHT        = 0.40   # maximum per-asset weight (concentration limit)
MIN_RETURN_HIST   = 20     # min return observations needed
SHRINKAGE_ALPHA   = 0.2    # Ledoit-Wolf shrinkage intensity (constant)
RISK_FREE_DAILY   = 0.055 / 252.0   # daily risk-free rate


# ── Data Structures ────────────────────────────────────────────────────────────

@dataclass
class PortfolioWeights:
    """Optimized portfolio weights for the signal universe."""
    method:          str
    computed_at:     float
    symbols:         List[str]
    weights:         Dict[str, float]    # symbol → weight (sum = 1)
    expected_return: float
    expected_vol:    float
    sharpe:          float
    max_drawdown:    float = 0.0
    # Per-symbol Kelly multiplier (weight / equal_weight)
    kelly_multipliers: Dict[str, float] = field(default_factory=dict)

    def get_multiplier(self, symbol: str) -> float:
        """Return Kelly position-size multiplier for symbol (1.0 = neutral)."""
        return self.kelly_multipliers.get(symbol, 1.0)


@dataclass
class BLView:
    """Black-Litterman investor view: asset or spread."""
    description:   str
    symbols:       List[str]    # assets in the view
    signs:         List[float]  # +1 for long, -1 for short
    expected_ret:  float        # expected return of the view (annualised)
    confidence:    float        # 0-1: 0 = ignored, 1 = absolute view


# ── Covariance Estimation ──────────────────────────────────────────────────────

def _ledoit_wolf_shrinkage(returns: np.ndarray) -> np.ndarray:
    """
    Ledoit-Wolf constant-correlation shrinkage estimator.
    Shrinks towards scaled identity to reduce estimation error.
    Reference: Ledoit & Wolf (2004)
    """
    T, N = returns.shape
    if T < 2 or N < 2:
        return np.eye(N) * 1e-4

    S   = np.cov(returns.T, ddof=1)   # sample covariance
    mu  = np.mean(np.diag(S))         # avg variance

    # Shrinkage target: scaled identity
    F   = mu * np.eye(N)

    # Ledoit-Wolf analytical shrinkage intensity
    delta = float(np.linalg.norm(S - F, "fro") ** 2)
    gamma = float(np.sum(np.diag(S) ** 2)) / T

    alpha = min(SHRINKAGE_ALPHA, max(0.0, gamma / (delta + 1e-12)))

    return (1.0 - alpha) * S + alpha * F


# ── Optimization Helpers ───────────────────────────────────────────────────────

def _portfolio_stats(w: np.ndarray, mu: np.ndarray, cov: np.ndarray) -> Tuple[float, float, float]:
    """Return (expected_return, volatility, sharpe) for weight vector w."""
    ret  = float(w @ mu)
    vol  = float(np.sqrt(w @ cov @ w))
    sr   = (ret - RISK_FREE_DAILY) / (vol + 1e-9)
    return ret, vol, sr


def _max_sharpe(mu: np.ndarray, cov: np.ndarray, n: int) -> np.ndarray:
    """Maximize Sharpe Ratio via quadratic programming."""
    def neg_sharpe(w):
        r, v, _ = _portfolio_stats(w, mu, cov)
        return -(r - RISK_FREE_DAILY) / (v + 1e-9)

    def grad_neg_sharpe(w):
        r, v, _ = _portfolio_stats(w, mu, cov)
        excess  = r - RISK_FREE_DAILY
        dr      = mu
        dv      = cov @ w / (v + 1e-9)
        return -(dr * v - excess * dv) / (v ** 2 + 1e-12)

    w0   = np.ones(n) / n
    bnds = Bounds(MIN_WEIGHT, MAX_WEIGHT)
    cons = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
    res  = minimize(neg_sharpe, w0, jac=grad_neg_sharpe,
                    method="SLSQP", bounds=bnds, constraints=cons,
                    options={"maxiter": 1000, "ftol": 1e-9})
    return res.x if res.success else w0


def _min_variance(cov: np.ndarray, n: int) -> np.ndarray:
    """Find minimum variance portfolio."""
    def port_var(w):
        return float(w @ cov @ w)

    def grad_var(w):
        return 2.0 * (cov @ w)

    w0   = np.ones(n) / n
    bnds = Bounds(MIN_WEIGHT, MAX_WEIGHT)
    cons = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
    res  = minimize(port_var, w0, jac=grad_var,
                    method="SLSQP", bounds=bnds, constraints=cons,
                    options={"maxiter": 1000, "ftol": 1e-12})
    return res.x if res.success else w0


def _risk_parity(cov: np.ndarray, n: int) -> np.ndarray:
    """
    Equal Risk Contribution (ERC / Risk Parity) portfolio.
    Each asset contributes equally to total portfolio variance.
    Reference: Maillard, Roncalli & Teiletche (2010)
    """
    def erc_obj(w):
        w = np.maximum(w, 1e-8)
        port_var = float(w @ cov @ w)
        mrc      = cov @ w                   # marginal risk contribution
        rc       = w * mrc                   # risk contribution
        rc_mean  = port_var / n
        return float(np.sum((rc - rc_mean) ** 2))

    def erc_grad(w):
        w        = np.maximum(w, 1e-8)
        port_var = float(w @ cov @ w)
        mrc      = cov @ w
        rc       = w * mrc
        rc_mean  = port_var / n
        # ∂obj/∂w_i = 2 * Σ_j (rc_j − rc_mean) * ∂rc_j/∂w_i
        d_rc     = np.diag(mrc) + (cov @ np.diag(w)) + np.outer(w, mrc)  # approx
        return 2.0 * d_rc.T @ (rc - rc_mean)

    w0   = np.ones(n) / n
    bnds = Bounds(MIN_WEIGHT, MAX_WEIGHT)
    cons = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
    res  = minimize(erc_obj, w0, jac=erc_grad,
                    method="SLSQP", bounds=bnds, constraints=cons,
                    options={"maxiter": 2000, "ftol": 1e-12})
    return res.x if res.success else w0


def _black_litterman(mu_eq: np.ndarray, cov: np.ndarray, views: List[BLView],
                     symbols: List[str], tau: float = 0.05) -> np.ndarray:
    """
    Black-Litterman posterior expected returns.
    Reference: Black & Litterman (1992)

    mu_eq  : equilibrium expected returns (from CAPM / equal-weight implied)
    cov    : Σ covariance matrix
    views  : investor views
    tau    : uncertainty scaling (typical 0.025–0.05)
    Returns: posterior expected return vector
    """
    n = len(symbols)
    if not views:
        return mu_eq

    valid_views = [v for v in views if len(v.symbols) > 0 and v.confidence > 0]
    if not valid_views:
        return mu_eq

    k   = len(valid_views)
    P   = np.zeros((k, n))
    Q   = np.zeros(k)
    Omega = np.zeros((k, k))  # view uncertainty diagonal

    sym_idx = {s: i for i, s in enumerate(symbols)}

    for i, view in enumerate(valid_views):
        for s, sign in zip(view.symbols, view.signs):
            if s in sym_idx:
                P[i, sym_idx[s]] = sign
        Q[i]         = view.expected_ret
        # Omega = (1 - confidence) / confidence × P Σ P' (tau-scaled)
        view_var     = tau * float(P[i] @ cov @ P[i])
        conf_factor  = max(1e-4, 1.0 - view.confidence) / (view.confidence + 1e-8)
        Omega[i, i]  = view_var * conf_factor

    # BL posterior: μ_BL = [(τΣ)⁻¹ + P'Ω⁻¹P]⁻¹ × [(τΣ)⁻¹μ_eq + P'Ω⁻¹Q]
    tau_cov    = tau * cov
    tau_cov_inv = np.linalg.pinv(tau_cov)
    omega_inv   = np.diag(1.0 / (np.diag(Omega) + 1e-12))

    M1 = tau_cov_inv + P.T @ omega_inv @ P
    M2 = tau_cov_inv @ mu_eq + P.T @ omega_inv @ Q

    try:
        mu_bl = np.linalg.solve(M1, M2)
    except np.linalg.LinAlgError:
        mu_bl = np.linalg.lstsq(M1, M2, rcond=None)[0]

    return mu_bl


# ── Main Optimizer Class ───────────────────────────────────────────────────────

class PortfolioOptimizer:
    """
    Live portfolio optimizer for the Unity Engine signal universe.

    Maintains a rolling return history per symbol and recomputes optimal
    weights on a scheduled interval. Weight multipliers are applied to
    Kelly position sizing in UnityProfitBooster.
    """

    def __init__(self, symbols: Optional[List[str]] = None):
        self._symbols  = list(symbols) if symbols else []
        self._lock     = threading.RLock()
        # rolling return buffer: symbol → list of daily returns
        self._returns: Dict[str, List[float]] = {s: [] for s in self._symbols}
        self._weights: Optional[PortfolioWeights] = None
        self._weights_ts: float = 0.0
        self._refresh_interval: float = 600.0   # recompute every 10 min
        self._bl_views: List[BLView] = []
        self._active_method: str = "max_sharpe"   # or "min_var", "risk_parity", "bl"

    # ── Public API ─────────────────────────────────────────────────────────────

    def update_return(self, symbol: str, ret: float) -> None:
        """Record a new return observation for a symbol. Auto-adds new symbols."""
        with self._lock:
            if symbol not in self._returns:
                # v11.0: auto-register new symbols as engine encounters them
                self._symbols.append(symbol)
                self._returns[symbol] = []
            if symbol in self._returns:
                self._returns[symbol].append(ret)
                # Keep last 252 observations (1 year daily)
                if len(self._returns[symbol]) > 252:
                    self._returns[symbol] = self._returns[symbol][-252:]

    def set_bl_views(self, views: List[BLView]) -> None:
        """Update Black-Litterman investor views (from LLM analysis)."""
        with self._lock:
            self._bl_views = list(views)

    def set_method(self, method: str) -> None:
        """Set optimization method: max_sharpe | min_var | risk_parity | bl"""
        with self._lock:
            if method in ("max_sharpe", "min_var", "risk_parity", "bl"):
                self._active_method = method

    def get_multiplier(self, symbol: str) -> float:
        """
        Return Kelly position-size multiplier for symbol.
        1.0 = neutral (equal weight), >1.0 = overweight, <1.0 = underweight
        """
        with self._lock:
            if self._weights:
                return self._weights.get_multiplier(symbol)
        return 1.0

    def get_weights(self) -> Optional[PortfolioWeights]:
        with self._lock:
            return self._weights

    def get_weight(self, symbol: str) -> Optional[float]:
        """
        Return the latest allocation weight [0..1] for a specific symbol.
        Returns None when no weights have been computed yet.
        Used by UnitySignalFilter Gate 8.5c for Kelly adjustment.
        """
        with self._lock:
            if self._weights is None:
                return None
            return self._weights.weights.get(symbol.upper())

    def compute(self) -> Optional[PortfolioWeights]:
        """
        Synchronous compute — run from thread pool.
        Returns PortfolioWeights or None if insufficient data.
        """
        with self._lock:
            symbols = [s for s in self._symbols if len(self._returns.get(s, [])) >= MIN_RETURN_HIST]
            if len(symbols) < 2:
                return None
            ret_matrix = np.array([self._returns[s][-252:] for s in symbols], dtype=float).T
            views  = list(self._bl_views)
            method = self._active_method

        n  = len(symbols)
        T  = ret_matrix.shape[0]

        # Shrinkage covariance
        cov = _ledoit_wolf_shrinkage(ret_matrix)

        # Annualise daily covariance
        cov_ann = cov * 252.0

        # Expected returns: sample mean (annualised)
        mu_daily = np.mean(ret_matrix, axis=0)
        mu_ann   = mu_daily * 252.0

        # Select optimization method
        if method == "risk_parity":
            w = _risk_parity(cov_ann, n)
            label = "Risk Parity"
        elif method == "min_var":
            w = _min_variance(cov_ann, n)
            label = "Min Variance"
        elif method == "bl" and views:
            # Equilibrium returns (CAPM implied from equal-weight)
            w_eq    = np.ones(n) / n
            port_var_eq = float(w_eq @ cov_ann @ w_eq)
            lam_eq  = (float(w_eq @ mu_ann) - RISK_FREE_DAILY * 252) / (port_var_eq + 1e-9)
            mu_eq   = lam_eq * cov_ann @ w_eq
            mu_bl   = _black_litterman(mu_eq, cov_ann, views, symbols)
            w = _max_sharpe(mu_bl, cov_ann, n)
            label = "Black-Litterman"
        else:
            w = _max_sharpe(mu_ann, cov_ann, n)
            label = "Max Sharpe"

        # Normalize
        w = np.clip(w, MIN_WEIGHT, MAX_WEIGHT)
        w = w / w.sum()

        # Portfolio stats
        exp_r, exp_v, sharpe = _portfolio_stats(w, mu_ann, cov_ann)

        # Kelly multipliers: w_i / (1/n) = n × w_i
        eq_weight = 1.0 / n
        mults = {s: float(np.clip(w[i] / eq_weight, 0.25, 3.0)) for i, s in enumerate(symbols)}

        result = PortfolioWeights(
            method=label,
            computed_at=time.time(),
            symbols=symbols,
            weights={s: float(w[i]) for i, s in enumerate(symbols)},
            expected_return=float(exp_r),
            expected_vol=float(exp_v),
            sharpe=float(sharpe),
            kelly_multipliers=mults,
        )
        with self._lock:
            self._weights    = result
            self._weights_ts = time.time()
        return result

    async def compute_async(self, executor=None) -> Optional[PortfolioWeights]:
        """Async wrapper — runs compute() on executor."""
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            if executor:
                return await loop.run_in_executor(executor, self.compute)
            else:
                return self.compute()
        except Exception as exc:
            _log.warning(f"[PortfolioOptimizer] compute_async failed: {exc}")
            return None

    def format_text(self) -> str:
        """Format portfolio weights for Telegram display."""
        with self._lock:
            pw = self._weights
        if not pw:
            return "📊 Portfolio Optimizer: insufficient return data"

        lines = [
            f"📊 *Portfolio Optimizer* — {pw.method}",
            f"E[R]={pw.expected_return:.1%}  σ={pw.expected_vol:.1%}  SR={pw.sharpe:.2f}",
            "",
        ]
        top_syms = sorted(pw.weights.items(), key=lambda x: -x[1])[:10]
        for sym, w in top_syms:
            mult = pw.kelly_multipliers.get(sym, 1.0)
            bar  = "█" * int(w * 40)
            lines.append(f"  {sym:12s} {w:.1%}  ×{mult:.2f}  {bar}")
        if len(pw.symbols) > 10:
            lines.append(f"  … +{len(pw.symbols)-10} more")
        return "\n".join(lines)
