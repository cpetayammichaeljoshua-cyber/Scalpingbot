"""
Telegram Bot for Trading Signals

Sends rich formatted trading signals to Telegram chat.
Supports:
- Buy/Sell signal notifications
- Market state updates
- Error notifications
- Performance reports
"""

import os
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, List
import aiohttp

logger = logging.getLogger(__name__)


class TelegramSignalBot:
    """
    Telegram Bot for sending trading signals
    
    Features:
    - Rich formatted signal messages
    - Async message sending
    - Retry mechanism for failed sends
    - Rate limiting compliance
    """
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        """
        Initialize Telegram Bot
        
        Args:
            bot_token: Telegram Bot API token
            chat_id: Target chat ID for signals
        """
        self.bot_token = bot_token or os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID', '')
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self._session: Optional[aiohttp.ClientSession] = None
        self._message_queue: List[Dict] = []
        self._last_message_time: Optional[datetime] = None
        self._min_message_interval = 1.0
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self) -> None:
        """Close the aiohttp session and cleanup connectors"""
        if self._session:
            try:
                await self._session.close()
                await asyncio.sleep(0.3)
                logger.info("Telegram bot session closed")
            except Exception as e:
                logger.warning(f"Error closing session: {e}")
            finally:
                self._session = None
    
    def _format_price(self, price: float) -> str:
        """Format price with appropriate decimals"""
        if price >= 1000:
            return f"${price:,.2f}"
        elif price >= 1:
            return f"${price:.4f}"
        else:
            return f"${price:.6f}"
    
    def _format_signal_message(self, signal: Dict) -> str:
        """
        Format trading signal as Telegram message
        
        Args:
            signal: Signal dictionary from SignalEngine
            
        Returns:
            Formatted message string
        """
        direction = signal['type']
        emoji = "🟢" if direction == "LONG" else "🔴"
        direction_emoji = "📈" if direction == "LONG" else "📉"
        
        entry = self._format_price(signal['entry_price'])
        sl = self._format_price(signal['stop_loss'])
        tp = self._format_price(signal['take_profit'])
        risk = signal['risk_percent']
        rr = signal['risk_reward_ratio']
        
        stc_value = signal.get('stc_value', 0)
        atr = signal.get('atr', 0)
        
        timestamp = signal.get('timestamp', datetime.now())
        if hasattr(timestamp, 'strftime'):
            time_str = timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')
        else:
            time_str = str(timestamp)
        
        leverage_section = self._format_leverage_section(signal)
        
        message = f"""
{emoji} <b>UT BOT + STC SIGNAL</b> {emoji}

{direction_emoji} <b>Direction:</b> {direction}
💱 <b>Pair:</b> {signal.get('symbol', 'ETH/USDT')}
⏰ <b>Timeframe:</b> {signal.get('timeframe', '5m')}

━━━━━━━━━━━━━━━━━━━━━

💰 <b>Entry Price:</b> {entry}
🛑 <b>Stop Loss:</b> {sl}
🎯 <b>Take Profit:</b> {tp}

━━━━━━━━━━━━━━━━━━━━━

📊 <b>Risk:</b> {risk:.2f}%
🎲 <b>Risk:Reward:</b> 1:{rr}

━━━━━━━━━━━━━━━━━━━━━

<b>INDICATOR VALUES:</b>
📉 <b>STC:</b> {stc_value:.2f}
📏 <b>ATR:</b> {atr:.4f}

━━━━━━━━━━━━━━━━━━━━━

{leverage_section}

━━━━━━━━━━━━━━━━━━━━━

<b>CONFIRMATION:</b>
✅ UT Bot {direction} Signal
✅ STC {"Green ↑" if direction == "LONG" else "Red ↓"}
✅ All conditions met

🕐 <i>{time_str}</i>

<b>#ETHUSDT #{direction} #UTBot #STC</b>
"""
        return message.strip()
    
    def _format_market_state_message(self, state: Dict) -> str:
        """
        Format market state update message
        
        Args:
            state: Market state dictionary
            
        Returns:
            Formatted message string
        """
        price = self._format_price(state.get('price', 0))
        stc = state.get('stc_value', 0)
        stc_color = state.get('stc_color', 'neutral')
        stc_slope = state.get('stc_slope', 'neutral')
        ut_color = state.get('ut_bar_color', 'neutral')
        
        stc_emoji = "🟢" if stc_color == "green" else "🔴" if stc_color == "red" else "⚪"
        ut_emoji = "🟢" if ut_color == "green" else "🔴" if ut_color == "red" else "⚪"
        slope_emoji = "↗️" if stc_slope == "up" else "↘️" if stc_slope == "down" else "➡️"
        
        timestamp = state.get('timestamp', datetime.now())
        if hasattr(timestamp, 'strftime'):
            time_str = timestamp.strftime('%H:%M:%S UTC')
        else:
            time_str = str(timestamp)
        
        message = f"""
📊 <b>MARKET UPDATE</b>

💱 ETH/USDT | 5m
💰 Price: {price}

{ut_emoji} UT Bot: {ut_color.upper()}
{stc_emoji} STC: {stc:.1f} {slope_emoji}

🕐 {time_str}
"""
        return message.strip()
    
    def _format_error_message(self, error: str, context: str = "") -> str:
        """Format error notification message"""
        return f"""
⚠️ <b>BOT ERROR</b>

{context}
<code>{error}</code>

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
    
    def _format_startup_message(self) -> str:
        """Format bot startup message"""
        return f"""
🚀 <b>UT BOT + STC SIGNAL BOT STARTED</b>

📊 Strategy: UT Bot Alerts + STC Indicator
💱 Pair: ETH/USDT
⏰ Timeframe: 5 minutes
🎲 Risk:Reward: 1:1.5

<b>Settings:</b>
• UT Bot Key: 2.0, ATR Period: 6
• STC Length: 80, Fast: 27, Slow: 50
• Swing Lookback: 5 bars

✅ Bot is now monitoring for signals...

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
    
    def _format_shutdown_message(self, reason: str = "Manual shutdown") -> str:
        """Format bot shutdown message"""
        return f"""
🛑 <b>BOT STOPPED</b>

Reason: {reason}

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
    
    async def send_message(self, text: str, parse_mode: str = "HTML", 
                          disable_notification: bool = False,
                          retry_count: int = 3) -> bool:
        """
        Send message to Telegram
        
        Args:
            text: Message text
            parse_mode: Telegram parse mode (HTML or Markdown)
            disable_notification: Send without notification sound
            retry_count: Number of retries on failure
            
        Returns:
            True if sent successfully
        """
        if not self.bot_token or not self.chat_id:
            logger.error("Telegram bot token or chat ID not configured")
            return False
        
        now = datetime.now()
        if self._last_message_time:
            elapsed = (now - self._last_message_time).total_seconds()
            if elapsed < self._min_message_interval:
                await asyncio.sleep(self._min_message_interval - elapsed)
        
        session = await self._get_session()
        url = f"{self.base_url}/sendMessage"
        
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_notification": disable_notification
        }
        
        for attempt in range(retry_count):
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with session.post(url, json=payload, timeout=timeout) as response:
                    if response.status == 200:
                        self._last_message_time = datetime.now()
                        logger.info("Message sent successfully")
                        return True
                    else:
                        error_text = await response.text()
                        logger.warning(f"Telegram API error (attempt {attempt+1}): {error_text}")
                        
            except asyncio.TimeoutError:
                logger.warning(f"Timeout sending message (attempt {attempt+1})")
            except Exception as e:
                logger.error(f"Error sending message (attempt {attempt+1}): {e}")
            
            if attempt < retry_count - 1:
                await asyncio.sleep(2 ** attempt)
        
        logger.error("Failed to send message after all retries")
        return False
    
    def _format_leverage_section(self, signal: Dict) -> str:
        """Format leverage and margin details from signal"""
        leverage_config = signal.get('leverage_config', {})
        recommended_lev = leverage_config.get('base_leverage', 5)
        auto_lev = signal.get('recommended_leverage', recommended_lev)
        margin_type = leverage_config.get('margin_type', 'CROSS')
        auto_margin = leverage_config.get('auto_add_margin', True)
        
        return f"""
⚡ <b>LEVERAGE & MARGIN:</b>
• Recommended: {recommended_lev}x
• Auto Leverage: {auto_lev}x
• Margin Type: {margin_type}
• Cross Margin: {'✅ Enabled' if margin_type == 'CROSS' else '❌ Disabled'}
• Auto Add Margin: {'✅ Active' if auto_margin else '❌ Inactive'}"""
    
    def _format_trade_execution(self, trade_info: Dict) -> str:
        """
        Format trade execution details
        
        Args:
            trade_info: Trade execution info from orchestrator
            
        Returns:
            Formatted trade execution section
        """
        if not trade_info:
            return ""
        
        trade_result = trade_info.get('trade_result', {})
        leverage_result = trade_info.get('leverage_result')
        balance = trade_info.get('balance', 0)
        
        if not trade_result.get('success'):
            return f"""
━━━━━━━━━━━━━━━━━━━━━

⚠️ <b>AUTO-TRADE FAILED</b>
{trade_result.get('message', 'Unknown error')}
"""
        
        leverage = leverage_result.leverage if leverage_result else 0
        position_size = leverage_result.position_size if leverage_result else 0
        position_value = leverage_result.position_value if leverage_result else 0
        margin = leverage_result.margin_required if leverage_result else 0
        confidence = leverage_result.confidence if leverage_result else 0
        reason = leverage_result.reason if leverage_result else ""
        
        entry_order = trade_result.get('entry', {})
        sl_order = trade_result.get('stop_loss', {})
        tp_order = trade_result.get('take_profit', {})
        
        return f"""
━━━━━━━━━━━━━━━━━━━━━

🤖 <b>AUTO-TRADE EXECUTED</b>

⚡ <b>Leverage:</b> {leverage}x
📊 <b>Position Size:</b> {position_size:.4f} ETH
💵 <b>Position Value:</b> ${position_value:,.2f}
💰 <b>Margin Used:</b> ${margin:,.2f}
📈 <b>Confidence:</b> {confidence*100:.1f}%

<b>LEVERAGE CALCULATION:</b>
{reason}

<b>ORDERS:</b>
✅ Entry: {'Filled' if entry_order.success else 'Failed'}
🛑 Stop Loss: {'Set' if sl_order.success else 'Failed'}
🎯 Take Profit: {'Set' if tp_order.success else 'Failed'}

💳 <b>Account Balance:</b> ${balance:,.2f}
"""
    
    async def send_signal(self, signal: Dict, trade_info: Optional[Dict] = None) -> bool:
        """
        Send trading signal to Telegram
        
        Args:
            signal: Signal dictionary from SignalEngine
            trade_info: Optional trade execution info
            
        Returns:
            True if sent successfully
        """
        message = self._format_signal_message(signal)
        
        if trade_info:
            message += self._format_trade_execution(trade_info)
        
        return await self.send_message(message, disable_notification=False)
    
    async def send_market_update(self, state: Dict) -> bool:
        """
        Send market state update
        
        Args:
            state: Market state dictionary
            
        Returns:
            True if sent successfully
        """
        message = self._format_market_state_message(state)
        return await self.send_message(message, disable_notification=True)
    
    async def send_error(self, error: str, context: str = "") -> bool:
        """
        Send error notification
        
        Args:
            error: Error message
            context: Additional context
            
        Returns:
            True if sent successfully
        """
        message = self._format_error_message(error, context)
        return await self.send_message(message)
    
    async def send_startup_notification(self) -> bool:
        """Send bot startup notification"""
        message = self._format_startup_message()
        return await self.send_message(message)
    
    async def send_shutdown_notification(self, reason: str = "Manual shutdown") -> bool:
        """Send bot shutdown notification"""
        message = self._format_shutdown_message(reason)
        return await self.send_message(message)
    
    def send_signal_sync(self, signal: Dict) -> bool:
        """Synchronous wrapper for send_signal"""
        try:
            asyncio.get_running_loop()
            # Already inside an async context — schedule as a fire-and-forget task
            asyncio.ensure_future(self.send_signal(signal))
            return True
        except RuntimeError:
            # No running event loop — create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.send_signal(signal))
            finally:
                loop.close()

    def send_message_sync(self, text: str) -> bool:
        """Synchronous wrapper for send_message"""
        try:
            asyncio.get_running_loop()
            # Already inside an async context — schedule as a fire-and-forget task
            asyncio.ensure_future(self.send_message(text))
            return True
        except RuntimeError:
            # No running event loop — create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.send_message(text))
            finally:
                loop.close()
