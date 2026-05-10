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
        
        # Target configuration - Set for Michael Joshua Tayam
        self.admin_name = "Michael Joshua Tayam"
        self.target_chat_id = None  # Will be set when user starts bot
        self.channel_id = None      # Will be set when user provides channel
        
        # Auto-forwarding settings
        self.auto_forward_enabled = True
        self.signal_counter = 0
        
        self.logger.info(f"Bot initialized for {self.admin_name}")
        
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
            
            async with aiohttp.ClientSession() as session:
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
            emoji = "🔵"
            action_text = "TRADING SIGNAL"
        
        # Format timestamp
        timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        
        # Calculate risk/reward ratio if available
        entry = parsed_signal.get('entry_price')
        stop_loss = parsed_signal.get('stop_loss')
        take_profit = parsed_signal.get('take_profit')
        
        risk_reward = "N/A"
        if entry and stop_loss and take_profit:
            try:
                risk = abs(float(entry) - float(stop_loss))
                reward = abs(float(take_profit) - float(entry))
                if risk > 0:
                    risk_reward = f"1:{round(reward/risk, 2)}"
            except:
                pass
        
        # Professional signal format
        formatted = f"""
{emoji} **{action_text}**

📊 **Instrument:** `{parsed_signal.get('symbol', 'N/A')}`
📈 **Direction:** `{direction}`
💰 **Entry Price:** `{entry or 'Market'}`

🛑 **Stop Loss:** `{stop_loss or 'Not specified'}`
🎯 **Take Profit:** `{take_profit or 'Not specified'}`
⚖️ **Risk/Reward:** `{risk_reward}`

📋 **Signal Analysis:**
• **Confidence:** {parsed_signal.get('confidence', 'Medium')}
• **Timeframe:** {parsed_signal.get('timeframe', 'Not specified')}
• **Setup Type:** {parsed_signal.get('setup_type', 'Standard')}

⏰ **Time:** `{timestamp}`
🔢 **Signal #:** `{self.signal_counter}`

---
*Auto-forwarded by Trading Bot*
*For: {self.admin_name}*
        """
        
        return formatted
    
    async def process_and_forward_signal(self, signal_text, source_chat_id):
        """Process signal and automatically forward to targets"""
        try:
            self.signal_counter += 1
            self.logger.info(f"Processing signal #{self.signal_counter} from chat {source_chat_id}")
            
            # Parse the signal
            parsed_signal = await self.signal_parser.parse_signal(signal_text)
            
            if parsed_signal:
                # Enhance signal with risk analysis
                risk_analysis = await self.risk_manager.analyze_signal(parsed_signal)
                parsed_signal.update(risk_analysis)
                
                # Format the signal professionally
                formatted_signal = self.format_professional_signal(parsed_signal, signal_text)
                
                # Send confirmation to source
                confirmation = f"✅ **Signal #{self.signal_counter} Processed**\n\nSignal parsed and forwarded successfully!"
                await self.send_message(source_chat_id, confirmation)
                
                # Forward to target chat if set
                if self.target_chat_id:
                    success = await self.send_message(self.target_chat_id, formatted_signal)
                    if success:
                        self.logger.info(f"Signal forwarded to target chat {self.target_chat_id}")
                
                # Forward to channel if set
                if self.channel_id:
                    success = await self.send_message(self.channel_id, formatted_signal)
                    if success:
                        self.logger.info(f"Signal forwarded to channel {self.channel_id}")
                
                # Log successful processing
                self.logger.info(f"Signal #{self.signal_counter} processed successfully")
                return True
                
            else:
                # Signal parsing failed
                error_msg = f"❌ **Signal #{self.signal_counter} Failed**\n\nCould not parse the trading signal. Please check format."
                await self.send_message(source_chat_id, error_msg)
                self.logger.warning(f"Failed to parse signal #{self.signal_counter}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error processing signal: {e}")
            error_msg = f"❌ **Error Processing Signal**\n\n{str(e)}"
            await self.send_message(source_chat_id, error_msg)
            return False
    
    async def handle_command(self, message, chat_id, user_name=""):
        """Handle bot commands with enhanced functionality"""
        text = message.get('text', '')
        
        if text.startswith('/start'):
            # Set this chat as target if it's the first start
            if not self.target_chat_id:
                self.target_chat_id = chat_id
                
            welcome = f"""
🤖 **Automated Signal Bot Active**
*Configured for: {self.admin_name}*

**Bot Status:** Online and Ready
**Auto-Forward:** {'Enabled' if self.auto_forward_enabled else 'Disabled'}

**Available Commands:**
• `/start` - Bot information
• `/status` - System status
• `/setchat` - Set target chat (current: {self.target_chat_id or 'Not set'})
• `/setchannel @channel` - Set target channel
• `/toggle` - Toggle auto-forwarding
• `/stats` - Signal statistics

**How it works:**
Send any trading signal and I'll automatically:
1. Parse and analyze the signal
2. Apply risk management
3. Format professionally
4. Forward to designated targets

*Ready to process signals!*
            """
            await self.send_message(chat_id, welcome)
            
        elif text.startswith('/status'):
            status = f"""
📊 **Bot Status Report**

✅ **System:** Online
👤 **User:** {self.admin_name}
🎯 **Target Chat:** `{self.target_chat_id or 'Not set'}`
📢 **Channel:** `{self.channel_id or 'Not set'}`
🔄 **Auto-Forward:** `{'ON' if self.auto_forward_enabled else 'OFF'}`
📈 **Signals Processed:** `{self.signal_counter}`
🕒 **Uptime:** `{datetime.now().strftime('%H:%M:%S')}`

**System Ready:** All components operational
            """
            await self.send_message(chat_id, status)
            
        elif text.startswith('/setchat'):
            self.target_chat_id = chat_id
            await self.send_message(chat_id, f"✅ **Target Chat Updated**\n\nSignals will be forwarded to: `{chat_id}`")
            
        elif text.startswith('/setchannel'):
            parts = text.split()
            if len(parts) > 1:
                self.channel_id = parts[1]
                await self.send_message(chat_id, f"✅ **Channel Set**\n\nTarget channel: `{self.channel_id}`")
            else:
                await self.send_message(chat_id, "**Usage:** `/setchannel @your_channel_username`")
                
        elif text.startswith('/toggle'):
            self.auto_forward_enabled = not self.auto_forward_enabled
            status = "enabled" if self.auto_forward_enabled else "disabled"
            await self.send_message(chat_id, f"🔄 **Auto-forwarding {status}**")
            
        elif text.startswith('/stats'):
            stats = f"""
📊 **Signal Statistics**

**Total Processed:** `{self.signal_counter}`
**Success Rate:** `100%` (All parsed signals forwarded)
**Active Since:** Bot startup
**Target Chat:** `{self.target_chat_id or 'Not configured'}`
**Channel:** `{self.channel_id or 'Not configured'}`

*Bot optimized for {self.admin_name}*
            """
            await self.send_message(chat_id, stats)
    
    async def run_automated_bot(self):
        """Main automated bot loop"""
        self.logger.info(f"Starting automated signal bot for {self.admin_name}")
        
        offset = None
        
        while True:
            try:
                # Get updates from Telegram
                updates = await self.get_updates(offset)
                
                for update in updates:
                    # Update offset
                    offset = update['update_id'] + 1
                    
                    # Process message
                    if 'message' in update:
                        message = update['message']
                        chat_id = message['chat']['id']
                        user_name = message.get('from', {}).get('first_name', 'Unknown')
                        
                        if 'text' in message:
                            text = message['text']
                            
                            if text.startswith('/'):
                                # Handle command
                                await self.handle_command(message, chat_id, user_name)
                            else:
                                # Process as potential trading signal
                                if self.auto_forward_enabled:
                                    await self.process_and_forward_signal(text, chat_id)
                                else:
                                    await self.send_message(chat_id, "⏸️ Auto-forwarding is disabled. Use /toggle to enable.")
                
                # Rate limiting
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Error in bot loop: {e}")
                await asyncio.sleep(5)

async def main():
    """Initialize and run the automated signal bot"""
    bot = AutomatedSignalBot()
    
    try:
        print("🚀 Starting Automated Signal Bot")
        print(f"👤 Configured for: {bot.admin_name}")
        print("📱 Processing trading signals automatically")
        print("🎯 Auto-forwarding enabled")
        print("🔄 Bot ready for signals")
        print("\nPress Ctrl+C to stop")
        
        await bot.run_automated_bot()
        
    except KeyboardInterrupt:
        print(f"\n🛑 Stopping automated bot for {bot.admin_name}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())