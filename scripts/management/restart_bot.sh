#!/bin/bash
# Restart a specific bot

if [ -z "$1" ]; then
    echo "Usage: $0 <timeframe>"
    echo "Example: $0 3m"
    exit 1
fi

TIMEFRAME=$1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$WORKSPACE_ROOT"

echo "🔄 Restarting ${TIMEFRAME} bot..."

if ! supervisorctl -c config/supervisord.conf status > /dev/null 2>&1; then
    echo "❌ Supervisord not running"
    exit 1
fi

supervisorctl -c config/supervisord.conf restart "extgap_${TIMEFRAME}"
echo "✅ Bot restarted"
