"""Unity Engine — Vectorized EV Pre-Screener   v18.16
====================================================

Institutional quant layer: eliminates structurally negative-EV symbols from
the full 14-gate pipeline using a SINGLE numpy vectorized pass across the
entire active symbol universe simultaneously.

Architecture
------------
  • Reads from GIL-safe module-level dicts (_ws_state, _live_mark_data,
    _live_liq_data) — zero-lock acquisition, zero-copy reads.
  • On first call per cycle, builds numpy float64 cost arrays for ALL symbols
    in ws_state in one O(N) sweep: spread_rt_bps[N], funding_bps[N],
    div_penalty_bps[N], liq_penalty_bps[N].
  • Computes raw_ev_bps = bayes_edge_bps − Σ cost_layers
  • Caches the resulting approved frozenset for _CACHE_TTL_SEC (default 5s)
    so subsequent per-symbol calls within the same scan cycle are O(1) dict
    lookups — the numpy array is built exactly once per cycle.
  • Total computation: ~0.15ms for 80 symbols on a single CPU core.

Cost model
----------
  spread_rt_bps    WS bid/ask round-trip spread (live or 8bps static fallback)
  funding_bps      |funding_rate| × 10,000 × HOLD_WEIGHT (partial-hold estimate)
  div_penalty_bps  |mark−index divergence| × DIV_WEIGHT (impaired execution)
  liq_penalty_bps  Liquidation cascade penalty (>$1M or >$5M in last 60s)

Integration
-----------
  Pre-Gate F in UnitySignalFilter.apply() — fires after Pre-Gate E
  (mark-price divergence block) and before Gate 0 full EV computation.
  EV floor = 15bps (lighter than Gate 0's 35bps — first-pass filter only).
  Set UNITY_VEV_ENABLED=0 to disable (full pass-through for all symbols).
  Set UNITY_VEV_FLOOR_BPS=N to tune the floor.
"""

from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, FrozenSet, List, Optional

_log = logging.getLogger("UnityEngine.VectorizedEV")

try:
    import numpy as _np
    _NP_OK = True
except ImportError:
    _np = None  # type: ignore[assignment]
    _NP_OK = False

# ── Configuration (env-tunable, read once at module load) ─────────────────────
_VEV_ENABLED: bool = os.getenv("UNITY_VEV_ENABLED", "1") not in ("0", "false", "False")

# Pre-screener EV floor in bps. Intentionally lighter than Gate 0's 35bps —
# acts as a coarse first-pass filter, not a precision gate.
_VEV_FLOOR_BPS: float = float(os.getenv("UNITY_VEV_FLOOR_BPS", "15.0") or 15.0)

# Max age of WS orderbook data to be used in spread computation.
# Data older than this → assume worst-case static spread fallback.
_WS_MAX_AGE_SEC: float = 10.0

# Static round-trip spread fallback when live WS data is unavailable (bps).
# 4bps one-leg × 2 = 8bps round-trip (conservative for USDM perpetuals).
_STATIC_SPREAD_RT_BPS: float = 8.0

# Funding cost weight: fraction of 8h funding period assumed for a signal hold.
# e.g. 0.01% (1bps) 8h funding × 0.25 weight = 0.25bps added execution cost.
_FUNDING_HOLD_WEIGHT: float = 0.25

# Mark/index divergence penalty multiplier.
# Each 1bps of |div_bps| adds this many bps to estimated execution cost.
_DIV_BPS_PENALTY_WEIGHT: float = 0.50

# Liquidation cascade thresholds and penalty values (USD notional in 60s).
_LIQ_HEAVY_USD: float = 5_000_000.0   # $5M → +4bps cost
_LIQ_LIGHT_USD: float = 1_000_000.0   # $1M → +1.5bps cost
_LIQ_HEAVY_BPS: float = 4.0
_LIQ_LIGHT_BPS: float = 1.5

# Cache TTL: re-compute at most once per cycle even when called per-symbol.
_CACHE_TTL_SEC: float = 5.0


class VectorizedEVScreener:
    """
    Singleton vectorized EV pre-screener for Unity Engine v18.3.

    Builds a full numpy cost matrix for the entire WS-active symbol universe
    on the first call per scan cycle, then serves subsequent per-symbol checks
    from an O(1) frozenset cache — paying the ~0.15ms numpy cost only once.

    Usage (inside UnitySignalFilter.apply)::

        _approved = _unity_vev_screener.check(
            symbol      = symbol,
            ws_state    = self._ws_state_ref or {},
            live_mark   = _live_mark_data,
            live_liq    = _live_liq_data,
            edge_bps    = _bayes_edge_bps,
        )
        if not _approved:
            return False, "VEV_REJECT: ...", 0.0
    """

    __slots__ = (
        "_cache_ts", "_cache_result", "_last_stats",
        "_buf_cap", "_buf_spread", "_buf_funding", "_buf_div_pen", "_buf_liq_pen",
    )

    def __init__(self) -> None:
        self._cache_ts: float = 0.0
        self._cache_result: FrozenSet[str] = frozenset()
        self._last_stats: Dict[str, Any] = {}
        # Pre-allocated fixed-capacity cost buffers — reused every rebuild cycle
        # to eliminate 4× numpy heap allocations per 5s VEV cache cycle. [v18.16]
        _CAP = 256
        self._buf_cap: int = _CAP
        if _NP_OK:
            self._buf_spread  = _np.empty(_CAP, dtype=_np.float64)
            self._buf_funding = _np.empty(_CAP, dtype=_np.float64)
            self._buf_div_pen = _np.empty(_CAP, dtype=_np.float64)
            self._buf_liq_pen = _np.empty(_CAP, dtype=_np.float64)
        else:
            self._buf_spread = self._buf_funding = self._buf_div_pen = self._buf_liq_pen = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def check(
        self,
        symbol: str,
        ws_state: Dict[str, Any],
        live_mark: Dict[str, Dict[str, float]],
        live_liq: Dict[str, Dict[str, float]],
        edge_bps: float = 30.0,
        floor_bps: Optional[float] = None,
    ) -> bool:
        """
        Return True if ``symbol`` passes the vectorized EV pre-screen.

        On first call per cycle: rebuilds the numpy cost array for all symbols
        in ``ws_state`` (O(N) pass, ~0.15ms for 80 symbols), caches result.
        Subsequent calls within the same cycle: O(1) frozenset lookup.

        Always returns True when numpy is unavailable or VEV is disabled —
        the screener is a performance optimisation, never a hard dependency.
        """
        if not _VEV_ENABLED or not _NP_OK:
            return True

        # Pass through when no WS data is available — the screener requires
        # live spread data to compute friction costs.  Without WS state,
        # we cannot distinguish cheap vs expensive symbols.  Gate 0 handles
        # the full EV decision with its own static fallback.
        if not ws_state:
            return True

        _floor = floor_bps if floor_bps is not None else _VEV_FLOOR_BPS
        sym_u = symbol.upper()

        _now = time.monotonic()
        if _now - self._cache_ts > _CACHE_TTL_SEC:
            self._rebuild(ws_state, live_mark, live_liq, edge_bps, _floor)
            self._cache_ts = _now

        # If the symbol has no entry in the approved cache (e.g. it has no
        # WS data yet — newly listed or just reconnecting), pass it through
        # rather than hard-blocking it.  Absence of data ≠ high friction.
        # Only reject when the symbol IS in the WS universe AND failed the floor.
        if sym_u not in ws_state and sym_u not in self._cache_result:
            return True  # not in WS universe → no cost data → pass through

        return sym_u in self._cache_result

    def invalidate(self) -> None:
        """Force a rebuild on the next check() call (call at scan-cycle start)."""
        self._cache_ts = 0.0
        self._cache_result = frozenset()

    @property
    def last_stats(self) -> Dict[str, Any]:
        """Last rebuild statistics for monitoring (read-only copy)."""
        return dict(self._last_stats)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _rebuild(
        self,
        ws_state: Dict[str, Any],
        live_mark: Dict[str, Dict[str, float]],
        live_liq: Dict[str, Dict[str, float]],
        edge_bps: float,
        floor_bps: float,
    ) -> None:
        """
        Build numpy cost arrays for all symbols in ws_state, compute EV, cache result.
        Called once per cycle — O(N) dict reads + 4 numpy element-wise ops.
        """
        if not ws_state:
            self._cache_result = frozenset()
            return

        t0 = time.perf_counter_ns()
        symbols: List[str] = list(ws_state.keys())
        n = len(symbols)

        # ── Buffer reuse — zero-allocation cost arrays [v18.16] ───────────────
        # Grow the pre-allocated buffers only when the symbol universe exceeds
        # the current capacity (rare; default cap=256 covers any real deployment).
        if n > self._buf_cap:
            _new_cap = n * 2
            self._buf_spread  = _np.empty(_new_cap, dtype=_np.float64)
            self._buf_funding = _np.empty(_new_cap, dtype=_np.float64)
            self._buf_div_pen = _np.empty(_new_cap, dtype=_np.float64)
            self._buf_liq_pen = _np.empty(_new_cap, dtype=_np.float64)
            self._buf_cap = _new_cap
        # Slice views into the pre-allocated buffers; fill() replaces heap alloc.
        spread_rt = self._buf_spread[:n]
        funding   = self._buf_funding[:n]
        div_pen   = self._buf_div_pen[:n]
        liq_pen   = self._buf_liq_pen[:n]
        spread_rt.fill(_STATIC_SPREAD_RT_BPS)
        funding.fill(0.0)
        div_pen.fill(0.0)
        liq_pen.fill(0.0)

        _ts_now = time.time()

        for i, sym in enumerate(symbols):
            # ── WS spread (round-trip bps) ──────────────────────────────────
            _ob = ws_state.get(sym)
            if _ob is not None:
                _age = _ts_now - float(_ob.get("ts", 0.0) or 0.0)
                if _age < _WS_MAX_AGE_SEC:
                    _sp = float(_ob.get("spread_pct", 0.0) or 0.0)
                    if _sp > 0.0:
                        # spread_pct is one-leg fraction → bps RT = sp × 2 × 10000
                        spread_rt[i] = min(50.0, _sp * 20_000.0)

            # ── Mark-price data: funding cost + divergence penalty ─────────
            _md = live_mark.get(sym)
            if _md:
                _fr = float(_md.get("funding_rate", 0.0) or 0.0)
                # funding_rate is 8h decimal (e.g. 0.0001 = 0.01%)
                # cost_bps = |fr| × 10000 × HOLD_WEIGHT
                funding[i] = abs(_fr) * 10_000.0 * _FUNDING_HOLD_WEIGHT

                _dv = float(_md.get("div_bps", 0.0) or 0.0)
                div_pen[i] = abs(_dv) * _DIV_BPS_PENALTY_WEIGHT

            # ── Liquidation cascade penalty ──────────────────────────────
            _lq = live_liq.get(sym)
            if _lq:
                _usd = float(_lq.get("liq_usd_60s", 0.0) or 0.0)
                if _usd > _LIQ_HEAVY_USD:
                    liq_pen[i] = _LIQ_HEAVY_BPS
                elif _usd > _LIQ_LIGHT_USD:
                    liq_pen[i] = _LIQ_LIGHT_BPS

        # ── Vectorized EV = edge − total_costs (single numpy pass) ─────────────
        total_cost = spread_rt + funding + div_pen + liq_pen   # shape (n,)
        ev_bps     = edge_bps - total_cost                     # shape (n,)
        pass_mask  = ev_bps >= floor_bps                       # bool array

        approved_set: FrozenSet[str] = frozenset(
            symbols[i] for i in range(n) if pass_mask[i]
        )

        elapsed_us  = (time.perf_counter_ns() - t0) // 1_000
        n_approved  = int(pass_mask.sum())
        n_rejected  = n - n_approved

        self._cache_result = approved_set
        self._last_stats = {
            "n_total":     n,
            "n_approved":  n_approved,
            "n_rejected":  n_rejected,
            "elapsed_us":  elapsed_us,
            "ev_min_bps":  float(_np.min(ev_bps)),
            "ev_max_bps":  float(_np.max(ev_bps)),
            "ev_mean_bps": float(_np.mean(ev_bps)),
            "floor_bps":   floor_bps,
        }

        if n_rejected > 0:
            _log.debug(
                f"⚡ [VEV v18.3] {n_rejected}/{n} symbols pre-rejected "
                f"(floor={floor_bps:.1f}bps) in {elapsed_us}μs | "
                f"EV range [{self._last_stats['ev_min_bps']:.1f}, "
                f"{self._last_stats['ev_max_bps']:.1f}]bps avg="
                f"{self._last_stats['ev_mean_bps']:.1f}bps"
            )


# ── Module-level singleton — imported by start_unity_engine.py ────────────────
_unity_vev_screener: VectorizedEVScreener = VectorizedEVScreener()
