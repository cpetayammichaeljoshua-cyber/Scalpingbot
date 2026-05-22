
#!/usr/bin/env python3
"""
Environment Setup Script for Perfect Scalping Bot
Use this to set up your environment variables securely
"""

def setup_environment():
    """Guide user through setting up environment variables"""
    print("🔐 Perfect Scalping Bot - Environment Setup")
    print("=" * 50)
    print()
    print("To fix the security vulnerabilities, you need to set up environment variables.")
    print("Please use Replit's Secrets tab to add the following:")
    print()
    print("1. TELEGRAM_BOT_TOKEN")
    print("   - Go to @BotFather on Telegram")
    print("   - Create a new bot or use existing one")
    print("   - Copy the bot token")
    print("   - Add it to Replit Secrets with key: TELEGRAM_BOT_TOKEN")
    print()
    print("2. SESSION_SECRET (optional)")
    print("   - Generate a secure random string")
    print("   - Add it to Replit Secrets with key: SESSION_SECRET")
    print()
    print("📱 Steps to add secrets in Replit:")
    print("   1. Click on 'Secrets' tab in the left sidebar")
    print("   2. Click '+ New Secret'")
    print("   3. Enter the key name and value")
    print("   4. Click 'Add Secret'")
    print()
    print("✅ After adding secrets, your bot will be secure and ready to run!")
    print()
    print("🚀 Run the bot with: python SignalMaestro/perfect_scalping_bot.py")

if __name__ == "__main__":
    setup_environment()
