#!/usr/bin/env python3
"""
SwarmBM25Memory — BM25-based episodic memory for MiroFish Swarm Intelligence.

Each resolved signal is stored as a text "document" describing its context
(symbol, timeframe, session, agent votes, RSI, volume, outcome).
At query time, BM25 retrieves the most semantically similar past episodes,
providing the AIOrchestrationAgent with grounded historical context.

BM25 was chosen over embeddings because:
  1. Zero inference cost (no API call required)
  2. Deterministic and fast (O(D·q) where D=docs, q=query terms)
  3. No external dependencies beyond stdlib
  4. Keyword overlap with trading domain terms is high

Architecture:
  - In-memory ring buffer (max_docs configurable, default 500)
  - TF-IDF-style BM25 with k1=1.5, b=0.75 (Robertson–Zaragoza params)
  - Auto-stop words for common trading noise tokens
  - Thread-safe reads (GIL sufficient for append + search pattern)
  - Optional persistence via SQLite WAL if trade_memory is provided
"""

import math
import re
import time
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("SwarmBM25Memory")


# ─────────────────────────────────────────────────────────────────────────────
# Document & Retrieval Types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MemoryDocument:
    """A single resolved signal episode stored in BM25 memory."""
    doc_id: int
    text: str                          # tokenized text for BM25
    symbol: str
    action: str                        # BUY | SELL
    outcome: str                       # WIN | LOSS | UNKNOWN
    confidence: float
    consensus: float
    timeframe: str
    session: str
    rsi: float
    volume_ratio: float
    timestamp: float = field(default_factory=time.time)
    tokens: List[str] = field(default_factory=list)  # pre-tokenized


@dataclass
class RetrievalResult:
    """Single BM25 retrieval hit."""
    doc_id: int
    score: float
    symbol: str
    action: str
    outcome: str
    confidence: float
    consensus: float
    timeframe: str
    session: str
    text: str


# ─────────────────────────────────────────────────────────────────────────────
# Tokenizer
# ─────────────────────────────────────────────────────────────────────────────

_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
    "of", "to", "and", "or", "with", "for", "by", "from", "as",
    "signal", "trade", "market", "price", "candle",
})


def _tokenize(text: str) -> List[str]:
    """Lower-case, split on non-word chars, drop stop words and short tokens."""
    raw = re.split(r"[^a-zA-Z0-9%+\-\.]+", text.lower())
    return [
        t for t in raw
        if len(t) >= 2 and t not in _STOP_WORDS
    ]


# ─────────────────────────────────────────────────────────────────────────────
# BM25 Index
# ─────────────────────────────────────────────────────────────────────────────

class BM25Index:
    """
    Okapi BM25 index for in-memory document retrieval.

    Parameters:
        k1 (float): Term saturation factor (1.5 = moderate, 2.0 = high)
        b  (float): Length normalization (0.75 = standard)
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b  = b
        self._docs:       List[MemoryDocument]          = []
        self._tf:         List[Dict[str, int]]          = []   # term freq per doc
        self._df:         Dict[str, int]                = defaultdict(int)  # doc freq
        self._avg_len:    float                         = 0.0
        self._total_len:  int                           = 0
        self._next_id:    int                           = 0

    def add(self, doc: MemoryDocument) -> None:
        """Add a document to the index."""
        doc.doc_id = self._next_id
        self._next_id += 1
        tokens = _tokenize(doc.text)
        doc.tokens = tokens

        tf: Dict[str, int] = defaultdict(int)
        for t in tokens:
            tf[t] += 1

        for term in tf:
            self._df[term] += 1

        self._docs.append(doc)
        self._tf.append(dict(tf))
        self._total_len += len(tokens)
        self._avg_len = self._total_len / len(self._docs)

    def remove_oldest(self) -> None:
        """Remove the oldest document from the index."""
        if not self._docs:
            return
        old_doc = self._docs.pop(0)
        old_tf  = self._tf.pop(0)
        self._total_len -= len(old_doc.tokens)
        self._avg_len = self._total_len / max(len(self._docs), 1)
        for term, freq in old_tf.items():
            self._df[term] = max(0, self._df[term] - 1)
            if self._df[term] == 0:
                del self._df[term]

    def search(self, query_text: str, top_k: int = 5) -> List[RetrievalResult]:
        """BM25 search. Returns top_k results sorted by score descending."""
        if not self._docs:
            return []

        query_tokens = _tokenize(query_text)
        if not query_tokens:
            return []

        N = len(self._docs)
        scores: List[Tuple[float, int]] = []

        for idx, (doc, tf) in enumerate(zip(self._docs, self._tf)):
            dl   = len(doc.tokens)
            norm = 1.0 - self.b + self.b * dl / max(self._avg_len, 1.0)
            score = 0.0
            for term in query_tokens:
                if term not in tf:
                    continue
                df   = self._df.get(term, 0)
                idf  = math.log((N - df + 0.5) / (df + 0.5) + 1.0)
                tfv  = tf[term]
                tfn  = (tfv * (self.k1 + 1.0)) / (tfv + self.k1 * norm)
                score += idf * tfn
            if score > 0:
                scores.append((score, idx))

        scores.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, idx in scores[:top_k]:
            doc = self._docs[idx]
            results.append(RetrievalResult(
                doc_id=doc.doc_id,
                score=round(score, 4),
                symbol=doc.symbol,
                action=doc.action,
                outcome=doc.outcome,
                confidence=doc.confidence,
                consensus=doc.consensus,
                timeframe=doc.timeframe,
                session=doc.session,
                text=doc.text,
            ))
        return results

    @property
    def size(self) -> int:
        return len(self._docs)


# ─────────────────────────────────────────────────────────────────────────────
# SwarmBM25Memory — Public API
# ─────────────────────────────────────────────────────────────────────────────

class SwarmBM25Memory:
    """
    Episodic memory for MiroFish Swarm Intelligence using BM25 retrieval.

    Usage:
        memory = SwarmBM25Memory(max_docs=500)

        # Record a signal when it fires
        memory.record_signal(signal, outcome="UNKNOWN")

        # Update outcome when trade resolves
        memory.update_outcome(doc_id=42, outcome="WIN")

        # Query similar past episodes before generating AI narrative
        context = memory.retrieve_context(symbol="ETHUSDT", action="BUY",
                                          session="US", rsi=62, top_k=3)
    """

    def __init__(self, max_docs: int = 500, k1: float = 1.5, b: float = 0.75):
        self.max_docs = max_docs
        self._index   = BM25Index(k1=k1, b=b)
        self._id_map:  Dict[int, MemoryDocument] = {}  # doc_id → doc for update
        self._win_counter: Dict[str, int] = defaultdict(int)
        self._total_counter: Dict[str, int] = defaultdict(int)
        logger.info(f"🧠 SwarmBM25Memory initialized (max_docs={max_docs})")

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _build_text(symbol: str, action: str, timeframe: str, session: str,
                    rsi: float, volume_ratio: float, confidence: float,
                    consensus: float, agent_votes: dict, outcome: str) -> str:
        """
        Build a descriptive text document from signal fields.
        Designed so BM25 keyword overlap works on trading-domain terms.
        """
        vote_str = " ".join(
            f"{name.replace('Agent','').lower()}_{vote.lower()}"
            for name, vote in (agent_votes or {}).items()
        )
        rsi_label = (
            "rsi_oversold" if rsi < 30 else
            "rsi_overbought" if rsi > 70 else
            "rsi_neutral"
        )
        vol_label = "high_volume" if volume_ratio > 1.5 else (
            "low_volume" if volume_ratio < 0.7 else "normal_volume"
        )
        conf_label = (
            "very_high_conf" if confidence >= 88 else
            "high_conf" if confidence >= 80 else
            "moderate_conf"
        )
        cons_label = (
            "unanimous" if consensus >= 0.95 else
            "strong_consensus" if consensus >= 0.85 else
            "good_consensus"
        )
        return (
            f"{symbol} {action.lower()} {timeframe} {session.lower()} "
            f"{rsi_label} {vol_label} {conf_label} {cons_label} "
            f"{vote_str} outcome_{outcome.lower()}"
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def record_signal(self,
                      symbol: str,
                      action: str,
                      timeframe: str,
                      session: str,
                      rsi: float,
                      volume_ratio: float,
                      confidence: float,
                      consensus: float,
                      agent_votes: dict,
                      outcome: str = "UNKNOWN") -> int:
        """
        Record a new signal episode.  Returns the doc_id for later outcome update.

        If the index is full (≥ max_docs), evict the oldest document first.
        """
        text = self._build_text(
            symbol, action, timeframe, session, rsi, volume_ratio,
            confidence, consensus, agent_votes, outcome
        )
        doc = MemoryDocument(
            doc_id=-1,  # assigned by BM25Index.add()
            text=text,
            symbol=symbol,
            action=action,
            outcome=outcome,
            confidence=confidence,
            consensus=consensus,
            timeframe=timeframe,
            session=session,
            rsi=rsi,
            volume_ratio=volume_ratio,
        )

        if self._index.size >= self.max_docs:
            # Evict oldest before adding — keep ring-buffer size bounded
            oldest = self._index._docs[0] if self._index._docs else None
            if oldest:
                self._id_map.pop(oldest.doc_id, None)
            self._index.remove_oldest()

        self._index.add(doc)
        self._id_map[doc.doc_id] = doc

        self._total_counter[symbol] += 1
        if outcome == "WIN":
            self._win_counter[symbol] += 1

        return doc.doc_id

    def record_from_swarm_signal(self, signal, outcome: str = "UNKNOWN") -> int:
        """
        Convenience wrapper: record from a SwarmSignal dataclass instance.
        Compatible with mirofish_swarm_strategy.SwarmSignal.
        """
        return self.record_signal(
            symbol=getattr(signal, "symbol", "UNKNOWN"),
            action=getattr(signal, "action", "BUY"),
            timeframe=getattr(signal, "timeframe", "15m"),
            session=getattr(signal, "market_session", "UNKNOWN"),
            rsi=float(getattr(signal, "rsi", 50.0)),
            volume_ratio=float(getattr(signal, "volume_ratio", 1.0)),
            confidence=float(getattr(signal, "confidence", 70.0)),
            consensus=float(getattr(signal, "swarm_consensus", 0.75)),
            agent_votes=getattr(signal, "agent_votes", {}),
            outcome=outcome,
        )

    def update_outcome(self, doc_id: int, outcome: str) -> bool:
        """
        Update the outcome of a previously recorded episode.
        Returns True if doc_id was found and updated.
        """
        doc = self._id_map.get(doc_id)
        if doc is None:
            return False

        old_outcome = doc.outcome
        doc.outcome = outcome

        # Re-build text with updated outcome and re-index the doc
        doc.text = self._build_text(
            doc.symbol, doc.action, doc.timeframe, doc.session,
            doc.rsi, doc.volume_ratio, doc.confidence, doc.consensus,
            {}, outcome
        )
        doc.tokens = _tokenize(doc.text)

        # Update TF in index (find doc position by doc_id)
        for idx, d in enumerate(self._index._docs):
            if d.doc_id == doc_id:
                # Remove old TF terms from DF
                for term, freq in self._index._tf[idx].items():
                    self._index._df[term] = max(0, self._index._df.get(term, 0) - 1)
                    if self._index._df[term] == 0:
                        del self._index._df[term]
                # Add new TF
                from collections import Counter
                new_tf = dict(Counter(doc.tokens))
                for term in new_tf:
                    self._index._df[term] = self._index._df.get(term, 0) + 1
                self._index._tf[idx] = new_tf
                break

        # Update win counter
        if old_outcome != "WIN" and outcome == "WIN":
            self._win_counter[doc.symbol] += 1
        elif old_outcome == "WIN" and outcome != "WIN":
            self._win_counter[doc.symbol] = max(0, self._win_counter[doc.symbol] - 1)

        return True

    def retrieve_context(self,
                         symbol: str,
                         action: str,
                         session: str = "US",
                         rsi: float = 50.0,
                         volume_ratio: float = 1.0,
                         confidence: float = 75.0,
                         consensus: float = 0.80,
                         agent_votes: dict = None,
                         top_k: int = 5) -> List[RetrievalResult]:
        """
        Retrieve the top_k most similar past signal episodes using BM25.

        Constructs a query document from the current signal context and
        searches the memory index.  Returns a ranked list of past episodes.
        """
        query_text = self._build_text(
            symbol, action, "15m", session, rsi, volume_ratio,
            confidence, consensus, agent_votes or {}, "UNKNOWN"
        )
        return self._index.search(query_text, top_k=top_k)

    def get_symbol_win_rate(self, symbol: str) -> Optional[float]:
        """Return win rate for a symbol, or None if no recorded trades."""
        total = self._total_counter.get(symbol, 0)
        if total == 0:
            return None
        return self._win_counter.get(symbol, 0) / total

    def summarize_context(self,
                          results: List[RetrievalResult],
                          current_action: str) -> str:
        """
        Produce a compact natural-language summary of retrieved episodes
        for injection into the AIOrchestrationAgent's ReACT reasoning chain.

        Example output:
          "Memory: 3 similar past signals — 2 WIN 1 LOSS.
           BUY signals: 2/2 WIN (100%). Symbol ETHUSDT WR: 67%."
        """
        if not results:
            return "Memory: no similar past episodes found."

        wins   = sum(1 for r in results if r.outcome == "WIN")
        losses = sum(1 for r in results if r.outcome == "LOSS")
        ukwn   = sum(1 for r in results if r.outcome == "UNKNOWN")

        dir_results = [r for r in results if r.action == current_action]
        dir_wins    = sum(1 for r in dir_results if r.outcome == "WIN")

        total_known = wins + losses
        wr_str = f"{wins}/{total_known} WIN" if total_known > 0 else "no resolved"

        summary = (
            f"Memory({len(results)} similar): {wr_str} | "
            f"{current_action} alignment: {dir_wins}/{len(dir_results)} WIN"
        )
        if ukwn:
            summary += f" | {ukwn} unresolved"
        return summary

    @property
    def size(self) -> int:
        return self._index.size

    def status(self) -> str:
        total_known = sum(self._total_counter.values())
        total_wins  = sum(self._win_counter.values())
        wr = total_wins / total_known if total_known > 0 else 0.0
        return (
            f"BM25Memory: {self.size}/{self.max_docs} docs | "
            f"global WR={wr:.1%} ({total_wins}W/{total_known-total_wins}L)"
        )
