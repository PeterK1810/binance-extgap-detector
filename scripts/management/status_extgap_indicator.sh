#!/bin/bash
# Check status of Binance External Gap Indicator

# Default values
TIMEFRAME="${1:-5m}"

# Set up paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/binance_extgap_indicator_${TIMEFRAME}.pid"
LOG_FILE="$SCRIPT_DIR/logs/extgap_indicator_${TIMEFRAME}.log"

echo "External Gap Indicator Status ($TIMEFRAME)"
echo "=========================================="

# Check if PID file exists
if [ ! -f "$PID_FILE" ]; then
    echo "Status: NOT RUNNING (no PID file)"
    exit 0
fi

# Read PID
PID=$(cat "$PID_FILE")

# Check if process is running
if ps -p "$PID" > /dev/null 2>&1; then
    echo "Status: RUNNING"
    echo "PID: $PID"

    # Show process details
    echo ""
    echo "Process details:"
    ps -p "$PID" -o pid,ppid,user,%cpu,%mem,etime,cmd

    # Show recent log entries
    if [ -f "$LOG_FILE" ]; then
        echo ""
        echo "Recent log entries (last 10 lines):"
        echo "-----------------------------------"
        tail -n 10 "$LOG_FILE"
    fi
else
    echo "Status: STOPPED (stale PID file)"
    echo "PID file exists but process $PID is not running"
fi

echo ""
echo "Files:"
echo "  PID file: $PID_FILE"
echo "  Log file: $LOG_FILE"
