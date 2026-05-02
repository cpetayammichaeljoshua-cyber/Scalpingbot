#!/usr/bin/env python3
"""
HIGH-FREQUENCY SCALPING BOT - FXSUSDT
Entry point for production deployment
"""
import asyncio
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("🚀 STARTING HIGH-FREQUENCY SCALPING BOT")
    logger.info("=" * 80)
    
    from SignalMaestro.fxsusdt_telegram_bot import FXSUSDTTelegramBot
    bot = FXSUSDTTelegramBot()
    
    # Override to HIGH-FREQUENCY mode
    bot.min_signal_interval_minutes = 2
    
    logger.info(f"✅ Config: {bot.min_signal_interval_minutes}min rate limit")
    logger.info(f"✅ Signals: Frequent trades to @SignalTactics")
    logger.info(f"✅ Commands: {len(bot.commands)} available")
    logger.info("=" * 80)
    
    await bot.start_telegram_polling()

if __name__ == "__main__":
    if not os.getenv('TELEGRAM_BOT_TOKEN'):
        logger.error("Missing TELEGRAM_BOT_TOKEN in secrets")
        exit(1)
    asyncio.run(main())
