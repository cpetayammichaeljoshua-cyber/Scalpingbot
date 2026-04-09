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
import math
from collections import deque
import os
import time
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

try:
    from SignalMaestro.smart_llm_router import SmartLLMRouter
except ImportError:
    try:
        from smart_llm_router import SmartLLMRouter
    except ImportError:
        SmartLLMRouter = None

# G0DM0D3 Strategy Engine — Primary AI Layer (github.com/elder-plinius/G0DM0D3)
# ULTRAPLINIAN multi-model racing + AutoTune + STM + GODMODE CLASSIC via OpenRouter
try:
    from SignalMaestro.godmod3_strategy import G0DM0D3Engine, get_godmod3_engine
    _GODMOD3_AVAILABLE = True
except ImportError:
    try:
        from godmod3_strategy import G0DM0D3Engine, get_godmod3_engine
        _GODMOD3_AVAILABLE = True
    except ImportError:
        _GODMOD3_AVAILABLE = False
        G0DM0D3Engine = None  # type: ignore
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
    take_profit_4: float = 0.0
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

    # ── Prediction Market Papers (Shannon / Kelly / Decay) ──────────────────
    shannon_entropy: float = 0.0
    kelly_fraction: float = 0.0
    kelly_decay_factor: float = 1.0

    # ── IRONS AI Score & Indicator Panel ──────────────────────────────────
    irons_score: int = 0
    irons_risk: str = ""
    irons_categories: dict = field(default_factory=dict)
    irons_indicators: dict = field(default_factory=dict)
    irons_patterns: list = field(default_factory=list)
    irons_squeeze: bool = False
    mtf_4h: str = "NEUTRAL"
    mtf_1h: str = "NEUTRAL"

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
        if self.take_profit_4 == 0.0:
            if self.action == "BUY":
                self.take_profit_4 = self.entry_price + (self.take_profit - self.entry_price) * 3.8
            else:
                self.take_profit_4 = self.entry_price - (self.entry_price - self.take_profit) * 3.8


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
            mult = 0.15
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
        influence_weight=0.18,
        sentiment_bias=0.0,
        response_delay_min=50,
        response_delay_max=200,
        active_sessions=["ASIAN", "EU", "US", "TRANSITION"],
        session_multipliers={"ASIAN": 0.90, "EU": 1.10, "US": 1.15, "TRANSITION": 0.60}
    )

    def analyze(self, closes: List[float], params: dict,
                graph: MarketGraphMemory,
                highs: Optional[List[float]] = None,
                lows: Optional[List[float]] = None) -> Tuple[str, float]:
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
                vote, conf = "BUY", min(base, 90.0)
            else:
                base = 55.0 + min(spread_pct * spread_mult, 30.0)
                base += bearish_count * 3.5
                if crossover_down: base = min(base + 12, 95)
                if slope_down:     base = min(base + 5,  95)
                if len(closes) >= 4 and closes[-1] < closes[-2] < closes[-3]:
                    base = min(base + 4, 95)
                vote, conf = "SELL", min(base, 90.0)

            # Ichimoku Tenkan/Kijun crossover — additional trend confirmation
            # Requires at least 26 candles (kijun period) plus some history
            if len(closes) >= 30:
                try:
                    # Use real OHLC highs/lows when available (passed from _analyze_timeframe).
                    # Falls back to closes-as-proxy only when raw OHLC was not provided.
                    _ich_h = highs if (highs and len(highs) >= 30) else closes
                    _ich_l = lows  if (lows  and len(lows)  >= 30) else closes
                    _ten_val, _kij_val = _tenkan_kijun(closes, _ich_h, _ich_l, 9, 26)
                    if _ten_val is not None and _kij_val is not None:
                        if vote == "BUY"  and _ten_val > _kij_val: conf = min(conf + 4, 92)
                        if vote == "SELL" and _ten_val < _kij_val: conf = min(conf + 4, 92)
                        if vote == "BUY"  and _ten_val < _kij_val: conf = max(conf - 4, 50)
                        if vote == "SELL" and _ten_val > _kij_val: conf = max(conf - 4, 50)
                except Exception:
                    pass

            # ── Supertrend confirmation (v4 enhancement) ──────────────────────
            # Supertrend is the strongest single trend filter: when ST is bullish
            # and we vote BUY → strong bonus; if ST contradicts → penalty.
            if highs and lows and len(highs) >= 15:
                try:
                    _st_result = _supertrend(closes, highs, lows, period=10, multiplier=3.0)
                    if _st_result is not None:
                        _st_val, _st_dir = _st_result
                        if vote == "BUY"  and _st_dir == 1:  conf = min(conf + 5, 92)
                        if vote == "SELL" and _st_dir == -1: conf = min(conf + 5, 92)
                        if vote == "BUY"  and _st_dir == -1: conf = max(conf - 10, 50)
                        if vote == "SELL" and _st_dir == 1:  conf = max(conf - 10, 50)
                except Exception:
                    pass

            # ── Parabolic SAR confirmation ─────────────────────────────────────
            if highs and lows and len(highs) >= 5:
                try:
                    _sar_result = _parabolic_sar(highs, lows)
                    if _sar_result is not None:
                        _sar_val, _sar_dir = _sar_result
                        if vote == "BUY"  and _sar_dir == 1:  conf = min(conf + 3, 92)
                        if vote == "SELL" and _sar_dir == -1: conf = min(conf + 3, 92)
                        if vote == "BUY"  and _sar_dir == -1: conf = max(conf - 5, 50)
                        if vote == "SELL" and _sar_dir == 1:  conf = max(conf - 5, 50)
                except Exception:
                    pass

            # ── Full Ichimoku Cloud S/R filter ─────────────────────────────────
            # Price inside the cloud → low-confidence zone (avoid it)
            # Price above cloud for BUY or below for SELL → strong confirmation
            if highs and lows and len(closes) >= 52:
                try:
                    _ich = _ich_cloud(highs, lows, closes)
                    if _ich and _ich.get("cloud_top") and _ich.get("cloud_bot"):
                        _cloud_top = _ich["cloud_top"]
                        _cloud_bot = _ich["cloud_bot"]
                        _cur = closes[-1]
                        if vote == "BUY":
                            if _cur > _cloud_top:   conf = min(conf + 5, 92)   # above cloud: bullish
                            elif _cur < _cloud_bot: conf = max(conf - 8, 50)    # below cloud: bearish
                            else:                   conf = max(conf - 5, 50)    # inside cloud: uncertain
                        elif vote == "SELL":
                            if _cur < _cloud_bot:   conf = min(conf + 5, 92)   # below cloud: bearish
                            elif _cur > _cloud_top: conf = max(conf - 8, 50)    # above cloud: bullish
                            else:                   conf = max(conf - 5, 50)    # inside cloud: uncertain
                except Exception:
                    pass

            # ── Hull Moving Average slope confirmation ────────────────────────
            # HMA is lag-reduced and responsive — its slope gives a clean early
            # trend-direction read that complements the multi-EMA alignment above.
            if len(closes) >= fast + 4:
                try:
                    hma_now  = _hma(closes, fast)
                    hma_prev = _hma(closes[:-2], fast)
                    if hma_now is not None and hma_prev is not None:
                        hma_rising  = hma_now > hma_prev
                        hma_falling = hma_now < hma_prev
                        if vote == "BUY"  and hma_rising:  conf = min(conf + 3, 92)
                        if vote == "SELL" and hma_falling: conf = min(conf + 3, 92)
                        if vote == "BUY"  and hma_falling: conf = max(conf - 3, 50)
                        if vote == "SELL" and hma_rising:  conf = max(conf - 3, 50)
                except Exception:
                    pass

            # Graph memory: confirm with stored TrendState
            trend_state = graph.get_trend_state()
            if trend_state:
                if vote == "BUY"  and "bullish" in trend_state.lower(): conf = min(conf + 3, 92)
                elif vote == "SELL" and "bearish" in trend_state.lower(): conf = min(conf + 3, 92)

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
            return vote, min(conf, 95.0)

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
        influence_weight=0.16,
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
            # Compute the previous-bar MACD once and derive both cross signals inline.
            # This replaces two separate _is_macd_cross_up/down() calls which each
            # internally re-ran _macd(closes[:-1]) AND _macd(closes) — 4 redundant
            # full MACD chain computations that double the cost for every bar of every
            # symbol.  We already have (macd_line, signal_line) from above, so only
            # the previous-bar values need to be fetched here.
            _cross_up = _cross_down = False
            if len(closes) >= 35 and macd_line is not None and signal_line is not None:
                _pm, _ps = _macd(closes[:-1])
                if _pm is not None and _ps is not None:
                    _cross_up   = _pm <= _ps and macd_line > signal_line
                    _cross_down = _pm >= _ps and macd_line < signal_line
            cross_up   = _cross_up
            cross_down = _cross_down

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
                base = 54.0 + (rsi - 50) * 0.9
                if macd_bull:      base = min(base + 8, 90)
                if cross_up:       base = min(base + 8, 90)
                if rsi_slope_up:   base = min(base + 4, 90)
                if stoch and stoch > 50: base = min(base + 3, 90)
                vote, conf = "BUY", min(base, 88.0)
            elif rsi < 45:
                base = 54.0 + (50 - rsi) * 0.9
                if not macd_bull:    base = min(base + 8, 90)
                if cross_down:       base = min(base + 8, 90)
                if rsi_slope_down:   base = min(base + 4, 90)
                if stoch and stoch < 50: base = min(base + 3, 90)
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

            # Multi-period Rate of Change (5/10/20-bar) — momentum strength confirmation
            # Per ML feature-importance analysis: ROC momentum ~38% predictive weight.
            # Composite across three periods for noise-robust momentum direction.
            roc5  = _roc(closes, 5)
            roc10 = _roc(closes, 10)
            roc20 = _roc(closes, 20)
            roc_signals = sum([
                (1 if (roc5  is not None and roc5  > 0) else -1 if (roc5  is not None and roc5  < 0) else 0),
                (1 if (roc10 is not None and roc10 > 0) else -1 if (roc10 is not None and roc10 < 0) else 0),
                (1 if (roc20 is not None and roc20 > 0) else -1 if (roc20 is not None and roc20 < 0) else 0),
            ])
            if vote != "NEUTRAL":
                if vote == "BUY" and roc_signals > 0:
                    conf = min(conf + min(roc_signals * 2.0, 6.0), 95.0)
                elif vote == "SELL" and roc_signals < 0:
                    conf = min(conf + min(abs(roc_signals) * 2.0, 6.0), 95.0)
                elif (vote == "BUY" and roc_signals < -1) or (vote == "SELL" and roc_signals > 1):
                    conf = max(conf - 3.0, 50.0)

            # ── Proper RSI Divergence (v4 — swing-based, not bar-comparison) ─────
            # Uses the _rsi_divergence() helper which identifies swing pivots.
            # Divergence confirmation gives high-quality reversal/continuation signal.
            if len(closes) >= 50:
                try:
                    div_result = _rsi_divergence(closes, period=14, lookback=30)
                    if div_result is not None:
                        div_type, div_strength = div_result
                        if div_type == "bullish":
                            # Bullish divergence: price lower low + RSI higher low = reversal signal
                            if vote == "BUY":  conf = min(conf + int(div_strength * 10), 95.0)  # confirm
                            if vote == "SELL": conf = max(conf - int(div_strength * 8), 50.0)   # contradict
                        elif div_type == "bearish":
                            # Bearish divergence: price higher high + RSI lower high = exhaustion
                            if vote == "SELL": conf = min(conf + int(div_strength * 10), 95.0)  # confirm
                            if vote == "BUY":  conf = max(conf - int(div_strength * 8), 50.0)   # contradict
                except Exception:
                    pass
            else:
                # Fallback for shorter series: simple 3-bar RSI slope comparison
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
        influence_weight=0.15,
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
            avg_vol = sum(v[-21:-1]) / 20 if len(v) >= 21 else (sum(v[:-1]) / (len(v) - 1) if len(v) > 1 else float(v[0]))
            vol_ratio = v[-1] / avg_vol if avg_vol > 0 else 1.0

            price_up   = c[-1] > c[-2]
            price_down = c[-1] < c[-2]

            # True CMF — uses real OHLC highs/lows when available
            cmf = _cmf(c, v, period=14, highs=h, lows=l)

            # Determine vote based on OBV trend (primary) + surge amplification
            if obv_rising and obv_mom_bull:
                base = 57.0
                if cmf and cmf > 0:     base = min(base + cmf * 60, 88)
                if price_up:            base = min(base + 5, 88)
                if vol_ratio > 1.5:     base = min(base + min((vol_ratio - 1.5) * 12, 14), 88)
                elif vol_ratio > 1.2:   base = min(base + 4, 88)
                vote, conf = "BUY", min(base, 88.0)
            elif obv_falling and obv_mom_bear:
                base = 57.0
                if cmf and cmf < 0:     base = min(base + abs(cmf) * 60, 88)
                if price_down:          base = min(base + 5, 88)
                if vol_ratio > 1.5:     base = min(base + min((vol_ratio - 1.5) * 12, 14), 88)
                elif vol_ratio > 1.2:   base = min(base + 4, 88)
                vote, conf = "SELL", min(base, 88.0)
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
        influence_weight=0.12,
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

            # ── Keltner Channel Squeeze (v4 enhancement) ─────────────────────
            # When BB bands are inside KC bands → squeeze is ON → explosive move soon.
            # Direction of breakout determined by current vote.
            # When squeeze fires, it strongly confirms a breakout signal.
            if highs and lows and len(highs) >= 25:
                try:
                    squeeze_result = _squeeze_momentum(closes, highs, lows,
                                                       bb_period=20, kc_period=20,
                                                       kc_atr=14, kc_mult=1.5)
                    if squeeze_result is not None:
                        squeeze_on, sq_momentum = squeeze_result
                        if squeeze_on:
                            # Squeeze detected: breakout imminent — boost if direction aligns
                            if vote == "BUY"  and sq_momentum > 0:
                                conf = min(conf + 9, 95.0)   # squeeze bullish breakout
                            elif vote == "SELL" and sq_momentum < 0:
                                conf = min(conf + 9, 95.0)   # squeeze bearish breakdown
                            elif vote == "BUY"  and sq_momentum < 0:
                                conf = max(conf - 6, 50.0)   # squeeze momentum contra
                            elif vote == "SELL" and sq_momentum > 0:
                                conf = max(conf - 6, 50.0)   # squeeze momentum contra
                        else:
                            # No squeeze — trend mode: small boost for expansion alignment
                            if vote != "NEUTRAL" and sq_momentum != 0:
                                if (vote == "BUY" and sq_momentum > 0) or (vote == "SELL" and sq_momentum < 0):
                                    conf = min(conf + 3, 95.0)
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
        influence_weight=0.12,
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

            _min_conviction = 12
            if abs(score) < _min_conviction:
                return "NEUTRAL", 50.0

            if score > 0:
                return "BUY",  min(52.0 + abs(score) * 0.75, 88.0)
            elif score < 0:
                return "SELL", min(52.0 + abs(score) * 0.75, 88.0)
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
        influence_weight=0.04,
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

            # Contrarian overextension detection
            _overext_buy  = bull_score == 3 and dev_pct > 3.5
            _overext_sell = bear_score == 3 and dev_pct < -3.5

            if _overext_buy:
                vote, conf = "SELL", min(58.0 + abs(dev_pct) * 1.2, 72.0)
            elif _overext_sell:
                vote, conf = "BUY", min(58.0 + abs(dev_pct) * 1.2, 72.0)
            elif bull_score == 3:
                base = 60.0 + min(dev_pct * 1.2, 12.0) if dev_pct > 0 else 60.0
                if vol_contracting: base = min(base + 5, 100)
                vote, conf = "BUY", min(base, 82.0)
            elif bull_score == 2:
                vote, conf = "BUY", 56.0 + (4 if vol_contracting else 0)
            elif bear_score == 3:
                base = 60.0 + min(abs(dev_pct) * 1.2, 12.0) if dev_pct < 0 else 60.0
                if vol_contracting: base = min(base + 5, 100)
                vote, conf = "SELL", min(base, 82.0)
            elif bear_score == 2:
                vote, conf = "SELL", 56.0 + (4 if vol_contracting else 0)
            else:
                if dev_pct > 2.0:
                    vote, conf = "BUY", 53.0
                elif dev_pct < -2.0:
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
        influence_weight=0.04,
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
            return "SELL", min(60.0 + vwap_dev * 2.5, 80.0)
        elif vwap_dev < -2.0 and oi_rising:
            return "BUY", min(60.0 + abs(vwap_dev) * 2.5, 80.0)
        elif vwap_dev > 1.5 and not oi_rising and price_mom < -0.3:
            return "SELL", min(58.0 + vwap_dev * 2, 72.0)
        elif vwap_dev < -1.5 and not oi_rising and price_mom > 0.3:
            return "BUY", min(58.0 + abs(vwap_dev) * 2, 72.0)
        elif vwap_dev > 0.8:
            base = 55.0 + vwap_dev * 2.0
            if price_mom > 0: base = min(base + 3, 100)
            return "BUY", min(base, 76.0)
        elif vwap_dev < -0.8:
            base = 55.0 + abs(vwap_dev) * 2.0
            if price_mom < 0: base = min(base + 3, 100)
            return "SELL", min(base, 76.0)
        elif vwap_dev > 0.4:
            return "BUY", 53.0
        elif vwap_dev < -0.4:
            return "SELL", 53.0
        else:
            return "NEUTRAL", 50.0


# ─────────────────────────────────────────────────────────────────────────────
# Pivot Support/Resistance Agent — v4 New Agent
# ─────────────────────────────────────────────────────────────────────────────

class PivotSRAgent:
    """
    Pivot Support/Resistance Agent — v4 Production Addition.

    Identifies key support/resistance zones using:
    1. Classic Pivot Points (P, R1/R2/R3, S1/S2/S3) — institutional reference levels
    2. Volume Profile POC — highest-volume price level (magnetic S/R)
    3. Price proximity scoring — is current price approaching S/R?
    4. Entry quality score — avoid buying at resistance, selling at support

    Votes BUY when: price is above pivot/POC with clear upward path to next R
    Votes SELL when: price is below pivot/POC with clear downward path to next S
    Penalizes entries directly AT resistance (BUY) or support (SELL)
    """
    NAME = "PivotSRAgent"
    PROFILE = AgentProfile(
        agent_id=9,
        name="PivotSRAgent",
        persona="Institutional S/R specialist. Pivot points + volume profile POC. Avoids S/R traps.",
        stance="neutral",
        activity_level=0.88,
        influence_weight=0.07,
        sentiment_bias=0.0,
        response_delay_min=50,
        response_delay_max=200,
        active_sessions=["ASIAN", "EU", "US", "TRANSITION"],
        session_multipliers={"ASIAN": 0.90, "EU": 1.05, "US": 1.10, "TRANSITION": 0.70}
    )

    # Proximity threshold: price within this % of a pivot level = "at that level"
    _PROX_PCT = 0.35   # 0.35% of price = "at level"
    _NEAR_PCT = 0.75   # 0.75% = "near level" (soft zone)

    def analyze(self, closes: List[float], highs: List[float],
                lows: List[float], volumes: List[float],
                graph: MarketGraphMemory) -> Tuple[str, float]:
        try:
            if len(closes) < 22 or len(highs) < 22 or len(lows) < 22:
                return "NEUTRAL", 50.0

            cur = closes[-1]
            score = 0.0   # positive = bullish, negative = bearish

            # ── Classic Pivot Points ─────────────────────────────────────────
            pivots = _pivot_points(highs, lows, closes)
            if pivots:
                p   = pivots["P"]
                r1  = pivots["R1"]; r2 = pivots["R2"]
                s1  = pivots["S1"]; s2 = pivots["S2"]

                def _prox(level: float) -> float:
                    return abs(cur - level) / max(cur, 1e-9) * 100

                # Price position relative to pivot P
                if cur > p:
                    # Above pivot → bullish bias
                    score += 15.0
                    # Check if approaching R1 (resistance — bad for BUY)
                    if _prox(r1) < self._PROX_PCT:
                        score -= 20.0   # at R1: selling pressure imminent
                    elif _prox(r1) < self._NEAR_PCT:
                        score -= 10.0   # near R1: caution
                    elif cur < r1 * 0.997:
                        score += 10.0   # below R1 with room to run = good BUY zone
                else:
                    # Below pivot → bearish bias
                    score -= 15.0
                    # Check if approaching S1 (support — bad for SELL)
                    if _prox(s1) < self._PROX_PCT:
                        score += 20.0   # at S1: buying pressure imminent
                    elif _prox(s1) < self._NEAR_PCT:
                        score += 10.0   # near S1: caution on shorts
                    elif cur > s1 * 1.003:
                        score -= 10.0   # above S1 with room to fall = good SELL zone

                # Breakout above R1/R2 — momentum signal
                if cur > r1 and cur < r2:
                    score += 18.0   # broken R1, targeting R2 = strong BUY
                elif cur > r2:
                    score += 12.0   # broken R2 = very bullish

                # Breakdown below S1/S2
                if cur < s1 and cur > s2:
                    score -= 18.0   # broken S1, targeting S2 = strong SELL
                elif cur < s2:
                    score -= 12.0   # broken S2 = very bearish

                # Register pivot levels in graph memory
                graph.add_node(
                    MarketEntityType.PRICE_LEVEL, "PivotP",
                    f"Daily Pivot P={p:.4f} R1={r1:.4f} S1={s1:.4f}",
                    {"pivot": p, "r1": r1, "s1": s1, "cur_above_p": cur > p}
                )

            # ── Volume Profile POC ──────────────────────────────────────────
            if len(volumes) >= 20:
                poc = _volume_profile_poc(closes, volumes, n_bins=20)
                if poc is not None:
                    poc_prox = abs(cur - poc) / max(cur, 1e-9) * 100
                    if cur > poc:
                        score += 8.0   # price above POC = buyers in control
                        if poc_prox < self._PROX_PCT:
                            score -= 5.0  # right at POC = neutral/contested
                    else:
                        score -= 8.0   # price below POC = sellers in control
                        if poc_prox < self._PROX_PCT:
                            score += 5.0  # right at POC support = contested

            # ── Convert score to vote ────────────────────────────────────────
            if score >= 30:
                vote, conf = "BUY",  min(62.0 + score * 0.5, 85.0)
            elif score >= 18:
                vote, conf = "BUY",  min(55.0 + score * 0.6, 75.0)
            elif score <= -30:
                vote, conf = "SELL", min(62.0 + abs(score) * 0.5, 85.0)
            elif score <= -18:
                vote, conf = "SELL", min(55.0 + abs(score) * 0.6, 75.0)
            else:
                vote, conf = "NEUTRAL", 50.0

            return vote, min(conf, 90.0)

        except Exception:
            return "NEUTRAL", 50.0


# ─────────────────────────────────────────────────────────────────────────────
# AI Orchestration Agent — ReACT Pattern
# ─────────────────────────────────────────────────────────────────────────────

class AIOrchestrationAgent:
    """
    AI Orchestration Agent implementing MiroFish ReACT pattern + G0DM0D3 AI Strategy.
    Reason → Act (InsightForge) → Reflect → Conclude.

    AI Priority (G0DM0D3-enhanced):
      1. G0DM0D3 ULTRAPLINIAN  — Primary: multi-model racing via OpenRouter (qwen/qwen3.6-plus:free)
                                  GODMODE CLASSIC 5-combo parallel racing as fallback within G0DM0D3
      2. Claude (Anthropic)    — Secondary: claude-sonnet-4-6 cascade
      3. OpenAI GPT-4o-mini    — Tertiary fallback
      4. Rule-based consensus  — Final deterministic fallback (always available)
    """
    NAME = "AIOrchestrationAgent"
    PROFILE = AgentProfile(
        agent_id=8,
        name="AIOrchestrationAgent",
        persona=(
            "G0DM0D3 AI Engine: ULTRAPLINIAN multi-model racing + AutoTune + STM + GODMODE CLASSIC. "
            "Primary: qwen/qwen3.6-plus:free via OpenRouter. "
            "ReACT: Reason-Act(G0DM0D3)-Reflect-Conclude. Fallback: Claude → GPT → Rule-based."
        ),
        stance="neutral",
        activity_level=0.96,
        influence_weight=0.06,
        sentiment_bias=0.0,
        response_delay_min=300,
        response_delay_max=1500,
        active_sessions=["ASIAN", "EU", "US", "TRANSITION"],
        session_multipliers={"ASIAN": 1.00, "EU": 1.00, "US": 1.05, "TRANSITION": 0.65}
    )

    # Claude model cascade — tried in order until one succeeds.
    # ORDER: Claude 4+ / latest models FIRST (user-specified: claude-sonnet-4-6),
    # then 3.x legacy models as fallback.  404-failed models are skipped and added
    # to _claude_failed_models; set clears every _CLAUDE_MODEL_RETRY_INTERVAL secs
    # so newly-provisioned models (e.g. after account upgrade) are auto-discovered.
    _CLAUDE_MODELS = [
        # ── Claude 4 / latest generation (2025-2026) — PRIMARY ───────────────
        "claude-sonnet-4-6",            # Latest: Claude Sonnet 4.6 (user-specified primary)
        "claude-opus-4-5",              # May 2025: Claude Opus 4.5 (highest capability)
        "claude-sonnet-4-5",            # May 2025: Claude Sonnet 4.5
        "claude-haiku-4-5",             # May 2025: Claude Haiku 4.5 (fastest)
        # ── Claude 3.7 / 3.5 — FALLBACK (older plan compatibility) ──────────
        "claude-3-7-sonnet-20250219",   # Feb 2025: Claude 3.7 Sonnet
        "claude-3-5-sonnet-20241022",   # Oct 2024: Claude 3.5 Sonnet
        "claude-3-5-haiku-20241022",    # Oct 2024: Claude 3.5 Haiku
        "claude-3-5-sonnet-20240620",   # Jun 2024: original 3.5 sonnet release
        "claude-3-opus-20240229",       # Feb 2024: Claude 3 Opus
    ]
    # Interval to reset the 404-failed model set — allows recovery when Anthropic
    # provisions new model access on the account without requiring a bot restart.
    # Reduced to 10 min (from 30) so new access is discovered faster.
    _CLAUDE_MODEL_RETRY_INTERVAL = 600.0    # 10 minutes (was 30)
    # OpenAI re-test interval for permanently-disabled state (key may be updated)
    _OPENAI_RETRY_INTERVAL = 14400.0        # 4 hours — re-probe if key was updated
    _OPENAI_MODEL  = "gpt-4o-mini"
    _AI_TIMEOUT    = 25.0   # seconds — hard timeout for any AI call (raised from 15→25)
    _MAX_TOKENS    = 300    # sufficient for the structured JSON response

    def __init__(self):
        self.logger = logging.getLogger(__name__ + ".AIOrchestrationAgent")
        self.claude_client = None
        self.openai_client = None
        self._react_log: deque = deque(maxlen=50)
        self._claude_err_count  = 0
        self._openai_err_count  = 0
        # Claude model cascade — set of models confirmed as 404 (not available on account).
        # When a model 404s, it is added here and skipped on all future calls.
        # Each model is logged exactly ONCE when first added (deduplicates parallel coroutines).
        # Every _CLAUDE_MODEL_RETRY_INTERVAL seconds the set is cleared so that newly
        # provisioned models (e.g. after an account upgrade) are retried automatically.
        self._claude_failed_models: set = set()
        # Timestamp of last failed-model-set reset (monotonic seconds).
        self._claude_failed_models_last_reset: float = time.time()
        # Unix timestamp until which Claude is disabled (0 = enabled).
        # Credits-exhausted errors set a 30-min cooldown; invalid key is permanent.
        self._claude_disabled_until: float = 0.0
        self._claude_perm_disabled: bool   = False
        # Async probe lock — only ONE coroutine probes the cascade after a reset;
        # all others skip and use rule-based fallback until a winner is found.
        # This prevents 80 parallel symbol scans from each retrying all 7 models
        # simultaneously every time the 10-min retry window clears.
        self._claude_probe_lock: Optional[asyncio.Lock] = None
        self._claude_probe_in_progress: bool = False
        # Claude API inference semaphore — limits CONCURRENT Claude API calls to
        # prevent 429 "too many concurrent connections" rate-limit errors when
        # 30 parallel symbol scans all try to call Claude simultaneously.
        # Lazy-created inside the running event loop by _get_api_sem().
        self._claude_api_sem: Optional[asyncio.Semaphore] = None
        # 429 rate-limit: short cooldown (seconds) before next cycle can retry Claude.
        self._claude_ratelimit_until: float = 0.0
        # Same pattern for OpenAI — 401 triggers periodic re-test (key may change).
        self._openai_disabled_until: float = 0.0
        self._openai_perm_disabled: bool   = False
        self._openai_perm_disabled_at: float = 0.0   # timestamp of permanent disable
        self._llm_router: Optional[Any] = None
        if SmartLLMRouter is not None:
            self._llm_router = SmartLLMRouter(available_models=list(self._CLAUDE_MODELS) + [self._OPENAI_MODEL])
        self._init_claude()
        self._init_openai()

        # ── G0DM0D3 Engine — PRIMARY AI STRATEGY ─────────────────────────────
        # Integrates full G0DM0D3 framework (github.com/elder-plinius/G0DM0D3):
        # ULTRAPLINIAN multi-model racing + AutoTune + STM + GODMODE CLASSIC
        # Primary model: qwen/qwen3.6-plus:free via OpenRouter
        self._godmod3: Optional[G0DM0D3Engine] = None
        if _GODMOD3_AVAILABLE:
            try:
                self._godmod3 = get_godmod3_engine()
                if self._godmod3.is_available():
                    self.logger.info(
                        "✅ G0DM0D3 Engine ACTIVE — ULTRAPLINIAN+AutoTune+STM+GODMODE "
                        "(qwen/qwen3.6-plus:free via OpenRouter) [PRIMARY AI]"
                    )
                else:
                    self.logger.warning(
                        "⚠️ G0DM0D3 Engine: OPENROUTER_API_KEY not set — "
                        "falling back to Claude/OpenAI. Set OPENROUTER_API_KEY to enable."
                    )
            except Exception as _g3e:
                self.logger.warning(f"⚠️ G0DM0D3 init failed (non-fatal): {_g3e}")
                self._godmod3 = None
        else:
            self.logger.info("ℹ️ G0DM0D3 module not available — using Claude/OpenAI")

    def _get_probe_lock(self) -> asyncio.Lock:
        """Lazily create the probe lock inside the running event loop."""
        if self._claude_probe_lock is None:
            self._claude_probe_lock = asyncio.Lock()
        return self._claude_probe_lock

    def _get_api_sem(self) -> asyncio.Semaphore:
        """Lazily create the Claude API concurrency semaphore inside the event loop.

        Limits to 3 simultaneous Claude API calls so that 30 parallel symbol
        scans do not all hammer the API at once — prevents 429 concurrent-
        connection rate-limit errors on lower-tier Anthropic accounts.
        """
        if self._claude_api_sem is None:
            self._claude_api_sem = asyncio.Semaphore(3)
        return self._claude_api_sem

    # ── Client initialisation ────────────────────────────────────────────────

    @staticmethod
    def _clean_api_key(raw: str) -> str:
        """Strip invisible Unicode formatting chars (U+200E, etc.) that break auth headers."""
        import unicodedata
        return "".join(
            ch for ch in raw
            if unicodedata.category(ch) not in ("Cf", "Cc", "Cs", "Co", "Cn")
            and ch.isprintable()
        ).strip()

    def _init_claude(self):
        """Initialise the Anthropic AsyncAnthropic client (non-blocking).

        max_retries=0: disable SDK-internal retries on every call.
        Auth / billing errors (credits exhausted) should NEVER be retried —
        they are permanent until resolved by the user.  Without this, each
        call that hits a credits-exhausted 402 internally retries twice,
        flooding logs with 'Retrying request…' INFO lines from the SDK before
        the permanent-disable circuit breaker can fire.  The circuit breaker
        in _query_claude() handles retry logic at the application layer.
        """
        try:
            import anthropic
            api_key = self._clean_api_key(os.getenv("ANTHROPIC_API_KEY", ""))
            if api_key:
                self.claude_client = anthropic.AsyncAnthropic(
                    api_key=api_key,
                    max_retries=0,
                )
                _primary = self._CLAUDE_MODELS[0]
                _fallbacks = self._CLAUDE_MODELS[1:]
                self.logger.info(
                    f"✅ AIOrchestrationAgent: Claude ready — primary model: {_primary} "
                    f"| fallback cascade: {_fallbacks}"
                )
            else:
                self.logger.info("ℹ️  AIOrchestrationAgent: No ANTHROPIC_API_KEY — Claude disabled")
        except ImportError:
            self.logger.info("ℹ️  AIOrchestrationAgent: anthropic package not found — Claude disabled")
        except Exception as e:
            self.logger.debug(f"Claude init error: {e}")

    def _init_openai(self):
        """Initialise the AsyncOpenAI client as fallback.

        max_retries=0: disable SDK-internal retries.
        A 401 (invalid key) is permanent — retrying wastes HTTP round-trips
        and floods logs with INFO retry messages.  Billing/quota errors use a
        time-based 30-min cooldown that auto-retries without a bot restart.
        Application-layer retry decisions are made in _query_openai().
        """
        try:
            from openai import AsyncOpenAI
            api_key = self._clean_api_key(os.getenv("OPENAI_API_KEY", ""))
            if api_key:
                self.openai_client = AsyncOpenAI(
                    api_key=api_key,
                    max_retries=0,
                )
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
                      graph_context: str,
                      rsi: float = 50.0, macd_line: float = 0.0,
                      macd_signal: float = 0.0, bb_pct: float = 50.0,
                      stoch_k: float = 50.0, atr_pct: float = 0.3) -> str:
        """
        Build the ReACT trading prompt enriched with full technical indicator data.
        The additional indicators (RSI, MACD, BB%, Stoch, ATR%) give Claude/GPT
        the same data a professional trader would have on their chart.
        """
        # MACD cross description
        _macd_cross = ""
        if macd_line > macd_signal:
            _macd_cross = "bullish (MACD above signal)"
        elif macd_line < macd_signal:
            _macd_cross = "bearish (MACD below signal)"
        else:
            _macd_cross = "neutral (at crossover)"

        # RSI zone
        _rsi_zone = "neutral"
        if rsi >= 70:
            _rsi_zone = "overbought (bearish risk)"
        elif rsi >= 60:
            _rsi_zone = "mildly overbought"
        elif rsi <= 30:
            _rsi_zone = "oversold (bullish opportunity)"
        elif rsi <= 40:
            _rsi_zone = "mildly oversold"

        # BB position description
        _bb_zone = "mid-band"
        if bb_pct >= 85:
            _bb_zone = "near upper band (extended, reversion risk)"
        elif bb_pct >= 65:
            _bb_zone = "upper half (bullish bias)"
        elif bb_pct <= 15:
            _bb_zone = "near lower band (extended, reversion risk)"
        elif bb_pct <= 35:
            _bb_zone = "lower half (bearish bias)"

        return (
            f"You are a professional quantitative crypto futures trader using ReACT reasoning.\n"
            f"Symbol: {symbol} | Timeframe: {timeframe} | Session: {session}\n"
            f"Current price: ${cur_price:,.4g} | 1h change: {chg_1h:+.2f}%\n\n"
            f"Technical indicators:\n"
            f"  RSI(14)={rsi:.1f} [{_rsi_zone}]\n"
            f"  MACD={macd_line:+.5g} | Signal={macd_signal:+.5g} [{_macd_cross}]\n"
            f"  BB%={bb_pct:.1f}% [{_bb_zone}]\n"
            f"  Stochastic(14)={stoch_k:.1f}\n"
            f"  ATR%={atr_pct:.3f}% (volatility)\n\n"
            f"Swarm agent votes: {votes_summary}\n"
            f"Buy votes: {buy_votes} | Sell votes: {sell_votes}\n"
            f"Graph memory: {graph_context}\n\n"
            f"REASON: What do the technical indicators and agent consensus indicate?\n"
            f"ACT: What is the most probable next {timeframe} move?\n"
            f"REFLECT: Any conflicting signals (OB/OS vs trend, MACD divergence) reducing confidence?\n"
            f"CONCLUDE: Final trading signal.\n\n"
            f"Reply ONLY as valid JSON (no markdown, no extra text):\n"
            f"{{\"reason\": \"<1 sentence>\", \"act\": \"<1 sentence>\", "
            f"\"reflect\": \"<1 sentence>\", "
            f"\"vote\": \"BUY\"|\"SELL\"|\"NEUTRAL\", "
            f"\"confidence\": 50-95, \"narrative\": \"<concise reason>\"}}"
        )

    @staticmethod
    def _parse_ai_response(content: str) -> Optional[dict]:
        """
        Extract and parse JSON from AI response — handles markdown code fences
        and nested JSON structures.  Uses a brace-counting extractor so nested
        objects (e.g. {"data": {"x": 1}}) are captured correctly instead of
        being truncated by the old r'\{[^{}]*\}' regex.
        """
        # Strip markdown code fences if present
        content = re.sub(r"```(?:json)?\s*", "", content).strip()

        # Try direct parse first (the cleanest path)
        try:
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            pass

        # Brace-counting extractor — finds the outermost {} object
        depth = 0
        start = -1
        for i, ch in enumerate(content):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        return json.loads(content[start:i + 1])
                    except (json.JSONDecodeError, ValueError):
                        # This brace pair wasn't valid JSON — keep scanning
                        start = -1
        return None

    # ── Claude query ─────────────────────────────────────────────────────────

    async def _query_claude(self, prompt: str) -> Optional[dict]:
        """
        Send prompt to Claude; return parsed dict or None on any error.

        Circuit-breaker + model cascade behaviour:
        ──────────────────────────────────────────
        • 404 not_found_error (model unavailable on this account) →
          automatically advances to the next model in _CLAUDE_MODELS cascade
          and retries in the SAME call (no wasted cycle).  Logs once per
          model switch to avoid spam.
        • credits exhausted / billing → 30-min cooldown (auto-retry).
          Race-condition safe: only the first coroutine to fire the cooldown
          logs the warning; subsequent parallel coroutines see the flag and
          return silently.
        • invalid/expired key → permanent disable (won't fix itself).
        • network timeout → silent fallback, counted in _claude_err_count.

        Probe-lock: when the 10-min retry window clears, ONLY ONE coroutine
        runs the cascade probe.  All 80 parallel symbol-scan coroutines would
        otherwise simultaneously try all 7 models → 560 error lines in a burst.
        Non-probe coroutines return None and fall through to rule-based until the
        probe completes and confirms a working model (or re-sets perm_disabled).
        """
        if self.claude_client is None:
            return None

        # ── Permanent-disable + periodic reset ──────────────────────────
        if self._claude_perm_disabled:
            _now_reset = time.time()
            if (_now_reset - self._claude_failed_models_last_reset
                    >= self._CLAUDE_MODEL_RETRY_INTERVAL):
                # Only ONE coroutine resets and runs the probe; others skip.
                _lock = self._get_probe_lock()
                if _lock.locked():
                    # Another coroutine is already probing — return None for now.
                    return None
                async with _lock:
                    # Re-check inside lock (another coroutine may have just reset).
                    if self._claude_perm_disabled and (
                        time.time() - self._claude_failed_models_last_reset
                            >= self._CLAUDE_MODEL_RETRY_INTERVAL
                    ):
                        self._claude_failed_models.clear()
                        self._claude_failed_models_last_reset = time.time()
                        self._claude_perm_disabled = False
                        self.logger.info(
                            "🔄 Claude retry window reached — clearing failed-model set. "
                            "Probing cascade (1 coroutine only). Others use rule-based."
                        )
                    # Fall through to attempt below (still inside lock = single probe)
            else:
                return None  # Still in cooldown — fast exit

        # ── 429 Concurrent rate-limit cooldown (per-cycle, short) ───────
        if self._claude_ratelimit_until > 0:
            _now_rl = time.time()
            if _now_rl < self._claude_ratelimit_until:
                return None  # Still in rate-limit cool-off; use rule-based this cycle
            self._claude_ratelimit_until = 0.0  # Cooldown elapsed — try again

        # ── Credits / billing cooldown ───────────────────────────────────
        if self._claude_disabled_until > 0:
            _now = time.time()
            if _now < self._claude_disabled_until:
                return None
            self._claude_disabled_until = 0.0
            self._claude_err_count      = 0
            self.logger.info(
                "💳 Claude cooldown elapsed — re-enabling. "
                "Attempting API call (credits may have been added)."
            )

        # ── Model cascade using deduplicating failed-model set ───────────
        # _claude_failed_models is a shared set (single agent instance).
        # When a model is added, ALL concurrent coroutines see it immediately
        # at their next check, so each model is logged as failed EXACTLY ONCE
        # regardless of how many parallel symbol scans are in flight.
        available_models = [m for m in self._CLAUDE_MODELS
                            if m not in self._claude_failed_models]
        if not available_models:
            if not self._claude_perm_disabled:
                self._claude_perm_disabled = True
                self._claude_failed_models_last_reset = time.time()
                self.logger.warning(
                    "🔑 Claude: no accessible model in cascade. "
                    f"Tried: {self._CLAUDE_MODELS}. "
                    f"Re-probe in {int(self._CLAUDE_MODEL_RETRY_INTERVAL//60)} min. "
                    "Rule-based fallback active."
                )
            return None

        for _current_model in available_models:
            try:
                # ── Concurrency gate: max 3 simultaneous Claude API calls ──
                # Prevents 429 "too many concurrent connections" errors when
                # 30 parallel symbol scans all try Claude at the same time.
                async with self._get_api_sem():
                    coro = self.claude_client.messages.create(
                        model=_current_model,
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
                    self._claude_ratelimit_until = 0.0  # Clear any rate limit cooldown
                    # Log once when a model succeeds after cascade fallback
                    if len(self._claude_failed_models) > 0:
                        self.logger.info(
                            f"✅ Claude cascade: {_current_model} working "
                            f"(skipped {len(self._claude_failed_models)} unavailable model(s))"
                        )
                return data

            except asyncio.TimeoutError:
                self._claude_err_count += 1
                if self._claude_err_count <= 3:
                    self.logger.warning(
                        f"⏱ Claude/{_current_model} timeout ({self._AI_TIMEOUT}s) "
                        "— falling back to OpenAI/rule-based"
                    )
                return None

            except Exception as e:
                err_str = str(e).lower()

                # ── 404 not_found: model unavailable on this account ──────
                # set.add() is idempotent — concurrent coroutines are safe.
                # Log ONCE when newly added (_is_new flag).
                _NOT_FOUND_PHRASES = (
                    "not_found_error", "not found", "404",
                    "model: claude", "no such model", "unknown model",
                )
                if any(p in err_str for p in _NOT_FOUND_PHRASES):
                    _is_new = _current_model not in self._claude_failed_models
                    self._claude_failed_models.add(_current_model)
                    if _is_new:
                        _remaining = [m for m in self._CLAUDE_MODELS
                                      if m not in self._claude_failed_models]
                        if _remaining:
                            self.logger.warning(
                                f"⚠️ Claude model unavailable: {_current_model} → "
                                f"trying: {_remaining[0]}"
                            )
                        else:
                            self.logger.warning(
                                f"⚠️ Claude model unavailable: {_current_model}. "
                                "All cascade models exhausted — rule-based active."
                            )
                    # Try next model in the cascade for-loop
                    continue

                # ── Permanent errors: wrong key / no access ───────────────
                _PERM_PHRASES = (
                    "invalid x-api-key", "invalid api key",
                    "authentication_error", "permission_error",
                    "access denied", "permission denied",
                )
                if any(p in err_str for p in _PERM_PHRASES):
                    if not self._claude_perm_disabled:
                        self._claude_perm_disabled = True
                        self._claude_failed_models_last_reset = time.time()
                        self.logger.warning(
                            "🔑 Claude disabled — invalid or expired API key. "
                            "Update ANTHROPIC_API_KEY secret to re-enable."
                        )
                    return None

                # ── Temporary errors: credits/billing — 30-min cooldown ───
                _CREDIT_PHRASES = (
                    "credit balance is too low", "insufficient_quota",
                    "billing", "payment", "your account",
                    "overloaded_error",
                )
                if any(p in err_str for p in _CREDIT_PHRASES):
                    _cooldown = 1800  # 30 minutes
                    _was_enabled = self._claude_disabled_until == 0.0
                    self._claude_disabled_until = time.time() + _cooldown
                    if _was_enabled:
                        self.logger.warning(
                            f"💳 Claude paused — credits/billing issue. "
                            f"Auto-retrying in {_cooldown // 60} min. "
                            "Add credits at console.anthropic.com if needed."
                        )
                    return None

                # ── 429 Concurrent connection rate-limit ──────────────────
                # The model IS accessible — the account just limits simultaneous
                # connections.  The API semaphore (max 3) gates future calls.
                # Do NOT add the model to _claude_failed_models.
                # Apply a short per-cycle cooldown so rule-based runs this round,
                # and Claude resumes on the NEXT scan cycle automatically.
                _RATELIMIT_PHRASES = (
                    "rate_limit_error", "rate limit", "concurrent connections",
                    "ratelimiterror", "too many requests",
                )
                if (any(p in err_str for p in _RATELIMIT_PHRASES)
                        or "429" in str(e)):
                    if self._claude_ratelimit_until == 0.0:
                        # First rate-limit hit — set 30s cooldown and log once
                        self._claude_ratelimit_until = time.time() + 30.0
                        self.logger.warning(
                            f"⏳ Claude/{_current_model} rate-limited (429 concurrent) "
                            "— 30s cooldown. Rule-based active this cycle. "
                            "Semaphore(3) gates future calls to prevent recurrence."
                        )
                    return None  # Model valid — don't add to failed set

                # ── Generic transient error ───────────────────────────────
                self._claude_err_count += 1
                if self._claude_err_count <= 5:
                    self.logger.warning(
                        f"⚠️ Claude/{_current_model} {type(e).__name__} "
                        f"(#{self._claude_err_count}): {str(e)[:200]}"
                    )
                return None

        # All available cascade models failed with 404 this round
        if not self._claude_perm_disabled:
            self._claude_perm_disabled = True
            self._claude_failed_models_last_reset = time.time()
            self.logger.warning(
                f"🔑 Claude: all {len(self._CLAUDE_MODELS)} models returned 404. "
                f"Re-probe in {int(self._CLAUDE_MODEL_RETRY_INTERVAL//60)} min. "
                "Rule-based fallback active."
            )
        return None

    # ── OpenAI query ─────────────────────────────────────────────────────────

    async def _query_openai(self, prompt: str) -> Optional[dict]:
        """
        Send prompt to OpenAI; return parsed dict or None on any error.

        Circuit-breaker behaviour:
        ──────────────────────────
        • 401 / invalid key → timed disable: re-probes every 4 hours in case
          the OPENAI_API_KEY secret has been updated since the last failure.
        • billing / quota / rate-limit → 30-min cooldown, then auto-retry.
          Race-condition safe: only the first coroutine to hit the quota
          error logs the warning; parallel coroutines silently return None.
        • network timeout → silent fallback, counted in _openai_err_count.
        """
        if self.openai_client is None:
            return None
        if self._openai_perm_disabled:
            # Re-probe every 4 hours — the user may have updated the API key secret.
            _since = time.time() - self._openai_perm_disabled_at
            if _since < self._OPENAI_RETRY_INTERVAL:
                return None
            # Re-read and re-init the client with the (possibly updated) key
            _new_key = self._clean_api_key(os.getenv("OPENAI_API_KEY", ""))
            if not _new_key:
                self._openai_perm_disabled_at = time.time()  # reset timer
                return None
            try:
                from openai import AsyncOpenAI
                self.openai_client = AsyncOpenAI(api_key=_new_key, max_retries=0)
                self._openai_perm_disabled      = False
                self._openai_perm_disabled_at   = 0.0
                self._openai_err_count          = 0
                self.logger.info(
                    "🔄 OpenAI re-enabled — detected new API key. Testing connectivity…"
                )
            except Exception:
                self._openai_perm_disabled_at = time.time()
                return None
        if self._openai_disabled_until > 0:
            _now = time.time()
            if _now < self._openai_disabled_until:
                return None
            self._openai_disabled_until = 0.0
            self._openai_err_count      = 0
            self.logger.info(
                "🔑 OpenAI cooldown elapsed — re-enabling. Attempting API call."
            )
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
            err_str = str(e).lower()

            # ── Permanent errors: invalid/expired key (401) ──
            _PERM_PHRASES = (
                "401", "invalid_api_key", "incorrect api key",
                "authentication", "invalid x-api-key",
            )
            if any(p in err_str for p in _PERM_PHRASES):
                if not self._openai_perm_disabled:
                    self._openai_perm_disabled     = True
                    self._openai_perm_disabled_at  = time.time()
                    self.logger.warning(
                        "🔑 OpenAI disabled — invalid/expired API key (401). "
                        f"Auto-re-probe in {int(self._OPENAI_RETRY_INTERVAL//3600)}h. "
                        "Set a valid OPENAI_API_KEY secret to re-enable immediately."
                    )
                return None

            # ── Temporary errors: billing/quota/rate-limit — 30-min retry ──
            # Race-condition safe: check if WE are the first coroutine to set
            # the cooldown.  Parallel symbol-scan coroutines all fail at the
            # same timestamp; only the first logs the warning.
            _TEMP_PHRASES = (
                "insufficient_quota", "billing", "payment", "your account",
                "429", "rate_limit_exceeded", "overloaded", "service_unavailable",
                "access denied", "permission denied",
            )
            if any(p in err_str for p in _TEMP_PHRASES):
                _cooldown = 1800  # 30 minutes
                _was_enabled = self._openai_disabled_until == 0.0
                self._openai_disabled_until = time.time() + _cooldown
                if _was_enabled:
                    # Only the first coroutine logs — subsequent ones are silenced.
                    self.logger.warning(
                        f"🔑 OpenAI paused — quota/billing/rate issue. "
                        f"Auto-retrying in {_cooldown // 60} min. Rule-based active until then."
                    )
                return None

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

        # ── Compute technical indicators for the enriched prompt ──
        # These are the same indicators the swarm agents use, giving Claude/GPT
        # the same full-chart context a professional trader would have.
        #
        # BUG FIX: avoid `_fn() or fallback` pattern — when the indicator
        # returns exactly 0.0 (e.g. RSI=0 on a perfectly falling market, or
        # Stochastic=0 when price is at the k-period low), Python evaluates
        # `0.0 or fallback` as `fallback`, silently replacing valid extremes.
        # Use an explicit None-check instead, consistent with _analyze_timeframe.
        _rsi_raw   = _rsi(closes, 14)
        _rsi_val   = _rsi_raw if _rsi_raw is not None else 50.0
        _macd_l, _macd_s = _macd(closes)
        _macd_l    = _macd_l if _macd_l is not None else 0.0
        _macd_s    = _macd_s if _macd_s is not None else 0.0
        _bb_up, _bb_mid, _bb_lo = _bollinger(closes, 20, 2.0)
        if _bb_up is not None and _bb_lo is not None and _bb_up != _bb_lo:
            _bb_pct = (closes[-1] - _bb_lo) / (_bb_up - _bb_lo) * 100.0
        else:
            _bb_pct = 50.0
        _stoch_d   = _stochastic(closes, 14, 3)          # smoothed %D (3-SMA of %K)
        _stoch_k   = _stoch_d if _stoch_d is not None else 50.0
        _atr_raw   = _atr_close(closes, 14)
        _atr_val   = _atr_raw if _atr_raw is not None else (closes[-1] * 0.003)
        _atr_pct   = (_atr_val / closes[-1] * 100.0) if closes[-1] > 0 else 0.3

        # Build the shared prompt once — used by both AI providers
        prompt = self._build_prompt(
            symbol, timeframe, session, cur_price, chg_1h,
            votes_summary, buy_votes, sell_votes, graph_context,
            rsi=_rsi_val, macd_line=_macd_l, macd_signal=_macd_s,
            bb_pct=_bb_pct, stoch_k=_stoch_k, atr_pct=_atr_pct
        )

        # ── ACT: G0DM0D3 PRIMARY (ULTRAPLINIAN + GODMODE CLASSIC via OpenRouter) ──
        # G0DM0D3 is the main AI strategy: races multiple free OpenRouter models in
        # parallel (ULTRAPLINIAN), auto-tunes sampling params, applies STM normalisation.
        # Falls back to GODMODE CLASSIC (5 prompt combos) if ULTRAPLINIAN fails.
        ai_source = None
        data = None

        # ── G0DM0D3 pre-filter gate ──
        # Only call G0DM0D3 when the non-AI swarm shows reasonable consensus.
        # This reduces API calls from ~80/cycle to ~8-15/cycle — staying under free tier limits.
        #
        # Gate requirements (both must be true):
        #   1) At least 5 of 9 non-AI agents voted in one direction (≥56% agreement)
        #      v5.0: Lowered from 7 (≥78%) → 5 (≥56%) — 7/9 was almost never triggered,
        #            causing AI to return NEUTRAL for every signal (was the main win-rate killer)
        #   2) The winning direction dominates by ≥2 votes over the losing direction
        #      v5.0: Lowered from 3 → 2 — even marginal consensus benefits from AI confirmation
        #
        # Rationale: With 26 free models and per-model buckets, we have far more AI capacity.
        # A lower gate means more AI calls, but the per-model rate limiter handles throttling.
        _g3_min_votes = 5   # 5/9 = 56% non-AI consensus required (was 7/9=78% — too strict)
        _g3_min_margin = 2  # winning direction must lead by ≥2 (was 3 — too strict)
        _g3_should_call = (
            (buy_votes >= _g3_min_votes or sell_votes >= _g3_min_votes)
            and abs(buy_votes - sell_votes) >= _g3_min_margin
        )

        if self._godmod3 is not None and self._godmod3.is_available() and _g3_should_call:
            try:
                _g3_start = time.time()
                _g3_vote, _g3_conf, _g3_narrative, _g3_trace = await asyncio.wait_for(
                    self._godmod3.analyze(prompt, atr_pct=_atr_pct, symbol=symbol),
                    timeout=35.0,  # 35s: G0DM0D3 can take 23s+ with full 5-tier cascade
                                   # v5.0: was _AI_TIMEOUT + 5.0 = 20s — too short for cascade
                )
                _g3_ms = (time.time() - _g3_start) * 1000

                if _g3_vote in ("BUY", "SELL", "NEUTRAL") and _g3_conf >= 50.0:
                    data = {
                        "vote": _g3_vote,
                        "confidence": _g3_conf,
                        "narrative": _g3_narrative,
                        "reason": f"G0DM0D3 ULTRAPLINIAN/GODMODE analysis",
                        "act": f"Signal: {_g3_vote} @{_g3_conf:.1f}%",
                        "reflect": f"Multi-model consensus via OpenRouter ({_g3_ms:.0f}ms)",
                    }
                    ai_source = f"G0DM0D3/qwen3.6-plus+race"
                    react_trace.append({
                        "step": "ACT",
                        "source": ai_source,
                        "strategy": "ULTRAPLINIAN+GODMODE_CLASSIC",
                        "vote": _g3_vote,
                        "confidence": _g3_conf,
                        "latency_ms": _g3_ms,
                    })
            except asyncio.TimeoutError:
                self.logger.debug("⏱️ G0DM0D3 timeout — falling back to Claude")
            except Exception as _g3e:
                self.logger.debug(f"⚠️ G0DM0D3 error (non-fatal): {_g3e}")

        # ── ACT: Claude (secondary, with automatic model cascade on 404) ──
        # ClawRouter-inspired routing: log the routing decision for this prompt
        _route_decision = None
        if self._llm_router is not None:
            try:
                _route_decision = self._llm_router.route(
                    prompt=prompt, max_output_tokens=self._MAX_TOKENS,
                )
            except Exception:
                pass

        # ── ACT: Claude (secondary — only if G0DM0D3 didn't provide data) ──
        _call_ms = 0.0
        if data is None:
            _call_start = time.time()
            data = await self._query_claude(prompt)
            _call_ms = (time.time() - _call_start) * 1000
            if data:
                _active_model = next(
                    (m for m in self._CLAUDE_MODELS if m not in self._claude_failed_models),
                    self._CLAUDE_MODELS[-1]
                )
                ai_source = f"Claude/{_active_model}"
                if self._llm_router is not None:
                    self._llm_router.record_outcome(_active_model, success=True, latency_ms=_call_ms)
            else:
                if self._llm_router is not None:
                    _failed_model = next(
                        (m for m in self._CLAUDE_MODELS if m not in self._claude_failed_models),
                        self._CLAUDE_MODELS[0]
                    )
                    self._llm_router.record_outcome(_failed_model, success=False, latency_ms=_call_ms)
                # ── ACT: OpenAI (tertiary fallback) ──
                _call_start = time.time()
                data = await self._query_openai(prompt)
                _call_ms = (time.time() - _call_start) * 1000
                if data:
                    ai_source = f"OpenAI/{self._OPENAI_MODEL}"
                    if self._llm_router is not None:
                        self._llm_router.record_outcome(self._OPENAI_MODEL, success=True, latency_ms=_call_ms)
                else:
                    if self._llm_router is not None:
                        self._llm_router.record_outcome(self._OPENAI_MODEL, success=False, latency_ms=_call_ms)

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
        High-precision rule-based AI fallback with TradingAgents-style Bull/Bear
        debate scoring. Active when both Claude and OpenAI are unavailable.

        Design goals
        ────────────
        1. Quality over quantity — prefer NEUTRAL when conviction is low.
        2. Bull/Bear debate scoring — structured evidence from both sides with
           debate margin influencing confidence (ported from TradingAgents).
        3. Momentum + RSI + MACD + BB confirmation — 4-layer technical validation.
        4. Stricter quorum (≥4 agents) — four independent agents must agree.
        5. Confidence range 50–88: capped at 88 for reduced information quality.
        6. Dominant-side margin requirement (≥60% dominance).
        """
        buy_confs  = [v["conf"] for v in agent_summary.values() if v["vote"] == "BUY"]
        sell_confs = [v["conf"] for v in agent_summary.values() if v["vote"] == "SELL"]
        n_buy   = len(buy_confs)
        n_sell  = len(sell_confs)
        n_total = len(agent_summary)

        if n_buy == 0 and n_sell == 0:
            return "NEUTRAL", 50.0, "No agent consensus"

        # Weighted aggregate confidence per side (sum rewarded by agent count AND depth)
        avg_buy_conf  = sum(buy_confs)  / n_buy  if n_buy  else 0.0
        avg_sell_conf = sum(sell_confs) / n_sell if n_sell else 0.0

        # Score = count × avg_confidence — rewards both breadth and depth of agreement
        buy_score  = n_buy  * avg_buy_conf
        sell_score = n_sell * avg_sell_conf

        # ── Dominant-side margin requirement ──────────────────────────────────
        # If the winning side's score is within 15% of the total (very thin margin),
        # the consensus is too close to call — issue NEUTRAL to avoid marginal calls.
        total_score = buy_score + sell_score
        if total_score > 0:
            buy_frac  = buy_score  / total_score
            sell_frac = sell_score / total_score
        else:
            return "NEUTRAL", 50.0, "No scored agents"
        if max(buy_frac, sell_frac) < 0.60:   # need at least 60% dominance
            return "NEUTRAL", 50.0, (
                f"Rule-based: thin margin — BUY {buy_frac:.0%} vs SELL {sell_frac:.0%}"
            )

        # ── Technical indicator layer ─────────────────────────────────────────
        # RSI overbought/oversold, MACD direction, Bollinger band position, and
        # short-term price momentum are computed directly from closes to provide
        # independent technical confirmation beyond the 8-agent swarm votes.
        _rsi_raw  = _rsi(closes, 14)       if len(closes) >= 16  else None
        _macd_l, _macd_s = _macd(closes)   if len(closes) >= 36  else (None, None)
        _bb_u, _bb_m, _bb_l = _bollinger(closes, 20) if len(closes) >= 20 else (None, None, None)

        _momentum_bonus    = 0.0
        _momentum_conflict = False
        _tech_boost        = 0.0
        _tech_veto         = False
        _tech_notes        = []

        # 4-bar slope for short-term directional momentum
        if len(closes) >= 5 and closes[-1] > 0:
            _slope4 = (closes[-1] - closes[-5]) / closes[-1] * 100

            # Stronger momentum check using 8-bar slope for trend confirmation
            if len(closes) >= 9:
                _slope8 = (closes[-1] - closes[-9]) / closes[-1] * 100
            else:
                _slope8 = _slope4

            if buy_score > sell_score:
                if _slope4 > 0.15 and _slope8 > 0.05:
                    _momentum_bonus = min(_slope4 * 3.0, 10.0)     # up to +10 pts
                    _tech_notes.append(f"momentum+{_momentum_bonus:.1f}pt")
                elif _slope4 < -0.40:
                    _momentum_conflict = True
                    _tech_notes.append("momentum_conflict")
                elif _slope4 < -0.20:
                    _momentum_bonus = -5.0                         # soft penalty
                    _tech_notes.append("momentum_weak_contra-5pt")
            elif sell_score > buy_score:
                if _slope4 < -0.15 and _slope8 < -0.05:
                    _momentum_bonus = min(abs(_slope4) * 3.0, 10.0)
                    _tech_notes.append(f"momentum+{_momentum_bonus:.1f}pt")
                elif _slope4 > 0.40:
                    _momentum_conflict = True
                    _tech_notes.append("momentum_conflict")
                elif _slope4 > 0.20:
                    _momentum_bonus = -5.0
                    _tech_notes.append("momentum_weak_contra-5pt")

        # RSI confirmation
        if _rsi_raw is not None:
            if buy_score > sell_score:
                if _rsi_raw < 35:                                  # oversold — strong BUY support
                    _tech_boost += 5.0
                    _tech_notes.append(f"RSI_oversold({_rsi_raw:.0f})+5pt")
                elif _rsi_raw < 45:                                # mild oversold
                    _tech_boost += 2.0
                    _tech_notes.append(f"RSI_low({_rsi_raw:.0f})+2pt")
                elif _rsi_raw > 72:                                # overbought into BUY — veto
                    _tech_veto = True
                    _tech_notes.append(f"RSI_overbought({_rsi_raw:.0f})VETO")
                elif _rsi_raw > 63:                                # elevated into BUY — penalty
                    _tech_boost -= 5.0
                    _tech_notes.append(f"RSI_high({_rsi_raw:.0f})-5pt")
            else:
                if _rsi_raw > 65:                                  # overbought — strong SELL support
                    _tech_boost += 5.0
                    _tech_notes.append(f"RSI_overbought({_rsi_raw:.0f})+5pt")
                elif _rsi_raw > 55:                                # mild overbought
                    _tech_boost += 2.0
                    _tech_notes.append(f"RSI_high({_rsi_raw:.0f})+2pt")
                elif _rsi_raw < 28:                                # oversold into SELL — veto
                    _tech_veto = True
                    _tech_notes.append(f"RSI_oversold({_rsi_raw:.0f})VETO")
                elif _rsi_raw < 37:                                # low into SELL — penalty
                    _tech_boost -= 5.0
                    _tech_notes.append(f"RSI_low({_rsi_raw:.0f})-5pt")

        # MACD histogram direction confirmation
        if _macd_l is not None and _macd_s is not None:
            macd_hist = _macd_l - _macd_s
            if buy_score > sell_score:
                if macd_hist > 0:
                    _tech_boost += 3.0
                    _tech_notes.append("MACD_bull+3pt")
                else:
                    _tech_boost -= 4.0
                    _tech_notes.append("MACD_bear-4pt")
            else:
                if macd_hist < 0:
                    _tech_boost += 3.0
                    _tech_notes.append("MACD_bear+3pt")
                else:
                    _tech_boost -= 4.0
                    _tech_notes.append("MACD_bull-4pt")

        # Bollinger band position — price relative to mid and bands
        if _bb_u is not None and _bb_l is not None and _bb_m is not None and closes[-1] > 0:
            _bb_width_pct = (_bb_u - _bb_l) / closes[-1] * 100
            _bb_pos = (closes[-1] - _bb_l) / (_bb_u - _bb_l) if (_bb_u - _bb_l) > 0 else 0.5
            if buy_score > sell_score:
                if _bb_pos < 0.25:
                    _tech_boost += 3.0
                    _tech_notes.append("BB_low+3pt")
                elif _bb_pos > 0.85:
                    _tech_boost -= 4.0
                    _tech_notes.append("BB_high-4pt")
                if _bb_width_pct < 0.35:
                    _tech_boost -= 2.0
                    _tech_notes.append("BB_squeeze-2pt")
            else:
                if _bb_pos > 0.75:
                    _tech_boost += 3.0
                    _tech_notes.append("BB_high+3pt")
                elif _bb_pos < 0.15:
                    _tech_boost -= 4.0
                    _tech_notes.append("BB_low-4pt")
                if _bb_width_pct < 0.35:
                    _tech_boost -= 2.0
                    _tech_notes.append("BB_squeeze-2pt")

        _bull_evidence = 0.0
        _bear_evidence = 0.0
        if _rsi_raw is not None:
            if _rsi_raw < 40:
                _bull_evidence += (40 - _rsi_raw) * 0.15
            elif _rsi_raw > 60:
                _bear_evidence += (_rsi_raw - 60) * 0.15
        if _macd_l is not None and _macd_s is not None:
            _mh = _macd_l - _macd_s
            if _mh > 0:
                _bull_evidence += min(abs(_mh) * 100, 3.0)
            else:
                _bear_evidence += min(abs(_mh) * 100, 3.0)
        if len(closes) >= 5 and closes[-1] > 0:
            _s4 = (closes[-1] - closes[-5]) / closes[-1] * 100
            if _s4 > 0:
                _bull_evidence += min(_s4 * 1.5, 3.0)
            else:
                _bear_evidence += min(abs(_s4) * 1.5, 3.0)
        if _bb_u is not None and _bb_l is not None and (_bb_u - _bb_l) > 0:
            _bp = (closes[-1] - _bb_l) / (_bb_u - _bb_l)
            if _bp < 0.3:
                _bull_evidence += 2.0
            elif _bp > 0.7:
                _bear_evidence += 2.0
        _bull_evidence += n_buy * 0.8
        _bear_evidence += n_sell * 0.8
        _debate_total = _bull_evidence + _bear_evidence
        if _debate_total > 0:
            _debate_margin = abs(_bull_evidence - _bear_evidence) / _debate_total
        else:
            _debate_margin = 0.0
        _debate_bonus = _debate_margin * 6.0
        _tech_notes.append(f"debate_bull={_bull_evidence:.1f}_bear={_bear_evidence:.1f}_margin={_debate_margin:.2f}")

        _MIN_QUORUM = 4

        if buy_score > sell_score:
            if n_buy < _MIN_QUORUM:
                return "NEUTRAL", 50.0, (
                    f"Rule-based: only {n_buy}/{n_total} agents BUY — below quorum ({_MIN_QUORUM})"
                )
            # Technical veto: RSI overbought into BUY is hard rejection
            if _tech_veto:
                return "NEUTRAL", 50.0, (
                    f"Rule-based: BUY vetoed by technical indicator | {', '.join(_tech_notes)}"
                )
            participation = (n_buy + n_sell) / n_total
            conf = (avg_buy_conf * 0.65) + (50.0 * 0.35)
            conf += participation * 12.0
            conf += _momentum_bonus
            conf += _tech_boost
            if _bull_evidence > _bear_evidence:
                conf += _debate_bonus
            elif _bear_evidence > _bull_evidence:
                conf -= _debate_bonus * 0.5
            if _momentum_conflict:
                conf = max(conf - 12.0, 50.0)
            if chg_1h > 1.5:
                conf = min(conf + 6.0, 88.0)
            elif chg_1h > 0.5:
                conf = min(conf + 3.0, 88.0)
            elif chg_1h < -0.5:
                conf = max(conf - 4.0, 50.0)
            if n_sell == 0 and n_buy >= 5:
                conf = min(conf + 4.0, 88.0)
            conf = min(conf, 88.0)
            margin = buy_score - sell_score
            narrative = (
                f"Rule-based AI: {n_buy}/{n_total} BUY "
                f"(avg={avg_buy_conf:.1f}%, margin={margin:.1f}, "
                f"1h={chg_1h:+.2f}%, debate={_debate_margin:.2f}, "
                f"tech=[{', '.join(_tech_notes) or 'none'}])"
            )
            return "BUY", round(conf, 1), narrative

        elif sell_score > buy_score:
            if n_sell < _MIN_QUORUM:
                return "NEUTRAL", 50.0, (
                    f"Rule-based: only {n_sell}/{n_total} agents SELL — below quorum ({_MIN_QUORUM})"
                )
            if _tech_veto:
                return "NEUTRAL", 50.0, (
                    f"Rule-based: SELL vetoed by technical indicator | {', '.join(_tech_notes)}"
                )
            participation = (n_buy + n_sell) / n_total
            conf = (avg_sell_conf * 0.65) + (50.0 * 0.35)
            conf += participation * 12.0
            conf += _momentum_bonus
            conf += _tech_boost
            if _bear_evidence > _bull_evidence:
                conf += _debate_bonus
            elif _bull_evidence > _bear_evidence:
                conf -= _debate_bonus * 0.5
            if _momentum_conflict:
                conf = max(conf - 12.0, 50.0)
            if chg_1h < -1.5:
                conf = min(conf + 6.0, 88.0)
            elif chg_1h < -0.5:
                conf = min(conf + 3.0, 88.0)
            elif chg_1h > 0.5:
                conf = max(conf - 4.0, 50.0)
            if n_buy == 0 and n_sell >= 5:
                conf = min(conf + 4.0, 88.0)
            conf = min(conf, 88.0)
            margin = sell_score - buy_score
            narrative = (
                f"Rule-based AI: {n_sell}/{n_total} SELL "
                f"(avg={avg_sell_conf:.1f}%, margin={margin:.1f}, "
                f"1h={chg_1h:+.2f}%, debate={_debate_margin:.2f}, "
                f"tech=[{', '.join(_tech_notes) or 'none'}])"
            )
            return "SELL", round(conf, 1), narrative

        return "NEUTRAL", 50.0, "Balanced signals — no edge"


# ─────────────────────────────────────────────────────────────────────────────
# FLOOP Pro Agent — ML-Optimized Range Filter (Pine Script → Python)
# ─────────────────────────────────────────────────────────────────────────────

class FLOOPAgent:
    """
    FLOOP Pro Agent — 10th swarm member, ML-optimized range filter.

    Python port of the FLOOP Pro Pine Script indicator with ML-proven scoring.

    Feature importance (from ML backtesting analysis of Pine Script signals):
      1. ROC momentum (5/10/20-period) : ~38%  — top predictor
      2. ATR/price volatility norm     : ~23%
      3. EMA alignment (60/200)        : ~14%  (+27pt win-rate lift)
      4. Sensitivity cross-check S:12/16: ~12%
      5. HTF MA filter (EMA200 on 1H)  : ~13%

    ML scoring: EMA=4, ROC≤4, VOL=2, SENS=3, HTF=1 → max 14 pts

    Range filter core (Pine Script → Python):
      rng = ATR × atr_mult × (sensitivity / 8.0)
      Filter tracks price: breaks above band → filter rises; breaks below → falls.
      Trend = +1 rising, -1 falling.
    """
    NAME = "FLOOPAgent"
    PROFILE = AgentProfile(
        agent_id=10,
        name="FLOOPAgent",
        persona=(
            "FLOOP Pro ML-optimized range filter. EMA60/200 alignment (+27pt WR). "
            "ROC 5/10/20 momentum (top predictor). ATR adaptive band S:12/S:16 cross-check."
        ),
        stance="neutral",
        activity_level=0.90,
        influence_weight=0.08,
        sentiment_bias=0.0,
        response_delay_min=10,
        response_delay_max=50,
        active_sessions=["ASIAN", "EU", "US", "TRANSITION"],
        session_multipliers={"ASIAN": 0.90, "EU": 1.05, "US": 1.10, "TRANSITION": 0.75},
    )

    _SENSITIVITIES = [12, 16]   # S:12 and S:16 most predictive per ML analysis
    _ATR_LEN       = 14
    _ATR_MULT      = 1.5
    _FILTER_HIST   = 60         # bars of history used in batch range filter

    def analyze(
        self,
        closes: List[float],
        highs:  List[float],
        lows:   List[float],
        graph:  "MarketGraphMemory",
        htf_closes: Optional[List[float]] = None,
    ) -> Tuple[str, float]:
        """Run FLOOP Pro analysis. Returns (vote, confidence)."""
        try:
            n = len(closes)
            # BUG FIX: guard lowered from 210 → 200.
            # The kline acceptance gate in _analyze_timeframe requires ≥200 bars
            # (BTCUSDT_PARAMS["15m"]["min_candles"] = 200), so klines arrays of
            # size 200-209 are valid but were silently NEUTRAL here — wasting the
            # 10th agent.  All FLOOP computations (EMA200, ROC20, ATR14, range
            # filter×60 bars) work correctly with exactly 200 bars.
            if n < 200:
                return "NEUTRAL", 50.0

            score = 0.0   # positive → BUY, negative → SELL

            # ── 1. EMA Alignment (ML weight=4, +27pt WR lift) ────────────────
            ema_fast = _ema(closes, 60)
            ema_slow = _ema(closes, 200)
            ema_bull = False
            ema_bear = False
            if ema_fast is not None and ema_slow is not None:
                if ema_fast > ema_slow:
                    score    += 4.0
                    ema_bull  = True
                else:
                    score    -= 4.0
                    ema_bear  = True

            # ── 2. ROC Momentum (ML ~38% importance, max ±4 pts) ─────────────
            # Three ROC periods 5/10/20 — each bullish +1, bearish -1
            roc_raw = 0.0
            for period in (5, 10, 20):
                if n > period + 1:
                    base = closes[-(period + 1)]
                    if base > 0:
                        roc = (closes[-1] - base) / base * 100.0
                        roc_raw += 1.0 if roc > 0 else -1.0
            # roc_raw in [-3, +3] → scale to ±4
            score += roc_raw * (4.0 / 3.0)

            # ── 3. ATR/Price Volatility Norm (ML ~23% importance, ±2 pts) ───
            atr_val = _true_atr(closes, highs, lows, self._ATR_LEN)
            cur     = closes[-1]
            atr_norm = 0.0
            if atr_val is not None and cur > 0:
                atr_norm = atr_val / cur
                if 0.004 <= atr_norm <= 0.030:
                    # Good volatility regime: enough to profit, not chaotic
                    score += 2.0 if score >= 0 else -2.0
                elif atr_norm > 0.060:
                    # Chaotic volatility: dampen confidence
                    score *= 0.65

            # ── 4. Range Filter Sensitivity Cross-Check (ML ~12%, ±3 pts) ───
            rf_votes = [
                self._range_filter_trend(closes, highs, lows, s)
                for s in self._SENSITIVITIES
            ]
            n_bull_rf = rf_votes.count(1)
            n_bear_rf = rf_votes.count(-1)
            n_sens    = len(self._SENSITIVITIES)
            if n_bull_rf == n_sens:
                score += 3.0          # unanimous bullish across all sensitivities
            elif n_bear_rf == n_sens:
                score -= 3.0          # unanimous bearish across all sensitivities
            elif n_bull_rf > n_bear_rf:
                score += 1.5          # majority bullish
            elif n_bear_rf > n_bull_rf:
                score -= 1.5          # majority bearish

            # ── 5. HTF MA Filter — 1H EMA200 (ML ~13%, ±1 pt) ──────────────
            if htf_closes and len(htf_closes) >= 200:
                htf_ema200 = _ema(htf_closes, 200)
                if htf_ema200 is not None:
                    score += 1.0 if htf_closes[-1] > htf_ema200 else -1.0

            # ── Convert score to vote ─────────────────────────────────────────
            # Max possible: 4+4+2+3+1 = 14; min: -14
            abs_s = abs(score)
            if score >= 7.0:
                vote = "BUY"
                conf = min(62.0 + abs_s * 2.2, 90.0)
            elif score >= 4.0:
                vote = "BUY"
                conf = min(53.0 + abs_s * 1.8, 78.0)
            elif score <= -7.0:
                vote = "SELL"
                conf = min(62.0 + abs_s * 2.2, 90.0)
            elif score <= -4.0:
                vote = "SELL"
                conf = min(53.0 + abs_s * 1.8, 78.0)
            else:
                vote = "NEUTRAL"
                conf = 50.0

            graph.add_node(
                MarketEntityType.INDICATOR_STATE, "FLOOP_State",
                (f"FLOOP score={score:.1f} ema_bull={ema_bull} "
                 f"rf={rf_votes} atr_norm={atr_norm:.4f}"),
                {"floop_score": score, "ema_bull": ema_bull,
                 "rf_votes": rf_votes, "atr_norm": round(atr_norm, 5)}
            )
            return vote, min(conf, 90.0)

        except Exception:
            return "NEUTRAL", 50.0

    def _range_filter_trend(
        self,
        closes:      List[float],
        highs:       List[float],
        lows:        List[float],
        sensitivity: int,
        atr_mult:    float = 1.5,
        atr_len:     int   = 14,
    ) -> int:
        """
        FLOOP range filter batch computation.

        Returns +1 (bullish trend), -1 (bearish trend), 0 (indeterminate).

        Algorithm:
          rng = ATR × atr_mult × (sensitivity / 8.0)
          filter tracks close:
            - close > filter+rng  → filter = close - rng  (bullish break)
            - close < filter-rng  → filter = close + rng  (bearish break)
          Trend direction = last two filter values compared.
        """
        n = len(closes)
        if n < atr_len + 5:
            return 0

        # Work on last _FILTER_HIST bars
        use = min(n, self._FILTER_HIST)
        c_w = closes[-use:]
        h_w = highs[-use:] if len(highs) >= use else highs
        l_w = lows[-use:]  if len(lows)  >= use else lows
        m   = len(c_w)

        atr_val = _true_atr(c_w, h_w, l_w, atr_len)
        if atr_val is None or atr_val <= 0:
            return 0

        rng = atr_val * atr_mult * (sensitivity / 8.0)

        filt      = c_w[0]
        prev_filt = filt
        for i in range(1, m):
            c = c_w[i]
            if c > filt + rng:
                new_filt = c - rng
            elif c < filt - rng:
                new_filt = c + rng
            else:
                new_filt = filt
            if i == m - 2:
                prev_filt = filt
            filt = new_filt

        if filt > prev_filt:
            return 1
        elif filt < prev_filt:
            return -1
        return 0


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
        self.min_signal_strength = 65.0     # v8: raised for 10/10 unanimous requirement
        self.min_confidence      = 67.0     # v8: raised to match unanimous consensus gate
        self.min_swarm_consensus = 0.95     # v8: STRICT — ≥95% weighted consensus (10/10 unanimous)
        self.min_active_agents   = 8        # v8: quorum needs 8/10 agents non-NEUTRAL (was 5)
        self.min_rr_ratio        = 1.60     # v8: raised: minimum 1.60:1 risk-reward (was 1.55)

        # ── Initialize all 10 agents (v5: +FLOOPAgent) ──
        self.trend_agent      = TrendAgent()
        self.momentum_agent   = MomentumAgent()
        self.volume_agent     = VolumeAgent()
        self.volatility_agent = VolatilityAgent()
        self.orderflow_agent  = OrderFlowAgent()
        self.sentiment_agent  = SentimentAgent()
        self.funding_agent    = FundingFlowAgent()
        self.pivot_agent      = PivotSRAgent()          # v4: S/R agent
        self.floop_agent      = FLOOPAgent()            # v5: FLOOP Pro ML range filter
        self.ai_agent         = AIOrchestrationAgent()

        self._agents = [
            self.trend_agent, self.momentum_agent, self.volume_agent,
            self.volatility_agent, self.orderflow_agent, self.sentiment_agent,
            self.funding_agent, self.pivot_agent, self.floop_agent, self.ai_agent,
        ]

        # ── Per-symbol Market Knowledge Graphs ──
        # Each symbol gets its own isolated graph so scans don't contaminate
        # each other's TrendState / RSI_State / VWAP_State nodes.
        self._symbol_graphs: Dict[str, MarketGraphMemory] = {}

        # ── HTF klines cache: symbol → (klines, timestamp) ──
        # Caches 1H klines for HTF trend confirmation — refreshed every 5 min
        self._htf_cache: Dict[str, Tuple[list, float]] = {}
        self._htf_cache_ttl = 300.0  # 5 minutes

        # ── HTF 4H klines cache — refreshed every 15 min (4H bars change slowly) ──
        self._htf_4h_cache: Dict[str, Tuple[list, float]] = {}
        self._htf_4h_cache_ttl = 900.0  # 15 minutes

        # ── Session state ──
        self._current_session  = "UNKNOWN"
        self._session_activity = 1.0
        self._global_win_rate  = 0.335  # calibrated to actual historical win rate (~33.5%)

        self.logger.info("🐟 MiroFish Swarm Strategy v5.0 initialized — USDM Futures")
        self.logger.info("   Architecture: Profiles+Ontology+Graph+InsightForge+ReACT+Sessions+PivotSR+FLOOPPro")
        self.logger.info(f"   Agents: {len(self._agents)} | Quorum: {self.min_active_agents} | "
                         f"Consensus gate: {self.min_swarm_consensus:.0%}")
        self.logger.info("   v5 Enhancements: FLOOPPro(EMA60/200+ROC5/10/20+ATRnorm+RangeFilter+HTFfilter)")

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

        # ── HTF 1H klines prefetch for trend filter ────────────────────────────
        # BUG FIX: _htf_cache / _htf_cache_ttl were defined in __init__ but the
        # 1H klines were never actually fetched or passed to _analyze_timeframe.
        # This populates the cache once per symbol per 5-minute TTL window and
        # supplies htf_closes to every timeframe's analysis pipeline.
        htf_closes_1h: Optional[List[float]] = None
        _skip_htf = any(tf == "1h" for tf in self.timeframes)  # avoid double-fetch on 1H scans
        if not _skip_htf:
            try:
                _now_ts = time.time()
                _cached  = self._htf_cache.get(symbol)
                if _cached and (_now_ts - _cached[1]) < self._htf_cache_ttl:
                    htf_closes_1h = _cached[0]
                    self.logger.debug(f"[{symbol}] HTF 1H cache hit ({len(htf_closes_1h)} bars)")
                else:
                    _htf_raw = await asyncio.wait_for(
                        trader.get_market_data(symbol, "1h", 55), timeout=5.0
                    )
                    if _htf_raw and len(_htf_raw) >= 25:
                        htf_closes_1h = [float(k[4]) for k in _htf_raw]
                        self._htf_cache[symbol] = (htf_closes_1h, _now_ts)
                        # Cap cache size to 120 entries (same logic as _symbol_graphs)
                        if len(self._htf_cache) > 120:
                            for _ev in list(self._htf_cache.keys()):
                                if _ev != "BTCUSDT":
                                    del self._htf_cache[_ev]
                                    break
                        self.logger.debug(
                            f"[{symbol}] HTF 1H fetched — {len(htf_closes_1h)} bars cached"
                        )
            except Exception as _htf_err:
                self.logger.debug(f"[{symbol}] HTF 1H fetch skipped: {_htf_err}")

        # ── HTF 4H klines prefetch for MTF panel ──────────────────────────────
        # FIX: _htf_4h was always "NEUTRAL" because 4H data was never fetched.
        # Now fetched with a 15-minute cache TTL (4H bars move slowly).
        htf_closes_4h: Optional[List[float]] = None
        _skip_htf_4h = any(tf == "4h" for tf in self.timeframes)
        if not _skip_htf_4h:
            try:
                _now_ts4 = time.time()
                _cached4 = self._htf_4h_cache.get(symbol)
                if _cached4 and (_now_ts4 - _cached4[1]) < self._htf_4h_cache_ttl:
                    htf_closes_4h = _cached4[0]
                    self.logger.debug(f"[{symbol}] HTF 4H cache hit ({len(htf_closes_4h)} bars)")
                else:
                    _htf4_raw = await asyncio.wait_for(
                        trader.get_market_data(symbol, "4h", 30), timeout=5.0
                    )
                    if _htf4_raw and len(_htf4_raw) >= 10:
                        htf_closes_4h = [float(k[4]) for k in _htf4_raw]
                        self._htf_4h_cache[symbol] = (htf_closes_4h, _now_ts4)
                        if len(self._htf_4h_cache) > 120:
                            for _ev4 in list(self._htf_4h_cache.keys()):
                                if _ev4 != "BTCUSDT":
                                    del self._htf_4h_cache[_ev4]
                                    break
                        self.logger.debug(
                            f"[{symbol}] HTF 4H fetched — {len(htf_closes_4h)} bars cached"
                        )
            except Exception as _htf4_err:
                self.logger.debug(f"[{symbol}] HTF 4H fetch skipped: {_htf4_err}")

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
                    klines, tf, params, funding_rate, symbol, sym_graph,
                    htf_closes=htf_closes_1h,
                    htf_4h_closes=htf_closes_4h,
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
                                  graph: "MarketGraphMemory" = None,
                                  htf_closes: Optional[List[float]] = None,
                                  htf_4h_closes: Optional[List[float]] = None) -> Optional[SwarmSignal]:
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
            cur_price = closes[-1]   # BUG FIX: define early so Step 5.5 risk debate can use it
            if cur_price_check < 0.0001:
                self.logger.debug(
                    f"⚠️ [{symbol}|{tf}] Price ${cur_price_check:.8f} < $0.0001 "
                    f"— micro-price filtered"
                )
                return None

            session = self._current_session

            # ── Step 1: Run all deterministic agents ──
            trend_vote, trend_conf = self.trend_agent.analyze(
                closes, params, graph, highs=highs, lows=lows
            )

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

            # ── Step 1b: PivotSRAgent — institutional S/R analysis ─────────────
            # BUG FIX: pivot_agent was initialized in __init__ but never called —
            # the 9th agent was completely wasted.  Now properly integrated.
            pivot_vote, pivot_conf = self.pivot_agent.analyze(
                closes, highs, lows, volumes, graph
            )

            # ── Step 1c: FLOOPAgent — ML-optimized range filter (v5) ──────────
            # Implements FLOOP Pro Pine Script logic in pure Python.
            # Uses HTF 1H closes for the HTF MA filter (1pt of ML scoring).
            floop_vote, floop_conf = self.floop_agent.analyze(
                closes, highs, lows, graph, htf_closes=htf_closes
            )

            # ── Step 2: Build base agent votes (all 9 deterministic agents) ──
            base_votes = {
                "TrendAgent":       {"vote": trend_vote,    "conf": trend_conf},
                "MomentumAgent":    {"vote": momentum_vote, "conf": momentum_conf},
                "VolumeAgent":      {"vote": volume_vote,   "conf": volume_conf},
                "VolatilityAgent":  {"vote": vol_vote,      "conf": vol_conf},
                "OrderFlowAgent":   {"vote": of_vote,       "conf": of_conf},
                "SentimentAgent":   {"vote": sent_vote,     "conf": sent_conf},
                "FundingFlowAgent": {"vote": funding_vote,  "conf": funding_conf},
                "PivotSRAgent":     {"vote": pivot_vote,    "conf": pivot_conf},
                "FLOOPAgent":       {"vote": floop_vote,    "conf": floop_conf},
            }

            # ── Step 3: AI Orchestration (ReACT) ──
            try:
                ai_vote, ai_conf, ai_narrative, react_trace = await asyncio.wait_for(
                    self.ai_agent.analyze(
                        symbol, closes, base_votes, tf, graph, session
                    ),
                    timeout=10.0
                )
            except asyncio.CancelledError:
                raise  # never swallow CancelledError — propagate to the task runner
            except (asyncio.TimeoutError, Exception):
                # react_trace must be a valid JSON string (not bare "") so that any
                # downstream json.loads() or slicing on the string value is safe.
                ai_vote, ai_conf, ai_narrative, react_trace = "NEUTRAL", 50.0, "", "[]"

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
                "PivotSRAgent":         self.pivot_agent.PROFILE,
                "FLOOPAgent":           self.floop_agent.PROFILE,
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

            total_signal_weight = buy_weight + sell_weight
            # Check for near-zero total weight BEFORE normalization — after
            # normalization buy_weight + sell_weight is always 1.0, making
            # the check dead code and silently passing zero-signal cycles.
            if total_signal_weight < 0.005:
                return None
            buy_weight  /= total_signal_weight
            sell_weight /= total_signal_weight

            # ── Quorum check ──
            active_votes = [(n, d) for n, d in all_votes.items() if d["vote"] != "NEUTRAL"]
            n_active = len(active_votes)
            if n_active < self.min_active_agents:
                self.logger.debug(f"⚠️ Quorum not met: {n_active}/{len(all_votes)} agents active")
                return None

            # ── Consensus ──
            # buy_weight and sell_weight are now normalised → they sum to 1.0.
            # consensus = normalised dominant weight (fraction of directional signal).
            # BUG FIX: exact ties now return None (no directional bias).
            if buy_weight > sell_weight:
                action    = "BUY"
                consensus = buy_weight      # already normalised; equals buy / (buy+sell)
            elif sell_weight > buy_weight:
                action    = "SELL"
                consensus = sell_weight     # already normalised; equals sell / (buy+sell)
            else:
                self.logger.debug(f"⚠️ Exact weight tie {buy_weight:.4f} — no direction, skipped")
                return None

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

            # ── HARD UNANIMOUS GATE (v8.0) ────────────────────────────────────
            # 10/10 unanimous requirement: ZERO contrary agents allowed.
            # Any agent voting AGAINST the consensus direction → reject signal.
            # This is the highest-conviction filter — only signals where ALL
            # participating agents agree pass to the confidence/IRONS/NN gates.
            n_aligned  = len(aligned_agents)
            n_contrary = len(contrary_agents)

            if n_contrary > 0:
                self.logger.debug(
                    f"⚠️ [{symbol}|{tf}] STRICT 10/10 UNANIMOUS GATE: "
                    f"{n_contrary} contrary agent(s) "
                    f"({', '.join(n for n, _, _ in contrary_agents)}) "
                    f"oppose {action} — signal REJECTED (unanimous required)"
                )
                return None

            # ── Participation scoring ─────────────────────────────────────────
            participation_rate = n_active / len(all_votes)

            if participation_rate >= 0.60:     # ≥6/10 agents active
                participation_bonus = (participation_rate - 0.5) * 18
                weighted_conf = min(weighted_conf + participation_bonus, 98.0)
            elif participation_rate < 0.30:    # <3/10 agents active
                participation_penalty = (0.30 - participation_rate) * 30
                weighted_conf = max(weighted_conf - participation_penalty, 50.0)

            # Contrary agent divergence penalty
            if contrary_agents:
                contrary_w_sum = sum(w for _, _, w in contrary_agents)
                aligned_w_sum  = sum(w for _, _, w in aligned_agents)
                divergence = contrary_w_sum / max(aligned_w_sum, 0.01)
                if divergence > 0.4:
                    weighted_conf *= (1.0 - divergence * 0.15)

            # ── Unanimous consensus bonus ──────────────────────────────────────
            # When every non-neutral agent votes the same direction (0 contrarians)
            # AND at least 6/10 agents participated, this is an extremely rare and
            # highly reliable setup.  Apply a direct +4pt confidence bonus.
            # This partially offsets the strict min_confidence gate for elite setups.
            if n_contrary == 0 and n_active >= 6:
                weighted_conf = min(weighted_conf + 4.0, 95.0)

            session_boost = (self._session_activity - 1.0) * 3.0
            weighted_conf = min(max(weighted_conf + session_boost, 0.0), 95.0)

            signal_strength = min(weighted_conf * 0.55 + consensus * 100 * 0.45, 96.0)
            confidence = weighted_conf

            # ── Step 5.5: TradingAgents-style Risk Debate ───────────────────
            # 3 risk perspectives (Aggressive/Conservative/Neutral) evaluate
            # the signal from different angles, producing a net confidence adj.
            # Ported from TradingAgents risk_mgmt debate pattern.
            try:
                _risk_adj = 0.0

                _rsi_5a = _rsi(closes, 14) if len(closes) >= 16 else 50.0
                _rsi_5a = _rsi_5a if _rsi_5a is not None else 50.0
                _mom_4bar = ((closes[-1] - closes[-5]) / closes[-5] * 100
                             if len(closes) >= 5 and closes[-5] != 0 else 0.0)
                _atr_5a = atr / cur_price * 100 if atr and cur_price > 0 else 0.5

                _agg_score = 0.0
                if abs(_mom_4bar) > 0.3:
                    _mom_aligned = (
                        (action == "BUY" and _mom_4bar > 0) or
                        (action == "SELL" and _mom_4bar < 0)
                    )
                    _agg_score += 2.0 if _mom_aligned else -1.0
                if consensus >= 0.90:
                    _agg_score += 1.5
                if n_contrary == 0 and n_active >= 7:
                    _agg_score += 1.5
                _agg_score = max(-3.0, min(_agg_score, 4.0))

                _con_score = 0.0
                if action == "BUY" and _rsi_5a > 68:
                    _con_score -= 2.5
                elif action == "SELL" and _rsi_5a < 32:
                    _con_score -= 2.5
                if _atr_5a > 2.0:
                    _con_score -= 1.5
                if n_contrary >= 3:
                    _con_score -= 1.5
                _con_score = max(-4.0, min(_con_score, 1.0))

                _neu_score = 0.0
                if 40 < _rsi_5a < 60:
                    _neu_score += 0.5
                if 0.5 < _atr_5a < 1.5:
                    _neu_score += 0.5
                if consensus >= 0.80 and n_contrary <= 2:
                    _neu_score += 1.0
                _neu_score = max(-1.0, min(_neu_score, 2.0))

                _risk_adj = (_agg_score * 0.35 + _con_score * 0.40 + _neu_score * 0.25)
                _risk_adj = max(-4.0, min(_risk_adj, 3.5))
                confidence = max(50.0, min(95.0, confidence + _risk_adj))
                signal_strength = max(0.0, min(100.0, signal_strength + _risk_adj * 0.5))
                self.logger.debug(
                    f"[{symbol}|{tf}] Risk debate: agg={_agg_score:+.1f} "
                    f"con={_con_score:+.1f} neu={_neu_score:+.1f} "
                    f"→ adj={_risk_adj:+.1f}pt conf={confidence:.1f}%"
                )
            except Exception:
                pass

            # ── Step 5b: HTF 1H trend alignment filter ────────────────────────
            # BUG FIX: _htf_cache was designed and allocated in __init__ but the
            # actual klines were never fetched or used here. This wires the cache
            # into the decision pipeline so counter-trend signals on 15m/5m/3m
            # are penalised when the 1H EMA9/21 disagrees with the action.
            if htf_closes is not None and len(htf_closes) >= 25:
                try:
                    htf_ema9  = _ema(htf_closes, 9)
                    htf_ema21 = _ema(htf_closes, 21)
                    if htf_ema9 is not None and htf_ema21 is not None:
                        htf_bullish = htf_ema9 > htf_ema21
                        htf_aligned = (
                            (action == "BUY"  and htf_bullish) or
                            (action == "SELL" and not htf_bullish)
                        )
                        # EMA spread as a measure of trend strength on 1H
                        htf_spread_pct = abs(htf_ema9 - htf_ema21) / max(htf_ema21, 1e-9) * 100

                        if not htf_aligned:
                            if htf_spread_pct >= 0.50:
                                # Strong opposing HTF trend — hard reject to protect
                                # short-timeframe signals from being blown out by the
                                # higher-timeframe trend.  e.g. 15m BUY vs 1H bearish
                                # with EMA spread ≥ 0.5% = high-confidence macro trend.
                                self.logger.debug(
                                    f"[{symbol}|{tf}] 🚫 HTF 1H strong counter-trend "
                                    f"(spread={htf_spread_pct:.2f}%) — hard reject"
                                )
                                return None
                            else:
                                # Weak opposing HTF — soft penalty only
                                old_conf = confidence
                                confidence      = max(confidence      * 0.87, 50.0)
                                signal_strength = max(signal_strength * 0.87, 0.0)
                                self.logger.debug(
                                    f"[{symbol}|{tf}] ⬇️ HTF 1H counter-trend "
                                    f"(spread={htf_spread_pct:.2f}%) — "
                                    f"conf {old_conf:.1f}% → {confidence:.1f}%"
                                )
                        else:
                            # Trend-aligned: reward scaled by HTF trend strength
                            htf_reward = 1.04 if htf_spread_pct < 0.30 else 1.06
                            confidence      = min(confidence      * htf_reward, 95.0)
                            signal_strength = min(signal_strength * htf_reward, 100.0)
                            self.logger.debug(
                                f"[{symbol}|{tf}] ⬆️ HTF 1H aligned with {action} "
                                f"(spread={htf_spread_pct:.2f}%) — conf={confidence:.1f}%"
                            )
                except Exception:
                    pass

            # ── Step 5c: Supertrend directional confirmation ──────────────────
            # _supertrend() is fully implemented but was wired to zero agents.
            # Direction=+1 means bullish (price above ST), -1 = bearish.
            # Aligned → +3% confidence reward; contradicting → -10% penalty.
            if len(closes) >= 15 and highs and lows:
                try:
                    st_result = _supertrend(closes, highs, lows, period=10, multiplier=3.0)
                    if st_result is not None:
                        st_val, st_dir = st_result
                        st_aligned = (
                            (action == "BUY"  and st_dir == 1) or
                            (action == "SELL" and st_dir == -1)
                        )
                        if st_aligned:
                            confidence      = min(confidence      * 1.03, 95.0)
                            signal_strength = min(signal_strength * 1.03, 100.0)
                            self.logger.debug(
                                f"[{symbol}|{tf}] ⬆️ Supertrend aligned (+3%)"
                            )
                        else:
                            confidence      = max(confidence      * 0.90, 50.0)
                            signal_strength = max(signal_strength * 0.90, 0.0)
                            self.logger.debug(
                                f"[{symbol}|{tf}] ⬇️ Supertrend contra (-10%)"
                            )
                except Exception:
                    pass

            # ── Step 5d: Parabolic SAR directional confirmation ───────────────
            # SAR direction=+1 = price above SAR (bullish), -1 = bearish.
            # Small reward (+2pt) when aligned; penalty (-4pt) when contrary.
            if highs and lows and len(highs) >= 5:
                try:
                    sar_result = _parabolic_sar(highs, lows)
                    if sar_result is not None:
                        _sar_val, sar_dir = sar_result
                        sar_aligned = (
                            (action == "BUY"  and sar_dir == 1) or
                            (action == "SELL" and sar_dir == -1)
                        )
                        if sar_aligned:
                            confidence = min(confidence + 2.0, 95.0)
                        else:
                            confidence = max(confidence - 4.0, 50.0)
                except Exception:
                    pass

            # ── Step 5e: Ichimoku Cloud position filter ───────────────────────
            # Price above cloud → bullish; below cloud → bearish; inside → neutral.
            # Trades in the cloud get -5pt; trades against the cloud -10pt.
            if highs and lows and len(closes) >= 52:
                try:
                    ich = _ich_cloud(highs, lows, closes)
                    if ich:
                        cloud_top = ich.get("cloud_top")
                        cloud_bot = ich.get("cloud_bot")
                        _cur = closes[-1]
                        if cloud_top is not None and cloud_bot is not None:
                            above_cloud  = _cur > cloud_top
                            below_cloud  = _cur < cloud_bot
                            inside_cloud = not above_cloud and not below_cloud
                            if action == "BUY":
                                if above_cloud:
                                    confidence = min(confidence + 3.0, 95.0)
                                elif inside_cloud:
                                    confidence = max(confidence - 5.0, 50.0)
                                else:
                                    confidence = max(confidence - 10.0, 50.0)
                            else:
                                if below_cloud:
                                    confidence = min(confidence + 3.0, 95.0)
                                elif inside_cloud:
                                    confidence = max(confidence - 5.0, 50.0)
                                else:
                                    confidence = max(confidence - 10.0, 50.0)
                    else:
                        confidence = max(confidence - 3.0, 50.0)
                except Exception:
                    pass
            elif len(closes) < 52:
                confidence = max(confidence - 3.0, 50.0)

            if signal_strength < self.min_signal_strength or confidence < self.min_confidence:
                return None

            # ── Step 5f: Cheap rejection filters (before expensive TP/SL computation) ──
            cur_price = closes[-1]

            if atr and atr > 0 and cur_price > 0:
                atr_ratio_pct = atr / cur_price
                if atr_ratio_pct > 0.03:
                    self.logger.debug(
                        f"⚠️ [{symbol}|{tf}] ATR={atr_ratio_pct:.1%} > 3% "
                        f"(extreme volatility) — signal rejected"
                    )
                    return None

            _bb_u_f, _bb_m_f, _bb_l_f = _bollinger(closes, 20)
            if _bb_u_f is not None and _bb_l_f is not None and cur_price > 0:
                _bb_w_pct = (_bb_u_f - _bb_l_f) / cur_price * 100
                if _bb_w_pct < 0.25:
                    self.logger.debug(
                        f"⚠️ [{symbol}|{tf}] BB width {_bb_w_pct:.2f}% < 0.25% "
                        f"(extremely compressed market) — signal rejected"
                    )
                    return None

            _rsi_raw  = _rsi(closes, 14)
            rsi_val   = _rsi_raw if _rsi_raw is not None else 50.0
            # 20-bar average of bars preceding the current bar (excluding current
            # to avoid look-ahead bias in the volume ratio comparison).
            # Fixed from sum(volumes[-20:-1])/19 which only averaged 19 bars.
            _avg_vol  = (
                sum(volumes[-21:-1]) / 20 if len(volumes) >= 21
                else (sum(volumes[:-1]) / (len(volumes) - 1) if len(volumes) > 1 else 0.0)
            )
            vol_ratio = volumes[-1] / _avg_vol if _avg_vol > 0 else 1.0
            leverage  = LEVERAGE_MAP.get(tf, 15)

            # Kelly Criterion: moved to after Step 7 (uses actual TP1/SL distances)

            _cur_sess = getattr(self, "_current_session", "US")
            # Raised volume floor: ASIAN 0.65→0.70, others 0.75→0.80.
            # Low-volume signals fire on thin order books where fills are unreliable.
            _vol_floor = 0.70 if _cur_sess == "ASIAN" else 0.80
            if vol_ratio < _vol_floor:
                self.logger.debug(
                    f"⚠️ [{symbol}|{tf}] Volume ratio {vol_ratio:.2f}x < {_vol_floor:.2f}x "
                    f"— low-volume signal rejected ({_cur_sess} session)"
                )
                return None

            # ── Step 5g: RSI divergence confirmation (regular + hidden) ──
            if len(closes) >= 50:
                try:
                    _rsi_div = _rsi_divergence(closes, period=14, lookback=40)
                    if _rsi_div is not None:
                        _div_type, _div_strength = _rsi_div
                        _div_aligned = (
                            (action == "BUY"  and _div_type == "bullish") or
                            (action == "SELL" and _div_type == "bearish")
                        )
                        _hidden_aligned = (
                            (action == "BUY"  and _div_type == "hidden_bullish") or
                            (action == "SELL" and _div_type == "hidden_bearish")
                        )
                        if _div_aligned and _div_strength > 0.3:
                            confidence = min(confidence + 3.0, 95.0)
                            signal_strength = min(signal_strength + 2.0, 100.0)
                        elif _hidden_aligned and _div_strength > 0.2:
                            confidence = min(confidence + 2.0, 95.0)
                            signal_strength = min(signal_strength + 1.5, 100.0)
                        elif not _div_aligned and not _hidden_aligned and _div_strength > 0.5:
                            confidence = max(confidence - 5.0, 50.0)
                except Exception:
                    pass

            # ── Step 5h: Squeeze momentum confirmation ──
            if len(closes) >= 25 and highs and lows:
                try:
                    _sq = _squeeze_momentum(closes, highs, lows)
                    if _sq is not None:
                        _sq_on, _sq_val = _sq
                        if _sq_on:
                            _sq_aligned = (
                                (action == "BUY"  and _sq_val > 0) or
                                (action == "SELL" and _sq_val < 0)
                            )
                            if _sq_aligned:
                                confidence = min(confidence + 2.0, 95.0)
                            else:
                                confidence = max(confidence - 3.0, 50.0)
                except Exception:
                    pass

            # ── Step 5i: Market regime detection (v3 multi-indicator voting) ──
            # Upgraded from simple EMA/ATR check to moss-trade-bot v3 logic:
            # 4-factor voting: EMA20/50 cross, ADX+DI, ATR-rank, momentum
            _regime = "RANGING"
            if len(closes) >= 50 and atr and atr > 0:
                try:
                    _votes_bull = 0
                    _votes_bear = 0
                    _votes_side = 0

                    _ema20 = _ema(closes, 20)
                    _ema50 = _ema(closes, 50)
                    if _ema20 is not None and _ema50 is not None:
                        if _ema20 > _ema50:
                            _votes_bull += 1
                        elif _ema20 < _ema50:
                            _votes_bear += 1
                        else:
                            _votes_side += 1

                    _adx_proxy = _compute_adx_proxy(closes, highs, lows, 14) if highs and lows and len(closes) >= 30 else None
                    if _adx_proxy is not None:
                        _adx_val_5i, _pdi_5i, _mdi_5i = _adx_proxy
                        if _adx_val_5i > 25:
                            if _pdi_5i > _mdi_5i:
                                _votes_bull += 1
                            else:
                                _votes_bear += 1
                        else:
                            _votes_side += 1
                    else:
                        _votes_side += 1

                    _atr_norm = atr / cur_price if cur_price > 0 else 0.01
                    if _atr_norm < 0.008:
                        _votes_side += 1

                    _mom_ret = (closes[-1] - closes[-min(48, len(closes))]) / closes[-min(48, len(closes))] if closes[-min(48, len(closes))] != 0 else 0
                    if _mom_ret > 0.05:
                        _votes_bull += 1
                    elif _mom_ret < -0.05:
                        _votes_bear += 1
                    else:
                        _votes_side += 1

                    if _votes_bull > _votes_bear and _votes_bull > _votes_side:
                        _regime = "BULL"
                    elif _votes_bear > _votes_bull and _votes_bear > _votes_side:
                        _regime = "BEAR"
                    else:
                        _regime = "RANGING"

                    if _regime == "BULL":
                        if action == "BUY":
                            confidence = min(confidence + 2.5, 95.0)
                        else:
                            confidence = max(confidence - 2.0, 50.0)
                    elif _regime == "BEAR":
                        if action == "SELL":
                            confidence = min(confidence + 2.5, 95.0)
                        else:
                            confidence = max(confidence - 2.0, 50.0)
                    else:
                        # RANGING market — require maximum consensus or reject.
                        # Tightened from 0.88 → 0.95 to match global unanimous gate:
                        # contribute disproportionately to losses.
                        if consensus < 0.95:
                            self.logger.debug(
                                f"⚠️ [{symbol}|{tf}] RANGING regime + consensus={consensus:.0%} < 95% "
                                f"— low-conviction ranging signal rejected (unanimous gate)"
                            )
                            return None
                        confidence = max(confidence - 1.5, 50.0)
                except Exception:
                    pass

            # ── Step 5j: Systematic Trading Factors (awesome-systematic-trading) ──
            # Integrates academic research-backed factors for crypto futures:
            #
            # 1. Time-Series Momentum (Moskowitz et al, 2012, Sharpe 0.576):
            #    12-period lookback excess return → volatility-inverse confidence scaling.
            #    Assets with positive momentum get boosted; negative penalized.
            if len(closes) >= 14 and atr and atr > 0:
                try:
                    _ts_ret_12 = (closes[-1] - closes[-13]) / closes[-13] if closes[-13] != 0 else 0
                    _ts_vol = atr / cur_price if cur_price > 0 else 0.01
                    _ts_vol_inv = min(1.0 / max(_ts_vol, 0.005), 5.0)
                    _ts_mom_aligned = (
                        (action == "BUY" and _ts_ret_12 > 0.005) or
                        (action == "SELL" and _ts_ret_12 < -0.005)
                    )
                    _ts_mom_contra = (
                        (action == "BUY" and _ts_ret_12 < -0.01) or
                        (action == "SELL" and _ts_ret_12 > 0.01)
                    )
                    if _ts_mom_aligned:
                        _ts_boost = min(abs(_ts_ret_12) * _ts_vol_inv * 15.0, 3.0)
                        confidence = min(confidence + _ts_boost, 95.0)
                    elif _ts_mom_contra:
                        _ts_penalty = min(abs(_ts_ret_12) * _ts_vol_inv * 10.0, 4.0)
                        confidence = max(confidence - _ts_penalty, 50.0)
                except Exception:
                    pass

            # 2. Overnight Seasonality (Dyhrberg et al, 2022, Sharpe 0.892):
            #    BTC shows statistically significant positive returns 21:00-00:59 UTC.
            #    Boost BUY confidence during this window; penalize SELL.
            try:
                from datetime import datetime, timezone as _tz
                _utc_hour = datetime.now(_tz.utc).hour
                _is_overnight_window = _utc_hour in (21, 22, 23, 0)
                if _is_overnight_window and symbol in ("BTCUSDT", "ETHUSDT"):
                    if action == "BUY":
                        confidence = min(confidence + 1.5, 95.0)
                    elif action == "SELL":
                        confidence = max(confidence - 1.0, 50.0)
            except Exception:
                pass

            # 3. Short-Term Reversal (Jegadeesh 1990, Sharpe 0.816):
            #    Assets with extreme 1-week returns tend to reverse.
            #    If signal is contra-extreme-move, boost; if with-extreme-move, penalize.
            if len(closes) >= 8:
                try:
                    _st_ret_5 = (closes[-1] - closes[-6]) / closes[-6] if closes[-6] != 0 else 0
                    _extreme_up = _st_ret_5 > 0.08
                    _extreme_down = _st_ret_5 < -0.08
                    if _extreme_up and action == "SELL":
                        confidence = min(confidence + 2.0, 95.0)
                    elif _extreme_down and action == "BUY":
                        confidence = min(confidence + 2.0, 95.0)
                    elif _extreme_up and action == "BUY":
                        confidence = max(confidence - 3.0, 50.0)
                    elif _extreme_down and action == "SELL":
                        confidence = max(confidence - 3.0, 50.0)
                except Exception:
                    pass

            # 4. Volatility Persistence Filter (Mandelbrot, vol clustering):
            #    If recent volatility is rising (ATR expanding), tighten SL via reduced
            #    confidence for trend signals; if contracting (squeeze), boost breakouts.
            if len(closes) >= 20 and atr and atr > 0:
                try:
                    _recent_range = max(highs[-5:]) - min(lows[-5:])
                    _older_range = max(highs[-15:-5]) - min(lows[-15:-5])
                    if _older_range > 0:
                        _vol_expansion = _recent_range / _older_range
                        if _vol_expansion > 1.8:
                            confidence = max(confidence - 1.5, 50.0)
                        elif _vol_expansion < 0.5:
                            confidence = min(confidence + 1.5, 95.0)
                except Exception:
                    pass

            # ── Step 5k: InsiderTactics data-driven filters (4326-trade analysis) ──
            try:
                from datetime import datetime, timezone as _tz
                _utc_h = datetime.now(_tz.utc).hour

                _IT_BEST_HOURS  = {0, 2, 3, 11, 12, 19, 23}
                _IT_WORST_HOURS = {1, 5, 8, 16}
                if _utc_h in _IT_BEST_HOURS:
                    confidence = min(confidence + 2.0, 95.0)
                elif _utc_h in _IT_WORST_HOURS:
                    confidence = max(confidence - 3.0, 50.0)

                # Direction boost is now regime-aware and symmetric:
                # Only boost when the action aligns with the detected market regime.
                # Previously this unconditionally added +1.5pt to every BUY and
                # penalised every SELL by -1.0pt — biasing the bot toward longs
                # regardless of market structure. Counter-trend filtering is already
                # handled by the EMA200 gate (Step 5n).
                if action == "BUY" and _regime == "BULL":
                    confidence = min(confidence + 1.5, 95.0)
                elif action == "SELL" and _regime == "BEAR":
                    confidence = min(confidence + 1.5, 95.0)

                _IT_BLACKLIST = {
                    "TRUMPUSDT", "STOUSDT", "APRUSDT", "PUMPUSDT", "COSUSDT",
                    "ASTERUSDT", "MANAUSDT", "GMTUSDT", "XMRUSDT", "KAVAUSDT",
                }
                if symbol in _IT_BLACKLIST:
                    self.logger.debug(f"⚠️ [{symbol}] InsiderTactics blacklist (0% WR) — rejected")
                    return None

                _IT_BOOST_SYMS = {
                    "SIRENUSDT": 3.0, "BARDUSDT": 4.0, "ANIMEUSDT": 3.5,
                    "UNIUSDT": 3.0, "ARBUSDT": 3.0, "DASHUSDT": 3.0,
                    "BCHUSDT": 2.0, "DOTUSDT": 2.0, "BANDUSDT": 4.0,
                    "RLCUSDT": 4.0,
                }
                _IT_PENALTY_SYMS = {
                    "ADAUSDT": -2.0, "ETHUSDT": -1.0, "SOLUSDT": -1.5,
                    "RIVERUSDT": -3.0, "ZECUSDT": -3.0,
                }
                if symbol in _IT_BOOST_SYMS:
                    confidence = min(confidence + _IT_BOOST_SYMS[symbol], 95.0)
                elif symbol in _IT_PENALTY_SYMS:
                    confidence = max(confidence + _IT_PENALTY_SYMS[symbol], 50.0)
            except Exception:
                pass

            # ── Step 5m: TradingAgents Portfolio Manager 5-tier gate ────────
            # Synthesizes all accumulated evidence into a final rating:
            #   BUY(+3) / OVERWEIGHT(+1.5) / HOLD(0) / UNDERWEIGHT(-1.5) / SELL(-3)
            # Ported from TradingAgents portfolio_manager.py decision pattern.
            try:
                _pm_score = 0.0
                _pm_score += (consensus - 0.75) * 10.0
                _pm_score += (confidence - 70.0) * 0.1
                _pm_score += (participation_rate - 0.5) * 4.0
                if n_contrary == 0:
                    _pm_score += 1.5
                elif n_contrary >= 3:
                    _pm_score -= 2.0
                if _regime == "BULL" and action == "BUY":
                    _pm_score += 1.0
                elif _regime == "BEAR" and action == "SELL":
                    _pm_score += 1.0
                elif _regime == "RANGING":
                    _pm_score -= 0.5

                if _pm_score >= 4.0:
                    _pm_tier = "BUY"
                    _pm_adj = 3.0
                elif _pm_score >= 2.0:
                    _pm_tier = "OVERWEIGHT"
                    _pm_adj = 1.5
                elif _pm_score >= 0.0:
                    _pm_tier = "HOLD"
                    _pm_adj = 0.0
                elif _pm_score >= -2.0:
                    _pm_tier = "UNDERWEIGHT"
                    _pm_adj = -1.5
                else:
                    _pm_tier = "SELL"
                    _pm_adj = -3.0

                confidence = max(50.0, min(95.0, confidence + _pm_adj))
                signal_strength = max(0.0, min(100.0, signal_strength + _pm_adj * 0.5))
                self.logger.debug(
                    f"[{symbol}|{tf}] PM gate: score={_pm_score:.1f} "
                    f"tier={_pm_tier} adj={_pm_adj:+.1f}pt "
                    f"conf={confidence:.1f}%"
                )
            except Exception:
                pass

            if signal_strength < self.min_signal_strength or confidence < self.min_confidence:
                return None

            # ── Step 5n: EMA200 trend alignment (critical win-rate filter) ──
            # Only allow LONG signals when price is above EMA200 (bull market structure)
            # and SHORT signals when price is below EMA200 (bear market structure).
            # Counter-trend signals (against EMA200) require ≥95% swarm consensus.
            # Research: trading with the major trend improves win rate by 15-25%.
            if len(closes) >= 200:
                try:
                    _ema200 = _ema(closes, 200)
                    if _ema200 is not None:
                        _price_above_ema200 = closes[-1] > _ema200
                        _ema200_aligned = (
                            (action == "BUY"  and _price_above_ema200) or
                            (action == "SELL" and not _price_above_ema200)
                        )
                        if not _ema200_aligned:
                            # Raised from 0.92 → 0.95: counter-trend EMA200 trades
                            # require near-unanimous swarm consensus (9/10+ agents).
                            if consensus < 0.95:
                                self.logger.debug(
                                    f"⚠️ [{symbol}|{tf}] Against EMA200 trend "
                                    f"(price {'above' if _price_above_ema200 else 'below'} EMA200={_ema200:.4g}) "
                                    f"consensus={consensus:.0%} < 95% — signal rejected"
                                )
                                return None
                            else:
                                confidence = max(confidence - 5.0, 50.0)
                                self.logger.debug(
                                    f"⚠️ [{symbol}|{tf}] Counter-EMA200 trade allowed (consensus={consensus:.0%} ≥ 95%) "
                                    f"— conf penalized -5pt → {confidence:.1f}%"
                                )
                except Exception:
                    pass

            # ── Step 6: InsightForge market context ──
            insight          = graph.insight_forge(f"{symbol} {action} signal", n_facts=5)
            graph_insight_txt = insight.to_text()

            # ── Step 7: ATR-based price levels ──
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

            # Post-tick collision guard: ensure rounding doesn't collapse TP levels
            def _ensure_tp_separation(tp1_d, tp2_d, tp3_d, price, tick_fn, is_buy=True):
                _sign = 1 if is_buy else -1
                _t1 = tick_fn(price + _sign * tp1_d)
                _t2 = tick_fn(price + _sign * tp2_d)
                _t3 = tick_fn(price + _sign * tp3_d)
                if (_sign == 1 and _t2 <= _t1) or (_sign == -1 and _t2 >= _t1):
                    tp2_d = tp1_d + min_tp_gap * 1.5
                    _t2 = tick_fn(price + _sign * tp2_d)
                if (_sign == 1 and _t3 <= _t2) or (_sign == -1 and _t3 >= _t2):
                    tp3_d = tp2_d + min_tp_gap * 1.5
                return tp1_d, tp2_d, tp3_d

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

            tp1_dist, tp2_dist, tp3_dist = _ensure_tp_separation(
                tp1_dist, tp2_dist, tp3_dist, cur_price, _tick, is_buy=(action == "BUY")
            )

            if action == "BUY":
                stop_loss   = _tick(cur_price - sl_dist)
                take_profit = _tick(cur_price + tp1_dist)
                tp2         = _tick(cur_price + tp2_dist)
                tp3         = _tick(cur_price + tp3_dist)
                # Safety: SL strictly below entry
                if stop_loss >= cur_price:
                    stop_loss = _tick(cur_price * (1 - sl_pct))
                # Post-tick TP collision check
                if tp2 <= take_profit:
                    tp2 = _tick(take_profit + min_tp_gap)
                if tp3 <= tp2:
                    tp3 = _tick(tp2 + min_tp_gap)
            else:
                stop_loss   = _tick(cur_price + sl_dist)
                take_profit = _tick(cur_price - tp1_dist)
                tp2         = _tick(cur_price - tp2_dist)
                tp3         = _tick(cur_price - tp3_dist)
                # Safety: SL strictly above entry
                if stop_loss <= cur_price:
                    stop_loss = _tick(cur_price * (1 + sl_pct))
                # Post-tick TP collision check (SHORT: TP prices descend)
                if tp2 >= take_profit:
                    tp2 = _tick(take_profit - min_tp_gap)
                if tp3 >= tp2:
                    tp3 = _tick(tp2 - min_tp_gap)

            # ── TP4: additional 3.8× target (deep runner level) ──
            tp4_dist = max(tp3_dist + min_tp_gap * 2.0, cur_price * 0.040)
            tp4_dist = min(tp4_dist, cur_price * 0.20)   # cap at 20% from entry
            if action == "BUY":
                tp4 = _tick(cur_price + tp4_dist)
                if tp4 <= tp3:
                    tp4 = _tick(tp3 + min_tp_gap)
            else:
                tp4 = _tick(cur_price - tp4_dist)
                if tp4 >= tp3:
                    tp4 = _tick(tp3 - min_tp_gap)

            # R:R uses TP2 as the effective reward target (realistic for a partial-exit
            # strategy where Cornix closes 50% at TP1 and 35% at TP2).  TP1-only R:R
            # underestimates the true risk/reward of the trade plan.
            _sl_dist_rr = abs(stop_loss - cur_price)
            if _sl_dist_rr > 0:
                rr = abs(tp2 - cur_price) / _sl_dist_rr
            else:
                rr = 0.0

            # High-quality gate: reject weak R:R signals
            if rr < self.min_rr_ratio:
                self.logger.debug(
                    f"⚠️ [{tf}] R:R(TP2)={rr:.2f} below minimum {self.min_rr_ratio:.2f} — signal rejected"
                )
                return None

            # ── Kelly Criterion dynamic leverage (uses actual TP1/SL distances) ──
            # Default reduced 0.42 → 0.35 to reflect actual historical win rate
            # (~33-34%) and prevent over-leveraging on new sessions.
            _hist_wr = getattr(self, '_global_win_rate', 0.35)
            _consensus_p = min(consensus, 0.95) * (confidence / 100.0)
            _kelly_p = _hist_wr * 0.6 + _consensus_p * 0.4
            _kelly_p = max(0.05, min(_kelly_p, 0.85))
            _kelly_q = 1.0 - _kelly_p
            _kelly_b = abs(take_profit - cur_price) / max(abs(cur_price - stop_loss), 1e-10)
            if _kelly_b <= 0 or _kelly_b > 20:
                _kelly_b = 1.693
            _kelly_f = (_kelly_b * _kelly_p - _kelly_q) / max(_kelly_b, 0.01)
            _kelly_f = max(0.0, min(_kelly_f, 1.0)) * 0.5
            if _kelly_f > 0:
                leverage = max(3, min(int(leverage * (0.5 + _kelly_f)), 30))

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

            # ── Step 9: IRONS AI comprehensive scoring ──
            _irons_result = {}
            _htf_1h = "NEUTRAL"; _htf_4h = "NEUTRAL"
            try:
                # Use proper exponential moving averages (not SMA) for the HTF trend.
                # SMA over the last N bars ignores the weighting of recent prices
                # and produces the same result regardless of how prices have been
                # trending within those N bars — EMA correctly emphasises recent action.
                if htf_closes and len(htf_closes) >= 9:
                    _htf_ema9  = _ema(htf_closes, 9)
                    _htf_ema21 = _ema(htf_closes, 21) if len(htf_closes) >= 21 else _htf_ema9
                    if _htf_ema9 is not None and _htf_ema21 is not None:
                        if _htf_ema9 > _htf_ema21:
                            _htf_1h = "BUY"
                        elif _htf_ema9 < _htf_ema21:
                            _htf_1h = "SELL"
            except Exception:
                pass

            # ── 4H trend from prefetched 4H klines ──────────────────────────
            try:
                if htf_4h_closes and len(htf_4h_closes) >= 9:
                    _4h_ema9  = _ema(htf_4h_closes, 9)
                    _4h_ema21 = _ema(htf_4h_closes, 21) if len(htf_4h_closes) >= 21 else _4h_ema9
                    if _4h_ema9 is not None and _4h_ema21 is not None:
                        if _4h_ema9 > _4h_ema21:
                            _htf_4h = "BUY"
                        elif _4h_ema9 < _4h_ema21:
                            _htf_4h = "SELL"
            except Exception:
                pass

            try:
                from SignalMaestro.irons_ai_scorer import IRONSScorer
                _macd_l, _macd_s = _macd(closes)
                _irons_result = IRONSScorer.score(
                    closes=closes, highs=highs, lows=lows, volumes=volumes,
                    action=action, atr=atr, rsi=rsi_val,
                    macd_line=_macd_l, macd_sig=_macd_s,
                    swarm_consensus=consensus, confidence=confidence,
                    vol_ratio=vol_ratio, regime=_regime,
                    htf_1h=_htf_1h, htf_4h=_htf_4h,
                )
            except Exception as _e:
                self.logger.debug(f"IRONSScorer error: {_e}")

            return SwarmSignal(
                symbol=symbol,
                action=action,
                entry_price=cur_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                take_profit_1=take_profit,
                take_profit_2=tp2,
                take_profit_3=tp3,
                take_profit_4=tp4,
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
                irons_score=_irons_result.get("score", 0),
                irons_risk=_irons_result.get("risk_label", ""),
                irons_categories=_irons_result.get("categories", {}),
                irons_indicators=_irons_result.get("indicators", {}),
                irons_patterns=_irons_result.get("patterns", []),
                irons_squeeze=_irons_result.get("squeeze_on", False),
                mtf_1h=_htf_1h,
                mtf_4h=_htf_4h,
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

def _compute_adx_proxy(closes: List[float], highs: List[float], lows: List[float],
                       period: int = 14) -> Optional[Tuple[float, float, float]]:
    """
    Compute true smoothed ADX (Average Directional Index) plus +DI/-DI.

    Bug Fix: Previous implementation Wilder-smoothed TR/+DM/-DM correctly but
    then computed a single raw DX from the final smoothed values.  This is NOT
    ADX — ADX is the Wilder-smoothed average of all individual DX values.
    A single raw DX can spike from 0→80 in one bar, making the RANGING regime
    detector extremely noisy and generating false ranging/trending regimes.

    Correct algorithm (Wilder 1978):
      1. Compute raw TR, +DM, -DM for each bar.
      2. Wilder-smooth each series.
      3. Compute +DI and -DI from the smoothed series.
      4. Compute DX from +DI and -DI for each smoothed bar.
      5. Wilder-smooth the DX series to get ADX.

    Returns (adx, last_pdi, last_mdi).
    """
    n = len(closes)
    if n < period * 2 + 2 or len(highs) < n or len(lows) < n:
        return None
    plus_dm_list: List[float] = []
    minus_dm_list: List[float] = []
    tr_list: List[float] = []
    for i in range(1, n):
        h_diff = highs[i] - highs[i - 1]
        l_diff = lows[i - 1] - lows[i]
        plus_dm_list.append(max(h_diff, 0.0) if h_diff > l_diff else 0.0)
        minus_dm_list.append(max(l_diff, 0.0) if l_diff > h_diff else 0.0)
        tr_list.append(max(highs[i] - lows[i],
                           abs(highs[i] - closes[i - 1]),
                           abs(lows[i] - closes[i - 1])))
    if len(tr_list) < period + 1:
        return None

    # Wilder-smooth TR, +DM, -DM and accumulate DX values for ADX smoothing
    atr_s = sum(tr_list[:period])
    pdm_s = sum(plus_dm_list[:period])
    mdm_s = sum(minus_dm_list[:period])
    dx_vals: List[float] = []
    last_pdi, last_mdi = 0.0, 0.0
    for i in range(period, len(tr_list)):
        atr_s = atr_s - atr_s / period + tr_list[i]
        pdm_s = pdm_s - pdm_s / period + plus_dm_list[i]
        mdm_s = mdm_s - mdm_s / period + minus_dm_list[i]
        atr_guard = max(atr_s, 1e-10)
        last_pdi = pdm_s / atr_guard * 100.0
        last_mdi = mdm_s / atr_guard * 100.0
        denom = last_pdi + last_mdi
        if denom > 0.0:
            dx_vals.append(abs(last_pdi - last_mdi) / denom * 100.0)

    if not dx_vals:
        return None

    # Wilder-smooth DX values to produce ADX
    if len(dx_vals) < period:
        adx = sum(dx_vals) / len(dx_vals)
    else:
        adx = sum(dx_vals[:period]) / period
        for dv in dx_vals[period:]:
            adx = (adx * (period - 1) + dv) / period

    return (adx, last_pdi, last_mdi)


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
    # Exact boundary: pure uptrend → RSI must be exactly 100.0 (not 99.01).
    # Pure downtrend → exactly 0.0.  Normal case: standard RS formula.
    if avg_loss == 0.0:
        return 100.0
    if avg_gain == 0.0:
        return 0.0
    rs = avg_gain / avg_loss
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
    """
    Stochastic %D oscillator — smoothed Stochastic (d_period-SMA of raw %K).

    Bug Fix: Previous implementation computed raw %K only and never used the
    d_period parameter.  Raw %K is extremely noisy on crypto (can swing 0-100
    in a single bar), producing false momentum confirmation signals.
    %D = SMA(d_period) of %K provides the standard smoothed signal used by
    virtually all professional charting packages and removes bar-level noise.

    Returns value in range [0, 100].
    """
    needed = k_period + d_period - 1
    if len(closes) < needed:
        return None
    k_vals: List[float] = []
    for shift in range(d_period - 1, -1, -1):
        if shift == 0:
            win   = closes[-k_period:]
            price = closes[-1]
        else:
            win   = closes[-(k_period + shift):-shift]
            price = closes[-1 - shift]
        lo = min(win)
        hi = max(win)
        k_vals.append(50.0 if hi == lo else (price - lo) / (hi - lo) * 100.0)
    return sum(k_vals) / len(k_vals)


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
            if len(data) < p:
                return []
            sm = sum(data[:p])
            result = [sm]
            for v in data[p:]:
                sm = sm - (sm / p) + v
                result.append(sm)
            return result

        atr_s    = _wilder_smooth(tr_vals, period)
        pdm_s    = _wilder_smooth(plus_dm, period)
        mdm_s    = _wilder_smooth(minus_dm, period)
        if not atr_s or not pdm_s or not mdm_s:
            return None
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


# ─────────────────────────────────────────────────────────────────────────────
# Advanced Indicator Helpers — v4 Production Enhancement
# ─────────────────────────────────────────────────────────────────────────────

def _supertrend(closes: List[float], highs: List[float], lows: List[float],
                period: int = 10, multiplier: float = 3.0) -> Optional[Tuple[float, int]]:
    """
    Supertrend indicator.
    Returns (supertrend_value, direction) where direction=+1 means bullish (price above ST),
    direction=-1 means bearish (price below ST).
    Returns None if insufficient data.
    """
    n = min(len(closes), len(highs), len(lows))
    if n < period + 2:
        return None
    c, h, l = closes[-n:], highs[-n:], lows[-n:]

    # Compute ATR using true range
    atr_vals = []
    for i in range(1, n):
        tr = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
        atr_vals.append(tr)

    # Wilder ATR smoothing — only need to verify we have enough bars;
    # the actual per-bar atr_smooth is recomputed from scratch below in the
    # flipping state machine so we don't need to persist the series here.
    if len(atr_vals) < period + 1:
        return None

    # Build upper/lower basic bands, then apply Supertrend flipping logic
    # We need at least 2 computed bars for the flip logic
    # Use simplified but correct approach: compute on the last few candles
    results = []
    atr_smooth = sum(atr_vals[:period]) / period
    # BUG FIX: was `atr_vals[i-1]` which double-counted the last seed element
    # at i=period (Wilder smoothing starts on the element AFTER the seed window).
    # Correct: at each bar i, consume atr_vals[i] (not atr_vals[i-1]) so the
    # seed window covers atr_vals[0..period-1] and the Wilder updates start at
    # atr_vals[period].  Guard for the final bar where i may equal len(atr_vals).
    for i in range(period, n):
        if i < len(atr_vals):
            atr_smooth = (atr_smooth * (period - 1) + atr_vals[i]) / period
        hl2 = (h[i] + l[i]) / 2.0
        basic_upper = hl2 + multiplier * atr_smooth
        basic_lower = hl2 - multiplier * atr_smooth
        results.append((basic_upper, basic_lower, c[i]))

    if not results:
        return None

    # Supertrend flip state machine
    final_upper = results[0][0]
    final_lower = results[0][1]
    # BUG FIX: initial direction compared close against basic_upper (almost always
    # false since basic_upper = HL2 + mult*ATR is above the close by construction).
    # Correct check: if close is above basic_lower the trend starts bullish.
    direction   = 1 if results[0][2] > results[0][1] else -1

    for bu, bl, close in results[1:]:
        # Upper band: only move down
        new_upper = min(bu, final_upper) if close < final_upper else bu
        # Lower band: only move up
        new_lower = max(bl, final_lower) if close > final_lower else bl

        if direction == 1:
            if close < new_lower:
                direction = -1
                final_upper = new_upper
                final_lower = new_lower
            else:
                final_lower = new_lower
                final_upper = new_upper
        else:
            if close > new_upper:
                direction = 1
                final_upper = new_upper
                final_lower = new_lower
            else:
                final_upper = new_upper
                final_lower = new_lower

    st_val = final_lower if direction == 1 else final_upper
    return st_val, direction


def _pivot_points(highs: List[float], lows: List[float],
                  closes: List[float]) -> Optional[Dict[str, float]]:
    """
    Classic daily pivot points computed from the previous full candle window.
    Returns dict with keys: P, R1, R2, R3, S1, S2, S3.
    Uses the most recent 20-bar window as the "previous session".
    """
    if len(closes) < 22:
        return None
    # Use previous 20-candle window as the reference period
    h = max(highs[-21:-1])
    l = min(lows[-21:-1])
    c = closes[-2]   # previous close (one candle behind current)
    p = (h + l + c) / 3.0
    r1 = 2 * p - l
    r2 = p + (h - l)
    r3 = h + 2 * (p - l)
    s1 = 2 * p - h
    s2 = p - (h - l)
    s3 = l - 2 * (h - p)
    return {"P": p, "R1": r1, "R2": r2, "R3": r3, "S1": s1, "S2": s2, "S3": s3}


def _keltner_channel(closes: List[float], highs: List[float],
                     lows: List[float], ema_period: int = 20,
                     atr_period: int = 10, multiplier: float = 2.0
                     ) -> Optional[Tuple[float, float, float]]:
    """
    Keltner Channel: Middle = EMA(20), Upper = EMA + 2×ATR(10), Lower = EMA - 2×ATR(10).
    Returns (upper, middle, lower) or None.
    Used with Bollinger Bands to detect squeeze: when BB is inside KC → breakout imminent.
    """
    n = min(len(closes), len(highs), len(lows))
    if n < max(ema_period, atr_period) + 5:
        return None
    c, h, l = closes[-n:], highs[-n:], lows[-n:]
    mid = _ema(c, ema_period)
    if mid is None:
        return None
    atr_val = _true_atr(c, h, l, atr_period)
    if atr_val is None:
        atr_val = _atr_close(c, atr_period) or 0.0
    upper = mid + multiplier * atr_val
    lower = mid - multiplier * atr_val
    return upper, mid, lower


def _parabolic_sar(highs: List[float], lows: List[float],
                   af_start: float = 0.02, af_max: float = 0.20
                   ) -> Optional[Tuple[float, int]]:
    """
    Parabolic SAR — trailing stop indicator.
    Returns (sar_value, direction) where direction=+1 = bullish (SAR below price),
    direction=-1 = bearish (SAR above price).
    Requires at least 5 candles.
    """
    n = min(len(highs), len(lows))
    if n < 5:
        return None
    h, l = highs[-n:], lows[-n:]

    # Initial state: assume bullish on first bar
    direction = 1
    sar       = l[0]
    ep        = h[0]   # extreme point
    af        = af_start

    for i in range(1, n):
        prev_sar = sar
        sar = sar + af * (ep - sar)

        if direction == 1:
            # Bullish
            sar = min(sar, l[i-1], l[i-2] if i >= 2 else l[i-1])
            if l[i] < sar:
                # Flip to bearish
                direction = -1
                sar = ep
                ep  = l[i]
                af  = af_start
            else:
                if h[i] > ep:
                    ep = h[i]
                    af = min(af + af_start, af_max)
        else:
            # Bearish
            sar = max(sar, h[i-1], h[i-2] if i >= 2 else h[i-1])
            if h[i] > sar:
                # Flip to bullish
                direction = 1
                sar = ep
                ep  = h[i]
                af  = af_start
            else:
                if l[i] < ep:
                    ep = l[i]
                    af = min(af + af_start, af_max)

    return sar, direction


def _ich_cloud(highs: List[float], lows: List[float], closes: List[float],
               tenkan: int = 9, kijun: int = 26, senkou_b: int = 52
               ) -> Optional[Dict[str, float]]:
    """
    Full Ichimoku Cloud computation.
    Returns dict with tenkan, kijun, senkou_a, senkou_b, chikou.
    Senkou A/B define the cloud (support/resistance zones).
    """
    n = min(len(closes), len(highs), len(lows))
    if n < senkou_b:
        return None
    h, l, c = highs[-n:], lows[-n:], closes[-n:]

    def mid_point(period, idx_end):
        sl = h[max(0, idx_end - period):idx_end]
        ll = l[max(0, idx_end - period):idx_end]
        if not sl or not ll:
            return None
        return (max(sl) + min(ll)) / 2.0

    ten_val = mid_point(tenkan, n)
    kij_val = mid_point(kijun, n)
    sA      = ((ten_val or 0) + (kij_val or 0)) / 2.0 if ten_val and kij_val else None
    sB      = mid_point(senkou_b, n)
    chikou  = c[-1]  # current close plotted 26 periods back

    return {
        "tenkan":   ten_val,
        "kijun":    kij_val,
        "senkou_a": sA,
        "senkou_b": sB,
        "chikou":   chikou,
        "cloud_top": max(sA, sB) if sA is not None and sB is not None else None,
        "cloud_bot": min(sA, sB) if sA is not None and sB is not None else None,
    }


def _rsi_divergence(closes: List[float], period: int = 14,
                    lookback: int = 50) -> Optional[Tuple[str, float]]:
    """
    RSI divergence detection — scans last `lookback` bars for price/RSI divergence.
    Returns ("bullish", strength) for bullish divergence, ("bearish", strength) for bearish,
    or None if no significant divergence.
    strength ∈ [0, 1] reflects how clear the divergence is.

    O(n) single-pass Wilder RSI — replaces the O(n²) loop that called _rsi() from
    scratch for each of the `lookback` bars (80 symbols × 2 calls/cycle = 160 full
    RSI recalculations per scan round).
    """
    if len(closes) < lookback + period + 5:
        return None
    recent = closes[-(lookback + period):]

    # Incremental Wilder RSI series — one forward pass over `recent`
    gains  = [max(recent[i] - recent[i - 1], 0.0) for i in range(1, len(recent))]
    losses = [max(recent[i - 1] - recent[i], 0.0) for i in range(1, len(recent))]

    if len(gains) < period:
        return None

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def _to_rsi(ag: float, al: float) -> float:
        if al == 0.0:
            return 100.0
        if ag == 0.0:
            return 0.0
        return 100.0 - (100.0 / (1.0 + ag / al))

    rsi_vals = [_to_rsi(avg_gain, avg_loss)]

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rsi_vals.append(_to_rsi(avg_gain, avg_loss))

    if len(rsi_vals) < 10:
        return None

    price_window = recent[-len(rsi_vals):]

    # Find swing lows for bullish divergence (price makes lower low, RSI makes higher low)
    n = len(price_window)
    # Use simple 3-bar swing: local minima and maxima
    price_lows_idx  = [i for i in range(2, n-2)
                       if price_window[i] <= price_window[i-1] and price_window[i] <= price_window[i+1]
                       and price_window[i] <= price_window[i-2] and price_window[i] <= price_window[i+2]]
    price_highs_idx = [i for i in range(2, n-2)
                       if price_window[i] >= price_window[i-1] and price_window[i] >= price_window[i+1]
                       and price_window[i] >= price_window[i-2] and price_window[i] >= price_window[i+2]]

    # Bullish divergence: price lower low + RSI higher low
    if len(price_lows_idx) >= 2:
        i1, i2 = price_lows_idx[-2], price_lows_idx[-1]
        price_ll = price_window[i2] < price_window[i1]
        rsi_hl   = rsi_vals[i2] > rsi_vals[i1]
        if price_ll and rsi_hl:
            price_diff = (price_window[i1] - price_window[i2]) / max(price_window[i1], 1e-9)
            rsi_diff   = (rsi_vals[i2] - rsi_vals[i1]) / max(abs(rsi_vals[i1]) + 1, 1e-9)
            strength   = min((price_diff * 10 + rsi_diff * 5), 1.0)
            if strength > 0.1:
                return "bullish", strength

    # Bearish divergence: price higher high + RSI lower high
    if len(price_highs_idx) >= 2:
        i1, i2 = price_highs_idx[-2], price_highs_idx[-1]
        price_hh = price_window[i2] > price_window[i1]
        rsi_lh   = rsi_vals[i2] < rsi_vals[i1]
        if price_hh and rsi_lh:
            price_diff = (price_window[i2] - price_window[i1]) / max(price_window[i1], 1e-9)
            rsi_diff   = (rsi_vals[i1] - rsi_vals[i2]) / max(abs(rsi_vals[i1]) + 1, 1e-9)
            strength   = min((price_diff * 10 + rsi_diff * 5), 1.0)
            if strength > 0.1:
                return "bearish", strength

    # Hidden bullish divergence: price higher low + RSI lower low (trend continuation)
    if len(price_lows_idx) >= 2:
        i1, i2 = price_lows_idx[-2], price_lows_idx[-1]
        price_hl = price_window[i2] > price_window[i1]
        rsi_ll   = rsi_vals[i2] < rsi_vals[i1]
        if price_hl and rsi_ll:
            price_diff = (price_window[i2] - price_window[i1]) / max(price_window[i1], 1e-9)
            rsi_diff   = (rsi_vals[i1] - rsi_vals[i2]) / max(abs(rsi_vals[i1]) + 1, 1e-9)
            strength   = min((price_diff * 8 + rsi_diff * 4), 0.8)
            if strength > 0.15:
                return "hidden_bullish", strength

    # Hidden bearish divergence: price lower high + RSI higher high (trend continuation)
    if len(price_highs_idx) >= 2:
        i1, i2 = price_highs_idx[-2], price_highs_idx[-1]
        price_lh = price_window[i2] < price_window[i1]
        rsi_hh   = rsi_vals[i2] > rsi_vals[i1]
        if price_lh and rsi_hh:
            price_diff = (price_window[i1] - price_window[i2]) / max(price_window[i1], 1e-9)
            rsi_diff   = (rsi_vals[i2] - rsi_vals[i1]) / max(abs(rsi_vals[i1]) + 1, 1e-9)
            strength   = min((price_diff * 8 + rsi_diff * 4), 0.8)
            if strength > 0.15:
                return "hidden_bearish", strength

    return None


def _volume_profile_poc(closes: List[float], volumes: List[float],
                        n_bins: int = 20) -> Optional[float]:
    """
    Volume Profile — Point of Control (POC): price level with highest traded volume.
    Returns the POC price level which acts as a strong S/R magnet.
    """
    if len(closes) < 20 or len(volumes) < 20:
        return None
    n = min(len(closes), len(volumes))
    c, v = closes[-n:], volumes[-n:]
    lo, hi = min(c), max(c)
    if hi == lo:
        return None
    bin_size = (hi - lo) / n_bins
    bins = [0.0] * n_bins
    for price, vol in zip(c, v):
        idx = min(int((price - lo) / bin_size), n_bins - 1)
        bins[idx] += vol
    max_bin = max(range(n_bins), key=lambda i: bins[i])
    poc = lo + (max_bin + 0.5) * bin_size
    return poc


def _squeeze_momentum(closes: List[float], highs: List[float],
                      lows: List[float], bb_period: int = 20,
                      kc_period: int = 20, kc_atr: int = 14,
                      kc_mult: float = 1.5) -> Optional[Tuple[bool, float]]:
    """
    Squeeze Momentum (TTM Squeeze): detects when Bollinger Bands are inside
    Keltner Channels (high-probability breakout setup).
    Returns (squeeze_on, momentum_value) where:
    - squeeze_on = True means BB is inside KC (breakout imminent)
    - momentum_value > 0 = bullish breakout likely, < 0 = bearish likely
    """
    n = min(len(closes), len(highs), len(lows))
    if n < max(bb_period, kc_period) + 5:
        return None

    c, h, l = closes[-n:], highs[-n:], lows[-n:]

    # Bollinger Bands
    bb_up, bb_mid, bb_lo = _bollinger(c, bb_period, 2.0)
    if bb_up is None:
        return None

    # Keltner Channel
    kc_result = _keltner_channel(c, h, l, kc_period, kc_atr, kc_mult)
    if kc_result is None:
        return None
    kc_up, kc_mid, kc_lo = kc_result

    # Squeeze: BB inside KC
    squeeze_on = (bb_up < kc_up) and (bb_lo > kc_lo)

    # Momentum: linear regression of (close - midpoint)
    # BUG FIX: use kc_mid (EMA) for both sides to eliminate SMA/EMA lag-mismatch.
    # bb_mid is SMA, kc_mid is EMA — averaging them creates jitter during high vol.
    if n < 5:
        return squeeze_on, 0.0
    mom_vals = []
    mid_ref = kc_mid if kc_mid is not None else (bb_mid if bb_mid is not None else c[-1])
    for i in range(-5, 0):
        mom_vals.append(c[i] - mid_ref)
    momentum = mom_vals[-1] - mom_vals[0] if len(mom_vals) >= 2 else 0.0

    return squeeze_on, momentum
