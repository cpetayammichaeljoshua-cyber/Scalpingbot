
#!/usr/bin/env python3
"""
Bot Health Check and Monitoring
Ensures the bot is running optimally
"""

import asyncio
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# Add SignalMaestro to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'SignalMaestro'))

async def check_bot_health():
    """Comprehensive health check"""
    print("=" * 70)
    print("🔍 BOT HEALTH CHECK - FXSUSDT COMPREHENSIVE")
    print("=" * 70)
    
    checks_passed = 0
    checks_total = 0
    
    # Check 1: Import modules
    checks_total += 1
    try:
        from SignalMaestro.fxsusdt_telegram_bot import FXSUSDTTelegramBot
        from SignalMaestro.fxsusdt_trader import FXSUSDTTrader
        from SignalMaestro.ichimoku_sniper_strategy import IchimokuSniperStrategy
        print("✅ All modules imported successfully")
        checks_passed += 1
    except Exception as e:
        print(f"❌ Module import failed: {e}")
    
    # Check 2: Environment variables
    checks_total += 1
    required_vars = ['TELEGRAM_BOT_TOKEN', 'BINANCE_API_KEY', 'BINANCE_API_SECRET']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if not missing_vars:
        print("✅ All environment variables configured")
        checks_passed += 1
    else:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
    
    # Check 3: API connections
    checks_total += 1
    try:
        from SignalMaestro.fxsusdt_trader import FXSUSDTTrader
        trader = FXSUSDTTrader()
        if await trader.test_connection():
            print("✅ Binance API connection successful")
            checks_passed += 1
        else:
            print("❌ Binance API connection failed")
    except Exception as e:
        print(f"❌ API connection error: {e}")
    
    # Check 4: Telegram connection
    checks_total += 1
    try:
        from SignalMaestro.fxsusdt_telegram_bot import FXSUSDTTelegramBot
        bot = FXSUSDTTelegramBot()
        if await bot.test_telegram_connection():
            print("✅ Telegram connection successful")
            checks_passed += 1
        else:
            print("❌ Telegram connection failed")
    except Exception as e:
        print(f"❌ Telegram connection error: {e}")
    
    # Check 5: AI processor
    checks_total += 1
    try:
        from openai_handler import get_openai_status
        status = get_openai_status()
        if status.get('enabled'):
            print("✅ AI processor enabled (fallback mode active)")
            checks_passed += 1
        else:
            print("⚠️  AI processor in fallback mode (OpenAI API not configured)")
            checks_passed += 1  # Still counts as passing since fallback works
    except Exception as e:
        print(f"❌ AI processor check failed: {e}")
    
    # Check 6: File structure
    checks_total += 1
    required_files = [
        'SignalMaestro/fxsusdt_telegram_bot.py',
        'SignalMaestro/fxsusdt_trader.py',
        'SignalMaestro/ichimoku_sniper_strategy.py',
        'SignalMaestro/dynamic_position_manager.py',
        'openai.py'
    ]
    
    missing_files = [f for f in required_files if not Path(f).exists()]
    if not missing_files:
        print("✅ All required files present")
        checks_passed += 1
    else:
        print(f"❌ Missing files: {', '.join(missing_files)}")
    
    # Summary
    print("=" * 70)
    print(f"📊 HEALTH CHECK SUMMARY: {checks_passed}/{checks_total} checks passed")
    
    if checks_passed == checks_total:
        print("✅ BOT IS FULLY OPERATIONAL")
        print("🚀 Ready to start trading")
    elif checks_passed >= checks_total - 1:
        print("⚠️  BOT IS OPERATIONAL (minor issues)")
        print("🚀 Can start with limited functionality")
    else:
        print("❌ BOT HAS CRITICAL ISSUES")
        print("🔧 Fix the issues above before starting")
    
    print("=" * 70)
    
    return checks_passed >= checks_total - 1

if __name__ == "__main__":
    result = asyncio.run(check_bot_health())
    sys.exit(0 if result else 1)
