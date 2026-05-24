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
    # Anthropic direct / OpenRouter paid
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
    # OpenRouter via their API path (prefix anthropic/)
    "anthropic/claude-3-5-sonnet-20241022": {"input": 3.0,  "output": 15.0},
    "anthropic/claude-3-5-haiku-20241022":  {"input": 0.80, "output": 4.0},
    "openai/gpt-4o-mini":                   {"input": 0.15, "output": 0.60},
    # v5.9: OpenRouter free-tier fallbacks — confirmed working 2026-05-07
    # REMOVED: meta-llama/llama-3.2-3b-instruct:free → 404/rate_limit storm
    # REMOVED: meta-llama/llama-3.1-8b-instruct:free → 404
    # REMOVED: google/gemma-2-9b-it:free → 404
    # REMOVED: mistralai/mistral-7b-instruct:free → 404
    # REMOVED: qwen/qwen-2.5-7b-instruct:free → unconfirmed
    # REMOVED: microsoft/phi-3-mini-128k-instruct:free → 404
    "meta-llama/llama-3.3-70b-instruct:free":                         {"input": 0.0, "output": 0.0},
    "qwen/qwen3-next-80b-a3b-instruct:free":                          {"input": 0.0, "output": 0.0},
    "qwen/qwen3-coder:free":                                          {"input": 0.0, "output": 0.0},
    # REMOVED: qwen/qwen3-235b-a22b:free → 404 confirmed live log 2026-05-13 [v18.68]
    # REMOVED: qwen/qwen3-30b-a3b:free  → 404 confirmed live log 2026-05-13 [v18.68] (also April 2026)
    # v18.72: Qwen3-235B-A22B re-added under correct OpenRouter slug (GitHub repo: QwenLM/Qwen3)
    "qwen/qwen3-235b-a22b-instruct:free":                             {"input": 0.0, "output": 0.0},
    # v18.74: AEON-7 Qwen3.6-27B — tentative, 404-circuit-breaks gracefully (slug pending confirmation)
    "aeon-7/qwen3.6-27b-aeon-ultimate-uncensored-dflash:free":       {"input": 0.0, "output": 0.0},
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free":  {"input": 0.0, "output": 0.0},
    "z-ai/glm-4.5-air:free":                                         {"input": 0.0, "output": 0.0},
    # REMOVED: google/gemma-3-12b-it:free → 404 confirmed 2026-05-08 live log [v18.32]
    # REMOVED: meta-llama/llama-4-scout:free → 404 confirmed live log 2026-05-08 [v18.33]
    "deepseek/deepseek-r1:free":                                      {"input": 0.0, "output": 0.0},
    # v18.90: New confirmed-working OpenRouter free models (2026-05-22)
    "microsoft/phi-4-reasoning:free":                                 {"input": 0.0, "output": 0.0},
    "google/gemma-3-27b-it:free":                                     {"input": 0.0, "output": 0.0},
    "mistralai/devstral-small:free":                                  {"input": 0.0, "output": 0.0},
    "mistralai/mistral-small-3.2-24b-instruct:free":                  {"input": 0.0, "output": 0.0},
    "tngtech/deepseek-r1t-chimera:free":                              {"input": 0.0, "output": 0.0},
}

BASELINE_MODEL = "anthropic/claude-3-5-sonnet-20241022"

# v5.9+: TIER_MODELS — paid models first (best quality), then OpenRouter free-tier
# fallbacks at end so SmartLLMRouter always resolves to a working endpoint.
# Free models are rate-limited but never return 401 with a valid OpenRouter key.
# Updated 2026-05-07: replaced 404 models with confirmed-working tier from GODMOD3.
_FREE_SIMPLE = [
    # REMOVED: meta-llama/llama-4-maverick:free → 404 confirmed live log 2026-05-09 [v18.54]
    # REMOVED: qwen/qwen3-235b-a22b:free → 404 confirmed live log 2026-05-13 [v18.68]
    # REMOVED: qwen/qwen3-30b-a3b:free → 404 confirmed live log 2026-05-13 [v18.68] (also April 2026)
    # REMOVED: meta-llama/llama-4-scout:free → 404 confirmed live log 2026-05-08 [v18.33]
    # v18.72: Qwen3-235B-A22B re-added with corrected OpenRouter slug (QwenLM/Qwen3 GitHub release)
    # v18.76: deepseek-r1 re-confirmed working 2026-05-14 — added to simple pool for fast reasoning
    # v18.90: Added phi-4-reasoning, gemma-3-27b, devstral-small, mistral-small-3.2, chimera (confirmed 2026-05-22)
    "qwen/qwen3-235b-a22b-instruct:free",
    "qwen/qwen3-coder:free",
    "deepseek/deepseek-r1:free",
    "tngtech/deepseek-r1t-chimera:free",                         # v18.90: fast R1-based reasoning
    "meta-llama/llama-3.3-70b-instruct:free",
    "microsoft/phi-4-reasoning:free",                            # v18.90: strong reasoning, 404-safe
    "google/gemma-3-27b-it:free",                                # v18.90: 27B IT model confirmed
    "mistralai/devstral-small:free",                             # v18.90: Mistral code+reasoning
    "mistralai/mistral-small-3.2-24b-instruct:free",             # v18.90: balanced 24B model
    "qwen/qwen3-14b:free",                                       # v18.92: Qwen3 14B — same family as confirmed 235B; efficient smaller sibling
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
    "z-ai/glm-4.5-air:free",
    "aeon-7/qwen3.6-27b-aeon-ultimate-uncensored-dflash:free",   # tentative; 404-safe
]
_FREE_REASONING = [
    # REMOVED: deepseek/deepseek-r1:free → 404 confirmed live log 2026-05-08 [v18.37/v18.46]
    # REMOVED: meta-llama/llama-4-maverick:free → 404 confirmed live log 2026-05-09 [v18.54]
    # REMOVED: qwen/qwen3-235b-a22b:free → 404 confirmed live log 2026-05-13 [v18.68]
    # REMOVED: qwen/qwen3-30b-a3b:free → 404 confirmed live log 2026-05-13 [v18.68]
    # v18.72: Qwen3-235B-A22B re-added with corrected slug — 235B MoE, top reasoning model
    # v18.76: deepseek-r1 re-confirmed working 2026-05-14 — re-added to reasoning pool
    # v18.90: Added phi-4-reasoning, chimera, gemma-3-27b, devstral (confirmed reasoning tier)
    "qwen/qwen3-235b-a22b-instruct:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "deepseek/deepseek-r1:free",
    "tngtech/deepseek-r1t-chimera:free",                         # v18.90: R1T chimera blend
    "microsoft/phi-4-reasoning:free",                            # v18.90: phi-4 dedicated reasoning
    "meta-llama/llama-3.3-70b-instruct:free",
    "z-ai/glm-4.5-air:free",
    "qwen/qwen3-coder:free",
    "google/gemma-3-27b-it:free",                                # v18.90: 27B instruction-tuned
    "mistralai/devstral-small:free",                             # v18.90: Mistral code+reasoning
    "mistralai/mistral-small-3.2-24b-instruct:free",             # v18.90: balanced 24B
    "qwen/qwen3-14b:free",                                       # v18.92: Qwen3 14B — confirmed same family as 235B
    "aeon-7/qwen3.6-27b-aeon-ultimate-uncensored-dflash:free",   # tentative; 404-safe
]

TIER_MODELS = {
    # v19.1: ZERO bare slugs — ALL paid entries use explicit provider/model format
    # (e.g. 'anthropic/...', 'openai/...') which OpenRouter resolves correctly.
    # Bare slugs like 'claude-sonnet-4-6', 'gpt-4o-mini', 'claude-3-7-sonnet-20250219'
    # are Anthropic/OpenAI direct-API only — they return 401/404 on OpenRouter
    # WITHOUT ANTHROPIC_API_KEY/OPENAI_API_KEY and trigger the 3-failure auto-quarantine
    # on EVERY cold boot, causing "Free-tier fast-path ACTIVATED" on startup.
    # ROOT CAUSE FIX: remove all bare slugs → quarantine never fires on cold boot.
    # Free-tier (:free) models follow the same provider/model:free format and are fine.
    "SIMPLE": [
        "anthropic/claude-3-5-haiku-20241022",
        "anthropic/claude-3-haiku-20240307",
        "openai/gpt-4o-mini",
        "openai/gpt-4.1-mini",
        "google/gemini-flash-1.5",
    ] + _FREE_SIMPLE,
    "MEDIUM": [
        "anthropic/claude-3-5-sonnet-20241022",
        "anthropic/claude-3-5-haiku-20241022",
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "google/gemini-pro-1.5",
    ] + _FREE_SIMPLE,
    "COMPLEX": [
        "anthropic/claude-3-5-sonnet-20241022",
        "anthropic/claude-3-opus-20240229",
        "openai/gpt-4o",
        "openai/gpt-4-turbo",
        "google/gemini-pro-1.5",
    ] + _FREE_REASONING,
    "REASONING": [
        "anthropic/claude-3-5-sonnet-20241022",
        "anthropic/claude-3-opus-20240229",
        "openai/gpt-4o",
        "openai/gpt-4-turbo",
        "google/gemini-pro-1.5",
    ] + _FREE_REASONING,
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
        # v18.96: Free-tier fast-path flag.  Set True when first quarantine fires
        # (indicates API key has no paid credits).  Causes _select_model() to
        # skip paid models and prefer free-tier (:free suffix) models first,
        # eliminating the 3-failure burn-in cycle for each paid model per session.
        self._free_tier_mode: bool = False
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
        # v19.1: Guard — only track OpenRouter-format slugs (must contain '/').
        # Bare slugs like 'claude-sonnet-4-6' or 'gpt-4o-mini' are direct
        # Anthropic/OpenAI API models, NOT OpenRouter endpoints.  Recording
        # their auth failures here would trigger false quarantine + free-tier
        # fast-path for OpenRouter paid models.
        if "/" not in model:
            if success:
                logger.debug(f"[SmartLLM] skip record_outcome (bare slug, non-OpenRouter): {model}")
            return
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
            # v18.95: Auto-quarantine — at exactly 3 failures with zero successes
            # in this session, disable the model for 1 hour to stop hammering
            # dead endpoints (404-storm / 503 prevention).  Fires once (== 3)
            # so the log is not repeated on every subsequent failure.
            # Does not permanently disable — model retries on next engine start.
            if h.failures == 3 and h.successes == 0 and not h.permanently_disabled:
                h.disabled_until = time.time() + 3600.0
                logger.info(
                    f"[SmartLLM v18.96] Auto-quarantine: '{model}' "
                    f"→ 3 failures / 0 successes → disabled 1h (endpoint dead or rate-limited)"
                )
                # v18.96: Enable free-tier fast-path when first paid model is quarantined.
                # This signals the key has no paid credits → skip paid model burn-ins.
                if not self._free_tier_mode and not model.endswith(":free"):
                    self._free_tier_mode = True
                    logger.info(
                        f"[SmartLLM v18.96] Free-tier fast-path ACTIVATED — "
                        f"paid model quarantined → routing will prefer :free models first"
                    )

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

    def _select_model(self, tier: str) -> Optional[str]:
        candidates = TIER_MODELS.get(tier, TIER_MODELS["MEDIUM"])

        # v18.96: Free-tier fast-path — when API key has no paid credits, build
        # a preferred list that puts :free models first to avoid 3-failure burn-in
        # on paid models.  Falls back to the standard candidate order if no free
        # model is available.
        if self._free_tier_mode:
            _free_first = [m for m in candidates if m.endswith(":free")]
            _paid_rest  = [m for m in candidates if not m.endswith(":free")]
            candidates  = _free_first + _paid_rest

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

        for _fallback_tier in ("SIMPLE", "MEDIUM", "COMPLEX"):
            _fb_cands = TIER_MODELS.get(_fallback_tier, [])
            if self._free_tier_mode:
                _fb_cands = [m for m in _fb_cands if m.endswith(":free")] + \
                            [m for m in _fb_cands if not m.endswith(":free")]
            for model in _fb_cands:
                health = self._health.get(model)
                if health and not health.is_available:
                    continue
                return model

        _free_fallback = [m for m in (candidates or []) if m.endswith(":free")]
        return (_free_fallback[0] if _free_fallback else None) or \
               (candidates[0] if candidates else "gpt-4o-mini")

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = MODEL_PRICING.get(model, {"input": 3.0, "output": 15.0})
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost
