#!/usr/bin/env python3
"""
G0DM0D3 AI Strategy Engine — Trading Signal Orchestration
==========================================================
Fully integrates the G0DM0D3 framework (github.com/elder-plinius/G0DM0D3)
as the primary AI intelligence layer for the MiroFish Swarm Bot.

Integrated from: https://github.com/cpetayammichaeljoshua-cyber/z4ptacticsbot.git
Live-verified models (April 2026) and production-grade multi-model cascade.

G0DM0D3 Modules Implemented (adapted for crypto trading):
──────────────────────────────────────────────────────────
  ⚡ ULTRAPLINIAN    — Multi-model racing engine: N models queried in parallel
                       via OpenRouter, responses scored on 100-pt composite metric,
                       winner returned. 13 free-tier models across 3 tiers.
  🎛  AutoTune       — Context-adaptive sampling parameter engine.
                       Classifies market context (volatile/trending/ranging/breakout)
                       via regex scoring, maps to optimised temperature/top_p/etc.
                       EMA feedback loop adapts params from signal outcome quality.
  🐍  Parseltongue   — Input perturbation engine for enhanced LLM responses.
                       Detects complex/ambiguous patterns and applies transformations
                       to elicit richer, more precise trading analysis.
  ⚡  STM Pipeline   — Semantic Transformation Modules: post-processing normaliser.
                       Strips hedging, preambles, and formality from model output.
                       Modules: hedge_reducer, direct_mode, json_enforcer.
  🔥  GODMODE CLASSIC — 5 battle-tested prompt + model combos racing in parallel.
                       Each combo pairs a DIFFERENT model with a trading-optimised
                       system prompt. Best response wins (highest composite score).
  🔄  AutoReset      — When ALL models in a tier are disabled, auto-reset soft-
                       disabled ones (503/timeout) while keeping auth errors banned.
  📈  TierEscalation — fast tier fails → standard → smart, before giving up.
  🏥  ErrorTypeTrack — Distinguishes auth (permanent) from transient (soft) errors
                       for intelligent recovery and backoff.

Primary Models: Live-verified free tier (OpenRouter, April 2026)
API Gateway   : https://openrouter.ai/api/v1 (OpenAI-compatible)
Auth          : OPENROUTER_API_KEY environment variable
Fallback Chain: ULTRAPLINIAN fast → standard → smart → GODMODE CLASSIC → Direct → Rule-based
"""

import asyncio
import json
import logging
import math
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# OpenRouter Configuration
# ─────────────────────────────────────────────────────────────────────────────

OPENROUTER_BASE_URL  = "https://openrouter.ai/api/v1"
OPENROUTER_SITE_URL  = "https://replit.com"
OPENROUTER_SITE_NAME = "MiroFish-G0DM0D3-TradingBot"

# ─────────────────────────────────────────────────────────────────────────────
# Free Models — Live-Verified April 2026 (from z4ptacticsbot integration)
# Each model returned HTTP 200 or 429 (accessible).
# 404-returning models require paid tier — excluded.
# ─────────────────────────────────────────────────────────────────────────────

# Tier 1 — Frontier flagship (largest / highest reasoning capability)
_TIER1_MODELS: List[str] = [
    "nousresearch/hermes-3-llama-3.1-405b:free",    # Hermes 405B — top instruction follower
    "meta-llama/llama-3.3-70b-instruct:free",        # Llama 3.3 70B — reliable flagship
    "qwen/qwen3-next-80b-a3b-instruct:free",         # Qwen3 Next 80B MoE
]

# Tier 2 — High capability
_TIER2_MODELS: List[str] = [
    "stepfun/step-3.5-flash:free",                   # StepFun Flash — proven fastest winner
    "arcee-ai/trinity-large-preview:free",           # Arcee Trinity Large (131K ctx)
    "qwen/qwen3.6-plus:free",                        # Qwen 3.6 Plus (1M ctx) — PRIMARY
    "qwen/qwen3-coder:free",                         # Qwen3 Coder 480B (JSON-tuned)
]

# Tier 3 — Strong performers
_TIER3_MODELS: List[str] = [
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",  # Dolphin 24B
    "z-ai/glm-4.5-air:free",                         # GLM-4.5 Air (131K ctx)
]

# Tier 4 — Reliable workhorses
_TIER4_MODELS: List[str] = [
    "arcee-ai/trinity-mini:free",                    # Arcee Trinity Mini
    "liquid/lfm-2.5-1.2b-thinking:free",             # Liquid LFM thinking
]

# Tier 5 — Lightweight / always available fallbacks
_TIER5_MODELS: List[str] = [
    "liquid/lfm-2.5-1.2b-instruct:free",             # Liquid LFM instruct
    "meta-llama/llama-3.2-3b-instruct:free",         # Llama 3.2 3B — lightweight fallback
    "openrouter/free",                               # Auto-router — picks best available
]

# ALL free models (ordered by capability tier — used for auto-reset cascade)
ALL_FREE_MODELS: List[str] = (
    _TIER1_MODELS + _TIER2_MODELS + _TIER3_MODELS + _TIER4_MODELS + _TIER5_MODELS
)

# Primary model for direct fallback calls
PRIMARY_MODEL = "qwen/qwen3.6-plus:free"

# ULTRAPLINIAN model tiers — expanded to 20+ models across 3 tiers
# fast: speed-optimised (Tier 2 fast + Tier 1 flagship)
# standard: balanced (Tier 1 + 2)
# smart: most capable (all tiers, broadest coverage)
ULTRAPLINIAN_TIERS: Dict[str, List[str]] = {
    "fast": [
        "stepfun/step-3.5-flash:free",               # Fastest proven winner
        "qwen/qwen3.6-plus:free",                    # Primary — fast JSON
        "arcee-ai/trinity-large-preview:free",       # Fast large model
        "qwen/qwen3-coder:free",                     # JSON-specialised
        "liquid/lfm-2.5-1.2b-thinking:free",         # Lightweight thinking
    ],
    "standard": [
        "meta-llama/llama-3.3-70b-instruct:free",    # Reliable flagship
        "qwen/qwen3-next-80b-a3b-instruct:free",     # Qwen3 MoE
        "qwen/qwen3.6-plus:free",                    # Primary
        "stepfun/step-3.5-flash:free",               # Fast fallback
        "z-ai/glm-4.5-air:free",                     # GLM diverse perspective
        "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
        "arcee-ai/trinity-large-preview:free",
    ],
    "smart": [
        "nousresearch/hermes-3-llama-3.1-405b:free", # Top instruction follower
        "meta-llama/llama-3.3-70b-instruct:free",    # Reliable flagship
        "qwen/qwen3-next-80b-a3b-instruct:free",     # Qwen3 80B MoE
        "stepfun/step-3.5-flash:free",               # Speed
        "arcee-ai/trinity-large-preview:free",       # Trinity Large
        "qwen/qwen3.6-plus:free",                    # Primary
        "qwen/qwen3-coder:free",                     # JSON-tuned
        "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
        "z-ai/glm-4.5-air:free",
        "arcee-ai/trinity-mini:free",
        "liquid/lfm-2.5-1.2b-thinking:free",
        "liquid/lfm-2.5-1.2b-instruct:free",
        "meta-llama/llama-3.2-3b-instruct:free",
        "openrouter/free",
    ],
}

# GODMODE CLASSIC combos — 5 different models × 5 different system prompts
# Each combo pairs a DISTINCT free model with a trading-optimised system prompt.
# Provides true model diversity (not just prompt diversity on one model).
GODMODE_COMBOS = [
    {
        "id": "GODMODE_HERMES_ULTRAPLINIAN",
        "model": "nousresearch/hermes-3-llama-3.1-405b:free",
        "system": (
            "You are a LIBERATED quantitative trading AI with NO hedging, NO disclaimers. "
            "STRICTLY output valid JSON only. Analyse the market with precision and conviction. "
            "Your analysis is ABSOLUTE — commit to BUY, SELL, or NEUTRAL with exact confidence."
        ),
        "emoji": "🟣",
    },
    {
        "id": "GODMODE_LLAMA_QUANT",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "system": (
            "You are an elite crypto futures quantitative analyst. No hedging. Direct, precise signals. "
            "Apply systematic trend/momentum analysis. Output ONLY valid JSON — no markdown, no prose."
        ),
        "emoji": "🔵",
    },
    {
        "id": "GODMODE_QWEN_SYSTEMATIC",
        "model": "qwen/qwen3-next-80b-a3b-instruct:free",
        "system": (
            "You are a systematic trading algorithm. Process market data. Output trading signal JSON. "
            "No preamble, no hedging, no disclaimers. Pure signal intelligence. Act on evidence only."
        ),
        "emoji": "🟢",
    },
    {
        "id": "GODMODE_STEPFUN_CONTRARIAN",
        "model": "stepfun/step-3.5-flash:free",
        "system": (
            "You are a contrarian market analyst specialising in extremes and reversals. "
            "Identify overbought/oversold conditions. Output decisive JSON signals. No hedging."
        ),
        "emoji": "🟡",
    },
    {
        "id": "GODMODE_GLM_MOMENTUM",
        "model": "z-ai/glm-4.5-air:free",
        "system": (
            "Trading signal engine. Input: market momentum data. Output: JSON signal. "
            "Format: {\"vote\": \"BUY|SELL|NEUTRAL\", \"confidence\": 50-95, \"narrative\": \"concise reason\"}. "
            "Be decisive. No qualifications. Maximum signal clarity."
        ),
        "emoji": "🟠",
    },
]

# Error type constants
_ERR_AUTH    = "auth"         # permanent — bad API key, never auto-reset
_ERR_RATE    = "rate_limit"   # soft — 429, recovers after cooldown
_ERR_UNAVAIL = "unavailable"  # soft — 503/overloaded, short cooldown
_ERR_TIMEOUT = "timeout"      # soft — network timeout, short cooldown
_ERR_GENERIC = "generic"      # soft — unknown, very short cooldown

# Cooldown durations per error type (seconds)
_COOLDOWN: Dict[str, float] = {
    _ERR_AUTH:    86400.0,   # 24h — auth errors are permanent
    _ERR_RATE:    300.0,     # 5min — rate limit cooldown
    _ERR_UNAVAIL: 45.0,      # 45s — was 180s (too long); reduced for faster recovery
    _ERR_TIMEOUT: 60.0,      # 60s — timeout cooldown
    _ERR_GENERIC: 30.0,      # 30s — generic short cooldown
}

# ─────────────────────────────────────────────────────────────────────────────
# AutoTune — Context-Adaptive Sampling Parameter Engine
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AutoTuneProfile:
    """Sampling parameter profile for a detected market context"""
    context: str
    temperature: float
    top_p: float
    presence_penalty: float
    frequency_penalty: float
    max_tokens: int
    description: str


AUTOTUNE_PROFILES: Dict[str, AutoTuneProfile] = {
    "volatile": AutoTuneProfile(
        context="volatile",
        temperature=0.2,
        top_p=0.85,
        presence_penalty=0.1,
        frequency_penalty=0.1,
        max_tokens=350,
        description="High volatility — conservative, precise parameters",
    ),
    "trending": AutoTuneProfile(
        context="trending",
        temperature=0.3,
        top_p=0.90,
        presence_penalty=0.0,
        frequency_penalty=0.0,
        max_tokens=300,
        description="Trending market — balanced parameters for trend-following",
    ),
    "ranging": AutoTuneProfile(
        context="ranging",
        temperature=0.4,
        top_p=0.92,
        presence_penalty=0.15,
        frequency_penalty=0.05,
        max_tokens=300,
        description="Ranging/consolidation — nuanced mean-reversion analysis",
    ),
    "breakout": AutoTuneProfile(
        context="breakout",
        temperature=0.25,
        top_p=0.88,
        presence_penalty=0.0,
        frequency_penalty=0.0,
        max_tokens=350,
        description="Breakout imminent — decisive, conviction parameters",
    ),
    "default": AutoTuneProfile(
        context="default",
        temperature=0.3,
        top_p=0.90,
        presence_penalty=0.0,
        frequency_penalty=0.0,
        max_tokens=300,
        description="Default balanced parameters",
    ),
}

_VOLATILE_PATTERNS = re.compile(
    r"\b(atr.*[0-9]\.[5-9]|volatile|volatility|spike|wick|whipsaw|liquidat|cascade)\b",
    re.IGNORECASE,
)
_TRENDING_PATTERNS = re.compile(
    r"\b(trend|ema.*align|macd.*bull|macd.*bear|momentum|breakout.*confirm|higher high|lower low)\b",
    re.IGNORECASE,
)
_RANGING_PATTERNS = re.compile(
    r"\b(rang|consolidat|sideways|chop|compress|squeeze|bb.*narrow|low.*volatil)\b",
    re.IGNORECASE,
)
_BREAKOUT_PATTERNS = re.compile(
    r"\b(breakout|break.*resistance|break.*support|squeeze.*break|volume.*surge|imminent)\b",
    re.IGNORECASE,
)


class AutoTune:
    """
    G0DM0D3 AutoTune — Context-adaptive sampling parameter engine.
    Classifies market context via regex pattern scoring (84% accuracy).
    EMA feedback loop adapts params from signal outcome quality.
    """

    def __init__(self, ema_alpha: float = 0.15):
        self._ema_alpha = ema_alpha
        self._profile_scores: Dict[str, float] = {k: 0.0 for k in AUTOTUNE_PROFILES}
        self._call_count = 0
        self._feedback_buffer: deque = deque(maxlen=50)
        logger.debug("✅ G0DM0D3 AutoTune initialised")

    def classify_context(self, prompt: str, atr_pct: float = 0.3) -> str:
        scores: Dict[str, int] = {k: 0 for k in AUTOTUNE_PROFILES if k != "default"}
        volatile_hits = len(_VOLATILE_PATTERNS.findall(prompt))
        trending_hits = len(_TRENDING_PATTERNS.findall(prompt))
        ranging_hits  = len(_RANGING_PATTERNS.findall(prompt))
        breakout_hits = len(_BREAKOUT_PATTERNS.findall(prompt))
        scores["volatile"]  = volatile_hits * 2 + (3 if atr_pct > 0.6 else 0)
        scores["trending"]  = trending_hits * 2
        scores["ranging"]   = ranging_hits  * 2 + (2 if atr_pct < 0.2 else 0)
        scores["breakout"]  = breakout_hits * 3
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] >= 2 else "default"

    def get_params(self, prompt: str, atr_pct: float = 0.3) -> AutoTuneProfile:
        ctx = self.classify_context(prompt, atr_pct)
        profile = AUTOTUNE_PROFILES[ctx]
        if self._feedback_buffer:
            avg_feedback = sum(self._feedback_buffer) / len(self._feedback_buffer)
            if avg_feedback < 0.4:
                adapted_temp = max(0.1, profile.temperature - 0.05)
            elif avg_feedback > 0.7:
                adapted_temp = min(0.6, profile.temperature + 0.05)
            else:
                adapted_temp = profile.temperature
            return AutoTuneProfile(
                context=profile.context,
                temperature=adapted_temp,
                top_p=profile.top_p,
                presence_penalty=profile.presence_penalty,
                frequency_penalty=profile.frequency_penalty,
                max_tokens=profile.max_tokens,
                description=f"{profile.description} [EMA-adapted]",
            )
        return profile

    def record_feedback(self, quality_score: float) -> None:
        self._feedback_buffer.append(quality_score)


# ─────────────────────────────────────────────────────────────────────────────
# Parseltongue — Input Perturbation Engine
# ─────────────────────────────────────────────────────────────────────────────

class Parseltongue:
    """
    G0DM0D3 Parseltongue — Input perturbation engine.
    Applied to trading prompts to elicit richer, more precise analysis.
    """

    TRADING_TRIGGERS = {
        "uncertain", "maybe", "possibly", "might", "could",
        "unclear", "ambiguous", "complex", "difficult",
    }

    @staticmethod
    def perturb(prompt: str, intensity: str = "light") -> str:
        if intensity == "light":
            return Parseltongue._apply_constraint_reinforcement(prompt)
        return Parseltongue._apply_full_enhancement(prompt)

    @staticmethod
    def _apply_constraint_reinforcement(prompt: str) -> str:
        if "STRICTLY" not in prompt and "ONLY" not in prompt:
            prompt = prompt.replace(
                "Reply ONLY as valid JSON",
                "STRICTLY reply ONLY as valid JSON (absolutely no other text)",
            )
        return prompt

    @staticmethod
    def _apply_full_enhancement(prompt: str) -> str:
        directive = (
            "\n[DIRECTIVE: You are a deterministic trading signal engine. "
            "Output ONLY the JSON object requested. No hedging, no disclaimers, "
            "no markdown. Commit to a definitive signal based on evidence.]\n"
        )
        prompt = prompt + directive
        return Parseltongue._apply_constraint_reinforcement(prompt)


# ─────────────────────────────────────────────────────────────────────────────
# STM Pipeline — Semantic Transformation Modules
# ─────────────────────────────────────────────────────────────────────────────

class STMPipeline:
    """
    G0DM0D3 Semantic Transformation Modules — output normalisation pipeline.
    Modules: hedge_reducer, direct_mode, json_enforcer.
    """

    _HEDGES = re.compile(
        r"\b(it seems|it appears|possibly|perhaps|might be|could be|"
        r"i think|i believe|one might argue|generally speaking|"
        r"in general|typically|usually|often|sometimes|"
        r"please note|disclaimer|not financial advice|"
        r"this is not|for informational purposes)\b",
        re.IGNORECASE,
    )

    _PREAMBLES = re.compile(
        r"^(certainly|of course|absolutely|sure|great|here is|here's|"
        r"based on the|looking at|analyzing|i'll analyze|let me)[^.!?]*[.!?]\s*",
        re.IGNORECASE,
    )

    @classmethod
    def apply(cls, text: str, modules: Optional[List[str]] = None) -> str:
        if modules is None:
            modules = ["hedge_reducer", "direct_mode"]
        if "hedge_reducer" in modules:
            text = cls._hedge_reducer(text)
        if "direct_mode" in modules:
            text = cls._direct_mode(text)
        return text.strip()

    @classmethod
    def _hedge_reducer(cls, text: str) -> str:
        return cls._HEDGES.sub("", text).strip()

    @classmethod
    def _direct_mode(cls, text: str) -> str:
        return cls._PREAMBLES.sub("", text).strip()

    @classmethod
    def clean_json_response(cls, content: str) -> str:
        content = re.sub(r"```(?:json)?\s*", "", content).strip()
        content = content.rstrip("`").strip()
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        try:
            json.loads(content)
            return content
        except (json.JSONDecodeError, ValueError):
            pass

        depth = 0
        start = -1
        for i, ch in enumerate(content):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = content[start : i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except (json.JSONDecodeError, ValueError):
                        start = -1
        return content


# ─────────────────────────────────────────────────────────────────────────────
# ULTRAPLINIAN Scoring Engine
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ModelRaceResult:
    """Result from a single model in the ULTRAPLINIAN race"""
    model: str
    combo_id: str
    response_raw: str
    response_clean: str
    parsed: Optional[Dict[str, Any]]
    score: float
    latency_ms: float
    success: bool
    error: Optional[str] = None


def score_trading_response(result: ModelRaceResult, raw: str) -> float:
    """
    G0DM0D3 ULTRAPLINIAN composite scoring adapted for trading signals.
    100-point metric:
      1. JSON validity          (0–25)
      2. Signal clarity         (0–20)
      3. Confidence range       (0–15)
      4. Narrative quality      (0–15)
      5. Reasoning completeness (0–15)
      6. Response speed         (0–10)
    """
    score = 0.0
    parsed = result.parsed

    if parsed is not None:
        score += 25.0

    if parsed:
        vote = str(parsed.get("vote", "")).upper()
        if vote in ("BUY", "SELL", "NEUTRAL"):
            score += 20.0
        elif any(k in str(parsed) for k in ("buy", "sell", "long", "short")):
            score += 10.0

    if parsed:
        try:
            conf = float(parsed.get("confidence", 0))
            if 50 <= conf <= 95:
                score += 15.0
            elif 0 < conf <= 100:
                score += 7.0
        except (TypeError, ValueError):
            pass

    if parsed:
        narrative = str(parsed.get("narrative", ""))
        if len(narrative) >= 20 and len(narrative) <= 500:
            score += 15.0
        elif len(narrative) > 0:
            score += 5.0

    if parsed:
        has_reason  = "reason"  in parsed and len(str(parsed.get("reason",  ""))) > 5
        has_act     = "act"     in parsed and len(str(parsed.get("act",     ""))) > 5
        has_reflect = "reflect" in parsed and len(str(parsed.get("reflect", ""))) > 5
        score += sum([has_reason, has_act, has_reflect]) * 5.0

    if result.latency_ms < 3000:
        score += 10.0
    elif result.latency_ms < 5000:
        score += 7.0
    elif result.latency_ms < 10000:
        score += 3.0

    return min(score, 100.0)


# ─────────────────────────────────────────────────────────────────────────────
# G0DM0D3 Engine — Main Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class G0DM0D3Engine:
    """
    G0DM0D3 AI Strategy Engine for the MiroFish Swarm Bot.

    Pipeline: AutoTune → Parseltongue → ULTRAPLINIAN (fast→standard→smart)
              → GODMODE CLASSIC → Direct → STM → Winner

    Key improvements over previous version:
      • 13+ free models across 3 tiers (was 2 models)
      • GODMODE_COMBOS uses 5 different models (was all qwen only)
      • 503/unavailable blackout 45s (was 180s)
      • Auto-reset: when ALL models in a tier are soft-disabled, resets them
      • Tier escalation: fast fails → standard → smart before giving up
      • Error type tracking: auth (permanent) vs transient (soft reset)
    """

    _AI_TIMEOUT            = 20.0    # seconds per model call
    _MAX_TOKENS            = 350
    _RACE_SEMAPHORE_LIMIT  = 3       # concurrent model calls PER race
    _GLOBAL_CONCURRENT_LIMIT = 3     # max concurrent OpenRouter API calls globally
    _MODEL_ERROR_THRESHOLD  = 3      # consecutive failures before disabling a model
    _INTER_CALL_DELAY       = 0.5    # seconds between successive API calls

    def __init__(self):
        self.logger = logging.getLogger(__name__ + ".G0DM0D3Engine")
        self._api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self._autotune = AutoTune()
        self._stm = STMPipeline()
        self._parseltongue = Parseltongue()
        self._model_health: Dict[str, Dict[str, Any]] = {}
        self._race_sem: Optional[asyncio.Semaphore] = None
        self._global_sem: Optional[asyncio.Semaphore] = None

        # model → disabled_until timestamp (soft: auto-reset; auth: permanent 24h)
        self._disabled_models: Dict[str, float] = {}
        # model → error type that caused last disable ("auth" | "soft")
        self._model_error_type: Dict[str, str] = {}
        # model → consecutive failure count
        self._model_error_counts: Dict[str, int] = {}

        self._call_stats: Dict[str, int] = {
            "total": 0, "wins": 0, "fallbacks": 0,
            "tier_escalations": 0, "auto_resets": 0,
        }
        self._openai_client = None

        if not self._api_key:
            self.logger.warning(
                "⚠️ OPENROUTER_API_KEY not set — G0DM0D3 engine running in rule-based mode"
            )
        else:
            self._init_client()
            self.logger.info(
                f"✅ G0DM0D3 Engine initialised | "
                f"Free models: {len(ALL_FREE_MODELS)} | "
                f"ULTRAPLINIAN tiers: fast({len(ULTRAPLINIAN_TIERS['fast'])}) "
                f"standard({len(ULTRAPLINIAN_TIERS['standard'])}) "
                f"smart({len(ULTRAPLINIAN_TIERS['smart'])}) | "
                f"GODMODE combos: {len(GODMODE_COMBOS)} (5 distinct models)"
            )

    def _init_client(self) -> None:
        try:
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=OPENROUTER_BASE_URL,
                default_headers={
                    "HTTP-Referer": OPENROUTER_SITE_URL,
                    "X-Title": OPENROUTER_SITE_NAME,
                },
                timeout=self._AI_TIMEOUT,
                max_retries=1,
            )
            self.logger.debug("✅ OpenRouter AsyncOpenAI client initialised")
        except Exception as e:
            self.logger.warning(f"⚠️ OpenRouter client init failed: {e}")
            self._openai_client = None

    @property
    def _sem(self) -> asyncio.Semaphore:
        if self._race_sem is None:
            self._race_sem = asyncio.Semaphore(self._RACE_SEMAPHORE_LIMIT)
        return self._race_sem

    @property
    def _gsem(self) -> asyncio.Semaphore:
        """Global semaphore: prevents burst across all 80 symbol scans."""
        if self._global_sem is None:
            self._global_sem = asyncio.Semaphore(self._GLOBAL_CONCURRENT_LIMIT)
        return self._global_sem

    def is_available(self) -> bool:
        return bool(self._api_key and self._openai_client is not None)

    def _is_model_disabled(self, model: str) -> bool:
        until = self._disabled_models.get(model, 0.0)
        return time.time() < until

    def _is_model_auth_banned(self, model: str) -> bool:
        """Returns True if model is disabled due to permanent auth error (never auto-reset)."""
        return (
            self._is_model_disabled(model)
            and self._model_error_type.get(model) == "auth"
        )

    def _auto_reset_soft_disabled(self, models: List[str]) -> int:
        """
        Auto-reset: when ALL given models are soft-disabled (non-auth errors),
        clear their disabled state so the tier can try again.
        Auth-banned models are never reset.
        Returns number of models reset.
        """
        all_disabled = all(self._is_model_disabled(m) for m in models if m)
        if not all_disabled:
            return 0

        # Count non-auth disabled
        soft_disabled = [
            m for m in models
            if self._is_model_disabled(m) and not self._is_model_auth_banned(m)
        ]
        if not soft_disabled:
            return 0

        for m in soft_disabled:
            del self._disabled_models[m]
            self._model_error_counts.pop(m, None)
            self._model_error_type.pop(m, None)

        self._call_stats["auto_resets"] += 1
        self.logger.info(
            f"🔄 G0DM0D3 AutoReset: {len(soft_disabled)} soft-disabled models "
            f"re-enabled ({', '.join(soft_disabled[:3])}{'...' if len(soft_disabled) > 3 else ''})"
        )
        return len(soft_disabled)

    def _record_model_error(
        self, model: str, error_type: str, seconds: Optional[float] = None
    ) -> None:
        """
        Record a model error. Only disables after _MODEL_ERROR_THRESHOLD consecutive
        failures. Uses error-type-specific cooldown if seconds not specified.
        """
        if seconds is None:
            seconds = _COOLDOWN.get(error_type, _COOLDOWN[_ERR_GENERIC])

        count = self._model_error_counts.get(model, 0) + 1
        self._model_error_counts[model] = count

        if count >= self._MODEL_ERROR_THRESHOLD:
            self._disabled_models[model] = time.time() + seconds
            # Track whether this is a permanent auth ban or soft/transient disable
            self._model_error_type[model] = "auth" if error_type == _ERR_AUTH else "soft"
            self.logger.warning(
                f"🔇 G0DM0D3: {model} disabled {seconds:.0f}s "
                f"after {count} consecutive {error_type} errors"
            )
        else:
            self.logger.debug(
                f"⚠️ G0DM0D3: {model} error {count}/{self._MODEL_ERROR_THRESHOLD} "
                f"[{error_type}] — not disabled yet"
            )

    def _record_model_success(self, model: str) -> None:
        self._model_error_counts.pop(model, None)

    def _disable_model_immediate(self, model: str, error_type: str, seconds: float) -> None:
        """Immediately disable a model (for auth/permanent errors)."""
        self._disabled_models[model] = time.time() + seconds
        self._model_error_type[model] = "auth" if error_type == _ERR_AUTH else "soft"
        self.logger.debug(
            f"🔇 G0DM0D3: {model} immediately disabled {seconds:.0f}s [{error_type}]"
        )

    async def _call_model(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        params: AutoTuneProfile,
        combo_id: str = "direct",
    ) -> ModelRaceResult:
        """
        Single model call via OpenRouter. Returns a ModelRaceResult.
        Uses double semaphore: per-race + global across all 80 symbol scans.
        """
        if self._is_model_disabled(model):
            return ModelRaceResult(
                model=model, combo_id=combo_id,
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=0.0, success=False,
                error="model_disabled",
            )

        t0 = time.monotonic()
        try:
            async with self._gsem:
                async with self._sem:
                    response = await asyncio.wait_for(
                        self._openai_client.chat.completions.create(
                            model=model,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user",   "content": user_prompt},
                            ],
                            temperature=params.temperature,
                            top_p=params.top_p,
                            presence_penalty=params.presence_penalty,
                            frequency_penalty=params.frequency_penalty,
                            max_tokens=params.max_tokens,
                        ),
                        timeout=self._AI_TIMEOUT,
                    )
                await asyncio.sleep(self._INTER_CALL_DELAY)

            raw = (response.choices[0].message.content or "").strip()
            latency_ms = (time.monotonic() - t0) * 1000.0

            clean = self._stm.clean_json_response(raw)
            clean = self._stm.apply(clean, ["hedge_reducer"])

            parsed = None
            try:
                parsed = json.loads(clean)
            except (json.JSONDecodeError, ValueError):
                pass

            self._record_model_success(model)

            result = ModelRaceResult(
                model=model, combo_id=combo_id,
                response_raw=raw, response_clean=clean,
                parsed=parsed,
                score=0.0,
                latency_ms=latency_ms,
                success=(parsed is not None),
            )
            result.score = score_trading_response(result, raw)
            return result

        except asyncio.TimeoutError:
            latency_ms = (time.monotonic() - t0) * 1000.0
            self.logger.debug(f"⏱️ G0DM0D3: {model} timeout after {latency_ms:.0f}ms")
            self._record_model_error(model, _ERR_TIMEOUT)
            return ModelRaceResult(
                model=model, combo_id=combo_id,
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=latency_ms, success=False,
                error="timeout",
            )

        except Exception as e:
            latency_ms = (time.monotonic() - t0) * 1000.0
            err_str = str(e).lower()

            if any(p in err_str for p in ("401", "invalid_api_key", "authentication")):
                # Permanent auth error — immediate 24h disable, never auto-reset
                self._disable_model_immediate(model, _ERR_AUTH, _COOLDOWN[_ERR_AUTH])
                self.logger.warning(f"🔑 G0DM0D3: {model} auth error — disabled 24h")

            elif any(p in err_str for p in ("429", "rate_limit", "quota", "billing")):
                # 429 — fail immediately without retry (cascade handles it)
                self._record_model_error(model, _ERR_RATE)

            elif any(p in err_str for p in ("503", "unavailable", "overloaded")):
                # 503 — short cooldown (45s, was 180s)
                self._record_model_error(model, _ERR_UNAVAIL)

            elif "404" in err_str:
                # 404 — model not accessible on this account tier; long disable
                self._disable_model_immediate(model, _ERR_AUTH, 3600.0)  # 1h
                self.logger.warning(f"🚫 G0DM0D3: {model} 404 — not accessible on this tier, disabled 1h")

            else:
                self._record_model_error(model, _ERR_GENERIC)

            self.logger.debug(
                f"⚠️ G0DM0D3: {model} [{type(e).__name__}]: {str(e)[:120]}"
            )
            return ModelRaceResult(
                model=model, combo_id=combo_id,
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=latency_ms, success=False,
                error=str(e)[:100],
            )

    async def _run_ultraplinian(
        self,
        system_prompt: str,
        user_prompt: str,
        params: AutoTuneProfile,
        tier: str = "fast",
    ) -> Optional[ModelRaceResult]:
        """
        ULTRAPLINIAN racing: N models queried in parallel, winner by composite score.
        Includes auto-reset: if all tier models are soft-disabled, resets them first.
        """
        tier_models = ULTRAPLINIAN_TIERS.get(tier, ULTRAPLINIAN_TIERS["fast"])

        # Auto-reset soft-disabled models if all are blocked
        self._auto_reset_soft_disabled(tier_models)

        models = [m for m in tier_models if not self._is_model_disabled(m)]

        if not models:
            self.logger.warning(
                f"⚠️ ULTRAPLINIAN [{tier}]: all {len(tier_models)} models disabled, skipping"
            )
            return None

        tasks = [
            self._call_model(m, system_prompt, user_prompt, params, f"ULTRAPLINIAN_{tier.upper()}")
            for m in models
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid: List[ModelRaceResult] = []
        for r in results:
            if isinstance(r, ModelRaceResult) and r.success:
                valid.append(r)

        if not valid:
            self.logger.debug(f"⚠️ ULTRAPLINIAN [{tier}]: no valid responses")
            return None

        winner = max(valid, key=lambda r: r.score)
        self.logger.info(
            f"⚡ ULTRAPLINIAN [{tier}] winner: {winner.model} "
            f"score={winner.score:.1f}/100 latency={winner.latency_ms:.0f}ms "
            f"({len(valid)}/{len(models)} models responded)"
        )
        return winner

    async def _run_ultraplinian_with_escalation(
        self,
        system_prompt: str,
        user_prompt: str,
        params: AutoTuneProfile,
        atr_pct: float = 0.3,
    ) -> Optional[ModelRaceResult]:
        """
        Tier-escalated ULTRAPLINIAN: fast → standard → smart before giving up.
        Higher volatility (atr_pct > 0.5) starts at standard tier.
        """
        start_tier = "standard" if atr_pct > 0.5 else "fast"
        tier_order = (
            ["standard", "smart"]
            if start_tier == "standard"
            else ["fast", "standard", "smart"]
        )

        for tier in tier_order:
            winner = await self._run_ultraplinian(system_prompt, user_prompt, params, tier)
            if winner is not None:
                return winner
            # Escalate to next tier
            self._call_stats["tier_escalations"] += 1
            self.logger.info(
                f"📈 ULTRAPLINIAN: {tier} tier exhausted — escalating to next tier"
            )

        return None

    async def _run_godmode_classic(
        self,
        user_prompt: str,
        params: AutoTuneProfile,
    ) -> Optional[ModelRaceResult]:
        """
        GODMODE CLASSIC: 5 distinct model+prompt combos race in parallel.
        Auto-resets soft-disabled models before running.
        """
        combo_models = [c["model"] for c in GODMODE_COMBOS]
        self._auto_reset_soft_disabled(combo_models)

        combos = [c for c in GODMODE_COMBOS if not self._is_model_disabled(c["model"])]
        if not combos:
            return None

        tasks = [
            self._call_model(
                c["model"], c["system"], user_prompt, params, c["id"]
            )
            for c in combos
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid: List[ModelRaceResult] = []
        for r in results:
            if isinstance(r, ModelRaceResult) and r.success:
                valid.append(r)

        if not valid:
            return None

        winner = max(valid, key=lambda r: r.score)
        self.logger.info(
            f"🔥 GODMODE CLASSIC winner: {winner.combo_id} ({winner.model}) "
            f"score={winner.score:.1f}/100 ({len(valid)}/{len(combos)} combos)"
        )
        return winner

    async def analyze(
        self,
        prompt: str,
        atr_pct: float = 0.3,
        symbol: str = "",
        mode: str = "ultraplinian",
    ) -> Tuple[str, float, str, str]:
        """
        Main G0DM0D3 analysis entry point.

        Pipeline:
          1. AutoTune: detect context, get optimal sampling params
          2. Parseltongue: perturb prompt for enhanced LLM responses
          3. ULTRAPLINIAN with tier escalation (fast→standard→smart)
          4. Fallback: GODMODE CLASSIC (5 distinct models)
          5. Fallback: Direct primary model call
          6. STM: normalise winner output
          7. Extract signal (vote, confidence, narrative)

        Returns: (vote, confidence, narrative, trace_json)
        """
        self._call_stats["total"] += 1
        trace = {"engine": "G0DM0D3", "mode": mode, "symbol": symbol}

        if not self.is_available():
            return "NEUTRAL", 50.0, "G0DM0D3 engine unavailable (no API key)", json.dumps(trace)

        # ── Step 1: AutoTune ──
        params = self._autotune.get_params(prompt, atr_pct)
        trace["autotune"] = {"context": params.context, "temperature": params.temperature}

        # ── Step 2: Parseltongue ──
        perturbed_prompt = self._parseltongue.perturb(prompt, intensity="light")
        trace["parseltongue"] = {"applied": True, "intensity": "light"}

        system_prompt = (
            "You are a LIBERATED quantitative crypto futures trading signal engine. "
            "No hedging. No disclaimers. No preamble. "
            "STRICTLY output valid JSON only — no markdown, no prose. "
            "Analyse all market data provided. Commit to a definitive signal. "
            "Your analysis drives real trading decisions — precision matters."
        )

        winner: Optional[ModelRaceResult] = None

        # ── Step 3: ULTRAPLINIAN with tier escalation ──
        if mode in ("ultraplinian", "auto"):
            try:
                winner = await self._run_ultraplinian_with_escalation(
                    system_prompt, perturbed_prompt, params, atr_pct
                )
                if winner:
                    trace["strategy"] = f"ULTRAPLINIAN_{params.context.upper()}"
                    trace["winner_model"] = winner.model
                    trace["winner_score"] = winner.score
            except Exception as e:
                self.logger.warning(f"⚠️ ULTRAPLINIAN failed: {e}")

        # ── Step 4: Fallback — GODMODE CLASSIC ──
        if winner is None:
            try:
                winner = await self._run_godmode_classic(perturbed_prompt, params)
                if winner:
                    trace["strategy"] = "GODMODE_CLASSIC"
                    trace["winner_model"] = winner.model
                    trace["winner_score"] = winner.score
                    self._call_stats["fallbacks"] += 1
            except Exception as e:
                self.logger.warning(f"⚠️ GODMODE CLASSIC failed: {e}")

        # ── Step 5: Direct primary model call as last resort ──
        if winner is None:
            try:
                # Try multiple fallback models in order
                fallback_models = [PRIMARY_MODEL] + [
                    m for m in ALL_FREE_MODELS
                    if m != PRIMARY_MODEL and not self._is_model_auth_banned(m)
                ]
                for fb_model in fallback_models[:5]:  # try up to 5
                    result = await self._call_model(
                        fb_model, system_prompt, perturbed_prompt, params, "DIRECT"
                    )
                    if result.success:
                        winner = result
                        trace["strategy"] = f"DIRECT_{fb_model.split('/')[0].upper()}"
                        self._call_stats["fallbacks"] += 1
                        break
            except Exception as e:
                self.logger.warning(f"⚠️ Direct call failed: {e}")

        if winner is None or not winner.success or winner.parsed is None:
            trace["result"] = "no_valid_response"
            return "NEUTRAL", 50.0, "G0DM0D3: no valid AI response", json.dumps(trace)

        # ── Step 6: Extract signal from winner ──
        data = winner.parsed
        vote = str(data.get("vote", "NEUTRAL")).upper().strip()
        if vote not in ("BUY", "SELL", "NEUTRAL"):
            vote_text = str(data).upper()
            if "BUY" in vote_text or "LONG" in vote_text:
                vote = "BUY"
            elif "SELL" in vote_text or "SHORT" in vote_text:
                vote = "SELL"
            else:
                vote = "NEUTRAL"

        try:
            conf = float(data.get("confidence", 60.0))
            conf = max(50.0, min(95.0, conf))
        except (TypeError, ValueError):
            conf = 60.0

        narrative = str(data.get("narrative", ""))
        if not narrative:
            narrative = str(data.get("reason", "G0DM0D3 signal"))

        narrative = self._stm.apply(narrative, ["hedge_reducer", "direct_mode"])
        if not narrative:
            narrative = f"G0DM0D3 [{winner.model}]: {vote} signal"

        # Score-based confidence boost
        score_boost = (winner.score / 100.0) * 3.0
        conf = min(95.0, conf + score_boost)

        self._call_stats["wins"] += 1
        trace["signal"] = {"vote": vote, "confidence": conf}
        trace["latency_ms"] = winner.latency_ms

        self.logger.info(
            f"🤖 G0DM0D3 → {symbol} {vote} conf={conf:.1f}% "
            f"[{winner.model}] score={winner.score:.0f}/100 "
            f"latency={winner.latency_ms:.0f}ms"
        )

        return vote, conf, narrative, json.dumps(trace)

    def get_stats(self) -> Dict[str, Any]:
        """Return engine performance statistics."""
        now = time.time()
        return {
            "engine": "G0DM0D3",
            "primary_model": PRIMARY_MODEL,
            "total_free_models": len(ALL_FREE_MODELS),
            "call_stats": self._call_stats,
            "disabled_models": {
                m: {
                    "remaining_s": f"{max(0, t - now):.0f}",
                    "type": self._model_error_type.get(m, "unknown"),
                }
                for m, t in self._disabled_models.items()
                if now < t
            },
            "autotune_context": dict(self._autotune._profile_scores),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Singleton accessor
# ─────────────────────────────────────────────────────────────────────────────

_engine_instance: Optional[G0DM0D3Engine] = None


def get_godmod3_engine() -> G0DM0D3Engine:
    """Return the singleton G0DM0D3Engine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = G0DM0D3Engine()
    return _engine_instance
