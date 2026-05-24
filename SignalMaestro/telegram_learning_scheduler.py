
#!/usr/bin/env python3
"""
Telegram Learning Scheduler
Regularly scans Telegram channel for new trades and retrains ML models
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional
import schedule
import time
import threading

class TelegramLearningScheduler:
    """Scheduler for automatic Telegram scanning and ML retraining"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.scheduler_thread = None
        
        # Configuration from environment
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.channel_username = os.getenv('TELEGRAM_CHANNEL', '@SignalTactics')
        self.scan_interval_hours = int(os.getenv('SCAN_INTERVAL_HOURS', '6'))  # Scan every 6 hours
        self.retrain_after_trades = int(os.getenv('RETRAIN_THRESHOLD', '5'))  # Retrain after 5 new trades
        
        # Track last scan time
        self.last_scan_time = None
        self.new_trades_count = 0
    
    def start(self):
        """Start the learning scheduler"""
        if not self.bot_token:
            self.logger.warning("⚠️ No Telegram bot token configured - scheduler disabled")
            return False
        
        self.running = True
        
        # Schedule regular scans
        schedule.every(self.scan_interval_hours).hours.do(self._schedule_scan_and_retrain)
        
        # Schedule immediate scan on startup
        schedule.every().minute.do(self._initial_scan).tag('initial')
        
        # Start scheduler thread
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        self.logger.info(f"📅 Telegram learning scheduler started - scanning every {self.scan_interval_hours} hours")
        return True
    
    def stop(self):
        """Stop the learning scheduler"""
        self.running = False
        schedule.clear()
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        
        self.logger.info("📅 Telegram learning scheduler stopped")
    
    def _run_scheduler(self):
        """Run the scheduler in a separate thread"""
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except Exception as e:
                self.logger.error(f"Scheduler error: {e}")
                time.sleep(300)  # Wait 5 minutes on error
    
    def _initial_scan(self):
        """Perform initial scan on startup"""
        try:
            asyncio.create_task(self.scan_and_retrain())
            schedule.clear('initial')  # Remove initial scan job
        except Exception as e:
            self.logger.error(f"Initial scan error: {e}")
    
    def _schedule_scan_and_retrain(self):
        """Schedule scan and retrain task"""
        try:
            asyncio.create_task(self.scan_and_retrain())
        except Exception as e:
            self.logger.error(f"Scheduled scan error: {e}")
    
    async def scan_and_retrain(self):
        """Scan Telegram channel and retrain ML models if needed"""
        try:
            self.logger.info("🔍 Starting scheduled Telegram scan and ML retraining...")
            
            # Import components
            from telegram_trade_scanner import TelegramTradeScanner
            from ml_trade_analyzer import MLTradeAnalyzer
            
            # Initialize scanner
            scanner = TelegramTradeScanner(self.bot_token, self.channel_username)
            
            # Determine scan period (since last scan or default 24 hours)
            days_back = 1  # Default to last 24 hours
            if self.last_scan_time:
                hours_since_scan = (datetime.now() - self.last_scan_time).total_seconds() / 3600
                days_back = max(1, int(hours_since_scan / 24))
            
            # Scan for new trades
            trade_responses = await scanner.scan_channel_history(days_back=days_back)
            
            if trade_responses:
                # Store new trades
                await scanner.store_scanned_trades(trade_responses)
                self.new_trades_count += len(trade_responses)
                
                self.logger.info(f"📈 Found {len(trade_responses)} new trades from Telegram")
                
                # Check if we should retrain
                if self.new_trades_count >= self.retrain_after_trades:
                    # Initialize ML analyzer and retrain
                    ml_analyzer = MLTradeAnalyzer()
                    await ml_analyzer.analyze_and_learn(include_telegram_data=True)
                    
                    self.logger.info(f"🧠 ML models retrained with {self.new_trades_count} new trades")
                    self.new_trades_count = 0  # Reset counter
                else:
                    self.logger.info(f"📊 {self.new_trades_count}/{self.retrain_after_trades} trades collected - waiting for more data")
            else:
                self.logger.info("📭 No new trades found in Telegram channel")
            
            # Update last scan time
            self.last_scan_time = datetime.now()
            
            # Generate learning summary
            await self._generate_learning_summary()
            
        except Exception as e:
            self.logger.error(f"❌ Error in scheduled scan and retrain: {e}")
    
    async def _generate_learning_summary(self):
        """Generate and log learning progress summary"""
        try:
            from ml_trade_analyzer import MLTradeAnalyzer
            
            ml_analyzer = MLTradeAnalyzer()
            summary = ml_analyzer.get_learning_summary()
            
            self.logger.info(f"""
📊 Learning Progress Summary:
• Total Trades Analyzed: {summary.get('total_trades_analyzed', 0)}
• Win Rate: {summary.get('win_rate', 0):.1%}
• Total Insights: {summary.get('total_insights_generated', 0)}
• Learning Status: {summary.get('learning_status', 'unknown').title()}
• Last Scan: {self.last_scan_time.strftime('%Y-%m-%d %H:%M') if self.last_scan_time else 'Never'}
• Next Scan: {(datetime.now() + timedelta(hours=self.scan_interval_hours)).strftime('%Y-%m-%d %H:%M')}
            """)
            
        except Exception as e:
            self.logger.error(f"Error generating learning summary: {e}")
    
    def force_scan_and_retrain(self):
        """Force immediate scan and retrain"""
        try:
            asyncio.create_task(self.scan_and_retrain())
            self.logger.info("🔄 Force scan and retrain triggered")
        except Exception as e:
            self.logger.error(f"Error forcing scan and retrain: {e}")
    
    def get_status(self) -> dict:
        """Get scheduler status"""
        return {
            'running': self.running,
            'last_scan_time': self.last_scan_time.isoformat() if self.last_scan_time else None,
            'new_trades_count': self.new_trades_count,
            'retrain_threshold': self.retrain_after_trades,
            'scan_interval_hours': self.scan_interval_hours,
            'next_scan_time': (datetime.now() + timedelta(hours=self.scan_interval_hours)).isoformat() if self.running else None
        }

# Global scheduler instance
_scheduler_instance = None

def get_scheduler() -> TelegramLearningScheduler:
    """Get or create scheduler instance"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = TelegramLearningScheduler()
    return _scheduler_instance

def start_learning_scheduler():
    """Start the learning scheduler"""
    scheduler = get_scheduler()
    return scheduler.start()

def stop_learning_scheduler():
    """Stop the learning scheduler"""
    global _scheduler_instance
    if _scheduler_instance:
        _scheduler_instance.stop()
        _scheduler_instance = None

if __name__ == "__main__":
    # Test the scheduler
    import logging
    logging.basicConfig(level=logging.INFO)
    
    scheduler = TelegramLearningScheduler()
    if scheduler.start():
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            scheduler.stop()
    else:
        print("Failed to start scheduler")
