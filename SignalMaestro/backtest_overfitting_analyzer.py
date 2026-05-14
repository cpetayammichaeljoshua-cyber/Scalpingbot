"""
SignalMaestro.backtest_overfitting_analyzer — v1.0
====================================================

Probability of Backtesting Overfitting (PBO) analyzer for the Unity Engine.

Implements three complementary anti-overfitting metrics used by Gate 8.5d to
penalise proxy-backtest results that exhibit signs of in-sample curve-fitting:

  1. Walk-Forward Ratio (WFR)
     Split the trade sequence into first-half (In-Sample) and second-half
     (Out-of-Sample).  WFR = OOS_Sharpe / IS_Sharpe.  A genuine strategy
     should transfer: WFR ≥ 0.5 is healthy; WFR < 0.3 is suspect; < 0.1
     is near-certain overfit.

  2. Bootstrap PBO Score  (Bailey & Lopez de Prado 2014, simplified)
     Resample the IS trade sequence N times.  For each resample, compute
     whether the resampled Sharpe > OOS Sharpe.  PBO ≈ fraction of
     resamples where IS outperforms OOS.  PBO > 0.55 suggests overfitting.

  3. Deflated Sharpe Ratio (DSR)  (Bailey & Lopez de Prado 2014)
     Adjusts the annualised Sharpe for (a) multiple independent tests
     implicit in the parameter optimisation, (b) non-normality via skewness
     and kurtosis corrections.  A DSR < 0 means the strategy's Sharpe is
     entirely explained by luck at the chosen lookback length.

All three metrics are computed from the raw per-trade R-return sequence
produced by `_vectorized_backtest`.  Requires NumPy ≥ 1.20; degrades
gracefully to NaN / neutral when NumPy is absent or sample size < 20.

Scores are combined into a single `OverfitAssessment` with:
  • `pbo_score`           — 0.0 (no overfit) … 1.0 (certain overfit)
  • `walk_forward_ratio`  — OOS/IS Sharpe (higher is better)
  • `deflated_sharpe`     — adjusted Sharpe (positive = real edge)
  • `quality_penalty`     — [-5.0, 0.0] bias applied to Gate 8.5
  • `label`               — "CLEAN" / "SUSPECT" / "OVERFIT"
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional

try:
    import numpy as np
    _NP_OK = True
except ImportError:
    np = None          # type: ignore[assignment]
    _NP_OK = False


# ─────────────────────────────── constants ────────────────────────────────────

_MIN_TRADES_PBO      = 20    # require at least 20 trades for meaningful PBO
_BOOTSTRAP_REPS      = 500   # bootstrap resamples for PBO estimate
_WFR_SUSPECT         = 0.30  # walk-forward ratio below this → suspect
_WFR_OVERFIT         = 0.10  # walk-forward ratio below this → likely overfit
_PBO_SUSPECT         = 0.55  # bootstrap PBO above this → suspect
_PBO_OVERFIT         = 0.70  # bootstrap PBO above this → likely overfit
_DSR_TESTS           = 16    # assumed independent parameter variations tested
                              # (conservative for a tuned EMA+RSI strategy)


# ─────────────────────────────── data classes ─────────────────────────────────

@dataclass
class OverfitAssessment:
    """Result of the three-metric anti-overfitting analysis."""

    n_trades:           int     = 0
    is_sharpe:          float   = 0.0   # in-sample annualised Sharpe
    oos_sharpe:         float   = 0.0   # out-of-sample annualised Sharpe
    walk_forward_ratio: float   = 1.0   # OOS/IS Sharpe  (≥0.5 good)
    pbo_score:          float   = 0.0   # bootstrap P(IS>OOS)  (<0.55 good)
    deflated_sharpe:    float   = 0.0   # DSR  (>0 = real edge)
    quality_penalty:    float   = 0.0   # [-5, 0] bias for Gate 8.5
    label:              str     = "CLEAN"  # CLEAN / SUSPECT / OVERFIT

    def as_dict(self) -> dict:
        return {
            "n_trades":            self.n_trades,
            "is_sharpe":           round(self.is_sharpe, 3),
            "oos_sharpe":          round(self.oos_sharpe, 3),
            "walk_forward_ratio":  round(self.walk_forward_ratio, 3),
            "pbo_score":           round(self.pbo_score, 3),
            "deflated_sharpe":     round(self.deflated_sharpe, 3),
            "quality_penalty":     round(self.quality_penalty, 2),
            "label":               self.label,
        }


# ─────────────────────────────── helpers ──────────────────────────────────────

def _annualised_sharpe(returns: List[float], trades_per_year: float = 4380.0) -> float:
    """
    Annualised Sharpe from a per-trade R-return list.
    `trades_per_year` default = 4380 assumes 15-min bars, avg 1 trade / 2h.
    Returns 0.0 when std ≈ 0 or insufficient data.
    """
    if len(returns) < 4:
        return 0.0
    n   = len(returns)
    mu  = sum(returns) / n
    var = sum((r - mu) ** 2 for r in returns) / max(1, n - 1)
    std = math.sqrt(var)
    if std < 1e-9:
        return 0.0
    freq_factor = math.sqrt(trades_per_year)
    return (mu / std) * freq_factor


def _annualised_sharpe_np(returns: "np.ndarray", trades_per_year: float = 4380.0) -> float:
    """NumPy-accelerated version (preferred when np is available)."""
    if returns.size < 4:
        return 0.0
    std = float(np.std(returns, ddof=1))
    if std < 1e-9:
        return 0.0
    return float(np.mean(returns) / std) * math.sqrt(trades_per_year)


# ─────────────────────────────── core metrics ─────────────────────────────────

def _walk_forward_ratio(returns: List[float]) -> tuple[float, float, float]:
    """
    Split returns at midpoint → IS (first half) + OOS (second half).
    Returns (wfr, is_sharpe, oos_sharpe).
    """
    n = len(returns)
    mid = n // 2
    is_r  = returns[:mid]
    oos_r = returns[mid:]
    if not is_r or not oos_r:
        return 1.0, 0.0, 0.0
    is_sh  = _annualised_sharpe(is_r)
    oos_sh = _annualised_sharpe(oos_r)
    if abs(is_sh) < 1e-9:
        wfr = 1.0  # IS flat → no overfitting signal (cold strategy)
    else:
        wfr = oos_sh / is_sh
    return float(wfr), float(is_sh), float(oos_sh)


def _bootstrap_pbo(returns: List[float], n_reps: int = _BOOTSTRAP_REPS) -> float:
    """
    Simplified CSCV bootstrap PBO estimate for a single strategy.

    Algorithm:
      1. Split into IS and OOS halves.
      2. Resample the IS half n_reps times (with replacement).
      3. Count fraction of resamples where resampled IS Sharpe > OOS Sharpe.
      4. PBO ≈ that fraction.

    A random strategy (no real edge) produces PBO ≈ 0.50 by symmetry.
    A genuine transferable strategy produces PBO < 0.45 (IS ≈ OOS).
    A curve-fitted strategy produces PBO → 1.0 (IS always >> OOS).
    """
    n = len(returns)
    if n < _MIN_TRADES_PBO:
        return 0.0
    mid = n // 2
    is_r  = returns[:mid]
    oos_r = returns[mid:]

    oos_sh  = _annualised_sharpe(oos_r)
    n_is    = len(is_r)
    count_above = 0

    if _NP_OK:
        is_arr  = np.asarray(is_r, dtype=np.float64)
        oos_arr = np.asarray(oos_r, dtype=np.float64)
        oos_sh  = _annualised_sharpe_np(oos_arr)
        for _ in range(n_reps):
            idx      = np.random.randint(0, n_is, n_is)
            resamp   = is_arr[idx]
            boot_sh  = _annualised_sharpe_np(resamp)
            if boot_sh > oos_sh:
                count_above += 1
    else:
        for _ in range(n_reps):
            resamp  = [random.choice(is_r) for _ in range(n_is)]
            boot_sh = _annualised_sharpe(resamp)
            if boot_sh > oos_sh:
                count_above += 1

    return count_above / n_reps


def _deflated_sharpe(
    returns: List[float],
    n_tests: int = _DSR_TESTS,
    trades_per_year: float = 4380.0,
) -> float:
    """
    Deflated Sharpe Ratio (DSR) per Bailey & Lopez de Prado (2014).

    DSR = SR × √(1 − γ₃·SR/√T + (γ₄−1)/4·SR²/T)
    where γ₃=skewness, γ₄=kurtosis, T=observations, SR=observed Sharpe.

    Then deflate for multiple testing:
      SR* = SR_target = √Var(max SR_i) over n_tests independent trials
           ≈ √((1−γ_E)·z²_max + γ_E·z_max)  where z_max = E[max of n_tests N(0,1)]
           simplified: SR* = √(2·ln(n_tests)) (conservative upper bound)

    DSR = Φ((DSR_adjusted − SR*) / 1) where Φ is the normal CDF.
    We return the pre-CDF value (adjusted_SR − SR*) so DSR > 0 = genuine edge.
    """
    n = len(returns)
    if n < 20:
        return 0.0

    if _NP_OK:
        arr  = np.asarray(returns, dtype=np.float64)
        mu   = float(np.mean(arr))
        std  = float(np.std(arr, ddof=1))
        if std < 1e-9:
            return 0.0
        skew = float(np.mean(((arr - mu) / std) ** 3))
        kurt = float(np.mean(((arr - mu) / std) ** 4))
    else:
        mu  = sum(returns) / n
        var = sum((r - mu) ** 2 for r in returns) / max(1, n - 1)
        std = math.sqrt(var)
        if std < 1e-9:
            return 0.0
        skew = sum(((r - mu) / std) ** 3 for r in returns) / n
        kurt = sum(((r - mu) / std) ** 4 for r in returns) / n

    sr_obs = (mu / std) * math.sqrt(trades_per_year)

    # Non-normality adjustment factor (from BLP Eq. 1)
    adj = math.sqrt(1.0 - skew * sr_obs / math.sqrt(n) +
                    (kurt - 1.0) / 4.0 * sr_obs ** 2 / n)
    adj = max(0.01, adj)       # prevent negative under heavy kurtosis
    sr_adjusted = sr_obs * adj

    # SR_target: expected max Sharpe from n_tests independent random strategies
    # Simplified conservative bound: √(2·ln(n_tests))
    sr_target = math.sqrt(2.0 * math.log(max(2, n_tests))) if n_tests > 1 else 0.0

    return sr_adjusted - sr_target   # >0 means genuine edge above noise floor


# ─────────────────────────────── main API ─────────────────────────────────────

class BacktestOverfittingAnalyzer:
    """
    Stateless helper — call assess(returns) after a proxy backtest run.

    Usage::

        from SignalMaestro.backtest_overfitting_analyzer import BacktestOverfittingAnalyzer
        bpoa = BacktestOverfittingAnalyzer()
        assessment = bpoa.assess(r_returns_list)
        quality_score += assessment.quality_penalty   # apply to Gate 8.5

    Quality penalty scale:
      CLEAN   (WFR ≥ 0.50, PBO < 0.55, DSR > 0)   →  0.0  (no penalty)
      SUSPECT (WFR 0.10-0.50 OR PBO 0.55-0.70)     → -3.0  (soft warning)
      OVERFIT (WFR < 0.10  OR PBO > 0.70 OR DSR<0) → -5.0  (strong warning)
    """

    def assess(
        self,
        r_returns: List[float],
        n_tests:   int   = _DSR_TESTS,
        tpy:       float = 4380.0,
    ) -> OverfitAssessment:
        """
        Compute the three-metric overfitting assessment from a per-trade
        R-return list (positive = win in R, negative = loss in R).

        Returns a neutral CLEAN assessment with no penalty when the sample
        is too small (< 20 trades) — protects against false positives on
        cold-start results.
        """
        n = len(r_returns)
        result = OverfitAssessment(n_trades=n)

        if n < _MIN_TRADES_PBO:
            return result   # too few trades → neutral

        # 1. Walk-forward ratio
        wfr, is_sh, oos_sh = _walk_forward_ratio(r_returns)
        result.walk_forward_ratio = wfr
        result.is_sharpe          = is_sh
        result.oos_sharpe         = oos_sh

        # 2. Bootstrap PBO
        pbo = _bootstrap_pbo(r_returns)
        result.pbo_score = pbo

        # 3. Deflated Sharpe
        dsr = _deflated_sharpe(r_returns, n_tests=n_tests, trades_per_year=tpy)
        result.deflated_sharpe = dsr

        # 4. Classify + assign penalty
        is_overfit = (wfr < _WFR_OVERFIT) or (pbo > _PBO_OVERFIT) or (dsr < -1.0)
        is_suspect = (not is_overfit) and (
            (wfr < _WFR_SUSPECT) or (pbo > _PBO_SUSPECT) or (dsr < 0.0)
        )

        if is_overfit:
            result.label          = "OVERFIT"
            result.quality_penalty = -5.0
        elif is_suspect:
            result.label          = "SUSPECT"
            result.quality_penalty = -3.0
        else:
            result.label          = "CLEAN"
            result.quality_penalty = 0.0

        return result


# Module-level singleton — import once, reuse everywhere
_default_analyzer = BacktestOverfittingAnalyzer()

def assess_overfitting(r_returns: List[float]) -> OverfitAssessment:
    """Convenience function — uses the module-level singleton."""
    return _default_analyzer.assess(r_returns)
