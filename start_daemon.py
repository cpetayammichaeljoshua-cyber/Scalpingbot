
#!/usr/bin/env python3
"""
Main starter script for Perfect Scalping Bot on Replit
Handles automatic startup and indefinite operation
"""

import os
import sys
import asyncio
import signal
from pathlib import Path

# Add SignalMaestro to path
sys.path.insert(0, str(Path(__file__).parent / "SignalMaestro"))

from replit_daemon import ReplitDaemon

def main():
    """Main entry point for Replit deployment"""
    print("🤖 Perfect Scalping Bot - Replit Deployment")
    print("🔧 Optimized for indefinite operation")
    print("🌐 Starting daemon with keep-alive server...")
    
    # Check for required environment variables
    required_vars = ['TELEGRAM_BOT_TOKEN']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {missing_vars}")
        print("Please set these in the Secrets tab in Replit")
        return
    
    # Initialize and start daemon
    daemon = ReplitDaemon("SignalMaestro/perfect_scalping_bot.py")
    
    try:
        daemon.start_daemon()
    except KeyboardInterrupt:
        print("\n🛑 Shutdown requested")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        return

if __name__ == "__main__":
    main()
