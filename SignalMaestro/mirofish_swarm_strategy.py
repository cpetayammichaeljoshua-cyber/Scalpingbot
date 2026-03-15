#!/usr/bin/env python3
"""
MiroFish Swarm Intelligence Strategy — BTCUSDT USDM Futures
100% Strictly based on github.com/666ghj/MiroFish architecture:

MiroFish Architectural Concepts Implemented:
1. Agent Profiles       — Each agent has persona, stance, influence_weight, activity_level,
                          sentiment_bias, response_delay, active_hours (oasis_profile_generator.py)
2. Market Ontology      — Entity types + relationship types defining the market knowledge graph
                          (ontology_generator.py)
3. Graph-State Memory   — Typed nodes + temporal edges tracking market state with
                          valid_at / invalid_at / expired flags (graph_builder.py + zep_tools.py)
4. InsightForge         — Decompose analysis into sub-queries, retrieve from graph, aggregate
                          (zep_tools.py InsightForgeResult)
5. ReACT Pattern        — Reason → Act → Reflect loop for AI orchestration (report_agent.py)
6. Market Session Layer — Session-aware agent weight multipliers (simulation_config_generator.py)
7. Event-Driven Agents  — Agents react to market events (funding rates, OI, volume spikes)
8. Consensus Emergence  — Weighted collective intelligence with participation scoring (simulation_runner.py)

v3.1 — Comprehensive Enhancement:
- Agents: eliminated excessive NEUTRAL zones, added continuous signals
- Consensus: participation bonus/penalty, quorum requirement, divergence penalty
- ATR: true range calculation (high-low-prev_close)
- New helpers: BB%B, ADX proxy, Stochastic, CMF, EMA slope
- AIOrchestrationAgent: robust rule-based fallback, improved prompt
- FundingFlowAgent: real funding-rate fetch with VWAP proxy fallback
"""

import asyncio
import logging
from collections import deque
import os
import time
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum

# ─────────────────────────────────────────────────────────────────────────────
# MiroFish Market Ontology
# Mirrors ontology_generator.py — entity/relationship taxonomy for market graph
# ─────────────────────────────────────────────────────────────────────────────

class MarketEntityType(str, Enum):
    """Market knowledge graph entity types (MiroFish ontology)"""
    TREND_STATE      = "TrendState"
    PRICE_LEVEL      = "PriceLevel"
    PATTERN          = "Pattern"
    SIGNAL           = "Signal"
    MARKET_SESSION   = "MarketSession"
    CATALYST         = "Catalyst"
    INDICATOR_STATE  = "IndicatorState"
    AGENT_BELIEF     = "AgentBelief"

class MarketEdgeType(str, Enum):
    """Temporal relationship types in the market graph (MiroFish edge ontology)"""
    CONFIRMS         = "CONFIRMS"
    CONTRADICTS      = "CONTRADICTS"
    EVOLVES_TO       = "EVOLVES_TO"
    PRECEDED_BY      = "PRECEDED_BY"
    TARGETS          = "TARGETS"
    INVALIDATES      = "INVALIDATES"
    CAUSED_BY        = "CAUSED_BY"
    ALIGNED_WITH     = "ALIGNED_WITH"
    DIVERGES_FROM    = "DIVERGES_FROM"


# ─────────────────────────────────────────────────────────────────────────────
# Graph-State Memory Nodes & Edges
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GraphNode:
    """Market knowledge graph node"""
    uuid: str
    name: str
    entity_type: MarketEntityType
    summary: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_text(self) -> str:
        return f"[{self.entity_type.value}] {self.name}: {self.summary}"


@dataclass
class GraphEdge:
    """Temporal market knowledge graph edge"""
    uuid: str
    edge_type: MarketEdgeType
    fact: str
    source_uuid: str
    target_uuid: str
    source_name: str = ""
    target_name: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    expired_at: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        return self.expired_at is not None

    @property
    def is_invalid(self) -> bool:
        return self.invalid_at is not None

    def to_text(self, include_temporal: bool = True) -> str:
        base = f"{self.source_name} --[{self.edge_type.value}]--> {self.target_name}: {self.fact}"
        if include_temporal and self.invalid_at:
            base += f" (invalidated: {self.invalid_at})"
        return base


# ─────────────────────────────────────────────────────────────────────────────
# Signal Data Class
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SwarmSignal:
    """MiroFish Swarm signal for BTCUSDT USDM Futures"""
    symbol: str
    action: str
    entry_price: float
    stop_loss: float
    take_profit: float
    signal_strength: float
    confidence: float
    risk_reward_ratio: float
    atr_value: float
    timestamp: datetime
    timeframe: str = "15m"
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    take_profit_3: float = 0.0
    leverage: int = 15
    rsi: float = 50.0
    volume_ratio: float = 1.0
    crossover_detected: bool = False
    swarm_consensus: float = 0.0
    agent_votes: dict = field(default_factory=dict)
    ai_narrative: str = ""
    market_session: str = "UNKNOWN"
    graph_insight: str = ""
    react_reasoning: str = ""
    participation_rate: float = 0.0  # fraction of agents that voted non-NEUTRAL

    def __post_init__(self):
        if self.take_profit_1 == 0.0:
            self.take_profit_1 = self.take_profit
        if self.take_profit_2 == 0.0:
            if self.action == "BUY":
                self.take_profit_2 = self.entry_price + (self.take_profit - self.entry_price) * 1.8
            else:
                self.take_profit_2 = self.entry_price - (self.entry_price - self.take_profit) * 1.8
        if self.take_profit_3 == 0.0:
            if self.action == "BUY":
                self.take_profit_3 = self.entry_price + (self.take_profit - self.entry_price) * 2.8
            else:
                self.take_profit_3 = self.entry_price - (self.entry_price - self.take_profit) * 2.8


# ─────────────────────────────────────────────────────────────────────────────
# BTCUSDT Timeframe Parameters
# ─────────────────────────────────────────────────────────────────────────────

BTCUSDT_PARAMS = {
    "1m":  {"sl_pct": 0.30, "tp1_pct": 0.50, "tp2_pct": 0.95,  "tp3_pct": 1.50,  "ema_fast": 9,  "ema_slow": 21, "min_candles": 100},
    "3m":  {"sl_pct": 0.40, "tp1_pct": 0.70, "tp2_pct": 1.30,  "tp3_pct": 2.00,  "ema_fast": 9,  "ema_slow": 21, "min_candles": 120},
    "5m":  {"sl_pct": 0.55, "tp1_pct": 1.00, "tp2_pct": 1.80,  "tp3_pct": 2.75,  "ema_fast": 9,  "ema_slow": 21, "min_candles": 200},
    "15m": {"sl_pct": 0.65, "tp1_pct": 1.10, "tp2_pct": 2.00,  "tp3_pct": 3.10,  "ema_fast": 9,  "ema_slow": 21, "min_candles": 200},
    "30m": {"sl_pct": 0.80, "tp1_pct": 1.35, "tp2_pct": 2.50,  "tp3_pct": 3.80,  "ema_fast": 13, "ema_slow": 34, "min_candles": 200},
    "1h":  {"sl_pct": 1.00, "tp1_pct": 1.70, "tp2_pct": 3.20,  "tp3_pct": 4.90,  "ema_fast": 21, "ema_slow": 55, "min_candles": 200},
    "4h":  {"sl_pct": 1.30, "tp1_pct": 2.20, "tp2_pct": 4.00,  "tp3_pct": 6.20,  "ema_fast": 21, "ema_slow": 55, "min_candles": 200},
}

LEVERAGE_MAP = {
    "1m": 20, "3m": 15, "5m": 15, "15m": 10, "30m": 8, "1h": 5, "4h": 3
}


# ─────────────────────────────────────────────────────────────────────────────
# MiroFish Agent Profile System
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentProfile:
    """
    Full MiroFish agent profile for a trading analysis agent.
    Mirrors OasisAgentProfile / AgentActivityConfig from MiroFish.
    """
    agent_id: int
    name: str
    persona: str
    stance: str
    activity_level: float
    influence_weight: float
    sentiment_bias: float
    response_delay_min: int
    response_delay_max: int
    active_sessions: List[str]
    session_multipliers: Dict[str, float] = field(default_factory=dict)

    def effective_weight(self, session: str) -> float:
        """Compute session-adjusted influence weight"""
        if session in self.active_sessions:
            mult = self.session_multipliers.get(session, 1.0)
        else:
            mult = 0.5
        return self.influence_weight * self.activity_level * mult


# ─────────────────────────────────────────────────────────────────────────────
# Market Session Classifier
# ─────────────────────────────────────────────────────────────────────────────

MARKET_SESSIONS = {
    "ASIAN": {
        "hours": list(range(0, 9)),
        "activity": 0.75,
        "volatility_bias": -0.1,
        "description": "Asian session (Tokyo/Shanghai)"
    },
    "EU": {
        "hours": list(range(7, 17)),
        "activity": 1.0,
        "volatility_bias": 0.1,
        "description": "European session (London/Frankfurt)"
    },
    "US": {
        "hours": list(range(13, 23)),
        "activity": 1.2,
        "volatility_bias": 0.2,
        "description": "US session (New York)"
    },
    "TRANSITION": {
        "hours": [23],
        "activity": 0.5,
        "volatility_bias": -0.2,
        "description": "Session transition"
    },
}

def get_current_market_session() -> Tuple[str, float]:
    """
    Returns (session_name, activity_multiplier) for current UTC time.

    Uses >= comparison so TRANSITION (activity=0.5) is correctly matched
    when hour 23 falls in its range and no other session is active.
    Previously used >, which meant TRANSITION was never selected by the
    loop (0.5 > 0.5 is False) and was returned only by coincidence because
    it happened to be the hardcoded default value.
    """
    utc_hour = datetime.now(timezone.utc).hour
    best_session = "TRANSITION"
    best_activity = -1.0          # sentinel: any match (even 0.5) wins
    for name, cfg in MARKET_SESSIONS.items():
        if utc_hour in cfg["hours"]:
            if cfg["activity"] >= best_activity:
                best_activity = cfg["activity"]
                best_session = name
    # If no session matched (shouldn't happen with the TRANSITION catchall),
    # default gracefully to TRANSITION with its defined activity.
    if best_activity < 0:
        best_activity = MARKET_SESSIONS["TRANSITION"]["activity"]
        best_session  = "TRANSITION"
    return best_session, best_activity


# ─────────────────────────────────────────────────────────────────────────────
# MiroFish Market Graph Memory
# ─────────────────────────────────────────────────────────────────────────────

class MarketGraphMemory:
    def __init__(self, max_nodes: int = 500, max_edges: int = 1000):
        self._nodes: Dict[str, GraphNode] = {}
        # O(1) reverse lookup: (name, entity_type) → uuid
        self._node_name_index: Dict[Tuple, str] = {}
        self._edges: List[GraphEdge] = []
        self._node_counter = 0
        self._edge_counter = 0
        self.max_nodes = max_nodes
        self.max_edges = max_edges
        self.logger = logging.getLogger(__name__ + ".GraphMemory")

    def _gen_id(self, prefix: str) -> str:
        self._node_counter += 1
        return f"{prefix}-{self._node_counter:06d}"

    def add_node(self, entity_type: MarketEntityType, name: str,
                 summary: str, attributes: Dict = None) -> str:
        # O(1) lookup via reverse index
        existing = self._node_name_index.get((name, entity_type))
        if existing and existing in self._nodes:
            self._nodes[existing].summary = summary
            if attributes:
                self._nodes[existing].attributes.update(attributes)
            return existing
        node_id = self._gen_id("node")
        node = GraphNode(
            uuid=node_id, name=name, entity_type=entity_type,
            summary=summary, attributes=attributes or {}
        )
        self._nodes[node_id] = node
        self._node_name_index[(name, entity_type)] = node_id
        self._prune_nodes()
        return node_id

    def add_edge(self, edge_type: MarketEdgeType, source_uuid: str,
                 target_uuid: str, fact: str) -> str:
        self._edge_counter += 1
        edge_id = f"edge-{self._edge_counter:06d}"
        src_node = self._nodes.get(source_uuid)
        tgt_node = self._nodes.get(target_uuid)
        edge = GraphEdge(
            uuid=edge_id, edge_type=edge_type, fact=fact,
            source_uuid=source_uuid, target_uuid=target_uuid,
            source_name=src_node.name if src_node else source_uuid,
            target_name=tgt_node.name if tgt_node else target_uuid,
            valid_at=datetime.now(timezone.utc).isoformat()
        )
        self._edges.append(edge)
        self._prune_edges()
        return edge_id

    def invalidate_edges(self, source_name: str, edge_type: MarketEdgeType):
        now = datetime.now(timezone.utc).isoformat()
        for edge in self._edges:
            if (edge.source_name == source_name and
                    edge.edge_type == edge_type and not edge.is_invalid):
                edge.invalid_at = now

    def insight_forge(self, topic: str, n_facts: int = 8) -> "InsightForgeResult":
        sub_queries = self._decompose_query(topic)
        facts, entities, relations = [], [], []
        for sq in sub_queries:
            if len(facts) >= n_facts:
                break
            sq_lower = sq.lower()
            for node in self._nodes.values():
                if any(kw in node.name.lower() or kw in node.summary.lower()
                       for kw in sq_lower.split()):
                    entities.append({"name": node.name, "type": node.entity_type.value,
                                     "summary": node.summary})
                    facts.append(node.to_text())
                    if len(facts) >= n_facts:
                        break
            if len(facts) >= n_facts:
                break
            for edge in self._edges[-50:]:
                if not edge.is_invalid and any(
                        kw in edge.fact.lower() for kw in sq_lower.split()):
                    relations.append(edge.to_text())
                    facts.append(edge.fact)
                    if len(facts) >= n_facts:
                        break
        return InsightForgeResult(
            query=topic, sub_queries=sub_queries,
            semantic_facts=facts[:n_facts], entity_insights=entities[:6],
            relationship_chains=relations[:6],
            total_facts=len(facts), total_entities=len(entities),
            total_relationships=len(relations)
        )

    def _decompose_query(self, topic: str) -> List[str]:
        return [
            f"What is the current trend state for {topic}?",
            f"What price levels are relevant to {topic}?",
            f"What patterns have formed recently for {topic}?",
            f"What catalysts are driving {topic}?",
        ]

    def get_active_signals(self, window: int = 20) -> List[GraphNode]:
        signals = [n for n in self._nodes.values()
                   if n.entity_type == MarketEntityType.SIGNAL]
        return signals[-window:]

    def get_trend_state(self) -> Optional[str]:
        trends = [n for n in self._nodes.values()
                  if n.entity_type == MarketEntityType.TREND_STATE]
        return trends[-1].summary if trends else None

    def summarize(self) -> Dict[str, Any]:
        return {
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "active_edges": sum(1 for e in self._edges if not e.is_invalid),
            "trend_state": self.get_trend_state(),
            "recent_signals": len(self.get_active_signals(10))
        }

    def _find_node_by_name(self, name: str, entity_type: MarketEntityType) -> Optional[str]:
        uid = self._node_name_index.get((name, entity_type))
        if uid and uid in self._nodes:
            return uid
        return None

    def _prune_nodes(self):
        if len(self._nodes) > self.max_nodes:
            excess = len(self._nodes) - self.max_nodes
            # Dict preserves insertion order (Python 3.7+); node IDs are monotonically
            # increasing, so the first `excess` keys are always the oldest.
            # Using list() is O(n) vs sorted() O(n log n) — critical in hot path.
            oldest = list(self._nodes.keys())[:excess]
            for k in oldest:
                node = self._nodes.pop(k)
                self._node_name_index.pop((node.name, node.entity_type), None)

    def _prune_edges(self):
        if len(self._edges) > self.max_edges:
            self._edges = self._edges[-(self.max_edges):]


@dataclass
class InsightForgeResult:
    """InsightForge result (mirrors zep_tools.py InsightForgeResult)"""
    query: str
    sub_queries: List[str]
    semantic_facts: List[str] = field(default_factory=list)
    entity_insights: List[Dict] = field(default_factory=list)
    relationship_chains: List[str] = field(default_factory=list)
    total_facts: int = 0
    total_entities: int = 0
    total_relationships: int = 0

    def to_text(self) -> str:
        parts = [f"InsightForge — {self.query}",
                 f"Facts: {self.total_facts} | Entities: {self.total_entities}"]
        if self.semantic_facts:
            parts.append("Key facts: " + "; ".join(self.semantic_facts[:3]))
        if self.entity_insights:
            parts.append("Entities: " + ", ".join(
                e.get("name", "") for e in self.entity_insights[:3]))
        return " | ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Individual Swarm Agents — Full MiroFish Agent Profile System
# ─────────────────────────────────────────────────────────────────────────────

class TrendAgent:
    """
    Trend Analysis Agent.
    EMA multi-alignment (9/21/50/200) + slope + crossover detection.
    Votes non-NEUTRAL whenever EMAs have directional bias.
    """
    NAME = "TrendAgent"
    PROFILE = AgentProfile(
        agent_id=1,
        name="TrendAgent",
        persona="Systematic trend follower. Multi-EMA alignment + slope + crossover specialist.",
        stance="trend_follower",
        activity_level=0.92,
        influence_weight=0.22,
        sentiment_bias=0.0,
        response_delay_min=50,
        response_delay_max=200,
        active_sessions=["ASIAN", "EU", "US", "TRANSITION"],
        session_multipliers={"ASIAN": 0.90, "EU": 1.10, "US": 1.15, "TRANSITION": 0.60}
    )

    def analyze(self, closes: List[float], params: dict,
                graph: MarketGraphMemory) -> Tuple[str, float]:
        try:
            if len(closes) < params["ema_slow"] + 5:
                return "NEUTRAL", 50.0

            fast, slow = params["ema_fast"], params["ema_slow"]
            ema_fast   = _ema(closes, fast)
            ema_slow   = _ema(closes, slow)
            if ema_fast is None or ema_slow is None:
                return "NEUTRAL", 50.0

            ema_50  = _ema(closes, 50)  if len(closes) >= 55  else None
            ema_200 = _ema(closes, 200) if len(closes) >= 210 else None

            prev_fast = _ema(closes[:-1], fast)
            prev_slow = _ema(closes[:-1], slow)
            if prev_fast is None or prev_slow is None:
                return "NEUTRAL", 50.0

            crossover_up   = prev_fast <= prev_slow and ema_fast > ema_slow
            crossover_down = prev_fast >= prev_slow and ema_fast < ema_slow

            cur = closes[-1]

            # Multi-EMA alignment score (0-4): use None-safe checks so missing
            # EMA50/200 history contributes 0 rather than a biased comparison.
            bullish_count = sum([
                ema_fast > ema_slow,
                (cur > ema_50)  if ema_50  is not None else False,
                (cur > ema_200) if ema_200 is not None else False,
                (ema_50 > ema_200) if (ema_50 is not None and ema_200 is not None) else False,
            ])
            bearish_count = sum([
                ema_fast < ema_slow,
                (cur < ema_50)  if ema_50  is not None else False,
                (cur < ema_200) if ema_200 is not None else False,
                (ema_50 < ema_200) if (ema_50 is not None and ema_200 is not None) else False,
            ])

            # EMA spread as confidence indicator
            spread_pct = abs(ema_fast - ema_slow) / ema_slow * 100
            spread_mult = 10.0 if fast <= 10 else 7.0

            # EMA slope (fast EMA trending direction)
            ema_fast_prev2 = _ema(closes[:-2], fast) if len(closes) > fast + 2 else ema_fast
            slope_up   = ema_fast > (ema_fast_prev2 or ema_fast)
            slope_down = ema_fast < (ema_fast_prev2 or ema_fast)

            if ema_fast >= ema_slow:
                base = 55.0 + min(spread_pct * spread_mult, 30.0)
                # EMA alignment bonuses
                base += bullish_count * 3.5
                if crossover_up: base = min(base + 12, 100)
                if slope_up:     base = min(base + 5,  100)
                # Rising 3-candle sequence
                if len(closes) >= 4 and closes[-1] > closes[-2] > closes[-3]:
                    base = min(base + 4, 100)
                vote, conf = "BUY", min(base, 95.0)
            else:
                base = 55.0 + min(spread_pct * spread_mult, 30.0)
                base += bearish_count * 3.5
                if crossover_down: base = min(base + 12, 100)
                if slope_down:     base = min(base + 5,  100)
                if len(closes) >= 4 and closes[-1] < closes[-2] < closes[-3]:
                    base = min(base + 4, 100)
                vote, conf = "SELL", min(base, 95.0)

            # Ichimoku Tenkan/Kijun crossover — additional trend confirmation
            # Requires at least 26 candles (kijun period) plus some history
            if len(closes) >= 30:
                try:
                    # Build highs/lows proxy from closes for Ichimoku (best effort)
                    # Actual OHLC passed to _analyze_timeframe; here we approximate from closes
                    _ten_val, _kij_val = _tenkan_kijun(closes, closes, closes, 9, 26)
                    if _ten_val is not None and _kij_val is not None:
                        if vote == "BUY"  and _ten_val > _kij_val: conf = min(conf + 6, 100)
                        if vote == "SELL" and _ten_val < _kij_val: conf = min(conf + 6, 100)
                        if vote == "BUY"  and _ten_val < _kij_val: conf = max(conf - 4, 50)
                        if vote == "SELL" and _ten_val > _kij_val: conf = max(conf - 4, 50)
                except Exception:
                    pass

            # Graph memory: confirm with stored TrendState
            trend_state = graph.get_trend_state()
            if trend_state:
                if vote == "BUY"  and "bullish" in trend_state.lower(): conf = min(conf + 5, 100)
                elif vote == "SELL" and "bearish" in trend_state.lower(): conf = min(conf + 5, 100)

            # Update graph TrendState node
            label = "bullish" if vote == "BUY" else "bearish"
            graph.add_node(
                MarketEntityType.TREND_STATE,
                f"TrendState_{vote}",
                f"EMA{fast}/{slow} {label} | spread={spread_pct:.3f}% align={bullish_count if vote=='BUY' else bearish_count}/4",
                {"ema_fast": ema_fast, "ema_slow": ema_slow,
                 "above_200": (cur > ema_200) if ema_200 is not None else None,
                 "alignment": bullish_count}
            )
            return vote, conf

        except Exception:
            return "NEUTRAL", 50.0


class MomentumAgent:
    """
    Momentum Analysis Agent.
    RSI (with slope) + MACD histogram + Stochastic proxy.
    Narrow dead-zone (49-51 only). Non-NEUTRAL whenever RSI has directional bias.
    """
    NAME = "MomentumAgent"
    PROFILE = AgentProfile(
        agent_id=2,
        name="MomentumAgent",
        persona="Aggressive momentum trader. RSI slope + MACD histogram + Stochastic. Buys strength.",
        stance="momentum",
        activity_level=0.93,
        influence_weight=0.20,
        sentiment_bias=0.05,
        response_delay_min=30,
        response_delay_max=150,
        active_sessions=["EU", "US", "TRANSITION"],
        session_multipliers={"ASIAN": 0.80, "EU": 1.15, "US": 1.20, "TRANSITION": 0.55}
    )

    def analyze(self, closes: List[float], graph: MarketGraphMemory) -> Tuple[str, float]:
        try:
            if len(closes) < 35:
                return "NEUTRAL", 50.0

            rsi = _rsi(closes, 14)
            if rsi is None:
                return "NEUTRAL", 50.0

            # RSI slope: is momentum accelerating?
            rsi_prev = _rsi(closes[:-3], 14)
            rsi_slope_up   = rsi_prev is not None and rsi > rsi_prev
            rsi_slope_down = rsi_prev is not None and rsi < rsi_prev

            macd_line, signal_line = _macd(closes)
            macd_hist = (macd_line - signal_line) if (macd_line is not None and signal_line is not None) else 0.0
            macd_bull  = macd_line > signal_line if macd_line is not None and signal_line is not None else False
            cross_up   = _is_macd_cross_up(closes)
            cross_down = _is_macd_cross_down(closes)

            # Stochastic proxy (RSI of RSI)
            stoch = _stochastic(closes, 14, 3)

            # RSI momentum regime — narrow dead zone 49-51
            if rsi >= 70:
                # Overbought
                vote, conf = "SELL", min(60.0 + (rsi - 70) * 1.8, 92.0)
                if rsi_slope_down: conf = min(conf + 5, 95)
            elif rsi <= 30:
                # Oversold
                vote, conf = "BUY", min(60.0 + (30 - rsi) * 1.8, 92.0)
                if rsi_slope_up: conf = min(conf + 5, 95)
            elif rsi > 55:
                # Bullish momentum zone
                base = 54.0 + (rsi - 50) * 0.9
                if macd_bull:      base = min(base + 9, 100)
                if cross_up:       base = min(base + 10, 100)
                if rsi_slope_up:   base = min(base + 5, 100)
                if stoch and stoch > 50: base = min(base + 4, 100)
                vote, conf = "BUY", min(base, 92.0)
            elif rsi < 45:
                # Bearish momentum zone
                base = 54.0 + (50 - rsi) * 0.9
                if not macd_bull:    base = min(base + 9, 100)
                if cross_down:       base = min(base + 10, 100)
                if rsi_slope_down:   base = min(base + 5, 100)
                if stoch and stoch < 50: base = min(base + 4, 100)
                vote, conf = "SELL", min(base, 92.0)
            elif 51 <= rsi <= 55:
                # Mild bullish bias
                base = 52.0 + (rsi - 50) * 0.6
                if macd_bull: base = min(base + 6, 100)
                vote, conf = "BUY", min(base, 70.0)
            elif 45 <= rsi <= 49:
                # Mild bearish bias
                base = 52.0 + (50 - rsi) * 0.6
                if not macd_bull: base = min(base + 6, 100)
                vote, conf = "SELL", min(base, 70.0)
            else:
                # True dead zone (49-51)
                vote, conf = "NEUTRAL", 50.0

            # Histogram momentum bonus — normalised to % of price so it is
            # asset-price-independent (e.g. BTC at $70k vs a $0.01 alt-coin).
            # Multiplier capped at 25 (was 50) to prevent extreme boosts on
            # low-price alts where tiny absolute histograms produce large pct values.
            if macd_hist and vote != "NEUTRAL" and closes[-1] > 0:
                norm_hist = abs(macd_hist) / closes[-1] * 100   # dimensionless %
                hist_boost = min(norm_hist * 25, 8.0)           # hard cap at +8 pts
                if vote == "BUY"  and macd_hist > 0: conf = min(conf + hist_boost, 95.0)
                if vote == "SELL" and macd_hist < 0: conf = min(conf + hist_boost, 95.0)

            # Williams %R — additional overbought/oversold confirmation
            wr = _williams_r(closes, 14)
            if wr is not None and vote != "NEUTRAL":
                if vote == "BUY"  and wr < -80:  conf = min(conf + 4, 95.0)  # oversold
                if vote == "SELL" and wr > -20:  conf = min(conf + 4, 95.0)  # overbought

            # Rate of Change (10-bar) — momentum strength confirmation
            roc = _roc(closes, 10)
            if roc is not None and vote != "NEUTRAL":
                if vote == "BUY"  and roc > 0: conf = min(conf + min(abs(roc) * 2, 5), 95.0)
                if vote == "SELL" and roc < 0: conf = min(conf + min(abs(roc) * 2, 5), 95.0)

            # RSI bearish divergence: price making new high but RSI lower (hidden weakness)
            if len(closes) >= 20:
                rsi_3bars_ago = _rsi(closes[:-3], 14)
                if rsi_3bars_ago is not None:
                    price_new_high = closes[-1] > max(closes[-20:-1])
                    price_new_low  = closes[-1] < min(closes[-20:-1])
                    if vote == "BUY"  and price_new_low  and rsi > rsi_3bars_ago:
                        conf = min(conf + 5, 95.0)   # bullish divergence
                    if vote == "SELL" and price_new_high and rsi < rsi_3bars_ago:
                        conf = min(conf + 5, 95.0)   # bearish divergence

            regime = "overbought" if rsi >= 70 else "oversold" if rsi <= 30 else f"rsi={rsi:.1f}"
            graph.add_node(
                MarketEntityType.INDICATOR_STATE,
                "RSI_State",
                f"RSI={rsi:.1f} ({regime}) MACD={'bull' if macd_bull else 'bear'} hist={(macd_hist or 0.0):.4f}",
                {"rsi": rsi, "macd_hist": macd_hist, "rsi_slope": "up" if rsi_slope_up else "down"}
            )
            return vote, conf

        except Exception:
            return "NEUTRAL", 50.0


class VolumeAgent:
    """
    Volume Analysis Agent.
    OBV trend (primary) + CMF + volume surge amplification.
    Non-NEUTRAL when OBV has a directional trend — much more active.
    """
    NAME = "VolumeAgent"
    PROFILE = AgentProfile(
        agent_id=3,
        name="VolumeAgent",
        persona="Institutional volume tracker. OBV trend + CMF + volume surge specialist.",
        stance="neutral",
        activity_level=0.90,
        influence_weight=0.18,
        sentiment_bias=0.0,
        response_delay_min=100,
        response_delay_max=300,
        active_sessions=["EU", "US", "TRANSITION"],
        session_multipliers={"ASIAN": 0.70, "EU": 1.10, "US": 1.25, "TRANSITION": 0.50}
    )

    def analyze(self, closes: List[float], volumes: List[float],
                graph: MarketGraphMemory,
                highs: Optional[List[float]] = None,
                lows: Optional[List[float]] = None) -> Tuple[str, float]:
        try:
            if len(closes) < 20 or len(volumes) < 20:
                return "NEUTRAL", 50.0

            n = min(len(closes), len(volumes))
            c, v = closes[-n:], volumes[-n:]
            h = highs[-n:] if (highs and len(highs) >= n) else None
            l = lows[-n:]  if (lows  and len(lows)  >= n) else None
            obv_vals = _obv(c, v)

            # OBV trend: compare OBV with its own EMA as primary signal
            obv_ema_short = _ema(obv_vals, 10)
            obv_ema_long  = _ema(obv_vals, 20)
            obv_rising    = (obv_ema_short is not None and obv_ema_long is not None
                             and obv_ema_short > obv_ema_long)
            obv_falling   = (obv_ema_short is not None and obv_ema_long is not None
                             and obv_ema_short < obv_ema_long)

            # OBV momentum: recent OBV vs older OBV
            obv_mom_bull = len(obv_vals) >= 10 and obv_vals[-1] > obv_vals[-10]
            obv_mom_bear = len(obv_vals) >= 10 and obv_vals[-1] < obv_vals[-10]

            # Volume surge
            avg_vol = sum(v[-20:-1]) / 19 if len(v) >= 20 else sum(v) / len(v)
            vol_ratio = v[-1] / avg_vol if avg_vol > 0 else 1.0

            price_up   = c[-1] > c[-2]
            price_down = c[-1] < c[-2]

            # True CMF — uses real OHLC highs/lows when available
            cmf = _cmf(c, v, period=14, highs=h, lows=l)

            # Determine vote based on OBV trend (primary) + surge amplification
            if obv_rising and obv_mom_bull:
                base = 57.0
                if cmf and cmf > 0:     base = min(base + cmf * 80, 100)
                if price_up:            base = min(base + 6, 100)
                if vol_ratio > 1.5:     base = min(base + min((vol_ratio - 1.5) * 15, 18), 100)
                elif vol_ratio > 1.2:   base = min(base + 5, 100)
                vote, conf = "BUY", min(base, 90.0)
            elif obv_falling and obv_mom_bear:
                base = 57.0
                if cmf and cmf < 0:     base = min(base + abs(cmf) * 80, 100)
                if price_down:          base = min(base + 6, 100)
                if vol_ratio > 1.5:     base = min(base + min((vol_ratio - 1.5) * 15, 18), 100)
                elif vol_ratio > 1.2:   base = min(base + 5, 100)
                vote, conf = "SELL", min(base, 90.0)
            elif vol_ratio > 1.5 and price_up:
                # Pure surge signal when OBV ambiguous
                vote, conf = "BUY", min(60.0 + (vol_ratio - 1.5) * 12, 82.0)
            elif vol_ratio > 1.5 and price_down:
                vote, conf = "SELL", min(60.0 + (vol_ratio - 1.5) * 12, 82.0)
            elif obv_rising:
                vote, conf = "BUY", 54.0
            elif obv_falling:
                vote, conf = "SELL", 54.0
            else:
                vote, conf = "NEUTRAL", 50.0

            # VWAP deviation as additional directional confirmation
            if len(c) >= 20 and len(v) >= 20:
                try:
                    vwap_sum_v = max(sum(v[-20:]), 1e-9)
                    vwap = sum(c[i] * v[i] for i in range(-20, 0)) / vwap_sum_v
                    if vwap > 0:
                        vwap_dev = (c[-1] - vwap) / vwap * 100
                        if vote == "BUY"  and vwap_dev > 0:  conf = min(conf + 3, 90.0)
                        if vote == "SELL" and vwap_dev < 0:  conf = min(conf + 3, 90.0)
                        if vote == "BUY"  and vwap_dev < -1.5: conf = max(conf - 5, 50.0)  # price below VWAP weakens BUY
                        if vote == "SELL" and vwap_dev > 1.5:  conf = max(conf - 5, 50.0)  # price above VWAP weakens SELL
                except Exception:
                    pass

            # Catalyst node on large surge
            if vol_ratio > 2.0:
                direction = "bullish" if price_up else "bearish"
                graph.add_node(
                    MarketEntityType.CATALYST, "VolumeCatalyst",
                    f"Volume spike {vol_ratio:.1f}x avg — {direction} catalyst",
                    {"vol_ratio": vol_ratio, "direction": direction}
                )
            return vote, conf

        except Exception:
            return "NEUTRAL", 50.0


class VolatilityAgent:
    """
    Volatility Regime Agent.
    BB %B position (continuous) + ATR regime + Keltner squeeze detection.
    Uses BB%B for directional bias — non-NEUTRAL when price has BB position bias.
    """
    NAME = "VolatilityAgent"
    PROFILE = AgentProfile(
        agent_id=4,
        name="VolatilityAgent",
        persona="Volatility regime specialist. BB%B position, ATR regime, Keltner squeeze detector.",
        stance="contrarian",
        activity_level=0.88,
        influence_weight=0.15,
        sentiment_bias=-0.05,
        response_delay_min=80,
        response_delay_max=250,
        active_sessions=["ASIAN", "EU", "US", "TRANSITION"],
        session_multipliers={"ASIAN": 1.00, "EU": 1.00, "US": 1.10, "TRANSITION": 0.65}
    )

    def analyze(self, closes: List[float], highs: List[float],
                lows: List[float],
                graph: MarketGraphMemory) -> Tuple[str, float, float]:
        try:
            if len(closes) < 25:
                return "NEUTRAL", 50.0, 0.0

            # True ATR (uses high/low/prev_close)
            atr_val = ((_true_atr(closes, highs, lows, 14) if (highs and lows) else None)
                       or _atr_close(closes, 14) or 0.0)

            upper, mid, lower = _bollinger(closes, 20, 2.0)
            if upper is None or mid is None or lower is None:
                return "NEUTRAL", 50.0, atr_val

            cur  = closes[-1]
            prev = closes[-2]

            # BB %B: price position within bands (0=at lower, 1=at upper, >1=above upper)
            bb_range = upper - lower
            bb_pct_b = (cur - lower) / bb_range if bb_range > 0 else 0.5

            # BB width for squeeze detection
            bb_width = bb_range / mid if mid > 0 else 0

            # ATR percentile (high = expansion, low = contraction)
            recent_trs = [abs(closes[i] - closes[i-1]) for i in range(-20, 0)]
            atr_pct = sum(1 for x in recent_trs if x < atr_val) / len(recent_trs) if recent_trs else 0.5

            # ATR trend (expanding = trend continuation).
            # Compare two same-length 14-bar windows: the most recent 14 candles
            # vs the preceding 14 candles.  Using the full series for atr_now vs a
            # shorter slice for atr_prev produced incompatible Wilder-smoothed values.
            if len(closes) >= 28:
                atr_now  = _atr_close(closes[-14:], 7)
                atr_prev = _atr_close(closes[-28:-14], 7)
            else:
                atr_now  = _atr_close(closes, 7)
                atr_prev = atr_now
            atr_expanding = (atr_now and atr_prev and atr_now > atr_prev * 1.05)

            # Primary signal: BB %B position
            if bb_pct_b >= 1.0:
                # Price above upper band: strong trend signal (or overbought in range)
                pct_above = (cur - upper) / upper * 100
                vote, conf = "BUY", min(62.0 + pct_above * 8, 90.0)
            elif bb_pct_b <= 0.0:
                # Price below lower band
                pct_below = (lower - cur) / lower * 100
                vote, conf = "SELL", min(62.0 + pct_below * 8, 90.0)
            elif bb_pct_b > 0.65:
                # Upper half — bullish pressure
                base = 54.0 + (bb_pct_b - 0.5) * 55
                vote, conf = "BUY", min(base, 82.0)
            elif bb_pct_b < 0.35:
                # Lower half — bearish pressure
                base = 54.0 + (0.5 - bb_pct_b) * 55
                vote, conf = "SELL", min(base, 82.0)
            elif cur > mid and prev <= mid:
                # Mid-band crossover up
                vote, conf = "BUY", 60.0
            elif cur < mid and prev >= mid:
                # Mid-band crossover down
                vote, conf = "SELL", 60.0
            elif bb_pct_b > 0.5:
                vote, conf = "BUY", 52.5
            elif bb_pct_b < 0.5:
                vote, conf = "SELL", 52.5
            else:
                vote, conf = "NEUTRAL", 50.0

            # ATR expansion confirms trend continuation
            if atr_expanding and vote != "NEUTRAL":
                conf = min(conf + 5, 95.0)

            # ATR percentile boost
            if atr_pct > 0.75 and vote != "NEUTRAL":
                conf = min(conf + 4, 95.0)

            # ADX — trend-strength filter using the pre-built _adx() helper.
            # ADX >= 25 = trending market → boost directional conviction.
            # ADX <  20 = ranging market  → temper over-confident calls.
            try:
                adx = _adx(closes, highs, lows, 14) if (highs and lows) else None
                if adx is not None and vote != "NEUTRAL":
                    if adx >= 25:
                        adx_boost = min((adx - 25) / 10.0, 6.0)  # up to +6 pts
                        conf = min(conf + adx_boost, 95.0)
                    elif adx < 20:
                        conf = max(conf - 3.0, 50.0)              # -3 pts in ranging
            except Exception:
                pass

            # Price levels in graph
            graph.add_node(MarketEntityType.PRICE_LEVEL, "BB_Upper",
                           f"BB upper: {upper:.2f} (bb_width={bb_width:.4f})",
                           {"level": upper, "bb_width": bb_width})
            graph.add_node(MarketEntityType.PRICE_LEVEL, "BB_Lower",
                           f"BB lower: {lower:.2f} bb_pct_b={bb_pct_b:.3f}",
                           {"level": lower, "bb_pct_b": bb_pct_b})
            return vote, conf, atr_val

        except Exception:
            return "NEUTRAL", 50.0, 0.0


class OrderFlowAgent:
    """
    Order Flow / Price Action Agent.
    Engulfing, hammer/star, 3-candle sequence, close position, wick analysis.
    Scores are additive — generates directional signals more consistently.
    """
    NAME = "OrderFlowAgent"
    PROFILE = AgentProfile(
        agent_id=5,
        name="OrderFlowAgent",
        persona="Price action purist. Multi-pattern scoring: engulfing, candle structure, pressure.",
        stance="neutral",
        activity_level=0.88,
        influence_weight=0.15,
        sentiment_bias=0.0,
        response_delay_min=20,
        response_delay_max=100,
        active_sessions=["ASIAN", "EU", "US", "TRANSITION"],
        session_multipliers={"ASIAN": 0.90, "EU": 1.05, "US": 1.10, "TRANSITION": 0.60}
    )

    def analyze(self, opens: List[float], highs: List[float],
                lows: List[float], closes: List[float],
                graph: MarketGraphMemory) -> Tuple[str, float]:
        try:
            if len(closes) < 5:
                return "NEUTRAL", 50.0

            c, o, h, l = closes, opens, highs, lows
            score = 0.0
            patterns_detected = []

            # ── Candlestick patterns ──
            # Bullish/Bearish engulfing
            if c[-1] > o[-1] and c[-2] < o[-2] and c[-1] > o[-2] and o[-1] < c[-2]:
                score += 22; patterns_detected.append("bullish_engulfing")
            elif c[-1] < o[-1] and c[-2] > o[-2] and c[-1] < o[-2] and o[-1] > c[-2]:
                score -= 22; patterns_detected.append("bearish_engulfing")

            # Hammer / Shooting star
            candle_range = h[-1] - l[-1]
            if candle_range > 0:
                body       = abs(c[-1] - o[-1])
                upper_wick = h[-1] - max(c[-1], o[-1])
                lower_wick = min(c[-1], o[-1]) - l[-1]
                if body > 0:
                    if lower_wick > body * 2 and upper_wick < body:
                        score += 16; patterns_detected.append("hammer")
                    elif upper_wick > body * 2 and lower_wick < body:
                        score -= 16; patterns_detected.append("shooting_star")

                # Close pressure (where did price close in candle range)
                close_pos = (c[-1] - l[-1]) / candle_range
                if close_pos > 0.75:   score += 12
                elif close_pos > 0.6:  score += 6
                elif close_pos < 0.25: score -= 12
                elif close_pos < 0.4:  score -= 6

                # Wick rejection
                if lower_wick > candle_range * 0.45: score += 8  # Strong lower wick rejection
                if upper_wick > candle_range * 0.45: score -= 8  # Strong upper wick rejection

            # Three-candle sequences
            if c[-1] > c[-2] > c[-3]:
                score += 10; patterns_detected.append("three_rising")
            elif c[-1] < c[-2] < c[-3]:
                score -= 10; patterns_detected.append("three_falling")

            # Five-candle trend
            if len(c) >= 6 and all(c[-i] > c[-i-1] for i in range(1, 5)):
                score += 8; patterns_detected.append("five_bar_rally")
            elif len(c) >= 6 and all(c[-i] < c[-i-1] for i in range(1, 5)):
                score -= 8; patterns_detected.append("five_bar_decline")

            # Inside bar — candle fully within prior candle's range (consolidation before breakout)
            if h[-1] < h[-2] and l[-1] > l[-2]:
                # Inside bar: direction determined by prior trend
                if c[-2] > o[-2]:   score += 7; patterns_detected.append("inside_bar_bull")
                else:               score -= 7; patterns_detected.append("inside_bar_bear")

            # Outside bar / engulfing range — current bar engulfs previous by range
            if h[-1] > h[-2] and l[-1] < l[-2]:
                if c[-1] > o[-1]:   score += 12; patterns_detected.append("outside_bar_bull")
                else:               score -= 12; patterns_detected.append("outside_bar_bear")

            # Tweezer top / bottom
            if abs(h[-1] - h[-2]) / max(h[-1], h[-2], 1e-9) < 0.001:
                score -= 8; patterns_detected.append("tweezer_top")
            elif abs(l[-1] - l[-2]) / max(l[-1], l[-2], 1e-9) < 0.001:
                score += 8; patterns_detected.append("tweezer_bottom")

            # Morning/Evening star simplified
            if len(c) >= 3 and o[-3] and c[-3]:
                if (c[-3] < o[-3] and                              # Bearish bar
                    abs(c[-2] - o[-2]) < abs(c[-3] - o[-3]) * 0.3 and  # Small middle
                    c[-1] > o[-1] and c[-1] > (o[-3] + c[-3]) / 2):    # Bullish close
                    score += 18; patterns_detected.append("morning_star")
                elif (c[-3] > o[-3] and
                      abs(c[-2] - o[-2]) < abs(c[-3] - o[-3]) * 0.3 and
                      c[-1] < o[-1] and c[-1] < (o[-3] + c[-3]) / 2):
                    score -= 18; patterns_detected.append("evening_star")

            # Doji reduces conviction
            if candle_range > 0 and abs(c[-1] - o[-1]) / candle_range < 0.08:
                score *= 0.65

            # Update graph
            if patterns_detected:
                direction = "bullish" if score > 0 else "bearish"
                graph.add_node(
                    MarketEntityType.PATTERN,
                    f"CandlePattern_{patterns_detected[0]}",
                    f"{', '.join(patterns_detected)} — {direction} | score={score:.1f}",
                    {"patterns": patterns_detected, "score": score}
                )

            if score > 0:
                return "BUY",  min(52.0 + abs(score) * 0.85, 92.0)
            elif score < 0:
                return "SELL", min(52.0 + abs(score) * 0.85, 92.0)
            return "NEUTRAL", 50.0

        except Exception:
            return "NEUTRAL", 50.0


class SentimentAgent:
    """
    Market Sentiment Agent.
    Multi-EMA alignment score (price vs 9/21/50) + deviation regime + momentum.
    Much lower thresholds — votes consistently with trend regime.
    """
    NAME = "SentimentAgent"
    PROFILE = AgentProfile(
        agent_id=6,
        name="SentimentAgent",
        persona="Market regime detector. Multi-EMA price alignment + sentiment momentum.",
        stance="contrarian",
        activity_level=0.80,
        influence_weight=0.05,
        sentiment_bias=-0.1,
        response_delay_min=200,
        response_delay_max=500,
        active_sessions=["US", "TRANSITION"],
        session_multipliers={"ASIAN": 0.60, "EU": 0.80, "US": 1.30, "TRANSITION": 0.50}
    )

    def analyze(self, closes: List[float],
                graph: MarketGraphMemory) -> Tuple[str, float]:
        try:
            if len(closes) < 50:
                return "NEUTRAL", 50.0

            cur = closes[-1]

            # Multi-EMA price alignment (0-3 scale)
            _e9  = _ema(closes, 9);  ema_9  = _e9  if _e9  is not None else cur
            _e21 = _ema(closes, 21); ema_21 = _e21 if _e21 is not None else cur
            _e50 = _ema(closes, 50); ema_50 = _e50 if _e50 is not None else cur

            above_9  = cur > ema_9
            above_21 = cur > ema_21
            above_50 = cur > ema_50

            bull_score = int(above_9) + int(above_21) + int(above_50)
            bear_score = int(not above_9) + int(not above_21) + int(not above_50)

            # Mean deviation as secondary signal
            mean_50 = sum(closes[-50:]) / 50 if closes else 0.0
            dev_pct  = (cur - mean_50) / mean_50 * 100 if mean_50 != 0 else 0.0

            # Vol contraction → breakout potential
            vol_10 = sum(abs(closes[i] - closes[i-1]) for i in range(-10, 0)) / 10
            vol_30 = sum(abs(closes[i] - closes[i-1]) for i in range(-30, 0)) / 30
            vol_contracting = vol_10 < vol_30 * 0.75

            # Primary signal from EMA alignment
            if bull_score == 3:
                base = 62.0 + min(dev_pct * 1.5, 15.0) if dev_pct > 0 else 62.0
                if vol_contracting: base = min(base + 6, 100)
                vote, conf = "BUY", min(base, 88.0)
            elif bull_score == 2:
                vote, conf = "BUY", 58.0 + (5 if vol_contracting else 0)
            elif bear_score == 3:
                base = 62.0 + min(abs(dev_pct) * 1.5, 15.0) if dev_pct < 0 else 62.0
                if vol_contracting: base = min(base + 6, 100)
                vote, conf = "SELL", min(base, 88.0)
            elif bear_score == 2:
                vote, conf = "SELL", 58.0 + (5 if vol_contracting else 0)
            else:
                # Mixed alignment (bull=1, bear=2 or vice versa)
                if dev_pct > 1.5:
                    vote, conf = "BUY", 53.0
                elif dev_pct < -1.5:
                    vote, conf = "SELL", 53.0
                else:
                    vote, conf = "NEUTRAL", 50.0

            # Register sentiment state in graph memory (mirrors all other agents)
            ema_align_str = f"bull_score={bull_score}/3 bear_score={bear_score}/3"
            graph.add_node(
                MarketEntityType.INDICATOR_STATE,
                "Sentiment_State",
                f"EMA alignment: {ema_align_str} dev={dev_pct:+.2f}% vol_contract={vol_contracting}",
                {"bull_score": bull_score, "bear_score": bear_score,
                 "dev_pct": dev_pct, "vol_contracting": vol_contracting}
            )
            return vote, conf

        except Exception:
            return "NEUTRAL", 50.0


class FundingFlowAgent:
    """
    Funding Rate / Open Interest Agent — UNIQUE TO FUTURES MARKET.
    Uses real funding rate if available, otherwise uses VWAP + OI proxy.
    Lower thresholds and expanded signal range for 5M trading.
    """
    NAME = "FundingFlowAgent"
    PROFILE = AgentProfile(
        agent_id=7,
        name="FundingFlowAgent",
        persona="Futures derivatives specialist. Funding rate, VWAP deviation, OI squeeze detector.",
        stance="contrarian",
        activity_level=0.82,
        influence_weight=0.05,
        sentiment_bias=0.0,
        response_delay_min=150,
        response_delay_max=400,
        active_sessions=["ASIAN", "EU", "US", "TRANSITION"],
        session_multipliers={"ASIAN": 1.00, "EU": 1.00, "US": 1.05, "TRANSITION": 0.65}
    )

    def analyze(self, closes: List[float], volumes: List[float],
                graph: MarketGraphMemory,
                funding_rate: float = None) -> Tuple[str, float]:
        try:
            if len(closes) < 30 or len(volumes) < 30:
                return "NEUTRAL", 50.0

            n = min(len(closes), len(volumes))
            c, v = closes[-n:], volumes[-n:]

            # VWAP deviation as funding proxy
            vwap_sum_v = max(sum(v[-20:]), 1e-9)
            vwap = sum(c[i] * v[i] for i in range(-20, 0)) / vwap_sum_v
            vwap = max(vwap, 1e-9)  # guard against near-zero prices causing ZeroDivisionError
            vwap_dev = (c[-1] - vwap) / vwap * 100  # positive = price above VWAP = bullish

            # OI proxy: sustained volume trend (rising vol = rising OI pressure)
            vol_ema_short = _ema(v, 8)
            vol_ema_long  = _ema(v, 20)
            oi_rising = (vol_ema_short and vol_ema_long and vol_ema_short > vol_ema_long)

            # Price momentum for context
            price_mom = (c[-1] - c[-10]) / c[-10] * 100 if (len(c) >= 10 and c[-10] != 0) else 0.0

            # Real funding rate takes precedence
            if funding_rate is not None:
                if funding_rate > 0.0005:
                    # Positive funding = longs pay shorts = overcrowded longs
                    # Squeeze risk = SELL bias
                    conf = min(58.0 + funding_rate * 50000, 85.0)
                    vote = "SELL"
                elif funding_rate < -0.0005:
                    # Negative funding = shorts pay longs = overcrowded shorts
                    conf = min(58.0 + abs(funding_rate) * 50000, 85.0)
                    vote = "BUY"
                else:
                    # Neutral funding — use VWAP
                    vote, conf = self._vwap_signal(vwap_dev, oi_rising, price_mom)
            else:
                vote, conf = self._vwap_signal(vwap_dev, oi_rising, price_mom)

            # Store VWAP in graph
            _fr_str = f"{funding_rate:.6f}" if funding_rate is not None else "n/a"
            graph.add_node(
                MarketEntityType.INDICATOR_STATE, "VWAP_State",
                f"VWAP={vwap:.6g} dev={vwap_dev:+.2f}% OI={'rising' if oi_rising else 'falling'} fund={_fr_str}",
                {"vwap": vwap, "dev_pct": vwap_dev, "oi_rising": oi_rising}
            )
            return vote, conf

        except Exception:
            return "NEUTRAL", 50.0

    @staticmethod
    def _vwap_signal(vwap_dev: float, oi_rising: bool,
                     price_mom: float) -> Tuple[str, float]:
        # Squeeze: extreme VWAP deviation + rising OI = squeeze imminent
        if vwap_dev > 2.0 and oi_rising:
            return "SELL", min(60.0 + vwap_dev * 3, 84.0)  # Long squeeze
        elif vwap_dev < -2.0 and oi_rising:
            return "BUY", min(60.0 + abs(vwap_dev) * 3, 84.0)  # Short squeeze
        elif vwap_dev > 0.8:
            # Price comfortably above VWAP = bullish
            base = 55.0 + vwap_dev * 2.5
            if price_mom > 0: base = min(base + 4, 100)
            return "BUY", min(base, 80.0)
        elif vwap_dev < -0.8:
            base = 55.0 + abs(vwap_dev) * 2.5
            if price_mom < 0: base = min(base + 4, 100)
            return "SELL", min(base, 80.0)
        elif vwap_dev > 0.3:
            return "BUY", 53.0
        elif vwap_dev < -0.3:
            return "SELL", 53.0
        else:
            return "NEUTRAL", 50.0


# ─────────────────────────────────────────────────────────────────────────────
# AI Orchestration Agent — ReACT Pattern
# ─────────────────────────────────────────────────────────────────────────────

class AIOrchestrationAgent:
    """
    AI Orchestration Agent implementing MiroFish ReACT pattern.
    Reason → Act (InsightForge) → Reflect → Conclude.

    AI Priority:
      1. Claude (Anthropic) claude-3-5-haiku-20241022  — primary (fastest, cheapest, smart)
      2. OpenAI GPT-4o-mini                            — secondary fallback
      3. Rule-based consensus analysis                 — final fallback (always available)
    """
    NAME = "AIOrchestrationAgent"
    PROFILE = AgentProfile(
        agent_id=8,
        name="AIOrchestrationAgent",
        persona="Senior quantitative analyst. ReACT: Reason-Act-Reflect-Conclude. Claude 3.5 Haiku primary + GPT-4o-mini + rule fallback.",
        stance="neutral",
        activity_level=0.92,
        influence_weight=0.05,
        sentiment_bias=0.0,
        response_delay_min=300,
        response_delay_max=1500,
        active_sessions=["ASIAN", "EU", "US", "TRANSITION"],
        session_multipliers={"ASIAN": 1.00, "EU": 1.00, "US": 1.05, "TRANSITION": 0.65}
    )

    # Claude model — fast, highly capable, cost-effective for trading signals
    _CLAUDE_MODEL  = "claude-3-5-haiku-20241022"
    _OPENAI_MODEL  = "gpt-4o-mini"
    _AI_TIMEOUT    = 10.0   # seconds — hard timeout for any AI call
    _MAX_TOKENS    = 256    # sufficient for the structured JSON response

    def __init__(self):
        self.logger = logging.getLogger(__name__ + ".AIOrchestrationAgent")
        self.claude_client = None
        self.openai_client = None
        self._react_log: deque = deque(maxlen=50)
        self._claude_err_count  = 0
        self._openai_err_count  = 0
        # Set True when Claude is permanently disabled (e.g. no credits, invalid key)
        self._claude_disabled   = False
        self._init_claude()
        self._init_openai()

    # ── Client initialisation ────────────────────────────────────────────────

    def _init_claude(self):
        """Initialise the Anthropic AsyncAnthropic client (non-blocking)."""
        try:
            import anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
            if api_key:
                self.claude_client = anthropic.AsyncAnthropic(api_key=api_key)
                self.logger.info(
                    f"✅ AIOrchestrationAgent: Claude ({self._CLAUDE_MODEL}) ready — primary AI"
                )
            else:
                self.logger.info("ℹ️  AIOrchestrationAgent: No ANTHROPIC_API_KEY — Claude disabled")
        except ImportError:
            self.logger.info("ℹ️  AIOrchestrationAgent: anthropic package not found — Claude disabled")
        except Exception as e:
            self.logger.debug(f"Claude init error: {e}")

    def _init_openai(self):
        """Initialise the AsyncOpenAI client as fallback."""
        try:
            from openai import AsyncOpenAI
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if api_key:
                self.openai_client = AsyncOpenAI(api_key=api_key)
                self.logger.info(
                    f"✅ AIOrchestrationAgent: OpenAI ({self._OPENAI_MODEL}) ready — secondary fallback"
                )
            else:
                self.logger.info("ℹ️  AIOrchestrationAgent: No OPENAI_API_KEY — OpenAI fallback disabled")
        except Exception as e:
            self.logger.debug(f"OpenAI init error: {e}")

    # ── Shared prompt builder ────────────────────────────────────────────────

    @staticmethod
    def _build_prompt(symbol: str, timeframe: str, session: str,
                      cur_price: float, chg_1h: float, votes_summary: str,
                      buy_votes: int, sell_votes: int,
                      graph_context: str) -> str:
        return (
            f"You are a professional quantitative crypto futures trader using ReACT reasoning.\n"
            f"Symbol: {symbol} | Timeframe: {timeframe} | Session: {session}\n"
            f"Current price: ${cur_price:,.4g} | 1h change: {chg_1h:+.2f}%\n"
            f"Swarm agent votes: {votes_summary}\n"
            f"Buy votes: {buy_votes} | Sell votes: {sell_votes}\n"
            f"Graph memory: {graph_context}\n\n"
            f"REASON: What does the market context indicate?\n"
            f"ACT: What is the most probable next {timeframe} move?\n"
            f"REFLECT: Any conflicting signals reducing confidence?\n"
            f"CONCLUDE: Final trading signal.\n\n"
            f"Reply ONLY as valid JSON (no markdown, no extra text):\n"
            f"{{\"reason\": \"<1 sentence>\", \"act\": \"<1 sentence>\", "
            f"\"reflect\": \"<1 sentence>\", "
            f"\"vote\": \"BUY\"|\"SELL\"|\"NEUTRAL\", "
            f"\"confidence\": 50-95, \"narrative\": \"<concise reason>\"}}"
        )

    @staticmethod
    def _parse_ai_response(content: str) -> Optional[dict]:
        """Extract and parse JSON from AI response — handles markdown code fences."""
        # Strip markdown code fences if present
        content = re.sub(r"```(?:json)?\s*", "", content).strip()
        match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            return None

    # ── Claude query ─────────────────────────────────────────────────────────

    async def _query_claude(self, prompt: str) -> Optional[dict]:
        """Send prompt to Claude; return parsed dict or None on any error."""
        if self.claude_client is None or self._claude_disabled:
            return None
        try:
            coro = self.claude_client.messages.create(
                model=self._CLAUDE_MODEL,
                max_tokens=self._MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
            response = await asyncio.wait_for(coro, timeout=self._AI_TIMEOUT)
            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
            data = self._parse_ai_response(text.strip())
            if data:
                self._claude_err_count = 0
            return data
        except asyncio.TimeoutError:
            self._claude_err_count += 1
            if self._claude_err_count <= 3:
                self.logger.warning("⏱ Claude timeout — falling back to OpenAI")
            return None
        except Exception as e:
            self._claude_err_count += 1
            err_str = str(e)
            # Detect permanent billing / permission errors — disable Claude immediately
            _permanent_phrases = (
                "credit balance is too low",
                "insufficient_quota",
                "billing",
                "payment",
                "access denied",
                "permission denied",
                "your account",
            )
            if any(p in err_str.lower() for p in _permanent_phrases):
                if not self._claude_disabled:
                    self._claude_disabled = True
                    self.logger.warning(
                        "💳 Claude disabled — insufficient API credits. "
                        "Add credits at console.anthropic.com to re-enable. "
                        "Falling back to OpenAI + rule-based permanently."
                    )
                return None
            if self._claude_err_count <= 5:
                self.logger.warning(
                    f"⚠️ Claude {type(e).__name__} (#{self._claude_err_count}): {err_str[:200]}"
                )
            return None

    # ── OpenAI query ─────────────────────────────────────────────────────────

    async def _query_openai(self, prompt: str) -> Optional[dict]:
        """Send prompt to OpenAI; return parsed dict or None on any error."""
        if self.openai_client is None:
            return None
        try:
            response = await asyncio.wait_for(
                self.openai_client.chat.completions.create(
                    model=self._OPENAI_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=self._MAX_TOKENS,
                    temperature=0.20,
                ),
                timeout=self._AI_TIMEOUT,
            )
            text = response.choices[0].message.content.strip()
            data = self._parse_ai_response(text)
            if data:
                self._openai_err_count = 0
            return data
        except asyncio.TimeoutError:
            self._openai_err_count += 1
            if self._openai_err_count <= 3:
                self.logger.warning("⏱ OpenAI timeout — falling back to rule-based")
            return None
        except Exception as e:
            self._openai_err_count += 1
            if self._openai_err_count <= 3:
                self.logger.debug(f"OpenAI error: {type(e).__name__}: {e}")
            return None

    # ── Main ReACT loop ──────────────────────────────────────────────────────

    async def analyze(self, symbol: str, closes: List[float],
                      agent_summary: dict, timeframe: str,
                      graph: MarketGraphMemory,
                      session: str) -> Tuple[str, float, str, str]:
        react_trace = []

        # ── REASON: build shared context ──
        cur_price = closes[-1] if closes else 0.0
        # Correct 1-hour lookback per timeframe (off-by-one was here before):
        # N=5 for 15m means closes[-5]→closes[-1] = 4 bars = 60 min exactly
        _tf_1h_candles = {"1m": 61, "3m": 21, "5m": 13, "15m": 5, "30m": 3, "1h": 2, "4h": 2}
        _lookback_1h   = _tf_1h_candles.get(timeframe, 5)
        chg_1h = (
            (closes[-1] - closes[-_lookback_1h]) / closes[-_lookback_1h] * 100
            if len(closes) >= _lookback_1h and closes[-_lookback_1h] != 0 else 0.0
        )
        votes_summary = ", ".join(
            f"{k}: {v['vote']}({v['conf']:.0f}%)" for k, v in agent_summary.items()
        )
        buy_votes  = sum(1 for v in agent_summary.values() if v["vote"] == "BUY")
        sell_votes = sum(1 for v in agent_summary.values() if v["vote"] == "SELL")
        insight       = graph.insight_forge(f"{symbol} {timeframe} trading signal", n_facts=5)
        graph_context = insight.to_text()

        react_trace.append({
            "step": "REASON",
            "observation": (
                f"Price={cur_price:.4g}, 1h_chg={chg_1h:+.2f}%, "
                f"session={session}, agents=[{votes_summary}]"
            ),
            "graph_insight": graph_context,
            "buy_votes": buy_votes,
            "sell_votes": sell_votes,
        })

        # Build the shared prompt once — used by both AI providers
        prompt = self._build_prompt(
            symbol, timeframe, session, cur_price, chg_1h,
            votes_summary, buy_votes, sell_votes, graph_context
        )

        # ── ACT: Claude (primary) ──
        ai_source = None
        data = await self._query_claude(prompt)
        if data:
            ai_source = f"Claude/{self._CLAUDE_MODEL}"
        else:
            # ── ACT: OpenAI (secondary fallback) ──
            data = await self._query_openai(prompt)
            if data:
                ai_source = f"OpenAI/{self._OPENAI_MODEL}"

        if data:
            vote        = data.get("vote", "NEUTRAL").upper().strip()
            conf        = float(data.get("confidence", 50))
            narrative   = str(data.get("narrative", ""))
            reason_txt  = str(data.get("reason", ""))
            act_txt     = str(data.get("act", ""))
            reflect_txt = str(data.get("reflect", ""))

            if vote not in ("BUY", "SELL", "NEUTRAL"):
                vote = "NEUTRAL"
            conf = max(50.0, min(float(conf), 95.0))

            react_trace.append({
                "step": "ACT", "source": ai_source,
                "reason": reason_txt, "act": act_txt,
                "reflect": reflect_txt, "vote": vote, "confidence": conf
            })

            # ── REFLECT: swarm consistency check ──
            swarm_dir   = ("BUY" if buy_votes > sell_votes
                           else ("SELL" if sell_votes > buy_votes else "NEUTRAL"))
            total_active = buy_votes + sell_votes
            if total_active > 0 and vote != "NEUTRAL" and vote != swarm_dir:
                conf = max(conf * 0.85, 50.0)   # never drop below floor
                react_trace.append({
                    "step": "REFLECT",
                    "adjustment": f"{ai_source} ({vote}) contradicts swarm ({swarm_dir}), -15% conf"
                })

            self._react_log.append(react_trace)
            return vote, conf, narrative, json.dumps(react_trace[-3:])

        # ── Final fallback: deterministic rule-based analysis ──
        vote, conf, narrative = self._rule_based_analysis(agent_summary, closes, chg_1h)
        react_trace.append({
            "step": "FALLBACK", "vote": vote, "conf": conf,
            "reason": "Rule-based: all AI providers unavailable"
        })
        return vote, conf, narrative, json.dumps(react_trace)

    @staticmethod
    def _rule_based_analysis(agent_summary: dict, closes: List[float],
                              chg_1h: float) -> Tuple[str, float, str]:
        """
        Comprehensive rule-based AI fallback when OpenAI is unavailable.
        Aggregates agent votes with confidence weighting.
        """
        buy_confs  = [v["conf"] for v in agent_summary.values() if v["vote"] == "BUY"]
        sell_confs = [v["conf"] for v in agent_summary.values() if v["vote"] == "SELL"]
        n_buy  = len(buy_confs)
        n_sell = len(sell_confs)
        n_total = len(agent_summary)

        if n_buy == 0 and n_sell == 0:
            return "NEUTRAL", 50.0, "No agent consensus"

        # Weight-adjusted aggregate confidence
        avg_buy_conf  = sum(buy_confs)  / n_buy  if n_buy  else 0
        avg_sell_conf = sum(sell_confs) / n_sell if n_sell else 0

        # Score: number × avg confidence
        buy_score  = n_buy  * avg_buy_conf
        sell_score = n_sell * avg_sell_conf

        if buy_score > sell_score and n_buy >= 1:
            participation = (n_buy + n_sell) / n_total
            conf = avg_buy_conf * 0.65 + 50 * 0.35
            conf += participation * 12
            if chg_1h > 0.5: conf = min(conf + 5, 95)
            narrative = (f"Rule-based: {n_buy}/{n_total} agents BUY "
                         f"(avg_conf={avg_buy_conf:.1f}%, 1h={chg_1h:+.2f}%)")
            return "BUY", min(conf, 90.0), narrative

        elif sell_score > buy_score and n_sell >= 1:
            participation = (n_buy + n_sell) / n_total
            conf = avg_sell_conf * 0.65 + 50 * 0.35
            conf += participation * 12
            if chg_1h < -0.5: conf = min(conf + 5, 95)
            narrative = (f"Rule-based: {n_sell}/{n_total} agents SELL "
                         f"(avg_conf={avg_sell_conf:.1f}%, 1h={chg_1h:+.2f}%)")
            return "SELL", min(conf, 90.0), narrative

        return "NEUTRAL", 50.0, "Balanced signals — no edge"


# ─────────────────────────────────────────────────────────────────────────────
# MiroFish Swarm Strategy — Main Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class MiroFishSwarmStrategy:
    """
    MiroFish Multi-Agent Swarm Intelligence Strategy for BTCUSDT USDM Futures.
    Strictly based on github.com/666ghj/MiroFish architecture.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        self.timeframes     = ["15m"]
        self.primary_timeframe = "15m"

        # Pre-boost signal gates — calibrated for quality over quantity
        self.min_signal_strength = 62.0     # raised: require stronger pre-boost signal
        self.min_confidence      = 64.0     # raised: require solid agent agreement
        self.min_swarm_consensus = 0.72     # raised: ≥72% weighted consensus (was 62%)
        self.min_active_agents   = 5        # raised: quorum needs 5/8 agents non-NEUTRAL (was 3)
        self.min_rr_ratio        = 1.50     # raised: minimum 1.5:1 risk-reward (was 1.30)

        # ── Initialize all 8 agents ──
        self.trend_agent      = TrendAgent()
        self.momentum_agent   = MomentumAgent()
        self.volume_agent     = VolumeAgent()
        self.volatility_agent = VolatilityAgent()
        self.orderflow_agent  = OrderFlowAgent()
        self.sentiment_agent  = SentimentAgent()
        self.funding_agent    = FundingFlowAgent()
        self.ai_agent         = AIOrchestrationAgent()

        self._agents = [
            self.trend_agent, self.momentum_agent, self.volume_agent,
            self.volatility_agent, self.orderflow_agent, self.sentiment_agent,
            self.funding_agent, self.ai_agent,
        ]

        # ── Per-symbol Market Knowledge Graphs ──
        # Each symbol gets its own isolated graph so scans don't contaminate
        # each other's TrendState / RSI_State / VWAP_State nodes.
        self._symbol_graphs: Dict[str, MarketGraphMemory] = {}

        # ── Session state ──
        self._current_session  = "UNKNOWN"
        self._session_activity = 1.0

        self.logger.info("🐟 MiroFish Swarm Strategy v3.1 initialized — BTCUSDT USDM Futures")
        self.logger.info("   Architecture: Profiles+Ontology+Graph+InsightForge+ReACT+Sessions")
        self.logger.info(f"   Agents: {len(self._agents)} | Quorum: {self.min_active_agents} | "
                         f"Consensus gate: {self.min_swarm_consensus:.0%}")

    # ─────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────

    async def generate_multi_timeframe_signals(
        self, trader, symbol: str = "BTCUSDT"
    ) -> List[SwarmSignal]:
        """
        Generate swarm signals with full MiroFish pipeline for any USDM symbol.

        Args:
            trader: BTCUSDTTrader instance (provides kline/funding data)
            symbol: USDM futures symbol, e.g. "ETHUSDT", "BTCUSDT"

        Returns:
            Sorted list of SwarmSignals (best first by consensus × confidence)
        """
        signals = []
        self._current_session, self._session_activity = get_current_market_session()
        self.logger.debug(
            f"[{symbol}] Session: {self._current_session} (activity={self._session_activity:.2f})"
        )

        # Try to fetch live funding rate for this symbol — extract float from dict
        funding_rate = None
        try:
            if hasattr(trader, "get_funding_rate"):
                fr_raw = await asyncio.wait_for(
                    trader.get_funding_rate(symbol), timeout=3.0
                )
                if isinstance(fr_raw, dict):
                    funding_rate = float(fr_raw.get("fundingRate", 0) or 0)
                elif isinstance(fr_raw, (int, float)):
                    funding_rate = float(fr_raw)
        except Exception as _fr_err:
            self.logger.debug(f"[{symbol}] Funding rate fetch skipped: {_fr_err}")

        # ── Per-symbol isolated graph (prevents cross-symbol node contamination) ──
        if symbol not in self._symbol_graphs:
            self._symbol_graphs[symbol] = MarketGraphMemory(max_nodes=200, max_edges=400)
            # Cap to 120 tracked symbols to bound memory.
            # BUG FIX: `next(iter(...))` evicted the first-inserted symbol, which
            # is BTCUSDT (always added first).  Skip BTCUSDT when evicting so the
            # most important market is never silently dropped from memory.
            if len(self._symbol_graphs) > 120:
                for _evict_sym in list(self._symbol_graphs.keys()):
                    if _evict_sym != "BTCUSDT":
                        del self._symbol_graphs[_evict_sym]
                        break
        sym_graph = self._symbol_graphs[symbol]

        for tf in self.timeframes:
            try:
                params = BTCUSDT_PARAMS.get(tf, BTCUSDT_PARAMS["5m"])
                limit  = min(params["min_candles"] + 50, 1000)
                klines = await trader.get_market_data(symbol, tf, limit)

                if klines is None or len(klines) < params["min_candles"]:
                    self.logger.debug(
                        f"[{symbol}] ⚠️ Insufficient data for {tf}: "
                        f"{len(klines) if klines else 0}"
                    )
                    continue

                signal = await self._analyze_timeframe(
                    klines, tf, params, funding_rate, symbol, sym_graph
                )
                if signal:
                    signals.append(signal)

            except Exception as e:
                self.logger.warning(f"[{symbol}] ⚠️ Error scanning {tf}: {e}")
                continue

        signals.sort(key=lambda s: (s.swarm_consensus, s.confidence), reverse=True)
        return signals

    # ─────────────────────────────────────────
    # Core Analysis Pipeline
    # ─────────────────────────────────────────

    async def _analyze_timeframe(self, klines: List, tf: str, params: dict,
                                  funding_rate: float = None,
                                  symbol: str = "BTCUSDT",
                                  graph: "MarketGraphMemory" = None) -> Optional[SwarmSignal]:
        if graph is None:
            # Fallback: create a temporary graph (should not normally happen)
            graph = MarketGraphMemory(max_nodes=100, max_edges=200)
        try:
            opens   = [float(k[1]) for k in klines]
            highs   = [float(k[2]) for k in klines]
            lows    = [float(k[3]) for k in klines]
            closes  = [float(k[4]) for k in klines]
            volumes = [float(k[5]) for k in klines]

            if len(closes) < 50:
                return None

            # ── Micro-price filter: skip coins priced below $0.0001 ──
            # These generate precision noise and unmeaningful TP/SL distances
            cur_price_check = closes[-1]
            if cur_price_check < 0.0001:
                self.logger.debug(
                    f"⚠️ [{symbol}|{tf}] Price ${cur_price_check:.8f} < $0.0001 "
                    f"— micro-price filtered"
                )
                return None

            session = self._current_session

            # ── Step 1: Run all deterministic agents ──
            trend_vote, trend_conf = self.trend_agent.analyze(closes, params, graph)

            momentum_vote, momentum_conf = self.momentum_agent.analyze(closes, graph)

            volume_vote, volume_conf = self.volume_agent.analyze(
                closes, volumes, graph, highs=highs, lows=lows
            )

            # VolatilityAgent: pass highs/lows for true ATR
            vol_vote, vol_conf, atr = self.volatility_agent.analyze(
                closes, highs, lows, graph
            )

            of_vote, of_conf = self.orderflow_agent.analyze(
                opens, highs, lows, closes, graph
            )

            sent_vote, sent_conf = self.sentiment_agent.analyze(closes, graph)

            funding_vote, funding_conf = self.funding_agent.analyze(
                closes, volumes, graph, funding_rate
            )

            # ── Step 2: Build base agent votes ──
            base_votes = {
                "TrendAgent":       {"vote": trend_vote,    "conf": trend_conf},
                "MomentumAgent":    {"vote": momentum_vote, "conf": momentum_conf},
                "VolumeAgent":      {"vote": volume_vote,   "conf": volume_conf},
                "VolatilityAgent":  {"vote": vol_vote,      "conf": vol_conf},
                "OrderFlowAgent":   {"vote": of_vote,       "conf": of_conf},
                "SentimentAgent":   {"vote": sent_vote,     "conf": sent_conf},
                "FundingFlowAgent": {"vote": funding_vote,  "conf": funding_conf},
            }

            # ── Step 3: AI Orchestration (ReACT) ──
            try:
                ai_vote, ai_conf, ai_narrative, react_trace = await asyncio.wait_for(
                    self.ai_agent.analyze(
                        symbol, closes, base_votes, tf, graph, session
                    ),
                    timeout=10.0
                )
            except (asyncio.TimeoutError, Exception):
                ai_vote, ai_conf, ai_narrative, react_trace = "NEUTRAL", 50.0, "", ""

            all_votes = dict(base_votes)
            all_votes["AIOrchestrationAgent"] = {"vote": ai_vote, "conf": ai_conf}

            # ── Step 4: Session-aware weighted consensus ──
            agent_profiles = {
                "TrendAgent":           self.trend_agent.PROFILE,
                "MomentumAgent":        self.momentum_agent.PROFILE,
                "VolumeAgent":          self.volume_agent.PROFILE,
                "VolatilityAgent":      self.volatility_agent.PROFILE,
                "OrderFlowAgent":       self.orderflow_agent.PROFILE,
                "SentimentAgent":       self.sentiment_agent.PROFILE,
                "FundingFlowAgent":     self.funding_agent.PROFILE,
                "AIOrchestrationAgent": self.ai_agent.PROFILE,
            }

            buy_weight  = 0.0
            sell_weight = 0.0
            effective_weights = {}

            for name, data in all_votes.items():
                profile = agent_profiles.get(name)
                eff_w   = profile.effective_weight(session) if profile else 0.05
                effective_weights[name] = eff_w
                if data["vote"] == "BUY":
                    buy_weight  += eff_w * (data["conf"] / 100.0)
                elif data["vote"] == "SELL":
                    sell_weight += eff_w * (data["conf"] / 100.0)

            total_eff = sum(effective_weights.values())
            if total_eff > 0:
                buy_weight  /= total_eff
                sell_weight /= total_eff

            total_signal_weight = buy_weight + sell_weight
            if total_signal_weight < 0.005:
                return None

            # ── Quorum check ──
            active_votes = [(n, d) for n, d in all_votes.items() if d["vote"] != "NEUTRAL"]
            n_active = len(active_votes)
            if n_active < self.min_active_agents:
                self.logger.debug(f"⚠️ Quorum not met: {n_active}/{len(all_votes)} agents active")
                return None

            # ── Consensus ──
            if buy_weight >= sell_weight:
                action    = "BUY"
                consensus = buy_weight / total_signal_weight
            else:
                action    = "SELL"
                consensus = sell_weight / total_signal_weight

            if consensus < self.min_swarm_consensus:
                self.logger.debug(f"⚠️ Weak consensus {consensus:.2f} — skipped")
                return None

            # ── Step 5: Confidence calculation with participation scoring ──
            aligned_agents  = [(n, d, effective_weights.get(n, 0.05))
                               for n, d in all_votes.items() if d["vote"] == action]
            contrary_agents = [(n, d, effective_weights.get(n, 0.05))
                               for n, d in all_votes.items()
                               if d["vote"] != action and d["vote"] != "NEUTRAL"]

            total_aligned_w = sum(w for _, _, w in aligned_agents)
            if total_aligned_w > 0:
                weighted_conf = sum(d["conf"] * w for _, d, w in aligned_agents) / total_aligned_w
            else:
                weighted_conf = 50.0

            # Participation bonus/penalty
            n_aligned  = len(aligned_agents)
            n_contrary = len(contrary_agents)
            participation_rate = n_active / len(all_votes)

            if participation_rate >= 0.625:    # ≥5 agents active
                participation_bonus = (participation_rate - 0.5) * 30
                weighted_conf = min(weighted_conf + participation_bonus, 100.0)
            elif participation_rate < 0.375:   # <3 agents active
                participation_penalty = (0.375 - participation_rate) * 25
                weighted_conf = max(weighted_conf - participation_penalty, 50.0)

            # Contrary agent divergence penalty
            if contrary_agents:
                contrary_w_sum = sum(w for _, _, w in contrary_agents)
                aligned_w_sum  = sum(w for _, _, w in aligned_agents)
                divergence = contrary_w_sum / max(aligned_w_sum, 0.01)
                if divergence > 0.4:
                    weighted_conf *= (1.0 - divergence * 0.15)

            # Session activity boost
            session_boost = (self._session_activity - 1.0) * 6.0
            weighted_conf = min(max(weighted_conf + session_boost, 0.0), 100.0)

            signal_strength = min(weighted_conf * 0.55 + consensus * 100 * 0.45, 100.0)
            confidence = weighted_conf

            if signal_strength < self.min_signal_strength or confidence < self.min_confidence:
                return None

            # ── Step 6: InsightForge market context ──
            insight          = graph.insight_forge(f"{symbol} {action} signal", n_facts=5)
            graph_insight_txt = insight.to_text()

            # ── Step 7: ATR-based price levels ──
            cur_price = closes[-1]
            sl_pct  = params["sl_pct"]  / 100
            tp1_pct = params["tp1_pct"] / 100
            tp2_pct = params["tp2_pct"] / 100
            tp3_pct = params["tp3_pct"] / 100

            # ── Hard caps: SL ≤ 3%, TP3 ≤ 15% of entry price
            #    This prevents absurdly wide levels for highly volatile alts.
            _MAX_SL_PCT  = 0.03
            _MAX_TP3_PCT = 0.15

            if atr and atr > 0:
                # ATR-scaled SL/TP — all levels use the same ATR multiplier base
                # so TP1 < TP2 < TP3 (LONG) is always preserved
                atr_sl_mult = 1.5
                _sl_ratio = sl_pct if sl_pct > 0 else 1.0  # guard against zero sl_pct
                sl_dist  = max(atr * atr_sl_mult,                              cur_price * sl_pct)
                tp1_dist = max(atr * atr_sl_mult * (tp1_pct / _sl_ratio),     cur_price * tp1_pct)
                tp2_dist = max(atr * atr_sl_mult * (tp2_pct / _sl_ratio),     cur_price * tp2_pct)
                tp3_dist = max(atr * atr_sl_mult * (tp3_pct / _sl_ratio),     cur_price * tp3_pct)
            else:
                sl_dist  = cur_price * sl_pct
                tp1_dist = cur_price * tp1_pct
                tp2_dist = cur_price * tp2_pct
                tp3_dist = cur_price * tp3_pct
                atr = cur_price * 0.003

            # Apply caps to prevent unrealistic levels for volatile alts
            sl_dist  = min(sl_dist,  cur_price * _MAX_SL_PCT)
            tp3_dist = min(tp3_dist, cur_price * _MAX_TP3_PCT)
            tp2_dist = min(tp2_dist, cur_price * _MAX_TP3_PCT * 0.65)
            tp1_dist = min(tp1_dist, cur_price * _MAX_TP3_PCT * 0.35)

            # Enforce minimum TP1 distance: at least 1.0% move required from entry
            # This prevents near-zero TP signals on tiny-ATR coins
            min_tp1_dist = cur_price * 0.010
            tp1_dist = max(tp1_dist, min_tp1_dist)
            tp2_dist = max(tp2_dist, cur_price * 0.018)
            tp3_dist = max(tp3_dist, cur_price * 0.028)

            # Enforce strict ordering: TP1 < TP2 < TP3 (LONG) or TP1 > TP2 > TP3 (SHORT)
            # Each subsequent TP must be at least 0.3% beyond the previous
            min_tp_gap = cur_price * 0.003
            tp2_dist = max(tp2_dist, tp1_dist + min_tp_gap)
            tp3_dist = max(tp3_dist, tp2_dist + min_tp_gap)

            def _tick(price: float, tick: float = None) -> float:
                """Round price to appropriate precision for the current magnitude."""
                if tick is None:
                    if price >= 10_000:   tick = 0.1
                    elif price >= 1_000:  tick = 0.01
                    elif price >= 100:    tick = 0.001
                    elif price >= 10:     tick = 0.0001
                    elif price >= 1:      tick = 0.00001
                    elif price >= 0.1:    tick = 0.000001
                    elif price >= 0.01:   tick = 0.0000001
                    else:                 tick = 0.00000001
                return round(round(price / tick) * tick, 10)

            if action == "BUY":
                stop_loss   = _tick(cur_price - sl_dist)
                take_profit = _tick(cur_price + tp1_dist)
                tp2         = _tick(cur_price + tp2_dist)
                tp3         = _tick(cur_price + tp3_dist)
                # Safety: SL strictly below entry
                if stop_loss >= cur_price:
                    stop_loss = _tick(cur_price * (1 - sl_pct))
            else:
                stop_loss   = _tick(cur_price + sl_dist)
                take_profit = _tick(cur_price - tp1_dist)
                tp2         = _tick(cur_price - tp2_dist)
                tp3         = _tick(cur_price - tp3_dist)
                # Safety: SL strictly above entry
                if stop_loss <= cur_price:
                    stop_loss = _tick(cur_price * (1 + sl_pct))

            rr = abs(take_profit - cur_price) / abs(stop_loss - cur_price) if abs(stop_loss - cur_price) > 0 else 0

            # High-quality gate: reject weak R:R signals
            if rr < self.min_rr_ratio:
                self.logger.debug(
                    f"⚠️ [{tf}] R:R={rr:.2f} below minimum {self.min_rr_ratio:.2f} — signal rejected"
                )
                return None

            leverage  = LEVERAGE_MAP.get(tf, 15)
            # BUG FIX: `_rsi(...) or 50.0` treats RSI=0.0 as falsy and wrongly
            # maps it to 50.  Use an explicit None check instead.
            _rsi_raw  = _rsi(closes, 14)
            rsi_val   = _rsi_raw if _rsi_raw is not None else 50.0
            _avg_vol  = sum(volumes[-20:-1]) / 19 if len(volumes) >= 20 else 0.0
            vol_ratio = volumes[-1] / _avg_vol if _avg_vol > 0 else 1.0

            # ── Step 8: Update graph signal node ──
            signal_node_id = graph.add_node(
                MarketEntityType.SIGNAL,
                f"Signal_{action}_{tf}_{int(time.time())}",
                f"{action} @ {cur_price:.6g} | consensus={consensus:.0%} conf={confidence:.1f}% part={participation_rate:.0%}",
                {"action": action, "price": cur_price, "consensus": consensus,
                 "tf": tf, "session": session, "n_aligned": n_aligned}
            )
            trend_state_id = graph._find_node_by_name(
                f"TrendState_{action}", MarketEntityType.TREND_STATE
            )
            if trend_state_id:
                graph.add_edge(
                    MarketEdgeType.CONFIRMS, trend_state_id, signal_node_id,
                    f"TrendState confirms {action} @ {cur_price:.6g}"
                )

            agent_summary_str = " ".join(
                n[:4] + ":" + d["vote"][:1] for n, d in all_votes.items()
            )
            self.logger.info(
                f"🐟 [{symbol}|{tf}|{session}] Swarm: {action} @ ${cur_price:,.4g} | "
                f"Consensus={consensus:.0%} Conf={confidence:.1f}% Str={signal_strength:.1f}% "
                f"Part={n_active}/{len(all_votes)} | Agents: {agent_summary_str}"
            )

            return SwarmSignal(
                symbol=symbol,
                action=action,
                entry_price=cur_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                take_profit_1=take_profit,
                take_profit_2=tp2,
                take_profit_3=tp3,
                signal_strength=signal_strength,
                confidence=confidence,
                risk_reward_ratio=rr,
                atr_value=atr,
                timestamp=datetime.now(),
                timeframe=tf,
                leverage=leverage,
                rsi=rsi_val,
                volume_ratio=vol_ratio,
                swarm_consensus=consensus,
                agent_votes={n: d["vote"] for n, d in all_votes.items()},
                ai_narrative=ai_narrative,
                market_session=session,
                graph_insight=graph_insight_txt,
                react_reasoning=react_trace,
                participation_rate=participation_rate,
                crossover_detected=(
                    all_votes.get("TrendAgent", {}).get("vote") == action and
                    trend_conf >= 65.0
                ),
            )

        except Exception as e:
            self.logger.error(f"Error analyzing {tf}: {e}", exc_info=True)
            return None

    def get_market_memory_summary(self) -> dict:
        if not self._symbol_graphs:
            return {"nodes": 0, "edges": 0, "active_edges": 0,
                    "trend_state": None, "recent_signals": 0, "tracked_symbols": 0}
        total_nodes  = sum(len(g._nodes) for g in self._symbol_graphs.values())
        total_edges  = sum(len(g._edges) for g in self._symbol_graphs.values())
        active_edges = sum(sum(1 for e in g._edges if not e.is_invalid)
                          for g in self._symbol_graphs.values())
        # Use BTC graph for narrative trend state, fall back to first available
        ref_graph = (self._symbol_graphs.get("BTCUSDT")
                     or next(iter(self._symbol_graphs.values())))
        return {
            "nodes":           total_nodes,
            "edges":           total_edges,
            "active_edges":    active_edges,
            "trend_state":     ref_graph.get_trend_state(),
            "recent_signals":  len(ref_graph.get_active_signals(10)),
            "tracked_symbols": len(self._symbol_graphs),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Pure-Python Technical Indicator Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ema(data: List[float], period: int) -> Optional[float]:
    if len(data) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(data[:period]) / period
    for price in data[period:]:
        ema = price * k + ema * (1 - k)
    return ema


def _ema_series(data: List[float], period: int) -> Optional[List[float]]:
    if len(data) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(data[:period]) / period
    result = [ema]
    for price in data[period:]:
        ema = price * k + ema * (1 - k)
        result.append(ema)
    return result


def _rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    if len(gains) < period:
        return None
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    rs = avg_gain / avg_loss if avg_loss > 0 else 100.0
    return 100.0 - (100.0 / (1.0 + rs))


def _macd(closes: List[float], fast: int = 12, slow: int = 26,
          signal: int = 9) -> Tuple[Optional[float], Optional[float]]:
    if len(closes) < slow + signal:
        return None, None
    ema_fast_s = _ema_series(closes, fast)
    ema_slow_s = _ema_series(closes, slow)
    if not ema_fast_s or not ema_slow_s:
        return None, None
    # Align both series chronologically (newest at end).
    # ema_slow_s is shorter (slow > fast), so we take the last n elements
    # of ema_fast_s to align with ema_slow_s — both end at the same close.
    n = min(len(ema_fast_s), len(ema_slow_s))
    macd_series = [f - s for f, s in zip(ema_fast_s[-n:], ema_slow_s[-n:])]
    if len(macd_series) < signal:
        return None, None
    sig_line = _ema(macd_series, signal)
    return macd_series[-1], sig_line


def _obv(closes: List[float], volumes: List[float]) -> List[float]:
    obv = [0.0]
    n = min(len(closes), len(volumes))
    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv


def _bollinger(closes: List[float], period: int = 20, std_dev: float = 2.0):
    if len(closes) < period:
        return None, None, None
    window = closes[-period:]
    mid = sum(window) / period
    variance = sum((x - mid) ** 2 for x in window) / period
    sd = variance ** 0.5
    return mid + std_dev * sd, mid, mid - std_dev * sd


def _atr_close(closes: List[float], period: int = 14) -> Optional[float]:
    """ATR using close-to-close (fallback when OHLC unavailable)"""
    if len(closes) < period + 1:
        return None
    trs = [abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def _true_atr(closes: List[float], highs: List[float], lows: List[float],
              period: int = 14) -> Optional[float]:
    """True ATR using OHLC: TR = max(H-L, |H-prev_C|, |L-prev_C|)"""
    if len(closes) < period + 1 or len(highs) < period + 1 or len(lows) < period + 1:
        return _atr_close(closes, period)
    trs = []
    for i in range(1, len(closes)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        trs.append(max(hl, hc, lc))
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def _stochastic(closes: List[float], k_period: int = 14,
                d_period: int = 3) -> Optional[float]:
    """Stochastic %K oscillator"""
    if len(closes) < k_period:
        return None
    window = closes[-k_period:]
    low_k  = min(window)
    high_k = max(window)
    if high_k == low_k:
        return 50.0
    return (closes[-1] - low_k) / (high_k - low_k) * 100


def _cmf(closes: List[float], volumes: List[float],
         period: int = 14,
         highs: Optional[List[float]] = None,
         lows: Optional[List[float]] = None) -> Optional[float]:
    """
    Chaikin Money Flow.

    Uses true OHLC high/low when highs and lows are provided (accurate).
    Falls back to adjacent-close estimation only when OHLC data is absent.
    The close-proxy was the original implementation; it systematically
    underestimates candle range on trending bars and mislabels the money
    flow multiplier direction when the real wick extends beyond either close.
    """
    if len(closes) < period + 1 or len(volumes) < period:
        return None
    use_ohlc = (highs is not None and lows is not None
                and len(highs) >= len(closes) and len(lows) >= len(closes))
    mf_vol_sum = 0.0
    vol_sum = 0.0
    for i in range(-period, 0):
        if use_ohlc:
            hi = highs[i]
            lo = lows[i]
        else:
            hi = max(closes[i], closes[i - 1])
            lo = min(closes[i], closes[i - 1])
        rng = hi - lo
        if rng > 0:
            mf_mult = ((closes[i] - lo) - (hi - closes[i])) / rng
        else:
            mf_mult = 0.0
        mf_vol_sum += mf_mult * volumes[i]
        vol_sum += abs(volumes[i])
    return mf_vol_sum / vol_sum if vol_sum > 0 else 0.0


def _is_macd_cross_up(closes: List[float]) -> bool:
    if len(closes) < 35:
        return False
    prev_m, prev_s = _macd(closes[:-1])
    cur_m,  cur_s  = _macd(closes)
    if None in (prev_m, prev_s, cur_m, cur_s):
        return False
    return prev_m <= prev_s and cur_m > cur_s


def _is_macd_cross_down(closes: List[float]) -> bool:
    if len(closes) < 35:
        return False
    prev_m, prev_s = _macd(closes[:-1])
    cur_m,  cur_s  = _macd(closes)
    if None in (prev_m, prev_s, cur_m, cur_s):
        return False
    return prev_m >= prev_s and cur_m < cur_s


def _williams_r(closes: List[float], period: int = 14) -> Optional[float]:
    """
    Williams %R oscillator — measures overbought/oversold conditions.
    Returns value in range [-100, 0].
    -80 to -100 = oversold (bullish signal zone)
    -20 to 0    = overbought (bearish signal zone)
    """
    if len(closes) < period:
        return None
    window = closes[-period:]
    highest = max(window)
    lowest  = min(window)
    if highest == lowest:
        return -50.0
    return (highest - closes[-1]) / (highest - lowest) * -100.0


def _roc(closes: List[float], period: int = 10) -> Optional[float]:
    """
    Rate of Change — percentage change from N bars ago.
    Positive = upward momentum, negative = downward momentum.
    """
    if len(closes) < period + 1:
        return None
    prev = closes[-(period + 1)]
    if prev == 0:
        return None
    return (closes[-1] - prev) / prev * 100.0


def _adx(closes: List[float], highs: List[float], lows: List[float],
          period: int = 14) -> Optional[float]:
    """
    Average Directional Index (ADX) — trend strength indicator.
    Returns ADX value [0, 100]. Higher = stronger trend.
    <20 = weak/no trend, 20-40 = moderate trend, >40 = strong trend.
    """
    n = min(len(closes), len(highs), len(lows))
    if n < period * 2 + 1:
        return None
    c, h, l = closes[-n:], highs[-n:], lows[-n:]
    try:
        plus_dm, minus_dm, tr_vals = [], [], []
        for i in range(1, len(c)):
            up_move   = h[i] - h[i-1]
            down_move = l[i-1] - l[i]
            plus_dm.append(up_move   if (up_move > down_move and up_move > 0)   else 0.0)
            minus_dm.append(down_move if (down_move > up_move and down_move > 0) else 0.0)
            tr = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
            tr_vals.append(tr)

        def _wilder_smooth(data, p):
            sm = sum(data[:p])
            result = [sm]
            for v in data[p:]:
                sm = sm - (sm / p) + v
                result.append(sm)
            return result

        atr_s    = _wilder_smooth(tr_vals, period)
        pdm_s    = _wilder_smooth(plus_dm, period)
        mdm_s    = _wilder_smooth(minus_dm, period)
        dx_vals  = []
        for i in range(len(atr_s)):
            if atr_s[i] == 0:
                continue
            pdi = 100 * pdm_s[i] / atr_s[i]
            mdi = 100 * mdm_s[i] / atr_s[i]
            denom = pdi + mdi
            if denom == 0:
                continue
            dx_vals.append(100 * abs(pdi - mdi) / denom)

        if len(dx_vals) < period:
            return None
        adx_val = sum(dx_vals[-period:]) / period
        return adx_val
    except Exception:
        return None


def _tenkan_kijun(closes: List[float], highs: List[float], lows: List[float],
                  tenkan: int = 9, kijun: int = 26) -> Tuple[Optional[float], Optional[float]]:
    """
    Ichimoku Cloud: Tenkan-sen (Conversion Line) and Kijun-sen (Base Line).
    Tenkan = (highest_high + lowest_low) / 2 over tenkan periods.
    Kijun  = (highest_high + lowest_low) / 2 over kijun periods.
    Returns (tenkan_val, kijun_val) or (None, None) if insufficient data.
    """
    n = min(len(closes), len(highs), len(lows))
    if n < kijun:
        return None, None
    h, l = highs[-n:], lows[-n:]
    ten_h = max(h[-tenkan:]);  ten_l = min(l[-tenkan:])
    kij_h = max(h[-kijun:]);   kij_l = min(l[-kijun:])
    return (ten_h + ten_l) / 2.0, (kij_h + kij_l) / 2.0


def _hma(closes: List[float], period: int = 14) -> Optional[float]:
    """
    Hull Moving Average — fast, smooth, lag-reduced MA.
    HMA(n) = EMA(2 * EMA(n/2) − EMA(n), sqrt(n))

    Correct implementation: compute the full EMA series for both the half-period
    and full-period, align their lengths, compute the point-wise difference series,
    then take the EMA of that series with sqrt(period).
    """
    if len(closes) < period + 4:
        return None
    half   = max(2, period // 2)
    sqrt_p = max(2, int(period ** 0.5))

    half_series = _ema_series(closes, half)
    full_series = _ema_series(closes, period)
    if half_series is None or full_series is None:
        return None

    # Align series lengths (half_series is longer since half < period)
    n = min(len(half_series), len(full_series))
    diff_series = [
        2.0 * h - f
        for h, f in zip(half_series[-n:], full_series[-n:])
    ]
    if len(diff_series) < sqrt_p:
        return None
    return _ema(diff_series, sqrt_p)
