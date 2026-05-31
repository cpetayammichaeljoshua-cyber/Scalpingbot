"""
SignalMaestro.backtest_overfitting_analyzer — v2.0 (Unity Engine v20.0)
=======================================================================

Probability of Backtesting Overfitting (PBO) analyzer + 4-Step Strategy
Validation Framework for the Unity Engine.

FOUR-STEP STRATEGY DEVELOPMENT (from image — Trading Strategy Development Steps):
  Step 1 — In-Sample Excellence
     Verify the strategy has genuine positive-EV in the training window.
     Metrics: IS Sharpe > 0, IS WR > 35%, IS PF > 1.2, IS EV > 0.

  Step 2 — In-Sample Permutation Test
     Randomly permute the IS return sequence N times.  Compute the fraction
     of permuted strategies that beat the observed IS Sharpe.  If too many
     permuted strategies beat the real one, the IS edge is luck-derived.
     p-value < 0.05 → genuine IS edge (real strategy beats 95%+ of random).

  Step 3 — Walk-Forward Test (OOS Validation)
     Split the trade sequence into first-half (In-Sample) and second-half
     (Out-of-Sample).  WFR = OOS_Sharpe / IS_Sharpe.  A genuine strategy
     should transfer: WFR ≥ 0.5 is healthy; WFR < 0.3 is suspect; < 0.1
     is near-certain overfit.

  Step 4 — Walk-Forward Permutation Test
     Apply the permutation test to the OOS sequence.  If OOS permuted
     strategies outperform the real OOS strategy, the OOS result is also
     luck-based.  p-value < 0.10 → genuine OOS edge.

ORIGINAL THREE METRICS (retained and enhanced):
  • Walk-Forward Ratio (WFR)  — OOS/IS Sharpe
  • Bootstrap PBO Score       — Bailey & Lopez de Prado 2014 (1000 reps)
  • Deflated Sharpe Ratio     — Adjusted for non-normality + multiple testing

All metrics feed a single `StrategyValidationResult` that gates Gate 8.5d
with a quality penalty of [-7.0, 0.0].  Steps 1–4 all pass → CLEAN (0 pts).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

try:
    import numpy as np
    _NP_OK = True
except ImportError:
    np = None          # type: ignore[assignment]
    _NP_OK = False


# ──────────────────────────────── constants ───────────────────────────────────

_MIN_TRADES_PBO         = 20     # require at least 20 trades for meaningful PBO
_BOOTSTRAP_REPS         = 1000   # v18.76: 1000 bootstrap resamples
_PERMUTATION_REPS       = 1000   # v20.0: 1000 permutation test reps per step
_WFR_SUSPECT            = 0.30   # walk-forward ratio below this → suspect
_WFR_OVERFIT            = 0.10   # walk-forward ratio below this → likely overfit
_PBO_SUSPECT            = 0.55   # bootstrap PBO above this → suspect
_PBO_OVERFIT            = 0.70   # bootstrap PBO above this → likely overfit
_DSR_TESTS              = 16     # assumed independent parameter variations tested
_IS_PVAL_THRESHOLD      = 0.05   # Step 2: IS permutation p-value threshold
_OOS_PVAL_THRESHOLD     = 0.10   # Step 4: WF permutation p-value threshold
_IS_SHARPE_MIN          = 0.0    # Step 1: IS Sharpe must be positive
_IS_WR_MIN              = 0.35   # Step 1: IS win rate floor (35%)
_IS_PF_MIN              = 1.2    # Step 1: IS profit factor floor
_WFR_CLEAN              = 0.55   # Clean WFR threshold [v18.76: 0.50→0.55]


# ───────────────────────────── data classes ───────────────────────────────────

@dataclass
class OverfitAssessment:
    """Result of the three-metric anti-overfitting analysis (original API, preserved)."""

    n_trades:           int     = 0
    is_sharpe:          float   = 0.0
    oos_sharpe:         float   = 0.0
    walk_forward_ratio: float   = 1.0
    pbo_score:          float   = 0.0
    deflated_sharpe:    float   = 0.0
    quality_penalty:    float   = 0.0
    label:              str     = "CLEAN"

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


@dataclass
class StrategyValidationResult:
    """
    v20.0 — Full 4-step strategy validation result.

    Integrates the original 3-metric analysis with the complete
    institutional 4-step framework (IS Excellence → IS Permutation
    → Walk-Forward → WF Permutation).
    """
    n_trades:            int   = 0
    # ── Step 1: In-Sample Excellence ──────────────────────────────────────────
    step1_pass:          bool  = False
    is_sharpe:           float = 0.0
    is_win_rate:         float = 0.0
    is_profit_factor:    float = 1.0
    is_ev:               float = 0.0
    # ── Step 2: In-Sample Permutation Test ────────────────────────────────────
    step2_pass:          bool  = False
    is_pval:             float = 1.0   # fraction of permuted IS strategies beating observed IS
    # ── Step 3: Walk-Forward Test ─────────────────────────────────────────────
    step3_pass:          bool  = False
    walk_forward_ratio:  float = 1.0
    oos_sharpe:          float = 0.0
    # ── Step 4: Walk-Forward Permutation Test ─────────────────────────────────
    step4_pass:          bool  = False
    oos_pval:            float = 1.0   # fraction of permuted OOS strategies beating observed OOS
    # ── Original 3-metric fields (backwards compat) ───────────────────────────
    pbo_score:           float = 0.0
    deflated_sharpe:     float = 0.0
    quality_penalty:     float = 0.0
    label:               str   = "CLEAN"   # CLEAN / SUSPECT / OVERFIT
    steps_passed:        int   = 0         # 0–4

    def as_dict(self) -> dict:
        return {
            "n_trades":           self.n_trades,
            "steps_passed":       self.steps_passed,
            "label":              self.label,
            "quality_penalty":    round(self.quality_penalty, 2),
            # Step 1
            "step1_is_excellence": self.step1_pass,
            "is_sharpe":          round(self.is_sharpe, 3),
            "is_win_rate":        round(self.is_win_rate, 3),
            "is_profit_factor":   round(self.is_profit_factor, 3),
            "is_ev":              round(self.is_ev, 4),
            # Step 2
            "step2_is_permutation": self.step2_pass,
            "is_pval":            round(self.is_pval, 3),
            # Step 3
            "step3_walk_forward": self.step3_pass,
            "walk_forward_ratio": round(self.walk_forward_ratio, 3),
            "oos_sharpe":         round(self.oos_sharpe, 3),
            # Step 4
            "step4_oos_permutation": self.step4_pass,
            "oos_pval":           round(self.oos_pval, 3),
            # Original
            "pbo_score":          round(self.pbo_score, 3),
            "deflated_sharpe":    round(self.deflated_sharpe, 3),
        }

    def to_overfit_assessment(self) -> OverfitAssessment:
        """Convert to legacy OverfitAssessment for backwards compatibility."""
        return OverfitAssessment(
            n_trades=self.n_trades,
            is_sharpe=self.is_sharpe,
            oos_sharpe=self.oos_sharpe,
            walk_forward_ratio=self.walk_forward_ratio,
            pbo_score=self.pbo_score,
            deflated_sharpe=self.deflated_sharpe,
            quality_penalty=self.quality_penalty,
            label=self.label,
        )


# ──────────────────────────── helper functions ────────────────────────────────

def _annualised_sharpe(returns: List[float], trades_per_year: float = 4380.0) -> float:
    """Annualised Sharpe from a per-trade R-return list."""
    if len(returns) < 4:
        return 0.0
    n   = len(returns)
    mu  = sum(returns) / n
    var = sum((r - mu) ** 2 for r in returns) / max(1, n - 1)
    std = math.sqrt(var)
    if std < 1e-9:
        return 0.0
    return (mu / std) * math.sqrt(trades_per_year)


def _annualised_sharpe_np(returns: "np.ndarray", trades_per_year: float = 4380.0) -> float:
    """NumPy-accelerated version (preferred when np is available)."""
    if returns.size < 4:
        return 0.0
    std = float(np.std(returns, ddof=1))
    if std < 1e-9:
        return 0.0
    return float(np.mean(returns) / std) * math.sqrt(trades_per_year)


def _win_rate(returns: List[float]) -> float:
    """Fraction of positive returns (wins)."""
    if not returns:
        return 0.0
    wins = sum(1 for r in returns if r > 0)
    return wins / len(returns)


def _profit_factor(returns: List[float]) -> float:
    """Gross profit / gross loss. Returns 0 when no losses exist."""
    gross_win  = sum(r for r in returns if r > 0)
    gross_loss = abs(sum(r for r in returns if r < 0))
    if gross_loss < 1e-9:
        return 10.0   # all winners → cap at 10
    return gross_win / gross_loss


def _ev(returns: List[float]) -> float:
    """Expected value per trade (mean return)."""
    if not returns:
        return 0.0
    return sum(returns) / len(returns)


# ───────────────────────────── core metrics ───────────────────────────────────

def _walk_forward_ratio(returns: List[float]) -> Tuple[float, float, float]:
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
        wfr = 1.0
    else:
        wfr = oos_sh / is_sh
    return float(wfr), float(is_sh), float(oos_sh)


def _permutation_pvalue(returns: List[float], n_reps: int = _PERMUTATION_REPS) -> float:
    """
    Permutation test p-value.

    Computes the fraction of randomly permuted return sequences whose
    Sharpe Ratio exceeds the observed Sharpe.  A low p-value (e.g. < 0.05)
    means the observed strategy is genuinely better than random — its edge
    is not explained by lucky ordering.

    Args:
        returns: per-trade R-returns (observed sequence, un-permuted)
        n_reps:  number of random permutations to evaluate

    Returns:
        p-value ∈ [0, 1] — fraction of permutations beating observed Sharpe.
        LOW p-value → genuine edge.  HIGH p-value → likely luck.
    """
    if len(returns) < 10:
        return 0.5   # neutral when insufficient data
    obs_sharpe = _annualised_sharpe(returns)
    count_beat = 0

    if _NP_OK:
        arr = np.asarray(returns, dtype=np.float64)
        for _ in range(n_reps):
            perm = arr.copy()
            np.random.shuffle(perm)
            perm_sh = _annualised_sharpe_np(perm)
            if perm_sh > obs_sharpe:
                count_beat += 1
    else:
        r_list = list(returns)
        for _ in range(n_reps):
            perm = r_list[:]
            random.shuffle(perm)
            perm_sh = _annualised_sharpe(perm)
            if perm_sh > obs_sharpe:
                count_beat += 1

    return count_beat / n_reps


def _bootstrap_pbo(returns: List[float], n_reps: int = _BOOTSTRAP_REPS) -> float:
    """
    Simplified CSCV bootstrap PBO estimate for a single strategy.
    Bailey & Lopez de Prado (2014).

    PBO ≈ fraction of IS-bootstrap resamples whose Sharpe > OOS Sharpe.
    HIGH PBO → curve-fitted (bad).  LOW PBO → transferable (good).
    """
    n = len(returns)
    if n < _MIN_TRADES_PBO:
        return 0.0
    mid = n // 2
    is_r  = returns[:mid]
    oos_r = returns[mid:]

    oos_sh = _annualised_sharpe(oos_r)
    n_is   = len(is_r)
    count_above = 0

    if _NP_OK:
        is_arr  = np.asarray(is_r,  dtype=np.float64)
        oos_arr = np.asarray(oos_r, dtype=np.float64)
        oos_sh  = _annualised_sharpe_np(oos_arr)
        for _ in range(n_reps):
            idx     = np.random.randint(0, n_is, n_is)
            resamp  = is_arr[idx]
            boot_sh = _annualised_sharpe_np(resamp)
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
    n_tests: int   = _DSR_TESTS,
    trades_per_year: float = 4380.0,
) -> float:
    """
    Deflated Sharpe Ratio (DSR) per Bailey & Lopez de Prado (2014).
    Returns pre-CDF value: DSR > 0 = genuine edge above noise floor.
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
    adj = math.sqrt(max(0.0001, 1.0 - skew * sr_obs / math.sqrt(n) +
                        (kurt - 1.0) / 4.0 * sr_obs ** 2 / n))
    adj = max(0.01, adj)
    sr_adjusted = sr_obs * adj
    sr_target = math.sqrt(2.0 * math.log(max(2, n_tests))) if n_tests > 1 else 0.0
    return sr_adjusted - sr_target


# ─────────────────────────── 4-STEP FRAMEWORK ────────────────────────────────

def _step1_in_sample_excellence(is_returns: List[float]) -> Tuple[bool, float, float, float, float]:
    """
    Step 1: In-Sample Excellence.
    Returns (pass, is_sharpe, is_win_rate, is_profit_factor, is_ev).
    """
    if len(is_returns) < 10:
        return True, 0.0, 0.5, 1.0, 0.0   # neutral pass on cold-start
    sh = _annualised_sharpe(is_returns)
    wr = _win_rate(is_returns)
    pf = _profit_factor(is_returns)
    ev = _ev(is_returns)
    passed = (sh > _IS_SHARPE_MIN) and (wr >= _IS_WR_MIN) and (pf >= _IS_PF_MIN) and (ev > 0)
    return passed, sh, wr, pf, ev


def _step2_is_permutation(is_returns: List[float], n_reps: int = _PERMUTATION_REPS) -> Tuple[bool, float]:
    """
    Step 2: In-Sample Permutation Test.
    Returns (pass, p_value). Low p-value → genuine IS edge.
    """
    if len(is_returns) < 10:
        return True, 0.0   # neutral pass on cold-start
    pval = _permutation_pvalue(is_returns, n_reps=n_reps)
    passed = pval < _IS_PVAL_THRESHOLD
    return passed, pval


def _step3_walk_forward(returns: List[float]) -> Tuple[bool, float, float, float]:
    """
    Step 3: Walk-Forward Test (OOS Validation).
    Returns (pass, wfr, is_sharpe, oos_sharpe).
    """
    if len(returns) < 20:
        return True, 1.0, 0.0, 0.0   # neutral pass on cold-start
    wfr, is_sh, oos_sh = _walk_forward_ratio(returns)
    passed = wfr >= _WFR_SUSPECT   # 0.30 is the minimum for a non-suspect strategy
    return passed, wfr, is_sh, oos_sh


def _step4_wf_permutation(returns: List[float], n_reps: int = _PERMUTATION_REPS) -> Tuple[bool, float]:
    """
    Step 4: Walk-Forward Permutation Test (OOS permutation test).
    Tests whether the OOS returns have genuine edge vs random permutations.
    Returns (pass, p_value). Low p-value → genuine OOS edge.
    """
    n = len(returns)
    if n < 20:
        return True, 0.0   # neutral pass on cold-start
    oos_returns = returns[n // 2:]
    if len(oos_returns) < 10:
        return True, 0.0
    pval = _permutation_pvalue(oos_returns, n_reps=n_reps)
    passed = pval < _OOS_PVAL_THRESHOLD
    return passed, pval


# ──────────────────────────── main analyzers ─────────────────────────────────

class StrategyValidator:
    """
    v20.0 — Complete 4-step institutional strategy validation framework.

    Runs all four validation steps and produces a `StrategyValidationResult`
    with per-step pass/fail and the unified quality penalty.

    Quality penalty scale:
      All 4 steps pass   → CLEAN    →  0.0 pts
      3 of 4 pass        → SUSPECT  → -3.0 pts
      ≤ 2 of 4 pass      → OVERFIT  → -7.0 pts

    Usage::
        validator = StrategyValidator()
        result = validator.validate(r_returns_list)
        quality_score += result.quality_penalty
    """

    def validate(
        self,
        r_returns:  List[float],
        n_tests:    int   = _DSR_TESTS,
        tpy:        float = 4380.0,
        n_perms:    int   = _PERMUTATION_REPS,
    ) -> StrategyValidationResult:
        """
        Run all 4 validation steps.

        Args:
            r_returns: per-trade R-returns (positive=win, negative=loss)
            n_tests:   number of independent strategy tests for DSR correction
            tpy:       trades per year for Sharpe annualisation
            n_perms:   permutation test repetitions (default 1000)

        Returns:
            StrategyValidationResult with all step results and quality penalty.
        """
        n = len(r_returns)
        result = StrategyValidationResult(n_trades=n)

        if n < 10:
            result.step1_pass = result.step2_pass = True
            result.step3_pass = result.step4_pass = True
            result.steps_passed = 4
            result.label = "CLEAN"
            return result

        # IS/OOS split
        mid = n // 2
        is_returns  = r_returns[:mid]
        oos_returns = r_returns[mid:]

        # ── Step 1: In-Sample Excellence ──────────────────────────────────────
        s1_pass, is_sh, is_wr, is_pf, is_ev = _step1_in_sample_excellence(is_returns)
        result.step1_pass       = s1_pass
        result.is_sharpe        = is_sh
        result.is_win_rate      = is_wr
        result.is_profit_factor = is_pf
        result.is_ev            = is_ev

        # ── Step 2: In-Sample Permutation Test ────────────────────────────────
        s2_pass, is_pval = _step2_is_permutation(is_returns, n_reps=n_perms)
        result.step2_pass = s2_pass
        result.is_pval    = is_pval

        # ── Step 3: Walk-Forward Test ─────────────────────────────────────────
        s3_pass, wfr, _, oos_sh = _step3_walk_forward(r_returns)
        result.step3_pass       = s3_pass
        result.walk_forward_ratio = wfr
        result.oos_sharpe       = oos_sh

        # ── Step 4: Walk-Forward Permutation Test ─────────────────────────────
        s4_pass, oos_pval = _step4_wf_permutation(r_returns, n_reps=n_perms)
        result.step4_pass = s4_pass
        result.oos_pval   = oos_pval

        # ── Original 3-metric metrics (retained for backwards compat) ─────────
        result.pbo_score      = _bootstrap_pbo(r_returns)
        result.deflated_sharpe = _deflated_sharpe(r_returns, n_tests=n_tests, trades_per_year=tpy)

        # ── Aggregate scoring ─────────────────────────────────────────────────
        steps_passed = sum([s1_pass, s2_pass, s3_pass, s4_pass])
        result.steps_passed = steps_passed

        if steps_passed == 4:
            result.label          = "CLEAN"
            result.quality_penalty = 0.0
        elif steps_passed == 3:
            result.label          = "SUSPECT"
            result.quality_penalty = -3.0
        elif steps_passed == 2:
            result.label          = "SUSPECT"
            result.quality_penalty = -5.0
        else:
            result.label          = "OVERFIT"
            result.quality_penalty = -7.0

        return result


class BacktestOverfittingAnalyzer:
    """
    Stateless helper — call assess(returns) after a proxy backtest run.
    Backwards-compatible with existing Gate 8.5d pipeline.
    Internally delegates to StrategyValidator (v20.0 4-step framework).

    Quality penalty scale:
      CLEAN   (all 4 steps pass)             →  0.0  (no penalty)
      SUSPECT (3 steps pass)                 → -3.0  (soft warning)
      SUSPECT (2 steps pass)                 → -5.0  (strong warning)
      OVERFIT (≤ 1 step passes)              → -7.0  (strong veto)
    """

    def __init__(self):
        self._validator = StrategyValidator()

    def assess(
        self,
        r_returns: List[float],
        n_tests:   int   = _DSR_TESTS,
        tpy:       float = 4380.0,
    ) -> OverfitAssessment:
        """
        Compute the anti-overfitting assessment from a per-trade R-return list.
        Returns a neutral CLEAN assessment with no penalty when sample < 20.
        Compatible with existing Gate 8.5d code (returns OverfitAssessment).
        """
        n = len(r_returns)
        if n < _MIN_TRADES_PBO:
            return OverfitAssessment(n_trades=n)

        svr = self._validator.validate(r_returns, n_tests=n_tests, tpy=tpy)
        return svr.to_overfit_assessment()

    def assess_full(
        self,
        r_returns: List[float],
        n_tests:   int   = _DSR_TESTS,
        tpy:       float = 4380.0,
    ) -> StrategyValidationResult:
        """
        v20.0 — Full 4-step validation. Returns StrategyValidationResult.
        Use this for richer step-by-step results and logging.
        """
        return self._validator.validate(r_returns, n_tests=n_tests, tpy=tpy)


# Module-level singletons — import once, reuse everywhere
_default_analyzer  = BacktestOverfittingAnalyzer()
_default_validator = StrategyValidator()


def assess_overfitting(r_returns: List[float]) -> OverfitAssessment:
    """Convenience function — uses the module-level singleton (backwards compat)."""
    return _default_analyzer.assess(r_returns)


def validate_strategy(r_returns: List[float]) -> StrategyValidationResult:
    """
    v20.0 convenience function — full 4-step institutional validation.
    Returns StrategyValidationResult with per-step pass/fail and penalty.
    """
    return _default_validator.validate(r_returns)
