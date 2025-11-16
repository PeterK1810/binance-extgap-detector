#!/bin/bash
# Start Binance External Gap Indicator

set -e

# Default values
TIMEFRAME="5m"
SYMBOL="BTCUSDT"
INSTANCE_ID="${INSTANCE_ID:-LOCAL}"
BACKGROUND=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --timeframe|-t)
            TIMEFRAME="$2"
            shift 2
            ;;
        --symbol|-s)
            SYMBOL="$2"
            shift 2
            ;;
        --instance|-i)
            INSTANCE_ID="$2"
            shift 2
            ;;
        --bg|--background)
            BACKGROUND=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--timeframe 5m] [--symbol BTCUSDT] [--instance LOCAL] [--bg]"
            exit 1
            ;;
    esac
done

# Set up paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/binance_extgap_indicator_${TIMEFRAME}.py"
LOG_FILE="$SCRIPT_DIR/logs/extgap_indicator_${TIMEFRAME}.log"
PID_FILE="$SCRIPT_DIR/binance_extgap_indicator_${TIMEFRAME}.pid"

# Create directories
mkdir -p "$SCRIPT_DIR/data"
mkdir -p "$SCRIPT_DIR/logs"

# Check if script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Error: Script not found: $PYTHON_SCRIPT"
    echo "Using generic script instead..."
    PYTHON_SCRIPT="$SCRIPT_DIR/binance_extgap_indicator_5m.py"
fi

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "External gap indicator ($TIMEFRAME) is already running (PID: $PID)"
        exit 1
    else
        echo "Removing stale PID file"
        rm "$PID_FILE"
    fi
fi

# Activate virtual environment if it exists
if [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    source "$PROJECT_ROOT/venv/bin/activate"
elif [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
else
    echo "Warning: No virtual environment found"
fi

# Export instance ID
export INSTANCE_ID="$INSTANCE_ID"

# Set UTF-8 encoding for Python to handle emojis in Windows
export PYTHONIOENCODING=utf-8

# Start the script
if [ "$BACKGROUND" = true ]; then
    echo "Starting external gap indicator ($TIMEFRAME) in background..."
    nohup python "$PYTHON_SCRIPT" \
        --symbol "$SYMBOL" \
        --timeframe "$TIMEFRAME" \
        --output "data/binance_extgap_${TIMEFRAME}_gaps.csv" \
        --trades-output "data/binance_extgap_${TIMEFRAME}_trades.csv" \
        > "$LOG_FILE" 2>&1 &

    echo $! > "$PID_FILE"
    echo "External gap indicator started (PID: $(cat $PID_FILE))"
    echo "Log file: $LOG_FILE"
    echo "PID file: $PID_FILE"
    echo ""
    echo "To stop: ./stop_extgap_indicator.sh --timeframe $TIMEFRAME"
    echo "To view logs: tail -f $LOG_FILE"
else
    echo "Starting external gap indicator ($TIMEFRAME) in foreground..."
    python "$PYTHON_SCRIPT" \
        --symbol "$SYMBOL" \
        --timeframe "$TIMEFRAME" \
        --output "data/binance_extgap_${TIMEFRAME}_gaps.csv" \
        --trades-output "data/binance_extgap_${TIMEFRAME}_trades.csv"
fi
