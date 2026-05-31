
#!/usr/bin/env python3
"""
Futures Command Handler
Handles Telegram commands for the Enhanced Binance Futures Signal Bot
"""

import asyncio
import logging
import json
import aiohttp
from datetime import datetime
from typing import Dict, Any, Optional, List

class FuturesCommandHandler:
    """Command handler for futures bot"""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.logger = logging.getLogger(__name__)
        
        # Available commands
        self.commands = {
            '/start': self.handle_start,
            '/help': self.handle_help,
            '/status': self.handle_status,
            '/markets': self.handle_markets,
            '/scan': self.handle_scan,
            '/top': self.handle_top_symbols,
            '/stats': self.handle_stats,
            '/settings': self.handle_settings,
            '/admin': self.handle_admin
        }
    
    async def handle_command(self, message_text: str, chat_id: str) -> bool:
        """Handle incoming command"""
        try:
            command = message_text.split()[0].lower()
            
            if command in self.commands:
                response = await self.commands[command](message_text, chat_id)
                if response:
                    return await self.bot.send_telegram_message(chat_id, response)
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error handling command: {e}")
            return False
    
    async def handle_start(self, message_text: str, chat_id: str) -> str:
        """Handle /start command"""
        return """
🚀 **Enhanced Binance Futures Signal Bot**

🎯 **Features:**
• Scans all USDT perpetual futures
• Advanced multi-strategy analysis
• Dynamic leverage optimization
• Real-time signal generation

📋 **Available Commands:**
/help - Show this help message
/status - Bot status and performance
/markets - Active markets being monitored
/scan - Force market scan
/top - Top performing symbols
/stats - Performance statistics

📢 **Channel:** @SignalTactics
🤖 **Powered by AI Multi-Strategy Analysis**

Ready to generate premium futures signals! 🎯
        """
    
    async def handle_help(self, message_text: str, chat_id: str) -> str:
        """Handle /help command"""
        return """
📚 **Command Reference:**

🔧 **Basic Commands:**
• `/start` - Initialize bot
• `/help` - Show this help
• `/status` - Bot status & health

📊 **Market Commands:**
• `/markets` - Active markets (top 20)
• `/scan` - Force immediate market scan
• `/top` - Top volume symbols today

📈 **Performance Commands:**
• `/stats` - Bot performance statistics
• `/settings` - Current bot settings

👨‍💼 **Admin Commands:**
• `/admin` - Admin panel (authorized users only)

🎯 **About:**
This bot scans all Binance USDT perpetual futures using advanced technical analysis and sends high-probability signals to @SignalTactics.

⚡ **Real-time monitoring of 100+ futures symbols**
🧠 **AI-powered multi-strategy analysis**
📊 **Dynamic leverage optimization**
        """
    
    async def handle_status(self, message_text: str, chat_id: str) -> str:
        """Handle /status command"""
        try:
            uptime = datetime.now() - self.bot.last_heartbeat
            
            status = f"""
📊 **Bot Status Report**

🔄 **Operational Status:** {'🟢 ONLINE' if self.bot.running else '🔴 OFFLINE'}
⏰ **Uptime:** {uptime.days}d {uptime.seconds//3600}h {(uptime.seconds%3600)//60}m
🎯 **Signals Generated:** {self.bot.signal_counter}
📈 **Active Symbols:** {len(self.bot.active_symbols)}

📊 **Performance:**
• **Total Signals:** {self.bot.performance_stats['total_signals']}
• **Win Rate:** {self.bot.performance_stats['win_rate']:.1f}%
• **Avg RRR:** {self.bot.performance_stats['average_rrr']:.1f}

⚙️ **Settings:**
• **Min Signal Strength:** {self.bot.min_signal_strength}%
• **Max Signals/Hour:** {self.bot.max_signals_per_hour}
• **Leverage Range:** {self.bot.leverage_range[0]}-{self.bot.leverage_range[1]}x

🎯 **Channel:** @SignalTactics
⚡ **Last Scan:** {datetime.now().strftime('%H:%M:%S')}
            """
            
            return status
            
        except Exception as e:
            return f"❌ Error getting status: {e}"
    
    async def handle_markets(self, message_text: str, chat_id: str) -> str:
        """Handle /markets command"""
        try:
            if not self.bot.active_symbols:
                return "📊 No active markets loaded yet. Try again in a moment."
            
            markets_text = "📊 **Top Active Futures Markets:**\n\n"
            
            # Show top 20 symbols
            for i, symbol in enumerate(self.bot.active_symbols[:20], 1):
                markets_text += f"{i:2d}. `{symbol}`\n"
            
            markets_text += f"\n📈 **Total Active:** {len(self.bot.active_symbols)} symbols"
            markets_text += f"\n🔄 **Refresh Rate:** Every hour"
            markets_text += f"\n💰 **Min Volume:** ${self.bot.min_volume_usdt:,.0f} USDT"
            
            return markets_text
            
        except Exception as e:
            return f"❌ Error getting markets: {e}"
    
    async def handle_scan(self, message_text: str, chat_id: str) -> str:
        """Handle /scan command"""
        try:
            await self.bot.send_telegram_message(chat_id, "🔍 **Initiating market scan...**\n⏳ Analyzing futures markets...")
            
            # Force a market scan
            signal = await self.bot.scan_futures_markets()
            
            if signal:
                await self.bot.send_futures_signal(signal)
                return f"✅ **Scan Complete!**\n\n🎯 Signal found and sent: {signal['symbol']} {signal['direction']}\n💪 Strength: {signal['signal_strength']:.0f}%"
            else:
                return "✅ **Scan Complete!**\n\n📊 No high-probability signals found at this time.\n⏳ Continuing automated monitoring..."
                
        except Exception as e:
            return f"❌ Scan error: {e}"
    
    async def handle_top_symbols(self, message_text: str, chat_id: str) -> str:
        """Handle /top command"""
        try:
            # Get top symbols by volume
            url = f"{self.bot.futures_base_url}/fapi/v1/ticker/24hr"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        tickers = await response.json()
                        
                        # Filter USDT pairs and sort by volume
                        usdt_tickers = [t for t in tickers if t['symbol'].endswith('USDT')]
                        usdt_tickers.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
                        
                        top_text = "🏆 **Top Futures by 24h Volume:**\n\n"
                        
                        for i, ticker in enumerate(usdt_tickers[:15], 1):
                            symbol = ticker['symbol']
                            volume = float(ticker['quoteVolume'])
                            change = float(ticker['priceChangePercent'])
                            price = float(ticker['lastPrice'])
                            
                            change_emoji = "🟢" if change >= 0 else "🔴"
                            
                            top_text += f"{i:2d}. `{symbol}`\n"
                            top_text += f"    💰 ${price:.4f} {change_emoji} {change:+.1f}%\n"
                            top_text += f"    📊 Vol: ${volume:,.0f}\n\n"
                        
                        return top_text
            
            return "❌ Unable to fetch top symbols"
            
        except Exception as e:
            return f"❌ Error getting top symbols: {e}"
    
    async def handle_stats(self, message_text: str, chat_id: str) -> str:
        """Handle /stats command"""
        try:
            stats = self.bot.performance_stats
            
            stats_text = f"""
📈 **Performance Statistics**

🎯 **Signal Generation:**
• **Total Signals:** {stats['total_signals']}
• **Profitable Signals:** {stats['profitable_signals']}
• **Win Rate:** {stats['win_rate']:.1f}%
• **Total Profit:** {stats['total_profit']:+.1f}%

⚖️ **Risk Management:**
• **Average RRR:** {stats['average_rrr']:.1f}
• **Max Signals/Hour:** {self.bot.max_signals_per_hour}
• **Min Signal Strength:** {self.bot.min_signal_strength}%

📊 **Market Coverage:**
• **Active Symbols:** {len(self.bot.active_symbols)}
• **Timeframes:** {', '.join(self.bot.timeframes)}
• **Market Type:** Binance USDT Perpetuals

🤖 **Strategy:**
• **Multi-Strategy Analysis**
• **Dynamic Leverage Optimization**
• **Volume & Momentum Confirmation**
• **Support/Resistance Analysis**

⏰ **Last Updated:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
            """
            
            return stats_text
            
        except Exception as e:
            return f"❌ Error getting statistics: {e}"
    
    async def handle_settings(self, message_text: str, chat_id: str) -> str:
        """Handle /settings command"""
        try:
            settings_text = f"""
⚙️ **Bot Configuration**

🎯 **Signal Settings:**
• **Min Signal Strength:** {self.bot.min_signal_strength}%
• **Max Signals/Hour:** {self.bot.max_signals_per_hour}
• **Signal Interval:** {self.bot.min_signal_interval // 60} minutes

💰 **Market Filters:**
• **Min Volume (24h):** ${self.bot.min_volume_usdt:,.0f} USDT
• **Min Price Change:** 0.5%
• **Active Symbols:** {len(self.bot.active_symbols)}

⚡ **Leverage Settings:**
• **Min Leverage:** {self.bot.leverage_range[0]}x
• **Max Leverage:** {self.bot.leverage_range[1]}x
• **Dynamic Adjustment:** ✅ Enabled

📊 **Analysis Timeframes:**
{chr(10).join([f'• {tf}' for tf in self.bot.timeframes])}

🎯 **Target Channel:** @SignalTactics
🔄 **Auto Symbol Refresh:** Every hour
⚡ **Real-time Monitoring:** ✅ Active
            """
            
            return settings_text
            
        except Exception as e:
            return f"❌ Error getting settings: {e}"
    
    async def handle_admin(self, message_text: str, chat_id: str) -> str:
        """Handle /admin command"""
        # Simple admin check (you can enhance this)
        if self.bot.admin_chat_id and chat_id != self.bot.admin_chat_id:
            return "❌ Access denied. Admin privileges required."
        
        return f"""
👨‍💼 **Admin Panel**

🔧 **Bot Control:**
• **Status:** {'🟢 RUNNING' if self.bot.running else '🔴 STOPPED'}
• **PID:** {self.bot.pid_file.read_text() if self.bot.pid_file.exists() else 'N/A'}
• **Uptime:** {(datetime.now() - self.bot.last_heartbeat).total_seconds():.0f}s

📊 **Current Stats:**
• **Signals Today:** {self.bot.signal_counter}
• **Active Symbols:** {len(self.bot.active_symbols)}
• **Last Signal:** {max(self.bot.last_signal_time.values()) if self.bot.last_signal_time else 'None'}

⚙️ **Quick Actions:**
Send `/scan` to force market scan
Send `/markets` to refresh symbol list

🎯 **Channel Status:** @SignalTactics
        """

# Integration function
def integrate_command_handler(bot_instance):
    """Integrate command handler into bot"""
    command_handler = FuturesCommandHandler(bot_instance)
    
    # Add method to bot instance
    bot_instance.handle_command = command_handler.handle_command
    bot_instance.command_handler = command_handler
    
    return command_handler
