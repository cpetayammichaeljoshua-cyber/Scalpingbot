#!/usr/bin/env python3
import asyncio
import subprocess
import json
import time
from pathlib import Path

async def monitor_continuous_operation():
    while True:
        try:
            # Check if critical processes are running
            with open('continuous_operation_config.json', 'r') as f:
                config = json.load(f)
            
            # Restart signal pusher if needed
            result = subprocess.run(['pgrep', '-f', 'continuous_signal_pusher.py'], 
                                  capture_output=True, text=True)
            
            if not result.stdout.strip():
                print("Restarting continuous signal pusher...")
                subprocess.Popen(['python', 'continuous_signal_pusher.py'])
            
            await asyncio.sleep(config.get('health_check_interval', 60))
            
        except Exception as e:
            print(f"Monitoring error: {e}")
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(monitor_continuous_operation())
