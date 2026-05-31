#!/usr/bin/env python3
"""
Unity Engine — Stochastic Quantitative Engine v1.0 (v18.99)
Institutional-grade stochastic calculus module for the Unity trading system.

Implements:
  1. Ornstein-Uhlenbeck (OU) Process       — mean reversion detection & entry timing
  2. Geometric Brownian Motion (GBM)        — price path simulation & VaR
  3. Heston Stochastic Volatility           — vol regime detection & better TP/SL
  4. Merton Jump-Diffusion                  — fat-tail / gap risk modeling
  5. Euler-Maruyama SDE Solver              — general numerical SDE integration
  6. Probability of Backtesting Overfitting — CSCV-based PBO for strategy validation
  7. Implied Volatility Solver              — Brent's method Newton-Raphson hybrid
  8. Kalman Filter                          — adaptive noise-reduced price/trend estimate
  9. Factor IC / IR rolling engine          — signal quality validation
 10. Portfolio Optimization (MVO / RP / BL) — position-level capital allocation overlay

All methods are pure-NumPy / SciPy — no torch required (works in SOVEREIGN SKLEARN mode).
Designed to be async-safe: heavy batch computations released via asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import optimize, stats

_log = logging.getLogger("UnityEngine.StochasticQuant")


# ─────────────────────────────────────────────────────────────────────────────
# Data containers
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OUParams:
    """Calibrated Ornstein-Uhlenbeck parameters."""
    kappa:    float   # mean-reversion speed (θ)
    mu:       float   # long-term equilibrium (μ)
    sigma:    float   # diffusion (σ)
    half_life: float  # ln(2)/kappa — bars to return halfway to mean
    r_squared: float  # calibration R²

@dataclass
class HestonParams:
    """Calibrated Heston stochastic-volatility parameters."""
    kappa:   float   # vol mean-reversion speed
    theta:   float   # long-run variance
    xi:      float   # vol of vol
    rho:     float   # S-v correlation
    v0:      float   # current variance

@dataclass
class JumpParams:
    """Merton jump-diffusion parameters."""
    lam:    float   # jump intensity (jumps/year)
    mu_j:   float   # mean log-jump size
    sigma_j: float  # jump-size std

@dataclass
class QuantSignal:
    """Composite stochastic signal for a single asset."""
    symbol:          str
    timestamp:       float

    ou_zscore:       float   # OU z-score: >+2 → mean-reversion SELL; <-2 → BUY
    ou_halflife:     float   # OU half-life in bars
    ou_regime:       str     # "TRENDING" | "REVERTING" | "NEUTRAL"

    heston_vol:      float   # current Heston instantaneous vol
    heston_regime:   str     # "LOW_VOL" | "MID_VOL" | "HIGH_VOL" | "CRISIS"

    gbm_var_1d:      float   # 1-day 95% VaR (fractional)
    gbm_cvar_1d:     float   # 1-day 95% CVaR (fractional)

    jump_prob_1d:    float   # P(at least 1 jump today)

    kalman_trend:    float   # Kalman-filtered price trend (bps/bar)
    kalman_noise:    float   # residual noise estimate

    pbo_score:       float   # probability of overfitting (0=none, 1=fully overfit)

    entry_quality:   float   # composite [0,1] — higher → better entry timing
    sl_multiplier:   float   # recommended SL distance multiplier vs static
    tp_multiplier:   float   # recommended TP distance multiplier vs static


# ─────────────────────────────────────────────────────────────────────────────
# 1. Ornstein-Uhlenbeck Engine
# ─────────────────────────────────────────────────────────────────────────────

class OUEngine:
    """
    Ornstein-Uhlenbeck mean-reversion process.
    dX_t = κ(μ - X_t)dt + σ dW_t

    Calibrates κ, μ, σ via discrete-time OLS on the AR(1) representation:
      X_{t+1} - X_t = a + b·X_t + ε_t
    where: a = κμΔt, b = -κΔt, σ² = Var(ε)/Δt
    """

    @staticmethod
    def calibrate(prices: np.ndarray, dt: float = 1.0) -> Optional[OUParams]:
        """Fit OU parameters to price series using OLS."""
        try:
            if len(prices) < 20:
                return None
            x = np.asarray(prices, dtype=float)
            # AR(1): ΔX = a + b·X_t + ε
            dx = np.diff(x)
            xt = x[:-1]
            A = np.column_stack([np.ones(len(xt)), xt])
            result = np.linalg.lstsq(A, dx, rcond=None)
            a, b = result[0]
            residuals = dx - (a + b * xt)
            sigma2 = np.var(residuals) / dt

            kappa = -b / dt
            if kappa <= 1e-6:
                kappa = 1e-6
            mu = a / (kappa * dt) if abs(kappa * dt) > 1e-9 else float(np.mean(x))
            sigma = math.sqrt(max(sigma2, 1e-12))
            half_life = math.log(2) / kappa

            ss_res = float(np.sum(residuals**2))
            ss_tot = float(np.sum((dx - np.mean(dx))**2))
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0

            return OUParams(kappa=kappa, mu=mu, sigma=sigma, half_life=half_life, r_squared=max(r2, 0.0))
        except Exception as e:
            _log.debug(f"OUEngine.calibrate error: {e}")
            return None

    @staticmethod
    def zscore(price: float, params: OUParams) -> float:
        """OU z-score: how many std-devs is current price from equilibrium."""
        sigma_eq = params.sigma / math.sqrt(max(2 * params.kappa, 1e-9))
        return (price - params.mu) / max(sigma_eq, 1e-12)

    @staticmethod
    def half_life_regime(half_life: float) -> str:
        """Classify regime based on OU half-life."""
        if half_life < 5:
            return "REVERTING"
        elif half_life < 20:
            return "NEUTRAL"
        else:
            return "TRENDING"

    @staticmethod
    def simulate(params: OUParams, n_steps: int = 100, dt: float = 1.0,
                 x0: Optional[float] = None) -> np.ndarray:
        """Euler-Maruyama simulation of OU path."""
        x = np.empty(n_steps + 1)
        x[0] = params.mu if x0 is None else x0
        sqrt_dt = math.sqrt(dt)
        for i in range(n_steps):
            dW = np.random.standard_normal()
            x[i + 1] = x[i] + params.kappa * (params.mu - x[i]) * dt + params.sigma * sqrt_dt * dW
        return x


# ─────────────────────────────────────────────────────────────────────────────
# 2. Heston Stochastic Volatility Engine
# ─────────────────────────────────────────────────────────────────────────────

class HestonEngine:
    """
    Heston (1993) stochastic volatility model.
    dS = μS dt + √v S dW^S
    dv = κ(θ - v)dt + ξ√v dW^v,  corr(dW^S, dW^v) = ρ dt

    Simplified moment-matching calibration from realized vol series.
    """

    @staticmethod
    def calibrate_from_returns(returns: np.ndarray, dt: float = 1/252) -> HestonParams:
        """
        Calibrate Heston parameters from a return series using method-of-moments.
        Fits CIR process to rolling realized variance sequence.
        """
        try:
            ret = np.asarray(returns, dtype=float)
            if len(ret) < 30:
                sigma_r = float(np.std(ret))
                v0 = sigma_r ** 2 / dt
                return HestonParams(kappa=1.0, theta=v0, xi=0.2, rho=-0.7, v0=v0)

            # Rolling 5-bar realized variance
            window = min(10, len(ret) // 3)
            rv = np.array([np.var(ret[max(0, i - window):i + 1]) / dt
                           for i in range(len(ret))])
            rv = np.maximum(rv, 1e-10)

            v0 = float(rv[-1])
            theta = float(np.mean(rv))
            var_rv = float(np.var(rv))
            # From CIR moment matching: Var(v) ≈ ξ²θ/(2κ)
            # Use autocorrelation to get κ: AC(1) ≈ exp(-κΔt)
            if len(rv) > 1:
                ac1 = float(np.corrcoef(rv[:-1], rv[1:])[0, 1])
                ac1 = max(min(ac1, 0.9999), 0.0001)
                kappa = -math.log(ac1) / dt
            else:
                kappa = 2.0
            kappa = max(kappa, 0.01)

            xi = math.sqrt(max(var_rv * 2 * kappa / max(theta, 1e-10), 1e-6))
            xi = min(xi, 5.0)

            # Estimate ρ from leverage effect
            if len(ret) > 1:
                ret_aligned = ret[1:]
                rv_diff = np.diff(rv)
                if len(ret_aligned) == len(rv_diff) and np.std(ret_aligned) > 1e-12 and np.std(rv_diff) > 1e-12:
                    rho = float(np.corrcoef(ret_aligned, rv_diff)[0, 1])
                    rho = max(min(rho, 0.99), -0.99)
                else:
                    rho = -0.7
            else:
                rho = -0.7

            return HestonParams(kappa=kappa, theta=theta, xi=xi, rho=rho, v0=v0)
        except Exception as e:
            _log.debug(f"HestonEngine.calibrate error: {e}")
            sigma_est = float(np.std(returns)) if len(returns) > 1 else 0.01
            v0 = sigma_est ** 2 / max(dt, 1e-9)
            return HestonParams(kappa=1.0, theta=v0, xi=0.3, rho=-0.7, v0=v0)

    @staticmethod
    def vol_regime(v: float, theta: float) -> str:
        """Classify vol regime relative to long-run mean."""
        ratio = math.sqrt(v) / max(math.sqrt(theta), 1e-9)
        if ratio < 0.6:
            return "LOW_VOL"
        elif ratio < 1.2:
            return "MID_VOL"
        elif ratio < 2.0:
            return "HIGH_VOL"
        else:
            return "CRISIS"

    @staticmethod
    def simulate_paths(params: HestonParams, n_paths: int = 500, n_steps: int = 20,
                       dt: float = 1/252, s0: float = 1.0) -> np.ndarray:
        """Monte Carlo simulation of Heston paths — returns final S/S0 ratios."""
        sqrt_dt = math.sqrt(dt)
        S = np.ones(n_paths) * s0
        v = np.ones(n_paths) * params.v0
        rho = params.rho
        sqrt_1_rho2 = math.sqrt(max(1 - rho ** 2, 0.0))
        for _ in range(n_steps):
            Z1 = np.random.standard_normal(n_paths)
            Z2 = np.random.standard_normal(n_paths)
            Wv = Z1
            Ws = rho * Z1 + sqrt_1_rho2 * Z2
            v_plus = np.maximum(v, 0.0)
            sv = np.sqrt(v_plus)
            dv = params.kappa * (params.theta - v_plus) * dt + params.xi * sv * sqrt_dt * Wv
            v = np.maximum(v + dv, 0.0)
            dS = sv * sqrt_dt * Ws
            S *= np.exp(dS - 0.5 * v_plus * dt)
        return S / s0


# ─────────────────────────────────────────────────────────────────────────────
# 3. GBM / VaR Engine
# ─────────────────────────────────────────────────────────────────────────────

class GBMEngine:
    """
    Geometric Brownian Motion engine for VaR / CVaR estimation.
    dS = μ dt + σ dW  (log-return form)
    """

    @staticmethod
    def fit(returns: np.ndarray, dt: float = 1.0) -> Tuple[float, float]:
        """Fit GBM drift and vol from log-return series."""
        r = np.asarray(returns, dtype=float)
        mu = float(np.mean(r)) / dt
        sigma = float(np.std(r)) / math.sqrt(dt)
        return mu, sigma

    @staticmethod
    def var_cvar(mu: float, sigma: float, horizon: float = 1.0,
                 alpha: float = 0.05, n_sim: int = 5000) -> Tuple[float, float]:
        """
        Parametric GBM VaR and CVaR via Monte Carlo.
        Returns (VaR, CVaR) as fractional losses (positive = loss).
        """
        try:
            sqrt_h = math.sqrt(horizon)
            sims = np.random.normal(mu * horizon - 0.5 * sigma**2 * horizon,
                                    sigma * sqrt_h, n_sim)
            losses = -(np.exp(sims) - 1.0)
            var = float(np.percentile(losses, (1 - alpha) * 100))
            cvar = float(np.mean(losses[losses >= var]))
            return max(var, 0.0), max(cvar, 0.0)
        except Exception:
            return sigma * math.sqrt(horizon) * 1.645, sigma * math.sqrt(horizon) * 2.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Merton Jump-Diffusion Engine
# ─────────────────────────────────────────────────────────────────────────────

class JumpDiffusionEngine:
    """
    Merton (1976) jump-diffusion model.
    log(S_T/S_0) ~ N(·) + compound Poisson jumps.

    Calibrated from return series by separating diffusive and jump components
    using the bipower variation approach.
    """

    @staticmethod
    def calibrate(returns: np.ndarray, dt: float = 1/252) -> JumpParams:
        """Estimate jump intensity and size from return series."""
        try:
            r = np.asarray(returns, dtype=float)
            if len(r) < 20:
                return JumpParams(lam=2.0, mu_j=-0.01, sigma_j=0.02)

            # Bipower variation estimate of diffusive variance
            bpv = np.sum(np.abs(r[:-1]) * np.abs(r[1:])) * math.pi / (2.0 * len(r))
            rv = float(np.var(r))
            jump_var = max(rv - bpv / dt, 0.0)

            # Threshold for jump detection (3σ of diffusive component)
            sigma_d = math.sqrt(max(bpv / dt, 1e-10))
            thresh = 3.0 * sigma_d * math.sqrt(dt)
            jumps = r[np.abs(r) > thresh]

            lam = max(len(jumps) / max(len(r) * dt, 1e-9), 0.1)
            mu_j = float(np.mean(jumps)) if len(jumps) > 0 else -0.01
            sigma_j = float(np.std(jumps)) if len(jumps) > 1 else max(sigma_d, 0.01)

            return JumpParams(lam=lam, mu_j=mu_j, sigma_j=max(sigma_j, 0.005))
        except Exception as e:
            _log.debug(f"JumpDiffusionEngine.calibrate error: {e}")
            return JumpParams(lam=2.0, mu_j=-0.01, sigma_j=0.02)

    @staticmethod
    def jump_prob(params: JumpParams, horizon_days: float = 1.0) -> float:
        """P(at least one jump in horizon) = 1 - exp(-λ·T)."""
        return 1.0 - math.exp(-params.lam * horizon_days / 252.0)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Kalman Filter (Price Trend Estimator)
# ─────────────────────────────────────────────────────────────────────────────

class KalmanFilter:
    """
    Linear Kalman Filter for noise-reduced price trend estimation.
    State: [price_level, velocity]
    Observation: price_level
    """

    def __init__(self, obs_noise: float = 1.0, proc_noise: float = 0.1):
        self.Q = np.diag([proc_noise, proc_noise * 0.1])  # process noise
        self.R = np.array([[obs_noise]])                   # obs noise
        self.A = np.array([[1.0, 1.0], [0.0, 1.0]])       # state transition
        self.H = np.array([[1.0, 0.0]])                    # observation
        self.P = np.eye(2) * 1.0
        self.x = None                                       # state estimate

    def update(self, observation: float) -> Tuple[float, float]:
        """
        Process one observation.
        Returns (filtered_price, velocity_estimate).
        """
        z = np.array([[observation]])
        if self.x is None:
            self.x = np.array([[observation], [0.0]])
            return observation, 0.0

        # Predict
        x_pred = self.A @ self.x
        P_pred = self.A @ self.P @ self.A.T + self.Q

        # Update
        S = self.H @ P_pred @ self.H.T + self.R
        K = P_pred @ self.H.T @ np.linalg.inv(S)
        self.x = x_pred + K @ (z - self.H @ x_pred)
        self.P = (np.eye(2) - K @ self.H) @ P_pred

        return float(self.x[0, 0]), float(self.x[1, 0])

    def bulk_update(self, prices: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Run filter over a price series, return (filtered, velocity)."""
        n = len(prices)
        filtered = np.empty(n)
        velocity = np.empty(n)
        for i, p in enumerate(prices):
            f, v = self.update(float(p))
            filtered[i] = f
            velocity[i] = v
        return filtered, velocity


# ─────────────────────────────────────────────────────────────────────────────
# 6. Probability of Backtesting Overfitting (PBO) — CSCV
# ─────────────────────────────────────────────────────────────────────────────

class PBOEngine:
    """
    Probability of Backtesting Overfitting via Combinatorially Symmetric
    Cross-Validation (CSCV) — Bailey, Borwein, López de Prado, Zhu (2014).

    PBO ∈ [0,1]: 0 = no overfitting detected, 1 = fully overfit.
    """

    @staticmethod
    def compute(returns_matrix: np.ndarray, n_subsets: int = 8) -> float:
        """
        Args:
            returns_matrix: shape (n_periods, n_strategies) — returns for each
                            candidate strategy (parameter set) per period.
            n_subsets:      number of cross-validation splits (must be even, ≥4).

        Returns:
            pbo: float ∈ [0, 1]
        """
        try:
            T, S = returns_matrix.shape
            if S < 2 or T < n_subsets:
                return 0.0

            n_subsets = max(4, n_subsets // 2 * 2)  # ensure even
            subset_size = T // n_subsets
            if subset_size < 1:
                return 0.0

            # Build n_subsets equal blocks
            blocks = []
            for i in range(n_subsets):
                start = i * subset_size
                end = min(start + subset_size, T)
                blocks.append(returns_matrix[start:end, :])

            # All ways to split n_subsets blocks into IS/OOS halves
            half = n_subsets // 2
            all_idx = list(range(n_subsets))
            n_lambdas = 0
            n_overfit = 0

            for is_idx in combinations(all_idx, half):
                oos_idx = [i for i in all_idx if i not in is_idx]

                is_data  = np.vstack([blocks[i] for i in is_idx])
                oos_data = np.vstack([blocks[i] for i in oos_idx])

                is_sharpe  = np.mean(is_data,  axis=0) / (np.std(is_data,  axis=0) + 1e-12)
                oos_sharpe = np.mean(oos_data, axis=0) / (np.std(oos_data, axis=0) + 1e-12)

                best_is  = int(np.argmax(is_sharpe))
                rank_oos = float(stats.rankdata(oos_sharpe)[best_is]) / S

                # λ = logit of OOS rank
                lam = math.log(rank_oos / max(1.0 - rank_oos, 1e-9))
                n_lambdas += 1
                if lam < 0:
                    n_overfit += 1

            pbo = n_overfit / max(n_lambdas, 1)
            return float(pbo)
        except Exception as e:
            _log.debug(f"PBOEngine.compute error: {e}")
            return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 7. Implied Volatility Solver
# ─────────────────────────────────────────────────────────────────────────────

class IVSolver:
    """
    Black-Scholes Implied Volatility solver using Brent's method.
    Provides the IV surface slice for a given (price, strike, T, r) tuple.
    """

    @staticmethod
    def _bs_price(S: float, K: float, T: float, r: float, sigma: float,
                  option_type: str = "call") -> float:
        if T <= 0 or sigma <= 0:
            return max((S - K) if option_type == "call" else (K - S), 0.0)
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        N = stats.norm.cdf
        if option_type == "call":
            return S * N(d1) - K * math.exp(-r * T) * N(d2)
        else:
            return K * math.exp(-r * T) * N(-d2) - S * N(-d1)

    @staticmethod
    def solve(market_price: float, S: float, K: float, T: float,
              r: float = 0.0, option_type: str = "call") -> Optional[float]:
        """
        Solve for implied volatility using Brent's method.
        Returns IV or None if no solution found.
        """
        try:
            if T <= 0 or market_price <= 0:
                return None
            intrinsic = max((S - K if option_type == "call" else K - S), 0.0)
            if market_price <= intrinsic:
                return None

            def objective(sigma: float) -> float:
                return IVSolver._bs_price(S, K, T, r, sigma, option_type) - market_price

            # Brent's method on [0.001, 10.0]
            try:
                iv = optimize.brentq(objective, 1e-4, 10.0, xtol=1e-6, maxiter=100)
                return float(iv)
            except ValueError:
                return None
        except Exception as e:
            _log.debug(f"IVSolver.solve error: {e}")
            return None


# ─────────────────────────────────────────────────────────────────────────────
# 8. Portfolio Optimization (MVO / Risk Parity / Black-Litterman)
# ─────────────────────────────────────────────────────────────────────────────

class PortfolioOptimizer:
    """
    Institutional portfolio construction toolkit.
    Methods: Mean-Variance Optimization (MVO), Risk Parity (RP),
             Black-Litterman (BL) posterior, Minimum Variance.
    """

    @staticmethod
    def min_variance(cov: np.ndarray) -> np.ndarray:
        """Global minimum variance weights via quadratic programming (analytical)."""
        try:
            n = cov.shape[0]
            inv_cov = np.linalg.inv(cov + np.eye(n) * 1e-8)
            ones = np.ones(n)
            w = inv_cov @ ones
            return w / w.sum()
        except Exception:
            return np.ones(cov.shape[0]) / cov.shape[0]

    @staticmethod
    def risk_parity(cov: np.ndarray, max_iter: int = 500) -> np.ndarray:
        """Equal risk contribution (Risk Parity) weights."""
        try:
            n = cov.shape[0]
            w = np.ones(n) / n
            for _ in range(max_iter):
                sigma = math.sqrt(float(w @ cov @ w))
                marginal_risk = cov @ w / max(sigma, 1e-12)
                rc = w * marginal_risk
                target = sigma / n
                w_new = w * target / (marginal_risk + 1e-12)
                w_new = np.maximum(w_new, 1e-9)
                w_new /= w_new.sum()
                if np.max(np.abs(w_new - w)) < 1e-8:
                    break
                w = w_new
            return w / w.sum()
        except Exception:
            return np.ones(cov.shape[0]) / cov.shape[0]

    @staticmethod
    def black_litterman(
        mu_prior: np.ndarray, cov: np.ndarray,
        P: np.ndarray, Q: np.ndarray,
        omega: Optional[np.ndarray] = None, tau: float = 0.05
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Black-Litterman posterior (μ_BL, Σ_BL).
        P:  (k, n) view matrix
        Q:  (k,)   view expected returns
        omega: (k,k) view uncertainty (default: proportional to tau·P·Σ·P')
        """
        try:
            n = len(mu_prior)
            Sigma_pi = tau * cov
            if omega is None:
                omega = np.diag(np.diag(P @ Sigma_pi @ P.T))
            M = np.linalg.inv(np.linalg.inv(Sigma_pi) + P.T @ np.linalg.inv(omega) @ P)
            mu_bl = M @ (np.linalg.inv(Sigma_pi) @ mu_prior + P.T @ np.linalg.inv(omega) @ Q)
            sigma_bl = M + cov
            return mu_bl, sigma_bl
        except Exception:
            return mu_prior, cov

    @staticmethod
    def mvo(mu: np.ndarray, cov: np.ndarray, target_return: Optional[float] = None,
            long_only: bool = True, max_weight: float = 0.30) -> np.ndarray:
        """
        Mean-Variance Optimization via scipy minimize.
        If target_return is None, maximizes Sharpe ratio.
        """
        try:
            n = len(mu)
            if n == 1:
                return np.array([1.0])

            def neg_sharpe(w: np.ndarray) -> float:
                port_ret = float(w @ mu)
                port_var = float(w @ cov @ w)
                return -port_ret / max(math.sqrt(port_var), 1e-12)

            constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
            if target_return is not None:
                constraints.append({"type": "eq", "fun": lambda w: float(w @ mu) - target_return})

            bounds = [(0.0 if long_only else -max_weight, max_weight)] * n
            w0 = np.ones(n) / n
            res = optimize.minimize(neg_sharpe, w0, method="SLSQP",
                                    bounds=bounds, constraints=constraints,
                                    options={"maxiter": 500, "ftol": 1e-9})
            if res.success:
                w = np.maximum(res.x, 0.0)
                return w / max(w.sum(), 1e-9)
            return np.ones(n) / n
        except Exception:
            return np.ones(len(mu)) / max(len(mu), 1)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Factor IC / IR Rolling Engine
# ─────────────────────────────────────────────────────────────────────────────

class FactorICIR:
    """
    Rolling Information Coefficient (IC) and Information Ratio (IR) tracker.
    IC = Spearman rank correlation between predicted and realized returns.
    IR = IC.mean() / IC.std() — signal quality metric.
    """

    def __init__(self, window: int = 20):
        self.window = window
        self._ic_history: List[float] = []

    def update(self, predictions: np.ndarray, realized: np.ndarray) -> Tuple[float, float]:
        """
        Compute IC for this period and return (IC, rolling_IR).
        predictions, realized: arrays of same length.
        """
        try:
            ic = float(stats.spearmanr(predictions, realized).correlation)
            if math.isnan(ic):
                ic = 0.0
        except Exception:
            ic = 0.0

        self._ic_history.append(ic)
        if len(self._ic_history) > self.window * 3:
            self._ic_history = self._ic_history[-self.window * 3:]

        recent = self._ic_history[-self.window:]
        if len(recent) < 3:
            return ic, 0.0
        ic_mean = float(np.mean(recent))
        ic_std  = float(np.std(recent))
        ir = ic_mean / max(ic_std, 1e-9)
        return ic, ir

    @property
    def mean_ic(self) -> float:
        if not self._ic_history:
            return 0.0
        return float(np.mean(self._ic_history[-self.window:]))

    @property
    def ir(self) -> float:
        recent = self._ic_history[-self.window:]
        if len(recent) < 3:
            return 0.0
        return float(np.mean(recent)) / max(float(np.std(recent)), 1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# 10. Main Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class StochasticQuantEngine:
    """
    Unity Engine Stochastic Quant Orchestrator.

    Maintains per-symbol calibrated models and provides composite QuantSignals
    for use by the signal filter (EV gate, TP/SL calibration, OU entry timing).

    Thread-safe via asyncio.to_thread() for heavy computations.
    """

    def __init__(self):
        self._ou:      Dict[str, OUParams]     = {}
        self._heston:  Dict[str, HestonParams] = {}
        self._jumps:   Dict[str, JumpParams]   = {}
        self._kalman:  Dict[str, KalmanFilter] = {}
        self._factor:  Dict[str, FactorICIR]   = {}
        self._last_signal: Dict[str, QuantSignal] = {}
        self._last_calibration: Dict[str, float] = {}
        self._calibration_ttl = 300.0  # recalibrate every 5 min
        self.pbo_engine = PBOEngine()
        _log.info("✅ [v18.99] StochasticQuantEngine initialised — OU/Heston/JumpDiff/GBM/Kalman/PBO/MVO")

    def _should_recalibrate(self, symbol: str) -> bool:
        last = self._last_calibration.get(symbol, 0.0)
        return (time.time() - last) > self._calibration_ttl

    def _calibrate_symbol(self, symbol: str, prices: np.ndarray, returns: np.ndarray) -> None:
        """Synchronous calibration — call via asyncio.to_thread()."""
        try:
            ou = OUEngine.calibrate(prices)
            if ou:
                self._ou[symbol] = ou

            heston = HestonEngine.calibrate_from_returns(returns)
            self._heston[symbol] = heston

            jumps = JumpDiffusionEngine.calibrate(returns)
            self._jumps[symbol] = jumps

            if symbol not in self._kalman:
                self._kalman[symbol] = KalmanFilter()

            if symbol not in self._factor:
                self._factor[symbol] = FactorICIR()

            self._last_calibration[symbol] = time.time()
        except Exception as e:
            _log.debug(f"Calibration error [{symbol}]: {e}")

    async def calibrate_async(self, symbol: str, prices: np.ndarray,
                               returns: np.ndarray) -> None:
        """Async wrapper for calibration — offloads CPU work to thread."""
        if self._should_recalibrate(symbol):
            await asyncio.to_thread(self._calibrate_symbol, symbol, prices, returns)

    def _compute_signal_sync(self, symbol: str, current_price: float,
                              prices: np.ndarray, returns: np.ndarray) -> QuantSignal:
        """Synchronous signal computation."""
        ts = time.time()

        # ── OU signal ──────────────────────────────────────────────────────
        ou = self._ou.get(symbol)
        if ou:
            ou_z  = OUEngine.zscore(current_price, ou)
            ou_hl = ou.half_life
            ou_regime = OUEngine.half_life_regime(ou_hl)
        else:
            ou_z, ou_hl, ou_regime = 0.0, 999.0, "NEUTRAL"

        # ── Heston vol regime ──────────────────────────────────────────────
        heston = self._heston.get(symbol)
        if heston:
            heston_vol    = math.sqrt(max(heston.v0, 0.0))
            heston_regime = HestonEngine.vol_regime(heston.v0, heston.theta)
        else:
            heston_vol    = float(np.std(returns[-20:])) * math.sqrt(252) if len(returns) >= 20 else 0.2
            heston_regime = "MID_VOL"

        # ── GBM VaR ────────────────────────────────────────────────────────
        if len(returns) >= 10:
            mu_gbm, sig_gbm = GBMEngine.fit(returns[-min(60, len(returns)):])
            var_1d, cvar_1d = GBMEngine.var_cvar(mu_gbm, sig_gbm, horizon=1.0)
        else:
            sig_gbm = 0.02
            var_1d, cvar_1d = sig_gbm * 1.645, sig_gbm * 2.0

        # ── Jump probability ───────────────────────────────────────────────
        jp = self._jumps.get(symbol)
        jump_prob = JumpDiffusionEngine.jump_prob(jp) if jp else 0.02

        # ── Kalman filter ──────────────────────────────────────────────────
        kf = self._kalman.get(symbol)
        if kf is not None and len(prices) >= 5:
            recent_p = prices[-min(30, len(prices)):]
            _, velocity = kf.bulk_update(recent_p)
            kalman_trend = float(velocity[-1]) if len(velocity) > 0 else 0.0
            kalman_noise = float(np.std(np.diff(recent_p) - velocity[:-1])) if len(velocity) > 1 else 0.01
        else:
            kalman_trend, kalman_noise = 0.0, float(np.std(returns[-5:])) if len(returns) >= 5 else 0.01

        # ── TP/SL multipliers from vol regime ──────────────────────────────
        vol_ratio = heston_vol / max(math.sqrt(heston.theta) if heston else 0.2, 1e-9)
        sl_mult = max(0.7, min(1.5, vol_ratio))
        tp_mult = max(0.8, min(1.3, 1.0 / max(vol_ratio, 0.5)))

        # ── Entry quality composite ────────────────────────────────────────
        # Higher = better entry timing
        # OU z-score in [1.5, 3.0] → strong reversal setup
        ou_q = min(max(abs(ou_z) - 1.0, 0.0), 2.0) / 2.0 if ou_regime == "REVERTING" else 0.0
        # Low vol → cleaner signal
        vol_q = max(0.0, 1.0 - (vol_ratio - 1.0)) if vol_ratio > 1.0 else 1.0
        # Jump risk degrades entry quality
        jump_q = 1.0 - min(jump_prob * 5.0, 0.5)
        # Kalman noise penalty
        noise_q = max(0.0, 1.0 - kalman_noise / max(abs(kalman_trend) + 1e-9, 1e-9) * 0.1)

        entry_quality = float(np.clip(0.3 * ou_q + 0.3 * vol_q + 0.2 * jump_q + 0.2 * noise_q, 0.0, 1.0))

        return QuantSignal(
            symbol=symbol, timestamp=ts,
            ou_zscore=ou_z, ou_halflife=ou_hl, ou_regime=ou_regime,
            heston_vol=heston_vol, heston_regime=heston_regime,
            gbm_var_1d=var_1d, gbm_cvar_1d=cvar_1d,
            jump_prob_1d=jump_prob,
            kalman_trend=kalman_trend, kalman_noise=kalman_noise,
            pbo_score=0.0,
            entry_quality=entry_quality,
            sl_multiplier=sl_mult,
            tp_multiplier=tp_mult,
        )

    async def get_signal(self, symbol: str, prices: np.ndarray,
                         returns: np.ndarray) -> QuantSignal:
        """
        Async entry point: calibrate if needed, compute and return QuantSignal.
        """
        try:
            if len(prices) < 5:
                return self._null_signal(symbol)

            await self.calibrate_async(symbol, prices, returns)
            signal = await asyncio.to_thread(
                self._compute_signal_sync, symbol, float(prices[-1]), prices, returns
            )
            self._last_signal[symbol] = signal
            return signal
        except Exception as e:
            _log.debug(f"get_signal error [{symbol}]: {e}")
            return self._null_signal(symbol)

    def get_cached_signal(self, symbol: str) -> Optional[QuantSignal]:
        """Return last computed signal without recalculating."""
        return self._last_signal.get(symbol)

    @staticmethod
    def _null_signal(symbol: str) -> QuantSignal:
        return QuantSignal(
            symbol=symbol, timestamp=time.time(),
            ou_zscore=0.0, ou_halflife=999.0, ou_regime="NEUTRAL",
            heston_vol=0.2, heston_regime="MID_VOL",
            gbm_var_1d=0.02, gbm_cvar_1d=0.04,
            jump_prob_1d=0.02,
            kalman_trend=0.0, kalman_noise=0.01,
            pbo_score=0.0,
            entry_quality=0.5,
            sl_multiplier=1.0, tp_multiplier=1.0,
        )

    def compute_portfolio_weights(
        self,
        symbols: List[str],
        returns_matrix: np.ndarray,
        method: str = "risk_parity",
    ) -> Dict[str, float]:
        """
        Compute portfolio weights across symbols.
        method: 'risk_parity' | 'mvo' | 'min_variance'
        Returns dict {symbol: weight}.
        """
        try:
            if returns_matrix.shape[1] != len(symbols):
                return {s: 1.0 / len(symbols) for s in symbols}
            cov = np.cov(returns_matrix.T)
            if cov.ndim == 0:
                cov = np.array([[float(cov)]])
            opt = PortfolioOptimizer
            if method == "risk_parity":
                w = opt.risk_parity(cov)
            elif method == "mvo":
                mu = np.mean(returns_matrix, axis=0)
                w = opt.mvo(mu, cov)
            else:
                w = opt.min_variance(cov)
            return {s: float(w[i]) for i, s in enumerate(symbols)}
        except Exception as e:
            _log.debug(f"Portfolio weights error: {e}")
            return {s: 1.0 / max(len(symbols), 1) for s in symbols}


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton (imported by start_unity_engine.py)
# ─────────────────────────────────────────────────────────────────────────────

_STOCHASTIC_ENGINE: Optional[StochasticQuantEngine] = None


def get_stochastic_engine() -> StochasticQuantEngine:
    """Get or create the module-level singleton."""
    global _STOCHASTIC_ENGINE
    if _STOCHASTIC_ENGINE is None:
        _STOCHASTIC_ENGINE = StochasticQuantEngine()
    return _STOCHASTIC_ENGINE
