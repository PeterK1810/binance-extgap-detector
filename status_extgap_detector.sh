#!/bin/bash
###############################################################################
# Check Status of Binance External Gap Detectors
###############################################################################
#
# Usage:
#   ./status_extgap_detector.sh [v1|v2]
#
# Examples:
#   ./status_extgap_detector.sh       # Check all versions
#   ./status_extgap_detector.sh v1    # Check only v1
#   ./status_extgap_detector.sh v2    # Check only v2
#
###############################################################################

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Determine which versions to check
if [[ -n "$1" ]]; then
    if [[ "$1" != "v1" && "$1" != "v2" ]]; then
        echo -e "${RED}Error: Invalid version '$1'. Use v1 or v2${NC}"
        exit 1
    fi
    VERSIONS=("$1")
else
    VERSIONS=("v1" "v2")
fi

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Binance External Gap Detector Status${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

# Function to check version status
check_version() {
    local ver=$1
    local pid_file="binance_extgap_detector_${ver}.pid"
    local log_file="logs/extgap_detector_${ver}.log"
    local csv_file="data/extgap_detector_${ver}_gaps.csv"

    if [[ "$ver" == "v1" ]]; then
        local version_name="Simple Reset Logic"
    else
        local version_name="Corrected Reset Logic"
    fi

    echo -e "\n${CYAN}Version $ver ($version_name)${NC}"
    echo -e "${CYAN}────────────────────────────────────────────────────────────${NC}"

    # Check if running
    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo -e "Status:     ${GREEN}✓ RUNNING${NC} (PID: $pid)"

            # Get process info
            if command -v ps &> /dev/null; then
                local uptime=$(ps -p "$pid" -o etime= | tr -d ' ')
                echo -e "Uptime:     $uptime"

                local cpu=$(ps -p "$pid" -o %cpu= | tr -d ' ')
                local mem=$(ps -p "$pid" -o %mem= | tr -d ' ')
                echo -e "CPU:        ${cpu}%"
                echo -e "Memory:     ${mem}%"
            fi
        else
            echo -e "Status:     ${YELLOW}⚠️  STOPPED${NC} (stale PID file)"
            echo -e "            Remove with: rm $pid_file"
        fi
    else
        echo -e "Status:     ${RED}✗ NOT RUNNING${NC}"
        echo -e "            Start with: ./start_extgap_detector.sh --version $ver --bg"
    fi

    # Check log file
    if [[ -f "$log_file" ]]; then
        local log_size=$(du -h "$log_file" | cut -f1)
        local log_lines=$(wc -l < "$log_file")
        echo -e "Log file:   ${GREEN}✓${NC} $log_file ($log_size, $log_lines lines)"

        # Show last log entry
        if [[ -s "$log_file" ]]; then
            local last_log=$(tail -1 "$log_file" | cut -c1-80)
            echo -e "Last log:   $last_log"
        fi

        # Count recent errors
        local recent_errors=$(tail -100 "$log_file" 2>/dev/null | grep -c "ERROR" || echo "0")
        if [[ $recent_errors -gt 0 ]]; then
            echo -e "Errors:     ${YELLOW}⚠️  $recent_errors errors in last 100 lines${NC}"
        fi
    else
        echo -e "Log file:   ${YELLOW}⚠️  Not found${NC}"
    fi

    # Check CSV file
    if [[ -f "$csv_file" ]]; then
        local csv_lines=$(($(wc -l < "$csv_file") - 1))  # Subtract header
        local csv_size=$(du -h "$csv_file" | cut -f1)
        echo -e "CSV file:   ${GREEN}✓${NC} $csv_file ($csv_size, $csv_lines gaps)"

        if [[ $csv_lines -gt 0 ]]; then
            # Count bullish/bearish gaps
            local bullish=$(grep -c "bullish" "$csv_file" 2>/dev/null || echo "0")
            local bearish=$(grep -c "bearish" "$csv_file" 2>/dev/null || echo "0")
            local reversals=$(grep -c ",True$" "$csv_file" 2>/dev/null || echo "0")

            echo -e "            ⬆️  Bullish: $bullish | ⬇️  Bearish: $bearish | 🔄 Reversals: $reversals"

            # Show last gap
            local last_gap=$(tail -1 "$csv_file")
            if [[ -n "$last_gap" ]]; then
                local last_time=$(echo "$last_gap" | cut -d',' -f1 | cut -d'T' -f2 | cut -d'+' -f1)
                local last_polarity=$(echo "$last_gap" | cut -d',' -f3)
                local last_level=$(echo "$last_gap" | cut -d',' -f4)
                echo -e "Last gap:   $last_time UTC | $last_polarity @ $last_level"
            fi
        fi
    else
        echo -e "CSV file:   ${YELLOW}⚠️  Not found${NC}"
    fi
}

# Check each version
for ver in "${VERSIONS[@]}"; do
    check_version "$ver"
done

echo -e "\n${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}Quick Commands:${NC}"
echo -e "  Start v1:  ./start_extgap_detector.sh --version v1 --bg"
echo -e "  Start v2:  ./start_extgap_detector.sh --version v2 --bg"
echo -e "  Stop v1:   ./stop_extgap_detector.sh --version v1"
echo -e "  Stop v2:   ./stop_extgap_detector.sh --version v2"
echo -e "  Logs v1:   tail -f logs/extgap_detector_v1.log"
echo -e "  Logs v2:   tail -f logs/extgap_detector_v2.log"
echo -e "  Compare:   diff data/extgap_detector_v1_gaps.csv data/extgap_detector_v2_gaps.csv"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
