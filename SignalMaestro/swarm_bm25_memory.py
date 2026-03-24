#!/usr/bin/env python3
"""
SwarmBM25Memory — BM25-based offline memory for TradingAgents-style reflection.

Ported from TauricResearch/TradingAgents FinancialSituationMemory.
Uses BM25Okapi for lexical similarity matching — no API calls, no token limits,
works offline with any LLM provider. SQLite-backed persistence so lessons survive
bot restarts.

Memory roles (mirroring TradingAgents architecture):
  - bull:         Bullish researcher reflections
  - bear:         Bearish researcher reflections
  - risk_agg:     Aggressive risk analyst reflections
  - risk_con:     Conservative risk analyst reflections
  - risk_neu:     Neutral risk analyst reflections
  - portfolio_mgr: Portfolio manager final decision reflections
"""

import json
import logging
import os
import re
import sqlite3
import time
from typing import Dict, List, Optional, Tuple

try:
    from rank_bm25 import BM25Okapi
    _HAS_BM25 = True
except ImportError:
    _HAS_BM25 = False

logger = logging.getLogger(__name__)

MEMORY_DB_PATH = os.path.join(os.path.dirname(__file__), "swarm_memory.db")

MEMORY_ROLES = [
    "bull", "bear", "risk_agg", "risk_con", "risk_neu", "portfolio_mgr",
]

MAX_LESSONS_PER_ROLE = 2000


class BM25MemoryBank:
    """Single BM25-indexed memory bank for one role."""

    def __init__(self, role: str):
        self.role = role
        self.documents: List[str] = []
        self.recommendations: List[str] = []
        self.metadata: List[dict] = []
        self.bm25 = None

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        tokens = re.findall(r'\b\w+\b', text.lower())
        return tokens

    def _rebuild_index(self):
        if self.documents and _HAS_BM25:
            tokenized_docs = [self._tokenize(doc) for doc in self.documents]
            self.bm25 = BM25Okapi(tokenized_docs)
        else:
            self.bm25 = None

    def add_lesson(self, situation: str, recommendation: str, meta: dict = None):
        self.documents.append(situation)
        self.recommendations.append(recommendation)
        self.metadata.append(meta or {})
        if len(self.documents) > MAX_LESSONS_PER_ROLE:
            self.documents = self.documents[-MAX_LESSONS_PER_ROLE:]
            self.recommendations = self.recommendations[-MAX_LESSONS_PER_ROLE:]
            self.metadata = self.metadata[-MAX_LESSONS_PER_ROLE:]
        self._rebuild_index()

    def get_memories(self, current_situation: str, n_matches: int = 2) -> List[dict]:
        if not self.documents or self.bm25 is None or not _HAS_BM25:
            return []
        query_tokens = self._tokenize(current_situation)
        if not query_tokens:
            return []
        scores = self.bm25.get_scores(query_tokens)
        top_indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:n_matches]
        max_score = max(scores) if max(scores) > 0 else 1
        results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            normalized_score = scores[idx] / max_score if max_score > 0 else 0
            results.append({
                "matched_situation": self.documents[idx],
                "recommendation": self.recommendations[idx],
                "similarity_score": normalized_score,
                "metadata": self.metadata[idx],
            })
        return results

    def clear(self):
        self.documents = []
        self.recommendations = []
        self.metadata = []
        self.bm25 = None


class SwarmBM25Memory:
    """
    Multi-role BM25 memory system with SQLite persistence.

    Mirrors TradingAgents' FinancialSituationMemory but with:
    - Multiple named memory banks (bull, bear, risk perspectives, PM)
    - SQLite persistence (lessons survive bot restarts)
    - Automatic pruning to MAX_LESSONS_PER_ROLE
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or MEMORY_DB_PATH
        self.banks: Dict[str, BM25MemoryBank] = {
            role: BM25MemoryBank(role) for role in MEMORY_ROLES
        }
        self._init_db()
        self._load_from_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS swarm_lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    situation TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    metadata_json TEXT DEFAULT '{}',
                    created_at REAL DEFAULT (strftime('%s','now')),
                    UNIQUE(role, situation, recommendation)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_lessons_role
                ON swarm_lessons(role)
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"SwarmBM25Memory DB init error: {e}")

    def _load_from_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT role, situation, recommendation, metadata_json "
                "FROM swarm_lessons ORDER BY id ASC"
            )
            count = 0
            for role, situation, recommendation, meta_json in cursor:
                if role in self.banks:
                    meta = {}
                    try:
                        meta = json.loads(meta_json) if meta_json else {}
                    except Exception:
                        pass
                    self.banks[role].documents.append(situation)
                    self.banks[role].recommendations.append(recommendation)
                    self.banks[role].metadata.append(meta)
                    count += 1
            conn.close()
            for bank in self.banks.values():
                bank._rebuild_index()
            if count > 0:
                logger.info(
                    f"SwarmBM25Memory loaded {count} lessons from DB "
                    f"({', '.join(f'{r}={len(b.documents)}' for r, b in self.banks.items() if b.documents)})"
                )
        except Exception as e:
            logger.warning(f"SwarmBM25Memory load error: {e}")

    def add_lesson(self, role: str, situation: str, recommendation: str,
                   meta: dict = None):
        if role not in self.banks:
            logger.warning(f"Unknown memory role: {role}")
            return
        self.banks[role].add_lesson(situation, recommendation, meta)
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT OR IGNORE INTO swarm_lessons "
                "(role, situation, recommendation, metadata_json) "
                "VALUES (?, ?, ?, ?)",
                (role, situation, recommendation, json.dumps(meta or {}))
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"SwarmBM25Memory persist error: {e}")

    def get_memories(self, role: str, current_situation: str,
                     n_matches: int = 2) -> List[dict]:
        if role not in self.banks:
            return []
        return self.banks[role].get_memories(current_situation, n_matches)

    def get_all_memories(self, current_situation: str,
                         n_matches: int = 1) -> Dict[str, List[dict]]:
        results = {}
        for role, bank in self.banks.items():
            memories = bank.get_memories(current_situation, n_matches)
            if memories:
                results[role] = memories
        return results

    def store_trade_reflection(self, symbol: str, action: str, outcome: str,
                               pnl_pct: float, situation_text: str,
                               indicators: dict = None):
        _won = outcome in ("TP1", "TP2", "TP3")
        _lost = outcome == "SL"

        meta = {
            "symbol": symbol,
            "action": action,
            "outcome": outcome,
            "pnl_pct": pnl_pct,
            "timestamp": time.time(),
        }
        if indicators:
            meta["indicators"] = indicators

        if _won:
            bull_lesson = (
                f"WINNING {action} on {symbol}: {outcome} hit, PnL={pnl_pct:+.1f}%. "
                f"Indicators confirmed the move. Similar setups should be taken with confidence."
            )
            self.add_lesson("bull", situation_text, bull_lesson, meta)

            bear_lesson = (
                f"MISSED OPPORTUNITY: {action} on {symbol} was correct ({outcome}, PnL={pnl_pct:+.1f}%). "
                f"The bearish concerns were overweighted. Adjust for similar patterns."
            )
            self.add_lesson("bear", situation_text, bear_lesson, meta)

            pm_lesson = (
                f"CORRECT DECISION: {action} {symbol} achieved {outcome} ({pnl_pct:+.1f}%). "
                f"Rating: BUY/OVERWEIGHT was appropriate for this setup."
            )
            self.add_lesson("portfolio_mgr", situation_text, pm_lesson, meta)

        elif _lost:
            bull_lesson = (
                f"FAILED {action} on {symbol}: SL hit, PnL={pnl_pct:+.1f}%. "
                f"Bullish thesis was wrong. Avoid similar setups or require stronger confirmation."
            )
            self.add_lesson("bull", situation_text, bull_lesson, meta)

            bear_lesson = (
                f"CORRECT CAUTION: {action} on {symbol} hit SL (PnL={pnl_pct:+.1f}%). "
                f"The risk concerns were valid. Similar setups should be avoided or downsized."
            )
            self.add_lesson("bear", situation_text, bear_lesson, meta)

            pm_lesson = (
                f"WRONG DECISION: {action} {symbol} hit SL ({pnl_pct:+.1f}%). "
                f"Rating should have been UNDERWEIGHT/SELL for this setup."
            )
            self.add_lesson("portfolio_mgr", situation_text, pm_lesson, meta)

            risk_con_lesson = (
                f"RISK VALIDATED: Conservative view correct — {action} {symbol} "
                f"hit SL ({pnl_pct:+.1f}%). Reduce exposure on similar setups."
            )
            self.add_lesson("risk_con", situation_text, risk_con_lesson, meta)

            risk_agg_lesson = (
                f"AGGRESSIVE LOSS: {action} {symbol} SL hit ({pnl_pct:+.1f}%). "
                f"The aggressive stance was too optimistic. Tighten risk on similar patterns."
            )
            self.add_lesson("risk_agg", situation_text, risk_agg_lesson, meta)
        else:
            pm_lesson = (
                f"EXPIRED/NEUTRAL: {action} {symbol} outcome={outcome} ({pnl_pct:+.1f}%). "
                f"Position timed out. Consider tighter TP or longer expiry for similar setups."
            )
            self.add_lesson("portfolio_mgr", situation_text, pm_lesson, meta)

    def get_lesson_counts(self) -> Dict[str, int]:
        return {role: len(bank.documents) for role, bank in self.banks.items()}

    def get_confidence_adjustment(self, current_situation: str,
                                   action: str) -> float:
        adjustment = 0.0
        pm_memories = self.get_memories("portfolio_mgr", current_situation, n_matches=3)
        for mem in pm_memories:
            if mem["similarity_score"] < 0.3:
                continue
            meta = mem.get("metadata", {})
            past_pnl = meta.get("pnl_pct", 0)
            past_outcome = meta.get("outcome", "")
            past_action = meta.get("action", "")

            same_direction = (past_action == action)

            if past_outcome in ("TP1", "TP2", "TP3") and same_direction:
                adjustment += min(past_pnl * 0.3, 2.0) * mem["similarity_score"]
            elif past_outcome == "SL" and same_direction:
                adjustment += max(past_pnl * 0.5, -3.0) * mem["similarity_score"]
            elif past_outcome == "SL" and not same_direction:
                adjustment += 0.5 * mem["similarity_score"]

        return max(-5.0, min(5.0, adjustment))
