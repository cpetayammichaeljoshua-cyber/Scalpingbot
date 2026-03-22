#!/usr/bin/env python3
"""
Smart LLM Router — ClawRouter-Inspired Intelligent Model Routing
================================================================
Adapted from BlockRunAI/ClawRouter (github.com/BlockRunAI/ClawRouter)

Analyzes each AI request across multiple weighted dimensions and routes
to the optimal model in the available cascade.  Tracks model health,
estimated costs, and cumulative savings.

Tier system (maps to available models):
  SIMPLE    → cheapest / fastest  (haiku, gpt-4o-mini)
  MEDIUM    → balanced            (sonnet, gpt-4o)
  COMPLEX   → best reasoning      (opus, sonnet-latest)
  REASONING → extended thinking   (opus with chain-of-thought)

Dimensions scored (adapted from ClawRouter rules.ts):
  1. Token count          — prompt length proxy
  2. Technical complexity  — indicator / market terms
  3. Reasoning markers     — multi-step / analytical
  4. Code / structured     — JSON output, structured data
  5. Domain specificity    — trading-specific complexity
  6. Multi-step patterns   — sequential reasoning
  7. Question complexity   — compound questions
  8. Market volatility     — high-vol needs better models
  9. Agent count           — many agents = more synthesis

Confidence calibration via sigmoid (from ClawRouter).
"""

import time
import math
import logging
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    model: str
    tier: str
    confidence: float
    reasoning: str
    cost_estimate: float
    savings_pct: float
    dimensions_fired: List[str]


@dataclass
class ModelHealth:
    model_id: str
    total_calls: int = 0
    successes: int = 0
    failures: int = 0
    avg_latency_ms: float = 0.0
    last_success: float = 0.0
    last_failure: float = 0.0
    disabled_until: float = 0.0
    permanently_disabled: bool = False

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.successes / self.total_calls

    @property
    def is_available(self) -> bool:
        if self.permanently_disabled:
            return False
        if self.disabled_until > time.time():
            return False
        return True


MODEL_PRICING = {
    "claude-sonnet-4-6":            {"input": 3.0,  "output": 15.0},
    "claude-opus-4-5":              {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-5":            {"input": 3.0,  "output": 15.0},
    "claude-haiku-4-5":             {"input": 0.80, "output": 4.0},
    "claude-3-7-sonnet-20250219":   {"input": 3.0,  "output": 15.0},
    "claude-3-5-sonnet-20241022":   {"input": 3.0,  "output": 15.0},
    "claude-3-5-haiku-20241022":    {"input": 0.80, "output": 4.0},
    "claude-3-5-sonnet-20240620":   {"input": 3.0,  "output": 15.0},
    "claude-3-opus-20240229":       {"input": 15.0, "output": 75.0},
    "gpt-4o-mini":                  {"input": 0.15, "output": 0.60},
    "gpt-4o":                       {"input": 2.50, "output": 10.0},
}

BASELINE_MODEL = "claude-opus-4-5"

TIER_MODELS = {
    "SIMPLE": [
        "claude-haiku-4-5", "claude-3-5-haiku-20241022",
        "gpt-4o-mini",
    ],
    "MEDIUM": [
        "claude-sonnet-4-6", "claude-sonnet-4-5",
        "claude-3-7-sonnet-20250219", "claude-3-5-sonnet-20241022",
        "claude-3-5-sonnet-20240620",
        "gpt-4o-mini",
    ],
    "COMPLEX": [
        "claude-sonnet-4-6", "claude-opus-4-5", "claude-sonnet-4-5",
        "claude-3-7-sonnet-20250219", "claude-3-5-sonnet-20241022",
        "claude-3-opus-20240229",
        "gpt-4o-mini",
    ],
    "REASONING": [
        "claude-opus-4-5", "claude-sonnet-4-6", "claude-sonnet-4-5",
        "claude-3-7-sonnet-20250219", "claude-3-opus-20240229",
        "claude-3-5-sonnet-20241022",
        "gpt-4o-mini",
    ],
}

TRADING_KEYWORDS = [
    "fibonacci", "ichimoku", "bollinger", "macd", "rsi",
    "divergence", "confluence", "liquidity", "orderflow",
    "order flow", "market structure", "supply zone", "demand zone",
    "breakout", "consolidation", "accumulation", "distribution",
    "wyckoff", "elliott", "harmonic", "pivot",
]

REASONING_KEYWORDS = [
    "analyze", "evaluate", "compare", "synthesize", "reason",
    "explain why", "step by step", "think through", "consider",
    "weigh", "trade-off", "tradeoff", "pros and cons",
    "risk assessment", "probability", "likelihood",
]

SIMPLE_KEYWORDS = [
    "list", "summarize", "format", "convert", "translate",
    "extract", "count", "yes or no", "true or false",
]


class SmartLLMRouter:
    """
    ClawRouter-inspired intelligent model router for the trading bot.
    Scores each AI request across multiple dimensions, selects the optimal
    tier, and returns the best available model from the cascade.
    """

    TIER_BOUNDARIES = {
        "simple_medium": -0.2,
        "medium_complex": 0.35,
        "complex_reasoning": 0.70,
    }
    CONFIDENCE_STEEPNESS = 5.0

    DIMENSION_WEIGHTS = {
        "tokenCount":          0.15,
        "technicalComplexity": 0.20,
        "reasoningMarkers":    0.20,
        "structuredOutput":    0.10,
        "domainSpecificity":   0.15,
        "multiStep":           0.08,
        "questionComplexity":  0.05,
        "simpleIndicators":    0.07,
    }

    def __init__(self, available_models: Optional[List[str]] = None):
        self._health: Dict[str, ModelHealth] = {}
        self._total_requests = 0
        self._total_savings = 0.0
        self._available_models = available_models or []
        logger.info(
            f"🧭 SmartLLMRouter initialized — "
            f"ClawRouter-inspired multi-dimensional routing | "
            f"{len(self._available_models)} models available"
        )

    def update_available_models(self, models: List[str]):
        self._available_models = models

    def route(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_output_tokens: int = 300,
        market_volatility: float = 0.0,
        agent_count: int = 10,
    ) -> RoutingDecision:
        self._total_requests += 1

        full_text = f"{system_prompt or ''} {prompt}".lower()
        estimated_tokens = max(1, len(full_text) // 4)

        dimensions = self._score_dimensions(
            prompt.lower(), full_text, estimated_tokens,
            market_volatility, agent_count,
        )

        weighted_score = sum(
            d["score"] * self.DIMENSION_WEIGHTS.get(d["name"], 0)
            for d in dimensions
        )
        signals = [d["signal"] for d in dimensions if d["signal"]]

        reasoning_count = sum(
            1 for kw in REASONING_KEYWORDS
            if kw in prompt.lower()
        )
        if reasoning_count >= 3:
            tier = "REASONING"
            confidence = max(
                self._calibrate_confidence(max(weighted_score, 0.3)),
                0.85,
            )
        else:
            tier, confidence = self._score_to_tier(weighted_score)

        model = self._select_model(tier)
        cost_est = self._estimate_cost(model, estimated_tokens, max_output_tokens)
        baseline = self._estimate_cost(BASELINE_MODEL, estimated_tokens, max_output_tokens)
        savings = max(0, (baseline - cost_est) / baseline) if baseline > 0 else 0

        self._total_savings += (baseline - cost_est) if baseline > cost_est else 0

        reasoning_str = (
            f"score={weighted_score:.2f} tier={tier} | "
            f"{', '.join(signals[:4])}"
        )

        return RoutingDecision(
            model=model,
            tier=tier,
            confidence=confidence,
            reasoning=reasoning_str,
            cost_estimate=cost_est,
            savings_pct=savings,
            dimensions_fired=signals,
        )

    def record_outcome(
        self, model: str, success: bool, latency_ms: float = 0,
    ):
        if model not in self._health:
            self._health[model] = ModelHealth(model_id=model)
        h = self._health[model]
        h.total_calls += 1
        if success:
            h.successes += 1
            h.last_success = time.time()
            if h.avg_latency_ms == 0:
                h.avg_latency_ms = latency_ms
            else:
                h.avg_latency_ms = h.avg_latency_ms * 0.9 + latency_ms * 0.1
        else:
            h.failures += 1
            h.last_failure = time.time()

    def disable_model(self, model: str, duration_s: float = 0, permanent: bool = False):
        if model not in self._health:
            self._health[model] = ModelHealth(model_id=model)
        h = self._health[model]
        if permanent:
            h.permanently_disabled = True
        elif duration_s > 0:
            h.disabled_until = time.time() + duration_s

    def enable_model(self, model: str):
        if model in self._health:
            self._health[model].permanently_disabled = False
            self._health[model].disabled_until = 0

    def get_stats(self) -> Dict:
        return {
            "total_requests": self._total_requests,
            "total_savings_usd": round(self._total_savings, 4),
            "model_health": {
                m: {
                    "calls": h.total_calls,
                    "success_rate": round(h.success_rate, 3),
                    "avg_latency_ms": round(h.avg_latency_ms, 1),
                    "available": h.is_available,
                }
                for m, h in self._health.items()
            },
        }

    def _score_dimensions(
        self,
        user_text: str,
        full_text: str,
        estimated_tokens: int,
        market_volatility: float,
        agent_count: int,
    ) -> List[Dict]:
        dims = []

        if estimated_tokens < 100:
            dims.append({"name": "tokenCount", "score": -1.0, "signal": f"short ({estimated_tokens}tok)"})
        elif estimated_tokens > 500:
            dims.append({"name": "tokenCount", "score": 1.0, "signal": f"long ({estimated_tokens}tok)"})
        else:
            dims.append({"name": "tokenCount", "score": 0, "signal": None})

        tech_matches = [kw for kw in TRADING_KEYWORDS if kw in user_text]
        if len(tech_matches) >= 4:
            dims.append({"name": "technicalComplexity", "score": 1.0, "signal": f"technical ({', '.join(tech_matches[:3])})"})
        elif len(tech_matches) >= 2:
            dims.append({"name": "technicalComplexity", "score": 0.5, "signal": f"technical ({', '.join(tech_matches[:2])})"})
        else:
            dims.append({"name": "technicalComplexity", "score": 0, "signal": None})

        reason_matches = [kw for kw in REASONING_KEYWORDS if kw in user_text]
        if len(reason_matches) >= 2:
            dims.append({"name": "reasoningMarkers", "score": 1.0, "signal": f"reasoning ({', '.join(reason_matches[:2])})"})
        elif len(reason_matches) >= 1:
            dims.append({"name": "reasoningMarkers", "score": 0.5, "signal": "reasoning-light"})
        else:
            dims.append({"name": "reasoningMarkers", "score": 0, "signal": None})

        if re.search(r'json|structured|schema|format.*output', user_text):
            dims.append({"name": "structuredOutput", "score": 0.5, "signal": "structured-output"})
        else:
            dims.append({"name": "structuredOutput", "score": 0, "signal": None})

        domain_matches = sum(1 for kw in [
            "funding rate", "open interest", "liquidation",
            "perpetual", "futures", "leverage", "margin",
            "order book", "depth", "spread", "slippage",
        ] if kw in user_text)
        if domain_matches >= 3:
            dims.append({"name": "domainSpecificity", "score": 1.0, "signal": "domain-heavy"})
        elif domain_matches >= 1:
            dims.append({"name": "domainSpecificity", "score": 0.4, "signal": "domain-light"})
        else:
            dims.append({"name": "domainSpecificity", "score": 0, "signal": None})

        multi_step_patterns = [r'first.*then', r'step \d', r'\d\.\s']
        if any(re.search(p, user_text) for p in multi_step_patterns):
            dims.append({"name": "multiStep", "score": 0.5, "signal": "multi-step"})
        else:
            dims.append({"name": "multiStep", "score": 0, "signal": None})

        q_count = user_text.count('?')
        if q_count > 3:
            dims.append({"name": "questionComplexity", "score": 0.5, "signal": f"{q_count} questions"})
        else:
            dims.append({"name": "questionComplexity", "score": 0, "signal": None})

        simple_matches = sum(1 for kw in SIMPLE_KEYWORDS if kw in user_text)
        if simple_matches >= 2:
            dims.append({"name": "simpleIndicators", "score": -1.0, "signal": "simple-task"})
        elif simple_matches >= 1:
            dims.append({"name": "simpleIndicators", "score": -0.5, "signal": "simple-light"})
        else:
            dims.append({"name": "simpleIndicators", "score": 0, "signal": None})

        return dims

    def _score_to_tier(self, score: float) -> Tuple[str, float]:
        b = self.TIER_BOUNDARIES
        if score < b["simple_medium"]:
            tier = "SIMPLE"
            dist = b["simple_medium"] - score
        elif score < b["medium_complex"]:
            tier = "MEDIUM"
            dist = min(score - b["simple_medium"], b["medium_complex"] - score)
        elif score < b["complex_reasoning"]:
            tier = "COMPLEX"
            dist = min(score - b["medium_complex"], b["complex_reasoning"] - score)
        else:
            tier = "REASONING"
            dist = score - b["complex_reasoning"]

        confidence = self._calibrate_confidence(dist)
        return tier, confidence

    def _calibrate_confidence(self, distance: float) -> float:
        return 1.0 / (1.0 + math.exp(-self.CONFIDENCE_STEEPNESS * distance))

    def _select_model(self, tier: str) -> str:
        candidates = TIER_MODELS.get(tier, TIER_MODELS["MEDIUM"])

        for model in candidates:
            if model not in self._available_models:
                continue
            health = self._health.get(model)
            if health and not health.is_available:
                continue
            return model

        for model in candidates:
            health = self._health.get(model)
            if health and not health.is_available:
                continue
            return model

        return candidates[0] if candidates else "gpt-4o-mini"

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = MODEL_PRICING.get(model, {"input": 3.0, "output": 15.0})
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost
