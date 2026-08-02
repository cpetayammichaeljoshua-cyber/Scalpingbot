
#!/usr/bin/env python3
"""
Replit Daemon System for Perfect Scalping Bot
Optimized for Replit's infrastructure with auto-restart and monitoring
"""

import os
import sys
import time
import signal
import asyncio
import logging
import subprocess
import json
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import aiohttp

class ReplitDaemon:
    """Replit-optimized daemon for indefinite bot operation"""
    
    def __init__(self, script_path: str = "SignalMaestro/perfect_scalping_bot.py"):
        self.script_path = script_path
        self.process = None
        self.running = False
        self.restart_count = 0
        self.max_restarts = 99999  # Virtually unlimited
        self.restart_delay = 10
        self.health_check_interval = 60
        self.max_memory_mb = 512  # Replit memory limit
        
        # Replit-specific settings
        self.replit_keep_alive_port = 8080
        self.keep_alive_server = None
        
        # Status tracking
        self.status_file = Path("bot_daemon_status.json")
        self.log_file = Path("daemon.log")
        self.pid_file = Path("daemon.pid")
        
        # Statistics
        self.stats = {
            'start_time': datetime.now().isoformat(),
            'total_restarts': 0,
            'last_restart': None,
            'uptime_total': 0,
            'health_checks': 0,
            'last_health_check': None
        }
        
        self._setup_logging()
        self._setup_signal_handlers()
        self._write_pid_file()
        
    def _setup_logging(self):
        """Setup logging optimized for Replit"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - DAEMON - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file, mode='a'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.info(f"🛑 Received signal {signum}, shutting down daemon...")
            self.running = False
            if self.process:
                self.stop_bot()
            if self.keep_alive_server:
                self.stop_keep_alive_server()
            sys.exit(0)
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
    def _write_pid_file(self):
        """Write daemon PID file"""
        try:
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))
            self.logger.info(f"📝 Daemon PID: {os.getpid()}")
        except Exception as e:
            self.logger.error(f"Could not write PID file: {e}")
    
    def _update_status(self, status: str, details: Dict[str, Any] = None):
        """Update status file for monitoring"""
        try:
            status_data = {
                'status': status,
                'timestamp': datetime.now().isoformat(),
                'daemon_pid': os.getpid(),
                'bot_pid': self.process.pid if self.process else None,
                'restart_count': self.restart_count,
                'uptime_seconds': (datetime.now() - datetime.fromisoformat(self.stats['start_time'])).total_seconds(),
                'stats': self.stats,
                'replit_optimized': True
            }
            if details:
                status_data.update(details)
                
            with open(self.status_file, 'w') as f:
                json.dump(status_data, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Could not update status: {e}")
    
    async def start_keep_alive_server(self):
        """Start keep-alive HTTP server for Replit"""
        from aiohttp import web
        
        async def health_check(request):
            """Health check endpoint"""
            health = {
                'status': 'healthy' if self.is_bot_running() else 'unhealthy',
                'daemon_pid': os.getpid(),
                'bot_pid': self.process.pid if self.process else None,
                'restart_count': self.restart_count,
                'uptime': (datetime.now() - datetime.fromisoformat(self.stats['start_time'])).total_seconds(),
                'timestamp': datetime.now().isoformat()
            }
            return web.json_response(health)
        
        async def status_endpoint(request):
            """Detailed status endpoint"""
            if self.status_file.exists():
                try:
                    with open(self.status_file, 'r') as f:
                        status = json.load(f)
                    return web.json_response(status)
                except (json.JSONDecodeError, ValueError, KeyError, TypeError):  # NEXT-5: narrowed from bare except
                    pass
            return web.json_response({'error': 'Status not available'})
        
        app = web.Application()
        app.router.add_get('/', health_check)
        app.router.add_get('/health', health_check)
        app.router.add_get('/status', status_endpoint)
        
        try:
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', self.replit_keep_alive_port)
            await site.start()
            self.keep_alive_server = runner
            self.logger.info(f"🌐 Keep-alive server started on port {self.replit_keep_alive_port}")
        except Exception as e:
            self.logger.error(f"Failed to start keep-alive server: {e}")
    
    def stop_keep_alive_server(self):
        """Stop keep-alive server"""
        if self.keep_alive_server:
            try:
                asyncio.create_task(self.keep_alive_server.cleanup())
                self.logger.info("🛑 Keep-alive server stopped")
            except Exception as e:
                self.logger.error(f"Error stopping keep-alive server: {e}")
    
    def start_bot(self) -> bool:
        """Start the trading bot"""
        try:
            if self.is_bot_running():
                self.logger.warning("Bot already running")
                return True
            
            self.logger.info(f"🚀 Starting bot (attempt #{self.restart_count + 1})")
            
            # Enhanced environment for Replit
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['REPLIT_DAEMON'] = '1'
            
            # Start bot process
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
            
            # Wait for startup
            time.sleep(5)
            
            if self.is_bot_running():
                self.restart_count += 1
                self.stats['total_restarts'] += 1
                self.stats['last_restart'] = datetime.now().isoformat()
                
                self.logger.info(f"✅ Bot started successfully (PID: {self.process.pid})")
                self._update_status('running', {'bot_pid': self.process.pid})
                
                # Start output monitoring
                threading.Thread(target=self._monitor_bot_output, daemon=True).start()
                
                return True
            else:
                self.logger.error("❌ Bot failed to start")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error starting bot: {e}")
            return False
    
    def stop_bot(self, force: bool = False) -> bool:
        """Stop the trading bot"""
        if not self.is_bot_running():
            return True
            
        try:
            self.logger.info(f"🛑 Stopping bot (PID: {self.process.pid})")
            
            if force:
                self.process.kill()
                self.logger.info("💥 Bot forcefully killed")
            else:
                self.process.terminate()
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
    
    def is_bot_running(self) -> bool:
        """Check if bot is running"""
        if not self.process:
            return False
        try:
            return self.process.poll() is None
        except Exception:  # NEXT-5: narrowed from bare except
            return False
    
    def restart_bot(self) -> bool:
        """Restart the bot"""
        self.logger.info("🔄 Restarting bot...")
        
        if self.is_bot_running():
            self.stop_bot()
            
        time.sleep(self.restart_delay)
        return self.start_bot()
    
    def _monitor_bot_output(self):
        """Monitor bot output for health"""
        try:
            last_output = datetime.now()
            
            while self.is_bot_running() and self.running:
                if self.process.stdout:
                    line = self.process.stdout.readline()
                    if line:
                        last_output = datetime.now()
                        
                        # Log important messages
                        if any(keyword in line.lower() for keyword in ['error', 'exception', 'failed', 'critical']):
                            self.logger.warning(f"Bot: {line.strip()}")
                        elif any(keyword in line.lower() for keyword in ['signal', 'trade', 'profit']):
                            self.logger.info(f"Bot: {line.strip()}")
                
                # Check for output timeout (bot might be frozen)
                if (datetime.now() - last_output).total_seconds() > 300:  # 5 minutes
                    self.logger.warning("⚠️ No bot output for 5 minutes, may need restart")
                
                time.sleep(1)
                
        except Exception as e:
            self.logger.error(f"Error monitoring bot output: {e}")
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check"""
        health = {
            'healthy': False,
            'checks': {},
            'issues': [],
            'replit_optimized': True
        }
        
        self.stats['health_checks'] += 1
        self.stats['last_health_check'] = datetime.now().isoformat()
        
        # Check if bot is running
        bot_running = self.is_bot_running()
        health['checks']['bot_running'] = bot_running
        
        if not bot_running:
            health['issues'].append("Bot process is not running")
            return health
        
        try:
            # Memory check (Replit-specific)
            try:
                import psutil
                process = psutil.Process(self.process.pid)
                memory_mb = process.memory_info().rss / 1024 / 1024
                health['checks']['memory_mb'] = memory_mb
                health['checks']['memory_ok'] = memory_mb < self.max_memory_mb
                
                if memory_mb > self.max_memory_mb:
                    health['issues'].append(f"High memory usage: {memory_mb:.1f}MB")
            except ImportError:
                health['checks']['memory_check'] = 'unavailable'
            
            # Overall health
            health['healthy'] = bot_running and len(health['issues']) == 0
            
        except Exception as e:
            health['issues'].append(f"Health check error: {e}")
        
        return health
    
    async def daemon_loop(self):
        """Main daemon loop"""
        self.logger.info("🔍 Starting Replit daemon loop...")
        
        # Start keep-alive server
        await self.start_keep_alive_server()
        
        # Initial bot start
        if not self.start_bot():
            self.logger.error("❌ Failed to start bot initially")
            return False
        
        while self.running:
            try:
                # Check if bot is still running
                if not self.is_bot_running():
                    self.logger.warning("⚠️ Bot process died, restarting...")
                    if self.restart_count < self.max_restarts:
                        if self.restart_bot():
                            self.logger.info("✅ Bot restarted successfully")
                        else:
                            self.logger.error("❌ Failed to restart bot, retrying in 30s...")
                            await asyncio.sleep(30)
                            continue
                    else:
                        self.logger.error("❌ Maximum restart limit reached")
                        break
                
                # Periodic health check
                health = self.health_check()
                self._update_status('monitoring', {'health': health})
                
                if not health['healthy']:
                    self.logger.warning(f"⚠️ Health issues detected: {health['issues']}")
                
                # Wait before next check
                await asyncio.sleep(self.health_check_interval)
                
            except KeyboardInterrupt:
                self.logger.info("🛑 Daemon interrupted")
                break
            except Exception as e:
                self.logger.error(f"Daemon loop error: {e}")
                await asyncio.sleep(10)
        
        return True
    
    def start_daemon(self):
        """Start the daemon"""
        self.logger.info("🤖 Starting Replit Daemon for Perfect Scalping Bot")
        self.logger.info(f"📁 Bot script: {self.script_path}")
        self.logger.info(f"🆔 Daemon PID: {os.getpid()}")
        self.logger.info(f"🌐 Keep-alive port: {self.replit_keep_alive_port}")
        
        self.running = True
        
        try:
            asyncio.run(self.daemon_loop())
        except KeyboardInterrupt:
            self.logger.info("🛑 Daemon interrupted by user")
        finally:
            self._cleanup()
        
        return True
    
    def _cleanup(self):
        """Cleanup on shutdown"""
        self.logger.info("🧹 Cleaning up daemon...")
        
        if self.is_bot_running():
            self.stop_bot()
        
        if self.keep_alive_server:
            self.stop_keep_alive_server()
        
        if self.pid_file.exists():
            self.pid_file.unlink()
        
        self._update_status('stopped')
        self.logger.info("✅ Daemon cleanup complete")

def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("""
🤖 Replit Daemon for Perfect Scalping Bot

Usage:
  python replit_daemon.py <command>

Commands:
  start     - Start daemon and bot
  stop      - Stop daemon and bot  
  restart   - Restart everything
  status    - Show status
  health    - Health check

Examples:
  python replit_daemon.py start
  python replit_daemon.py status
        """)
        return
    
    command = sys.argv[1].lower()
    daemon = ReplitDaemon()
    
    if command == 'start':
        print("🚀 Starting Replit Daemon...")
        daemon.start_daemon()
        
    elif command == 'stop':
        if daemon.pid_file.exists():
            try:
                with open(daemon.pid_file, 'r') as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGTERM)
                print("🛑 Stop signal sent to daemon")
            except (FileNotFoundError, ProcessLookupError):
                print("❌ Daemon not running")
        else:
            print("❌ No daemon PID file found")
            
    elif command == 'restart':
        # Stop first
        if daemon.pid_file.exists():
            try:
                with open(daemon.pid_file, 'r') as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGTERM)
                time.sleep(3)
            except (FileNotFoundError, ProcessLookupError):
                pass
        
        # Start new
        daemon.start_daemon()
        
    elif command == 'status':
        if daemon.status_file.exists():
            try:
                with open(daemon.status_file, 'r') as f:
                    status = json.load(f)
                print(f"\n📊 Replit Daemon Status:")
                print(f"Status: {status.get('status', 'unknown')}")
                print(f"Daemon PID: {status.get('daemon_pid', 'N/A')}")
                print(f"Bot PID: {status.get('bot_pid', 'N/A')}")
                print(f"Restart Count: {status.get('restart_count', 0)}")
                if status.get('uptime_seconds'):
                    uptime = timedelta(seconds=status['uptime_seconds'])
                    print(f"Uptime: {uptime}")
            except Exception as e:
                print(f"Error reading status: {e}")
        else:
            print("No status file found")
    
    elif command == 'health':
        daemon.logger.info("Performing health check...")
        health = daemon.health_check()
        print(f"\n🏥 Health: {'✅ Healthy' if health['healthy'] else '⚠️ Issues'}")
        
        for check, result in health.get('checks', {}).items():
            icon = '✅' if result else '❌'
            print(f"  {icon} {check}: {result}")
        
        if health.get('issues'):
            print("\n⚠️ Issues:")
            for issue in health['issues']:
                print(f"  • {issue}")
    
    else:
        print(f"❌ Unknown command: {command}")

if __name__ == "__main__":
    main()
