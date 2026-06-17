#!/usr/bin/env python3
"""
Unity Engine — Walk-Forward Backtest Harness
=============================================

Purpose
-------
Validate candidate signal filters against REAL recorded trades using a
purged, embargoed, expanding-window walk-forward — so a filter is only
credited when its benefit persists OUT-OF-SAMPLE. This is the rigorous
alternative to eyeballing the full dataset (which invites overfitting).

Methodology
-----------
1. Load resolved trades (have an outcome + pnl_pct) for one `source`,
   sorted chronologically by entry timestamp.
2. Split into K chronological folds. For fold i, TRAIN = folds [0..i-1]
   (expanding window), TEST = fold i, with an EMBARGO gap of trades
   dropped between train and test to avoid horizon leakage.
3. Each candidate filter is *learned on TRAIN only* (e.g. "is the
   RSI>70 bucket negative-expectancy in the training window?") and then
   *applied to the unseen TEST fold*. This exposes overfitting: a filter
   that helps in-sample but not out-of-sample will show it here.
4. Aggregate kept TEST trades across all folds and report WR, avg PnL,
   total PnL, per-trade Sharpe, and max drawdown vs the unfiltered
   baseline.

Run:  python3 SignalMaestro/walk_forward_backtest.py --source bot --folds 6
"""

from __future__ import annotations
import argparse
import os
import sqlite3
import statistics as st
from dataclasses import dataclass
from typing import Callable, Optional

DB_PATH_CANDIDATES = [
    "SignalMaestro/trade_history.db",
    "trade_history.db",
]

# ----------------------------------------------------------------------------- data
def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_trades(source: Optional[str]) -> list[dict]:
    path = next((p for p in DB_PATH_CANDIDATES if os.path.exists(p)), None)
    if not path:
        raise SystemExit("trade_history.db not found")
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM trades")]
    con.close()

    out = []
    for r in rows:
        if source and r.get("source") != source:
            continue
        if r.get("outcome") in (None, "", "OPEN", "PENDING", "ACTIVE"):
            continue
        pnl = _num(r.get("pnl_pct"))
        if pnl is None:
            continue
        ts = _num(r.get("timestamp"))
        if ts is None:
            continue
        out.append({
            "ts": ts,
            "pnl": pnl,
            "session": (r.get("session") or "").strip(),
            "rsi": _num(r.get("rsi")),
            "volume_ratio": _num(r.get("volume_ratio")),
            "confidence": _num(r.get("confidence")),
            "rr": _num(r.get("risk_reward_ratio")),
            "action": (r.get("action") or "").strip(),
            "outcome": (r.get("outcome") or "").upper(),
        })
    out.sort(key=lambda x: x["ts"])
    return out


# ----------------------------------------------------------------------------- metrics
@dataclass
class Metrics:
    n: int
    wr: float          # pnl-sign win rate
    out_wr: float      # outcome win rate (TP=win, SL/EXPIRED=loss)
    avg: float         # avg pnl per trade (% points)
    total: float       # sum of pnl (% points)
    sharpe: float      # per-trade sharpe = mean/std
    max_dd: float      # max peak-to-trough of cumulative equity (% points)


def compute(trades: list[dict]) -> Metrics:
    if not trades:
        return Metrics(0, 0, 0, 0, 0, 0, 0)
    pnls = [t["pnl"] for t in trades]
    n = len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    out_wins = sum(1 for t in trades if t["outcome"].startswith("TP"))
    avg = st.mean(pnls)
    total = sum(pnls)
    sd = st.pstdev(pnls) if n > 1 else 0.0
    sharpe = (avg / sd) if sd else 0.0
    # max drawdown of cumulative equity curve
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        eq += p
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)
    return Metrics(n, wins / n * 100, out_wins / n * 100, avg, total, sharpe, max_dd)


# ----------------------------------------------------------------------------- filters
# A filter is a family: it is FIT on train (returns a predicate) then APPLIED to test.
# predicate(trade) -> True means KEEP the trade (signal passes the filter).

def fit_session_filter(train: list[dict], min_n: int, tau: float) -> Callable[[dict], bool]:
    """Blacklist sessions whose TRAIN mean pnl < tau (with >= min_n samples)."""
    by: dict[str, list[float]] = {}
    for t in train:
        by.setdefault(t["session"], []).append(t["pnl"])
    blacklist = {s for s, v in by.items() if len(v) >= min_n and st.mean(v) < tau}
    return lambda t: t["session"] not in blacklist, blacklist


def fit_threshold_filter(train: list[dict], field: str, lo: float, hi: float,
                         min_n: int, tau: float):
    """Enable a 'block trades with field in [lo,hi)' rule only if that
    bucket is negative-expectancy on TRAIN (>= min_n samples)."""
    bucket = [t["pnl"] for t in train
              if t[field] is not None and lo <= t[field] < hi]
    enabled = len(bucket) >= min_n and st.mean(bucket) < tau
    if not enabled:
        return (lambda t: True), False

    def keep(t):
        v = t[field]
        return not (v is not None and lo <= v < hi)
    return keep, True


# ----------------------------------------------------------------------------- walk-forward
def walk_forward(trades: list[dict], folds: int, embargo: int,
                 filter_name: str, min_n: int, tau: float):
    """Returns (oos_baseline_trades, oos_kept_trades, debug_lines)."""
    n = len(trades)
    fold_size = n // folds
    base_oos: list[dict] = []
    kept_oos: list[dict] = []
    dbg = []
    for i in range(1, folds):
        train_end = i * fold_size
        test_start = train_end + embargo
        test_end = (i + 1) * fold_size if i < folds - 1 else n
        train = trades[:train_end - embargo] if train_end - embargo > 0 else trades[:train_end]
        test = trades[test_start:test_end]
        if not train or not test:
            continue

        if filter_name == "session":
            keep, info = fit_session_filter(train, min_n, tau)
        elif filter_name == "rsi_overbought":
            keep, info = fit_threshold_filter(train, "rsi", 70.0, 1e9, min_n, tau)
        elif filter_name == "vol_spike":
            keep, info = fit_threshold_filter(train, "volume_ratio", 2.0, 1e9, min_n, tau)
        elif filter_name == "confidence_high":
            # test the HYPOTHESIS that high confidence is better: keep only conf>=80.
            # (Expected to FAIL OOS — confidence looked miscalibrated.)
            keep = lambda t: (t["confidence"] is not None and t["confidence"] >= 80.0)
            info = ">=80"
        elif filter_name == "session+vol":
            kf, _ = fit_session_filter(train, min_n, tau)
            kv, _ = fit_threshold_filter(train, "volume_ratio", 2.0, 1e9, min_n, tau)
            keep = lambda t, kf=kf, kv=kv: kf(t) and kv(t)
            info = "session+vol"
        elif filter_name == "session+rsi+vol":
            kf, _ = fit_session_filter(train, min_n, tau)
            kr, _ = fit_threshold_filter(train, "rsi", 70.0, 1e9, min_n, tau)
            kv, _ = fit_threshold_filter(train, "volume_ratio", 2.0, 1e9, min_n, tau)
            keep = lambda t, kf=kf, kr=kr, kv=kv: kf(t) and kr(t) and kv(t)
            info = "session+rsi+vol"
        else:
            raise ValueError(filter_name)

        base_oos.extend(test)
        kept_oos.extend([t for t in test if keep(t)])
        dbg.append(f"   fold {i}: train={len(train):4} test={len(test):4} learned={info}")
    return base_oos, kept_oos, dbg


# ----------------------------------------------------------------------------- report
def fmt(m: Metrics) -> str:
    return (f"n={m.n:4} | WR={m.wr:4.1f}% outWR={m.out_wr:4.1f}% | "
            f"avgPnL={m.avg:+.3f}% total={m.total:+8.1f}% | "
            f"Sharpe={m.sharpe:+.3f} | maxDD={m.max_dd:6.1f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="bot",
                    help="trade source to backtest (bot|insidertactics|all)")
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--embargo", type=int, default=10,
                    help="trades dropped between train and test (anti-leakage)")
    ap.add_argument("--min-n", type=int, default=40,
                    help="min train samples before trusting a bucket's sign")
    ap.add_argument("--tau", type=float, default=-0.05,
                    help="train mean-pnl threshold below which a bucket is blacklisted")
    args = ap.parse_args()

    src = None if args.source == "all" else args.source
    trades = load_trades(src)
    print("=" * 78)
    print(f"WALK-FORWARD BACKTEST  source={args.source!r}  trades={len(trades)}  "
          f"folds={args.folds}  embargo={args.embargo}  minN={args.min_n}  tau={args.tau}")
    print("=" * 78)

    if len(trades) < args.folds * 30:
        print(f"⚠️  thin data ({len(trades)}); results are indicative only.")

    print("\nFULL-SAMPLE baseline (all trades):")
    print("   " + fmt(compute(trades)))

    print("\nOUT-OF-SAMPLE (aggregated walk-forward test folds):")
    for name in ("session", "rsi_overbought", "vol_spike", "confidence_high",
                 "session+vol", "session+rsi+vol"):
        base, kept, dbg = walk_forward(trades, args.folds, args.embargo,
                                       name, args.min_n, args.tau)
        bm, km = compute(base), compute(kept)
        if name == "session":  # baseline is identical across filters; print once
            print("   BASELINE (OOS, no filter):")
            print("      " + fmt(bm))
            print()
        filtered_out = bm.n - km.n
        d_total = km.total - bm.total
        d_avg = km.avg - bm.avg
        d_dd = km.max_dd - bm.max_dd
        verdict = "HELPS" if (km.avg > bm.avg and km.max_dd <= bm.max_dd + 1e-9) else (
            "neutral" if abs(d_avg) < 0.02 else "HURTS")
        print(f"   [{name}]  ({filtered_out} signals filtered out of {bm.n})")
        print("      " + fmt(km))
        print(f"      Δ avgPnL={d_avg:+.3f}%  Δ total={d_total:+.1f}%  "
              f"Δ maxDD={d_dd:+.1f}%  →  {verdict}")
        for line in dbg:
            print(line)
        print()

    print("=" * 78)
    print("READ: a filter is only worth shipping if it improves OOS avgPnL AND")
    print("does not worsen OOS maxDD. 'confidence_high' is included as a control —")
    print("if it does not help, the confidence score is not predictive.")
    print("=" * 78)


if __name__ == "__main__":
    main()
