#!/usr/bin/env python3
"""
TradeMemory — SQLite-backed historical signal ledger with outcome tracking.

Every signal the bot sends is persisted here. A background coroutine continuously
monitors open trades against live price to label outcomes (TP1/TP2/TP3/SL/EXPIRED).
Labeled trades feed the NeuralSignalTrainer for continuous self-improvement.

Schema is versioned (AUTO MIGRATION) so restarts never lose history.
"""

import sqlite3
import json
import os
import time
import logging
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

# ── DB path sits next to this module ──────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "trade_history.db")

# Trade expires after this many seconds with no TP/SL touch (6 hours on 15M)
TRADE_EXPIRY_SECONDS = 21_600

AGENT_ORDER = [
    "TrendAgent", "MomentumAgent", "VolumeAgent",
    "VolatilityAgent", "OrderFlowAgent", "SentimentAgent",
    "FundingFlowAgent", "PivotSRAgent", "FLOOPAgent", "AIOrchestrationAgent",
]


# ─────────────────────────────────────────────────────────────────────────────
# Data containers
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TradeRecord:
    id:               Optional[int]
    timestamp:        float        # Unix ts of signal emission
    symbol:           str          # e.g. "BTCUSDT", "ETHUSDT"
    action:           str          # "BUY" | "SELL"
    entry_price:      float
    stop_loss:        float
    tp1:              float
    tp2:              float
    tp3:              float
    confidence:       float        # post-boost confidence at emission
    swarm_consensus:  float
    signal_strength:  float
    participation_rate: float
    rsi:              float
    volume_ratio:     float
    risk_reward_ratio: float
    leverage:         int
    session:          str
    agent_votes_json: str          # JSON {"TrendAgent": "BUY", ...}
    atr_ratio:        float        # atr / entry_price (normalised volatility)
    bb_position:      float        # (close - lower) / (upper - lower), 0–1
    hour_of_day:      int          # 0–23 UTC
    # Outcome (filled by OutcomeTracker)
    outcome:          Optional[str]   # "TP1"|"TP2"|"TP3"|"SL"|"EXPIRED"
    outcome_price:    Optional[float]
    outcome_timestamp: Optional[float]
    pnl_pct:          Optional[float]  # raw % P&L (positive = profit)


# ─────────────────────────────────────────────────────────────────────────────
# TradeMemory — storage layer
# ─────────────────────────────────────────────────────────────────────────────

class TradeMemory:
    """
    Persistent SQLite store for every signal sent and its eventual outcome.
    Thread-safe via WAL mode. Migrations applied automatically on first connect.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._init_db()
        count = self._count_total()
        self.logger.info(
            f"📚 TradeMemory ready — {DB_PATH} | "
            f"{count} historical trades loaded"
        )

    # ── Schema ────────────────────────────────────────────────────────────────

    _db_lock = __import__("threading").Lock()

    @contextmanager
    def _db(self):
        """
        Managed SQLite connection context manager with thread lock.
        Commits on clean exit, rolls back on exception, and always closes
        the connection — preventing file-handle leaks in long-running async bots.
        """
        with self._db_lock:
            conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _init_db(self):
        with self._db() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp         REAL    NOT NULL,
                    symbol            TEXT    NOT NULL DEFAULT 'BTCUSDT',
                    action            TEXT    NOT NULL,
                    entry_price       REAL    NOT NULL,
                    stop_loss         REAL    NOT NULL,
                    tp1               REAL    NOT NULL,
                    tp2               REAL    NOT NULL,
                    tp3               REAL    NOT NULL,
                    confidence        REAL    NOT NULL,
                    swarm_consensus   REAL    NOT NULL,
                    signal_strength   REAL    NOT NULL,
                    participation_rate REAL   NOT NULL DEFAULT 0.700,
                    rsi               REAL    NOT NULL DEFAULT 50.0,
                    volume_ratio      REAL    NOT NULL DEFAULT 1.0,
                    risk_reward_ratio REAL    NOT NULL DEFAULT 1.5,
                    leverage          INTEGER NOT NULL DEFAULT 10,
                    session           TEXT    NOT NULL DEFAULT 'US',
                    agent_votes_json  TEXT    NOT NULL DEFAULT '{}',
                    atr_ratio         REAL    NOT NULL DEFAULT 0.003,
                    bb_position       REAL    NOT NULL DEFAULT 0.5,
                    hour_of_day       INTEGER NOT NULL DEFAULT 12,
                    outcome           TEXT    DEFAULT NULL,
                    outcome_price     REAL    DEFAULT NULL,
                    outcome_timestamp REAL    DEFAULT NULL,
                    pnl_pct           REAL    DEFAULT NULL
                )
            """)
            # Auto-migration: single PRAGMA table_info call covers all column checks
            existing_cols = {
                row[1] for row in c.execute("PRAGMA table_info(trades)").fetchall()
            }
            if "symbol" not in existing_cols:
                c.execute("ALTER TABLE trades ADD COLUMN symbol TEXT NOT NULL DEFAULT 'BTCUSDT'")
                self.logger.info("📦 DB migrated: added 'symbol' column to trades")

            # Auto-migration: add partial_outcome column if missing (upgrade path).
            # This column persists the in-memory ratchet best across restarts so
            # OutcomeTracker._init_best_from_db() can re-seed it correctly.
            if "partial_outcome" not in existing_cols:
                c.execute(
                    "ALTER TABLE trades ADD COLUMN partial_outcome TEXT DEFAULT NULL"
                )
                self.logger.info(
                    "📦 DB migrated: added 'partial_outcome' column to trades"
                )

            if "source" not in existing_cols:
                c.execute(
                    "ALTER TABLE trades ADD COLUMN source TEXT DEFAULT 'bot'"
                )
                self.logger.info(
                    "📦 DB migrated: added 'source' column to trades"
                )

            # Indexes for fast open-trade and per-symbol queries
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_outcome
                ON trades (outcome, timestamp)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_symbol_outcome
                ON trades (symbol, outcome, timestamp)
            """)

    # ── Writes ────────────────────────────────────────────────────────────────

    def record_signal(
        self,
        signal,
        bb_position: float = 0.5,
    ) -> int:
        """
        Persist a newly sent SwarmSignal. Returns the new trade ID.
        atr_ratio is derived from signal.atr_value / signal.entry_price.
        Supports multi-symbol: reads signal.symbol (falls back to 'BTCUSDT').
        """
        ts = signal.timestamp.timestamp() if signal.timestamp else time.time()
        atr_ratio = (
            signal.atr_value / signal.entry_price
            if (getattr(signal, "atr_value", None) and signal.entry_price)
            else 0.003
        )
        symbol = getattr(signal, "symbol", "BTCUSDT") or "BTCUSDT"
        with self._db() as c:
            cur = c.execute("""
                INSERT INTO trades (
                    timestamp, symbol, action, entry_price, stop_loss,
                    tp1, tp2, tp3,
                    confidence, swarm_consensus, signal_strength,
                    participation_rate, rsi, volume_ratio,
                    risk_reward_ratio, leverage, session,
                    agent_votes_json, atr_ratio, bb_position, hour_of_day
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ts,
                symbol,
                signal.action,
                signal.entry_price,
                signal.stop_loss,
                signal.take_profit_1,
                signal.take_profit_2,
                signal.take_profit_3,
                signal.confidence,
                signal.swarm_consensus,
                signal.signal_strength,
                getattr(signal, "participation_rate", 0.700),
                signal.rsi,
                signal.volume_ratio,
                signal.risk_reward_ratio,
                signal.leverage,
                getattr(signal, "market_session", "US"),
                json.dumps(signal.agent_votes or {}),
                atr_ratio,
                bb_position,
                datetime.fromtimestamp(ts, tz=timezone.utc).hour,
            ))
            trade_id = cur.lastrowid

        def _pfmt(p: float) -> str:
            """Format price with full precision regardless of magnitude."""
            if p >= 1000:   return f"{p:,.2f}"
            if p >= 1:      return f"{p:.4f}"
            if p >= 0.001:  return f"{p:.6f}"
            return f"{p:.10f}".rstrip("0").rstrip(".")

        self.logger.info(
            f"📝 Trade #{trade_id} recorded: {symbol} {signal.action} @ "
            f"${_pfmt(signal.entry_price)} | "
            f"TP1={signal.take_profit_1:.6g} TP2={signal.take_profit_2:.6g} "
            f"TP3={signal.take_profit_3:.6g} SL={signal.stop_loss:.6g}"
        )
        return trade_id

    def write_partial_outcome(self, trade_id: int, partial: str):
        """
        Persist the best intermediate TP level seen so far for an open trade.

        Called by OutcomeTracker whenever the in-memory ratchet advances
        (e.g. price reaches TP1 while still watching for TP2/TP3).  Stored
        in the `partial_outcome` column so _init_best_from_db() can re-seed
        the ratchet correctly after a bot restart without relying on the
        non-existent `notes` column.
        """
        try:
            with self._db() as c:
                c.execute(
                    "UPDATE trades SET partial_outcome=? WHERE id=? AND outcome IS NULL",
                    (partial, trade_id),
                )
        except Exception as e:
            self.logger.debug(f"write_partial_outcome #{trade_id}: {e}")

    def resolve_trade(
        self,
        trade_id: int,
        outcome: str,
        outcome_price: float,
        pnl_pct: float,
    ):
        """Mark a trade with its final outcome."""
        with self._db() as c:
            c.execute("""
                UPDATE trades
                SET outcome=?, outcome_price=?, outcome_timestamp=?, pnl_pct=?,
                    partial_outcome=NULL
                WHERE id=? AND outcome IS NULL
            """, (outcome, outcome_price, time.time(), pnl_pct, trade_id))
        self.logger.info(
            f"✅ Trade #{trade_id} resolved: {outcome} @ "
            f"${outcome_price:.6g} | PnL: {pnl_pct:+.2f}%"
        )

    # ── Reads ─────────────────────────────────────────────────────────────────

    def get_open_trades(self) -> List[Dict]:
        """All trades not yet resolved (no outcome)."""
        with self._db() as c:
            rows = c.execute("""
                SELECT * FROM trades
                WHERE outcome IS NULL
                ORDER BY timestamp ASC
            """).fetchall()
        return [dict(r) for r in rows]

    def get_labeled_trades(self, limit: int = 1000) -> List[Dict]:
        """All trades with a resolved outcome, newest first."""
        with self._db() as c:
            rows = c.execute("""
                SELECT * FROM trades
                WHERE outcome IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def count_new_labeled_since(self, since_ts: float) -> int:
        """Count trades labeled after a given timestamp (for retraining trigger)."""
        with self._db() as c:
            return c.execute("""
                SELECT COUNT(*) FROM trades
                WHERE outcome IS NOT NULL AND outcome_timestamp > ?
            """, (since_ts,)).fetchone()[0]

    def _count_total(self) -> int:
        with self._db() as c:
            return c.execute("SELECT COUNT(*) FROM trades").fetchone()[0]

    def get_stats(self) -> Dict[str, Any]:
        """
        Summary statistics for /stats command and heartbeat.

        BUG FIX: Previously used pnl_pct > 0 for wins and pnl_pct <= 0 for losses.
        This miscounted neutral EXPIRED trades (pnl ~0%) as confirmed losses, inflating
        the reported loss rate and misrepresenting bot performance.

        Fix: use the unambiguous outcome field:
          wins   = outcome IN ('TP1','TP2','TP3')  — price reached take-profit
          losses = outcome = 'SL'                  — stop-loss hit
          EXPIRED trades are reported separately (not counted as win or loss).

        Also reduced from 8 separate SQL calls to 2 for lower DB overhead.
        """
        with self._db() as c:
            total   = c.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            labeled = c.execute("SELECT COUNT(*) FROM trades WHERE outcome IS NOT NULL").fetchone()[0]

            row = c.execute("""
                SELECT
                    COUNT(CASE WHEN outcome IN ('TP1','TP2','TP3') THEN 1 END) AS wins,
                    COUNT(CASE WHEN outcome = 'SL'                 THEN 1 END) AS losses,
                    COUNT(CASE WHEN outcome = 'TP1'                THEN 1 END) AS tp1_hits,
                    COUNT(CASE WHEN outcome = 'TP2'                THEN 1 END) AS tp2_hits,
                    COUNT(CASE WHEN outcome = 'TP3'                THEN 1 END) AS tp3_hits,
                    COUNT(CASE WHEN outcome = 'SL'                 THEN 1 END) AS sl_hits,
                    COUNT(CASE WHEN outcome = 'EXPIRED'            THEN 1 END) AS expired_count,
                    AVG(pnl_pct)                                               AS avg_pnl
                FROM trades
                WHERE outcome IS NOT NULL
            """).fetchone()

        wins         = row[0] or 0
        losses       = row[1] or 0
        tp1_hits     = row[2] or 0
        tp2_hits     = row[3] or 0
        tp3_hits     = row[4] or 0
        sl_hits      = row[5] or 0
        expired_count = row[6] or 0
        avg_pnl      = row[7]

        resolved     = wins + losses  # definitive outcomes only (excludes EXPIRED)
        win_rate     = (wins / resolved * 100) if resolved > 0 else 0.0
        return {
            "total_signals":  total,
            "labeled":        labeled,
            "open":           total - labeled,
            "wins":           wins,
            "losses":         losses,
            "expired":        expired_count,
            "win_rate":       round(win_rate, 1),
            "avg_pnl_pct":    round(avg_pnl or 0, 3),
            "tp1_hits":       tp1_hits,
            "tp2_hits":       tp2_hits,
            "tp3_hits":       tp3_hits,
            "sl_hits":        sl_hits,
        }

    def get_loss_trades(self, limit: int = 500) -> List[Dict]:
        """Trades that hit SL or expired with negative P&L — for loss pattern analysis."""
        with self._db() as c:
            rows = c.execute("""
                SELECT * FROM trades
                WHERE outcome IS NOT NULL
                  AND (outcome = 'SL' OR (outcome = 'EXPIRED' AND pnl_pct <= 0))
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_win_trades(self, limit: int = 500) -> List[Dict]:
        """Trades that hit TP1/TP2/TP3 — for win pattern analysis."""
        with self._db() as c:
            rows = c.execute("""
                SELECT * FROM trades
                WHERE outcome IN ('TP1', 'TP2', 'TP3')
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_stats_by_session(self) -> Dict[str, Dict]:
        """
        Win rate broken down by trading session.

        BUG FIX: Previously used pnl_pct > 0 for wins, which miscounted neutral
        EXPIRED trades (pnl ~0%) as losses, identical to the bug fixed in get_stats().
        Now uses the unambiguous outcome field consistent with all other stat methods:
          wins   = outcome IN ('TP1','TP2','TP3')
          losses = outcome = 'SL'
          EXPIRED trades are excluded from both win and loss counts.
        """
        with self._db() as c:
            rows = c.execute("""
                SELECT session,
                       COUNT(*) as total,
                       SUM(CASE WHEN outcome IN ('TP1','TP2','TP3') THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN outcome = 'SL'                 THEN 1 ELSE 0 END) as losses
                FROM trades
                WHERE outcome IS NOT NULL
                GROUP BY session
            """).fetchall()
        result = {}
        for row in rows:
            sess, total, wins, losses = row[0], row[1], row[2] or 0, row[3] or 0
            resolved = wins + losses
            result[sess] = {
                "total":    total,
                "wins":     wins,
                "losses":   losses,
                "win_rate": round(wins / resolved * 100, 1) if resolved > 0 else 0.0,
            }
        return result

    def get_recent_loss_rate(self, n: int = 20) -> float:
        """
        Loss rate for the last N definitively resolved trades.

        FIXED: Previously used pnl_pct <= 0 which counted any trade with tiny
        negative P&L (including neutral EXPIRED at -0.1%) as a confirmed loss.
        This inflated the apparent loss rate, triggering unnecessary high-loss-
        rate retrains and falsely blacklisting symbols like BTCUSDT.

        Fix: Only count unambiguous outcomes:
          • SL hits          → always a loss
          • EXPIRED pnl < −0.5% → confirmed loss (significant drawdown)
          • TP1/TP2/TP3      → win (not a loss)
          • EXPIRED pnl > −0.5% → neutral (excluded from rate calculation)
        """
        with self._db() as c:
            rows = c.execute("""
                SELECT outcome, pnl_pct FROM trades
                WHERE outcome IS NOT NULL
                ORDER BY COALESCE(outcome_timestamp, timestamp) DESC
                LIMIT ?
            """, (n * 3,)).fetchall()  # fetch 3× to account for neutral exclusions
        if not rows:
            return 0.0
        definitive = []
        for outcome, pnl in rows:
            outcome = (outcome or "").upper()
            pnl = float(pnl or 0.0)
            if outcome in ("TP1", "TP2", "TP3"):
                definitive.append(0)  # win = not a loss
            elif outcome == "SL":
                definitive.append(1)  # loss
            elif outcome == "EXPIRED":
                if pnl >= 0.5:
                    definitive.append(0)  # profitable expiry = win
                elif pnl <= -0.5:
                    definitive.append(1)  # significant loss expiry
                # else: neutral, skip
            if len(definitive) >= n:
                break
        if not definitive:
            return 0.0
        return sum(definitive) / len(definitive)

    def get_symbol_stats(self, min_trades: int = 5) -> Dict[str, Dict]:
        """
        Per-symbol win/loss statistics for the most recent trades.

        FIX 8: Per-symbol performance tracking — enables the bot to identify
        and optionally block symbols that are persistently unprofitable.

        Returns a dict keyed by symbol with:
          win_rate    — fraction of resolved trades that were profitable
          total       — number of resolved trades
          recent_loss_rate — loss rate for last 10 resolved trades
        """
        with self._db() as c:
            rows = c.execute("""
                SELECT symbol,
                       COUNT(*) AS total,
                       SUM(CASE WHEN outcome IN ('TP1','TP2','TP3') THEN 1 ELSE 0 END) AS wins,
                       SUM(CASE WHEN outcome = 'SL'                 THEN 1 ELSE 0 END) AS losses
                FROM trades
                WHERE outcome IS NOT NULL
                GROUP BY symbol
                HAVING COUNT(*) >= ?
            """, (min_trades,)).fetchall()
        result: Dict[str, Dict] = {}
        for row in rows:
            sym, total, wins, sym_losses = row[0], row[1], row[2] or 0, row[3] or 0
            resolved = wins + sym_losses
            result[sym] = {
                "total":    total,
                "wins":     wins,
                "losses":   sym_losses,
                "win_rate": round(wins / resolved, 4) if resolved > 0 else 0.0,
            }

        # Also compute recent_loss_rate (last 10 definitive) per symbol.
        # FIXED: previously used pnl_pct <= 0 which flagged neutral EXPIRED
        # trades (-0.1% pnl) as losses, falsely inflating per-symbol loss rates
        # and causing symbols like BTCUSDT to be blacklisted.
        with self._db() as c:
            for sym in list(result.keys()):
                recent = c.execute("""
                    SELECT outcome, pnl_pct FROM trades
                    WHERE outcome IS NOT NULL AND symbol = ?
                    ORDER BY COALESCE(outcome_timestamp, timestamp) DESC
                    LIMIT 30
                """, (sym,)).fetchall()
                if recent:
                    definitive = []
                    for outcome, pnl in recent:
                        outcome = (outcome or "").upper()
                        pnl = float(pnl or 0.0)
                        if outcome in ("TP1", "TP2", "TP3"):
                            definitive.append(0)
                        elif outcome == "SL":
                            definitive.append(1)
                        elif outcome == "EXPIRED":
                            if pnl >= 0.5:
                                definitive.append(0)
                            elif pnl <= -0.5:
                                definitive.append(1)
                        if len(definitive) >= 10:
                            break
                    if definitive:
                        result[sym]["recent_loss_rate"] = round(
                            sum(definitive) / len(definitive), 4
                        )
                    else:
                        result[sym]["recent_loss_rate"] = 0.0
                else:
                    result[sym]["recent_loss_rate"] = 0.0
        return result


# ─────────────────────────────────────────────────────────────────────────────
# OutcomeTracker — background coroutine
# ─────────────────────────────────────────────────────────────────────────────

class OutcomeTracker:
    """
    Runs as a background async task alongside the main scanner.
    Every CHECK_INTERVAL seconds it:
      1. Batch-fetches current prices for ALL symbols with open trades
      2. For each open trade, checks if TP1/TP2/TP3 or SL was touched
      3. Resolves the trade and computes raw P&L %
      4. Expires trades older than TRADE_EXPIRY_SECONDS
      5. Signals the trainer when enough new labels have accumulated

    Multi-symbol aware: works correctly across all USDM perpetual markets.
    Outcome priority (best first):  TP3 > TP2 > TP1 > SL
    We compare current price against all levels each cycle to track the
    BEST outcome that price has reached so far.  SL only beats a TP if
    no TP was ever touched.
    """

    CHECK_INTERVAL       = 90     # seconds between price checks (was 120)
    RETRAIN_THRESHOLD    = 8      # new labels needed to trigger re-train (was 10)
    MIN_TRAIN_SAMPLES    = 20     # minimum labeled trades to train at all
    # FIX 3: Minimum seconds between any two retrains.
    # Prevents infinite retrain loop when high_loss_rate gate fires every 90s.
    MIN_RETRAIN_INTERVAL = 1800   # 30 minutes minimum between retrains

    def __init__(self, memory: TradeMemory, trainer, trader, bot=None,
                 bm25_memory=None):
        self.logger  = logging.getLogger(__name__)
        self.memory  = memory
        self.trainer = trainer
        self.trader  = trader
        self.bot = bot
        self._bm25_memory = bm25_memory
        # Per-trade best outcome seen so far (in-memory ratchet).
        # Pre-populate from the DB so a restart never downgrades a trade that
        # had already reached TP1/TP2 but hasn't been fully resolved yet.
        self._best: Dict[int, Optional[str]] = {}
        # FIX 2: _last_train_count updated only after successful training.
        self._last_train_count = 0
        # FIX 3: Track last retrain wall-clock time to enforce cooldown.
        self._last_retrain_time: float = 0.0
        self._init_best_from_db()

    def _init_best_from_db(self):
        """
        Seed the in-memory `_best` ratchet from the `partial_outcome` column.

        Without this, a bot restart would forget that a trade had already
        touched TP1/TP2 (stored in partial_outcome by the ratchet write path).
        The ratchet would then start from None and could write a worse
        outcome (e.g. SL hit after TP1) as the final label.

        Previously read from a `notes` column that does not exist in the schema,
        so pre-seeding silently failed every time.  Now reads from `partial_outcome`
        which is written by write_partial_outcome() whenever the ratchet advances.
        """
        try:
            open_trades = self.memory.get_open_trades()
            pre_seeded = 0
            for trade in open_trades:
                tid = trade.get("id")
                if tid is None:
                    continue
                # partial_outcome is written by the ratchet write path each time
                # a new best TP level is reached (TP1 → TP2 → TP3).
                partial = trade.get("partial_outcome")
                if partial in ("TP1", "TP2", "TP3", "SL"):
                    self._best[tid] = partial
                    pre_seeded += 1
            if pre_seeded:
                self.logger.info(
                    f"🔎 OutcomeTracker: pre-seeded _best ratchet "
                    f"for {pre_seeded} in-flight trade(s) from partial_outcome"
                )
        except Exception as e:
            self.logger.debug(f"_init_best_from_db: {e}")

    async def run(self):
        """Main loop — run as asyncio.create_task()."""
        self.logger.info("🔎 OutcomeTracker started (multi-symbol)")

        # ── Startup training on historical data ────────────────────────────────
        # If the NN has not been trained yet and labeled trades already exist in
        # the DB (e.g. from a previous session), train immediately so the NN gate
        # is active from the first scan cycle.  Without this, the bot waits for
        # the first new resolution event (which can take hours), leaving 200+
        # historical labeled trades unused on restart.
        try:
            await asyncio.sleep(5)  # Brief delay to let bot fully initialise
            if self.trainer is not None and not getattr(self.trainer, "trained", False):
                labeled = self.memory.get_labeled_trades()
                if len(labeled) >= self.MIN_TRAIN_SAMPLES:
                    self.logger.info(
                        f"🧠 Startup: training NN on {len(labeled)} existing labeled "
                        f"trades (trainer was untrained after restart)"
                    )
                    await self._maybe_retrain()
        except Exception as _startup_err:
            self.logger.warning(f"Startup NN training skipped: {_startup_err}")

        while True:
            try:
                await asyncio.sleep(self.CHECK_INTERVAL)
                await self._check_all()
            except asyncio.CancelledError:
                self.logger.info("🔎 OutcomeTracker cancelled")
                break
            except Exception as e:
                self.logger.error(f"OutcomeTracker error: {e}", exc_info=True)
                await asyncio.sleep(30)

    async def _check_all(self):
        open_trades = self.memory.get_open_trades()
        if not open_trades:
            return

        # ── Collect unique symbols from open trades ──
        symbols_needed = list({t.get("symbol", "BTCUSDT") for t in open_trades})

        # ── Batch-fetch prices for all symbols ──
        price_map: Dict[str, float] = {}
        try:
            if hasattr(self.trader, "get_prices_for_symbols"):
                price_map = await self.trader.get_prices_for_symbols(symbols_needed)
            else:
                # Fallback: fetch BTCUSDT only (legacy trader)
                p = await self.trader.get_current_price()
                if p:
                    price_map = {s: p for s in symbols_needed}
        except Exception as e:
            self.logger.warning(f"Price batch fetch failed: {e}")
            return

        if not price_map:
            return

        now = time.time()
        newly_resolved = 0

        for trade in open_trades:
            tid    = trade["id"]
            symbol = trade.get("symbol", "BTCUSDT")
            current_price = price_map.get(symbol)
            if current_price is None:
                continue

            entry  = trade["entry_price"]
            sl     = trade["stop_loss"]
            tp1    = trade["tp1"]
            tp2    = trade["tp2"]
            tp3    = trade["tp3"]
            action = trade["action"]
            age    = now - trade["timestamp"]

            # ── Determine which levels have been reached this cycle ──
            if action == "BUY":
                best = self._eval_buy(current_price, sl, tp1, tp2, tp3)
            else:
                best = self._eval_sell(current_price, sl, tp1, tp2, tp3)

            # Persist best seen so far (ratchet — never downgrade TP level).
            # When the ratchet advances, write the new best to `partial_outcome`
            # so a restart can re-seed the ratchet from the DB instead of losing
            # all intermediate TP progress (previously read from non-existent `notes`).
            prev_best = self._best.get(tid)
            new_best  = self._better_outcome(prev_best, best)
            self._best[tid] = new_best

            # Write to DB only when ratchet actually advances to save writes
            if new_best != prev_best and new_best in ("TP1", "TP2", "TP3", "SL"):
                self.memory.write_partial_outcome(tid, new_best)

            resolved_outcome = self._best[tid]

            # Resolve if a definitive outcome is available OR trade expired
            should_resolve = (
                resolved_outcome in ("SL", "TP1", "TP2", "TP3") or
                age >= TRADE_EXPIRY_SECONDS
            )

            if should_resolve:
                if resolved_outcome is None or age >= TRADE_EXPIRY_SECONDS:
                    resolved_outcome = "EXPIRED"

                pnl_pct = self._calc_pnl(
                    action, entry, current_price, resolved_outcome,
                    sl, tp1, tp2, tp3
                )
                self.memory.resolve_trade(tid, resolved_outcome, current_price, pnl_pct)
                self._best.pop(tid, None)
                newly_resolved += 1

                # ── Adaptive confidence threshold: update streak counter ──
                # Wins reset the streak; losses tighten the confidence gate.
                # FIX: use same ±0.5% threshold as build_label() so neutral
                # EXPIRED trades (|pnl| < 0.5%) do not count as losses.
                if self.bot is not None and hasattr(self.bot, "update_loss_streak"):
                    is_loss = (resolved_outcome == "SL") or (
                        resolved_outcome == "EXPIRED" and pnl_pct <= -0.5
                    )
                    try:
                        _streak_coro = self.bot.update_loss_streak(is_loss)
                        if asyncio.iscoroutine(_streak_coro):
                            await _streak_coro
                    except Exception as _se:
                        self.logger.debug(f"streak update skipped: {_se}")

                # ── Online (incremental) learning: immediately update the NN
                # from this one resolved trade so the model adapts in real-time
                # between full batch retrains.  Only runs when the model is
                # already trained (has a fitted normaliser); safe no-op otherwise.
                if self.trainer is not None and hasattr(self.trainer, "update_online"):
                    resolved_record = {
                        **trade,
                        "outcome": resolved_outcome,
                        "outcome_price": current_price,
                        "pnl_pct": pnl_pct,
                    }
                    try:
                        self.trainer.update_online(resolved_record, n_steps=5, lr_scale=0.1)
                    except Exception as _oe:
                        self.logger.debug(f"online update skipped: {_oe}")

                if self._bm25_memory is not None:
                    try:
                        _sit_parts = [
                            f"symbol={symbol} action={action}",
                            f"session={trade.get('session', 'UNKNOWN')}",
                            f"rsi={trade.get('rsi', 50):.0f}",
                            f"vol_ratio={trade.get('volume_ratio', 1.0):.2f}",
                            f"consensus={trade.get('swarm_consensus', 0):.2f}",
                            f"confidence={trade.get('confidence', 0):.1f}",
                            f"atr_ratio={trade.get('atr_ratio', 0):.4f}",
                            f"bb_pos={trade.get('bb_position', 0.5):.2f}",
                        ]
                        _avj = trade.get("agent_votes_json", "{}")
                        try:
                            _votes = json.loads(_avj) if isinstance(_avj, str) else _avj
                            _sit_parts.append(
                                f"votes={' '.join(f'{k[:4]}:{v[0]}' for k, v in _votes.items())}"
                            )
                        except Exception:
                            pass
                        _situation_text = " | ".join(_sit_parts)
                        _ind_snapshot = {
                            "rsi": trade.get("rsi", 50),
                            "vol_ratio": trade.get("volume_ratio", 1.0),
                            "atr_ratio": trade.get("atr_ratio", 0),
                            "bb_position": trade.get("bb_position", 0.5),
                            "hour": trade.get("hour_of_day", 0),
                        }
                        self._bm25_memory.store_trade_reflection(
                            symbol=symbol,
                            action=action,
                            outcome=resolved_outcome,
                            pnl_pct=pnl_pct,
                            situation_text=_situation_text,
                            indicators=_ind_snapshot,
                        )
                    except Exception as _ref_err:
                        self.logger.debug(f"BM25 reflection skipped: {_ref_err}")

        if newly_resolved > 0:
            self.logger.info(
                f"🔎 OutcomeTracker: resolved {newly_resolved} trades "
                f"across {len(symbols_needed)} symbol(s)"
            )
            await self._maybe_retrain()

    # ── Outcome evaluation helpers ─────────────────────────────────────────

    @staticmethod
    def _eval_buy(price, sl, tp1, tp2, tp3) -> Optional[str]:
        if price >= tp3: return "TP3"
        if price >= tp2: return "TP2"
        if price >= tp1: return "TP1"
        if price <= sl:  return "SL"
        return None

    @staticmethod
    def _eval_sell(price, sl, tp1, tp2, tp3) -> Optional[str]:
        if price <= tp3: return "TP3"
        if price <= tp2: return "TP2"
        if price <= tp1: return "TP1"
        if price >= sl:  return "SL"
        return None

    _RANK = {"TP3": 4, "TP2": 3, "TP1": 2, "SL": 1, "EXPIRED": 0, None: -1}

    def _better_outcome(self, a: Optional[str], b: Optional[str]) -> Optional[str]:
        """Return the better (higher rank) of two outcomes. Never downgrade a TP."""
        if self._RANK.get(a, -1) >= self._RANK.get(b, -1):
            return a
        return b

    @staticmethod
    def _calc_pnl(
        action: str, entry: float, exit_price: float,
        outcome: str, sl: float, tp1: float, tp2: float, tp3: float
    ) -> float:
        """Raw percentage P&L (not leveraged) for labelling."""
        if outcome == "SL":
            ref = sl
        elif outcome == "TP3":
            ref = tp3
        elif outcome == "TP2":
            ref = tp2
        elif outcome == "TP1":
            ref = tp1
        else:
            ref = exit_price  # EXPIRED — use current price

        if entry == 0:
            return 0.0
        if action == "BUY":
            return (ref - entry) / entry * 100.0
        else:
            return (entry - ref) / entry * 100.0

    # ── Retraining trigger ─────────────────────────────────────────────────

    async def _maybe_retrain(self):
        """
        Fire-and-forget retraining when enough new labels have accumulated.

        Enhanced triggers:
          1. Enough new labels (RETRAIN_THRESHOLD = 8)
          2. Recent loss rate > 55% → force cold retrain to correct bias

        FIX 2: _last_train_count is only updated when training SUCCEEDS.
          Previously it was updated before calling train(), so any training
          error permanently prevented future retraining.

        FIX 3: Minimum retrain cooldown (MIN_RETRAIN_INTERVAL = 1800s).
          The high_loss_rate gate previously fired every CHECK_INTERVAL (90s)
          creating an infinite tight retrain loop.  Now a minimum of 30 minutes
          must elapse between any two retraining runs.
        """
        labeled = self.memory.get_labeled_trades()
        if len(labeled) < self.MIN_TRAIN_SAMPLES:
            return

        # FIX 3: Enforce minimum retrain cooldown
        now_ts = time.time()
        elapsed_since_retrain = now_ts - self._last_retrain_time
        if elapsed_since_retrain < self.MIN_RETRAIN_INTERVAL:
            remaining = self.MIN_RETRAIN_INTERVAL - elapsed_since_retrain
            self.logger.debug(
                f"🧠 Retrain cooldown active — {remaining:.0f}s remaining "
                f"(min interval: {self.MIN_RETRAIN_INTERVAL}s)"
            )
            return

        new_since_last = len(labeled) - self._last_train_count

        # Check rolling loss rate — force retrain if losing frequently
        recent_loss_rate = self.memory.get_recent_loss_rate(n=20)
        high_loss_rate   = recent_loss_rate > 0.55  # > 55% losses in last 20 trades

        if new_since_last < self.RETRAIN_THRESHOLD and not high_loss_rate:
            return

        trigger = "high_loss_rate" if high_loss_rate else "new_labels"
        self.logger.info(
            f"🧠 Triggering NN retraining [{trigger}] — "
            f"{len(labeled)} total labeled trades (+{new_since_last} new) | "
            f"recent_loss_rate={recent_loss_rate:.1%}"
        )

        # FIX 3: Mark retrain start time immediately to prevent concurrent triggers
        self._last_retrain_time = now_ts

        # Cold retrain when loss rate is high (don't fine-tune a biased model)
        # Warm restart (fine-tune) for small incremental updates
        _use_warm = (
            getattr(self.trainer, "trained", False)
            and new_since_last < 30
            and not high_loss_rate
        )

        import functools
        _train_fn = functools.partial(
            self.trainer.train, labeled,
            epochs=300 if not _use_warm else 200,
            warm_restart=_use_warm,
        )

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, _train_fn)
            status = result.get("status", "?")
            if status == "trained":
                # FIX 2: Only update _last_train_count on successful training.
                # Previously set BEFORE training — any error permanently blocked
                # future retrains because the counter advanced even on failure.
                self._last_train_count = len(labeled)

                mode     = "warm" if _use_warm else "cold"
                win_acc  = result.get("win_acc",  0.0)
                loss_acc = result.get("loss_acc", 0.0)
                dz       = result.get("danger_zones", 0)
                opt_thresh = result.get("opt_threshold", 0.5)
                class_w    = result.get("class_weight", 2.0)
                self.logger.info(
                    f"🧠 NN retrained ({mode}): acc={result['accuracy']:.1%} | "
                    f"win_acc={win_acc:.1%} | loss_acc={loss_acc:.1%} | "
                    f"W/L={result['wins']}/{result['losses']} | "
                    f"class_w={class_w:.2f}x | "
                    f"val_loss={result['val_loss']:.4f} | "
                    f"opt_thresh={opt_thresh:.3f} | "
                    f"danger_zones={dz} | epochs={result.get('epochs_run', '?')}"
                )
                if loss_acc < 0.50:
                    self.logger.warning(
                        f"⚠️ Loss accuracy {loss_acc:.1%} < 50% — model not learning "
                        f"losses well.  Will force cold retrain next cycle."
                    )
            else:
                # Training skipped / errored — reset cooldown so next cycle can retry
                self.logger.warning(
                    f"⚠️ Retrain not completed (status={status}) — "
                    f"cooldown reset for next cycle"
                )
                self._last_retrain_time = 0.0  # allow retry next cycle
        except Exception as e:
            self.logger.error(f"Retraining error: {e}")
            self._last_retrain_time = 0.0  # allow retry next cycle
