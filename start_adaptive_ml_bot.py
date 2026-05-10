#!/usr/bin/env python3
import os
import sys
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_PATH = os.path.join(BASE_DIR, "SignalMaestro/ml_enhanced_trading_bot.py")

if __name__ == "__main__":
    print("🚀 TradeTactics ML Bot Launching...")
    subprocess.run([sys.executable, BOT_PATH])
