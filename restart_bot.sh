#!/bin/bash
# Restart a specific bot

if [ -z "$1" ]; then
    echo "Usage: $0 <timeframe>"
    echo "Example: $0 3m"
    exit 1
fi

TIMEFRAME=$1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🔄 Restarting ${TIMEFRAME} bot..."

if ! supervisorctl -c supervisord.conf status > /dev/null 2>&1; then
    echo "❌ Supervisord not running"
    exit 1
fi

supervisorctl -c supervisord.conf restart "extgap_${TIMEFRAME}"
echo "✅ Bot restarted"
