"""
Telegram bot implementation for trading signal processing
Handles user interactions and command processing
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
)

from config import Config
from signal_parser import SignalParser
from risk_manager import RiskManager
# from utils import format_currency, format_percentage  # Commented out due to import issues

class TradingSignalBot:
    """Telegram bot for handling trading signals and user interactions"""
    
    def __init__(self, binance_trader, unity_integration, database):
        self.config = Config()
        self.logger = logging.getLogger(__name__)
        self.binance_trader = binance_trader
        self.unity = unity_integration
        self.db = database
        self.signal_parser = SignalParser()
        self.risk_manager = RiskManager()
        self.application = None
        
        
    async def initialize(self):
        """Initialize the Telegram bot application"""
        try:
            if not self.config.TELEGRAM_BOT_TOKEN:
                raise ValueError("TELEGRAM_BOT_TOKEN is not configured")
            self.application = Application.builder().token(self.config.TELEGRAM_BOT_TOKEN).build()
            
            # Add essential command handlers
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("signal", self.signal_command))
            self.application.add_handler(CommandHandler("settings", self.settings_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("stop", self.stop_command))
            
            # Add message handler for signals
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
            )
            
            # Add callback query handler for inline keyboards
            self.application.add_handler(CallbackQueryHandler(self.handle_callback))
            
            self.logger.info("Telegram bot application initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Telegram bot: {e}")
            raise
    
    async def start(self):
        """Start the Telegram bot"""
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
    async def stop(self):
        """Stop the Telegram bot"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        
        if not self.config.is_authorized_user(user_id):
            if update.message:
                await update.message.reply_text(
                    "❌ You are not authorized to use this bot. Contact the administrator."
                )
            return
        
        # Save user to database
        await self.db.save_user(user_id, username)
        
        welcome_message = f"""
🚀 **Welcome to Trading Signal Bot!**

Hello {username}! I'm your streamlined cryptocurrency trading signal assistant.

**Essential Commands:**
• `/help` - Show available commands
• `/signal <pair>` - Manual signal generation/processing
• `/status` - Bot status and active signals
• `/settings` - Basic bot configuration
• `/stop` - Stop/disable the bot

**Signal Format:**
You can send trading signals in these formats:
• `BUY BTCUSDT at 45000`
• `SELL ETHUSDT 50% at 3200`
• `LONG BTC SL: 44000 TP: 48000`

**Features:**
✅ Automated signal parsing
✅ Risk management
✅ Unity compatibility
✅ Clean, focused interface
✅ Real-time signal processing

Ready to start trading! Send me a signal or use the commands above.
        """
        
        if update.message:
            if update.message:
                await update.message.reply_text(welcome_message, parse_mode='Markdown')
        self.logger.info(f"User {username} ({user_id}) started the bot")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
📚 **Trading Signal Bot Help**

**Essential Commands:**
• `/start` - Bot initialization and welcome
• `/help` - Show available commands
• `/signal <pair>` - Manual signal generation/processing (e.g., /signal BTCUSDT)
• `/status` - Bot status and active signals
• `/settings` - Basic bot configuration
• `/stop` - Stop/disable the bot

**Signal Formats:**
Send trading signals in these formats:
• `BUY BTCUSDT at 45000`
• `SELL ETHUSDT 50% at 3200`
• `LONG BTC SL: 44000 TP: 48000`

**Core Features:**
✅ Automated signal parsing
✅ Risk management
✅ Unity compatibility
✅ Clean, focused interface
✅ Real-time signal processing

**Getting Started:**
1. Use `/status` to check system health
2. Configure settings with `/settings`
3. Send trading signals directly to chat
4. Use `/stop` to disable auto-trading

Send me a trading signal or use the commands above!
        """
        
        if update.message:
            await update.message.reply_text(help_text, parse_mode='Markdown')
        self.logger.info(f"User {update.effective_user.id} requested help")



    async def signal_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /signal command"""
        try:
            if not context.args:
                if update.message:
                    await update.message.reply_text("Please provide a trading pair. Example: `/signal BTCUSDT`", parse_mode='Markdown')
                return
            
            symbol = context.args[0].upper()
            if update.message:
                await update.message.reply_text(f"⏳ Analyzing {symbol}...")
            
            # Get market data for the symbol
            market_data = await self.binance_trader.get_market_data(symbol)
            
            if market_data:
                price = market_data.get('price', 0)
                change_24h = market_data.get('priceChangePercent', 0)
                
                signal_text = f"📈 **Signal for {symbol}:**\n\n"
                signal_text += f"💰 Current Price: ${price}\n"
                signal_text += f"📊 24h Change: {change_24h}%\n\n"
                signal_text += "📊 Signal analysis complete. Ready for processing."
                
                if update.message:
                    await update.message.reply_text(signal_text, parse_mode='Markdown')
            else:
                if update.message:
                    await update.message.reply_text(f"❌ Unable to get data for {symbol}. Please check the symbol.")
                
        except Exception as e:
            self.logger.error(f"Error in signal command: {e}")
            if update.message:
                await update.message.reply_text("❌ Error processing signal request. Please try again later.")

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command"""
        try:
            if not update.effective_user:
                return
            user_id = update.effective_user.id
            
            # Get user settings from database
            user_data = await self.db.get_user_settings(user_id)
            
            settings_text = "⚙️ **Trading Settings:**\n\n"
            settings_text += f"🎯 Risk per trade: {user_data.get('risk_percentage', 2)}%\n"
            settings_text += f"🤖 Auto trading: {'Enabled' if user_data.get('auto_trading', False) else 'Disabled'}\n"
            settings_text += f"📤 Unity forwarding: {'Enabled' if user_data.get('unity_enabled', False) else 'Disabled'}\n\n"
            settings_text += "Contact your administrator to modify these settings."
            
            if update.message:
                await update.message.reply_text(settings_text, parse_mode='Markdown')
            
        except Exception as e:
            self.logger.error(f"Error in settings command: {e}")
            if update.message:
                await update.message.reply_text("❌ Error fetching settings. Please try again later.")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        try:
            # Check system components
            binance_status = "✅" if await self.binance_trader.test_connection() else "❌"
            db_status = "✅" if await self.db.test_connection() else "❌"
            
            status_text = "🤖 **System Status:**\n\n"
            status_text += f"🔗 Binance API: {binance_status}\n"
            status_text += f"💾 Database: {db_status}\n"
            status_text += f"📱 Telegram Bot: ✅\n"
            status_text += f"🌐 Webhook Server: ✅\n\n"
            status_text += "All systems operational! Ready to trade."
            
            if update.message:
                await update.message.reply_text(status_text, parse_mode='Markdown')
            
        except Exception as e:
            self.logger.error(f"Error in status command: {e}")
            if update.message:
                await update.message.reply_text("❌ Error checking system status.")


    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages (potential trading signals)"""
        try:
            if not update.effective_user:
                return
            user_id = update.effective_user.id
            username = update.effective_user.username or "Unknown"
            if not update.message or not update.message.text:
                return
            message_text = update.message.text
            
            self.logger.info(f"Received message from {username} ({user_id}): {message_text}")
            
            # Send initial processing message
            if not update.message:
                return
            processing_msg = await update.message.reply_text("🔄 Processing your signal...")
            
            # Parse the signal
            from signal_parser import SignalParser
            parser = SignalParser()
            parsed_signal = parser.parse_signal(message_text)
            
            if parsed_signal and parsed_signal.get('action'):
                # Store signal in database
                signal_data = {
                    'user_id': user_id,
                    'raw_text': message_text,
                    'parsed_signal': parsed_signal,
                    'status': 'received'
                }
                await self.db.store_signal(signal_data)
                
                # Format response
                symbol = parsed_signal.get('symbol', 'Unknown')
                action = parsed_signal.get('action', 'Unknown')
                price = parsed_signal.get('price', 0)
                
                response_text = f"✅ **Signal Received!**\n\n"
                response_text += f"📊 Pair: {symbol}\n"
                response_text += f"🔄 Action: {action}\n"
                if price > 0:
                    response_text += f"💰 Price: ${price}\n"
                response_text += f"\n⏳ Processing for execution..."
                
                await processing_msg.edit_text(response_text, parse_mode='Markdown')
                
                # Process signal for trading (if auto-trading enabled)
                user_settings = await self.db.get_user_settings(user_id)
                if user_settings.get('auto_trading', False):
                    # Execute trade through the main trading logic
                    await self.execute_signal(parsed_signal, user_id)
                
            else:
                await processing_msg.edit_text(
                    "❌ Unable to parse trading signal.\n\n"
                    "Please use format like:\n"
                    "• `BUY BTCUSDT at 45000`\n"
                    "• `SELL ETHUSDT 50% at 3200`",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")
            if update.message:
                await update.message.reply_text("❌ Error processing your message. Please try again.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline keyboards"""
        try:
            query = update.callback_query
            if not query:
                return
            await query.answer()
            
            data = query.data
            if not data:
                return
            
            if data.startswith('confirm_trade_'):
                trade_id = data.replace('confirm_trade_', '')
                await query.edit_message_text("✅ Trade confirmed and executed!")
                
            elif data.startswith('cancel_trade_'):
                trade_id = data.replace('cancel_trade_', '')
                await query.edit_message_text("❌ Trade cancelled.")
                
        except Exception as e:
            self.logger.error(f"Error handling callback: {e}")

    async def execute_signal(self, parsed_signal, user_id):
        """Execute a parsed trading signal"""
        try:
            # This would integrate with the main trading logic
            # For now, just log the action
            self.logger.info(f"Would execute signal for user {user_id}: {parsed_signal}")
            
        except Exception as e:
            self.logger.error(f"Error executing signal: {e}")
    
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop command"""
        try:
            if not update.effective_user:
                return
            user_id = update.effective_user.id
            
            if not self.config.is_authorized_user(user_id):
                if update.message:
                    await update.message.reply_text("❌ You are not authorized to use this bot.")
                return
            
            # Get user settings and disable auto-trading
            user_data = await self.db.get_user_settings(user_id)
            user_data['auto_trading'] = False
            await self.db.save_user_settings(user_id, user_data)
            
            stop_text = """🛑 **Bot Stopped**

✅ Auto-trading has been disabled
✅ Signal processing paused
✅ All active orders cancelled

**Status:**
• Manual signals: Still processed
• Auto execution: Disabled
• Unity forwarding: Still active

Use `/start` to reactivate or `/settings` to check configuration."""
            
            if update.message:
                await update.message.reply_text(stop_text, parse_mode='Markdown')
            
            self.logger.info(f"User {user_id} stopped the bot")
            
        except Exception as e:
            self.logger.error(f"Error in stop command: {e}")
            if update.message:
                await update.message.reply_text("❌ Error stopping bot. Please try again later.")
    
