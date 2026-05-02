"""
gate_backtester.py — Replays historical trades from `advanced_ml_trading.db`
through Unity Engine's signal-filter gates and reports, per gate:

  • how many real trades the gate would have REJECTED
  • the win rate / avg P&L of the trades it would have rejected
    (i.e. the opportunity cost of the gate)
  • the win rate / avg P&L of the trades it would have ACCEPTED
  • a sweep over alternative thresholds for the tunable gates (G3, G0.5)

This does NOT modify the live engine. Read-only analysis.

Run:  python3 gate_backtester.py
"""

from __future__ import annotations
import sqlite3
import statistics
from collections import defaultdict
from typing import Callable, Iterable

DB_PATH = "advanced_ml_trading.db"

# ── Mirror Unity Engine constants (start_unity_engine.py) ───────────────
AI_THRESHOLD_PERCENT = 80.0          # Gate 3 base threshold (line 136)
SESSION_DEAD_HOURS_UTC = range(0, 4) # Gate 0.5 dead-zone 00-03h UTC
SESSION_PRIME_HOURS_UTC = range(12, 21)  # Gate 0.5 prime 12-20h UTC
SLIPPAGE_BPS_ROUND_TRIP = 10.0       # Gate 0 EV slippage (0.05%/side)


def fetch_trades(db_path: str) -> list[dict]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        "SELECT symbol, direction, entry_price, exit_price, stop_loss, "
        "take_profit_1, signal_strength, profit_loss, trade_result, "
        "ml_confidence, hour_of_day, market_volatility, volume_ratio "
        "FROM ml_trades WHERE profit_loss IS NOT NULL"
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def is_winner(t: dict) -> bool:
    return (t.get("profit_loss") or 0) > 0


def stats(label: str, trades: Iterable[dict]) -> dict:
    trades = list(trades)
    n = len(trades)
    if n == 0:
        return {"label": label, "n": 0, "wr": None, "avg_pnl": None, "expectancy": None}
    wins = sum(1 for t in trades if is_winner(t))
    pnls = [(t.get("profit_loss") or 0) for t in trades]
    wr = wins / n
    avg = statistics.mean(pnls)
    return {"label": label, "n": n, "wr": wr, "avg_pnl": avg, "expectancy": avg}


def fmt_row(s: dict) -> str:
    if s["n"] == 0:
        return f"  {s['label']:<28} n=0"
    return (
        f"  {s['label']:<28} n={s['n']:>5}  "
        f"WR={s['wr']*100:>5.1f}%  avg_pnl={s['avg_pnl']:+7.2f}%  "
        f"expectancy={s['expectancy']:+7.2f}%/trade"
    )


# ── Gate predicates: return True if the gate would PASS this trade ──────

def g0_ev_pass(t: dict) -> bool:
    """Gate 0 — EV>0 after 10bps round-trip slippage.
    Approximation: signal_strength * tp_distance - (1-signal_strength) * sl_distance > slippage.
    Without true probabilities we use signal_strength/100 as p(win).
    """
    e, sl, tp = t.get("entry_price"), t.get("stop_loss"), t.get("take_profit_1")
    p = (t.get("signal_strength") or 0) / 100.0
    if not (e and sl and tp and p):
        return True  # no data → don't penalise
    direction = (t.get("direction") or "").upper()
    if direction == "BUY":
        win_pct = (tp - e) / e * 100
        loss_pct = (e - sl) / e * 100
    else:
        win_pct = (e - tp) / e * 100
        loss_pct = (sl - e) / e * 100
    ev_bps = (p * win_pct - (1 - p) * loss_pct) * 100  # to bps
    return ev_bps > SLIPPAGE_BPS_ROUND_TRIP


def g0_5_session_pass(t: dict) -> bool:
    """Gate 0.5 — block dead-zone hours UTC 00-03h (penalty turns into reject in worst case)."""
    h = t.get("hour_of_day")
    if h is None:
        return True
    return h not in SESSION_DEAD_HOURS_UTC


def g0_8_min_tp1_pass(t: dict) -> bool:
    """Gate 0.8 — TP1 must be ≥0.40% from entry."""
    e, tp = t.get("entry_price"), t.get("take_profit_1")
    if not (e and tp):
        return True
    return abs(tp - e) / e >= 0.004


def g1_rr_pass(t: dict) -> bool:
    """Gate 1 — Weighted R:R ≥ 1.55 (using TP1 only as proxy)."""
    e, sl, tp = t.get("entry_price"), t.get("stop_loss"), t.get("take_profit_1")
    if not (e and sl and tp):
        return True
    risk = abs(e - sl)
    reward = abs(tp - e)
    if risk == 0:
        return True
    return (reward / risk) >= 1.55


def g3_confidence_pass(threshold: float) -> Callable[[dict], bool]:
    """Gate 3 — AI confidence ≥ threshold."""
    def _f(t: dict) -> bool:
        c = t.get("signal_strength") or t.get("ml_confidence") or 0
        return c >= threshold
    return _f


def g4_nn_pass(t: dict) -> bool:
    """Gate 4 — NN win-prob ≥ optimal threshold. Use ml_confidence ≥ 50 as proxy."""
    c = t.get("ml_confidence")
    if c is None:
        return True
    return c >= 50.0


# ── Reporting ───────────────────────────────────────────────────────────

def gate_impact(name: str, predicate: Callable[[dict], bool], trades: list[dict]) -> None:
    accepted = [t for t in trades if predicate(t)]
    rejected = [t for t in trades if not predicate(t)]
    print(f"\n── {name} ──")
    print(fmt_row(stats("ACCEPTED (gate pass)", accepted)))
    print(fmt_row(stats("REJECTED (opp cost)", rejected)))
    if rejected and accepted:
        s_a, s_r = stats("a", accepted), stats("r", rejected)
        delta_wr = (s_a["wr"] - s_r["wr"]) * 100
        delta_ev = s_a["expectancy"] - s_r["expectancy"]
        verdict = "✅ KEEP" if (delta_wr > 0 and delta_ev > 0) else (
                  "⚠️  MARGINAL" if delta_ev > -0.5 else "❌ REJECTING WINNERS — LOOSEN")
        print(f"  Δ-WR(accept-reject) = {delta_wr:+.1f}pp  "
              f"Δ-expectancy = {delta_ev:+.2f}%/trade   {verdict}")


def threshold_sweep(name: str, build_pred, thresholds, trades) -> None:
    print(f"\n── {name} threshold sweep ──")
    print(f"  {'thresh':<8}{'n_pass':>8}{'WR_pass':>10}{'EV_pass':>12}"
          f"{'n_rej':>8}{'WR_rej':>10}{'EV_rej':>12}")
    for th in thresholds:
        pred = build_pred(th)
        a = [t for t in trades if pred(t)]
        r = [t for t in trades if not pred(t)]
        sa, sr = stats("", a), stats("", r)
        wa = f"{sa['wr']*100:>9.1f}%" if sa['n'] else "       -"
        ea = f"{sa['expectancy']:+10.2f}%" if sa['n'] else "        -"
        wr = f"{sr['wr']*100:>9.1f}%" if sr['n'] else "       -"
        er = f"{sr['expectancy']:+10.2f}%" if sr['n'] else "        -"
        print(f"  {th:<8}{sa['n']:>8}{wa}{ea}{sr['n']:>8}{wr}{er}")


def main() -> None:
    print("═" * 78)
    print("UNITY ENGINE — GATE BACKTESTER (replay of historical trades)")
    print("═" * 78)
    trades = fetch_trades(DB_PATH)
    print(f"\nLoaded {len(trades)} historical trades from {DB_PATH}")
    print(fmt_row(stats("OVERALL (no gates)", trades)))

    gate_impact("Gate 0   — EV > 0 after slippage",   g0_ev_pass,         trades)
    gate_impact("Gate 0.5 — Block dead-zone hours",  g0_5_session_pass,  trades)
    gate_impact("Gate 0.8 — TP1 ≥ 0.40% from entry", g0_8_min_tp1_pass,  trades)
    gate_impact("Gate 1   — Weighted R:R ≥ 1.55",    g1_rr_pass,         trades)
    gate_impact("Gate 3   — AI confidence ≥ 80",     g3_confidence_pass(80.0), trades)
    gate_impact("Gate 4   — ML confidence ≥ 50",     g4_nn_pass,         trades)

    threshold_sweep("Gate 3 (AI confidence)",
                    g3_confidence_pass,
                    [50, 60, 65, 70, 75, 80, 85, 90],
                    trades)

    print("\n" + "═" * 78)
    print("READING GUIDE:")
    print("  • If REJECTED rows have HIGHER WR/EV than ACCEPTED, the gate is "
          "destroying alpha and should be loosened or removed.")
    print("  • Δ-expectancy is the per-trade P&L lift from keeping the gate.")
    print("  • Threshold sweep: pick the threshold that maximises EV_pass while "
          "keeping enough n_pass for a meaningful sample.")
    print("═" * 78)


if __name__ == "__main__":
    main()
