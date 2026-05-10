#!/usr/bin/env python3
import subprocess
import json
import time
import requests
from datetime import datetime

def check_processes():
    with open('process_monitoring_config.json', 'r') as f:
        config = json.load(f)
    
    for process_name in config['critical_processes']:
        result = subprocess.run(['pgrep', '-f', process_name], 
                              capture_output=True, text=True)
        
        if not result.stdout.strip():
            print(f"{datetime.now()}: Restarting {process_name}")
            subprocess.Popen(['python', process_name])
    
    # Check health endpoints
    for endpoint in config.get('health_endpoints', []):
        try:
            response = requests.get(endpoint, timeout=5)
            if response.status_code == 200:
                print(f"{datetime.now()}: {endpoint} healthy")
        except:
            print(f"{datetime.now()}: {endpoint} unreachable")

if __name__ == "__main__":
    while True:
        try:
            check_processes()
            time.sleep(30)
        except Exception as e:
            print(f"Monitor error: {e}")
            time.sleep(10)
