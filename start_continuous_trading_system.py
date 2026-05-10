
#!/usr/bin/env python3
"""
Continuous Trading System Startup
Dynamically Perfectly Advanced Flexible Adaptable Comprehensive
Ensures the trading bot runs continuously and pushes trades to the channel
"""

import asyncio
import subprocess
import sys
import os
import time
import signal
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import threading

class ContinuousTradingSystemStarter:
    """Comprehensive startup manager for continuous trading operations"""
    
    def __init__(self):
        self.setup_logging()
        self.processes = {}
        self.running = True
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
    def setup_logging(self):
        """Setup logging system"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - CONTINUOUS_SYSTEM - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_dir / "continuous_trading_system.log"),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"🛑 Received shutdown signal {signum}")
        self.running = False
        self.stop_all_processes()
        sys.exit(0)
    
    def check_prerequisites(self) -> Dict[str, bool]:
        """Check system prerequisites"""
        self.logger.info("🔍 Checking system prerequisites...")
        
        checks = {
            'telegram_token': bool(os.getenv('TELEGRAM_BOT_TOKEN')),
            'telegram_channel': bool(os.getenv('TELEGRAM_CHANNEL_ID')),
            'binance_api_key': bool(os.getenv('BINANCE_API_KEY')),
            'binance_api_secret': bool(os.getenv('BINANCE_API_SECRET')),
            'required_files': True,
            'directories': True
        }
        
        # Check required files
        required_files = [
            'continuous_bot_manager.py',
            'bot_health_monitor.py',
            'SignalMaestro/ultimate_trading_bot.py',
            'start_ultimate_bot.py'
        ]
        
        for file_path in required_files:
            if not Path(file_path).exists():
                self.logger.warning(f"❌ Missing required file: {file_path}")
                checks['required_files'] = False
        
        # Create required directories
        required_dirs = [
            'logs', 'data', 'ml_models', 'backups',
            'SignalMaestro/logs', 'SignalMaestro/ml_models'
        ]
        
        for dir_path in required_dirs:
            try:
                Path(dir_path).mkdir(parents=True, exist_ok=True)
                self.logger.info(f"✅ Directory ensured: {dir_path}")
            except Exception as e:
                self.logger.error(f"❌ Failed to create directory {dir_path}: {e}")
                checks['directories'] = False
        
        # Report results
        passed_checks = sum(checks.values())
        total_checks = len(checks)
        
        self.logger.info(f"📊 Prerequisites: {passed_checks}/{total_checks} passed")
        
        for check, result in checks.items():
            status = "✅" if result else "❌"
            self.logger.info(f"   {status} {check}")
        
        return checks
    
    def start_process(self, name: str, command: List[str], wait_time: int = 5) -> bool:
        """Start a process and track it"""
        try:
            self.logger.info(f"🚀 Starting {name}...")
            self.logger.info(f"📝 Command: {' '.join(command)}")
            
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Wait for process to stabilize
            time.sleep(wait_time)
            
            # Check if process is still running
            if process.poll() is None:
                self.processes[name] = {
                    'process': process,
                    'command': command,
                    'start_time': datetime.now(),
                    'pid': process.pid
                }
                
                self.logger.info(f"✅ {name} started successfully (PID: {process.pid})")
                return True
            else:
                self.logger.error(f"❌ {name} failed to start")
                return False
                
        except Exception as e:
            self.logger.error(f"💥 Error starting {name}: {e}")
            return False
    
    def stop_process(self, name: str) -> bool:
        """Stop a specific process"""
        if name not in self.processes:
            self.logger.info(f"🔍 Process {name} not found")
            return True
        
        try:
            process_info = self.processes[name]
            process = process_info['process']
            
            self.logger.info(f"🛑 Stopping {name} (PID: {process.pid})")
            
            # Try graceful shutdown
            process.terminate()
            
            try:
                process.wait(timeout=10)
                self.logger.info(f"✅ {name} stopped gracefully")
            except subprocess.TimeoutExpired:
                self.logger.warning(f"⏰ {name} graceful shutdown timeout, force killing...")
                process.kill()
                process.wait()
                self.logger.info(f"💥 {name} force killed")
            
            del self.processes[name]
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping {name}: {e}")
            return False
    
    def stop_all_processes(self):
        """Stop all managed processes"""
        self.logger.info("🛑 Stopping all processes...")
        
        for name in list(self.processes.keys()):
            self.stop_process(name)
        
        self.logger.info("✅ All processes stopped")
    
    def monitor_processes(self):
        """Monitor all processes and restart if needed"""
        while self.running:
            try:
                for name, info in list(self.processes.items()):
                    process = info['process']
                    
                    if process.poll() is not None:
                        self.logger.warning(f"⚠️ Process {name} died, restarting...")
                        
                        # Remove dead process
                        del self.processes[name]
                        
                        # Restart process
                        time.sleep(5)
                        self.start_process(name, info['command'])
                
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                self.logger.error(f"Process monitoring error: {e}")
                time.sleep(10)
    
    def start_system(self) -> bool:
        """Start the complete continuous trading system"""
        try:
            self.logger.info("🚀 CONTINUOUS TRADING SYSTEM STARTUP")
            self.logger.info("=" * 80)
            self.logger.info("🎯 Dynamically Perfectly Advanced Flexible Adaptable Comprehensive")
            self.logger.info("🔄 Starting all components for continuous operation")
            self.logger.info("=" * 80)
            
            # Check prerequisites
            prereqs = self.check_prerequisites()
            critical_missing = not all([
                prereqs['required_files'],
                prereqs['directories']
            ])
            
            if critical_missing:
                self.logger.error("💥 Critical prerequisites missing, cannot start system")
                return False
            
            if not prereqs['telegram_token']:
                self.logger.warning("⚠️ TELEGRAM_BOT_TOKEN not set - bot functionality will be limited")
            
            # Start continuous bot manager (primary component)
            self.logger.info("\n🎯 STARTING PRIMARY COMPONENTS")
            self.logger.info("-" * 50)
            
            if not self.start_process(
                "Continuous Bot Manager",
                [sys.executable, "continuous_bot_manager.py"],
                wait_time=10
            ):
                self.logger.error("💥 Failed to start Continuous Bot Manager")
                return False
            
            # Wait for bot manager to fully initialize
            self.logger.info("⏳ Allowing bot manager to initialize...")
            time.sleep(15)
            
            # Start health monitor (secondary component)
            self.logger.info("\n📊 STARTING MONITORING COMPONENTS")
            self.logger.info("-" * 50)
            
            self.start_process(
                "Health Monitor",
                [sys.executable, "bot_health_monitor.py"],
                wait_time=5
            )
            
            # Start keep-alive service (tertiary component)
            self.logger.info("\n🌐 STARTING AUXILIARY SERVICES")
            self.logger.info("-" * 50)
            
            self.start_process(
                "Keep-Alive Service",
                [sys.executable, "keep_alive.py"],
                wait_time=5
            )
            
            # Show startup summary
            self.logger.info("\n" + "=" * 80)
            self.logger.info("🎊 STARTUP COMPLETE - SYSTEM STATUS")
            self.logger.info("=" * 80)
            
            active_processes = len(self.processes)
            self.logger.info(f"🔢 Active Processes: {active_processes}")
            
            for name, info in self.processes.items():
                uptime = (datetime.now() - info['start_time']).total_seconds()
                self.logger.info(f"   ✅ {name} (PID: {info['pid']}, Uptime: {uptime:.1f}s)")
            
            self.logger.info("\n🌟 FEATURES ACTIVE:")
            self.logger.info("   • Continuous bot operation with auto-restart")
            self.logger.info("   • Advanced health monitoring and alerting")
            self.logger.info("   • Keep-alive service for external monitoring")
            self.logger.info("   • Comprehensive error recovery")
            self.logger.info("   • Real-time performance tracking")
            
            self.logger.info("\n🔄 Starting process monitoring loop...")
            
            # Start process monitoring in separate thread
            monitor_thread = threading.Thread(target=self.monitor_processes, daemon=True)
            monitor_thread.start()
            
            # Keep main thread alive and show periodic status
            try:
                while self.running:
                    time.sleep(60)  # Status update every minute
                    
                    active_count = len(self.processes)
                    if active_count > 0:
                        self.logger.info(f"💚 System running normally - {active_count} processes active")
                    else:
                        self.logger.error("🚨 No processes running - system needs restart")
                        break
            
            except KeyboardInterrupt:
                self.logger.info("\n🛑 Manual shutdown requested")
            
            return True
            
        except Exception as e:
            self.logger.error(f"💥 System startup error: {e}")
            return False
        
        finally:
            self.logger.info("🧹 Cleaning up...")
            self.stop_all_processes()
            self.logger.info("✅ Continuous Trading System shutdown complete")
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get current system status"""
        status = {
            'timestamp': datetime.now().isoformat(),
            'system_running': self.running,
            'active_processes': len(self.processes),
            'processes': {}
        }
        
        for name, info in self.processes.items():
            uptime = (datetime.now() - info['start_time']).total_seconds()
            status['processes'][name] = {
                'pid': info['pid'],
                'uptime_seconds': uptime,
                'command': ' '.join(info['command']),
                'running': info['process'].poll() is None
            }
        
        return status

def main():
    """Main entry point"""
    print("🤖 CONTINUOUS TRADING SYSTEM")
    print("=" * 80)
    print("🎯 Dynamically Perfectly Advanced Flexible Adaptable Comprehensive")
    print("🔄 Complete solution for continuous bot operation")
    print("🛡️ Auto-restart, health monitoring, and error recovery")
    print("📊 Real-time performance tracking and alerting")
    print("=" * 80)
    
    starter = ContinuousTradingSystemStarter()
    
    try:
        success = starter.start_system()
        if success:
            print("✅ System startup completed successfully")
        else:
            print("❌ System startup failed")
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
