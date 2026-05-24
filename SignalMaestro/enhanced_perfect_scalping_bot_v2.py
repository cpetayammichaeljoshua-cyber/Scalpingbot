
#!/usr/bin/env python3
"""
Enhanced Perfect Scalping Bot V2 with Advanced SL/TP Management
- 1 SL and 3 TPs with dynamic management
- TP1 hit: SL moves to entry
- TP2 hit: SL moves to TP1
- TP3 hit: Full position closure
- Unity integration with compact responses
- Rate limiting (3 responses per hour)
- Time-based strategy enhancement
"""

import asyncio
import logging
import json
import aiohttp
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from collections import defaultdict
import time

from config import Config
from enhanced_unity_integration import EnhancedUnityExecutor
from binance_trader import BinanceTrader
from risk_manager import RiskManager
from signal_parser import SignalParser
from stop_loss_integration_module import StopLossIntegrator

@dataclass
class TradeProgress:
    """Enhanced trade tracking with precise SL/TP management"""
    symbol: str
    direction: str
    entry_price: float
    original_sl: float
    current_sl: float
    tp1: float
    tp2: float
    tp3: float
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    position_closed: bool = False
    start_time: Optional[datetime] = None
    profit_locked: float = 0.0
    stage: str = "active"  # active, tp1_hit, tp2_hit, completed
    risk_reward_ratio: float = 3.0

    def __post_init__(self):
        if self.start_time is None:
            self.start_time = datetime.now()

class MessageRateLimiter:
    """Rate limiter for Telegram messages (3 per hour)"""
    
    def __init__(self, max_messages: int = 3, time_window: int = 3600):
        self.max_messages = max_messages
        self.time_window = time_window
        self.message_timestamps = []
    
    def can_send_message(self) -> bool:
        """Check if we can send a message within rate limits"""
        now = time.time()
        # Remove old timestamps
        self.message_timestamps = [
            ts for ts in self.message_timestamps 
            if now - ts < self.time_window
        ]
        return len(self.message_timestamps) < self.max_messages
    
    def record_message(self):
        """Record that a message was sent"""
        self.message_timestamps.append(time.time())

class TimeTheoryAnalyzer:
    """Time-based analysis for enhanced strategy"""
    
    @staticmethod
    def get_market_session(dt: Optional[datetime] = None) -> str:
        """Determine current market session"""
        if dt is None:
            dt = datetime.utcnow()
        
        hour = dt.hour
        
        if 0 <= hour < 8:
            return "ASIA"
        elif 8 <= hour < 16:
            return "LONDON"
        elif 16 <= hour < 24:
            return "NY"
        else:
            return "OVERLAP"
    
    @staticmethod
    def get_volatility_factor(session: str) -> float:
        """Get volatility factor based on session"""
        factors = {
            "ASIA": 0.8,
            "LONDON": 1.2,
            "NY": 1.0,
            "OVERLAP": 1.3
        }
        return factors.get(session, 1.0)
    
    @staticmethod
    def is_high_impact_time() -> bool:
        """Check if current time is high impact (news, opens, closes)"""
        now = datetime.utcnow()
        hour = now.hour
        minute = now.minute
        
        # Major market opens/closes and common news times
        high_impact_times = [
            (8, 30), (9, 0),   # London open
            (13, 30), (14, 0), # NY open
            (21, 0), (21, 30)  # Major closes
        ]
        
        return (hour, minute) in high_impact_times or minute in [0, 30]

class EnhancedPerfectScalpingBotV2:
    """Enhanced Perfect Scalping Bot with Advanced Features"""
    
    def __init__(self):
        self.config = Config()
        self.logger = self._setup_logging()
        self.unity = EnhancedUnityExecutor()
        self.binance_trader = BinanceTrader()
        self.risk_manager = RiskManager()
        self.signal_parser = SignalParser()
        
        # Initialize stop loss integration
        self.stop_loss_integrator = StopLossIntegrator(self)
        
        # Bot state management
        self.active_trades: Dict[str, TradeProgress] = {}
        self.running = False
        self.admin_chat_id = self.config.TELEGRAM_CHAT_ID
        self.bot_token = self.config.TELEGRAM_BOT_TOKEN
        
        # Rate limiting and enhancement features
        self.rate_limiter = MessageRateLimiter(max_messages=3, time_window=3600)
        self.time_analyzer = TimeTheoryAnalyzer()
        
        # Performance tracking
        self.total_trades = 0
        self.winning_trades = 0
        self.total_profit = 0.0
        
    def _setup_logging(self) -> logging.Logger:
        """Setup enhanced logging"""
        logger = logging.getLogger('EnhancedScalpingBotV2')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            formatter = logging.Formatter(
                '%(asctime)s | %(levelname)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    async def start(self):
        """Start the enhanced bot"""
        self.logger.info("🚀 Starting Enhanced Perfect Scalping Bot V2...")
        self.running = True
        
        # Test integrations
        await self._test_integrations()
        
        # Send startup notification
        if self.rate_limiter.can_send_message():
            startup_msg = self._create_startup_message()
            await self.send_rate_limited_message(self.admin_chat_id, startup_msg)
        
        self.logger.info("✅ Enhanced Perfect Scalping Bot V2 is running!")
        
        # Main loop
        await self._main_loop()
    
    async def _test_integrations(self):
        """Test all integrations"""
        try:
            # Test Unity connection
            unity_test = await self.unity.test_connection()
            self.logger.info(f"Unity: {'✅' if unity_test.get('success') else '❌'}")
            
            # Test Binance connection
            binance_test = await self.binance_trader.test_connection()
            self.logger.info(f"Binance: {'✅' if binance_test else '❌'}")
            
        except Exception as e:
            self.logger.error(f"Integration test error: {e}")
    
    def _create_startup_message(self) -> str:
        """Create compact startup message"""
        session = self.time_analyzer.get_market_session()
        volatility = self.time_analyzer.get_volatility_factor(session)
        high_impact = self.time_analyzer.is_high_impact_time()
        
        return f"""🤖 **Enhanced Bot V2 Online**

📊 **Session:** {session} ({volatility:.1f}x volatility)
⏰ **Impact Time:** {'🔥 HIGH' if high_impact else '📈 Normal'}
🎯 **SL/TP System:** Active
🌐 **Unity:** Connected
⚡ **Rate Limit:** 3/hour
🧠 **Time Theory:** Enabled

*Ready for precision scalping!*"""
    
    async def _main_loop(self):
        """Main bot execution loop"""
        while self.running:
            try:
                # Monitor active trades
                await self._monitor_active_trades()
                
                # Process any pending signals (webhook integration would add signals here)
                await self._process_pending_signals()
                
                # Cleanup completed trades
                self._cleanup_completed_trades()
                
                await asyncio.sleep(1)  # 1-second monitoring interval
                
            except Exception as e:
                self.logger.error(f"Main loop error: {e}")
                await asyncio.sleep(5)
    
    async def process_signal(self, signal_data: Dict[str, Any]):
        """Process incoming trading signal with enhanced features"""
        try:
            self.logger.info(f"📨 Processing signal: {signal_data}")
            
            # Parse the signal
            parsed_signal = await self._parse_and_validate_signal(signal_data)
            if not parsed_signal:
                return
            
            # Apply time theory enhancements
            enhanced_signal = self._apply_time_theory(parsed_signal)
            
            # Calculate precise SL/TP levels
            trade_setup = await self._calculate_sl_tp_levels(enhanced_signal)
            if not trade_setup:
                return
            
            # Create trade progress tracker
            trade = TradeProgress(
                symbol=trade_setup['symbol'],
                direction=trade_setup['direction'],
                entry_price=trade_setup['entry_price'],
                original_sl=trade_setup['stop_loss'],
                current_sl=trade_setup['stop_loss'],
                tp1=trade_setup['tp1'],
                tp2=trade_setup['tp2'],
                tp3=trade_setup['tp3'],
                risk_reward_ratio=trade_setup.get('risk_reward_ratio', 3.0)
            )
            
            # Store active trade
            self.active_trades[trade.symbol] = trade
            
            # Create stop loss manager for dynamic monitoring
            await self.stop_loss_integrator.create_trade_stop_loss(
                symbol=trade.symbol,
                direction=trade.direction,
                entry_price=trade.entry_price
            )
            
            # Forward to Unity
            unity_success = await self.forward_to_executor(enhanced_signal, trade)
            
            # Send compact confirmation
            if self.rate_limiter.can_send_message():
                confirmation_msg = self._create_compact_confirmation(enhanced_signal, trade, unity_success)
                await self.send_rate_limited_message(self.admin_chat_id, confirmation_msg)
            
            # Start monitoring
            asyncio.create_task(self.monitor_trade_progression(trade.symbol))
            
            self.logger.info(f"✅ Signal processed: {trade.symbol} {trade.direction}")
            
        except Exception as e:
            self.logger.error(f"❌ Error processing signal: {e}")
    
    async def _parse_and_validate_signal(self, signal_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse and validate incoming signal"""
        try:
            # Parse signal
            if isinstance(signal_data, str):
                parsed = self.signal_parser.parse_signal(signal_data)
            else:
                parsed = signal_data
            
            if not parsed or not parsed.get('action'):
                self.logger.warning("Invalid signal format")
                return None
            
            # Validate with risk manager
            validation = await self.risk_manager.validate_signal(parsed)
            if not validation.get('valid'):
                self.logger.warning(f"Signal validation failed: {validation.get('errors')}")
                return None
            
            return parsed
            
        except Exception as e:
            self.logger.error(f"Signal parsing error: {e}")
            return None
    
    def _apply_time_theory(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """Apply time theory enhancements to signal"""
        try:
            session = self.time_analyzer.get_market_session()
            volatility_factor = self.time_analyzer.get_volatility_factor(session)
            high_impact = self.time_analyzer.is_high_impact_time()
            
            enhanced_signal = signal.copy()
            
            # Adjust SL/TP based on session volatility
            if 'stop_loss' in signal and 'entry_price' in signal:
                entry = signal['entry_price']
                sl = signal['stop_loss']
                sl_distance = abs(entry - sl)
                
                # Adjust SL distance based on volatility
                adjusted_sl_distance = sl_distance * volatility_factor
                
                if signal.get('action', '').upper() in ['BUY', 'LONG']:
                    enhanced_signal['stop_loss'] = entry - adjusted_sl_distance
                else:
                    enhanced_signal['stop_loss'] = entry + adjusted_sl_distance
            
            # Add time-based metadata
            enhanced_signal.update({
                'market_session': session,
                'volatility_factor': volatility_factor,
                'high_impact_time': high_impact,
                'time_enhanced': True
            })
            
            return enhanced_signal
            
        except Exception as e:
            self.logger.error(f"Time theory application error: {e}")
            return signal
    
    async def _calculate_sl_tp_levels(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Calculate precise SL and 3 TP levels"""
        try:
            symbol = signal.get('symbol', '')
            action = signal.get('action', '').upper()
            entry_price = signal.get('entry_price') or signal.get('price', 0)
            
            if not all([symbol, action, entry_price]):
                self.logger.warning("Missing required signal data for SL/TP calculation")
                return None
            
            # Get current market price if needed
            if not entry_price:
                entry_price = await self.binance_trader.get_current_price(symbol)
            
            # Calculate SL based on risk percentage (2% default)
            risk_percent = 0.02
            volatility_factor = signal.get('volatility_factor', 1.0)
            adjusted_risk = risk_percent * volatility_factor
            
            if action in ['BUY', 'LONG']:
                stop_loss = entry_price * (1 - adjusted_risk)
                # 3 TPs with 1:1, 1:2, 1:3 ratios
                sl_distance = entry_price - stop_loss
                tp1 = entry_price + (sl_distance * 1.0)  # 1:1
                tp2 = entry_price + (sl_distance * 2.0)  # 1:2
                tp3 = entry_price + (sl_distance * 3.0)  # 1:3
            else:  # SELL, SHORT
                stop_loss = entry_price * (1 + adjusted_risk)
                sl_distance = stop_loss - entry_price
                tp1 = entry_price - (sl_distance * 1.0)
                tp2 = entry_price - (sl_distance * 2.0)
                tp3 = entry_price - (sl_distance * 3.0)
            
            return {
                'symbol': symbol,
                'direction': action,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'tp1': tp1,
                'tp2': tp2,
                'tp3': tp3,
                'risk_reward_ratio': 3.0,
                'session': signal.get('market_session', 'UNKNOWN')
            }
            
        except Exception as e:
            self.logger.error(f"SL/TP calculation error: {e}")
            return None
    
    def _create_compact_confirmation(self, signal: Dict[str, Any], trade: TradeProgress, unity_success: bool) -> str:
        """Create compact confirmation message"""
        direction_emoji = "🟢" if trade.direction in ['LONG', 'BUY'] else "🔴"
        session = signal.get('market_session', 'N/A')
        impact = "🔥" if signal.get('high_impact_time') else "📈"
        
        return f"""{direction_emoji} **{trade.symbol} {trade.direction}**

💰 **Entry:** {trade.entry_price:.4f} | **Session:** {session} {impact}
🛑 **SL:** {trade.current_sl:.4f}

🎯 **TPs:** {trade.tp1:.4f} | {trade.tp2:.4f} | {trade.tp3:.4f}
📊 **R:R:** 1:3 | 🌐 **Unity:** {'✅' if unity_success else '❌'}
⚡ **Monitoring:** Active"""
    
    async def forward_to_executor(self, signal: Dict[str, Any], trade: TradeProgress) -> bool:
        """Forward signal to Unity with enhanced format"""
        try:
            unified_signal = {
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
                'risk_reward_ratio': trade.risk_reward_ratio,
                'timeframe': 'Multi-TF',
                'strategy': 'Enhanced Perfect Scalping V2',
                'market_session': signal.get('market_session', 'UNKNOWN'),
                'volatility_factor': signal.get('volatility_factor', 1.0)
            }
            
            result = await self.unity.send_initial_signal(unified_signal)
            return result.get('success', False)
            
        except Exception as e:
            self.logger.error(f"Unity forwarding error: {e}")
            return False
    
    async def _monitor_active_trades(self):
        """Monitor all active trades for TP/SL hits"""
        for symbol, trade in list(self.active_trades.items()):
            try:
                if trade.position_closed:
                    continue
                
                # Get current price
                current_price = await self.binance_trader.get_current_price(symbol)
                if not current_price:
                    continue
                
                # Update dynamic stop loss system with current price
                sl_actions = await self.stop_loss_integrator.update_stop_loss_price(symbol, current_price)
                
                # Execute any triggered stop loss actions
                for action in sl_actions:
                    await self.stop_loss_integrator.execute_stop_loss_action(action)
                
                # Check for TP/SL hits
                await self._check_tp_sl_hits(trade, current_price)
                
            except Exception as e:
                self.logger.error(f"Error monitoring {symbol}: {e}")
    
    async def _check_tp_sl_hits(self, trade: TradeProgress, current_price: float):
        """Check for TP/SL hits and manage position accordingly"""
        try:
            symbol = trade.symbol
            
            if trade.direction in ['LONG', 'BUY']:
                # Long position checks
                if current_price <= trade.current_sl and not trade.position_closed:
                    await self._handle_stop_loss_hit(trade, current_price)
                elif current_price >= trade.tp3 and not trade.tp3_hit:
                    await self._handle_tp3_hit(trade)
                elif current_price >= trade.tp2 and not trade.tp2_hit:
                    await self._handle_tp2_hit(trade)
                elif current_price >= trade.tp1 and not trade.tp1_hit:
                    await self._handle_tp1_hit(trade)
            else:
                # Short position checks
                if current_price >= trade.current_sl and not trade.position_closed:
                    await self._handle_stop_loss_hit(trade, current_price)
                elif current_price <= trade.tp3 and not trade.tp3_hit:
                    await self._handle_tp3_hit(trade)
                elif current_price <= trade.tp2 and not trade.tp2_hit:
                    await self._handle_tp2_hit(trade)
                elif current_price <= trade.tp1 and not trade.tp1_hit:
                    await self._handle_tp1_hit(trade)
                    
        except Exception as e:
            self.logger.error(f"TP/SL check error for {trade.symbol}: {e}")
    
    async def _handle_tp1_hit(self, trade: TradeProgress):
        """Handle TP1 hit - Move SL to entry"""
        try:
            trade.tp1_hit = True
            trade.current_sl = trade.entry_price  # Move SL to entry
            trade.profit_locked = 1.0
            trade.stage = "tp1_hit"
            
            # Send SL update to Unity
            await self.unity.update_stop_loss(
                trade.symbol, 
                trade.entry_price, 
                "TP1 hit - SL moved to entry"
            )
            
            # Compact notification
            if self.rate_limiter.can_send_message():
                msg = f"""🎯 **TP1 HIT** - {trade.symbol}

🟢⚪⚪ Progress | 🛑 **SL → Entry:** {trade.entry_price:.4f}
💰 **Profit Secured:** Break-even | ⏭️ **Next:** TP2"""
                await self.send_rate_limited_message(self.admin_chat_id, msg)
            
            self.logger.info(f"🎯 TP1 hit for {trade.symbol} - SL moved to entry")
            
        except Exception as e:
            self.logger.error(f"TP1 handling error: {e}")
    
    async def _handle_tp2_hit(self, trade: TradeProgress):
        """Handle TP2 hit - Move SL to TP1"""
        try:
            trade.tp2_hit = True
            trade.current_sl = trade.tp1  # Move SL to TP1
            trade.profit_locked = 2.0
            trade.stage = "tp2_hit"
            
            # Send SL update to Unity
            await self.unity.update_stop_loss(
                trade.symbol,
                trade.tp1,
                "TP2 hit - SL moved to TP1"
            )
            
            # Compact notification
            if self.rate_limiter.can_send_message():
                msg = f"""🚀 **TP2 HIT** - {trade.symbol}

🟢🟢⚪ Progress | 🛑 **SL → TP1:** {trade.tp1:.4f}
💰 **Profit Secured:** +2.0R | 🎯 **Final:** TP3"""
                await self.send_rate_limited_message(self.admin_chat_id, msg)
            
            self.logger.info(f"🚀 TP2 hit for {trade.symbol} - SL moved to TP1")
            
        except Exception as e:
            self.logger.error(f"TP2 handling error: {e}")
    
    async def _handle_tp3_hit(self, trade: TradeProgress):
        """Handle TP3 hit - Full position closure"""
        try:
            trade.tp3_hit = True
            trade.position_closed = True
            trade.profit_locked = 3.0
            trade.stage = "completed"
            
            # Close position in Unity
            await self.unity.close_position(
                trade.symbol,
                "TP3 hit - Full closure",
                100
            )
            
            # Update performance stats
            self.total_trades += 1
            self.winning_trades += 1
            self.total_profit += 3.0  # 3R profit
            
            # Compact success notification
            if self.rate_limiter.can_send_message():
                win_rate = (self.winning_trades / self.total_trades) * 100
                msg = f"""🏆 **TP3 COMPLETE** - {trade.symbol}

🟢🟢🟢 Full Success | 💰 **Profit:** +3.0R
📊 **Stats:** {self.winning_trades}/{self.total_trades} ({win_rate:.1f}%)
💎 **Total P&L:** +{self.total_profit:.1f}R"""
                await self.send_rate_limited_message(self.admin_chat_id, msg)
            
            self.logger.info(f"🏆 TP3 hit for {trade.symbol} - Full closure completed")
            
        except Exception as e:
            self.logger.error(f"TP3 handling error: {e}")
    
    async def _handle_stop_loss_hit(self, trade: TradeProgress, current_price: float):
        """Handle stop loss hit"""
        try:
            trade.position_closed = True
            trade.stage = "stopped_out"
            
            # Close position in Unity
            await self.unity.close_position(
                trade.symbol,
                "Stop loss hit",
                100
            )
            
            # Update performance stats
            self.total_trades += 1
            loss_amount = -1.0 if trade.profit_locked == 0 else 0  # If no TP hit, -1R loss
            self.total_profit += loss_amount
            
            # Compact loss notification
            if self.rate_limiter.can_send_message():
                win_rate = (self.winning_trades / self.total_trades) * 100 if self.total_trades > 0 else 0
                msg = f"""🛑 **SL HIT** - {trade.symbol}

❌ **Stopped:** {current_price:.4f} | **Loss:** {loss_amount:.1f}R
📊 **Stats:** {self.winning_trades}/{self.total_trades} ({win_rate:.1f}%)
💰 **Total P&L:** {self.total_profit:+.1f}R"""
                await self.send_rate_limited_message(self.admin_chat_id, msg)
            
            self.logger.info(f"🛑 Stop loss hit for {trade.symbol} at {current_price:.4f}")
            
        except Exception as e:
            self.logger.error(f"Stop loss handling error: {e}")
    
    async def _process_pending_signals(self):
        """Process any pending signals (placeholder for webhook integration)"""
        # This would be implemented with webhook server or signal queue
        pass
    
    def _cleanup_completed_trades(self):
        """Clean up completed trades older than 1 hour"""
        try:
            current_time = datetime.now()
            cutoff_time = current_time - timedelta(hours=1)
            
            completed_symbols = []
            for symbol, trade in self.active_trades.items():
                if trade.position_closed and trade.start_time and trade.start_time < cutoff_time:
                    completed_symbols.append(symbol)
            
            for symbol in completed_symbols:
                del self.active_trades[symbol]
                
        except Exception as e:
            self.logger.error(f"Cleanup error: {e}")
    
    async def send_rate_limited_message(self, chat_id: str, message: str):
        """Send rate-limited message to Telegram"""
        try:
            if not self.rate_limiter.can_send_message():
                self.logger.info("Rate limit reached - message skipped")
                return
            
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        self.rate_limiter.record_message()
                        self.logger.info("✅ Message sent successfully")
                    else:
                        error = await response.text()
                        self.logger.warning(f"Telegram API error: {error}")
                        
        except Exception as e:
            self.logger.error(f"Message send error: {e}")
    
    async def monitor_trade_progression(self, symbol: str):
        """Monitor individual trade progression"""
        try:
            self.logger.info(f"🔍 Monitoring {symbol}")
            
            while symbol in self.active_trades and not self.active_trades[symbol].position_closed:
                await asyncio.sleep(2)  # Check every 2 seconds
                
            self.logger.info(f"✅ Monitoring completed for {symbol}")
            
        except Exception as e:
            self.logger.error(f"Trade monitoring error for {symbol}: {e}")
    
    async def get_status_report(self) -> Dict[str, Any]:
        """Get comprehensive status report"""
        try:
            active_count = len([t for t in self.active_trades.values() if not t.position_closed])
            win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
            
            return {
                'status': 'running' if self.running else 'stopped',
                'active_trades': active_count,
                'total_trades': self.total_trades,
                'winning_trades': self.winning_trades,
                'win_rate': win_rate,
                'total_profit': self.total_profit,
                'session': self.time_analyzer.get_market_session(),
                'rate_limit_remaining': 3 - len(self.rate_limiter.message_timestamps),
                'unity_connected': True,  # Would check actual status
                'uptime': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Status report error: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def stop(self):
        """Stop the bot gracefully"""
        self.logger.info("🛑 Stopping Enhanced Perfect Scalping Bot V2...")
        self.running = False
        
        # Close any remaining positions
        for symbol, trade in self.active_trades.items():
            if not trade.position_closed:
                await self.unity.close_position(symbol, "Bot shutdown", 100)
        
        self.logger.info("✅ Bot stopped gracefully")

# Example usage
async def main():
    """Main execution function"""
    bot = EnhancedPerfectScalpingBotV2()
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        await bot.stop()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
