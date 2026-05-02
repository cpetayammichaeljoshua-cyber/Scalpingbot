#!/usr/bin/env python3
"""
FXSUSDT Production Trading Bot Launcher
Production-ready deployment with market intelligence and order flow analysis
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/production_bot_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def check_environment():
    """Verify all required environment variables and dependencies"""
    logger.info("🔍 Checking production environment...")
    
    required_env_vars = [
        'TELEGRAM_BOT_TOKEN',
        'BINANCE_API_KEY',
        'BINANCE_API_SECRET'
    ]
    
    missing_vars = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        logger.info("Please set these in Replit Secrets: /Dashboard → Secrets")
        return False
    
    logger.info("✅ Environment variables verified")
    return True

def check_dependencies():
    """Verify all required packages are installed"""
    logger.info("📦 Checking dependencies...")
    
    required_packages = [
        'aiohttp',
        'aiosqlite',
        'ccxt',
        'flask',
        'numpy',
        'pandas',
        'python-telegram-bot',
        'python-binance'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        logger.warning(f"⚠️  Some packages missing: {', '.join(missing_packages)}")
        logger.info("Installing missing packages...")
        import subprocess
        for package in missing_packages:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package])
                logger.info(f"✅ Installed {package}")
            except Exception as e:
                logger.error(f"Failed to install {package}: {e}")
                return False
    
    logger.info("✅ All dependencies verified")
    return True

async def main():
    """Main production bot launcher"""
    logger.info("=" * 80)
    logger.info("🚀 FXSUSDT Production Trading Bot")
    logger.info("=" * 80)
    logger.info(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    # Verify environment
    if not check_environment():
        logger.error("❌ Environment check failed")
        sys.exit(1)
    
    # Check dependencies
    if not check_dependencies():
        logger.error("❌ Dependency check failed")
        sys.exit(1)
    
    # Import bot after all checks
    try:
        logger.info("📥 Importing bot modules...")
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        
        from SignalMaestro.fxsusdt_telegram_bot import FXSUSDTTelegramBot
        
        logger.info("✅ Bot modules loaded successfully")
        
        # Initialize bot
        logger.info("🤖 Initializing FXSUSDT Trading Bot...")
        bot = FXSUSDTTelegramBot()
        logger.info("✅ Bot initialized successfully")
        
        # Display bot status
        logger.info(f"   • Telegram Channel: {bot.channel_id}")
        logger.info(f"   • Contract: {bot.contract_specs['symbol']}")
        logger.info(f"   • Max Leverage: {bot.contract_specs['max_leverage']}")
        logger.info(f"   • Funding Interval: {bot.contract_specs['funding_interval']}")
        
        # Start bot
        logger.info("\n" + "=" * 80)
        logger.info("🌐 Starting Telegram command system...")
        logger.info("=" * 80)
        
        try:
            telegram_success = await bot.start_telegram_polling()
            
            if not telegram_success:
                logger.warning("⚠️ Telegram polling failed to start")
            else:
                logger.info("✅ Telegram bot active and listening for commands")
            
            # Keep bot running
            logger.info("\n💡 Bot is now LIVE and ready for trading commands")
            logger.info("📊 Available commands: /help, /price, /balance, /status, /signal, etc.")
            
            # Run continuous operations
            logger.info("🔄 Starting market monitoring...")
            await bot.run_continuous_scanner()
            
        except KeyboardInterrupt:
            logger.info("\n👋 Bot stopped by user")
        except Exception as e:
            logger.error(f"❌ Bot runtime error: {e}", exc_info=True)
            sys.exit(1)
        finally:
            # Cleanup
            if hasattr(bot, 'telegram_app') and bot.telegram_app:
                try:
                    await bot.telegram_app.stop()
                    logger.info("✅ Bot shutdown complete")
                except Exception as e:
                    logger.error(f"Error during shutdown: {e}")
    
    except ImportError as e:
        logger.error(f"❌ Failed to import bot modules: {e}")
        logger.error("Make sure all required files are in SignalMaestro directory")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot terminated")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
