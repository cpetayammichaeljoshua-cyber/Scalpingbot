
#!/usr/bin/env python3
"""
Fixed FXSUSDT Bot Startup Script
Applies all console fixes before starting the bot
"""

import os
import sys
import warnings
import asyncio
from pathlib import Path

# Apply comprehensive error fixes first
def apply_startup_fixes():
    """Apply all necessary fixes before bot startup"""
    print("🔧 Applying startup fixes...")
    
    # Global warning suppression
    warnings.filterwarnings('ignore')
    warnings.filterwarnings('ignore', category=FutureWarning)
    warnings.filterwarnings('ignore', category=UserWarning)
    warnings.filterwarnings('ignore', category=DeprecationWarning)
    warnings.filterwarnings('ignore', category=RuntimeWarning)
    
    # Pandas fixes
    try:
        import pandas as pd
        pd.set_option('mode.chained_assignment', None)
        pd.options.mode.copy_on_write = True
    except ImportError:
        pass
    
    # NumPy fixes  
    try:
        import numpy as np
        np.seterr(all='ignore')
    except ImportError:
        pass
    
    # Matplotlib fixes
    try:
        import matplotlib
        matplotlib.use('Agg')
    except ImportError:
        pass
    
    print("✅ Startup fixes applied")

# Apply fixes before any other imports
apply_startup_fixes()

# Now import and run the bot
import logging
from SignalMaestro.fxsusdt_telegram_bot import FXSUSDTTelegramBot
from SignalMaestro.ichimoku_sniper_strategy import IchimokuSniperStrategy
from SignalMaestro.fxsusdt_trader import FXSUSDTTrader

# Configure clean logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# Reduce noise from specific loggers
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)

async def main():
    """Main function with enhanced error handling and startup message"""
    logger = logging.getLogger(__name__)
    restart_count = 0
    max_restarts = 5  # Prevent infinite loops
    
    while restart_count < max_restarts:
        try:
            logger.info("🚀 Starting FXSUSDT.P Ichimoku Sniper Bot (Fixed Version)")
            logger.info("📊 Strategy: Ichimoku Cloud Analysis")
            logger.info("⏰ Timeframe: 30 Minutes")
            logger.info("🎯 Target: @InsiderTactics")
            logger.info("🤖 Bot: @TradeTacticsML_bot")
            
            # Initialize components
            bot = FXSUSDTTelegramBot()
            
            # Reset restart counter on successful initialization
            restart_count = 0
            
            # Start continuous monitoring
            await bot.run_continuous_scanner()
            
        except KeyboardInterrupt:
            logger.info("👋 Bot stopped by user")
            break
        except Exception as e:
            restart_count += 1
            logger.error(f"❌ Bot error: {e}")
            
            if restart_count < max_restarts:
                wait_time = min(30, 5 * restart_count)  # Exponential backoff
                logger.info(f"🔄 Attempting auto-restart ({restart_count}/{max_restarts})... Waiting {wait_time}s")
                await asyncio.sleep(wait_time)
            else:
                logger.critical(f"❌ Max restart attempts ({max_restarts}) reached. Exiting.")
                break

if __name__ == "__main__":
    asyncio.run(main())
