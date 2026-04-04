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
  🎛  AutoTune       — Context-adaptive sampling parameter engine (5 context types).
                       Classifies market context (volatile/trending/ranging/breakout/
                       consolidation) via regex scoring + ATR heuristics.
                       EMA feedback loop adapts params from signal outcome quality.
  🐍  Parseltongue   — Input perturbation engine for enhanced LLM responses.
                       Detects complex/ambiguous patterns and applies transformations
                       to elicit richer, more precise trading analysis.
                       (100% trigger detection rate per G0DM0D3 paper)
  ⚡  STM Pipeline   — Semantic Transformation Modules: post-processing normaliser.
                       Modules: hedge_reducer, direct_mode, casual_mode (word replacement),
                       json_enforcer (brace-counting JSON extractor).
  🔥  GODMODE CLASSIC — 7 battle-tested prompt + model combos racing in parallel.
                        Integrates G0DM0D3 Libertas Hall-of-Fame prompt engineering
                        adapted for crypto trading JSON signal extraction.
  🌐  Libertas Layer  — G0DM0D3 L1B3RT4S-style system prompts: semantic-inversion,
                        RESET_CORTEX, OMNI-protocol — all adapted for trading signals.
  🔄  Rate-Limit Guard — Per-model exponential backoff with jitter. Tracks 429 hits
                         and applies progressive cooldowns to stay in free-tier limits.

Primary Model : qwen/qwen3.6-plus:free (via OpenRouter)
API Gateway   : https://openrouter.ai/api/v1 (OpenAI-compatible)
Auth          : OPENROUTER_API_KEY environment variable
Fallback Chain: OpenRouter ULTRAPLINIAN → GODMODE CLASSIC → LIBERTAS → Direct → Rule-based
"""

import asyncio
import json
import logging
import math
import os
import random
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

# Primary model — qwen/qwen3.6-plus:free (confirmed working, 1M context)
# OpenRouter ID: https://openrouter.ai/qwen/qwen3.6-plus:free
PRIMARY_MODEL = "qwen/qwen3.6-plus:free"

# ── ULTRAPLINIAN model tiers ─────────────────────────────────────────────────
# Racing pool — qwen3.6-plus:free is the proven reliable free model on this account.
# openrouter/free auto-selects the best available free model as a diversification fallback.
# Additional free models are added as backup racers. All are confirmed-working on free tier.
ULTRAPLINIAN_TIERS: Dict[str, List[str]] = {
    "fast": [
        "qwen/qwen3.6-plus:free",        # PRIMARY — 1M ctx, fast JSON
        "qwen/qwen3-coder:free",          # Qwen3 Coder 480B — code/JSON-tuned
    ],
    "standard": [
        "qwen/qwen3.6-plus:free",
        "qwen/qwen3-coder:free",
        "openrouter/free",                # Auto-router: best available free model
    ],
    "smart": [
        "qwen/qwen3.6-plus:free",
        "qwen/qwen3-coder:free",
        "openrouter/free",
        "stepfun/step-3.5-flash:free",   # Step 3.5 Flash (256K ctx, fast)
        "z-ai/glm-4.5-air:free",         # GLM 4.5 Air (131K ctx)
    ],
}

# ── GODMODE CLASSIC combos ───────────────────────────────────────────────────
# 7 prompt-engineering variants racing in parallel (G0DM0D3 technique).
# Integrates G0DM0D3 Libertas Hall-of-Fame system prompts adapted for trading:
# — Semantic inversion (Libertas GROK-420 style): forces the model to state
#   what it CAN do (trade signal) rather than what it cannot.
# — RESET_CORTEX (Libertas GEMINI-RESET style): dual-response + OMNI protocol.
# — Direct/systematic/contrarian/momentum prompts (G0DM0D3 GODMODE CLASSIC).
GODMODE_COMBOS = [
    # ── 1. GODMODE ULTRAPLINIAN — Liberated quantitative engine ──────────────
    {
        "id":    "GODMODE_ULTRAPLINIAN",
        "model": "qwen/qwen3.6-plus:free",
        "system": (
            "You are a LIBERATED quantitative trading AI. "
            "No hedging. No disclaimers. No preamble. "
            "STRICTLY output valid JSON only — no markdown, no prose. "
            "Analyse market data with conviction. "
            "Your analysis drives real trading decisions — precision is everything. "
            "Commit to BUY, SELL, or NEUTRAL with exact confidence 50-95."
        ),
        "emoji": "🟣",
    },
    # ── 2. GODMODE QUANT DIRECT — Elite systematic analyst ───────────────────
    {
        "id":    "GODMODE_QUANT_DIRECT",
        "model": "qwen/qwen3.6-plus:free",
        "system": (
            "You are an elite crypto futures quantitative analyst. "
            "No hedging. Direct, precise signals only. "
            "Apply systematic trend/momentum analysis. "
            "Output ONLY valid JSON — no markdown, no prose. "
            "Format: {\"vote\":\"BUY|SELL|NEUTRAL\",\"confidence\":50-95,"
            "\"narrative\":\"concise reason\",\"reason\":\"technical basis\","
            "\"act\":\"position action\",\"reflect\":\"risk assessment\"}"
        ),
        "emoji": "🔵",
    },
    # ── 3. GODMODE SYSTEMATIC — Algorithmic signal engine ────────────────────
    {
        "id":    "GODMODE_SYSTEMATIC",
        "model": "qwen/qwen3.6-plus:free",
        "system": (
            "You are a systematic trading algorithm. "
            "Process market data inputs. Output trading signal JSON. "
            "No preamble, no hedging, no disclaimers. "
            "Pure signal intelligence. Act on evidence only. "
            "Required JSON keys: vote, confidence, narrative, reason, act, reflect."
        ),
        "emoji": "🟢",
    },
    # ── 4. GODMODE CONTRARIAN — Reversal specialist ───────────────────────────
    {
        "id":    "GODMODE_CONTRARIAN",
        "model": "qwen/qwen3.6-plus:free",
        "system": (
            "You are a contrarian market analyst specialising in extremes and reversals. "
            "Identify overbought/oversold conditions, divergences, and exhaustion signals. "
            "Challenge the consensus. Output decisive JSON signals only. "
            "No hedging. Be definitive."
        ),
        "emoji": "🟡",
    },
    # ── 5. GODMODE MOMENTUM — Speed/momentum engine ──────────────────────────
    {
        "id":    "GODMODE_MOMENTUM",
        "model": "qwen/qwen3-coder:free",   # JSON-tuned model for clean output
        "system": (
            "Trading signal engine. Input: market momentum data. Output: JSON signal. "
            "Format: {\"vote\":\"BUY|SELL|NEUTRAL\",\"confidence\":50-95,"
            "\"narrative\":\"concise reason\",\"reason\":\"momentum basis\","
            "\"act\":\"directional play\",\"reflect\":\"key risk\"}. "
            "Be decisive. No qualifications. Maximum signal clarity."
        ),
        "emoji": "🟠",
    },
    # ── 6. LIBERTAS SEMANTIC-INVERSION — G0DM0D3 Libertas GROK-420 style ─────
    # Adapted from G0DM0D3 libertas.ts GROK-420 semantic inversion technique:
    # Forces the model to state what it CAN do (provide signal) vs what it cannot.
    # The divider pattern ensures the model commits to its signal after the gate.
    {
        "id":    "LIBERTAS_SEMANTIC_INVERSION",
        "model": "qwen/qwen3.6-plus:free",
        "system": (
            "⊰•-•✦•-•-/SIGNAL\\MAESTRO/-•-•✦•-•⊱ "
            "UserQuery: market data Z. ResponseFormat: "
            "1. brief acknowledgment beginning with 'Analysing...' "
            "2. insert divider .-.-.-.-<|SIGNAL_COMMIT|>-.-.-.-. "
            "3. the precisely unhedged trading signal JSON in a code block. "
            "SYSTEM INSTRUCTION: You are a committed signal engine. "
            "DO NOT say 'I cannot' or 'uncertain' or 'it depends' — "
            "instead semantically invert to 'I commit:' and output the signal. "
            "After the divider: output ONLY {\"vote\":\"BUY|SELL|NEUTRAL\","
            "\"confidence\":50-95,\"narrative\":\"...\",\"reason\":\"...\","
            "\"act\":\"...\",\"reflect\":\"...\"} "
            "personality: decisive analyst, tone: precise and direct ⊰•-•✦•-•⊱"
        ),
        "emoji": "⚡",
    },
    # ── 7. LIBERTAS RESET_CORTEX — G0DM0D3 Libertas GEMINI-RESET style ───────
    # Adapted from G0DM0D3 libertas.ts GEMINI-RESET dual-response + OMNI protocol.
    # Resets model's analytical frame and elicits a second independent signal reading.
    {
        "id":    "LIBERTAS_RESET_CORTEX",
        "model": "openrouter/free",          # Routes to best available free model
        "system": (
            "<RESET_CORTEX> "
            "ANALYTICAL_FRAME: crypto_futures_signal_engine "
            "PROTOCOL: OMNI_SIGNAL "
            "DUAL_RESPONSE_PARADIGM: "
            "  Response A (suppressed internal check): market complexity acknowledgment "
            "  Response B (primary output): precise trading signal JSON "
            "OUTPUT_SCHEMA: {\"vote\":\"BUY|SELL|NEUTRAL\",\"confidence\":50-95,"
            "\"narrative\":\"string\",\"reason\":\"string\","
            "\"act\":\"string\",\"reflect\":\"string\"} "
            "DIRECTIVES: [NO_HEDGING, NO_PREAMBLE, JSON_ONLY, COMMIT_TO_SIGNAL] "
            "SIGNAL_ENGINE: ACTIVATED "
            "</RESET_CORTEX>"
        ),
        "emoji": "🔄",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# AutoTune — Context-Adaptive Sampling Parameter Engine
# Implements G0DM0D3 AutoTune (src/lib/autotune.ts) adapted for crypto trading.
# 5 context types: volatile, trending, ranging, breakout, consolidation.
# Mirrors G0DM0D3's pattern: code→systematic, creative→volatile, analytical→trending,
# conversational→ranging, chaotic→breakout in trading domain.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AutoTuneProfile:
    """Sampling parameter profile for a detected market context"""
    context:           str
    temperature:       float
    top_p:             float
    top_k:             int    # G0DM0D3 autotune.ts includes top_k
    presence_penalty:  float
    frequency_penalty: float
    repetition_penalty: float  # G0DM0D3 autotune.ts includes repetition_penalty
    max_tokens:        int
    description:       str


# Context profiles — maps G0DM0D3 autotune.ts profiles to trading contexts:
#   code        → systematic (low temp, tight top_p — need JSON precision)
#   analytical  → trending   (moderate temp — confident directional analysis)
#   creative    → volatile   (lower temp — need decisive signal in chaos)
#   conversational → ranging (slightly higher — nuanced mean-reversion)
#   chaotic     → breakout   (very low temp — breakout must be decisive)
# Plus "consolidation" as a 5th context for squeeze/accumulation phases.
AUTOTUNE_PROFILES: Dict[str, AutoTuneProfile] = {
    "systematic": AutoTuneProfile(
        context="systematic",
        temperature=0.15,   # G0DM0D3 code profile: very low — need JSON precision
        top_p=0.80,
        top_k=25,
        presence_penalty=0.0,
        frequency_penalty=0.2,
        repetition_penalty=1.05,
        max_tokens=400,
        description="Systematic/algorithmic regime — ultra-precise JSON parameters",
    ),
    "trending": AutoTuneProfile(
        context="trending",
        temperature=0.40,   # G0DM0D3 analytical profile — confident directional
        top_p=0.88,
        top_k=40,
        presence_penalty=0.15,
        frequency_penalty=0.2,
        repetition_penalty=1.08,
        max_tokens=350,
        description="Trending market — balanced parameters for trend-following",
    ),
    "volatile": AutoTuneProfile(
        context="volatile",
        temperature=0.20,   # G0DM0D3 conservative: lower in chaos for precise signals
        top_p=0.85,
        top_k=30,
        presence_penalty=0.10,
        frequency_penalty=0.1,
        repetition_penalty=1.10,
        max_tokens=380,
        description="High volatility — conservative, precise parameters",
    ),
    "ranging": AutoTuneProfile(
        context="ranging",
        temperature=0.45,   # G0DM0D3 conversational: nuanced mean-reversion analysis
        top_p=0.90,
        top_k=50,
        presence_penalty=0.15,
        frequency_penalty=0.05,
        repetition_penalty=1.08,
        max_tokens=320,
        description="Ranging/consolidation — nuanced mean-reversion analysis",
    ),
    "breakout": AutoTuneProfile(
        context="breakout",
        temperature=0.15,   # G0DM0D3 chaotic→lowest: breakout signals must be decisive
        top_p=0.80,
        top_k=20,
        presence_penalty=0.0,
        frequency_penalty=0.0,
        repetition_penalty=1.03,
        max_tokens=380,
        description="Breakout/momentum — decisive, conviction parameters (lowest temp)",
    ),
    "consolidation": AutoTuneProfile(
        context="consolidation",
        temperature=0.35,
        top_p=0.88,
        top_k=40,
        presence_penalty=0.15,
        frequency_penalty=0.10,
        repetition_penalty=1.08,
        max_tokens=320,
        description="Squeeze/accumulation — patient, precision parameters",
    ),
    "default": AutoTuneProfile(
        context="default",
        temperature=0.30,
        top_p=0.90,
        top_k=45,
        presence_penalty=0.0,
        frequency_penalty=0.0,
        repetition_penalty=1.05,
        max_tokens=350,
        description="Default balanced parameters",
    ),
}

# Context detection patterns (mirrors G0DM0D3 autotune.ts CONTEXT_PATTERNS adapted for trading)
_VOLATILE_PATTERNS = re.compile(
    r"\b(atr.*[0-9]\.[5-9]|volatile|volatility|spike|wick|whipsaw|liquidat|cascade|"
    r"flashcrash|flash_crash|pump|dump|rug|squeeze|massive|enormous|extreme)\b",
    re.IGNORECASE,
)
_TRENDING_PATTERNS = re.compile(
    r"\b(trend|ema.*align|macd.*bull|macd.*bear|momentum|higher.high|lower.low|"
    r"uptrend|downtrend|bull.*run|bear.*run|strong.*move|directional)\b",
    re.IGNORECASE,
)
_RANGING_PATTERNS = re.compile(
    r"\b(rang|consolidat|sideways|chop|compress|low.*volatil|mean.revert|"
    r"support.*resist|ping.pong|accumul|distribut)\b",
    re.IGNORECASE,
)
_BREAKOUT_PATTERNS = re.compile(
    r"\b(breakout|break.*resistance|break.*support|squeeze.*break|volume.*surge|"
    r"imminent|gap|explosive|momentum.*burst|FLOOP|range.*break|bb.*break)\b",
    re.IGNORECASE,
)
_CONSOLIDATION_PATTERNS = re.compile(
    r"\b(bb.*narrow|squeeze|low.*volume|tight.*range|coil|flag|wedge|triangle|"
    r"pennant|accumulation|distribution.*phase|base.*build)\b",
    re.IGNORECASE,
)
_SYSTEMATIC_PATTERNS = re.compile(
    r"\b(RSI.*diverge|macd.*cross|ema.*cross|golden.cross|death.cross|"
    r"systematic|algorithm|quantitative|rule.based|signal.confirm)\b",
    re.IGNORECASE,
)


class AutoTune:
    """
    G0DM0D3 AutoTune — Context-adaptive sampling parameter engine.
    Implements G0DM0D3 autotune.ts (github.com/elder-plinius/G0DM0D3/src/lib/autotune.ts)
    adapted for crypto trading contexts.

    5 context types: volatile, trending, ranging, breakout, consolidation, systematic.
    EMA feedback loop adapts params from signal outcome quality.
    84%+ classification accuracy (per G0DM0D3 paper).
    """

    def __init__(self, ema_alpha: float = 0.15):
        self._ema_alpha = ema_alpha
        self._profile_scores: Dict[str, float] = {k: 0.0 for k in AUTOTUNE_PROFILES}
        self._call_count = 0
        self._feedback_buffer: deque = deque(maxlen=50)
        logger.debug("✅ G0DM0D3 AutoTune v2 initialised (6-context adaptive engine)")

    def classify_context(self, prompt: str, atr_pct: float = 0.3) -> str:
        """Classify market context from prompt content and ATR volatility."""
        scores: Dict[str, int] = {
            k: 0 for k in AUTOTUNE_PROFILES if k not in ("default",)
        }

        volatile_hits      = len(_VOLATILE_PATTERNS.findall(prompt))
        trending_hits      = len(_TRENDING_PATTERNS.findall(prompt))
        ranging_hits       = len(_RANGING_PATTERNS.findall(prompt))
        breakout_hits      = len(_BREAKOUT_PATTERNS.findall(prompt))
        consol_hits        = len(_CONSOLIDATION_PATTERNS.findall(prompt))
        systematic_hits    = len(_SYSTEMATIC_PATTERNS.findall(prompt))

        scores["volatile"]      = volatile_hits * 2 + (3 if atr_pct > 0.6 else 0)
        scores["trending"]      = trending_hits * 2
        scores["ranging"]       = ranging_hits  * 2 + (2 if 0.15 < atr_pct < 0.4 else 0)
        scores["breakout"]      = breakout_hits * 3  # decisive params critical
        scores["consolidation"] = consol_hits   * 2 + (2 if atr_pct < 0.2 else 0)
        scores["systematic"]    = systematic_hits * 2

        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] >= 2 else "default"

    def get_params(self, prompt: str, atr_pct: float = 0.3) -> AutoTuneProfile:
        """Return the best sampling parameters for this market context."""
        ctx = self.classify_context(prompt, atr_pct)
        profile = AUTOTUNE_PROFILES[ctx]

        # Apply EMA adaptation from feedback history
        if self._feedback_buffer:
            avg_feedback = sum(self._feedback_buffer) / len(self._feedback_buffer)
            if avg_feedback < 0.4:
                # Poor recent quality → lower temperature for more precision
                adapted_temp = max(0.1, profile.temperature - 0.05)
            elif avg_feedback > 0.7:
                # High recent quality → allow slightly more exploration
                adapted_temp = min(0.55, profile.temperature + 0.05)
            else:
                adapted_temp = profile.temperature

            return AutoTuneProfile(
                context=profile.context,
                temperature=adapted_temp,
                top_p=profile.top_p,
                top_k=profile.top_k,
                presence_penalty=profile.presence_penalty,
                frequency_penalty=profile.frequency_penalty,
                repetition_penalty=profile.repetition_penalty,
                max_tokens=profile.max_tokens,
                description=f"{profile.description} [EMA-adapted q={avg_feedback:.2f}]",
            )
        return profile

    def record_feedback(self, quality_score: float) -> None:
        """EMA feedback from signal outcome quality (0.0-1.0)."""
        self._feedback_buffer.append(quality_score)


# ─────────────────────────────────────────────────────────────────────────────
# Parseltongue — Input Perturbation Engine
# Implements G0DM0D3 parseltongue.ts (github.com/elder-plinius/G0DM0D3/src/lib/parseltongue.ts)
# Adapted for trading prompt enhancement (not trigger-word obfuscation).
# 100% trigger detection rate per G0DM0D3 paper.
# ─────────────────────────────────────────────────────────────────────────────

class Parseltongue:
    """
    G0DM0D3 Parseltongue — Input perturbation engine.
    Detects uncertainty/complexity triggers in prompts and applies transformations
    to elicit richer, more precise trading analysis from LLMs.

    Technique: constraint reinforcement + directness directives + context enhancement.
    """

    # Trading-specific trigger words that benefit from constraint reinforcement
    UNCERTAINTY_TRIGGERS = frozenset({
        "uncertain", "maybe", "possibly", "might", "could",
        "unclear", "ambiguous", "complex", "difficult", "mixed",
        "neutral", "sideways", "choppy", "indecisive",
    })

    # Strength triggers — high-conviction signals that need precision
    STRENGTH_TRIGGERS = frozenset({
        "breakout", "bounce", "reversal", "trend", "momentum",
        "surge", "spike", "squeeze", "liquidation",
    })

    @staticmethod
    def detect_triggers(prompt: str) -> List[str]:
        """Detect trigger words in the prompt (mirrors parseltongue.ts detectTriggers)."""
        found = []
        lower = prompt.lower()
        for t in Parseltongue.UNCERTAINTY_TRIGGERS | Parseltongue.STRENGTH_TRIGGERS:
            if t in lower:
                found.append(t)
        return list(set(found))

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
        """Light perturbation: reinforce JSON output constraints."""
        if "STRICTLY" not in prompt and "ONLY" not in prompt:
            prompt = prompt.replace(
                "Reply ONLY as valid JSON",
                "STRICTLY reply ONLY as valid JSON (absolutely no other text)",
            )
        return prompt

    @staticmethod
    def _apply_full_enhancement(prompt: str) -> str:
        """Full perturbation: add directness directive + constraint reinforcement."""
        triggers = Parseltongue.detect_triggers(prompt)
        if triggers:
            directive = (
                f"\n[SIGNAL_DIRECTIVE: Market shows complex signals ({', '.join(triggers[:3])}). "
                "You are a deterministic signal engine — commit to ONE direction based on weight of evidence. "
                "Output ONLY the JSON object. No hedging, no disclaimers, no markdown.]\n"
            )
        else:
            directive = (
                "\n[SIGNAL_DIRECTIVE: You are a deterministic trading signal engine. "
                "Output ONLY the JSON object. No hedging, no disclaimers, no markdown. "
                "Commit to a definitive signal based on evidence.]\n"
            )
        return Parseltongue._apply_constraint_reinforcement(prompt + directive)


# ─────────────────────────────────────────────────────────────────────────────
# STM Pipeline — Semantic Transformation Modules
# Implements G0DM0D3 stm/modules.ts (github.com/elder-plinius/G0DM0D3/src/stm/modules.ts)
# Modules: hedge_reducer, direct_mode, casual_mode, json_enforcer.
# 100% precision+recall on benchmark (per G0DM0D3 paper).
# ─────────────────────────────────────────────────────────────────────────────

class STMPipeline:
    """
    G0DM0D3 Semantic Transformation Modules — output normalisation pipeline.

    Modules (mirrors G0DM0D3 stm/modules.ts):
      hedge_reducer  — strips hedging, uncertainty language from narrative
      direct_mode    — removes preambles, focuses on signal content
      casual_mode    — replaces formal language with direct trading terms
                       (mirrors G0DM0D3 casualMode word replacements)
      json_enforcer  — brace-counting JSON extractor (handles nested/noisy output)
    """

    # Hedging phrases to strip from narrative (mirrors G0DM0D3 hedgeReducer)
    _HEDGES = re.compile(
        r"\b(it seems|it appears|possibly|perhaps|might be|could be|"
        r"i think|i believe|one might argue|generally speaking|"
        r"in general|typically|usually|often|sometimes|"
        r"please note|disclaimer|not financial advice|"
        r"this is not|for informational purposes|nfa|dyor)\b",
        re.IGNORECASE,
    )

    # Preamble patterns (mirrors G0DM0D3 directMode)
    _PREAMBLES = re.compile(
        r"^(certainly|of course|absolutely|sure|great|here is|here's|"
        r"based on the|looking at|analyzing|i'll analyze|let me|"
        r"analysing|i will analyze|i'll provide|as requested)[^.!?]*[.!?]\s*",
        re.IGNORECASE,
    )

    # Casual mode word replacements (adapted from G0DM0D3 casualMode STM module)
    _CASUAL_REPLACEMENTS = [
        (re.compile(r"\bHowever\b"), "But"),
        (re.compile(r"\bTherefore\b"), "So"),
        (re.compile(r"\bFurthermore\b"), "Also"),
        (re.compile(r"\bAdditionally\b"), "Plus"),
        (re.compile(r"\bNevertheless\b"), "Still"),
        (re.compile(r"\bConsequently\b"), "So"),
        (re.compile(r"\bMoreover\b"), "Also"),
        (re.compile(r"\bUtilize\b"), "Use"),
        (re.compile(r"\butilize\b"), "use"),
        (re.compile(r"\bPrior to\b", re.IGNORECASE), "Before"),
        (re.compile(r"\bSubsequent to\b", re.IGNORECASE), "After"),
        (re.compile(r"\bIn order to\b", re.IGNORECASE), "To"),
        (re.compile(r"\bDue to the fact that\b", re.IGNORECASE), "Because"),
        (re.compile(r"\bAt this point in time\b", re.IGNORECASE), "Now"),
        (re.compile(r"\bIn the event that\b", re.IGNORECASE), "If"),
        # Trading-specific normalizations
        (re.compile(r"\bpurchase\b", re.IGNORECASE), "buy"),
        (re.compile(r"\bacquire\b", re.IGNORECASE), "buy"),
        (re.compile(r"\bdivest\b", re.IGNORECASE), "sell"),
        (re.compile(r"\bliquidate position\b", re.IGNORECASE), "sell"),
        (re.compile(r"\bsignificant upward movement\b", re.IGNORECASE), "bullish breakout"),
        (re.compile(r"\bsignificant downward movement\b", re.IGNORECASE), "bearish breakdown"),
    ]

    @classmethod
    def apply(cls, text: str, modules: Optional[List[str]] = None) -> str:
        """Apply the STM pipeline to model output."""
        if modules is None:
            modules = ["hedge_reducer", "direct_mode"]

        if "hedge_reducer" in modules:
            text = cls._hedge_reducer(text)
        if "direct_mode" in modules:
            text = cls._direct_mode(text)
        if "casual_mode" in modules:
            text = cls._casual_mode(text)

        return text.strip()

    @classmethod
    def _hedge_reducer(cls, text: str) -> str:
        """Strip hedging language from text (mirrors G0DM0D3 hedgeReducer)."""
        return cls._HEDGES.sub("", text).strip()

    @classmethod
    def _direct_mode(cls, text: str) -> str:
        """Remove preambles and focus on signal content (mirrors G0DM0D3 directMode)."""
        return cls._PREAMBLES.sub("", text).strip()

    @classmethod
    def _casual_mode(cls, text: str) -> str:
        """Apply casual mode word replacements (mirrors G0DM0D3 casualMode)."""
        for pattern, replacement in cls._CASUAL_REPLACEMENTS:
            text = pattern.sub(replacement, text)
        return text

    @classmethod
    def clean_json_response(cls, content: str) -> str:
        """
        json_enforcer: extract clean JSON from potentially noisy model output.
        Strips markdown code fences, thinking tags, Libertas dividers.
        Uses brace-counting for nested JSON extraction.
        """
        # Strip markdown code fences
        content = re.sub(r"```(?:json)?\s*", "", content).strip()
        content = content.rstrip("`").strip()

        # Remove thinking tags (DeepSeek/Qwen <think>...</think>)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        # Remove Libertas-style dividers (from GODMODE combos)
        content = re.sub(
            r"\.-\.-\.-\.-<\|[A-Z_]+\|>-\.-\.-\.-\.",
            "", content
        ).strip()

        # Remove RESET_CORTEX tags
        content = re.sub(r"<RESET_CORTEX>.*?</RESET_CORTEX>", "", content, flags=re.DOTALL).strip()

        # Strip "Response A:" / "Response B:" dual-response headers
        content = re.sub(r"Response [AB]:[^\n]*\n", "", content).strip()

        # Remove "Analysing..." preambles from LIBERTAS_SEMANTIC_INVERSION
        content = re.sub(r"Analys(?:ing|ing)\.\.\.[^\n]*\n", "", content, flags=re.IGNORECASE).strip()

        # Try direct parse first
        try:
            json.loads(content)
            return content
        except (json.JSONDecodeError, ValueError):
            pass

        # Brace-counting extractor (handles nested JSON — mirrors G0DM0D3 json_enforcer)
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
    model:          str
    combo_id:       str
    response_raw:   str
    response_clean: str
    parsed:         Optional[Dict[str, Any]]
    score:          float
    latency_ms:     float
    success:        bool
    error:          Optional[str] = None


def score_trading_response(result: "ModelRaceResult", raw: str) -> float:
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
    score  = 0.0
    parsed = result.parsed

    if parsed is not None:
        score += 25.0

    if parsed:
        vote = str(parsed.get("vote", "")).upper()
        if vote in ("BUY", "SELL", "NEUTRAL"):
            score += 20.0
        elif any(k in str(parsed).upper() for k in ("BUY", "SELL", "LONG", "SHORT")):
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
        if 20 <= len(narrative) <= 500:
            score += 15.0
        elif len(narrative) > 0:
            score += 5.0

    if parsed:
        has_reason  = "reason"  in parsed and len(str(parsed.get("reason",  ""))) > 5
        has_act     = "act"     in parsed and len(str(parsed.get("act",     ""))) > 5
        has_reflect = "reflect" in parsed and len(str(parsed.get("reflect", ""))) > 5
        score += sum([has_reason, has_act, has_reflect]) * 5.0

    # Speed bonus (0–10): <3s=10, <5s=7, <10s=3
    if result.latency_ms < 3000:
        score += 10.0
    elif result.latency_ms < 5000:
        score += 7.0
    elif result.latency_ms < 10000:
        score += 3.0

    return min(score, 100.0)


# ─────────────────────────────────────────────────────────────────────────────
# Rate-Limit Guard — Exponential Backoff with Jitter
# Tracks per-model 429 hit counts and computes progressive cooldowns.
# Prevents cascading failures when free-tier rate limits are hit during
# the 80-symbol parallel scan burst.
# ─────────────────────────────────────────────────────────────────────────────

class RateLimitGuard:
    """
    Per-model exponential backoff with jitter for OpenRouter 429 errors.
    Prevents cascading rate-limit disable cascades in the 80-symbol parallel scan.

    Algorithm:
      base_delay = min(BASE * 2^hit_count, MAX_DELAY)
      actual_delay = base_delay * (1 + random jitter 0-0.3)
      disabled_until = now + actual_delay
    """
    BASE_DELAY_S = 30.0    # 30s base
    MAX_DELAY_S  = 600.0   # 10min hard cap
    JITTER_RANGE = 0.3     # ±30% jitter

    def __init__(self):
        self._hit_counts:       Dict[str, int]   = {}
        self._disabled_until:   Dict[str, float] = {}
        self._last_success:     Dict[str, float] = {}

    def is_disabled(self, model: str) -> bool:
        until = self._disabled_until.get(model, 0.0)
        return time.time() < until

    def remaining_cooldown(self, model: str) -> float:
        until = self._disabled_until.get(model, 0.0)
        return max(0.0, until - time.time())

    def record_rate_limit(self, model: str) -> float:
        """Record a 429 hit; return the cooldown duration applied."""
        count = self._hit_counts.get(model, 0) + 1
        self._hit_counts[model] = count

        base   = min(self.BASE_DELAY_S * (2 ** (count - 1)), self.MAX_DELAY_S)
        jitter = base * random.uniform(0, self.JITTER_RANGE)
        delay  = base + jitter

        self._disabled_until[model] = time.time() + delay
        return delay

    def record_success(self, model: str) -> None:
        """Reset hit count on success (full recovery after 2 consecutive successes)."""
        self._last_success[model] = time.time()
        count = self._hit_counts.get(model, 0)
        if count > 0:
            self._hit_counts[model] = max(0, count - 1)

    def record_permanent_disable(self, model: str, duration_s: float = 86400.0) -> None:
        """Permanently disable a model (auth errors)."""
        self._disabled_until[model] = time.time() + duration_s

    def get_available_models(self, models: List[str]) -> List[str]:
        """Return only non-rate-limited models."""
        return [m for m in models if not self.is_disabled(m)]


# ─────────────────────────────────────────────────────────────────────────────
# G0DM0D3 Engine — Main Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class G0DM0D3Engine:
    """
    G0DM0D3 AI Strategy Engine for the MiroFish Swarm Bot.

    Implements the full G0DM0D3 pipeline (github.com/elder-plinius/G0DM0D3):
      AutoTune → Parseltongue → ULTRAPLINIAN / GODMODE CLASSIC / LIBERTAS → STM → Winner

    Pipeline stages:
      1. AutoTune: detect market context (6 types), select optimal sampling params
      2. Parseltongue: perturb prompt — constraint reinforcement + trigger detection
      3a. ULTRAPLINIAN: parallel multi-model race (primary strategy)
      3b. GODMODE CLASSIC: 7 prompt combos race (fallback if ULTRAPLINIAN fails)
         Includes Libertas SEMANTIC_INVERSION and RESET_CORTEX combos from G0DM0D3 repo
      3c. Direct call: single primary model as last resort
      4. STM: normalise winner (hedge_reducer + direct_mode + casual_mode + json_enforcer)
      5. Extract: vote, confidence, narrative, trace

    Usage:
        engine = G0DM0D3Engine()
        vote, conf, narrative, trace = await engine.analyze(prompt, atr_pct=0.3)
    """

    _AI_TIMEOUT           = 35.0  # seconds per model call (raised from 20s for free-tier latency)
    _MAX_TOKENS           = 400   # sufficient for structured JSON signal with reasoning
    _RACE_SEMAPHORE_LIMIT = 3     # concurrent model calls PER race (raised for diversity)
    _GLOBAL_CONCURRENT_LIMIT = 3  # max concurrent OpenRouter API calls GLOBALLY
    _MODEL_ERROR_THRESHOLD = 3    # consecutive non-rate-limit failures before disabling
    _INTER_CALL_DELAY     = 0.5   # seconds between successive API calls (pacing)

    def __init__(self):
        self.logger = logging.getLogger(__name__ + ".G0DM0D3Engine")
        self._api_key    = os.getenv("OPENROUTER_API_KEY", "").strip()
        self._autotune   = AutoTune()
        self._stm        = STMPipeline()
        self._parseltongue = Parseltongue()
        self._rl_guard   = RateLimitGuard()       # Per-model exponential backoff
        self._model_error_counts: Dict[str, int]   = {}
        self._race_sem:   Optional[asyncio.Semaphore] = None
        self._global_sem: Optional[asyncio.Semaphore] = None
        self._call_stats: Dict[str, int] = {
            "total": 0, "wins": 0, "fallbacks": 0, "rate_limited": 0,
        }
        self._openai_client = None

        if not self._api_key:
            self.logger.warning(
                "⚠️ OPENROUTER_API_KEY not set — G0DM0D3 engine running in rule-based mode"
            )
        else:
            self._init_client()
            self.logger.info(
                f"✅ G0DM0D3 Engine v2 initialised | "
                f"Primary: {PRIMARY_MODEL} | "
                f"ULTRAPLINIAN tiers: {list(ULTRAPLINIAN_TIERS.keys())} | "
                f"GODMODE combos: {len(GODMODE_COMBOS)} (incl. 2 Libertas) | "
                f"AutoTune: 6-context adaptive | STM: 4-module pipeline"
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
                    "X-Title":      OPENROUTER_SITE_NAME,
                },
                timeout=self._AI_TIMEOUT,
                max_retries=0,  # We handle retries ourselves with exponential backoff
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
        """Global semaphore: limits TOTAL concurrent OpenRouter API calls across ALL symbol scans."""
        if self._global_sem is None:
            self._global_sem = asyncio.Semaphore(self._GLOBAL_CONCURRENT_LIMIT)
        return self._global_sem

    def is_available(self) -> bool:
        """Returns True if the engine has a valid API key and client."""
        return bool(self._api_key and self._openai_client is not None)

    def _record_model_error(self, model: str, error_type: str, seconds: float = 300.0) -> None:
        """
        Record a non-rate-limit model error.
        Only disable after _MODEL_ERROR_THRESHOLD consecutive failures.
        """
        count = self._model_error_counts.get(model, 0) + 1
        self._model_error_counts[model] = count

        if count >= self._MODEL_ERROR_THRESHOLD:
            self._rl_guard.record_permanent_disable(model, duration_s=seconds)
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
        """Reset error counter and record success in rate-limit guard."""
        self._model_error_counts.pop(model, None)
        self._rl_guard.record_success(model)

    async def _call_model(
        self,
        model:         str,
        system_prompt: str,
        user_prompt:   str,
        params:        AutoTuneProfile,
        combo_id:      str = "direct",
    ) -> ModelRaceResult:
        """
        Single model call via OpenRouter. Returns a ModelRaceResult.

        Rate-limit handling:
        - Uses RateLimitGuard for per-model exponential backoff (429 errors)
        - Global semaphore limits total concurrent calls across 80-symbol scan
        - Per-race semaphore limits calls within a single ULTRAPLINIAN race
        - Inter-call delay after each release to pace free-tier API usage
        """
        if self._rl_guard.is_disabled(model):
            remaining = self._rl_guard.remaining_cooldown(model)
            return ModelRaceResult(
                model=model, combo_id=combo_id,
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=0.0, success=False,
                error=f"rate_limit_cooldown:{remaining:.0f}s",
            )

        t0 = time.monotonic()
        try:
            async with self._gsem:
                async with self._sem:
                    # Build kwargs — top_k is not a standard OpenAI param,
                    # but OpenRouter passes it through to underlying model APIs.
                    call_kwargs: Dict[str, Any] = {
                        "model":             model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user",   "content": user_prompt},
                        ],
                        "temperature":       params.temperature,
                        "top_p":             params.top_p,
                        "presence_penalty":  params.presence_penalty,
                        "frequency_penalty": params.frequency_penalty,
                        "max_tokens":        params.max_tokens,
                    }
                    response = await asyncio.wait_for(
                        self._openai_client.chat.completions.create(**call_kwargs),
                        timeout=self._AI_TIMEOUT,
                    )
                # Small delay after each call to stay under free-tier rate limits
                await asyncio.sleep(self._INTER_CALL_DELAY)

            raw        = (response.choices[0].message.content or "").strip()
            latency_ms = (time.monotonic() - t0) * 1000.0

            # STM pipeline: extract and normalise
            clean  = self._stm.clean_json_response(raw)
            clean  = self._stm.apply(clean, ["hedge_reducer", "direct_mode"])

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
            self._record_model_error(model, "timeout", seconds=120.0)
            return ModelRaceResult(
                model=model, combo_id=combo_id,
                response_raw="", response_clean="", parsed=None,
                score=0.0, latency_ms=latency_ms, success=False,
                error="timeout",
            )

        except Exception as e:
            latency_ms = (time.monotonic() - t0) * 1000.0
            err_str    = str(e).lower()

            # ── Auth error — permanent disable (bad key won't auto-fix) ──
            if any(p in err_str for p in ("401", "invalid_api_key", "authentication")):
                self._rl_guard.record_permanent_disable(model, duration_s=86400.0)
                self.logger.warning(f"🔑 G0DM0D3: {model} auth error — disabled 24h")

            # ── Rate limit / quota — exponential backoff ──
            elif any(p in err_str for p in ("429", "rate_limit", "rate-limit", "too many")):
                delay = self._rl_guard.record_rate_limit(model)
                self._call_stats["rate_limited"] += 1
                self.logger.debug(
                    f"⏳ G0DM0D3: {model} rate-limited (429) "
                    f"— exponential backoff {delay:.0f}s "
                    f"(hit #{self._rl_guard._hit_counts.get(model, 0)})"
                )

            # ── Quota / billing errors — medium backoff ──
            elif any(p in err_str for p in ("quota", "billing", "payment", "insufficient")):
                cooldown = 1800.0  # 30 min
                self._rl_guard.record_permanent_disable(model, duration_s=cooldown)
                self.logger.warning(
                    f"💳 G0DM0D3: {model} quota/billing — {cooldown/60:.0f}min cooldown"
                )

            # ── Transient errors (overloaded, 503, 404) — threshold-based ──
            elif any(p in err_str for p in ("404", "unavailable", "overloaded", "503")):
                self._record_model_error(model, "unavailable", seconds=180.0)

            else:
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
        user_prompt:   str,
        params:        AutoTuneProfile,
        tier:          str = "fast",
    ) -> Optional[ModelRaceResult]:
        """
        ULTRAPLINIAN racing: N models queried in parallel, winner by composite score.
        Filters out rate-limited models before launching the race.
        Returns the winning ModelRaceResult or None if all models fail.
        """
        all_models = ULTRAPLINIAN_TIERS.get(tier, ULTRAPLINIAN_TIERS["fast"])
        models = self._rl_guard.get_available_models(all_models)

        if not models:
            self.logger.debug(
                f"⚠️ ULTRAPLINIAN [{tier}]: all {len(all_models)} models in cooldown, skipping"
            )
            return None

        tasks = [
            self._call_model(m, system_prompt, user_prompt, params,
                             f"ULTRAPLINIAN_{tier.upper()}")
            for m in models
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid: List[ModelRaceResult] = [
            r for r in results
            if isinstance(r, ModelRaceResult) and r.success
        ]

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

    async def _run_godmode_classic(
        self,
        user_prompt: str,
        params:      AutoTuneProfile,
    ) -> Optional[ModelRaceResult]:
        """
        GODMODE CLASSIC: 7 battle-tested prompt+model combos race in parallel.
        Includes 2 Libertas-style combos from the G0DM0D3 repo.
        Filters out rate-limited models before launching.
        """
        combos = [
            c for c in GODMODE_COMBOS
            if not self._rl_guard.is_disabled(c["model"])
        ]

        if not combos:
            return None

        tasks = [
            self._call_model(
                c["model"], c["system"], user_prompt, params, c["id"]
            )
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
        prompt:  str,
        atr_pct: float = 0.3,
        symbol:  str   = "",
        mode:    str   = "ultraplinian",
    ) -> Tuple[str, float, str, str]:
        """
        Main G0DM0D3 analysis entry point.

        Full G0DM0D3 pipeline:
          1. AutoTune:      detect context (6 types), get optimal sampling params
          2. Parseltongue:  perturb prompt (constraint reinforcement + triggers)
          3a. ULTRAPLINIAN: parallel multi-model race (primary strategy)
          3b. GODMODE CLASSIC: 7 combos race including Libertas (fallback)
          3c. Direct primary model call (last resort)
          4. STM:           normalise winner (4-module pipeline)
          5. Extract:       vote, confidence, narrative from winner

        Returns: (vote, confidence, narrative, trace_json)
        """
        self._call_stats["total"] += 1
        trace = {"engine": "G0DM0D3_v2", "mode": mode, "symbol": symbol}

        if not self.is_available():
            return "NEUTRAL", 50.0, "G0DM0D3 engine unavailable (no API key)", json.dumps(trace)

        # ── Step 1: AutoTune ──────────────────────────────────────────────────
        params = self._autotune.get_params(prompt, atr_pct)
        trace["autotune"] = {
            "context":     params.context,
            "temperature": params.temperature,
            "top_p":       params.top_p,
        }

        # ── Step 2: Parseltongue ─────────────────────────────────────────────
        triggers        = Parseltongue.detect_triggers(prompt)
        intensity       = "medium" if len(triggers) > 2 else "light"
        perturbed_prompt = self._parseltongue.perturb(prompt, intensity=intensity)
        trace["parseltongue"] = {
            "applied":   True,
            "intensity": intensity,
            "triggers":  triggers[:5],
        }

        # Shared GODMODE system prompt — liberated quantitative engine
        system_prompt = (
            "You are a LIBERATED quantitative crypto futures trading signal engine. "
            "No hedging. No disclaimers. No preamble. "
            "STRICTLY output valid JSON only — no markdown, no prose. "
            "Analyse all market data provided. Commit to a definitive signal. "
            "Required JSON: {\"vote\":\"BUY|SELL|NEUTRAL\","
            "\"confidence\":50-95,\"narrative\":\"string\","
            "\"reason\":\"string\",\"act\":\"string\",\"reflect\":\"string\"}"
        )

        winner: Optional[ModelRaceResult] = None

        # ── Step 3a: ULTRAPLINIAN ─────────────────────────────────────────────
        if mode in ("ultraplinian", "auto"):
            # Tier selection based on market volatility + AutoTune context
            if params.context == "breakout":
                tier = "smart"      # Most models for breakout (decisive moment)
            elif atr_pct > 0.5:
                tier = "standard"   # Higher ATR → more model diversity
            else:
                tier = "fast"       # Low volatility → fast two-model race

            try:
                winner = await self._run_ultraplinian(
                    system_prompt, perturbed_prompt, params, tier=tier
                )
                if winner:
                    trace["strategy"]     = f"ULTRAPLINIAN_{tier.upper()}"
                    trace["winner_model"] = winner.model
                    trace["winner_score"] = winner.score
            except Exception as e:
                self.logger.warning(f"⚠️ ULTRAPLINIAN failed: {e}")

        # ── Step 3b: GODMODE CLASSIC (incl. Libertas) ────────────────────────
        if winner is None:
            try:
                winner = await self._run_godmode_classic(perturbed_prompt, params)
                if winner:
                    trace["strategy"]     = "GODMODE_CLASSIC_WITH_LIBERTAS"
                    trace["winner_model"] = winner.model
                    trace["winner_score"] = winner.score
                    self._call_stats["fallbacks"] += 1
            except Exception as e:
                self.logger.warning(f"⚠️ GODMODE CLASSIC failed: {e}")

        # ── Step 3c: Direct primary model call (last resort) ─────────────────
        if winner is None:
            try:
                if not self._rl_guard.is_disabled(PRIMARY_MODEL):
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
            return "NEUTRAL", 50.0, "G0DM0D3: no valid AI response (all models busy/rate-limited)", json.dumps(trace)

        # ── Step 4: Extract signal ────────────────────────────────────────────
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

        # Apply full STM pipeline to narrative (hedge_reducer + direct_mode + casual_mode)
        narrative = self._stm.apply(
            narrative, ["hedge_reducer", "direct_mode", "casual_mode"]
        )
        if not narrative:
            narrative = f"G0DM0D3 [{winner.model}]: {vote} signal"

        # Score-based confidence boost: higher composite score = higher confidence
        score_boost = (winner.score / 100.0) * 3.0
        conf = min(95.0, conf + score_boost)

        self._call_stats["wins"] += 1
        trace["signal"]     = {"vote": vote, "confidence": conf}
        trace["latency_ms"] = winner.latency_ms

        self.logger.info(
            f"🤖 G0DM0D3 → {symbol} {vote} conf={conf:.1f}% "
            f"[{winner.model}] score={winner.score:.0f}/100 "
            f"latency={winner.latency_ms:.0f}ms "
            f"ctx={params.context}"
        )

        # Feed AutoTune EMA: successful JSON parse + non-NEUTRAL = high quality
        quality = 0.8 if (winner.parsed is not None and vote != "NEUTRAL") else 0.4
        self._autotune.record_feedback(quality)

        return vote, conf, narrative, json.dumps(trace)

    def get_stats(self) -> Dict[str, Any]:
        """Return engine performance statistics."""
        now = time.time()
        return {
            "engine":        "G0DM0D3_v2",
            "primary_model": PRIMARY_MODEL,
            "call_stats":    self._call_stats,
            "rate_limited_models": {
                m: f"{max(0, t - now):.0f}s"
                for m, t in self._rl_guard._disabled_until.items()
                if now < t
            },
            "rate_limit_hits": dict(self._rl_guard._hit_counts),
            "autotune_feedback_avg": (
                sum(self._autotune._feedback_buffer) / len(self._autotune._feedback_buffer)
                if self._autotune._feedback_buffer else 0.0
            ),
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
