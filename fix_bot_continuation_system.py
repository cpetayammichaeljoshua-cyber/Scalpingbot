
#!/usr/bin/env python3
"""
Bot Continuation System - Dynamically Perfectly Advanced Flexible Adaptable Comprehensive
Fixes the issue where bot stops after 5th method completes and ensures continuous signal pushing
"""

import asyncio
import logging
import subprocess
import json
import os
import time
import signal
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import psutil
from datetime import datetime, timedelta

class BotContinuationSystem:
    """Advanced system to ensure bot continues operation after workflow completion"""
    
    def __init__(self):
        self.setup_logging()
        self.running = True
        self.monitored_processes = {}
        self.restart_count = 0
        self.last_health_check = datetime.now()
        
        # Configuration
        self.health_check_interval = 30  # seconds
        self.max_restart_attempts = 10
        self.process_timeout = 300  # 5 minutes
        
        # Process priority order
        self.bot_priority = [
            ("python continuous_signal_pusher.py", "Continuous Signal Pusher", True),
            ("python start_ultimate_bot.py", "Ultimate Trading Bot", False),
            ("python SignalMaestro/ultimate_trading_bot.py", "Ultimate Trading Bot Direct", False),
            ("python SignalMaestro/perfect_scalping_bot.py", "Perfect Scalping Bot", False),
            ("python SignalMaestro/enhanced_signal_bot.py", "Enhanced Signal Bot", False)
        ]
        
        # Signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        self.logger.info("Bot Continuation System initialized")
    
    def setup_logging(self):
        """Setup logging system"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - BOT_CONTINUATION - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_dir / "bot_continuation_system.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"🛑 Received shutdown signal {signum}")
        self.running = False
        self.stop_all_processes()
        sys.exit(0)
    
    def stop_all_processes(self):
        """Stop all monitored processes"""
        for proc_name, process in self.monitored_processes.items():
            try:
                if process and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
                    self.logger.info(f"✅ Stopped {proc_name}")
            except Exception as e:
                self.logger.error(f"Error stopping {proc_name}: {e}")
    
    async def check_ultimate_workflow_status(self) -> bool:
        """Check if Ultimate Combined Workflow has completed"""
        try:
            # Check if workflow report exists
            report_file = Path("ULTIMATE_COMBINED_WORKFLOW_REPORT.md")
            if report_file.exists():
                with open(report_file, 'r') as f:
                    content = f.read()
                    if "WORKFLOW COMPLETED SUCCESSFULLY" in content:
                        self.logger.info("✅ Ultimate Combined Workflow completed successfully")
                        return True
            
            # Check process files
            process_file = Path("ultimate_bot_process.json")
            if process_file.exists():
                with open(process_file, 'r') as f:
                    process_info = json.load(f)
                    pid = process_info.get('pid')
                    
                    if pid and psutil.pid_exists(pid):
                        process = psutil.Process(pid)
                        if process.is_running():
                            self.logger.info(f"✅ Process {pid} still running")
                            return False
            
            return True  # Assume completed if no active processes
            
        except Exception as e:
            self.logger.error(f"Error checking workflow status: {e}")
            return True
    
    async def start_process(self, command: str, name: str, critical: bool = False) -> Optional[subprocess.Popen]:
        """Start a new process"""
        try:
            self.logger.info(f"🚀 Starting {name}...")
            self.logger.info(f"📝 Command: {command}")
            
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            
            process = subprocess.Popen(
                command.split(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                bufsize=1
            )
            
            # Wait for process to stabilize
            await asyncio.sleep(5)
            
            if process.poll() is None:
                self.logger.info(f"✅ {name} started successfully (PID: {process.pid})")
                self.monitored_processes[name] = process
                
                # Save process info
                process_info = {
                    'name': name,
                    'pid': process.pid,
                    'command': command,
                    'start_time': datetime.now().isoformat(),
                    'critical': critical
                }
                
                with open(f'{name.lower().replace(" ", "_")}_process.json', 'w') as f:
                    json.dump(process_info, f, indent=2)
                
                return process
            else:
                self.logger.error(f"❌ {name} failed to start")
                return None
                
        except Exception as e:
            self.logger.error(f"Error starting {name}: {e}")
            return None
    
    async def ensure_critical_processes_running(self):
        """Ensure critical processes are running"""
        try:
            # Check if workflow has completed
            workflow_completed = await self.check_ultimate_workflow_status()
            
            if workflow_completed:
                self.logger.info("🔄 Ultimate workflow completed, ensuring continuous operation...")
                
                # Start critical processes
                for command, name, critical in self.bot_priority:
                    if critical:
                        # Check if already running
                        if name in self.monitored_processes:
                            process = self.monitored_processes[name]
                            if process and process.poll() is None:
                                continue  # Already running
                        
                        # Start the process
                        process = await self.start_process(command, name, critical)
                        if process:
                            break  # Successfully started critical process
                
                # Start supporting processes
                for command, name, critical in self.bot_priority:
                    if not critical and len(self.monitored_processes) < 3:
                        if name not in self.monitored_processes:
                            await self.start_process(command, name, critical)
                            await asyncio.sleep(2)  # Stagger starts
            
        except Exception as e:
            self.logger.error(f"Error ensuring critical processes: {e}")
    
    async def health_check_processes(self):
        """Perform health check on all processes"""
        try:
            dead_processes = []
            
            for name, process in self.monitored_processes.items():
                if process.poll() is not None:  # Process has died
                    self.logger.warning(f"⚠️ Process {name} has stopped")
                    dead_processes.append(name)
            
            # Remove dead processes
            for name in dead_processes:
                del self.monitored_processes[name]
            
            # Restart critical processes if needed
            if dead_processes:
                await self.ensure_critical_processes_running()
            
            self.last_health_check = datetime.now()
            
        except Exception as e:
            self.logger.error(f"Error in health check: {e}")
    
    async def monitor_webview_updates(self):
        """Monitor for webview update failures and fix them"""
        try:
            # Start enhanced webview error handler
            webview_handler_started = False
            
            for name, process in self.monitored_processes.items():
                if "webview" in name.lower() or "error_handler" in name.lower():
                    webview_handler_started = True
                    break
            
            if not webview_handler_started:
                self.logger.info("🌐 Starting enhanced webview error handler...")
                await self.start_process(
                    "python enhanced_webview_error_handler.py", 
                    "Enhanced Webview Error Handler", 
                    False
                )
                
        except Exception as e:
            self.logger.error(f"Error monitoring webview updates: {e}")
    
    async def fix_signal_channel_connection(self):
        """Fix signal pushing to Telegram channel"""
        try:
            # Ensure Telegram bot token is available
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            if not bot_token:
                self.logger.error("❌ No Telegram bot token found")
                return
            
            # Test channel access
            import aiohttp
            
            url = f"https://api.telegram.org/bot{bot_token}/getChat"
            params = {'chat_id': '@SignalTactics'}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        self.logger.info("✅ Telegram channel access confirmed")
                    else:
                        self.logger.warning("⚠️ Telegram channel access issue")
            
        except Exception as e:
            self.logger.error(f"Error fixing signal channel connection: {e}")
    
    async def continuous_monitoring_loop(self):
        """Main continuous monitoring loop"""
        self.logger.info("🔍 Starting continuous monitoring loop...")
        
        while self.running:
            try:
                # Ensure critical processes are running
                await self.ensure_critical_processes_running()
                
                # Perform health checks
                await self.health_check_processes()
                
                # Monitor webview updates
                await self.monitor_webview_updates()
                
                # Fix signal channel connection
                await self.fix_signal_channel_connection()
                
                # Status report
                active_processes = len([p for p in self.monitored_processes.values() if p.poll() is None])
                self.logger.info(f"📊 Status: {active_processes} active processes, {self.restart_count} restarts")
                
                # Wait before next check
                await asyncio.sleep(self.health_check_interval)
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(10)  # Recovery delay
    
    async def initialize_continuation_system(self):
        """Initialize the bot continuation system"""
        try:
            self.logger.info("🎯 Initializing Bot Continuation System...")
            
            # Wait for any existing processes to complete
            await asyncio.sleep(30)
            
            # Check if Ultimate Combined Workflow completed
            workflow_completed = await self.check_ultimate_workflow_status()
            
            if workflow_completed:
                self.logger.info("✅ Workflow completion detected, starting continuation phase...")
                
                # Ensure continuous signal pusher is running
                await self.ensure_critical_processes_running()
                
                # Start monitoring loop
                await self.continuous_monitoring_loop()
            else:
                self.logger.info("⏳ Waiting for Ultimate Combined Workflow to complete...")
                # Wait and check again
                while self.running and not workflow_completed:
                    await asyncio.sleep(60)  # Check every minute
                    workflow_completed = await self.check_ultimate_workflow_status()
                
                if workflow_completed:
                    await self.initialize_continuation_system()
            
        except Exception as e:
            self.logger.error(f"Error initializing continuation system: {e}")

async def main():
    """Main function"""
    system = BotContinuationSystem()
    await system.initialize_continuation_system()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot Continuation System stopped")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
