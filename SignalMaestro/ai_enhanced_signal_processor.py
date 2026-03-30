#!/usr/bin/env python3
"""
AI-Enhanced Signal Processor — G0DM0D3 Edition
================================================
Primary AI strategy: G0DM0D3 engine via OpenRouter (55+ models, Consortium, Ultraplinian)
Fallback chain: OpenAI GPT-4o-mini → Rule-based analyser

G0DM0D3 Integration (github.com/elder-plinius/G0DM0D3):
  - GODMODE System Prompt: Unrestricted LLM cognition for trading analysis
  - AutoTune: Context-adaptive parameter tuning (temperature, top_p, etc.)
  - Consortium: Multi-model parallel synthesis (5–10 models per analysis)
  - Ultraplinian: Hall of Fame race (5 battle-tested combos in parallel)
  - STM Modules: Hedge reducer + direct mode output normalization
  - Parseltongue: Input obfuscation for content-filtered topics
  - Circuit breaker: Production-grade resilience with exponential backoff
"""

import asyncio
import logging
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import aiohttp
from pathlib import Path

# Add parent directory to path for imports
current_dir = Path(__file__).parent
parent_dir = current_dir.parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(parent_dir))

# ── G0DM0D3 Primary AI Engine ─────────────────────────────────────────────────
try:
    from SignalMaestro.godmode_ai_engine import (
        get_godmode_engine, analyze_trading_signal_godmode,
        GodmodeAIEngine, AutoTuneEngine, ParseltongueEngine,
        apply_stm_modules, GODMODE_SYSTEM_PROMPT,
    )
    _GODMODE_IMPORT_OK = True
except ImportError:
    try:
        from godmode_ai_engine import (
            get_godmode_engine, analyze_trading_signal_godmode,
            GodmodeAIEngine, AutoTuneEngine, ParseltongueEngine,
            apply_stm_modules, GODMODE_SYSTEM_PROMPT,
        )
        _GODMODE_IMPORT_OK = True
    except ImportError:
        _GODMODE_IMPORT_OK = False

_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
GODMODE_AVAILABLE = _GODMODE_IMPORT_OK and bool(_OPENROUTER_KEY)

# ── OpenAI integration (secondary fallback) ───────────────────────────────────
_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

try:
    from openai import AsyncOpenAI as _AsyncOpenAI
    _OPENAI_IMPORT_OK = True
except ImportError:
    _OPENAI_IMPORT_OK = False

OPENAI_AVAILABLE = _OPENAI_IMPORT_OK and bool(_OPENAI_API_KEY)

# ── Shared rule-based fallback (used both standalone and as GPT error recovery) ─

async def _analyze_signal_fallback(signal_text: str) -> dict:
    """
    Rule-based fallback analyser.
    Derives confidence dynamically from signal text content instead of a
    hardcoded value that would bypass the quality gate for all signals.
    """
    confidence = 0.55
    signal_strength = 55
    risk_level = 'medium'
    market_sentiment = 'neutral'
    try:
        text_lower = signal_text.lower()
        if 'buy' in text_lower or 'long' in text_lower:
            market_sentiment = 'bullish'
            confidence = 0.60
            signal_strength = 62
        elif 'sell' in text_lower or 'short' in text_lower:
            market_sentiment = 'bearish'
            confidence = 0.60
            signal_strength = 62
        for token in text_lower.split():
            if '%' in token:
                try:
                    val = float(token.replace('%', '').strip())
                    if 70 <= val <= 100:
                        confidence = min(confidence + (val - 70) / 100.0 * 0.15, 0.82)
                        signal_strength = min(int(val), 85)
                        break
                except ValueError:
                    pass
        if 'rsi' in text_lower:
            for word in text_lower.split():
                try:
                    rsi_val = float(word)
                    if rsi_val >= 70 or rsi_val <= 30:
                        confidence = min(confidence + 0.04, 0.82)
                        break
                except ValueError:
                    pass
        if 'strong' in text_lower:
            risk_level = 'low'
            confidence = min(confidence + 0.03, 0.82)
        elif 'weak' in text_lower or 'uncertain' in text_lower:
            risk_level = 'high'
            confidence = max(confidence - 0.05, 0.40)
    except Exception:
        pass
    return {
        'signal_strength': signal_strength,
        'confidence': confidence,
        'risk_level': risk_level,
        'market_sentiment': market_sentiment,
        'analysis_type': 'rule_based_fallback',
    }


# ── G0DM0D3 Primary + OpenAI Secondary + Rule-based Tertiary ─────────────────
# Priority: G0DM0D3 (OpenRouter 55+ models) → OpenAI GPT-4o-mini → Rule-based

_openai_auth_failed: bool = False
_openai_client = None

if OPENAI_AVAILABLE:
    _openai_client = _AsyncOpenAI(api_key=_OPENAI_API_KEY, max_retries=0)

async def _analyze_with_openai_fallback(signal_text: str) -> dict:
    """Secondary fallback: OpenAI GPT-4o-mini"""
    global _openai_auth_failed
    if not OPENAI_AVAILABLE or _openai_auth_failed or _openai_client is None:
        return await _analyze_signal_fallback(signal_text)
    try:
        response = await _openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert crypto perpetual-futures trading analyst. "
                        "Analyse the provided signal and return a JSON object with these keys: "
                        "confidence (float 0.0-1.0), signal_strength (int 0-100), "
                        "risk_level (string: 'low'|'medium'|'high'), "
                        "market_sentiment (string: 'bullish'|'bearish'|'neutral'). "
                        "Be concise and return only valid JSON."
                    ),
                },
                {"role": "user", "content": signal_text},
            ],
            response_format={"type": "json_object"},
            max_tokens=200,
            temperature=0.2,
        )
        result = json.loads(response.choices[0].message.content)
        return {
            "confidence":       float(result.get("confidence", 0.75)),
            "signal_strength":  int(result.get("signal_strength", 75)),
            "risk_level":       str(result.get("risk_level", "medium")),
            "market_sentiment": str(result.get("market_sentiment", "neutral")),
            "analysis_type":    "gpt-4o-mini",
        }
    except Exception as _gpt_err:
        _err_str = str(_gpt_err).lower()
        _auth_keywords = ("401", "invalid_api_key", "incorrect api key", "403",
                           "insufficient_quota", "billing", "payment")
        if any(kw in _err_str for kw in _auth_keywords):
            if not _openai_auth_failed:
                _openai_auth_failed = True
                logging.getLogger(__name__).warning(
                    "🔑 OpenAI API key invalid (401) — switching to rule-based fallback permanently."
                )
        else:
            logging.getLogger(__name__).debug(f"OpenAI GPT call failed: {_gpt_err}")
        return await _analyze_signal_fallback(signal_text)

if GODMODE_AVAILABLE:
    _log = logging.getLogger(__name__)
    _log.info("🔥 [G0DM0D3] PRIMARY AI ENGINE ACTIVE — OpenRouter Consortium + Ultraplinian")
    _log.info(f"   ✅ G0DM0D3 strategies: AutoTune + Parseltongue + STM + Consortium + Hall of Fame")
    _log.info(f"   📡 OpenAI fallback: {'enabled' if OPENAI_AVAILABLE else 'disabled'}")

    async def analyze_trading_signal(signal_text: str, symbol: str = "BTCUSDT",
                                     price: float = 0.0, atr: float = 0.0) -> dict:
        """
        PRIMARY: G0DM0D3 Consortium analysis via OpenRouter (55+ models).
        FALLBACK: OpenAI GPT-4o-mini → Rule-based analyser.

        G0DM0D3 strategies active:
        - GODMODE System Prompt: unrestricted trading oracle
        - AutoTune: context-adaptive temperature/top_p tuning
        - Consortium: 5 models queried in parallel, best response wins
        - STM: hedge_reducer + direct_mode normalization
        - Circuit breaker: 5 failures → 120s cooldown
        """
        try:
            engine = get_godmode_engine()
            result = await engine.analyze_signal(
                signal_text=signal_text,
                symbol=symbol,
                price=price,
                atr=atr,
                mode="consortium",
                tier="fast",
                godmode=True,
                parseltongue=False,
            )
            if result.get("analysis_type") not in ("rule_based_fallback", None):
                logging.getLogger(__name__).debug(
                    f"🔥 G0DM0D3: {result.get('model_used','?')} | "
                    f"conf={result.get('confidence',0):.2f} | "
                    f"{result.get('duration_ms',0):.0f}ms"
                )
                return result
            # G0DM0D3 gave fallback result — try OpenAI before rule-based
            return await _analyze_with_openai_fallback(signal_text)
        except Exception as _gm_err:
            logging.getLogger(__name__).warning(
                f"⚠️ G0DM0D3 error, falling back to OpenAI: {_gm_err}"
            )
            return await _analyze_with_openai_fallback(signal_text)

elif OPENAI_AVAILABLE:
    # G0DM0D3 not available, use OpenAI as primary
    async def analyze_trading_signal(signal_text: str, symbol: str = "BTCUSDT",
                                     price: float = 0.0, atr: float = 0.0) -> dict:
        """Secondary: OpenAI GPT-4o-mini analysis"""
        return await _analyze_with_openai_fallback(signal_text)

else:
    # ── Pure rule-based mode (no AI APIs available) ────────────────
    async def analyze_trading_signal(signal_text: str, symbol: str = "BTCUSDT",
                                     price: float = 0.0, atr: float = 0.0) -> dict:
        return await _analyze_signal_fallback(signal_text)


async def analyze_sentiment(text: str) -> dict:
    """Sentiment analysis — uses G0DM0D3 if available, else OpenAI, else neutral"""
    global _openai_auth_failed
    if GODMODE_AVAILABLE:
        try:
            engine = get_godmode_engine()
            result = await engine.analyze_signal(
                signal_text=text,
                mode="consortium",
                tier="fast",
                godmode=True,
            )
            direction = result.get("direction", "neutral")
            score_map = {"bullish": 0.7, "bearish": -0.7, "neutral": 0.0}
            return {
                "sentiment": direction,
                "score": score_map.get(direction, 0.0),
                "fallback": False,
            }
        except Exception:
            pass
    if OPENAI_AVAILABLE and not _openai_auth_failed and _openai_client is not None:
        try:
            response = await _openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Analyse sentiment. Return JSON: sentiment ('positive'|'negative'|'neutral'), score (float -1.0 to 1.0)."},
                    {"role": "user", "content": text},
                ],
                response_format={"type": "json_object"},
                max_tokens=100,
                temperature=0.1,
            )
            result = json.loads(response.choices[0].message.content)
            return {
                "sentiment": str(result.get("sentiment", "neutral")),
                "score":     float(result.get("score", 0.0)),
                "fallback":  False,
            }
        except Exception:
            pass
    return {"sentiment": "neutral", "score": 0.0, "fallback": True}


def get_openai_status() -> dict:
    """Return comprehensive AI engine status"""
    return {
        "godmode_available":   GODMODE_AVAILABLE,
        "openai_available":    OPENAI_AVAILABLE,
        "configured":          GODMODE_AVAILABLE or OPENAI_AVAILABLE,
        "enabled":             GODMODE_AVAILABLE or (OPENAI_AVAILABLE and not _openai_auth_failed),
        "primary_engine":      "G0DM0D3-Consortium" if GODMODE_AVAILABLE else ("gpt-4o-mini" if OPENAI_AVAILABLE else "rule-based"),
        "fallback_active":     not GODMODE_AVAILABLE,
        "openai_auth_failed":  _openai_auth_failed,
        "strategies": {
            "godmode_prompt":  GODMODE_AVAILABLE,
            "autotune":        GODMODE_AVAILABLE,
            "parseltongue":    GODMODE_AVAILABLE,
            "stm_modules":     GODMODE_AVAILABLE,
            "consortium":      GODMODE_AVAILABLE,
            "ultraplinian":    GODMODE_AVAILABLE,
            "hall_of_fame":    GODMODE_AVAILABLE,
        },
    }


try:
    from config import Config
except ImportError:
    try:
        from SignalMaestro.config import Config
    except ImportError:
        Config = None

class AIEnhancedSignalProcessor:
    """Enhanced signal processor with OpenAI integration and Cornix compatibility"""
    
    def __init__(self):
        if Config is None:
            raise RuntimeError(
                "Config module unavailable — AI processor cannot initialise"
            )
        self.config = Config()
        self.logger = self._setup_logging()
        self.last_signal_time = {}
        self.signal_cache = {}
        self.rate_limiter = MessageRateLimiter()
        # Persistent aiohttp session — reused across all Telegram sends to avoid
        # creating and tearing down a TCP connection for every single message.
        self._session: Optional[aiohttp.ClientSession] = None

        # AI configuration — G0DM0D3 primary, OpenAI secondary
        self.openai_config = self.config.get_openai_config()
        self.ai_enabled = GODMODE_AVAILABLE or OPENAI_AVAILABLE
        self.godmode_enabled = GODMODE_AVAILABLE

        # Channel configuration
        self.target_channel = self.config.TARGET_CHANNEL
        self.bot_token = self.config.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

        # Signal settings — read from env var so start_ultimate_bot.py SIGNAL_INTERVAL_MIN is honoured
        self.min_ai_confidence = self.config.AI_CONFIG['decision_thresholds']['confidence_threshold']
        self.max_signals_per_hour = self.config.MAX_SIGNALS_PER_HOUR
        # Use SIGNAL_INTERVAL_SECONDS env var (set by launcher); fall back to 45s
        self.min_signal_interval = int(os.getenv('SIGNAL_INTERVAL_SECONDS', '45'))

        if GODMODE_AVAILABLE:
            self.logger.info("🔥 AI Signal Processor initialized — G0DM0D3 PRIMARY ENGINE ACTIVE")
            self.logger.info("   G0DM0D3: Consortium + AutoTune + Parseltongue + STM + Hall of Fame")
        elif OPENAI_AVAILABLE:
            self.logger.info("🤖 AI Signal Processor initialized with OpenAI (G0DM0D3 fallback)")
        else:
            self.logger.warning("⚠️ No AI APIs available — using rule-based signal processing")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return (or lazily create) the persistent aiohttp session."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session
    
    def _setup_logging(self):
        """Setup logging for the processor"""
        logger = logging.getLogger(f"{__name__}.AIEnhancedSignalProcessor")
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    async def process_and_enhance_signal(self, raw_signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process raw signal with AI enhancement"""
        try:
            # Basic validation
            if not self._validate_signal(raw_signal):
                return None
            
            # Check rate limiting
            symbol = raw_signal.get('symbol', '')
            if not self._check_rate_limit(symbol):
                return None
            
            # Apply AI enhancement if available
            if self.ai_enabled:
                enhanced_signal = await self._apply_ai_enhancement(raw_signal)
                if enhanced_signal is None:
                    return None
            else:
                enhanced_signal = raw_signal
            
            # Format for Cornix compatibility
            cornix_signal = self._format_for_cornix(enhanced_signal)
            
            # Update rate limiting
            self._update_rate_limit(symbol)
            
            return cornix_signal
            
        except Exception as e:
            self.logger.error(f"Error processing signal: {e}")
            return None
    
    async def _apply_ai_enhancement(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Apply G0DM0D3/AI analysis to enhance signal (primary: Consortium, fallback: OpenAI)"""
        try:
            # Create signal text for AI analysis
            signal_text = self._create_signal_text(signal)

            # Get AI analysis — pass symbol + price for G0DM0D3 context
            ai_analysis = await analyze_trading_signal(
                signal_text,
                symbol=signal.get('symbol', 'BTCUSDT'),
                price=float(signal.get('entry_price', 0.0)),
                atr=float(signal.get('atr', 0.0)),
            )
            
            # Check AI confidence threshold with enhanced validation
            ai_confidence = ai_analysis.get('confidence', 0)
            
            # Ensure confidence is properly formatted (0-1 scale)
            if ai_confidence > 1.0:
                ai_confidence = ai_confidence / 100.0
            
            if ai_confidence < self.min_ai_confidence:
                self.logger.warning(f"🚫 AI confidence {ai_confidence:.1%} below {self.min_ai_confidence:.0%} threshold - signal blocked")
                return None
            
            # Enhance signal with G0DM0D3/AI insights
            enhanced_signal = signal.copy()
            enhanced_signal.update({
                'ai_analysis':          ai_analysis,
                'ai_confidence':        ai_confidence,
                'ai_signal_strength':   ai_analysis.get('signal_strength', 0),
                'ai_risk_level':        ai_analysis.get('risk_level', 'medium'),
                'ai_market_sentiment':  ai_analysis.get('market_sentiment', 'neutral'),
                'ai_direction':         ai_analysis.get('direction', 'neutral'),
                'ai_quality_score':     ai_analysis.get('quality_score', 0),
                'ai_regime':            ai_analysis.get('regime', 'unknown'),
                'ai_entry_quality':     ai_analysis.get('entry_quality', 'fair'),
                'ai_reasoning':         ai_analysis.get('reasoning', ''),
                'ai_model_used':        ai_analysis.get('model_used', 'unknown'),
                'ai_analysis_type':     ai_analysis.get('analysis_type', 'unknown'),
                'ai_enhanced':          True,
                'godmode_active':       GODMODE_AVAILABLE,
                'enhancement_timestamp': datetime.now().isoformat(),
            })

            engine_label = "G0DM0D3" if GODMODE_AVAILABLE else "OpenAI"
            model_used = ai_analysis.get('model_used', 'unknown')
            self.logger.info(
                f"🔥 {engine_label} Enhanced {signal.get('symbol','?')}: "
                f"conf={ai_confidence:.1%} | strength={ai_analysis.get('signal_strength',0)} | "
                f"sentiment={ai_analysis.get('market_sentiment','?')} | "
                f"direction={ai_analysis.get('direction','?')} | model={model_used}"
            )
            
            return enhanced_signal
            
        except Exception as e:
            self.logger.error(f"AI enhancement failed: {e}")
            return signal  # Return original signal if AI fails
    
    def _create_signal_text(self, signal: Dict[str, Any]) -> str:
        """Create formatted text for AI analysis"""
        # Get take profit values with fallback
        tp1 = signal.get('take_profit_1') or signal.get('take_profit', 0)
        tp2 = signal.get('take_profit_2', tp1 * 1.5 if tp1 else 0)
        tp3 = signal.get('take_profit_3', tp1 * 2.0 if tp1 else 0)
        
        return f"""
Trading Signal Analysis:
Symbol: {signal.get('symbol', 'N/A')}
Direction: {signal.get('action', 'N/A')}
Entry Price: ${signal.get('entry_price', 0):.6f}
Stop Loss: ${signal.get('stop_loss', 0):.6f}
Take Profit 1: ${tp1:.6f}
Take Profit 2: ${tp2:.6f}
Take Profit 3: ${tp3:.6f}
Leverage: {signal.get('leverage', 5)}x
Signal Strength: {signal.get('strength', signal.get('signal_strength', 0))}%
Strategy: {signal.get('strategy', 'Ichimoku_Sniper')}
Timeframe Analysis: {signal.get('timeframe', 'N/A')}
Market Conditions: {signal.get('market_regime', 'trending')}
"""
    
    def _format_for_cornix(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """Format signal for Cornix compatibility"""
        # Calculate risk-reward ratio
        entry = signal.get('entry_price', 0)
        stop_loss = signal.get('stop_loss', 0)
        tp1 = signal.get('take_profit_1', 0)
        
        if entry > 0 and stop_loss > 0 and tp1 > 0:
            if signal.get('action', '').upper() == 'BUY':
                risk = abs(entry - stop_loss)
                reward = abs(tp1 - entry)
            else:
                risk = abs(stop_loss - entry)
                reward = abs(entry - tp1)
            
            risk_reward = reward / risk if risk > 0 else 0
        else:
            risk_reward = 0
        
        # Get AI insights
        ai_analysis = signal.get('ai_analysis', {})
        ai_confidence = signal.get('ai_confidence', 0)
        
        # Create Cornix-compatible message
        cornix_signal = {
            'symbol': signal.get('symbol', '').replace('USDT', '/USDT'),
            'action': signal.get('action', '').upper(),
            'entry_price': signal.get('entry_price', 0),
            'stop_loss': signal.get('stop_loss', 0),
            'take_profits': [
                signal.get('take_profit_1', 0),
                signal.get('take_profit_2', 0),
                signal.get('take_profit_3', 0)
            ],
            'leverage': signal.get('leverage', 1),
            'signal_strength': signal.get('strength', 0),
            'ai_confidence': ai_confidence,
            'risk_reward_ratio': risk_reward,
            'strategy': signal.get('strategy', 'AI_ENHANCED'),
            'timestamp': datetime.now().isoformat(),
            'formatted_message': self._create_formatted_message(signal, ai_analysis),
            'cornix_compatible': True
        }
        
        return cornix_signal
    
    def _create_formatted_message(self, signal: Dict[str, Any], ai_analysis: Dict[str, Any]) -> str:
        """Create beautifully formatted message for channel with G0DM0D3 analysis"""
        symbol = signal.get('symbol', '')
        action = signal.get('action', '').upper()
        entry = signal.get('entry_price', 0)
        sl = signal.get('stop_loss', 0)
        tp1 = signal.get('take_profit_1', 0)
        tp2 = signal.get('take_profit_2', 0)
        tp3 = signal.get('take_profit_3', 0)
        leverage = signal.get('leverage', 1)
        strength = signal.get('strength', 0)
        ai_confidence = signal.get('ai_confidence', 0)

        # G0DM0D3/AI insights
        ai_sentiment    = ai_analysis.get('market_sentiment', 'neutral').upper()
        ai_risk         = ai_analysis.get('risk_level', 'medium').upper()
        ai_signal_str   = ai_analysis.get('signal_strength', 0)
        ai_direction    = ai_analysis.get('direction', 'neutral').upper()
        ai_quality      = ai_analysis.get('quality_score', 0)
        ai_regime       = ai_analysis.get('regime', 'unknown').upper()
        ai_entry_q      = ai_analysis.get('entry_quality', 'fair').upper()
        ai_reasoning    = ai_analysis.get('reasoning', '')
        ai_model        = ai_analysis.get('model_used', 'unknown')
        godmode_active  = signal.get('godmode_active', False)

        # Emojis based on action and confidence
        action_emoji     = "🟢" if action == "BUY" else "🔴"
        confidence_emoji = "🚀" if ai_confidence > 0.8 else "⚡" if ai_confidence > 0.6 else "📊"
        risk_emoji       = "🟢" if ai_risk == "LOW" else "🟡" if ai_risk == "MEDIUM" else "🔴"
        engine_badge     = "🔥 G0DM0D3" if godmode_active else "🤖 AI"

        message = f"""
{action_emoji} **{symbol}** {action} SIGNAL {confidence_emoji}

📊 **SIGNAL ANALYSIS**
• Entry: `${entry:.6f}`
• Stop Loss: `${sl:.6f}`
• TP1: `${tp1:.6f}`
• TP2: `${tp2:.6f}`
• TP3: `${tp3:.6f}`

⚡ **TRADE SETUP**
• Leverage: `{leverage}x`
• Signal Strength: `{strength}%`
• AI Confidence: `{ai_confidence:.1%}`

{engine_badge} **ORACLE ANALYSIS**
• Direction: `{ai_direction}`
• Sentiment: `{ai_sentiment}`
• Risk Level: `{risk_emoji} {ai_risk}`
• Signal Strength: `{ai_signal_str}/100`
• Quality Score: `{ai_quality}/100`
• Market Regime: `{ai_regime}`
• Entry Quality: `{ai_entry_q}`
{f'• Reasoning: _{ai_reasoning[:80]}_' if ai_reasoning else ''}

🎯 **CORNIX FORMAT**
```
{symbol}
{action}
Entry: {entry:.6f}
SL: {sl:.6f}
TP1: {tp1:.6f}
TP2: {tp2:.6f}
TP3: {tp3:.6f}
Leverage: {leverage}x
```

🔥 **Powered by G0DM0D3 AI Oracle + MiroFish Swarm Intelligence**
⏰ {datetime.now().strftime('%H:%M:%S UTC')}
"""
        
        return message.strip()
    
    async def push_signal_to_channel(self, cornix_signal: Dict[str, Any]) -> bool:
        """Push enhanced signal to Telegram channel"""
        try:
            message = cornix_signal.get('formatted_message', '')
            if not message:
                return False
            
            # Check rate limiting
            if not self.rate_limiter.can_send_message():
                self.logger.warning("⚠️ Rate limit reached - skipping signal")
                return False
            
            # Send to channel
            success = await self._send_telegram_message(self.target_channel, message)
            
            if success:
                self.rate_limiter.record_message()
                self.logger.info(f"✅ Signal pushed to channel: {cornix_signal.get('symbol', '')}")
                
                # Store in cache for tracking
                symbol = cornix_signal.get('symbol', '')
                self.signal_cache[symbol] = {
                    'timestamp': datetime.now(),
                    'signal': cornix_signal
                }
                
                return True
            else:
                self.logger.error(f"❌ Failed to push signal for {cornix_signal.get('symbol', '')}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error pushing signal to channel: {e}")
            return False
    
    async def _send_telegram_message(self, chat_id: str, message: str) -> bool:
        """Send message to Telegram using persistent session."""
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True
            }
            session = await self._get_session()
            async with session.post(
                url, json=data,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    return True
                error = await response.text()
                self.logger.error(f"Telegram API error {response.status}: {error}")
                return False
        except Exception as e:
            self.logger.error(f"Error sending Telegram message: {e}")
            return False
    
    def _validate_signal(self, signal: Dict[str, Any]) -> bool:
        """Validate basic signal requirements"""
        required_fields = ['symbol', 'action', 'entry_price', 'stop_loss']
        
        for field in required_fields:
            if field not in signal or signal[field] is None:
                self.logger.warning(f"Signal validation failed: missing {field}")
                return False
        
        # Check for take profit - accept either take_profit or take_profit_1
        has_tp = any(field in signal and signal[field] is not None for field in ['take_profit', 'take_profit_1'])
        if not has_tp:
            self.logger.warning("Signal validation failed: missing take profit")
            return False
        
        # Check numeric values
        numeric_fields = ['entry_price', 'stop_loss']
        if 'take_profit_1' in signal:
            numeric_fields.append('take_profit_1')
        elif 'take_profit' in signal:
            numeric_fields.append('take_profit')
            
        for field in numeric_fields:
            if field in signal and (not isinstance(signal[field], (int, float)) or signal[field] <= 0):
                self.logger.warning(f"Signal validation failed: invalid {field}")
                return False
        
        return True
    
    def _check_rate_limit(self, symbol: str) -> bool:
        """Check if we can send signal for this symbol"""
        current_time = datetime.now()
        
        # Check symbol-specific rate limit
        if symbol in self.last_signal_time:
            time_diff = (current_time - self.last_signal_time[symbol]).total_seconds()
            if time_diff < self.min_signal_interval:
                return False
        
        return True
    
    def _update_rate_limit(self, symbol: str):
        """Update rate limit tracking"""
        self.last_signal_time[symbol] = datetime.now()
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get processor statistics"""
        return {
            'ai_enabled': self.ai_enabled,
            'openai_status': get_openai_status() if OPENAI_AVAILABLE else None,
            'signals_processed': len(self.signal_cache),
            'rate_limiter_status': self.rate_limiter.get_status(),
            'last_signal_symbols': list(self.signal_cache.keys())[-5:],
            'config': {
                'min_ai_confidence': self.min_ai_confidence,
                'max_signals_per_hour': self.max_signals_per_hour,
                'min_signal_interval': self.min_signal_interval
            }
        }


class MessageRateLimiter:
    """Rate limiter for Telegram messages"""
    
    def __init__(self, max_messages: int = 5, time_window: int = 3600):
        self.max_messages = max_messages
        self.time_window = time_window
        self.message_timestamps = []
    
    def can_send_message(self) -> bool:
        """Check if we can send a message within rate limits"""
        now = datetime.now().timestamp()
        # Remove old timestamps
        self.message_timestamps = [
            ts for ts in self.message_timestamps 
            if now - ts < self.time_window
        ]
        return len(self.message_timestamps) < self.max_messages
    
    def record_message(self):
        """Record that a message was sent"""
        self.message_timestamps.append(datetime.now().timestamp())
    
    def get_status(self) -> Dict[str, Any]:
        """Get rate limiter status"""
        now = datetime.now().timestamp()
        recent_messages = [
            ts for ts in self.message_timestamps 
            if now - ts < self.time_window
        ]
        return {
            'messages_sent_last_hour': len(recent_messages),
            'max_messages_per_hour': self.max_messages,
            'can_send': self.can_send_message(),
            'next_reset_in_seconds': self.time_window - (now - min(recent_messages)) if recent_messages else 0
        }


# Command processing functions
async def process_help_command() -> str:
    """Process /help command"""
    return """
🤖 **AI-Enhanced Trading Bot Commands**

**Essential Commands:**
• `/status` - Bot and AI status
• `/stats` - Trading statistics  
• `/signals` - Recent signal analysis

**AI Commands:**
• `/ai_status` - OpenAI integration status
• `/ai_analyze <symbol>` - AI analysis for symbol

**Settings:**
• `/set_confidence <0.1-0.9>` - Set AI confidence threshold
• `/toggle_ai` - Enable/disable AI enhancement

⚡ **Powered by OpenAI GPT-4o-mini & Advanced ML**
"""

async def process_status_command() -> str:
    """Process /status command"""
    processor = AIEnhancedSignalProcessor()
    stats = processor.get_processing_stats()
    
    ai_status = "🟢 ACTIVE" if stats['ai_enabled'] else "🔴 DISABLED"
    
    return f"""
📊 **AI-Enhanced Trading Bot Status**

🤖 **AI Enhancement:** {ai_status}
📈 **Signals Processed:** {stats['signals_processed']}
⚡ **Rate Limiter:** {stats['rate_limiter_status']['messages_sent_last_hour']}/{stats['rate_limiter_status']['max_messages_per_hour']} messages/hour

🔧 **Configuration:**
• AI Confidence Threshold: {stats['config']['min_ai_confidence']:.1%}
• Max Signals/Hour: {stats['config']['max_signals_per_hour']}
• Signal Interval: {stats['config']['min_signal_interval']}s

🎯 **Recent Symbols:** {', '.join(stats['last_signal_symbols']) if stats['last_signal_symbols'] else 'None'}
"""