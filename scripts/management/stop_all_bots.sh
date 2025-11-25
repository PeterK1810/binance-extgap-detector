#!/bin/bash
# Stop all external gap indicator bots gracefully

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$WORKSPACE_ROOT"

echo "🛑 Stopping all bots..."

if supervisorctl -c config/supervisord.conf status > /dev/null 2>&1; then
    supervisorctl -c config/supervisord.conf stop extgap_bots:*
    sleep 2
    supervisorctl -c config/supervisord.conf shutdown
    echo "✅ All bots stopped"
else
    echo "⚠️  Supervisord not running"
fi
