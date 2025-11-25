#!/bin/bash
# Convenience script to stop all 3 trading bots (3m, 15m, 1h)

set -e

cd /home/runner/workspace

echo "=========================================="
echo "External Gap Indicator - Stop All Bots"
echo "=========================================="
echo ""

# Stop each bot
echo "🛑 Stopping 3m bot..."
./stop_extgap_indicator.sh --timeframe 3m || echo "  (3m bot was not running)"

echo "🛑 Stopping 15m bot..."
./stop_extgap_indicator.sh --timeframe 15m || echo "  (15m bot was not running)"

echo "🛑 Stopping 1h bot..."
./stop_extgap_indicator.sh --timeframe 1h || echo "  (1h bot was not running)"

echo ""
echo "=========================================="
echo "✅ All bots stopped!"
echo "=========================================="
