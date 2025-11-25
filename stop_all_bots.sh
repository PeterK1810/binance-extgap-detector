#!/bin/bash
# Stop all external gap indicator bots gracefully

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🛑 Stopping all bots..."

if supervisorctl -c supervisord.conf status > /dev/null 2>&1; then
    supervisorctl -c supervisord.conf stop extgap_bots:*
    sleep 2
    supervisorctl -c supervisord.conf shutdown
    echo "✅ All bots stopped"
else
    echo "⚠️  Supervisord not running"
fi
