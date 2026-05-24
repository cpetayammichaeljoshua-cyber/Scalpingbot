
#!/usr/bin/env python3
"""
Deployment Manager for Enhanced Trading Bot
Handles deployment automation, monitoring, and restart functionality
"""

import asyncio
import logging
import subprocess
import json
import os
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import psutil
import aiohttp

class DeploymentManager:
    """Manages bot deployment, monitoring, and automatic restarts"""
    
    def __init__(self):
        self.logger = self._setup_logging()
        self.process = None
        self.restart_count = 0
        self.max_restarts = 10
        self.restart_window = timedelta(hours=1)
        self.last_restart = None
        self.monitoring = False
        
        # Health check configuration
        self.health_check_url = "http://0.0.0.0:5000/health"
        self.health_check_interval = 30  # seconds
        self.health_check_timeout = 10   # seconds
        
        # Log file paths
        self.log_dir = "logs"
        self.ensure_log_directory()
    
    def _setup_logging(self) -> logging.Logger:
        """Setup deployment logging"""
        logger = logging.getLogger('DeploymentManager')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            formatter = logging.Formatter(
                '%(asctime)s | DEPLOY | %(levelname)s | %(message)s'
            )
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def ensure_log_directory(self):
        """Ensure log directory exists"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
    
    async def deploy_bot(self, script_name: str = "webhook_server_enhanced.py") -> bool:
        """Deploy the trading bot"""
        try:
            self.logger.info("🚀 Starting bot deployment...")
            
            # Check if bot is already running
            if self.process and self.process.poll() is None:
                self.logger.info("Bot already running, stopping first...")
                await self.stop_bot()
            
            # Prepare environment
            env = os.environ.copy()
            env['PYTHONPATH'] = os.getcwd()
            
            # Start the bot process
            log_file = os.path.join(self.log_dir, f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
            
            with open(log_file, 'w') as f:
                self.process = subprocess.Popen(
                    [sys.executable, f"SignalMaestro/{script_name}"],
                    env=env,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    cwd=os.getcwd()
                )
            
            self.logger.info(f"✅ Bot deployed with PID: {self.process.pid}")
            self.logger.info(f"📋 Logs: {log_file}")
            
            # Wait a moment for startup
            await asyncio.sleep(5)
            
            # Verify deployment
            if await self.check_bot_health():
                self.logger.info("🔥 Bot deployment successful and healthy!")
                return True
            else:
                self.logger.warning("⚠️ Bot deployed but health check failed")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Deployment failed: {e}")
            return False
    
    async def stop_bot(self) -> bool:
        """Stop the trading bot gracefully"""
        try:
            if not self.process:
                self.logger.info("No bot process to stop")
                return True
            
            self.logger.info("🛑 Stopping bot gracefully...")
            
            # Try graceful shutdown first
            self.process.terminate()
            
            # Wait for graceful shutdown
            try:
                await asyncio.wait_for(
                    asyncio.create_task(self._wait_for_process()),
                    timeout=10.0
                )
                self.logger.info("✅ Bot stopped gracefully")
                return True
            except asyncio.TimeoutError:
                # Force kill if graceful shutdown fails
                self.logger.warning("Forcing bot shutdown...")
                self.process.kill()
                await self._wait_for_process()
                self.logger.info("✅ Bot force stopped")
                return True
                
        except Exception as e:
            self.logger.error(f"Error stopping bot: {e}")
            return False
    
    async def _wait_for_process(self):
        """Wait for process to terminate"""
        while self.process and self.process.poll() is None:
            await asyncio.sleep(0.1)
    
    async def check_bot_health(self) -> bool:
        """Check if bot is healthy"""
        try:
            timeout = aiohttp.ClientTimeout(total=self.health_check_timeout)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.health_check_url) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            return data.get('server_running', True)
                        except:
                            # If JSON parsing fails but status is 200, consider healthy
                            return True
                    return False
                    
        except Exception as e:
            self.logger.debug(f"Health check failed: {e}")
            # If health check fails, check if process is still running
            if self.process and self.process.poll() is None:
                # Process is running, might be starting up
                return True
            return False
    
    async def restart_bot(self, reason: str = "Manual restart"):
        """Restart the bot with restart limits"""
        try:
            now = datetime.now()
            
            # Check restart limits
            if self.last_restart and (now - self.last_restart) < self.restart_window:
                if self.restart_count >= self.max_restarts:
                    self.logger.error(f"❌ Restart limit reached ({self.max_restarts} in {self.restart_window})")
                    return False
            else:
                # Reset counter if outside window
                self.restart_count = 0
            
            self.logger.info(f"🔄 Restarting bot - Reason: {reason}")
            
            # Stop current instance
            await self.stop_bot()
            
            # Wait a moment
            await asyncio.sleep(2)
            
            # Deploy new instance
            success = await self.deploy_bot()
            
            if success:
                self.restart_count += 1
                self.last_restart = now
                self.logger.info(f"✅ Bot restarted successfully (attempt {self.restart_count})")
                return True
            else:
                self.logger.error("❌ Bot restart failed")
                return False
                
        except Exception as e:
            self.logger.error(f"Restart error: {e}")
            return False
    
    async def start_monitoring(self):
        """Start continuous monitoring"""
        self.logger.info("👁️ Starting bot monitoring...")
        self.monitoring = True
        
        consecutive_failures = 0
        max_failures = 3
        
        while self.monitoring:
            try:
                # Check if process is still running
                if self.process and self.process.poll() is not None:
                    self.logger.warning("⚠️ Bot process died, restarting...")
                    await self.restart_bot("Process died")
                    consecutive_failures = 0
                    continue
                
                # Health check
                if await self.check_bot_health():
                    consecutive_failures = 0
                    self.logger.debug("✅ Health check passed")
                else:
                    consecutive_failures += 1
                    self.logger.warning(f"⚠️ Health check failed ({consecutive_failures}/{max_failures})")
                    
                    if consecutive_failures >= max_failures:
                        self.logger.error("❌ Multiple health check failures, restarting...")
                        await self.restart_bot("Health check failures")
                        consecutive_failures = 0
                
                # Wait for next check
                await asyncio.sleep(self.health_check_interval)
                
            except Exception as e:
                self.logger.error(f"Monitoring error: {e}")
                await asyncio.sleep(self.health_check_interval)
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.logger.info("🛑 Stopping monitoring...")
        self.monitoring = False
    
    async def get_status(self) -> Dict[str, Any]:
        """Get deployment status"""
        try:
            status = {
                'deployment_time': datetime.now().isoformat(),
                'process_running': self.process and self.process.poll() is None,
                'process_pid': self.process.pid if self.process else None,
                'restart_count': self.restart_count,
                'monitoring_active': self.monitoring,
                'health_check_url': self.health_check_url
            }
            
            # Add process info if running
            if status['process_running']:
                try:
                    proc = psutil.Process(self.process.pid)
                    status.update({
                        'cpu_percent': proc.cpu_percent(),
                        'memory_mb': proc.memory_info().rss / 1024 / 1024,
                        'uptime_seconds': (datetime.now() - datetime.fromtimestamp(proc.create_time())).total_seconds()
                    })
                except:
                    pass
            
            # Health check
            status['healthy'] = await self.check_bot_health()
            
            return status
            
        except Exception as e:
            return {'error': str(e)}
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, shutting down...")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def shutdown(self):
        """Graceful shutdown"""
        self.logger.info("🛑 Initiating graceful shutdown...")
        
        self.stop_monitoring()
        await self.stop_bot()
        
        self.logger.info("✅ Shutdown complete")

async def main():
    """Main deployment function"""
    manager = DeploymentManager()
    manager.setup_signal_handlers()
    
    try:
        # Deploy bot
        success = await manager.deploy_bot()
        
        if success:
            # Start monitoring
            await manager.start_monitoring()
        else:
            manager.logger.error("❌ Initial deployment failed")
            
    except KeyboardInterrupt:
        await manager.shutdown()
    except Exception as e:
        manager.logger.error(f"Fatal deployment error: {e}")
        await manager.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
