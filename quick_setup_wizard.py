
#!/usr/bin/env python3
"""
Quick Setup Wizard
Dynamically perfectly advanced flexible adaptable comprehensive
Interactive wizard for setting up monitoring services
"""

import os
import webbrowser
import time
from datetime import datetime
from typing import Dict, List

class QuickSetupWizard:
    """Interactive setup wizard for monitoring services"""
    
    def __init__(self):
        self.repl_name = os.getenv('REPL_SLUG', 'workspace')
        self.repl_owner = os.getenv('REPL_OWNER', 'carlotayam18')
        self.base_url = f"https://{self.repl_name}.{self.repl_owner}.repl.co"
        
        self.endpoints = {
            'keepalive': f"{self.base_url}/keepalive",
            'health': f"{self.base_url}/health", 
            'ping': f"{self.base_url}/ping",
            'status': f"{self.base_url}/status"
        }
        
        self.services = {
            'kaffeine': {
                'name': 'Kaffeine',
                'url': 'https://kaffeine.herokuapp.com/',
                'difficulty': 'Easy',
                'signup': False,
                'endpoint': 'keepalive',
                'description': 'Simple, no-signup monitoring'
            },
            'uptimerobot': {
                'name': 'UptimeRobot', 
                'url': 'https://uptimerobot.com/',
                'difficulty': 'Medium',
                'signup': True,
                'endpoint': 'health',
                'description': '50 monitors free, email alerts'
            },
            'freshping': {
                'name': 'Freshping',
                'url': 'https://www.freshworks.com/website-monitoring/',
                'difficulty': 'Easy',
                'signup': True,
                'endpoint': 'status',
                'description': '50 checks free, public status pages'
            }
        }
    
    def show_banner(self):
        """Display wizard banner"""
        print("🧙‍♂️ QUICK MONITORING SETUP WIZARD")
        print("=" * 50)
        print("Dynamically Perfectly Advanced Flexible Adaptable")
        print("Let's get your trading bot monitored in 5 minutes!")
        print()
        print(f"🤖 Your Bot: {self.base_url}")
        print()
    
    def get_user_level(self) -> str:
        """Get user experience level"""
        print("🎯 What's your experience with monitoring services?")
        print("1. 🟢 Beginner (I'm new to this)")
        print("2. 🟡 Intermediate (I've used some before)")  
        print("3. 🔴 Advanced (I want full control)")
        print()
        
        while True:
            choice = input("Choose your level (1-3): ").strip()
            if choice == '1':
                return 'beginner'
            elif choice == '2':
                return 'intermediate'
            elif choice == '3':
                return 'advanced'
            else:
                print("❌ Please choose 1, 2, or 3")
    
    def show_endpoints(self):
        """Display available endpoints"""
        print("📊 AVAILABLE MONITORING ENDPOINTS:")
        print("-" * 40)
        for name, url in self.endpoints.items():
            print(f"🔗 {name.title()}: {url}")
        print()
    
    def setup_beginner(self):
        """Beginner setup flow"""
        print("🟢 BEGINNER SETUP")
        print("-" * 20)
        print("Perfect! Let's start with the simplest option.")
        print()
        print("📋 RECOMMENDATION: Kaffeine")
        print("   ✅ No signup required")
        print("   ✅ 30-second setup")  
        print("   ✅ Keeps your bot awake")
        print("   ✅ Free forever")
        print()
        
        if self.confirm("Start with Kaffeine"):
            self.setup_kaffeine()
            
            print("\n🎉 Great! You now have basic monitoring.")
            print("💡 Pro tip: Consider adding UptimeRobot later for email alerts")
            
            if self.confirm("Want to add UptimeRobot now too"):
                self.setup_uptimerobot()
    
    def setup_intermediate(self):
        """Intermediate setup flow"""
        print("🟡 INTERMEDIATE SETUP")
        print("-" * 20)
        print("Great choice! Let's set up reliable monitoring with alerts.")
        print()
        
        services = ['uptimerobot', 'kaffeine']
        
        for service_key in services:
            service = self.services[service_key]
            print(f"📊 {service['name']}: {service['description']}")
            
            if self.confirm(f"Setup {service['name']}"):
                if service_key == 'kaffeine':
                    self.setup_kaffeine()
                elif service_key == 'uptimerobot':
                    self.setup_uptimerobot()
                print()
    
    def setup_advanced(self):
        """Advanced setup flow"""
        print("🔴 ADVANCED SETUP")
        print("-" * 20)
        print("Excellent! Let's build a comprehensive monitoring system.")
        print()
        
        print("🎯 Advanced features:")
        print("   • Multiple redundant services")
        print("   • Different monitoring intervals")
        print("   • Custom endpoint selection")
        print("   • Advanced alerting")
        print()
        
        for service_key, service in self.services.items():
            print(f"🔧 {service['name']} ({service['difficulty']}): {service['description']}")
            
            if self.confirm(f"Setup {service['name']}"):
                self.setup_service(service_key)
                print()
        
        print("🚀 Advanced tip: Consider GitHub Actions for custom monitoring")
        if self.confirm("Show GitHub Actions setup"):
            self.show_github_actions()
    
    def setup_kaffeine(self):
        """Setup Kaffeine monitoring"""
        print("☕ SETTING UP KAFFEINE")
        print("-" * 25)
        
        endpoint = self.endpoints['keepalive']
        
        print(f"1. Opening: https://kaffeine.herokuapp.com/")
        print(f"2. Copy this URL: {endpoint}")
        print("3. Paste it in the form")
        print("4. Click 'Submit'")
        print()
        
        if self.confirm("Open Kaffeine website now"):
            webbrowser.open('https://kaffeine.herokuapp.com/')
            
            print("📋 INSTRUCTIONS:")
            print(f"   URL to enter: {endpoint}")
            print("   Then click 'Submit'")
            print()
            
            input("✅ Press Enter when you've completed the setup...")
            print("🎉 Kaffeine setup complete!")
    
    def setup_uptimerobot(self):
        """Setup UptimeRobot monitoring"""
        print("🤖 SETTING UP UPTIMEROBOT")
        print("-" * 28)
        
        endpoint = self.endpoints['health']
        
        print("1. Create account at UptimeRobot")
        print("2. Go to 'My Monitors' > 'Add New Monitor'")
        print("3. Select 'HTTP(s)' monitor type")
        print(f"4. Enter URL: {endpoint}")
        print("5. Set name: 'Trading Bot Monitor'")
        print("6. Set interval: 5 minutes")
        print("7. Configure email alerts")
        print()
        
        if self.confirm("Open UptimeRobot website now"):
            webbrowser.open('https://uptimerobot.com/')
            
            print("📋 SETUP DETAILS:")
            print(f"   Monitor URL: {endpoint}")
            print("   Monitor Name: Trading Bot Monitor")
            print("   Interval: 5 minutes")
            print("   Type: HTTP(s)")
            print()
            
            input("✅ Press Enter when you've completed the setup...")
            print("🎉 UptimeRobot setup complete!")
    
    def setup_service(self, service_key: str):
        """Generic service setup"""
        service = self.services[service_key]
        endpoint = self.endpoints[service['endpoint']]
        
        print(f"🔧 SETTING UP {service['name'].upper()}")
        print("-" * (15 + len(service['name'])))
        
        if service_key == 'kaffeine':
            self.setup_kaffeine()
        elif service_key == 'uptimerobot':
            self.setup_uptimerobot()
        elif service_key == 'freshping':
            print("1. Sign up at Freshping")
            print("2. Go to 'Checks' > 'Add Check'")
            print("3. Select 'HTTP/HTTPS' check")
            print(f"4. Enter URL: {endpoint}")
            print("5. Set check name: 'Trading Bot Status'")
            print("6. Set interval: 1 minute")
            print()
            
            if self.confirm("Open Freshping website"):
                webbrowser.open(service['url'])
                print(f"📊 Monitor URL: {endpoint}")
                input("✅ Press Enter when setup is complete...")
    
    def show_github_actions(self):
        """Show GitHub Actions setup"""
        print("🐙 GITHUB ACTIONS MONITORING")
        print("-" * 30)
        print("Automated monitoring using GitHub workflows")
        print()
        
        workflow_content = f'''name: Keep Bot Alive
on:
  schedule:
    - cron: '*/25 * * * *'  # Every 25 minutes
  workflow_dispatch:

jobs:
  keep-alive:
    runs-on: ubuntu-latest
    steps:
    - name: Ping Trading Bot
      run: |
        curl -f "{self.endpoints['keepalive']}" || exit 1
        echo "Bot ping successful at $(date)"
'''
        
        print("📁 Create file: `.github/workflows/keep-alive.yml`")
        print("📝 Content:")
        print(workflow_content)
        print()
        print("✅ Commit and push to GitHub")
        print("🚀 The workflow will run every 25 minutes automatically")
    
    def confirm(self, message: str) -> bool:
        """Get user confirmation"""
        response = input(f"❓ {message}? (y/n): ").lower().strip()
        return response in ['y', 'yes', '1', 'true']
    
    def test_endpoints(self):
        """Test all endpoints"""
        print("🧪 TESTING YOUR ENDPOINTS")
        print("-" * 28)
        
        import requests
        
        for name, url in self.endpoints.items():
            try:
                print(f"Testing {name}... ", end="")
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    print(f"✅ OK ({response.status_code})")
                else:
                    print(f"⚠️ Warning ({response.status_code})")
            except Exception as e:
                print(f"❌ Failed ({str(e)[:30]}...)")
        print()
    
    def show_next_steps(self):
        """Show recommended next steps"""
        print("🎯 NEXT STEPS & RECOMMENDATIONS")
        print("-" * 35)
        print("✅ Your monitoring is now active!")
        print()
        print("📊 Monitor your setup:")
        print(f"   • Dashboard: {self.base_url}:8080") 
        print(f"   • Health check: {self.endpoints['health']}")
        print(f"   • Status page: {self.endpoints['status']}")
        print()
        print("🔔 Recommended actions:")
        print("   • Test your alerts (if configured)")
        print("   • Set up email notifications")
        print("   • Check monitoring logs regularly")
        print("   • Consider adding backup services")
        print()
        print("💡 Pro tips:")
        print("   • Use different intervals for different services")
        print("   • Monitor from multiple geographic locations")
        print("   • Set up both email and SMS alerts")
        print("   • Keep monitoring service credentials secure")
    
    def run_wizard(self):
        """Run the complete setup wizard"""
        try:
            self.show_banner()
            
            # Test endpoints first
            print("🔍 First, let's check if your bot is running...")
            self.test_endpoints()
            
            self.show_endpoints()
            
            # Get user experience level
            level = self.get_user_level()
            print()
            
            # Run appropriate setup flow
            if level == 'beginner':
                self.setup_beginner()
            elif level == 'intermediate':
                self.setup_intermediate()
            else:  # advanced
                self.setup_advanced()
            
            print()
            
            # Final testing and next steps
            if self.confirm("Test endpoints again"):
                self.test_endpoints()
            
            self.show_next_steps()
            
            print("\n🎉 SETUP WIZARD COMPLETE!")
            print("Your trading bot monitoring is now configured.")
            print(f"🤖 Bot URL: {self.base_url}")
            print(f"📅 Setup completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
        except KeyboardInterrupt:
            print("\n\n🛑 Setup wizard cancelled by user")
            print("You can run this wizard again anytime!")
        except Exception as e:
            print(f"\n❌ Setup wizard error: {e}")
            print("Please try running the wizard again")

def main():
    """Main wizard entry point"""
    wizard = QuickSetupWizard()
    wizard.run_wizard()

if __name__ == "__main__":
    main()
