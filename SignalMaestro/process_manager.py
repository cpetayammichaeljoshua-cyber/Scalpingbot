
#!/usr/bin/env python3
"""
Enhanced Process Manager for Perfect Scalping Bot
Provides keep-alive, heartbeat monitoring, and automatic restart capabilities
"""

import os
import sys
import time
import signal
import subprocess
import threading
import psutil
import json
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

class ProcessManager:
    """Enhanced process manager with keep-alive and monitoring"""
    
    def __init__(self, script_path: str = "SignalMaestro/perfect_scalping_bot.py"):
        self.script_path = script_path
        self.process = None
        self.running = False
        self.restart_count = 0
        self.max_restarts = 1000
        self.restart_delay = 5
        self.heartbeat_interval = 30
        self.max_memory_mb = 1000
        self.max_cpu_percent = 90
        
        # Monitoring
        self.last_heartbeat = None
        self.health_check_failures = 0
        self.max_health_failures = 3
        
        # Status files
        self.pid_file = Path("process_manager.pid")
        self.status_file = Path("process_status.json")
        self.log_file = Path("process_manager.log")
        
        # Statistics
        self.stats = {
            'start_time': datetime.now().isoformat(),
            'total_restarts': 0,
            'last_restart': None,
            'uptime_total': 0,
            'health_checks': 0,
            'health_failures': 0
        }
        
        self._setup_logging()
        self._setup_signal_handlers()
        
    def _setup_logging(self):
        """Setup logging for process manager"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - PROCESS_MGR - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.info(f"🛑 Received signal {signum}, shutting down...")
            self.running = False
            self.stop_process()
            sys.exit(0)
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        # Handle status signal (SIGUSR1)
        if hasattr(signal, 'SIGUSR1'):
            def status_handler(signum, frame):
                self._log_status_report()
            signal.signal(signal.SIGUSR1, status_handler)
    
    def _write_pid_file(self):
        """Write process manager PID file"""
        try:
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))
            self.logger.info(f"📝 Process manager PID: {os.getpid()}")
        except Exception as e:
            self.logger.error(f"Could not write PID file: {e}")
    
    def _update_status(self, status: str, details: Dict[str, Any] = None):
        """Update status file"""
        try:
            status_data = {
                'status': status,
                'timestamp': datetime.now().isoformat(),
                'manager_pid': os.getpid(),
                'bot_pid': self.process.pid if self.process else None,
                'restart_count': self.restart_count,
                'uptime_seconds': (datetime.now() - datetime.fromisoformat(self.stats['start_time'])).total_seconds(),
                'stats': self.stats
            }
            if details:
                status_data.update(details)
                
            with open(self.status_file, 'w') as f:
                json.dump(status_data, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Could not update status: {e}")
    
    def start_process(self) -> bool:
        """Start the bot process with enhanced monitoring"""
        try:
            if self.is_process_running():
                self.logger.warning("Process already running")
                return True
            
            self.logger.info(f"🚀 Starting bot process (attempt #{self.restart_count + 1})")
            
            # Start process with proper environment
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'  # Ensure unbuffered output
            
            self.process = subprocess.Popen([
                sys.executable, self.script_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
            bufsize=1,
            universal_newlines=True
            )
            
            # Wait for successful startup
            time.sleep(3)
            
            if self.is_process_running():
                self.restart_count += 1
                self.stats['total_restarts'] += 1
                self.stats['last_restart'] = datetime.now().isoformat()
                self.last_heartbeat = datetime.now()
                
                self.logger.info(f"✅ Bot started successfully (PID: {self.process.pid})")
                self._update_status('running', {'bot_pid': self.process.pid})
                
                # Start output monitoring in separate thread
                threading.Thread(target=self._monitor_output, daemon=True).start()
                
                return True
            else:
                self.logger.error("❌ Bot failed to start")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error starting process: {e}")
            return False
    
    def stop_process(self, force: bool = False) -> bool:
        """Stop the bot process gracefully"""
        if not self.is_process_running():
            self.logger.info("Process not running")
            return True
            
        try:
            self.logger.info(f"🛑 Stopping bot process (PID: {self.process.pid})")
            
            if force:
                self.process.kill()
                self.logger.info("💥 Process forcefully killed")
            else:
                self.process.terminate()
                try:
                    self.process.wait(timeout=15)
                    self.logger.info("✅ Process stopped gracefully")
                except subprocess.TimeoutExpired:
                    self.logger.warning("⚠️ Graceful shutdown timeout, forcing...")
                    self.process.kill()
            
            self.process = None
            self._update_status('stopped')
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping process: {e}")
            return False
    
    def restart_process(self) -> bool:
        """Restart the bot process"""
        self.logger.info("🔄 Restarting bot process...")
        
        if self.is_process_running():
            self.stop_process()
            
        time.sleep(self.restart_delay)
        return self.start_process()
    
    def is_process_running(self) -> bool:
        """Check if bot process is running"""
        if not self.process:
            return False
        try:
            return self.process.poll() is None
        except:
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        health = {
            'healthy': False,
            'checks': {},
            'issues': [],
            'recommendations': []
        }
        
        self.stats['health_checks'] += 1
        
        # Check if process is running
        process_running = self.is_process_running()
        health['checks']['process_running'] = process_running
        
        if not process_running:
            health['issues'].append("Bot process is not running")
            self.health_check_failures += 1
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
                health['recommendations'].append("Consider restarting to free memory")
            
            # CPU check
            cpu_percent = bot_process.cpu_percent(interval=1)
            health['checks']['cpu_percent'] = cpu_percent
            health['checks']['cpu_ok'] = cpu_percent < self.max_cpu_percent
            
            if cpu_percent > self.max_cpu_percent:
                health['issues'].append(f"High CPU usage: {cpu_percent:.1f}%")
            
            # Heartbeat check
            if self.last_heartbeat:
                heartbeat_age = (datetime.now() - self.last_heartbeat).total_seconds()
                health['checks']['heartbeat_age'] = heartbeat_age
                health['checks']['heartbeat_ok'] = heartbeat_age < 300  # 5 minutes
                
                if heartbeat_age > 300:
                    health['issues'].append(f"Stale heartbeat: {heartbeat_age:.0f}s ago")
            
            # Overall health
            health['healthy'] = (
                process_running and 
                memory_mb < self.max_memory_mb and 
                cpu_percent < self.max_cpu_percent and
                len(health['issues']) == 0
            )
            
            if health['healthy']:
                self.health_check_failures = 0
            else:
                self.health_check_failures += 1
                self.stats['health_failures'] += 1
                
        except Exception as e:
            health['issues'].append(f"Health check error: {e}")
            self.health_check_failures += 1
            self.stats['health_failures'] += 1
        
        return health
    
    def _monitor_output(self):
        """Monitor process output for heartbeat and errors"""
        try:
            while self.is_process_running():
                if self.process.stdout:
                    line = self.process.stdout.readline()
                    if line:
                        # Look for heartbeat patterns in output
                        if any(keyword in line.lower() for keyword in ['scanning', 'signal', 'heartbeat', 'update']):
                            self.last_heartbeat = datetime.now()
                        
                        # Log critical errors
                        if any(keyword in line.lower() for keyword in ['error', 'exception', 'failed']):
                            self.logger.warning(f"Bot output: {line.strip()}")
                        
                time.sleep(1)
                
        except Exception as e:
            self.logger.error(f"Error monitoring output: {e}")
    
    def keep_alive_loop(self):
        """Main keep-alive monitoring loop"""
        self.logger.info("🔍 Starting keep-alive monitoring...")
        
        while self.running:
            try:
                # Check if process is still running
                if not self.is_process_running():
                    self.logger.warning("⚠️ Bot process died, restarting...")
                    if self.restart_count < self.max_restarts:
                        if self.start_process():
                            self.logger.info("✅ Bot restarted successfully")
                        else:
                            self.logger.error("❌ Failed to restart bot")
                            break
                    else:
                        self.logger.error("❌ Maximum restart limit reached")
                        break
                
                # Periodic health check
                health = self.health_check()
                if not health['healthy']:
                    self.logger.warning(f"⚠️ Health check failed: {health['issues']}")
                    
                    # Auto-restart on consecutive health failures
                    if self.health_check_failures >= self.max_health_failures:
                        self.logger.warning("🚨 Multiple health check failures, restarting...")
                        self.restart_process()
                        self.health_check_failures = 0
                
                self._update_status('monitoring', {'health': health})
                
                time.sleep(self.heartbeat_interval)
                
            except KeyboardInterrupt:
                self.logger.info("🛑 Keep-alive interrupted")
                break
            except Exception as e:
                self.logger.error(f"Keep-alive loop error: {e}")
                time.sleep(10)
    
    def start_manager(self):
        """Start the process manager"""
        self.logger.info("🤖 Starting Enhanced Process Manager")
        self.logger.info(f"📁 Script: {self.script_path}")
        self.logger.info(f"🆔 Manager PID: {os.getpid()}")
        
        # Write PID file
        self._write_pid_file()
        
        self.running = True
        
        # Start bot initially
        if not self.start_process():
            self.logger.error("❌ Failed to start bot initially")
            return False
        
        # Start keep-alive monitoring
        try:
            self.keep_alive_loop()
        except KeyboardInterrupt:
            self.logger.info("🛑 Manager interrupted")
        finally:
            self._cleanup()
        
        return True
    
    def _cleanup(self):
        """Cleanup on shutdown"""
        self.logger.info("🧹 Cleaning up process manager...")
        
        if self.is_process_running():
            self.stop_process()
        
        if self.pid_file.exists():
            self.pid_file.unlink()
        
        self._update_status('stopped')
        self.logger.info("✅ Process manager cleanup complete")
    
    def _log_status_report(self):
        """Log comprehensive status report"""
        uptime = datetime.now() - datetime.fromisoformat(self.stats['start_time'])
        
        status_report = f"""
📊 **PROCESS MANAGER STATUS REPORT**
⏰ Uptime: {uptime.days}d {uptime.seconds//3600}h {(uptime.seconds%3600)//60}m
🔄 Total Restarts: {self.stats['total_restarts']}
🏥 Health Checks: {self.stats['health_checks']}
❌ Health Failures: {self.stats['health_failures']}
🤖 Bot PID: {self.process.pid if self.process else 'N/A'}
🛡️ Manager Status: {'Running' if self.running else 'Stopped'}
💾 Memory Usage: {self._get_memory_usage()} MB
"""
        self.logger.info(status_report)
    
    def _get_memory_usage(self) -> float:
        """Get current memory usage"""
        try:
            process = psutil.Process(os.getpid())
            return round(process.memory_info().rss / 1024 / 1024, 2)
        except:
            return 0.0
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status"""
        if self.status_file.exists():
            try:
                with open(self.status_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        return {
            'status': 'unknown',
            'manager_running': False,
            'bot_running': False
        }

def main():
    """CLI interface for process manager"""
    if len(sys.argv) < 2:
        print("""
🤖 Enhanced Process Manager for Perfect Scalping Bot

Usage:
  python process_manager.py <command>

Commands:
  start     - Start process manager and bot
  stop      - Stop process manager and bot
  restart   - Restart everything
  status    - Show detailed status
  health    - Health check
  logs      - Show recent logs (optional: number of lines)
  kill      - Force kill all processes

Examples:
  python process_manager.py start
  python process_manager.py status
  python process_manager.py logs 100
        """)
        return
    
    command = sys.argv[1].lower()
    manager = ProcessManager()
    
    if command == 'start':
        print("🚀 Starting Enhanced Process Manager...")
        manager.start_manager()
        
    elif command == 'stop':
        status = manager.get_status()
        if status.get('manager_pid'):
            try:
                os.kill(status['manager_pid'], signal.SIGTERM)
                print("🛑 Stop signal sent to process manager")
            except ProcessLookupError:
                print("❌ Process manager not running")
        else:
            print("❌ No process manager PID found")
            
    elif command == 'restart':
        # Stop first
        status = manager.get_status()
        if status.get('manager_pid'):
            try:
                os.kill(status['manager_pid'], signal.SIGTERM)
                time.sleep(3)
            except ProcessLookupError:
                pass
        
        # Start new
        manager.start_manager()
        
    elif command == 'status':
        status = manager.get_status()
        print(f"\n📊 Process Manager Status:")
        print(f"Status: {status.get('status', 'unknown')}")
        print(f"Manager PID: {status.get('manager_pid', 'N/A')}")
        print(f"Bot PID: {status.get('bot_pid', 'N/A')}")
        print(f"Restart Count: {status.get('restart_count', 0)}")
        if status.get('uptime_seconds'):
            uptime = timedelta(seconds=status['uptime_seconds'])
            print(f"Uptime: {uptime}")
        
        # Show health if available
        health = status.get('health', {})
        if health:
            print(f"\n🏥 Health: {'✅ Healthy' if health.get('healthy') else '⚠️ Issues'}")
            for check, result in health.get('checks', {}).items():
                icon = '✅' if result else '❌'
                print(f"  {icon} {check}: {result}")
        
    elif command == 'health':
        health = manager.health_check()
        print(f"\n🏥 Health Check: {'✅ Healthy' if health['healthy'] else '⚠️ Issues'}")
        
        print("\n📋 Checks:")
        for check, result in health.get('checks', {}).items():
            icon = '✅' if result else '❌'
            print(f"  {icon} {check}: {result}")
        
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
        
        if manager.log_file.exists():
            print(f"\n📋 Recent Logs ({lines} lines):")
            print("=" * 60)
            try:
                with open(manager.log_file, 'r') as f:
                    all_lines = f.readlines()
                    recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                    print(''.join(recent_lines))
            except Exception as e:
                print(f"Error reading logs: {e}")
        else:
            print("No log file found")
    
    elif command == 'kill':
        print("💥 Force killing all bot processes...")
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'perfect_scalping_bot.py' in cmdline or 'process_manager.py' in cmdline:
                    proc.kill()
                    print(f"Killed process {proc.info['pid']}: {proc.info['name']}")
        except Exception as e:
            print(f"Error: {e}")
    
    else:
        print(f"❌ Unknown command: {command}")

if __name__ == "__main__":
    main()
