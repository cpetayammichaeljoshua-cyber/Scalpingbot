#!/usr/bin/env python3
"""
Enhanced Perfect Scalping Bot V3 Starter
Advanced Time-Fibonacci Theory with ML Enhancement
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# Add SignalMaestro to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(current_dir, 'SignalMaestro'))

async def main():
    """Start the Enhanced Perfect Scalping Bot V3"""
    try:
        print("🚀 Starting Enhanced Perfect Scalping Bot V3...")
        print("📊 Strategy: Advanced Time-Based + Fibonacci Theory")
        print("🧠 ML Enhancement: Active on every trade")
        print("⏰ Initialization time:", datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'))
        print("🎯 Features:")
        print("   • Advanced Time Session Analysis")
        print("   • Fibonacci Golden Ratio Scalping")
        print("   • ML-Enhanced Trade Validation")
        print("   • Rate Limited: 2 trades/hour")
        print("   • Multi-timeframe Confluence")
        print("=" * 70)

        # Import and start the bot
        from SignalMaestro.enhanced_perfect_scalping_bot_v3 import EnhancedPerfectScalpingBotV3

        bot = EnhancedPerfectScalpingBotV3()
        await bot.start_bot()

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Please ensure all required modules are installed")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Critical error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Enhanced Perfect Scalping Bot V3 stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)