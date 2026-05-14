
#!/bin/bash
# Perfect Scalping Bot Daemon Startup Script
# Starts the bot in background with proper logging and monitoring

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_SCRIPT="$BOT_DIR/SignalMaestro/perfect_scalping_bot.py"
PID_FILE="$BOT_DIR/perfect_scalping_bot.pid"
LOG_FILE="$BOT_DIR/perfect_scalping_bot.log"

echo "🤖 Perfect Scalping Bot Daemon Startup"
echo "========================================"

# Check if bot is already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "❌ Bot is already running with PID $PID"
        exit 1
    else
        echo "🧹 Removing stale PID file"
        rm -f "$PID_FILE"
    fi
fi

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Start bot in background
echo "🚀 Starting Perfect Scalping Bot..."
echo "📁 Working Directory: $BOT_DIR"
echo "📜 Log File: $LOG_FILE"
echo "🆔 PID File: $PID_FILE"

cd "$BOT_DIR"

# Start with nohup for daemon-like behavior
nohup python3 "$BOT_SCRIPT" >> "$LOG_FILE" 2>&1 &
BOT_PID=$!

# Verify startup
sleep 3
if kill -0 "$BOT_PID" 2>/dev/null; then
    echo "✅ Bot started successfully with PID $BOT_PID"
    echo "📊 Monitor logs: tail -f $LOG_FILE"
    echo "🛑 Stop bot: kill $BOT_PID"
    echo "🔍 Check status: python3 process_manager.py status"
else
    echo "❌ Bot failed to start"
    echo "📋 Check logs: cat $LOG_FILE"
    exit 1
fi

echo ""
echo "🛡️ Bot running in daemon mode with auto-restart protection"
echo "⚡ Use Ctrl+C in the original terminal to stop gracefully"
echo "💾 Process management available via process_manager.py"
