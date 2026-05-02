#!/usr/bin/env python3
"""
Simple Telegram Trading Signal Bot
Focused only on processing and forwarding trading signals via Telegram
"""

import asyncio
import logging
import os
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from signal_parser import SignalParser
from risk_manager import RiskManager
from config import Config

class SimpleTradingBot:
    """Simple Telegram bot for trading signals"""
    
    def __init__(self):
        self.config = Config()
        self.logger = self._setup_logging()
        self.signal_parser = SignalParser()
        self.risk_manager = RiskManager()
        
        # Initialize Telegram bot
        self.bot_token = self.config.TELEGRAM_BOT_TOKEN
        self.application = None
        
    def _setup_logging(self):
        """Setup logging for the bot"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('telegram_bot.log'),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger(__name__)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_message = """
🤖 *Trading Signal Bot Active*

Welcome! I'm your trading signal assistant. Here's what I can do:

📊 *Commands:*
• `/start` - Show this welcome message
• `/status` - Check bot status
• `/help` - Show available commands

📈 *Signal Processing:*
• Send me trading signals and I'll process them
• I can parse various signal formats
• Risk management analysis included
• Formatted signals for easy reading

Send me a trading signal to get started!
        """
        
        await update.message.reply_text(
            welcome_message, 
            parse_mode='Markdown'
        )
        
        self.logger.info(f"User {update.effective_user.id} started the bot")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        status_message = f"""
📊 *Bot Status*

✅ *System Status:* Online
🕐 *Last Update:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🔧 *Mode:* Signal Processing
📈 *Supported Pairs:* {len(self.config.SUPPORTED_PAIRS)} pairs

*Ready to process trading signals!*
        """
        
        await update.message.reply_text(
            status_message,
            parse_mode='Markdown'
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_message = """
🆘 *Help & Commands*

*Available Commands:*
• `/start` - Welcome message
• `/status` - Bot status
• `/help` - This help message

*Signal Processing:*
• Send any trading signal message
• Supported formats: TradingView, manual signals, copy-paste
• I'll parse and format the signal for you

*Example Signal:*
```
BTCUSDT LONG
Entry: 45000
Stop Loss: 44000
Take Profit: 47000
Risk: 2%
```

Just send me your signal and I'll process it!
        """
        
        await update.message.reply_text(
            help_message,
            parse_mode='Markdown'
        )
    
    async def process_signal_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process incoming signal messages"""
        try:
            user_message = update.message.text
            user_id = update.effective_user.id
            
            self.logger.info(f"Processing signal from user {user_id}: {user_message[:50]}...")
            
            # Parse the signal
            parsed_signal = await self.signal_parser.parse_signal(user_message)
            
            if parsed_signal:
                # Apply risk management
                risk_analysis = await self.risk_manager.analyze_signal(parsed_signal)
                
                # Format the response
                formatted_response = self._format_signal_response(parsed_signal, risk_analysis)
                
                await update.message.reply_text(
                    formatted_response,
                    parse_mode='Markdown'
                )
                
                self.logger.info(f"Successfully processed signal for user {user_id}")
                
            else:
                # Signal couldn't be parsed
                await update.message.reply_text(
                    "❌ Could not parse this as a trading signal.\n\n"
                    "Please send a proper trading signal with:\n"
                    "• Trading pair (e.g., BTCUSDT)\n" 
                    "• Direction (LONG/SHORT/BUY/SELL)\n"
                    "• Entry price\n"
                    "• Stop loss (optional)\n"
                    "• Take profit (optional)\n\n"
                    "Use /help for examples.",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            self.logger.error(f"Error processing signal: {e}")
            await update.message.reply_text(
                f"❌ Error processing signal: {str(e)}\n\n"
                "Please try again or use /help for guidance."
            )
    
    def _format_signal_response(self, signal, risk_analysis):
        """Format the parsed signal into a nice response"""
        
        # Direction emoji
        direction_emoji = "🟢" if signal.get('direction', '').upper() in ['LONG', 'BUY'] else "🔴"
        
        response = f"""
{direction_emoji} *TRADING SIGNAL PROCESSED*

📊 *Pair:* `{signal.get('symbol', 'N/A')}`
📈 *Direction:* `{signal.get('direction', 'N/A').upper()}`
💰 *Entry:* `{signal.get('entry_price', 'N/A')}`

🛡️ *Risk Management:*
• *Stop Loss:* `{signal.get('stop_loss', 'Not set')}`
• *Take Profit:* `{signal.get('take_profit', 'Not set')}`
• *Risk Level:* `{risk_analysis.get('risk_level', 'Medium')}`

⚠️ *Analysis:*
{risk_analysis.get('analysis', 'Signal processed successfully')}

📅 *Time:* `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`
        """
        
        return response
    
    async def initialize(self):
        """Initialize the Telegram bot"""
        try:
            # Create application
            self.application = Application.builder().token(self.bot_token).build()
            
            # Add handlers
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            
            # Handle all text messages as potential signals
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_signal_message)
            )
            
            self.logger.info("Telegram bot initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Telegram bot: {e}")
            raise
    
    async def start(self):
        """Start the bot"""
        try:
            self.logger.info("Starting Telegram bot...")
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            self.logger.info("✅ Telegram bot is running and ready for signals!")
            
            # Keep the bot running
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            self.logger.error(f"Error starting bot: {e}")
            raise
    
    async def stop(self):
        """Stop the bot"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
        
        self.logger.info("Telegram bot stopped")

async def main():
    """Main function to run the simple Telegram bot"""
    bot = SimpleTradingBot()
    
    try:
        await bot.initialize()
        
        print("🚀 Simple Telegram Trading Signal Bot Starting...")
        print("📱 Processing trading signals via Telegram")
        print("🔄 Bot is ready to receive signals")
        print("Press Ctrl+C to stop...")
        
        await bot.start()
        
    except KeyboardInterrupt:
        print("\n🛑 Shutting down bot...")
        await bot.stop()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())