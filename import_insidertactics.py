#!/usr/bin/env python3
import csv
import sqlite3
import os
import re
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "SignalMaestro", "trade_history.db")
CSV_FILES = [
    "attached_assets/insidertactics-59250_1774228425414.csv",
    "attached_assets/insidertactics-59250-2_1774228807781.csv",
]

VALID_STATUSES = {"stopped out", "all targets achieved", "partial targets achieved", "closed at exchange"}

def import_data():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    existing_cols = {row[1] for row in c.execute("PRAGMA table_info(trades)").fetchall()}
    if "source" not in existing_cols:
        c.execute("ALTER TABLE trades ADD COLUMN source TEXT DEFAULT 'bot'")
        conn.commit()

    c.execute("DELETE FROM trades WHERE source='insidertactics'")
    conn.commit()
    print(f"Cleared previous InsiderTactics imports")

    imported = 0
    skipped_status = 0
    skipped_unfilled = 0
    seen_keys = set()

    for csv_path in CSV_FILES:
        if not os.path.exists(csv_path):
            print(f"Skipping missing: {csv_path}")
            continue
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    status = (row.get("Status", "") or "").strip().lower()
                    if status not in VALID_STATUSES:
                        skipped_status += 1
                        continue

                    filled_pct = float(row.get("Entry Targets % Filled", "0") or "0")
                    num_filled = int(row.get("Number of Filled Entry Targets", "0") or "0")
                    if filled_pct <= 0 or num_filled <= 0:
                        skipped_unfilled += 1
                        continue

                    date_str = row.get("Date", "")
                    if not date_str:
                        continue
                    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    ts = dt.timestamp()

                    symbol = (row.get("Symbol", "") or "").replace("/", "")
                    if not symbol:
                        continue

                    direction = (row.get("Direction", "") or "").strip().lower()
                    action = "BUY" if direction == "long" else "SELL"

                    entry = float(row.get("Filled Average Entry Price", 0) or 0)
                    if entry <= 0:
                        entry = float(row.get("Average Entry Price", 0) or 0)
                    if entry <= 0:
                        continue

                    dedup_key = f"{ts:.0f}_{symbol}_{action}_{entry:.8f}"
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    sl = float(row.get("Stop Loss Price", 0) or 0)
                    if sl <= 0:
                        sl = entry * (0.97 if action == "BUY" else 1.03)

                    tp1 = float(row.get("TP1 Price", 0) or 0)
                    tp2 = float(row.get("TP2 Price", 0) or 0)
                    tp3 = float(row.get("TP3 Price", 0) or 0)
                    if tp1 <= 0:
                        tp1 = entry * (1.02 if action == "BUY" else 0.98)
                    if tp2 <= 0:
                        tp2 = entry * (1.04 if action == "BUY" else 0.96)
                    if tp3 <= 0:
                        tp3 = entry * (1.06 if action == "BUY" else 0.94)

                    pnl_str = row.get("Signal Gained Profit %", "0") or "0"
                    pnl = float(pnl_str)

                    last_target = int(row.get("Last Target", "0") or "0")
                    if status in ("all targets achieved", "partial targets achieved") and last_target >= 1:
                        outcome = f"TP{min(last_target, 3)}"
                    elif status in ("all targets achieved", "partial targets achieved"):
                        outcome = "TP1"
                    elif status == "stopped out":
                        outcome = "SL"
                    elif status == "closed at exchange":
                        outcome = "TP1" if pnl > 0 else "SL"
                    else:
                        outcome = None

                    lev_str = row.get("Leverage", "10")
                    lev = 10
                    if lev_str:
                        m = re.search(r"([\d.]+)", lev_str)
                        if m:
                            lev = int(float(m.group(1)))

                    hour = dt.hour
                    confidence = 70.0
                    consensus = 0.80
                    signal_strength = 65.0
                    rr = abs(tp1 - entry) / max(abs(entry - sl), 1e-10)

                    c.execute("""
                        INSERT INTO trades (
                            timestamp, symbol, action, entry_price, stop_loss,
                            tp1, tp2, tp3,
                            confidence, swarm_consensus, signal_strength,
                            participation_rate, rsi, volume_ratio,
                            risk_reward_ratio, leverage, session,
                            agent_votes_json, atr_ratio, bb_position, hour_of_day,
                            outcome, pnl_pct, source
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        ts, symbol, action, entry, sl,
                        tp1, tp2, tp3,
                        confidence, consensus, signal_strength,
                        0.7, 50.0, 1.0,
                        rr, lev, "InsiderTactics",
                        "{}", 0.003, 0.5, hour,
                        outcome, pnl, "insidertactics",
                    ))
                    imported += 1
                except Exception:
                    continue

    conn.commit()

    total = c.execute("SELECT COUNT(*) FROM trades WHERE source='insidertactics'").fetchone()[0]
    wins = c.execute("SELECT COUNT(*) FROM trades WHERE source='insidertactics' AND outcome LIKE 'TP%'").fetchone()[0]
    losses = c.execute("SELECT COUNT(*) FROM trades WHERE source='insidertactics' AND outcome='SL'").fetchone()[0]
    conn.close()

    print(f"Imported {imported} InsiderTactics trades into {DB_PATH}")
    print(f"  Skipped: {skipped_status} non-executed (cancelled/active), {skipped_unfilled} unfilled")
    print(f"  Results: {wins} wins, {losses} losses ({wins/(wins+losses)*100:.1f}% WR)" if (wins+losses) > 0 else "  No outcomes")
    print(f"  Deduped keys: {len(seen_keys)}")

if __name__ == "__main__":
    import_data()
