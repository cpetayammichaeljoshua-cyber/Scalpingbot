#!/usr/bin/env python3
"""
FXSUSDT.P Ichimoku Sniper Bot Runner
Main entry point for the FXSUSDT.P trading bot
"""

import asyncio
import logging
import sys
import os
import warnings
from pathlib import Path

# Apply comprehensive console fixes at startup
warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'

# Reduce HTTP request logging
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram.ext.Application').setLevel(logging.WARNING)

# Add SignalMaestro to path
current_dir = Path(__file__).parent
signal_maestro_path = current_dir / "SignalMaestro"
sys.path.insert(0, str(signal_maestro_path))

try:
    from fxsusdt_telegram_bot import FXSUSDTTelegramBot
except ImportError as e:
    print(f"Import error: {e}")
    print("Available files in SignalMaestro:")
    if signal_maestro_path.exists():
        for file in signal_maestro_path.glob("*.py"):
            print(f"  {file.name}")
    sys.exit(1)

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('fxsusdt_bot.log'),
            logging.StreamHandler()
        ]
    )

async def main():
    """Main function"""
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("🚀 Starting FXSUSDT.P Ichimoku Sniper Bot")
    logger.info("📊 Strategy: Ichimoku Cloud Analysis")
    logger.info("⏰ Timeframe: 30 Minutes")
    logger.info("🎯 Target: @SignalTactics")
    logger.info("🤖 Bot: TradeTactics")

    # Check required environment variables
    required_secrets = ['TELEGRAM_BOT_TOKEN', 'BINANCE_API_KEY', 'BINANCE_API_SECRET']
    missing_secrets = [secret for secret in required_secrets if not os.getenv(secret)]

    if missing_secrets:
        logger.error(f"❌ Missing required secrets: {', '.join(missing_secrets)}")
        logger.error("Please add these to your Replit secrets:")
        for secret in missing_secrets:
            logger.error(f"   {secret}")
        return

    try:
        # Create bot instance
        bot = FXSUSDTTelegramBot()

        logger.info("🤖 Starting Telegram command system...")

        # Start the Telegram command system first
        telegram_success = await bot.start_telegram_polling()

        if not telegram_success:
            logger.warning("⚠️ Telegram polling failed to start, continuing with scanner only")

        # Give command system time to initialize
        await asyncio.sleep(2)

        logger.info("🔍 Starting market scanner...")

        # Start the continuous scanner
        await bot.run_continuous_scanner()

    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
        if hasattr(bot, 'telegram_app') and bot.telegram_app:
            try:
                await bot.telegram_app.updater.stop()
                await bot.telegram_app.stop()
                await bot.telegram_app.shutdown()
            except Exception as e:
                logger.error(f"Error stopping Telegram app: {e}")
    except Exception as e:
        logger.error(f"❌ Critical error: {e}")
        if hasattr(bot, 'telegram_app') and bot.telegram_app:
            try:
                await bot.telegram_app.updater.stop()
                await bot.telegram_app.stop()
                await bot.telegram_app.shutdown()
            except Exception as e:
                logger.error(f"Error stopping Telegram app: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())