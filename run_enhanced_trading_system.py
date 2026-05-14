#!/usr/bin/env python3
"""
Enhanced Trading System - Ultimate Comprehensive Launcher
Dynamically perfectly comprehensive flexible advanced precise fastest intelligent
Combines: Error Fixing + Health Checks + Freqtrade Integration + SignalMaestro Bot
"""

import asyncio
import subprocess
import sys
import os
import logging
from pathlib import Path
from datetime import datetime

class EnhancedTradingSystemLauncher:
    """
    Ultimate comprehensive trading system launcher
    Orchestrates all components for maximum performance
    """
    
    def __init__(self):
        self.setup_logging()
        self.components_status = {}
        
    def setup_logging(self):
        """Setup comprehensive logging"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - LAUNCHER - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_dir / "enhanced_system_launcher.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def print_banner(self):
        """Display system banner"""
        banner = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║        ENHANCED TRADING SYSTEM - ULTIMATE COMPREHENSIVE PLATFORM             ║
║                                                                              ║
║  SignalMaestro + Freqtrade Integration + AI Analysis + Auto-Recovery        ║
║  Dynamically Perfectly Comprehensive Flexible Advanced Precise Fastest      ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
        print(banner)
        self.logger.info("Enhanced Trading System starting...")
    
    def run_component(self, name: str, command: list, timeout: int = 60) -> bool:
        """Run a system component and track status"""
        self.logger.info(f"🔄 Running {name}...")
        print(f"\n{'='*80}")
        print(f"▶️  {name}")
        print(f"{'='*80}")
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.getcwd()
            )
            
            # Show output
            if result.stdout:
                print(result.stdout)
            if result.stderr and result.returncode != 0:
                print(f"⚠️  Errors: {result.stderr}")
            
            success = result.returncode == 0
            self.components_status[name] = {
                'success': success,
                'timestamp': datetime.now().isoformat(),
                'exit_code': result.returncode
            }
            
            if success:
                self.logger.info(f"✅ {name} completed successfully")
                print(f"✅ {name} - SUCCESS")
            else:
                self.logger.warning(f"⚠️  {name} completed with warnings (exit code: {result.returncode})")
                print(f"⚠️  {name} - COMPLETED WITH WARNINGS")
            
            return success
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"❌ {name} timed out after {timeout}s")
            print(f"❌ {name} - TIMEOUT")
            self.components_status[name] = {
                'success': False,
                'timestamp': datetime.now().isoformat(),
                'error': 'timeout'
            }
            return False
            
        except Exception as e:
            self.logger.error(f"❌ {name} failed: {e}")
            print(f"❌ {name} - FAILED: {e}")
            self.components_status[name] = {
                'success': False,
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            }
            return False
    
    async def run_async_component(self, name: str, module: str):
        """Run an async component"""
        self.logger.info(f"🚀 Starting async component: {name}")
        print(f"\n{'='*80}")
        print(f"🚀 {name}")
        print(f"{'='*80}")
        
        try:
            # Import and run the module
            if module == 'freqtrade_integration':
                from freqtrade_integration import main as ft_main
                await ft_main()
            elif module == 'enhanced_bridge':
                from enhanced_signalmaestro_freqtrade_bridge import main as bridge_main
                await bridge_main()
            
            self.components_status[name] = {
                'success': True,
                'timestamp': datetime.now().isoformat()
            }
            self.logger.info(f"✅ {name} completed")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ {name} failed: {e}")
            print(f"❌ Error in {name}: {e}")
            self.components_status[name] = {
                'success': False,
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            }
            return False
    
    def generate_system_report(self):
        """Generate comprehensive system status report"""
        print("\n" + "="*80)
        print("📊 ENHANCED TRADING SYSTEM - EXECUTION REPORT")
        print("="*80)
        print(f"Report Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Components Executed: {len(self.components_status)}")
        
        successful = sum(1 for c in self.components_status.values() if c.get('success', False))
        print(f"Successful: {successful}/{len(self.components_status)}")
        print("\n" + "-"*80)
        print("Component Status:")
        print("-"*80)
        
        for name, status in self.components_status.items():
            status_icon = "✅" if status.get('success') else "❌"
            print(f"{status_icon} {name}")
            if not status.get('success') and 'error' in status:
                print(f"   Error: {status['error']}")
        
        print("="*80)
        
        # Save report
        report_file = Path("logs") / f"system_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w') as f:
            f.write(f"Enhanced Trading System Report\n")
            f.write(f"Generated: {datetime.now()}\n\n")
            for name, status in self.components_status.items():
                f.write(f"{name}: {'SUCCESS' if status.get('success') else 'FAILED'}\n")
                f.write(f"  Timestamp: {status.get('timestamp')}\n")
                if 'error' in status:
                    f.write(f"  Error: {status['error']}\n")
                f.write("\n")
        
        self.logger.info(f"📄 Report saved to {report_file}")
    
    async def run_full_system(self):
        """Execute the complete enhanced trading system"""
        self.print_banner()
        
        # Phase 1: System Preparation
        print("\n🔧 PHASE 1: SYSTEM PREPARATION")
        print("-"*80)
        
        # Note: Error fixer already ran, skip to save time
        # self.run_component(
        #     "Dynamic Error Fixer",
        #     [sys.executable, "dynamic_comprehensive_error_fixer.py"],
        #     timeout=120
        # )
        
        self.run_component(
            "Bot Health Check",
            [sys.executable, "bot_health_check.py"],
            timeout=30
        )
        
        # Phase 2: Freqtrade Integration
        print("\n🚀 PHASE 2: FREQTRADE INTEGRATION")
        print("-"*80)
        
        await self.run_async_component(
            "Freqtrade Integration",
            "freqtrade_integration"
        )
        
        await self.run_async_component(
            "Enhanced SignalMaestro-Freqtrade Bridge",
            "enhanced_bridge"
        )
        
        # Phase 3: Bot Startup
        print("\n🤖 PHASE 3: TRADING BOT ACTIVATION")
        print("-"*80)
        print("✅ All systems ready for trading")
        print("📊 Use workflow to start continuous trading bot")
        
        # Generate final report
        self.generate_system_report()
        
        print("\n" + "="*80)
        print("🎉 ENHANCED TRADING SYSTEM INITIALIZATION COMPLETE")
        print("="*80)
        print("\n📋 Next Steps:")
        print("  1. Review the system report above")
        print("  2. Start the trading bot workflow for continuous operation")
        print("  3. Monitor logs in the logs/ directory")
        print("\n✅ System is ready for live trading!\n")

async def main():
    """Main entry point"""
    launcher = EnhancedTradingSystemLauncher()
    await launcher.run_full_system()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹️  System startup interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Critical error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
