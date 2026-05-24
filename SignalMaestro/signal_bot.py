#!/usr/bin/env python3
"""
Telegram Signal Bot - Receives and forwards trading signals
Processes signals and sends formatted messages to Telegram bot/channel
"""

import asyncio
import logging
import os
from datetime import datetime
from telegram import Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, Update
from signal_parser import SignalParser
from config import Config

class TelegramSignalBot:
    """Bot that processes trading signals and forwards to Telegram"""
    
    def __init__(self):
        self.config = Config()
        self.logger = self._setup_logging()
        self.signal_parser = SignalParser()
        
        # Telegram configuration
        self.bot_token = self.config.TELEGRAM_BOT_TOKEN
        self.application = None
        self.bot = None
        
        # Channel/chat configuration (you can set these)
        self.target_channel = None  # Set your channel ID here
        self.admin_user_id = None   # Set your user ID here
        
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
    
    async def setup_bot(self):
        """Initialize Telegram bot"""
        try:
            self.application = Application.builder().token(self.bot_token).build()
            self.bot = Bot(token=self.bot_token)
            
            # Add handlers
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("setchat", self.set_chat_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            
            # Handle all text messages as potential signals
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_signal)
            )
            
            self.logger.info("Telegram bot initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize bot: {e}")
            raise
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        message = """
🤖 *Signal Processing Bot*

Send me trading signals and I'll process and forward them!

*Commands:*
• `/start` - This message
• `/setchat` - Set target channel/chat
• `/status` - Bot status

*Usage:*
Just send trading signals as text messages.
        """
        
        await update.message.reply_text(message, parse_mode='Markdown')
        self.logger.info(f"User {update.effective_user.id} started bot")
    
    async def set_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set target chat/channel"""
        chat_id = update.effective_chat.id
        self.target_channel = chat_id
        
        await update.message.reply_text(
            f"✅ Target chat set to: `{chat_id}`\n"
            f"Signals will be forwarded here.",
            parse_mode='Markdown'
        )
        
        self.logger.info(f"Target channel set to {chat_id}")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot status"""
        status = f"""
📊 *Bot Status*

✅ *Online:* Active
🎯 *Target Channel:* `{self.target_channel or 'Not set'}`
🕒 *Time:* `{datetime.now().strftime('%H:%M:%S')}`

Ready to process signals!
        """
        
        await update.message.reply_text(status, parse_mode='Markdown')
    
    async def process_signal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process incoming signal messages"""
        try:
            signal_text = update.message.text
            user_id = update.effective_user.id
            
            self.logger.info(f"Processing signal from user {user_id}")
            
            # Parse the signal
            parsed_signal = await self.signal_parser.parse_signal(signal_text)
            
            if parsed_signal:
                # Format the signal
                formatted_signal = self._format_signal(parsed_signal, signal_text)
                
                # Send to user (confirmation)
                await update.message.reply_text(
                    "✅ Signal processed and forwarded!",
                    parse_mode='Markdown'
                )
                
                # Forward to target channel if set
                if self.target_channel:
                    await self.bot.send_message(
                        chat_id=self.target_channel,
                        text=formatted_signal,
                        parse_mode='Markdown'
                    )
                    
                    self.logger.info(f"Signal forwarded to channel {self.target_channel}")
                else:
                    await update.message.reply_text(
                        "⚠️ No target channel set. Use /setchat command."
                    )
                
            else:
                await update.message.reply_text(
                    "❌ Could not parse as trading signal. Please check format."
                )
                
        except Exception as e:
            self.logger.error(f"Error processing signal: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    def _format_signal(self, parsed_signal, original_text):
        """Format parsed signal for Telegram"""
        
        # Get direction emoji
        direction = parsed_signal.get('direction', '').upper()
        emoji = "🟢" if direction in ['LONG', 'BUY'] else "🔴" if direction in ['SHORT', 'SELL'] else "🔵"
        
        # Format the signal
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
{original_text[:200]}...
```
        """
        
        return formatted
    
    async def start_polling(self):
        """Start the bot polling"""
        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            self.logger.info("✅ Signal bot is running!")
            
            # Keep running
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            self.logger.error(f"Error in polling: {e}")
            raise
    
    async def stop(self):
        """Stop the bot"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
        
        self.logger.info("Bot stopped")

async def main():
    """Run the signal bot"""
    bot = TelegramSignalBot()
    
    try:
        print("🚀 Starting Telegram Signal Bot...")
        print("📡 Initializing bot...")
        
        await bot.setup_bot()
        
        print("✅ Bot ready!")
        print("📱 Send signals to process and forward")
        print("🎯 Use /setchat to set target channel")
        print("Press Ctrl+C to stop")
        
        await bot.start_polling()
        
    except KeyboardInterrupt:
        print("\n🛑 Stopping bot...")
        await bot.stop()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())