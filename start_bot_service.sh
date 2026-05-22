
#!/bin/bash
# Perfect Scalping Bot Service Startup
# Provides systemd-like functionality for continuous operation

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="perfect-scalping-bot"
PID_FILE="$BOT_DIR/service.pid"
LOG_FILE="$BOT_DIR/service.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

print_status() {
    echo -e "${BLUE}🤖 Perfect Scalping Bot Service${NC}"
    echo "=================================="
}

is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            return 0
        else
            rm -f "$PID_FILE"
            return 1
        fi
    fi
    return 1
}

start_service() {
    if is_running; then
        echo -e "${YELLOW}⚠️ Service is already running${NC}"
        return 1
    fi

    print_status
    echo -e "${GREEN}🚀 Starting service...${NC}"
    
    cd "$BOT_DIR"
    
    # Start daemon in background
    nohup python3 SignalMaestro/bot_daemon.py start >> "$LOG_FILE" 2>&1 &
    DAEMON_PID=$!
    
    # Save PID
    echo $DAEMON_PID > "$PID_FILE"
    
    # Wait and verify startup
    sleep 5
    if is_running; then
        log "✅ Service started successfully (PID: $DAEMON_PID)"
        echo -e "${GREEN}✅ Service started successfully${NC}"
        echo -e "${BLUE}📊 Monitor: tail -f $LOG_FILE${NC}"
        echo -e "${BLUE}🛑 Stop: $0 stop${NC}"
        return 0
    else
        log "❌ Service failed to start"
        echo -e "${RED}❌ Service failed to start${NC}"
        return 1
    fi
}

stop_service() {
    if ! is_running; then
        echo -e "${YELLOW}⚠️ Service is not running${NC}"
        return 1
    fi

    print_status
    echo -e "${YELLOW}🛑 Stopping service...${NC}"
    
    PID=$(cat "$PID_FILE")
    
    # Send termination signal
    kill -TERM "$PID" 2>/dev/null
    
    # Wait for graceful shutdown
    for i in {1..10}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    
    # Force kill if still running
    if kill -0 "$PID" 2>/dev/null; then
        log "⚠️ Forcing service shutdown"
        kill -KILL "$PID" 2>/dev/null
    fi
    
    rm -f "$PID_FILE"
    log "✅ Service stopped"
    echo -e "${GREEN}✅ Service stopped${NC}"
}

restart_service() {
    print_status
    echo -e "${BLUE}🔄 Restarting service...${NC}"
    stop_service
    sleep 3
    start_service
}

status_service() {
    print_status
    
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo -e "${GREEN}✅ Service is running (PID: $PID)${NC}"
        
        # Get daemon status
        if [ -f "bot_daemon_status.json" ]; then
            echo -e "${BLUE}📊 Status Details:${NC}"
            python3 -c "
import json
try:
    with open('bot_daemon_status.json', 'r') as f:
        status = json.load(f)
    print(f\"  Status: {status.get('status', 'unknown')}\")
    print(f\"  Bot PID: {status.get('bot_pid', 'N/A')}\")
    print(f\"  Restarts: {status.get('restart_count', 0)}\")
    if 'uptime_seconds' in status:
        uptime = int(status['uptime_seconds'])
        hours = uptime // 3600
        minutes = (uptime % 3600) // 60
        print(f\"  Uptime: {hours}h {minutes}m\")
except Exception as e:
    print(f\"  Status file error: {e}\")
"
        fi
    else
        echo -e "${RED}❌ Service is not running${NC}"
    fi
}

health_check() {
    print_status
    echo -e "${BLUE}🏥 Performing health check...${NC}"
    
    if is_running; then
        python3 SignalMaestro/bot_daemon.py health
    else
        echo -e "${RED}❌ Service is not running${NC}"
    fi
}

show_logs() {
    LINES=${2:-50}
    echo -e "${BLUE}📋 Recent Logs ($LINES lines):${NC}"
    echo "=" * 50
    
    if [ -f "$LOG_FILE" ]; then
        tail -n "$LINES" "$LOG_FILE"
    else
        echo "No log file found"
    fi
}

case "$1" in
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        status_service
        ;;
    health)
        health_check
        ;;
    logs)
        show_logs "$@"
        ;;
    *)
        echo "🤖 Perfect Scalping Bot Service Manager"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|health|logs}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the bot service"
        echo "  stop    - Stop the bot service"
        echo "  restart - Restart the bot service"
        echo "  status  - Show service status"
        echo "  health  - Perform health check"
        echo "  logs    - Show recent logs (optional: lines count)"
        echo ""
        echo "Examples:"
        echo "  $0 start"
        echo "  $0 logs 100"
        exit 1
        ;;
esac

exit $?
