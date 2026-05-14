
#!/usr/bin/env python3
"""
Start Hourly Automation System
Main entry point for the automated backtest and optimization system
"""

import asyncio
import logging
import sys
import os
from pathlib import Path
import subprocess

# Install required packages
required_packages = ['schedule', 'numpy', 'python-telegram-bot', 'aiohttp']
for package in required_packages:
    try:
        __import__(package.replace('-', '_'))
    except ImportError:
        print(f"Installing {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# Add SignalMaestro to path
current_dir = Path(__file__).parent
signal_maestro_path = current_dir / "SignalMaestro"
sys.path.insert(0, str(signal_maestro_path))
sys.path.insert(0, str(current_dir))

try:
    from SignalMaestro.hourly_automation_scheduler import HourlyAutomationScheduler
    from SignalMaestro.automated_backtest_optimizer import AutomatedBacktestOptimizer
except ImportError as e:
    print(f"Import error: {e}")
    try:
        # Try alternative import paths
        from hourly_automation_scheduler import HourlyAutomationScheduler
        from automated_backtest_optimizer import AutomatedBacktestOptimizer
    except ImportError as e2:
        print(f"Alternative import error: {e2}")
        print("Make sure you're running from the correct directory")
        print("Available files:")
        for f in os.listdir(signal_maestro_path):
            if f.endswith('.py'):
                print(f"  - {f}")
        sys.exit(1)

def setup_logging():
    """Setup comprehensive logging"""
    log_dir = Path("SignalMaestro/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / 'hourly_automation.log'),
            logging.StreamHandler()
        ]
    )

async def main():
    """Main function"""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 Starting FXSUSDT Hourly Automation System")
    logger.info("📊 Automated Backtest and Optimization Service")
    logger.info("⏰ Runs every hour for continuous improvement")
    
    # Check required environment variables
    required_secrets = ['TELEGRAM_BOT_TOKEN', 'BINANCE_API_KEY', 'BINANCE_API_SECRET']
    missing_secrets = [secret for secret in required_secrets if not os.getenv(secret)]
    
    if missing_secrets:
        logger.error(f"❌ Missing required secrets: {', '.join(missing_secrets)}")
        logger.error("Please add these to your Replit secrets")
        return 1
    
    # Create necessary directories
    directories = [
        "SignalMaestro/hourly_reports",
        "SignalMaestro/logs",
        "SignalMaestro/backups"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    print("🤖 FXSUSDT HOURLY AUTOMATION SYSTEM")
    print("=" * 50)
    print("📊 Features:")
    print("  • Automated backtesting every hour")
    print("  • Parameter optimization with grid search")
    print("  • Intelligent parameter updates")
    print("  • Performance tracking and reporting")
    print("  • Telegram notifications")
    print("  • Historical data analysis")
    print("")
    print("⏰ Schedule:")
    print("  • Runs at :00 and :30 of every hour")
    print("  • 24/7 continuous optimization")
    print("  • Automatic parameter tuning")
    print("")
    print("📊 Monitoring:")
    print("  • Status: SignalMaestro/hourly_automation_status.json")
    print("  • Reports: SignalMaestro/hourly_reports/")
    print("  • Logs: SignalMaestro/logs/hourly_automation.log")
    print("=" * 50)
    
    # Test single optimization cycle first
    logger.info("🧪 Running initial optimization test...")
    try:
        optimizer = AutomatedBacktestOptimizer()
        test_report = await optimizer.run_hourly_cycle()
        
        print("\n✅ Initial optimization test completed successfully!")
        print("📊 Sample report preview:")
        print("-" * 30)
        print(test_report[:500] + "..." if len(test_report) > 500 else test_report)
        print("-" * 30)
        
    except Exception as e:
        logger.error(f"❌ Initial test failed: {e}")
        print(f"\n❌ Error during initial test: {e}")
        print("Please check your API credentials and try again.")
        return 1
    
    # Start the scheduler
    print("\n🚀 Starting hourly scheduler...")
    print("⏰ The system will now run continuously")
    print("📱 Check your Telegram for notifications")
    print("🛑 Press Ctrl+C to stop")
    print("")
    
    try:
        scheduler = HourlyAutomationScheduler()
        scheduler.start_scheduler()
        
    except KeyboardInterrupt:
        logger.info("👋 Hourly automation stopped by user")
        print("\n👋 Hourly automation system stopped")
        return 0
    except Exception as e:
        logger.error(f"❌ Critical error: {e}")
        print(f"\n❌ Critical error: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
