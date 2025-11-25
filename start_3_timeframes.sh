#!/bin/bash
# Multi-timeframe launcher for Reserved VM deployment
# Runs 3m, 15m, and 1h trading bots and keeps the main process alive

set -e

cd /home/runner/workspace

echo "=========================================="
echo "External Gap Indicator - Multi-Timeframe Launcher"
echo "=========================================="
echo ""

trap 'echo "Shutting down all bots..."; kill $(jobs -p) 2>/dev/null; exit 0' SIGTERM SIGINT

PIDS=()

mkdir -p logs data

echo "🚀 Starting 3m bot..."
python binance_extgap_indicator_3m.py \
    --symbol BTCUSDT \
    --timeframe 3m \
    --output data/binance_extgap_3m_gaps.csv \
    --trades-output data/binance_extgap_3m_trades.csv \
    >> logs/extgap_indicator_3m.log 2>&1 &
PIDS+=($!)
echo "   Started with PID: ${PIDS[-1]}"
sleep 2

echo "🚀 Starting 15m bot..."
python binance_extgap_indicator_15m.py \
    --symbol BTCUSDT \
    --timeframe 15m \
    --output data/binance_extgap_15m_gaps.csv \
    --trades-output data/binance_extgap_15m_trades.csv \
    >> logs/extgap_indicator_15m.log 2>&1 &
PIDS+=($!)
echo "   Started with PID: ${PIDS[-1]}"
sleep 2

echo "🚀 Starting 1h bot..."
python binance_extgap_indicator_1h.py \
    --symbol BTCUSDT \
    --timeframe 1h \
    --output data/binance_extgap_1h_gaps.csv \
    --trades-output data/binance_extgap_1h_trades.csv \
    >> logs/extgap_indicator_1h.log 2>&1 &
PIDS+=($!)
echo "   Started with PID: ${PIDS[-1]}"

echo ""
echo "=========================================="
echo "✅ All 3 bots launched!"
echo "   PIDs: ${PIDS[*]}"
echo "=========================================="
echo ""
echo "Keeping main process alive to maintain deployment..."
echo "Press Ctrl+C to stop all bots"
echo ""

wait "${PIDS[@]}"

echo "All processes have exited"
