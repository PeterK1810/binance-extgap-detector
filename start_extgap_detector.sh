#!/bin/bash
###############################################################################
# Start Binance External Gap Detector
###############################################################################
#
# Usage:
#   ./start_extgap_detector.sh --version v1|v2 [OPTIONS]
#
# Options:
#   --version v1|v2    Version to run (v1=simple, v2=corrected) [REQUIRED]
#   --symbol SYMBOL    Trading symbol (default: BTCUSDT)
#   --bg               Run in background mode
#   --log-level LEVEL  Logging level (DEBUG|INFO|WARNING|ERROR)
#
# Examples:
#   ./start_extgap_detector.sh --version v1 --bg
#   ./start_extgap_detector.sh --version v2 --symbol ETHUSDT --bg
#   ./start_extgap_detector.sh --version v1 --log-level DEBUG
#
###############################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
VERSION=""
SYMBOL="BTCUSDT"
BACKGROUND=false
LOG_LEVEL="INFO"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --symbol)
            SYMBOL="$2"
            shift 2
            ;;
        --bg|--background)
            BACKGROUND=true
            shift
            ;;
        --log-level)
            LOG_LEVEL="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}Error: Unknown option $1${NC}"
            echo "Usage: $0 --version v1|v2 [--symbol SYMBOL] [--bg] [--log-level LEVEL]"
            exit 1
            ;;
    esac
done

# Validate version
if [[ "$VERSION" != "v1" && "$VERSION" != "v2" ]]; then
    echo -e "${RED}Error: --version is required and must be v1 or v2${NC}"
    echo "Usage: $0 --version v1|v2 [--symbol SYMBOL] [--bg] [--log-level LEVEL]"
    exit 1
fi

# Set script name based on version
if [[ "$VERSION" == "v1" ]]; then
    SCRIPT="binance_extgap_detector_v1_simple.py"
    PID_FILE="binance_extgap_detector_v1.pid"
    VERSION_NAME="Simple Reset Logic"
else
    SCRIPT="binance_extgap_detector_v2_corrected.py"
    PID_FILE="binance_extgap_detector_v2.pid"
    VERSION_NAME="Corrected Reset Logic"
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Binance External Gap Detector - Version $VERSION ($VERSION_NAME)${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

# Check if already running
if [[ -f "$PID_FILE" ]]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Detector version $VERSION is already running (PID: $OLD_PID)${NC}"
        echo -e "${YELLOW}   Stop it first with: ./stop_extgap_detector.sh --version $VERSION${NC}"
        exit 1
    else
        echo -e "${YELLOW}⚠️  Stale PID file found, removing...${NC}"
        rm -f "$PID_FILE"
    fi
fi

# Check if script exists
if [[ ! -f "$SCRIPT" ]]; then
    echo -e "${RED}❌ Error: Script not found: $SCRIPT${NC}"
    exit 1
fi

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Error: python3 not found${NC}"
    exit 1
fi

# Check for virtual environment (optional but recommended)
if [[ -d "../venv" ]]; then
    echo -e "${GREEN}✓${NC} Activating virtual environment..."
    source ../venv/bin/activate
elif [[ -d "venv" ]]; then
    echo -e "${GREEN}✓${NC} Activating virtual environment..."
    source venv/bin/activate
else
    echo -e "${YELLOW}⚠️  No virtual environment found, using system Python${NC}"
fi

# Check required packages
echo -e "${GREEN}✓${NC} Checking dependencies..."
python3 -c "import websockets, aiohttp" 2>/dev/null || {
    echo -e "${RED}❌ Error: Missing required packages${NC}"
    echo -e "   Install with: pip install websockets aiohttp python-dotenv"
    exit 1
}

# Check for .env in parent directory
PARENT_ENV="../.env"
if [[ ! -f "$PARENT_ENV" ]]; then
    echo -e "${YELLOW}⚠️  Warning: .env file not found at $PARENT_ENV${NC}"
    echo -e "${YELLOW}   Telegram notifications may not work${NC}"
fi

# Build command
CMD="python3 $SCRIPT --symbol $SYMBOL --log-level $LOG_LEVEL"

# Start bot
echo -e "${GREEN}✓${NC} Symbol: $SYMBOL"
echo -e "${GREEN}✓${NC} Log level: $LOG_LEVEL"

if [[ "$BACKGROUND" == true ]]; then
    echo -e "${GREEN}✓${NC} Starting in background mode..."
    nohup $CMD > /dev/null 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"

    # Wait a moment and check if still running
    sleep 2
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Detector version $VERSION started successfully (PID: $PID)${NC}"
        echo -e "${BLUE}──────────────────────────────────────────────────────────────${NC}"
        echo -e "   View logs:   tail -f logs/extgap_detector_${VERSION}.log"
        echo -e "   View status: ./status_extgap_detector.sh $VERSION"
        echo -e "   Stop bot:    ./stop_extgap_detector.sh --version $VERSION"
        echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
    else
        echo -e "${RED}❌ Error: Process died immediately after starting${NC}"
        echo -e "   Check logs: tail -f logs/extgap_detector_${VERSION}.log"
        rm -f "$PID_FILE"
        exit 1
    fi
else
    echo -e "${GREEN}✓${NC} Starting in foreground mode (Ctrl+C to stop)..."
    echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
    $CMD
fi
