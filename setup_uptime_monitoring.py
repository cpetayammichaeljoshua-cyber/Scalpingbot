
#!/usr/bin/env python3
"""
Enhanced Setup script for uptime monitoring
Configures external ping services and provides automated setup for various platforms
"""

import os
import requests
import json
import subprocess
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional

class EnhancedUptimeSetup:
    def __init__(self):
        self.repl_name = os.getenv('REPL_SLUG', 'trading-bot')
        self.repl_owner = os.getenv('REPL_OWNER', 'user')
        self.replit_url = f"https://{self.repl_name}.{self.repl_owner}.repl.co"
        
        # Multiple endpoints for different services
        self.endpoints = {
            'health': f"{self.replit_url}/health",
            'ping': f"{self.replit_url}/ping",
            'keepalive': f"{self.replit_url}/keepalive",
            'dashboard': f"{self.replit_url}:8080"
        }
        
        # Ping services configuration
        self.ping_services = [
            {
                'name': 'Kaffeine',
                'url': 'https://kaffeine.herokuapp.com/',
                'endpoint': 'keepalive',
                'interval': '5 minutes',
                'free_tier': True,
                'setup_method': 'manual'
            },
            {
                'name': 'UptimeRobot',
                'url': 'https://uptimerobot.com/',
                'endpoint': 'health',
                'interval': '5 minutes',
                'free_tier': True,
                'monitors_limit': 50,
                'setup_method': 'api'
            },
            {
                'name': 'Pingdom',
                'url': 'https://www.pingdom.com/',
                'endpoint': 'ping',
                'interval': '5 minutes',
                'free_tier': True,
                'monitors_limit': 1,
                'setup_method': 'manual'
            },
            {
                'name': 'StatusCake',
                'url': 'https://www.statuscake.com/',
                'endpoint': 'health',
                'interval': '5 minutes',
                'free_tier': True,
                'monitors_limit': 10,
                'setup_method': 'api'
            },
            {
                'name': 'Freshping',
                'url': 'https://www.freshworks.com/website-monitoring/',
                'endpoint': 'health',
                'interval': '1 minute',
                'free_tier': True,
                'monitors_limit': 50,
                'setup_method': 'manual'
            },
            {
                'name': 'Site24x7',
                'url': 'https://www.site24x7.com/',
                'endpoint': 'health',
                'interval': '5 minutes',
                'free_tier': True,
                'monitors_limit': 5,
                'setup_method': 'manual'
            }
        ]
        
    def print_banner(self):
        """Print enhanced setup banner"""
        print("🚀" + "="*60 + "🚀")
        print("   ENHANCED UPTIME MONITORING SETUP FOR TRADING BOT")
        print("🚀" + "="*60 + "🚀")
        print()
        print(f"📡 Your Repl: {self.repl_name}")
        print(f"👤 Owner: {self.repl_owner}")
        print(f"🌐 URL: {self.replit_url}")
        print()
        
    def test_endpoints(self):
        """Test all endpoints for accessibility"""
        print("🧪 TESTING ENDPOINTS")
        print("-" * 40)
        
        results = {}
        
        for name, url in self.endpoints.items():
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    print(f"   ✅ {name.title()}: Working ({response.status_code})")
                    results[name] = 'working'
                else:
                    print(f"   ⚠️ {name.title()}: Warning ({response.status_code})")
                    results[name] = 'warning'
            except requests.exceptions.Timeout:
                print(f"   ⏱️ {name.title()}: Timeout")
                results[name] = 'timeout'
            except Exception as e:
                print(f"   ❌ {name.title()}: Failed ({str(e)[:50]})")
                results[name] = 'failed'
        
        print()
        return results
    
    def print_service_setup_instructions(self):
        """Print detailed setup instructions for each service"""
        print("🔧 EXTERNAL PING SERVICES SETUP")
        print("=" * 50)
        print()
        
        for i, service in enumerate(self.ping_services, 1):
            print(f"{i}. {service['name'].upper()}")
            print(f"   🌐 URL: {service['url']}")
            print(f"   📡 Endpoint: {self.endpoints[service['endpoint']]}")
            print(f"   ⏰ Interval: {service['interval']}")
            print(f"   💰 Free Tier: {'Yes' if service['free_tier'] else 'No'}")
            
            if 'monitors_limit' in service:
                print(f"   📊 Free Monitors: {service['monitors_limit']}")
            
            print(f"   🛠️ Setup Method: {service['setup_method'].title()}")
            
            # Specific setup instructions
            self._print_specific_instructions(service)
            print()
    
    def _print_specific_instructions(self, service: Dict[str, Any]):
        """Print specific setup instructions for each service"""
        endpoint_url = self.endpoints[service['endpoint']]
        
        if service['name'] == 'Kaffeine':
            print(f"   📝 Instructions:")
            print(f"      1. Visit: {service['url']}")
            print(f"      2. Enter URL: {endpoint_url}")
            print(f"      3. Click 'Submit'")
            print(f"      4. Kaffeine will ping every 30 minutes")
            
        elif service['name'] == 'UptimeRobot':
            print(f"   📝 Instructions:")
            print(f"      1. Create account at: {service['url']}")
            print(f"      2. Go to 'Add New Monitor'")
            print(f"      3. Select 'HTTP(s)'")
            print(f"      4. Enter URL: {endpoint_url}")
            print(f"      5. Set name: 'Trading Bot Health'")
            print(f"      6. Set interval: 5 minutes")
            print(f"   🔧 API Setup (optional):")
            self._print_uptimerobot_api_setup(endpoint_url)
            
        elif service['name'] == 'Pingdom':
            print(f"   📝 Instructions:")
            print(f"      1. Create account at: {service['url']}")
            print(f"      2. Go to 'Synthetics' > 'Add Check'")
            print(f"      3. Select 'Uptime'")
            print(f"      4. Enter URL: {endpoint_url}")
            print(f"      5. Set name: 'Trading Bot Uptime'")
            print(f"      6. Configure alerts")
            
        elif service['name'] == 'StatusCake':
            print(f"   📝 Instructions:")
            print(f"      1. Create account at: {service['url']}")
            print(f"      2. Go to 'Uptime' > 'New Test'")
            print(f"      3. Enter URL: {endpoint_url}")
            print(f"      4. Set test name: 'Trading Bot Monitor'")
            print(f"      5. Set check rate: 5 minutes")
            
        elif service['name'] == 'Freshping':
            print(f"   📝 Instructions:")
            print(f"      1. Create account at: {service['url']}")
            print(f"      2. Go to 'Checks' > 'Add Check'")
            print(f"      3. Select 'HTTP/HTTPS'")
            print(f"      4. Enter URL: {endpoint_url}")
            print(f"      5. Set name: 'Trading Bot Health'")
            print(f"      6. Set interval: 1 minute")
            
        elif service['name'] == 'Site24x7':
            print(f"   📝 Instructions:")
            print(f"      1. Create account at: {service['url']}")
            print(f"      2. Go to 'Website' > 'Add Monitor'")
            print(f"      3. Enter URL: {endpoint_url}")
            print(f"      4. Set name: 'Trading Bot Monitor'")
            print(f"      5. Configure monitoring frequency")
    
    def _print_uptimerobot_api_setup(self, endpoint_url: str):
        """Print UptimeRobot API setup commands"""
        print(f"      curl -X POST https://api.uptimerobot.com/v2/newMonitor \\")
        print(f"        -d 'api_key=YOUR_API_KEY' \\")
        print(f"        -d 'format=json' \\")
        print(f"        -d 'type=1' \\")
        print(f"        -d 'url={endpoint_url}' \\")
        print(f"        -d 'friendly_name=Trading Bot Health' \\")
        print(f"        -d 'interval=300'")
    
    def generate_curl_tests(self):
        """Generate curl commands for testing"""
        print("🔧 TESTING COMMANDS")
        print("-" * 30)
        
        for name, url in self.endpoints.items():
            print(f"# Test {name} endpoint")
            print(f"curl -I {url}")
            print()
    
    def create_monitoring_script(self):
        """Create a local monitoring script"""
        script_content = f'''#!/bin/bash
# Local uptime monitoring script
# Generated on {datetime.now().isoformat()}

ENDPOINTS=(
    "{self.endpoints['health']}"
    "{self.endpoints['ping']}"
    "{self.endpoints['keepalive']}"
)

echo "🔍 Testing Trading Bot Endpoints..."
echo "Time: $(date)"
echo "----------------------------------------"

for endpoint in "${{ENDPOINTS[@]}}"; do
    echo -n "Testing $endpoint: "
    if curl -f -s "$endpoint" > /dev/null; then
        echo "✅ OK"
    else
        echo "❌ FAILED"
    fi
done

echo "----------------------------------------"
'''
        
        script_file = 'monitor_endpoints.sh'
        with open(script_file, 'w') as f:
            f.write(script_content)
        
        # Make executable
        os.chmod(script_file, 0o755)
        
        print(f"📝 Created monitoring script: {script_file}")
        print(f"   Run with: ./{script_file}")
        print()
    
    def create_status_page_html(self):
        """Create a simple status page HTML"""
        html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Bot Status</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
        .status {{ padding: 10px; margin: 10px 0; border-radius: 4px; }}
        .online {{ background: #d4edda; color: #155724; }}
        .offline {{ background: #f8d7da; color: #721c24; }}
        .endpoint {{ font-family: monospace; background: #f8f9fa; padding: 5px; border-radius: 3px; }}
        h1 {{ color: #333; text-align: center; }}
        .last-updated {{ text-align: center; color: #666; font-size: 0.9em; }}
    </style>
    <script>
        async function checkStatus() {{
            const endpoints = [
                {{ name: 'Health Check', url: '{self.endpoints["health"]}' }},
                {{ name: 'Ping', url: '{self.endpoints["ping"]}' }},
                {{ name: 'Keep Alive', url: '{self.endpoints["keepalive"]}' }}
            ];
            
            for (const endpoint of endpoints) {{
                try {{
                    const response = await fetch(endpoint.url);
                    const statusEl = document.getElementById(endpoint.name.replace(' ', ''));
                    if (response.ok) {{
                        statusEl.className = 'status online';
                        statusEl.innerHTML = `✅ ${{endpoint.name}}: Online`;
                    }} else {{
                        statusEl.className = 'status offline';
                        statusEl.innerHTML = `❌ ${{endpoint.name}}: Offline (Status: ${{response.status}})`;
                    }}
                }} catch (error) {{
                    const statusEl = document.getElementById(endpoint.name.replace(' ', ''));
                    statusEl.className = 'status offline';
                    statusEl.innerHTML = `❌ ${{endpoint.name}}: Offline (Error: ${{error.message}})`;
                }}
            }}
            
            document.getElementById('lastUpdated').textContent = `Last updated: ${{new Date().toLocaleString()}}`;
        }}
        
        // Check status on load and every 30 seconds
        window.onload = checkStatus;
        setInterval(checkStatus, 30000);
    </script>
</head>
<body>
    <div class="container">
        <h1>🤖 Trading Bot Status Dashboard</h1>
        
        <div id="HealthCheck" class="status">⏳ Checking Health...</div>
        <div id="Ping" class="status">⏳ Checking Ping...</div>
        <div id="KeepAlive" class="status">⏳ Checking Keep Alive...</div>
        
        <h2>📡 Monitoring Endpoints</h2>
        <p><strong>Health Check:</strong> <span class="endpoint">{self.endpoints["health"]}</span></p>
        <p><strong>Ping:</strong> <span class="endpoint">{self.endpoints["ping"]}</span></p>
        <p><strong>Keep Alive:</strong> <span class="endpoint">{self.endpoints["keepalive"]}</span></p>
        <p><strong>Dashboard:</strong> <span class="endpoint">{self.endpoints["dashboard"]}</span></p>
        
        <div class="last-updated" id="lastUpdated">Checking status...</div>
    </div>
</body>
</html>'''
        
        with open('status_page.html', 'w') as f:
            f.write(html_content)
        
        print("📄 Created status page: status_page.html")
        print(f"   Open in browser or host it online")
        print()
    
    def print_pro_tips(self):
        """Print professional tips for uptime monitoring"""
        print("💡 PRO TIPS FOR UPTIME MONITORING")
        print("=" * 40)
        print()
        print("🎯 Best Practices:")
        print("   • Use multiple services for redundancy")
        print("   • Set up email/SMS alerts for downtime")
        print("   • Monitor response time trends")
        print("   • Check from different geographic locations")
        print("   • Set appropriate timeout values (10-30 seconds)")
        print()
        print("📊 Monitoring Strategy:")
        print("   • Primary: UptimeRobot or Pingdom (reliable)")
        print("   • Backup: Kaffeine (simple, free)")
        print("   • Advanced: StatusCake or Site24x7 (detailed metrics)")
        print()
        print("⚠️ Common Issues:")
        print("   • Cold starts: Replit may sleep after inactivity")
        print("   • Network issues: Temporary connectivity problems")
        print("   • Rate limiting: Don't ping too frequently")
        print("   • SSL certificates: Ensure HTTPS endpoints work")
        print()
        print("🔧 Troubleshooting:")
        print("   • Check logs if endpoints fail")
        print("   • Verify firewall/security settings")
        print("   • Test manually with curl first")
        print("   • Monitor both HTTP and response content")
        print()
    
    def run_setup(self):
        """Run the complete enhanced setup"""
        self.print_banner()
        
        # Test endpoints first
        endpoint_results = self.test_endpoints()
        
        # Print setup instructions
        self.print_service_setup_instructions()
        
        # Generate testing tools
        self.generate_curl_tests()
        self.create_monitoring_script()
        self.create_status_page_html()
        
        # Print pro tips
        self.print_pro_tips()
        
        # Final summary
        print("✅ SETUP COMPLETE!")
        print("=" * 30)
        print()
        print("📋 Next Steps:")
        print("1. Choose 2-3 monitoring services from the list above")
        print("2. Set up accounts and configure monitors")
        print("3. Test your monitors to ensure they work")
        print("4. Configure alert notifications")
        print("5. Run the monitoring script periodically")
        print()
        print(f"🌐 Enhanced Dashboard: {self.endpoints['dashboard']}")
        print(f"📄 Local Status Page: ./status_page.html")
        print(f"🔧 Local Monitor Script: ./monitor_endpoints.sh")
        print()
        print("🎯 Your bot should now stay alive with external pings!")

if __name__ == "__main__":
    setup = EnhancedUptimeSetup()
    setup.run_setup()
