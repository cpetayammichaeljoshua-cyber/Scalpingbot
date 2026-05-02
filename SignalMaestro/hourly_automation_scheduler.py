
#!/usr/bin/env python3
"""
Hourly Automation Scheduler
Runs automated backtest and optimization every hour
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
import threading
import json
import sys
import os

# Install schedule if not available
try:
    import schedule
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "schedule"])
    import schedule

try:
    from automated_backtest_optimizer import AutomatedBacktestOptimizer
    from fxsusdt_telegram_bot import FXSUSDTTelegramBot
except ImportError as e:
    print(f"Import error: {e}")
    # Add current directory to path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    try:
        from automated_backtest_optimizer import AutomatedBacktestOptimizer
        from fxsusdt_telegram_bot import FXSUSDTTelegramBot
    except ImportError:
        print("Failed to import required modules. Please check file paths.")
        sys.exit(1)

class HourlyAutomationScheduler:
    """Scheduler for hourly automated optimization"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.optimizer = AutomatedBacktestOptimizer()
        self.telegram_bot = None
        self.running = False
        self.status_file = Path("SignalMaestro/hourly_automation_status.json")
        
        # Initialize Telegram bot for notifications
        try:
            self.telegram_bot = FXSUSDTTelegramBot()
            self.logger.info("✅ Telegram bot initialized for notifications")
        except Exception as e:
            self.logger.warning(f"Telegram bot not available: {e}")
        
        self.logger.info("⏰ Hourly Automation Scheduler initialized")
    
    def save_status(self, status: dict):
        """Save current status to file"""
        try:
            with open(self.status_file, 'w') as f:
                json.dump(status, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving status: {e}")
    
    def load_status(self) -> dict:
        """Load status from file"""
        try:
            if self.status_file.exists():
                with open(self.status_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading status: {e}")
        
        return {
            'last_run': None,
            'next_run': None,
            'cycles_completed': 0,
            'total_optimizations_applied': 0,
            'last_optimization_score': 0,
            'status': 'initialized'
        }
    
    async def run_optimization_cycle(self):
        """Run one optimization cycle and handle notifications"""
        try:
            start_time = datetime.now()
            self.logger.info(f"🚀 Starting automated optimization cycle at {start_time.strftime('%H:%M:%S')}")
            
            # Pre-cycle error checking and fixing
            try:
                from comprehensive_error_fixer import ComprehensiveErrorFixer
                error_fixer = ComprehensiveErrorFixer()
                
                # Apply quick fixes before optimization
                optimizations = await error_fixer.optimize_bot_performance()
                if optimizations:
                    self.logger.info(f"Applied {len(optimizations)} pre-optimization fixes")
            except Exception as e:
                self.logger.warning(f"Error in pre-cycle optimization: {e}")
            
            # Update status
            status = self.load_status()
            status['status'] = 'running'
            status['last_run'] = start_time.isoformat()
            self.save_status(status)
            
            # Send start notification
            if self.telegram_bot and self.telegram_bot.admin_chat_id:
                await self.telegram_bot.send_message(
                    self.telegram_bot.admin_chat_id,
                    f"🤖 **Hourly Optimization Started**\n\n⏰ Time: {start_time.strftime('%H:%M UTC')}\n📊 Running automated backtest and parameter optimization..."
                )
            
            # Run the optimization cycle
            report = await self.optimizer.run_hourly_cycle()
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            # Update status
            status = self.load_status()
            status['status'] = 'completed'
            status['cycles_completed'] = status.get('cycles_completed', 0) + 1
            status['last_duration_seconds'] = duration
            status['next_run'] = (end_time + timedelta(hours=1)).isoformat()
            self.save_status(status)
            
            # Send completion notification with report
            if self.telegram_bot and self.telegram_bot.admin_chat_id:
                summary_report = f"""✅ **Hourly Optimization Complete**

⏱️ **Duration:** {duration:.1f} seconds
🔄 **Cycle:** #{status['cycles_completed']}
📈 **Next Run:** {(end_time + timedelta(hours=1)).strftime('%H:%M UTC')}

{report}"""
                
                # Split long messages if needed
                if len(summary_report) > 4000:
                    # Send summary first
                    summary = f"""✅ **Hourly Optimization Complete**

⏱️ **Duration:** {duration:.1f} seconds
🔄 **Cycle:** #{status['cycles_completed']}
📈 **Next Run:** {(end_time + timedelta(hours=1)).strftime('%H:%M UTC')}

📊 Full report saved. Use /admin status for details."""
                    
                    await self.telegram_bot.send_message(self.telegram_bot.admin_chat_id, summary)
                else:
                    await self.telegram_bot.send_message(self.telegram_bot.admin_chat_id, summary_report)
            
            self.logger.info(f"✅ Optimization cycle completed in {duration:.1f}s")
            
        except Exception as e:
            self.logger.error(f"Error in optimization cycle: {e}")
            
            # Update status with error
            status = self.load_status()
            status['status'] = 'error'
            status['last_error'] = str(e)
            status['error_time'] = datetime.now().isoformat()
            self.save_status(status)
            
            # Send error notification
            if self.telegram_bot and self.telegram_bot.admin_chat_id:
                await self.telegram_bot.send_message(
                    self.telegram_bot.admin_chat_id,
                    f"❌ **Optimization Cycle Failed**\n\n🕐 Time: {datetime.now().strftime('%H:%M UTC')}\n💥 Error: {str(e)}\n\n🔄 Will retry next hour."
                )
    
    def schedule_optimization_cycle(self):
        """Schedule the optimization cycle to run"""
        def run_async_optimization():
            try:
                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.run_optimization_cycle())
                loop.close()
            except Exception as e:
                self.logger.error(f"Error in scheduled optimization: {e}")
        
        # Run in separate thread to avoid blocking
        thread = threading.Thread(target=run_async_optimization, daemon=True)
        thread.start()
    
    def start_scheduler(self):
        """Start the hourly scheduler"""
        self.running = True
        
        # Schedule to run at the top of every hour
        schedule.every().hour.at(":00").do(self.schedule_optimization_cycle)
        
        # Also schedule a few extra runs for testing
        schedule.every().hour.at(":30").do(self.schedule_optimization_cycle)  # Half-hour runs for more frequent optimization
        
        self.logger.info("⏰ Scheduler started - running every hour at :00 and :30")
        
        # Update status
        status = self.load_status()
        status['status'] = 'scheduled'
        status['scheduler_started'] = datetime.now().isoformat()
        status['next_run'] = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        status['next_run'] = status['next_run'].isoformat()
        self.save_status(status)
        
        # Run first cycle immediately (optional)
        self.logger.info("🚀 Running initial optimization cycle...")
        self.schedule_optimization_cycle()
        
        # Keep the scheduler running
        try:
            while self.running:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            self.logger.info("👋 Scheduler stopped by user")
            self.stop_scheduler()
    
    def stop_scheduler(self):
        """Stop the scheduler"""
        self.running = False
        schedule.clear()
        
        # Update status
        status = self.load_status()
        status['status'] = 'stopped'
        status['scheduler_stopped'] = datetime.now().isoformat()
        self.save_status(status)
        
        self.logger.info("🛑 Scheduler stopped")
    
    def get_status_report(self) -> str:
        """Get current status report"""
        status = self.load_status()
        
        current_time = datetime.now()
        
        if status.get('last_run'):
            last_run = datetime.fromisoformat(status['last_run'])
            time_since_last = current_time - last_run
            last_run_str = f"{last_run.strftime('%H:%M UTC')} ({time_since_last.total_seconds()/3600:.1f}h ago)"
        else:
            last_run_str = "Never"
        
        if status.get('next_run'):
            next_run = datetime.fromisoformat(status['next_run'])
            time_to_next = next_run - current_time
            next_run_str = f"{next_run.strftime('%H:%M UTC')} (in {time_to_next.total_seconds()/3600:.1f}h)"
        else:
            next_run_str = "Not scheduled"
        
        report = f"""⏰ **HOURLY AUTOMATION STATUS**

🔄 **Current Status:** {status.get('status', 'Unknown').upper()}
📊 **Last Run:** {last_run_str}
📈 **Next Run:** {next_run_str}
🎯 **Cycles Completed:** {status.get('cycles_completed', 0)}
⚡ **Optimizations Applied:** {status.get('total_optimizations_applied', 0)}

🤖 **System Health:** {'🟢 Running' if self.running else '🔴 Stopped'}
📅 **Uptime:** {(current_time - datetime.fromisoformat(status.get('scheduler_started', current_time.isoformat()))).total_seconds()/3600:.1f}h
"""
        
        if status.get('last_error'):
            error_time = datetime.fromisoformat(status['error_time'])
            time_since_error = current_time - error_time
            report += f"\n⚠️ **Last Error:** {status['last_error']}\n📅 **Error Time:** {error_time.strftime('%H:%M UTC')} ({time_since_error.total_seconds()/3600:.1f}h ago)"
        
        return report

async def main():
    """Main function"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('SignalMaestro/hourly_automation.log'),
            logging.StreamHandler()
        ]
    )
    
    scheduler = HourlyAutomationScheduler()
    
    print("🚀 Starting Hourly Automation Scheduler...")
    print("⏰ Will run optimization every hour at :00 and :30")
    print("🤖 Telegram notifications enabled")
    print("📊 Status saved to: SignalMaestro/hourly_automation_status.json")
    print("📜 Logs saved to: SignalMaestro/hourly_automation.log")
    print("\nPress Ctrl+C to stop...")
    
    try:
        scheduler.start_scheduler()
    except KeyboardInterrupt:
        print("\n👋 Stopping scheduler...")
        scheduler.stop_scheduler()

if __name__ == "__main__":
    asyncio.run(main())
