#!/bin/bash
# Stop Binance External Gap Indicator

set -e

# Default values
TIMEFRAME="5m"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --timeframe|-t)
            TIMEFRAME="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--timeframe 5m]"
            exit 1
            ;;
    esac
done

# Set up paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/binance_extgap_indicator_${TIMEFRAME}.pid"

# Check if PID file exists
if [ ! -f "$PID_FILE" ]; then
    echo "External gap indicator ($TIMEFRAME) is not running (no PID file found)"
    exit 0
fi

# Read PID
PID=$(cat "$PID_FILE")

# Check if process is running
if ! ps -p "$PID" > /dev/null 2>&1; then
    echo "Process $PID is not running (stale PID file)"
    rm "$PID_FILE"
    exit 0
fi

# Stop the process
echo "Stopping external gap indicator ($TIMEFRAME) (PID: $PID)..."
kill -SIGTERM "$PID"

# Wait for process to stop (max 10 seconds)
for i in {1..10}; do
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo "External gap indicator stopped successfully"
        rm "$PID_FILE"
        exit 0
    fi
    sleep 1
done

# Force kill if still running
echo "Process did not stop gracefully, forcing kill..."
kill -SIGKILL "$PID" 2>/dev/null || true
rm "$PID_FILE"
echo "External gap indicator stopped (forced)"
