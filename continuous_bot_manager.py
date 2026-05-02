
#!/usr/bin/env python3
"""
Continuous Bot Manager - Dynamically Perfectly Advanced Flexible Adaptable Comprehensive
Ensures the trading bot runs continuously and pushes trades to the channel
with advanced error recovery, health monitoring, and auto-restart capabilities
"""

import asyncio
import subprocess
import sys
import os
import json
import time
import signal
import psutil
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import traceback
import threading
import queue

class ContinuousBotManager:
    """Advanced continuous bot manager with comprehensive monitoring and recovery"""
    
    def __init__(self):
        self.setup_logging()
        
        # Bot management configuration
        self.bot_script_priority = [
            ("python start_ultimate_bot.py", "Ultimate Trading Bot V3"),
            ("python SignalMaestro/ultimate_trading_bot.py", "Ultimate Trading Bot"),
            ("python start_enhanced_bot_v2.py", "Enhanced Perfect Scalping Bot V2"),
            ("python SignalMaestro/enhanced_perfect_scalping_bot.py", "Enhanced Perfect Scalping Bot"),
            ("python SignalMaestro/perfect_scalping_bot.py", "Perfect Scalping Bot")
        ]
        
        # Process management
        self.current_process = None
        self.current_bot_name = None
        self.running = True
        self.restart_count = 0
        self.max_restart_attempts = 1000
        self.restart_delay = 10  # seconds
        self.health_check_interval = 30  # seconds
        
        # Status tracking
        self.status_file = Path("continuous_bot_status.json")
        self.pid_file = Path("continuous_bot_manager.pid")
        self.start_time = datetime.now()
        self.last_health_check = None
        self.consecutive_failures = 0
        self.max_consecutive_failures = 3
        
        # Performance metrics
        self.metrics = {
            'total_starts': 0,
            'total_restarts': 0,
            'uptime_seconds': 0,
            'health_checks_passed': 0,
            'health_checks_failed': 0,
            'last_successful_start': None,
            'last_failure': None,
            'consecutive_uptime_record': 0
        }
        
        # Signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Write manager PID
        self.write_manager_pid()
        
    def setup_logging(self):
        """Setup comprehensive logging system"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - CONTINUOUS_BOT_MGR - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_dir / "continuous_bot_manager.log"),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def write_manager_pid(self):
        """Write manager process PID"""
        try:
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))
            self.logger.info(f"🆔 Continuous Bot Manager PID: {os.getpid()}")
        except Exception as e:
            self.logger.error(f"Failed to write PID file: {e}")
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"🛑 Received shutdown signal {signum}")
        self.running = False
        self.stop_current_bot()
        if self.pid_file.exists():
            self.pid_file.unlink()
        sys.exit(0)
    
    def update_status(self, status: str, details: Dict[str, Any] = None):
        """Update status file with current state"""
        try:
            status_data = {
                'status': status,
                'timestamp': datetime.now().isoformat(),
                'manager_pid': os.getpid(),
                'bot_pid': self.current_process.pid if self.current_process else None,
                'bot_name': self.current_bot_name,
                'restart_count': self.restart_count,
                'uptime_seconds': (datetime.now() - self.start_time).total_seconds(),
                'consecutive_failures': self.consecutive_failures,
                'metrics': self.metrics,
                'running': self.running
            }
            
            if details:
                status_data.update(details)
                
            with open(self.status_file, 'w') as f:
                json.dump(status_data, f, indent=2, default=str)
                
        except Exception as e:
            self.logger.error(f"Failed to update status: {e}")
    
    def is_bot_running(self) -> bool:
        """Check if current bot process is running"""
        if not self.current_process:
            return False
        try:
            return self.current_process.poll() is None
        except Exception:
            return False
    
    def start_bot(self) -> bool:
        """Start the trading bot using priority order"""
        for command, bot_name in self.bot_script_priority:
            try:
                self.logger.info(f"🚀 Attempting to start: {bot_name}")
                self.logger.info(f"📝 Command: {command}")
                
                # Start the bot process
                env = os.environ.copy()
                env['PYTHONUNBUFFERED'] = '1'
                
                self.current_process = subprocess.Popen(
                    command.split(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True,
                    text=True,
                    bufsize=1
                )
                
                # Wait for process to stabilize
                await_time = 5
                self.logger.info(f"⏳ Waiting {await_time}s for bot to stabilize...")
                time.sleep(await_time)
                
                # Check if bot started successfully
                if self.is_bot_running():
                    self.current_bot_name = bot_name
                    self.restart_count += 1
                    self.metrics['total_starts'] += 1
                    self.metrics['last_successful_start'] = datetime.now().isoformat()
                    self.consecutive_failures = 0
                    
                    self.logger.info(f"✅ {bot_name} started successfully!")
                    self.logger.info(f"🆔 Bot PID: {self.current_process.pid}")
                    
                    # Start output monitoring
                    self.start_output_monitoring()
                    
                    self.update_status('running', {
                        'bot_pid': self.current_process.pid,
                        'bot_command': command,
                        'start_time': datetime.now().isoformat()
                    })
                    
                    return True
                else:
                    self.logger.warning(f"❌ {bot_name} failed to start properly")
                    self.current_process = None
                    continue
                    
            except Exception as e:
                self.logger.error(f"💥 Error starting {bot_name}: {e}")
                self.current_process = None
                continue
        
        # All bot attempts failed
        self.logger.error("💥 All bot startup attempts failed!")
        self.consecutive_failures += 1
        self.metrics['last_failure'] = datetime.now().isoformat()
        return False
    
    def start_output_monitoring(self):
        """Start monitoring bot output in a separate thread"""
        def monitor_output():
            try:
                while self.is_bot_running() and self.running:
                    if self.current_process and self.current_process.stdout:
                        try:
                            line = self.current_process.stdout.readline()
                            if line:
                                line = line.strip()
                                
                                # Log important messages
                                if any(keyword in line.lower() for keyword in [
                                    'signal', 'trade', 'error', 'exception', 'failed', 
                                    'started', 'connected', 'heartbeat', 'scanning'
                                ]):
                                    self.logger.info(f"🤖 Bot: {line}")
                                
                                # Check for critical errors
                                if any(keyword in line.lower() for keyword in [
                                    'critical', 'fatal', 'crashed', 'died'
                                ]):
                                    self.logger.error(f"🚨 Critical bot error: {line}")
                                    
                        except Exception as e:
                            if self.running:
                                self.logger.warning(f"Output monitoring error: {e}")
                    
                    time.sleep(1)
            except Exception as e:
                if self.running:
                    self.logger.error(f"Output monitoring thread error: {e}")
        
        monitor_thread = threading.Thread(target=monitor_output, daemon=True)
        monitor_thread.start()
    
    def stop_current_bot(self):
        """Stop the current bot process gracefully"""
        if not self.is_bot_running():
            self.logger.info("🔍 No bot process running")
            return True
        
        try:
            self.logger.info(f"🛑 Stopping {self.current_bot_name} (PID: {self.current_process.pid})")
            
            # Try graceful shutdown first
            self.current_process.terminate()
            
            # Wait for graceful shutdown
            try:
                self.current_process.wait(timeout=15)
                self.logger.info("✅ Bot stopped gracefully")
            except subprocess.TimeoutExpired:
                self.logger.warning("⏰ Graceful shutdown timeout, force killing...")
                self.current_process.kill()
                self.current_process.wait()
                self.logger.info("💥 Bot force killed")
            
            self.current_process = None
            self.current_bot_name = None
            
            self.update_status('stopped')
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping bot: {e}")
            return False
    
    def perform_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        health = {
            'healthy': False,
            'checks': {},
            'issues': [],
            'recommendations': []
        }
        
        try:
            # Check if bot is running
            bot_running = self.is_bot_running()
            health['checks']['bot_running'] = bot_running
            
            if not bot_running:
                health['issues'].append("Bot process is not running")
                return health
            
            # Get process information
            bot_process = psutil.Process(self.current_process.pid)
            
            # Memory check
            memory_info = bot_process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            health['checks']['memory_mb'] = round(memory_mb, 2)
            health['checks']['memory_ok'] = memory_mb < 1000  # 1GB limit
            
            if memory_mb > 1000:
                health['issues'].append(f"High memory usage: {memory_mb:.1f}MB")
                health['recommendations'].append("Consider restarting bot to free memory")
            
            # CPU check
            try:
                cpu_percent = bot_process.cpu_percent(interval=1)
                health['checks']['cpu_percent'] = round(cpu_percent, 2)
                health['checks']['cpu_ok'] = cpu_percent < 90
                
                if cpu_percent > 90:
                    health['issues'].append(f"High CPU usage: {cpu_percent:.1f}%")
            except psutil.AccessDenied:
                health['checks']['cpu_percent'] = 'access_denied'
                health['checks']['cpu_ok'] = True  # Assume OK if can't check
            
            # Process age check
            create_time = datetime.fromtimestamp(bot_process.create_time())
            age_seconds = (datetime.now() - create_time).total_seconds()
            health['checks']['uptime_seconds'] = age_seconds
            health['checks']['uptime_healthy'] = age_seconds > 60  # At least 1 minute
            
            # Overall health
            health['healthy'] = (
                bot_running and 
                health['checks']['memory_ok'] and 
                health['checks']['cpu_ok'] and
                health['checks']['uptime_healthy']
            )
            
            if health['healthy']:
                self.metrics['health_checks_passed'] += 1
            else:
                self.metrics['health_checks_failed'] += 1
                
        except psutil.NoSuchProcess:
            health['issues'].append("Bot process no longer exists")
            self.metrics['health_checks_failed'] += 1
        except Exception as e:
            health['issues'].append(f"Health check error: {str(e)}")
            self.metrics['health_checks_failed'] += 1
        
        self.last_health_check = datetime.now()
        return health
    
    def run_continuous_monitoring(self):
        """Main continuous monitoring loop"""
        self.logger.info("🔍 Starting continuous monitoring loop...")
        
        while self.running:
            try:
                current_time = datetime.now()
                
                # Check if bot is still running
                if not self.is_bot_running():
                    self.logger.warning("⚠️ Bot process died, attempting restart...")
                    
                    if self.consecutive_failures >= self.max_consecutive_failures:
                        self.logger.error(f"🚨 Maximum consecutive failures ({self.max_consecutive_failures}) reached")
                        # Increase restart delay for persistent failures
                        extended_delay = min(self.restart_delay * (2 ** self.consecutive_failures), 300)  # Max 5 minutes
                        self.logger.info(f"⏰ Extended restart delay: {extended_delay}s")
                        time.sleep(extended_delay)
                    
                    if self.restart_count < self.max_restart_attempts:
                        self.logger.info(f"🔄 Restart attempt {self.restart_count + 1}/{self.max_restart_attempts}")
                        
                        if self.start_bot():
                            self.logger.info("✅ Bot restarted successfully")
                            self.metrics['total_restarts'] += 1
                        else:
                            self.logger.error("❌ Bot restart failed")
                            time.sleep(self.restart_delay)
                    else:
                        self.logger.error(f"💥 Maximum restart attempts ({self.max_restart_attempts}) reached")
                        break
                
                # Periodic health check
                if (not self.last_health_check or 
                    (current_time - self.last_health_check).total_seconds() >= self.health_check_interval):
                    
                    health = self.perform_health_check()
                    
                    if health['healthy']:
                        self.logger.info("💚 Health check passed")
                        
                        # Update uptime record
                        current_uptime = (current_time - self.start_time).total_seconds()
                        if current_uptime > self.metrics['consecutive_uptime_record']:
                            self.metrics['consecutive_uptime_record'] = current_uptime
                    else:
                        self.logger.warning(f"💛 Health check issues: {health['issues']}")
                        
                        # Auto-restart on critical health issues
                        if len(health['issues']) > 2:
                            self.logger.warning("🔄 Multiple health issues detected, restarting bot...")
                            self.stop_current_bot()
                            time.sleep(5)
                            self.start_bot()
                    
                    self.update_status('monitoring', {'health': health})
                
                # Update metrics
                self.metrics['uptime_seconds'] = (current_time - self.start_time).total_seconds()
                
                # Sleep before next check
                time.sleep(5)  # Check every 5 seconds
                
            except KeyboardInterrupt:
                self.logger.info("🛑 Monitoring interrupted by user")
                break
            except Exception as e:
                self.logger.error(f"💥 Monitoring loop error: {e}")
                time.sleep(10)  # Extended sleep on error
    
    def start_continuous_operation(self):
        """Start continuous bot operation"""
        try:
            self.logger.info("🚀 CONTINUOUS BOT MANAGER STARTING")
            self.logger.info("=" * 80)
            self.logger.info(f"📁 Working Directory: {os.getcwd()}")
            self.logger.info(f"🆔 Manager PID: {os.getpid()}")
            self.logger.info(f"🔄 Max Restart Attempts: {self.max_restart_attempts}")
            self.logger.info(f"⏰ Health Check Interval: {self.health_check_interval}s")
            self.logger.info("=" * 80)
            
            # Initial bot startup
            self.logger.info("🎯 Starting initial bot...")
            if not self.start_bot():
                self.logger.error("💥 Failed to start initial bot!")
                return False
            
            self.logger.info("✅ Initial bot started successfully")
            self.logger.info("🔍 Starting continuous monitoring...")
            
            # Run continuous monitoring
            self.run_continuous_monitoring()
            
            return True
            
        except Exception as e:
            self.logger.error(f"💥 Critical error in continuous operation: {e}")
            self.logger.error(f"📍 Stack trace: {traceback.format_exc()}")
            return False
        
        finally:
            self.logger.info("🧹 Cleaning up...")
            self.stop_current_bot()
            if self.pid_file.exists():
                self.pid_file.unlink()
            self.update_status('stopped')
            self.logger.info("✅ Continuous Bot Manager shutdown complete")

def main():
    """Main entry point"""
    print("🤖 CONTINUOUS BOT MANAGER")
    print("=" * 80)
    print("🎯 Dynamically Perfectly Advanced Flexible Adaptable Comprehensive")
    print("🔄 Ensuring continuous bot operation with advanced monitoring")
    print("🛡️ Auto-restart, health monitoring, and error recovery")
    print("=" * 80)
    
    manager = ContinuousBotManager()
    
    try:
        success = manager.start_continuous_operation()
        if success:
            print("✅ Continuous operation completed successfully")
        else:
            print("❌ Continuous operation failed")
            return 1
    except KeyboardInterrupt:
        print("\n🛑 Manual shutdown requested")
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
