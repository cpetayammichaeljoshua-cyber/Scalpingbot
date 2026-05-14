
#!/usr/bin/env python3
"""
Automated Enhanced Backtest and Optimization Sequence
Runs comprehensive backtest with advanced features, then applies optimizations
"""

import asyncio
import subprocess
import sys
import os
from pathlib import Path
import time

def run_command(command, description):
    """Run a command and handle output"""
    print(f"\n🔄 {description}...")
    print(f"Command: {command}")
    print("=" * 60)
    
    try:
        # Run the command
        result = subprocess.run(
            command,
            shell=True,
            capture_output=False,  # Show output in real-time
            text=True,
            cwd=Path.cwd()
        )
        
        if result.returncode == 0:
            print(f"✅ {description} completed successfully")
            return True
        else:
            print(f"❌ {description} failed with return code {result.returncode}")
            return False
            
    except Exception as e:
        print(f"❌ Error running {description}: {e}")
        return False

def main():
    """Main sequence runner"""
    
    print("🚀 ENHANCED COMPREHENSIVE BACKTEST & OPTIMIZATION SEQUENCE")
    print("=" * 80)
    print("🎯 This will automatically run:")
    print("   1. Enhanced Comprehensive Backtest with Advanced Features")
    print("   2. Enhanced Bot Optimization based on results")
    print("=" * 80)
    
    start_time = time.time()
    
    # Step 1: Run enhanced comprehensive backtest
    step1_success = run_command(
        "python run_comprehensive_backtest_enhanced.py",
        "Enhanced Comprehensive Backtest with Advanced Features"
    )
    
    if not step1_success:
        print("\n❌ Enhanced backtest failed. Falling back to standard backtest...")
        step1_success = run_command(
            "python run_comprehensive_backtest.py",
            "Standard Comprehensive Backtest (Fallback)"
        )
    
    if not step1_success:
        print("\n💥 Both enhanced and standard backtests failed!")
        print("Please check your configuration and try again.")
        return 1
    
    print(f"\n⏱️ Backtest completed. Waiting 2 seconds before optimization...")
    time.sleep(2)
    
    # Step 2: Run enhanced bot optimization
    step2_success = run_command(
        "python enhance_bot_from_backtest_enhanced.py",
        "Enhanced Bot Optimization with Advanced Analytics"
    )
    
    if not step2_success:
        print("\n❌ Enhanced optimization failed. Falling back to standard optimization...")
        step2_success = run_command(
            "python enhance_bot_from_backtest.py",
            "Standard Bot Optimization (Fallback)"
        )
    
    # Calculate total execution time
    total_time = time.time() - start_time
    
    print("\n" + "=" * 80)
    print("📊 ENHANCED BACKTEST & OPTIMIZATION SEQUENCE RESULTS")
    print("=" * 80)
    
    if step1_success and step2_success:
        print("🎉 SEQUENCE COMPLETED SUCCESSFULLY!")
        print(f"⏱️ Total execution time: {total_time:.1f} seconds")
        print("\n📋 Generated Files:")
        
        files_to_check = [
            "ENHANCED_COMPREHENSIVE_BACKTEST_REPORT.md",
            "COMPREHENSIVE_BACKTEST_REPORT.md", 
            "ENHANCED_BOT_OPTIMIZATION_REPORT.md",
            "BOT_ENHANCEMENT_REPORT.md",
            "enhanced_optimized_bot_config.json",
            "optimized_bot_config.json"
        ]
        
        for file_name in files_to_check:
            file_path = Path(file_name)
            if file_path.exists():
                print(f"   ✅ {file_name}")
            else:
                print(f"   ❌ {file_name} (not found)")
        
        print("\n🚀 ENHANCED TRADING BOT READY!")
        print("=" * 80)
        print("🎯 Key Features Enabled:")
        print("   • Advanced Price Action Analysis")
        print("   • Advanced Liquidity & Engineered Liquidity Detection")
        print("   • Advanced Timing & Sequential Move Optimization") 
        print("   • Advanced Schelling Points Identification")
        print("   • Advanced Order Flow Analysis")
        print("   • Advanced Strategic Positioning")
        print("   • Dynamic 3-Level Stop Loss System")
        print("   • Dynamic Leverage Optimization (10x-75x)")
        print("\n📊 Backtest Configuration:")
        print("   • Capital: $10 USD")
        print("   • Risk: 10% per trade") 
        print("   • Max Trades: 3 concurrent")
        print("   • Market: Binance Futures USDM")
        print("   • Leverage: Dynamic 10x-75x")
        
        print("\n📈 Expected Performance Improvements:")
        print("   • Higher win rate through advanced signal filtering")
        print("   • Better risk-adjusted returns via strategic positioning")
        print("   • Reduced drawdowns with dynamic stop loss system")
        print("   • Optimized leverage utilization for maximum efficiency")
        print("   • Enhanced timing with session and liquidity analysis")
        
        return 0
        
    else:
        print("💥 SEQUENCE FAILED!")
        print(f"⏱️ Total execution time: {total_time:.1f} seconds")
        
        if not step1_success:
            print("❌ Backtest phase failed")
        if not step2_success:
            print("❌ Optimization phase failed")
            
        print("\n🔧 Troubleshooting:")
        print("   • Check your Python environment and dependencies")
        print("   • Verify SignalMaestro directory structure")
        print("   • Review error logs in the console output above")
        print("   • Try running individual components manually")
        
        return 1

if __name__ == "__main__":
    print("🌟 Welcome to Enhanced Backtest & Optimization Automation")
    print("🔧 Preparing to run advanced backtesting sequence...")
    
    exit_code = main()
    
    if exit_code == 0:
        print("\n🎊 All systems ready! Enhanced trading bot is optimized and ready to trade!")
    else:
        print("\n🚨 Setup incomplete. Please review errors and try again.")
    
    sys.exit(exit_code)
