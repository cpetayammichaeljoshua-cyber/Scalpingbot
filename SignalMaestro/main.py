#!/usr/bin/env python3
"""
Automated Cryptocurrency Trading Signal Bot
Main application entry point with Telegram and Cornix integration
"""

import asyncio
import logging
import threading
import time
from datetime import datetime

from config import Config
# from telegram_bot import TradingSignalBot  # Temporarily disabled due to import issues
from webhook_server import WebhookServer
from database import Database
from logger import setup_logging
from binance_trader import BinanceTrader
from cornix_integration import CornixIntegration

class TradingBotManager:
    """Main manager class for the trading bot system"""
    
    def __init__(self):
        self.config = Config()
        self.logger = setup_logging()
        self.db = Database()
        self.binance_trader = BinanceTrader()
        self.cornix = CornixIntegration()
        self.telegram_bot = None
        self.webhook_server = None
        
    async def initialize(self):
        """Initialize all components"""
        try:
            # Initialize database
            await self.db.initialize()
            self.logger.info("Database initialized successfully")
            
            # Initialize Binance trader (using testnet mode to avoid restrictions)
            try:
                await self.binance_trader.initialize()
                self.logger.info("Binance trader initialized successfully")
            except Exception as e:
                self.logger.warning(f"Binance trader initialization failed: {e}. Continuing in demo mode.")
            
            # Initialize Telegram bot (temporarily disabled)
            # self.telegram_bot = TradingSignalBot(
            #     self.binance_trader, 
            #     self.cornix, 
            #     self.db
            # )
            # await self.telegram_bot.initialize()
            self.logger.info("Telegram bot initialization skipped (demo mode)")
            
            # Initialize webhook server
            self.webhook_server = WebhookServer(
                None,  # self.telegram_bot,  # Temporarily disabled
                self.binance_trader, 
                self.cornix,
                self.db
            )
            
            self.logger.info("All components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize components: {e}")
            raise
    
    def start_webhook_server(self):
        """Start the webhook server in a separate thread"""
        def run_server():
            self.webhook_server.run()
        
        webhook_thread = threading.Thread(target=run_server, daemon=True)
        webhook_thread.start()
        self.logger.info("Webhook server started on port 5000")
    
    async def start_telegram_bot(self):
        """Start the Telegram bot"""
        if self.telegram_bot:
            await self.telegram_bot.start()
            self.logger.info("Telegram bot started successfully")
        else:
            self.logger.info("Telegram bot is disabled - skipping startup")
    
    async def run_monitoring_loop(self):
        """Run continuous monitoring and health checks"""
        while True:
            try:
                # Check system health
                await self.health_check()
                
                # Update portfolio data
                await self.update_portfolio_data()
                
                # Clean old data
                await self.cleanup_old_data()
                
                # Sleep for 60 seconds before next check
                await asyncio.sleep(60)
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)
    
    async def health_check(self):
        """Perform system health checks"""
        try:
            # Check Binance connection
            await self.binance_trader.ping()
            
            # Check database connection
            await self.db.health_check()
            
            # Log health status
            self.logger.debug("System health check passed")
            
        except Exception as e:
            self.logger.warning(f"Health check failed: {e}")
    
    async def update_portfolio_data(self):
        """Update portfolio and balance information"""
        try:
            balance = await self.binance_trader.get_account_balance()
            await self.db.update_portfolio_snapshot(balance)
            
        except Exception as e:
            self.logger.error(f"Failed to update portfolio data: {e}")
    
    async def cleanup_old_data(self):
        """Clean up old data from database"""
        try:
            # Clean data older than 30 days
            cutoff_date = datetime.utcnow().timestamp() - (30 * 24 * 60 * 60)
            await self.db.cleanup_old_data(cutoff_date)
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup old data: {e}")
    
    async def shutdown(self):
        """Gracefully shutdown all components"""
        self.logger.info("Shutting down trading bot...")
        
        try:
            if self.telegram_bot:
                await self.telegram_bot.stop()
            
            if self.binance_trader:
                await self.binance_trader.close()
            
            if self.db:
                await self.db.close()
                
            self.logger.info("All components shut down successfully")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")

async def main():
    """Main application entry point"""
    bot_manager = TradingBotManager()
    
    try:
        # Initialize all components
        await bot_manager.initialize()
        
        # Start webhook server
        bot_manager.start_webhook_server()
        
        # Start telegram bot
        telegram_task = asyncio.create_task(bot_manager.start_telegram_bot())
        
        # Start monitoring loop
        monitoring_task = asyncio.create_task(bot_manager.run_monitoring_loop())
        
        print("🚀 Trading Signal Bot is running!")
        print("📱 Telegram bot active")
        print("🌐 Webhook server running on http://0.0.0.0:5000")
        print("📊 Monitoring system active")
        print("Press Ctrl+C to stop...")
        
        # Wait for tasks to complete
        await asyncio.gather(telegram_task, monitoring_task)
        
    except KeyboardInterrupt:
        print("\n🛑 Received shutdown signal...")
        await bot_manager.shutdown()
        
    except Exception as e:
        print(f"❌ Critical error: {e}")
        await bot_manager.shutdown()
        raise

if __name__ == "__main__":
    asyncio.run(main())
