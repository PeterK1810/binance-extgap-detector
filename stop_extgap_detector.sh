#!/bin/bash
###############################################################################
# Stop Binance External Gap Detector
###############################################################################
#
# Usage:
#   ./stop_extgap_detector.sh --version v1|v2
#   ./stop_extgap_detector.sh --all    # Stop both versions
#
# Examples:
#   ./stop_extgap_detector.sh --version v1
#   ./stop_extgap_detector.sh --version v2
#   ./stop_extgap_detector.sh --all
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
STOP_ALL=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --all)
            STOP_ALL=true
            shift
            ;;
        *)
            echo -e "${RED}Error: Unknown option $1${NC}"
            echo "Usage: $0 --version v1|v2 OR --all"
            exit 1
            ;;
    esac
done

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Function to stop a specific version
stop_version() {
    local ver=$1
    local pid_file="binance_extgap_detector_${ver}.pid"

    echo -e "${BLUE}Stopping detector version $ver...${NC}"

    if [[ ! -f "$pid_file" ]]; then
        echo -e "${YELLOW}⚠️  No PID file found for version $ver ($pid_file)${NC}"
        echo -e "${YELLOW}   Detector may not be running${NC}"
        return 1
    fi

    local pid=$(cat "$pid_file")

    if ! ps -p "$pid" > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Process $pid is not running (stale PID file)${NC}"
        rm -f "$pid_file"
        return 1
    fi

    # Send SIGTERM
    echo -e "${GREEN}✓${NC} Sending SIGTERM to process $pid..."
    kill "$pid"

    # Wait for graceful shutdown (max 5 seconds)
    local count=0
    while ps -p "$pid" > /dev/null 2>&1 && [[ $count -lt 10 ]]; do
        sleep 0.5
        count=$((count + 1))
    done

    # Force kill if still running
    if ps -p "$pid" > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Process didn't stop gracefully, sending SIGKILL...${NC}"
        kill -9 "$pid"
        sleep 1
    fi

    # Clean up PID file
    rm -f "$pid_file"

    if ps -p "$pid" > /dev/null 2>&1; then
        echo -e "${RED}❌ Failed to stop process $pid${NC}"
        return 1
    else
        echo -e "${GREEN}✅ Detector version $ver stopped successfully${NC}"
        return 0
    fi
}

# Main logic
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Stop Binance External Gap Detector${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

if [[ "$STOP_ALL" == true ]]; then
    echo -e "${BLUE}Stopping all detector versions...${NC}"
    stopped=0
    for ver in v1 v2; do
        if stop_version "$ver"; then
            stopped=$((stopped + 1))
        fi
    done
    echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
    if [[ $stopped -eq 0 ]]; then
        echo -e "${YELLOW}⚠️  No detectors were running${NC}"
    else
        echo -e "${GREEN}✅ Stopped $stopped detector(s)${NC}"
    fi
elif [[ -n "$VERSION" ]]; then
    if [[ "$VERSION" != "v1" && "$VERSION" != "v2" ]]; then
        echo -e "${RED}Error: --version must be v1 or v2${NC}"
        exit 1
    fi
    stop_version "$VERSION"
    echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
else
    echo -e "${RED}Error: Must specify --version v1|v2 OR --all${NC}"
    echo "Usage: $0 --version v1|v2 OR --all"
    exit 1
fi
