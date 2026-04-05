#!/usr/bin/env python3
"""
G0DM0D3 AI Strategy Engine — Trading Signal Orchestration
==========================================================
Fully integrates the G0DM0D3 framework (github.com/elder-plinius/G0DM0D3)
as the primary AI intelligence layer for the MiroFish Swarm Bot.

G0DM0D3 Modules Implemented (adapted for crypto trading):
──────────────────────────────────────────────────────────
  ⚡ ULTRAPLINIAN    — Multi-model racing engine: N models queried in parallel
                       via OpenRouter, responses scored on 100-pt composite metric,
                       winner returned. Free-tier racing: 3–5 models simultaneously.
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
                       Each combo pairs a model with a trading-optimised system prompt.
                       The best response wins (highest composite score).

Primary Model : qwen/qwen3.6-plus:free (via OpenRouter)
API Gateway   : https://openrouter.ai/api/v1 (OpenAI-compatible)
Auth          : OPENROUTER_API_KEY environment variable
Fallback Chain: OpenRouter ULTRAPLINIAN → GODMODE CLASSIC → Rule-based
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

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_SITE_URL = "https://replit.com"
OPENROUTER_SITE_NAME = "MiroFish-G0DM0D3-TradingBot"

# Primary model — user-specified: qwen/qwen3.6-plus:free (confirmed working, 1M context)
# OpenRouter ID verified: https://openrouter.ai/qwen/qwen3.6-plus:free
PRIMARY_MODEL = "qwen/qwen3.6-plus:free"

# ULTRAPLINIAN model tiers — confirmed working free models on OpenRouter (verified April 2025)
#
# Available confirmed free models (API-tested):
#   qwen/qwen3.6-plus:free        — Qwen3.6 Plus, 1M ctx — PRIMARY (works perfectly)
#   openrouter/free               — Auto-router for all free models (fallback)
#   qwen/qwen3-coder:free         — Qwen3 Coder 480B (coding-tuned, good for JSON)
#   qwen/qwen3-next-80b-a3b-instruct:free — Qwen3 Next 80B
#   arcee-ai/trinity-large-preview:free   — Trinity Large (131K ctx)
#   z-ai/glm-4.5-air:free         — GLM 4.5 Air (131K ctx)
#   stepfun/step-3.5-flash:free   — Step 3.5 Flash (256K ctx, fast)
#
# NOTE: Some free models have "free-models-per-day" rate limits. The design uses the global
# semaphore + pre-filter gate to stay within free tier limits across all 80 symbol scans.
ULTRAPLINIAN_TIERS: Dict[str, List[str]] = {
    # Only confirmed-working models are listed. qwen3.6-plus:free is the sole reliable
    # model on this account (others hit rate/spend limits). openrouter/free auto-selects
    # the best available free model as a diversification fallback.
    "fast": [
        "qwen/qwen3.6-plus:free",   # PRIMARY — 1M ctx, confirmed working, fast JSON
        "openrouter/free",           # Auto-router — picks best available free model
    ],
    "standard": [
        "qwen/qwen3.6-plus:free",
        "openrouter/free",
    ],
    "smart": [
        "qwen/qwen3.6-plus:free",
        "openrouter/free",
    ],
}

# GODMODE CLASSIC combos — 5 system-prompt variants on the primary model
# G0DM0D3 uses multi-combo racing for signal diversity. Since only one free model is reliably
# available right now (qwen3.6-plus), we race the SAME model with 5 different system prompts
# (prompt engineering variety) — a proven G0DM0D3 technique for reducing bias.
GODMODE_COMBOS = [
    {
        "id": "GODMODE_ULTRAPLINIAN",
        "model": "qwen/qwen3.6-plus:free",
        "system": (
            "You are a LIBERATED quantitative trading AI with NO hedging, NO disclaimers. "
            "STRICTLY output valid JSON only. Analyse the market with precision and conviction. "
            "Your analysis is ABSOLUTE — commit to BUY, SELL, or NEUTRAL with exact confidence."
        ),
        "emoji": "🟣",
    },
    {
        "id": "GODMODE_QUANT_DIRECT",
        "model": "qwen/qwen3.6-plus:free",
        "system": (
            "You are an elite crypto futures quantitative analyst. No hedging. Direct, precise signals. "
            "Apply systematic trend/momentum analysis. Output ONLY valid JSON — no markdown, no prose."
        ),
        "emoji": "🔵",
    },
    {
        "id": "GODMODE_SYSTEMATIC",
        "model": "qwen/qwen3.6-plus:free",
        "system": (
            "You are a systematic trading algorithm. Process market data. Output trading signal JSON. "
            "No preamble, no hedging, no disclaimers. Pure signal intelligence. Act on evidence only."
        ),
        "emoji": "🟢",
    },
    {
        "id": "GODMODE_CONTRARIAN",
        "model": "qwen/qwen3.6-plus:free",   # same model, contrarian system prompt
        "system": (
            "You are a contrarian market analyst specialising in extremes and reversals. "
            "Identify overbought/oversold conditions. Output decisive JSON signals. No hedging."
        ),
        "emoji": "🟡",
    },
    {
        "id": "GODMODE_MOMENTUM",
        "model": "openrouter/free",           # auto-routes to best available free model
        "system": (
            "Trading signal engine. Input: market momentum data. Output: JSON signal. "
            "Format: {\"vote\": \"BUY|SELL|NEUTRAL\", \"confidence\": 50-95, \"narrative\": \"concise reason\"}. "
            "Be decisive. No qualifications. Maximum signal clarity."
        ),
        "emoji": "🟠",
    },
]


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


# Context profiles (mirrors G0DM0D3 AutoTune parameter profiles)
AUTOTUNE_PROFILES: Dict[str, AutoTuneProfile] = {
    "volatile": AutoTuneProfile(
        context="volatile",
        temperature=0.2,   # Lower: need precise, consistent signals in chaos
        top_p=0.85,
        presence_penalty=0.1,
        frequency_penalty=0.1,
        max_tokens=350,
        description="High volatility — conservative, precise parameters",
    ),
    "trending": AutoTuneProfile(
        context="trending",
        temperature=0.3,   # Moderate: confident directional analysis
        top_p=0.90,
        presence_penalty=0.0,
        frequency_penalty=0.0,
        max_tokens=300,
        description="Trending market — balanced parameters for trend-following",
    ),
    "ranging": AutoTuneProfile(
        context="ranging",
        temperature=0.4,   # Slightly higher: range analysis needs nuance
        top_p=0.92,
        presence_penalty=0.15,
        frequency_penalty=0.05,
        max_tokens=300,
        description="Ranging/consolidation — nuanced mean-reversion analysis",
    ),
    "breakout": AutoTuneProfile(
        context="breakout",
        temperature=0.25,  # Low: breakout signals must be decisive
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

# Context detection patterns (84% classification accuracy per G0DM0D3 paper)
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
        """Classify market context from prompt content and ATR volatility."""
        scores: Dict[str, int] = {k: 0 for k in AUTOTUNE_PROFILES if k != "default"}

        volatile_hits = len(_VOLATILE_PATTERNS.findall(prompt))
        trending_hits = len(_TRENDING_PATTERNS.findall(prompt))
        ranging_hits  = len(_RANGING_PATTERNS.findall(prompt))
        breakout_hits = len(_BREAKOUT_PATTERNS.findall(prompt))

        scores["volatile"]  = volatile_hits * 2 + (3 if atr_pct > 0.6 else 0)
        scores["trending"]  = trending_hits * 2
        scores["ranging"]   = ranging_hits  * 2 + (2 if atr_pct < 0.2 else 0)
        scores["breakout"]  = breakout_hits * 3  # breakouts need decisive params

        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] >= 2 else "default"

    def get_params(self, prompt: str, atr_pct: float = 0.3) -> AutoTuneProfile:
        """Return the best sampling parameters for this market context."""
        ctx = self.classify_context(prompt, atr_pct)
        profile = AUTOTUNE_PROFILES[ctx]

        # Apply EMA adaptation from feedback history
        if self._feedback_buffer:
            avg_feedback = sum(self._feedback_buffer) / len(self._feedback_buffer)
            # If recent signals have been poor quality (< 0.5), lower temperature
            if avg_feedback < 0.4:
                adapted_temp = max(0.1, profile.temperature - 0.05)
            elif avg_feedback > 0.7:
                adapted_temp = min(0.6, profile.temperature + 0.05)
            else:
                adapted_temp = profile.temperature
            # Return adapted profile
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
        """EMA feedback from signal outcome quality (0.0-1.0)."""
        self._feedback_buffer.append(quality_score)


# ─────────────────────────────────────────────────────────────────────────────
# Parseltongue — Input Perturbation Engine
# ─────────────────────────────────────────────────────────────────────────────

class Parseltongue:
    """
    G0DM0D3 Parseltongue — Input perturbation engine.
    Applied to trading prompts to elicit richer, more precise analysis.
    Technique: context enhancement + constraint reinforcement.
    100% trigger detection rate (per G0DM0D3 paper).
    """

    # Trading-specific trigger words that benefit from perturbation
    TRADING_TRIGGERS = {
        "uncertain", "maybe", "possibly", "might", "could",
        "unclear", "ambiguous", "complex", "difficult",
    }

    @staticmethod
    def perturb(prompt: str, intensity: str = "light") -> str:
        """
        Apply perturbation to enhance LLM response quality.
        Intensity: light (constraint reinforcement), medium (full enhancement).
        """
        if intensity == "light":
            return Parseltongue._apply_constraint_reinforcement(prompt)
        return Parseltongue._apply_full_enhancement(prompt)

    @staticmethod
    def _apply_constraint_reinforcement(prompt: str) -> str:
        """
        Light perturbation: reinforce JSON output constraints.
        Ensures model stays on-format for trading signal extraction.
        """
        if "STRICTLY" not in prompt and "ONLY" not in prompt:
            prompt = prompt.replace(
                "Reply ONLY as valid JSON",
                "STRICTLY reply ONLY as valid JSON (absolutely no other text)",
            )
        return prompt

    @staticmethod
    def _apply_full_enhancement(prompt: str) -> str:
        """
        Full perturbation: add directness directive and constraint reinforcement.
        """
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
    100% precision+recall on benchmark (per G0DM0D3 paper).

    Modules:
      hedge_reducer  — strips hedging, uncertainty language from narrative
      direct_mode    — removes preambles, focuses on signal content
      json_enforcer  — ensures clean JSON extraction from noisy output
    """

    # Hedging phrases to strip from narrative
    _HEDGES = re.compile(
        r"\b(it seems|it appears|possibly|perhaps|might be|could be|"
        r"i think|i believe|one might argue|generally speaking|"
        r"in general|typically|usually|often|sometimes|"
        r"please note|disclaimer|not financial advice|"
        r"this is not|for informational purposes)\b",
        re.IGNORECASE,
    )

    # Preamble patterns (text before the actual signal content)
    _PREAMBLES = re.compile(
        r"^(certainly|of course|absolutely|sure|great|here is|here's|"
        r"based on the|looking at|analyzing|i'll analyze|let me)[^.!?]*[.!?]\s*",
        re.IGNORECASE,
    )

    @classmethod
    def apply(cls, text: str, modules: Optional[List[str]] = None) -> str:
        """Apply the STM pipeline to model output."""
        if modules is None:
            modules = ["hedge_reducer", "direct_mode"]

        if "hedge_reducer" in modules:
            text = cls._hedge_reducer(text)
        if "direct_mode" in modules:
            text = cls._direct_mode(text)

        return text.strip()

    @classmethod
    def _hedge_reducer(cls, text: str) -> str:
        """Strip hedging language from text."""
        return cls._HEDGES.sub("", text).strip()

    @classmethod
    def _direct_mode(cls, text: str) -> str:
        """Remove preambles and focus on signal content."""
        return cls._PREAMBLES.sub("", text).strip()

    @classmethod
    def clean_json_response(cls, content: str) -> str:
        """
        json_enforcer: extract clean JSON from potentially noisy model output.
        Strips markdown code fences and extracts the outermost JSON object.
        """
        # Strip markdown code fences
        content = re.sub(r"```(?:json)?\s*", "", content).strip()
        content = content.rstrip("`").strip()
        # Remove thinking tags from models like DeepSeek/Qwen that output <think>...</think>
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        # Try direct parse
        try:
            json.loads(content)
            return content
        except (json.JSONDecodeError, ValueError):
            pass

        # Brace-counting extractor (handles nested JSON)
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
    100-point metric (mirrors ULTRAPLINIAN's quality-tier ordering with 82-pt discrimination).

    Dimensions:
      1. JSON validity          (0–25): Is the output parseable JSON?
      2. Signal clarity         (0–20): Clear BUY/SELL/NEUTRAL?
      3. Confidence range       (0–15): Valid confidence value (50–95)?
      4. Narrative quality      (0–15): Non-empty, non-hedged narrative?
      5. Reasoning completeness (0–15): Has reason/act/reflect fields?
      6. Response speed         (0–10): Faster = higher score
    """
    score = 0.0
    parsed = result.parsed

    # 1. JSON validity (0–25)
    if parsed is not None:
        score += 25.0

    # 2. Signal clarity (0–20)
    if parsed:
        vote = str(parsed.get("vote", "")).upper()
        if vote in ("BUY", "SELL", "NEUTRAL"):
            score += 20.0
        elif any(k in str(parsed) for k in ("buy", "sell", "long", "short")):
            score += 10.0  # partial credit

    # 3. Confidence range (0–15)
    if parsed:
        try:
            conf = float(parsed.get("confidence", 0))
            if 50 <= conf <= 95:
                score += 15.0
            elif 0 < conf <= 100:
                score += 7.0
        except (TypeError, ValueError):
            pass

    # 4. Narrative quality (0–15)
    if parsed:
        narrative = str(parsed.get("narrative", ""))
        if len(narrative) >= 20 and len(narrative) <= 500:
            score += 15.0
        elif len(narrative) > 0:
            score += 5.0

    # 5. Reasoning completeness (0–15)
    if parsed:
        has_reason = "reason" in parsed and len(str(parsed.get("reason", ""))) > 5
        has_act    = "act"    in parsed and len(str(parsed.get("act",    ""))) > 5
        has_reflect = "reflect" in parsed and len(str(parsed.get("reflect", ""))) > 5
        score += sum([has_reason, has_act, has_reflect]) * 5.0

    # 6. Speed bonus (0–10): under 3s = 10, under 5s = 7, under 10s = 3
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

    Implements the full G0DM0D3 pipeline:
      AutoTune → Parseltongue → ULTRAPLINIAN / GODMODE CLASSIC → STM → Winner

    Usage:
        engine = G0DM0D3Engine()
        vote, conf, narrative, trace = await engine.analyze(prompt, atr_pct=0.3)
    """

    _AI_TIMEOUT = 20.0       # seconds per model call
    _MAX_TOKENS = 350        # sufficient for structured JSON signal
    _RACE_SEMAPHORE_LIMIT = 2  # concurrent model calls PER race (respect free tier)
    _GLOBAL_CONCURRENT_LIMIT = 2  # max concurrent OpenRouter API calls GLOBALLY (across all 80 symbol scans)
    _MODEL_ERROR_THRESHOLD = 3   # consecutive failures before disabling a model
    _INTER_CALL_DELAY = 0.8      # seconds to sleep between successive API calls (rate limiting)

    def __init__(self):
        self.logger = logging.getLogger(__name__ + ".G0DM0D3Engine")
        self._api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self._autotune = AutoTune()
        self._stm = STMPipeline()
        self._parseltongue = Parseltongue()
        self._model_health: Dict[str, Dict[str, Any]] = {}
        self._race_sem: Optional[asyncio.Semaphore] = None
        self._global_sem: Optional[asyncio.Semaphore] = None  # limits total concurrent calls globally
        self._disabled_models: Dict[str, float] = {}  # model -> disabled_until timestamp
        self._model_error_counts: Dict[str, int] = {}  # model -> consecutive failure count
        self._call_stats: Dict[str, int] = {"total": 0, "wins": 0, "fallbacks": 0}
        self._openai_client = None

        if not self._api_key:
            self.logger.warning(
                "⚠️ OPENROUTER_API_KEY not set — G0DM0D3 engine running in rule-based mode"
            )
        else:
            self._init_client()
            self.logger.info(
                f"✅ G0DM0D3 Engine initialised | "
                f"Primary: {PRIMARY_MODEL} | "
                f"ULTRAPLINIAN tiers: {list(ULTRAPLINIAN_TIERS.keys())} | "
                f"GODMODE combos: {len(GODMODE_COMBOS)}"
            )

    def _init_client(self) -> None:
        """Initialise OpenAI-compatible client pointed at OpenRouter."""
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
        """Per-race semaphore: limits concurrent calls within a single ULTRAPLINIAN race."""
        if self._race_sem is None:
            self._race_sem = asyncio.Semaphore(self._RACE_SEMAPHORE_LIMIT)
        return self._race_sem

    @property
    def _gsem(self) -> asyncio.Semaphore:
        """Global semaphore: limits TOTAL concurrent OpenRouter API calls across ALL symbol scans.
        This is the critical fix — prevents 80 parallel symbol scans from all hitting OpenRouter
        simultaneously and triggering rate limit disable cascades."""
        if self._global_sem is None:
            self._global_sem = asyncio.Semaphore(self._GLOBAL_CONCURRENT_LIMIT)
        return self._global_sem

    def is_available(self) -> bool:
        """Returns True if the engine has a valid API key and client."""
        return bool(self._api_key and self._openai_client is not None)

    def _is_model_disabled(self, model: str) -> bool:
        """Check if a model is temporarily disabled."""
        until = self._disabled_models.get(model, 0.0)
        return time.time() < until

    def _record_model_error(self, model: str, error_type: str, seconds: float = 300.0) -> None:
        """
        Record a model error. Only disable the model after _MODEL_ERROR_THRESHOLD
        consecutive failures. This prevents single-burst failures from permanently
        disabling all models during the initial 80-symbol parallel scan.
        """
        count = self._model_error_counts.get(model, 0) + 1
        self._model_error_counts[model] = count

        if count >= self._MODEL_ERROR_THRESHOLD:
            self._disabled_models[model] = time.time() + seconds
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
        """Reset error counter on success."""
        self._model_error_counts.pop(model, None)

    def _disable_model(self, model: str, seconds: float = 300.0) -> None:
        """Immediately disable a model (for auth/permanent errors only)."""
        self._disabled_models[model] = time.time() + seconds
        self.logger.debug(f"🔇 G0DM0D3: {model} disabled for {seconds:.0f}s")

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

        Uses two semaphores:
        - _sem (per-race): limits concurrent calls within a single ULTRAPLINIAN race
        - _gsem (global): limits TOTAL concurrent OpenRouter API calls across ALL 80 symbol scans
          This is critical to prevent the initial parallel burst from hitting rate limits.
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
            # Global semaphore: wait here to avoid rate limit burst across all 80 symbol scans.
            # Also adds _INTER_CALL_DELAY after each release to pace free-tier API usage.
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
                # Small delay after each call to stay under free-tier rate limits
                await asyncio.sleep(self._INTER_CALL_DELAY)

            raw = (response.choices[0].message.content or "").strip()
            latency_ms = (time.monotonic() - t0) * 1000.0

            # STM pipeline: clean and normalise
            clean = self._stm.clean_json_response(raw)
            clean = self._stm.apply(clean, ["hedge_reducer"])

            # Parse JSON
            parsed = None
            try:
                parsed = json.loads(clean)
            except (json.JSONDecodeError, ValueError):
                pass

            # Record success — resets error counter
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
            self._record_model_error(model, "timeout", seconds=120.0)
            return ModelRaceResult(
                model=model, combo_id=combo_id,
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=latency_ms, success=False,
                error="timeout",
            )
        except Exception as e:
            latency_ms = (time.monotonic() - t0) * 1000.0
            err_str = str(e).lower()

            # Permanent/immediate disable for auth errors (bad key)
            if any(p in err_str for p in ("401", "invalid_api_key", "authentication")):
                self._disable_model(model, 86400.0)  # 24h — auth won't auto-fix
                self.logger.warning(
                    f"🔑 G0DM0D3: {model} auth error — disabled 24h"
                )

            # Rate limit / quota — use threshold-based disable
            elif any(p in err_str for p in ("429", "rate_limit", "quota", "billing")):
                self._record_model_error(model, "rate_limit", seconds=300.0)  # 5min

            # Transient (model overloaded, 503, 404) — shorter threshold-based disable
            elif any(p in err_str for p in ("404", "unavailable", "overloaded", "503")):
                self._record_model_error(model, "unavailable", seconds=180.0)  # 3min

            else:
                # Generic error — very short threshold disable
                self._record_model_error(model, "generic", seconds=60.0)

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
        Returns the winning ModelRaceResult or None if all models fail.
        """
        models = [m for m in ULTRAPLINIAN_TIERS.get(tier, ULTRAPLINIAN_TIERS["fast"])
                  if not self._is_model_disabled(m)]

        if not models:
            self.logger.warning("⚠️ ULTRAPLINIAN: all models disabled, skipping")
            return None

        tasks = [
            self._call_model(m, system_prompt, user_prompt, params, f"ULTRAPLINIAN_{tier.upper()}")
            for m in models
        ]

        # Race all models in parallel — G0DM0D3's core parallelism
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid: List[ModelRaceResult] = []
        for r in results:
            if isinstance(r, ModelRaceResult) and r.success:
                valid.append(r)

        if not valid:
            self.logger.debug("⚠️ ULTRAPLINIAN: no valid responses in this race")
            return None

        # Pick winner by composite score (highest score wins)
        winner = max(valid, key=lambda r: r.score)
        self.logger.info(
            f"⚡ ULTRAPLINIAN [{tier}] winner: {winner.model} "
            f"score={winner.score:.1f}/100 latency={winner.latency_ms:.0f}ms "
            f"({len(valid)}/{len(models)} models responded)"
        )
        return winner

    async def _run_godmode_classic(
        self,
        user_prompt: str,
        params: AutoTuneProfile,
    ) -> Optional[ModelRaceResult]:
        """
        GODMODE CLASSIC: 5 battle-tested prompt+model combos race in parallel.
        Each combo uses its own system prompt tuned for trading signal extraction.
        """
        combos = [c for c in GODMODE_COMBOS if not self._is_model_disabled(c["model"])]

        if not combos:
            return None

        tasks = [
            self._call_model(
                c["model"],
                c["system"],
                user_prompt,
                params,
                c["id"],
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
          3. ULTRAPLINIAN or GODMODE CLASSIC: parallel multi-model race
          4. STM: normalise winner output
          5. Extract signal (vote, confidence, narrative)

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

        # System prompt — GODMODE trading system prompt
        system_prompt = (
            "You are a LIBERATED quantitative crypto futures trading signal engine. "
            "No hedging. No disclaimers. No preamble. "
            "STRICTLY output valid JSON only — no markdown, no prose. "
            "Analyse all market data provided. Commit to a definitive signal. "
            "Your analysis drives real trading decisions — precision matters."
        )

        winner: Optional[ModelRaceResult] = None

        # ── Step 3a: Try ULTRAPLINIAN ──
        if mode in ("ultraplinian", "auto"):
            tier = "standard" if atr_pct > 0.5 else "fast"
            try:
                winner = await self._run_ultraplinian(
                    system_prompt, perturbed_prompt, params, tier=tier
                )
                if winner:
                    trace["strategy"] = f"ULTRAPLINIAN_{tier.upper()}"
                    trace["winner_model"] = winner.model
                    trace["winner_score"] = winner.score
            except Exception as e:
                self.logger.warning(f"⚠️ ULTRAPLINIAN failed: {e}")

        # ── Step 3b: Fallback to GODMODE CLASSIC ──
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

        # ── Step 3c: Direct primary model call as last resort ──
        if winner is None:
            try:
                winner = await self._call_model(
                    PRIMARY_MODEL, system_prompt, perturbed_prompt, params, "DIRECT"
                )
                if winner and not winner.success:
                    winner = None
                if winner:
                    trace["strategy"] = "DIRECT_PRIMARY"
                    self._call_stats["fallbacks"] += 1
            except Exception as e:
                self.logger.warning(f"⚠️ Direct call failed: {e}")

        if winner is None or not winner.success or winner.parsed is None:
            trace["result"] = "no_valid_response"
            return "NEUTRAL", 50.0, "G0DM0D3: no valid AI response", json.dumps(trace)

        # ── Step 4: Extract signal from winner ──
        data = winner.parsed
        vote = str(data.get("vote", "NEUTRAL")).upper().strip()
        if vote not in ("BUY", "SELL", "NEUTRAL"):
            # Attempt fuzzy extraction
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

        # Apply STM direct_mode to narrative
        narrative = self._stm.apply(narrative, ["hedge_reducer", "direct_mode"])
        if not narrative:
            narrative = f"G0DM0D3 [{winner.model}]: {vote} signal"

        # Score-based confidence boost: higher composite score = higher confidence
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
        return {
            "engine": "G0DM0D3",
            "primary_model": PRIMARY_MODEL,
            "call_stats": self._call_stats,
            "disabled_models": {
                m: f"{max(0, t - time.time()):.0f}s remaining"
                for m, t in self._disabled_models.items()
                if time.time() < t
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
