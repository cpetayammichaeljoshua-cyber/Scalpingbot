
#!/usr/bin/env python3
"""
Startup script for ML-Enhanced Trading Bot
Handles initialization, monitoring, and auto-restart functionality
"""

import asyncio
import subprocess
import sys
import os
import signal
import time
import json
from datetime import datetime
from pathlib import Path

class MLBotManager:
    """Manager for ML-Enhanced Trading Bot with auto-restart"""
    
    def __init__(self):
        self.bot_script = "SignalMaestro/ml_enhanced_trading_bot.py"
        self.pid_file = Path("ml_enhanced_trading_bot.pid")
        self.status_file = Path("ml_bot_status.json")
        self.log_file = Path("ml_bot_manager.log")
        self.running = True
        self.restart_count = 0
        self.max_restarts = 10
        
    def log(self, message):
        """Log message with timestamp"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] {message}"
        print(log_message)
        
        try:
            with open(self.log_file, 'a') as f:
                f.write(log_message + '\n')
        except:
            pass
    
    def update_status(self, status, details=None):
        """Update bot status file"""
        try:
            status_data = {
                'status': status,
                'timestamp': datetime.now().isoformat(),
                'restart_count': self.restart_count,
                'details': details or {}
            }
            
            with open(self.status_file, 'w') as f:
                json.dump(status_data, f, indent=2)
        except Exception as e:
            self.log(f"Failed to update status: {e}")
    
    def check_bot_running(self):
        """Check if bot is currently running"""
        try:
            if not self.pid_file.exists():
                return False
            
            with open(self.pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            # Check if process exists
            try:
                os.kill(pid, 0)  # This doesn't kill, just checks if process exists
                return True
            except OSError:
                # Process doesn't exist, clean up PID file
                self.pid_file.unlink()
                return False
                
        except Exception as e:
            self.log(f"Error checking bot status: {e}")
            return False
    
    def stop_bot(self):
        """Stop the running bot"""
        try:
            if not self.pid_file.exists():
                self.log("No PID file found - bot may not be running")
                return True
            
            with open(self.pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            self.log(f"Stopping bot with PID {pid}")
            
            # Send SIGTERM for graceful shutdown
            os.kill(pid, signal.SIGTERM)
            
            # Wait for graceful shutdown
            for i in range(30):  # Wait up to 30 seconds
                if not self.check_bot_running():
                    self.log("Bot stopped gracefully")
                    return True
                time.sleep(1)
            
            # Force kill if still running
            self.log("Bot didn't stop gracefully, force killing...")
            os.kill(pid, signal.SIGKILL)
            time.sleep(2)
            
            if self.pid_file.exists():
                self.pid_file.unlink()
            
            return True
            
        except Exception as e:
            self.log(f"Error stopping bot: {e}")
            return False
    
    async def start_bot(self):
        """Start the ML-enhanced trading bot"""
        try:
            if self.check_bot_running():
                self.log("Bot is already running")
                return True
            
            self.log("Starting ML-Enhanced Trading Bot...")
            self.update_status('starting', {'restart_count': self.restart_count})
            
            # Start the bot process
            process = await asyncio.create_subprocess_exec(
                sys.executable, self.bot_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            self.log(f"Bot started with PID {process.pid}")
            self.update_status('running', {'pid': process.pid, 'restart_count': self.restart_count})
            
            # Wait for process to complete and handle restart
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                self.log("Bot exited normally")
                self.update_status('stopped', {'exit_code': 0})
                return False  # Normal exit, don't restart
            else:
                self.log(f"Bot crashed with exit code {process.returncode}")
                if stderr:
                    self.log(f"Error output: {stderr.decode()}")
                self.update_status('crashed', {'exit_code': process.returncode})
                return True  # Crash, should restart
                
        except Exception as e:
            self.log(f"Error starting bot: {e}")
            self.update_status('error', {'error': str(e)})
            return True  # Error, should restart
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.log(f"Received signal {signum}, shutting down...")
            self.running = False
            self.stop_bot()
            sys.exit(0)
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    
    async def monitor_loop(self):
        """Main monitoring loop with auto-restart"""
        self.log("🚀 ML-Enhanced Trading Bot Manager Starting")
        self.log("⚙️ Auto-restart enabled (max 10 restarts)")
        self.log("🧠 Machine Learning features active")
        self.log("⏰ 30-minute cooldown system enabled")
        
        while self.running and self.restart_count < self.max_restarts:
            try:
                should_restart = await self.start_bot()
                
                if should_restart and self.running:
                    self.restart_count += 1
                    wait_time = min(60 * self.restart_count, 300)  # Max 5 minutes
                    
                    self.log(f"🔄 Restart #{self.restart_count}/{self.max_restarts} in {wait_time} seconds")
                    self.update_status('restarting', {
                        'restart_count': self.restart_count,
                        'wait_time': wait_time
                    })
                    
                    await asyncio.sleep(wait_time)
                else:
                    break
                    
            except Exception as e:
                self.log(f"Monitor loop error: {e}")
                await asyncio.sleep(30)
        
        if self.restart_count >= self.max_restarts:
            self.log(f"🛑 Maximum restarts ({self.max_restarts}) reached. Manual intervention required.")
            self.update_status('max_restarts_reached', {'restart_count': self.restart_count})
        else:
            self.log("✅ Bot manager shutting down normally")
            self.update_status('shutdown', {'restart_count': self.restart_count})

async def main():
    """Main function"""
    manager = MLBotManager()
    manager.setup_signal_handlers()
    
    # Handle command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == 'stop':
            print("Stopping ML-Enhanced Trading Bot...")
            manager.stop_bot()
            return
        elif command == 'status':
            if manager.check_bot_running():
                print("✅ ML-Enhanced Trading Bot is running")
            else:
                print("❌ ML-Enhanced Trading Bot is not running")
            return
        elif command == 'restart':
            print("Restarting ML-Enhanced Trading Bot...")
            manager.stop_bot()
            await asyncio.sleep(3)
    
    # Start monitoring
    await manager.monitor_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot manager stopped by user")
    except Exception as e:
        print(f"❌ Manager error: {e}")
