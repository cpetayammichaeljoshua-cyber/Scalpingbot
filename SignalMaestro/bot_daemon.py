
#!/usr/bin/env python3
"""
Advanced Bot Daemon Manager - PM2-like functionality for Python
Provides continuous operation, auto-restart, and health monitoring
"""

import os
import sys
import time
import json
import signal
import subprocess
import threading
import psutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import logging

class BotDaemon:
    """Advanced daemon manager for the Perfect Scalping Bot"""
    
    def __init__(self):
        self.bot_script = "SignalMaestro/perfect_scalping_bot.py"
        self.pid_file = Path("bot_daemon.pid")
        self.status_file = Path("bot_daemon_status.json")
        self.log_file = Path("bot_daemon.log")
        self.process = None
        self.running = False
        self.restart_count = 0
        self.max_restarts = 1000
        self.start_time = None
        self.last_health_check = None
        self.auto_restart = True
        self.restart_delay = 5  # seconds
        
        # Health monitoring
        self.health_check_interval = 60  # seconds
        self.max_memory_mb = 500  # MB
        self.max_cpu_percent = 80  # %
        
        # Statistics
        self.stats = {
            'total_restarts': 0,
            'uptime_total': 0,
            'last_crash_time': None,
            'crash_count': 0,
            'health_checks_passed': 0,
            'health_checks_failed': 0
        }
        
        self._setup_logging()
        self._load_stats()
        
    def _setup_logging(self):
        """Setup daemon logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - BOT_DAEMON - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def _load_stats(self):
        """Load persistent statistics"""
        stats_file = Path("bot_daemon_stats.json")
        if stats_file.exists():
            try:
                with open(stats_file, 'r') as f:
                    self.stats.update(json.load(f))
            except Exception as e:
                self.logger.warning(f"Could not load stats: {e}")
    
    def _save_stats(self):
        """Save persistent statistics"""
        try:
            with open("bot_daemon_stats.json", 'w') as f:
                json.dump(self.stats, f, indent=2, default=str)
        except Exception as e:
            self.logger.warning(f"Could not save stats: {e}")
    
    def _write_pid_file(self):
        """Write daemon PID file"""
        try:
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))
        except Exception as e:
            self.logger.error(f"Could not write PID file: {e}")
    
    def _update_status(self, status: str, details: Dict[str, Any] = None):
        """Update status file"""
        try:
            status_data = {
                'status': status,
                'timestamp': datetime.now().isoformat(),
                'daemon_pid': os.getpid(),
                'bot_pid': self.process.pid if self.process else None,
                'restart_count': self.restart_count,
                'uptime_seconds': (datetime.now() - self.start_time).total_seconds() if self.start_time else 0,
                'auto_restart': self.auto_restart,
                'stats': self.stats
            }
            if details:
                status_data.update(details)
                
            with open(self.status_file, 'w') as f:
                json.dump(status_data, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Could not update status: {e}")
    
    def is_bot_running(self) -> bool:
        """Check if bot process is running"""
        if not self.process:
            return False
        try:
            return self.process.poll() is None
        except:
            return False
    
    def start_bot(self) -> bool:
        """Start the bot process"""
        try:
            self.logger.info(f"🚀 Starting bot (attempt #{self.restart_count + 1})")
            
            # Start bot process
            self.process = subprocess.Popen([
                sys.executable, self.bot_script
            ], 
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True
            )
            
            # Wait a moment to check if it started successfully
            time.sleep(2)
            
            if self.is_bot_running():
                self.restart_count += 1
                if not self.start_time:
                    self.start_time = datetime.now()
                    
                self.logger.info(f"✅ Bot started successfully (PID: {self.process.pid})")
                self._update_status('running', {
                    'bot_pid': self.process.pid,
                    'start_time': datetime.now().isoformat()
                })
                return True
            else:
                self.logger.error("❌ Bot failed to start")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error starting bot: {e}")
            return False
    
    def stop_bot(self, force: bool = False) -> bool:
        """Stop the bot process"""
        if not self.is_bot_running():
            self.logger.info("Bot is not running")
            return True
            
        try:
            self.logger.info(f"🛑 Stopping bot (PID: {self.process.pid})")
            
            if force:
                self.process.kill()
                self.logger.info("💥 Bot forcefully killed")
            else:
                self.process.terminate()
                # Wait for graceful shutdown
                try:
                    self.process.wait(timeout=10)
                    self.logger.info("✅ Bot stopped gracefully")
                except subprocess.TimeoutExpired:
                    self.logger.warning("⚠️ Graceful shutdown timeout, forcing...")
                    self.process.kill()
            
            self.process = None
            self._update_status('stopped')
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping bot: {e}")
            return False
    
    def restart_bot(self) -> bool:
        """Restart the bot process"""
        self.logger.info("🔄 Restarting bot...")
        
        if self.is_bot_running():
            self.stop_bot()
            
        time.sleep(self.restart_delay)
        return self.start_bot()
    
    def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        health = {
            'healthy': False,
            'checks': {},
            'issues': [],
            'recommendations': []
        }
        
        # Check if bot is running
        bot_running = self.is_bot_running()
        health['checks']['bot_running'] = bot_running
        
        if not bot_running:
            health['issues'].append("Bot process is not running")
            return health
        
        try:
            # Get process info
            bot_process = psutil.Process(self.process.pid)
            
            # Memory check
            memory_mb = bot_process.memory_info().rss / 1024 / 1024
            health['checks']['memory_mb'] = memory_mb
            health['checks']['memory_ok'] = memory_mb < self.max_memory_mb
            
            if memory_mb > self.max_memory_mb:
                health['issues'].append(f"High memory usage: {memory_mb:.1f}MB")
                health['recommendations'].append("Consider restarting bot to free memory")
            
            # CPU check
            cpu_percent = bot_process.cpu_percent(interval=1)
            health['checks']['cpu_percent'] = cpu_percent
            health['checks']['cpu_ok'] = cpu_percent < self.max_cpu_percent
            
            if cpu_percent > self.max_cpu_percent:
                health['issues'].append(f"High CPU usage: {cpu_percent:.1f}%")
            
            # Restart count check
            health['checks']['restart_count'] = self.restart_count
            health['checks']['restart_count_ok'] = self.restart_count < 50
            
            if self.restart_count > 20:
                health['issues'].append(f"High restart count: {self.restart_count}")
                health['recommendations'].append("Check logs for recurring errors")
            
            # Overall health
            health['healthy'] = (
                bot_running and 
                memory_mb < self.max_memory_mb and 
                cpu_percent < self.max_cpu_percent
            )
            
            if health['healthy']:
                self.stats['health_checks_passed'] += 1
            else:
                self.stats['health_checks_failed'] += 1
                
        except Exception as e:
            health['issues'].append(f"Health check error: {e}")
            self.stats['health_checks_failed'] += 1
        
        self.last_health_check = datetime.now()
        return health
    
    def monitor_loop(self):
        """Main monitoring loop"""
        self.logger.info("🔍 Starting bot monitoring...")
        
        while self.running:
            try:
                # Check if bot is still running
                if not self.is_bot_running():
                    self.logger.warning("⚠️ Bot process died, restarting...")
                    self.stats['crash_count'] += 1
                    self.stats['last_crash_time'] = datetime.now().isoformat()
                    
                    if self.auto_restart and self.restart_count < self.max_restarts:
                        if self.restart_bot():
                            self.stats['total_restarts'] += 1
                        else:
                            self.logger.error("❌ Failed to restart bot")
                            break
                    else:
                        self.logger.error("❌ Auto-restart disabled or max restarts reached")
                        break
                
                # Periodic health check
                if (not self.last_health_check or 
                    (datetime.now() - self.last_health_check).total_seconds() > self.health_check_interval):
                    
                    health = self.health_check()
                    if not health['healthy']:
                        self.logger.warning(f"⚠️ Health check failed: {health['issues']}")
                    
                    self._update_status('monitoring', {'health': health})
                
                # Save stats periodically
                self._save_stats()
                
                time.sleep(5)  # Check every 5 seconds
                
            except KeyboardInterrupt:
                self.logger.info("🛑 Monitor interrupted by user")
                break
            except Exception as e:
                self.logger.error(f"Monitor loop error: {e}")
                time.sleep(10)
    
    def start_daemon(self):
        """Start daemon mode"""
        self.logger.info("🤖 Starting Bot Daemon Manager")
        self.logger.info(f"📁 Working Directory: {os.getcwd()}")
        self.logger.info(f"🆔 Daemon PID: {os.getpid()}")
        
        # Write daemon PID
        self._write_pid_file()
        
        # Set signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        self.running = True
        self.start_time = datetime.now()
        
        # Start bot initially
        if not self.start_bot():
            self.logger.error("❌ Failed to start bot initially")
            return False
        
        # Start monitoring in separate thread
        monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        monitor_thread.start()
        
        try:
            # Keep daemon alive
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("🛑 Daemon interrupted")
        finally:
            self._cleanup()
        
        return True
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"🛑 Received signal {signum}, shutting down...")
        self.running = False
        self.auto_restart = False
        self.stop_bot()
    
    def _cleanup(self):
        """Cleanup on shutdown"""
        self.logger.info("🧹 Cleaning up daemon...")
        
        if self.is_bot_running():
            self.stop_bot()
        
        if self.pid_file.exists():
            self.pid_file.unlink()
        
        self._update_status('stopped')
        self._save_stats()
        
        self.logger.info("✅ Daemon cleanup complete")
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive daemon status"""
        if self.status_file.exists():
            try:
                with open(self.status_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        return {
            'status': 'unknown',
            'daemon_running': False,
            'bot_running': False
        }

def main():
    """CLI interface for daemon management"""
    daemon = BotDaemon()
    
    if len(sys.argv) < 2:
        print("""
🤖 Perfect Scalping Bot Daemon Manager

Usage:
  python bot_daemon.py <command>

Commands:
  start     - Start daemon and bot
  stop      - Stop daemon and bot
  restart   - Restart daemon and bot
  status    - Show status
  health    - Health check
  logs      - Show recent logs
  stats     - Show statistics

Advanced:
  monitor   - Start monitoring only
  kill      - Force kill all processes

Examples:
  python bot_daemon.py start
  python bot_daemon.py status
  python bot_daemon.py health
        """)
        return
    
    command = sys.argv[1].lower()
    
    if command == 'start':
        print("🚀 Starting Bot Daemon...")
        daemon.start_daemon()
        
    elif command == 'stop':
        status = daemon.get_status()
        if status.get('daemon_pid'):
            try:
                os.kill(status['daemon_pid'], signal.SIGTERM)
                print("🛑 Stop signal sent to daemon")
            except ProcessLookupError:
                print("❌ Daemon not running")
        else:
            print("❌ No daemon PID found")
            
    elif command == 'restart':
        # Stop first
        status = daemon.get_status()
        if status.get('daemon_pid'):
            try:
                os.kill(status['daemon_pid'], signal.SIGTERM)
                time.sleep(3)
            except ProcessLookupError:
                pass
        
        # Start new
        daemon.start_daemon()
        
    elif command == 'status':
        status = daemon.get_status()
        print("\n📊 Daemon Status:")
        print(f"Status: {status.get('status', 'unknown')}")
        print(f"Daemon PID: {status.get('daemon_pid', 'N/A')}")
        print(f"Bot PID: {status.get('bot_pid', 'N/A')}")
        print(f"Restart Count: {status.get('restart_count', 0)}")
        if status.get('uptime_seconds'):
            uptime = timedelta(seconds=status['uptime_seconds'])
            print(f"Uptime: {uptime}")
        
    elif command == 'health':
        health = daemon.health_check()
        print(f"\n🏥 Health Check: {'✅ Healthy' if health['healthy'] else '⚠️ Issues'}")
        
        print("\n📋 Checks:")
        for check, result in health.get('checks', {}).items():
            status_icon = '✅' if result else '❌'
            print(f"  {status_icon} {check}: {result}")
        
        if health.get('issues'):
            print("\n⚠️ Issues:")
            for issue in health['issues']:
                print(f"  • {issue}")
                
        if health.get('recommendations'):
            print("\n💡 Recommendations:")
            for rec in health['recommendations']:
                print(f"  • {rec}")
    
    elif command == 'logs':
        lines = 50
        if len(sys.argv) > 2:
            try:
                lines = int(sys.argv[2])
            except ValueError:
                pass
        
        if daemon.log_file.exists():
            print(f"\n📋 Recent Logs ({lines} lines):")
            print("=" * 50)
            try:
                with open(daemon.log_file, 'r') as f:
                    all_lines = f.readlines()
                    recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                    print(''.join(recent_lines))
            except Exception as e:
                print(f"Error reading logs: {e}")
        else:
            print("No log file found")
    
    elif command == 'stats':
        daemon._load_stats()
        print("\n📊 Statistics:")
        print(f"Total Restarts: {daemon.stats.get('total_restarts', 0)}")
        print(f"Crash Count: {daemon.stats.get('crash_count', 0)}")
        print(f"Health Checks Passed: {daemon.stats.get('health_checks_passed', 0)}")
        print(f"Health Checks Failed: {daemon.stats.get('health_checks_failed', 0)}")
        if daemon.stats.get('last_crash_time'):
            print(f"Last Crash: {daemon.stats['last_crash_time']}")
    
    elif command == 'kill':
        print("💥 Force killing all bot processes...")
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if 'perfect_scalping_bot.py' in ' '.join(proc.info['cmdline'] or []):
                    proc.kill()
                    print(f"Killed process {proc.info['pid']}")
        except Exception as e:
            print(f"Error: {e}")
    
    else:
        print(f"❌ Unknown command: {command}")

if __name__ == "__main__":
    main()
