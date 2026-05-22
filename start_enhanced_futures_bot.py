
#!/usr/bin/env python3
"""
Start Enhanced Binance Futures Signal Bot
Comprehensive startup script with error handling and monitoring
"""

import asyncio
import logging
import os
import sys
import subprocess
import json
import time
from pathlib import Path
from datetime import datetime

# Add SignalMaestro to path
sys.path.insert(0, 'SignalMaestro')

async def main():
    """Main startup function"""
    try:
        print("🚀 Starting Enhanced Binance Futures Signal Bot...")
        
        # Import the bot
        from SignalMaestro.enhanced_binance_futures_signal_bot import EnhancedBinanceFuturesSignalBot
        from SignalMaestro.futures_command_handler import integrate_command_handler
        
        # Create bot instance
        bot = EnhancedBinanceFuturesSignalBot()
        
        # Integrate command handler
        integrate_command_handler(bot)
        
        # Start bot
        await bot.start_bot()
        
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Ensure environment variables
    required_env = ['TELEGRAM_BOT_TOKEN']
    missing_env = [var for var in required_env if not os.getenv(var)]
    
    if missing_env:
        print(f"❌ Missing environment variables: {missing_env}")
        sys.exit(1)
    
    # Run bot
    asyncio.run(main())
