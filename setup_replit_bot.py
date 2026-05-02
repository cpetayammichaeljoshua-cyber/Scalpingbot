
#!/usr/bin/env python3
"""
Setup script for Perfect Scalping Bot on Replit
Configures environment and validates setup
"""

import os
import sys
import json
from pathlib import Path

def check_environment():
    """Check and validate environment setup"""
    print("🔧 Checking Replit environment...")
    
    # Check Python version
    python_version = sys.version_info
    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 8):
        print(f"❌ Python {python_version.major}.{python_version.minor} detected. Python 3.8+ required.")
        return False
    else:
        print(f"✅ Python {python_version.major}.{python_version.minor}.{python_version.micro} detected")
    
    # Check required environment variables
    required_vars = {
        'TELEGRAM_BOT_TOKEN': 'Telegram bot token from @BotFather',
        'CORNIX_WEBHOOK_URL': 'Cornix webhook URL (optional)',
        'CORNIX_BOT_UUID': 'Cornix bot UUID (optional)'
    }
    
    missing_vars = []
    for var, description in required_vars.items():
        if os.getenv(var):
            print(f"✅ {var} configured")
        else:
            if var == 'TELEGRAM_BOT_TOKEN':
                print(f"❌ {var} missing - {description}")
                missing_vars.append(var)
            else:
                print(f"⚠️ {var} not set - {description}")
    
    if missing_vars:
        print(f"\n❌ Missing required variables: {missing_vars}")
        print("Please set these in the Secrets tab in Replit")
        return False
    
    return True

def create_directories():
    """Create necessary directories"""
    print("📁 Creating directories...")
    
    directories = [
        Path("logs"),
        Path("ml_models"),
        Path("data"),
        Path("SignalMaestro")
    ]
    
    for directory in directories:
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            print(f"✅ Created {directory}")
        else:
            print(f"✅ {directory} already exists")

def create_config_files():
    """Create configuration files"""
    print("⚙️ Creating configuration files...")
    
    # Create .env template if it doesn't exist
    env_file = Path(".env")
    if not env_file.exists():
        env_template = """# Perfect Scalping Bot Configuration
# Set these in Replit Secrets instead

# Required
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Optional Cornix Integration
CORNIX_WEBHOOK_URL=your_cornix_webhook_url_here
CORNIX_BOT_UUID=your_cornix_bot_uuid_here
WEBHOOK_SECRET=your_webhook_secret_here

# Optional API Keys
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_SECRET_KEY=your_binance_secret_key_here
"""
        with open(env_file, 'w') as f:
            f.write(env_template)
        print("✅ Created .env template")
    
    # Create gitignore
    gitignore_file = Path(".gitignore")
    gitignore_content = """# Environment and secrets
.env
*.env
secrets/

# Logs
*.log
logs/

# Database files
*.db
*.sqlite

# Python cache
__pycache__/
*.pyc
*.pyo

# Process files
*.pid
bot_daemon_status.json
bot_status.json

# ML models (can be large)
ml_models/*.pkl
ml_models/*.joblib

# OS generated files
.DS_Store
Thumbs.db
"""
    
    if not gitignore_file.exists():
        with open(gitignore_file, 'w') as f:
            f.write(gitignore_content)
        print("✅ Created .gitignore")

def setup_replit_config():
    """Setup Replit-specific configuration"""
    print("🔧 Setting up Replit configuration...")
    
    # Create replit.nix if needed (for dependencies)
    nix_file = Path("replit.nix")
    if not nix_file.exists():
        nix_content = """{ pkgs }: {
  deps = [
    pkgs.python3
    pkgs.python3Packages.pip
    pkgs.python3Packages.setuptools
  ];
}
"""
        with open(nix_file, 'w') as f:
            f.write(nix_content)
        print("✅ Created replit.nix")

def validate_setup():
    """Validate the complete setup"""
    print("✅ Validating setup...")
    
    # Check if main files exist
    required_files = [
        "SignalMaestro/perfect_scalping_bot.py",
        "SignalMaestro/replit_daemon.py", 
        "start_daemon.py"
    ]
    
    missing_files = []
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"✅ {file_path} exists")
        else:
            print(f"❌ {file_path} missing")
            missing_files.append(file_path)
    
    if missing_files:
        print(f"\n❌ Missing files: {missing_files}")
        return False
    
    print("\n🎉 Setup validation complete!")
    return True

def show_deployment_instructions():
    """Show deployment instructions for Replit"""
    print("""
🚀 **PERFECT SCALPING BOT - REPLIT DEPLOYMENT GUIDE**

**1. Set Environment Variables:**
   Go to Secrets tab in Replit and add:
   - TELEGRAM_BOT_TOKEN: Get from @BotFather
   - CORNIX_WEBHOOK_URL: From Cornix dashboard (optional)
   - CORNIX_BOT_UUID: From Cornix dashboard (optional)

**2. Start the Bot:**
   Click the "Run" button or use:
   ```
   python start_daemon.py
   ```

**3. Monitor the Bot:**
   - Check console output for status
   - Health endpoint: https://your-repl-name.your-username.repl.co/health
   - Status endpoint: https://your-repl-name.your-username.repl.co/status

**4. Telegram Commands:**
   Send /start to your bot in Telegram to begin

**5. Auto-Restart:**
   The daemon automatically restarts if the bot crashes

**6. Cornix Integration:**
   - Set CORNIX_WEBHOOK_URL for automatic trade execution
   - Bot will send signals to Cornix for automated trading
   - SL/TP management is fully automated

**🔧 Troubleshooting:**
   - Check logs in the console
   - Use daemon commands: status, health, restart
   - Verify environment variables in Secrets

**⚡ The bot runs indefinitely on Replit with auto-restart!**
""")

def main():
    """Main setup function"""
    print("🤖 Perfect Scalping Bot - Replit Setup")
    print("=" * 50)
    
    # Run setup steps
    if not check_environment():
        print("\n❌ Environment check failed!")
        return False
    
    create_directories()
    create_config_files()
    setup_replit_config()
    
    if not validate_setup():
        print("\n❌ Setup validation failed!")
        return False
    
    show_deployment_instructions()
    
    print("\n✅ Setup complete! Ready to deploy on Replit.")
    return True

if __name__ == "__main__":
    main()
