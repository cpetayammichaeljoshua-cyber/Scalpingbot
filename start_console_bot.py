#!/usr/bin/env python3
"""
Console Runner for Ultimate Trading Bot
Runs the bot in console mode without daemonization for direct monitoring
"""

import asyncio
import argparse
import json
import logging
import sys
from pathlib import Path

# Set up logging for console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('console_bot.log')
    ]
)

async def main():
    """Main function to run the bot in console mode"""
    parser = argparse.ArgumentParser(description='Run Ultimate Trading Bot in Console Mode')
    parser.add_argument('--config', default='trading_bot_config.json', 
                       help='Path to configuration file')
    parser.add_argument('--console', action='store_true', default=True,
                       help='Run in console mode (default)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Run in dry-run mode for testing')
    
    args = parser.parse_args()
    
    # Load configuration
    config_path = Path(args.config)
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = json.load(f)
        logging.info(f"✅ Configuration loaded from {config_path}")
    else:
        logging.error(f"❌ Configuration file not found: {config_path}")
        sys.exit(1)
    
    # Import bot after config is ready
    bot = None
    try:
        from SignalMaestro.ultimate_trading_bot import UltimateTradingBot
        
        # Initialize bot with console configuration
        bot = UltimateTradingBot()
        
        # Override configuration with loaded config
        await bot.load_external_config(config_path)
        
        # Set console mode
        bot.deployment_mode = "console_workflow"
        bot.dry_run_mode = args.dry_run
        
        logging.info("🚀 Starting Ultimate Trading Bot in Console Mode...")
        logging.info(f"💰 Capital Base: ${config['trading_config']['capital_base']} USDT")
        logging.info(f"⚠️ Risk Percentage: {config['trading_config']['risk_percentage']}%")
        logging.info(f"📈 Market Type: {config['trading_config']['market_type']}")
        logging.info(f"🔧 Dry Run: {'ON' if args.dry_run else 'OFF'}")
        
        # Start the bot
        await bot.run_bot()
        
    except KeyboardInterrupt:
        logging.info("⏹️ Console bot stopped by user")
    except Exception as e:
        logging.error(f"❌ Console bot error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logging.info("🧹 Cleaning up console bot...")
        if bot and hasattr(bot, 'stop'):
            try:
                await bot.stop()
            except:
                pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ Console bot stopped by user")
    except Exception as e:
        print(f"❌ Console bot startup error: {e}")
        sys.exit(1)