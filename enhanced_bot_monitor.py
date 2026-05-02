
#!/usr/bin/env python3
"""
Enhanced Bot Monitor
Monitors bot health and automatically fixes console errors
"""

import asyncio
import subprocess
import sys
import os
import json
import logging
import time
import warnings
from datetime import datetime
from pathlib import Path

# Apply fixes at module level
warnings.filterwarnings('ignore')

class EnhancedBotMonitor:
    """Enhanced bot monitoring with automatic error fixing"""
    
    def __init__(self):
        self.setup_logging()
        self.bot_process = None
        self.running = True
        self.restart_count = 0
        
    def setup_logging(self):
        """Setup clean logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - MONITOR - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('logs/bot_monitor.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Suppress noisy loggers
        logging.getLogger('urllib3').setLevel(logging.ERROR)
        logging.getLogger('requests').setLevel(logging.ERROR)
        
    def apply_console_fixes(self):
        """Apply console fixes"""
        try:
            subprocess.run([sys.executable, 'apply_comprehensive_console_fixes.py'], 
                         capture_output=True, text=True, timeout=30)
            self.logger.info("✅ Console fixes applied")
        except Exception as e:
            self.logger.warning(f"⚠️ Console fixes failed: {e}")
    
    def start_bot(self):
        """Start the bot process"""
        try:
            self.logger.info("🚀 Starting FXSUSDT bot...")
            
            # Apply fixes before starting
            self.apply_console_fixes()
            
            # Start bot process
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            
            self.bot_process = subprocess.Popen(
                [sys.executable, 'start_fxsusdt_bot_fixed.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                text=True
            )
            
            self.logger.info(f"✅ Bot started with PID: {self.bot_process.pid}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to start bot: {e}")
            return False
    
    def is_bot_healthy(self):
        """Check if bot is healthy"""
        if not self.bot_process:
            return False
        
        return self.bot_process.poll() is None
    
    def restart_bot(self):
        """Restart the bot"""
        self.logger.info("🔄 Restarting bot...")
        
        # Stop current process
        if self.bot_process:
            try:
                self.bot_process.terminate()
                self.bot_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.bot_process.kill()
                self.bot_process.wait()
        
        # Wait before restart
        time.sleep(5)
        
        # Start new process
        if self.start_bot():
            self.restart_count += 1
            self.logger.info(f"✅ Bot restarted successfully (restart #{self.restart_count})")
        else:
            self.logger.error("❌ Bot restart failed")
    
    async def monitor_loop(self):
        """Main monitoring loop"""
        self.logger.info("👁️ Starting enhanced bot monitoring...")
        
        # Initial bot start
        if not self.start_bot():
            self.logger.error("❌ Failed to start bot initially")
            return
        
        while self.running:
            try:
                # Check bot health
                if not self.is_bot_healthy():
                    self.logger.warning("⚠️ Bot is not healthy, restarting...")
                    self.restart_bot()
                
                # Update status
                status = {
                    'timestamp': datetime.now().isoformat(),
                    'bot_running': self.is_bot_healthy(),
                    'restart_count': self.restart_count,
                    'monitor_status': 'active'
                }
                
                with open('enhanced_bot_status.json', 'w') as f:
                    json.dump(status, f, indent=2)
                
                # Wait before next check
                await asyncio.sleep(30)
                
            except KeyboardInterrupt:
                self.logger.info("🛑 Monitor stopped by user")
                break
            except Exception as e:
                self.logger.error(f"❌ Monitor error: {e}")
                await asyncio.sleep(10)
        
        # Cleanup
        if self.bot_process:
            self.bot_process.terminate()
            
        self.logger.info("✅ Monitor stopped")

async def main():
    """Main function"""
    monitor = EnhancedBotMonitor()
    await monitor.monitor_loop()

if __name__ == "__main__":
    asyncio.run(main())
