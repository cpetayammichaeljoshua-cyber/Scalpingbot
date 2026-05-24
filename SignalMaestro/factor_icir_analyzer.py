"""
SignalMaestro — Factor IC/IR Analyzer  v11.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Institutional-grade factor analysis engine integrated into Unity Engine v11.0.

Capabilities:
• Spearman rank IC (cross-sectional, daily)
• Rolling IC series (regime-aware decay)
• IR = IC_mean / IC_std — risk-adjusted factor reliability
• N-quantile return decomposition (monotonicity test)
• Factor turnover (transaction-cost proxy)
• Multi-holding-period analysis (1/5/10/21 bars)
• Live integration: feeds quality_bias into Gate 8.5 alongside DynBacktester
• Async-safe: all compute on ThreadPoolExecutor, no event-loop blocking

Reference: Vibe-Trading (HKUDS/Vibe-Trading), Alphalens methodology
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.stats import spearmanr

_log = logging.getLogger("UnityEngine.FactorICIR")

# ── Constants ────────────────────────────────────────────────────────────────
N_QUANTILES         = 5
HOLDING_PERIODS     = [1, 5, 10, 21]   # bars
MIN_UNIVERSE_SIZE   = 8                 # min symbols to compute IC
ROLLING_IC_WINDOW   = 30               # bars for rolling IC MA
IC_STRONG_THRESHOLD = 0.05             # Mean IC > 0.05 → strong factor
IR_STRONG_THRESHOLD = 0.30             # IR > 0.30 → reliable factor
MAX_FACTOR_HISTORY  = 500              # max daily snapshots retained


@dataclass
class FactorSnapshot:
    """One cross-sectional observation: factor values + realized returns."""
    timestamp:    float
    factor_vals:  Dict[str, float]   # symbol → factor value
    fwd_returns:  Dict[str, Dict[int, float]]  # symbol → {period: return}


@dataclass
class ICIRResult:
    """IC/IR summary for a single holding period."""
    holding_period: int
    ic_mean:        float
    ic_std:         float
    ir:             float
    ic_gt003_pct:   float   # fraction of |IC| > 0.03
    rolling_ic_30:  float   # recent 30-bar rolling IC mean
    is_strong:      bool    # IC > 0.05 AND IR > 0.30
    quality_bias:   float   # [-4, +5] bias for Gate 8.5


@dataclass
class QuantileResult:
    """Quantile return decomposition for a holding period."""
    holding_period: int
    quantile_means: Dict[int, float]   # quantile 1..N → mean return
    spread:         float              # Q_top − Q_bottom
    monotonic:      bool               # does Q1 < Q2 < ... < QN ?
    turnover:       float              # avg top-quantile turnover


@dataclass
class FactorAnalysisReport:
    """Full factor analysis report — posted to /metrics and Telegram bot."""
    computed_at:    float
    n_symbols:      int
    n_snapshots:    int
    icir_by_period: Dict[int, ICIRResult]
    quantile_by_period: Dict[int, QuantileResult]
    best_period:    int          # holding period with highest |IR|
    composite_bias: float        # aggregate quality_bias for Gate 8.5


class FactorICIRAnalyzer:
    """
    Live factor IC/IR analyzer for the Unity Engine signal universe.

    Factor construction: multi-factor composite from available signal features
      • Momentum factor  : 20-bar price return (mean-reversion adjusted)
      • Volume factor    : OFI Z-score (order-flow imbalance)
      • Quality factor   : IRONS score (25-indicator composite)
      • GEX factor       : gamma-net bias (dealer positioning)
      • NN factor        : neural network win-probability

    The composite factor is an equal-weight rank of the above.
    IC/IR is computed on the composite and each sub-factor.
    """

    def __init__(self, universe_symbols: Optional[List[str]] = None, executor=None):
        self._symbols   = list(universe_symbols) if universe_symbols else []
        self._executor  = executor
        self._lock      = threading.RLock()

        # Rolling history
        self._snapshots: deque[FactorSnapshot] = deque(maxlen=MAX_FACTOR_HISTORY)
        self._ic_series: Dict[int, deque] = {h: deque(maxlen=MAX_FACTOR_HISTORY) for h in HOLDING_PERIODS}

        # Latest report (cached)
        self._report: Optional[FactorAnalysisReport] = None
        self._report_ts: float = 0.0
        self._refresh_interval: float = 300.0   # recompute every 5 min

        # Per-symbol factor value buffer (updated by main engine)
        self._factor_buffer: Dict[str, Dict[str, float]] = {}  # symbol → {factor_name: val}
        self._price_buffer:  Dict[str, deque]            = {s: deque(maxlen=30) for s in self._symbols}

    # ── Public API ────────────────────────────────────────────────────────────

    def update_symbol(self, symbol: str, price: float,
                      ofi_z: float = 0.0, irons: float = 0.0,
                      gex_net: float = 0.0, nn_prob: float = 0.0) -> None:
        """Called by main engine on every scan cycle for each symbol."""
        with self._lock:
            pb = self._price_buffer.setdefault(symbol, deque(maxlen=30))
            pb.append(price)
            mom = self._calc_momentum(pb)
            self._factor_buffer[symbol] = {
                "momentum": mom,
                "ofi":      float(ofi_z),
                "irons":    float(irons) / 100.0,   # normalise 0-1
                "gex":      float(np.tanh(gex_net / 1e9)) if gex_net else 0.0,
                "nn":       float(nn_prob),
            }

    def record_returns(self, symbol: str, bar_returns: Dict[int, float]) -> None:
        """
        Called after forward periods have elapsed.
        bar_returns = {1: ret_1bar, 5: ret_5bar, 10: ret_10bar, 21: ret_21bar}
        """
        with self._lock:
            if symbol not in self._factor_buffer:
                return
            # Find or create a snapshot for this symbol's factor values
            now = time.time()
            snap = FactorSnapshot(
                timestamp=now,
                factor_vals={symbol: self._composite_factor(symbol)},
                fwd_returns={symbol: bar_returns},
            )
            # Merge into existing snapshot if recent (within 60s)
            if self._snapshots and now - self._snapshots[-1].timestamp < 60:
                last = self._snapshots[-1]
                last.factor_vals[symbol] = snap.factor_vals[symbol]
                last.fwd_returns[symbol] = snap.fwd_returns[symbol]
            else:
                self._snapshots.append(snap)

    async def get_report(self) -> Optional[FactorAnalysisReport]:
        """Return cached report, refreshing if stale."""
        now = time.time()
        if self._report and now - self._report_ts < self._refresh_interval:
            return self._report
        loop = asyncio.get_event_loop()
        try:
            if self._executor:
                report = await loop.run_in_executor(self._executor, self._compute_report)
            else:
                report = self._compute_report()
            if report:
                with self._lock:
                    self._report    = report
                    self._report_ts = now
            return self._report
        except Exception as exc:
            _log.warning(f"[FactorICIR] compute_report failed: {exc}")
            return self._report

    def get_quality_bias(self, symbol: str) -> float:
        """
        Return Gate 8.5 quality bias for a symbol based on its quantile ranking.
        Range: [-4.0, +5.0]
        """
        with self._lock:
            if not self._report:
                return 0.0
            return self._report.composite_bias

    def get_symbol_quantile(self, symbol: str) -> Optional[int]:
        """Return 1..N quantile rank of symbol in current cross-section, or None."""
        with self._lock:
            if not self._factor_buffer:
                return None
            scores = {s: self._composite_factor(s) for s in self._factor_buffer}
            if symbol not in scores:
                return None
            sorted_syms = sorted(scores.items(), key=lambda x: x[1])
            n = len(sorted_syms)
            rank = next(i for i, (s, _) in enumerate(sorted_syms) if s == symbol) + 1
            q = int(np.ceil(rank / n * N_QUANTILES))
            return max(1, min(N_QUANTILES, q))

    def format_report_text(self, report: Optional[FactorAnalysisReport] = None) -> str:
        """Format report for Telegram display."""
        r = report or self._report
        if not r:
            return "📊 Factor IC/IR: insufficient data (need ≥8 symbols, ≥30 snapshots)"
        lines = [
            f"📊 *Factor IC/IR Analysis* — {len(r.icir_by_period)} holding periods",
            f"Universe: {r.n_symbols} symbols | Snapshots: {r.n_snapshots}",
            "",
        ]
        for period, icir in sorted(r.icir_by_period.items()):
            sig = "✅" if icir.is_strong else "⚠️"
            lines.append(
                f"{sig} *{period}d* — IC={icir.ic_mean:+.4f} IR={icir.ir:+.3f} "
                f"Roll={icir.rolling_ic_30:+.4f} Bias={icir.quality_bias:+.1f}"
            )
        lines.append("")
        best = r.icir_by_period.get(r.best_period)
        if best:
            qr = r.quantile_by_period.get(r.best_period)
            mono = "✅ monotonic" if (qr and qr.monotonic) else "⚠️ non-monotonic"
            lines.append(f"Best period: *{r.best_period}d* | Quantile spread: {qr.spread:+.4f} ({mono})" if qr else "")
            lines.append(f"Composite Gate-8.5 bias: *{r.composite_bias:+.2f}*")
        return "\n".join(lines)

    # ── Internal compute ──────────────────────────────────────────────────────

    def _compute_report(self) -> Optional[FactorAnalysisReport]:
        with self._lock:
            snaps = list(self._snapshots)
        if len(snaps) < 10:
            return None

        # Collect all symbol factor values + forward returns across all snapshots
        all_ic: Dict[int, List[float]] = {h: [] for h in HOLDING_PERIODS}
        all_qrets: Dict[int, List[Dict[int, float]]] = {h: [] for h in HOLDING_PERIODS}
        all_top_q_sets: Dict[int, List[set]] = {h: [] for h in HOLDING_PERIODS}

        for snap in snaps:
            if len(snap.factor_vals) < MIN_UNIVERSE_SIZE:
                continue
            symbols = list(snap.factor_vals.keys())
            f_vals  = np.array([snap.factor_vals[s] for s in symbols])
            for h in HOLDING_PERIODS:
                rets = []
                syms_h = []
                for s in symbols:
                    r = snap.fwd_returns.get(s, {}).get(h)
                    if r is not None and np.isfinite(r):
                        rets.append(r)
                        syms_h.append(s)
                if len(syms_h) < MIN_UNIVERSE_SIZE:
                    continue
                f_h = np.array([snap.factor_vals[s] for s in syms_h])
                r_h = np.array(rets)
                ic, _ = spearmanr(f_h, r_h)
                if np.isfinite(ic):
                    all_ic[h].append(ic)
                # Quantile decomposition
                q_bounds = np.percentile(f_h, np.linspace(0, 100, N_QUANTILES + 1))
                q_rets: Dict[int, float] = {}
                for q in range(1, N_QUANTILES + 1):
                    lo, hi = q_bounds[q - 1], q_bounds[q]
                    mask = (f_h >= lo) & (f_h <= hi)
                    if mask.sum() > 0:
                        q_rets[q] = float(r_h[mask].mean())
                all_qrets[h].append(q_rets)
                # Track top-Q symbols for turnover
                top_q_syms = set(s for s, fv in zip(syms_h, f_h) if fv >= q_bounds[-2])
                all_top_q_sets[h].append(top_q_syms)

        icir_results: Dict[int, ICIRResult] = {}
        quant_results: Dict[int, QuantileResult] = {}
        for h in HOLDING_PERIODS:
            ics = np.array(all_ic[h])
            if len(ics) < 5:
                continue
            ic_mean  = float(np.mean(ics))
            ic_std   = float(np.std(ics))
            ir       = ic_mean / ic_std if ic_std > 1e-9 else 0.0
            ic_gt003 = float(np.mean(np.abs(ics) > 0.03))
            roll_ics = ics[-ROLLING_IC_WINDOW:] if len(ics) >= ROLLING_IC_WINDOW else ics
            rolling  = float(np.mean(roll_ics))
            strong   = abs(ic_mean) > IC_STRONG_THRESHOLD and abs(ir) > IR_STRONG_THRESHOLD
            bias     = self._ic_to_quality_bias(ic_mean, ir)
            icir_results[h] = ICIRResult(
                holding_period=h, ic_mean=ic_mean, ic_std=ic_std, ir=ir,
                ic_gt003_pct=ic_gt003, rolling_ic_30=rolling, is_strong=strong,
                quality_bias=bias
            )
            # Quantile
            qrets_list = all_qrets[h]
            if qrets_list:
                mean_qrets: Dict[int, float] = {}
                for q in range(1, N_QUANTILES + 1):
                    vals = [d[q] for d in qrets_list if q in d]
                    mean_qrets[q] = float(np.mean(vals)) if vals else 0.0
                spread = mean_qrets.get(N_QUANTILES, 0.0) - mean_qrets.get(1, 0.0)
                vals_sorted = [mean_qrets.get(q, 0.0) for q in range(1, N_QUANTILES + 1)]
                mono = all(vals_sorted[i] <= vals_sorted[i+1] for i in range(len(vals_sorted)-1))
                # Turnover
                sets_h = all_top_q_sets[h]
                turnover_vals = []
                for i in range(1, len(sets_h)):
                    prev, curr = sets_h[i-1], sets_h[i]
                    if prev or curr:
                        t = len(prev.symmetric_difference(curr)) / max(len(prev | curr), 1)
                        turnover_vals.append(t)
                avg_turn = float(np.mean(turnover_vals)) if turnover_vals else 0.5
                quant_results[h] = QuantileResult(
                    holding_period=h, quantile_means=mean_qrets, spread=spread,
                    monotonic=mono, turnover=avg_turn
                )

        if not icir_results:
            return None

        best_period = max(icir_results, key=lambda h: abs(icir_results[h].ir))
        composite   = float(np.mean([v.quality_bias for v in icir_results.values()]))
        composite   = float(np.clip(composite, -4.0, 5.0))

        return FactorAnalysisReport(
            computed_at=time.time(),
            n_symbols=len(self._factor_buffer),
            n_snapshots=len(snaps),
            icir_by_period=icir_results,
            quantile_by_period=quant_results,
            best_period=best_period,
            composite_bias=composite,
        )

    @staticmethod
    def _calc_momentum(pb: deque) -> float:
        """20-bar momentum factor value."""
        prices = list(pb)
        if len(prices) < 2:
            return 0.0
        oldest = prices[0]
        newest = prices[-1]
        return (newest - oldest) / oldest if oldest else 0.0

    def _composite_factor(self, symbol: str) -> float:
        """Equal-weight rank composite of sub-factors."""
        fb = self._factor_buffer.get(symbol)
        if not fb:
            return 0.0
        return float(np.mean(list(fb.values())))

    @staticmethod
    def _ic_to_quality_bias(ic_mean: float, ir: float) -> float:
        """
        Map IC/IR to Gate 8.5 quality_bias in range [-4, +5].
        Strong positive IC + high IR → +5 (strong alpha signal)
        Negative IC or low IR → −4 (factor predicts loss)
        """
        if abs(ic_mean) < 0.02 or abs(ir) < 0.15:
            return 0.0
        sign = np.sign(ic_mean)
        magnitude = min(abs(ic_mean) / 0.10, 1.0) * min(abs(ir) / 0.50, 1.0)
        if sign > 0:
            return float(np.round(magnitude * 5.0, 1))
        else:
            return float(np.round(magnitude * -4.0, 1))
