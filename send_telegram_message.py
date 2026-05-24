
import requests
from SignalMaestro.config import Config

def send_telegram_message(token, chat_id, text):
    """Sends a message to a Telegram channel."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error sending message: {e}")
        return None

def main():
    # Load configuration
    config = Config()
    
    # Your bot and channel configuration
    bot_token = config.TELEGRAM_BOT_TOKEN
    channel_id = "@SignalTactics"  # Your channel
    
    # Test message
    message_text = """
🤖 **TradeTactics Bot Test Message**

✅ Bot is connected and working!
📊 Ready to send trading signals to @SignalTactics

This is a test message from your Telegram bot!
    """
    
    print(f"Sending message to channel: {channel_id}")
    print(f"Using bot: TradeTactics_bot")
    
    response = send_telegram_message(bot_token, channel_id, message_text)
    
    if response and response.get('ok'):
        print("✅ Message sent successfully!")
        print(f"Message ID: {response.get('result', {}).get('message_id')}")
    else:
        print("❌ Failed to send message.")
        if response:
            print(f"Error: {response.get('description', 'Unknown error')}")

if __name__ == "__main__":
    main()
