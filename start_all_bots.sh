#!/bin/bash
# Master launcher for all external gap indicator bots
# This script is called by Replit's "Run" button

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$WORKSPACE_ROOT"

echo "================================================"
echo "External Gap Indicator - Multi-Bot Launcher"
echo "================================================"
echo ""

# Validate environment
if [ ! -f config/.env ]; then
    echo "❌ ERROR: config/.env file not found"
    exit 1
fi

# Check required Telegram credentials
source config/.env
if [ -z "$TELEGRAM_BOT_TOKEN_EXTGAP_3M" ]; then
    echo "⚠️  WARNING: TELEGRAM_BOT_TOKEN_EXTGAP_3M not set"
fi
if [ -z "$TELEGRAM_BOT_TOKEN_EXTGAP_5M" ]; then
    echo "⚠️  WARNING: TELEGRAM_BOT_TOKEN_EXTGAP_5M not set"
fi
if [ -z "$TELEGRAM_BOT_TOKEN_EXTGAP_15M" ]; then
    echo "⚠️  WARNING: TELEGRAM_BOT_TOKEN_EXTGAP_15M not set"
fi
if [ -z "$TELEGRAM_BOT_TOKEN_EXTGAP_1H" ]; then
    echo "⚠️  WARNING: TELEGRAM_BOT_TOKEN_EXTGAP_1H not set"
fi

# Create directories
mkdir -p data/indicators/gaps data/indicators/trades data/detectors logs/indicators logs/detectors logs/supervisor

# Check if supervisor already running
if supervisorctl -c config/supervisord.conf status > /dev/null 2>&1; then
    echo "✅ Supervisord already running"
    echo ""
    supervisorctl -c config/supervisord.conf status
else
    echo "🚀 Starting supervisord..."
    supervisord -c config/supervisord.conf
    sleep 2
    echo "✅ Supervisord started"
fi

echo ""
echo "📊 Bot Status:"
supervisorctl -c config/supervisord.conf status

echo ""
echo "================================================"
echo "✅ All bots launched successfully!"
echo "================================================"
echo ""
echo "Management Commands:"
echo "  bash scripts/management/status_all_bots.sh      - Check status"
echo "  bash scripts/management/stop_all_bots.sh        - Stop all bots"
echo "  bash scripts/management/restart_bot.sh 3m       - Restart single bot"
echo "  tail -f logs/supervisor/supervisord.log - View supervisor logs"
echo ""
echo "Individual Bot Logs:"
echo "  tail -f logs/indicators/extgap_indicator_3m_stdout.log"
echo "  tail -f logs/indicators/extgap_indicator_5m_stdout.log"
echo "  tail -f logs/indicators/extgap_indicator_15m_stdout.log"
echo "  tail -f logs/indicators/extgap_indicator_1h_stdout.log"
echo ""
