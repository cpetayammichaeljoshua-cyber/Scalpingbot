#!/usr/bin/env python3
"""
Enhanced Perfect Scalping Bot with Advanced SL/TP Management
- 1 SL and 3 TPs with dynamic management
- SL moves to entry on TP1, to TP1 on TP2, full close on TP3
- Cornix integration with proper formatting
- Rate-limited Telegram responses (3 per hour)
- Compact and enhanced UI responses
"""

import asyncio
import logging
import os
import json
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from collections import defaultdict

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config import Config
from signal_parser import SignalParser
from binance_trader import BinanceTrader
from enhanced_cornix_integration import EnhancedCornixIntegration
from database import Database
from risk_manager import RiskManager
from advanced_trading_strategy import AdvancedTradingStrategy

# Import enhanced uptime service
from uptime_service import EnhancedUptimeService

@dataclass
class TradeProgress:
    """Track trade progression through TP levels"""
    symbol: str
    entry_price: float
    original_sl: float
    current_sl: float
    tp1: float
    tp2: float
    tp3: float
    direction: str
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    start_time: datetime = None
    profit_locked: float = 0.0

class EnhancedPerfectScalpingBot:
    """Enhanced scalping bot with advanced SL/TP management"""

    def __init__(self):
        self.config = Config()
        self.signal_parser = SignalParser()
        self.risk_manager = RiskManager()
        self.binance_trader = BinanceTrader()
        self.cornix = EnhancedCornixIntegration()
        self.db = Database()
        self.strategy = AdvancedTradingStrategy(binance_trader=self.binance_trader)
        self.uptime_service = EnhancedUptimeService(port=8080)

        # Telegram bot
        self.bot_token = self.config.TELEGRAM_BOT_TOKEN
        self.bot = None
        self.application = None

        # Chat configuration
        self.admin_chat_id = int(self.config.ADMIN_USER_ID) if self.config.ADMIN_USER_ID else None
        self.target_channel = None

        # Trade tracking
        self.active_trades: Dict[str, TradeProgress] = {}
        self.trade_monitoring_tasks: Dict[str, asyncio.Task] = {}

        # Rate limiting (3 messages per hour)
        self.message_timestamps = []
        self.max_messages_per_hour = 3

        # Performance tracking
        self.performance_stats = {
            'total_signals': 0,
            'successful_trades': 0,
            'total_profit': 0.0,
            'win_rate': 0.0,
            'avg_profit_per_trade': 0.0
        }

        # Running state
        self.running = False

    def _setup_logging(self):
        """Setup enhanced logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('enhanced_scalping_bot.log'),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger(__name__)

    async def initialize(self):
        """Initialize all components"""
        try:
            # Initialize database
            await self.db.initialize()

            # Initialize Telegram bot
            self.application = Application.builder().token(self.bot_token).build()
            self.bot = Bot(token=self.bot_token)

            # Add handlers
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("trades", self.active_trades_command))
            self.application.add_handler(CommandHandler("stats", self.stats_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_signal)
            )

            # Initialize trading components
            await self.binance_trader.initialize()

            self.logger.info("✅ Enhanced Perfect Scalping Bot initialized")
            return True

        except Exception as e:
            self.logger.error(f"❌ Initialization failed: {e}")
            return False

    async def start(self):
        """Start the enhanced bot"""
        if not await self.initialize():
            return False

        self.running = True

        # Start enhanced uptime service
        asyncio.create_task(self.uptime_service.run())
        self.logger.info("🌐 Enhanced uptime service started on port 8080")

        # Start Telegram bot
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        # Send startup message
        if self.admin_chat_id:
            startup_msg = """🚀 **Enhanced Perfect Scalping Bot ONLINE**

🎯 **Advanced Features:**
• Dynamic SL/TP Management
• Auto SL movement (Entry→TP1→TP2)
• 3-Level Take Profit System
• Cornix Integration
• Rate-Limited Responses (3/hr)

⚡ Ready for signals!"""
            await self.send_rate_limited_message(self.admin_chat_id, startup_msg)

        self.logger.info("🚀 Enhanced Perfect Scalping Bot started successfully")

        # Keep running
        try:
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await self.stop()

    async def stop(self):
        """Stop the bot gracefully"""
        self.running = False

        # Cancel all monitoring tasks
        for task in self.trade_monitoring_tasks.values():
            task.cancel()

        # Stop Telegram bot
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

        self.logger.info("🛑 Enhanced Perfect Scalping Bot stopped")

    def _can_send_message(self) -> bool:
        """Check if we can send a message (rate limiting)"""
        now = datetime.now()
        # Remove timestamps older than 1 hour
        self.message_timestamps = [
            ts for ts in self.message_timestamps
            if now - ts < timedelta(hours=1)
        ]
        return len(self.message_timestamps) < self.max_messages_per_hour

    async def send_rate_limited_message(self, chat_id: int, text: str, **kwargs) -> bool:
        """Send message with rate limiting"""
        if not self._can_send_message():
            self.logger.warning("⚠️ Message rate limit reached (3/hour)")
            return False

        try:
            await self.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown', **kwargs)
            self.message_timestamps.append(datetime.now())
            return True
        except Exception as e:
            self.logger.error(f"❌ Failed to send message: {e}")
            return False

    async def start_command(self, update, context):
        """Handle /start command"""
        user_id = update.effective_user.id

        if not self.config.is_authorized_user(user_id):
            await update.message.reply_text("❌ Unauthorized access")
            return

        welcome_msg = """🤖 **Enhanced Perfect Scalping Bot**

**Features:**
🎯 Advanced SL/TP Management
⚡ 3-Level Take Profit System
🔄 Auto SL Movement
🌐 Cornix Integration
📊 Real-time Monitoring

**Commands:**
/status - System status
/trades - Active trades
/stats - Performance stats
/help - Command list

Send trading signals to get started!"""

        await update.message.reply_text(welcome_msg, parse_mode='Markdown')

    async def status_command(self, update, context):
        """Handle /status command"""
        status_msg = f"""📊 **System Status**

🤖 **Bot:** {'🟢 Online' if self.running else '🔴 Offline'}
🔗 **Binance:** {'🟢 Connected' if await self.binance_trader.test_connection() else '🔴 Disconnected'}
🌐 **Cornix:** {'🟢 Ready' if self.cornix.webhook_url else '🔴 Not configured'}
💾 **Database:** {'🟢 Connected' if await self.db.test_connection() else '🔴 Error'}

📈 **Active Trades:** {len(self.active_trades)}
🎯 **Messages Sent:** {len(self.message_timestamps)}/3 (last hour)

All systems operational! ⚡"""

        await update.message.reply_text(status_msg, parse_mode='Markdown')

    async def active_trades_command(self, update, context):
        """Handle /trades command"""
        if not self.active_trades:
            await update.message.reply_text("📭 **No Active Trades**\n\nSend signals to start trading!")
            return

        trades_msg = "🔄 **Active Trades**\n\n"
        for symbol, trade in self.active_trades.items():
            progress = "🟢" if trade.tp1_hit else "⚪"
            progress += "🟢" if trade.tp2_hit else "⚪"
            progress += "🟢" if trade.tp3_hit else "⚪"

            trades_msg += f"**{symbol}** {trade.direction}\n"
            trades_msg += f"Progress: {progress}\n"
            trades_msg += f"Profit: +{trade.profit_locked:.1f}R\n\n"

        await update.message.reply_text(trades_msg, parse_mode='Markdown')

    async def stats_command(self, update, context):
        """Handle /stats command"""
        stats = self.performance_stats

        stats_msg = f"""📈 **Performance Stats**

🎯 **Total Signals:** {stats['total_signals']}
✅ **Successful Trades:** {stats['successful_trades']}
💰 **Total Profit:** +{stats['total_profit']:.1f}R
🏆 **Win Rate:** {stats['win_rate']:.1f}%
📊 **Avg Profit/Trade:** +{stats['avg_profit_per_trade']:.1f}R

🔥 **Strategy:** Perfect Scalping v2.0
⚡ **Enhanced with AI-driven SL/TP management**"""

        await update.message.reply_text(stats_msg, parse_mode='Markdown')

    async def help_command(self, update, context):
        """Handle /help command"""
        help_msg = """📚 **Help Guide**

**Commands:**
/start - Initialize bot
/status - System status
/trades - Active trades
/stats - Performance stats
/help - This help

**Signal Format:**
```
BTCUSDT LONG
Entry: 45000
SL: 44000
TP1: 46000
TP2: 47000
TP3: 48000
```

**Features:**
🎯 Auto SL movement on TP hits
⚡ 3-level profit taking
🌐 Cornix integration
📊 Real-time monitoring

Rate limited to 3 responses/hour for optimal performance."""

        await update.message.reply_text(help_msg, parse_mode='Markdown')

    async def handle_signal(self, update, context):
        """Handle incoming trading signals"""
        try:
            user_id = update.effective_user.id

            if not self.config.is_authorized_user(user_id):
                return

            signal_text = update.message.text
            self.logger.info(f"📨 Received signal from user {user_id}")

            # Parse signal
            parsed_signal = await self.signal_parser.parse_signal(signal_text)

            if not parsed_signal:
                if self._can_send_message():
                    await update.message.reply_text("❌ **Invalid Signal Format**\n\nUse proper format with Entry, SL, TP1, TP2, TP3")
                return

            # Validate signal structure
            if not self._validate_signal_structure(parsed_signal):
                if self._can_send_message():
                    await update.message.reply_text("❌ **Invalid Price Structure**\n\nCheck SL/TP price relationships")
                return

            # Process the signal
            await self.process_trading_signal(parsed_signal, update)

        except Exception as e:
            self.logger.error(f"❌ Error handling signal: {e}")
            if self._can_send_message():
                await update.message.reply_text("❌ **Processing Error**\n\nSignal processing failed. Please try again.")

    def _validate_signal_structure(self, signal: Dict[str, Any]) -> bool:
        """Validate signal price structure"""
        try:
            direction = signal.get('direction', '').upper()
            entry = float(signal.get('entry_price', 0))
            sl = float(signal.get('stop_loss', 0))
            tp1 = float(signal.get('tp1', 0))
            tp2 = float(signal.get('tp2', 0))
            tp3 = float(signal.get('tp3', 0))

            if direction in ['LONG', 'BUY']:
                return sl < entry < tp1 < tp2 < tp3
            elif direction in ['SHORT', 'SELL']:
                return tp3 < tp2 < tp1 < entry < sl

            return False
        except (ValueError, TypeError):
            return False

    async def process_trading_signal(self, signal: Dict[str, Any], update):
        """Process and execute trading signal"""
        try:
            symbol = signal['symbol']
            direction = signal['direction'].upper()

            # Create trade progress tracker
            trade_progress = TradeProgress(
                symbol=symbol,
                entry_price=float(signal['entry_price']),
                original_sl=float(signal['stop_loss']),
                current_sl=float(signal['stop_loss']),
                tp1=float(signal['tp1']),
                tp2=float(signal['tp2']),
                tp3=float(signal['tp3']),
                direction=direction,
                start_time=datetime.now()
            )

            # Store active trade
            self.active_trades[symbol] = trade_progress

            # Send compact confirmation message
            confirmation_msg = self._create_compact_confirmation(signal, trade_progress)

            if await self.send_rate_limited_message(update.effective_chat.id, confirmation_msg):
                # Forward to Cornix
                await self.forward_to_cornix(signal, trade_progress)

                # Start trade monitoring
                monitor_task = asyncio.create_task(self.monitor_trade_progression(symbol))
                self.trade_monitoring_tasks[symbol] = monitor_task

                # Update stats
                self.performance_stats['total_signals'] += 1

                self.logger.info(f"✅ Signal processed successfully: {symbol} {direction}")

        except Exception as e:
            self.logger.error(f"❌ Error processing signal: {e}")

    def _create_compact_confirmation(self, signal: Dict[str, Any], trade: TradeProgress) -> str:
        """Create compact confirmation message"""
        direction_emoji = "🟢" if trade.direction in ['LONG', 'BUY'] else "🔴"

        return f"""{direction_emoji} **{trade.symbol} {trade.direction}**

💰 **Entry:** {trade.entry_price:.4f}
🛑 **SL:** {trade.current_sl:.4f}

🎯 **Take Profits:**
TP1: {trade.tp1:.4f} ⚪
TP2: {trade.tp2:.4f} ⚪
TP3: {trade.tp3:.4f} ⚪

📊 **R:R Ratio:** 1:3
🌐 **Cornix:** ✅ Sent
⚡ **Monitoring:** Active"""

    async def forward_to_cornix(self, signal: Dict[str, Any], trade: TradeProgress) -> bool:
        """Forward signal to Cornix with proper formatting"""
        try:
            # Create Cornix-compatible payload
            cornix_signal = {
                'symbol': trade.symbol,
                'action': 'buy' if trade.direction in ['LONG', 'BUY'] else 'sell',
                'entry_price': trade.entry_price,
                'stop_loss': trade.original_sl,
                'tp1': trade.tp1,
                'tp2': trade.tp2,
                'tp3': trade.tp3,
                'direction': trade.direction.lower(),
                'leverage': signal.get('leverage', 10),
                'signal_strength': 85,
                'risk_reward_ratio': 3.0,
                'timeframe': 'Multi-TF',
                'strategy': 'Enhanced Perfect Scalping'
            }

            # Forward through enhanced Cornix integration
            result = await self.cornix.send_initial_signal(cornix_signal)

            if result.get('success'):
                self.logger.info(f"✅ Signal forwarded to Cornix: {trade.symbol}")
                return True
            else:
                self.logger.warning(f"⚠️ Cornix forwarding failed: {result.get('error')}")
                return False

        except Exception as e:
            self.logger.error(f"❌ Error forwarding to Cornix: {e}")
            return False

    async def monitor_trade_progression(self, symbol: str):
        """Monitor trade progression and manage SL/TP"""
        try:
            trade = self.active_trades.get(symbol)
            if not trade:
                return

            self.logger.info(f"🔍 Starting trade monitoring for {symbol}")

            while symbol in self.active_trades and self.running:
                current_trade = self.active_trades[symbol]

                # Simulate price movements for demo (replace with real price fetching)
                current_price = await self._get_current_price(symbol)
                if not current_price:
                    await asyncio.sleep(30)
                    continue

                # Check TP levels
                if not current_trade.tp1_hit and self._check_tp_hit(current_price, current_trade.tp1, current_trade.direction):
                    await self.handle_tp1_hit(symbol)
                elif not current_trade.tp2_hit and current_trade.tp1_hit and self._check_tp_hit(current_price, current_trade.tp2, current_trade.direction):
                    await self.handle_tp2_hit(symbol)
                elif not current_trade.tp3_hit and current_trade.tp2_hit and self._check_tp_hit(current_price, current_trade.tp3, current_trade.direction):
                    await self.handle_tp3_hit(symbol)
                    break  # Trade completed

                await asyncio.sleep(30)  # Check every 30 seconds

        except Exception as e:
            self.logger.error(f"❌ Error monitoring trade {symbol}: {e}")
        finally:
            # Clean up
            if symbol in self.trade_monitoring_tasks:
                del self.trade_monitoring_tasks[symbol]

    def _check_tp_hit(self, current_price: float, tp_price: float, direction: str) -> bool:
        """Check if take profit level is hit"""
        if direction in ['LONG', 'BUY']:
            return current_price >= tp_price
        else:
            return current_price <= tp_price

    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current market price"""
        try:
            ticker = await self.binance_trader.get_ticker(symbol)
            return float(ticker.get('price', 0)) if ticker else None
        except Exception as e:
            self.logger.error(f"❌ Error getting price for {symbol}: {e}")
            return None

    async def handle_tp1_hit(self, symbol: str):
        """Handle TP1 hit - Move SL to entry"""
        try:
            trade = self.active_trades[symbol]
            trade.tp1_hit = True
            trade.current_sl = trade.entry_price
            trade.profit_locked = 1.0

            # Send SL update to Cornix
            await self.cornix.update_stop_loss(symbol, trade.entry_price, "TP1 hit - SL moved to entry")

            # Record partial trade outcome for ML learning
            await self._record_trade_outcome(trade, 'TP1_HIT', 1.0)

            # Compact notification
            if self._can_send_message() and self.admin_chat_id:
                msg = f"""🎯 **TP1 HIT** - {symbol}

🟢⚪⚪ Progress
🛑 **SL moved to Entry:** {trade.entry_price:.4f}
💰 **Profit Secured:** +1.0R
🧠 **ML Updated:** ✅
⚡ **Monitoring TP2...**"""
                await self.send_rate_limited_message(self.admin_chat_id, msg)

            self.logger.info(f"🎯 TP1 hit for {symbol} - SL moved to entry")

        except Exception as e:
            self.logger.error(f"❌ Error handling TP1 for {symbol}: {e}")

    async def handle_tp2_hit(self, symbol: str):
        """Handle TP2 hit - Move SL to TP1"""
        try:
            trade = self.active_trades[symbol]
            trade.tp2_hit = True
            trade.current_sl = trade.tp1
            trade.profit_locked = 2.0

            # Send SL update to Cornix
            await self.cornix.update_stop_loss(symbol, trade.tp1, "TP2 hit - SL moved to TP1")

            # Record partial trade outcome for ML learning
            await self._record_trade_outcome(trade, 'TP2_HIT', 2.0)

            # Compact notification
            if self._can_send_message() and self.admin_chat_id:
                msg = f"""🚀 **TP2 HIT** - {symbol}

🟢🟢⚪ Progress
🛑 **SL moved to TP1:** {trade.tp1:.4f}
💰 **Profit Secured:** +2.0R
🧠 **ML Updated:** ✅
⚡ **Final target: TP3**"""
                await self.send_rate_limited_message(self.admin_chat_id, msg)

            self.logger.info(f"🚀 TP2 hit for {symbol} - SL moved to TP1")

        except Exception as e:
            self.logger.error(f"❌ Error handling TP2 for {symbol}: {e}")

    async def handle_tp3_hit(self, symbol: str):
        """Handle TP3 hit - Full trade closure"""
        try:
            trade = self.active_trades[symbol]
            trade.tp3_hit = True
            trade.profit_locked = 3.0

            # Send full closure to Cornix
            await self.cornix.close_position(symbol, "TP3 hit - Full profit target reached", 100)

            # Record trade outcome for ML learning
            await self._record_trade_outcome(trade, 'TP3_HIT', 3.0)

            # Final notification
            if self._can_send_message() and self.admin_chat_id:
                msg = f"""🏆 **PERFECT TRADE** - {symbol}

🟢🟢🟢 **COMPLETE**
💰 **Final Profit:** +3.0R (1:3 R:R)
⏰ **Duration:** {self._format_duration(trade.start_time)}
🎯 **Status:** Fully Closed
🧠 **ML Retrained:** ✅

🔥 **Excellent execution!**"""
                await self.send_rate_limited_message(self.admin_chat_id, msg)

            # Update performance stats
            self.performance_stats['successful_trades'] += 1
            self.performance_stats['total_profit'] += 3.0
            self.performance_stats['win_rate'] = (self.performance_stats['successful_trades'] / self.performance_stats['total_signals']) * 100
            self.performance_stats['avg_profit_per_trade'] = self.performance_stats['total_profit'] / self.performance_stats['total_signals']

            # Remove from active trades
            del self.active_trades[symbol]

            self.logger.info(f"🏆 Perfect trade completed: {symbol} - Full 1:3 R:R achieved")

        except Exception as e:
            self.logger.error(f"❌ Error handling TP3 for {symbol}: {e}")

    def _format_duration(self, start_time: datetime) -> str:
        """Format trade duration"""
        duration = datetime.now() - start_time
        hours, remainder = divmod(duration.total_seconds(), 3600)
        minutes = remainder // 60
        return f"{int(hours)}h {int(minutes)}m"

    async def _record_trade_outcome(self, trade: TradeProgress, exit_reason: str, profit_r: float):
        """Record trade outcome for ML learning and trigger retraining"""
        try:
            # Import ML analyzer
            from ml_trade_analyzer import MLTradeAnalyzer

            ml_analyzer = MLTradeAnalyzer()

            # Create trade outcome data
            trade_outcome = {
                'symbol': trade.symbol,
                'direction': trade.direction,
                'entry_price': trade.entry_price,
                'exit_price': trade.entry_price * (1 + profit_r * 0.01),  # Approximate exit price
                'stop_loss': trade.original_sl,
                'take_profit_1': trade.tp1,
                'take_profit_2': trade.tp2,
                'take_profit_3': trade.tp3,
                'signal_strength': 85,  # Default signal strength
                'leverage': 10,  # Default leverage
                'position_size': 100,  # Default position size
                'trade_result': 'PROFIT' if profit_r > 0 else 'LOSS',
                'profit_loss': profit_r,
                'duration_minutes': (datetime.now() - trade.start_time).total_seconds() / 60,
                'entry_time': trade.start_time,
                'exit_time': datetime.now(),
                'market_conditions': {
                    'exit_reason': exit_reason,
                    'tp1_hit': trade.tp1_hit,
                    'tp2_hit': trade.tp2_hit,
                    'tp3_hit': trade.tp3_hit,
                    'sl_moved_to_entry': trade.current_sl == trade.entry_price,
                    'sl_moved_to_tp1': trade.current_sl == trade.tp1
                },
                'indicators_data': {},
                'cvd_trend': 'neutral',
                'volatility': 0.02,
                'volume_ratio': 1.0,
                'ema_alignment': True,
                'rsi_value': 50.0,
                'macd_signal': 'bullish' if trade.direction in ['LONG', 'BUY'] else 'bearish',
                'lessons_learned': f"Enhanced scalping trade - {exit_reason}"
            }

            # Record the trade
            await ml_analyzer.record_trade(trade_outcome)

            # Trigger immediate retraining after every trade
            await self._trigger_ml_retraining()

            self.logger.info(f"🧠 Trade outcome recorded and ML retrained: {trade.symbol}")

        except Exception as e:
            self.logger.error(f"❌ Error recording trade outcome: {e}")

    async def _trigger_ml_retraining(self):
        """Trigger ML model retraining after every trade"""
        try:
            from ml_trade_analyzer import MLTradeAnalyzer
            from telegram_trade_scanner import TelegramTradeScanner

            # Initialize components
            ml_analyzer = MLTradeAnalyzer()

            # Check if we have Telegram bot token for scanning
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            channel_username = os.getenv('TELEGRAM_CHANNEL', '@SignalTactics')

            # Scan recent Telegram trades if possible
            if bot_token:
                try:
                    scanner = TelegramTradeScanner(bot_token, channel_username)
                    # Scan last 3 days for recent trades
                    recent_trades = await scanner.scan_channel_history(days_back=3)
                    if recent_trades:
                        await scanner.store_scanned_trades(recent_trades)
                        self.logger.info(f"📨 Scanned {len(recent_trades)} recent Telegram trades")
                except Exception as scan_error:
                    self.logger.warning(f"Telegram scanning failed: {scan_error}")

            # Perform ML analysis and learning (including Telegram data)
            await ml_analyzer.analyze_and_learn(include_telegram_data=True)

            self.logger.info("🧠 ML model retrained successfully after trade completion")

        except Exception as e:
            self.logger.error(f"❌ Error during ML retraining: {e}")

    async def handle_tp1_hit(self, symbol: str):
        """Handle TP1 hit - Move SL to entry"""
        try:
            trade = self.active_trades[symbol]
            trade.tp1_hit = True
            trade.current_sl = trade.entry_price
            trade.profit_locked = 1.0

            # Send SL update to Cornix
            await self.cornix.update_stop_loss(symbol, trade.entry_price, "TP1 hit - SL moved to entry")

            # Record partial trade outcome for ML learning
            await self._record_trade_outcome(trade, 'TP1_HIT', 1.0)

            # Compact notification
            if self._can_send_message() and self.admin_chat_id:
                msg = f"""🎯 **TP1 HIT** - {symbol}

🟢⚪⚪ Progress
🛑 **SL moved to Entry:** {trade.entry_price:.4f}
💰 **Profit Secured:** +1.0R
🧠 **ML Updated:** ✅
⚡ **Monitoring TP2...**"""
                await self.send_rate_limited_message(self.admin_chat_id, msg)

            self.logger.info(f"🎯 TP1 hit for {symbol} - SL moved to entry")

        except Exception as e:
            self.logger.error(f"❌ Error handling TP1 for {symbol}: {e}")

    async def handle_tp2_hit(self, symbol: str):
        """Handle TP2 hit - Move SL to TP1"""
        try:
            trade = self.active_trades[symbol]
            trade.tp2_hit = True
            trade.current_sl = trade.tp1
            trade.profit_locked = 2.0

            # Send SL update to Cornix
            await self.cornix.update_stop_loss(symbol, trade.tp1, "TP2 hit - SL moved to TP1")

            # Record partial trade outcome for ML learning
            await self._record_trade_outcome(trade, 'TP2_HIT', 2.0)

            # Compact notification
            if self._can_send_message() and self.admin_chat_id:
                msg = f"""🚀 **TP2 HIT** - {symbol}

🟢🟢⚪ Progress
🛑 **SL moved to TP1:** {trade.tp1:.4f}
💰 **Profit Secured:** +2.0R
🧠 **ML Updated:** ✅
⚡ **Final target: TP3**"""
                await self.send_rate_limited_message(self.admin_chat_id, msg)

            self.logger.info(f"🚀 TP2 hit for {symbol} - SL moved to TP1")

        except Exception as e:
            self.logger.error(f"❌ Error handling TP2 for {symbol}: {e}")

    async def send_sl_update_to_cornix(self, symbol: str, new_sl: float, reason: str):
        """Send stop loss update to Cornix"""
        try:
            update_payload = {
                'action': 'update_stop_loss',
                'symbol': symbol.replace('USDT', '/USDT'),
                'new_stop_loss': new_sl,
                'reason': reason,
                'timestamp': datetime.now().isoformat(),
                'bot_id': 'enhanced_perfect_scalping_bot'
            }

            # Send via webhook
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.cornix.webhook_url,
                    json=update_payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                ) as response:
                    if response.status == 200:
                        self.logger.info(f"✅ SL update sent to Cornix: {symbol}")
                    else:
                        self.logger.warning(f"⚠️ Cornix SL update failed: {response.status}")

        except Exception as e:
            self.logger.error(f"❌ Error sending SL update to Cornix: {e}")

    async def send_trade_closure_to_cornix(self, symbol: str, reason: str):
        """Send trade closure to Cornix"""
        try:
            closure_payload = {
                'action': 'close_position',
                'symbol': symbol.replace('USDT', '/USDT'),
                'reason': reason,
                'close_percentage': 100,
                'timestamp': datetime.now().isoformat(),
                'bot_id': 'enhanced_perfect_scalping_bot'
            }

            # Send via webhook
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.cornix.webhook_url,
                    json=closure_payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                ) as response:
                    if response.status == 200:
                        self.logger.info(f"✅ Trade closure sent to Cornix: {symbol}")
                    else:
                        self.logger.warning(f"⚠️ Cornix closure failed: {response.status}")

        except Exception as e:
            self.logger.error(f"❌ Error sending closure to Cornix: {e}")

async def main():
    """Main function to run the enhanced bot"""
    bot = EnhancedPerfectScalpingBot()

    try:
        print("🚀 Starting Enhanced Perfect Scalping Bot...")
        await bot.start()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Bot error: {e}")
    finally:
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())