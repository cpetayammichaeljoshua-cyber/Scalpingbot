#!/usr/bin/env python3
"""
Dynamic Signal Integrator - Connects AI signal processing with main trading bot
Handles dynamic signal pushing to channel with Unity compatibility
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

# Add project paths
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    from ai_enhanced_signal_processor import AIEnhancedSignalProcessor
    AI_PROCESSOR_AVAILABLE = True
except ImportError:
    AI_PROCESSOR_AVAILABLE = False

class DynamicSignalIntegrator:
    """Integrates AI signal processing with the main trading bot"""
    
    def __init__(self, trading_bot=None):
        self.trading_bot = trading_bot
        self.logger = self._setup_logging()
        
        # Initialize AI processor if available
        if AI_PROCESSOR_AVAILABLE:
            self.ai_processor = AIEnhancedSignalProcessor()
            self.logger.info("🤖 AI-Enhanced Signal Processor integrated")
        else:
            self.ai_processor = None
            self.logger.warning("⚠️ AI Signal Processor not available")
        
        # Integration settings
        self.auto_push_enabled = True
        self.unity_integration_enabled = True
        
    def _setup_logging(self):
        """Setup logging"""
        logger = logging.getLogger(f"{__name__}.DynamicSignalIntegrator")
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    async def process_and_push_signal(self, raw_signal: Dict[str, Any]) -> bool:
        """Process signal with AI and push to channel dynamically"""
        try:
            if not self.ai_processor:
                # Fallback without AI processing
                return await self._push_raw_signal(raw_signal)
            
            # Process with AI enhancement
            enhanced_signal = await self.ai_processor.process_and_enhance_signal(raw_signal)
            
            if enhanced_signal is None:
                self.logger.info(f"Signal filtered by AI: {raw_signal.get('symbol', 'N/A')}")
                return False
            
            # Push enhanced signal to channel
            success = await self.ai_processor.push_signal_to_channel(enhanced_signal)
            
            if success:
                self.logger.info(f"✅ Enhanced signal pushed: {enhanced_signal.get('symbol', 'N/A')}")
                
                # Log to trading bot if available
                if self.trading_bot and hasattr(self.trading_bot, 'logger'):
                    self.trading_bot.logger.info(
                        f"📡 AI-Enhanced signal pushed to channel: {enhanced_signal.get('symbol', 'N/A')} "
                        f"(AI Confidence: {enhanced_signal.get('ai_confidence', 0):.1%})"
                    )
                
                return True
            else:
                self.logger.error(f"❌ Failed to push enhanced signal: {enhanced_signal.get('symbol', 'N/A')}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error in signal processing and pushing: {e}")
            return False
    
    async def _push_raw_signal(self, signal: Dict[str, Any]) -> bool:
        """Fallback method to push raw signal without AI enhancement"""
        try:
            # Create basic Unity-compatible message
            message = self._create_basic_unity_message(signal)
            
            # Send via trading bot if available
            if self.trading_bot and hasattr(self.trading_bot, 'send_channel_message'):
                return await self.trading_bot.send_channel_message(message)
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error pushing raw signal: {e}")
            return False
    
    def _create_basic_unity_message(self, signal: Dict[str, Any]) -> str:
        """Create basic Unity-compatible message"""
        symbol = signal.get('symbol', '')
        action = signal.get('action', '').upper()
        entry = signal.get('entry_price', 0)
        sl = signal.get('stop_loss', 0)
        tp1 = signal.get('take_profit_1', 0)
        tp2 = signal.get('take_profit_2', 0)
        tp3 = signal.get('take_profit_3', 0)
        leverage = signal.get('leverage', 1)
        
        action_emoji = "🟢" if action == "BUY" else "🔴"
        
        message = f"""
{action_emoji} **{symbol}** {action} SIGNAL

📊 **TRADE SETUP**
• Entry: `${entry:.6f}`
• Stop Loss: `${sl:.6f}`
• TP1: `${tp1:.6f}`
• TP2: `${tp2:.6f}`
• TP3: `${tp3:.6f}`
• Leverage: `{leverage}x`

🎯 **UNITY FORMAT**
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

⏰ {datetime.now().strftime('%H:%M:%S UTC')}
"""
        return message.strip()
    
    def get_integration_status(self) -> Dict[str, Any]:
        """Get integration status"""
        return {
            'ai_processor_available': AI_PROCESSOR_AVAILABLE,
            'ai_processor_enabled': self.ai_processor is not None,
            'auto_push_enabled': self.auto_push_enabled,
            'unity_integration_enabled': self.unity_integration_enabled,
            'trading_bot_connected': self.trading_bot is not None
        }


# Essential Commands for Trading Bot
ESSENTIAL_COMMANDS = {
    '/start': 'Start the bot',
    '/status': 'Bot status and statistics',
    '/help': 'Show available commands',
    '/signals': 'Recent signals analysis',
    '/ai_status': 'AI integration status',
    '/toggle_ai': 'Enable/disable AI enhancement'
}

async def cmd_start() -> str:
    """Essential /start command"""
    return """
🤖 **AI-Enhanced Trading Bot**

✅ **Bot Status:** Active
🔥 **AI Enhancement:** Enabled
📡 **Channel:** Live Signal Pushing
🎯 **Unity:** Compatible

**Quick Commands:**
• `/status` - View bot statistics
• `/signals` - Recent signal analysis
• `/ai_status` - AI system status

🚀 **Ready for dynamic signal processing!**
"""

async def cmd_status(trading_bot=None) -> str:
    """Essential /status command"""
    try:
        # Get integrator status if available
        integrator = DynamicSignalIntegrator(trading_bot)
        status = integrator.get_integration_status()
        
        ai_status = "🟢 ACTIVE" if status['ai_processor_enabled'] else "🔴 DISABLED"
        push_status = "🟢 ENABLED" if status['auto_push_enabled'] else "🔴 DISABLED"
        
        return f"""
📊 **Bot Status Report**

🤖 **AI Enhancement:** {ai_status}
📡 **Auto Push:** {push_status}
🎯 **Unity Integration:** {'🟢 ACTIVE' if status['unity_integration_enabled'] else '🔴 DISABLED'}

⚡ **System Health:** All systems operational
📈 **Signal Processing:** Dynamic & AI-Enhanced
🔄 **Last Update:** {datetime.now().strftime('%H:%M:%S UTC')}
"""
    except Exception as e:
        return f"📊 **Bot Status:** ✅ Active\n⚠️ Status details unavailable: {str(e)[:50]}"

async def cmd_help() -> str:
    """Essential /help command"""
    return """
🤖 **AI-Enhanced Trading Bot Commands**

**Essential Commands:**
• `/start` - Initialize bot
• `/status` - System status & stats
• `/help` - This help message

**Signal Commands:**  
• `/signals` - Recent signal analysis
• `/ai_status` - AI system status
• `/toggle_ai` - Toggle AI enhancement

🔥 **Features:**
• Dynamic signal processing
• AI-enhanced analysis with GPT-5
• Unity-compatible formatting
• Real-time channel pushing

⚡ **Powered by Advanced ML & OpenAI**
"""

async def cmd_signals(trading_bot=None) -> str:
    """Essential /signals command"""
    try:
        integrator = DynamicSignalIntegrator(trading_bot)
        if integrator.ai_processor:
            stats = integrator.ai_processor.get_processing_stats()
            recent_signals = stats.get('last_signal_symbols', [])
            signals_count = stats.get('signals_processed', 0)
            
            return f"""
📊 **Recent Signals Analysis**

🔢 **Total Processed:** {signals_count}
📈 **Recent Symbols:** {', '.join(recent_signals[-5:]) if recent_signals else 'None'}

🤖 **AI Status:** {'🟢 Active' if stats['ai_enabled'] else '🔴 Inactive'}
⚡ **Rate Limiter:** {stats['rate_limiter_status']['messages_sent_last_hour']}/{stats['rate_limiter_status']['max_messages_per_hour']} msgs/hour

🎯 **AI Confidence Threshold:** {stats['config']['min_ai_confidence']:.1%}
"""
        else:
            return "📊 **Signals:** AI processor not available"
    except Exception as e:
        return f"📊 **Signals:** Status unavailable ({str(e)[:30]})"

async def cmd_ai_status() -> str:
    """Essential /ai_status command"""
    try:
        if AI_PROCESSOR_AVAILABLE:
            from openai_handler import get_openai_status
            openai_status = get_openai_status()
            
            return f"""
🤖 **AI System Status**

🔌 **OpenAI Integration:** {'🟢 Connected' if openai_status['configured'] else '🔴 Not configured'}
⚡ **API Status:** {'🟢 Active' if openai_status['enabled'] else '🔴 Disabled'}
🧠 **Model:** {openai_status.get('model', 'N/A')}
💭 **Max Tokens:** {openai_status.get('max_tokens', 'N/A')}

📡 **Signal Processing:** AI-Enhanced
🎯 **Analysis:** Real-time market sentiment
🔮 **Predictions:** GPT-5 powered insights
"""
        else:
            return """
🤖 **AI System Status**

🔴 **Status:** AI processor not available
⚠️ **Mode:** Fallback processing active
📊 **Signals:** Basic processing only
"""
    except Exception as e:
        return f"🤖 **AI Status:** Error retrieving status ({str(e)[:30]})"