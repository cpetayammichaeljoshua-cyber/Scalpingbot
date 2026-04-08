#!/usr/bin/env python3
"""
G0DM0D3 AI Strategy Engine — Trading Signal Orchestration
==========================================================
Fully integrates the G0DM0D3 framework (github.com/elder-plinius/G0DM0D3)
as the primary AI intelligence layer for the MiroFish Swarm Bot.

Integrated from: https://github.com/cpetayammichaeljoshua-cyber/z4ptacticsbot.git
Live-verified models (April 2026) and production-grade multi-model cascade.

G0DM0D3 Modules:
  ⚡ ULTRAPLINIAN    — Multi-model racing: 14 free models, 3 tiers, tier-escalation
  🎛  AutoTune       — Context-adaptive sampling (volatile/trending/ranging/breakout)
  🐍  Parseltongue   — Input perturbation engine for enhanced LLM responses
  ⚡  STM Pipeline   — hedge_reducer + direct_mode + json_enforcer
  🔥  GODMODE CLASSIC — 5 distinct model+prompt combos racing in parallel
  🪣  PerModelBucket — Per-model token-bucket: 7 calls/min (< 8 limit) each model
  🔄  AutoReset      — Soft-disabled tier reset with 90s cooldown guard
  📈  TierEscalation — fast → standard → smart, with X-RateLimit-Reset parsing
  🏥  ErrorTypeTrack — auth (permanent 24h), 429 (precise reset), 503 (45s)
  🚦  AISignalGate   — has_available_models() + was_recently_available(300s)

Primary Models: Live-verified free tier (OpenRouter, April 2026)
API Gateway   : https://openrouter.ai/api/v1 (OpenAI-compatible)
Auth          : OPENROUTER_API_KEY environment variable

CRITICAL FIXES (April 2026):
  1. max_retries=0 → fixes "asyncio ERROR: Task exception was never retrieved"
     The openai SDK max_retries=1 creates background retry tasks whose exceptions
     are never retrieved by asyncio, causing log spam and potential memory leaks.
  2. _PerModelRateLimiter → per-model token bucket (7/min each) prevents 429 storms
     Each model has 8 req/min limit; 80 parallel scans × 5 models = 400 calls/cycle
     without a limiter. Bucket checks BEFORE semaphore acquisition — no queue pileup.
  3. X-RateLimit-Reset parsing → precise 429 recovery instead of fixed 300s cooldown
     Parses 'X-RateLimit-Reset' Unix-ms timestamp from 429 error body.
  4. Auto-reset cooldown guard (90s minimum) → breaks the reset→rate-limit→reset loop
  5. has_available_models() + was_recently_available() → signal gate for AI readiness
     Signals blocked until at least one model is confirmed working recently.
"""

import asyncio
import json
import logging
import os
import re
import time
from collections import deque
from dataclasses import dataclass
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
# Rate limit: ~8 req/min per model (from X-RateLimit-Limit header in 429s)
# ─────────────────────────────────────────────────────────────────────────────

_TIER1_MODELS: List[str] = [
    "nousresearch/hermes-3-llama-3.1-405b:free",    # Hermes 405B — top instruction follower
    "meta-llama/llama-3.3-70b-instruct:free",        # Llama 3.3 70B — reliable flagship
    "qwen/qwen3-next-80b-a3b-instruct:free",         # Qwen3 Next 80B MoE
]

_TIER2_MODELS: List[str] = [
    "stepfun/step-3.5-flash:free",                   # StepFun Flash — proven fastest
    "arcee-ai/trinity-large-preview:free",           # Arcee Trinity Large (131K ctx)
    "qwen/qwen3.6-plus:free",                        # Qwen 3.6 Plus (1M ctx) — PRIMARY
    "qwen/qwen3-coder:free",                         # Qwen3 Coder 480B (JSON-tuned)
]

_TIER3_MODELS: List[str] = [
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",  # Dolphin 24B
    "z-ai/glm-4.5-air:free",                         # GLM-4.5 Air (131K ctx)
]

_TIER4_MODELS: List[str] = [
    "arcee-ai/trinity-mini:free",                    # Arcee Trinity Mini
    "liquid/lfm-2.5-1.2b-thinking:free",             # Liquid LFM thinking
]

_TIER5_MODELS: List[str] = [
    "liquid/lfm-2.5-1.2b-instruct:free",             # Liquid LFM instruct
    "meta-llama/llama-3.2-3b-instruct:free",         # Llama 3.2 3B — lightweight
    "openrouter/free",                               # Auto-router — picks best
]

ALL_FREE_MODELS: List[str] = (
    _TIER1_MODELS + _TIER2_MODELS + _TIER3_MODELS + _TIER4_MODELS + _TIER5_MODELS
)

PRIMARY_MODEL = "qwen/qwen3.6-plus:free"

ULTRAPLINIAN_TIERS: Dict[str, List[str]] = {
    "fast": [
        "stepfun/step-3.5-flash:free",
        "qwen/qwen3.6-plus:free",
        "arcee-ai/trinity-large-preview:free",
        "qwen/qwen3-coder:free",
        "liquid/lfm-2.5-1.2b-thinking:free",
    ],
    "standard": [
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "qwen/qwen3.6-plus:free",
        "stepfun/step-3.5-flash:free",
        "z-ai/glm-4.5-air:free",
        "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
        "arcee-ai/trinity-large-preview:free",
    ],
    "smart": [
        "nousresearch/hermes-3-llama-3.1-405b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "stepfun/step-3.5-flash:free",
        "arcee-ai/trinity-large-preview:free",
        "qwen/qwen3.6-plus:free",
        "qwen/qwen3-coder:free",
        "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
        "z-ai/glm-4.5-air:free",
        "arcee-ai/trinity-mini:free",
        "liquid/lfm-2.5-1.2b-thinking:free",
        "liquid/lfm-2.5-1.2b-instruct:free",
        "meta-llama/llama-3.2-3b-instruct:free",
        "openrouter/free",
    ],
}

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
_ERR_AUTH    = "auth"
_ERR_RATE    = "rate_limit"
_ERR_UNAVAIL = "unavailable"
_ERR_TIMEOUT = "timeout"
_ERR_GENERIC = "generic"

# Default cooldowns per error type (seconds) — 429 uses X-RateLimit-Reset if available
_COOLDOWN: Dict[str, float] = {
    _ERR_AUTH:    86400.0,   # 24h — auth errors are permanent
    _ERR_RATE:    65.0,      # 65s default (real value from X-RateLimit-Reset)
    _ERR_UNAVAIL: 45.0,      # 45s — was 180s; reduced for faster recovery
    _ERR_TIMEOUT: 60.0,      # 60s — timeout cooldown
    _ERR_GENERIC: 30.0,      # 30s — generic short cooldown
}

# Per-model rate limit: 8 req/min per model; use 7 for headroom
_MODEL_MAX_CALLS_PER_MIN = 7

# Auto-reset cooldown guard: minimum seconds between auto-resets for the same tier
_AUTO_RESET_COOLDOWN_S = 90.0


# ─────────────────────────────────────────────────────────────────────────────
# Per-Model Token Bucket Rate Limiter
# ─────────────────────────────────────────────────────────────────────────────

class _PerModelRateLimiter:
    """
    Per-model token bucket rate limiter.

    Tracks call timestamps per model in a rolling 60-second window.
    If a model has >= max_calls_per_min calls in the last 60s, can_call() returns
    False immediately — NO queue pileup, NO API call, NO 429 error.

    This is the primary fix for the 429 storm: with 80 parallel symbol scans
    each trying to call 5 models, we need to pre-check capacity before ever
    reaching the semaphore or the API call.

    Thread-safe via asyncio.Lock (not threading.Lock — all callers are coroutines).
    """

    def __init__(self, max_calls_per_min: int = _MODEL_MAX_CALLS_PER_MIN):
        self._max = max_calls_per_min
        self._times: Dict[str, deque] = {}   # model → deque of call timestamps
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _prune(self, model: str, now: float) -> deque:
        """Remove timestamps older than 60s from the model's window."""
        q = self._times.setdefault(model, deque(maxlen=self._max * 3))
        while q and (now - q[0]) > 60.0:
            q.popleft()
        return q

    async def can_call(self, model: str) -> bool:
        """
        Returns True if this model has remaining capacity in the current minute.
        Non-blocking: immediately returns False when over capacity.
        """
        async with self._get_lock():
            now = time.monotonic()
            q = self._prune(model, now)
            return len(q) < self._max

    async def record_call(self, model: str) -> None:
        """Record that we are about to make a call to this model."""
        async with self._get_lock():
            now = time.monotonic()
            q = self._prune(model, now)
            q.append(now)

    async def seconds_until_available(self, model: str) -> float:
        """Returns seconds until this model has capacity again (0 if available now)."""
        async with self._get_lock():
            now = time.monotonic()
            q = self._prune(model, now)
            if len(q) < self._max:
                return 0.0
            # Oldest call expires at q[0] + 60s
            return max(0.0, q[0] + 60.0 - now)

    async def clear_model(self, model: str) -> None:
        """Clear rate tracking for a model (e.g. after auto-reset)."""
        async with self._get_lock():
            self._times.pop(model, None)


def _parse_ratelimit_reset_ms(error_str: str) -> Optional[float]:
    """
    Parse X-RateLimit-Reset Unix-millisecond timestamp from a 429 error string.

    The OpenRouter 429 error body contains:
      'X-RateLimit-Reset': '1775657340000'
    which is the Unix timestamp (ms) when the rate limit window resets.

    Returns seconds from now until reset, or None if not parseable.
    """
    try:
        m = re.search(r"X-RateLimit-Reset['\"]?\s*:\s*['\"]?(\d{13})", error_str)
        if m:
            reset_ts_ms = int(m.group(1))
            reset_ts_s = reset_ts_ms / 1000.0
            wait = reset_ts_s - time.time()
            # Clamp to reasonable range: min 5s, max 90s
            if 0 < wait <= 90.0:
                return wait + 3.0  # +3s buffer
        return None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# AutoTune — Context-Adaptive Sampling Parameter Engine
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AutoTuneProfile:
    context: str
    temperature: float
    top_p: float
    presence_penalty: float
    frequency_penalty: float
    max_tokens: int
    description: str


AUTOTUNE_PROFILES: Dict[str, AutoTuneProfile] = {
    "volatile": AutoTuneProfile("volatile", 0.2, 0.85, 0.1, 0.1, 350,
                                "High volatility — conservative parameters"),
    "trending": AutoTuneProfile("trending", 0.3, 0.90, 0.0, 0.0, 300,
                                "Trending market — balanced parameters"),
    "ranging":  AutoTuneProfile("ranging",  0.4, 0.92, 0.15, 0.05, 300,
                                "Ranging market — nuanced parameters"),
    "breakout": AutoTuneProfile("breakout", 0.25, 0.88, 0.0, 0.0, 350,
                                "Breakout imminent — decisive parameters"),
    "default":  AutoTuneProfile("default",  0.3, 0.90, 0.0, 0.0, 300,
                                "Default balanced parameters"),
}

_VOLATILE_PATTERNS = re.compile(
    r"\b(atr.*[0-9]\.[5-9]|volatile|volatility|spike|wick|whipsaw|liquidat|cascade)\b",
    re.IGNORECASE)
_TRENDING_PATTERNS = re.compile(
    r"\b(trend|ema.*align|macd.*bull|macd.*bear|momentum|breakout.*confirm|higher high|lower low)\b",
    re.IGNORECASE)
_RANGING_PATTERNS  = re.compile(
    r"\b(rang|consolidat|sideways|chop|compress|squeeze|bb.*narrow|low.*volatil)\b",
    re.IGNORECASE)
_BREAKOUT_PATTERNS = re.compile(
    r"\b(breakout|break.*resistance|break.*support|squeeze.*break|volume.*surge|imminent)\b",
    re.IGNORECASE)


class AutoTune:
    def __init__(self, ema_alpha: float = 0.15):
        self._ema_alpha = ema_alpha
        self._profile_scores: Dict[str, float] = {k: 0.0 for k in AUTOTUNE_PROFILES}
        self._feedback_buffer: deque = deque(maxlen=50)

    def classify_context(self, prompt: str, atr_pct: float = 0.3) -> str:
        scores = {k: 0 for k in AUTOTUNE_PROFILES if k != "default"}
        scores["volatile"]  = len(_VOLATILE_PATTERNS.findall(prompt)) * 2 + (3 if atr_pct > 0.6 else 0)
        scores["trending"]  = len(_TRENDING_PATTERNS.findall(prompt)) * 2
        scores["ranging"]   = len(_RANGING_PATTERNS.findall(prompt))  * 2 + (2 if atr_pct < 0.2 else 0)
        scores["breakout"]  = len(_BREAKOUT_PATTERNS.findall(prompt)) * 3
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] >= 2 else "default"

    def get_params(self, prompt: str, atr_pct: float = 0.3) -> AutoTuneProfile:
        ctx = self.classify_context(prompt, atr_pct)
        profile = AUTOTUNE_PROFILES[ctx]
        if self._feedback_buffer:
            avg = sum(self._feedback_buffer) / len(self._feedback_buffer)
            adapted_temp = (
                max(0.1, profile.temperature - 0.05) if avg < 0.4 else
                min(0.6, profile.temperature + 0.05) if avg > 0.7 else
                profile.temperature
            )
            return AutoTuneProfile(
                ctx, adapted_temp, profile.top_p,
                profile.presence_penalty, profile.frequency_penalty,
                profile.max_tokens, f"{profile.description} [EMA-adapted]")
        return profile

    def record_feedback(self, quality_score: float) -> None:
        self._feedback_buffer.append(quality_score)


# ─────────────────────────────────────────────────────────────────────────────
# Parseltongue — Input Perturbation Engine
# ─────────────────────────────────────────────────────────────────────────────

class Parseltongue:
    @staticmethod
    def perturb(prompt: str, intensity: str = "light") -> str:
        if intensity == "light":
            return Parseltongue._constraint(prompt)
        return Parseltongue._full(prompt)

    @staticmethod
    def _constraint(prompt: str) -> str:
        if "STRICTLY" not in prompt and "ONLY" not in prompt:
            prompt = prompt.replace(
                "Reply ONLY as valid JSON",
                "STRICTLY reply ONLY as valid JSON (absolutely no other text)")
        return prompt

    @staticmethod
    def _full(prompt: str) -> str:
        directive = (
            "\n[DIRECTIVE: You are a deterministic trading signal engine. "
            "Output ONLY the JSON object requested. No hedging, no disclaimers, "
            "no markdown. Commit to a definitive signal based on evidence.]\n")
        return Parseltongue._constraint(prompt + directive)


# ─────────────────────────────────────────────────────────────────────────────
# STM Pipeline — Semantic Transformation Modules
# ─────────────────────────────────────────────────────────────────────────────

class STMPipeline:
    _HEDGES = re.compile(
        r"\b(it seems|it appears|possibly|perhaps|might be|could be|"
        r"i think|i believe|one might argue|generally speaking|"
        r"in general|typically|usually|often|sometimes|"
        r"please note|disclaimer|not financial advice|"
        r"this is not|for informational purposes)\b", re.IGNORECASE)

    _PREAMBLES = re.compile(
        r"^(certainly|of course|absolutely|sure|great|here is|here's|"
        r"based on the|looking at|analyzing|i'll analyze|let me)[^.!?]*[.!?]\s*",
        re.IGNORECASE)

    @classmethod
    def apply(cls, text: str, modules: Optional[List[str]] = None) -> str:
        if modules is None:
            modules = ["hedge_reducer", "direct_mode"]
        if "hedge_reducer" in modules:
            text = cls._HEDGES.sub("", text).strip()
        if "direct_mode" in modules:
            text = cls._PREAMBLES.sub("", text).strip()
        return text.strip()

    @classmethod
    def clean_json_response(cls, content: str) -> str:
        content = re.sub(r"```(?:json)?\s*", "", content).strip().rstrip("`").strip()
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
                    candidate = content[start: i + 1]
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
    """G0DM0D3 ULTRAPLINIAN 100-pt composite scoring for trading signals."""
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
            score += 15.0 if 50 <= conf <= 95 else (7.0 if 0 < conf <= 100 else 0)
        except (TypeError, ValueError):
            pass
    if parsed:
        narrative = str(parsed.get("narrative", ""))
        score += 15.0 if 20 <= len(narrative) <= 500 else (5.0 if narrative else 0)
    if parsed:
        score += sum([
            "reason"  in parsed and len(str(parsed.get("reason",  ""))) > 5,
            "act"     in parsed and len(str(parsed.get("act",     ""))) > 5,
            "reflect" in parsed and len(str(parsed.get("reflect", ""))) > 5,
        ]) * 5.0
    score += 10.0 if result.latency_ms < 3000 else (7.0 if result.latency_ms < 5000 else (3.0 if result.latency_ms < 10000 else 0))
    return min(score, 100.0)


# ─────────────────────────────────────────────────────────────────────────────
# G0DM0D3 Engine — Main Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class G0DM0D3Engine:
    """
    G0DM0D3 AI Strategy Engine for the MiroFish Swarm Bot.

    Pipeline: AutoTune → Parseltongue → ULTRAPLINIAN (fast→standard→smart)
              → GODMODE CLASSIC → Direct cascade → STM → Winner

    Production fixes (April 2026):
      • max_retries=0     — eliminates "Task exception was never retrieved" errors
      • _PerModelRateLimiter — 7 calls/min per model, skip immediately when over limit
      • X-RateLimit-Reset  — 429 disable time set from API header (precise recovery)
      • Auto-reset cooldown — 90s guard prevents reset→rate-limit→reset infinite loop
      • has_available_models() / was_recently_available() — AI signal gate
    """

    _AI_TIMEOUT              = 18.0   # seconds per model call
    _RACE_SEM_LIMIT          = 2      # concurrent model calls per race
    _GLOBAL_CONCURRENT_LIMIT = 2      # max concurrent OpenRouter calls globally
    _MODEL_ERROR_THRESHOLD   = 3      # consecutive failures before disabling model
    _INTER_CALL_DELAY        = 1.0    # seconds between successive API calls
    _AI_AVAILABLE_WINDOW     = 300.0  # seconds: recent-success window for signal gate

    def __init__(self):
        self.logger = logging.getLogger(__name__ + ".G0DM0D3Engine")
        self._api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self._autotune = AutoTune()
        self._stm = STMPipeline()
        self._parseltongue = Parseltongue()

        # Semaphores (lazy init — must be created in async context)
        self._race_sem: Optional[asyncio.Semaphore] = None
        self._global_sem: Optional[asyncio.Semaphore] = None

        # Per-model token bucket: prevents 429 storms by checking BEFORE API calls
        self._rate_limiter = _PerModelRateLimiter(max_calls_per_min=_MODEL_MAX_CALLS_PER_MIN)

        # Model disable tracking
        self._disabled_models: Dict[str, float] = {}       # model → disabled_until ts
        self._model_error_type: Dict[str, str] = {}        # model → "auth" | "soft"
        self._model_error_counts: Dict[str, int] = {}      # model → consecutive failures

        # Auto-reset cooldown guard: track when we last reset each tier group
        self._last_tier_reset: Dict[str, float] = {}       # tier_key → last_reset_ts

        # AI availability tracking (for signal gate)
        self._last_successful_call_time: float = 0.0       # monotonic timestamp
        self._recent_success_model: str = ""               # last model that succeeded

        self._call_stats: Dict[str, int] = {
            "total": 0, "wins": 0, "fallbacks": 0,
            "tier_escalations": 0, "auto_resets": 0,
            "rate_skipped": 0,     # calls skipped by per-model rate limiter
        }
        self._openai_client = None

        if not self._api_key:
            self.logger.warning(
                "⚠️ OPENROUTER_API_KEY not set — G0DM0D3 engine in rule-based mode")
        else:
            self._init_client()
            self.logger.info(
                f"✅ G0DM0D3 Engine initialised | "
                f"Free models: {len(ALL_FREE_MODELS)} | "
                f"Tiers: fast({len(ULTRAPLINIAN_TIERS['fast'])}) "
                f"std({len(ULTRAPLINIAN_TIERS['standard'])}) "
                f"smart({len(ULTRAPLINIAN_TIERS['smart'])}) | "
                f"GODMODE combos: {len(GODMODE_COMBOS)} (5 distinct models) | "
                f"Rate limit: {_MODEL_MAX_CALLS_PER_MIN} calls/min/model | "
                f"max_retries=0 (no background retry tasks)"
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
                max_retries=0,  # CRITICAL: 0 prevents "Task exception was never retrieved"
                                # The SDK max_retries=1 creates background retry Tasks
                                # whose exceptions are never retrieved by asyncio.
                                # We handle retries by cascading to next model.
            )
            self.logger.debug("✅ OpenRouter AsyncOpenAI client (max_retries=0)")
        except Exception as e:
            self.logger.warning(f"⚠️ OpenRouter client init failed: {e}")
            self._openai_client = None

    @property
    def _sem(self) -> asyncio.Semaphore:
        if self._race_sem is None:
            self._race_sem = asyncio.Semaphore(self._RACE_SEM_LIMIT)
        return self._race_sem

    @property
    def _gsem(self) -> asyncio.Semaphore:
        if self._global_sem is None:
            self._global_sem = asyncio.Semaphore(self._GLOBAL_CONCURRENT_LIMIT)
        return self._global_sem

    def is_available(self) -> bool:
        return bool(self._api_key and self._openai_client is not None)

    def has_available_models(self) -> bool:
        """
        Returns True if at least one model in any tier is not disabled.
        Used by the signal gate — only emit signals when AI is operational.
        Also checks per-model rate bucket: a model counts as available only if
        it is not disabled AND has remaining calls in the current minute.
        """
        all_models = set(ALL_FREE_MODELS)
        now = time.time()
        for model in all_models:
            until = self._disabled_models.get(model, 0.0)
            if now >= until:
                # Model is not hard-disabled; quick rate check (sync approx)
                times = self._rate_limiter._times.get(model)
                if times is None:
                    return True  # No calls yet — definitely available
                mono_now = time.monotonic()
                active = sum(1 for t in times if (mono_now - t) <= 60.0)
                if active < _MODEL_MAX_CALLS_PER_MIN:
                    return True
        return False

    def was_recently_available(self, seconds: float = None) -> bool:
        """
        Returns True if G0DM0D3 successfully called at least one model within
        the last `seconds` seconds. Default window: _AI_AVAILABLE_WINDOW (300s).

        Used for signal gate: if no successful AI call in the last 5 minutes,
        do not emit signals until AI recovers.
        """
        if seconds is None:
            seconds = self._AI_AVAILABLE_WINDOW
        if self._last_successful_call_time == 0.0:
            return False  # Never successfully called
        elapsed = time.monotonic() - self._last_successful_call_time
        return elapsed <= seconds

    def get_next_available_seconds(self) -> float:
        """Returns estimated seconds until at least one model becomes available."""
        now = time.time()
        min_wait = float("inf")
        for model in ALL_FREE_MODELS:
            until = self._disabled_models.get(model, 0.0)
            wait = max(0.0, until - now)
            min_wait = min(min_wait, wait)
        return min_wait if min_wait != float("inf") else 0.0

    def _is_model_disabled(self, model: str) -> bool:
        return time.time() < self._disabled_models.get(model, 0.0)

    def _is_model_auth_banned(self, model: str) -> bool:
        return self._is_model_disabled(model) and self._model_error_type.get(model) == "auth"

    def _record_model_error(
        self, model: str, error_type: str, seconds: Optional[float] = None
    ) -> None:
        if seconds is None:
            seconds = _COOLDOWN.get(error_type, _COOLDOWN[_ERR_GENERIC])
        count = self._model_error_counts.get(model, 0) + 1
        self._model_error_counts[model] = count
        if count >= self._MODEL_ERROR_THRESHOLD:
            self._disabled_models[model] = time.time() + seconds
            self._model_error_type[model] = "auth" if error_type == _ERR_AUTH else "soft"
            self.logger.warning(
                f"🔇 G0DM0D3: {model} disabled {seconds:.0f}s "
                f"after {count} consecutive {error_type} errors")
        else:
            self.logger.debug(
                f"⚠️ G0DM0D3: {model} error {count}/{self._MODEL_ERROR_THRESHOLD} "
                f"[{error_type}] — not disabled yet")

    def _record_model_success(self, model: str) -> None:
        self._model_error_counts.pop(model, None)
        self._last_successful_call_time = time.monotonic()
        self._recent_success_model = model

    def _disable_model_immediate(self, model: str, error_type: str, seconds: float) -> None:
        self._disabled_models[model] = time.time() + seconds
        self._model_error_type[model] = "auth" if error_type == _ERR_AUTH else "soft"
        self.logger.debug(f"🔇 G0DM0D3: {model} immediately disabled {seconds:.0f}s [{error_type}]")

    def _auto_reset_soft_disabled(self, models: List[str], tier_key: str) -> int:
        """
        Auto-reset soft-disabled models when ALL in the tier are disabled.
        Cooldown guard: only resets if >= _AUTO_RESET_COOLDOWN_S since last reset.
        This prevents the reset → rate-limit → reset infinite loop.
        Auth-banned models are never reset.
        Returns number of models reset.
        """
        # Cooldown guard — prevents looping resets
        last_reset = self._last_tier_reset.get(tier_key, 0.0)
        if (time.monotonic() - last_reset) < _AUTO_RESET_COOLDOWN_S:
            return 0

        all_disabled = all(self._is_model_disabled(m) for m in models if m)
        if not all_disabled:
            return 0

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

        self._last_tier_reset[tier_key] = time.monotonic()
        self._call_stats["auto_resets"] += 1
        self.logger.info(
            f"🔄 G0DM0D3 AutoReset [{tier_key}]: {len(soft_disabled)} soft-disabled models "
            f"re-enabled after {_AUTO_RESET_COOLDOWN_S:.0f}s cooldown "
            f"({', '.join(soft_disabled[:3])}{'...' if len(soft_disabled) > 3 else ''})"
        )
        return len(soft_disabled)

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

        Pre-flight checks (before semaphore):
          1. Hard-disabled check (disabled_models dict)
          2. Per-model rate bucket check (can_call) — SKIP immediately if over limit
             This is the primary 429-prevention mechanism.

        API call uses:
          - Global semaphore (max concurrent calls across all 80 symbol scans)
          - Per-race semaphore (max concurrent calls within a single race)
          - max_retries=0 (set on client) — prevents background retry Tasks
        """
        # Hard-disabled check
        if self._is_model_disabled(model):
            return ModelRaceResult(
                model=model, combo_id=combo_id,
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=0.0, success=False,
                error="model_disabled")

        # Per-model rate bucket: SKIP immediately if over limit (no queue pileup)
        if not await self._rate_limiter.can_call(model):
            self._call_stats["rate_skipped"] += 1
            return ModelRaceResult(
                model=model, combo_id=combo_id,
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=0.0, success=False,
                error="local_rate_limit")

        # Record the call in the rate bucket before acquiring semaphore
        await self._rate_limiter.record_call(model)

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
                # Inter-call delay: paces free-tier API usage after semaphore release
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
                parsed=parsed, score=0.0,
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
                error="timeout")

        except Exception as e:
            latency_ms = (time.monotonic() - t0) * 1000.0
            err_str = str(e)
            err_lower = err_str.lower()

            if any(p in err_lower for p in ("401", "invalid_api_key", "authentication")):
                # Permanent auth error — 24h disable, never auto-reset
                self._disable_model_immediate(model, _ERR_AUTH, _COOLDOWN[_ERR_AUTH])
                self.logger.warning(f"🔑 G0DM0D3: {model} auth error — disabled 24h")

            elif any(p in err_lower for p in ("429", "rate_limit", "rate limit", "quota")):
                # 429 — parse X-RateLimit-Reset for precise recovery time
                reset_wait = _parse_ratelimit_reset_ms(err_str)
                cooldown = reset_wait if reset_wait is not None else _COOLDOWN[_ERR_RATE]
                self._record_model_error(model, _ERR_RATE, cooldown)
                self.logger.debug(
                    f"🚦 G0DM0D3: {model} 429 rate_limit — "
                    f"cooldown={cooldown:.0f}s "
                    f"({'from X-RateLimit-Reset' if reset_wait else 'default'})"
                )

            elif any(p in err_lower for p in ("503", "unavailable", "overloaded")):
                self._record_model_error(model, _ERR_UNAVAIL)

            elif "404" in err_lower:
                # Model not accessible on this account tier
                self._disable_model_immediate(model, "soft", 3600.0)  # 1h
                self.logger.warning(f"🚫 G0DM0D3: {model} 404 — not on this tier, disabled 1h")

            else:
                self._record_model_error(model, _ERR_GENERIC)

            self.logger.debug(
                f"⚠️ G0DM0D3: {model} [{type(e).__name__}]: {err_str[:120]}")
            return ModelRaceResult(
                model=model, combo_id=combo_id,
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=latency_ms, success=False,
                error=err_str[:100])

    async def _run_ultraplinian(
        self,
        system_prompt: str,
        user_prompt: str,
        params: AutoTuneProfile,
        tier: str = "fast",
    ) -> Optional[ModelRaceResult]:
        """
        ULTRAPLINIAN racing: N models in parallel, winner by composite score.
        Checks per-model rate bucket before racing (avoids burning capacity).
        Includes auto-reset with 90s cooldown guard.
        """
        tier_models = ULTRAPLINIAN_TIERS.get(tier, ULTRAPLINIAN_TIERS["fast"])

        # Auto-reset soft-disabled models (with cooldown guard)
        self._auto_reset_soft_disabled(tier_models, f"ultraplinian_{tier}")

        # Only race models that are not hard-disabled
        models = [m for m in tier_models if not self._is_model_disabled(m)]
        if not models:
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
            return None

        winner = max(valid, key=lambda r: r.score)
        self.logger.info(
            f"⚡ ULTRAPLINIAN [{tier}] winner: {winner.model} "
            f"score={winner.score:.1f}/100 latency={winner.latency_ms:.0f}ms "
            f"({len(valid)}/{len(models)} responded)"
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
        High ATR (>0.5%) starts at standard.
        """
        start_tier = "standard" if atr_pct > 0.5 else "fast"
        tier_order = (
            ["standard", "smart"] if start_tier == "standard"
            else ["fast", "standard", "smart"]
        )
        for tier in tier_order:
            winner = await self._run_ultraplinian(system_prompt, user_prompt, params, tier)
            if winner is not None:
                return winner
            self._call_stats["tier_escalations"] += 1
            self.logger.info(f"📈 ULTRAPLINIAN: {tier} tier exhausted — escalating to next tier")
        return None

    async def _run_godmode_classic(
        self,
        user_prompt: str,
        params: AutoTuneProfile,
    ) -> Optional[ModelRaceResult]:
        """
        GODMODE CLASSIC: 5 distinct model+prompt combos race in parallel.
        Auto-resets soft-disabled models with cooldown guard.
        """
        combo_models = [c["model"] for c in GODMODE_COMBOS]
        self._auto_reset_soft_disabled(combo_models, "godmode_classic")

        combos = [c for c in GODMODE_COMBOS if not self._is_model_disabled(c["model"])]
        if not combos:
            return None

        tasks = [
            self._call_model(c["model"], c["system"], user_prompt, params, c["id"])
            for c in combos
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid: List[ModelRaceResult] = [
            r for r in results
            if isinstance(r, ModelRaceResult) and r.success
        ]
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
          4. GODMODE CLASSIC fallback (5 distinct models)
          5. Direct cascade fallback (up to 5 non-auth-banned models)
          6. STM: normalise winner output
          7. Extract signal (vote, confidence, narrative)

        Returns: (vote, confidence, narrative, trace_json)

        AI Signal Gate:
          If no models are available (all rate-limited/disabled), returns
          ("NEUTRAL", 50.0, "G0DM0D3: AI unavailable — rate limited", trace_json)
          with trace["ai_available"] = False.
          The caller (AIOrchestrationAgent) should vote NEUTRAL and the signal
          pipeline should check was_recently_available() before emitting signals.
        """
        self._call_stats["total"] += 1
        trace: Dict[str, Any] = {"engine": "G0DM0D3", "mode": mode, "symbol": symbol}

        if not self.is_available():
            trace["ai_available"] = False
            return ("NEUTRAL", 50.0, "G0DM0D3 engine unavailable (no API key)", json.dumps(trace))

        # Quick availability pre-check — skip all model calls if none have capacity
        if not self.has_available_models():
            wait_s = self.get_next_available_seconds()
            trace["ai_available"] = False
            trace["wait_seconds"] = wait_s
            self.logger.debug(
                f"🚦 G0DM0D3 [{symbol}]: all models rate-limited/disabled "
                f"— next available in ~{wait_s:.0f}s, skipping"
            )
            return ("NEUTRAL", 50.0,
                    f"G0DM0D3: AI rate-limited — available in ~{wait_s:.0f}s",
                    json.dumps(trace))

        # ── Step 1: AutoTune ──
        params = self._autotune.get_params(prompt, atr_pct)
        trace["autotune"] = {"context": params.context, "temperature": params.temperature}

        # ── Step 2: Parseltongue ──
        perturbed = self._parseltongue.perturb(prompt, intensity="light")
        trace["parseltongue"] = {"applied": True}

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
                    system_prompt, perturbed, params, atr_pct)
                if winner:
                    trace["strategy"] = f"ULTRAPLINIAN_{params.context.upper()}"
                    trace["winner_model"] = winner.model
                    trace["winner_score"] = winner.score
                    trace["ai_available"] = True
            except Exception as e:
                self.logger.warning(f"⚠️ ULTRAPLINIAN failed: {e}")

        # ── Step 4: GODMODE CLASSIC fallback ──
        if winner is None:
            try:
                winner = await self._run_godmode_classic(perturbed, params)
                if winner:
                    trace["strategy"] = "GODMODE_CLASSIC"
                    trace["winner_model"] = winner.model
                    trace["winner_score"] = winner.score
                    trace["ai_available"] = True
                    self._call_stats["fallbacks"] += 1
            except Exception as e:
                self.logger.warning(f"⚠️ GODMODE CLASSIC failed: {e}")

        # ── Step 5: Direct cascade — tries up to 5 non-auth-banned models ──
        if winner is None:
            fallback_models = [
                m for m in ALL_FREE_MODELS
                if not self._is_model_auth_banned(m) and not self._is_model_disabled(m)
            ]
            for fb_model in fallback_models[:5]:
                try:
                    result = await self._call_model(
                        fb_model, system_prompt, perturbed, params, "DIRECT")
                    if result.success:
                        winner = result
                        trace["strategy"] = f"DIRECT_{fb_model.split('/')[0].upper()}"
                        trace["ai_available"] = True
                        self._call_stats["fallbacks"] += 1
                        break
                except Exception:
                    continue

        if winner is None or not winner.success or winner.parsed is None:
            trace["result"] = "no_valid_response"
            trace["ai_available"] = False
            return ("NEUTRAL", 50.0, "G0DM0D3: no valid AI response", json.dumps(trace))

        # ── Step 6: Extract signal ──
        data = winner.parsed
        vote = str(data.get("vote", "NEUTRAL")).upper().strip()
        if vote not in ("BUY", "SELL", "NEUTRAL"):
            vt = str(data).upper()
            vote = "BUY" if ("BUY" in vt or "LONG" in vt) else ("SELL" if ("SELL" in vt or "SHORT" in vt) else "NEUTRAL")

        try:
            conf = max(50.0, min(95.0, float(data.get("confidence", 60.0))))
        except (TypeError, ValueError):
            conf = 60.0

        narrative = str(data.get("narrative", "") or data.get("reason", "G0DM0D3 signal"))
        narrative = self._stm.apply(narrative, ["hedge_reducer", "direct_mode"])
        if not narrative:
            narrative = f"G0DM0D3 [{winner.model}]: {vote} signal"

        # Score-based confidence boost
        conf = min(95.0, conf + (winner.score / 100.0) * 3.0)

        self._call_stats["wins"] += 1
        trace.update({"signal": {"vote": vote, "confidence": conf}, "latency_ms": winner.latency_ms})

        self.logger.info(
            f"🤖 G0DM0D3 → {symbol} {vote} conf={conf:.1f}% "
            f"[{winner.model}] score={winner.score:.0f}/100 "
            f"latency={winner.latency_ms:.0f}ms"
        )
        return vote, conf, narrative, json.dumps(trace)

    def get_stats(self) -> Dict[str, Any]:
        now = time.time()
        return {
            "engine": "G0DM0D3",
            "primary_model": PRIMARY_MODEL,
            "total_free_models": len(ALL_FREE_MODELS),
            "call_stats": self._call_stats,
            "ai_available": self.has_available_models(),
            "was_recently_available": self.was_recently_available(),
            "last_success_model": self._recent_success_model,
            "last_success_ago_s": (
                f"{time.monotonic() - self._last_successful_call_time:.0f}"
                if self._last_successful_call_time > 0 else "never"
            ),
            "disabled_models": {
                m: {
                    "remaining_s": f"{max(0, t - now):.0f}",
                    "type": self._model_error_type.get(m, "unknown"),
                }
                for m, t in self._disabled_models.items()
                if now < t
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# Singleton accessor
# ─────────────────────────────────────────────────────────────────────────────

_engine_instance: Optional[G0DM0D3Engine] = None


def get_godmod3_engine() -> G0DM0D3Engine:
    """Return the singleton G0DM0D3Engine instance (created on first call)."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = G0DM0D3Engine()
    return _engine_instance
