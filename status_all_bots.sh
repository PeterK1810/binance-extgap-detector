#!/bin/bash
# Check status of all external gap indicator bots

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================"
echo "External Gap Indicator - Bot Status"
echo "================================================"
echo ""

if ! supervisorctl -c supervisord.conf status > /dev/null 2>&1; then
    echo "❌ Supervisord not running"
    exit 1
fi

supervisorctl -c supervisord.conf status

echo ""
echo "Recent log activity:"
echo ""
echo "--- 3M Bot (last 5 lines) ---"
tail -5 logs/extgap_indicator_3m_stdout.log 2>/dev/null || echo "No logs yet"
echo ""
echo "--- 15M Bot (last 5 lines) ---"
tail -5 logs/extgap_indicator_15m_stdout.log 2>/dev/null || echo "No logs yet"
echo ""
echo "--- 1H Bot (last 5 lines) ---"
tail -5 logs/extgap_indicator_1h_stdout.log 2>/dev/null || echo "No logs yet"
echo ""
