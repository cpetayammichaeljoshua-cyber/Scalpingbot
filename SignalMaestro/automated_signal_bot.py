#!/usr/bin/env python3
"""
Fully Automated Telegram Signal Bot for Michael Joshua Tayam
Processes trading signals and automatically forwards them to designated targets
"""

import asyncio
import logging
import json
import aiohttp
import os
from datetime import datetime
from signal_parser import SignalParser
from risk_manager import RiskManager
from config import Config
from typing import Optional


class AutomatedSignalBot:
    """Fully automated Telegram bot for signal processing and forwarding"""

    def __init__(self):
        self.config = Config()
        self.logger = self._setup_logging()
        self.signal_parser = SignalParser()
        self.risk_manager = RiskManager()

        # Telegram configuration
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

        # Persistent aiohttp session for Telegram API connection reuse
        self._session: Optional[aiohttp.ClientSession] = None

        # Target configuration - Set for Michael Joshua Tayam
        self.admin_name = "Michael Joshua Tayam"
        self.target_chat_id = None  # Will be set when user starts bot
        self.channel_id = None      # Will be set when user provides channel

        # Auto-forwarding settings
        self.auto_forward_enabled = True
        self.signal_counter = 0

        self.logger.info(f"Bot initialized for {self.admin_name}")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return (or lazily create) the persistent aiohttp session."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    def _setup_logging(self):
        """Setup comprehensive logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('automated_signal_bot.log'),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger(__name__)

    async def send_message(self, chat_id, text, parse_mode='Markdown'):
        """Send message to Telegram with error handling"""
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }

            session = await self._get_session()
            async with session.post(url, json=data) as response:
                if response.status == 200:
                    self.logger.info(f"Message sent successfully to {chat_id}")
                    return True
                else:
                    error_text = await response.text()
                    self.logger.error(f"Failed to send message: {error_text}")
                    return False

        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            return False

    async def get_updates(self, offset=None, timeout=30):
        """Get updates from Telegram with improved error handling"""
        try:
            url = f"{self.base_url}/getUpdates"
            params = {'timeout': timeout}
            if offset is not None:
                params['offset'] = offset

            session = await self._get_session()
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('result', [])
                else:
                    self.logger.error(f"Failed to get updates: {response.status}")
                    return []

        except Exception as e:
            self.logger.error(f"Error getting updates: {e}")
            return []

    def format_professional_signal(self, parsed_signal, original_text):
        """Format trading signal with professional styling"""

        # Get direction and set appropriate styling
        direction = parsed_signal.get('direction', '').upper()
        if direction in ['LONG', 'BUY']:
            emoji = "🟢"
            action_text = "BUY SIGNAL"
        elif direction in ['SHORT', 'SELL']:
            emoji = "🔴"
            action_text = "SELL SIGNAL"
        else:
            emoji = "⚪"
            action_text = "SIGNAL"

        # Format entry, stop loss, take profit
        entry = parsed_signal.get('entry_price', 0)
        sl = parsed_signal.get('stop_loss', 0)
        tp1 = parsed_signal.get('take_profit_1', 0)
        tp2 = parsed_signal.get('take_profit_2', 0)
        tp3 = parsed_signal.get('take_profit_3', 0)
        leverage = parsed_signal.get('leverage', 0)
        confidence = parsed_signal.get('confidence', 0)

        # Calculate risk/reward
        risk = abs(entry - sl)
        reward = abs(tp1 - entry)
        rr_ratio = reward / risk if risk > 0 else 0

        msg = f"""
{emoji} <b>{action_text}</b> {emoji}
━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 Symbol:</b> {parsed_signal.get('symbol', 'N/A')}
<b>🎯 Direction:</b> {direction}
<b>💰 Entry:</b> ${entry:,.6f}
<b>🛡 Stop Loss:</b> ${sl:,.6f}
<b>🎯 TP1:</b> ${tp1:,.6f}
<b>🎯 TP2:</b> ${tp2:,.6f}
<b>🎯 TP3:</b> ${tp3:,.6f}
<b>⚡ Leverage:</b> {leverage}x
<b>📈 R:R Ratio:</b> 1:{rr_ratio:.2f}
<b>🎯 Confidence:</b> {confidence:.1f}%

<i>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>
"""
        return msg

    async def forward_to_admin(self, message):
        """Forward message to admin"""
        if self.target_chat_id:
            await self.send_message(self.target_chat_id, message)

    async def forward_to_channel(self, message):
        """Forward message to channel"""
        if self.channel_id:
            await self.send_message(self.channel_id, message)

    async def process_incoming_signal(self, message_text):
        """Process incoming signal message"""
        try:
            # Parse the signal
            parsed = self.signal_parser.parse_signal(message_text)
            if not parsed:
                self.logger.warning("Failed to parse signal")
                return None

            # Validate with risk manager
            risk_check = self.risk_manager.validate_signal(parsed)
            if not risk_check['valid']:
                self.logger.warning(f"Signal failed risk check: {risk_check['reason']}")
                return None

            # Format professional signal
            formatted = self.format_professional_signal(parsed, message_text)

            # Forward to admin and channel
            await self.forward_to_admin(formatted)
            await self.forward_to_channel(formatted)

            self.signal_counter += 1
            self.logger.info(f"Processed and forwarded signal #{self.signal_counter}")

            return parsed

        except Exception as e:
            self.logger.error(f"Error processing signal: {e}")
            return None

    async def handle_update(self, update):
        """Handle incoming Telegram update"""
        try:
            message = update.get('message')
            if not message:
                return

            chat_id = message.get('chat', {}).get('id')
            text = message.get('text', '')

            # Set target chat ID if not set
            if self.target_chat_id is None:
                self.target_chat_id = chat_id
                self.logger.info(f"Target chat ID set to: {chat_id}")

            # Check for commands
            if text.startswith('/start'):
                welcome = f"""
🤖 <b>Automated Signal Bot</b>
━━━━━━━━━━━━━━━━━━━━━━━
Welcome, <b>{self.admin_name}</b>!

Bot is now monitoring for trading signals.
Send or forward signals for automatic processing.

<b>Commands:</b>
/start - Show this message
/status - Show bot status
/signals - Show signal count
/help - Show help

<i>Powered by SignalMaestro</i>
"""
                await self.send_message(chat_id, welcome)
                return

            elif text.startswith('/status'):
                status = f"""
📊 <b>Bot Status</b>
━━━━━━━━━━━━━━━━━━━━━━━
<b>Admin:</b> {self.admin_name}
<b>Signals Processed:</b> {self.signal_counter}
<b>Auto-Forward:</b> {'✅ Enabled' if self.auto_forward_enabled else '❌ Disabled'}
<b>Target Chat:</b> {self.target_chat_id or 'Not Set'}
<b>Channel:</b> {self.channel_id or 'Not Set'}
"""
                await self.send_message(chat_id, status)
                return

            elif text.startswith('/signals'):
                await self.send_message(chat_id, f"📈 Total signals processed: {self.signal_counter}")
                return

            elif text.startswith('/help'):
                help_text = """
📖 <b>Help - Available Commands</b>
━━━━━━━━━━━━━━━━━━━━━━━
/start - Start the bot
/status - Show bot status
/signals - Show signal count
/help - Show this help
"""
                await self.send_message(chat_id, help_text)
                return

            # Process as trading signal
            await self.process_incoming_signal(text)

        except Exception as e:
            self.logger.error(f"Error handling update: {e}")

    async def run(self):
        """Main bot loop"""
        self.logger.info("🤖 Automated Signal Bot started")
        offset = None

        while True:
            try:
                updates = await self.get_updates(offset=offset)
                for update in updates:
                    offset = update['update_id'] + 1
                    await self.handle_update(update)

                await asyncio.sleep(1)

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)


async def main():
    bot = AutomatedSignalBot()
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())