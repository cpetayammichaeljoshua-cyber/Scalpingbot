#!/usr/bin/env python3
"""
Simple Signal Bot for Telegram
Receives and forwards trading signals without complex dependencies
"""

import asyncio
import logging
import json
import aiohttp
from datetime import datetime
from signal_parser import SignalParser
from config import Config

class SimpleSignalBot:
    """Simple bot that forwards signals to Telegram using HTTP API"""
    
    def __init__(self):
        self.config = Config()
        self.logger = self._setup_logging()
        self.signal_parser = SignalParser()
        
        # Telegram bot configuration
        self.bot_token = self.config.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        
        # Target configuration (set by user)
        self.target_chat_id = None
        self.channel_id = None
        
    def _setup_logging(self):
        """Setup logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('signal_bot.log'),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger(__name__)
    
    async def send_message(self, chat_id, text, parse_mode='Markdown'):
        """Send message to Telegram using HTTP API"""
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': parse_mode
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        self.logger.info(f"Message sent to {chat_id}")
                        return True
                    else:
                        error_text = await response.text()
                        self.logger.error(f"Failed to send message: {error_text}")
                        return False
                        
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            return False
    
    async def get_updates(self, offset=None, timeout=30):
        """Get updates from Telegram"""
        try:
            url = f"{self.base_url}/getUpdates"
            params = {
                'timeout': timeout
            }
            if offset is not None:
                params['offset'] = offset
            
            async with aiohttp.ClientSession() as session:
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
    
    def format_signal(self, parsed_signal, original_text):
        """Format trading signal for Telegram"""
        
        # Direction emoji
        direction = parsed_signal.get('direction', '').upper()
        if direction in ['LONG', 'BUY']:
            emoji = "🟢"
        elif direction in ['SHORT', 'SELL']:
            emoji = "🔴"
        else:
            emoji = "🔵"
        
        # Format signal
        formatted = f"""
{emoji} **TRADING SIGNAL**

📊 **Pair:** `{parsed_signal.get('symbol', 'N/A')}`
📈 **Direction:** `{direction}`
💰 **Entry:** `{parsed_signal.get('entry_price', 'N/A')}`

🛑 **Stop Loss:** `{parsed_signal.get('stop_loss', 'Not set')}`
🎯 **Take Profit:** `{parsed_signal.get('take_profit', 'Not set')}`

⏰ **Time:** `{datetime.now().strftime('%H:%M:%S')}`

---
*Original Signal:*
```
{original_text[:150]}
```
        """
        
        return formatted
    
    async def process_signal_text(self, signal_text, source_chat_id=None):
        """Process a trading signal"""
        try:
            self.logger.info("Processing signal...")
            
            # Parse signal
            parsed_signal = await self.signal_parser.parse_signal(signal_text)
            
            if parsed_signal:
                # Format signal
                formatted_signal = self.format_signal(parsed_signal, signal_text)
                
                # Send to target chat if set
                if self.target_chat_id:
                    await self.send_message(self.target_chat_id, formatted_signal)
                    self.logger.info(f"Signal forwarded to chat {self.target_chat_id}")
                
                # Send to channel if set  
                if self.channel_id:
                    await self.send_message(self.channel_id, formatted_signal)
                    self.logger.info(f"Signal forwarded to channel {self.channel_id}")
                
                # Send confirmation to source
                if source_chat_id:
                    await self.send_message(
                        source_chat_id, 
                        "✅ Signal processed and forwarded!"
                    )
                
                return True
            else:
                # Failed to parse
                if source_chat_id:
                    await self.send_message(
                        source_chat_id,
                        "❌ Could not parse as trading signal. Please check format."
                    )
                return False
                
        except Exception as e:
            self.logger.error(f"Error processing signal: {e}")
            if source_chat_id:
                await self.send_message(source_chat_id, f"❌ Error: {str(e)}")
            return False
    
    async def handle_command(self, message, chat_id):
        """Handle bot commands"""
        text = message.get('text', '')
        
        if text.startswith('/start'):
            welcome = """
🤖 **Signal Bot Active**

Send trading signals and I'll process them!

**Commands:**
• `/start` - This message
• `/setchat` - Set target chat
• `/setchannel` - Set target channel  
• `/status` - Bot status

**Usage:**
Just send trading signal text messages.
            """
            await self.send_message(chat_id, welcome)
            
        elif text.startswith('/setchat'):
            self.target_chat_id = chat_id
            await self.send_message(
                chat_id, 
                f"✅ Target chat set to: `{chat_id}`"
            )
            
        elif text.startswith('/setchannel'):
            # Extract channel ID from command if provided
            parts = text.split()
            if len(parts) > 1:
                self.channel_id = parts[1]
                await self.send_message(
                    chat_id,
                    f"✅ Target channel set to: `{self.channel_id}`"
                )
            else:
                await self.send_message(
                    chat_id,
                    "Please provide channel ID: `/setchannel @your_channel`"
                )
                
        elif text.startswith('/status'):
            status = f"""
📊 **Bot Status**

✅ **Online:** Active
🎯 **Target Chat:** `{self.target_chat_id or 'Not set'}`
📢 **Target Channel:** `{self.channel_id or 'Not set'}`
🕒 **Time:** `{datetime.now().strftime('%H:%M:%S')}`

Ready to process signals!
            """
            await self.send_message(chat_id, status)
    
    async def run_bot(self):
        """Main bot loop"""
        self.logger.info("Starting signal bot...")
        
        offset = None
        
        while True:
            try:
                # Get updates
                updates = await self.get_updates(offset)
                
                for update in updates:
                    # Update offset
                    offset = update['update_id'] + 1
                    
                    # Process message
                    if 'message' in update:
                        message = update['message']
                        chat_id = message['chat']['id']
                        
                        if 'text' in message:
                            text = message['text']
                            
                            if text.startswith('/'):
                                # Handle command
                                await self.handle_command(message, chat_id)
                            else:
                                # Process as signal
                                await self.process_signal_text(text, chat_id)
                
                # Small delay to avoid hitting rate limits
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Error in bot loop: {e}")
                await asyncio.sleep(5)

async def main():
    """Run the signal bot"""
    bot = SimpleSignalBot()
    
    try:
        print("🚀 Starting Simple Signal Bot...")
        print("📱 Bot will process and forward trading signals")
        print("🎯 Use /setchat and /setchannel to configure targets")
        print("Press Ctrl+C to stop")
        
        await bot.run_bot()
        
    except KeyboardInterrupt:
        print("\n🛑 Stopping bot...")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())